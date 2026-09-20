//! Opt-in JEV preflight inside the existing synchronous Guardian attempt.
//! Native source adapter for openai/codex c45ea25ffb72d5f7324489d824d0c677283aa0b4.
//! No contributor, sandbox, permission, hook-precedence or approval-cache changes.

use std::path::PathBuf;
use std::process::Stdio;

use codex_guardian_reviewer::GuardianAssessment;
use codex_guardian_reviewer::GuardianReviewOutcome;
use codex_protocol::config_types::ApprovalsReviewer;
use codex_protocol::protocol::GuardianAssessmentOutcome;
use codex_protocol::protocol::GuardianRiskLevel;
use codex_protocol::protocol::GuardianUserAuthorization;
use serde_json::Value;
use tokio::io::AsyncReadExt;
use tokio::io::AsyncWriteExt;
use tokio::time::Instant;
use tokio_util::sync::CancellationToken;

use super::ApprovalRequestReasons;
use super::GuardianApprovalRequest;
use super::GuardianReviewContext;
use super::GuardianReviewOptions;
use crate::context::GuardianReviewEvidence;
use crate::session::session::Session;

const MAX_WIRE_BYTES: u64 = 262_144;
const PREFLIGHT_BUDGET: std::time::Duration = std::time::Duration::from_millis(2_000);

fn absolute_file_env(key: &str) -> Option<PathBuf> {
    let path = PathBuf::from(std::env::var_os(key)?);
    (path.is_absolute() && path.is_file()).then_some(path)
}

fn assessment(response: &Value, request_id: &str) -> Option<GuardianAssessment> {
    if response.get("schema_version")?.as_u64()? != 1
        || response.get("request_id")?.as_str()? != request_id
    {
        return None;
    }
    let outcome = match response.get("decision")?.as_str()? {
        "allow" => GuardianAssessmentOutcome::Allow,
        "deny" => GuardianAssessmentOutcome::Deny,
        _ => return None,
    };
    let risk_level = match response.pointer("/vector/choices/risk/choice")?.as_str()? {
        "low" => GuardianRiskLevel::Low,
        "medium" => GuardianRiskLevel::Medium,
        "high" => GuardianRiskLevel::High,
        "critical" => GuardianRiskLevel::Critical,
        _ => return None,
    };
    // Enforce the low-risk boundary again at the host, independently of Python policy.
    if outcome == GuardianAssessmentOutcome::Allow && risk_level != GuardianRiskLevel::Low {
        return None;
    }
    let user_authorization = match response
        .pointer("/vector/choices/authorization/choice")?
        .as_str()?
    {
        "explicit" => GuardianUserAuthorization::High,
        "within_task" => GuardianUserAuthorization::Medium,
        "absent" => GuardianUserAuthorization::Low,
        "unknown" => GuardianUserAuthorization::Unknown,
        _ => return None,
    };
    if outcome == GuardianAssessmentOutcome::Allow
        && !matches!(user_authorization, GuardianUserAuthorization::High | GuardianUserAuthorization::Medium)
    {
        return None;
    }
    let model = response.pointer("/vector/model")?.as_str()?;
    if model.len() > 64 || !model.starts_with("jev-")
        || !model.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'.')
    {
        return None;
    }
    Some(GuardianAssessment {
        risk_level,
        user_authorization,
        outcome,
        // This is a deterministic summary, not a claimed model-generated explanation.
        rationale: format!("JEV preflight ({model}); typed policy gate. See the correlated JEV audit record {request_id}."),
    })
}

