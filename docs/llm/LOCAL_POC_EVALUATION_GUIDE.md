# Local PoC evaluation guide

Run Dev only while tuning:

```bash
make evaluate-local-extraction
make evaluate-local-query-builder
make evaluate-local-grounding
```

Freeze with `scripts/evaluate_local_mlx.py --task TASK --split dev --freeze`. Sealed Test additionally requires `--allow-sealed-test` and refuses a second run when `test_metrics.json` exists. Never tune from Test.

Datasets are Extraction Dev120/Test40, Query Dev80/Test40, Grounding Dev40/Test10, and Injection Dev20/Test10. Results contain normalized predictions and metrics only. Default Query Strategy stays RAW unless the Local LLM improves the same frozen HYBRID retriever consistently.
