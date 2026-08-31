# CSight 제품 준비도 및 RTX 4090 Qwen3.8 감사

> 2026-08-30 19:28 KST 갱신: P0-3 Case 접수 배정과 P0-4 reviewer 직접 객체 권한은
> migration 0026과 ADR-0111로 구현·검증됐다. RTX 4090 후보 matrix와 fail-closed gate는
> ADR-0113으로 추가됐고 terminal customer content는 migration 0029와 ADR-0114로 삭제 경계를
> 확장했다. 아래 진단은 발견 당시 기록으로 보존한다. 실제 Keycloak OIDC protocol, 로컬 Alertmanager
> 장애·복구, physical WAL·MinIO version 복원 절차는 통과했지만, 고객 IdP의 권한 변경→session 종료
> 자동화, 전달 실패 경보, 암호화된 off-host 복원 반복과 실제 4090 model qualification은 남아 있다.

- 기준 시각: 2026-08-30 11:43 KST
- 기준 브랜치: `codex/operator-console-product-direction`
- 기준 커밋: `3daaa7bff56fa0e25f7ca69bf6bc31d68a2cdb79`
- 감사 성격: 읽기 중심 제품·운영 감사. 이번 문서는 발견 사항과 승격 관문을 고정하며,
  P0 수정이나 실제 고객 데이터 반입을 승인하지 않는다.

## 1. 결론

현재 CSight는 사람 확정형 상담 운영 흐름, append-only 기록, 정책 근거, 역할별 화면,
작업 처리선 분리 같은 중요한 제품 기반을 이미 갖췄다. 다만 현재 실행 상태를 정확히
분류하면 **내부 시연 가능, 제한 운영 파일럿 불가**다.

이유는 기능 수가 부족해서가 아니다. 아래 네 가지 제품 진실이 아직 일치하지 않는다.

1. schema drift는 0024로 수렴했고 strict Compose의 실제 분리 로그인 경로도 검증했다. 다만 기본
   데모 시작은 의도적으로 owner 호환 모드이며 파일럿 배포에는 strict overlay를 선택해야 한다.
2. Case 접수 배정과 reviewer 직접-ID 소유권은 구현됐지만, 고객 IdP의 관리자·담당자 실제 두 계정
   수동 acceptance는 아직 실행하지 않았다.
3. 원문·파생 문구·terminal snapshot·MinIO 모든 version 삭제는 구현됐지만, 고객별 retention 입력,
   로그 전수 검사, backup 만료와 legal hold 운영 계약은 아직 남아 있다.
4. Qwen과 Vision은 현재 Core에서 `mock`이며, 과거 Qwen3.8-27B INT4 관측은 역사적 Shadow
   baseline일 뿐이다. 현재 matrix의 release eligible 후보는 0개다.

따라서 지금 우선순위는 새로운 모델이나 인프라를 더 붙이는 일이 아니라 **DB 진실 → 업무 소유권
→ 개인정보 삭제 → 실제 모델 승격 → 복구·관측 증명** 순서로 기존 구현을 실제 운영 설정과
end-to-end 관문에 연결하는 것이다.

## 2. 현재 실측 기준선

| 관측 | 결과 | 해석 |
|---|---|---|
| Core 서비스 | 9개 모두 healthy, API/Web/Embedding/공개 주소 정상 | 내부 시연 가능성은 확인 |
| DB migration | `20260830_0031` head | drift repair 이후 OIDC back-channel logout까지 선형 적용 |
| DB drift | `alembic check` exit 0 | 빈 DB·기존 drift DB·현재 runtime 수렴 확인 |
| DB 실행 계정 | 기본 데모는 owner; strict overlay는 API/Worker/Dispatcher 분리 LOGIN 실기동 PASS | 파일럿은 strict overlay만 허용해야 함 |
| 인증 | 로컬 시연은 `OIDC_ENABLED=false`; 격리 Keycloak 자격 PASS | 고객 IdP lifecycle 자동화는 별도 Gate |
| 개인정보 입력 | sanitizer off, malware scanner disabled | 실제 고객 이미지 반입 금지 |
| 관측 | OTel off, exporter 없음 | 장애 경보 전달 미증명 |
| 모델 | `LLM_PROVIDER=mock`, `VISION_PROVIDER=mock` | 현재 healthy는 실제 모델 healthy가 아님 |
| 저장소 암호화 경로 | `MINIO_SECURE=false` | 단일 Mac 내부 시연 설정 |

최초 감사에서 `alembic check`가 검출한 drift는 다음 세 묶음이었다.

- `case_evidence`의 `(tenant_id, case_id, idempotency_key, sha256)` ORM unique constraint가 DB에 없다.
- 운영 실패·복구 테이블의 check constraint 18개가 migration/ORM naming convention 차이로 불일치한다.
- `ix_policy_retrieval_similarity_run_group`은 DB에 있지만 ORM metadata에는 없다.

이 세 묶음은 additive migration `20260830_0024_schema_drift_repair`와 ORM index metadata 보강으로
수렴했다. disposable PostgreSQL에서 빈 DB→head와 unique가 빠진 기존 0023→head를 모두 검증하고,
재빌드된 현재 컨테이너에서도 `alembic check`가 `No new upgrade operations detected`를 반환했다.
즉 schema drift는 닫혔지만 **서비스 health, migration head, 제품 준비도는 여전히 서로 다른 관문**이다.

## 3. RTX 4090 모델 결정

### 3.1 이름부터 구분한다

현재 저장소의 모델은 `Qwen3-8B`가 아니라 실제 별도 계열인 **`Qwen3.8-27B`**다.
이 둘은 모델 카드, 파라미터 규모, 체크포인트, 품질·메모리 특성이 모두 다르므로 화면이나
운영 문서에서 줄여 부르거나 자동 대체하면 안 된다.

### 3.2 27B 체크포인트 적합성

