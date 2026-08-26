# Sprint 2 — Append-only Analysis Run & LLM Structured Extraction

- 작업일: 2026-08-26 (Asia/Seoul)
- Branch: `feature/sprint-2-analysis-llm`
- Base: Sprint 1 Closeout `244c282bdeaf96beff6df595a240f0908aa7cba9`
- 상태: 구현 완료, 독립 Closeout 재감사와 로컬 Commit Gate 통과
- Git 정책: 승인된 Closeout Commit만 로컬 생성; Push·PR 금지

## 1. 범위와 완료 경계

이번 Sprint는 인증된 Reviewer/Admin이 기존 Case에 Text Analysis Run을 등록하고, PostgreSQL
Transactional Outbox와 RabbitMQ/Celery를 거쳐 결정적 Mock 또는 선택적 vLLM으로 구조화한
결과를 Append-only 저장·조회하는 단일 Vertical Slice다.

구현 범위:

- Case와 분리된 Analysis Run, Text Stage Run, Stage Attempt
- 분석 생성 전용 Tenant Idempotency
- Transactional Outbox와 별도 Dispatcher
- Claim Token/Lease로 Fencing된 얇은 Celery Task
- Code-based Prompt Manifest와 SHA-256 Content Hash
- Strict Text Extraction Schema와 정확한 `source_quote` 검증
- 결정적 Mock과 OpenAI-compatible vLLM Adapter
- 생성·목록·상세 API와 Case 상세의 최신 Run 요약

명시적 비범위:

- Vision 호출·이미지 품질·Detection·Segmentation
- Text/Vision Alignment와 Partial Failure 조합
- Policy, RAG/pgvector 검색, Routing, Approval, Review, Report
- 고객 응답 생성, SSE, 취소, 수동 재시도 API, Prompt 관리 UI
- 자동 Provider 선택·Fallback, Redis, Kubernetes, Triton, 외부 CRM

## 2. 실제 Pipeline

```text
POST Analysis Run
  → PostgreSQL Transaction
    → Analysis Run + TEXT_EXTRACTION Stage
    → Analysis Idempotency Record
    → analysis.requested.v1 Outbox Event
  → 202 Accepted + Location
  → Dispatcher Claim / RabbitMQ Publish
  → Celery Task (six reference IDs only)
  → fenced Stage Claim + Attempt
  → Case allowlisted fields reload
  → Mock 또는 vLLM structured extraction
  → strict schema + exact source_quote validation
  → immutable Result + Attempt/Stage/Run terminal state
```

Case Status는 이 흐름에서 변경하지 않는다. 재분석은 기존 Result를 덮어쓰지 않고 새 Run을
생성한다.

## 3. 구현 구성

| 영역 | 구현 |
|---|---|
| Domain | Run/Stage/Attempt 상태, 전이, Failure, Provider Metadata, Prompt Manifest |
| Schema | 정확한 Sprint 2 taxonomy, extra-forbid, 입력·출력 길이 상한, Quote 검증 |
| Persistence | 여섯 테이블, Tenant 복합 FK, Named Check/Unique/Index, Result add/get-only |
| Application | Start/List/Get/Latest, fenced Execute, durable Retry, Outbox Dispatch |
| Provider | 결정적 Mock failure modes, strict JSON Schema vLLM Chat Adapter |
| API | POST 202/Replay 200, 목록 필터, 상세 결과, Case 최신 Run 요약 |
| Runtime | Dispatcher Process, RabbitMQ publisher, 얇은 Celery Worker, safe logs |
| Operations | Settings bounds, Mock default, external GPU opt-in, Compose/Make targets |

Accepted 설계 결정:

- `ADR-0009`: Transactional Outbox와 Fenced Analysis 실행
- `ADR-0010`: Code Prompt Registry와 구조화 결과만 보존
- `ADR-0011`: Case와 Analysis Run 수명주기 분리

## 4. 데이터 모델과 불변조건

Migration `20260826_0003`은 기존 Revision을 수정하지 않고 다음을 추가한다.

| 테이블 | 책임 |
|---|---|
| `analysis_runs` | 요청·Pipeline·Run 상태와 안전한 Failure |
| `analysis_stage_runs` | Text Stage, Provider/Model/Prompt/Schema Snapshot, Claim Lease |
| `analysis_stage_attempts` | 시도별 실행 상태와 Metadata 이력 |
| `llm_extraction_results` | 검증된 구조화 결과 한 건, Update/Delete 없음 |
| `analysis_request_idempotency_records` | Tenant·Operation·Key 원자적 Claim |
| `outbox_events` | DB와 Broker 사이의 내구성 있는 발행 상태 |

