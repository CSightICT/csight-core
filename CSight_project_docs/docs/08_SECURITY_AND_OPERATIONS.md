# 08. Security and Operations

## 1. 네트워크 경계

```text
외부 사용자
→ HTTPS Web/API
→ Core Application & Data Plane
→ 사설망
→ LLM / Vision Inference Node
```

### 외부 공개

- Reverse Proxy의 HTTPS 포트
- 별도 Presign Hostname을 사용할 경우, 신뢰할 수 있는 HTTPS Proxy/Gateway가 서명된
  Object GET에 필요한 제한된 경로와 Method만 전달

### 사설망 전용

- PostgreSQL
- RabbitMQ
- MinIO 내부 Object API, Console, Admin API
- vLLM API
- Vision API 또는 Triton

### 차단

- 외부 → DB
- 외부 → LLM / Vision API
- LLM / Vision → 업무 DB

## 2. 인증과 권한

### MVP

- 로컬·PoC 전용 HS256 JWT Access Token
- Tenant Slug + 이메일 + Argon2id Password 로그인
- 필수 `sub`, `tenant_id`, `roles`, `iss`, `aud`, `iat`, `exp`, `jti` Claim 검증
- Token 검증 후 현재 사용자 활성 상태와 역할을 DB에서 다시 조회
- 역할: `ADMIN`, `REVIEWER`, `QUALITY_VIEWER`
- `ADMIN`·`REVIEWER`: Case 생성·조회, Evidence 업로드
- `QUALITY_VIEWER`: Case·Evidence 조회만 가능
- `ADMIN`·`REVIEWER`: Analysis Run 등록과 조회
- `QUALITY_VIEWER`: Analysis Run 조회만 가능, 등록 금지
- Tenant Scope는 요청 Body가 아닌 인증 Principal에서 결정
- 다른 Tenant의 Case/Evidence는 `404`로 숨김; `ADMIN`도 Cross-tenant 접근 불가
- Seed는 `local`/`test`에서 설정으로 명시적으로 허용한 경우에만 실행

### 제한 운영 파일럿

- OIDC Authorization Code + PKCE S256와 asymmetric ID-token/JWKS 검증
- `Secure`, `HttpOnly`, `SameSite=Lax` opaque session cookie; DB에는 session/CSRF SHA-256만 저장
- 절대 8시간, 유휴 30분, 만료 5분 전 경고; 설정으로 더 짧게만 조정 가능
- IdP group은 정확히 한 tenant와 허용 role 집합에 매핑하고, 활성 local account의 tenant/role을
  최종 권한으로 다시 확인
- Cookie 기반 unsafe request는 memory-only CSRF header가 없으면 거부
- 서명 검증된 OIDC back-channel logout은 issuer-scoped subject/session hash로 기존 세션을 원자적으로
  폐기하고, raw token·subject·session ID는 수명주기 기록에 저장하지 않음
- 그룹 제거·계정 비활성화는 IdP session 종료와 back-channel 전달 성공까지 하나의 운영 절차로 취급
- 기존 HS256 bearer 경로는 한 release 호환 범위로 유지하고 브라우저 memory 밖에는 저장하지 않음
- 고객 IdP의 logout 재시도·실패 경보와 고객별 session timeout 설정은 파일럿 Gate

## 3. 개인정보와 민감정보

- 고객 문의와 이미지에는 이름, 연락처, 주소, 주문정보가 포함될 수 있다.
- 로그에 고객 원문 전체를 남기지 않는다.
- SQL 문장 로그를 명시적으로 켜더라도 Bind Parameter 값은 항상 숨긴다.
- Object Storage 접근은 짧은 만료시간의 Signed URL을 사용한다.
- Signed URL은 별도 요청에서만 발급하고 DB·로그·목록 응답에 저장하지 않는다.
- 개발 데이터는 마스킹 또는 합성 데이터를 우선한다.
- 합성·Shadow·반입·출처 미확인 Case는 운영 KPI, SLA, drift readiness에서 기본 제외한다. Case의
  `source_scope`와 provenance는 생성 후 변경할 수 없으며 실제 파일럿 유입만 `PILOT_LIVE`를 사용한다.
