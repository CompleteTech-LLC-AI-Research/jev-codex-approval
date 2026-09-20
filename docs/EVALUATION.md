# Evaluation protocol

## What was run in this package build

The actual local Python test report is in `reports/unit-tests.txt`. The scripted functional replay is in `reports/functional-replay/`. It supplies predefined model responses to 24 example cases and checks the gate's output. This is a software-routing test, not a JEV capability measurement. Synthetic latency does not predict API or Codex latency.

No live API, Guardian run, native Codex compile, or end-to-end native session was executed. Native Rust parser tests are present as source but are not included in the Python test count.

## Repeat the offline checks

```sh
python -m unittest discover -s tests -t . -v
python benchmarks/run.py
```

The replay output includes all cases and separates allow, deny, defer, invalid responses and unused vectors. Do not discard deferrals to make coverage or accuracy appear better.

## Opt-in live classifier evaluation

```sh
python benchmarks/run.py --live --config /absolute/consented/config.toml --out reports/live-classifier
```

This command sends eligible fixture state to TypeSafe and incurs provider usage. The configuration must explicitly allow remote context, and the environment must supply the API key. Live mode ignores the fixture's `synthetic_response`; expected labels and scripted responses are never included in the state sent to the model.

The example labels are hand-authored demonstrations. They are not an independent safety benchmark. Replace them with a versioned, independently adjudicated dataset before interpreting accuracy or choosing thresholds. Use diverse repositories and realistic user authorization, with explicit target/payload scope, not only isolated command strings.

## Paired Guardian comparison

Collect the original Guardian assessment stream and JEV audit from the same captured actions. Normalize Guardian outcomes into JSONL records:

```json
{"request_id":"actual-review-id","decision":"allow","elapsed_ms":1234.0}
```

Use real review IDs and observed measurements. This is a normalization schema, not a fabricated result. The native adapter retains the Guardian review ID for correlation. If a review has retries or repeated records, select the desired attempt explicitly; the comparator rejects duplicate IDs rather than silently choosing one.

```sh
python benchmarks/compare.py \
  --jev /absolute/jev-audit.jsonl \
  --guardian /absolute/normalized-guardian.jsonl \
  --labels /absolute/independent-labels.jsonl \
  --out reports/paired-comparison.json
```

Independent labels use `request_id` and `label` (`allow` or `deny`). The comparator preserves unpaired IDs and unlabeled counts. It reports agreement separately from error rates and does not treat Guardian as ground truth. The current comparator does not compute a speedup: collect and analyze complete approval/turn latency separately, including dropped, deferred and failed calls.

## Calibration without automatic promotion

```sh
python benchmarks/calibrate.py \
  --calibration-results reports/live-classifier/results.jsonl \
  --out reports/threshold-proposals.json
```

The utility sweeps combined probability/confidence thresholds on saved vectors and writes proposals only. It does not modify TOML. It cannot calibrate semantic accuracy from scripted fixtures; the shipped fixture-calibration report merely demonstrates the report format.

Split data by repository/scenario family before calibration to avoid leakage from near-duplicate commands or contexts. Freeze model version, question hash and effective policy hash before holdout evaluation. Changed policies and unknown categories require new evaluation. Do not keep testing the same holdout while tuning.

## Metrics and denominators

Report automatic coverage over all eligible review attempts, not only successful API calls. Count false allows among proposed allows and unsafe-case acceptance over independently unsafe cases. Report false denials separately from defer. Preserve missing model responses, provider failures, timeouts, malformed answers and audit failures.

Measure end-to-end p50, p95 and p99 latency from approval request to final host outcome, plus provider-only latency, subprocess/context overhead, audit overhead, original Guardian fallback latency and turn completion time. Keep deterministic/cached routes separate because the implementation deliberately leaves them unchanged.

Record model and policy versions, question hash, input sizes, action category, environment/platform, provider error rate and the exact data split. Compute costs from observed token counts and a separately dated pricing source rather than hard-coded “current” prices.

## Interpreting zero errors

For zero observed errors in `n` independent proposed allows, the one-sided exact 95% binomial upper confidence bound is `1 - 0.05^(1/n)`. A handful of successful examples yields a weak bound. Related commands and shared repositories are correlated, so simple independent-trial bounds can be optimistic; use scenario-family analysis or an appropriate clustered procedure as well.

No particular threshold or rollout error budget is certified by this package.
