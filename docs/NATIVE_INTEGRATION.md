# Native Codex integration

## Supported baseline and limitations

The source adapter targets only `openai/codex` at `c45ea25ffb72d5f7324489d824d0c677283aa0b4`. It is source-level integration, not a binary plugin or a currently supported upstream `jev` configuration value. The installer does not clone, switch branches, build, or run Codex automatically. It has not been validated by a native build in the package-build environment.

Do not apply it to an arbitrary newer checkout or bypass the blob checks. Review the equivalent interfaces and port deliberately. The pinned repo's `AGENTS.md` is the authority for its development commands. [Source register S14](SOURCES.md)

## 1. Prepare isolated locations

Keep the package, Python interpreter, configuration and audit directory outside any agent-writable workspace. A typical POSIX layout is:

```text
/opt/jev-codex-approval/          operator-managed package
/home/operator/.config/jev/      private configuration
/home/operator/.local/state/jev/ private metadata logs
/home/operator/src/codex/        reviewed native source checkout
```

Use locations appropriate to the machine. Do not copy these paths literally without adapting them. Same-UID processes are not a security boundary; for stronger separation use a dedicated service account and appropriate operating-system controls.

## 2. Review and apply the source transformation

First make an explicit source-control checkpoint in your own checkout. Then, from this package:

```sh
python scripts/install_native.py --repo /absolute/path/to/pinned/codex > native-review.diff
```

Review the diff. The installer checks HEAD and exact original Git blob hashes before producing any change. The diff must show only two modified native files and one new native module. The Python runtime remains outside the Codex repository.

Apply explicitly:

```sh
python scripts/install_native.py --repo /absolute/path/to/pinned/codex --apply > applied-native.diff
```

No commit, push, pull request or remote write is performed. The installer refuses an already-existing `jev.rs`; it does not overwrite an earlier integration or merge unknown changes.

## 3. Build and test before enabling

In the pinned Codex checkout, follow `AGENTS.md`. In particular:

```sh
cd /absolute/path/to/pinned/codex/codex-rs
just test -p codex-core
just fix -p codex-core
just fmt
```

Use the repository's build workflow for the CLI binary. Its instructions also require the complete test suite for core changes after scoped tests; follow the repository's approval convention before running that larger suite. Do not substitute the Python tests for native integration validation.

The new Rust module contains five targeted parser/binding tests. Additional native integration tests are still required for actual context rendering, cancellation while a subprocess is running, authorization changes during a response, required-review policies, background/multi-environment sessions, and each supported operating system. Nothing in the archive claims those integration tests have already passed.

## 4. Create the initially inert config

POSIX example, run from the extracted package:

```sh
mkdir -p "$HOME/.config/jev" "$HOME/.local/state/jev"
chmod 700 "$HOME/.config/jev" "$HOME/.local/state/jev"
cp examples/config.shadow.toml "$HOME/.config/jev/approval.toml"
chmod 600 "$HOME/.config/jev/approval.toml"
```

Set `audit_path` in the file to an absolute path inside the private state directory. Leave `mode = "shadow"`. Review what data may be sent and your organization's processor requirements before changing `allow_remote_context` to `true`.

The config loader refuses a relative path, symlink file, unknown configuration key, floating model alias, arbitrary API endpoint, and—on POSIX—a group/world-writable or differently owned config. Windows deployments need appropriate ACLs; the POSIX mode checks are not an equivalent Windows ACL verifier.

## 5. Connect the reviewed native binary

Set these variables in the environment launching the patched Codex process:

```sh
export CODEX_JEV_PYTHON="/absolute/path/to/python3"
export CODEX_JEV_LAUNCHER="/absolute/path/to/jev-codex-approval/scripts/launcher.py"
export CODEX_JEV_CONFIG="$HOME/.config/jev/approval.toml"
```

For direct TypeSafe requests, supply `TYPESAFE_API_KEY` through your normal secure environment/secret-management method. Do not put a key in a repository, command argument, example file or audit log. For stronger key separation, use the optional daemon described in [OPERATIONS.md](OPERATIONS.md).

The relevant existing Codex configuration is:

```toml
approval_policy = "on-request"
approvals_reviewer = "auto_review"
```

Keep the existing sandbox and permission profile unchanged. These options select the existing review route; they do not add `jev` as an upstream reviewer name. Existing administrator requirements can restrict them. [Source register S12](SOURCES.md)

On Windows, set the same three environment variables to absolute paths, using the actual `python.exe`. The Rust launcher passes separate arguments and uses Python isolated mode; it does not concatenate the proposed action into a shell command. The PowerShell daemon launcher is included, but native Windows behavior still needs a real build/test.

## 6. Shadow and enforce deliberately

Shadow mode records JEV's candidate while preserving Guardian's final decision. Unsupported, mandatory, retry and escalation paths do not become candidates in the native v0.1 adapter. The Python engine's required-audit rule makes an unset/unwritable audit path an abstention.

To progress to enforcement, first validate a frozen workload with independent labels. Add the observed effective `policy_hash` to `approved_policy_hashes`. Review the question set and set `approved_question_hash` to the output of:

```sh
python -m jev_approval questions
```

Only after those checks should `mode` change to `enforce`. Keep `enable_fast_deny = false` until denial quality is separately tested. `examples/config.enforce.template.toml` deliberately contains invalid placeholders to prevent accidental activation.

## Rollback

Remove `CODEX_JEV_PYTHON`, `CODEX_JEV_LAUNCHER` and `CODEX_JEV_CONFIG` from the Codex launch environment and restart Codex. Without those variables, the source adapter does not start a process and the original review route remains.

To remove the source changes, review `git diff` first. Use the recorded patch with `git apply --check -R applied-native.diff`, then reverse it only if it still applies to the exact changes. Do not blindly restore whole files after unrelated work has accumulated. The hook installer has its own explicit `--remove --apply` option and never needs to be installed for native integration.
