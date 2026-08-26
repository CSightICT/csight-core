# Sprint 2 Closeout — 독립 감사 및 로컬 기준점

- 감사일: 2026-08-26 (Asia/Seoul)
- Branch: `feature/sprint-2-analysis-llm`
- Base: Sprint 1 Closeout `244c282bdeaf96beff6df595a240f0908aa7cba9`
- 대상: Base 이후 Sprint 2 전체 변경
- 판정: `PASS` — P0 미해결 0, P1 미해결 0
- Git 경계: 아래 Gate 통과 범위만 로컬 Commit하며 Push·PR은 만들지 않는다.

## 1. 감사 방법과 범위

이전 완료 보고의 수치를 전제로 삼지 않고 코드, Migration, 테스트와 실제 Docker 실행을 다시
확인했다. `AGENTS.md`, Blueprint, 관련 설계 문서 03–09, ADR-0009~0011과 진행 문서를 읽었고,
`kaputt_best_vision_architecture.md`는 Sprint 3 참고자료로만 읽었다. 해당 사용자 파일은
수정·삭제·Stage하지 않는다.

감사 범위는 Append-only Result, Analysis 수명주기, Transactional Outbox, Celery 재전달,
Claim Token/Lease Fencing, Strict LLM 경계, Tenant Scope, Migration `20260826_0003`, HTTP와
Docker Runtime이다. Vision, Alignment, Policy, Routing, Review, Report와 RAG는 범위 밖이다.

## 2. 발견 사항 분류

| 등급 | 발견 | 처리 |
|---|---:|---|
| P0 | 0 | 미해결 0 |
| P1 | 0 | 미해결 0 |
| P2 | 2 | Closeout 원장 추가와 Git·다음 작업 문서 상태 동기화 |
| P3 | 3 | DLQ·운영자 재처리, 비정상 DB 상태 Reconciliation, Retention/Cleanup을 후속 이관 |

재현 가능한 Tenant 유출, Secret 노출, 데이터 손상, Append-only 위반, 중복 Result, Event 유실,
Retry 한도 오류는 발견하지 못했다. 최초 Live 감사용 일회성 스크립트는 실제 요청 전에 존재하지
않는 설정 속성을 참조해 중단됐으며, 고정된 Local API 바인딩으로 수정해 재실행했다. 이 도구
오류를 제품 검증 PASS로 계산하지 않았다.

## 3. Append-only 감사

- `SQLAlchemyLLMExtractionResultRepository`와 Port는 `add`와 `get_by_run`만 제공한다.
- DB는 `(tenant_id, analysis_run_id)`와 `(tenant_id, stage_run_id)` Unique Constraint를 가진다.
- Result FK는 같은 Tenant·Run의 `TEXT_EXTRACTION` Stage만 참조하게 강제한다.
- 재분석은 새 Idempotency Key로 새 Run·Stage·Outbox를 생성한다.
- Terminal Run/Stage는 Worker 진입에서 No-op이고, 완료 쓰기는 현재 Claim Token으로 Fencing된다.
- Stage, Attempt, Run과 Result 성공 쓰기는 같은 Unit of Work에서 Commit된다.

## 4. Outbox·Celery 복구 감사

- Run, Stage, 분석 Idempotency와 Outbox Event는 API의 한 Transaction에 저장된다.
- API에서 직접 `task.delay()`로 이어지는 Dual-write 경로가 없다.
- Dispatcher는 `FOR UPDATE SKIP LOCKED`, Claim Token, Publisher Confirm과 Stale Claim 회수를
  사용한다.
- Publish 실패는 Event를 미래 `PENDING`으로 되돌리고, 한도 소진 시 미실행 Run/Stage를
  `OUTBOX_DISPATCH_FAILED`로 종결한다.
- Queue Payload는 정확히 여섯 식별자이며 Poison Payload는 Use Case 전에 거부된다.
- 검증된 작업의 예상 밖 오류와 Soft Timeout은 명시적 재큐잉되고, Worker Lost/Hard Timeout은
  Late Acknowledgment 재전달 경계를 사용한다.
- 활성 Lease 중복은 기존 Claim을 침범하지 않고 Lease 만료 시각의 Recovery Outbox를 남긴다.
- 만료된 최종 Attempt는 새 Attempt 없이 Attempt `ABANDONED`, Stage/Run `FAILED`로 원자 종결된다.

## 5. LLM·Tenant 안전성 감사