- `pilot`·`production`에서는 OIDC server session만 허용한다. 비밀번호 토큰 route와 Bearer JWT는
  비활성화되며 IdP 장애 시에도 fallback으로 다시 열리지 않는다.
- 원본과 파생 데이터의 보관기간을 분리한다.
- 삭제 요청 시 Vector Index와 보고서 파생본까지 범위를 정의한다.
- Sprint 2 LLM에는 Allowlist한 고객 메시지·주문·상품 참조·요청만 전달한다. Case Attributes,
  내부 ID, Evidence, JWT, Signed URL과 Secret은 Prompt 입력에서 제외한다.
- LLM 전체 Prompt, Raw Provider Response와 Chain-of-thought를 DB·Outbox·Broker·로그에 남기지
  않는다. 검증된 구조화 결과, Version Snapshot, Token 수와 Latency만 보존한다.

## 4. Secret 관리

- `.env`를 저장소에 Commit하지 않는다.
- `.env.example`에는 키 이름만 제공한다.
- JWT Secret은 최소 32바이트이며 Local 예시값을 운영에 재사용하지 않는다.
- 개발 Seed 비밀번호는 각 12자 이상으로 환경변수에서만 받고 로그에 남기지 않는다.
- vLLM, Vision, MinIO, DB Credential을 분리한다.
- 선택적 vLLM API Key는 Secret 타입 설정에서만 읽고 Header 값이나 Base URL Credential을
  로그에 남기지 않는다. TLS 검증은 기본 활성화한다.
- Private vLLM Node에서는 API Key를 CLI 인자가 아닌 `VLLM_API_KEY` 환경변수로 주입해
  process listing과 시작 로그에 나타나지 않게 한다. 키가 출력된 경우 즉시 폐기·회전한다.
- PoC 이후 Secret Manager 또는 암호화된 CI Secret을 사용한다.

## 5. 파일 보안

- 파일 비어 있음과 `MAX_UPLOAD_BYTES` 검증
- Evidence multipart 요청 전체를 `MAX_UPLOAD_BYTES + 1 MiB`로 ASGI 경계에서 제한하고,
  `Content-Length`가 없는 요청도 제한
- `ALLOWED_IMAGE_MIME_TYPES`, `ALLOWED_IMAGE_EXTENSIONS` 제한
- 실제 이미지 Decode와 Client MIME·확장자·실제 형식 일치 검증
- 폭·높이와 `MAX_IMAGE_PIXELS` 검증
- Pillow 하드 안전 한계에 맞춰 `MAX_IMAGE_PIXELS` 설정을 최대 178,956,970으로 제한
- SHA-256 저장
- 파일명 직접 경로 사용 금지
- 원본 파일명은 표시용으로만 정규화하고 Object Key는 서버 UUID로 생성
- JPEG, PNG, WebP만 허용하고 SVG는 거부
- 필요 시 악성 파일 검사
- RabbitMQ 메시지에 이미지 Binary 또는 Base64를 넣지 않는다.
- Analysis RabbitMQ Payload는 `event_id`, `tenant_id`, `case_id`, `analysis_run_id`,
  `stage_run_id`, `correlation_id` 여섯 비어 있지 않은 문자열만 허용한다.

Sprint 1~2의 역사적 기본 경로는 EXIF 제거, 이미지 재인코딩, 개인정보 마스킹, 파생본 생성,
Virus Scan을 수행하지 않았다. 해당 경로에는 실제 고객 이미지를 반입하지 않는다.
Production HTTPS Proxy/Gateway에도 요청 본문 크기와 동시 업로드 수 제한을 적용한다.
애플리케이션 상한은 우회 방지의 최종 경계이며, Edge 제한을 대신하지 않는다.

