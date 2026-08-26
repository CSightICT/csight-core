# Evaluation Datasets Guide

모든 record는 합성이며 manifest에 version, split, generator, taxonomy/schema와 content hash를
기록한다.

| Dataset | Dev | Test | Total |
|---|---:|---:|---:|
| LLM Extraction v2 | 120 | 40 | 160 |
| Policy Retrieval v1 | 80 | 40 | 120 |
| Grounded Explanation v1 | 40 | 10 | 50 |
| Prompt Injection v1 | 20 | 10 | 30 |
| Reference Demo v1 | - | - | 10 |

```bash
make build-evaluation-data
make validate-evaluation-data
make evaluate-extraction-v2
make report-reference-data
```

Validation은 clause 존재, tenant isolation, split/count, exact source quote와 injection category를
검사한다. Test split은 Prompt 튜닝에 사용하지 않는다.
