# Policy Engine v1 Evaluation Guide

The synthetic set at `evaluation/policy_engine_v1/gold.jsonl` contains Dev 80 and sealed Test 40.
It covers satisfied/unsatisfied/missing inputs, mock Vision, absent Alignment, advisory Local LLM
fields, declared action, missing image/reference, high value, multiple/no matches, two tenants,
effective-date boundaries, and prompt text that must remain non-executable.

Run Dev while changing the engine:

```bash
uv run python scripts/evaluate_policy_engine.py --split dev
```

`frozen_profile.json` was created only after Dev passed. The sealed Test was executed once with
`--split test --sealed-test`; the evaluator now refuses another Test run because the artifact
exists. `make evaluate-policy-engine` reruns Dev and verifies the frozen Test artifact without
opening the holdout.

Required gates are 100% selection, rule exact match, condition status, effect F1, summary, source,
version, and deterministic replay, with zero cross-tenant selection, future rule selection, and
forbidden final decisions. These synthetic exactness results validate implementation correctness,
not real enterprise policy quality.