제한 운영 확장 단계는 Pillow 기반 orientation 적용·metadata-free 재인코딩과 원본/정규화본
ClamAV INSTREAM 검사를 Evidence 저장 전에 수행한다. Production composition은 두 경계가 모두
설정되지 않으면 Evidence 반입을 거부한다. 2026-08-30 격리된 실제 HTTP 자격 검증에서 EXIF 제거,
재인코딩, EICAR·손상 이미지·과대 요청 차단과 ClamAV 중단 시 실패-폐쇄가 통과했다. 절차와
파일럿 호스트 재검증 조건은 [Evidence 이미지 보안 런북](operations/EVIDENCE_SECURITY.md)을 따른다.
현재 시연 runtime은 이 경로가 비활성이고 x86_64 파일럿 호스트 자격도 아직 없으므로 실제 고객
이미지 반입 금지는 유지한다.
고객 문의 원문은 `case_sensitive_payloads`에 dual-write하며 정책 버전·만료·purge 시각과 PII-free
수명주기 Event를 기록한다. `20260829_0022_privacy_lifecycle`은 backfill·dual-write parity가 완전하지
않으면 upgrade를 중단한다. 이후 만료 작업은 restricted prose를 비우고 legacy 값을 고정된
`[PURGED_BY_RETENTION]` tombstone으로 바꾸는 작업을 한 트랜잭션에서 수행한다. legacy 컬럼 자체는
한 release 호환을 위해 남아 있으며 전체 컬럼 제거를 완료했다고 주장하지 않는다.

민감정보·Evidence 수명주기 운영 명령은 기본 `DRY_RUN`이다. DB 복구에는 `--execute`와 정확한 tenant
재확인이 필요하며 MinIO 삭제에는 `--delete-orphan-objects`가 추가로 필요하다. stale `PENDING`, 누락
object, failed-row object와 canonical orphan만 다루고 귀속 불가능한 key는 삭제하지 않는다. 모든
복구·삭제 요청·삭제 완료는 고객 원문·파일명·URL·예외 메시지가 없는 append-only event로 기록한다.
MinIO 삭제는 exact key의 payload version과 delete marker를 version ID별로 영구 삭제하고 재조회 결과가
0개일 때만 완료로 기록한다. version inventory가 실패·절단되거나 하나라도 남으면 차단 결과로 끝난다.
`20260830_0027_analysis_text_erasure`은 같은 원문 만료 transaction에서 LLM v1/v2 claim/source quote,
summary, 생성 query, grounded explanation과 provider failure message를 tombstone/빈 구조로 바꾸고
deferred DB trigger로 재삽입을 막는다. Run·model·prompt·policy·index·metric lineage와 회사 정책 citation은
보존한다. `20260830_0029_terminal_content_erasure`은 사람 rationale/action payload, Case attributes,
terminal report의 고객·주문·배송 snapshot과 안내 시뮬레이션 문구를 추가로 지우고 결정·보고서·안내문의
현재 hash를 재계산한다. PII-free lifecycle event에는 행 수, opaque hash 전환과 receipt digest만 남기며
deferred trigger가 복구를 차단한다. tenant onboarding retention, scheduler/alert, 로그 전수 검색,
backup 만료와 legal hold는 아직 완료 범위가 아니다.
절차와 stop 조건은 [Privacy lifecycle runbook](operations/PRIVACY_LIFECYCLE.md)을 따른다.
ADR-0118의 자동 만료 profile은 단일 tenant의 만료 원문 삭제만 수행하며 Evidence 복구·MinIO 삭제
capability를 갖지 않는다. 비로컬 기동은 명시적 retention pair, exact tenant UUID, RLS-enforced API
database role을 요구한다. 사람 actor를 위조하지 않고 append-only event에 system scheduler initiator를
기록하며 blocked·truncated·stale health는 성공으로 낮추지 않는다.

### Private Object와 Signed URL

- Bucket은 항상 Private다.
- `MINIO_ENDPOINT`는 Core 내부 업로드·삭제용이다.
- `MINIO_PRESIGNED_ENDPOINT`는 Client가 URL로 접근할 Hostname이다.
- `SIGNED_URL_TTL_SECONDS`는 1초~7일 범위 설정이며 Local 기본값은 900초다.
- Signed URL을 만들기 전에 내부 Endpoint의 Object HEAD로 실제 존재를 확인한다.
- Production Presign Hostname은 제한된 Object GET 경로만 Proxy하고 MinIO Console,
  Admin API, Bucket 목록과 Credential은 노출하지 않는다.

## 6. 장애 대응