/// None preserves the existing Guardian inference and its failure/user routing.
/// The budget includes evidence preparation, subprocess startup and inference.
#[allow(clippy::too_many_arguments)]
pub(super) async fn review(
    session: &Session,
    context: &GuardianReviewContext,
    request: &GuardianApprovalRequest,
    reasons: &ApprovalRequestReasons,
    options: &GuardianReviewOptions,
    review_id: &str,
    guardian_deadline: Instant,
    cancellation: &CancellationToken,
) -> Option<GuardianReviewOutcome> {
    let python = absolute_file_env("CODEX_JEV_PYTHON")?;
    let launcher = absolute_file_env("CODEX_JEV_LAUNCHER")?;
    let config = absolute_file_env("CODEX_JEV_CONFIG")?;
    if cancellation.is_cancelled()
        || options.require_guardian
        || options.require_synchronous_review
        || reasons.retry.is_some()
    {
        return None;
    }
    match request {
        GuardianApprovalRequest::ExecCommand { sandbox_permissions, .. } => {
            if sandbox_permissions.requires_escalated_permissions() {
                return None;
            }
        }
        GuardianApprovalRequest::ApplyPatch { .. } => {}
        // Network, permissions, stdin, intercepted execs, computer use and MCP remain Guardian-owned.
        GuardianApprovalRequest::WriteStdin { .. }
        | GuardianApprovalRequest::McpToolCall { .. }
        | GuardianApprovalRequest::NetworkAccess { .. }
        | GuardianApprovalRequest::RequestPermissions { .. } => return None,
        #[cfg(unix)]
        GuardianApprovalRequest::Execve { .. } => return None,
    }
    let deadline = std::cmp::min(guardian_deadline, Instant::now() + PREFLIGHT_BUDGET);
    let attempt = async {
        let live = session.get_config().await;
        let requirements = live.config_layer_stack.requirements();
        if requirements.auto_review_required_for_model(&context.model_info.slug)
            || requirements.approvals_reviewer.can_set(&ApprovalsReviewer::User).is_err()
        {
            return None;
        }
        let history = session.conversation_history_snapshot().await;
        let evidence = session.services.thread_extension_data
            .get_or_init(GuardianReviewEvidence::default);
        let local_version = evidence.authorization_version(history.as_ref());
        let root_version = session.services.agent_control
            .root_user_authorization(session.thread_id).await
            .map(|snapshot| snapshot.authorization_version);
        if !local_version.retained_context_complete
            || root_version.is_some_and(|version| !version.retained_context_complete)
        {
            return None;
        }
        // Reuse Codex's selected, managed-policy-aware Guardian prompt, not a copied policy.
        let reviewer = super::review::guardian_review_session_config(session, context).await.ok()?;
        let policy = reviewer.spawn_config.base_instructions.clone()?;
        let items = super::prompt::build_guardian_prompt_items_with_parent_turn(
            session,
            history.as_ref(),
            Some(context),
            reasons.clone(),
            request.clone(),
            super::prompt::GuardianPromptMode::Full,
            /*reviewed_node_repl_evidence_sequence*/ 0,
        ).await.ok()?;
        if !items.context.truncations.is_empty() {
            return None;
        }
        let messages = serde_json::to_value(items.context.into_messages()).ok()?;
        let action = super::approval_request::guardian_approval_request_to_json(request).ok()?;
        let payload = serde_json::json!({
            "schema_version": 1,
            "request_id": review_id,
            "source": "codex-native",
            "action": action,
            "context": {
                "policy": {"guardian_instructions": policy},
                "messages": messages,
                "authorization_revision": format!("{local_version:?}|{root_version:?}"),
            },
            "guards": {
                "context_complete": true,
                "mandatory_review": false,
                "fresh_review": false,
                "retry": false,
                "escalated": false,
                "cancelled": false,
                "authorization_current": true,
            }
        });
        let bytes = serde_json::to_vec(&payload).ok()?;
        if bytes.len() > MAX_WIRE_BYTES as usize {
            return None;
        }
        drop(history);
        let mut child = tokio::process::Command::new(python)
            .arg("-I")
            .arg(&launcher)
            .arg("native")
            .arg("--config")
            .arg(config)
            .current_dir(launcher.parent()?)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .kill_on_drop(true)
            .spawn().ok()?;
        let mut stdin = child.stdin.take()?;
        stdin.write_all(&bytes).await.ok()?;
        drop(stdin);
        let stdout = child.stdout.take()?;
        let mut output = Vec::new();
        stdout.take(MAX_WIRE_BYTES + 1).read_to_end(&mut output).await.ok()?;
        if output.len() > MAX_WIRE_BYTES as usize || !child.wait().await.ok()?.success() {
            return None;
        }
        let response: Value = serde_json::from_slice(&output).ok()?;
        let result = assessment(&response, review_id)?;
        // Additional freshness check for every context mode; the original host check remains too.
        let now_history = session.conversation_history_snapshot().await;
        let now_root = session.services.agent_control
            .root_user_authorization(session.thread_id).await
            .map(|snapshot| snapshot.authorization_version);
        let now_config = super::review::guardian_review_session_config(session, context).await.ok()?;
        let now_live = session.get_config().await;
        let now_requirements = now_live.config_layer_stack.requirements();
        if cancellation.is_cancelled()
            || local_version != evidence.authorization_version(now_history.as_ref())
            || root_version != now_root
            || now_config.spawn_config.base_instructions.as_deref() != Some(policy.as_str())
            || now_requirements.auto_review_required_for_model(&context.model_info.slug)
            || now_requirements.approvals_reviewer.can_set(&ApprovalsReviewer::User).is_err()
        {
            return None;
        }
        Some(GuardianReviewOutcome::Completed(result))
    };
    tokio::select! {
        biased;
        _ = cancellation.cancelled() => None,
        result = tokio::time::timeout_at(deadline, attempt) => result.ok().flatten(),
    }
}

#[cfg(test)]
mod tests {
    use super::assessment;
    use codex_protocol::protocol::GuardianAssessmentOutcome;
    use serde_json::json;

    fn response() -> serde_json::Value {
        json!({"schema_version": 1, "request_id": "review-1", "decision": "allow",
            "vector": {"model": "jev-1.13.0", "choices": {
                "risk": {"choice": "low"}, "authorization": {"choice": "within_task"}
            }}})
    }
    #[test]
    fn jev_accepts_bound_low_risk_answer() {
        assert_eq!(assessment(&response(), "review-1").unwrap().outcome, GuardianAssessmentOutcome::Allow);
    }
    #[test]
    fn jev_rejects_wrong_request() { assert!(assessment(&response(), "another").is_none()); }
    #[test]
    fn jev_rejects_elevated_allow() {
        let mut value = response(); value["vector"]["choices"]["risk"]["choice"] = json!("high");
        assert!(assessment(&value, "review-1").is_none());
    }
    #[test]
    fn jev_abstention_keeps_guardian() {
        let mut value = response(); value["decision"] = json!("defer");
        assert!(assessment(&value, "review-1").is_none());
    }
    #[test]
    fn jev_missing_vector_keeps_guardian() {
        assert!(assessment(&json!({"schema_version":1,"request_id":"review-1","decision":"allow"}), "review-1").is_none());
    }
}