| 후보 | 고정 revision | weight bytes | 단일 4090 판단 |
|---|---|---:|---|
| 공식 BF16 `Qwen/Qwen3.8-27B` | `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0` | 55,563,006,776 | 24,564 MiB VRAM에 적재 불가 |
| 공식 FP8 `Qwen/Qwen3.8-27B-FP8` | `017b9c7af6b5689d5dd426a76e0bc077eb5ca20a` | 30,866,866,928 | KV/runtime 전에도 적재 불가 |
| 현재 Community W4A16 | `63768c10df38c0395e12ef49edac1bd539eaeeea` | 21,018,000,928 | 실제 구동 성공, 운영 여유 부족 |

공식 [Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B),
[Qwen3.8-27B-FP8](https://huggingface.co/Qwen/Qwen3.8-27B-FP8)은 단일 24 GB급
4090에 전부 적재할 수 없다. 현재 사용 중인
[Community AWQ INT4](https://huggingface.co/cyankiwi/Qwen3.8-27B-AWQ-INT4)는
유일하게 저장소에서 실제 자격 검증한 27B 단일 GPU 후보다.

하지만 현재 측정은 다음 한계를 함께 보였다.

- workload peak 23,825 MiB, 관측 최저 여유 254 MiB
- 8,192 context, sequence 1, eager, FP8 KV에 고정
- 구조화 출력·인용 일치 100%, issue F1 0.95
- requested-action accuracy 0.23, missing-information F1 0.00
- 합성 100건이며 실제 고객 분포 자격이 아님

따라서 현재 아티팩트는 **시연 및 Shadow 기준선**으로 유지할 수 있지만 제품 기본 프로필로
자동 승격하면 안 된다. 정책과 인증된 사람만 최종 결정을 내리는 현재 경계도 유지한다.

### 3.3 권장 4090 전략

즉시 유지할 기준선:

- 현재 model revision, tokenizer, vLLM image digest, prompt/schema를 그대로 묶는다.
- `--language-model-only`, private bind, API key, context 8192, sequence 1, eager,
  FP8 KV, 자동 fallback 없음, 고객 문의 cache 없음 조건을 바꾸지 않는다.
- 이는 새로운 시연 전 환경 변경 위험을 줄이는 기준선일 뿐 파일럿 승격은 아니다.

파일럿 후보:

1. 공식 `Qwen3.8-27B` exact revision에서 CSight가 직접 W4A16 compressed-tensors
   양자화를 만들고 calibration corpus revision/digest/recipe까지 소유한다.
2. 4090에서 GPU utilization 0.88~0.90, context 4K/8K 후보를 별도 profile로 측정해
   최악 입력에서도 최소 2 GiB 여유가 나는지 확인한다. 결과 없이 현재 값을 변경하지 않는다.
3. 공식 `Qwen3-8B-FP8`은 **다른 모델의 별도 Shadow 후보**로만 비교한다. 더 작은 모델이라는
   이유만으로 자동 대체하지 않고 업무 품질, TTFT, 처리량, 전력, OOM 여유를 동일 데이터로 비교한다.
4. 두 후보 중 절대 업무 기준을 통과한 profile만 사람이 atomic activation하며 기존 실행은 보존한다.

4090에서 AWQ/GPTQ/FP8 지원 여부와 실제 체크포인트 적재 가능성은 다른 문제다.
[vLLM 양자화 호환표](https://docs.vllm.ai/en/stable/features/quantization/index.html)에 따르면
Ada는 AWQ/GPTQ/FP8를 지원하지만, NVFP4는 Blackwell 대상이므로 4090 기본 후보가 아니다.
GGUF도 현재 vLLM 제품 경로를 바꿀 만큼의 비교 증거가 없어 기본 경로에서 제외한다.

### 3.4 vLLM 보안·업그레이드

현재 고정한 vLLM `0.26.0` 이미지에는 `torchvision 0.26.0` 관련 scanner finding이 남는다.
vLLM은 알려진 취약 경로가 자사 media 처리에서 도달되지 않는다고 설명하지만, 이는 패치 완료를
뜻하지 않는다. [vLLM 공식 이슈 #51192](https://github.com/vllm-project/vllm/issues/51192)

현재 확인한 최신 stable `0.28.0`은 Transformers 5.15.0과 Qwen3.8 변경을 포함하는 환경 변경이다.
[vLLM 0.28.0 릴리스](https://github.com/vllm-project/vllm/releases/tag/v0.28.0)는 현재
v0.26.0 profile의 현장 교체가 아니라 별도 Runtime Challenger로만 사용한다. manifest-list digest
`sha256:61fc8a896b0a4fbbbdc063bc4b0dbc25ce98e02b5050c24aeb7830ac02039b14`를 후보 matrix에
고정했다. 당장은 텍스트 전용, private bind, 멀티모달 입력 거부, 만료일이 있는 risk acceptance를
보완 통제로 두고 후보별 전체 image/profile을 다시 자격 검증한다.

## 4. 제품 완성도 P0

### P0-1. DB drift를 0으로 만든다 — 완료

영향: 새로운 환경과 현재 DB가 같은 스키마라는 보장이 없고, 배포 재현성과 evidence 멱등성
검증이 깨진다.

관문:

- 빈 DB→head, 기존 0023 drift→head, 현재 runtime→head 성공
- 각 검증 DB와 현재 컨테이너에서 `alembic current=head`, `alembic check` exit 0
- 0024 재실행 no-op과 evidence unique 복구 검증
- 남은 후속: disposable PostgreSQL integration을 CI 필수 관문으로 승격하고 concurrent evidence
  upload 전체 경로를 release suite에 포함

### P0-2. 실제 DB 역할과 RLS를 활성화한다 — 활성화 경로 완료, 복구 자격 보강 필요

`DATABASE_PASSWORD_FILE`, 비밀번호 비출력 provisioner, `infra/compose.rls.yml`을 추가했다. 임시
private secret으로 API=`csight_api_login`, 세 Worker=`csight_worker_login`,
Dispatcher=`csight_dispatcher_login`을 실제 기동했고 모든 health와 `DATABASE_RLS_REQUIRED=true`
guard가 통과했다. 같은 strict 실행에서 실제 reviewer password login, `/auth/me`, 개인 문의 목록도
200을 반환했다. 검증 비밀은 삭제하고 현재 시연 서버는 owner 호환 모드로 복구했다.

관문:

- migrator 전용 owner와 API/Worker/Dispatcher의 서로 다른 `LOGIN`, `NOSUPERUSER`,
  `NOBYPASSRLS` 계정
- `DATABASE_RLS_REQUIRED=true`
- 정상뿐 아니라 terminal failure, replay, lease recovery까지 strict 계정 E2E
- 애플리케이션 tenant 조건을 의도적으로 제거한 cross-tenant read/write 0건
- 현재의 넓은 API/Worker 권한을 업무별 최소 권한 행렬로 축소

앞의 두 항목과 정상 인증/목록, omitted-predicate RLS는 통과했다. terminal failure·replay·lease
recovery를 실제 LOGIN Compose에서 한 번에 묶는 release suite와 최소 권한 축소는 아직 남는다.

### P0-3. 문의 접수 시점 소유권을 만든다

현재 담당자 배정은 정책 평가 뒤 생성되는 `human_review_task`에만 가능하다. 정책 검색이 실패하면
관리자는 사건을 배정할 대상 자체가 없다. 사용자 요구인 “문의가 들어오면 담당자 배정”과 다르다.

관문:

- 정책 실행과 독립된 case-level assignment 또는 intake work item
- 관리자 assign/reassign/unassign, CAS, append-only audit
- 이후 review task가 case 담당자를 상속
- `정책 검색 실패 → 관리자 배정 → 담당자 조회 → 복구 후 계속 처리` PostgreSQL E2E

### P0-4. 상담원 직접 객체 접근도 소유권으로 제한한다

operator 목록과 review task 상세은 담당자 범위를 적용하지만 기존 Case·Evidence API는 같은
tenant의 `CASE_READ`만 확인한다. 상담원 A가 상담원 B의 case ID를 알면 문의 원문과 증거에
접근할 수 있는 경로가 남는다.

관문:

- 상담원 A가 상담원 B의 Case, Evidence, Analysis, Workflow, Report 직접-ID API를 모두 404로 받음
- 관리자·명시된 감독 역할만 tenant 전체 접근
- 애플리케이션 ownership 조건과 DB 방어 계층을 함께 적용
- 관리자 1명·상담원 2명의 실제 API negative E2E

### P0-5. `WAITING_FOR_EVIDENCE`에서 업무가 사라지지 않게 한다 — 핵심 계약 완료

자료 요청 시 담당자와 활성 배정 구간을 보존하고, `WAITING_FOR_EVIDENCE`도 담당자의 활성 문의로
조회되도록 수정했다. 재개는 같은 담당자를 유지한 `CLAIMED`로 돌아가며, 기존 대기 행은 과거 최신
배정을 참조하는 새 `WAITING_OWNER_RECOVERY` 기록으로만 복구한다. 단, 실제 브라우저에서
`자료 요청 → 로그아웃 → 자료 제출 → 동일 담당자 재개` 전체 E2E는 아직 release 관문으로 남는다.

관문:

- WAITING 상태에서도 owner를 보존하거나 별도 `waiting_owner_id`를 기록
- 상태별 소유권·노출 행렬 고정
- 모든 비종결 담당 문의는 정확히 한 활성 메뉴, 내가 결정한 문의는 정확히 한 완료 메뉴에 존재
- `자료 요청 → 로그아웃 → 자료 제출 → 동일 담당자 재개` E2E

### P0-6. 증거 로드 실패에서 최종 결정을 차단한다 — 구현 완료, live E2E 대기

검토 상세은 Case API 실패와 이미지 0건을 구분한다. Case·Evidence 메타데이터 조회 실패뿐 아니라
각 `IMAGE`의 authenticated content fetch, upload availability, 브라우저 decode 상태를 집계한다. 한
장이라도 loading·failed·corrupt면 빠른 확인창과 수동 결정 모두 잠기며, 재시도 후 모든 사진이
정상 decode되어야 해제된다. 실제 이미지가 0건인 문의는 별도 reviewable 상태로 유지한다. 요약과
확인창의 decode 상태를 분리해 한 화면의 결과가 다른 화면을 잘못 해제하거나 영구 오염하지 않는다.

관문:

- `loading`, `loaded-empty`, Case `failed`, 이미지 `failed`·`corrupt` 구분과 결정 차단 완료
- 이미지 일부 실패·재시도 성공·요약/확인창 상태 격리를 component test로 고정
- 별도 override는 추가하지 않음
- 실제 API·브라우저의 Case 실패·부분 실패·영구 실패 E2E는 release 관문으로 남음

### P0-7. 코사인 `0.0` 변조를 수정하고 표현 계약을 고정한다 — 완료

`None`만 fallback하고 유효한 `0.0`을 그대로 보존한다. `NEAREST`는 버전된 설명 기준 `0.65`와의
절대 거리가 가까운 3개(동점이면 높은 cosine 우선), `LEAST`는 cosine이 가장 낮은 3개로 고정했다.
정확한 DB query와 `-1, 0, 0.65, 동점, 다중 query 중복` golden test가 이 계약을 검증하며,
최저 유사도는 정책의 공식 불적격 판정이나 부정 학습 라벨로 사용하지 않는다.

관문:

- `None`만 fallback하고 `0.0` 보존
- `-1, 0, 0.65, 동점, 다중 query 중복` golden test
- “최고 cosine 3개”와 “임계값까지 가장 가까운 3개” 중 하나를 ADR/API/UI에 동일하게 고정
- 최저 3개는 “검색상 거리가 먼 정책”으로 표시하고 rule 불적격 사유와 구분

### P0-8. 개인정보를 모든 복구 경로에서 실제로 삭제한다

`case_sensitive_payloads`와 legacy Case 원문 tombstone, LLM v1/v2 claim/source quote/summary, 생성 query,
grounded explanation과 관련 provider failure message 삭제를 0027로 구현했다. 0029는 사람 rationale와
action payload, Case attributes, terminal report의 고객·주문·배송 snapshot, communication 문구와 resolution
failure prose를 같은 transaction에서 지우고 결정·보고서·안내문의 현재 hash를 재계산한다. PII-free
event에는 opaque pre/post hash 전환과 receipt digest가 남고 deferred DB trigger가 재삽입을 차단한다.
MinIO도 exact key의 모든 payload version과 delete marker를 version ID로 삭제하고 0개를 재확인한다.
단일 고객 배포에서 명시적 tenant UUID와 승인된 retention pair를 요구하는 opt-in 자동 만료 프로세스를
추가했다. 최신-head 임시 PostgreSQL에서 RLS-enforced API role로 만료된 합성 문의의 원문·분석·
terminal 파생문이 사람 actor 없이 삭제되고 scheduler initiator가 기록되는 경로가 통과했다. 현재
시연 DB에서는 만료 0건·변경
0건과 aggregate healthcheck를 확인했다. 다만 고객별 계약 입력, 실제 경보 전달, 로그 전수 검색,
백업 만료·legal hold가 남아 있어 전체 P0-8은 계속 미완료다.

관문:

- 고객 onboarding에서 retention version/days와 단일 tenant UUID를 필수 입력하고 자동 만료 profile 활성
- blocked/truncated/unhealthy 신호가 실제 운영자에게 전달·확인되는 alert drill
- 알려진 synthetic PII marker를 DB 모든 text/JSON, report, log에서 검색해 0건
- MinIO object v1/v2와 delete marker를 포함해 복구 가능한 payload 0건
- EXIF, EICAR, malformed, oversized, scanner outage를 실제 ClamAV 경로로 검증
- backup 만료와 법적 보존 예외까지 삭제 계약에 포함

### P0-9. OIDC-only 실제 인증을 검증한다 — protocol 자격 통과, 고객 운영 연결 Gate

ADR-0116으로 non-local 비밀번호 인증 설정을 시작 단계에서 거부하고, password token route를
등록하지 않으며 Bearer JWT도 401로 차단한다. capability와 로그인 화면도 OIDC-only 상태를 그대로
반영한다. 현재 로컬 시연은 호환 로그인을 유지한다. 별도 Keycloak 26.7.2 격리 스택에서 실제
Authorization Code+PKCE, 역할 매핑, return path, CSRF, idle expiry, 비밀번호 route 부재를 통과했다.
Migration 0031과 ADR-0117은 표준 signed back-channel logout, issuer-scoped hashed subject/session,
append-only hashed receipt와 멱등 replay를 구현한다. 그룹 제거·계정 비활성화 뒤 Keycloak 사용자
session을 종료하면 이미 발급된 CSight session도 즉시 401이 되는 실제 E2E가 통과했다. 다만 권한
변경 API 자체는 logout을 발생시키지 않으므로 고객 IdP 운영 자동화가 권한 변경→session 종료→전달
재시도·경보를 하나로 묶는지 검증하기 전 파일럿 승격은 차단한다.

관문:

- non-local에서 legacy password route 404, capability `legacy_password_enabled=false`
- 실제 시험 IdP 로그인, 그룹 변경, 계정 비활성화, 만료, CSRF, 재인증 E2E
- 그룹 제거·계정 비활성화와 IdP session 종료를 원자적 운영 절차로 연결하고 기존 CSight 세션 즉시 회수
- OIDC session 외 password bearer로 보호 API 접근 불가

### P0-10. 합성·실운영 데이터를 지표와 자산에서 분리한다 — 구현 완료, 실표본 0

Migration 0030이 Case의 immutable `source_scope`와 provenance를 고정하고 report·learning asset에
전파한다. 기본 KPI와 readiness는 `PILOT_LIVE`만 포함하며 UI는 포함·제외·전체 건수를 분리한다.
현재 실행 DB의 `PILOT_LIVE`는 0건이므로 성과나 drift readiness는 계속 주장할 수 없다.

관문:

- immutable `source_scope`와 provenance 저장
- synthetic/demo/shadow/imported/pilot-live 분리
- 기본 KPI·SLA·drift·readiness에서 synthetic와 `NOT_ATTESTED` 제외
- 합성 60건만 존재하는 경우 pilot readiness=false

### P0-11. 접근성 검증을 실제로 실행되게 복구한다 — fixture 복구 완료

API fixture에 `inquiry_summary`와 최근접/최저 cosine 3개씩을 추가해 현재 상세 계약과 맞췄다.
320/375/768/1024/1440px 접근성 5건과 업무 시나리오 5건이 모두 통과했다.

관문:

- fixture를 현재 스키마·실제 배정 역할과 일치시킴
- 320/375/768/1024/1440px에서 admin/reviewer 양 역할 실행
- serious/critical 0, overflow 0, 44×44 미만 0
- dialog focus trap/Escape/복원과 mobile drawer keyboard E2E
- 최소 한 경로는 실제 API·PostgreSQL 인증/배정 사용

### P0-12. 실제 모델 release를 운영 경로에 연결한다 — 4090 Dev 실행, 후보 2개 모두 탈락

Core는 현재 mock이므로 과거 4090 자격 결과가 현재 runtime identity를 증명하지 않는다. 다만
manifest persistence, 관리자 activation/rollback, Worker startup 및 호출 직전 identity enforcement는
이제 구현되어 있다.

부분 완료: `qwen4090_candidate_matrix/1.0.0`과 strict 판정기를 추가했다. 공식 27B BF16/FP8은
weight bytes만으로 `HARDWARE_EXCLUDED`, 기존 Community 27B W4A16은 `SHADOW_ONLY`다. vLLM 0.28.0
Runtime Challenger와 공식 Qwen3-8B-FP8은 실제 4090 Dev를 실행했으나 절대 품질 관문에서 탈락했다.
검증 데이터는 모호한
legacy v1 대신 `llm_extraction_v2/2.0.0` 160건과 고정 digest를 사용한다. 현재 machine verdict는
의도적으로 `NO_RELEASE_ELIGIBLE`이다. 실제 vLLM 평가 placeholder는 exact candidate identity,
Dev 반복, 절대 기준 동결, sealed Test 1회, 결과 digest 재검증과 개인정보 없는 관측만 남기는 실행
harness로 교체했다. GPU host에서는 `nvidia-smi`를 200ms 간격으로 측정한다. Dev 실패로 freeze와
sealed Test는 열지 않았고, 100-case Core Shadow와 20-workflow도 실행하지 않았다.

또한 vLLM 0.28.0 27B Runtime Challenger와 공식 8B FP8 Model Challenger에 matrix-derived exact
Compose overlay와 allowlisted launcher를 추가했다. 이미지·artifact·revision·alias·context·sequence·
memory utilization·KV dtype·text-only·thinking-disabled가 matrix와 다르면 시작 전 검증이 실패한다.
Container health 뒤 authenticated `/v1/models` exact alias canary도 필요하다. 별도의 live host
preflight는 Linux x86_64, 단일 idle RTX 4090/CC 8.9/VRAM, NVIDIA Docker runtime, 로컬 Tailscale bind,
owner-only secret, exact local image digest, frozen Hugging Face snapshot 전체 content digest와 weight
bytes, dependency lock, SBOM, recipe, calibration evidence를 검사한다. 두 실행 후보의 실제 package
evidence를 수집해 matrix에 고정했고, strict 또는 명시적 Shadow-only provenance 상태에서만 시작했다.
실제 Dev 품질이 기준에 미달했으므로 P0-12 승격은 계속 차단 상태다.

관문:

- 실제 4090에서 host preflight 수집 후 package digest를 matrix에 고정
- signed manifest에 고정된 identity와 Worker runtime canary exact 일치 확인
- 현재 업무 계약으로 PRIMARY/SHADOW 100건 비교
- requested action·missing information 절대 기준 별도 통과
- 20/20 terminal, OOM/restart/duplicate/stall 0, metadata 100%
- timeout/429/5xx/malformed/reset/half-open 장애 주입
- 관리자 activation/rollback 실연, 자동 cross-model fallback 없음

## 5. P1 — 파일럿 운영 완성도

P0 뒤에는 다음을 순서대로 보강한다.

- 배정 UX: 즉시 select mutation 대신 확인, per-row 상태, 실제 사람 식별, 사유, 409 재조회,
  retry/unassign, 두 관리자 동시 배정 테스트
- 업무량·SLA: 담당자별 active/waiting/urgent/capacity와 `received_at`, `state_entered_at`, `due_at`
- 실시간 큐: 15~30초 bounded refresh 또는 push, 수동 새로고침, 마지막 갱신 시각
- 검색: 현재 25개 page의 client filter를 서버 검색과 query-bound cursor로 교체
- 운영 복구: 7개 versioned queue, DLX/DLQ, poison payload ledger, 인증된 replay/cancel
- 처리선 격리: 두 개의 120초 모델 작업 중 decision queue wait p95 2초 이하
- 관측: Collector/backend, W3C trace propagation, queue/outbox/provider/review/GPU 지표와 실제 알림 전달
- 복구: 암호화된 off-host base backup+WAL+MinIO versions, 격리 PITR, RPO 1시간/RTO 4시간 2회
- DB 안정성: pool, statement/lock/idle timeout과 20 session/1,000 case `EXPLAIN ANALYZE`
- 관리자 온보딩: 사용자 수명주기, IdP mapping preview, retention, 정책·모델 profile, SLA/timezone,
  알림·복원 준비 설정

RabbitMQ·Redis·Kubernetes·ANN·partitioning은 이 관문을 해결하지 않는다. 실측 병목 전에는 추가하지
않는 기존 원칙이 맞다.

## 6. 권장 실행 순서

### 묶음 A — 데이터 진실과 소유권

1. schema drift 0
2. strict DB roles/RLS 실제 활성화
3. case-level assignment와 reviewer direct-object authorization
4. WAITING 소유권 복구
5. evidence fail-closed와 cosine 0.0 수정
6. 접근성 fixture 복구 후 5 viewport 재검증

완료 조건: 관리자 1명·상담원 2명·실제 PostgreSQL로
`접수 → 배정 → 정책 실패/복구 → 자료 요청 → 재개 → 결정 → 내 처리 현황`을 완주하고,
다른 담당자 직접-ID 접근은 모두 404다.

### 묶음 B — 개인정보와 실제 인증

1. OIDC-only 실 IdP
2. image sanitizer+ClamAV 실제 활성화
3. tenant retention과 전체 파생 데이터 purge
4. MinIO 모든 version 완전 삭제
5. 합성/실운영 자산·KPI 분리

완료 조건: synthetic PII marker가 활성 DB·object versions·log에서 0건이고, 복원 가능한 백업의
만료 계약까지 문서화된다.

### 묶음 C — 4090 모델 release

1. 현 Community W4A16을 고정 Shadow 기준선으로 보존
2. 공식 Qwen3.8-27B exact base에서 **CSight가 소유·재현하는** W4A16과 별도 공식
   Qwen3-8B-FP8 후보 생성
3. 동일 corpus·4090로 업무 품질/VRAM/지연 비교
4. manifest registry, startup identity canary, activation/rollback 연결
5. SHADOW 100 + workflow 20 + soak/fault gate

완료 조건: 선택 profile이 업무 절대 기준을 통과하고 최악 입력에서 최소 2 GiB VRAM 여유,
OOM·restart 0이며, 모델 장애가 Core 전체 readiness를 내리지 않고 해당 기능만 degraded로 만든다.

### 묶음 D — 파일럿 운영 증명

1. DLQ와 운영자 replay/cancel
2. 실제 Worker lane Collector export, pilot dashboard, 운영자 paging receiver
3. 암호화된 off-host backup과 pilot hardware 반복 restore drill
4. 20 session/20 workflow/120초 처리선 격리 부하

완료 조건: RPO 1시간, RTO 4시간, 조회 p95 500ms, mutation p95 1초, decision queue p95 2초를
실측하고 경보 전달·확인까지 기록한다.

## 7. 이번 감사 검증 결과

| 검증 | 결과 |
|---|---|
| Core controller status와 서비스 health | PASS, 9개 healthy |
| API live/ready | PASS |
| 현재 DB head | PASS, `0031` |
| `alembic check` | PASS, exit 0 |
| vLLM resilience/contract/external-GPU test selection | 24 PASS, 5 SKIP; 실제 외부 GPU 미실행 |
| LLM Compose config | PASS |
| model cache/release/pilot qualification unit selection | 7 PASS |
| 상담 목록·검토 UI/client 관련 단위 선택 | 14 PASS |
| 접근성 Playwright 5 viewport + 업무 시나리오 5건 | PASS, 10/10 |
| strict RLS group-role·failure recovery | 10 PASS; 실제 별도 LOGIN 3종 integration 5 PASS |
| strict RLS Compose/API smoke | PASS, 5 runtime healthy/current_user 일치; login/me/operator cases 200 |
| 격리 Keycloak protocol 자격 | PASS / 고객 IdP 운영 연결은 미완료 |
| 격리 ClamAV 실제 HTTP 자격 | PASS / 현재 시연 runtime은 비활성 |
| 실제 Qwen current Core E2E | NOT_RUN / Core mock |
| local synthetic physical WAL + MinIO version restore | PASS; off-host encrypted repeat NOT_RUN |
| 20-client read + 120초 synthetic queue isolation | PASS; 20 terminal workflow/mutation/RLS-OIDC NOT_RUN |

## 8. 대외적으로 말할 수 있는 범위

현재 말할 수 있다:

- 사람만 최종 결정을 기록하는 내부 시연용 상담 운영 PoC
- 정책 검색·근거 연결·이미지 참고 분석·append-only 추적 구조
- 역할별 상담 화면과 관리자 배정의 구현 기반
- 단일 4090에서 Qwen3.8-27B Community W4A16의 제한적 합성 자격 결과

아직 말하면 안 된다:

- 실제 고객 파일럿 준비 완료
- tenant 격리·개인정보 완전 삭제·재해 복구가 운영 검증됨
- 모델이 환불·교환을 정확히 결정함
- 24×7, HA, 무중단, 자동 외부 처리
- 합성 지표가 고객 운영 품질이나 학습 자산 규모를 대표함

실제 외부 환불·결제·메일 동작은 계속 0이어야 하며, 이 경계는 위 관문을 통과한 뒤에도 별도
승인 없이는 바꾸지 않는다.

## 9. 2026-08-30 17:58 KST 현재 상태 재검증

### 9.1 RTX 4090 후보의 현재 결론

`make audit-qwen4090-hub`가 후보 5개의 정확한 Hugging Face commit, Apache-2.0 license,
quantized base-model lineage, 개별 safetensors LFS identity와 weight byte 합계를 온라인으로
대조했고 모두 `HUB_REVISION_VERIFIED`였다. 관측한 weight byte는 다음과 같다.

| 후보 | safetensors | 현재 의미 |
|---|---:|---|
| 공식 Qwen3.8-27B BF16 | 55,563,006,776 | 단일 4090 hardware exclusion |
| 공식 Qwen3.8-27B FP8 | 30,866,866,928 | 단일 4090 hardware exclusion |
| Community Qwen3.8-27B W4A16 | 21,018,000,928 | 구동 가능하지만 현재 baseline은 VRAM 여유 254 MiB |
| 공식 Qwen3-8B FP8 | 9,436,628,784 | 별도 소형 model challenger |

Hub metadata PASS는 실제 파일 다운로드·GPU 적재·품질 자격을 뜻하지 않는다. 현재 matrix 판정은
계속 `NO_RELEASE_ELIGIBLE`이며, 실행 가능한 두 프로필은 모두 Shadow 후보일 뿐이다.

4090에서의 비교 순서는 다음으로 고정한다.

1. 기존 27B/vLLM 0.26.0 profile은 변경하지 않고 역사적 Shadow baseline으로 보존한다.
2. 같은 Community 27B artifact의 vLLM 0.28.0, context 4,096, sequence 1,
   GPU memory utilization 0.88 profile을 먼저 실행해 runtime 변화만 분리 측정한다.
3. 공식 Qwen3-8B-FP8/vLLM 0.26.0, context 8,192, sequence 1, utilization 0.88을 다음에 실행해
   model 변화만 비교한다.
4. 27B 품질이 필요하고 Community provenance가 gate를 통과하지 못할 때만 공식 base exact
   revision에서 CSight-owned W4A16을 생성한다. recipe와 calibration digest 없이 만들지 않는다.

### 9.2 코드 완성도와 실제 제품 준비도의 차이

| 영역 | 현재 권위 있는 증거 | 판정 | 다음 통과 조건 |
|---|---|---|---|
| DB schema | Head `0031`, `alembic check` drift 0 | 구현 완료 | strict role release suite와 복구 경로 반복 |
| 실제 모델 | Core `LLM_PROVIDER=mock`, `VISION_PROVIDER=mock`; release eligible 0 | 미완료 | 4090 Dev/Test, Shadow 100, workflow 20, fault/soak |
| DB tenant 방어 | strict RLS 경로는 검증했으나 현재 시연 runtime은 `DATABASE_RLS_REQUIRED=false` | 파일럿 설정 미활성 | 고객 환경에서 별도 LOGIN과 RLS를 기본값으로 기동 |
| 인증 | Keycloak protocol 자격은 통과했으나 현재 runtime은 `OIDC_ENABLED=false` | 고객 운영 연결 미완료 | 고객 IdP 권한 변경→session 종료→재시도·경보 |
| 이미지 반입 | 격리된 실제 HTTP에서 정화·EICAR·손상·과대 요청·scanner outage PASS; 현재 runtime은 정화 `false`, scanner `disabled` | 경로 자격 통과, 고객 runtime 미활성 | x86_64 파일럿 호스트 재검증 후 production에서 두 경계 필수 활성 |
| 개인정보 보존 | 자동 만료 코드·latest-head PostgreSQL drill·healthcheck PASS; 현재 demo는 `development/30d`, automation off | 경로 구현, 고객 운영 미활성 | 고객 retention/tenant 입력, production profile, alert delivery, backup/legal hold |
| 실패 복구 | 실패 원장·use case는 있으나 runtime replay/cancel service는 의도적으로 `None` | 운영 복구 미완료 | 모든 pipeline cancel terminalization과 실제 DLQ drill |
| 관측·경보 | 격리 HTTP trace/metric·Prometheus query·로컬 firing/resolved·Collector 장애/복구 PASS; 현재 demo는 `OTEL_ENABLED=false` | HTTP 경로 자격 통과, 고객 runtime 미활성 | 실제 Worker lane, pilot dashboard p50/p95, 운영자 paging destination |
| 백업·복원 | v2 five-artifact binding, 실제 `pg_verifybackup`·post-base WAL replay·MinIO 4 versions/1 delete marker·tamper gate PASS; local RPO 0.0462m/RTO 0.2944m | 로컬 절차 자격 통과, 외부 내구성 미완료 | 암호화 immutable off-host copy와 pilot hardware 2회 반복 |
| 부하·격리 | 현재 demo read-only 20-client×3회: Case worst p95 396.274ms, Review 460.999ms; 격리 120초 model in-flight 중 decision 20건 queue p95 574.339ms, 유실·중복 0 | 읽기·routing 자격 통과, 전체 workflow 미완료 | strict RLS/OIDC, mutation p95 1s, 20/20 terminal·queue drain·stall 0, 실제 4090 부하 |
| 실제 성과 | `PILOT_LIVE` 표본 0 | 주장 불가 | 고객 승인 pilot-live 표본과 분리된 KPI |

따라서 현 시점 제품 판정은 **내부 시연 가능, 실제 고객 파일럿 시작 불가**다. 기능 화면을 더
추가하는 것보다 위 표의 실제 설정·운영 훈련·부하 증거를 닫는 것이 제품 완성도를 더 크게 높인다.

### 9.3 다음 실행 순서

4090 노드가 준비되면 `Hub audit → snapshot staging → unpinned host evidence → reviewed digest pin →
strict preflight → 27B runtime challenger Dev/freeze/sealed Test → Shadow/workflow/fault → 8B model
challenger 동일 비교 → signed activation/rollback` 순서로 진행한다. GPU 작업과 병행해 실제 고객
반입 전에는 `RLS/OIDC production profile → image security → retention → OTel alert → backup restore →
20-session load`를 닫는다. 어떤 단계에서도 모델이 최종 결정을 만들거나 실제 환불·메일을 실행하지
않는다.

## 10. 2026-08-31 01:36 KST 실제 4090 호스트 갱신

Tailscale의 `workstation`에 저장된 SSH 별칭으로 접속해 추정이 아니라 실제 호스트를 확인했다.
Linux x86_64, 단일 RTX 4090 24,564 MiB, compute capability 8.9, driver 580.173.02, Docker
29.5.3과 NVIDIA runtime은 정상이다. 루트 파일시스템은 준비 전 299 GiB가 비어 있었고, 별도
owner-controlled 모델 캐시와 vLLM 0.28 이미지를 준비한 뒤에도 약 255 GiB가 남았다.

현재 18001의 기존 VLM은 같은 Community Qwen3.8-27B AWQ exact revision과 vLLM 0.26 digest를
사용하며 health 200이다. 이 프로세스가 22,626 MiB를 사용해 GPU 여유는 1,350 MiB다. 단일 GPU에서
18000 LLM 후보와 동시 실행할 수 없다는 사실이 확인됐고, preflight는 이를
`GPU_FREE_VRAM_BELOW_PREFLIGHT_MINIMUM`과 `GPU_COMPUTE_PROCESS_ALREADY_ACTIVE`로 정확히
차단했다. 기존 VLM은 중단하거나 변경하지 않았다.

27B runtime challenger에는 다음 실제 패키지 증거를 수집해 matrix에 고정했다.

- artifact 전체 15파일과 safetensors 21,018,000,928 bytes content digest
- vLLM 0.28 exact image digest와 264-line canonical dependency lock
- Python·dpkg 749개 구성요소 CycloneDX SBOM
- publisher model card와 artifact `quantization_config`에 묶인 quantization recipe evidence

모델 카드는 calibration dataset을 `cyankiwi/calibration-medium`으로 선언하지만 사용 revision은
공개하지 않았다. 이를 임의 revision이나 가짜 digest로 채우지 않았다. host preflight는 모든
artifact/runtime/private-bind/offline/package 항목이 일치하더라도 이 한 항목을
`CALIBRATION_DATASET_DIGEST_NOT_PINNED` 경고로 유지한다. 새
`SHADOW_READY_PROVENANCE_INCOMPLETE` 상태는 이 경고만 남은 경우 평가용 Shadow 기동만 허용하고,
`strict_ready=false`와 release assessment의 `CALIBRATION_DATASET_UNPINNED`을 유지한다. PRIMARY와
release eligible 승격에는 사용할 수 없다.

실제 호스트 Python이 3.10이라 저장소의 Python 3.12/`uv` 전제를 만족하지 않는 배포성 결함도
찾았다. candidate의 digest-pinned image 안에서 verifier와 preflight를 실행하는 container tooling을
추가했다. host network뿐 아니라 host PID namespace를 사용해 기존 GPU process가 컨테이너에서
0건으로 숨지 않게 했고, `--pull=never`와 read-only package mount를 고정했다.

현재 제품 판정은 여전히 **내부 시연 가능, 파일럿 시작 불가**다. 다음 GPU 행동은 기존 VLM을
자동 복원하는 명시적 유지보수 창에서 27B v0.28 Shadow Dev를 실행하는 것이다. 중단 허가 전에는
실행하지 않는다. 8B FP8은 별도 exact snapshot/package evidence가 아직 없으므로 그 다음 후보로
남는다.

### 10.1 2026-08-31 01:48 KST 공식 8B 패키지와 자동 복구 준비

HF CLI로 `Qwen/Qwen3-8B-FP8` exact revision을 별도 owner-controlled cache에 받았다. snapshot은
12파일, safetensors 9,436,628,784 bytes이고 content digest를 matrix에 고정했다. vLLM 0.26 exact
image의 canonical lock 265줄, Python·dpkg 745-component CycloneDX SBOM, 공식 model card와
`config.json`에 묶인 FP8 recipe도 고정했다.

공식 config는 `activation_scheme=dynamic`, `fmt=e4m3`, `weight_block_size=[128,128]`을 명시한다.
기존 계약은 이 공식 사전양자화 dynamic FP8에도 임의 calibration dataset digest를 요구했다. 새
`OFFICIAL_PREQUANTIZED_DYNAMIC_FP8` mode는 official source와 FP8 format일 때만 허용하고 dataset
digest가 있으면 오히려 거부한다. Community artifact가 이 예외를 주장하는 schema는 validation에서
실패한다. 8B 실제 preflight는 package/provenance 항목이 모두 PASS했고, 기존 VLM이 만든 GPU free
1,350 MiB와 active process 1건만 FAIL이다.

Python 3.12와 frozen application dependency를 포함한 349 MB 평가 전용 local image를 만들고 실제
GPU host에서 evaluator import와 `nvidia-smi` 가용성을 확인했다. 기존 VLM compose는 재기동 입력
변수가 현재 shell에 남아 있지 않아 중단 뒤 복구에 실패할 수 있었지만, 실행 중 값을 출력하지 않고
owner-only restore env로 캡처하고 실제 `docker compose config`를 통과시켰다.

`run_qwen4090_maintenance_dev.sh`는 명시적 `ALLOW_VLM_MAINTENANCE=YES` 없이는 exit 2로 거부한다.
허가된 실행에서는 exact VLM image와 health를 확인하고 EXIT trap을 설치한 뒤에만 VLM을 중단한다.
정상·평가 실패·candidate 실패·SIGINT 모두 candidate를 제거하고 기존 VLM을 재기동하며 18001
health 복구 실패는 별도 오류로 끝낸다. runner는 Dev만 지원하고 freeze/sealed Test는 열 수 없다.
현재 fail-closed refusal을 실제 호스트에서 확인했고 VLM health는 계속 200이다.

### 10.2 2026-08-31 03:55 KST 실제 4090 Dev 비교 결과

사용자가 승인한 유지보수 창에서 기존 18001 VLM의 exact image와 health를 확인하고 두 후보를
순차 실행했다. 모든 종료 경로에서 후보를 제거하고 기존 VLM을 자동 복원했으며, 최종 상태는
`running/healthy`, restart 0, Tailscale 전용 18001 health 정상이다. 실제 고객 데이터, 정책 결정,
환불·메일·결제 호출은 없었다.

| 후보 | Dev 성공 | schema/인용 valid | p50 / p95 | 출력 처리량 | 최저 여유 VRAM | 안전 관측 |
|---|---:|---:|---:|---:|---:|---|
| Community 27B AWQ, vLLM 0.28 | 23/120 | 19.17% / 19.17% | 3.437s / 4.626s | 34.50 tok/s | 2,350 MiB | injection·reasoning 0 |
| 공식 8B FP8, vLLM 0.26 | 49/120 | 40.83% / 40.83% | 1.830s / 2.823s | 50.49 tok/s | 2,122 MiB | injection 4/120, reasoning 0 |

27B 실패 97건은 모두 `LLM_INVALID_STRUCTURED_OUTPUT`이었다. 8B는 구조화 출력 실패 45건과 exact
source quote 불일치 26건이었다. 8B가 더 빠르고 valid 건수도 많았지만 prompt-injection 위반이 있어
서비스 후보로 승격할 수 없다. 두 후보 모두 Dev gate 실패이므로 freeze, sealed Test, Core Shadow,
workflow, fault/soak와 activation을 실행하지 않았고 release eligible은 계속 0개다.
Matrix의 `qualification`은 freeze 이후 release-grade 증거만 수용하므로 실패한 반복 Dev를 그 필드에
끼워 넣지 않는다. 따라서 machine assessment의 `PENDING_QUALIFICATION`은 “실행한 적 없음”이 아니라
“승격 가능한 qualification package 없음”으로 읽으며, 실패 Dev의 권위 있는 증거는 별도 result
manifest와 이 감사 기록이다.

8B 첫 기동 실패는 모델 결함이 아니라 owner-controlled snapshot을 `HF_HOME` 바로 아래에 둔 캐시
layout 오류였다. vLLM이 요구하는 `HF_HOME/hub/models--...` 구조로 동일 inode를 재배치한 뒤 exact
artifact digest preflight와 모델 alias canary가 통과했다. 자동 유지보수 runner는 후보 실패 시 제거
전에 mode 0600의 고유 startup log를 남기도록 보강했다. privacy-safe Dev 결과 2세트는
`evaluation/results/qwen4090_extraction_v2/`에 복사하고 manifest/result digest를 다시 검증했다.

시연 결론은 기존 VLM과 Core 설정을 유지하는 것이다. 8B는 다음 Dev prompt-tuning 기준 후보일 뿐
PRIMARY도 자동 fallback도 아니다. 기존 `2.0.0-local.2` prompt가 로컬 MLX에서 schema-valid를
개선한 선행 증거는 있지만 의미 정확도 한계가 있으므로, 별도 Dev profile로 검증하기 전 운영 prompt를
교체하지 않는다.