| 실패 | 대응 |
|---|---|
| LLM Timeout/Unavailable | Run/Stage/Attempt `RETRY_WAITING`, 지수 Backoff와 미래 Outbox Event |
| LLM 영구 오류/최대 시도 소진 | Append-only 실패 이력과 Run/Stage `FAILED` |
| 만료된 Worker Lease | 이전 Attempt `ABANDONED`, 새 Claim Token으로 재실행 |
| 활성 Lease 중 중복 Delivery | Lease 만료 시각의 Reference-only Recovery Outbox Event 하나 저장 |
| 늦은 Worker 응답 | Claim Token 불일치로 Result·상태 쓰기 거부 |
| Vision Timeout/부분 실패 | Sprint 3 이후 범위; 자동 승인 금지 원칙 유지 |
| Core 재시작 | DB 상태 기반 복구 |
| Object Storage 실패 | 성공 응답 금지, Object 삭제와 Evidence `FAILED` 전환을 최선 노력으로 수행 |
| `AVAILABLE` DB 갱신 실패 | Object 삭제 후 `FAILED` 전환 시도, 불일치 상태 관측·복구 필요 |
| DB는 `AVAILABLE`, Object 누락 | Signed URL 성공 응답 금지, 불일치 오류 반환 후 Reconciliation 필요 |
| RabbitMQ 장애 | PENDING Outbox Backoff 재발행; 소진 시 미실행 Run/Stage `OUTBOX_DISPATCH_FAILED` |

Sprint 2는 RabbitMQ DLQ와 운영자용 수동 재처리 API를 구현하지 않는다. Dispatcher의
At-least-once Publish와 Worker Idempotency가 복구 기준이다. Celery Retry/Ack는 업무 상태의
Source of Truth가 아니며 DB 상태와 Outbox Event를 기준으로 운영한다.

현재 Core Compose는 장시간 모델 호출이 사람 검토·Resolution을 막지 않도록 기존 Queue 이름을
세 실행 Lane으로 분리한다.

- Model Lane: `analysis`, `grounded-explanation`, concurrency 1
- Retrieval Lane: `policy-retrieval`, concurrency 2
- Decision Lane: `policy-evaluation`, `human-review`, `case-resolution`,
  `external-action-simulation`, concurrency 2

기존 단일 `worker`가 새 Lane과 함께 Queue를 소비하지 않도록 모든 표준 Compose 기동 명령은
`--remove-orphans`로 이전 Worker container를 제거한다.

격리된 합성 RabbitMQ/Celery 자격에서 concurrency 1 Model Lane에 120초 작업 2건을 in-flight로 둔
상태로 concurrency 2 Decision Lane의 20건 enqueue-to-start p95는 574.339ms, max는 574.404ms였고
유실·중복은 0건이었다. 현재 demo의 legacy-auth read-only 20-client 3회 측정도 Case worst p95
396.274ms, Review worst p95 460.999ms로 500ms 예산을 통과했다. 이는 실제 20 terminal workflow,
mutation p95, RLS/OIDC session, provider/model 부하가 아니므로 전체 release 부하 gate는 계속
실패한다. 재현 절차는 `docs/operations/LOAD_AND_QUEUE_ISOLATION.md`를 따른다.

Dispatcher는 한 Pipeline의 예외를 해당 Pipeline 결과로만 기록하고 같은 Poll에서 뒤 Pipeline을
계속 실행한다. Pipeline별 로그에는 이름, 집계 수치, 안전한 예외 타입만 기록하고 예외 메시지나
Connection String은 기록하지 않는다.

RabbitMQ DLX는 아직 활성화하지 않는다. 기존 durable Queue가 dead-letter argument 없이 생성된
상태에서 같은 이름으로 `x-dead-letter-exchange`를 추가하면 RabbitMQ `PRECONDITION_FAILED`로
Worker 기동이 중단될 수 있다. 또한 현재는 DLQ retention, 인증된 조회·재처리·취소 계약이 없다.
따라서 DLX 도입은 Queue migration 또는 새 versioned Queue, retention, 권한 있는 운영자 replay,
idempotency 검증을 함께 설계한 뒤 진행한다. 그 전까지 malformed Analysis payload는 식별 가능한
Outbox Event와 미실행 Run/Stage를 DB에서 안전하게 실패 처리한 뒤 broker delivery를 재큐잉하지
않는다. 이 durable 실패 기록 자체가 실패한 경우에만 유실 방지를 위해 재전달한다.

