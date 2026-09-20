# Source register

Inspected September 20, 2026. Public documentation may change; the native integration is deliberately pinned to a specific source revision. The local package's own tests, design decisions and performance hypotheses are not vendor claims.

| ID | Primary source | Used for |
|---|---|---|
| S1 | [TypeSafe introduction](https://docs.typesafe.ai/introduction) | State and typed-decision model description |
| S2 | [TypeSafe API reference](https://docs.typesafe.ai/api) | `/v1/systemone`, request/answer fields and primitive contracts |
| S3 | [TypeSafe models](https://docs.typesafe.ai/models) | Version pin `jev-1.13.0`, aliases, text-only input and documented budgets |
| S4 | [TypeSafe confidence](https://docs.typesafe.ai/confidence) | Choice/Score confidence versus distributions; Noul has no confidence property |
| S5 | [Approval contributor contract](https://github.com/openai/codex/blob/c45ea25ffb72d5f7324489d824d0c677283aa0b4/codex-rs/ext/extension-api/src/contributors/approval_review.rs) | Allow/Reviewed/AskUser meanings |
| S6 | [Guardian routing](https://github.com/openai/codex/blob/c45ea25ffb72d5f7324489d824d0c677283aa0b4/codex-rs/ext/guardian-reviewer/src/routing.rs) | Mandatory/fresh review and cached-evidence route |
| S7 | [Host-bound review request](https://github.com/openai/codex/blob/c45ea25ffb72d5f7324489d824d0c677283aa0b4/codex-rs/core/src/guardian/review_request.rs) | Integration point and existing authorization freshness checks |
| S8 | [Core approval routing](https://github.com/openai/codex/blob/c45ea25ffb72d5f7324489d824d0c677283aa0b4/codex-rs/core/src/tools/approvals.rs) | Hook precedence and reviewer fallback |
| S9 | [Guardian context builder](https://github.com/openai/codex/blob/c45ea25ffb72d5f7324489d824d0c677283aa0b4/codex-rs/core/src/guardian/prompt.rs) | Trusted-user/root evidence and composed review inputs |
| S10 | [Reviewer configuration](https://github.com/openai/codex/blob/c45ea25ffb72d5f7324489d824d0c677283aa0b4/codex-rs/core/src/guardian/reviewer_config.rs) | Rendered effective Guardian base instructions |
| S11 | [Official Codex hooks documentation](https://developers.openai.com/codex/hooks) | Hook input/output and trust-review semantics |
| S12 | [Official configuration reference](https://developers.openai.com/codex/config-reference) | Existing approval/reviewer configuration |
| S13 | [JEV 1.13 limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13) | Need for workload testing rather than general safety assumptions |
| S14 | [Codex contributor instructions](https://github.com/openai/codex/blob/c45ea25ffb72d5f7324489d824d0c677283aa0b4/AGENTS.md) | Scoped `just` tests, formatting and minimal native footprint |
| S15 | [Guardian action serialization](https://github.com/openai/codex/blob/c45ea25ffb72d5f7324489d824d0c677283aa0b4/codex-rs/core/src/guardian/approval_request.rs) | Exact `exec_command` and `apply_patch` action shapes |
| S16 | [TypeSafe Python SDK](https://github.com/typesafe-ai/typesafe-sdk-python) | SDK alternative; runtime package uses direct documented HTTP |

S5, S6 and S8 were inspected in the preceding architecture work and are re-used here alongside fresh inspection of S7, S9, S10, S14 and S15. The chosen source pin is the inspected baseline, not an assertion that it is the latest upstream commit or a release tag.

## Provenance and reproduction

`adapters/codex-native/manifest.json` records the expected original Git blob hashes and native-build status. `MANIFEST.sha256` records this package's file hashes. `reports/` contains actual local test output and explicitly labeled scripted replay results. No test report in this archive represents live TypeSafe, a native Codex build, or a Guardian performance run.
