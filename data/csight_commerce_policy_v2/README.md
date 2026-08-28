# CSight Commerce 내부 운영규정 v2

> 이 자료는 CSight PoC의 정책 검색과 advisory 평가를 검증하기 위해 만든 완전한 가상 운영규정이다. 실제 기업의 정책, 약관, 법률 자문 또는 운영 관행을 복제하거나 주장하지 않는다.

- 가상 조직: `CSight Commerce`
- 대상 tenant: `csight`
- 문서 버전: `2.0.0`
- ACTIVE typed rule 버전: `2.0.1`
- Known-faulty `2.0.0` rule history는 기존 로컬 DB 검증용이며 clean ingest 대상이 아님
- source type: `SYNTHETIC_REFERENCE`
- 정책 효력: 상담원 검토 경로와 증거 요건을 제안하는 advisory 신호만 생성한다.
- 최종 결정: 인증된 사람 검토자만 기록할 수 있다.

`raw/csight/`에는 사람이 읽는 가상 사내 정책 원문이 있고, `rules/policy_rule_set_v2.json`에는 원문 조항 ID를 참조하는 typed rule blueprint가 있다. 준비 스크립트는 source hash를 다시 계산하여 immutable rule source reference를 만든다.
