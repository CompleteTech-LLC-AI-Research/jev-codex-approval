# Operations

## Runtime modes

`off` performs no model call. `shadow` can classify when separately consented and configured, but always proposes `defer` to Codex. `enforce` can propose a result only after the host guards, model/policy/question pins, confidence policy and required audit all pass.

The configuration is loaded for each one-shot launcher invocation. The daemon loads configuration once at startup, so restart it after a deliberate change. Never edit a deployed policy or threshold automatically from calibration output.

## Direct transport

A native review launches the fixed Python adapter with bounded input, output and lifetime. The Python HTTPS call has its own shorter configurable timeout. The native two-second budget includes context building, process startup and validation and is capped by the remaining Guardian deadline.

There are no automatic provider retries in this package's approval path. Rate limits and transient failures defer. The daemon retains circuit-breaker state across requests; a one-shot direct process does not. The current HTTPS client does not promise connection pooling, so measure the complete route rather than assuming transport overhead is negligible.

## Persistent local service

Create a strong random token:

```sh
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Store the resulting value through your normal secret-management mechanism. The service and the native client's environment need the same `JEV_APPROVAL_TOKEN`; it must be at least 32 characters. The TypeSafe key only needs to be in the service environment for this deployment.

Service configuration should have `daemon_url = ""`. Client configuration should set:

```toml
daemon_url = "http://127.0.0.1:8766/review"
daemon_token_env = "JEV_APPROVAL_TOKEN"
```

Both sides require explicit remote-context consent. Both client and service must be in enforce mode with compatible approved policy/question pins before a fast result is accepted. The client reapplies its own model and decision thresholds to a service result, so a less restrictive daemon configuration cannot silently widen the client's gate.

Start the service with:

```sh
export JEV_APPROVAL_CONFIG="/absolute/path/to/service.toml"
# Supply JEV_APPROVAL_TOKEN and TYPESAFE_API_KEY securely in this environment.
sh scripts/start-daemon.sh
```

On Windows:

```powershell
$env:JEV_APPROVAL_CONFIG = "C:\absolute\path\service.toml"
# Supply the two secrets securely in this environment.
.\scripts\start-daemon.ps1
```

The daemon binds only to loopback. Requests require the token, a bounded content length, and the versioned envelope. At most eight socket-handler threads are admitted; overload closes excess connections, which the caller treats as failure and defers. No action-execution endpoint exists.

A token is a bearer capability. A process that can steal the token can submit requests. Loopback HTTP is not an authentication substitute, and same-user process isolation is not supplied. Do not expose this service through a tunnel, reverse proxy or network binding.

## Diagnostics

```sh
python -I /absolute/package/scripts/launcher.py doctor --config /absolute/config.toml
```

The command reports mode, model pin, whether an API key is present, whether a daemon is selected, and whether hashes/audit are configured. It does not print keys or make a live provider call.

A standalone synthetic review is:

```sh
python -m jev_approval review --config /absolute/config.toml < examples/envelope.json
```

The example's synthetic policy hash will not match a native deployment's effective policy unless deliberately approved. Do not approve a synthetic policy hash as a substitute for the real Guardian policy.

## Audit handling

Audit files contain derived identifiers, typed vectors and timing, not raw prompts. Use owner-only local directories and files. Existing overly permissive POSIX files are rejected rather than silently trusted. Single append writes are used; the audit is not a cryptographically tamper-evident or fsync-backed durable ledger. Retain and rotate files using controlled operations while preserving review-ID correlation.

`candidate` is the gate's proposed classification. `decision` is the local engine's proposed host result after rollout restrictions. Neither proves execution. Correlate it with original Codex assessment events and tool outcomes. Audit failure causes abstention when `require_audit = true`; missing records must be counted in evaluations using the host event stream rather than silently ignored.

## Privacy operations

The literal-secret filter is a guardrail, not complete DLP. Eligible state can contain proprietary code and private user text even when no credential pattern matches. Explicit consent to third-party processing is required independently of API authentication. Operator configuration and credentials must remain outside the agent-writable sandbox. Do not use full-access/bypass mode as a way to test this as an enforcement boundary.

## Recovery

Provider outage: keep Codex's original reviewer and do not lower confidence or enable permissive defaults. Model drift: pin and evaluate the new version explicitly. Policy drift: inspect the new effective policy and reapprove only after validation. Changed upstream source: do not bypass the installer checks. Suspected tampering: disable the native launch variables, restart Codex, and inspect host/config/service integrity.
