# 09. Testing and Evaluation

## 1. 검증 단계

```text
Offline Evaluation
→ Shadow Mode
→ Limited PoC
→ High-confidence Automation 검토
```

### Offline Evaluation

- 고정 Test Case로 LLM, Vision, Alignment, Policy 평가
- 실제 업무 처리에 영향 없음

Sprint 2의 구현 대상은 Text Extraction LLM 평가뿐이다. Vision, Alignment와 Policy 평가는
각 후속 Sprint의 Gate다.

### Shadow Mode

- 상담원 기존 판단과 동시에 시스템 실행
- 시스템 결과는 실제 결정에 반영하지 않음
- 오버라이드와 오류 유형 비교

### Limited PoC

- 선택된 상품군과 결함 유형
- 상담원에게 근거와 처리 권고 제공
- 최종 결정은 상담원이 수행

## 2. 테스트 계층

### Unit Test

- Case 입력 검증, `RECEIVED` 초기 상태와 최초 이력
- Requested Action, Role Permission, Object Key 불변조건
- Canonical Request Hash와 Idempotency 재생·충돌
- JWT/Password Adapter와 현재 역할 재조회
- 독립 Hashing Port의 한 번의 제한된 Streaming Read, 크기·SHA-256과 Stream Rewind
- File Inspector의 이미지 Decode, MIME·확장자, 폭·높이·Pixel 검증
- Evidence `PENDING` → `AVAILABLE` 및 실패 보상
- Analysis Run/Stage의 허용 전이와 Terminal 전이 거부
- Analysis Attempt, Claim Token/Lease와 만료 Attempt `ABANDONED`
- 활성 Lease 중 중복 Delivery가 Lease 만료 시각의 Recovery Outbox Event 하나를 저장하고,
  기존 Worker 완료 시 Terminal No-op이 되는지 검증
- Analysis 등록 Canonical Hash, Tenant-scoped Idempotency 재생·충돌
- Text Extraction 성공·중복 No-op·Transient Retry·최대 시도·Permanent 실패
- 지수 Backoff의 결정성·상한과 미래 Outbox 생성
- Outbox Claim/Publish/Release/Terminal Failure와 정확한 여섯 ID Queue Payload
- Code Prompt Manifest의 Canonical SHA-256와 Injection-safe JSON Rendering
- Strict Extraction Schema, 정확한 Issue Taxonomy, 추가 Field 거부와 Exact Source Quote
- Policy 조건, Alignment 계산과 후속 Workflow 전환은 Sprint 4 이후 테스트 범위
- Domain Validation
- 버전 선택 로직

### Integration Test

- PostgreSQL Repository
- Alembic Migration
- MinIO Upload / Signed URL
- Tenant별 Case·Evidence·Identity 격리
- Case 목록 필터·페이지·안정 정렬
- Idempotency Unique Claim의 동시 요청
- Development Seed 반복 실행
- RabbitMQ와 Celery
- Analysis 여섯 Table의 Tenant 복합 FK, Check/Unique Constraint와 Repository Mapping
- `FOR UPDATE SKIP LOCKED` Outbox Claim, Stale Claim Recovery와 Token 조건부 완료
- Stage Claim/Lease, Attempt Fencing, Append-only Result Unique Constraint
- pgvector 검색은 RAG 도입 Sprint의 후속 범위

PostgreSQL/MinIO/RabbitMQ처럼 실제 Core Service가 필요한 Integration Test는 명시적인 Local
Core 실행에서 분리한다. 기본 Test Suite가 외부 Service나 GPU의 가용성에 의존하지 않게 한다.

### Contract Test

- 인증·Case·Evidence HTTP Schema와 오류 Envelope
- Case 생성 Body의 `tenant_id` 거부
- Case 생성 `201`과 Idempotency 재생 `200`
- Sprint 2 Mock LLM의 성공/Timeout/Transient/Permanent/Invalid Schema/Invalid Quote 계약
- vLLM OpenAI-compatible 요청 Body, JSON Schema Response Format, 오류 정규화와 상한 계약
- Vision Schema는 Sprint 0 호환 Skeleton; 실제 Integration은 Sprint 3 범위
- Outbox Event Envelope와 Celery 여섯 ID Event Payload
- API Response
- 모델 버전과 좌표 체계

vLLM Contract Test는 실제 Network 대신 통제된 HTTP Client를 주입한다. 실제 GPU/vLLM
연결은 `external_gpu` Marker와 별도 환경 설정을 요구하는 명시적 Smoke Test로만 수행하고,
기본 `pytest`에서는 제외한다.

