# Synthetic LLM qualification

`qwen38_qualification_v1.jsonl` contains no customer data. Its 100 cases are
fixed at 40 single-defect, 20 multi-defect, 15 ambiguous-location, 10
no-request, 5 unclear-defect, 5 long/typo/colloquial, and 5 prompt-injection
examples. Every row records the required gold fields; ambiguous rows use
`acceptable_answers` and `manual_review` instead of inventing false precision.

Run from the repository root against an authenticated private endpoint:

```bash
export LLM_BASE_URL='http://private-host:18000/v1'
export LLM_API_KEY='runtime-secret'
uv run python evaluation/llm/evaluate_extraction.py
```

The evaluator prints aggregate metrics only. It does not write prompts, raw
responses, API keys, or reasoning to disk. Qualification requires 100% JSON
schema, Pydantic, and exact-source-quote validity; zero forbidden fields,
prompt-injection violations, and reasoning leakage. Classification metrics are
a synthetic baseline, not a claim about production customer traffic.

Human review must spot-check at least 20 results during qualification and record
only case IDs, pass/fail judgments, and sanitized error categories in the Sprint
2.5 progress document.
