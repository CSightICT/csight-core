# Policy Corpus v1 Guide

> 이 Corpus는 CSight PoC의 검색·평가를 위해 제작한 합성 정책 Reference이며, 실제 기업
> 정책이나 법률 자문을 의미하지 않는다.

Raw Markdown은 `data/policy_corpus/raw/{tenant}`의 source다. Build는 이를 수정하지 않고
`normalized`, `clauses`, `manifests`, `reports`만 생성한다.

```bash
make build-policy-corpus
make validate-policy-corpus
```

Pipeline은 NFC/공백 정규화, heading/Clause 분할, type/tag enrichment, stable versioned ID,
SHA-256, parent relation, duplicate candidate와 version relation을 검증한다. Exception은 parent
Rule을 참조하며 near duplicate는 삭제하지 않고 보고만 한다. 현재 실측은 2 tenants,
24 documents, 168 clauses, 9 policy types, 48 exceptions, 48 evidence requirements, retired 6이다.