## 7. Health Check

- `/health/live`: 프로세스 생존
- `/health/ready`: DB·Queue 등 요청 처리 준비
- LLM `/health`
- Vision `/health`
- 모델 Warm-up 상태
- RabbitMQ Queue Depth
- MinIO 접근 가능성
- Outbox Dispatcher Process/반복 실행 상태와 PENDING/PROCESSING Claim Age
- Stage Lease 만료와 Retry Schedule

## 8. 관측성

현재 구현은 correlation ID와 trace/span ID가 있는 구조화 로그, tenant-scoped Operations Read API/UI,
그리고 opt-in OpenTelemetry HTTP/Celery span·저카디널리티 metric·OTLP/HTTP exporter 설정을 제공한다.
Operations 화면은 영속 Queue/Run 상태, 최고 대기시간, 실패·부분 성공·재시도·정체, 마지막 정상 처리,
최근 model/prompt/policy/threshold/index version을 bounded aggregate로 보여주며 Collector를 동기 조회하지
않는다. 격리된 digest-pinned 자격 환경에서 실제 HTTP trace·metric 수신, Prometheus 조회, UUID 없는
저카디널리티 라벨, 로컬 Alertmanager firing/resolved 전달과 Collector 장애·복구 중 API 무영향은
`PASS`다. RabbitMQ·MinIO·모델 노드 직접 상태, 실제 Worker lane export, 파일럿 호스트 dashboard
p50/p95와 운영자 paging destination 전달은 아직 `NOT_RUN`이므로 release gate는 계속 실패한다. 설정과
증거 절차는 `docs/operations/OPENTELEMETRY.md`와 ADR-0106을 따른다.

### System Metric

- API p50 / p95 / p99 Latency
- Error Rate
- Queue Depth
- Task Wait Time
- LLM TTFT / Total Latency
- Vision Inference Latency
- GPU Utilization / VRAM
- Retry / DLQ Count

### AI Metric

Sprint 2 운영 대상은 LLM Schema/Provider 실패와 Retry 지표다. Vision, 이미지 품질과 Alignment
지표는 해당 Stage가 추가되는 후속 Sprint부터 수집한다.

- LLM Schema Validation Failure
- Vision Low-confidence Rate
- Image Quality Failure Rate
- Alignment Score 분포
- 모델 버전별 오류율

### Business Metric

- Case 검토시간
- Approval Candidate Override율
- 위험 라우팅 오류율
- 추가 자료 요청률
- 재검토율
- 상품·결함별 반복 문제

로그와 Trace에는 상황에 따라 `correlation_id`, `tenant_id`, `user_id`, `case_id`,
`evidence_id`, `analysis_run_id`, `stage_run_id`, `event_id`, `task_id`, `operation`, `result`를
연결한다. 고객 문의 원문, Prompt/Raw LLM Response, Provider Request Body, Password, 전체 JWT,
LLM/MinIO Secret, Signed URL, 이미지 Binary, 전체 DB Connection String은 기록하지 않는다.

## 9. 백업

- PostgreSQL 정기 Dump 또는 Volume Snapshot
- MinIO 객체 백업
- Prompt·Policy·Threshold Export
- 복원 절차를 문서화하고 실제 복구 테스트 수행
- 개발 장비 단일 장애를 전제로 PoC 중요 데이터의 외부 백업 유지

Compose에는 PostgreSQL WAL archive와 MinIO bucket versioning 준비 계약이 있고,
`scripts/restore_manifest.py` v2는 DB base/WAL, MinIO version inventory와 실제 version backup,
policy/model/prompt/config version을 하나의 PII-free checksum manifest로 묶는다. 격리 합성 환경의
`pg_verifybackup`·post-base WAL replay·MinIO 4 versions/1 delete marker·tamper rejection과 timed
RPO/RTO는 `PASS`다. 이것은 백업 암호화를 수행하지 않는다. 암호화된 immutable off-host 저장소,
독립 key resolution과 pilot hardware에서의 두 차례 복원 훈련은 `NOT_RUN`이며 파일럿 시작
차단 조건이다. 상세 절차는 `docs/operations/RESTORE_DRILL.md`와 ADR-0119를 따른다.