- 출력 Schema는 승인, 거절, 보상, 사기, 책임, 법적·정책 판정 Field를 표현하지 않는다.
- 고객 입력은 Allowlist DTO를 JSON Escape한 단일 Untrusted Data Placeholder로 전달한다.
- Pydantic `extra="forbid"`, 중복 Enum 금지, 길이 상한과 Exact `source_quote` 검증이 적용된다.
- Raw Prompt, Raw Provider Response, Reasoning/Chain-of-thought Column과 저장 경로가 없다.
- Outbox/Broker에는 고객 원문, Evidence, Token, Signed URL과 Secret이 들어갈 수 없다.
- Repository 조회와 조건부 Update는 Tenant를 요구하며 복합 Tenant FK가 Cross-tenant 연결을
  거부한다.
- Worker는 Payload의 Tenant·Case·Run·Stage 조합을 모두 scoped 조회하고 불일치 시 실행하지
  않는다.
- 다른 Tenant의 Live Analysis 조회가 `404`임을 합성 Tenant로 확인했다.

## 6. Migration 감사

- `20260825_0001`과 `20260826_0002`는 Sprint 1 기준점과 동일하다.
- `20260826_0003`은 정확히 여섯 Analysis/Outbox Table만 추가한다.
- Result Unique, Stage/Attempt 상태 Check, Outbox Payload Check와 Tenant 복합 FK를 실제
  PostgreSQL에서 적용했다.
- Downgrade는 Outbox → 분석 Idempotency → Result → Attempt → Stage → Run 역순이다.
- 세 격리 경로 모두 Head `20260826_0003`과 `alembic check`의 `No new upgrade operations`
  결과를 확인한 뒤 임시 DB를 삭제했다.

## 7. 재실행 검증 원장

| 검사 | 결과 |
|---|---|
| Ruff | PASS — `All checks passed` |
| Ruff Format | PASS — 158 files already formatted |
| Pyright | PASS — 0 errors, 0 warnings, 0 informations |
| CI-safe 전체 | PASS — 291 passed, 36 deselected |
| Unit | PASS — 227 passed, 100 deselected |
| Contract | PASS — 45 passed, 282 deselected |
| Architecture | PASS — 4 passed |
| Sprint 1+2 HTTP | PASS — 29 passed |
| CI-safe E2E | PASS — 6 passed, 외부 설정 필요 1 skipped |
| Core Integration | PASS — 31 passed, 외부 vLLM 5 skipped, 291 deselected |
| Analysis PostgreSQL | PASS — Repository/Application 13 passed |
| RabbitMQ·Outbox 선택 실행 | PASS — 3 passed, 324 deselected |
| Duplicate·Retry·Lease·Max 선택 실행 | PASS — 7 passed, 6 deselected |
| Migration Unit | PASS — 기본 Suite에 포함된 6건 |
| 격리 Migration 3경로·Drift | PASS — Empty→Head, Sprint1→Head, Head→Sprint1→Head |
| Docker Build·Up | PASS — 최종 이미지 Build, 6개 장기 서비스 Healthy |
| Live Mock HTTP | PASS — 202, Replay 200, Conflict 409, Tenant 404, `SUCCEEDED` |
| Live Duplicate | PASS — 같은 Message 두 번 재발행 후 Result 1, Attempt 1 |
| 정리 | PASS — Analysis 6 Table 0, 합성 Tenant 0, Queue Ready/Unacked 0, 임시 DB 0 |
| `git diff --check` | PASS |

외부 vLLM 5건은 Phase A에서 Endpoint가 구성되지 않아 `SKIPPED`이며 Mock 통과를 실제 모델
검증으로 해석하지 않는다. 실제 Qwen3.8 검증은 별도 Sprint 2.5 브랜치의 Gate다.

## 8. Commit Gate

- [x] P0 미해결 0
- [x] P1 미해결 0
- [x] 전체 정적 검사 PASS
- [x] Sprint 0·1·2 회귀 PASS
- [x] 실제 PostgreSQL·RabbitMQ·Outbox·Mock E2E PASS
- [x] Migration 세 경로와 Drift PASS
- [x] Docker Build와 Core 6개 Health PASS
- [x] Live 202·200·409·404·SUCCEEDED와 Duplicate 1 Result PASS
- [x] 문서 갱신 완료
- [x] `git diff --check` PASS
- [x] Secret, `.env`, 생성물과 사용자 Kaputt 문서를 Commit 후보에서 제외
- [x] 로컬 Commit `feat: complete append-only LLM analysis pipeline` 생성
- [x] Push·PR 생성 금지

## 9. 후속 이관

- 실제 Qwen3.8 Artifact와 vLLM 호환성은 Sprint 2.5에서 별도로 검증한다.
- 비정상 수동 DB 변경으로 Result와 비Terminal 상태가 함께 존재하는 경우의 자동
  Reconciliation은 정상 Transaction 경로 밖의 후속 운영 기능이다.
- DLQ, 운영자 재처리·취소 API, Outbox/Attempt/Idempotency Retention은 후속 Sprint 범위다.
- Vision 참고문서는 보존하며 Sprint 3 계약 확정 전에는 구현에 반영하지 않는다.
