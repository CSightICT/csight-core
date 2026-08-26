# Policy RAG Contract (Design-only, not connected)

Sprint 4A는 Prompt와 strict schema만 고정하며 retrieval/index/RAG 실행은 하지 않는다.

`policy_query_builder` `1.0.0`은 Extraction v2, allowlisted Case metadata, as-of date를 받아 query와
filter 후보를 만든다. Tenant는 Application이 주입하고 모델이 생성·변경하지 못한다.

`grounded_policy_explanation` `1.0.0`은 Case summary와 retrieved Clause pack만 입력으로 받아
`applicable_evidence`와 `unresolved_conditions`를 반환한다. 모든 citation ID는 제공된 context에
실제로 있어야 한다. 환불·교환 승인, fraud, seller responsibility와 final decision은 금지한다.

정책 검색·설명은 최종 업무 결정이 아니다. Versioned Policy Evaluator와 Human Review가
결정 권한을 소유한다.