## 10. PoC와 상용화 경계

현재 장비 구성은 개발·멘토링·제한된 PoC를 위한 것이다.

상용화 시 우선 이전 대상:

- FastAPI
- Celery Worker
- PostgreSQL
- RabbitMQ
- MinIO

LLM·Vision API 계약은 유지하고 배포 위치만 변경한다.

Sprint 2 Local Runtime은 API, 별도 Outbox Dispatcher, 분리된 Celery Worker Lane, RabbitMQ와 PostgreSQL을
사용한다. 기본 Provider는 Network-free Mock으로 둘 수 있고 `LLM_PROVIDER=vllm`일 때만
설정된 사설 vLLM Endpoint를 호출한다. Vision/Alignment/Policy/Routing/Review/Report/RAG
Runtime은 아직 배포 대상이 아니다.

Sprint 2.5 Qwen Node는 host publish를 Tailscale address 하나로 제한하고 인증을 필수로 한다.
Container 내부 `0.0.0.0` listen은 private host publish와 함께만 허용한다. 기존 listener,
다른 Container와 GPU process를 임의로 종료하지 않는다.

Local Compose의 Published Port는 모두 `127.0.0.1`에만 Bind한다. 이것은 개발 편의 설정일
뿐 Production 접근 통제를 대신하지 않으며, Production에서는 HTTPS, Secret Store,
Network ACL과 제한된 Presign Gateway를 별도로 구성한다.

## 11. Sprint 3 Vision Security와 운영

- Vision Service는 CSight DB와 MinIO에 직접 접근하지 않는다.
- Worker가 private Storage에서 size-bounded read하고 Snapshot SHA-256을 확인한다.
- Queue/Outbox에 이미지, Base64, object key, Signed URL, credential을 넣지 않는다.
- Provider API key는 Authorization header로만 보내며 로그·오류·metadata에 저장하지 않는다.
- Adapter는 Provider가 반환한 path/URL/object key를 계약에 허용하지 않는다.
- 모든 Snapshot/Result 조회와 쓰기는 tenant/run/case/evidence 복합 FK와 repository scope를 따른다.
- 구조화 로그에는 run/stage/attempt/evidence/provider/model/version/taxonomy/threshold/latency/count/
  status context만 허용하고 고객 원문과 이미지 content는 금지한다.

기본 Provider는 deterministic Mock이며 외부 Vision은 `external_vision` opt-in marker로만
실행한다. 실제 Service가 없을 때 상태는 `SKIPPED_EXTERNAL_VISION_NOT_AVAILABLE`이다.

## 12. Sprint 4A Reference Data Security

Corpus와 Gold는 합성 데이터만 포함한다. Prompt v2는 고객 문장을 untrusted JSON data로 다루고
secret/prompt/reasoning/decision field를 금지한다. Query Builder tenant filter는 Application이
주입하며 Grounded Explanation citation은 제공된 Clause ID allowlist로 검증한다.

## 13. Sprint 4B Retrieval Security

Tenant/status/effective filter를 두 retriever의 candidate 계산 전에 적용한다. Raw query/clause/vector,
JWT, DB URL은 로그하지 않는다. Embedding service는 loopback/private network, access log off, DB 접근
없음으로 운영하고 tenant/internal ID를 model input에 보내지 않는다. 장애 시 mock fallback하지 않는다.

## 14. Sprint 4C-1 Reranker Security

Core filter 후 candidate만 private loopback service에 전달한다. Tenant/JWT/DB/case ID는 전달하지
않고 raw query/passage/pair/score list를 로그하거나 영구 저장하지 않는다. Unknown/duplicate/missing
candidate와 invalid score는 fail-closed이며 provider down은 reranked mode에만 503이다.

## Query planning security

Core owns tenant, ACTIVE status, and as-of hard filters. Only trusted product category may be an
additional hard filter. Logs and messages exclude customer text, prompts, raw responses, reasoning,
query text, clause text, JWTs, keys, and vectors. Provider failures never silently change strategy.

## Sprint 4C-3A Grounding Security

Citation allowlist는 tenant/retrieval/version 경계를 fail-closed로 검증한다. Raw prompt,
provider response, reasoning, 고객 원문, clause text, token, secret은 broker나 log에 넣지 않는다.
Provider 장애는 Grounded Run 실패로 격리하고 Core readiness와 기존 retrieval은 유지한다.