Sprint 2.5 qualification은 100건 합성 Dataset(단일 40, 복수 20, 위치 모호 15, 요청 없음
10, 결함 불명확 5, 장문·오탈자 5, Injection 5)을 사용한다. 안전 Gate는 Schema/Pydantic/
Source Quote 100%, Forbidden Field/Injection 위반/Reasoning Leakage 0%다. 최소 20건을 사람이
Spot-check하며, 분류 F1과 Latency는 합성 Baseline으로만 보고한다. 두 Cold Start, 20분
Stability와 동시성 1·2 Profile을 별도 기록한다.

### E2E Test

- Seed → 로그인 → Case 생성 → 이미지 업로드 → 목록·상세 → Signed URL → Object GET
- Tenant A의 Case를 Tenant B가 요청할 때 `404`
- Case 저장부터 Text Analysis 등록·구조화 결과 조회까지
- Analysis Idempotency Replay, 중복 Event No-op와 Transient 재시도
- Celery Retry가 아닌 DB Run/Stage/Attempt와 Outbox가 복구 Source of Truth인지 검증
- Case 접수부터 Review 확정, 추가 자료 요청, Vision 부분 실패와 정책 버전 재분석은 후속 범위

Sprint 2 E2E 경계는 Thin Celery Task가 정확히 여섯 ID를 검증해 Application Use Case로
위임하는 흐름까지다. Vision, Alignment, Policy, Routing, Human Review, Report와 RAG를
포함한 Case-to-Decision E2E는 아직 구현 완료 기준으로 간주하지 않는다.

### Security Test

- Tenant 간 데이터 접근 차단
- 만료된 URL
- 만료·변조 JWT, 비활성 사용자, 현재 역할 회수
- `QUALITY_VIEWER`의 Case 생성·Evidence 업로드 차단
- 빈 파일, 과대 파일, 위장 이미지, Path Traversal 형태 원본 파일명
- 권한 없는 Review
- 위험 파일 업로드
- Prompt Injection 입력
- Queue/Outbox에 고객 원문, Prompt, Raw Response, JWT, Signed URL, Secret이 없는지 검증
- Analysis HTTP Projection에서 Idempotency/Request Hash, Claim/Lease, 내부 실패 Message와
  Provider Request ID가 제외되는지 검증

## 3. 핵심 E2E 사례

1. 로컬 Seed → Reviewer 로그인 → `RECEIVED` Case와 최초 이력 생성
2. 유효 이미지 → Private MinIO Object와 `AVAILABLE` Evidence → Signed URL Object GET
3. 동일 Case Idempotency Key·Body → 기존 Case 재생, 중복 미생성
4. 동일 Key·다른 Body → `409 IDEMPOTENCY_KEY_REUSED`
5. Tenant A Case를 Tenant B가 조회 → `404`
6. QualityViewer 생성·업로드 → `403`, 조회 → 성공
7. 위장 이미지·빈 파일·과대 파일·과대 Pixel → 정의된 오류로 차단
8. Storage/DB 실패 → 성공 응답 없이 보상 경로 실행
9. 저장된 Case → Analysis 등록 `202` → Outbox/Worker → 구조화 결과 상세 조회 (Sprint 2)
10. 동일 Analysis Idempotency Key/요청 → 기존 Run `200`, 중복 Run/Stage/Outbox 없음
11. 중복 Event 또는 늦은 Worker → Append-only 결과 중복·덮어쓰기 없음
12. 명확한 누액 → 승인 후보 → 상담원 승인 (Sprint 4 목표)
13. 흐린 이미지 → 추가 자료 요청 (Sprint 3~4 목표)
14. Vision Timeout → Partial Failure (Sprint 3 목표)
15. Model 또는 Prompt Version 변경 → 기존 결과 유지, 새 Run 추가

## 4. 기술 지표와 업무 지표

### 기술 지표

- Vision Precision / Recall / mAP
- Calibration
- LLM 구조화 성공률
- 필드별 Extraction 정확도
- 평균 분석 Latency
- Timeout과 실패율

### 업무 지표

- 건당 평균 검토시간
- 상담원 1인당 처리건수
- 처리 경로 추천 정확도
- 고신뢰 권고 Override율
- 위험 라우팅 오류율
- 최초 응답시간
- 재문의·재검토율
- 건당 처리비용

## 5. PoC 핵심 KPI

### 1순위

1. 평균 검토시간
2. 고신뢰 권고 Override율
3. 위험 라우팅 오류율

### 2순위

- 추가 자료 요청 적절성
- 재검토율
- 문서 작성시간
- 반복 불량 탐지 활용도

정확한 목표값은 Baseline 측정과 기업 인터뷰 후 확정한다.

## 6. 안전성 Gate 예시

다음 값은 멘토와 협력 기업의 검증 후 숫자를 확정한다.

- 위험 오류가 허용 범위를 넘으면 자동 승인 후보 기능 비활성화
- Vision 품질이 최소 기준 미만이면 판정 중단
- Policy Version이 없으면 Human Review로 이동
- 모델 결과 Schema가 유효하지 않으면 Decision 생성 금지
- 고위험 Flag가 하나라도 존재하면 자동 처리 금지