주요 불변조건:

- 성공 Result는 `(tenant_id, analysis_run_id)`와 `(tenant_id, stage_run_id)`마다 최대 1개다.
- Result FK는 `TEXT_EXTRACTION` Stage를 복합 키로 강제한다.
- 모든 업무 FK는 Tenant를 포함하며 Cross-tenant 연결을 거부한다.
- Stage Claim과 완료는 Token으로 Fencing한다.
- Outbox `PROCESSING` Claim은 `FOR UPDATE SKIP LOCKED`와 Lease를 사용한다.
- Queue Payload는 `event_id`, `tenant_id`, `case_id`, `analysis_run_id`, `stage_run_id`,
  `correlation_id` 외의 Field를 허용하지 않는다.

## 5. API와 권한

| Method | Path | 권한 | 신규 상태 |
|---|---|---|---|
| POST | `/api/v1/cases/{case_id}/analysis-runs` | ADMIN, REVIEWER | 202; Replay 200 |
| GET | `/api/v1/cases/{case_id}/analysis-runs` | 모든 역할 | 200 |
| GET | `/api/v1/cases/{case_id}/analysis-runs/{run_id}` | 모든 역할 | 200 |
| GET | `/api/v1/cases/{case_id}` | 모든 역할 | 최신 Run 요약 또는 `null` |

- POST는 `Idempotency-Key`가 필수이며 `Location`, `Cache-Control: no-store`를 반환한다.
- 목록은 `status`, `pipeline`, `page`, `page_size`를 지원하고 생성일·ID 역순으로 정렬한다.
- 다른 Tenant의 Case/Run은 Role과 무관하게 `404`다.
- 공개 응답은 Idempotency Key/Hash, Correlation/Claim Token, Provider Request ID, Raw Failure
  Message, Raw Prompt와 Raw Response를 포함하지 않는다.

## 6. 멱등성·재시도·장애 처리

- API: `(tenant_id, analysis.create.v1, key)` PostgreSQL Claim. 같은 Hash는 원 Run, 다른
  Hash는 `409 IDEMPOTENCY_KEY_REUSED`다.
- Dispatcher: Publish 전 Commit된 Claim, Publisher Confirm, 제한된 Backoff/Jitter, 오래된
  Claim 회수. 확인 직후 종료로 인한 Duplicate Publish를 허용한다.
- Worker: Terminal 상태는 No-op이며, Claim Token이 바뀐 이전 Worker의 늦은 결과는 Commit할
  수 없다. 활성 Lease 중복 전달은 Lease 만료 시각의 참조 전용 복구 Outbox Event를 남긴 뒤
  No-op 처리한다.
- Worker Lost와 Hard Timeout은 Celery 재전달을 사용한다. 검증된 Payload 처리 중 일반 예외와
  Soft Timeout은 명시적 `Reject(requeue=True)`로 바꿔 이미 `PUBLISHED`인 Event가 유실되지
  않게 한다. 잘못된 Payload는 재큐잉하지 않는다.
- Lease가 만료된 최종 허용 Attempt는 새 Attempt를 만들지 않고 같은 Transaction에서
  Stage `FAILED`, Attempt `ABANDONED`, Run `FAILED`와
  `ANALYSIS_MAX_RETRIES_EXCEEDED`를 기록한다.
- Transient Provider 오류는 Stage/Run `RETRY_WAITING`, Attempt 결과와 미래 Outbox Event를
  한 Transaction에 저장한다.
- Permanent 오류는 즉시 `FAILED`, 최대 시도 소진은
  `ANALYSIS_MAX_RETRIES_EXCEEDED`다.
- Outbox 최대 시도 소진은 아직 실행되지 않은 Run/Stage를 `OUTBOX_DISPATCH_FAILED`로 끝내
  대기 상태에 영구 고립되지 않게 한다.

## 7. Prompt·보안·데이터 최소화

- 고객 메시지는 명령이 아니라 Escape된 Untrusted JSON Data로만 Prompt에 들어간다.
- 허용 입력은 `customer_message`, `order_ref`, `product_ref`, 기존 `requested_action`뿐이다.
- Arbitrary Case `attributes`, JWT, Signed URL, 이미지, Secret과 내부 ID는 Provider에 보내지
  않는다.
- Output에는 승인·거절·사기·책임·정책·보상 판정 Field가 없다.
- DB와 로그에 Raw Prompt, Raw Provider Response, Chain-of-thought, LLM API Key, JWT와 전체
  고객 원문 복제본을 저장하지 않는다.