Local MLX는 loopback에만 bind하고 별도 virtualenv와 immutable model revision을 사용한다.
Docker에는 host bridge URL만 제공한다. Optional LLM health는 Core readiness 의존성이 아니며,
provider failure는 Mock fallback 없이 기존 retry/failure 의미론으로 격리한다.

## Sprint 5A Safety

Typed allowlist 외 field/operator/effect는 ingestion 전에 거부한다. Python expression, eval/exec,
raw SQL/JSONPath와 자연어 규칙 실행은 없다. Input snapshot은 typed values와 qualification만
보존하고 고객 원문을 복제하지 않는다. Effects는 최종 승인·거절·fraud·liability를 표현하지 못한다.
# Sprint 5B authorization and operations

Viewer access is read-only. Reviewer actions are assignee-scoped; manager/safety and escalated claim
require Admin. Admin overrides are included in action payload audit. Review records exclude prompts,
model responses, reasoning, customer text, vectors, JWTs, and secrets. The worker consumes the
dedicated durable `human-review` queue.

## Limited-pilot PostgreSQL isolation

Migration `20260829_0020` enables and forces RLS on every current `tenant_id` table and on
`tenants`. API and Worker transactions bind a validated tenant through transaction-local
`app.tenant_id`; a missing context returns zero tenant rows. Exact login slug, OIDC session digest,
and poison-event UUID capabilities are separately bounded and never grant table-wide pre-auth
access. API, Worker, Dispatcher, and migration URLs are distinct deployment secrets. Dispatcher is
granted only seven Outbox tables. The legacy owner/superuser URL bypasses this boundary and is not
limited-pilot evidence. See ADR-0105 and `docs/operations/DATABASE_RLS_ROLES.md` for activation gates
and the remaining terminal-dispatch failure limitation.
## Reviewer direct-object authorization

Tenant isolation is necessary but not sufficient for reviewer accounts. API transactions set the
authenticated actor ID and whether the role may read every tenant Case. Restrictive `SELECT` RLS
policies call the shared Case-access predicate for Case, Evidence, analysis, retrieval, grounding,
policy evaluation, review, resolution, report, communication, and learning-asset tables. Application
dependencies apply the same rule and deliberately return `404` to avoid object enumeration.

## Signed model supply-chain and runtime authorization

The API and Worker hold only an approved Ed25519 public key in a regular, non-symlink,
non-group/world-writable file; the signing private key stays offline. Release and activation tables
use forced tenant RLS and reject UPDATE/DELETE. API may SELECT/INSERT, Worker may SELECT, and
Dispatcher has no privilege. Non-local vLLM must enable signed-release enforcement, and every
behavior-bearing artifact/runtime/prompt/schema digest must match the active tenant release before
the Worker calls the provider. No automatic cross-model fallback is permitted.

## Signed integration intake

Signed intake is disabled by default. Each enabled key ID is bound in deployment configuration to one tenant
and one active, no-role service actor; the request cannot select either. Ed25519 public keys must be regular,
non-symlink files that are not group/world writable, and private keys never enter CSight. Signatures expire
after the configured skew, capped at 300 seconds. Operators must prove valid creation, exact replay, one-byte
tamper rejection, stale rejection, and unchanged Case counts for failed requests before enabling a customer
source. Rotation adds a new key ID before retiring the old one. The canonical signing and smoke-test procedure
is in ADR-0120.

## Onboarding and pilot admission

The operator onboarding command accepts an explicit manifest and exposes `plan`, `apply`, and `verify`.
It never deletes a tenant, invents a retention period, prints a secret, or grants a role to the signed-intake
service actor. `apply` is additive and idempotent; conflicting existing identities fail closed. The generated
environment fragment is owner-readable only and contains references and public configuration, not private keys.

Pilot admission requires all six configuration gates and all 25 operational qualification gates to pass with
fresh evidence. Disk capacity, dependency health, alert delivery, restore drills, immutable image identity, and
real load evidence are operational gates rather than documentation claims. See ADR-0123 and
`docs/operations/PILOT_READINESS_AND_ONBOARDING.md`.
