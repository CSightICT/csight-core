# Sprint 3 — Vision Analysis와 Multimodal Fan-out/Join

## 1. 범위와 상태

- Branch: `feature/sprint-3-vision-analysis`
- Base: `7d63cbb chore: qualify qwen3.8 27b serving on single 4090`
- Migration: `20260826_0004`, previous `20260826_0003`
- 실제 Vision: `MOCK_QUALIFIED`; 외부 GPU Service는 `SKIPPED_EXTERNAL_VISION_NOT_AVAILABLE`
- Commit·Push·PR: 수행하지 않음
- 사용자 소유 `kaputt_best_vision_architecture.md`: 읽기 전용, 수정·Stage하지 않음

이번 Sprint는 Vision evidence analyzer, image별 append-only result, Evidence Snapshot, Text/Vision
fan-out과 Stage 상태 join만 구현한다. Alignment, Policy, Routing, Review, Report, RAG, 학습과
최종 승인은 범위 밖이다.

## 2. 구현 계약

- 두 Pipeline을 유지한다: text-only `1.0.0`, multimodal `1.0.0`.
- Multimodal Start는 AVAILABLE Image를 안정 정렬해 Snapshot하고 Text/Vision Stage와 Outbox
  Event 2개를 원자적으로 생성한다.
- Queue에는 reference ID 6개만 발행한다. Worker가 DB와 bounded private Storage read를 사용한다.
- SHA-256을 검증한 뒤 Vision Port에 안전한 metadata와 bytes를 전달한다.
- Provider-specific pixel geometry와 native class는 Adapter에서 `normalized_xyxy`와 canonical
  taxonomy로 변환한다.
- Vision Result는 이미지별로 저장하며 Raw provider response와 image binary는 저장하지 않는다.
- Run join은 `SUCCEEDED`, `PARTIAL_SUCCESS`, `FAILED`, `RETRY_WAITING` 의미를 ADR-0016대로 계산한다.

## 3. LLM 평가 선행 감사

- Gold/Output taxonomy, 대소문자와 enum은 일치한다. alias/metric 공식 오류는 발견되지 않았다.
- Missing Information은 micro set PRF로 올바르게 계산되며 empty denominator convention은 1.0이다.
- 평가기에는 exact-set match, macro-case F1, label support, empty expected/actual diagnostics를
  추가하고 regression test로 수식을 고정했다.
- 100행 모두 input `requested_action=UNSPECIFIED`이나 Gold는 message에서 7개 action을 추출하도록
  요구한다. Prompt가 input field와 message 추출의 precedence를 정의하지 않아 Action 0.23은
  순수 모델 capability로 해석할 수 없는 evaluation-design ambiguity다.
- Missing Gold support는 DEFECT_LOCATION 15, CUSTOMER_REQUEST 15, DEFECT_TYPE 10,
  ADDITIONAL_DESCRIPTION 10이다. 기존 F1 0.00은 예측 label 부재와 일치하며 수식 버그 증거는 없다.
- Metric bug가 아니고 실제 endpoint도 현재 설정되지 않아 100건 재평가는 수행하지 않았다.
  Prompt 대규모 튜닝은 제외하고 `QUALIFIED_WITH_LIMITATIONS`를 유지한다.

## 4. 검증 체크리스트

- [x] Base Git/회귀 확인과 전용 Branch 생성
- [x] Canonical schema, tri-state quality, normalized bbox validation
- [x] KAPUT native→canonical mapping과 UNKNOWN fallback
- [x] Remote multipart Adapter, timeout/status/schema/geometry 분류
- [x] 10개 deterministic Mock scenario
- [x] Evidence Snapshot, stable ordering, no-image 422 domain error
- [x] Migration previous head→0004와 drift 확인
- [x] PostgreSQL Mock multimodal success/partial/both-fail/retry/duplicate/tenant isolation
- [x] MinIO bounded private read와 digest verification 경로
- [x] Empty DB→Head, downgrade/upgrade isolated lifecycle와 drift 재검증
- [x] Docker image rebuild, migrate, seed, HTTP live text-only/multimodal/partial smoke
- [x] 전체 Ruff/Format/Pyright/Fast/Integration 최종 실행
- [x] 외부 Vision — endpoint/model/sample 미제공으로 `SKIPPED_EXTERNAL_VISION_NOT_AVAILABLE`

최종 결과는 Ruff PASS, Format 167 files, Pyright 0, Fast 328 passed/42 deselected,
Core Integration 36 passed/5 external-vLLM skipped/329 deselected, External Vision 1 skipped/
369 deselected다. Docker 6개 서비스는 Healthy, RabbitMQ ready/unacked는 0, Migration head는
`20260826_0004`이고 drift가 없다.

Live 경로는 text-only `SUCCEEDED`, multimodal 2 Stage/1 Vision Result/1 Detection
`SUCCEEDED`, no-image `422 IMAGE_EVIDENCE_REQUIRED`, Text 성공/Vision permanent failure
`PARTIAL_SUCCESS`를 확인했다. 실제 병렬 fan-out 중 Run CAS 경쟁에서 한 Stage가 고립되는
결함을 발견했고, 다른 Worker가 Run을 이미 `RUNNING`으로 전이한 경우 Stage claim을 유지하도록
수정한 뒤 같은 live partial 경로를 통과했다. 생성한 합성 Case 5개와 Object 4개는 정리했다.

## 5. 미해결과 다음 작업

- 실제 Vision model, health contract, detection quality, threshold calibration은 미검증이다.
- Mock quality는 계약 검증용이며 실제 Provider가 제공하지 않는 품질 값은 `NOT_EVALUATED/null`이다.
- KAPUT mapping은 architecture 참고 계약이며 실제 defect bbox dataset qualification이 아니다.
- Multi-image는 한 Vision Stage 안에서 순차 처리하므로 처리량 측정과 image-level parallelism은 후속이다.
- 다음 작업은 최종 Gate와 live Docker 검증 후 Evidence Alignment의 입력 계약만 설계하는 것이다.