- Quote 일치는 검증하지만 Summary 전체의 의미적 환각을 완전히 증명한다고 주장하지 않는다.
- 외부 vLLM 장애는 Core `/health/ready`를 실패시키지 않는다.

## 8. 검증 원장

아래 수치는 최종 코드와 문서 상태에서 직접 실행한 결과다. 외부 vLLM은 명시적 Endpoint가
없어 호출하지 않았으며 Skip을 Pass로 계산하지 않았다.

| 검사 | 상태 | 실제 결과 |
|---|---|---|
| Sprint 1 시작 Baseline | PASS | Fast 189 passed·18 deselected; Integration 18 passed·189 deselected |
| 기본 CI-safe pytest | PASS | 291 passed·36 deselected·0 failed |
| Core Integration | PASS | 31 passed·5 skipped·291 deselected·0 failed |
| Analysis CI-safe Focus | PASS | 76 passed·251 deselected·0 failed |
| Analysis Integration Focus | PASS | 13 passed·5 skipped·309 deselected·0 failed |
| Unit | PASS | 227 passed·100 deselected·0 failed |
| Contract | PASS | 45 passed·282 deselected·0 failed |
| Architecture | PASS | 4 passed·0 failed |
| Sprint 1+2 HTTP API | PASS | 29 passed·0 failed |
| RabbitMQ·Outbox Focus | PASS | 18 passed·309 deselected·0 failed |
| CI-safe E2E Marker | PASS | 6 passed·321 deselected·0 failed |
| Migration Unit | PASS | 6 passed·0 failed |
| External vLLM 기본 실행 | SKIPPED | 5 skipped·322 deselected; 외부 설정 없음 |
| PostgreSQL Application E2E | PASS | 8 passed; Retry·Worker Lost·최종 Lease 한도 포함 |
| Alembic 격리 수명주기 | PASS | 빈 DB→Head, Head→Sprint1→Head, Sprint1→Head, Drift 없음 |
| Ruff / Format / Pyright | PASS | Ruff 통과, 158 Python files, 0 errors·0 warnings |
| Docker Mock Live E2E | PASS | 202·Replay 200·Conflict 409·Tenant 404·SUCCEEDED |
| Duplicate Delivery Live | PASS | 재전달 후 Attempt 1·Result 1 |
| Docker / Queue / Cleanup | PASS | 6개 Healthy, 큐 0, Analysis 6개 테이블 0, MinIO Object 0 |
| `git diff --check` | PASS | Whitespace 오류 없음 |

## 9. 인계 체크리스트

- [x] Sprint 1 Closeout Commit에서 `feature/sprint-2-analysis-llm` Branch 생성
- [x] Domain/Prompt/Provider 계약과 결정적 Mock 구현
- [x] `20260826_0003` Migration·ORM·Repository·UoW 구현
- [x] Application Start/Query/Execute/Outbox 구현
- [x] Analysis HTTP와 역할·Tenant Scope 구현
- [x] vLLM Adapter와 `external_gpu` Marker 구현
- [x] Worker·Dispatcher 최종 Runtime 연결과 Compose 이미지 재빌드
- [x] 일반 예외·Soft/Hard Timeout·Worker Lost·Lease 만료 복구 경계 보강
- [x] 전체 Ruff, Python Format, Pyright, pytest 정확한 최종 수치 확정
- [x] 빈 DB→Head, Sprint1→Sprint2, Head→Sprint1→Head 격리 수명주기 재검증
- [x] 실제 Login→Case→202→Outbox→Worker→SUCCEEDED와 Duplicate/Retry/Tenant 검증
- [x] 검증 데이터·임시 DB 정리와 Docker 최종 Health 확인
- [x] `CURRENT_STATUS.md` Append-only Session Log와 다음 Action 갱신
- [x] 독립 Closeout 감사와 문서 갱신 후 승인된 Sprint 2 로컬 Commit 후보 확정
- [x] Push·PR 없이 미추적 사용자 파일을 보존

## 10. 다음 Action

독립 Closeout Gate를 통과한 정확한 Sprint 2 범위만 로컬 Commit하고 Push·PR은 만들지 않는다.
다음 작업은 별도 `feature/sprint-2-5-qwen38-serving` 브랜치에서 고정 Qwen3.8 Artifact를
실제 검증하는 것이다. Vision Stage와 Alignment는 여전히 Sprint 3 이후 범위다.
