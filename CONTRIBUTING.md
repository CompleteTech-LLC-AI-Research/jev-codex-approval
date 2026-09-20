# Development

Use Python 3.11 or newer. Keep runtime dependencies minimal and all failure paths abstaining. Run:

```sh
python -m unittest discover -s tests -t . -v
python benchmarks/run.py
```

Every schema change needs invalid/missing/ambiguous-input tests. Every routing change needs tests proving required-review and shadow behavior are preserved. Never add a success-shaped fallback for model or transport errors. Do not log raw context, provider error bodies or secrets.

Changes to `questions.py` change the question hash and must invalidate deployment approval. Changes to model, policy, scope or thresholds need fresh independent calibration/holdout evaluation. Benchmarks must clearly distinguish scripted fixtures, live model runs and real native integration results.

For native work, follow the pinned Codex repository's `AGENTS.md`, use its `just` workflows, and keep the core adapter narrow. Most policy/transport logic stays outside codex-core. Do not change sandbox environment variables or bypass managed reviews. Do not describe source-only validation as a passing native build.
