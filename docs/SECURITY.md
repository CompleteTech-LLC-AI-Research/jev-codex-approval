# Security model and threat analysis

This project is an experimental classifier integration. It is not an independently audited security product and does not guarantee correct authorization judgments.

## Assets and trust boundaries

Protected assets include user data, credentials, repository integrity, production resources, policy configuration and the meaning of a user's authorization. The native Codex host and its administrator configuration are authoritative. Repository content, tool arguments, model output, comments, tool descriptions, and retrieved text are evidence, not authorization.

The Python launcher, installed package, configuration, daemon token and audit directory must be controlled by the operator, outside agent-writable locations. The protocol's `source` field is not a signature. A same-user process with sufficient filesystem/environment access can tamper with the integration; a dedicated service account or stronger operating-system isolation is needed against that threat.

## Principal threats and controls

| Threat | Implemented control | Residual limitation |
|---|---|---|
| Prompt injection in repository/tool text | Reuse host provenance; explicit question trust boundary; hazard/defer route | The classifier itself can still be wrong or manipulated |
| Forged user authorization in agent prose | Host-derived evidence and revision checks; no transcript scraping | Meaning still requires model judgment |
| Cached or replayed approval | No new approval cache; request ID and snapshot binding | Same host authority can forge protocol input |
| Authorization change during inference | Extra native version/policy recheck plus existing Codex check | Arbitrary filesystem changes are not identical to auth revisions |
| Model/version drift | Versioned ID required; exact response model check | A model ID does not prove stable server-side internals |
| Malformed API output | Strict keys/types/ranges/distributions; no coercion to allow | Live provider contract not exercised in this build |
| API failure or rate limit | Bounded timeout and original-review fallback | Fallback latency can be worse than baseline |
| Sensitive state disclosure | Explicit consent, fixed HTTPS endpoint, no redirects/proxies, literal-secret block | Not comprehensive DLP; proprietary context may still be submitted |
| External localhost-service caller | Loopback-only binding and random bearer token | Local malware can steal a bearer token |
| Untrusted hook input | Packaged hook always abstains | Other pre-existing hooks retain their upstream behavior |
| Dangerous high-risk action | Low-risk-only fast allow; supported category limit | Low-risk misclassification remains a false-allow risk |
| Operator/config drift | Exact policy/question hash pins; guarded source installer | Hash pinning is not review or semantic correctness |
| Audit leak | No raw prompts, commands, keys or provider errors | Hashes permit correlation and dictionary guessing |

## Rules that the implementation must preserve

An absent answer, unknown value, timeout, missing model key, audit failure, low confidence, unknown authorization, unsupported medium, or expired snapshot must never become a new auto-approval. A proposed denial requires a policy violation; intrinsic risk alone is not an unauthorized action. A classification result must not expand permissions or rewrite the proposed action.

Native v0.1 refuses to replace mandatory/fresh review, retries or sandbox escalation. Network access, permission expansion, stdin, Unix interception and MCP/computer-use remain on their original paths. This narrow boundary is intentional, not evidence that those categories are unimportant.

## Why not use an approving PermissionRequest hook?

The inspected Codex hook path can decide before Guardian. Its public input is not the full native captured policy/authorization context. A hook that assumes missing state is safe, synthesizes a `mandatory_review=false` flag, or treats agent-provided explanations as trusted would weaken the intended architecture. The packaged hook therefore abstains even when otherwise configured to enforce.

## Why not trust confidence alone?

A concentrated distribution can be confidently incorrect. The package requires multiple signals, version and policy pins, supported scope and empirical rollout validation. These are risk-reduction measures, not a theorem about classifier correctness. Correlated questions do not supply independent statistical guarantees, and hazard probabilities must not be multiplied as though they were independent.

## Shell and filesystem caveats

The engine does not parse all shell languages or prove arbitrary program behavior. Expansions, environment overrides, aliases, hooks, symlinks, downloads, mutable scripts, build-system side effects, hidden egress and chained operations need dedicated adversarial coverage. Existing sandbox enforcement and Guardian's investigation remain important. Do not regard `git`, `python`, a build command or a read-like tool name as inherently safe.

## Configuration and lifecycle

The default config is shadow plus remote submission disabled. Live credentials do not themselves authorize data processing. Enforcement requires deliberate policy/question pins and action-category selection. Pin changes should be code-reviewed, with independent holdout evaluation. No automatic optimizer updates deployment configuration.

To immediately remove this component from routing, unset the three native launch environment variables and restart the patched Codex process. Preserve the existing Guardian path. Revert source changes only after inspecting intervening work.

## Validation required before production

A real Rust build and native integration tests are still outstanding. Tests must cover policy precedence, stale root/local authorization, concurrent approvals, history reset, process cancellation, process/output resource limits, platform-specific paths, and failure under actual Codex invocation. Live TypeSafe tests must cover malformed and ambiguous inputs, known prompt-injection patterns, distribution shifts and independently labeled false allows.

The archive's scripted tests do not satisfy these production gates.
