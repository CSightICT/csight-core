# Local MLX Extraction v2 error analysis

- Selected prompt: `2.0.0-local.2` after Dev-only comparison.
- Rejected `local.1`: 85/120 structured successes; 35 invalid outputs.
- Rejected 10-record `local.3` screen: 6/10 structured successes and p95 30.061 s.
- Selected Dev/Test structural validity and exact source quotes: 100%.
- Main limitation: requested-action recall is 0.0833 Dev and 0.1071 Test; ambiguity recall is 0.0833 Dev and 0.1667 Test. The model is conservative and omits explicit actions/ambiguities.
- No invalid output was repaired and no raw provider response or reasoning was retained.
