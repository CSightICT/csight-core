# Policy Ingestion Guide

Sprint 4B ingestion은 검증된 `data/policy_corpus/normalized/policy_documents_v1.jsonl`,
`clauses/policy_clauses_v1.jsonl`, manifest만 읽는다. Raw Markdown과 production 자동 seed는 사용하지
않는다.

```bash
make migrate
make ingest-policy-corpus
make ingest-policy-corpus  # 같은 run 재사용, duplicate 0
make validate-policy-db
```

동일 tenant/document/version의 source hash가 다르면
`POLICY_DOCUMENT_VERSION_CONTENT_MISMATCH`다. 새 의미는 새 version으로 append한다. 적재는
document/clause transaction이고 외부 embedding 호출과 분리된다. 합성 tenant 생성은 local/test
환경에서만 허용된다.

관련 테이블은 ingestion run, immutable document version, clause이며 parent는 같은 tenant의 corpus
clause만 참조할 수 있다. 실패 시 transaction은 rollback되고 기존 성공 corpus/index는 유지된다.