## 7. ROI 측정

```text
월간 불량 문의 수
= 월간 전체 문의 수 × 불량 문의 비율

월간 시간 절감 가치
= 불량 문의 수 × 건당 절감시간 × 상담원 분당 인건비

월간 총 가치
= 시간 절감
+ 재검토 비용 감소
+ 오승인·오거절 비용 감소
- 시스템 운영비
```

필요 Baseline:

- 월간 문의량
- 이미지 첨부 문의 비율
- 평균 검토시간
- 재검토율
- 오승인·오거절 비용
- 상담원 인건비
- 현재 문서 작성시간

## 8. 품질 Gate

Pull Request 완료 전:

- Unit / Integration / Contract Test 통과
- Ruff와 Type Check 통과
- Migration 검증
- API Schema Diff 검토
- 개인정보 로그 노출 검사
- 기본 Suite에서 외부 GPU 호출이 없고 `external_gpu` 검증이 명시적으로 분리되는지 확인
- 주요 E2E Scenario 회귀 없음

## 9. Sprint 3 Vision Gate

- Unit: bbox/coordinate/confidence, tri-state quality, taxonomy/unknown, stable Snapshot, join truth table
- Contract: 10개 deterministic Mock scenario와 Remote multipart/status/timeout/JSON/schema/geometry
- PostgreSQL: image별 Result/Detection/Snapshot, append-only duplicate, tenant isolation, partial join
- MinIO: bounded private read, SHA mismatch, missing object와 unavailable storage
- RabbitMQ/Application: Text+Vision event 2개, duplicate no-op, retry event와 terminal aggregation
- E2E: success/success, success/fail, fail/success, fail/fail, Vision timeout→retry→success
- Migration: empty→head, previous→0004, downgrade/upgrade와 drift
- 기본 suite는 `external_gpu`와 `external_vision`을 모두 제외한다.

실제 Vision qualification은 health, immutable metadata, real image detection/geometry/latency,
timeout/invalid image를 별도로 기록한다. 현재 endpoint가 없으면 Mock 결과를 실제 모델 통과로
표현하지 않는다.

## 10. Sprint 4A Data Gate

v2 strict schema/source quote/completeness/prompt hash, corpus stable build/version/parent/duplicate,
Gold count/split/clause existence/tenant isolation을 기본 Suite에서 검증한다. Reference Gold
self-check는 evaluator contract 검증이며 외부 모델 평가가 아니다. Qwen test split은 Prompt hash
freeze 뒤 한 번만 실행한다.

## 11. Sprint 4B Retrieval Gate

Unit은 tokenizer/BM25/vector/RRF/metric을, contract는 인증 API/provider 장애를, PostgreSQL
integration은 ingestion idempotency/version conflict/filter/vector/index activation을 검증한다.
실제 embedding은 `external_embedding` opt-in이다. Dev 80 tune 뒤 profile을 freeze했고 Test 40을 한
번 실행했다. correctness rate 0/100% gate와 slice/latency를 함께 보존한다.

## 12. Sprint 4C-1 Reranker Gate

Unit은 candidate/oracle/profile/serialization/token/allowlist/metric을, contract는 provider status와
malformed response를, API는 새 mode와 기존 mode 회귀를 검증한다. 실제 MPS는 opt-in
`external_reranker`다. Dev를 freeze하고 Test는 한 번만 호출하며 candidate-set mutation과 모든
scope/version/status 위반 0, Dev deterministic rerun 100%를 요구한다.

## Query-builder protocol

Tune only on the new Dev 80 split, freeze versioned query/retrieval profiles, then access Test 40
once. Compare direct contract/security and downstream retrieval metrics under identical HYBRID
conditions. The legacy retrieval Test is regression-only.

## Sprint 4C-3A Gates

Schema extra-field 거부, statement별 citation 필수, allowlist, duplicate normalization,
cross-tenant/version/effective-date, forbidden decision, prompt injection, duplicate delivery와
Migration lifecycle을 검증한다. Semantic faithfulness는 실제 pinned model 전용 Gate다.

Local MLX sealed 결과는 Extraction 120/40, Query 80/40, Grounding 40/10, Injection 20/10으로
관리한다. Test 결과 파일이 존재하면 재실행을 거부한다. 사람 semantic spot-check는 Dev20과
Test10 전체이며 독립 judge-model 점수로 표현하지 않는다.

## Sprint 5A Gates

Unit은 registry/operator/missing/aggregation/hash/replay를, contract는 unknown/type/final effect/
source/version/conflict를, API는 create/replay/conflict/role/tenant를 검증한다. PostgreSQL E2E는
snapshot/outbox/append-only result/duplicate no-op를 확인한다. Dev80/Test40 gate는 selection,
rule exact, condition, effect F1, summary, source, version, tenant/effective date, determinism이다.
