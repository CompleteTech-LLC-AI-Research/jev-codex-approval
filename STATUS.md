# Validation status

Built September 20, 2026. The sections below describe the original package-build evidence unless otherwise noted.

## Repository preparation verification

On September 20, 2026, the Windows source-tree test run completed with 71 tests: 68 passed and three POSIX-only permission/symlink checks skipped. The offline replay matched all 24 fixture expectations. Native build and live-model validation remain outstanding. Original build reports are retained as historical evidence.

## Executed successfully

- Python standard-library unit tests, including engine and strict-schema cases.
- Authenticated localhost daemon request/response integration test.
- Python native/hook launcher subprocess tests.
- Audit permission/symlink checks on this POSIX environment.
- Source-transform anchor tests, preserving the original fallback and validation suffix.
- Scripted 24-case routing replay; every case matched its supplied expectation.
- Fixture-based calibration report generation, explicitly not model calibration.

The current authoritative test count and exact output are in `reports/unit-tests.txt`. The release manifest repeats the final count after all checks.

## Written but not natively verified

`adapters/codex-native/jev.rs` and the guarded source installer target the exact inspected Codex commit and blob IDs. The new native parser tests are supplied as source. **The adapter has not been compiled, linted with the upstream Rust toolchain, or run inside a real Codex process in this environment.** Rust/Cargo and the full Codex workspace are not present here.

Source-transform tests exercise known anchors; they are not a substitute for compiling and testing the actual pinned checkout. Any required fix discovered by that build must be reviewed before enforcement.

## Not performed

No TypeSafe API credentials were used. No live model inference was run. No Guardian benchmark or independent semantic safety evaluation was run. No real-world speedup, false-allow guarantee, or production-readiness claim is made. The original package build did not install a package or modify a GitHub repository; repository publication is a separate subsequent step. `RELEASE.json` records that original build.

## Default behavior

The sample configuration uses shadow mode with remote submission disabled. The hook-compatibility adapter always abstains. Native enforced decisions require explicit setup, matching policy/question pins, eligible host context and successful required audit writing. Mandatory/fresh/retry/escalation and unsupported native routes stay with the existing reviewer.
