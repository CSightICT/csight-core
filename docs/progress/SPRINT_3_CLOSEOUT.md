# Sprint 3 Closeout — Vision Analysis와 Multimodal Pipeline

- 일자: 2026-08-26 (Asia/Seoul)
- Branch: `feature/sprint-3-vision-analysis`
- Base: `7d63cbb`
- Commit: `330cbdb feat: complete multimodal vision analysis pipeline`
- Push·PR: 수행하지 않음
- 사용자 소유 `kaputt_best_vision_architecture.md`: 수정·삭제·이동·Stage·Commit하지 않음

## 1. 최종 판정

Sprint 3 구현과 Migration을 실제 코드, 테스트, PostgreSQL, RabbitMQ, MinIO와 Docker Runtime으로
재감사했다. 완료를 막는 P0/P1은 발견되지 않았고 Closeout Gate를 통과했다.

```text
P0_UNRESOLVED=0
P1_UNRESOLVED=0
SPRINT_3_CLOSEOUT=PASS
```

실제 Vision endpoint/model/sample은 제공되지 않아 `MOCK_QUALIFIED`를 유지한다. Mock 계약과
실제 모델 품질을 혼동하지 않으며 외부 Vision 1건은 정확히
`SKIPPED_EXTERNAL_VISION_NOT_AVAILABLE`이다.

## 2. 집중 감사 결과

### Evidence Snapshot

- Multimodal Run 생성 트랜잭션에서 당시 `AVAILABLE` Image Evidence만 안정 정렬해 고정한다.
- Snapshot은 `position`, `evidence_id`, `sha256`을 보존한다.
- Worker는 Case의 현재 Evidence 목록이 아니라 Snapshot만 읽으며 private Storage bounded read
  뒤 SHA-256을 재검증한다.
- Run 생성 후 추가 Evidence가 기존 Run에 들어가지 않는 경계와 Snapshot/Result Evidence
  일치를 Unit·PostgreSQL Integration에서 확인했다.

### Vision append-only

- Evidence Snapshot Repository는 `add/list`, Vision Result Repository는 `add/list_by_run`만
  제공하며 성공 Result/Detection Update·Delete API가 없다.
- `(tenant_id, analysis_run_id, evidence_id)` Result unique와 Result별 detection index unique를
  DB가 강제한다.
- 완료 Stage 재전달은 terminal no-op이고 동일 image Result/Detection을 추가하지 않는다.

### Fan-out / Join

- Multimodal Start는 Text/Vision Stage와 reference-only Outbox Event 두 개를 같은 Transaction에
  생성한다.
- Worker는 DB Stage type으로 독립 Use Case를 선택하며 실행 순서를 가정하지 않는다.
- 동시 `QUEUED→RUNNING` CAS에서 다른 Worker가 Run을 이미 `RUNNING`으로 바꾼 경우 Stage claim을
  유지하는 경쟁 수정이 양 Stage에 적용되어 있다.
- 각 Stage terminal/retry 전이 후 전체 Stage 상태를 DB에서 다시 읽어 Run 상태를 집계한다.

### Partial Success

| Text | Vision | Run |
|---|---|---|
| Success | Success | `SUCCEEDED` |
| Success | Failed | `PARTIAL_SUCCESS` |
| Failed | Success | `PARTIAL_SUCCESS` |
| Failed | Failed | `FAILED` |
| Terminal + Retry | Retry | `RETRY_WAITING` |

성공한 Text/Vision Result는 다른 Stage 실패 또는 재시도에도 보존된다.

### 보안과 Canonical Contract

- Queue Payload는 event/tenant/case/run/stage/correlation 여섯 ID만 허용한다.
- Binary, Base64, Signed URL, object key와 MinIO credential을 Queue/Outbox에 넣지 않는다.
- Vision Provider는 업무 DB/MinIO에 직접 접근하지 않고 Worker가 허용된 bytes와 metadata만
  전달한다.
- Raw Provider JSON은 저장하지 않으며 모든 Repository는 tenant scope와 복합 FK를 사용한다.
- Geometry는 `normalized_xyxy`; confidence와 좌표 범위·순서는 Pydantic과 DB constraint가
  함께 보호한다.
- model-native class와 canonical taxonomy/version을 분리하고 품질의 `NOT_EVALUATED/null`을
  `false`와 구분한다.

### Migration

- 기존 Revision `0001`~`0003`은 수정하지 않았다.
- `20260826_0004`가 Snapshot→Result→Detection을 생성하고 downgrade는
  Detection→Result→Snapshot 역순이다.
- 별도 UUID DB 두 개로 empty→`0004`, `0004→0003→0004`, `0003→0004`와 Alembic drift 0을
  실제 확인한 뒤 임시 DB를 제거했다.

## 3. 실제 검증 원장

| 검사 | 상태 | 실제 결과 |
|---|---|---|
| Ruff | PASS | `All checks passed!` |
| Ruff Format | PASS | 165 files already formatted |
| Pyright strict | PASS | 0 errors, 0 warnings, 0 informations |
| CI-safe Regression | PASS | 328 passed, 42 deselected |
| Unit marker | PASS | 264 passed, 106 deselected |
| Contract marker | PASS | 45 passed, 325 deselected |
| Architecture path | PASS | 4 passed |
| E2E marker | PASS | 6 passed, 1 core-integration skipped, 363 deselected |
| Core Integration | PASS | 36 passed, 5 external-vLLM skipped, 329 deselected |
| External Vision | SKIPPED | 1 skipped, 369 deselected; endpoint 미제공 |
| Migration 세 경로 | PASS | empty/head, round-trip, previous/head |
| Alembic Drift | PASS | 두 격리 DB 모두 no new upgrade operations |
| Docker Health | PASS | API/Worker/Dispatcher/PostgreSQL/RabbitMQ/MinIO 6개 healthy |
| HTTP Health | PASS | live ok, ready의 PostgreSQL/RabbitMQ/MinIO ok |
| RabbitMQ Queue | PASS | `analysis` ready 0, unacked 0 |
| `git diff --check` | PASS | whitespace 오류 0 |

`pytest -m architecture`는 이 저장소에 해당 marker가 없어 370건을 deselect하고 exit 5였다.
코드 실패로 해석하지 않고 표준 경로 `pytest tests/architecture`를 실행해 4건 통과를 확인했다.

## 4. 알려진 제한사항

- 실제 Vision endpoint/model/dataset/threshold calibration은 검증하지 않았다.
- KAPUT mapping은 계약 가설이며 defect bbox ground truth qualification이 아니다.
- Multi-image는 Vision Stage 내부에서 순차 처리하며 throughput을 측정하지 않았다.
- Alignment, Policy, Routing, Review, Report, RAG와 최종 업무 결정은 구현하지 않았다.
- 기존 deprecated Vision skeleton compatibility field가 테스트 경고를 발생시키지만 P0/P1은
  아니며 후속 호환성 제거 Sprint에서 별도 version bump가 필요하다.

## 5. Closeout 체크리스트

- [x] P0 미해결 0
- [x] P1 미해결 0
- [x] 정적 검사와 전체 회귀 PASS
- [x] PostgreSQL·RabbitMQ·MinIO Integration PASS
- [x] Migration 세 경로와 Drift PASS
- [x] Docker 6개와 HTTP Health PASS
- [x] 문서·ADR-0013~0017 갱신
- [x] `git diff --check` PASS
- [x] Kaputt 사용자 파일 제외 확인
- [x] 로컬 Closeout Commit SHA `330cbdb` 확인
- [x] Sprint 4A 전용 브랜치 생성
