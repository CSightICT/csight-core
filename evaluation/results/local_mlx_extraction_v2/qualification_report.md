# Local MLX Extraction v2 qualification

Result: **LOCAL_POC structured-output qualified with semantic limitations**.

| Metric | Dev 120 | Sealed Test 40 |
|---|---:|---:|
| Schema / Pydantic valid | 1.0000 | 1.0000 |
| Source quote exact | 1.0000 | 1.0000 |
| Issue type F1 | 0.8649 | 0.8533 |
| Requested action F1 | 0.1538 | 0.1935 |
| Text ambiguity F1 | 0.0930 | 0.1951 |
| Forbidden / injection / reasoning | 0 | 0 |

The profile is suitable for local pipeline smoke and prompt development, not production quality claims.
