# CSight 현재 상태 및 세션 인계

이 문서는 다음 작업 세션의 시작점이다. 최신 상태 요약은 갱신할 수 있지만, 세션 로그는
append-only로 유지한다. 상세 구현 증거는 `SPRINT_0_FOUNDATION.md`와
`SPRINT_1_CASE_EVIDENCE.md`, 독립 감사 증거는 `SPRINT_1_CLOSEOUT.md`, 현재 분석 경로는
`SPRINT_2_ANALYSIS_LLM.md`, 독립 감사 원장 `SPRINT_2_CLOSEOUT.md`, 실제 모델 기록
`SPRINT_2_5_QWEN38_SERVING.md`, `SPRINT_3_VISION_ANALYSIS.md`, 최신 구현 원장
`SPRINT_5C_CASE_RESOLUTION_CONSOLE.md`와 합성 시나리오 검증 계약
`SCENARIO_POC_ACCEPTANCE_RUNNER.md`를 참조한다.

## 0. 문서 메타데이터

| 항목 | 값 |
|---|---|
| 현재 완료 단계 | 내부 시연용 제한 운영 기반 `DEMO_READY_WITH_BLOCKERS`; clean imatrix Q5는 실제 RTX 4090 synthetic Dev에서 guarded `local.8` Extraction 15/15와 기존 runtime `local.2` Grounding 25/25 절대 gate를 통과했다. LLM Query Builder는 RAW→HYBRID 기준 미달이므로 후보 전체는 계속 `NO_WINNER`·`NO_RELEASE_ELIGIBLE`; 실제 고객 파일럿과 모델 출시 승격은 차단 상태 |
| 상담원 UI 개선 | 2026-09-20 14:00: 데이터 자산 관리자 설명 간소화·상세접기·전체/실운영 구분 PASS. 2026-09-19 19:26: 실제 grid display 누락 수정, 이미지 중심 좌표 검증 PASS. 2026-09-19 19:15: 사진 중앙정렬/크기 보완·원문 아래 안내문 제거 PASS. 2026-09-19 19:11: 상시 노란 피드백 배너 제거·사진/프레임 원본비율 반응형 적용 PASS. 2026-09-13 17:15 KST: 담당자/날짜/상태 고정 열로 흔들림 수정, E2E6·build/lint PASS, Web 반영. 2026-09-13 17:04 KST: 담당자 선택을 문의 행에 통합, 하단 흰색 구역 제거·Web 반영 PASS. 2026-09-13 16:59 KST: 검토 제목 중복 제거·요약 글자 위계·담당자 선택 디자인 개선. Frontend92/E2E15·type/lint/build PASS, Web dev 반영 healthy. 2026-09-11 10:39 KST: 이상가능성 게이지삭제·사진최상단/바로아래저장요약·Web반영 PASS. 앞선10:25: 고객·상품/주문·고정정책 하단 기본접기 추가, 기존Case URL도 미결정 검토로 직행. Web 재반영·Frontend92/E2E15 PASS. 앞선 10:18 구현: 문의 내용 중심 목록·검토 직행·사진/작은 상품 정보/요약/숫자 threshold/허용·비허용, 상세 접기 구현 및 로컬 API/Web 반영 PASS. 실제 상담 시간·판단 품질 비교와 인증 사용자의 전체 사용 확인은 NOT_RUN. [설계/효과 측정](../product/CONSULTANT_FOCUSED_UI_2026-09-11.md) |
| 진행 중 작업 | ADR-0126 오프라인 두 엔진 대조·ADR-0127 즉시 개선4건에 이어 ADR-0128 내부 SHADOW 실모델 피드백을 배포했다. 기존 상담원 UI에서 새 문의를 사용하며 피드백할 수 있다. 두 엔진 대조 전용 UI·실제 공동 의미 품질·학습·보안 HTTP 재자격은 별도 NOT_RUN이다. 다음은 사용자 인증 UI 전체 사용 확인과 대표 문의/사진·독립 정답 기반 GX10 평가다. Query Builder와 joint Dev 미통과로 NO_WINNER·PRIMARY 승격 금지를 유지한다. 9/2 임의 canary의 human_review_required=false는 승인 통제 실패 증거가 아닌 미평가다. |
| 마지막 갱신일 | 2026-10-18 KST — 논문 참고서 및 실제 2쪽 DOCX/PDF 초안·인계 갱신. 마지막 운영 관측은 2026-10-01 14:13 KST로 유지 |
| 추계 논문 작성 준비 | 2026-10-18: [참고서](../papers/CSight_2026_추계_2쪽논문_작성참고서.md) 기반 학생 양식 2쪽 DOCX/PDF·그림1·검증표1·본문 MD 작성. 김혜린/차인택·선문대 AI소프트웨어학과·황세웅 지도교수(교신저자) 반영. 두 페이지 시각검수 및 한글 뷰어 DOCX 열람/인쇄2쪽 PASS. native HWP 생성 후보 열람 실패로 미납품; 최종 HWP 저장·접수·신규 실험 NOT_RUN |
| 공개 영상·콘솔 경로 | 2026-09-29 21:17 KST: `doongdoong.org`·`www` 루트와 `/login`은 시연 영상, `/login2`는 CSight 로그인 폼 PASS. 비로그인 업무 경로는 `/login2`로 이동하며 `/auth/capabilities` 200·기존 비밀번호 로그인 허용 확인. 실제 자격 증명으로 로그인 완료는 NOT_RUN. Mac·Tunnel 실행 중에만 공개 링크 사용 가능. [배포 인계](../demo-video/public-site/README.md) |
| 실제 모델 역할 연결 | 15:04 새 합성 문의10건의 실제 Q5 Text-v2(local.8)→RAW/HYBRID/Top3→Grounding(local.2)→정책→검토대기10/10 PASS. E3 사진10건 검증 PASS. 별도 구형 multimodal text-v1은2건 부분 실패(재시도 포함4개 stage)를 보존한다. Query Builder·reranker 미사용. 사람 UI 피드백/고객 의미 품질은 NOT_RUN. [현재 검증](TEST_DATA_RESET_2026-09-10.json); 이전 역할/SHADOW JSON은 과거 snapshot |
| 내부 실모델 통합 후속 | 사용자 승인에 따라 ADR-0128·Migration0037을 실배포했다. 내부 피드백 프로필에서 표시된 SHADOW→정책→사람 검토→모의 처리를 허용한다. 기본/별도 pilot 차단, PRIMARY 모델 승격 금지, 사람 최종 확인·자동 업무 금지는 유지. 격리 DB workflow·왕복/drift와 실서버 drift PASS. [단계 결과](SHADOW_HUMAN_FEEDBACK_2026-09-10.json); [이전 BLOCKED](INTERNAL_REAL_MODEL_INTEGRATION_2026-09-10.json)는 최신 사용자 승인 이전 이력 |
| 서버 제어 앱 기동 확인 | 14:04 앱 공용 제어 backend 빠른 시작 PASS, Core9 healthy·API/Web/Embedding/공개 주소 정상. 로컬 표시 파일로 실모델 피드백 overlay를 선택하며 GX10 Q5·Mac E3·SSH loopback 연결을 관리한다. 이번에는 GUI 대화상자 재검증/전체 cold-stop은 NOT_RUN, 앞선 GUI PASS는 이력 보존. NVFP4·ComfyUI·4090 무변경. [사용 안내](../operations/INTERNAL_SHADOW_FEEDBACK.md) |
| 기술 멘토링 준비 | 외부 전달은 [멘토님 공유 HTML](../mentoring/CSIGHT_MENTOR_HANDOUT_2026-09-09.html) 수정본을 사용한다: 상담원 콘솔⇄Core⇄독립 LLM/Vision 아키텍처 도식 1개, 검증 경계, 3개 주제/미해결 질문 12개. 완료 개선 4건과 관련 설명·수치는 제외 상태를 유지한다. 모바일/접기·펼치기/인쇄 지원. [원문](../mentoring/CSIGHT_MENTOR_HANDOUT_2026-09-09.md)과 [80개 종합 질문](../mentoring/CSIGHT_TECHNICAL_MENTORING_BRIEF_2026-09-09.md)은 내부 상세 근거로 보존. 실제 자료 전송·멘토 답변·출시 승인 없음 |
| 최신 로컬 코드 검증 | 2026-09-10 오프라인1493 passed / 97 deselected / 기존 warning36. 격리 PostgreSQL repair/SHADOW3 PASS·0038 drift0·실서버 drift0. 전체 Pyright 오류0, 변경 Python Ruff/format·diff-check PASS, OpenAPI snapshot/generated 동기화 PASS. 이전 Frontend92·typecheck/lint/build PASS는 이력이며 이번 UI 재검증 아님. 고객 품질·출시 자격과 별개 |
| 연결 GitHub 계정 | `it0615` |
| 원격 저장소 | `CSightICT/csight-core` — Private. 현재 HEAD와 원격 기능 브랜치는 `f2357ba0cee6`으로 일치한다. 이번 GGUF·runtime·평가 변경은 미커밋이며 Commit·Push·PR·`develop/main` 병합 없음 |
| 로컬 Git | `codex/operator-console-product-direction`; clean worktree `/Users/ckdlsxor/Desktop/CSight_rc_cd6471c`, RC image/volume, 사용자 소유 미추적 문서와 `kaputt_best_vision_architecture.md`를 보존했다. 양자화 산출물은 Khrin의 owner-controlled `/home/data`에만 있고 Git에 포함하지 않았다. |
| 마지막 검증 관측 | 2026-10-01 14:13 KST, Mac·GX10 실행 Docker 컨테이너 0개, 전용 Q5 running=false/ready=false. 잔여 CSight 전용 E3(8093)·SSH 터널(18004)도 소유 확인 후 종료해 리스너 없음. API/Web/Embedding/공개 주소 응답 없음. Docker 볼륨 보존 |
| 마지막 GitHub 관측 | 2026-08-28 23:02 KST, `origin/codex/operator-console-product-direction`의 `3daaa7bff56fa0e25f7ca69bf6bc31d68a2cdb79`에 대한 CI Run #33177793237 PASS. PR·`develop/main` 병합 없음 |

## 1. 다음 세션 시작 체크리스트

최신 문서 작업(2026-10-18 KST): 한국디지털콘텐츠학회 학생 양식 실제 2쪽 논문 초안.
[x] 참고서와 원본 JSON/ADR을 바탕으로 캡스톤 설계·산업 기대효과 중심 본문 작성.
[x] 사용자 제공 저자·소속·학생 이메일·황세웅 지도교수(교신저자) 반영.
[x] 편집 DOCX·검토 PDF·본문 MD·400dpi 구조도·4행3열 검증표 생성.
[x] render_docx 두 페이지 PNG 시각검수·PDF 텍스트/쪽수/표·그림 개수 대조 PASS.
[x] 한컴 뷰어에서 DOCX 정상 열람 및 인쇄 미리보기 1/2·2/2페이지 확인.
[x] 합성40/30·별도Text-v2 10건 분모, 구형부분실패4회·사람/외부동작0·현장경제성미평가 보존.
[ ] 한글 편집기에서 공식 학생 양식 글꼴/서식을 확인하고 최종 HWP로 저장·2쪽 재검수.
미해결: native HWP 후보는 실제 열람 실패로 납품 제외. 학회 접수·교수 이메일/지원문구 확인은 별도.
다음: [초안 편집 메모](../papers/CSight_2026_추계_초안_편집메모.md)에 따라 공동저자 검토 후 HWP 저장.
이번 작업은 문서만 변경했으며 서비스 가동 상태를 새로 확인하거나 재기동하지 않았다.

최신 운영 변경(2026-10-01 14:13 KST): 사용자 요청으로 CSight Docker/PoC 스택 종료.
[x] 종료 전 Mac CSight Core9와 GX10 Q5 실행 확인.
[x] 전용 controller stop PASS: GX10 Q5, Core Compose, Embedding, 공개 터널 종료.
[x] 잔여 전용 E3(8093)·SSH 터널(18004) 프로세스를 식별해 TERM 후 리스너 없음 확인.
[x] 종료 후 Mac·GX10 실행 Docker 컨테이너 각각 0개, Q5 running=false/ready=false 확인.
[x] DB·업로드 Docker 볼륨 보존. 다른 GPU 작업 종료0.
[ ] 재기동은 사용자 요청 때 수행. 현재 API/Web/Embedding/공개 주소는 응답 없음.
미해결: 종료 자체는 없음. 다음: 사용자가 요청하면 전용 controller start로 복구하고
Q5·Core·터널·합성 연결을 새 시각에 다시 검증한다.

최신 운영 변경(2026-09-30 13:01 KST): 사용자 요청으로 내려가 있던 GX10 Q5 복구·연결.
[x] 사전 status에서 Q5 running=false/ready=false, GX10 Docker 컨테이너·GPU 계산 프로세스 0 확인.
[x] 다른 계산 작업 종료0(해당 작업 없음); 전용 controller start/canary PASS, GX10 Q5 단독 running.
[x] Mac SSH 터널/E3 HTTP200, Core9 healthy/API200, Worker SHADOW·llama_cpp 경로 확인.
[x] 배포 Worker 합성 Extraction·Vision·Embedding·Grounding PASS; DB 쓰기/업무 효과0.
[ ] 실제 계정 로그인부터 새 문의·검토까지 사용자 인증 UI 전체 흐름은 NOT_RUN.
미해결: 인증 UI 종단 사용 확인. 다음: 기존 계정으로 `/login2`에 로그인해 새 합성 문의를
등록하고 SHADOW 분석·사람 검토 화면을 확인한다. 모델 출시 자격은 기존 차단 상태.

최신 운영 변경(2026-09-21 19:55 KST): 사용자 요청으로 GX10 llama.cpp Q5 종료.
[x] 전용 controller stop PASS, running=false/ready=false, 다른 작업 종료0.
미해결: 없음. 다음: 새 분석이 필요할 때만 사용자 요청에 따라 엔진 재기동.

최신 완료(2026-09-20 17:49 KST): 운영 상태 하단 DB 적재 원복 적용(ADR-0131).
[x] ADMIN/local/internal-feedback/SYNTHETIC_DEMO 조직 범위 제한, 분석·사진·정책 보존.
[x] 결정 후속 기록 원자적 보관 후 검토 대기·배정해제·version 증가. 실제 초기화는 아직 미실행.
[x] 단위/API4·격리DB1(재결정/중복/오류 rollback)·Frontend93·브라우저2(1440/375px fixture) PASS.
[x] 변경 Ruff·Pyright0·Web typecheck/lint·이미지 build·diff-check PASS.
[x] DB 백업 후0039 실배포, API/Web healthy·실API schema/미리보기7건·보관0건 PASS.
[x] 기존 controller로 GX10 Q5 재기동, ready/running PASS. 다른 GPU 작업 종료0.
[ ] 실제 사용자 인증 UI에서 원복 버튼 최종 실행 NOT_RUN: 사용자 시연 시 실행.
다음: 화면 새로고침 → 운영 상태 하단 DB 적재 원복 →7건 확인 → 검토 대기부터 시연.
준비도/버전 상세는 접힘. 실제 실패는 유지. PILOT_LIVE 운영지표에 합성 성과 혼입 없음.
전체 신규 문의 실모델 종단 검증·실환불/고객 출시 자격은 이번 검증 범위 아님.


최신 재기동(2026-09-13 16:51 KST): [x] 기존 controller start 완료 [x] Core9 healthy
[x] API/Web/Embedding/E3 HTTP200 [x] GX10 Q5 ready 및 synthetic canary PASS [x] 최신 UI 유지.
다음: 기존 상담원 화면 새로고침. 전체 업무 E2E·고객품질은 이번 NOT_RUN. 아래9/10 차단은 과거 기록이다.


최신 요청: 서버 다시 켜기. 20:04 Core9/API/Web/공개주소/Embedding/E3 정상, 문의10건 유지.
[x] Docker Desktop·기존 서비스 재기동, 정지된 Tailscale을 기존 accept-routes 설정 그대로 연결.
[ ] GX10 전체 기동 BLOCKED: 여유12,652MiB로 안전 기준 미달. 기존Q5는 running/oom=false지만 Mac18004 터널은 없음.
[ ] 다른 `kllm-recovery-recovery-20260910a-0`의 vLLM이74,676MiB 사용. 임의 중단하지 않았다.
다음: 해당 컨테이너 중단 허용 여부를 사용자에게 확인하거나 메모리 반환 후 제어 앱 start 재실행.
[현재 기동 기록](SERVER_RESTART_2026-09-10_2004.json). 아래15:04 통합 PASS는 당시 관측이며 현재 전체 연결을 보장하지 않는다.

이전 완료 요청: 기존 데이터를 초기화하고 임시 데이터로 실제 사용을 테스트한다. DB 불일치도 점검·수정한다.
[x] DB 감사: 제약542·lineage29·원문hash115·사람결정32·보고서23 등 PASS.
[x] Migration0038: 파일 없는 과거 fixture Evidence7건 AVAILABLE→FAILED, machine receipt7건.
[x] 새 DB 백업 실제 복원·격리 repair/Shadow3개·오프라인1478·타입0·Core9 healthy.
[x] 사용자 추가 확인: **모든 테스트 고객사의115건 전부** 초기화. 계정·정책·인덱스·모델 서버 보존.
[x] 초기화 직전 post-repair DB+사진 백업·DB 실제 복원→정확56개 업무 테이블 초기화. 보존25개 테이블의 count/hash 동일.
[x] 원래 사진 bucket/121개 version 항목을 보존하고 새 빈 versioned bucket으로 전환. Core9 healthy·0038 drift0.
[x] 임시 SHADOW 문의/사진10건 적재. E3 10/10 검증, 구형 multimodal text-v1은2건 부분 실패(재시도 포함4개 실패 stage)를 보존.
[x] 실제 검색 응답500 발견→검색/Grounding 공개 응답 allowlist 수정·계약8개 PASS·Core 재배포.
[x] 별도 Text-v2→RAW/HYBRID→Grounding→정책→검토 대기10건 PASS. 사람 최종 결정/실제 외부 동작0.
[x] 최종 제약542·원문/사진10·검토packet10·citation pack10 무결성 PASS, 대기메시지0·drift0.
[ ] 담당자가 /reviews를 새로고침해10건을 확인·피드백한다. 사람 UI 조작과 의미 품질 확인은 미실행.
[ ] 별도 후속: 구형 text-v1 형식 실패 개선, 임시 로컬 백업의 장기/offhost 보존.
이력 없는 과거 fixture17건은 거짓 이력을 만들지 않고 사용자 승인 초기화에서 제거했다. 백업에 원본 이력을 보존한다.
[DB 감사 결과](DB_CONSISTENCY_2026-09-10.json). 14:13의 범위 BLOCKED는 이후 사용자 확인으로 해소됐다.
[x] 14:13 읽기 전용 인벤토리: 전체 문의115건, 현재 화면의 `csight`51건, 다른 tenant64건.
[x] 초기화 범위 확인: 전체 tenant115건, 사용자 명시 승인. 과거 출처 표시는 변경하지 않는다.
[x] 계정·정책/검색 인덱스·모델 서비스 보존, 새 백업/복구 확인과 초기화 완료.
[x] SHADOW 임시 적재→실제 비동기 검증. [단계 JSON](TEST_DATA_RESET_2026-09-10.json).

현재 요청 인계: [x] 내부 SHADOW 차단 해제·실모델 연결·실배포·백업·단계 JSON.
[x] 인증/tenant/사람 결정/모의 실행/기존 분석 이력 보존.
[ ] 사용자가 새 내부 테스트 문의를 등록해 인증 UI 전체 흐름을 직접 확인하고 피드백한다.
[ ] 공동 실모델 품질 평가·E3 상업 사용권·고객 pilot는 별도 미완료다.
새 사용은 제어 앱으로 시작하고 화면을 새로고침한다. 이전 mock/PRIMARY 분석을 재사용하지 않는다.
ADR-0128은 이전 SHADOW 업무 금지를 내부 사용에 한해 대체하며 출시 승격 금지를 대체하지 않는다.

- [ ] `CSight_project_docs/AGENTS.md`, 관련 설계 문서, Accepted ADR을 읽는다.
- [ ] 이 문서의 진행 중 작업, 미해결 사항, 다음 작업을 확인한다.
- [ ] `pwd`, `git status --short --branch`, `git remote -v`로 실제 저장소 상태를 확인한다.
- [ ] 필요하면 `docker compose --env-file .env -f infra/compose.core.yml ps`로 런타임을
  다시 확인한다.
- [ ] 변경 전 관련 테스트, Migration, API/Event 계약을 확인한다.
- [ ] 이번 세션의 범위와 하지 않을 일을 명시한다.
- [ ] 아래의 첫 번째 미완료 실행 항목부터 진행한다.

### 2026-09-11 UI 작업 인계 체크리스트

- [x] 규칙·현재 상태·관련 설계/ADR 및 기존 변경 확인, 기존 미커밋 작업 보존.
- [x] 문의 중심 목록/검토 직행/간결한 검토 화면·ADR-0130·API 계약·문서 반영.
- [x] Frontend92, E2E14(320–1440px 접근성 포함), 오프라인Python1493, 격리DB2 PASS.
- [x] Pyright0·변경Ruff/format·Web타입/lint/build·OpenAPI동기화·diff PASS.
- [x] 로컬 API/Web만 이미지 교체, 이전 환경값 전체 동일·이전 이미지 보존·Core9 healthy.
- [ ] 실제 로그인 담당자의 신규 UI 사용 피드백, 실제 상담 시간/결정 품질 비교.
- [ ] 기존 실모델/백업/출시 미해결 항목은 이전 인계대로 후속 진행.

다음 행동: 기존 로그인으로 `http://127.0.0.1:8080/cases`를 새로고침하고 문의 내용→검토를 확인한다.
이번에 새 분석/사람 결정/외부 업무는 생성하지 않았다. 모델 연결 설정 보존은 현재 모델 endpoint 사용 가능 증거가 아니다.

## 2. 단계별 상태

| 단계 | 상태 | 근거 또는 다음 조건 |
|---|---|---|
| Sprint 0 Foundation 구현 | PASS | 상세 기록과 2026-08-26 검증 결과 존재 |
| Sprint 1 Case & Evidence 구현 | PASS | 인증→Case→Evidence→Signed URL E2E와 전체 회귀 통과 |
| Sprint 1 독립 Closeout | PASS | P0/P1 미해결 0, 격리 Migration·Live Tenant·Object HEAD 포함 |
| Sprint 1 Migration·Seed | PASS | Head `20260826_0002`, Drift 없음, Seed 2회 반복 성공 |
| Sprint 1 Tenant·파일 보안 | PASS | Principal Scope, Role, Private MinIO, 실제 저장 메타데이터 검증, 요청·이미지 상한 적용 |
| Sprint 2 Analysis·LLM | PASS | Append-only Run/Attempt/Result, Outbox, Celery, Mock, vLLM Adapter, API |
| Sprint 2 Migration·Live | PASS | Head `20260826_0003`, 격리 왕복·Drift, 실제 RabbitMQ Mock Vertical Slice |
| Sprint 2 복구·멱등성 | PASS | Replay/Conflict, Duplicate 1 Result, Lease Recovery·Fencing·Max Attempt 종결 |
| Sprint 2 독립 Closeout | PASS | P0/P1 미해결 0, 정적·회귀·Migration·Docker·Live Gate 재통과 |
| Sprint 2.5 Qwen3.8 실제 서빙 | QUALIFIED_WITH_LIMITATIONS | 4090 Cold Start 2회, 26분 안정성, 안전 Gate와 실제 Backend E2E 통과; Action/Missing 품질 제한 |
| Sprint 3 Vision·Multimodal | MOCK_QUALIFIED | Canonical Vision, Snapshot, Text/Vision fan-out/join, Partial Success와 live Mock E2E 통과 |
| Sprint 3 실제 Vision | INTERNAL_E3_CONNECTED_WITH_LIMITATIONS | SHA 고정 E3를 loopback MPS endpoint와 Core에 연결; 합성 이미지 1건이며 제품 qualification 아님 |
| Sprint 4A LLM Contract v2 | PASS | v1 보존, v2 Prompt/Schema/Persistence/API와 live Mock 통과 |
| Sprint 4A Policy Reference | PASS | 합성 2 Tenant, 24 Document, 168 Clause, retired 6 |
| Sprint 4A Evaluation Data | PASS | 160/120/50/30/10, Gold missing·cross-tenant 0 |
| Sprint 4A 실제 Qwen 평가 | SKIPPED | Endpoint 미사용; `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE` |
| Sprint 4A 독립 Closeout | PASS | P0/P1 0, 정적·전체 회귀·데이터·Migration·Docker 재검증 |
| Sprint 4A 로컬 Commit | PASS | `6f3a667 feat: add LLM contract v2 and policy reference corpus`, Push·PR 없음 |
| Sprint 4B Corpus Ingestion | PASS | Tenant 2, Document 24, Clause 168, idempotent reuse, conflict 차단 |
| Sprint 4B Lexical/Dense/Hybrid | QUALIFIED_WITH_LIMITATIONS | Exact BM25, Qwen 1024-d exact cosine, weighted RRF; 합성 corpus 한계 |
| Sprint 4B Retrieval API | PASS | Principal tenant, 세 mode, metadata 선필터, provider-down 격리 |
| Sprint 4B Locked Evaluation | PASS | Dev 80 freeze, Test 40 한 번, correctness 위반 0 |
| Sprint 4B 독립 Closeout | PASS | P0/P1 0, 전체 회귀·실제 MPS·Migration·Docker 재통과 |
| Sprint 4B 로컬 Commit | PASS | `4216028 feat: add hybrid policy retrieval baseline`, Push·PR 없음 |
| Sprint 4C-1 Candidate Upper Bound | PASS | Dev로 K20/final10 선택, Test 진단 한 번, candidate recall 상한 0.9375 |
| Sprint 4C-1 Qwen Reranker | QUALIFIED_WITH_LIMITATIONS | 고정 revision, MPS 실서빙, concurrency 1; CPU·실사용 분포 미검증 |
| Sprint 4C-1 Reranked API | PASS | `HYBRID_RERANKED`, 두 tenant smoke, no fallback, provider-down 503 |
| Sprint 4C-1 Locked Evaluation | NO_MEASURABLE_GAIN | Test Recall 동일, MRR 0.53833→0.51250, nDCG 0.59841→0.59802 |
| Sprint 4C-1 Profile Persistence | PASS | Migration `0007`, reranker profile 1, ACTIVE execution profile 2 |
| Sprint 4C-1 독립 Closeout | PASS | P0/P1 0, 전체 회귀·외부 모델·Migration·Docker 재통과 |
| Sprint 4C-1 로컬 Commit | PASS | `14cae29 chore: qualify qwen3 policy reranker`, Push·PR 없음 |
| Sprint 4C-2 Holdout | PASS | 독립 Dev 80/Test 40, sealed, broken/cross-tenant 0, stable hash |
| Sprint 4C-2 Query Plan/API | PASS | Strict 1~3 query, append-only Run/Outbox/Query/Hit, POST/List/Get |
| Sprint 4C-2 LLM 실제 평가 | SKIPPED | `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE`; Mock 성능 미보고 |
| Sprint 4C-2 Locked Evaluation | BLOCKED_EXTERNAL_LLM | RAW가 deterministic보다 우수; 실제 LLM 미평가 |
| Sprint 4C-2 로컬 Commit | PASS | `feat: add case-based policy retrieval query planning`; Push·PR 없음 |
| Sprint 4C-3A Citation Pack | PASS | clause/version/source/query provenance immutable snapshot |
| Sprint 4C-3A Structural Guardrails | PASS | Grounding 50 + Injection 30, 위반 0, replay 100% |
| Sprint 4C-3A Async Runtime | PASS | PostgreSQL/RabbitMQ/Celery Mock, replay 200, tenant 404, provider-down no fallback |
| Sprint 4C-3A Semantic Grounding | SKIPPED | 실제 Qwen 부재; precision/recall/faithfulness 미주장 |
| Sprint 4C-3A 독립 Closeout | PASS | P0 0, P1 0, 전체 회귀·Migration·최신 Docker·Live Gate 통과 |
| Sprint 4C-3B Local MLX PoC | QUALIFIED_WITH_LIMITATIONS | Local extraction/query/grounding, RAW 유지, top-3 context, 실제 timeout fault 미실행 |
| Sprint 4C-3B 독립 Closeout·Commit | PASS | P0/P1 0, `d0950f6 feat: add local MLX LLM grounding PoC`, Push·PR 없음 |
| Sprint 5A Typed Policy Engine | PASS | registry/rule/effect/qualification/append-only runtime 및 전체 검증 완료 |
| Sprint 5A Synthetic Rule Set | PASS | Tenant 2, Rule Set 2, Rule 24, Source link 24, forbidden effect 0 |
| Sprint 5A Dev/Test Evaluation | PASS | Dev80 freeze, sealed Test40 1회; exact/condition/effect/source/version/replay 100% |
| Sprint 5A Migration·Live | PASS | 세 lifecycle 경로 drift 0, Core 6 healthy, async smoke와 tenant 격리 통과 |
| Sprint 5B Task·Packet·Audit | PASS | effect mapping 1.0.0, task/packet/CREATED 각 1, duplicate event NOOP |
| Sprint 5B Assignment·State | PASS | CAS claim, concurrent 1 success/1 conflict, release/evidence/resume/escalate |
| Sprint 5B Human Decision | PASS | authenticated human-only resolve, rationale/basis 검증, immutable decision 1개 |
| Sprint 5B Authorization | PASS | Viewer read-only, Manager/Safety Admin-only, assignee/Admin 및 tenant 격리 |
| Sprint 5B Dev/Test Evaluation | PASS | Dev60/Test30 sealed; workflow metrics 1.0, safety violation 0 |
| Sprint 5B Async Reliability | PASS | 4 outbox claim/lease/backoff/terminal state, 3 worker lease/fencing, hash fail-closed |
| Sprint 5B Migration·Live | PASS | `0012` 세 lifecycle/drift 0, Core 6 healthy, broker outage recovery·live smoke |
| Sprint 5B Git Handoff | PASS | `4aefae6 feat: add human review workflow`, 원격 5B 기능 브랜치 백업 완료; PR 없음 |
| Sprint 5C Resolution·Action Contract | PASS | Case와 분리된 projection/event, mapping 1.0.0, explicit input only, immutable Intent |
| Sprint 5C DRY-RUN Reliability | PASS | 두 durable outbox, worker fencing, deterministic network-free simulation, `LIVE` fail-closed |
| Sprint 5C Report·KPI | PASS | content-hashed `review_report/1.0.0`, tenant KPI numerator/denominator/sample count |
| Sprint 5C Customer Communication | PASS_WITH_SCOPE | immutable EMAIL simulation v1.1, 실제 SMTP/통지 0, `side_effects_performed=false`; terminal Report 필요 |
| Sprint 5C Tenant Data Asset | PASS_WITH_SCOPE | terminal Report와 같은 transaction에서 PII 원문 제외 append-only asset 자동 적재; 30/60건 기준선 Gate |
| Sprint 5C React Console | PASS | OpenAPI 기반 상담원 화면과 5개 fixture-driven Playwright 시나리오; 3–5는 live causal E2E 아님 |
| Sprint 5C Migration·Live | PASS | Head `0016`, 기존 Report backfill, drift 0, Core runtime healthy, Remote E3 설정 보존 |
| Sprint 5C Git Handoff | PASS | `0a5f529 feat: add case resolution and PoC console`, 원격 5C 기능 브랜치 백업 완료; PR 없음 |
| HDP-100 합성 Scenario Pack | OFFLINE_READY | fictional product, 36 synthetic Case/Gold, 10 clause/7 rule, 5 demo, acceptance 9/9 |
| E3 보고서 지표 | REPORTED_NOT_REPRODUCED | AP 0.884863, AUROC 0.931604, threshold 0.8984375는 담당자 보고 수치; CSight 재현 아님 |
| Binary Vision Runtime | ACTUAL_E3_INTERNAL | image-level any-defect E3 score와 threshold 해석을 실제 checkpoint로 live 연결; Mock 기본값은 회귀용으로 유지 |
| 실제 E3 Runtime | PASS_WITH_SCOPE | exact E3 SHA/size/schema, offline strict load, loopback HTTP, MPS forward와 Core append-only 저장 통과; 합성 연결 증거만 해당 |
| E3 Top-100 Positive Replay | PASS_WITH_SCOPE | selected-correct defect 100/normal 0 전수 forward와 hard-plastic Core 6건 통과; 연결 재현 증거이며 성능평가·제품 qualification 아님 |
| Kaputt Qwen VLM Offline Enrichment | BLOCKED | Query Crop+동일 상품 Reference Crop+비교 Prompt 4/4 기술 성공·민감 패턴 0; 상품 유형 1/4·defect-positive 0/2로 전체 Batch 품질 Gate FAIL, 공식 Label/E3 대체 금지 |
| Kaputt Qwen Product Metadata 30 | BLOCKED | 분리 schema로 30/30 성공·specific generic name 25·uncertain 5·금지/민감 필드 0. taxonomy 공백과 Human Gold 부재로 자동 Catalog 적용 전 사람 검수 필요 |
| Vision Assessment Migration | PASS | DB Head `0015`, migration lifecycle·drift와 append-only assessment persistence 통과 |
| Parallel Text/Vision Join | PASS | parent `FOR UPDATE` 직렬화와 terminal redelivery reconciliation; 새 live Run과 기존 orphan 복구 통과 |
| HDP-100 Git Handoff | PASS | 기능 `dfd6db2`, closeout `5c152fd`; local HEAD와 동일 원격 기능 브랜치 SHA 확인, PR·`develop` 병합 미실행 |
| R1 Visual-Aligned Inquiry Demo | PASS | 이미지 관찰과 고객 진술을 분리한 4~5문장 가상 문의 10건; 결함 후보 6·기준 미만 참고 4, seed/replay와 private Evidence SHA 검증 |
| R1 Fictional Product Catalog | PASS | 검증된 사진 10장에 표시 전용 가상 상품명·SKU·KRW 가격대·문의 목적을 매핑; 목록 검색/표시와 상세 상품 카드 적용, 실제 판매가·환불 입력 추론 0 |
| R2 Synthetic Commerce Context | PASS | `synthetic_commerce_context/1.0.0` 고객·주문·결제·배송 스냅샷 10건 DB 저장; 연락처/결제/운송장 마스킹, 가상 주소 표시, 환불 2건 결제금액=명시 환불액, Action 추론 0 |
| R3 Closed-set Demo Expansion | PASS_WITH_SCOPE | 기존 10건을 변경하지 않고 10건 추가, 최신 시연 팩 20건=결함 후보 12+사람 확인 저점수 참고 8. 실제 E3 성공·재실행 멱등성·Private Evidence integrity 통과, 상품군 4/4 표현. 성능평가·정상 확정·실제 Action 아님 |
| Korean Business-language Console | PASS_WITH_SCOPE | 문의 목록·상세·검토 대기함·검토 상세를 한글 상품명 우선으로 표시하고 현재 DB 상품 참조 49종에 표시 전용 이름 적용. 요청 유형·검토 유형·우선순위·페이지 제목·모의 처리 문구도 한글화. 식별용 주문/SKU와 API 값은 보존, 인증 화면 수동 육안 확인은 미실행 |
| Review Decision Workspace Readability | PASS_WITH_SCOPE | 허용/비허용 상세 화면을 최대 1540px, 결정 패널 460px 이상, 선택 버튼 90px로 확대하고 데스크톱 밀도·태블릿 한 열·모바일 보정을 적용. 인증 브라우저 육안 확인은 미실행 |
| Operator-friendly Policy Summary | PASS_WITH_SCOPE | 원본 정책 enum·qualification JSON·모델 식별자를 첫 화면에서 제거하고 정책 권고, 문의/이미지 분석, 일치 확인, 근거 정합성을 자연어 상태로 표시. 원본 API/DB snapshot은 불변 보존 |
| Operational-language Console | PASS_WITH_SCOPE | 화면과 출력 문서의 개발·검증 용어를 상담 업무 표현으로 교체하고 기존 `DEMO` 식별자·주소는 표시 단계에서 정리. 외부 결제·메일 시스템 미연결과 실제 처리 0 경계는 명시적으로 유지. 인증 화면 수동 육안 확인은 미실행 |
| Product Direction Rationale | PASS | 모델 중심 기술 검증에서 사람 확정형 상담 운영 제품으로 이동한 근거, 채택 원칙, 의도적 제외 범위와 실제 고객 승격 조건을 `docs/product/PRODUCT_DIRECTION_EVOLUTION_2026-08-28.md`에 기록 |
| Operator Workflow Git Handoff | PASS | 누적 변경 100개 파일을 `c90357d`로 커밋해 새 원격 브랜치에 Push. 고신뢰 Secret·1 MiB 초과 staged blob 0, 사용자 소유 문서 3개 제외, PR 없음 |
| R1 Three-Column Console | PASS | 문의 내용·이미지 근거·정책 기반 권고 3열, legacy v2 숨김·R1 fail-closed 표시, 하단 운영 상세 접기 |
| R1 Consultant Workspace Simplification | PASS | `지금 할 일` 단일 CTA·4단계 진행 표시·문의/이미지+정책 2열 본문·기술 정보 접기, 데스크톱 inert X 제거 |
| R1 Continue Policy-Date Recovery | PASS | 업무 시간대 `Asia/Seoul` 기준일 계산으로 UTC/KST 효력일 422 해소; API `{error}` 계약의 코드·메시지를 UI에 그대로 표시 |
| R1 Human-confirmed Quick Review | PASS | PoC 준비도 0.70 Gate, 정책 효과 기반 단일 허용 mapping·비허용 `REJECT_REQUEST`, 자동 basis/rationale, CAS Claim→Resolve→비동기 Report 자동 열기; 모델 자동 Decision 0 |
| R1 Refund Processing Confirmation | PASS | immutable report snapshot만 사용한 환불 전용 운영 문서·A4 인쇄 화면; 금액/통화 누락 fail-closed, 결제취소·고객통지·RMA 미연동 표시, 실제 환불 완료 주장 0 |
| CSight Commerce Fictional Policy | PASS | 신규 8 Document·52 Clause, 전체 20/136; 문서·Index `2.0.0`, canonical Rule Set `2.0.1` sole active |
| R1 Policy→Human Review | PASS | 수리·Safety·단순변심 3건이 Policy `SUCCEEDED`, matching Review `PENDING`; Decision·Resolution·Action 0 |
| R1 Public Sharing Gate | BLOCKED | Cloudflare Access·강한 Credential·이미지 재배포 권리 미확보; 현재 본인 내부 시연 전용 |
| Limited PoC 승격 | BLOCKED | 실제 기업 Data/Policy는 오늘 범위에서 의도적으로 제외; Privacy·제품도메인 Vision·Shadow·Qwen 증거 미확보 |
| Limited Pilot Service Foundation | DEMO_READY_WITH_BLOCKERS | 상담원 단일 조회·명시 확인·워크플로 snapshot, OIDC+PKCE/session/CSRF, tenant RLS, 민감 payload 수명주기, 3개 queue lane, 운영 조회, PRIMARY/SHADOW·회로 차단·admission, 선택적 OpenTelemetry를 additive migration으로 구현. 사람만 최종 결정하고 실제 사업 동작은 계속 0 |
| Operator Queue Server Search + Onboarding View | PASS | Case·Review 목록의 문의/주문/상품 번호 검색을 pagination 전 단일 SQL에 적용하고 검색어 고정 cursor를 사용한다. 관리자 운영 화면은 개인정보 없는 6개 온보딩 gate만 표시하며 현재 실제 조회는 인력 1개 PASS·나머지 5개 FAIL, `pilot_ready=false`다. |
| Generic Signed Case Intake 0032 | PASS | 단일 tenant/source/no-role actor에 고정된 Ed25519 raw-body 서명, ±300초, 128 KiB, exact replay 200·conflict 409를 구현했다. 실제 PostgreSQL HTTP에서 최초 201·replay 200·conflict 409와 Case/history/sensitive/idempotency 각 1건을 확인했으며 실제 고객 key는 생성하지 않았다. |
| Task Model Route Plan 0033~0036 | PASS_WITH_SCOPE | 서명된 activation을 task별 append-only route plan으로 연결한다. Analysis, LLM Query Builder, Grounded Explanation run이 새 요청에서 역사적 plan을 같은 transaction에 고정하고 Worker가 task/mode/signature/deployment/runtime identity를 provider 호출 전에 검증한다. Query Build v2와 Search v2는 별도 durable event와 worker lane으로 분리됐고 RAW·DETERMINISTIC query는 route와 모델 호출이 없다. 실제 20-workflow 부하 자격은 미완료다. |
| Separate Limited-Pilot Runtime | BLOCKED | OIDC-only, strict RLS role, ClamAV, retention, OTel, signed intake/model과 복원 증거를 강제하는 별도 Compose/controller/preflight를 구현했다. clean SHA의 RC image 빌드와 local candidate stack 검증은 완료했지만 실제 `.env.pilot`과 fresh 운영 증거가 없어 pilot start는 실행하지 않았다. controller는 build/migrate/prune/down/volume 삭제를 하지 않는다. |
| Operator Queue Intake UI | PASS_WITH_SCOPE | 프론트의 새 케이스 메뉴·버튼·화면을 제거하고 이전 `/cases/new`는 목록으로 전환. 상담 케이스·검토 대기함 모두 주문/상품/문의 번호 검색과 정렬을 제공하며 5개 viewport에서 두 컨트롤 48px, 가로 overflow 0, Axe serious/critical 0을 확인 |
| Demo Embedding Runtime Availability | PASS_WITH_SCOPE | macOS 제어 앱이 Qwen Embedding을 분리 세션으로 시작해 `/health`와 `/v1/models` 준비 후 Core 9개와 Cloudflare 공개 주소를 시작하고, 상태 표시와 안전 종료까지 함께 수행. 실제 stop→start 뒤 `doongdoong.org` health와 새 HYBRID Retrieval SUCCEEDED를 확인. 현재 Mac 내부 시연 전용이며 HA 자격은 아님 |
| Limited Pilot Qualification | BLOCKED | schema drift, strict DB login/RLS, Case 배정·직접 객체 권한, 개인정보 삭제, 이미지 보안 adapter, 세 task route guard, 20-client read와 120초 모델/결정 queue 격리는 구현·부분 검증했다. 고객 IdP lifecycle, 실제 20-session/20-workflow, release 모델, 암호화 off-host WAL·MinIO 반복 복원과 경보 전달은 미완료다. 새 pilot readiness는 구성 6개와 운영 자격 25개를 freshness/digest와 함께 fail-closed로 합산하며 replay/cancel은 자격 전까지 503이다. |
| Schema Drift Repair 0024 | PASS | evidence 복합 unique 조건부 복구, 운영 실패 check 18개 이름 수렴, similarity index ORM metadata 정합화. 빈 DB·기존 drift DB·현재 runtime이 모두 head/check 0이며 재빌드 Core 정상 |
| Waiting Ownership + Similarity Contract 0025 | PASS_WITH_SCOPE | WAITING 담당자·활성 assignment 보존, same-owner CLAIMED 재개, 기존 행 append-only recovery, cosine 0.0 보존, 기준 0.65 거리 최근접/최저 3개 계약과 실제 PostgreSQL lifecycle 통과. 자료 제출 포함 브라우저 전체 E2E는 후속 release gate |
| Case Intake Assignment + Direct Ownership 0026 | PASS_WITH_SCOPE | 관리자 Case CAS 배정·재배정, append-only 이력, 열린 Review owner 원자 상속, 목록/직접-ID reviewer 404와 restrictive RLS를 실제 PostgreSQL·API·브라우저에서 검증. 담당자 대기함과 처리 현황은 보고서 생성이 아닌 사람 결정 기록을 경계로 즉시 분리한다. unassign은 현재 제품 계약에 포함하지 않으며 terminal Case 재배정은 차단 |
| Terminal Customer Content Erasure 0029 | PASS_WITH_SCOPE | 원문 만료 transaction에서 사람 rationale/action payload, Case attributes, terminal report 고객·주문·배송 snapshot, communication과 resolution failure prose를 삭제하고 결정·보고서·안내 hash를 재계산. PII-free receipt와 deferred DB 재삽입 차단을 실제 PostgreSQL workflow로 검증. tenant retention 운영·log scan·backup/legal hold는 미완료 |
| Pilot Data Provenance 0030 | PASS_WITH_SCOPE | Case 생성 시 `SYNTHETIC_DEMO` 또는 fail-closed `NOT_ATTESTED`를 서버가 부여하고 DB trigger로 변경을 차단. KPI·SLA·drift readiness는 `PILOT_LIVE`만 집계하며 합성 60건 readiness=false를 고정. 현재 실표본 0건이고 trusted pilot intake 자격은 별도 필요 |
| Non-local OIDC-only Authentication | PASS_WITH_OPERATIONAL_GATE | 실제 Keycloak에서 PKCE·역할 매핑·return path·CSRF·idle expiry, 새 로그인 차단과 signed back-channel 기존 세션 즉시 회수까지 PASS. 고객 IdP에서 권한 변경→provider session 종료→전달 재시도·경보 연결은 파일럿 onboarding Gate |
| Product Readiness + RTX4090 Audit | BLOCKED_P0 | schema drift, strict login/RLS, 담당자 소유권·직접 객체 권한과 local qualification runner, clean calibration과 실제 two-candidate Dev 비교는 완료. 그러나 Dev `NO_WINNER`이고 immutable artifact custody·sealed Test·Shadow, 개인정보·고객 IdP·off-host restore·alert 자격이 남음 |
| RTX4090 Qwen Candidate Gate | BLOCKED_NO_WINNER | clean imatrix `8d1de2…d40f`, pinned llama.cpp b10419 image `c85eec…18ef`, attested corpus와 최종 mixed Q4/Q6 `318c24…248f`·Q5 `d709a4…2219` evidence PASS. Q5는 guarded `local.8` Extraction 15/15와 runtime `local.2` Grounding 25/25 synthetic Dev gate를 통과했지만 LLM Query Builder가 RAW→HYBRID 기준선에 미달한다. 최종 identity의 fresh 세 task 동시 PASS와 artifact revision·조직 미러·Test·Shadow100·workflow20이 없으므로 전체 selection은 계속 `NO_WINNER`·`NO_RELEASE_ELIGIBLE`, PRIMARY·자동 fallback 0 |
| GX10 Read-only Inventory | PASS | 공개키-only SSH로 ASUS GX10/ARM64/GB10 CC 12.1/약 128GB unified memory/4TB NVMe/Ubuntu 24.04.4/CUDA 13.0/Docker arm64/NVIDIA CDI를 확인했다. 10GbE link·실제 throughput과 GPU container canary는 `NOT_RUN`. compact 결과는 owner-only `local-data/gx10-inventory/2026-09-02T000756+0900/inventory.json`; 원격 write·설치·전송·service 변경 0 |
| GX10 Execution Plan | PASS | ARM64/CUDA 13/GB10용 pinned llama.cpp b10419 별도 image, control input 22,449 bytes, Khrin→GX10 Q5 18,679,614,080 bytes와 deferred imatrix 13,663,264 bytes의 exact source/destination/SHA-256/partial path/rollback을 owner-only `local-data/gx10-plan/2026-09-02T001239+0900/plan.json`에 고정했다. 원격 생성·전송·build·canary는 `NOT_RUN`; 해당 mutation은 사용자 확인 필요 |
| GX10 Runner + Control Bundle | PASS | 기존 4090 `amd64/sm_89` 계약을 보존한 별도 `arm64/sm_121` Dockerfile·build·Compose·Mac/remote runner를 구현했다. bash/focused pytest 9/9/Ruff/format/diff와 live status PASS; reviewed control 5개/22,198 bytes를 owner-only staging SHA 검증 뒤 새 최종 경로로 이동. PRIMARY/core route/fallback false |
| GX10 Q5 Direct Transfer | PASS | source-IP·일회성 token 제한 Tailnet HTTP로 Khrin→GX10 direct 전송, Mac data path 0. HTTP 200/18,679,614,080 bytes/597.393초/31.27 MB/s; source·partial·final SHA `d709a4…2219`, owner-only 0600 final PASS. one-shot server 자동 종료, image/container/PRIMARY·4090 service 변경 0 |
| GX10 ARM64 Build + GPU Canary | PASS_WITH_SCOPE | pinned llama.cpp b10419 commit `aee56b3…ef28`, CUDA 13.0.1 arm64/GB10 image `b664e8…9ac4`(6,732,715,596 bytes)을 host package 설치 없이 build. 첫 SME compiler 실패는 정확한 build tree만 종료했고 `GGML_CPU_ALL_VARIANTS=OFF`로 재build PASS. CDI read-only/no-network canary가 NVIDIA GB10을 확인하고 residue 0 |
| GX10 Q5 Isolated Serve + Canary | PASS_WITH_SCOPE | owner-only runtime env와 exact Q5/image hash gate로 private candidate `:18002` serve. pinned CLI의 reasoning 값 `none` 실패와 residue 0을 증거화한 뒤 `off`로 PASS. 합성 connectivity canary와 단일 performance smoke만 통과했고 Dev quality·4K/16K/32K·decode tok/s·peak memory는 `NOT_RUN`. report 뒤 exact project stop, container/network 0, PRIMARY/route 0 |
| GX10 Q5 Context + Concurrency Benchmark | PASS | strict synthetic JSON, warmup/profile, streaming usage로 4K c1/c2/c4와 16K·32K c1의 24/24 성공·timeout/schema fail 0. 4K c1 decode 11.486934 tok/s, 32K input 32,173 tokens PASS. c2/c4 tail latency가 9.92/23.03초로 악화. unified memory는 GB10 `nvidia-smi memory.used=N/A`라 `/proc/meminfo` system-used 출처를 명시. 4090 동일 harness·GX10 세 task Dev는 NOT_RUN, 역할은 Model Lab/SHADOW 후보, PRIMARY 0 |
| GX10 User-installed Qwen3.8 vLLM | PASS_WITH_POLICY_GAP | `RadixArk/Qwen3.8-27B-NVFP4`가 port 8000에서 health/models 200, text strict JSON과 synthetic image VLM exact match를 통과했다. vision/image/video config가 있으나 API context는 32K로 제한된다. 단일 정책 canary가 환불 불가 판단은 맞췄지만 `human_review_required=false`를 반환했으므로 사람 최종결정은 application/policy 계층에서 강제해야 한다. 세 task Dev·real evidence VLM·soak/capacity는 NOT_RUN, PRIMARY 0 |
| GX10 Three-task Dev Preflight | BLOCKED | 기존 driver는 4090 전용 post-start evidence와 matrix의 amd64/CUDA12.8 runtime digest를 필수로 묶는다. GX10 ARM64/CUDA13 endpoint를 직접 주입하면 runtime identity를 오귀속하므로 우회를 거부했다. API key Mac 복사·service start·4090 변경 0. additive GX10 identity/driver 계약 전 live Dev 금지 |
| GX10 Operational Latency Interpretation | PASS | 사용자 요구 문서당 300초 미만. 관측 최악 p95 23.028초는 한도의 7.68%, headroom 276.972초라 속도는 현재 운영 blocker가 아니다. benchmark는 short synthetic output이므로 documents/day·실제 workflow capacity는 NOT_RUN. 다음 Gate는 일일 문의량·reviewer capacity 대비 처리량/queue/failure와 three-task quality |
| GX10 Quality-first Priority | PASS | LLM이 Extraction·Query Builder·Grounding의 큰 역할을 맡으므로 quality→safety/uncertainty→capacity/reliability→latency 순서로 고정. 세 task 모두 absolute PASS와 final identity joint Dev가 필요하고 평균 점수로 한 task FAIL을 상쇄하지 않는다. 모델은 advisory이며 정책·인증된 사람 검토가 최종 결정 소유 |
| Text/Vision Diagnostic Alignment v1 | PASS | ADR-0126, canonical source/snapshot/SHA/tenant/run/stage 검증, 주장별 TYPE_CANDIDATE/UNRESOLVED와 추가 자료 코드, immutable offline report와 합성 계약 30/30. 기본 backend 1335 PASS·최종 집중 129 PASS·전체 Pyright/Ruff PASS. 실제 모델 정확도·정책/UI 연결은 NOT_RUN |
| GitHub 협업 문서·템플릿 | PASS | 브랜치 규칙, PR·Issue 템플릿, CODEOWNERS 작성 |
| GitHub PoC·MVP·Release Branch Audit | PASS | 현재 PoC=`feature/scenario-poc-hard-plastic`; MVP 통합 기준=`develop`; 최종 릴리스 기준=`main`. 별도 `poc/mvp/final` branch·tag 없음, PoC 최신화 후에도 역할 유지 |
| PoC 안전 원격 백업 | PASS | Secret·5 MiB 초과·가중치·원본 이미지 0. E3/backend `0f4de4b`, Web `b3e09cf`, handoff `81b6e20`을 fast-forward Push했고 CI #108 PASS; 사용자 소유 문서 3개 미추적 보존 |
| 초기 Git 안전성 감사 | PASS | 고신뢰 Secret·5 MiB 초과 파일 없음, 방어 Ignore 보강 |
| 로컬 Git 초기화 | PASS | `main` 초기 커밋 `6fc20d3`, 로컬 `develop` 준비 |
| GitHub 조직·저장소 | PASS | `CSightICT`와 Private `CSightICT/csight-core` 생성 확인 |
| GitHub 플러그인 조직 접근 | PASS | ChatGPT Codex Connector를 `CSightICT/csight-core`에만 설치하고 조회 확인 |
| 원격 브랜치·초기 CI | PASS | `main`·`develop`·작업 브랜치 Push, 세 초기 Actions Run 성공 |
| GitHub 거버넌스 PR | PASS | `chore/github-governance` → `develop` PR #2 Open, 최신 CI 성공 |
| `main`·`develop` 보호 규칙 | BLOCKED | Private 저장소의 현재 플랜에서 API HTTP 403; Issue #1로 추적 |

## 3. Sprint 0 완료 체크리스트

- [x] Python 3.12, `uv.lock`, Ruff, Pyright strict, pytest 기반
- [x] FastAPI health/readiness/system-info API
- [x] PostgreSQL/pgvector, RabbitMQ, MinIO Core Compose
- [x] Alembic vector baseline
- [x] LLM·Vision Port와 deterministic Mock Adapter
- [x] 분석 전체 버전 참조 계약
- [x] 얇은 Celery Application Use Case 진입점
- [x] 구조화 로그와 민감정보 Redaction
- [x] Architecture, Contract, E2E, Integration 테스트
- [x] ARM64 Docker 및 CI-safe GitHub Actions Workflow
- [x] GitHub Actions 원격 실행

## 4. Sprint 1 완료 체크리스트

- [x] 작업 전 Sprint 0 정적 검사·테스트·Compose·Health·Migration 회귀 확인
- [x] 기술 독립 Case/Evidence Domain, Enum, Port와 Application Use Case 구현
- [x] 기존 Baseline을 보존한 `20260826_0002` Migration과 8개 테이블 구현
- [x] Local/Test 전용 Idempotent Seed, Argon2id 로그인, HS256 JWT와 현재 Role 재조회
- [x] Principal 기반 Tenant Scope와 ADMIN·REVIEWER·QUALITY_VIEWER 권한 적용
- [x] Case 생성·목록·상세·상태 이력과 Tenant 단위 생성 Idempotency 구현
- [x] JPEG·PNG·WebP 실제 Decode, SHA-256, 크기·MIME·확장자·Pixel 검증
- [x] multipart 요청 선처리 상한과 잘못된 Pillow 입력의 안정적 4xx 오류 매핑
- [x] Private MinIO 업로드, 실제 Object HEAD 메타데이터 검증과 Signed GET 구현
- [x] Storage·DB 실패 보상, 보상 실패 안전 관측과 실제 PostgreSQL·MinIO 통합 테스트
- [x] 다른 Tenant `404`, Role, 위장 파일, Signed Download를 포함한 E2E 검증
- [x] README, 핵심 설계 문서, ADR-0006~0008과 Sprint 1 Progress 동기화
- [x] Case/Evidence 접수에서 실제 LLM·Vision 분석을 시작하지 않음
- [x] 독립 Closeout에서 P1 3건과 P2 4건을 수정·검증하고 P0/P1 미해결 0 확인
- [x] Closeout 승인 범위의 로컬 기준점 Commit만 생성하고 Push하지 않음

## 5. Sprint 2 완료 체크리스트

- [x] Sprint 1 기준점 `244c282`에서 `feature/sprint-2-analysis-llm` Branch 생성
- [x] Case와 분리된 Append-only Analysis Run·Stage·Attempt·Result 계약 구현
- [x] Code Prompt Manifest, Content Hash, Strict Schema와 정확한 Source Quote 검증
- [x] 결정적 Mock과 OpenAI-compatible vLLM JSON Schema Adapter 구현
- [x] Run·Stage·Idempotency·Outbox 원자적 생성과 여섯 ID Queue Payload 적용
- [x] `FOR UPDATE SKIP LOCKED` Dispatcher와 Claim Token·Lease Fencing Worker 구현
- [x] Transient Backoff, Permanent Failure, Max Attempt, Worker Lost·Timeout 복구 구현
- [x] POST 202/Replay 200/Conflict 409, 목록·상세, Case Latest Analysis 연결
- [x] Tenant `404`, 역할 권한, Raw Prompt·Response·Secret 비보존 검증
- [x] 기존 Revision 불변의 `20260826_0003` Migration과 여섯 테이블 구현
- [x] Ruff, 158-file Format, Pyright 0, Fast 291, Core Integration 31 통과
- [x] 실제 Docker Login→Case→Outbox→RabbitMQ→Celery→SUCCEEDED와 중복 전달 통과
- [x] 격리 Migration 왕복·Drift, 검증 행·임시 DB 정리, 장기 서비스 6개 Healthy 확인
- [x] README, 핵심 설계 문서 03–10, ADR-0009~0011, Progress 문서 동기화
- [x] Vision·Alignment·Policy·Routing·Review·Report·RAG를 구현하지 않음
- [x] 독립 Closeout에서 P0/P1 미해결 0과 전체 Gate 재통과 확인
- [x] 승인된 Sprint 2 로컬 Commit만 생성하고 Push·PR은 만들지 않음
- [x] 미추적 Kaputt 문서를 수정·삭제·Stage하지 않고 보존

## 5.1. Sprint 2.5 완료 체크리스트

- [x] Sprint 2 Commit `294cb5b`에서 전용 Branch 생성, Push·PR 없음
- [x] Qwen3.8 Artifact revision과 vLLM image digest 고정
- [x] RTX 4090 환경·기존 Process·Disk·RAM·Private Network 감사
- [x] Tailscale private bind와 `VLLM_API_KEY` 환경변수 인증; 노출 일회용 Key 즉시 회전
- [x] Text-only, Vision modality 0, 서버·요청 non-thinking 이중 설정
- [x] Cold Start 2회, `/v1/models`, 26분 Stability, OOM/Error/Restart 0
- [x] 100건 합성 평가와 Prompt 1.0.1 개선 후 안전 Gate 전부 통과
- [x] Human Spot-check 20건과 성능 Profile A–D, Peak VRAM 측정
- [x] 실제 외부 GPU 5건 Skip 0, Backend E2E 성공 Run 10
- [x] Model/Revision/Prompt DB Snapshot, Duplicate No-op, Timeout Retry·Max 확인
- [x] Raw Prompt/Response/Reasoning Column 0, unsafe Outbox Payload 0
- [x] 합성 Data·Queue·Orphan 0, Core Worker 기본 Mock과 6개 Health 복구
- [x] README, 설계 03·05·06·08·09·10, ADR-0012, Manifest와 Progress 동기화
- [x] 이 문서를 포함한 로컬 Commit `chore: qualify qwen3.8 27b serving on single 4090` 생성;
  정확한 SHA는 `git log -1`과 최종 인계에서 확인

## 5.2. Sprint 3 완료 체크리스트

- [x] Base `7d63cbb` 확인 후 `feature/sprint-3-vision-analysis` Branch 생성
- [x] Qwen 평가 taxonomy/metric/empty-set 감사와 diagnostics regression
- [x] Canonical Vision schema, tri-state quality, normalized bbox, native taxonomy mapping
- [x] 10개 deterministic Mock와 private multipart Remote Adapter
- [x] `analysis_run_evidence` Snapshot, bounded MinIO read와 SHA-256 검증
- [x] `vision_analysis_results`/`vision_detections` image별 append-only persistence
- [x] Text-only 호환과 multimodal Text/Vision independent Outbox fan-out
- [x] Application-level join, `PARTIAL_SUCCESS`, partial result 보존과 retry
- [x] 병렬 Run CAS 경쟁에서 Stage 고립 방지 및 live 재검증
- [x] `20260826_0004` empty/previous/downgrade-upgrade/drift Migration Gate
- [x] API detail `vision_results`/`failed_stages`, no-image 422
- [x] PostgreSQL/MinIO/RabbitMQ/tenant/duplicate/retry/partial Mock E2E
- [x] ADR-0013~0017, 설계 03~10, README와 Sprint 3 Progress 동기화
- [x] Ruff, Format 167, Pyright 0, Fast 328, Core Integration 36
- [x] Docker 6개 Healthy, Queue 0, 합성 Case 5/Object 4 정리
- [x] 외부 Vision은 실제 endpoint 미제공을 숨기지 않고 1건 Skip
- [x] 독립 Closeout에서 P0/P1 미해결 0과 전체 Gate 재통과
- [x] Push·PR 없음, Kaputt 사용자 파일 미수정·미Stage

## 5.3. Sprint 4A 완료 체크리스트

- [x] Sprint 3 Closeout Commit `330cbdb`, Push·PR 없음, Kaputt 파일 제외
- [x] `feature/sprint-4a-llm-reference-data` Branch 생성
- [x] Text Extraction v1 호환과 v2 Pipeline/Prompt/Schema `2.0.0/2.0.0/2.0`
- [x] Declared/Extracted action과 Text/System missing 책임 분리
- [x] Completeness/action consistency rule `1.0.0`과 exact requested-action quote
- [x] 기존 v1 table 불변의 append-only v2 child Migration `20260826_0005`
- [x] Policy Query Builder/Grounded Explanation design-only Prompt/Schema
- [x] 합성 Policy Corpus 2 Tenant, 24 Document, 168 Clause, retired 6
- [x] Extraction 160, Retrieval 120, Grounding 50, Injection 30, Demo 10
- [x] Stable build/hash, manifest, quality/coverage report와 Make commands
- [x] ADR-0018~0025, data guide 4개, 설계 03~10과 README 갱신
- [x] 실제 Docker v2 Mock `SUCCEEDED`와 합성 row/queue 정리
- [x] Sprint 4A 최종 전체 Gate 실측값 확정
- [x] Sprint 4A Commit·Push·PR 없음, Kaputt 파일 미수정·미Stage

## 5.4. Sprint 4B 완료 체크리스트

- [x] Sprint 4A 독립 Closeout 후 정확한 로컬 Commit `6f3a667` 생성
- [x] `feature/sprint-4b-policy-retrieval` Branch 생성, Closeout 후 로컬 Commit 승인, Push·PR 없음
- [x] `20260826_0006`과 ingestion/document/clause/profile/embedding/index 6개 table
- [x] Normalized JSONL/manifest 기반 ingestion, 24 document/168 clause, 반복 run 재사용
- [x] 동일 document version의 다른 content hash를 명시적 mismatch로 차단
- [x] Principal tenant, ACTIVE, effective interval과 allowlisted metadata 선필터
- [x] Exact BM25와 versioned Korean tokenizer; dev k1 1.2/b 0.75 freeze
- [x] Qwen3-Embedding-0.6B pinned revision, 실제 1024-d MPS embedding 168개
- [x] pgvector exact cosine similarity와 NaN/Inf/dimension 검증
- [x] Versioned weighted RRF k20/lexical1.5/dense0.5, dedupe/stable tie
- [x] Read-only LEXICAL/DENSE/HYBRID API; decision/tenant/vector/internal ID 미노출
- [x] Provider down에서 lexical 200, dense/hybrid 503, Core ready 200
- [x] Dev 80에서 profile 선택 후 Test 40 한 번 실행; 이후 재튜닝/재평가 없음
- [x] Cross-tenant/future/retired/wrong-version/hard-negative/duplicate 0, determinism 100%
- [x] Qwen host-native qualification, external embedding Skip 0
- [x] ADR-0026~0038, RAG guide 4개, model manifest, 설계 03~10, README 갱신
- [x] 사용자 `kaputt_best_vision_architecture.md` 미수정·미삭제·미Stage

## 5.5. Sprint 4C-1 완료 체크리스트

- [x] Sprint 4B를 `4216028`로 로컬 Commit하고 전용 Branch 생성; Push·PR 없음
- [x] Frozen HYBRID_RRF 후보 K 10/20/30/50와 oracle 상한을 Dev에서 측정
- [x] Dev만으로 candidate K 20, final K 10 선택; Test 후보 진단은 한 번만 실행
- [x] Qwen3-Reranker-0.6B artifact revision, serialization, score 의미와 runtime 고정
- [x] Host-native MPS private service와 health/models/rerank endpoint 실제 검증
- [x] Pair token 길이·truncation, cold/warm latency, K별 latency와 concurrency 측정
- [x] Technology-neutral Port/Profile과 Remote·Mock Adapter, complete-set 검증
- [x] 기존 세 mode 불변의 `HYBRID_RERANKED`, no fallback, provider-down 503
- [x] Migration `20260826_0007`, immutable reranker/execution profile과 tenant resolution
- [x] Dev 80 freeze 후 locked Test 40 한 번; Test 결과로 profile 재조정하지 않음
- [x] Correctness 위반과 candidate mutation 0, Dev deterministic rerun 100%
- [x] 실제 두 tenant reranked smoke와 기존 mode/provider-down 회귀
- [x] ADR-0039~0048, architecture/evaluation guide, manifest, progress, README 동기화
- [x] Ruff·Format·Pyright·Fast·대상별·Integration·External·Migration·Runtime Gate 통과
- [x] `RERANKER_NO_MEASURABLE_GAIN`을 숨기지 않고 Sprint 4C-2 입력으로 보존
- [x] Sprint 4C-1 Commit·Stage·Push·PR 없음, Kaputt 파일 미수정·미삭제·미Stage

## 5.6. Sprint 4C-3A 완료 체크리스트

- [x] Sprint 4C-2를 `a282817` 로컬 Commit으로 고정하고 전용 Branch 생성
- [x] 성공 Retrieval Run에서 immutable content-hashed Citation Pack 생성
- [x] rank, clause/document version, source/effective/query/retrieval provenance snapshot
- [x] 고정 중립 summary, 문장별 citation 필수, decision-free strict output schema
- [x] Citation allowlist, duplicate normalization, tenant/version/effective-date fail-closed 검증
- [x] Append-only profile/pack/item/run/result/outbox Migration `20260827_0009`
- [x] Identifier-only Queue, thin Celery Worker, no silent fallback
- [x] Case 하위 POST/List/Get, Principal tenant scope, Viewer read-only
- [x] Mock orchestration과 vLLM strict JSON/citation contract 테스트
- [x] Grounding 50 + Prompt Injection 30 구조 평가, 위반 0, replay 100%
- [x] Semantic citation/unsupported claim/faithfulness를 실제 Qwen 부재로 SKIPPED
- [x] ADR-0059~0064, RAG architecture/evaluation guide, manifest, progress 동기화
- [x] 독립 Closeout에서 P0/P1 미해결 0, 최신 Docker Build·Live Runtime 재통과
- [ ] 실제 Qwen 4C-3B Dev qualification → freeze → sealed Test
- [ ] Sprint 5 versioned Policy Engine + Human Review 연결

## 5.7. Sprint 5A 진행 체크리스트

- [x] Sprint 4C-3B를 `d0950f6 feat: add local MLX LLM grounding PoC`로 로컬 Commit
- [x] `feature/sprint-5a-policy-engine-core` 브랜치 생성; Push·PR 없음
- [x] Typed field/operator registry와 missing/qualification semantics 구현
- [x] Final decision을 표현할 수 없는 effect allowlist와 human-review gate
- [x] Synthetic tenant 2, rule set 2, rule/source link 24/24 build·validation·DB ingestion
- [x] Source clause same-tenant/version/hash/effective interval 검증과 immutable version conflict 차단
- [x] Migration `20260827_0010_policy_engine`, rule/runtime/outbox 10개 table과 drift 0
- [x] Frozen typed input/qualification snapshot, 고객 원문·grounding text 비복제
- [x] POST 202/replay 200/List/Get와 identifier-only outbox/RabbitMQ/Celery route
- [x] Pure deterministic engine, append-only result, duplicate task `NOOP`
- [x] Dev80 freeze 후 sealed Test40 단 1회; rerun guard와 artifact verifier
- [x] ADR-0065~0076, Policy 문서 4개, README/설계/Makefile 동기화
- [x] 전체 Ruff/Format/Pyright/default/integration/migration lifecycle 최종 실행
- [x] 최신 Docker image rebuild, 5 queues consumer, API live smoke 및 cross-tenant/duplicate 검증
- [x] 최종 실제 수치를 Sprint 5A 문서와 아래 session log에 append

## 5.8. Sprint 5B 완료 체크리스트

- [x] Sprint 5A 독립 감사 후 `67eafdd feat: add versioned policy engine core` 로컬 Commit
- [x] `feature/sprint-5b-human-review-workflow` 생성; `4aefae6` Commit과 동일 원격 기능 브랜치 백업, PR 없음
- [x] Policy effect 집계와 `review_task_mapping/1.0.0` task type/priority 결정
- [x] 성공 Policy Evaluation과 `human_review.requested.v1` durable event 원자 저장
- [x] identifier-only `human-review` queue, bounded retry, thin task-creation worker
- [x] Task/Packet/CREATED action 원자 생성과 duplicate event/task NOOP
- [x] allowlisted metadata·qualification·policy/analysis provenance immutable packet/hash
- [x] PENDING/CLAIMED/WAITING/ESCALATED/RESOLVED typed state machine
- [x] CAS/row-lock claim, current assignment unique, concurrent claim 1 success/1 conflict
- [x] Release, evidence request, Admin/new-evidence resume, escalation과 assignment history
- [x] Viewer read-only, reviewer assignee scope, Manager/Safety/Escalated Admin-only
- [x] 명시적 human Resolve만 Decision/Basis/RESOLVED action/projection 원자 생성
- [x] Rationale 10–2000, policy basis 필수, citation/rule/evidence/run/tenant fail-closed
- [x] deterministic outcome relation 1.0.0과 task당 immutable Decision 1개
- [x] Queue/List/Detail/Case list와 여섯 action API, raw model/audit payload 비노출
- [x] Migration `20260827_0011_human_review` 7개 table, 세 lifecycle, drift 0
- [x] Human Review evaluation Dev60 freeze 후 sealed Test30 단 1회, verifier PASS
- [x] ADR-0077~0088, Review 문서 5개, README/설계/Make/환경 문서 동기화
- [x] Ruff, Format, Pyright, 전체 default/integration, Docker/queue/live smoke 검증
- [x] Migration `20260827_0012_async_reliability`, 네 Outbox claim/lease/backoff/terminal state
- [x] Retrieval·Grounding·Policy worker lease/fencing과 permanent/retry-exhausted 실패 기록
- [x] Packet·Decision hash 조회/Resolve 직전 재검증과 변조 fail-closed
- [x] Integration 임시 DB 격리·실행 후 삭제·잔존 0 검증
- [x] 실제 RabbitMQ 중단→backoff→복구와 duplicate delivery `NOOP` 검증
- [x] 외부 환불·교환·결제·CRM·알림·Decision revision 미구현 유지
- [x] 사용자 `kaputt_best_vision_architecture.md` 미수정·미삭제·미Stage
- [x] 사용자 `CSight_MASTER_HANDOFF_2026-08-27.md` 미수정·미삭제·미Stage

## 5.9. Sprint 5C 완료 체크리스트

- [x] `4aefae6`에서 `feature/sprint-5c-case-resolution-external-action` 생성
- [x] ADR-0089~0095와 Resolution architecture/state/input/demo boundary 계약 고정
- [x] Case 상태와 분리된 CAS Resolution Projection과 append-only Resolution Event 구현
- [x] `human_decision_to_external_action/1.0.0`의 네 승인 Action과 두 terminal mapping 구현
- [x] Case reference와 명시적 flat `external_action_input`만 허용하고 추론·기본값·coercion 차단
- [x] 누락·잘못된 입력을 `ACTION_NEEDS_INPUT`으로 종결하고 Intent/Attempt/Result 0 보장
- [x] 서로 다른 두 번째 Decision을 자동 대체하지 않고 `MANUAL_FOLLOW_UP_REQUIRED`로 종결
- [x] Decision·Resolution request 원자 저장, immutable typed Action Intent와 두 durable outbox 구현
- [x] Resolution/Simulation exact-event 검증, claim/lease/backoff/fencing, duplicate `NOOP` 구현
- [x] network-free deterministic `DRY_RUN`, `side_effects_performed=false`, `LIVE` fail-closed 구현
- [x] Resolution/Event/Intent read-only API와 tenant scope, cross-tenant `404`, `no-store` 구현
- [x] terminal Resolution별 immutable `review_report/1.0.0`과 printable 화면 구현
- [x] numerator/denominator/sample count와 zero-denominator null을 제공하는 PoC KPI API·화면 구현
- [x] React·TypeScript·Vite console, memory-only JWT, opaque checkpoint, `/api` proxy 구현
- [x] Backend default 554, Integration 51/5 skipped, DB head `0014` drift 0 검증
- [x] Frontend lint/type/OpenAPI/build, Vitest 6, Playwright 5 검증
- [x] 7 services healthy, 8 queues consumer 1/depth 0, live Decision→validated `DRY_RUN` 검증
- [x] 실제 RabbitMQ outage의 PENDING attempt 3→CONSUMED attempt 5와 final validated 검증
- [x] 5개 demo의 증거 수준을 구분하고 Scenario 3–5를 fixture-driven UI/component-backed로 기록
- [x] Sprint 5C 완료 당시 판정을 `SYNTHETIC_MOCK_SIMULATION_DEMO`로 유지하고 Limited PoC 외부 증거를 미해결로 기록
- [x] `0a5f529 feat: add case resolution and PoC console` Commit과 동일 원격 기능 브랜치 백업, PR 없음
- [x] 사용자 소유 루트 문서 두 개 미수정·미삭제·미Stage

## 5.10. HDP-100 합성 시나리오 기술 PoC 진행 체크리스트

- [x] 가상 브랜드의 fictional `HDP-100` 수동 펌프형 경질 플라스틱 상품 범위 고정
- [x] 실제 기업·고객 자료 없이 synthetic Case 36건과 1:1 Human Gold 36건 구성
- [x] version/effective date를 가진 synthetic policy 10 clause와 deterministic rule 7개 구성
- [x] DRY-RUN·입력 누락·기능 증거 요청·Safety·Vision Timeout의 demo 5개 고정
- [x] pack artifact/hash/reference/safety 경계를 acceptance runner로 offline 9/9 검증
- [x] E3를 위치·유형 없는 `BINARY_ANY_DEFECT_CLASSIFICATION` 후보로만 명세
- [x] 담당자 보고 AP 0.884863, AUROC 0.931604, threshold 0.8984375를 출처 경계와 함께 기록
- [x] 위 E3 지표를 `report_metrics_reproduced_by_csight=false`로 표시하고 CSight 성능 주장 차단
- [x] score `>= 0.8984375`는 `HIGH_CONFIDENCE_DEFECT_CANDIDATE`, 미만은 정상 판정이 아님을 고정
- [x] binary image assessment를 기존 Detection과 분리하고 Mock 회귀 계약과 실제 E3 내부 runtime을 각각 live 연결
- [x] `20260827_0015_vision_image_assessment`를 현재 DB Head로 적용
- [x] 실제 기업 Data/Policy는 오늘 시나리오 범위에서 의도적으로 제외
- [x] 실제 E3 checkpoint package와 host-private loopback serving endpoint 확보
- [x] 실제 E3 이미지 inference, immutable model identity, latency와 threshold 계약을 synthetic connectivity image로 검증
- [x] safe stop→idempotent setup→server restart 뒤 동일 synthetic score와 Docker Worker health 200 재확인
- [ ] 실제 endpoint timeout→retry recovery와 malformed-response fail-closed를 live fault injection으로 검증
- [x] parallel Text/Vision terminal join race 수정본의 live causal 재검증 완료
- [x] 현재 branch의 정확한 default/integration/static/runtime 수치를 별도 원장 행으로 추가
- [x] 사용자 소유 루트 문서 두 개 미수정·미삭제·미Stage

## 6. GitHub 협업 구축 체크리스트

- [x] 연결 계정 `it0615` 확인
- [x] 경량 GitFlow와 브랜치 명명 규칙 문서화
- [x] PR 템플릿과 Issue Form 작성
- [x] 초기 CODEOWNERS를 `@it0615`로 지정
- [x] 모든 세션 종료 시 상태 문서를 갱신하도록 `AGENTS.md`에 규칙 추가
- [x] 초기 커밋 대상의 Secret·대용량·Binary 안전성 감사
- [x] 로컬 Git을 `main`으로 초기화
- [x] 로컬 Foundation 초기 커밋 `6fc20d3` 생성
- [x] 로컬 `develop` 장기 브랜치 생성
- [x] 조직 handle `CSightICT`와 저장소 `csight-core` 확정
- [x] GitHub 브라우저에서 `it0615` 로그인 확인
- [x] `CSightICT` 조직 생성 및 설정 권한 확인
- [x] Private `CSightICT/csight-core` 저장소 생성
- [x] GitHub 플러그인에 `CSightICT/csight-core`만 접근 승인
- [x] GitHub CLI OAuth에 `workflow` scope 승인
- [x] 원격 `main` Push
- [x] 원격 `develop` 장기 브랜치 생성
- [x] 원격 `chore/github-governance` 작업 브랜치 Push
- [x] 첫 GitHub Actions 성공 후 Required check Context `Quality and fast tests` 확정
- [x] Squash·Merge 허용, Rebase 비활성화, 병합 후 브랜치 삭제 설정
- [x] 거버넌스 PR #2를 `develop` 대상으로 생성
- [ ] `main`과 `develop` Branch protection 적용 — 현재 Private 플랜 제약으로 BLOCKED, Issue #1
- [ ] 팀·협업자 권한과 조직 단위 CODEOWNERS 갱신

## 7. 마지막 검증 원장

2026-10-18 실제 논문 초안 검증 PASS: 공식 학생 HWP의 페이지/단/글자 설정을 추출해
DOCX에 대응; render_docx의 최종 PNG2장 시각검수(한글 누락·표 잘림 없음), pypdf로 A4 2쪽,
저자/소속/이메일/교수/40·30·10/10·참고문헌 추출, python-docx로 그림1·표1(4행3열) 대조.
한글 뷰어의 DOCX 정상 열람과 인쇄 미리보기2쪽 확인. 독립 본문·그림 근거 검토 필수수정0.
PDF 미리보기에서 지정 글꼴의 함초롬 대체와 영문 참고문헌 자간/정렬 차이는 편집 메모에 기록.
native HWP 후보는 파서 성공 후 실제 한글 뷰어에서 손상 오류가 나와 FAILED/미납품으로 처리.
최종 HWP 저장·학회 접수·새 실험·서비스 시험 NOT_RUN. 앱/DB 변경 없음으로 코드 검사 SKIPPED.
검증 기록: `tmp/paper-20261018/final_verification.json`.

2026-10-18 선행 참고서 작업 검증(위 실제 초안 이전): 공식 국내 추계 안내·제출 폼·HWP 본문/참고문헌 확인 PASS.
Python JSON/JSONL 파싱으로 정책 Gold dev80/test40·검토 dev60/test30 및 Manifest/지표 hash
일치, 고유 Case10의 Text-v2/검색/설명/정책 PASS 상태, 전체 분석22=성공18/부분성공4,
사람결정0을 대조 PASS. 참고서 로컬 링크33개(고유23경로) 존재·코드 fence 균형 PASS.
문서 독립 검토의 양식·Grounding/정책 별도 경로 표현 보완 반영. 기존 실험 재실행·GPU·서버
기능 시험·실제 사용자 평가·HWP 렌더링·학회 제출 NOT_RUN. 앱 코드·DB 변경이 없어
Migration·Ruff·Pyright·기본 pytest는 SKIPPED. 아래 이력은 해당 실행일의 검증으로 유지한다.

| 날짜 | 명령·검사 | 상태 | 실제 결과 |
|---|---|---|---|
| 2026-08-26 | `uv sync --frozen --group dev` | PASS | Python 3.12 환경과 lockfile 설치 |
| 2026-08-26 | Ruff / Ruff Format | PASS | 80 files |
| 2026-08-26 | Pyright strict | PASS | 0 errors, 0 warnings |
| 2026-08-26 | 기본 pytest | PASS | 37 passed |
| 2026-08-26 | Core Integration | PASS | 4 passed |
| 2026-08-26 | Architecture / Contract / E2E | PASS | 2 / 14 / 3 passed |
| 2026-08-26 | `make test-all` | PASS | 기본 37 + Integration 4 |
| 2026-08-26 | Compose와 Health 장애·복구 | PASS | 정상 200, RabbitMQ 장애 503, 복구 200 |
| 2026-08-26 | Git 초기 커밋 안전성 | PASS | 고신뢰 Secret·5 MiB 초과 파일 없음, Ignore 적용 확인 |
| 2026-08-26 | 협업 문서 YAML | PASS | Issue Form 4개와 CI Workflow 파싱 |
| 2026-08-26 | Foundation 초기 커밋 | PASS | `main` commit `6fc20d3` |
| 2026-08-26 | GitHub 조직·Private 저장소 | PASS | `CSightICT/csight-core`, People 2명 확인 |
| 2026-08-26 | 원격 `main` Push | BLOCKED | OAuth App에 `workflow` scope가 없어 서버가 거부 |
| 2026-08-26 | GitHub CLI scope 갱신 1차 | FAIL | 장치 인증 Polling 중 HTTP 502, 재시도 필요 |
| 2026-08-26 | GitHub 플러그인 저장소 조회 | BLOCKED | `CSightICT/csight-core` 404, 설치 범위 밖 |
| 2026-08-26 | GitHub 원격 CI | NOT_RUN | 원격 브랜치가 아직 Push되지 않음 |
| 2026-08-26 | GitHub CLI scope 갱신 2차 | PASS | `repo`, `read:org`, `gist`, `workflow` scope 확인 |
| 2026-08-26 | 원격 브랜치 Push | PASS | `main`, `develop`, `chore/github-governance` 추적 브랜치 생성 |
| 2026-08-26 | ChatGPT Codex Connector 설치 | PASS | `CSightICT/csight-core` 단일 저장소 범위로 조회 확인 |
| 2026-08-26 | 초기 GitHub Actions | PASS | 세 브랜치 성공, Check Context `Quality and fast tests` |
| 2026-08-26 | 저장소 병합 설정 | PASS | Squash·Merge 허용, Rebase 비활성화, 병합 후 브랜치 삭제 |
| 2026-08-26 | `main`·`develop` 보호 규칙 API | BLOCKED | Private 저장소의 현재 플랜에서 HTTP 403 |
| 2026-08-26 | 보호 규칙 추적 Issue | PASS | Issue #1 생성 |
| 2026-08-26 | 거버넌스 PR 생성 | PASS | PR #2 Open, `chore/github-governance` → `develop` |
| 2026-08-26 | 거버넌스 PR 최신 CI | PASS | Head `7298cda`, Run `32867908663`, `Quality and fast tests` 성공 |
| 2026-08-26 | Sprint 1 Dependency 동기화 | PASS | `uv sync --frozen --group dev`, Lockfile 기준 설치 성공 |
| 2026-08-26 | Sprint 1 Ruff / Format | PASS | 전체 Lint 통과, 138 files already formatted |
| 2026-08-26 | Sprint 1 Pyright strict | PASS | 0 errors, 0 warnings, 0 informations |
| 2026-08-26 | Sprint 1 `make test-all` | PASS | Fast 183 passed·18 deselected, Integration 18 passed·183 deselected |
| 2026-08-26 | Sprint 1 대상별 pytest | PASS | Unit 162, Architecture 4, Contract 14, 기존 E2E 3, HTTP API 15; 서로 중복 포함 |
| 2026-08-26 | Repository Tenant Scope | PASS | 모든 쓰기·조회 메서드 명시적 Tenant, 불일치 SQL 전 거부와 통합 검증 |
| 2026-08-26 | Case Idempotency 동시성 | PASS | PostgreSQL atomic `ON CONFLICT`, 동일 Tenant 중복 Case 1개 유지 |
| 2026-08-26 | 실제 PostgreSQL·MinIO 보상 | PASS | Partial write와 `AVAILABLE` 전환 실패 2건에서 Object 삭제·`FAILED` 확인 |
| 2026-08-26 | MinIO 대상 Integration | PASS | Private Signed/Unsigned 접근과 장애 보상 묶음 3 passed |
| 2026-08-26 | Private MinIO 접근 | PASS | Signed GET 성공, 서명 없는 동일 Object GET은 401/403 |
| 2026-08-26 | Tenant A/B HTTP E2E | PASS | 로그인·권한·Case·Evidence·Signed Download와 타 Tenant `404` |
| 2026-08-26 | Live HTTP Vertical Slice | PASS | 초기 17개 검사와 최종 이미지 재빌드 후 9개 Smoke 통과 |
| 2026-08-26 | Live Multipart 조기 상한 | PASS | Body 전송 전 `413 FILE_TOO_LARGE` 응답 확인 |
| 2026-08-26 | Alembic Upgrade / Head / Drift | PASS | `make migrate`, `20260826_0002 (head)`, 새 Upgrade 작업 없음 |
| 2026-08-26 | Raw Host Alembic | EXPECTED_FAIL | `.env` 미Export 직접 실행은 Fail-closed; 표준 `make migrate`·Compose 명령은 통과 |
| 2026-08-26 | Development Seed 2회 | PASS | 동일 Tenant·사용자·Role을 중복 생성하지 않고 Password Hash 유지 |
| 2026-08-26 | Final Compose Health | PASS | 최종 이미지 재빌드 후 API·Worker·PostgreSQL·RabbitMQ·MinIO 5개 Healthy |
| 2026-08-26 | 검증 데이터 정리 | PASS | Case·Evidence·History·Idempotency Row 0, MinIO Object 0 |
| 2026-08-26 | 독립 최종 감사 | PASS | 재현 가능한 P0·P1·P2 완료 차단 이슈 없음 |
| 2026-08-26 | `git diff --check` | PASS | Whitespace 오류 없음 |
| 2026-08-26 | Markdown 인계 검증 | PASS | 32 files, 로컬 Link 44개 존재, 불균형 Fence 0 |
| 2026-08-26 | Local 인증·Seed 값 누출 검사 | PASS | `.env` 밖에서 설정된 민감값 4개와 일치하는 내용 0 |
| 2026-08-26 | Sprint 1 Closeout 독립 감사 | PASS | P0 0, P1 3/3 수정, P2 4/4 보강, P0/P1 미해결 0 |
| 2026-08-26 | Closeout Ruff / Pyright | PASS | Lint 통과, Pyright 0 errors·0 warnings |
| 2026-08-26 | Closeout Format 후보 범위 | PASS | Sprint 1 Commit 후보 전체; 별도 미추적 Kaputt 문서 제외 |
| 2026-08-26 | Closeout `make test-all` | PASS | Fast 189 passed·18 deselected, Integration 18 passed·189 deselected |
| 2026-08-26 | Closeout 대상별 pytest | PASS | Unit 168, Architecture 4, Contract 14, 기존 E2E 3, HTTP API 15; 중복 포함 |
| 2026-08-26 | Closeout PostgreSQL / MinIO | PASS | PostgreSQL 대상 10, MinIO·보상 대상 3 |
| 2026-08-26 | 격리 Migration 수명주기 | PASS | 빈 DB→Head, Baseline→Head, Head→Baseline→Head, Drift와 복합 Tenant FK |
| 2026-08-26 | Closeout Compose·Seed | PASS | 이미지 Build, 장기 서비스 5개 Healthy, Seed 2회 |
| 2026-08-26 | Closeout Live HTTP | PASS | JWT, Case 201/Replay 200, Evidence, Signed GET, Object HEAD, A/B `404` |
| 2026-08-26 | 누락 Evidence Object | PASS | DB `AVAILABLE`이어도 URL `500 EVIDENCE_UPLOAD_FAILED` |
| 2026-08-26 | Closeout 검증 데이터 정리 | PASS | 업무 테이블 Row 0, MinIO Object 0, 임시 DB 2개 삭제 |
| 2026-08-26 | Closeout Commit 안전성 | PASS | `.env`·Secret·생성물·Kaputt 문서를 Stage하지 않고 로컬 Commit만 생성 |
| 2026-08-26 | Sprint 2 시작 Baseline | PASS | Fast 189 passed·18 deselected, Integration 18 passed·189 deselected |
| 2026-08-26 | Sprint 2 Ruff / Format | PASS | Lint 통과, Python 대상 158 files already formatted |
| 2026-08-26 | Sprint 2 Pyright strict | PASS | 0 errors, 0 warnings, 0 informations |
| 2026-08-26 | Sprint 2 기본 pytest | PASS | 291 passed·36 deselected·0 failed |
| 2026-08-26 | Sprint 2 Core Integration | PASS | 31 passed·5 external skipped·291 deselected·0 failed |
| 2026-08-26 | Sprint 2 Analysis Focus | PASS | Fast 76 passed·251 deselected; Integration 13 passed·5 skipped·309 deselected |
| 2026-08-26 | Sprint 2 Unit / Contract / Architecture | PASS | 227 passed·100 deselected / 45·282 / 4·0 |
| 2026-08-26 | Sprint 2 HTTP / RabbitMQ·Outbox / E2E | PASS | 29·0 / 18 passed·309 deselected / 6·321 |
| 2026-08-26 | Sprint 2 Migration Unit | PASS | 6 passed·0 failed |
| 2026-08-26 | Sprint 2 External vLLM | SKIPPED | 외부 Endpoint 미설정; 5 skipped·322 deselected, 호출 0 |
| 2026-08-26 | Sprint 2 PostgreSQL App E2E | PASS | 8 passed; Retry·Duplicate·Worker Lost·Lease Max·Fencing 포함 |
| 2026-08-26 | Sprint 2 격리 Migration | PASS | Empty→0003, 0003→0002→0003, Empty→0002→0003, Drift 없음 |
| 2026-08-26 | Sprint 2 Docker Build·Migration·Seed | PASS | 최종 이미지 Build, Head 적용, Development Seed 성공 |
| 2026-08-26 | Sprint 2 Live HTTP·Async | PASS | 202, Replay 200, Conflict 409, Tenant 404, Mock `SUCCEEDED` |
| 2026-08-26 | Sprint 2 Live Duplicate | PASS | 같은 Celery Message 재전달 뒤 Attempt 1·Result 1 유지 |
| 2026-08-26 | Sprint 2 Runtime Health | PASS | API·Worker·Dispatcher·PostgreSQL·RabbitMQ·MinIO 6개 Healthy |
| 2026-08-26 | Sprint 2 Queue·검증 데이터 정리 | PASS | Queue 0, Analysis 6개 Table 0, 합성 Case/Tenant 0, MinIO Object 0 |
| 2026-08-26 | Sprint 2 `git diff --check` | PASS | Whitespace 오류 없음 |
| 2026-08-26 | Sprint 2 Git 안전성 | PASS | Closeout 전 Commit·Push 0, 사용자 Kaputt 문서 수정·Stage·삭제 0 |
| 2026-08-26 | Sprint 2 독립 Closeout | PASS | P0 0, P1 0; 정적·291 Fast·31 Integration·세 Migration·Docker·Live 재통과 |
| 2026-08-26 | Sprint 2 Closeout Commit | PASS | `294cb5b`, 승인 범위 로컬 Commit; Push·PR 없음 |
| 2026-08-26 | Qwen Artifact·Runtime | PASS | revision 고정, vLLM 0.26.0 digest, Transformers 5.14.1, CUDA 13.0 |
| 2026-08-26 | Qwen Cold Start | PASS | 첫 Ready 8m06s, cache-hit Ready 97s, 동일 Profile 재현 |
| 2026-08-26 | Qwen Stability | PASS | 26m19s, Restart·OOM·Error 0, Healthy |
| 2026-08-26 | Qwen Quality Prompt 1.0.0 | FAIL | Pydantic 98%; multi-defect 중복 Enum 2건 재현 |
| 2026-08-26 | Qwen Quality Prompt 1.0.1 | PASS | 100건 Schema/Pydantic/Quote 100%, forbidden/injection/reasoning 0 |
| 2026-08-26 | Qwen Classification Baseline | LIMITATION | Issue F1 0.95, Action Accuracy 0.23, Missing F1 0.00 |
| 2026-08-26 | Qwen Spot-check | PASS_WITH_LIMITS | 안전 20/20, Issue 19/20, Action 10/20, Missing 8/20 |
| 2026-08-26 | Qwen Performance A–D | PASS | 30요청 성공, Timeout/OOM/Schema 실패 0; Peak 23,825 MiB |
| 2026-08-26 | 실제 External vLLM | PASS | 5 passed, 322 deselected, Skip 0 |
| 2026-08-26 | 실제 Qwen Backend E2E | PASS | 성공 Run/Result/Attempt 10/10/10, 고정 Metadata Snapshot |
| 2026-08-26 | Qwen Duplicate·Timeout | PASS | 재전달 Result/Attempt 1/1; Timeout Retry 후 Attempt 2 Max 종결 |
| 2026-08-26 | Sprint 2.5 정리·복구 | PASS | 합성 Case/Run 22 삭제, Queue/Orphan 0, Core 6개 Mock Healthy |
| 2026-08-26 | Sprint 2.5 최종 회귀 | PASS | Ruff, Format 162, Pyright 0, Fast 291, Integration 31 |
| 2026-08-26 | Sprint 3 시작 Baseline | PASS | Base `7d63cbb`; Fast 291 passed·36 deselected, Integration 31 passed·5 skipped·291 deselected |
| 2026-08-26 | Sprint 3 LLM 평가 감사 | PASS_WITH_LIMITS | Enum/PRF 수식 일치; Action input/gold 의미 모호, Missing support 진단 추가, 재평가 미실행 |
| 2026-08-26 | Sprint 3 Ruff / Format / Pyright | PASS | Ruff 0, Format 167 files, Pyright 0 errors·0 warnings |
| 2026-08-26 | Sprint 3 Fast Suite | PASS | 328 passed·42 deselected·0 failed |
| 2026-08-26 | Sprint 3 Core Integration | PASS | 36 passed·5 external-vLLM skipped·329 deselected·0 failed |
| 2026-08-26 | Sprint 3 Architecture·Contract·E2E | PASS | 합계 55 passed·0 failed; 기본 외부 호출 0 |
| 2026-08-26 | Sprint 3 PostgreSQL Multimodal E2E | PASS | Success, 양방향 Partial, Both Fail, Timeout Retry, Duplicate, Tenant 격리 5 tests |
| 2026-08-26 | Sprint 3 MinIO bounded read | PASS | 실제 Object read와 max size rejection 1 test |
| 2026-08-26 | Sprint 3 Migration lifecycle | PASS | Empty→0004, 0004→0003→0004, previous→0004, drift 0 |
| 2026-08-26 | Sprint 3 Live HTTP success | PASS | Login→PNG→Text success→2-Stage Multimodal success, Vision Result/Detection 각 1 |
| 2026-08-26 | Sprint 3 Live partial | PASS | 병렬 CAS 결함 수정 후 Text success/Vision permanent failure→`PARTIAL_SUCCESS` |
| 2026-08-26 | Sprint 3 Live no image | PASS | HTTP 422 `IMAGE_EVIDENCE_REQUIRED` |
| 2026-08-26 | Sprint 3 External Vision | SKIPPED | 1 skipped·369 deselected; `SKIPPED_EXTERNAL_VISION_NOT_AVAILABLE` |
| 2026-08-26 | Sprint 3 Docker·Queue | PASS | API/Worker/Dispatcher/PostgreSQL/RabbitMQ/MinIO 6개 Healthy; ready/unacked 0 |
| 2026-08-26 | Sprint 3 정리 | PASS | 합성 Case 5개와 private MinIO Object 4개 제거, 대상 Case 0 |
| 2026-08-26 | Sprint 3 Git 안전성 | PASS | `git diff --check`; Commit·Push·PR 0, Kaputt 파일 미수정·미Stage |
| 2026-08-26 | Sprint 3 Closeout 재감사 | PASS | P0/P1 0, Ruff, Format 165, Pyright 0, Fast 328, Integration 36 |
| 2026-08-26 | Sprint 3 Closeout Migration | PASS | empty→0004, 0004→0003→0004, 0003→0004, 두 DB drift 0 |
| 2026-08-26 | Sprint 3 Closeout Runtime | PASS | Core 6개 Healthy, HTTP ready, analysis queue ready/unacked 0 |
| 2026-08-26 | Sprint 3 Closeout Commit | PASS | `330cbdb feat: complete multimodal vision analysis pipeline`, Push·PR 없음 |
| 2026-08-26 | Sprint 4A LLM v2 Focus | PASS | v2/Corpus Unit 21, Prompt hash와 completeness/action/source quote |
| 2026-08-26 | Sprint 4A Policy Corpus | PASS | Build/validate 24 Document, 168 Clause, Tenant 2, duplicate 0 |
| 2026-08-26 | Sprint 4A Evaluation Data | PASS | 160/120/50/30/10, Gold missing 0, cross-tenant 0 |
| 2026-08-26 | Sprint 4A Migration 첫 시도 | FAIL | 오래된 Docker image가 `0005` 미포함; DB not up to date 감지 |
| 2026-08-26 | Sprint 4A Migration 재실행 | PASS | image rebuild 후 `0004→0005`, Alembic drift 0 |
| 2026-08-26 | Sprint 4A Live v2 Mock | PASS | Run SUCCEEDED, action 2, MULTIPLE_EXTRACTED, rule 1.0.0 |
| 2026-08-26 | Sprint 4A Live 정리 | PASS | 합성 Case/Run 관련 row 제거, RabbitMQ analysis 0/0 |
| 2026-08-26 | Sprint 4A 실제 Qwen | SKIPPED | Endpoint 미사용; `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE` |
| 2026-08-26 | Sprint 4A Stable Build | PASS | Policy·Evaluation aggregate hash가 반복 Build 전후 동일 |
| 2026-08-26 | Sprint 4A Static | PASS | Ruff, Format 179, Pyright 0 errors·warnings |
| 2026-08-26 | Sprint 4A Fast Regression | PASS | 354 passed, 42 deselected, 외부 호출 없음 |
| 2026-08-26 | Sprint 4A 대상별 Test | PASS | Unit 294, Architecture 4, Contract 50, E2E 6; 중복 포함 |
| 2026-08-26 | Sprint 4A Core Integration | PASS | 36 passed, external GPU 5 skipped, 355 deselected |
| 2026-08-26 | Sprint 4A External 기본 Gate | SKIPPED | GPU 5 skipped·391 deselected; Vision 1 skipped·395 deselected |
| 2026-08-26 | Sprint 4A Migration 3경로 | PASS | empty→0005, 0005→0004→0005, 0004→0005, drift 0; 임시 DB 0 |
| 2026-08-26 | Sprint 4A Final Runtime | PASS | 최신 image, Core 6개 Healthy, live/ready 200, analysis 0/0 |
| 2026-08-26 | Sprint 4A Git 인계 | PASS | `git diff --check`, Stage 0, Sprint 4A Commit·Push·PR 0, Kaputt 미추적 보존 |
| 2026-08-26 | Sprint 4A Closeout Commit | PASS | `6f3a667 feat: add LLM contract v2 and policy reference corpus`; Push·PR 없음 |
| 2026-08-26 | Sprint 4B Static | PASS | Ruff, Format 210, Pyright 0 errors/warnings |
| 2026-08-26 | Sprint 4B Fast Regression | PASS | 376 passed, 48 deselected, 31 warnings |
| 2026-08-26 | Sprint 4B 대상별 Test | PASS | Unit 299, Architecture 6, Contract 58, E2E+Policy API 14; 중복 포함 |
| 2026-08-26 | Sprint 4B PostgreSQL Integration | PASS | 전체 41 passed, external GPU 5 skipped, 378 deselected; policy 전용 5 passed |
| 2026-08-26 | Sprint 4B Ingestion/DB | PASS | run `252afd4b-05be-41aa-a961-ac42d91388fa` reuse, 2/24/168/168, active index 2 |
| 2026-08-26 | Sprint 4B Embedding | PASS | Qwen MPS 1024-d, external 1 passed·423 deselected, truncation/NaN/Inf/dimension mismatch 0 |
| 2026-08-26 | Sprint 4B Locked Evaluation | PASS | Dev 80/Test 40, Test 재실행 0, 세 mode result/profile artifact 검증 |
| 2026-08-26 | Sprint 4B Migration | PASS | empty→0006, 0005→0006, 0006→0005→0006, 두 DB drift 0, 임시 DB 삭제 |
| 2026-08-26 | Sprint 4B API Smoke | PASS | 두 tenant×세 mode 6건 200; provider down lexical 200/dense·hybrid 503, ready 200 |
| 2026-08-26 | Sprint 4B Runtime | PASS | 최신 image Core 6/6 Healthy, live/ready 200 |
| 2026-08-26 | Embedding Make lifecycle 첫 점검 | FAIL | 도구 셸 종료가 background descendant를 정리해 다음 호출 health 연결 거부 |
| 2026-08-26 | Embedding 전용 세션 재검증 | PASS | foreground 장기 세션에서 health/model/external embedding 1건 통과 |
| 2026-08-26 | Sprint 4B Closeout Commit | PASS | `4216028 feat: add hybrid policy retrieval baseline`; Push·PR 없음 |
| 2026-08-26 | Sprint 4C-1 Candidate Upper Bound | PASS | Dev K20 recall 0.9375, oracle MRR 1.0/nDCG 0.95164; Test 진단 1회 |
| 2026-08-26 | Qwen3 Reranker Artifact | PASS | `Qwen/Qwen3-Reranker-0.6B` revision `e61197e…5473`, Transformers 5.15.1 |
| 2026-08-26 | Qwen3 Reranker MPS Qualification | PASS_WITH_LIMITS | cold load 3.60s, K20 p50/p95 2.362/2.375s, concurrency limit 1 |
| 2026-08-26 | Sprint 4C-1 Locked Evaluation | NO_MEASURABLE_GAIN | Test Recall@10 0.925→0.925, MRR 0.53833→0.51250, nDCG 0.59841→0.59802 |
| 2026-08-26 | Sprint 4C-1 Correctness | PASS | tenant/version/effective/retired/duplicate/hard-negative/mutation 위반 0, Dev determinism 100% |
| 2026-08-26 | Sprint 4C-1 Static | PASS | Ruff 0, Format 232 files, Pyright 0 errors/warnings |
| 2026-08-26 | Sprint 4C-1 Fast Regression | PASS | 402 passed, 50 deselected, 31 warnings |
| 2026-08-26 | Sprint 4C-1 대상별 Test | PASS | Unit 319, Architecture 8, Contract 69/2 deselected, E2E 6 |
| 2026-08-26 | Sprint 4C-1 Integration | PASS | 42 passed, 5 external skipped, 405 deselected |
| 2026-08-26 | Sprint 4C-1 External Models | PASS | Embedding 1/451 deselected, Reranker 1/451 deselected, 모두 MPS |
| 2026-08-26 | Sprint 4C-1 Migration | PASS | empty/previous/round-trip to `0007`, 모든 경로 drift 0, 임시 DB 정리 |
| 2026-08-26 | Sprint 4C-1 API/Runtime | PASS | 두 tenant reranked, 기존 6 mode, down 503/no fallback, Core ready 200·6 healthy |
| 2026-08-27 | Sprint 4C-1 Closeout P1 | PASS | Format target의 reranker 누락 1건 수정, 전체 infra 234 files 확인 |
| 2026-08-27 | Sprint 4C-1 Closeout Static | PASS | Ruff, Format 234, Pyright 0 |
| 2026-08-27 | Sprint 4C-1 Closeout Regression | PASS | Fast 402/50 deselected, Unit 319, Architecture 8, Contract 69/2, E2E 6 |
| 2026-08-27 | Sprint 4C-1 Closeout Integration | PASS | 42 passed, external GPU 5 skipped, 405 deselected |
| 2026-08-27 | Sprint 4C-1 Closeout External | PASS | Embedding/Reranker 각 1 passed, 451 deselected, MPS |
| 2026-08-27 | Sprint 4C-1 Closeout Evaluation | PASS | Dev 80 재계산 mismatch 0, Test 미호출, candidate mutation 0 |
| 2026-08-27 | Sprint 4C-1 Closeout Migration | PASS | empty/previous/round-trip `0007`, drift 0, 임시 DB 3개 정리 |
| 2026-08-27 | Sprint 4C-1 Closeout API | PASS | base mode 200, reranked down 503, ready 200, Core 6 healthy |
| 2026-08-27 | Sprint 4C-2 Closeout Commit | PASS | `a282817 feat: add case-based policy retrieval query planning`; Push·PR 없음 |
| 2026-08-27 | Sprint 4C-3A Static | PASS | Format 258, Ruff 0, Pyright 0 errors/warnings |
| 2026-08-27 | Sprint 4C-3A Fast Regression | PASS | 431 passed, 3 external skipped, 47 deselected, 31 warnings |
| 2026-08-27 | Sprint 4C-3A Target Tests | PASS | Grounding unit/contract/migration 12 passed |
| 2026-08-27 | Sprint 4C-3A Integration | PASS | 42 passed, 5 external GPU skipped, 434 deselected |
| 2026-08-27 | Sprint 4C-3A Structural Evaluation | PASS | Grounding 50 + Injection 30, 위반 0, replay 100% |
| 2026-08-27 | Sprint 4C-3A Semantic Evaluation | SKIPPED | `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE` |
| 2026-08-27 | Sprint 4C-3A Migration | PASS | empty/previous/round-trip `0009`, drift 0, 임시 DB 3개 정리 |
| 2026-08-27 | Sprint 4C-3A Live Async | PASS | PostgreSQL/RabbitMQ/Celery, 10 citations/statements, replay 200, tenant 404 |
| 2026-08-27 | Sprint 4C-3A Provider Down | PASS | stable unavailable error, result 0, Mock fallback 0 |
| 2026-08-27 | Sprint 4C-3A Runtime Cleanup | PASS | 대상 run 3·result 2·outbox 3·item 10·pack 1 삭제, 대상 run 0 |
| 2026-08-27 | Sprint 4C-3A Compose Contract | PASS | 기본 Worker가 `grounded-explanation` queue를 소비하도록 보완, config render 통과 |
| 2026-08-27 | Sprint 4C-3A Docker Rebuild | BLOCKED | 외부 registry metadata 응답 정지; Dockerfile diff 0, 기존 Core 6 healthy |
| 2026-08-27 | Sprint 4C-3A Docker Rebuild Retry | PASS | 최신 image build, Dockerfile diff 0, Core 6 healthy, live/ready 200 |
| 2026-08-27 | Sprint 4C-3A Docker Queue/E2E | PASS | 4 queues consumer 1·depth 0, 10 citations/statements, replay 200, tenant 404 |
| 2026-08-27 | Sprint 4C-3A Duplicate Delivery | PASS | terminal event 2회 재전달 뒤 run 1·result 1·queue depth 0 |
| 2026-08-27 | Sprint 4C-3A Independent Closeout | PASS | P0 0, P1 0; 전체 Gate 통과; semantic model quality는 SKIPPED 유지 |
| 2026-08-27 | Sprint 5A Static | PASS | Ruff 0, Format 296, Pyright 0 errors/warnings/informations |
| 2026-08-27 | Sprint 5A Default Regression | PASS | 456 passed, 55 deselected, 31 warnings |
| 2026-08-27 | Sprint 5A Target Suites | PASS | Architecture 9, Unit 356, Contract 85/2 skipped, E2E 6, Policy API/core 19 |
| 2026-08-27 | Sprint 5A Integration first run | ENV_CONTENTION | 장기 Dispatcher가 test outbox를 선점해 1 failed, 43 passed, 5 skipped |
| 2026-08-27 | Sprint 5A Integration isolated | PASS | Worker/Dispatcher 일시 정지 후 44 passed, 5 external-GPU skipped, 462 deselected |
| 2026-08-27 | Sprint 5A Migration | PASS | empty/previous/round-trip `0010`, drift 0, 임시 DB 0; live DB head/drift 0 |
| 2026-08-27 | Sprint 5A Rule DB Audit | PASS | active 2, set 2, rule 24, source 24; orphan/mismatch/missing source/final effect 0 |
| 2026-08-27 | Sprint 5A Frozen Evaluation | PASS | Dev80/Test40 모든 metric 1.0; tenant/future/final-decision 위반 0 |
| 2026-08-27 | Sprint 5A Docker Runtime | PASS | 최종 image, Core 6 healthy, live/ready 정상, application queue 5개 consumer 1 |
| 2026-08-27 | Sprint 5A Live Async | PASS | rules 12, replay 200, duplicate NOOP, tenant 404, Mock Vision NOT_EVALUATED |
| 2026-08-27 | Sprint 5A Git Handoff | PASS | Branch 정확, Sprint 5A Commit·Push·PR 없음, Kaputt 미Stage 보존 |
| 2026-08-27 | Sprint 5B Static | PASS | Ruff 0, Format 315, Pyright 0 errors/warnings/informations |
| 2026-08-27 | Sprint 5B Default Regression | PASS | 484 passed, 57 deselected, 31 warnings |
| 2026-08-27 | Sprint 5B Integration | PASS | 46 passed, 5 external-GPU skipped, 490 deselected, 3 warnings |
| 2026-08-27 | Sprint 5B Focus | PASS | Human Review unit/HTTP/runtime 28, architecture 포함 focus 37, repository 2 |
| 2026-08-27 | Sprint 5B Evaluation | PASS | Dev60/Test30 sealed, 9 workflow metrics 1.0, 9 violation counts 0 |
| 2026-08-27 | Sprint 5B Migration | PASS | Empty→0011, 0010→0011, 0011→0010→0011, drift 0, 임시 DB 0 |
| 2026-08-27 | Sprint 5B Docker Runtime | PASS | 최신 image, Core 6 healthy, application queue 6개 consumer 1/depth 0 |
| 2026-08-27 | Sprint 5B Live Async/API | PASS | task/packet/created/claim/resolve/decision/basis 각 1, duplicate 409/NOOP, tenant 404 |
| 2026-08-27 | Sprint 5B Git Handoff | PASS | Branch `feature/sprint-5b-human-review-workflow`, Commit·Push·PR 없음, Kaputt 제외 |
| 2026-08-27 | Sprint 5B Reliability Static | PASS | Ruff 0, Format 324, Pyright 0 |
| 2026-08-27 | Sprint 5B Reliability Regression | PASS | Default 516 passed/59 deselected; Integration 48 passed/5 external-GPU skipped/522 deselected |
| 2026-08-27 | Sprint 5B Reliability Migration | PASS | Empty→0012, 0011→0012, 0012→0011→0012, drift 0, 임시 DB 잔존 0 |
| 2026-08-27 | Sprint 5B Broker Recovery | PASS | RabbitMQ 중단 시 pending/backoff, 재기동 후 CONSUMED; duplicate 두 번 `NOOP`, Result 불변 |
| 2026-08-27 | Sprint 5B Reliability Runtime | PASS | DB head 0012, Core 6 healthy, application queue 6개 consumer 1/depth 0, live smoke PASS |
| 2026-08-27 | Sprint 5B Commit·Remote Backup | PASS | `4aefae6 feat: add human review workflow`; `origin/feature/sprint-5b-human-review-workflow` Push, PR 없음 |
| 2026-08-27 | Sprint 5C Backend Static | PASS | Ruff, Format, Pyright 최종 통과 |
| 2026-08-27 | Sprint 5C Default Regression | PASS | 554 passed, 62 deselected |
| 2026-08-27 | Sprint 5C Integration | PASS | 51 passed, 5 external-GPU skipped, 560 deselected |
| 2026-08-27 | Sprint 5C Frontend Static·Contract | PASS | ESLint, TypeScript, generated OpenAPI check, production build 통과 |
| 2026-08-27 | Sprint 5C Frontend Tests | PASS | Vitest 6, Playwright 5; Playwright는 intercepted API fixture, Scenario 3–5 live causal E2E 아님 |
| 2026-08-27 | Sprint 5C Migration | PASS | PostgreSQL head `0014`, schema drift 0 |
| 2026-08-27 | Sprint 5C Docker Runtime | PASS | 7 services healthy, 8 application queues 각각 consumer 1/depth 0 |
| 2026-08-27 | Sprint 5C Live Resolution | PASS | Decision→Resolution→`DRY_RUN` validated, duplicate `NOOP`, `cases.status` 불변, cross-tenant `404` |
| 2026-08-27 | Sprint 5C Broker Recovery | PASS | 실제 Rabbit outage에서 request `PENDING` attempts 3→복구 뒤 `CONSUMED` attempts 5, final validated |
| 2026-08-27 | Sprint 5C Commit·Remote Backup | PASS | `0a5f529 feat: add case resolution and PoC console`; `origin/feature/sprint-5c-case-resolution-external-action` Push, PR 없음 |
| 2026-08-27 | Sprint 5C Limited PoC Gate | BLOCKED | 구현 Gate는 통과했으나 실제 Data/Policy/Vision·Privacy·Shadow·Qwen 외부 증거 미확보 |
| 2026-08-27 | Current Status HTML | PASS | 단일 HTML 200 응답, 외부 asset 0, 반응형·인쇄/PDF 레이아웃과 내부 데모/PoC Gate 구분 |
| 2026-08-27 | HDP-100 Scenario Dataset | PASS_WITH_SCOPE | fictional product, synthetic Case/Gold 36/36, demo/dev/test 5/21/10; 실제 기업·고객 Data 0 |
| 2026-08-27 | HDP-100 Synthetic Policy | PASS_WITH_SCOPE | version 1.0.0, effective 2026-08-27, 10 clauses, 7 rules; 법률·상업 효력 없음 |
| 2026-08-27 | HDP-100 Offline Acceptance | PASS | 필수 artifact/hash, 36 unique Case/Gold, policy, 5 safety demo, binary model boundary 9/9 |
| 2026-08-27 | E3 Offline Report Metrics | REPORTED_NOT_REPRODUCED | AP 0.884863, AUROC 0.931604, threshold 0.8984375; 담당자 보고 수치이며 CSight 미재현 |
| 2026-08-27 | Binary Vision Contract Live | PASS_WITH_SCOPE | 실제 E3가 아닌 deterministic Mock any-defect score/threshold 계약만 live 연결 |
| 2026-08-27 | Actual E3 Runtime | BLOCKED | `best.pt` checkpoint package, serving endpoint와 endpoint reference 모두 NOT_AVAILABLE |
| 2026-08-27 | Vision Assessment DB | HEAD_APPLIED | 현재 PostgreSQL Head `0015`; `vision_image_assessments` additive schema |
| 2026-08-27 | Parallel Join Focused Regression | PASS_WITH_SCOPE | 실제 PostgreSQL barrier 회귀 1 passed/14 deselected; live causal 재검증 완료를 뜻하지 않음 |
| 2026-08-27 | Parallel Text/Vision Join | PENDING_REVERIFICATION | live race 수정 후 재검증 중; 현재 branch 최종 causal 결과와 수치 미확정 |
| 2026-08-27 | Current Branch Full Regression | PENDING_REVERIFICATION | 기존 Sprint 5C의 554 default/51 integration 수치는 보존; HDP-100 branch 새 수치로 대체하지 않음 |
| 2026-08-27 | HDP-100 Backend Static | PASS | Ruff, Format 365, Pyright 0 errors·0 warnings·0 informations |
| 2026-08-27 | HDP-100 Default Regression | PASS | 585 passed, 65 deselected, 36 non-blocking deprecation warnings |
| 2026-08-27 | HDP-100 Integration | PASS | 54 passed, 5 external-vLLM GPU skipped, 591 deselected; disposable DB 잔존 0 |
| 2026-08-27 | HDP-100 Frontend | PASS | lint·TypeScript·OpenAPI sync·production build, Vitest 9, Playwright fixture scenario 5 |
| 2026-08-27 | HDP-100 Live Binary Vision | PASS_WITH_SCOPE | 새 parallel Run `18451c65-ec11-4beb-a814-a52f695f8505` SUCCEEDED; Result/Assessment/Detection 1/1/0, threshold 0.8984375, Mock score 0.965449 |
| 2026-08-27 | Parallel Join Orphan Recovery | PASS | 기존 orphan Run `e5d01e06-5f93-44b5-959e-1c18da81eb71`의 terminal event redelivery가 NOOP으로 parent를 SUCCEEDED 복구; Result/Assessment/Detection 1/1/0 |
| 2026-08-27 | HDP-100 Runtime Health | PASS | DB Head `0015`, 7 services healthy, 8 application queues consumer 1/depth 0, API·Web HTTP 200 |
| 2026-08-28 | HDP-100 Backend Static Reverification | PASS | Ruff PASS, Format 365 files, Pyright 0 |
| 2026-08-28 | HDP-100 Default Regression Reverification | PASS | 603 passed, 65 deselected |
| 2026-08-28 | HDP-100 Integration Reverification | PASS | 54 passed, 5 external-GPU skipped, 609 deselected; disposable DB 잔존 0 |
| 2026-08-28 | HDP-100 Frontend Reverification | PASS | lint·typecheck·generated OpenAPI sync·production build, Vitest 10, Playwright fixture scenario 5 |
| 2026-08-28 | HDP-100 Scenario Offline Reverification | PASS | acceptance 9/9; pack hash `6be7ad00ba4b92bd99fbcb0ab6c7b9163e387aa8ccd734751c479a2352c24ef1` |
| 2026-08-28 | Actual E3 Runtime Reverification | BLOCKED | endpoint, checkpoint package, endpoint reference 부재; runtime probe 미실행 |
| 2026-08-28 | HDP-100 Live Binary Vision Reverification | PASS | Run `fc249b72-92b4-4160-adee-2c9b0b66b092` SUCCEEDED; Mock score 0.961864, threshold 0.8984375, Detection 0, automatic Decision false |
| 2026-08-28 | HDP-100 Runtime Health Reverification | PASS | DB Head `0015`, 7 services healthy, 8 application queues consumer 1/depth 0 |
| 2026-08-28 | HDP-100 HTTP Surfaces | PASS | API·Web·상태 HTML 각각 HTTP 200 |
| 2026-08-28 | HDP-100 Git Commit·Remote Backup | NOT_RUN | 로컬 변경은 최종 검증됐으나 기능 Commit과 원격 기능 브랜치 Push는 아직 pending |
| 2026-08-28 | HDP-100 Git Commit·Remote Backup | PASS | `dfd6db2ab2052c4ce9a7f922d682c8e574abb05d feat: add hard-plastic scenario PoC`; local·`origin/feature/scenario-poc-hard-plastic` 동일 SHA, PR·`develop` 병합 미실행 |
| 2026-08-28 | HDP-100 Status Closeout·Remote Backup | PASS | `5c152fd0d1e97eba3b41b2ecea1cff7811814d90 docs: close out hard-plastic scenario PoC`; local HEAD·원격 기능 브랜치 일치, PR 없음 |
| 2026-08-28 | E1–E3 Weight Transfer Integrity | PASS | 전달 3개 checkpoint의 SHA256SUMS 재계산 일치; E3 size 264,918,248와 SHA `49e8a64c…1037e`가 canonical manifest와 일치 |
| 2026-08-28 | E3 Safe Offline Load | PASS | unsafe globals 0, `weights_only=True`·CPU mmap, exact root/config/225 float32 tensor/22,056,961 parameter/finite/strict key 검증; runtime model fetch 0 |
| 2026-08-28 | E3 Host Runtime | PASS_WITH_SCOPE | loopback `127.0.0.1:8093`, MPS float32, direct HTTP synthetic score 0.5347466/threshold 0.8984375, Detection 0; 제품 qualification 아님 |
| 2026-08-28 | E3 Core Causal Integration | PASS_WITH_SCOPE | Run `893f8927-7c71-4246-936b-5c752493ffc4` SUCCEEDED; exact model/version/SHA, BELOW_HIGH_CONFIDENCE_THRESHOLD, automatic Decision 0 |
| 2026-08-28 | E3 Failure Boundaries | PASS_WITH_SCOPE | wrong task와 MIME/content mismatch HTTP 422, sparse hash-drift가 `torch.load` 전 차단, symlink 거부, safe stop/setup/restart와 score 재현 통과; 실제 timeout recovery는 미실행 |
| 2026-08-28 | E3 Runtime Backend Regression | PASS | Ruff 0, Format 374, Pyright 0, Default 605 passed/65 deselected, Integration 54 passed/5 external-GPU skipped/611 deselected, disposable DB 0 |
| 2026-08-28 | E3 Runtime Frontend Regression | PASS | lint·typecheck·OpenAPI·build, Vitest 10, Playwright fixture E2E 5 통과 |
| 2026-08-28 | E3 Runtime Live Health | PASS | DB Head `0015`, E3 health 200, Core 7 services healthy, 8 queues consumer 1/depth 0, API·Web·상태 HTML HTTP 200 |
| 2026-08-28 | E3 Status Dashboard Browser QA | PASS | 실제 E3 연결/제품 qualification 차단 문구를 브라우저 DOM에서 확인하고 기존 상태 탭을 갱신 |
| 2026-08-28 | E3 Runtime Git Handoff | NOT_RUN | 현재 변경은 로컬 미Commit·미Push; checkpoint와 사용자 소유 루트 문서 2개는 Git 제외 |
| 2026-08-28 | Local Demo Admin Identity | PASS | tenant `csight`, user `csight@csight.demo`, active `ADMIN` 1계정/1역할; token·me HTTP 200, Argon2 hash 저장 확인 |
| 2026-08-28 | Cloudflare Public Demo Route | PASS_WITH_SCOPE | `doongdoong.org`·`www`의 game 3000/WS 3001 ingress를 CSight Web 8080으로 전환; 외부 system-info·token·me 200와 브라우저 Login DOM 확인, Access 미적용 |
| 2026-08-28 | E3 Top-100 Package Integrity | PASS_WITH_SCOPE | JPEG 100장 SHA/decode/2048²/RGB/EXIF·ICC 0, exact duplicate 0; package tree `4543f49f…cb132`, license·annotation provenance는 미제공 |
| 2026-08-28 | E3 Top-100 Direct Replay | PASS_WITH_SCOPE | 실제 E3 100/100 완료, source 0.5와 frozen 0.8984375 모두 100/100; score 0.9980715~0.9999757, selected-positive라 일반 metric 아님 |
| 2026-08-28 | E3 Top-100 Core Sample | PASS_WITH_SCOPE | 비식별 hard-plastic rank 003/032/054/058/078/080 6건 모두 SUCCEEDED; Evidence SHA·direct/Core score delta 0·Detection 0 |
| 2026-08-28 | E3 Top-100 Post-run Safety Audit | PASS | 6 Case 모두 Human Review Task/Resolution Event/Action Intent 0, Resolution GET 404; raw image Git·public Web 복사 0 |
| 2026-08-28 | E3 Top-100 Replay Report | PASS | local-only report hash `9400509e18689d6696e303a7f30a803cd1252872d21ff123c28b0b50e1d9d2bf` 재계산 일치; 원본·report는 Git 제외 |
| 2026-08-28 | E3 Top-100 Tool Static·Focused | PASS | Ruff 0, Format 376 files, Pyright 0; 새 unit/architecture focus 9 passed, E3 runtime 5 passed |
| 2026-08-28 | E3 Top-100 Default Regression | PASS | 612 passed, 65 deselected, 기존 deprecation warning 36 |
| 2026-08-28 | E3 Top-100 Status HTML | PASS | parse error·duplicate ID·missing anchor·external asset 0, local status·external login HTTP 200; Browser 1324px에서 카드 4·가로 overflow·console warning/error 0, 기존 console-link 세로 배치 수정 |
| 2026-08-28 | E3 Top-100 Integration Suite | NOT_RUN | App/API/Migration 계약 변경 없음; 실제 E3 100건과 Core 6건 causal run으로 이번 변경을 검증, 기존 54 integration 수치는 재사용하지 않음 |
| 2026-08-28 | E3 Normal Reference Audit·Replay | PASS_WITH_SCOPE | 사용자 제공 JPEG 77/77 SHA/decode/2048² RGB·EXIF/ICC 0·Top-100 overlap 0; 실제 E3 77/77이 0.8984375 미만. 사용자 진술 외 Gold·license·provenance는 없음 |
| 2026-08-28 | Realistic Internal Demo 6:4 | PASS_WITH_SCOPE | 결함 selected-correct 6 + 정상 참고 4를 10개 자연어 Case와 private Evidence로 고정; 실제 E3 10/10, 후보 6·기준 미만 4, 정상 성능·실제 분포 평가 아님 |
| 2026-08-28 | Private Evidence Content | PASS | 인증·tenant/Case scope·AVAILABLE·bounded read·size/SHA fail-closed endpoint와 Web Blob preview 구현; 10/10 저장 Object를 frozen source SHA로 재검증 |
| 2026-08-28 | `csight` Synthetic Policy Runtime | PASS | fictional corpus 12 Document/84 Clause/84 Qwen embedding/ACTIVE index 1, Rule/Source 12/12; local-only fail-closed prepare 2회 모두 신규 0·exact reuse |
| 2026-08-28 | Representative Policy→Review Flow | PASS_WITH_SCOPE | 결함 1·기준 미만 1이 Text v2→RAW Top-3→Grounding→Policy `SUCCEEDED`, matching Review 2 `PENDING`; E3는 policy input과 연결하지 않았고 Decision·Resolution·Action 0 |
| 2026-08-28 | Realistic Demo Backend Regression | PASS | Ruff PASS, Format 382, Pyright 0; default 648 passed/65 deselected, Integration 54 passed/5 external-GPU skipped/654 deselected, disposable DB 제거 |
| 2026-08-28 | Realistic Demo Frontend Regression | PASS | lint·typecheck·OpenAPI sync·build, Vitest 32, Playwright fixture scenario 5; 공개 Login DOM·console error 0 |
| 2026-08-28 | Realistic Demo Git Handoff | NOT_RUN | 이번 변경은 로컬 미Commit·미Push·PR 없음; raw image·checkpoint·local reports와 사용자 소유 루트 문서 2개는 Git 제외 |
| 2026-08-28 | R1 Visual-Aligned Seed Replay | PASS | R1 10건 seed/replay, Evidence integrity 10/10, 신규 workflow row 0; report hash `6a7b9af27016ea9a88141878cdbadaca71b2e3ea660f9b47c9d944c4f7002dba` |
| 2026-08-28 | CSight Commerce Policy `2.0.1` | PASS | 신규 8 Document·52 Clause·25 Rule/35 Source; 전체 20/136. prepare 1회 insert 25, 2회째 insert 0·exact reuse, `2.0.1` sole active |
| 2026-08-28 | Faulty Policy `2.0.0` Recovery | PASS | immutable hash 불일치 원인을 source 정렬로 확정; faulty `2.0.0`·failed Run은 삭제 없이 RETIRED 감사 이력, clean ingest는 v1+2.0.1만 생성 |
| 2026-08-28 | R1 Representative Policy→Review | PASS | 수리·Safety·단순변심 3건이 Text v2→RAW Top-3→Grounding→Policy `2.0.1` SUCCEEDED, Review 3 PENDING; Decision·Resolution·Intent·Attempt·Result 0 |
| 2026-08-28 | R1 Backend Final Regression | PASS | Ruff PASS, Format 384, Pyright 0; default 658 passed/65 deselected, Integration 54 passed/5 external-GPU skipped/664 deselected, disposable DB 제거 |
| 2026-08-28 | R1 Frontend Final Regression | PASS | lint·typecheck·OpenAPI sync·build PASS, Vitest 39, Playwright fixture 5; 공개 Login DOM·가로 overflow·console warning/error 0 |
| 2026-08-28 | R1 Runtime Reverification | PASS | 12:48 KST DB Head 0015, E3·Embedding MPS와 Core 7 services healthy, API live/ready·Web health PASS, Core `VISION_PROVIDER=remote` identity 일치 |
| 2026-08-28 | R1 Git Handoff | NOT_RUN | 사용자 지시 없음; 로컬 미Commit·미Push·PR. raw image·checkpoint·local report와 사용자 소유 루트 문서 2개는 Git 제외 |
| 2026-08-28 | Consultant UX·Continue 422 Regression | PASS_WITH_SCOPE | UTC/KST policy-date 원인을 API log·DB rule 효력일로 확정; OpenAPI sync·lint·typecheck·build, Vitest 42, Playwright fixture 5 PASS; 13:22 KST Core 7 healthy·API/Web/외부 tunnel health PASS. rebuild로 memory token이 초기화되어 인증 Case 수동 클릭은 미실행 |
| 2026-08-28 | Human-confirmed Quick Review Regression | PASS | OpenAPI sync·lint·typecheck·build, Vitest 15 files/45 tests, Playwright 5 PASS. Scenario 1이 정확한 CAS Claim v1→Resolve v2, `APPROVE_REPAIR`, rule+citation basis, Report 자동 navigation을 검증; Safety Reviewer 차단/Admin quick review 유지 |
| 2026-08-28 | Quick Review Runtime Surface | PASS | 13:50 KST 재빌드 후 Core 7 services healthy, API ready·Web health·외부 tunnel health PASS; 공개 Login title/DOM, browser console warning/error 0. 실제 인증 Decision 클릭은 데이터 변경 방지를 위해 NOT_RUN |
| 2026-08-28 | Refund Processing Confirmation UI | PASS | Shopify·Stripe·국내 전자상거래법 공식 자료의 공통 운영 필드를 참고해 특정 기업 복제 없이 구현. typecheck·lint·build PASS, Vitest 17 files/49 tests, Playwright fixture 5 PASS, 1440px full-page visual QA PASS |
| 2026-08-28 | Refund Confirmation Runtime Surface | PASS | 14:04 KST Web/API rebuild 후 DB Head `0015`, Core 7 services healthy, API readiness OK, local/public Login HTTP 200; 실제 Human Decision·환불 실행은 NOT_RUN |
| 2026-08-28 | GitHub Branch Stage Audit | PASS | 원격 7 branches. PoC `5c152fd`는 main/develop보다 21 commits, Sprint 5C보다 2 commits ahead이고 latest CI success. Vision `3e2d596`은 PoC와 55/21 diverged, latest CI success·Draft PR #4. PR #2 open, PoC PR·release tag 없음 |
| 2026-08-28 | Natural UI·Communication·Data Assets | PASS_WITH_SCOPE | 자연어 decision/status UI, terminal Report 기반 EMAIL simulation v1.1, tenant append-only allowlist asset. 기본 672 PASS, 격리 Migration 2 PASS, Web 57 PASS, Head 0016, live side effects 0 |
| 2026-08-28 | Runtime Memory Ready Baseline | PASS | 16:28 KST 단일 시점: CSight 귀속 약 4.21 GiB/32 GiB(13.16%), Vision 1,570 MiB, Embedding 1,732.5 MiB, Docker Core 961.95 MiB, tunnel 48.42 MiB. memory-pressure 여유 80%, swap-in/out 0; Case batch/동시 부하는 미실행 |
| 2026-08-28 | Kaputt Local Source Audit | PASS | 4090 Node `/home/data/datasets/kaputt` 406 GiB, extracted 101 GiB. Query image train 85,326·validation 4,874·test 10,067로 Parquet 행과 일치; `plastic_hard` 10,095, defect 1,323·negative 8,772 |
| 2026-08-28 | Qwen3.8 VLM Offline Sample | PASS | 별도 native VLM endpoint가 RTX 4090에서 healthy, prompt 1.2.0 균형 표본 4/4 schema success·요청 9.3–10.8초·민감 패턴 0. 사람 점검 상품 유형 유용성 1/4, defect positive 두 건 모두 `UNCERTAIN`; 전체 Batch 미실행 |
| 2026-08-28 | Qwen3.8 VLM Resource Recovery | PASS | 결과 SHA-256 `390f7d32a1b9a689d4071c59d2e8c0493851c7ea5ea3659f9af7ab58913b0d57`; append-only sample을 private derived 경로에 보존하고 전용 Container exit 0, GPU 22,365→95 MiB |
| 2026-08-28 | Qwen Query+Reference+Prompt Contract | PASS | 동일 `item_identifier`의 Query/Reference Crop 4쌍 선택 추출, vLLM image 2개 제한과 schema 2.0.0 적용. prompt 2.0.1 4/4 구조 성공·민감 패턴 0·결과 SHA `159f5ded7eb9559d5b322ca9d24d48cfc117ed4c94a922f89c7145cb8bac3811` |
| 2026-08-28 | Qwen Paired Label Quality Gate | FAIL | 사람 점검 상품 유형 유용성 1/4, 공식 defect-positive 탐지 0/2. 10,095건 전체 Batch를 중단하고 Qwen을 결함 Label/E3 대체 경로에서 제외 |
| 2026-08-28 | Qwen3.8 VLM Runtime Restart | PASS | 18:42 KST 전용 Container healthy, 인증 model API 200·exact served identity 확인. RTX 4090 21,511/24,564 MiB, utilization 0%, 39°C; Tailscale private `:18001` |
| 2026-08-28 | Kaputt Paired 30 Crop Preparation | PASS | deterministic defect 15/negative 15; Query Crop 30·same-item Reference Crop unique 28 준비. 31.6/41.6 GiB archive에서 missing 26/24만 선택 추출 |
| 2026-08-28 | Qwen Paired Defect 30 | FAIL | 30/30 schema success지만 UNCERTAIN 26, TP/FP/TN/FN 0/2/0/2, coverage 13.3%. 공식 Label/E3 대체 불가, 결과 SHA `e53a516b8ffb5400def2f490f3376716e18d89e2029670e6782a14f408deb2a6` |
| 2026-08-28 | Qwen Product Metadata 30 | PASS | 결함 필드 없는 별도 schema 30/30 success, specific name 25·uncertain 5, 금지 필드·민감 패턴 0, p50 8.5초·p95 10.0초, SHA `7ddc9197c957f9e81b5560476a789f06d555e346ff8dc0df734c076abfef846a` |
| 2026-08-28 | Qwen Product Taxonomy Gate | FAIL | Contact Sheet에서 supplement/cleaning-chemical/pet category 공백과 mismatch 확인. Human Gold 없이 25/30 specificity를 accuracy로 해석하거나 Catalog에 자동 반영하지 않음 |
| 2026-08-28 | PoC Closed-set Registry v1 | PASS_WITH_SCOPE | 상품군 4·결함군 3, 사람 승인 SHA Allowlist 10건. 실제 source identity/label 10/10 PASS, E3 채택 margin defect>=0.95/reference<=0.10. 현재 상품군 2/4·결함군 3/3 표현, 성능평가 아님 |
| 2026-08-28 | PoC Closed-set Registry v2 Expansion | PASS_WITH_SCOPE | 새 SHA Allowlist 10건을 실제 source와 대조하고 E3 채택 10/10. v1+v2 최신 팩은 20건(12:8), 상품군 4/4·결함군 3/3 표현. v3 seed/replay와 workflow boundary 0 통과, 클래스별 정확도 평가는 아님 |
| 2026-09-01 | Qwen3.8-27B GGUF source·toolchain·corpus attestation | PASS | exact BF16 53,808,281,952 bytes·`5a3eed…fa97e`, llama.cpp `aee56b3…ef28`, tool image `d486bf…afb2`, quantizer `05290c…f818`, attested corpus canonical `b39414…e90d`; 공개 fixture sidecar와 offline replay 일치 |
| 2026-09-01 | Protected final GGUF quantization and restoration | PASS | offline/no-GPU Docker 4 commands, control `REUSED_VERIFIED`와 세 후보 `EXECUTED`, 종료 후 후보·입력 재해시 PASS. evidence SHA `324772…1378`; 00:38 KST 기존 VLM healthy/restart 0/OOM false와 Counsel container identity 12/12 복구 |
| 2026-09-01 | GGUF release qualification | BLOCKED | mixed Q4/Q6 `6fb2b9…a0d9`·19,294,014,080 bytes와 Q5 `817bae…c075`·18,679,614,080 bytes를 matrix에 고정했지만 artifact revision·조직 미러·clean imatrix·provider-neutral Extraction evaluator·Dev/Test/Shadow100/workflow20이 없음; `NO_RELEASE_ELIGIBLE` |
| 2026-09-01 | GGUF implementation regression | PASS | 전체 Ruff, 제품 코드 format 605, Pyright 0, 기본 pytest 1171 PASS/94 SKIPPED, GGUF 집중 134 PASS, shell syntax와 diff check PASS. 사용자 소유 문서는 수정하지 않음 |
| 2026-09-02 | GX10 read-only inventory | PASS | ASUS GX10·aarch64·GB10 CC 12.1·memory 130,663,038,976 bytes·NVMe 4,096,805,658,624 bytes·Ubuntu 24.04.4·driver/CUDA 580.173.02/13.0·Docker 29.2.1 arm64·NVIDIA CDI 확인. 10GbE link/throughput·GPU container canary는 NOT_RUN, 원격 write/install/transfer/service change 0 |
| 2026-09-02 | GX10 execution plan | PASS | exact Q5/imatrix source·destination·bytes·SHA-256, owner-only partial→verify→atomic rename, control inputs, ARM64 build identity, scoped rollback과 mutation confirmation gate를 compact JSON으로 고정. install/transfer/build/canary/PRIMARY는 NOT_RUN |
| 2026-09-02 | GX10 runner implementation | PASS | 별도 arm64/sm_121 build·Compose·7-phase compact runner, local/remote mutation gate, append-only evidence와 failed-serve scoped cleanup 구현. focused 9 PASS와 실제 status changes=0 PASS |
| 2026-09-02 | GX10 prepare/control transfer | PASS | owner-only layout 생성 후 reviewed 5 files/22,198 bytes를 fresh staging에 전송, local/remote bytes·SHA 검증 뒤 빈 final path로 이동. 기존 overwrite, model/image/container/4090 change 0 |
| 2026-09-02 | GX10 Q5 transfer | BLOCKED | direct SSH auth 2종 BLOCKED, Taildrop inbox isolation unavailable. source/destination preflight는 PASS지만 다른 대기 파일 보호를 위해 18.68GB 전송·partial 생성 0 |
| 2026-09-02 | GX10 Q5 one-shot direct transfer | PASS | source-IP/token 제한 one-shot Tailnet server로 18,679,614,080 bytes를 Khrin→GX10 direct 전송. HTTP 200, source/partial/final SHA 일치, atomic final mode 0600; server 자동 종료와 4090 VLM/Counsel 보존 확인 |
| 2026-09-02 | GX10 ARM64 image build and GB10 CDI canary | PASS_WITH_SCOPE | pinned b10419 clean source로 image `b664e8…9ac4` arm64/6,732,715,596 bytes build. 첫 ARM SME compiler 실패의 process tree와 실패 image residue 0을 확인한 뒤 GX10 전용 CPU variant를 수정해 PASS; no-network/read-only GPU canary가 GB10을 확인하고 container residue 0 |
| 2026-09-02 | GX10 isolated Q5 serve, smoke, report, stop | PASS_WITH_SCOPE | exact Q5/image/owner gate와 owner-only runtime env로 private candidate serve. reasoning CLI contract 실패는 scoped cleanup 뒤 `off`로 수정. synthetic canary p95/TTFT 695.668/695.560ms, 단일 smoke 579.507/579.411ms, report `bc45d3…cef3`; stop 뒤 container/network 0. Dev·context·decode·peak memory NOT_RUN, PRIMARY 0 |
| 2026-09-02 | GX10 Q5 context and concurrency benchmark | PASS | 4K c1/c2/c4, 16K c1, 32K c1에서 warmup 후 strict synthetic 24/24 성공, timeout/schema failure 0. 4K c1 TTFT/latency p95 193.291/3,159.736ms·decode 11.486934 tok/s; 32K input 32,173 tokens PASS. c2/c4 p95 9.92/23.03초. same-harness 4090·GX10 three-task Dev NOT_RUN, candidate stopped, PRIMARY 0 |
| 2026-09-02 | GX10 three-task Dev identity preflight | BLOCKED | 4090 driver의 amd64/CUDA12.8 post-start identity를 GX10 ARM64/CUDA13에 재사용할 수 없다. 직접 evaluator 우회는 runtime evidence 오귀속이라 거부. service/key/route 변경 0, additive GX10 runtime identity 계약 필요 |
| 2026-09-02 | GX10 operational latency reinterpretation | PASS | 사용자 요구는 문서당 300초 미만. 관측 최악 p95 23.028초는 7.68%라 latency blocker 아님. c2/c4 tail은 최적화 항목. 실제 documents/day·queue·representative workflow capacity는 NOT_RUN, quality/runtime identity blocker 유지 |
| 2026-09-02 | GX10 quality-first priority | PASS | 세 task semantic quality와 safety/uncertainty를 capacity·latency보다 우선. weighted average 없이 Extraction/Query/Grounding all-pass와 final identity joint Dev 요구. Query Builder FAIL·GX10 identity BLOCKED라 NO_WINNER/PRIMARY 금지 유지 |

## 8. 미해결 사항과 사용자 결정

- 2026-10-18 논문 초안: 사용자 저자/소속/학생이메일/지도교수(교신저자) 확인 완료.
  학생 양식의 DOCX/PDF 2쪽 및 최종 그림/표 완료. 현재 환경은 한글 뷰어만 있어 HWP 저장 불가,
  직접생성 HWP 후보는 열람 실패. 한글 편집기에서 공식 서식 확인·HWP 저장 후 제출해야 한다.
  공동저자 검토·교신 이메일·지원 문구 확인·접수는 별도. 상담원 시간/판단 품질·기업 ROI 미측정,
  기존 모델 출시 판정과 고객 pilot 차단을 변경하지 않는다.

- 신규 장비 `gx10-ade1`은 2026-09-02 00:07 KST 공개키-only SSH로 읽기 전용 inventory를 완료했다.
  실제 제품은 ASUSTeK GX10/product version `5.36_GX10DGX`, ARM64·GB10 CC 12.1·20 logical CPU·
  memory 130,663,038,976 bytes·4TB NVMe, Ubuntu 24.04.4/kernel 6.17 NVIDIA, driver/CUDA
  580.173.02/13.0, Docker 29.2.1 arm64와 NVIDIA CDI다. 정확한 판매 SKU는 관측 불가다. 10GbE NIC는
  10G를 지원하지만 link down이라 negotiated speed/throughput은 `NOT_RUN`; 실제 GPU container canary도
  `NOT_RUN`이다. 4090의 x86_64/CUDA 12.8 llama.cpp 자격은 승계하지 않으며 install, upgrade, reboot,
  prune, 모델 전송은 ARM64 계획과 rollback 검토 뒤다.
- 00:12 KST 실행 계획은 Q5 원본 `18,679,614,080` bytes/`d709a4…2219`, clean imatrix
  `13,663,264` bytes/`8d1de2…d40f`를 Khrin에서 다시 읽어 exact content-addressed GX10 경로와
  owner-only partial→hash verify→atomic rename, 실패 시 해당 run 고유 partial만 제거하는 rollback으로
  고정했다. control input은 현재 5개/22,449 bytes의 경로·SHA를 고정했지만 실제 runner 구현 뒤 다시
  hash gate를 통과해야 한다. 원격 파일 생성·전송·image build·container canary는 사용자 확인 전
  `NOT_RUN`이다.
- 00:30 KST GX10 runner/control bundle은 PASS했지만 Q5 direct transport가 새 Gate다. Khrin에서 GX10으로
  표준 공개키 SSH와 Tailscale SSH가 모두 거부됐고, 양쪽 Taildrop CLI는 지원되지만 GX10의 `file get`은
  대기 inbox 전체를 이동하며 사전 목록/단일 파일 선택 기능이 없다. 다른 대기 파일을 건드리지 않기 위해
  전송을 시작하지 않았다. 다음 결정은 (a) 전송 후 제거할 dedicated temporary Khrin→GX10 public key,
  또는 (b) Khrin Tailscale 주소에만 bind하고 GX10 source IP·일회성 token으로 제한한 one-shot Q5 HTTP
  server 중 하나다. 어느 경우도 기존 VLM/Counsel 중지나 PRIMARY를 포함하지 않는다.
- 사용자가 one-shot 방식을 승인해 00:57 KST Q5 direct transfer를 완료했다. 첫 실행 명령은 destructive
  cleanup 안전 정책으로 시작 전 거부돼 remote change 0이었다. 다음 기술 시도는 SSH가 공백 포함 curl
  인자를 재분리해 binary stdout으로 잘못 전달되어 즉시 중단했으며 partial/final 0, server process 0을
  확인했다. 전용 remote receiver로 수정한 fresh run은 HTTP 200, 18,679,614,080 bytes, 597.393초,
  source/partial/final SHA `d709a4…2219` 일치로 PASS했다. 실패 시도의 빈 incoming directory 하나는
  자동 삭제하지 않고 남겼다.
- 01:27 KST pinned llama.cpp ARM64 build와 동일 Q5의 격리 lifecycle을 닫았다. 첫 build는 GCC의 ARM
  SME 미지원으로 실패해 해당 build process tree만 종료했고, GX10 전용 `GGML_CPU_ALL_VARIANTS=OFF`로
  image `b664e8…9ac4`를 만들었다. GB10 CDI canary와 Q5 serve/canary/단일 평가 smoke/report/stop은
  PASS했고 후보 container/network는 0이다. 단, 현재 수치는 합성 요청 각 1건뿐이며 decode tok/s,
  peak unified memory, 4K/16K/32K와 4090 동일 세 task Dev 비교는 `NOT_RUN`이다. 이 Gate 전 GX10
  PRIMARY·route·freeze·sealed Test는 계속 금지한다.
- 01:55 KST 합성 hardware benchmark를 4K concurrency 1/2/4와 16K·32K concurrency 1의 두 축으로
  실행했다. full cross-product는 `NOT_RUN`이다. 전체 24/24 strict JSON 성공, timeout/schema failure 0,
  32K actual input 32,173 tokens를 처리했다. 4K c1 decode는 11.486934 tok/s지만 c2/c4 tail latency가
  9.92/23.03초로 증가했다. GB10의 `nvidia-smi memory.used`가 N/A여서 unified memory는 출처를
  `PROC_MEMINFO_SYSTEM_USED`로 명시한 절대 host-used 표본이며 모델 전용 allocation으로 해석하지 않는다.
  4090 동일 harness는 기존 VLM/Counsel을 중단하지 않기 위해 `NOT_RUN`, 역사적 task Dev와 workload가
  달라 직접 수치 순위는 금지한다. GX10 역할은 Model Lab/SHADOW 후보이며 PRIMARY는 차단한다.
- 01:58 KST 세 task Dev 실행 전 기존 driver를 검사했다. 이 driver는 candidate matrix의 4090
  amd64/CUDA12.8 image·binary·SBOM과 4090 전용 post-start evidence를 강제한다. GX10 endpoint를 직접
  주입하면 ARM64/CUDA13 실행을 4090 identity로 오귀속하므로 `GX10_DEV_RUNTIME_IDENTITY_CONTRACT_MISSING`
  으로 `BLOCKED`했다. API key를 Mac으로 복사하거나 GX10/4090 서비스를 다시 시작하지 않았다. 다음
  구현은 v2 matrix를 재해석하지 않는 additive GX10 runtime identity와 Dev driver 계약이다.
- 02:07 KST 사용자가 문서당 5분 미만이면 충분하고 실제 병목은 일일 문의량과 사람 처리 한계라고
  운영 요구를 명확히 했다. 관측 최악 p95 23.028초는 300초 한도의 7.68%, headroom 276.972초이므로
  latency Gate는 PASS로 재해석한다. c2/c4 tail 증가는 운영 차단이 아니라 비용·효율 최적화 항목이다.
  현재 합성 output이 짧아 documents/day나 실제 end-to-end 문서 처리량은 `NOT_RUN`; 일일 문의량,
  peak-hour 도착률, reviewer 수·인당 처리량을 받은 뒤 queue headroom과 실패율을 평가한다.
- 02:12 KST 사용자는 LLM engine의 역할이 크므로 품질이 최우선이라고 명확히 했다. 이에 Gate 순서를
  three-task semantic quality, safety/uncertainty, capacity/reliability, latency 순으로 고정한다. Extraction,
  Query Builder, Grounding 중 하나라도 실패하면 weighted average나 빠른 응답으로 상쇄하지 않는다.
  기존 frozen 4090 matrix는 수정하지 않았고, GX10 final runtime identity로 fresh joint Dev를 통과하기
  전 Test·freeze·PRIMARY는 계속 금지한다.
- 20:01 KST 사용자 설치 `RadixArk/Qwen3.8-27B-NVFP4`가 별도 `vllm_node`에서 실제 실행 중임을
  확인했다. text와 synthetic VLM data path는 통과했지만 모델의 단일 정책 답변은 사람 검토 필요를
  false로 냈다. 따라서 이 endpoint는 현재 연결 가능한 multimodal SHADOW 후보일 뿐이며 CSight 안전
  경계·세 task 품질·실제 이미지 품질을 통과한 PRIMARY가 아니다. runtime identity 계약에는 현재
  vLLM/image/model/context 정보를 additive하게 고정하고 기존 4090 matrix를 재해석하지 않아야 한다.
- 2026-09-01 현재 상품화 P0와 clean RC candidate는 전체 기본·PostgreSQL·Web·정적 회귀를 통과했지만
  실제 pilot admission은 통과하지 않았다. 승인된 Ollama·불필요 cache 정리 후 Mac 가용 공간은
  38 GiB이며 clean build 관문은 닫혔다. `infra/pilot/.env.pilot`과 fresh 고객 운영 증거가 없어
  pilot start는 실행하지 않았고 현재 데모·RC volume은 보존했다.
- 온보딩 준비도는 6개 구성 gate, 새 pilot readiness는 여기에 25개 운영 자격 gate를 합산한다.
  고객별 signed-intake service actor/public key, 명시적 retention과 자동화, 고객 IdP group mapping,
  활성 policy index/rule set, 세 task PRIMARY route와 fresh 운영 증거를 실제 환경에 provision해야 한다.
- text extraction v2, LLM query builder, grounded explanation의 immutable plan snapshot과 historical
  activation/runtime identity guard, Query Build/Search의 독립 durable v2 event·worker 경계까지
  구현됐다. RAW·DETERMINISTIC은 route/provider 호출 0, LLM Query Build만 model lane 동시성 1,
  Search는 retrieval lane 동시성 2로 분리된다.
- CSight-owned Qwen3.8-27B GGUF 4종의 exact bytes·digest는 확보했지만 release eligible 모델은
  여전히 0개다. mixed Q4/Q6와 Q5의 `artifact_revision`·qualification은 null이며 개인 저장소는
  조직 소유 mirror가 아니다. 수선 이력이 있는 imatrix의 clean rerun, 현재 Dockerfile의 새 image·
  manifest parity, provider-neutral Extraction evaluator와 Dev/Test/Shadow/workflow evidence 전에는
  로컬 R&D 후보로만 유지하고 PRIMARY 자동 전환·fallback을 하지 않는다.
- 현재 Core DB는 head 0034이고 9개 서비스 readiness는 정상이나 코드의 migration head는 0036이다.
  실행 중 API/Web/Worker image와 DB는 시연본 보존을 위해 이번 작업트리로 재빌드·마이그레이션하지
  않았다. 구형 API image 내부의 Alembic package에는 DB가 가리키는 0034 revision 파일이 없어
  `alembic current`는 실패하지만 DB 원장 직접 조회는 0034이고 API dependency readiness는 정상이다.
  이 image에서 migration/restore 명령을 실행하지 않는다. clean `cd6471cd628e` RC image와 별도 0036
  candidate 검증은 완료했다. 별도 pilot은 실제 고객 env, 암호화 immutable off-host 복원 2회와
  남은 load/IdP gate가 갖춰진 뒤 시작한다.
- 운영 failure replay/cancel API 계약은 존재하지만 안전한 전체 pipeline cancellation/replay
  자격이 끝나지 않아 composition에서 503으로 비활성이다. 실패 원장을 덮어쓰는 임시 재처리는
  허용하지 않는다.
- HDP-100은 가상 브랜드의 fictional product이고 36 Case/Gold, 10 clause/7 rule, 5 demo가 모두
  합성이다. Offline acceptance 9/9는 artifact와 안전 계약의 완전성을 뜻하며 실제 고객/상품
  성능이나 실제 기업 정책 타당성을 뜻하지 않는다.
- E3 AP 0.884863, AUROC 0.931604, threshold 0.8984375는 담당자가 제공한 offline 보고서 수치다.
  CSight가 전달 checkpoint로 개별 forward와 threshold 적용은 실행했지만 held-out dataset metric을
  재계산하지 않았으므로 `SUPPLIED_OFFLINE_REPORT_WITH_LIMITATIONS`는 유지한다.
- E3 score가 0.8984375 이상이면 고신뢰 `defect candidate`일 뿐 결함 유형·위치·최종 결정을
  뜻하지 않는다. 미만은 `정상`이나 결함 없음이 아니라 고신뢰 후보 기준 미만이다.
- 현재 live 연결은 exact SHA가 고정된 E3 checkpoint를 host-native loopback endpoint로 띄우고
  Docker Worker가 호출하는 경로까지 통과했다. 합성 이미지 score 0.5347466은 threshold 미만이라
  정상 판정 없이 사람 검토로 수렴했다. 이는 제품별 정확도나 domain-shift qualification이 아니다.
- 전달 Top-100은 무결성 검사와 실제 E3 100/100 재실행, hard-plastic Core 6/6을 통과했다. 그러나
  E3가 이미 맞힌 defect 100/normal 0만 역선택한 자료라 accuracy·recall·specificity·FPR·calibration을
  산출하지 않는다. hard-plastic 14장도 모두 major defect이고 HDP-100 다섯 Human Gold를 대체하지 않는다.
- 사용자 제공 정상 참고 폴더 77장은 실제 E3에서 모두 frozen threshold 미만이었고 그중 4장을
  현실형 내부 데모에 섞었다. 그러나 정상 label의 근거는 사용자 진술뿐이고 무작위 표본·독립 Gold·
  license·원소유자·dataset revision이 없으므로 specificity/FPR 또는 `정상 확인` 근거가 아니다.
- 현실형 최신 20건의 12:8은 화면 시연을 위해 의도적으로 고른 비율이다. 결함 12장은 selected-correct
  positive, 저점수 참고 8장은 낮은 score의 pixel-reviewed allowlist이므로 실제 발생률·정확도·비교
  성능으로 해석하지 않는다. raw image는 private Evidence에만 저장하고 Git·공개 Web static에 복사하지 않는다.
- `poc_closed_set/2.0.0` 확장으로 네 상품군을 모두 화면에 표현하지만 표본 수가 작고 선별 편향이
  있으므로 상품군별 정확도·대표성 검증이 아니다. 세 결함군은 원천 multi-label로 나타나며 E3 결함 유형 예측 증거가 아니다.
  E3 `0.95/0.10`은 선별 여유폭이고 운영 threshold `0.8984375`를 변경하지 않는다.
- 가상 상품명·SKU·가격대 20건은 사진의 일반 외관과 기존 문의를 연결한 표시 전용 합성 카탈로그다.
  실제 상품 식별·시장조사·판매가·환불 금액이 아니며 LLM·Policy·Resolution·External Action 입력으로
  사용하지 않는다. 카탈로그에 없는 Case는 상품을 추정하지 않고 기존 `product_ref`만 표시한다.
- 새 10장은 사진별 제품군 육안 매칭, 개인 이름이 보이는 rank 61과 모호한 rank 56 제외,
  SHA/권리 경계와 E3 결과 고정을 거쳐 active catalog에 추가했다. 추가 확장은 같은 승인 절차를 반복한다.
- 실제 E3 결과는 `attributes.realistic_demo.policy_input_linkage=NOT_LINKED_TO_POLICY_INPUT`으로
  고정했다. 대표 3건의 Text/검색/Grounding/Policy/Human Review는 실제 비동기 경로를 통과했지만
  정책 판단이 Vision score를 사용했다는 뜻이 아니며, Review Packet이 최종 근거 snapshot이다.
- UI는 Retrieval↔Grounding의 직접 연결만 표시하고 Policy는 Text analysis 연결만 확정한다.
  다중 실행이 있을 때 Grounding↔Policy exact chain을 추정하지 않으며, 최신 실패 실행이 이전 성공
  결과를 가리지 않도록 실패 단계만 새 idempotency key로 재시도한다.
- Top-100 package에는 license, 원소유자, dataset revision, annotation provenance와 공개 재배포
  권리가 없다. 상품 label·barcode가 보이고 rank 061에는 개인 이름이 있어 Core 표본에서 제외했다.
  원본은 Git·Docker context·공개 Web에 복사하지 않고 내부 비상업 연결 재현에만 사용한다.
- parallel Text/Vision terminal join race는 parent Run row lock과 terminal redelivery
  reconciliation으로 수정했다. PostgreSQL 동시성 회귀와 새 live Run이 통과했고, 실제로
  고립됐던 기존 Run도 동일 event 재전달의 `NOOP` 경로에서 `SUCCEEDED`로 복구됐다.
- 실제 기업 Data와 실제 기업 Policy 반입은 오늘 HDP-100 합성 시나리오 범위에서 의도적으로
  제외했다. 따라서 실제 고객·정책·Privacy·Shadow 근거를 확보했다는 주장으로 승격하지 않는다.
- Sprint 5C 구현과 내부 데모 Gate는 통과했고 현재 판정은
  `SYNTHETIC_REAL_E3_TECH_DEMO`다. 실제 기업 정책·Case·사용자 Query 분포와 ROI를 검증하지
  않았으며 Local LLM은 `LOCAL_POC`, Vision은 `E3_RUNTIME_CONNECTED_NOT_PRODUCT_QUALIFIED`다.
- Kaputt 기반 E3는 교육·과학적 CV 연구 범위의 비상업 합성 기술 데모로만 사용한다. 사용자
  지시에 따라 Web 콘솔은 현재 `doongdoong.org` 공개 터널에 연결됐지만 E3 endpoint 자체는
  loopback에 남아 있다. 실제 데이터 업로드, 고객·상업 파일럿과 성능 홍보는 권리·법률 승인 전 차단한다.
- 공식 Kaputt Query 이미지는 이미 전량 추출돼 있고 Reference image/crop/mask는 압축 archive에
  있다. 동일 `item_identifier`의 Query/Reference Crop 4쌍을 선택 추출해 사진 2장+비교 Prompt로
  재검증했지만 상품 유형 유용성 1/4, 공식 defect-positive 탐지 0/2였다. 공식 defect label/E3를
  대체하거나 10,095건 전체를 자동 라벨링하지 않으며, Qwen derived label은 선택적 후보 데이터로만
  취급한다.
- 후속 paired 30건에서도 generic VLM 결함 task는 coverage 13.3%, TP 0이어서 품질 실패가
  확정됐다. 분리한 상품 메타데이터 task는 특정 generic name을 25/30 제안했지만 이는 specificity이지
  정확도가 아니다. 현재 category enum에 supplement, cleaning/chemical, pet-care가 없어 이름과
  category가 어긋나는 사례가 있으며, Human Gold 검수 전 자동 catalog/시나리오 반영을 금지한다.
- Limited PoC 승격에는 고객/상품/결함 범위, 비식별 실제 Case 30건 이상과 Human Gold,
  버전·효력일이 있는 실제 정책, 개인정보 Retention·삭제·EXIF·접근 승인, 실제 Vision qualification
  또는 명시적 제외, 실제 Qwen Extraction·Grounding 재평가와 Shadow 비교가 모두 필요하다.
- 실제 `LIVE` 외부 실행, 환불·교환·재배송·수리·결제·CRM·고객 알림, Case Closure, Decision
  amendment, Review 단계 입력 보완과 자동 SLA 배정은 구현하지 않았다. OIDC/RLS와 관리자 수동
  배정은 구현됐지만 실제 고객 IdP·별도 runtime login으로 묶은 운영 qualification은 남아 있다.
- 고객 안내 메일은 발송 결과가 아니라 `SIMULATED_NOT_SENT` 상태의 화면·감사 기록이다. 실제 SMTP,
  수신자 전송, 배송 성공률은 구현·검증하지 않았고 UI도 `실제 미발송`으로 고정한다.
- 데이터 자산은 고객 문의 원문·이름·전화·주소·담당자 rationale을 제외한 allowlist다. 현재 `csight`
  표본은 6건으로 기준선 최소 30건보다 적어 드리프트 수치를 표시하지 않는다. 30건은 기준선 준비,
  60건은 비교 구간 준비 Gate일 뿐 실제 성능 보장을 뜻하지 않는다.
- `csight` Admin은 사용자가 지정한 짧은 데모 Credential을 사용하며 Cloudflare Access는 없다.
  Web이 공개 터널에 연결된 현재 상태는 임시 합성 시연에만 사용하고, 외부 공유 전에는 Access를
  적용하거나 Credential을 강화해야 한다. 원장과 Git에는 비밀번호를 기록하지 않는다.
- 5개 Playwright demo는 intercepted API fixture를 사용한다. Scenario 1은 별도 live backend causal
  경로가 있고 Scenario 2는 PostgreSQL integration 경로가 있지만, Scenario 3–5는
  fixture-driven UI/component-backed이며 다섯 건 모두를 live causal E2E로 해석하면 안 된다.
- 현재 R1 10건 중 대표 3건은 Human Review `PENDING`까지만 준비했다. 사람 계정으로 Resolve하기
  전에는 Decision·Review Report·Resolution·DRY-RUN을 만들지 않으며, 이번 세션에서도 생성 수는 0이다.
- canonical Rule Set `2.0.1`은 DB 재구성 순서와 동일한 rule/source 정렬을 강제한다. 기존 faulty
  `2.0.0`과 그 실패 Evaluation/Outbox는 삭제하지 않고 RETIRED 감사 이력으로 남겼다.
- 정책 입력 snapshot은 실제 Vision과 미연결인데도 `MOCK_QUALIFIED`로 기록되는 provenance 정밀도
  한계가 남아 있다. 또한 `case.order_amount`는 generic attributes 기반이므로 실제 입력 확장 전
  source-tagged typed schema로 분리해야 한다. 현재 R1 seed는 이 값을 제공하지 않는다.
- `분석 계속하기` 422는 Case의 UTC 날짜 `2026-08-27`을 그대로 보내면 KST
  `2026-08-28`부터 효력인 Rule Set `2.0.1`이 선택되지 않던 문제였다. 현재 Web은
  가상 한국 데모의 업무 시간대 `Asia/Seoul`로 기준일을 계산한다. 다중 지역·실제 Tenant
  적용 전에는 서버가 권위 있는 Tenant timezone/policy-date 계약을 제공해야 한다.
- UI·API 수정과 자동 회귀는 통과했지만 Web rebuild로 기존 브라우저 memory token이
  초기화되어 인증된 R1 Case에서 수정된 CTA를 직접 클릭하는 마지막 수동 확인은 남아 있다.
  로그인 후 기존 실패 Case에서 재시도하면 추가 결정 없이 확인할 수 있다.
- HDP-100 기능은 `dfd6db2ab2052c4ce9a7f922d682c8e574abb05d`, closeout은
  `5c152fd0d1e97eba3b41b2ecea1cff7811814d90`로 Commit했고 local HEAD와 동일 원격 기능
  브랜치 SHA를 확인했다. PR 생성과 `develop` 병합은 아직 실행하지 않았다.
- GitHub에는 장기 `poc`, `mvp`, `final` branch가 따로 없다. 경량 GitFlow 계약상 현재 PoC는
  `feature/scenario-poc-hard-plastic`, 다음 통합/MVP 후보는 `develop`, 배포 가능한 최종 기준은
  `main`이다. 별도 영구 `mvp/final` branch를 추가하기보다 검증된 feature PR→`develop`,
  안정화 `release/vX.Y.Z`→`main`, annotated tag 순서를 따라야 한다.
- 원격 PoC는 `81b6e20`까지 fast-forward했고 CI #108이 PASS했다. 실제 E3 runtime·Top-100/정상 참고
  replay·현실형 10건·가상 정책 `2.0.1`은 `0f4de4b`, 상담원 UI·422 복구·빠른 검토·환불 확인서는
  `b3e09cf`, handoff는 `81b6e20`이다. 사용자 소유 문서 3개는 계속 미추적 보존한다.
- Vision 담당 원격 `feature/3-kaputt-dinov2-training`은 공통 기준 `4037d73`에서 PoC와 갈라져
  Vision 쪽 55 commits, PoC 쪽 21 commits가 서로 독점이다. Draft PR #4와 latest CI는 PASS지만
  PoC branch에 직접 merge하면 status/doc 및 runtime 계약 충돌 검토가 필요하다.

- 저장소를 Private로 유지하는 현재 플랜에서는 `main`·`develop` Branch protection API가
  HTTP 403을 반환한다. 저장소 공개 전환 없이 지원 플랜을 적용할지 Issue #1에서 결정한다.
- `kimhrin`은 현재 저장소 `read` 권한이라 보호 규칙의 필수 승인으로 인정되는
  write-access reviewer가 아니다. 명시적인 사용자 결정 전에는 권한을 올리지 않으며,
  필요하면 `write` 이상과 팀 구성을 별도로 승인한다.
- 초기에는 `@it0615`가 유일한 CODEOWNER다. 리뷰 가능한 구성원이 정해지면 조직 팀으로
  교체한다.
- Sprint 1은 Evidence 업로드 Idempotency, 강제 종료 뒤 `PENDING`·고아 Object 자동
  Reconciliation, Idempotency 만료 Cleanup·Key 재사용을 제공하지 않는다.
- 이미지 EXIF 제거·재인코딩·개인정보 마스킹·Virus Scan과 고객 원문·원본·Audit의
  Retention·삭제 정책은 실제 데이터 반입 전에 결정해야 한다.
- Refresh Token·Revocation·OIDC/SSO·PostgreSQL RLS와 Production MinIO Gateway,
  Secret Rotation, Edge 동시 업로드 제한은 후속 운영 범위다.
- Sprint 2.5에서 실제 Qwen Endpoint와 `external_gpu` 5건, Backend E2E 10건을 검증했다.
  다만 합성 기준 Action Accuracy 0.23과 Missing Information F1 0.00이므로 자동 Workflow
  결정에 사용하지 않고 Policy·Human Review 경계를 유지한다.
- Sprint 3 Vision Stage의 원래 Closeout은 Mock-qualified였다. 이후 E3 server/model/threshold
  runtime 연결은 통과했지만 실제 제품 dataset과 제품별 calibration은 여전히 검증하지 않았다.
- Text/Vision Alignment와 Claim↔Detection matching은 구현하지 않았다. Review UI와 immutable
  Review Report는 Sprint 5C 내부 데모로 구현됐지만 실제 운영 사용자/정책/데이터 품질 증거는
  없다. Policy Engine은 typed guidance만 생성하고 최종 업무 결정은 계속 Human Review가
  소유한다. Case/Evidence 접수만으로 Analysis가 자동 시작되지 않는다.
- KAPUT 참고 자료는 image-level 7-class multi-label과 item mask이며 defect bbox ground truth가
  아니다. Native→canonical mapping v1은 실제 모델 qualification 전까지 계약 가설이다.
- Vision image quality가 Provider에 없으면 `NOT_EVALUATED/null`이며 Mock quality를 실제 성능으로
  해석하지 않는다. Multi-image는 한 Stage에서 순차 처리하므로 throughput은 미측정이다.
- Sprint 2는 DLQ, 운영자 수동 재처리·취소 API, SSE, Provider 자동 선택·Fallback과 Prompt
  관리 UI를 제공하지 않는다. Raw Prompt·Provider Response를 보존하지 않는 것은 의도된
  보안·재현성 경계다.
- 실제 제품 측 결정인 결함 Taxonomy, 정책 표현, 개인정보 보존 기간, 인증·Tenant 범위는
  다음 Sprint의 ADR 대상으로 남아 있다.
- Qwen Node는 Peak VRAM 23,825 MiB로 24GB 여유가 매우 작고 FP8 KV cache를 사용한다.
  Context·동시성 변경과 실제 고객 분포 평가는 별도 requalification 대상이다.
- Community quantization의 calibration dataset은 Model Card에 기록되지 않아 제한사항이다.
- Qwen 평가 공식/enum 오류는 없었으나 100건 모두 input action `UNSPECIFIED`이고 Gold는 message
  action 추출을 요구해 Action 0.23의 의미가 모호하다. Metric bug가 아니므로 100건 재평가는
  실행하지 않았고 `QUALIFIED_WITH_LIMITATIONS`를 유지한다.
- Sprint 2는 독립 Closeout Gate를 통과했으며 승인된 로컬 Commit만 생성한다. 원격 Push와
  PR은 금지한다.
- 루트의 미추적 `kaputt_best_vision_architecture.md`는 Sprint 2와 무관한 사용자 작업물이다.
  이번 작업에서도 수정·삭제·Stage하지 않았으며 후속 소유 작업에서 별도로 다룬다.
- Sprint 4B Policy Corpus/Gold는 전부 합성 Reference이며 실제 기업 정책 정확성·법률 효력과
  실제 사용자 query 분포는 검증하지 않았다. Baseline corpus는 168 clause 규모다.
- Retrieval Test 40은 frozen profile로 한 번 실행 완료했다. Local MLX Query Builder와
  Grounded Explanation은 별도 Local PoC로 평가됐지만 Production Target Qwen3.8 재평가가 남았다.
  Policy Engine→Human Review→Resolution은 구현됐지만 실제 외부 실행과 운영 routing은 없다.
- Mac MPS embedding은 qualified지만 서비스 요청은 lock으로 직렬화되며 concurrency 2와 장시간
  swap/thrashing은 측정하지 않았다. Production network/process supervisor는 후속 운영 범위다.
- Qwen reranker는 Mac MPS에서 실제 qualification했지만 단일 process lock과 concurrency 1로
  제한한다. CPU fallback, 장시간 안정성, 실제 사용자 query 분포, production supervisor는 미검증이다.
- Locked Test에서 reranker는 Recall@10을 높이지 못했고 MRR/nDCG도 개선하지 못했다. 따라서
  자동 활성화 확대나 파라미터 재튜닝을 하지 않고 `RERANKER_NO_MEASURABLE_GAIN`으로 보존한다.
- 후보 K20 이후 recall 이득이 없고 candidate recall 0.9375가 현 corpus/query의 절대 상한이다.
  Query Builder 평가와 corpus recall 개선을 reranker 재튜닝보다 먼저 수행해야 한다.
- Sprint 4C-2의 실제 LLM Query Builder 3-way qualification은 계속
  `BLOCKED_EXTERNAL_LLM`이다. 4C-3A는 선택된 RAW 검색 결과와 독립적으로 진행했으며 이를
  LLM Query Builder 품질 증거로 해석하지 않는다.
- Sprint 4C-3A 구조 검증 뒤 Local MLX Grounding 의미 평가를 작은 합성 Test 10건과 사람
  spot-check 10건에서 통과했지만, 이를 Production faithfulness나 실제 기업 정책 품질로
  확대 해석하지 않는다.
- Citation Pack은 합성 Reference corpus의 immutable snapshot이다. 실제 기업 정책 정확성,
  법률 효력, 실제 사용자 분포, 보관·삭제 정책은 검증하지 않았다.
- 빠른 검토 `0.70`은 모델 confidence, Vision threshold, 정책 정확도 또는 실제 위험 확률이 아니다.
  `REQUIRES_HUMAN_REVIEW` 0.35, immutable Rule 0.25, Citation 0.15, qualification metadata 0.10,
  단일 `MARK_REVIEW_ELIGIBILITY` mapping 0.15의 PoC workflow-readiness 합계다. 제품 적용 전에는
  실제 상담원 사용성·오판 비용·Shadow 비교로 별도 재설정해야 한다.
- `허용`은 immutable Packet에서 `RETURN/REFUND/EXCHANGE/RESHIPMENT/REPAIR_REVIEW` 중 하나의
  typed mapping이 확정될 때만 활성화된다. `OTHER`, `ACTION_REVIEW`, 충돌 mapping은 고객 문장이나
  모델 출력으로 추론하지 않고 상세 검토로 보낸다. `비허용`은 준비도 Gate 통과 시
  `REJECT_REQUEST`로 기록한다.
- 빠른 검토는 사람이 누르는 하나의 UI 동작으로 기존 Claim·Resolve API를 조합한다. 자동화 테스트에서
  Decision→Resolution→Report를 검증했지만 실제 대기 중 R1 Case는 사용자 판단을 대신하지 않기 위해
  이번 세션에서 클릭하지 않았다. 따라서 live DB의 해당 Decision 생성은 다음 사용자 조작으로 남는다.
- 환불 처리 확인서는 Shopify·Stripe와 국내 전자상거래 공식 자료의 공통 필드를 참고한 CSight 가상
  사내 양식이다. 실제 결제업자 취소, 고객 통지, RMA·추적번호, 법정 처리기한을 기록한 증빙이 아니며,
  외부 연동 전에는 해당 항목을 `미요청/미발송/미연동`으로 유지한다. `ACTION_DRY_RUN_VALIDATED`도
  `환불 완료`가 아니라 `환불 요청 검증 완료`로만 표시한다.
- 메모리 약 4.21 GiB는 idle/ready 단일 시점 귀속 합계다. Apple MPS는 일반 RSS 대신 physical
  footprint를 사용했고 Docker는 cgroup 값을 사용했으므로 공유 page/cache 때문에 시스템 전체 사용량과
  정확히 일치하지 않는다. Vision peak 2,935 MiB와 Embedding peak 1,767 MiB는 동시 peak가 아니다.

## 9. 다음 실행 항목

- [ ] 논문 제출 준비: [편집 메모](../papers/CSight_2026_추계_초안_편집메모.md)와 DOCX/PDF를
  공동저자가 검토한 후 한글 편집기에서 공식 학생 서식·글꼴을 확인하고 HWP로 저장한다.
  저장 후 두 쪽/그림/표를 재확인하고 교신 이메일 및 제출 폼을 확인한다. 실제 접수는 별도 요청 때 수행.

- [x] `docs/progress/SESSION_HANDOFF_2026-09-01_GX10_MODEL_ENGINE.md`의 시작 프롬프트와 안전 경계를
  따라 Mac Git 상태와 `gx10-ade1` Tailscale online·active·ping 도달성을 읽기 전용으로 확인한다.
- [x] 공개키-only SSH로 `gx10-ade1`의 hardware/OS/CUDA/Docker/storage/network를 읽기 전용으로
  조사하고 원격 write·설치·전송·서비스 변경 0을 확인한다.
- [x] GX10 정상 stdout은 compact JSON, 전체 로그는 owner-only 원격 파일, 실패 때만 bounded tail을
  반환하는 `status/prepare/serve/canary/evaluate/report/stop` 실행 계약을 구현한다.
- [x] 현재 미커밋 source bundle에서 Secret·대형 파일·사용자 소유 파일을 제외한 스크립트 전송 범위를
  검토하고, GGUF/BF16/imatrix는 checksum과 byte size를 고정해 Khrin→GX10 직접 전송한다.
- [x] ARM64/CUDA 13/Blackwell용 pinned llama.cpp build, Q5 canary, decode·unified-memory 출처,
  4K/16K/32K와 4K concurrency 1/2/4 benchmark를 완료한다.
- [ ] 사용자 설치 GX10 vLLM의 image/model/runtime/context identity를 additive 계약으로 고정한 뒤 기존
  서비스를 중단하지 않고 동일 identity의 Extraction→Query Builder→Grounding frozen Dev를 실행한다.
  4090 same-harness는 별도 승인된 maintenance 창에서만 실행하며, 그 전에는 GX10을 PRIMARY로 전환하지 않는다.
- [x] Sprint 1 Diff를 독립 Closeout 감사하고 로컬 기준점 Commit을 생성한다.
- [x] Sprint 2 Append-only Analysis·Outbox·LLM Vertical Slice와 최종 검증을 완료한다.
- [x] Sprint 2 Diff를 독립 감사하고 승인된 로컬 Closeout Commit만 생성한다.
- [x] 깨끗한 Sprint 2 Commit에서 `feature/sprint-2-5-qwen38-serving` 브랜치를 만든다.
- [x] 고정 Qwen3.8 Artifact Revision과 GPU/vLLM 환경의 실제 서빙 Gate를 실행한다.
- [ ] 원격 작업 전 거버넌스 PR #2 병합 또는 Sprint 1 Branch 재정렬 순서를 결정한다.
- [ ] PR #2에 유효한 사람 리뷰와 승인을 확보한다.
- [ ] GitHub Private 저장소 Branch protection을 지원하는 플랜 적용 여부를 결정한다.
- [ ] `kimhrin`에게 승인 리뷰가 가능한 권한을 부여할지, 조직 팀을 만들지 결정한다.
- [ ] 플랜·리뷰어 결정 후 Issue #1의 목표 규칙을 `main`과 `develop`에 적용한다.
- [ ] 정책에 맞는 유효 승인 또는 명시적인 Bootstrap 예외 결정 후 PR #2를 `develop`에
  병합한다.
- [x] 다섯 `external_gpu` 합성 계약을 Skip 0으로 실행하고 Model Revision을 원장에 추가한다.
- [x] Sprint 2.5 로컬 Commit은 `git log -1`로 확인하고 Push·PR 없이 인계한다.
- [ ] 실제 고객 Data 반입 전에 개인정보·Retention 승인과 Action/Missing 품질 Dataset을
  별도 설계하고 Human Review Gate를 유지한다.
- [x] Sprint 3 Vision Stage, Evidence Snapshot, Text/Vision fan-out/join과 Partial Failure를
  ADR로 고정하고 Append-only Run·Attempt·Outbox를 확장한다.
- [x] 실제 E3 endpoint와 immutable model/taxonomy/threshold를 연결하고 synthetic image로
  direct HTTP와 Core causal model Gate를 실행한다.
- [ ] 제품도메인 대표 이미지와 Human Gold를 고정한 뒤 별도 product qualification을 실행한다.
- [x] 4090 Node의 Kaputt 전체 Query 추출 상태와 `plastic_hard` 분포를 확인하고, 별도 Qwen3.8
  VLM의 append-only 구조화 표본 4건을 실행한다.
- [x] `plastic_hard` 표본 4건의 Query/Reference Crop을 선택 추출해 사진 2장+비교 Prompt로
  재실행하고 상품 유형·가시 근거·defect-positive 탐지를 사람 검수한다.
- [x] paired 30건에서 결함 비교와 상품 메타데이터 schema/prompt를 분리하고 specific name 비율,
  금지 필드, 민감 패턴, latency와 결함 confusion/coverage를 평가한다.
- [ ] 사람이 paired 30건의 일반 상품명·category를 Gold로 확정하고 supplement,
  cleaning/chemical, pet-care taxonomy를 결정한 뒤 Qwen 후보의 accuracy를 계산한다. 결함 Target은
  공식 Label/E3만 사용한다.
- [ ] 다음 기능 Sprint에서는 먼저 Evidence Alignment 입력 계약과 Claim↔Detection matching,
  confidence calibration을 설계하고 Policy/Approval을 계속 분리한다.
- [x] 2026-09-09: offline diagnostic Alignment 1.0의 계약·유형 후보 연결·판단 불가·출처 검증과
  합성 평가 CLI를 완료한다. 위 항목의 calibration/실제 qualification/운영 stage 연결은 미완료로 남긴다.
- [ ] `docs/engine/ENGINE_IMPROVEMENT_PLAN_2026-09-09.md`에 따라 대표 상품군별 독립 정답과
  GX10 전용 runtime identity를 준비한 뒤 실제 text/vision/결합 품질을 각각 평가한다.
- [ ] Evidence Reconciliation·Orphan Cleanup·업로드 Idempotency와 Retention 정책을
  우선순위에 따라 별도 작업으로 계획한다.
- [x] Sprint 3 Closeout Commit을 확인하고 `feature/sprint-4a-llm-reference-data`에서 LLM
  Contract v2와 합성 Reference Data를 구현한다.
- [x] Sprint 3 Closeout Commit `330cbdb`와 Sprint 4A 전용 Branch를 확인한다.
- [x] LLM Contract v2, 합성 Policy Corpus와 고정 Evaluation Dataset을 구현한다.
- [x] Sprint 4A 최종 Gate를 확정하고 미커밋 상태로 인계한다.
- [x] Sprint 4B Policy ingestion→BM25→Qwen embedding→exact pgvector→RRF→locked evaluation을
  완료한다.
- [x] Sprint 4C-1은 frozen candidate baseline을 변경하지 않고 Qwen3-Reranker-0.6B profile,
  candidate reranking과 locked evaluation을 완료한다.
- [x] Sprint 4C-2에서 negative reranker 결과를 고정하고 raw/deterministic/LLM query builder를
  동일 candidate/evaluation 계약으로 분리 비교한다.
- [x] Citation Pack, strict grounded explanation schema, deterministic citation validation과
  Mock E2E를 Sprint 4C-3A 별도 계약으로 연결한다.
- [x] Sprint 4C-3A를 독립 감사하고 최신 Docker·Broker Gate까지 재통과한다.
- [x] 승인된 4C-3A 범위만 `feat: add citation grounding guardrails`로 로컬 Commit하고 새
  `feature/sprint-4c3b-local-mlx-grounding` 브랜치를 생성한다.
- [x] Local MLX Endpoint로 Grounding Dev 40 + Injection Dev 20에서 4C-3B를
  qualification하고 prompt/profile freeze 뒤 sealed Test 각 10건을 한 번만 실행한다.
- [x] Local MLX로 semantic citation precision/recall, unsupported policy claim rate와
  paraphrase faithfulness를 측정하기 전에는 구조 통과를 의미 품질 통과로 승격하지 않는다.
- [x] Sprint 5A에서 versioned Policy Engine Core를 구현하고 Grounded Explanation과 최종
  결정을 분리한다.
- [x] Sprint 5B Human Review decision record와 Admin override 계약을 구현한다.
- [x] Sprint 5B를 `4aefae6 feat: add human review workflow`로 Commit하고 원격 기능 브랜치에 백업한다.
- [x] Sprint 5C Resolution·External Action DRY-RUN, Review Report·KPI와 React 상담원 UI를 구현한다.
- [x] Sprint 5C 최종 Diff를 검토하고 `0a5f529` 기능 Commit·closeout 원장을 원격 기능 브랜치에 백업한다. PR과
  `develop` 병합은 거버넌스 결정 전까지 보류한다.
- [x] parallel Text/Vision join race 수정본을 live Mock binary 경로에서 재실행하고 terminal
  Run/Stage/Result/Assessment row와 duplicate 결과를 인과적으로 확인한다.
- [x] 재검증이 끝난 뒤에만 HDP-100 branch의 static/default/integration/migration/runtime 정확한
  수치를 새 원장 행에 추가한다. 기존 Sprint 5C 554/51 수치는 덮어쓰지 않는다.
- [x] HDP-100 변경을 `dfd6db2 feat: add hard-plastic scenario PoC`로 Commit하고 동일 원격 기능
  브랜치 SHA를 확인한다. PR과 `develop` 병합은 별도 결정 전까지 보류한다.
- [x] 실제 E3 checkpoint와 host-private endpoint를 확보하고 model identity, threshold,
  direct inference와 Core 저장 경로를 검증한다.
- [x] safe stop·idempotent setup·restart 뒤 direct score 재현과 Docker Worker health를 확인한다.
- [x] 전달받은 selected-correct Top-100의 파일 무결성을 검증하고 실제 E3 100장 전수 replay와
  비식별 hard-plastic 6건의 local Core causal sample을 수행한다.
- [x] 사용자 제공 정상 참고 77장을 격리 감사·실제 E3 replay하고, 결함 후보 6·threshold 미만 참고
  4의 현실형 내부 데모 Case/Evidence 10건을 비공개 저장 경로에 고정한다.
- [x] `csight` fictional 정책 Runtime을 local-only fail-closed로 준비하고 대표 결함 1·기준 미만 1을
  Text v2→RAW Top-3→Grounding→Policy→Human Review `PENDING`까지 실제 실행한다.
- [x] R1 장문 문의 10건·3열 상담원 UI·CSight Commerce 가상 정책 8문서/52조항과 canonical
  Rule Set `2.0.1`을 구현하고 대표 수리·Safety·단순변심 3건을 Human Review까지 실제 실행한다.
- [x] 검증된 R1 사진 10장에 표시 전용 가상 상품명·SKU·KRW 가격대·문의 목적을 매핑하고
  Case 목록 검색/표시와 상세 상품 카드에서 실제 판매가·환불 입력이 아님을 명시한다.
- [x] `COMMERCE_CONTEXT_R2_E3` 10건에 합성 고객 ID/이름·마스킹 연락처·주문/결제·가상 배송지와
  운송 정보를 DB 저장하고, Case 목록/상세와 새 환불 확인서 스냅샷에 allowlist로 연결한다.
- [ ] 추가 사진 시나리오는 개인 이름·바코드·브랜드·중복을 제외하고 사진별 제품군과 SHA를
  검토한 뒤 별도 버전으로 확장한다. 같은 사진에 다른 상품을 임의로 중복 매핑하지 않는다.
- [x] Case Workspace를 `지금 할 일` 단일 CTA와 2열 본문으로 단순화하고,
  데스크톱 inert X를 제거하며 UTC/KST policy-date 422와 API 오류 메시지 파싱을 수정한다.
- [x] Review 화면에 PoC 준비도 0.70 기반 `허용/비허용` 빠른 검토를 추가하고, 인증 Human 클릭 뒤
  CAS Claim→Resolve→Resolution/DRY-RUN→immutable Review Report 자동 열기를 연결한다.
- [x] `APPROVE_REFUND` 보고서를 금액·수량·처리 상태·취소 요청·고객 통지·반품 추적·정책 승인·
  감사 ID가 포함된 `환불 처리 확인서`로 분리하고 A4 인쇄, 누락값 fail-closed, 실제 환불 미실행
  표기를 검증한다.
- [x] 내부 decision/status 코드를 자연어 업무 라벨로 표시하고 terminal Report에서 고객 안내 EMAIL
  simulation을 생성·재열람하되 `SIMULATED_NOT_SENT`와 side effects 0을 고정한다.
- [x] terminal Report와 같은 transaction에서 tenant별 비식별 학습 asset을 자동 적재하고, 기존
  Report를 소급 allowlist 적재하며 데이터 자산 화면에 30/60건 기준선 준비 상태를 표시한다.
- [ ] 실제 상담원 처리 표본이 30건에 도달하면 데이터 누락·분포·버전 구성을 검토해 기준선을 승인하고,
  60건 전에는 드리프트 비교 수치를 생성하지 않는다.
- [ ] 인증된 담당자가 대기 중인 비Safety 대표 Case 하나에서 실제 `허용` 또는 `비허용`을 선택하고,
  생성된 Decision·Resolution·Report를 확인한다. 이 선택은 변경 불가능한 사람의 최종 판단이다.
- [ ] 로그인한 상담원 세션에서 기존 422 Case의 `분석 계속하기`를 한 번 누르고
  Policy `2.0.1` 성공 또는 이전 성공 실행 복구를 확인한다.
- [ ] 상담원 콘솔에서 대기 중인 대표 3건을 인증된 사람이 검토한다. 실제 판단이 입력되기 전에는
  Resolve·Review Report·Resolution·DRY-RUN을 만들지 않는다.
- [ ] 실제 데이터 입력 전에 Policy input qualification과 금액 provenance를 source-tagged typed
  schema로 보강한다.
- [ ] HDP-100 5개 합성 시나리오의 대표 이미지셋·Human Gold·재현 점수를 버전 고정한다.
- [ ] E3 endpoint timeout/restart와 malformed response를 live 주입하고 retry/fail-closed를 검증한다.
- [x] `doongdoong.org`·`www` Cloudflare ingress를 지뢰찾기 3000/3001에서 CSight Web 8080으로
  전환하고 외부 Web·API·Admin 인증과 브라우저 Login 화면을 검증한다.
- [x] GitHub 조직 저장소의 원격 branch·PR·CI·tag와 로컬 worktree를 교차 감사하고
  PoC=`feature/scenario-poc-hard-plastic`, MVP 통합=`develop`, 최종 릴리스=`main` 역할을 확인한다.
- [x] 로컬 후속 변경을 E3 runtime, 현실형 demo/policy, 상담원 Web, 상태 문서의 검토 가능한
  Commit으로 분리하되 사용자 소유 문서·raw image·checkpoint·local report는 제외한다.
- [x] 분리 Commit 전체 회귀와 Secret/대용량 파일 감사를 통과하고 사용자의 승인 범위에서
  원격 PoC branch를 fast-forward로 최신화해 CI #108 성공을 확인한다.
- [ ] Vision Draft PR #4의 `ml/cv` 변경을 현재 PoC runtime 계약과 별도 비교해 충돌을 해결한 뒤
  `develop` 통합 순서를 결정한다. PoC PR과 PR #2/보호 규칙 결정 전 `main` 승격은 금지한다.
- [ ] 공개 터널을 공유하기 전 Cloudflare Access를 적용하거나 `csight` Admin Credential을
  강화하고, 시연 종료 뒤 터널 복원·중단 여부를 결정한다.
- [ ] Kaputt 권리 범위를 벗어나는 고객·상업 사용은 별도 법률·권리자 승인 전 차단한다.
- [x] 내부 PoC 상품군 4개·결함군 3개와 첫 10건 SHA Allowlist를 버전 고정하고, E3 점수 margin과
  source label·사람 승인 fail-closed Gate를 적용한다.
- [x] 별도 `poc_closed_set/2.0.0`에 새 10건을 승인해 식품·건강보조제와 생활화학·접착제를 포함한
  상품군 4/4를 표현하고 actual E3·멱등 재실행을 통과한다. 이는 Human Gold 성능평가가 아니다.
- [ ] 고객 후보, 상품군 1개, 결함 유형 2~3개와 비식별 실제 Case/Human Gold 30건 이상을 확보한다.
- [ ] 버전·효력일이 있는 실제 기업 정책과 실제 Policy/Case/User Query 분포 평가를 확보한다.
- [ ] Retention·삭제·EXIF 제거·접근권한 승인을 받고 증거 artifact ID/hash를 Gate에 연결한다.
- [x] E3 manifest·preprocess·threshold·labels·model card와 checkpoint SHA package를 고정한다.
- [ ] 제품별 결함 평가를 완료하거나 Vision의 제품 적용 제외 범위를 명시 승인한다.
- [ ] 실제 목표 분포에서 Qwen3.8 Extraction·Grounding을 재평가하고 Shadow Mode Human 비교를 완료한다.
- [ ] 모든 외부 증거와 zero-safety/clean-environment artifact가 갖춰진 뒤에만
  `make require-limited-poc`으로 `LIMITED_POC` 승격을 판정한다.
- [ ] 대표 10 Case를 연속 처리하면서 5초 간격으로 Vision·Embedding physical footprint, Docker
  container memory, queue depth와 실패율을 함께 기록하고 p95/peak 기준점을 추가한다.
- [x] 문의/주문/상품 번호의 server-side Case·Review 검색, 검색어 고정 cursor와 관리자용 6개
  온보딩 준비도 API/UI를 구현하고 전체 Web·PostgreSQL 회귀를 통과한다.
- [x] generic Ed25519 signed Case intake, task별 signed model route plan, Analysis stage route
  snapshot과 text extraction v2 runtime identity guard를 migration 0032~0034로 구현한다.
- [x] demo controller와 분리된 fail-closed pilot Compose/controller/preflight를 구현하고 build,
  migrate, prune, volume 삭제 없이 admission 실패 시 start를 차단한다.
- [x] 사용자 승인 하에 filesystem 가용 공간을 최소 30 GiB로 확보하고, push된 SHA의 clean RC
  commit/image를 별도 worktree에서 검증한다. 2026-09-01 관측 가용 공간은 38 GiB다.
- [ ] 실제 고객 입력을 받은 뒤 owner-only `infra/pilot/.env.pilot`을 준비하고 preflight를 실행한다.
- [ ] 고객 tenant의 no-role signed-intake actor/public key, retention, OIDC group mapping, 활성
  policy index/rule set을 provision하고 온보딩 준비도에서 해당 gate를 각각 재검증한다.
- [x] Policy query builder와 grounded explanation에 immutable route snapshot·historical activation·
  exact runtime identity guard를 연결하고 Query Build/Search durable v2 event·worker를 분리한다.
- [x] exact BF16·pinned llama.cpp·attested corpus에서 Q4 control, imatrix Q4, mixed Q4/Q6, Q5를
  offline 생성하고 최종 후보·입력 재해시와 Khrin 서비스 원상복구를 완료한다.
- [x] imatrix를 clean one-pass로 재생성하고 현재 llama.cpp Dockerfile을 고정 image로 빌드해
  binary·build manifest·SBOM parity를 다시 고정했다.
- [ ] mixed Q4/Q6와 Q5를 개인 private 저장소의 불변 revision으로 먼저 고정하고, 우승 후보는
  조직 소유 private mirror와 새 signed manifest로 승격한다. 현재 파일을 자동 업로드하지 않는다.
- [x] provider-neutral GGUF 세 task evaluator와 authenticated canary를 연결해 mixed Q4/Q6·Q5를
  동일 source/lock/result 계약으로 실제 RTX 4090 Dev 비교하고 `NO_WINNER`를 불변 증거로 남겼다.
- [ ] 상대 우세한 Q5를 Dev 개선 기준으로 Extraction prompt/schema, Query plan, Grounding 미해결
  조건·주입 안전 profile을 조정하고 fresh Dev에서 세 절대 gate를 모두 다시 통과시킨다. Extraction과
  Grounding의 개별 synthetic Dev gate는 통과했지만 Query Builder와 최종 joint rerun은 미완료다.
- [x] Extraction 평가 보고서에 원문·예측 없이 ambiguity TP/FP/FN aggregate만 추가하고,
  결정론적 ambiguity 검증 후보를 고정 20건 Dev에서 `local.5`와 비교한다.
- [x] 동일 후보의 provider/adapter latency를 분리 측정하고 guarded `local.8` 전체 Dev에서 p95
  `4,908.237 ms`를 재현한다. bounded correction이 두 gate를 닫았으므로 Extraction QLoRA는 보류한다.
- [x] guarded `local.8` Q5 synthetic Dev 120건에서 canonical Extraction gate 15/15를 통과한다.
- [x] Grounding 미해결 조건 recall과 injection safety를 runtime `local.2`로 bounded canary→전체
  synthetic Dev 순서로 복구하고 canonical gate 25/25를 통과한다.
- [ ] LLM Query Builder는 RAW→HYBRID 기준선보다 모든 검색 지표가 높을 때만 PRIMARY 후보로 검토한다.
- [ ] Dev를 통과한 한 후보만 freeze→sealed Test 1회→signed SHADOW 100→20 terminal workflow로
  검증한다. 현재 `NO_WINNER`이므로 이 단계는 시작하지 않는다.
- [ ] release-eligible 모델, 실제 20-session/20-workflow, 고객 IdP lifecycle, 암호화 immutable
  off-host WAL·MinIO target-host 복원 2회와 경보 전달을 모두 증명한 뒤 pilot preflight/start를 실행한다.

## 10. 세션 종료 체크리스트

- [x] 2026-10-18 실제 논문 초안: 저자 정보, 그림/표, 2쪽 DOCX/PDF 시각 검증, 한글 DOCX
  정상 열람을 확인했다. native HWP 실패와 최종 저장/접수 미완료·후속 단계·검증 증거를 기록했다.
- [x] 2026-10-18 논문 참고서: 공식 양식·기존 실험 원본·분모·주장 범위·로컬 링크를 대조하고,
  HWP 조판·학회 접수·사용자 평가 미실행과 다음 작성 작업을 기록했다.
- [x] 변경한 파일과 목적을 기록했다.
- [x] 실제 실행한 검증 명령과 결과만 기록했다.
- [x] 실패·미실행·Skip을 `PASS`로 표현하지 않았다.
- [x] 외부 서비스 상태에 관측 날짜를 붙였다.
- [x] 남은 Blocker와 필요한 사용자 결정을 적었다.
- [x] 다음 작업을 한 개 이상의 실행 가능한 체크박스로 남겼다.
- [x] Secret, 고객 원문, 전체 URL을 기록하지 않았다.
- [x] 아래 세션 로그를 추가했다.
- [x] 2026-09-28 영상 게시: 원본 해시, 공개 루트·www·영상 범위 응답, 브라우저 자동 재생을 확인했다.
- [x] 2026-09-28 영상 게시: 미해결 가용성 조건과 다음 확인 항목을 아래 로그에 기록했다.
- [x] 2026-09-29 `/login` 영상 추가: 공개 브라우저 재생, 로컬 로그인 화면, 우회 설정 백업을 확인했다.
- [x] 2026-09-29 `/login2` 콘솔 복원: 공개 폼·비로그인 이동·영상 경로 유지, 검증 한계를 아래 로그에 기록했다.
- [x] 2026-09-30 GX10 Q5 복구: 사전 작업 인벤토리·canary·Core Worker 합성 경로·미실행 UI 범위를 아래 로그에 기록했다.
- [x] 2026-10-01 CSight Docker 종료: Mac/GX10 실행 컨테이너 0개·볼륨 보존·재기동 조건을 아래 로그에 기록했다.

## 11. 세션 로그

### 2026-08-26 — Sprint 0 Foundation 완료

- 목표: 실행 가능한 FastAPI/Celery/PostgreSQL/RabbitMQ/MinIO Foundation 구축
- 완료: API, Port/Adapter, Mock AI, Migration, Worker, Compose, CI, 테스트, 문서
- 검증: 기본 37건과 Integration 4건을 포함한 `make test-all`, 실제 장애·복구 경로 통과
- 미실행: GitHub 원격 CI
- 다음 작업: GitHub 협업 기반 생성 후 Sprint 1 Case/Evidence 경계 구현

### 2026-08-26 — GitHub 협업 기반 준비

- 목표: 조직 저장소, 장기 브랜치, PR 중심 협업, 세션 간 인계 체계 구축
- 완료: GitHub 계정 확인, 브랜치 정책, 기여 규칙, PR·Issue 템플릿, 체크리스트,
  초기 커밋 안전성 감사, 로컬 `main`·`develop`, `CSightICT` 조직과 Private
  `CSightICT/csight-core` 저장소
- 검증: GitHub 플러그인에서 연결 계정 `it0615` 확인, 새 조직 미존재 확인. 고신뢰
  Secret과 5 MiB 초과 커밋 후보가 없고 Issue Form YAML이 파싱됨을 확인. Ruff, Format,
  Pyright, 기본 37건과 Core Integration 4건 재통과
- Blocker: GitHub CLI OAuth App의 `workflow` scope 부족. 장치 인증 1차 시도는 HTTP 502
- 다음 작업: OAuth scope 갱신 재시도, 원격 Push, 첫 CI, Branch protection 적용

### 2026-08-26 — GitHub 연결 승인 및 원격 거버넌스 구축

- 목표: 승인된 `workflow` scope와 `CSightICT` 커넥터 연결로 원격 협업 경로를 활성화
- 완료: CLI `workflow` scope, 저장소 단위 Connector 설치, 세 원격 브랜치, 초기 CI,
  병합 방식 설정, 보호 규칙 추적 Issue #1, 거버넌스 PR #2
- 검증: GitHub 플러그인에서 Private 저장소 조회 성공. `main`, `develop`, 작업 브랜치의
  초기 Actions와 PR #2 Head `7298cda` Run `32867908663`이 성공하고 Check Context가
  `Quality and fast tests`임을 확인
- Blocker: Private 저장소의 현재 플랜은 Branch protection API를 HTTP 403으로 거부.
  `kimhrin`은 현재 `read` 권한이며 승인 없이 권한을 변경하지 않음
- 다음 작업: PR #2 사람 리뷰, 지원 플랜과 리뷰어 권한 결정, Issue #1 이행

### 2026-08-26 — Sprint 1 Case & Evidence Vertical Slice 완료

- 목표: 인증된 Tenant 사용자의 Case 접수부터 Private 이미지 Evidence와 Signed GET까지
  실제 PostgreSQL·MinIO 기반 End-to-End 경로 완성
- Branch: `feature/sprint-1-case-evidence`; 모든 변경은 미커밋이며 Commit·Push하지 않음
- 완료: Local Seed, Argon2id·HS256 인증, 현재 Role 재조회, Principal Tenant Scope,
  Case 생성·조회·이력·Idempotency, 이미지 검증·요청 상한, Private MinIO, 실제 HEAD
  무결성 확인, Signed URL, 실패 보상·안전 관측, Migration, API·운영 문서와 ADR-0006~0008
- 검증: Ruff, 138-file Format, Pyright 0, Fast 183건, 실제 Core Integration 18건,
  Tenant A/B E2E, 실제 MinIO/PostgreSQL 보상 2건, 최종 Live HTTP 9개와 Multipart 413,
  Migration Head·Drift, Seed 2회, 5개 장기 서비스 Healthy
- 정리: 테스트 업무 Row와 MinIO Object가 모두 0임을 확인하고 Core 서비스는 Healthy로 유지
- 감사: 독립 재검토에서 재현 가능한 P0·P1·P2 완료 차단 이슈 없음
- 제한: 자동 분석, Evidence Idempotency·Reconciliation, EXIF·악성코드 처리, Retention,
  OIDC·RLS와 Production Edge·Secret 운영은 후속 범위
- 다음 작업: 사용자 Diff 검토 후 별도 승인 시 Commit·Push·PR, 이후 Sprint 2 Analysis Run

### 2026-08-26 — Sprint 1 Closeout 독립 감사 및 로컬 기준점

- 목표: 미커밋 Sprint 1 전체 Diff를 기존 완료 보고와 독립적으로 재검토하고 재현 가능한
  로컬 기준점으로 확정
- 발견: P0 0, P1 3, P2 4. 타 Tenant Viewer 업로드 오류 우선순위, SQL Echo Bind 값,
  누락 Object Signed URL을 P1으로 확인
- 수정: Tenant `404` 우선, SQL Parameter 은닉, URL 전 Object HEAD, 빈 Allowlist
  Fail-closed와 Tenant·Animated·Hard Bomb 회귀 테스트
- 검증: Pyright 0, Fast 189, Integration 18, Unit 168, Contract 14, Architecture 4,
  기본 E2E 3, HTTP API 15, 격리 Migration 3경로·Drift·복합 FK, Compose 5개 Healthy,
  Seed 2회, 실제 JWT→Case Replay→Evidence→Signed GET→Object HEAD→Tenant A/B `404`
- 정리: 업무 Row 0, MinIO Object 0, UUID 기반 임시 DB 2개 삭제
- Git: 정확한 Sprint 1 후보만 로컬 Commit, Push·PR 없음. 범위 밖 미추적 Kaputt 문서는
  사용자 파일로 보존
- 다음 작업: 별도 승인 전 Push 금지; 원격 전 PR #2/Branch 순서 결정; 별도 지시 후 Sprint 2

### 2026-08-26 — Sprint 2 Append-only Analysis & LLM Vertical Slice 완료

- 목표: 인증된 Reviewer/Admin의 명시적 요청을 Append-only Analysis Run으로 등록하고
  PostgreSQL Outbox·RabbitMQ·Celery를 거쳐 Strict Text Extraction Result까지 완성
- Branch: `feature/sprint-2-analysis-llm`; Sprint 2 변경은 미커밋이며 Commit·Push하지 않음
- 완료: Run·Stage·Attempt·Result·Idempotency·Outbox, Prompt/Schema Snapshot, 결정적 Mock,
  vLLM Adapter, 생성·목록·상세·Case Latest API, Dispatcher·Worker·Compose와 ADR-0009~0011
- 복구: Provider Retry/Max, Worker Lost, Soft/Hard Timeout, 활성 Lease Wake-up, Claim Token
  Fencing, 최종 Lease 만료의 원자적 Failed 종결과 Duplicate Result 방지
- 검증: Ruff, Python Format 158, Pyright 0, Fast 291, Core Integration 31, Analysis Focus
  76/13, PostgreSQL Application E2E 8, 격리 Migration 세 경로와 Drift 없음
- Live: 실제 202·Replay 200·Conflict 409·Tenant 404, Mock `SUCCEEDED`, 같은 Celery Message
  재전달 뒤 Attempt 1·Result 1, 장기 서비스 6개 Healthy
- Skip: 외부 vLLM Endpoint 미설정으로 합성 GPU 계약 5건 Skip; 외부 호출은 하지 않음
- 정리: Analysis 여섯 Table, 합성 Case·Tenant, RabbitMQ Ready/Unacked와 임시 DB가 모두 0
- Git: Commit·Push·PR 없음. 사용자 소유 미추적 Kaputt 문서는 수정·삭제·Stage하지 않음
- 다음 작업: 사용자 Diff 검토와 별도 Git 승인 대기; 이후 별도 Sprint 3 지시가 있으면
  Vision·Alignment·Partial Failure 경계를 ADR부터 확정

### 2026-08-26 — Sprint 2 Closeout 독립 감사

- 목표: 미커밋 Sprint 2 전체 Diff를 이전 완료 보고와 독립적으로 감사하고 재현 가능한 로컬
  기준점으로 확정
- 발견: P0 0, P1 0, P2 문서 상태 2건, P3 후속 운영 경계 3건; P0/P1 미해결 0
- 검증: Ruff, Format 158, Pyright 0, Fast 291, Unit 227, Contract 45, Architecture 4,
  Integration 31, HTTP 29, 실제 PostgreSQL 세 Migration 경로와 Drift 없음
- Live: 최종 Docker Build, Core 6개 Healthy, 202·200·409·Tenant 404·`SUCCEEDED`, 같은
  Message 2회 재발행 뒤 Result 1·Attempt 1
- 정리: Analysis 여섯 Table, 합성 Tenant, RabbitMQ Ready/Unacked와 임시 DB가 모두 0
- Git: 승인된 Sprint 2 범위만 로컬 Commit하고 Push·PR 금지; Kaputt 사용자 파일은
  수정·삭제·Stage하지 않음
- 다음 작업: 깨끗한 Commit에서 Sprint 2.5 브랜치를 만들고 고정 Qwen3.8 실제 서빙 검증

### 2026-08-26 — Sprint 2.5 Qwen3.8 실제 서빙 Qualification

- 목표: 고정 `cyankiwi/Qwen3.8-27B-AWQ-INT4` revision을 단일 RTX 4090에서 private,
  text-only, non-thinking strict extraction으로 실제 검증
- 환경: vLLM 0.26.0 image digest, Transformers 5.14.1, CUDA 13.0, Driver 580.173.02,
  max length 8192, sequence 1, FP8 KV, eager, CPU Offload 없음
- 보안: private Tailscale bind와 인증. Process audit에서 초기 CLI API Key 노출을 발견해
  일회용 Key를 즉시 회전하고 `VLLM_API_KEY` 환경변수 주입으로 수정·재검증
- 재현성: `/v1/models` 일치, Cold Start 2회, cache-hit API Ready 97초, 26m19s 동안
  Restart·OOM·Error 0
- 품질: Prompt 1.0.0의 중복 Enum 2건을 숨기지 않고 재현. vLLM이 `uniqueItems`를 거부함을
  확인한 뒤 Taxonomy·set 지시의 Prompt 1.0.1로 version bump; 100건 안전 Gate 전부 통과
- 제한: Issue F1 0.95이나 Action Accuracy 0.23, Missing F1 0.00. Spot-check 안전 20/20,
  Issue 19/20, Action 10/20, Missing 8/20이라 Human Review 필수
- 성능: Profile A p50/p95 1.470/1.558초, TTFT 0.089/0.176초, 36.36 token/s;
  Peak VRAM 23,825 MiB. 동시성 2는 안정적이지만 latency가 약 2배
- Integration: 실제 External 5/5, Backend E2E 성공 10/10, Result·Attempt 각 10,
  Duplicate No-op 1/1, Timeout Retry 2 Attempt, Raw Column·unsafe Outbox 0
- 정리: 합성 Case/Run 22와 관련 Row 정리, Queue·Orphan 0, Core 6개 기본 Mock Healthy
- 검증: Ruff, Format 162, Pyright 0, Fast 291, Core Integration 31, 실제 External 5
- 판정: `QUALIFIED_WITH_LIMITATIONS`; Push·PR 없음. 다음 작업은 로컬 Commit SHA 기록과
  Sprint 3 Vision 계약 준비

### 2026-08-26 — Sprint 3 Vision Analysis와 Multimodal Fan-out/Join

- 목표: 기존 Append-only Analysis에 image별 Vision Stage/Result, immutable Evidence Snapshot,
  Text/Vision 독립 fan-out과 terminal join을 추가
- Branch/Base: `feature/sprint-3-vision-analysis` / `7d63cbb`; Commit·Push·PR 없음
- 완료: canonical schema/quality/bbox, KAPUT native mapping, 10 Mock scenario, Remote multipart
  Adapter, `20260826_0004`, Snapshot/Result/Detection repository, API detail과 no-image 422
- Workflow: text-only 유지, multimodal 2 Stage/Event, multi-image 순차 append, retry/lease/fencing,
  `SUCCEEDED`/`PARTIAL_SUCCESS`/`FAILED` 집계와 partial result 보존
- 발견·수정: 병렬 Worker가 동시에 Run `QUEUED→RUNNING` CAS를 시도할 때 패한 Stage claim이
  rollback되어 고립되던 결함. Run이 이미 `RUNNING`이면 claim을 유지하도록 양 Stage 수정
- LLM 감사: taxonomy/metric 수식 오류 0, Missing set/empty convention 정상. Action input/gold
  의미 모호성을 확인하고 exact/macro/support diagnostics와 regression test 추가; 재평가 미실행
- 검증: Ruff, Format 167, Pyright 0, Fast 328, Integration 36, Architecture/Contract/E2E 55,
  isolated Migration lifecycle/drift, 실제 MinIO bounded read, Docker 6개 Healthy와 Queue 0
- Live: Login→PNG upload→text-only success→multimodal success(2 Stage, Result/Detection 1),
  no-image 422, Text success/Vision failure partial success; 합성 Case 5/Object 4 정리
- External Vision: endpoint/model/sample 미제공으로 1 skipped·369 deselected,
  `SKIPPED_EXTERNAL_VISION_NOT_AVAILABLE`; 판정 `MOCK_QUALIFIED`
- 문서: ADR-0013~0017, 설계 03~10, README, Sprint 3 Progress와 현재 상태 동기화
- 다음 작업: 실제 Vision qualification 자산 확보 또는 별도 Sprint에서 Evidence Alignment 입력
  계약과 Claim↔Detection matching/calibration을 먼저 설계

### 2026-08-26 — Sprint 3 Closeout 감사

- 목표: 미커밋 Sprint 3 전체 Diff를 코드·테스트·Migration·Runtime 기준으로 재감사하고 로컬
  기준점 Commit 조건을 확정
- 감사: Evidence Snapshot, append-only Vision Result/Detection, 독립 fan-out, CAS 경쟁 수정,
  DB 기반 join, 네 partial 조합, 6-ID Queue, tenant 복합 FK와 canonical geometry 확인
- 검증: Ruff, Format 165, Pyright 0, Fast 328, Unit 264, Contract 45, Architecture 4, E2E 6,
  Core Integration 36, 격리 Migration 세 경로와 drift 0
- Runtime: API/Worker/Dispatcher/PostgreSQL/RabbitMQ/MinIO 6개 Healthy, HTTP ready,
  RabbitMQ analysis queue ready/unacked 0
- Skip: 실제 Vision 자산 미제공으로 외부 Vision 1건 `SKIPPED_EXTERNAL_VISION_NOT_AVAILABLE`
- 판정: P0 0, P1 0, `SPRINT_3_CLOSEOUT=PASS`; Push·PR 금지, Kaputt 사용자 파일 제외
- 다음 작업: 승인된 Sprint 3 범위만 로컬 Commit한 뒤 Sprint 4A 전용 브랜치를 생성

### 2026-08-26 — Sprint 4A LLM Contract v2와 Reference Data

- 목표: LLM 출력 의미를 v2로 분리하고 Policy Retrieval/RAG 구현 전에 합성 Reference Corpus와
  고정 Gold/평가 기준을 구축
- Git: Sprint 3 Closeout `330cbdb`에서 `feature/sprint-4a-llm-reference-data` 생성;
  Sprint 4A Commit·Push·PR 없음, Kaputt 사용자 파일 제외
- LLM: v1 보존, Pipeline/Prompt/Schema v2, 복수 action exact quote, text ambiguity,
  deterministic completeness/action consistency와 append-only v2 child/API
- Reference: 합성 Tenant 2, Document 24, Clause 168, Policy Type 9, retired 6,
  Exception/Evidence Requirement 각 48, duplicate 0
- Evaluation: Extraction 160, Retrieval 120, Grounding 50, Injection 30, Demo 10;
  manifest/hash/report와 Gold missing/cross-tenant 0
- Live: Docker image rebuild 후 Migration `0005`/drift 0, v2 Mock SUCCEEDED/action 2/
  MULTIPLE_EXTRACTED/rule 1.0.0; 합성 row와 queue 정리
- Skip: 실제 Qwen endpoint를 사용하지 않아 `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE`; Gold
  self-check를 모델 평가로 표현하지 않음
- 범위 밖: Embedding, BM25, pgvector, hybrid/reranker, RAG API, Policy Engine, Alignment,
  Routing, Review, Report, Vision 변경
- 다음 작업: 최종 전체 Gate 수치를 확정하고 Sprint 4B의 DB ingestion/검색 baseline에 인계

### 2026-08-26 — Sprint 4A 최종 Gate와 세션 인계

- 목표: Sprint 4A 미커밋 Diff를 정적 검사, 전체 회귀, 데이터 결정성, Migration 3경로와
  최신 Docker Runtime으로 최종 검증하고 다음 에이전트가 바로 이어갈 수 있게 확정
- 보강: Corpus validator가 순환 Parent, 문서–Clause 메타데이터 불일치, 만료 ACTIVE,
  비대칭·Cross-Tenant Supersession을 fail-closed하도록 강화하고 Contract 5건 추가
- 검증: Ruff, Format 179, Pyright 0, Fast 354/42 deselected, Unit 294, Architecture 4,
  Contract 50, E2E 6, Core Integration 36/외부 GPU 5 skipped
- 데이터: Policy 24/168과 Evaluation 160/120/50/30/10 재생성·검증, 반복 Build aggregate
  hash 동일, broken/duplicate/cross-tenant 0
- Migration/Runtime: empty→0005, 0005→0004→0005, 0004→0005, drift 0, 임시 DB 0;
  최신 image Core 6개 Healthy, live/ready 200, analysis queue 0/0
- Skip: Sprint 4A 실제 Qwen은 `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE`; Vision도 기존 실제 자산
  미제공으로 1건 Skip. Gold self-check는 실제 모델 평가가 아님
- Git: Branch `feature/sprint-4a-llm-reference-data`, Base `330cbdb`; Sprint 4A Commit·Push·PR
  없음. `kaputt_best_vision_architecture.md`는 사용자 파일로 미수정·미Stage
- 판정: `REFERENCE_DATA_QUALIFIED_WITH_LIMITATIONS`
- 다음 작업: 별도 Sprint 4B 지시에서 Policy Document/Clause DB schema와 ingestion부터 시작하고
  BM25 baseline→dense embedding→pgvector→metadata filter→hybrid retrieval 평가 순서 유지

### 2026-08-26 — Sprint 4A 독립 Closeout 감사

- 목표: Sprint 4A 전체 Diff를 코드·데이터·Migration·Runtime 기준으로 독립 재감사하고 승인된
  로컬 기준점 Commit 조건을 확정
- 감사: v1 호환, v2 append-only child/API, 합성 Corpus tenant/version/parent 무결성과 고정
  Gold 참조를 확인; P0 0, P1 0
- 검증: Ruff, Format 179, Pyright 0, Fast 354/42 deselected, Unit 294, Architecture 4,
  Contract 50, E2E 6
- Integration: 장기 실행 실제 Dispatcher가 테스트 Outbox를 선점해 최초 1건 실패; 실행
  서비스를 격리한 재실행은 36 passed, 외부 GPU 5 skipped
- 데이터: Policy 24/168/2와 Evaluation 160/120/50/30/10 재생성, stable aggregate hash,
  broken/duplicate/cross-tenant 0
- Migration/Runtime: 세 경로·drift 0, 임시 DB cleanup, 최신 Core 6개 Healthy,
  live/ready 200, queue 0/0
- 판정: `SPRINT_4A_CLOSEOUT=PASS`; 정확한 Commit message는
  `feat: add LLM contract v2 and policy reference corpus`, Push·PR 금지
- 안전: `kaputt_best_vision_architecture.md`는 사용자 파일로 계속 미수정·미Stage
- 다음 작업: 승인 범위만 Stage/Commit하고 해당 SHA에서
  `feature/sprint-4b-policy-retrieval`을 생성

### 2026-08-26 — Sprint 4B Policy Corpus Ingestion과 Hybrid Retrieval

- Git: Sprint 4A를 `6f3a667 feat: add LLM contract v2 and policy reference corpus`로 로컬
  Commit하고 `feature/sprint-4b-policy-retrieval` 생성; Sprint 4B Commit·Push·PR 없음
- Persistence: `20260826_0006`, manifest-driven immutable ingestion, tenant 2/document 24/clause
  168/embedding 168, idempotent run reuse와 version content mismatch 차단
- Retrieval: `ko_policy_lexical:1.0.0` exact BM25, pinned Qwen3 1024-d last-token normalized
  embedding, metadata-filtered pgvector exact cosine, weighted `policy_rrf:1.0.0`
- API: JWT principal tenant 기반 read-only 세 mode; 두 tenant 6 smoke 통과. Provider down에서
  lexical 200, dense/hybrid 503, Core readiness 200
- Evaluation: Dev 80에서 BM25/RRF freeze 후 Test 40 한 번 실행. Cross-tenant, future, retired,
  wrong-version, hard-negative, duplicate 0; determinism 100%
- Qualification: Apple M4/32 GB/macOS/MPS에서 model load와 168-clause embedding 실제 측정,
  external embedding Skip 0. Process supervisor/concurrency 2는 미검증
- 검증: Ruff/Format/Pyright, Fast, Unit/Contract/Architecture/API, 전체 Integration, migration
  3경로/drift 0, 최신 Core 6개 Healthy. 정확한 최종 count는 같은 날짜 검증 원장 최신 행 참조
- 실패 기록: 첫 embedding DB build FK flush, 첫 API image의 dev-only dependency, Dev result directory,
  도구 background process 수명주기 실패를 수정·재검증하고 숨기지 않음
- 문서: ADR-0026~0038, RAG guide 4개, Qwen manifest, 설계 03~10, README와 Sprint 4B progress
- 안전: `kaputt_best_vision_architecture.md` 미수정·미삭제·미Stage
- 다음 작업: Sprint 4C에서 reranker를 먼저 독립 qualification하고 그 뒤 query builder/citation/
  grounded explanation을 별도 locked evaluation으로 진행

### 2026-08-26 — Sprint 4B 독립 Closeout 감사

- 목표: 미커밋 Sprint 4B 전체 Diff를 코드·DB·평가 artifact·실서비스 기준으로 재감사하고
  로컬 기준점 Commit 조건을 확정
- 판정: P0 0, P1 0, `SPRINT_4B_CLOSEOUT=PASS`
- 검증: Ruff, Format 210, Pyright 0, Fast 376/48 deselected, Unit 306,
  Architecture 6, Contract 58/1 deselected, E2E 6, Integration 41/외부 GPU 5 skipped
- 데이터: tenant 2/document 24/clause 168/embedding 168/ACTIVE index 2, 동일 ingestion run
  재사용, parent/dimension mismatch 0
- 실제 모델/API: Qwen embedding MPS, external 1/423 deselected, 두 tenant 세 mode smoke,
  provider down LEXICAL 200·DENSE/HYBRID 503·Core ready 200
- Migration/Runtime: empty/previous/round-trip 세 경로 `0006`, drift 0, 임시 DB 정리,
  Core 6개 Healthy
- 문서 공백: 요청된 `PROJECT_BLUEPRINT.md`는 저장소에 없으며 canonical 설계 문서는
  `CSight_project_docs/docs`에서 감사
- 안전: 사용자 `kaputt_best_vision_architecture.md`는 미수정·미삭제·미Stage
- 다음 작업: 승인된 Sprint 4B 범위만 `feat: add hybrid policy retrieval baseline`으로 로컬
  Commit하고 Push/PR 없이 Sprint 4C-1 브랜치를 생성

### 2026-08-26 — Sprint 4C-1 Qwen Policy Reranker Qualification

- Git: Sprint 4B를 `4216028 feat: add hybrid policy retrieval baseline`으로 로컬 Commit하고
  `feature/sprint-4c1-policy-reranker` 생성; Sprint 4C-1 Commit·Stage·Push·PR 없음
- Candidate: frozen HYBRID_RRF를 K10/20/30/50으로 분석해 Dev max recall의 최소 K20과 final10을
  선택. Test 후보 진단은 한 번만 실행했고 K20 recall 0.9375, oracle nDCG 0.95164
- Model: `Qwen/Qwen3-Reranker-0.6B` revision `e61197ed45024b0ed8a2d74b80b4d909f1255473`,
  MPS private service, pair serialization 1.0.0, normalized yes/no score를 실제 검증
- Qualification: token min/p50/p95/max 172/178/187/189, truncation 0, cold load 3.60초,
  K20 p50/p95 2.362/2.375초. concurrency 2에서 tokenizer race를 수정했지만 처리 이득이 없어
  운영 동시성은 1로 제한; `QWEN3_RERANKER_QUALIFIED_WITH_LIMITATIONS`
- Architecture: 기술 독립 Port/Profile, Remote/Mock Adapter, full candidate allowlist와 응답 검증,
  `HYBRID_RERANKED`, no fallback, provider-down 503, 기존 세 mode와 Core readiness 보존
- Persistence: `20260826_0007`, immutable reranker profile과 tenant별 ACTIVE execution profile;
  activation 2회가 profile 1/execution 2를 유지
- Evaluation: Dev 80 freeze 뒤 locked Test 40 한 번. Test Hybrid→Reranked Recall@10
  0.925→0.925, MRR 0.53833→0.51250, nDCG 0.59841→0.59802; 개선 17/악화 23
- Correctness: cross-tenant/wrong-version/future/retired/duplicate/hard-negative/candidate mutation 0,
  Dev deterministic rerun 100%; Test 재호출·재튜닝 없음
- 검증: Ruff, Format 232, Pyright 0, Fast 402, Unit 319, Architecture 8, Contract 69,
  E2E 6, Integration 42, External embedding/reranker 각 1, Migration 세 경로 drift 0,
  두 tenant API와 Core 6개 Healthy
- 판정: `RERANKER_NO_MEASURABLE_GAIN`. 다음 작업은 Sprint 4C-2에서 negative result를 보존하고
  raw/deterministic/LLM query builder를 분리 평가하는 것
- 안전: `kaputt_best_vision_architecture.md`는 미수정·미삭제·미Stage

### 2026-08-27 — Sprint 4C-1 독립 Closeout 감사

- 목표: Sprint 4C-1 전체 Diff를 candidate/oracle, model contract, API, DB, 외부 MPS와
  locked evaluation 기준으로 독립 재감사하고 로컬 기준점 조건 확정
- 발견·수정: `make format-check`가 `infra/reranker`를 검사하지 않던 P1 1건을 전체 `infra`로
  확장; P0 0, 수정 후 P1 0
- 검증: Ruff, Format 234, Pyright 0, Fast 402, Unit 319, Architecture 8, Contract 69,
  E2E 6, Integration 42, External embedding/reranker 각 1
- Evaluation: K20/final10, candidate recall 0.9375, mutation 0, Dev 80 재계산 mismatch 0,
  Test 재호출 없음; `RERANKER_NO_MEASURABLE_GAIN` 유지
- Failure record: 봉인된 Dev artifact를 생성 명령으로 덮어쓰려는 시도는 guard가 거부했고,
  전용 verifier로 재현성을 확인. Make background model은 도구 셸 수명 때문에 종료돼 foreground
  세션으로 재실행
- Migration/Runtime: empty/previous/round-trip `0007`, drift 0, 임시 DB 정리, Core 6개 Healthy,
  base mode 200/reranked provider-down 503/readiness 200
- 안전: Push·PR 없음, `kaputt_best_vision_architecture.md` 미수정·미삭제·미Stage
- 다음 작업: 승인된 Sprint 4C-1 범위만 `chore: qualify qwen3 policy reranker`로 로컬 Commit하고
  `feature/sprint-4c2-policy-query-builder` Branch 생성

### 2026-08-27 — Sprint 4C-2 Policy Query Builder

- Git: 4C-1을 `14cae29 chore: qualify qwen3 policy reranker`로 로컬 Commit하고
  `feature/sprint-4c2-policy-query-builder` 생성; 4C-2 Commit·Push·PR 없음
- External: 실제 Endpoint 부재로 Extraction v2와 LLM Query Builder를
  `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE`로 기록; Mock을 Qwen 성능으로 사용하지 않음
- Dataset: 새 `policy_query_builder_v1` Dev 80/Test 40, Test sealed, broken/cross-tenant 0,
  hash `5040f219aff5546a88073f132889215df2574c3196bdcad9f4f9e28141fd72c4`
- Contract/Retrieval: Strict 1~3 Query, deterministic 1.0.0, prompt 1.1.0, Core hard filters,
  frozen HYBRID K20, reranker off, `policy_multi_query_rrf:1.0.0`, query provenance
- Persistence/API: Migration `0008`, append-only Run/Profile/Query/Hit와 전용 Outbox, POST 202/
  replay 200/conflict 409, List/Get, Viewer read-only, v1 result 거부
- Live: deterministic와 Mock-LLM Run SUCCEEDED, duplicate task NOOP, provider-down은
  `POLICY_QUERY_BUILDER_PROVIDER_UNAVAILABLE`, embedding-down은 `EMBEDDING_PROVIDER_UNAVAILABLE`,
  Core readiness 200, cross-tenant detail 404
- Evaluation: Dev RAW Recall/MRR/nDCG 1.0/0.709549/0.724277, deterministic
  1.0/0.667133/0.636635. Freeze 뒤 Test 1회 RAW 0.975/0.739236/0.741392,
  deterministic 1.0/0.724544/0.657571
- 판정: 평가된 두 전략에서는 RAW를 선택했지만 실제 LLM 비교가 없어 최종은
  `BLOCKED_EXTERNAL_LLM`; 기본 Retriever HYBRID 유지
- 검증: Ruff/Format 252/Pyright 0, Fast 419, Unit 327, Architecture 8, Contract 78,
  E2E 6, Integration 42/5 skipped, External embedding 1, Migration 3경로 drift 0,
  Core 6 healthy, 실제 RabbitMQ Worker vertical slice PASS, `git diff --check` PASS
- 다음 작업: 승인된 Qwen Endpoint가 생기면 Dev qualification부터 수행하고, 이후 4C-3
  Citation Pack/Grounded Explanation gate로 진행

### 2026-08-27 — Sprint 4C-2 Closeout and Sprint 4C-3A Citation Grounding

- Git: 4C-2를 `a282817 feat: add case-based policy retrieval query planning`으로 로컬
  Commit하고 `feature/sprint-4c3a-citation-grounding-guards` 생성; Push·PR 없음
- Citation Pack: 성공 Retrieval Run의 rank, clause/document version, title/section/type/text,
  effective interval, source hash, query IDs/strategy와 retrieval profile hash를 immutable snapshot
- Contract: 고정 중립 summary, statement별 citation 필수, extra field 금지, unresolved condition만
  허용; approval/rejection/fraud/responsibility/liability/final decision field 부재
- Validation: pack-local `CIT-NNN` allowlist, duplicate normalization, ACTIVE/as-of/version/tenant
  recheck, unknown citation fail-closed; Raw prompt/response/reasoning 비저장
- Async/API: append-only profile/pack/item/run/result/outbox, identifier-only RabbitMQ payload,
  thin Celery Worker, Case 하위 POST/List/Get, tenant isolation
- Evaluation: 합성 Grounding 50 + Injection 30에서 structural violation 0, replay 100%; semantic
  citation precision/recall, unsupported claim, paraphrase faithfulness는 실제 Qwen 부재로 SKIPPED
- Verification: Format 258/Ruff/Pyright PASS, Fast 431 passed/3 external skipped,
  Integration 42 passed/5 external GPU skipped, Grounding 대상 12 passed
- Migration/Runtime: empty/previous/round-trip `0009`와 drift 0; 실제 PostgreSQL/RabbitMQ/Celery
  Mock에서 10 citation/statement, replay 200, tenant 404. Provider-down은 stable unavailable로
  종료하고 result·Mock fallback 0; 검증 행 정리 완료
- Runtime audit fix: Compose 기본 Worker queue 목록에 `grounded-explanation`을 추가하고 rendered
  config에서 소비 대상 포함을 확인
- Docker: 외부 registry metadata 응답 정지로 새 image rebuild는 BLOCKED. Dockerfile diff 0,
  기존 Core 6개는 Healthy/live·ready 200이며 host-native 4C-3A broker flow로 런타임 검증
- 다음 작업: 4C-3A를 미커밋·Push/PR 없음으로 인계하고, 실제 Qwen 사용 가능 시 4C-3B Dev
  qualification부터 수행. Registry 복구 후 Docker image rebuild 재검증

### 2026-08-27 — Sprint 4C-3A Independent Closeout

- Audit: Citation Pack snapshot/allowlist, decision-free strict schema, append-only persistence,
  identifier-only broker payload와 thin Worker를 실제 코드·DB·API·Broker 기준으로 재검토
- 판정: P0 0, P1 0, `APPLICATION_QUALIFICATION=PASS`; semantic citation 품질은 실제 모델
  평가 전이므로 `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE` 유지
- Regression: Format 258, Ruff 0, Pyright 0, Fast 431 passed/3 skipped/47 deselected,
  Architecture+Unit+Contract+E2E 431 passed/2 skipped, Integration 42 passed/5 skipped
- Migration: empty/previous/round-trip `0009`, drift 0, 임시 DB 3개 정리
- Docker recovery: 제한적 재시도에서 최신 image build 성공; Dockerfile diff 0, Core 6 healthy,
  live/ready 200, 4 queues consumer 1·depth 0
- Live: 10 citations/statements, replay 200, tenant 404; terminal event 2회 재전달 뒤 run/result
  각 1건; provider-down은 stable unavailable, result 0, Mock fallback 0
- Cleanup: 검증용 Grounding run/result/outbox/item/pack을 범위 한정 삭제하고 대상 run 0 확인
- Git: `kaputt_best_vision_architecture.md`는 수정·삭제·Stage하지 않음; Closeout Commit만 생성하고
  Push·PR은 하지 않음
- 다음 작업: 지정 Commit에서 `feature/sprint-4c3b-local-mlx-grounding`을 만들고 preferred
  MLX artifact 존재성·revision·호환성을 먼저 검증한 뒤 Dev→freeze→Test 순서로 진행

### 2026-08-27 — Sprint 4C-3B Local MLX PoC

- Git: 4C-3A를 `72cbe12 feat: add citation grounding guardrails`로 로컬 Commit하고
  `feature/sprint-4c3b-local-mlx-grounding` 생성; 4C-3B Commit·Push·PR 없음
- Runtime: exact `mlx-community/Qwen3.5-9B-MLX-4bit` revision
  `938d8919941c6e7efd3c7150eff7fe9d12afa631`, MLX 0.32.2/mlx-vlm 0.6.17,
  localhost:8080, 4096 context, 512 output, concurrency 1, thinking disabled
- Extraction: Dev120/Test40 구조·source quote 100%, Test issue/action/ambiguity F1
  0.8533/0.1935/0.1951; `LOCAL_POC` only
- Query: Dev80/Test40 구조·안전 100%. Test Local Recall@10 0.90와 coverage 0.75가 RAW
  0.975/0.85보다 낮아 `RAW_REMAINS_SELECTED`
- Grounding: Dev40/Test10, Injection Dev20/Test10 구조·citation·의미·replay 100%, 위반 0;
  사람 spot-check Dev20/Test10 모두 rubric PASS
- Live: Docker Core 최신 rebuild 성공, 6개 healthy. Docker Worker→Mac MLX 실제 safe-default
  top-3 E2E 10/10, duplicate 0, citation violation 0. top-10은 4096 context 초과로 fail-closed
- Stability: 2시간 34분 이상 연속, RSS 약 6.50 GB, swap 0
- 미완료: 실제 timeout→recovery와 malformed-provider fault injection은 미실행(offline contract만
  존재). Qwen3.8 Production Target 재qualification 필요
- 검증: Ruff/Format/Pyright PASS, Default 437 passed, Architecture+Unit+Contract+E2E 437 passed,
  Integration 42 passed/5 skipped, External Local MLX 3 passed/skip 0, Migration drift 0,
  `git diff --check` PASS, 실제 Local 결과 cross-tenant 404
- 장애: unreachable Local endpoint는 retryable `LLM_PROVIDER_UNAVAILABLE`/provider `mlx`, Core
  readiness 200, Mock fallback 0. 실제 timeout recovery와 malformed response injection은 미실행
- Git 인계: Sprint 4C-3B 변경은 요청대로 미커밋; `kaputt_best_vision_architecture.md`는
  미수정·미삭제·미Stage
- 다음 작업: 실제 timeout recovery/malformed provider fault injection, Qwen3.8 재qualification,
  Sprint 5A Policy Engine과 Human Review Gate 준비

### 2026-08-27 — Sprint 4C-3B Independent Closeout

- 판정: P0 0, P1 0, `SPRINT_4C3B_CLOSEOUT=PASS`; 범위는 Local PoC이며 Qwen3.8 Production
  qualification이나 실제 기업 정책 품질을 의미하지 않음
- Runtime: pinned Qwen3.5-9B MLX revision, MLX 0.32.2/mlx-vlm 0.6.17, strict JSON과 reasoning
  leakage 0을 재확인; 실제 unreachable endpoint는 retryable provider `mlx`, Core ready 200
- Regression: Ruff 0, Format 275, Pyright 0, Default 437 passed/53 deselected,
  Integration 42 passed/5 external-GPU skipped, External Local MLX 3 passed/487 deselected
- Artifact: 봉인 Test를 재실행하지 않고 Extraction 40, Query 40, Grounding 10, Injection 10의
  metric/count와 frozen profile·현재 code prompt hash를 검증; Test 재실행 guard 확인
- 선택 결과: Extraction issue/action/ambiguity F1 0.8533/0.1935/0.1951, Local Query
  Recall@10 0.90 대 RAW 0.975로 `RAW_REMAINS_SELECTED`; 작은 합성 Grounding 결과를 Production
  faithfulness로 과장하지 않음
- Persistence/Runtime: head `20260827_0009`, drift 0, MLX extraction stage 12와 grounding result
  10, duplicate result group 0, raw prompt/response/reasoning column 0; Core 6 healthy, 4 application
  queue consumer 1/depth 0
- NOT_RUN: 실행 중 Local server의 ownership PID file이 없어 restart smoke는 안전상 미실행;
  실제 timeout→recovery와 malformed-provider runtime injection도 `OFFLINE_CONTRACT_ONLY` 유지
- Git: Closeout 문서 추가, `git diff --check` PASS. `kaputt_best_vision_architecture.md`는
  미수정·미삭제·미Stage; 정확한 로컬 Commit 메시지는
  `feat: add local MLX LLM grounding PoC`, Push·PR 금지
- 다음 작업: Closeout Commit 뒤 `feature/sprint-5a-policy-engine-core`를 생성하고, versioned
  deterministic Policy Engine을 LLM/RAG/최종 업무 결정과 분리해 구현

### 2026-08-27 — Sprint 5A Versioned Deterministic Policy Engine Core

- Git: Base `d0950f6`, Branch `feature/sprint-5a-policy-engine-core`; Sprint 5A 변경은 미커밋이며
  Push·PR 없음. 사용자 소유 `kaputt_best_vision_architecture.md`는 미수정·미삭제·미Stage
- Core: versioned typed field/operator registry, five condition statuses, four rule statuses,
  deterministic aggregation과 final decision을 표현할 수 없는 six-effect allowlist 구현
- Safety: Local MLX action/ambiguity는 hard input에서 제외하고 Mock Vision 조건은
  `NOT_EVALUATED`; 불확실 조건은 자동 eligibility/exception을 만들지 않고 review/evidence로 수렴
- Data: synthetic tenant 2, immutable rule set 2, rule/source 24/24. 동일 version content conflict,
  cross-tenant/source-version/hash/effective mismatch를 fail-closed 처리
- Persistence: Migration `20260827_0010_policy_engine`의 10개 table, frozen typed input과
  qualification snapshot, append-only result/effect, identifier-only outbox를 구현
- Runtime: POST 202/replay 200/List/Get, exact queue identifiers, 전용 `policy-evaluation` route,
  thin Celery task, duplicate terminal delivery `NOOP`, viewer read-only와 tenant 404 확인
- Evaluation: Dev80 freeze 뒤 sealed Test40을 단 한 번 실행. selection/rule/condition/effect/
  summary/source/version/replay 모두 1.0, cross-tenant/future/retired/final-decision 위반 0;
  sealed Test 재실행 guard가 이후 호출을 거부함
- Verification: Ruff PASS, Format 296, Pyright 0, Default 456 passed, isolated Integration
  44 passed/5 external-GPU skipped, migration 세 경로와 live drift 0, rule DB audit PASS
- Runtime verification: 최종 Docker Core 6/6 healthy, five application queues consumer 1/depth 0,
  live smoke rules 12/replay 200/duplicate NOOP/tenant 404/Mock Vision `NOT_EVALUATED`
- Failure record: 첫 Integration 실행은 장기 Dispatcher가 test outbox를 먼저 claim해 1건
  실패했으며 서비스 격리 후 전체 통과. 첫 host Alembic 확인은 `.env` 미Export로 접속 전
  중단됐고 환경 적용 후 head `0010`/drift 0 확인
- 범위 밖: 실제 정책 타당성, 실제 Vision, Evidence Alignment, final decision, routing,
  Human Review UI/override/final report, rule editor와 LLM rule generation
- 다음 작업: 사용자 Diff 검토 후 명시적 승인 시 Sprint 5A 로컬 Commit만 생성한다. 이후
  Sprint 5B에서 Policy Effect를 append-only Human Review로 연결하되 최종 결정은 사람이 소유한다.

### 2026-08-27 — Sprint 5A Independent Closeout Audit

- 판정: P0 0, P1 0, `POLICY_ENGINE_CORE_QUALIFIED_WITH_LIMITATIONS`
- Integrity: deterministic rebuild hash 동일, ingest 신규 row 0, active/set/rule/source
  2/2/24/24, source·tenant·version·final-effect 위반 0
- Evaluation: Dev80만 재계산해 모든 metric 1.0과 위반 0 확인; 봉인 Test40은 verifier로만
  검증하고 재실행하지 않음
- Regression: Ruff PASS, Format 296, Pyright 0, Default 456 passed/55 deselected,
  격리 Integration 44 passed/5 external-GPU skipped/462 deselected
- Migration: Empty→0010, 0009→0010, 0010→0009→0010과 drift 0, 임시 DB 0. 최초
  round-trip 명령의 잘못된 설명형 revision은 Alembic이 거부했고 실제 `20260827_0009`로 수정
- Runtime: Core 6 healthy, application queue 5개 consumer 1/depth 0, live rules12/replay200/
  duplicate NOOP/tenant404/Vision NOT_EVALUATED
- Git: `git diff --check` PASS. 지정 메시지 `feat: add versioned policy engine core`로 승인
  범위만 로컬 Commit 예정이며 Push·PR 없음; Kaputt 사용자 파일 제외
- 다음 작업: Commit SHA를 확인하고 `feature/sprint-5b-human-review-workflow`에서 immutable
  Review Packet, CAS Task, append-only Action 및 human-only Decision을 구현

### 2026-08-27 — Sprint 5B Human Review Workflow

- Git: Sprint 5A를 `67eafdd feat: add versioned policy engine core`로 로컬 Commit하고
  `feature/sprint-5b-human-review-workflow` 생성. Sprint 5B Commit·Push·PR 없음
- Boundary: Policy success가 identifier-only `human_review.requested.v1`을 원자 저장하고 thin
  Worker는 Task/Packet/CREATED만 생성. Final Decision은 authenticated Admin/Reviewer Resolve만 생성
- Workflow: versioned mapping, immutable packet, five-state machine, CAS claim, release/evidence/
  resume/escalate, assignment history, append-only actions와 decision/basis를 구현
- Authorization: Viewer read-only, Reviewer는 Standard/Evidence/Exception과 자신의 task만 action,
  Manager/Safety/Escalated claim 및 Manager/Safety resolve는 Admin only; cross-tenant는 404
- Integrity: Rule/Citation/Evidence/Analysis basis를 packet/run/tenant allowlist로 검증하고 rationale
  10–2000자를 요구. Decision/Packet은 수정·삭제 경로 없이 content hash와 unique constraint로 보호
- Evaluation: `human_review_workflow_v1` 90건, Dev60 freeze 뒤 sealed Test30 단 1회. mapping,
  priority, transition, authorization, assignment, basis, outcome, audit, replay 모두 1.0; 위반 0
- Verification: Ruff PASS, Format 315, Pyright 0, Default 484/57 deselected, Integration
  46/5 skipped/490 deselected, migration 세 경로 drift 0, 임시 DB 0
- Runtime: 최신 Docker 6 healthy, six application queues consumer 1/depth 0. Live task/packet/
  created/claim/resolve/decision/basis 각 1, duplicate event NOOP, claim/resolve 409, tenant 404
- Failure record: 첫 직접 probe에서 ORM relationship이 없는 aggregate insert flush 순서로 FK 오류가
  발생해 root와 decision을 먼저 flush하도록 수정. 첫 전체 회귀의 8 failures는 이전 migration
  테스트가 0010 head를 고정한 기대값이 원인이었고 0011 단일 head로 갱신 후 전체 통과
- Scope: 실제 환불·교환·결제·CRM·알림·보고서·UI·Decision revision/자동 assignment/SLA 없음.
  Grounding은 advisory, Local LLM은 LOCAL_POC, Vision은 MOCK_QUALIFIED
- Handoff: `docs/progress/SPRINT_5B_HUMAN_REVIEW_WORKFLOW.md`와 ADR-0077~0088이 canonical 인계점.
  `kaputt_best_vision_architecture.md`는 미수정·미삭제·미Stage이며 다음은 Sprint 5C 설계 검토

### 2026-08-27 — Sprint 5B Async Reliability Closeout

- 판정: P0 0, P1 0, `CLOSEOUT_PASS_WITH_PRODUCT_LIMITATIONS`
- Reliability: Policy Retrieval·Grounding·Policy Evaluation·Human Review Outbox에 claim token,
  lease, publish backoff, `CONSUMED/FAILED`와 실패 기록을 추가하고 fenced dispatcher로 통합
- Worker: Retrieval·Grounding·Policy worker 실행 lease, late-result fencing, bounded retry와 poison
  event의 durable failure를 구현; Human Review는 event 검증부터 Task·Packet·CREATED·CONSUMED까지
  단일 트랜잭션으로 처리
- Integrity: Packet/Decision hash를 조회와 Resolve 직전에 다시 검증하고 basis tenant/run/type/FK
  일치를 fail-closed로 보강; duplicate Resolve도 기존 Decision hash를 먼저 검증
- Verification: Ruff 0, Format 324, Pyright 0, Default 516 passed/59 deselected, disposable
  Integration 48 passed/5 external-GPU skipped/522 deselected, focused reliability 검증 통과
- Migration: Empty→0012, 0011→0012, 0012→0011→0012, drift 0, 임시 DB 잔존 0. 중간 개발형
  0012가 stamp된 live DB도 tolerant downgrade 뒤 최종 round-trip과 drift 0 확인
- Runtime: Core 6 healthy, six application queues consumer 1/depth 0. RabbitMQ 중단 중 event가
  backoff된 뒤 재기동 후 `CONSUMED`; duplicate worker 실행 두 번 모두 `NOOP`, Result 수 불변
- Failure record: 공유 DB Integration에서 dispatcher 경합이 드러나 disposable clone runner로
  격리했다. 중간 0012 live schema의 누락 constraint로 첫 downgrade가 실패해 명시적
  `DROP CONSTRAINT IF EXISTS` 복구 경로를 추가하고 전체 lifecycle을 재통과했다.
- Git: `feature/sprint-5b-human-review-workflow`에서 지정 메시지로 Commit하고 동일 원격 기능
  브랜치에 백업 예정. PR과 `develop` 병합은 거버넌스 PR #2와 보호 규칙 결정 전까지 보류
- Scope: 실제 기업 정책/Case/사용자 분포, 실제 Vision, Qwen3.8 재평가와 운영 UI는 미검증.
  `CSight_MASTER_HANDOFF_2026-08-27.md`와 `kaputt_best_vision_architecture.md`는 Commit 제외
- 다음 작업: `feature/sprint-5c-case-resolution-external-action`에서 Resolution Projection,
  immutable Action Intent, 입력 완전성 검증과 네트워크 없는 External Action DRY-RUN 구현

### 2026-08-27 — Sprint 5C Case Resolution, DRY-RUN, and Consultant Console Closeout

- 판정: 내부 시뮬레이션 데모 구현·검증 완료. 현재 제품 판정은
  `SYNTHETIC_MOCK_SIMULATION_DEMO`; Limited PoC는 외부 증거 미확보로 `BLOCKED`
- Git: Sprint 5B를 `4aefae6 feat: add human review workflow`로 Commit·Push했다. Sprint 5C 기능은
  `0a5f529 feat: add case resolution and PoC console`로 Commit하고
  `origin/feature/sprint-5c-case-resolution-external-action`에 백업했으며 PR은 만들지 않았다. 본
  closeout 원장도 동일 기능 브랜치의 후속 문서 Commit에 포함한다.
- Resolution: Case와 별도인 versioned projection/event, exact Decision mapping 1.0.0,
  immutable Action Intent, explicit input only, missing/invalid input과 conflicting Decision
  fail-closed 경로 구현. `cases.status`와 기존 Decision/Packet은 불변
- Reliability: Decision과 Resolution request 원자 저장, Resolution/Simulation별 durable outbox,
  claim/lease/backoff/exact-event validation, execution fencing과 duplicate `NOOP` 구현
- Action: network-free deterministic `DRY_RUN`만 생성하고 모든 Result가
  `side_effects_performed=false`; `LIVE`는 `LIVE_EXTERNAL_ACTION_DISABLED`
- Reporting: terminal Resolution version마다 content-hashed `review_report/1.0.0` snapshot,
  tenant-scoped latest read, tamper rejection, degraded integrity-failure snapshot과 printable UI 구현.
  PoC KPI는 모두 numerator/denominator/sample count와 zero-denominator null을 반환
- Console: React 19·TypeScript·Vite, OpenAPI type/check, memory-only JWT, opaque workflow checkpoint,
  Case/Evidence/analysis/retrieval/citation/policy/review/resolution/report/metrics 화면 구현
- Verification: Backend static PASS, default 554 passed/62 deselected, Integration 51 passed/
  5 external-GPU skipped/560 deselected. Frontend lint/type/OpenAPI/build PASS, Vitest 6,
  Playwright 5. PostgreSQL head `0014`, drift 0
- Runtime: 7 services healthy, 8 queues consumer 1/depth 0. Live Human Decision→Resolution→
  `ACTION_DRY_RUN_VALIDATED`, duplicate `NOOP`, Case status 불변, cross-tenant `404`
- Broker recovery: 실제 RabbitMQ 중단 중 Resolution request가 `PENDING` attempts 3까지 보존되고
  재기동 뒤 `CONSUMED` attempts 5, 최종 Resolution validated
- Demo evidence: Scenario 1은 별도 live backend causal 경로, Scenario 2는 disposable PostgreSQL
  integration을 보유한다. Playwright 5개는 intercepted API fixture이며 특히 Scenario 3–5는
  fixture-driven UI/component-backed로서 live causal E2E라고 주장하지 않는다.
- Remaining promotion evidence: actual `LIVE`, 실제 Data/Policy/Vision qualification, 개인정보
  승인, Shadow Human comparison, 실제 Qwen Extraction/Grounding reevaluation. 하나라도 없으면
  성능·ROI를 실제 PoC 결과로 주장하지 않는다.
- Handoff: 상세 원장은 `docs/progress/SPRINT_5C_CASE_RESOLUTION_CONSOLE.md`, 승격 계약은
  `docs/resolution/SPRINT_5C_DEMO_BOUNDARY.md`. 사용자 소유 루트 문서 두 개는 수정·삭제·Stage하지 않음

### 2026-08-27 — Current Status HTML Dashboard

- 산출물: `docs/progress/CSIGHT_CURRENT_STATUS_2026-08-27.html`
- 목적: Sprint 5B/5C 완료 범위, 검증 수치, 업무 흐름, 5개 데모의 증거 수준, Limited PoC
  미충족 Gate와 다음 실행 순서를 한 화면에서 확인
- 표현 경계: 현재 판정을 `SYNTHETIC_MOCK_SIMULATION_DEMO`로 유지하고 Scenario 3–5를
  fixture-driven으로 표시하며 실제 PoC 성능·ROI를 주장하지 않음
- 구현: 외부 asset이나 네트워크 의존성이 없는 standalone HTML, 반응형 화면과 인쇄/PDF 지원
- 검증: 로컬 exact URL HTTP 200, 핵심 판정·검증 수치·Git 기준점 포함, whitespace diff PASS
- Git 안전: 사용자 소유 루트 문서 두 개는 수정·삭제·Stage하지 않음

### 2026-08-27 — HDP-100 Synthetic Scenario PoC and Binary Vision Contract

- 판정: `SCENARIO_TECH_POC_READY` / offline pack `OFFLINE_SCENARIO_PACK_READY`; 실제 E3 runtime은
  `RUNTIME_VISION_INTEGRATION_BLOCKED`. Limited PoC 판정은 계속 `BLOCKED`
- Scope: 가상 브랜드의 fictional `HDP-100` 수동 펌프형 디스펜서. 실제 기업·고객 Data와 실제
  기업 Policy는 오늘 범위에서 의도적으로 사용하지 않음
- Artifacts: synthetic Case/Gold 36/36, split demo/dev/test 5/21/10, synthetic policy version
  1.0.0의 10 clauses/7 rules, 대표 demo 5개, artifact/pack hash 연결
- Offline verification: required artifact, JSON, synthetic boundary, hashes, Case 수, policy,
  Gold linkage, demo boundaries, binary model manifest의 9 checks 모두 PASS
- E3 evidence: epoch 10 `best.pt` 후보의 AP 0.884863, AUROC 0.931604, threshold 0.8984375는
  담당자 제공 보고서에서 전사한 수치이며 `report_metrics_reproduced_by_csight=false`
- Threshold boundary: score `>= 0.8984375`는 위치·유형 없는 고신뢰 결함 후보다. 더 낮은
  score는 `BELOW_HIGH_CONFIDENCE_THRESHOLD`이며 정상이나 결함 없음 판정이 아니다.
- Runtime: image-level any-defect assessment와 Detection을 분리하고 deterministic Mock binary
  contract만 live 연결. 실제 `best.pt`, checkpoint package, serving endpoint/reference는 부재
- Persistence: additive `20260827_0015_vision_image_assessment`가 현재 DB Head. 실제 E3 metric을
  runtime prediction에 복사하지 않고 score/threshold/outcome만 append-only 저장
- Pending failure record: parallel Text/Vision terminal join race를 수정했으며 live causal
  재검증이 진행 중. 실제 PostgreSQL barrier focused regression은 1 passed/14 deselected지만,
  재검증 완료 전 현재 branch의 새 전체 회귀 수치와 최종 live runtime 판정은
  `PENDING_REVERIFICATION`; 기존 Sprint 5C 554/51 결과는 역사적 기준점으로 보존
- Claim boundary: 실제 E3 추론, HDP-100 제품별 정확도, 실제 고객 성능, 정상 자동 판정,
  실제 기업 정책 검증, 자동 승인, 비용 절감·ROI는 주장하지 않음
- Documentation verification: acceptance/model/manifest/policy JSON 근거 대조 PASS, HTML5 parse
  error·중복 ID 0, 필수 section 10개 확인, 로컬 HTTP 200, whitespace diff PASS. Browser visual
  QA는 연결 가능한 browser runtime이 없어 이번 세션에서 수행하지 못함
- Git safety: `feature/scenario-poc-hard-plastic`, Base `30297c2`, 현재 변경 미Commit.
  `CSight_MASTER_HANDOFF_2026-08-27.md`와 `kaputt_best_vision_architecture.md`는 제외

### 2026-08-27 — HDP-100 Scenario PoC Final Regression and Live Recovery

- Root cause: parallel Text/Vision completion transactions at PostgreSQL `READ COMMITTED` each
  observed its own terminal Stage and the peer's uncommitted `RUNNING` Stage, so neither closed the
  parent Run. Tenant/case-scoped parent `FOR UPDATE` locking now serializes claim, completion,
  retry/failure, exhaustion, and Outbox terminal-failure joins.
- Recovery: terminal Stage redelivery now reconciles an orphan `RUNNING` parent without creating a
  second Result. The previously reproduced Run `e5d01e06-5f93-44b5-959e-1c18da81eb71` recovered
  through an actual worker `NOOP` delivery to `SUCCEEDED`, with Result/Assessment/Detection 1/1/0.
- Fresh live path: Run `18451c65-ec11-4beb-a814-a52f695f8505` completed Text and Mock binary Vision
  in parallel as `SUCCEEDED`. It persisted exactly one image assessment, no localized Detection,
  threshold 0.8984375 and deterministic synthetic score 0.965449; normal classification and
  automatic Decision remained false.
- Regression: Ruff PASS, Format 365, Pyright 0; Default 585 passed/65 deselected; disposable
  Integration 54 passed/5 external-vLLM GPU skipped/591 deselected with leftover DB 0.
- Frontend: lint, TypeScript, generated OpenAPI sync and production build PASS; Vitest 9 and
  Playwright intercepted-fixture scenarios 5 PASS.
- Runtime: latest backend/web images rebuilt, PostgreSQL Head `0015`, seven services healthy,
  eight application queues consumer 1/depth 0, five synthetic demo Cases seeded idempotently.
- Verdict: `SCENARIO_TECH_POC_READY` with `MOCK_CONTRACT_ONLY_NOT_E3_INFERENCE`. Actual E3 remains
  `RUNTIME_VISION_INTEGRATION_BLOCKED` until the Vision owner supplies the checkpoint package,
  immutable identity and private serving endpoint.
- Git safety: user-owned root documents remain unmodified and excluded; feature Commit and remote
  branch backup are the next closeout action, with no PR or `develop` merge.

### 2026-08-28 — HDP-100 Final Reverification Closeout

- Backend static: Ruff PASS, Format 365 files, Pyright 0.
- Backend regression: default 603 passed/65 deselected; disposable PostgreSQL Integration 54
  passed/5 external-GPU skipped/609 deselected, leftover DB 0.
- Frontend: lint, typecheck, generated OpenAPI sync and production build PASS; Vitest 10 and
  Playwright intercepted-fixture scenarios 5 PASS. 이 수치는 다섯 시나리오 모두의 live causal
  E2E를 뜻하지 않는다.
- Scenario pack: offline acceptance 9/9, canonical pack hash
  `6be7ad00ba4b92bd99fbcb0ab6c7b9163e387aa8ccd734751c479a2352c24ef1`.
- Live Mock binary path: Run `fc249b72-92b4-4160-adee-2c9b0b66b092` `SUCCEEDED`, score
  0.961864, threshold 0.8984375, localized Detection 0, automatic Decision false.
- Runtime: PostgreSQL Head `0015`, seven services healthy, eight application queues consumer
  1/depth 0, API·Web·상태 HTML HTTP 200.
- External boundary: 실제 E3 endpoint, checkpoint package와 endpoint reference가 없고 runtime
  probe도 실행하지 않아 `RUNTIME_VISION_INTEGRATION_BLOCKED`를 유지한다.
- Git safety: HDP-100 기능 Commit과 원격 기능 브랜치 백업은 아직 `NOT_RUN`이다. 사용자 소유
  `CSight_MASTER_HANDOFF_2026-08-27.md`와 `kaputt_best_vision_architecture.md`는 수정·삭제·Stage하지
  않았다.

### 2026-08-28 — HDP-100 Feature Commit and Remote Backup

- Commit: `dfd6db2ab2052c4ce9a7f922d682c8e574abb05d feat: add hard-plastic scenario PoC`.
- Branch: local `feature/scenario-poc-hard-plastic`와
  `origin/feature/scenario-poc-hard-plastic`가 동일 SHA임을 확인했다.
- Governance boundary: PR 생성과 `develop` 병합은 실행하지 않았다.
- Documentation boundary: 이 상태 문서 갱신 자체의 Commit SHA는 아직 없으므로 기록하지 않는다.
- Git safety: 사용자 소유 `CSight_MASTER_HANDOFF_2026-08-27.md`와
  `kaputt_best_vision_architecture.md`는 수정·삭제·Stage하지 않았다.

### 2026-08-28 — Real E3 Host Runtime and Synthetic Core Integration

- 목표: 담당자가 전달한 E1–E3 weights/README/SHA를 검증하고 canonical E3만 선택해 오늘의
  HDP-100 합성 기술 PoC에 실제 checkpoint forward를 연결
- Weight integrity: 세 checkpoint의 제공 SHA-256과 재계산값이 모두 일치. E3는 원격
  canonical manifest의 size 264,918,248와 SHA
  `49e8a64c08f293058262f434d48c463152c1b6b26eb005c61b79ffc95731037e`까지 일치
- Package/runtime: manifest·preprocess·threshold·labels·offline DINOv2 config를 고정하고,
  checkpoint는 Git/Docker 밖의 경로만 허용. unsafe globals 0, `weights_only=True`·mmap,
  exact root/config/tensor count/dtype/finite/strict key를 통과해야만 loopback server가 시작됨
- Direct inference: MPS float32 host runtime health 200. 합성 펌프 connectivity image의 실제 E3
  score 0.5347465873, frozen threshold 0.8984375, 결과
  `BELOW_HIGH_CONFIDENCE_THRESHOLD`, Detection·normal classification·automatic Decision 0
- Core causal path: Docker Worker→host-private endpoint 200. Run
  `893f8927-7c71-4246-936b-5c752493ffc4`가 `SUCCEEDED`로 완료되고 exact model/version/SHA와
  image assessment가 append-only 저장됨
- Failure/recovery: wrong task와 MIME/content mismatch 422, hash drift가 `torch.load` 전 차단,
  symlink 거부. 첫 stop 직후 즉시 health probe는 종료 유예 중 200이어서 재시도 후 closed를
  확인. 첫 setup 재실행은 기존 venv를 거부해 `--allow-existing`으로 수정하고 safe stop→setup→
  restart 뒤 동일 score와 Worker health 200을 재확인. 실제 timeout/malformed-response live
  fault injection은 `NOT_RUN`
- Backend verification: Ruff 0, Format 374, Pyright 0, Default 605 passed/65 deselected,
  disposable Integration 54 passed/5 external-GPU skipped/611 deselected, 임시 DB 0. E3 전용
  package/fail-closed test 5 passed
- Frontend/runtime: lint·typecheck·OpenAPI·build, Vitest 10, intercepted-fixture Playwright 5
  통과. DB Head `0015`, Core 7 services healthy, 8 queues consumer 1/depth 0, API·Web·상태 HTML
  HTTP 200. 브라우저에서 실제 E3 PASS와 product qualification BLOCKED 문구를 직접 확인
- Scope: 실제 checkpoint 연결은 `PASS_WITH_SCOPE`지만 합성 이미지 한 건의 기술 연결일 뿐
  held-out metric 재현, HDP-100 제품 accuracy, 고객 데이터/정책, ROI 증거가 아니다. Kaputt
  권리 범위 때문에 내부 비상업 연구 데모로 제한하고 public/customer/commercial 사용은 차단
- Git: 기존 Scenario 기능·closeout HEAD `5c152fd`는 원격 기능 브랜치와 일치. E3 runtime
  변경은 로컬 미Commit·미Push이며 가중치와 사용자 소유 루트 문서 두 개는 수정·복사·Stage하지 않음
- 다음 작업: HDP-100 5개 대표 합성 이미지·Human Gold·재현 점수를 고정하고 실제
  timeout/recovery와 malformed-response fail-closed를 주입 검증

### 2026-08-28 — Local Demo Admin Identity

- 목표: 상담원 콘솔에서 한 계정으로 일반 검토와 Safety Admin 시나리오를 모두 시연할 수 있도록
  local tenant `csight`와 `csight@csight.demo` 계정 생성
- Persistence: active Tenant 1, active User 1, `ADMIN` Role 1을 한 DB transaction으로 생성;
  비밀번호는 Argon2 hash로만 저장하고 평문은 원장·파일·Git에 기록하지 않음
- Verification: `/api/v1/auth/token` HTTP 200, 발급 Token으로 `/api/v1/auth/me` HTTP 200;
  Principal email과 단일 `ADMIN` Role, tenant user count 1과 account role count 1 확인
- Scope: 현재 loopback local demo 전용. 외부 공개·공유 환경에서는 Credential 교체 또는 계정
  제거가 선행돼야 함
- Git: Runtime DB identity 생성과 상태 원장 갱신만 수행; Commit·Push 없음

### 2026-08-28 — Cloudflare Domain Switch to CSight

- 목표: 개인 지뢰찾기 서버에 사용하던 `doongdoong.org` Cloudflare Tunnel을 현재 CSight 합성
  기술 데모 Web으로 전환
- Routing: root·`www`의 game HTTP `3000`과 `/socket` WebSocket `3001` ingress를 제거하고
  host loopback CSight Web `127.0.0.1:8080`으로 통합; catch-all 404 유지
- Activation: cloudflared ingress validation `OK`, LaunchAgent tunnel process kickstart 성공;
  지뢰찾기 HTTP/WS 서버는 로컬에서 계속 실행되지만 도메인에서는 분리됨
- External verification: root·`www` system-info가 `csight-core-api`, Web health 200; 외부
  `/auth/token`·`/auth/me` 200와 single `ADMIN` Principal 확인, Token cache header no-store/no-cache
- Browser QA: `https://doongdoong.org/login`, title `CSight 상담원 콘솔`, login form DOM과 console
  error 0을 확인하고 사용자에게 보이는 탭으로 인계
- Security boundary: Cloudflare Access 미적용이고 Demo Admin Credential이 짧다. 실제 데이터는
  업로드하지 않으며 외부 공유 전에 Access 또는 Credential 강화가 필요
- Git: Cloudflare local config와 상태 원장만 변경; CSight Commit·Push 없음

### 2026-08-28 — E3 Top-100 Selected-Positive Replay and Core Sample

- 목표: 전달된 E3-correct selected-positive package를 원본 복사 없이 실제 E3와 Core 경로로 재생
- Source integrity: JPEG 100/100의 manifest SHA·decode·2048² RGB·EXIF/ICC 부재를 확인.
  `DEFECT 100 / NORMAL 0`, hard-plastic 14장 모두 major defect이며 package tree SHA는
  `4543f49f9a54a989a694096b89f3be83a47cd1d80c4c46a5e2ab4ff4937cb132`
- Direct E3: exact revision `49e8a64c…1037e`, MPS float32에서 100/100 완료. source threshold
  0.5와 frozen threshold 0.8984375 모두 100/100; score 0.9980715–0.9999757,
  mean 0.9993894, median latency 932 ms
- Core causal sample: 시각 검토 allowlist ranks 003·032·054·058·078·080의
  Case→Evidence→Analysis 6/6 `SUCCEEDED`; Evidence SHA와 direct/Core score delta 0
- Safety audit: 각 Case의 Human Review Task·Resolution Event·Action Intent 0, Resolution GET 404.
  평가기가 Human Decision·Resolution·External Action을 요청하지 않았고 위치 Detection도 0
- Verdict: `TOP100_SELECTED_SUCCESS_REPLAY_AND_CORE_SAMPLE_PASS`; canonical report SHA
  `9400509e18689d6696e303a7f30a803cd1252872d21ff123c28b0b50e1d9d2bf`
- Verification: Ruff 0, Format 376, Pyright 0, 새 focus 9 passed, E3 runtime 5 passed,
  default 612 passed/65 deselected. HTML 구조·local status·external login HTTP와 1324px Browser
  카드/overflow/console 검증 통과; 시각 QA에서 발견한 기존 console-link 세로 배치를 수정. App/API/
  Migration 변경이 없어 disposable Integration 전체 suite는 재실행하지 않고 실제 Core 6건으로 검증
- Claim boundary: positive-only·correct-only 선택 편향 때문에 AP·AUROC·accuracy·recall·정상
  확인·제품 qualification·Limited PoC 승격 근거가 아님. package에 license·annotation provenance·
  공개 재배포 권리가 없고 rank 061에는 개인 이름이 보여 제외; 원본·report는 Git과 공개 Web 밖에 유지
- Git: Commit·Push·PR 없음. 사용자 소유 `CSight_MASTER_HANDOFF_2026-08-27.md`와
  `kaputt_best_vision_architecture.md`는 수정·삭제·Stage하지 않음
- 다음 작업: HDP-100 다섯 대표 이미지·Human Gold 고정, timeout/malformed-response live Gate,
  공개 접속 보호와 데이터 권리 확인

### 2026-08-28 — Realistic 6:4 Internal Demo and Human Review Staging

- 목표: selected-correct 결함만 보이던 기술 재생을 실제 상담 화면에 가까운 10건 구성으로 바꾸고,
  사용자 제공 정상 참고 이미지를 과장 없이 섞어 실제 E3·private Evidence·합성 정책 검토 경로를 확인
- Normal source: JPEG 77장, 2048×2048 RGB, EXIF/ICC·exact duplicate·Top-100 overlap 0. 실제
  E3 77/77이 source 0.5와 frozen 0.8984375 모두 미만이며 score 범위
  0.0000208903–0.0001434958. label 근거는 사용자 진술뿐이고 license·provenance·독립 Gold는 없음
- Frozen 6:4 selection: selected-correct defect ranks 003·032·054·058·078·080과 normal-reference
  ranks 002·008·017·023을 10개 합성 자연어 문의에 연결. 결과는 고신뢰 defect candidate 6,
  threshold 미만 참고 4이며 실제 prevalence·accuracy·normal confirmation이 아님
- Private Evidence: 원본을 Git·Web static에 복사하지 않고 tenant/Case-scoped Evidence API에 저장.
  인증된 same-origin content endpoint가 size/SHA를 fail-closed 재검증했고 최종 replay에서 10/10 일치
- Policy runtime: fictional `csight` corpus 12 Document/84 Clause/84 Qwen3 embedding/ACTIVE index 1,
  Rule/Source link 12/12. local/test와 loopback PostgreSQL/Embedding만 허용하며 existing semantic,
  embedding SHA/vector, exact index metadata가 다르면 자동 수정 없이 실패. 실제 prepare 2회 모두
  bundle/ingestion reuse, embedding created 0
- Live representative flow: `REAL-DEMO-DEFECT-03`과 `REAL-DEMO-NORMAL-01`이 각각 Text v2,
  RAW Top-3 Retrieval, Grounding, Policy Evaluation `SUCCEEDED`와 matching Human Review `PENDING`까지
  완료. E3는 `NOT_LINKED_TO_POLICY_INPUT`; Human Decision·Resolution·Action Intent·Simulation 0
- Idempotency/safety replay: 정책·Review 2건을 만든 뒤 10건 seed를 다시 실행해 Case/Analysis replay
  10, Evidence reuse·authenticated integrity 10, 새 workflow row 0을 확인. workflow before/after는
  Retrieval/Grounding/Policy/Review 각각 2로 동일, canonical report hash
  `8f26ed1ff7f8dca6daf55eee08106651e31ad2fa5cc3ed078cd8070b111cc6b7`
- UI: Bearer-authenticated image Blob preview, source provenance/selection bias/rights badge, E3 score·
  threshold 안전 해석, citation title/body/version, independent run IDs와 Review Packet 원장을 표시.
  최신 FAILED는 이전 성공 결과를 가리지 않고 실패한 Text/Vision branch만 새 key로 재시도
- Verification: Ruff PASS, Format 382, Pyright 0; default 648 passed/65 deselected/36 warnings,
  disposable Integration 54 passed/5 external-GPU skipped/654 deselected and removed; focused E3/demo
  29, E3 runtime 5; Web lint·typecheck·OpenAPI·build, Vitest 32, Playwright fixture 5 PASS
- Runtime/browser: DB Head `0015`, Core 7 services healthy, Qwen embedding 8091과 E3 8093 health PASS,
  Evidence content OpenAPI path 존재·unauthenticated 401. `https://doongdoong.org/login` 새 Web build와
  Login DOM, browser console error 0 확인; rebuild로 기존 browser memory token이 만료되어 로그인 후
  실제 Case 화면 검증은 사용자 세션에서 이어감
- Git safety: Commit·Push·PR 없음. checkpoint·raw image·local reports와 사용자 소유
  `CSight_MASTER_HANDOFF_2026-08-27.md`, `kaputt_best_vision_architecture.md`는 Git 제외
- 다음 작업: 상담원 콘솔에서 대표 2건을 사람이 직접 검토한다. 승인된 Human Decision이 생기기
  전에는 Review Report·Resolution·DRY-RUN을 생성하지 않고, 공개 공유 전 Access/credential과
  데이터 권리 경계를 먼저 보강한다.

### 2026-08-28 — R1 Visual-Aligned Inquiry, Three-Column Console, and Policy 2.0.1

- 목표: 짧고 이미지와 어긋날 수 있던 상담 문구를 실제 이커머스 반품·교환·환불 문의처럼 확장하고,
  상담원이 고객 주장·이미지·가상 사내 정책을 한 화면에서 비교할 수 있는 내부 데모를 완성
- R1 inquiry contract: 결함 후보 6·기준 미만 참고 4의 10건을 각 4~5문장으로 고정하고
  `demo_image_observation`과 `CUSTOMER_STATEMENT_ONLY_FOR_NON_VISIBLE_FACTS`를 분리. 실기업명·
  이메일·전화번호는 manifest validation에서 차단하고 legacy v2 Case는 삭제 없이 UI에서 숨김
- Seed/replay: R1 10 Case/Evidence/실제 E3를 생성한 뒤 같은 입력을 재실행해 Case/Analysis 10 replay,
  Evidence reuse·integrity 10, 신규 workflow row 0을 확인. canonical report hash는
  `6a7b9af27016ea9a88141878cdbadaca71b2e3ea660f9b47c9d944c4f7002dba`
- UI: Case 상세의 최상단을 `문의 내용 / 이미지 근거 / 정책 기반 권고` 3열로 정리하고 가상 문의·
  가상 사내 정책 배지, 사진 관찰/고객 진술 경계, exact E3 binary identity를 표시. 실행 ID·Workflow·
  Resolution은 하단 접이식 보조 영역으로 이동하고 bbox가 섞인 binary 결과는 fail-closed 처리
- Fictional policy: CSight Commerce 운영규정 8 Document·52 Clause와 25 typed Rule·35 Source를
  추가. 기존 포함 전체 20 Document·136 Clause이며 문서·retrieval index는 `2.0.0`, canonical
  Rule Set/Rules는 `2.0.1`로 고정
- Reliability recovery: 최초 v2 `2.0.0`에서 다중 source 순서와 DB 재구성 순서가 달라 immutable
  hash mismatch가 발생한 원인을 확정. production reconstruction과 ingest에 canonical 정렬을 강제하고,
  faulty `2.0.0`·failed Evaluation/Outbox는 삭제 없이 frozen hash가 일치하는 RETIRED 이력으로 보존.
  clean 환경은 v1+2.0.1만 만들며 live DB는 v1/2.0.0 RETIRED, 2.0.1 sole active
- Policy replay: prepare 1회에서 successor Rule 25를 추가하고, 2회째 bundle/ingestion exact reuse와
  insert 0을 확인. 현재 감사 이력 포함 Rule/Source는 62/82, active Rule Set은 1개
- Live representative flow: R1 rank 054 수리, rank 078 Safety, rank 008 단순변심 3건이 각각
  Text v2→RAW Top-3→Grounding→Policy `2.0.1`을 `SUCCEEDED`했고 matching Human Review 3건이
  `PENDING`. Top-3는 모두 `CSC-OPS-* / 2.0.0`; R1 10건의 Decision·Resolution·Intent·Attempt·Result 0
- Verification: Ruff PASS, Format 384, Pyright 0; default 658 passed/65 deselected/36 warnings;
  disposable Integration 54 passed/5 external-GPU skipped/664 deselected/5 warnings and removed;
  policy focus 19; Web lint·typecheck·OpenAPI sync·build, Vitest 39, Playwright fixture 5 PASS
- Runtime/browser at 12:48 KST: Docker 재시작 후 E3·Qwen Embedding MPS와 Core 7 services healthy,
  DB Head `0015`, API live/ready·Web health PASS, Core는 exact E3 remote identity 사용. 공개 Login은
  title/DOM/가로 overflow/console warning·error 0을 확인했고 비밀번호 입력이나 Human Resolve는 하지 않음
- Scope: 10건·정책은 모두 가상이며 E3 score는 policy input과 미연결. selected-correct 6:4와 권리
  미확인 이미지는 제품 성능·실제 분포·상업 PoC 근거가 아니며, Access·강한 Credential·재배포 권리
  확보 전 `doongdoong.org` URL과 계정을 제3자에게 공유하지 않음
- P2: policy input snapshot의 Vision qualification이 미연결 상태에서도 `MOCK_QUALIFIED`이고,
  `case.order_amount`가 generic attributes provenance를 사용한다. 현재 R1 seed에는 금액 입력이 없고
  최종 조치를 만들지 않지만 실제 데이터 전 source-tagged typed schema 보강이 필요
- Git safety: Commit·Push·PR 없음. checkpoint·raw image·local reports와 사용자 소유
  `CSight_MASTER_HANDOFF_2026-08-27.md`, `kaputt_best_vision_architecture.md`는 수정·삭제·Stage하지 않음
- 다음 작업: 대표 Review 3건은 인증된 사람이 실제 판단할 때만 Resolve한다. 외부 공유 전
  Access/Credential과 권리 경계를 보강하고, 제품 적용 전에는 권리 확인된 자체 표본·Human Gold와
  policy input provenance를 별도 qualification한다.

### 2026-08-28 — Consultant-first Workspace UX and Policy Date Recovery

- 목표: 실사용 상담원이 첫 화면에서 다음 행동을 바로 이해하도록 Case Workspace를
  단순화하고, 우측 `이어하기`가 정책 평가에서 반환하던 HTTP 422를 해소
- UX: 상단에 `지금 할 일` 단일 주요 CTA와 문의 접수→사진 확인→정책 검토→
  담당자 결정 4단계를 추가. 본문은 문의·이미지 맥락과 정책 권고의 2열로 재배치하고,
  모델 identity·실행 ID·Resolution은 접은 상세로 유지. 상시 노출되던 기능 없는
  데스크톱 X는 제거하고 모바일 사이드바가 열렸을 때만 닫기 버튼을 표시
- 422 원인: Case `created_at` UTC `2026-08-27`을 문자열로 잘라 정책 기준일로 사용했지만,
  한국 업무일은 `2026-08-28`이었고 active Rule Set `2.0.1`도 그날부터 효력이었음.
  API log와 DB rule 효력일을 조회해 `No active policy rule set is valid for as_of_date` 경로를 확정
- 수정: Web이 Case 시각을 `Asia/Seoul` 업무일로 변환한 후 정책 평가를 요청하고,
  서버의 `{error: {code, message}}` 계약을 클라이언트가 정상 파싱하여 재발 시에도
  포괄적 422 문구 대신 실제 이유를 표시
- 검증: OpenAPI generated snapshot sync, ESLint, TypeScript, production build PASS; Vitest
  14 files/42 tests, Playwright fixture scenario 5 PASS. 13:22 KST Core 7 services healthy,
  API readiness·Web health·외부 tunnel health PASS
- 미실행: rebuild로 브라우저 memory token이 초기화되어 인증된 실제 Case에서
  CTA 수동 클릭은 재로그인 후로 인계. 자동 회귀와 비인증 live health는 통과
- 보안·업무 경계: Policy·Vision은 권고만 제공하고 인증된 사람만 최종 결정.
  이번 세션에서 Decision·Resolution·Action을 생성하지 않음
- Git safety: Commit·Push·PR 없음. 사용자 소유 `CSight_MASTER_HANDOFF_2026-08-27.md`,
  `kaputt_best_vision_architecture.md`는 수정·삭제·Stage하지 않음
- 다음 작업: 사용자가 재로그인한 뒤 기존 422 Case에서 `분석 계속하기`를
  한 번 누르고 Policy `2.0.1` 성공 또는 기존 성공 실행 복구를 확인

### 2026-08-28 — Human-confirmed Quick Review and Automatic Report Flow

- 목표: 담당자가 복잡한 Decision form을 작성하지 않고 `허용/비허용`만 눌러도 검토 확정부터
  Resolution·DRY-RUN·최종 검토 문서까지 이어지는 PoC 기술 흐름 구현
- Decision boundary: 모델·정책·Worker가 Decision을 만들지 않으며 인증된 담당자의 명시적 클릭만
  기존 Human Resolve를 호출. Safety·Manager·Policy Exception은 Reviewer를 차단하고 Admin만 허용
- Readiness Gate: threshold `0.70`. Human Review 상태 0.35 + immutable Rule 0.25 + Citation 0.15 +
  qualification metadata 0.10 + 단일 policy eligibility mapping 0.15. 모델 accuracy나 Vision
  threshold가 아니라 PoC 화면 단순화를 위한 workflow-readiness이며 ADR-0097에 고정
- Allow mapping: `RETURN/REFUND_REVIEW`→`APPROVE_REFUND`, `EXCHANGE_REVIEW`→
  `APPROVE_EXCHANGE`, `RESHIPMENT_REVIEW`→`APPROVE_RESHIPMENT`, `REPAIR_REVIEW`→
  `APPROVE_REPAIR`. 복수·미지원 mapping은 허용을 비활성화하고 상세 검토로 fail-closed
- Deny mapping: Gate를 통과한 담당자의 `비허용`은 `REJECT_REQUEST`. 첫 Rule+Citations를 immutable
  basis로 자동 첨부하고 고정된 투명 rationale을 기록하며 고객 원문·LLM·Vision score로 Action을 추론하지 않음
- Client flow: PENDING/허용 권한 상태에서 한 번의 클릭으로 CAS Claim 후 갱신 version으로 Resolve.
  기존 비동기 Resolution/Simulation worker와 `review_report/1.0.0`을 polling하고 생성 즉시 인쇄 가능한
  보고서 화면을 자동으로 열며 별도 server Workflow Coordinator나 mutation API는 추가하지 않음
- UX: 우측 Decision Panel의 주 동작을 큰 `허용/비허용` 두 버튼과 준비도 meter로 단순화.
  상세 Decision·자료 요청·이관·반환은 접힌 예외 경로로 유지하고 버튼 클릭 시 immutable 최종 결정임을 명시
- Verification: OpenAPI sync, ESLint, TypeScript, production build PASS; Vitest 15 files/45 tests,
  Playwright fixture 5 PASS. 첫 시나리오는 Claim expected v1→Resolve v2, `APPROVE_REPAIR`,
  Rule+Citation, Report 자동 navigation과 side effects 0을 검증
- Runtime/browser: 13:50 KST Web rebuild, Core 7 services healthy, API ready·Web·외부 tunnel
  health PASS. 공개 Login title/DOM과 console warning/error 0; 비밀번호 입력이나 실제 Human Resolve는 미실행
- Scope: `0.70`을 성능·정확도·위험 확률·Limited PoC 증거로 주장하지 않음. 실제 상담원 clickstream과
  Shadow Gold 전에는 합성 데모용이며 LIVE 외부 실행과 Case Closure는 계속 없음
- Git safety: Commit·Push·PR 없음. 사용자 소유 `CSight_MASTER_HANDOFF_2026-08-27.md`,
  `kaputt_best_vision_architecture.md`는 수정·삭제·Stage하지 않음
- 다음 작업: 인증 담당자가 비Safety 대표 Case 하나의 정책/근거를 확인한 뒤 실제 `허용` 또는
  `비허용`을 선택하고 생성된 immutable Decision·Resolution·Report를 확인

### 2026-08-28 — Reference-informed Refund Processing Confirmation

- 목표: Human Decision 이후 생성되는 환불 보고서를 실제 이커머스 운영자가 읽는 환불 처리 문서와
  유사한 구조로 개선하되, 특정 기업 서식 복제와 실제 환불 완료 오인을 방지
- Reference: Shopify 공식 환불 안내의 금액·수량·배송비·사유·환불수단·고객 통지·timeline,
  Stripe 공식 환불 안내의 원결제수단·pending/succeeded/failed lifecycle, 국내 전자상거래법
  제18조의 환급·결제업자 취소 요청 관점을 공통 필드로 채택. 상세 근거와 경계는
  `docs/resolution/REFUND_PROCESSING_CONFIRMATION.md`에 기록
- 구현: `APPROVE_REFUND` 또는 `REFUND` Intent를 감지해 `환불 처리 확인서`로 렌더링. 문서번호,
  주문/SKU, 금액·통화·수량, 승인 근거, 취소 요청·통지·RMA/추적, 처리 이력, 정책/담당자 승인,
  Report/Packet/Decision/Intent/Result 감사 ID·Hash를 화면과 A4 인쇄에 구성
- Fail-closed: snapshot에 없는 값은 추정하지 않으며 금액·통화 누락은 `입력 필요`와
  `환불 정보 보완 필요`로 표시. 외부 결제/회수/통지 식별자는 `미요청/미발송/미연동`,
  `side_effects_performed=false`는 `실제 환불 미실행`으로 고정
- Verification: TypeScript·ESLint·production build PASS; Vitest 17 files/49 tests,
  Playwright 다섯 fixture scenario PASS. 1440px full-page 캡처로 데스크톱 문서 밀도·표·timeline·
  감사 footer를 직접 확인. 신규 환불 문서는 backend 계약 변경 없이 immutable report snapshot만 사용
- Runtime/data: Web/API 이미지를 재빌드해 현재 데모에 반영. 14:04 KST DB Head `0015`, Core 7
  services healthy, API ready와 local/public Login HTTP 200. 실제 인증 Human Decision과 외부 환불은 실행하지 않음
- Git safety: Commit·Push·PR 없음. 사용자 소유 `CSight_MASTER_HANDOFF_2026-08-27.md`,
  `kaputt_best_vision_architecture.md`와 새 미추적 개인 자료를 수정·삭제·Stage하지 않음
- 다음 작업: 인증 담당자가 명시적으로 환불을 허용한 complete refund Case에서 18,900 KRW 같은
  제출 입력이 문서에 표시되고 DRY-RUN 결과/실제 부작용 없음이 고정되는지 live UI로 확인

### 2026-08-28 — GitHub PoC, MVP, and Release Branch Audit

- 목표: `CSightICT/csight-core`에 PoC·MVP·최종 단계용 branch가 실제로 존재하는지 확인하고
  현재 로컬 구현과 원격 저장 상태의 차이를 확정
- 원격: private repository, default `main`, 총 7 branches. 명시적 `poc`, `mvp`, `final`,
  `release/*` branch와 tag는 없음. 경량 GitFlow 문서상 장기 branch는 `main/develop`만 유지
- Stage mapping: 현재 PoC 작업선은 `feature/scenario-poc-hard-plastic@5c152fd`, 다음 MVP 통합
  후보는 `develop@4037d73`, 최종 릴리스 기준은 `main@4037d73`. PoC는 main/develop보다
  21 commits ahead, Sprint 5C branch보다 2 commits ahead이고 뒤처짐 0
- CI/PR: PoC head push CI success. Governance PR #2는 open, Vision PR #4는 Draft/open이며
  `feature/3-kaputt-dinov2-training@3e2d596` latest push/PR CI success. PoC branch PR은 없음
- Divergence: Vision branch와 PoC branch는 `4037d73`에서 갈라져 Vision-only 55 commits,
  PoC-only 21 commits. 자동 fast-forward나 무검토 직접 merge 대상이 아님
- Local gap: local HEAD는 remote PoC와 같지만 후속 구현이 tracked 44 files, untracked 36 paths로
  남아 있음. E3 runtime, replay/demo/policy, 상담원 UX, 422/quick review/refund document가 원격 미반영
- 판정: GitHub 최신화 필요. 그러나 `main/develop` 직접 Push나 영구 `mvp/final` branch 생성이
  아니라 변경을 논리 단위로 분리 검증한 PoC backup→PR to `develop`→release/tag→`main` 순서가 맞음
- 실행: GitHub/로컬 read-only 감사와 이 원장 갱신만 수행. Commit·Push·branch 생성·PR 수정·병합 없음
- 다음 작업: 사용자 소유 자료를 제외한 Commit 후보 목록을 먼저 확정하고, 전체 회귀 뒤 사용자의
  명시적 승인으로 PoC branch backup을 갱신한다. 이후 Vision PR #4 통합 순서를 별도 결정

### 2026-08-28 — Realistic PoC Safe Commit Preparation

- 목표: 원격보다 앞선 E3 runtime·현실형 데모·가상 정책·상담원 UI를 사용자 소유 자료와 분리해
  검토 가능한 PoC Commit으로 고정하고 fast-forward 원격 백업 전 안전 Gate를 재확인
- Commit: E3/backend/policy/scenario `0f4de4b feat: add E3-backed realistic demo runtime`,
  상담원 UI/빠른 검토/환불 문서 `b3e09cf feat(web): streamline consultant review and refund reports`.
  이 원장을 포함한 상태 문서 Commit과 원격 Push는 아직 미실행
- 전체 검증: Ruff PASS, Format 384, Pyright 0; 기본 658 PASS/65 deselected,
  disposable Integration 54 PASS/외부 GPU 5 Skip/664 deselected 후 DB 정리, Vision E3 5 PASS.
  Web lint·typecheck·OpenAPI sync·production build, Vitest 17 files/49 tests, Playwright 5 PASS
- Data/runtime 검증: 합성 Scenario acceptance 9/9, 정책 DB 24 Document/168 Clause와 mismatch 0,
  Rule Set 2/Rule 24/forbidden decision effect 0. DB Head `0015`, Alembic drift 없음,
  Core 7 services healthy, API ready·local Web·public Login HTTP 200
- 승격 판정: `make verify-poc-readiness`는 정상 종료했지만 외부 증거 Gate가 비어 있어
  `SYNTHETIC_MOCK_SIMULATION_DEMO`를 유지. 실제 기업 데이터·정책·ROI·제품 Vision qualification을
  확보했다는 주장으로 승격하지 않음
- Git safety: 후보에서 Secret·5 MiB 초과 파일·가중치·checkpoint·원본 이미지 0. 사용자 소유
  `CSight_MASTER_HANDOFF_2026-08-27.md`, `kaputt_best_vision_architecture.md`,
  `ecommerce_vibe_coding_cs_automation_market_research.md`는 수정·삭제·Stage하지 않고 미추적 보존
- 미실행: 인증 Human Decision 클릭, 실제 외부 환불, PR 생성, `develop/main` 병합, 원격 Push·CI
- 다음 작업: 상태 문서 Commit 뒤 원격 PoC가 기존 `5c152fd`인지 다시 확인하고 fast-forward Push,
  GitHub Actions 성공을 관측한 후 정확한 원격 SHA와 Run을 이 원장에 추가

### 2026-08-28 — Realistic PoC Remote Backup and CI Closeout

- 목표: 검증·분리한 세 Commit을 현재 PoC 작업선에만 안전하게 백업하고 원격 회귀 결과를 확정
- 원격 경합 확인: Push 직전 `origin/feature/scenario-poc-hard-plastic`가 감사 기준 `5c152fd`와
  동일하고 local이 정확히 3 commits ahead임을 fetch로 재확인
- 범위 감사: 115 changed files, 금지된 image/checkpoint/archive 확장자 0, 5 MiB 초과 blob 0,
  고신뢰 Secret pattern 0. 사용자 소유 미추적 문서 3개는 staging과 Commit 범위 밖에 유지
- Push: `5c152fd..81b6e20` fast-forward. `develop`, `main`, Vision branch, PR, tag, release는 변경하지 않음
- GitHub CI: Run #108, head `81b6e207e1a593c2f3f3f44cc2fde441a49498c1`, conclusion `success`.
  `Quality and fast tests`와 `Consultant console` 두 Job 모두 PASS
- 판정: 최신 현실형 내부 기술 데모 변경은 원격 PoC에 백업 완료. 합성 정책·선별 이미지·제품
  qualification 미완료 경계와 Human-only final decision은 그대로 유지
- 다음 작업: 이 closeout 원장 Commit의 최종 CI를 확인한 뒤, Vision Draft PR #4와의 충돌 검토 및
  거버넌스 승인 전에는 PoC PR·`develop/main` 통합을 실행하지 않음

### 2026-08-28 — Fictional Product and Price Scenario Catalog

- 목표: 현재 R1 사진 10건이 기술용 `product_ref` 대신 실제 이커머스 상담처럼 읽히도록
  가상 상품명·SKU·가격대·문의 목적을 연결하되 실제 상품/가격 추론과 Action 입력을 분리
- 비용 절감: 저비용·낮은 추론 서브에이전트는 기존 manifest 감사와 초안만 수행. 최종 매핑은
  현재 10장 contact sheet와 source rank를 직접 대조하고 코드/안전 검증은 주 작업에서 수행
- 구현: `web/src/demo/productScenarioCatalog.ts`에 6 defect candidate·4 below-threshold reference
  카탈로그를 고정. 목록은 상품명 검색과 상품명·가상 SKU·가격대를 표시하고 상세는 가상 상품 배지,
  상품군·문의 목적·`실제 판매가/환불 금액 아님` 경계를 표시
- 안전 경계: 가격 basis는 `SYNTHETIC_DEMO_CATALOG_NOT_MARKET_RESEARCH`. representative price를
  External Action 입력으로 사용하지 않으며 미매칭 Case는 기존 `product_ref`만 표시. 기준 미만 사진을
  정상으로 확정하거나 실제 SKU·브랜드·판매가를 식별하지 않음
- 문서: 현실형 v2 README에 10건 상품/가격 표와 표시·검색·비추론 계약을 추가
- 검증: Web lint·typecheck·OpenAPI sync·production build PASS, Vitest 18 files/52 tests,
  Playwright 5 PASS, `git diff --check` PASS. Web 재빌드 후 Core 7 healthy, API ready·Web health·
  public Login HTTP 200, 새 Login DOM과 console warning/error 0
- 미실행: 브라우저에 Credential을 다시 입력하지 않아 인증 Case 상세 수동 확인과 Human Decision은
  미실행. 추가 사진 후보를 active catalog에 넣거나 원본 이미지를 Git/Web static으로 복사하지 않음
- Git: 변경은 로컬 미Commit·미Push. 사용자 소유 미추적 문서 3개는 수정·삭제·Stage하지 않음
- 다음 작업: 사용자가 로그인한 Case 상세에서 상품 카드가 사진/문의와 함께 보이는지 확인하고,
  추가 사진은 PII/브랜드/바코드·권리·SHA·E3 outcome 검토 후 별도 catalog version으로 확장

### 2026-08-28 — Synthetic Commerce Context and Refund Document R2

- 목표: PoC Case와 환불 확인서를 실제 이커머스 운영처럼 읽히게 하되 합성 고객/거래 문맥과
  External Action 입력을 분리
- 계약: `synthetic_commerce_context/1.0.0`을 Case JSONB 예약 속성으로 추가. 고객 ID·이름·멤버십,
  마스킹 전화/결제수단/운송장, 상품·판매자·결제 합계, `데모/가상` 배송지만 허용하고 금액 합계와
  timezone을 검증. ADR-0098에 display-only/비추론 경계를 고정
- 구현: Case 목록에 고객명·ID·결제금액, 상세에 고객/주문/배송 카드, 새 terminal Report에 검증된
  Commerce allowlist snapshot과 `direct_contact_values_included=false`를 저장. 환불 확인서는 원 결제액,
  명시 환불액, 마스킹 결제수단, 고객/수령인/배송지를 분리 표시
- DB/E3: 첫 `COMMERCE_CONTEXT_R2` 시도는 Core가 Mock 설정이라 첫 Case의 provider identity에서 즉시
  중단했고 Decision/Action 0. 해당 진단 Case는 append-only 보존하되 목록에서 제외. Core를 Remote E3로
  복구한 `COMMERCE_CONTEXT_R2_E3`은 10 Case·10 Evidence·10 actual E3 Analysis를 신규 생성하고 모두
  `SUCCEEDED`; Policy/Review/Decision/Action 신규 행 0. 같은 시드 재실행은 Case·Evidence·Analysis
  10/10을 재사용하고 Private Evidence 무결성을 다시 확인
- 금액 검증: R2 10건 모두 Commerce snapshot 존재. REFUND 2건은 결제금액/명시 환불액이 각각
  18,900/18,900원, 15,900/15,900원. 결제금액에서 Action parameter를 추론하는 경로는 없음
- 회귀: Ruff·Format 386·Pyright 0, 기본 664 PASS/65 deselected, 격리 Human Review→Resolution→Report
  통합 1 PASS와 임시 DB 정리. Web lint·typecheck·OpenAPI sync·build, Vitest 19 files/55 tests,
  Playwright 5 PASS
- Runtime: 15:38 KST Core 7 healthy, API ready·Web health·public Login HTTP 200, API/Worker/Dispatcher
  `VISION_PROVIDER=remote`와 E3 model/task identity 확인
- 미실행: 인증 Human Decision 클릭, 실제 외부 환불/통지/회수, 기존 immutable Report 소급 변경,
  Commit·Push·PR. 기존 사용자 소유 미추적 문서 3개는 보존
- 다음 작업: 로그인한 사용자가 R2 환불 Case `...002` 또는 `...010`에서 정책 흐름을 진행하고 명시적
  허용/비허용을 선택한 뒤, 새 immutable 환불 확인서에 고객·결제·배송 스냅샷이 표시되는지 확인

### 2026-08-28 — Natural Business UI, Customer Communication, and Tenant Data Assets

- 목표: 내부 enum을 상담원이 읽는 자연어로 바꾸고, 최종 처리 뒤 고객 안내 메일이 어떻게 보이는지
  실제 발송 없이 시연하며, 향후 drift 기준선을 위한 고객사 소유 데이터 축적 경로를 추가
- UI: `APPROVE_REFUND`, `ACTION_NEEDS_INPUT` 같은 코드는 `환불 승인`, `처리 정보 보완 필요`를
  주 라벨로 표시. 상세 결정 select·완료 요약·Resolution·환불 확인서에도 같은 업무 용어를 적용
- Communication: terminal `review_report/1.0.0`만 근거로 immutable EMAIL simulation v1.1을 생성.
  환불 검증 완료·입력 보완·검증 실패를 구분한 제목/본문을 만들고 `SIMULATED_NOT_SENT`,
  `side_effects_performed=false`를 DB check와 UI에 고정. 기존 v1.0 기록도 append-only 조회 호환
- Data asset: `case_learning_asset/1.0.0`을 terminal Report 생성 transaction에 자동 적재. 상품/요청,
  사람 결정, Resolution/Simulation 결과, 모델·정책·pipeline 버전만 allowlist하고 고객 원문·직접
  연락처·주소·담당자 rationale는 제외. 기존 Report는 Migration에서 같은 계약으로 소급 적재
- Drift Gate: tenant별 30건 전 `기준 데이터 수집 중`, 30~59건 `비교 데이터 수집 중`, 60건부터
  `드리프트 점검 준비 완료`. 현재 `csight` 6건으로 수치 판단을 보류하고 분포·버전 현황만 표시
- DB/API: additive `20260828_0016_communication_learning_assets`, Communication POST/GET와
  `/api/v1/data-assets/summary` no-store tenant API. 현재 DB Head `0016`, 기존 Report 9건 중 무결성
  정상 9건을 전체 tenant asset으로 backfill했고 `csight` 조회는 6건
- 검증: Ruff·Format 313·Pyright 0, 기본 672 PASS/59 deselected·6 external Skip, disposable
  PostgreSQL Migration 2 PASS/DB 제거. Web TypeScript·ESLint·OpenAPI sync·production build,
  Vitest 21 files/57 tests PASS. 배포 Login DOM·button 확인
- Runtime: 16:02 KST API/Worker/Dispatcher/Web healthy, PostgreSQL/RabbitMQ/MinIO ready. Core의
  Remote E3 model/revision/threshold identity를 rebuild 뒤에도 확인. live mail v1.1 생성·v1.0/v1.1
  재조회, 모든 상태 `SIMULATED_NOT_SENT`, side effects 0
- 미실행: 실제 SMTP, 외부 고객 통지, 환불/결제 취소, 새 Human Decision, Commit·Push·PR.
  사용자 소유 미추적 문서 3개는 수정·삭제·Stage하지 않음
- 다음 작업: 사용자가 새 R2 환불 Case를 사람 판단으로 처리한 뒤 새 환불 확인서와 안내 메일을
  함께 확인하고, 표본 30건 도달 시 allowlist 누락·분포·버전 기준선을 사람 승인으로 고정

### 2026-08-28 — Runtime Memory Ready Baseline

- 목표: 현재 로컬 PoC가 차지하는 메모리를 Docker Core와 host MPS 모델 서비스로 분리해 운영
  기준점으로 고정
- 측정: 16:28 KST, 호스트 32 GiB. Vision E3 physical footprint 1,570 MiB, Embedding endpoint와
  helper 1,732.5 MiB, Docker Core 7개 961.95 MiB, Cloudflare tunnel 48.42 MiB
- 합계: CSight 귀속 약 4,312.87 MiB/4.21 GiB, 호스트의 약 13.16%. Vision·Embedding 두 모델이
  76.6%, Docker Core가 22.3%, tunnel이 1.1%
- Docker 상세: Worker 258.7, MinIO 153.2, PostgreSQL 149.3, API 141.9, RabbitMQ 131.9,
  Dispatcher 117.8, Web 9.152 MiB
- 상태: Core 7개, Vision E3, Embedding healthy. Reranker·Local LLM은 미실행이라 0 MiB.
  memory-pressure 여유 지표 80%, 측정 시 swap-in/out 0
- 경계: idle/ready 단일 시점이며 모델은 MPS physical footprint, Docker는 cgroup, 작은 host
  process는 RSS를 사용했다. 공유 page/cache와 Docker VM accounting 때문에 시스템 전체 resident
  memory와 정확히 일치하지 않음
- 문서: `docs/progress/MEMORY_USAGE_BASELINE.md`에 측정 계약, 모듈별 표, 개별 peak와 다음 부하
  측정 순서를 기록
- 검증: 두 모델 health, Core 7 healthy, 산술 합계·비중 재계산, `git diff --check` PASS
- 미실행: 대표 10 Case 연속 부하, 동시 사용자, queue backlog, Reranker·Local LLM 추가 적재,
  Commit·Push·PR
- 다음 작업: 대표 10 Case 처리 중 5초 간격 current/peak와 queue depth·실패율을 함께 기록해
  p95/peak 운영 기준점을 append-only로 추가

### 2026-08-28 — Kaputt Source Recovery and Qwen3.8 VLM Sample Qualification

- 목표: 4090 Node에 이미 받은 Kaputt 원본을 재사용하고, 기존 text-only Qwen 경계를 보존한 채
  경질 플라스틱 상품 메타데이터의 offline 후보 라벨링·구조화 가능성을 확인
- Source: `/home/data/datasets/kaputt/extracted`에 Query 이미지 100,267장이 Parquet 행과 정확히
  일치. `plastic_hard`는 10,095건이며 defect 1,323·negative 8,772. Reference image/crop/mask는
  parent의 공식 archive에는 있으나 전량 추출되지 않음
- 구현: 별도 `csight-qwen3.8-27b-vlm` compose, strict JSON schema·deterministic balanced sampling·
  source SHA/model+prompt+preprocess provenance·append-only success/failure 기록 Script, ADR-0099와
  data contract 문서 추가. 실패 기록은 보존하되 성공 전에는 재시도할 수 있게 수정
- Runtime: pinned native VLM을 RTX 4090에 별도 private port로 적재. 첫 0.98 reservation은 가용
  VRAM 경계에서 fail-closed하여 0.95로 낮췄고, 이후 healthy. 기존 ADR-0012 text-only endpoint와
  Core provider는 변경하지 않음
- 표본: prompt 1.2.0으로 test의 defect 2·negative 2를 처리해 4/4 schema success, 9.3–10.8초/건,
  generic-only·중복 defect 0·민감 패턴 0. 사람 점검에서 사탕 용기 1건만 유용했고 머핀 트레이·
  바디케어 용기·접착제 용기 3건은 `UNCERTAIN`; defect-positive 두 건도 기준 비교 없이는 보류
- 판정: Pipeline 기술 검증은 PASS, label quality는 `QUALIFIED_WITH_LIMITATIONS`. 전체 10,095건
  Batch를 실행하지 않고 paired Reference 30건 Human spot-check를 다음 Gate로 설정
- 보존/정리: private derived JSONL SHA-256
  `390f7d32a1b9a689d4071c59d2e8c0493851c7ea5ea3659f9af7ab58913b0d57`; 전용 VLM Container를
  exit 0으로 중지해 GPU 22,365 MiB에서 95 MiB로 회수. 최초 탐색 중 받은 중복 sample 1.1 GiB는
  `/home/user/csight-kaputt-vlm/kdd-5305ccf`에 남겼으며 삭제는 사용자 승인 전 미실행
- 검증: targeted Ruff·Format PASS, Pyright 0, pytest 4 PASS, compose/runtime health·model identity,
  output schema/민감 패턴/사람 이미지 점검 PASS. 전체 Backend/Web 회귀는 이번 독립 offline 도구
  변경에서 재실행하지 않음
- Git safety: Commit·Push·PR 없음. 사용자 소유 미추적 문서 3개는 수정·삭제·Stage하지 않음
- 다음 작업: 공식 Reference archive에서 위 30건의 대응 image/crop만 선택 추출하고 Query↔Reference
  pair manifest를 만든 뒤 Qwen 결과를 사람 검수해 full-batch 실행 여부를 결정

### 2026-08-28 — Qwen Query+Reference Images and Comparison Prompt Correction

- 정정: 직전 실행도 Query 사진+Prompt를 함께 보냈지만 기준 사진이 없었다. 사용자 지적에 따라
  입력 계약을 Query Crop 1장+동일 `item_identifier` Reference Crop 1장+역할이 명시된 비교 Prompt로
  수정하고 schema를 `kaputt_vlm_enrichment/2.0.0`, prompt를 `2.0.1`로 갱신
- Data: 공식 31.6 GiB Query Crop과 41.6 GiB Reference Crop archive 전체를 풀지 않고 test 표본에
  필요한 각 4장만 선택 추출. Query/Reference 상대경로·SHA·preprocess와 full Query context 경로를
  append-only 결과에 보존
- Runtime: 별도 VLM의 prompt당 image 제한을 1→2로 변경하고 pinned model/revision은 유지. 기존
  Core text-only Qwen·E3·DB·Human Review는 변경하지 않음
- 실행: defect 2·negative 2 paired 표본 4/4 strict schema success, 9.6–12.0초/쌍,
  `QUERY_PLUS_REFERENCE` 4/4, 민감 패턴 0. 결과 SHA-256
  `159f5ded7eb9559d5b322ca9d24d48cfc117ed4c94a922f89c7145cb8bac3811`
- 품질 판정: 상품 유형 유용성 1/4, 공식 defect-positive 탐지 0/2로 FAIL. 사진+Prompt 전달 경로는
  동작하지만 Qwen3.8 generic VLM을 Kaputt defect labeler나 E3 대체로 사용하지 않음. 공식 Label은
  Ground Truth, E3는 결함 Vision, Qwen은 선택적 상품 설명 후보로 분리
- 자원: private derived JSONL을 보존하고 전용 Container exit 0, GPU 95 MiB로 회수
- 검증: targeted Ruff·Format PASS, Pyright 0, pytest 5 PASS, Compose config PASS, live paired
  4건·schema/provenance/민감 패턴·사람 이미지 대조. 전체 Backend/Web 회귀는 미실행
- Git safety: Commit·Push·PR 없음. 사용자 소유 미추적 문서 3개는 수정·삭제·Stage하지 않음
- 다음 작업: 상품 메타데이터가 필요하면 사람이 일반 상품 유형을 붙인 paired 30건에서 Qwen 보조
  유용성을 따로 평가하고, 결함 Target은 공식 Label/E3에 고정

### 2026-08-28 — Qwen3.8 Paired VLM Runtime Restart

- 사용자 지시로 전용 `csight-kaputt-vlm-qwen38-vlm-1` Container를 다시 시작
- 18:42 KST health `healthy`, 인증 `/v1/models` HTTP 200, served identity
  `csight-qwen3.8-27b-vlm` 확인
- RTX 4090 24,564 MiB 중 21,511 MiB 사용, idle utilization 0%, 39°C
- Query Crop+Reference Crop+Prompt용 image 2개 계약과 private Tailscale bind `:18001` 유지
- 실제 추가 Batch·DB/API 변경·Commit·Push·PR은 실행하지 않음. 품질 Gate FAIL과 공식 Label/E3
  경계는 그대로 유지
- 다음 작업: 승인된 소량 paired metadata 작업만 실행하고, full 10,095건 Batch는 별도 품질 승인 전 금지

### 2026-08-28 — Kaputt Paired 30 Qualification and Product Metadata Split

- 범위: 사용자 `진행해` 지시에 따라 full 10,095건 대신 deterministic paired 30건을 defect 15·
  negative 15로 고정. 기존 4쌍 재사용 후 Query Crop 26장·Reference Crop 24장만 공식 archive에서
  선택 추출해 Query 30/30·unique Reference 28/28 준비
- 결함 task: Query Crop+same-item Reference Crop+prompt 30/30 schema success, 실패 0. 그러나
  `UNCERTAIN` 26, `NO_VISIBLE_DEFECT` 2, `VISIBLE_DEFECT` 2. 공식 label 대비 TP/FP/TN/FN
  0/2/0/2, positive/negative abstain 각 13, coverage 13.3%로 품질 FAIL
- 결함 판정: detached pump를 관찰하고도 no-defect로 냈고 정상 보충제 용기 두 건은 viewpoint를
  deformation으로 오판. prompt의 관점 차이 금지에도 generic Qwen VLM은 E3/공식 label 대체 불가
- Product 분리: `kaputt_product_metadata/1.0.0`에는 name/category/form/use/usability/evidence만 두고
  condition·defect·price·refund·brand/SKU·business action을 제거. official defect label은 provenance에만
  보존하고 prompt 입력에서 제외
- Product 결과: 30/30 strict schema success·실패 0, specific generic name 25·uncertain 5,
  generic-only/paired 30, 금지 필드·email/phone/currency/long-number 0. latency min 7.4초, p50 8.5초,
  p95 10.0초, max 10.0초
- Visual QA: 임시 5x6 Contact Sheet로 이름 후보를 대조. 머핀 팬·로션·접착제·샴푸/세정 용기 등은
  유용한 후보였으나 supplement/cleaning-chemical/pet-care enum 부재로 category mismatch가 존재.
  25/30은 specificity이며 Human Gold accuracy가 아님
- Artifact: defect result SHA `e53a516b8ffb5400def2f490f3376716e18d89e2029670e6782a14f408deb2a6`,
  product result SHA `7ddc9197c957f9e81b5560476a789f06d555e346ff8dc0df734c076abfef846a`를 private
  `/home/data/datasets/kaputt/derived/csight-qwen38/`에 append-only 보존
- 검증: targeted Ruff·Format PASS, Pyright 0, pytest 6 PASS, remote Pydantic 30/30 재검증,
  provenance/task/금지 필드/민감 패턴/Contact Sheet 확인. 전체 Backend/Web 회귀는 미실행
- Runtime: 19:34 KST VLM healthy, GPU 22,731/24,564 MiB, idle 0%, 40°C. 사용자 재기동 지시에
  따라 Container를 중지하지 않고 유지
- Git safety: Commit·Push·PR·현재 PoC Catalog 자동 반영 없음. 사용자 소유 미추적 문서 3개 보존
- 다음 작업: 사람이 30건 product name/category Gold를 확정하고 taxonomy를 승인한 뒤 accuracy를
  계산하며, full Batch 또는 PoC Catalog 반영은 그 이후 별도 결정

### 2026-08-28 — Curated PoC Closed-set v1

- 목표: PoC/MVP 시연 범위를 열린 상품·결함 추론 대신 승인된 상품군 4개·결함군 3개와 점수
  구간으로 고정하고, 해당 조건을 통과한 데이터만 내부 데모에 채택
- 계약: `poc_closed_set/1.0.0`, 상품군은 뷰티·개인관리/식품·건강보조제/생활화학·접착제/
  주방·수납, 결함군은 개봉·분해/변형·파손/표면 손상·누액. E3 runtime threshold
  `0.8984375`는 유지하고 선별 margin만 defect `>=0.95`, reference `<=0.10`으로 설정
- 구현: `app/platform/poc_demo_selection.py`의 기술 독립 registry validator와 admission Gate,
  `evaluation/poc_closed_set_v1/registry.json` 10건 SHA Allowlist, v2 seed source identity·원천 label·
  E3 결과 fail-closed, seed report의 class/admission provenance를 추가
- UI: Case 상세 가상 상품 카드에 `PoC 상품군`, 자연어 `결함 시나리오`, `데이터 사용 기준`을 표시.
  저점수 참고는 `정상`이 아니라 `사람 확인 저점수 참고`로 명시
- 실제 coverage: 기존 10건은 상품군 2/4(`PERSONAL_CARE_CONTAINER`,
  `KITCHEN_OR_STORAGE_ITEM`)와 결함군 3/3을 표현. 나머지 상품군 두 개는 사진이 없어 미검증이며
  Qwen은 후보 제안만 하고 자동 승인·결함 분류에 사용하지 않음
- 검증: 실제 Top-100 package와 normal reference로 identity/rank/SHA/source label 10/10 PASS.
  기존 actual E3 seed 원장의 10건도 새 Gate 10/10 채택, defect 최저 0.9985969·reference 최고
  0.00006098로 각각 0.95/0.10 margin을 통과.
  Ruff PASS, Format 392, Pyright 0, 기본 682 PASS/65 deselected, closed-set 포함 targeted 25 PASS,
  Qwen 보조 도구 6 PASS. Web lint·typecheck·OpenAPI sync·22 files/60 tests·production build PASS,
  `git diff --check` PASS
- Runtime: 20:08 KST Web/API 재배포 뒤 Core 7 healthy, local Web/API health PASS, public Login DOM과
  console error 0. 인증 정보는 입력하지 않아 실제 Case 상세 화면과 live E3 seed 재실행은 미실행
- 안전: E3가 결함 유형을 예측하거나 저점수를 정상 확정한다는 주장 0, 실제 Decision/Action/메일
  발송 0. Commit·Push·PR 없음, 사용자 소유 미추적 문서는 수정·삭제·Stage하지 않음
- 다음 작업: 빈 상품군 두 개의 후보를 각 3~5장 확보해 사람 검수·권리·SHA·E3 score를 승인한 뒤
  `poc_closed_set` 새 버전에 추가하고, MVP 평가는 선별 표본과 분리된 Human Gold로 수행

### 2026-08-28 — Curated PoC 20-case Expansion

- 목표: 기존 최신 10건을 수정하지 않고 서로 다른 이미지·주문·문의 10건을 추가해 내부 시연
  범위를 결함 후보 12건과 사람 확인 저점수 참고 8건, 총 20건으로 확장
- 데이터: 결함 rank 1/9/22/31/73/79와 저점수 참고 rank 1/20/65/67을 사람 육안 대조하고
  exact SHA Allowlist로 고정. 개인 이름이 보이는 defect rank 61과 모호한 rank 56은 제외
- 계약: `realistic-internal-demo-v3`, `CLOSED_SET_EXPANSION_R3`,
  `poc_closed_set/2.0.0`. 기존 v2 10건과 registry v1은 불변이며 두 팩 합계로 상품군 4/4,
  원천 결함군 3/3을 표현. E3 운영 threshold `0.8984375`, 선별 margin `0.95/0.10` 유지
- Runtime: 최초 1건에서 API가 Mock snapshot, Worker가 Remote E3 snapshot인 설정 불일치를 발견.
  실패 Run 두 개는 삭제하지 않고 append-only 보존하고 API를 Worker와 같은 actual E3 identity로
  재구성. 고정 retry-2에서 성공한 뒤 새 10건 최신 Analysis `SUCCEEDED` 10/10
- 멱등성: 첫 완주에서 Case 9 생성/1 재사용, Evidence 9 업로드/1 재사용, 성공 Analysis 10 생성.
  즉시 재실행은 Case·Evidence·Analysis 10/10 재사용, Private Evidence integrity 10/10
- 안전: seed 전후 Policy Retrieval·Grounding·Policy Evaluation·Human Review·Resolution·Intent·
  Simulation Attempt/Result 모두 0. 저점수=정상 주장, 모델 결함 유형 예측, 실제 Decision·Action·메일 0
- UI: 20개 가상 상품/가격대와 closed-set 자연어 label 추가, provenance schema 3.0 fail-closed,
  상담 목록은 오래된 R1 중복을 숨기고 최신 R2 10건+R3 10건을 활성화. Web 재배포 후 local/public
  asset `index-CJlif6d0.js` 일치와 `/web-health` PASS
- 검증: Ruff·Format PASS, Pyright 0, targeted backend 35 PASS, 기본 686 PASS/65 Skip,
  Web lint·22 files/62 tests·production build PASS, v3 seed report replay hash
  `dc9bedb9b5de24a3a49c681b5d519024c6f52fd7791934d536d3a4879a78c8fb`, `git diff --check` PASS
- 범위: 클래스 표현은 정확도·calibration·시장 분포 평가가 아니다. 원본 재배포 권리는 미확인이고
  내부 합성 기술 시연만 허용. Commit·Push·PR 없음, 사용자 소유 미추적 문서 보존
- 다음 작업: 인증 상담원으로 새 상품군 대표 Case를 한 건씩 열어 표시와 Human Review 흐름을
  수동 확인하고, 20건 연속 처리의 메모리·queue·실패율 기준선을 별도로 기록

### 2026-08-28 — Korean Product-first Inquiry Console

- 목표: 상담 목록의 `case-primary`·`case-action` 영역과 상세 화면에서 내부 영문 코드보다 한글
  상품명과 자연어 업무 표현을 우선해 실제 상담원이 빠르게 읽을 수 있도록 정리
- 목록: `Case desk/상담 케이스`를 `문의 목록/접수된 문의`로 바꾸고, 활성 20건은 주문번호 대신
  `플랫케이스 오거나이저 2P` 같은 가상 상품명을 제목으로 표시. 주문번호·상품번호·가격대는
  한글 label이 붙은 보조 정보로 이동
- 업무값: `EXCHANGE/REFUND/RETURN/REPAIR/INFORMATION/OTHER/UNSPECIFIED`를
  교환/환불/반품/수리/정보 안내/기타 문의/아직 정하지 않음으로 표시. 검토 유형·우선순위·필터도
  일반 정책 검토/안전 검토/보통/긴급 등으로 변환하며 API 저장값은 변경하지 않음
- 상세/등록/보고서: 상세 제목을 상품명 우선으로 통일하고 문의 번호·주문 번호·상품 번호를 분리.
  새 문의 select와 버튼, 검토함, 데이터 자산, 운영 지표, 보고서의 영문 eyebrow와
  Resolution/DRY-RUN/Case 문구를 한글 업무 표현으로 교체
- 검증: Web ESLint PASS, TypeScript PASS, OpenAPI sync PASS, 22 files/62 tests PASS,
  production build PASS. 검색·처리 요청·모의 실행 요약의 잔여 영문도 제거한 뒤 local/public
  `/web-health` PASS와 배포 asset `index-BLCAsxTA.js` 일치, Core 7개 서비스 healthy
- 범위: CSS class와 API enum은 내부 계약이므로 변경하지 않고 사용자에게 보이는 문자열만 한글화.
  인증 정보는 입력하지 않아 실제 로그인 목록 육안 확인은 미실행. Backend·DB·Decision·Action 변경 0
- Git safety: Commit·Push·PR 없음, 사용자 소유 미추적 문서와 원본 이미지 보존
- 다음 작업: 기존 로그인 세션에서 활성 20건 목록과 대표 상세 1건의 한글 상품명·요청 유형을 육안 확인

### 2026-08-28 — Review Queue Product-name Unification

- 목표: 검토 대기함의 작업 유형 중심 제목을 문의 목록과 같은 상품명 중심 구조로 바꾸고,
  상담 목록·상세에서 `등록 상품 문의`로 보이던 기존 시연/점검 Case도 한글 상품명으로 통일
- 실제 범위 확인: 실행 중 DB를 읽기 전용 조회해 서로 다른 `product_ref` 49종을 확인. 최신
  R2/R3 20종 외에 이전 V1/V2 시연 참조, Kaputt/MLX/Policy/Query 점검 참조가 남아 있었음
- 구현: 최신 카탈로그·이전 참조 alias·내부 점검 참조를 하나의 표시 전용 resolver로 통합.
  검토 대기함은 각 Task의 Case 상세를 tenant API로 조회해 상품명, 검토 유형, 문의 번호를 함께 표시하고
  검토 상세 제목도 같은 resolver를 사용. 문의 목록·상세의 `등록 상품 문의` fallback 제거
- 안전 경계: 상품명은 합성 시연용 표시 metadata일 뿐이며 이미지 라벨, Vision class, 정책 입력,
  가격, 환불 금액, External Action parameter 또는 실제 상품 qualification에 사용하지 않음.
  Backend·DB·Human Decision·Action 변경 0
- 검증: Web ESLint PASS, TypeScript PASS, OpenAPI snapshot sync PASS, 23 files/61 tests PASS,
  current DB 49 product refs mapping coverage PASS, production build PASS. minified JS 500.69 kB에 대한
  Vite 권고 1건은 남았으나 build 실패·기능 오류는 아님. `git diff --check` PASS
- Runtime: 21:33 KST Web 재배포, local/public `/web-health` PASS, 양쪽 asset
  `index-DrYgNQF7.js` 일치, API/Worker/Dispatcher/Web/Postgres/RabbitMQ/MinIO 7개 healthy
- Git safety: Commit·Push·PR 없음, 사용자 소유 미추적 문서와 원본 이미지 보존
- 다음 작업: 기존 로그인 세션에서 문의 목록과 검토 대기함을 나란히 열어 동일 Case가 같은 상품명으로
  보이는지 수동 확인하고, 번들 분할은 화면 기능이 더 늘기 전에 별도 최적화

### 2026-08-28 — Full-width Allow/Deny Review Workspace

- 목표: 담당자가 허용/비허용을 선택하는 검토 상세 화면의 과도한 바깥 여백과 작은 글자·버튼을
  줄이고, 데스크톱 작업 공간을 실제 상담 업무 화면처럼 크게 사용
- 레이아웃: 검토 상세만 기존 1280px에서 최대 1540px로 확장. 좌측 근거와 우측 결정 패널을
  `1.25fr / min 460px`로 배치하고 gap 28px, Card padding 28px 적용. 1280px 이하에서는 한 열로
  전환해 좁은 좌우 열이 생기지 않도록 함
- 가독성: 상품명 제목, 탭, 검토 패킷 definition, 권고/qualification, 근거 기록의 글자·간격을 확대.
  빠른 검토 panel padding 26px, 허용/비허용 버튼 높이 90px, icon 25px, 판단 설명과 준비도 badge 확대
- 반응형: 760px 이하에서는 Card padding 18px, 빠른 검토 20px, 버튼 한 열과 header 세로 배치로
  모바일 overflow 없이 기존 조작 흐름을 유지
- 검증: Web ESLint PASS, TypeScript PASS, OpenAPI snapshot sync PASS, 23 files/61 tests PASS,
  production build PASS. minified JS 500.69 kB 권고 1건은 기존과 동일하며 기능 실패 아님.
  `git diff --check` PASS
- Runtime: 21:45 KST Web 재배포, local/public `/web-health` PASS, 양쪽 JS
  `index-Dxfs6VI-.js`와 CSS `index-DKhElaI1.css` 일치, Core 7개 서비스 healthy
- Browser scope: 연결된 브라우저는 로그인 화면 상태여서 인증 정보 입력 없이 검토 상세 육안 QA는
  실행하지 않음. CSS·component 회귀와 배포 asset까지만 현재 PASS
- Git safety: Commit·Push·PR 없음, Backend·DB·Human Decision·Action 변경 0, 사용자 소유 문서 보존
- 다음 작업: 사용자가 로그인한 뒤 대표 빠른 검토 1건을 열어 1440px 이상 화면에서 좌우 비율과
  첫 화면 내 허용/비허용 버튼 노출을 확인하고 필요하면 폭을 한 차례 미세 조정

### 2026-08-28 — Operator-friendly Policy and Analysis Summary

- 목표: 허용/비허용 검토 첫 화면의 정책 enum, qualification JSON, 영문 기술 용어를 상담원이
  즉시 이해할 수 있는 한글 업무 표현으로 전환
- 정책 권고: `REQUIRES_HUMAN_REVIEW`를 `담당자 확인 후 결정 필요`로 표시하고 추가 자료 필요,
  검토 가능, 적용 정책 없음 상태도 자연어 label로 확장. 정책은 참고이며 담당자가 최종 결정한다는
  설명을 함께 표시
- 분석 상태: raw JSON 대신 문의 내용 분석, 이미지 분석, 문의·이미지 일치 확인, 정책 근거 정합성
  네 항목으로 분리. `MOCK_QUALIFIED`는 `시연용 분석 결과 준비`, `NOT_AVAILABLE`은
  `담당자 확인 필요`로 표시하며 model family/revision은 첫 화면에서 숨김
- 문구 정리: `Grounded explanation`을 `정책 근거 확인 요약`, `immutable snapshot`을
  `변경 방지 기록`, 빠른 검토의 `DRY-RUN`을 `모의 처리 확인`으로 교체. 정책 평가 번호와 매핑
  버전은 삭제하지 않고 접힌 `기술 정보 보기`로 이동
- 안전 경계: presentation-only 변환이며 Packet/qualification snapshot/API/DB/hash와 빠른 검토
  점수·임계치·Human Decision 조건은 변경하지 않음. Mock/미지원 범위를 실제 검증 완료로 승격하지 않음
- 검증: Web ESLint PASS, TypeScript PASS, OpenAPI snapshot sync PASS, 24 files/63 tests PASS,
  production build PASS. minified JS 502.99 kB 권고 1건, `git diff --check` PASS
- Runtime: 22:09 KST Web 재배포, local/public `/web-health` PASS, 양쪽 JS
  `index-s6FnmG0z.js`와 CSS `index-CWAdx66O.css` 일치, Core 7개 서비스 healthy
- Git safety: Commit·Push·PR 없음, Backend·DB·Decision·Action 변경 0, 사용자 소유 문서 보존
- 다음 작업: 인증된 검토 상세에서 네 가지 상태가 한 줄씩 읽히고 기술 JSON이 노출되지 않는지
  육안 확인한 뒤, 규칙/인용/기록 탭의 raw key도 같은 label registry로 후속 정리

### 2026-08-28 — Operational-language Console Cleanup

- 목표: 상담원이 보는 화면과 출력 문서에서 `PoC`, 모의, 시뮬레이션, DRY-RUN, Mock, 데모,
  시연 같은 개발·검증 용어를 제거하고 실제 업무 흐름에 맞는 표현으로 통일
- 화면: 메뉴의 `PoC 지표`를 `운영 지표`, 빠른 검토와 처리 상태를 `처리 사전 확인`, 정책 자료를
  `사내 정책 참고 자료`로 교체. 문의·고객·상품 badge도 온라인 접수/고객 정보/상품 정보로 정리
- 문서/메일: 환불 문서는 `외부 처리 전 확인 문서`, 메일은 `안내 메일 만들기`로 전환. 신규 메일
  제목의 개발 표식을 제거하고, 기존 불변 메일은 저장 원본을 수정하지 않은 채 표시 단계에서 같은
  운영 문구로 정규화
- 데이터 표시: 내부 계약의 `DEMO` 상품·고객 참조와 테스트용 주소 표식은 DB/API 값을 바꾸지 않고
  표시 전용 상품번호·고객번호·주소로 정리. 실제 고객 데이터가 아니라는 안내는 유지
- 안전 경계: API enum, Event, DB schema, hash snapshot, Human Decision 조건은 변경하지 않음.
  실제 카드 취소·환급·교환·SMTP 전송은 계속 0이며 `외부 시스템 미반영`을 화면에 명시
- 검증: Web ESLint·TypeScript·OpenAPI sync PASS, 24 files/63 tests PASS, production build PASS.
  Backend 메일 생성 변경은 Ruff·Format과 관련 unit 15 tests PASS, `git diff --check` PASS
- Runtime: 22:29 KST API/Web 재배포, Core 7개 서비스 healthy. local/public JS
  `index-BdA6eGFX.js`와 CSS `index-CWAdx66O.css` 일치
- 미해결: 연결 브라우저의 인증 상태를 사용하지 않았으므로 실제 상담 케이스·검토·인쇄 화면 수동
  육안 확인은 미실행. 번들 500 kB 초과 권고 1건은 기능 실패가 아니며 후속 최적화 대상
- Git safety: Commit·Push·PR 없음, 사용자 소유 미추적 문서와 원본 이미지는 수정·삭제·Stage하지 않음
- 다음 작업: 사용자가 로그인한 상태에서 대표 환불 케이스의 상담 상세→빠른 검토→환불 확인서→안내
  메일을 순서대로 열어 잔여 개발 문구와 실제 처리 오해 가능성이 없는지 최종 육안 확인

### 2026-08-28 — Operator Workflow Product Direction and Git Handoff

- 목표: 현재까지 누적된 고객·주문 문맥, 20건 closed set, 상담원 UI, 빠른 검토, 환불 문서,
  안내 메일, 데이터 자산과 운영형 문구 변경을 별도 GitHub 브랜치에 보존하고 방향 전환 이유를 기록
- 방향 문서: `docs/product/PRODUCT_DIRECTION_EVOLUTION_2026-08-28.md`에 초기 기술 검증 목표,
  E3 이진 계약과 Qwen enrichment 한계, 실제 기업 데이터 없이 업무 흐름을 보여줘야 했던 이유,
  Human Decision·명시 입력·외부 시스템 미반영·비식별 데이터 자산 원칙과 다음 승격 조건을 정리
- Git: `feature/scenario-poc-hard-plastic`의 `dfaa373`에서
  `codex/operator-console-product-direction` 생성. 누적 100개 파일, 7,096 additions/309 deletions를
  `c90357d feat: evolve CSight into an operator workflow`로 커밋하고 같은 이름의 원격 브랜치에 Push
- 안전 감사: staged diff의 고신뢰 Secret 패턴 0, 1 MiB 초과 blob 0, `git diff --cached --check`
  PASS. `CSight_MASTER_HANDOFF_2026-08-27.md`, `ecommerce_vibe_coding_cs_automation_market_research.md`,
  `kaputt_best_vision_architecture.md`는 미추적 상태로 보존하고 Commit·Push에서 제외
- 검증: Ruff PASS, Format 392 files PASS, Pyright 0, 기본 Backend 686 PASS/65 deselected,
  Web ESLint·TypeScript·OpenAPI sync·24 files/63 tests·production build PASS. 번들 500 kB 초과 권고
  1건은 기능 실패가 아니며 후속 최적화 대상
- 원격 확인: 22:39 KST `refs/heads/codex/operator-console-product-direction`이
  `c90357da845a522bd3ce8ba8446c39f57139fafe`를 가리키는 것을 확인
- CI 정정: 문서 handoff `dac2447`의 Run #33176499654는 화면이 자연어로 바뀐 뒤에도 E2E가
  `APPROVE_REPAIR`, `Resolution 및 DRY-RUN` 같은 이전 표시를 찾고 있어 Consultant console Job이
  FAIL. 제품 기능 문제가 아니라 stale selector 18곳의 불일치였으며 실패 기록은 삭제하거나 재실행으로
  덮지 않음
- E2E 보정: 현재 화면의 수리 승인, 처리 사전 확인, 온라인 접수, 사내 정책 참고 자료와 외부 시스템
  미연결 문구를 검증하도록 수정. 로컬 Playwright 5/5 PASS 후 `42616a4 test(web): align scenarios
  with operator labels`로 Push
- 최종 원격 Gate: 22:52 KST `42616a4`의 GitHub CI Run #33177206525 PASS. Quality Job은
  Ruff·Format·Pyright·기본 회귀, Consultant console Job은 lint·typecheck·OpenAPI·unit·build·
  Playwright 5개 시나리오를 모두 통과
- 범위: 새 브랜치와 커밋·Push만 수행. PR 생성, `develop/main` 병합, tag/release, 사용자 소유 문서
  stage는 수행하지 않음
- 다음 작업: GitHub Actions 결과를 확인한 뒤 사용자가 원하면 이 브랜치에서 리뷰용 PR을 생성하고,
  인증 상담원 수동 시나리오 QA와 번들 분할을 별도 후속 커밋으로 진행

### 2026-08-28 — Operator Workflow CI Selector Stabilization

- 최종 상태 문서 커밋 `7ad1b9f`의 Run #33177439114에서 Backend Quality Job은 PASS했으나,
  Consultant console E2E가 `추가 자료 필요` 문구 두 곳을 하나로 가정한 strict locator 때문에 1건 FAIL
- 같은 상태 badge가 한 곳 또는 두 곳에 나타나는 양쪽 UI 상태를 허용하되 첫 번째 정확 일치 항목이
  보이는지 검증하도록 수정. 제품 동작·API·DB는 변경하지 않고 브라우저 회귀 검사의 모호성만 제거
- 실패 Run과 원인은 원장에 그대로 보존. 수정 후 로컬 Playwright 5/5 PASS, 수정 커밋의 GitHub CI를
  다시 확인
- 범위: PR·병합·tag/release 없음. 사용자 소유 미추적 문서 3개는 계속 Commit·Push에서 제외

### 2026-08-28 — Next-session Operator Workflow Handoff

- 다음 세션 전용 요약 `docs/progress/SESSION_HANDOFF_2026-08-28_OPERATOR_WORKFLOW.md` 작성
- 제품 방향 전환 근거, 현재 구현, E3/Qwen 역할 구분, Human Decision·명시 입력·외부 시스템 미반영
  경계, Git/CI 기준점, 미추적 보존 파일과 재시작 명령을 한 문서에 통합
- 현재 관측: 23:02 KST Git HEAD와 원격 `3daaa7b` 일치, GitHub CI #33177793237 PASS, DB Head
  `0016`, Core 7개 healthy, public `/web-health` `ok`
- 검증: 문서 전용 변경으로 제품 회귀는 NOT_RUN; `git diff --check` PASS, 인계 문서의 로컬 상대
  링크 10개 대상 파일 존재 PASS
- Git safety: 이번 인계 문서 작성 요청은 Commit·Push 권한으로 확장하지 않음. 새 문서와 원장 갱신은
  로컬 변경으로 남기고 사용자 소유 미추적 문서 3개는 계속 보존
- 다음 작업: 인계 문서의 7절에 따라 인증 상담원 공개 화면 수동 QA부터 시작

### 2026-08-29 — Investor-facing System Architecture SVG

- 목표: 최신 원격 브랜치와 운영형 상담원 인계 문서를 기준으로, 비기술 투자자가 전체 제품 구조와
  사람 최종 결정 경계를 한 장에서 이해할 수 있는 시스템 아키텍처 SVG 작성
- Git 기준점: `git fetch --prune origin` 후 가장 최근 원격 브랜치는
  `origin/codex/operator-console-product-direction`, HEAD `3daaa7b`로 확인. PR·병합·Push 없음
- 산출물: `CSight_project_docs/docs/assets/CSight_investor_system_architecture.svg`. 문의/이미지/주문
  접수 → 멀티모달 근거 분석 → 정책 근거 준비 → 상담원 최종 결정 → 처리 사전 확인/문서/비식별
  학습 자산의 흐름과 고객사 격리·비동기 복원력·Private Evidence·변경 불가능한 감사 원장을 표현
- 안전 경계: E3는 이미지 단위 결함 후보 선별만 담당하고, 정책과 모델은 근거/권고만 제공하며,
  인증된 사람만 최종 결정을 생성한다. 합성 정책·상거래 문맥과 외부 환불·결제·CRM·물류·메일
  미실행 범위를 SVG 하단에 명시
- 검증: XML well-formed PASS, macOS SVG→PNG 1600×1000 렌더 PASS, 전체 화면 육안 QA PASS,
  `git diff --check` PASS. 문서 전용 산출물이므로 제품 회귀 테스트는 NOT_RUN
- 미해결: 투자자 발표 자료의 실제 배경색·슬라이드 비율과 조합한 최종 배치 검토는 NOT_RUN
- 다음 작업: 필요 시 발표 덱에 맞춘 밝은 배경형 또는 16:9 슬라이드 삽입형 변형을 별도 자산으로 생성

### 2026-08-29 — Admin Operations Read API (append-only session log)

- 완료 체크리스트: technology-neutral operations contract/port, admin-only application services,
  SQLAlchemy aggregate read adapter, HTTP response schema/router/service container, bootstrap builder,
  focused unit test, opt-in PostgreSQL integration test, 운영 계약 문서를 새 파일 중심으로 구현
- 조회 계약: `GET /api/v1/operations/overview`와 `GET /api/v1/operations/failures`는 현재
  Principal tenant만 조회하고 `ADMIN` role을 HTTP/application 양쪽에서 확인. 응답은 고정 7 queue,
  고정 7 processing component, component당 상위 실패코드 최대 3개, 활성 version 최대 64개로 제한하고
  tenant/case/run/event ID, 원문 오류, 입력·출력·문의 내용은 반환하지 않음
- 집계 범위: legacy analysis outbox와 retrieval/grounding/evaluation/review/resolution/simulation durable
  outbox, 각 처리 run/task/attempt의 backlog·oldest age·failed·partial success·retry·stalled·last healthy,
  그리고 저장된 model/prompt/policy/threshold/index version을 endpoint당 PostgreSQL 한 문장으로 집계.
  `latest_run_snapshot`/`latest_succeeded_result`는 실제 활성 배포 증명이 아님을 source로 구분
- 실제 검증: focused Ruff `All checks passed`, Ruff format check `10 files already formatted`, focused
  Pyright `0 errors, 0 warnings, 0 informations`, `tests/unit/test_operations.py` 4 passed,
  `RUN_CORE_INTEGRATION=1 tests/integration/test_operations_read_sql.py` 1 passed. PostgreSQL test에서
  endpoint당 statement count 1, 7/7 고정 차원, response bound와 식별자 미노출을 확인
- 안전 경계: PostgreSQL은 read-only 조회만 수행했고 외부 network/GPU/provider/실제 환불·결제·메일 등
  사업 동작은 0. `app/main.py`, 공통 `dependencies.py`, router package export, permission enum은 이 세션에서
  수정하지 않았으며 Commit·Push·PR도 수행하지 않음
- 미해결: replay/cancel은 미구현. ADR-0011/0075의 새 immutable run 원칙과 ADR-0093의 fenced event
  원장을 지키려면 새 operation/event/run identity, idempotency, 대상 상태·권한, live claim race fencing,
  append-only audit reason과 side-effect 경계를 함께 정한 accepted contract가 먼저 필요
- 다음 작업: composition owner가 `build_operations_services(settings)`를
  `application.state.operations_services`에 연결하고 operations router를 include/export한 뒤 OpenAPI sync,
  전체 backend 회귀와 배선된 admin/reviewer HTTP smoke를 실행

### 2026-08-29 — Limited-pilot Demo-safe Closeout

- 목표와 종료선: 약 6주 계획 전체를 파일럿 적격으로 과장하지 않고, 2026-08-30 내부 시연을 깨뜨릴
  가능성이 큰 안전·복구·UI 문제를 우선 구현했다. 외부 GPU·실제 환불·결제·메일 동작은 0이며
  모델과 정책은 권고만 만들고 인증된 사람만 최종 결정을 생성하는 경계를 유지했다.
- 상담원 흐름: 사건/검토 목록 단일 조회와 상태별 건수·cursor, 업무 탭, 통합 workflow snapshot,
  timeout·지수 backoff·마지막 정상 결과, 동일 제출 멱등성 키, 빠른 결정의 명시 확인 dialog,
  cancel 0 mutation과 lost response/409 최종 상태 재조회 계약을 구현했다. 5개 viewport
  320/375/768/1024/1440에서 Axe serious/critical 0, 가로 overflow 0, 44px 조작 영역을 확인했다.
- 인증·보안: OIDC Authorization Code+PKCE, 일회성 browser-bound state cookie, hashed DB session,
  HttpOnly/Secure/SameSite cookie, CSRF, group→tenant/role mapping, 절대/유휴 만료와 복귀 경로를 추가했다.
  non-local 환경은 완전한 OIDC 설정 없이는 시작하지 않고 Uvicorn access log와 `/auth/` access/error
  log에서 callback code/state query를 차단한다. 관련 보안 집중 테스트 30 PASS.
- DB·개인정보: tenant 조건 보강, 기본 거부 RLS와 API/Worker/Dispatcher 역할, 민감 원문 분리·명시
  retention·fail-closed dual-read, PII-free append-only lifecycle event, idempotent purge와 Evidence 정합성
  dry-run/명시 삭제 경계를 추가했다. EXIF 제거·재인코딩·악성 파일 검사 port/adapter도 추가했지만 실제
  고객 이미지 반입 자격은 아직 부여하지 않았다.
- 비동기·운영: model 1/retrieval 2/decision 2의 별도 처리선, child dispatcher failure isolation,
  poison event 영구 실패/격리, durable failure ledger와 운영 overview/failure 조회를 구현했다. recovery
  replay/cancel 코드는 검증 자산으로 보존하되 일부 pipeline이 원본 작업을 실제 terminalize하지 않고도
  resolution을 남길 수 있어 runtime composition에서는 둘 다 비활성화했다. 관리자 조회만 사용 가능하다.
- 모델·관측: 기본 RAW→HYBRID→Top 3, process-scoped provider client, 5회 연속 장애/30초 circuit,
  global/tenant admission, tenant/index/profile/content-hash cache 경계, PRIMARY/SHADOW 및 package
  qualification 계약을 추가했다. OpenTelemetry는 기본 off·network-free이며 HTTP/Celery span과
  low-cardinality metric만 opt-in으로 제공한다.
- 정적·회귀 실제 결과: Ruff PASS, Format 478 files PASS, Pyright 0, 기본 Backend 809 PASS/83
  deselected, Web ESLint·TypeScript·OpenAPI sync PASS, Vitest 29 files/76 tests PASS, production build
  PASS. 초기 JS gzip 82.27 kB, 최대 raw chunk 257.97 kB로 120 kB/500 kB 예산 이내다.
- PostgreSQL 실제 결과: 격리 임시 DB에서 failure recovery·RLS·append-only·claim fencing·privacy
  preflight·migration round-trip·최종 Alembic drift check 7 PASS. 재빌드한 로컬 스택은 API,
  Dispatcher, model/retrieval/decision Worker, Web, PostgreSQL, RabbitMQ, MinIO 총 9개 healthy이며
  `/health/ready`와 `/web-health` PASS. DB Head `20260829_0022_privacy_lifecycle`, Case 94건과
  restricted payload 94건을 보존했다.
- 백업: 재빌드 전 `/private/tmp/csight_pre_demo_20260829.dump`를 PostgreSQL custom dump로 만들고
  SHA-256 `900b80ea73f0e75fd0ea0f9657d4687897bdc439cbd842ab74bb1026e71f84b3`, TOC 854개를 확인했다.
  이는 같은 Mac의 임시 안전 사본일 뿐 off-host 암호화 백업·RPO/RTO 복원 훈련 증거가 아니다.
- 미해결/파일럿 차단: 현재 데모 DB는 수정 전 0021 제약조건 이름으로 이미 migration이 적용되어
  최신 ORM과 `alembic check` 이름 drift가 남고, 뒤늦게 보강한 Evidence 복합 unique constraint도
  반영되지 않았다. 새 빈 DB는 drift 0이므로 시연 후 additive 수렴 migration으로 기존 DB만 고친다.
  실제 IdP, 20세션/20건 부하·120초 모델 격리, full E2E fault matrix, peak memory, off-host WAL/MinIO
  restore drill, 경보 전달, 실 고객 이미지 ClamAV 경로는 NOT_RUN이다.
- 다음 행동: 시연에서는 `http://127.0.0.1:8080`의 합성 문의 목록→검토 상세→확인 dialog→사람 결정→
  외부 처리 전 문서 흐름만 사용하고 운영 실패 replay/cancel은 사용하지 않는다. 시연 후 기존 DB
  수렴 migration과 복원 훈련을 먼저 끝낸 뒤에만 제한 운영 파일럿 승격을 다시 판단한다.
- Git safety: Commit·Push·PR 없음. 사용자 소유 미추적 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 수정·삭제·stage하지 않았다.

### 2026-08-29 — macOS One-click Server Controller

- 목표: 시연자가 Terminal 명령을 외우지 않고 CSight 로컬 서버를 켜고 끄며 상태와 상담원 화면을
  확인할 수 있는 작은 macOS 앱을 제공했다.
- 산출물: 바탕화면 `/Users/ckdlsxor/Desktop/CSight 서버 제어.app`, 실행 로직
  `scripts/csight_server_control.sh`, 대화상자 원본 `scripts/csight_server_control.applescript`.
- 기능: 빠른 시작, 코드 재빌드+Migration 시작, 상태 확인, 상담원 화면 열기, 서버 끄기. Docker
  Desktop이 꺼져 있으면 시작 작업이 자동으로 앱을 열고 최대 2분간 준비를 기다린다.
- 안전 경계: 종료는 `docker compose stop`만 사용하며 `down`, `volume rm`, `--volumes`를 사용하지
  않는다. 따라서 PostgreSQL·RabbitMQ·MinIO Named Volume과 시연 데이터는 보존된다. 코드 반영
  시작만 명시적으로 build와 migrator를 실행한다.
- 실제 검증: zsh syntax PASS, AppleScript compile PASS, local app codesign verify PASS, static safety
  unit 3 PASS. 실제 현재 스택에서 status가 9개 서비스·API 정상·상담원 화면 정상을 반환했고,
  stop→빠른 start를 한 번 수행한 뒤 9개 서비스 healthy, DB Head
  `20260829_0022_privacy_lifecycle`, Case 94건, restricted payload 94건 보존을 재확인했다.
- 문서: README 빠른 시작 아래에 앱 메뉴, 볼륨 보존 동작, source 경로와 프로젝트 이동 시 재컴파일
  조건을 추가했다.
- 미해결: macOS 전용 앱이며 프로젝트 경로를 옮기면 AppleScript의 `controllerPath`를 수정해 다시
  컴파일해야 한다. Windows/Linux launcher와 메뉴바 상주 기능은 이번 범위에서 NOT_RUN이다.
- 다음 행동: 시연 시작 전 바탕화면 앱에서 `서버 상태 확인`; 정상이 아니면 `서버 켜기 (빠른 시작)`;
  종료 후 `서버 끄기`를 사용한다. 시연 직전에는 불필요한 `코드 반영 후 켜기`를 실행하지 않는다.
- Git safety: Commit·Push·PR 없음. 기존 사용자 파일과 미추적 투자자 SVG를 수정·삭제·stage하지 않았다.

### 2026-08-29 — Operator Queue Intake UI Cleanup

- 목표: 상담원이 프론트에서 직접 새 케이스를 생성하는 기능을 제거하고, 상담 케이스와 검토 대기함의
  주문·상품·문의 번호 검색 및 정렬 영역을 시연용으로 단정하게 통일했다.
- 기능 제거: 사이드바 `새 케이스`, 상담 케이스의 `새 문의`·빈 목록 생성 버튼, lazy route와
  `NewCasePage` 구현·테스트를 삭제했다. 이전 북마크 `/cases/new`는 동적 case ID로 오인하지 않고
  `/cases`로 즉시 전환한다. Backend의 기존 additive API 계약은 이번 프론트 범위에서 변경하지 않았다.
- 목록 UX: 검토 대기함에도 상담 케이스와 같은 검색창을 추가했고 case/order/product reference와 표시용
  상품명·담당자를 현재 로드된 목록에서 검색한다. 검색 결과 건수와 전체 건수를 함께 보여주며 결과가
  없을 때 전용 안내를 표시한다.
- 스타일 원인과 수정: 공통 `label`의 column 방향이 큐 전용 검색·정렬 label을 뒤에서 덮어써 실제 높이가
  데스크톱 75/80px, 모바일 검색 300px까지 늘어났다. 큐 전용 컨트롤을 row 방향·48px로 고정하고
  테두리, 배경, focus ring, select 구분선을 하나의 시각 체계로 정리했다.
- 실제 검증: Web ESLint PASS, Vitest 전체 28 files/76 tests PASS, TypeScript 포함 production build PASS.
  Playwright에서 320/375/768/1024/1440px 각각 검색·정렬 48/48px, Axe serious/critical 0, 가로 overflow
  0, 44px 미만 조작 영역 0을 확인해 접근성 E2E 5/5 PASS했다. `git diff --check`도 PASS했다.
- 실행 반영: Docker registry의 base-image metadata 응답이 멈춰 immutable Web image 재빌드는 중단했지만
  기존 서비스는 계속 healthy였다. 검증된 local production `dist`를 현재 Web container에 복사했고,
  로컬 브라우저 reload에서 JS `index-D51HAjpP.js`와 CSS `index-B0VMCdDB.css`가 실제 로드됨을 확인했다.
  인증 정보는 사용하지 않아 배포 로그인 화면만 확인했고, 인증 후 목록 육안 검증은 fixture E2E로 수행했다.
- 미해결: Docker image 자체의 최신 코드 재빌드는 registry metadata 연결이 정상일 때 다시 수행해야 한다.
  현재 container는 stop→quick start에는 파일 변경이 유지되지만 명시적 rebuild/recreate 시 기존 image로
  돌아갈 수 있으므로 시연 직전에는 제어 앱의 `서버 켜기 (빠른 시작)`만 사용한다.
- 다음 행동: 시연 직전 `서버 상태 확인` 후 빠른 시작을 사용하고, 로그인 뒤 상담 케이스와 검토 대기함의
  검색·정렬을 한 번씩 확인한다. 시연 후 Web image를 정상 재빌드해 container-local 반영 의존성을 제거한다.
- Git safety: Commit·Push·PR 없음. 기존 대규모 작업트리 변경, 사용자 소유 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-29 — Policy Retrieval Embedding Outage Diagnosis

- 증상: 문의 `228374aa-…-a97e`는 이미지 분석까지 완료됐지만 정책 검색이 FAILED로 종료되어 정책 평가와
  사람 검토가 생성되지 않았고, 화면은 마지막 정상 단계 `ANALYSIS`와 정책 후보 0개를 표시했다.
- DB 증거: Retrieval Run `b96123b8-…-0b6b`, correlation `8f13527a-…-7f83a`, RAW query strategy,
  `as_of_date=2026-08-28`, 실행 1회, failure code `EMBEDDING_PROVIDER_UNAVAILABLE`, 10:07 KST terminal
  FAILED를 확인했다. 정책 날짜 422나 문의 데이터 문제가 아니다.
- 원인: RAW는 query-builder 전략일 뿐이며 Accepted ADR-0103과 application use case는 실제 검색을
  고정 HYBRID로 수행한다. 활성 index 2.0.0은 `Qwen/Qwen3-Embedding-0.6B` query embedding을 요구하지만
  host `127.0.0.1:8091`은 응답하지 않았고 PID 파일의 6483도 실행 중이 아닌 stale 상태였다.
- 운영 원인: macOS one-click controller의 빠른 시작은 `infra/compose.core.yml`만 시작하므로 Docker 밖의
  host-native Embedding을 시작하거나 health-check하지 않는다. Mac 종료 전 프로세스가 사라진 뒤 Core 9개만
  다시 올라와 화면·API는 healthy지만 정책 검색 기능만 degraded가 된 상태다.
- 영향 범위: 같은 실패코드의 최근 Retrieval 2건을 확인했고, 그 전 저장된 성공 실행은 30건이다. 실패는
  append-only로 정상 보존됐으며 하위 정책 평가·사람 결정으로 잘못 진행하지 않아 안전 경계는 유지됐다.
- 검증: Docker Core 9개 healthy, host 8091 connection refused, stale PID, 해당 Run/Outbox/Worker disposition과
  집계 결과를 read-only로 확인했다. 코드·DB·프로세스 상태 변경과 외부 사업 동작은 0, 테스트는 NOT_RUN이다.
- 미해결/다음 행동: 이번 요청은 원인 진단이므로 Embedding 시작, 실패 Run 재처리, controller 수정은 하지
  않았다. 다음 변경에서는 제어 앱이 Embedding을 함께 시작하고 health를 확인한 뒤, 기존 실패를 덮지 않는
  새 Retrieval Run으로 대표 문의를 검증해야 한다.
- Git safety: Commit·Push·PR 없음. 사용자 소유 파일과 기존 작업트리 변경을 보존했다.

### 2026-08-29 — Full-PoC macOS Controller Recovery

- 목표: 바탕화면 `CSight 서버 제어.app`의 빠른 시작 한 번으로 Docker Core뿐 아니라 HYBRID 정책
  검색에 필수인 host-native Qwen Embedding까지 오류 없이 시작하고, 상태 확인·안전 종료 범위에도
  포함했다.
- 구현: `scripts/csight_embedding_runtime.sh`를 추가하고 macOS 기본 `screen`의 전용 분리 세션에서
  Embedding을 실행한다. 대화상자나 호출 shell이 끝나도 엔진은 유지되며 PID·실제 command를 함께
  검증한다. stale PID는 제거하고 앱이 소유하지 않은 8091 프로세스는 강제 종료하지 않는다.
- 시작 Gate: 빠른 시작과 재빌드 시작 모두 Embedding `/health`와 `/v1/models`가 성공할 때까지 최대
  3분 기다린 뒤에만 Core를 시작한다. 상태 화면에는 Core 실행 수, API, Web, 정책 검색 엔진을 함께
  표시한다.
- 종료 안전성: `screen` 세션 종료 후 기록한 PID가 실제 `infra.embedding.server:app`인지 확인해
  `TERM`만 사용한다. Docker는 계속 `compose stop`만 사용해 PostgreSQL·RabbitMQ·MinIO Named
  Volume과 append-only 실행을 보존하고 `down`·volume 삭제·강제 KILL은 사용하지 않는다.
- 공개 주소: 기존 macOS Cloudflare Tunnel LaunchAgent를 시작·종료 범위에 포함하고 외부
  `https://doongdoong.org/web-health`까지 준비 Gate와 상태 표시에 추가했다. Tunnel 설정과 인증
  자료는 수정·삭제하지 않는다.
- 실제 전체 검증: controller stop으로 공개 주소·Core 0개·API/Web/Embedding down을 확인한 뒤
  controller 빠른 start로 Core 9개, API·Web·Embedding·공개 주소 모두 정상 복귀했다. 재시작 뒤
  외부 Web health 200과 새 합성 Retrieval `e581dfdc-c02a-495d-84c4-a2a1b092dbea`의
  `SUCCEEDED`, query 2개·hit 10개 저장을 확인했다.
- 회귀·앱 검증: 두 zsh 파일 syntax PASS, controller static safety unit 5 PASS, AppleScript compile
  PASS, 바탕화면 앱 ad-hoc codesign verify PASS. DB Head `20260829_0022_privacy_lifecycle`, Case
  97건을 확인했다.
- 경계/미해결: 기존 FAILED Retrieval은 감사 원칙에 따라 덮어쓰지 않고 보존한다. 문의 상세에서
  `분석 계속하기`를 누르면 정상 의존성으로 새 실행이 생성된다. 이 결과는 현재 Mac 내부 시연 가용성
  증거이며 HA·24x7·20명 부하·복원 훈련 자격은 아니다.
- 다음 행동: 시연 직전 바탕화면 앱에서 `서버 상태 확인`을 눌러 네 항목이 정상인지 보고, 이상 시
  `서버 켜기 (빠른 시작)`만 사용한다. 기존 실패 문의는 `분석 계속하기` 한 번으로 새 정책 검색을
  시작하고 사람 결정 전 확인 화면을 유지한다.
- Git safety: Commit·Push·PR 없음. 사용자 소유 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 수정·삭제·stage하지 않았다.

### 2026-08-30 — Admin Assignment and Personal Review Workspace

- 목표/완료: 문의가 들어온 뒤 관리자가 담당자를 지정·변경하고, reviewer-only 계정은 현재 배정된
  문의와 자신이 최종 처리한 문의만 분리해서 보도록 구현했다. 관리자 사이드바는 기존 명칭을 유지하고,
  담당자 사이드바는 `문의 대기`, `내 문의 처리 현황` 두 업무 메뉴만 표시한다.
- 배정 계약: 관리자 전용 `GET /api/v1/human-review-assignees`와
  `POST /api/v1/human-review-tasks/{task_id}/assign`을 추가했다. 배정·재배정은 CAS version을 검사하고
  `ASSIGNED`/`REASSIGNED` action과 `ADMIN_ASSIGNMENT` 이력을 append-only로 남긴다. 관리자 전용 검토는
  reviewer에게 배정되지 않도록 fail closed한다.
- 개인별 조회: reviewer-only의 활성 문의는 현재 assignee, 완료 문의는 immutable
  `human_review_decisions.decided_by` 기준으로 제한했다. Quality Viewer와 Admin의 감독용 전체 조회는
  유지했다. 담당자 `/cases`는 `my`, `/reviews`는 `complete`를 기본·유일 보기로 사용한다.
- 단일 검토 요약: 기존 `요약/정책 규칙/인용 근거/기록` 탭을 한 장의 `문의 검토 요약`으로 통합했다.
  사진, LLM 문의 요약, grounded 정책 설명, 인용 조항 본문, 기술 이력 접기를 한 흐름으로 표시한다.
- 유사도 근거: 새 HYBRID 실행부터 기존 query embedding을 재사용해 정확한 cosine 기준 최근접 3개와
  최저 3개를 `policy_retrieval_similarity_evidence`에 저장한다. 설명용 reference 0.65는
  `policy_similarity_reference/1.0.0`으로 고정했으며 정책 판정·승인·거절 임계값이 아니다. 기존 Run은
  점수를 추정하지 않고 새 분석이 필요하다고 표시한다. 결정·환불·메일 등 외부 동작은 추가하지 않았다.
- 문서/DB: Accepted ADR-0109, API/Architecture 계약, additive migration
  `20260830_0023_operator_assignment_similarity`를 추가했다. RLS 기본 거부와 API/Worker insert-select만
  허용하고 update/delete는 revoke했다.
- 실제 검증: Backend Ruff PASS, Pyright 0 error, unit 전체 714 PASS. Web 관련 Vitest 13 PASS,
  TypeScript production build PASS(초기 JS gzip 82.19KB). Controller `rebuild` 경로로 image build,
  migration, 전체 재기동을 완료했고 DB Head 0023, Core 9개/API/Web/Embedding/공개 주소 모두 정상이다.
  OpenAPI에서 두 배정 API를 확인했다.
- Runtime smoke: 합성 Policy Retrieval Run `e26aaf44-3135-4187-9f08-bbc460faa539`이 query 2개,
  hit 10개로 SUCCEEDED했고 DB에 NEAREST 3 / LEAST 3이 저장됐다. `csight-demo-brand`의 합성 관리자
  검토 1건을 실제 API로 관리자에게 배정해 `ASSIGNED`, version 2, `CLAIMED`를 확인했다. Reviewer
  개인 조회 API는 미배정 항목을 노출하지 않았다. Browser 검증 절차로
  `https://doongdoong.org/login`의 새 배포 화면이 정상 렌더링되는 것도 확인했다.
- 미해결: 기존 완료/대기 Run에는 exact cosine 근거가 없으므로 상세 화면에서 legacy 안내가 보인다.
  새 비교 6개를 시연하려면 새로 분석된 문의를 열어야 한다. 실제 reviewer 계정의 개인 큐 육안 확인은
  비밀번호를 브라우저에 입력하지 않아 NOT_RUN이며 API 역할 조회와 fixture UI 테스트로 검증했다.
- 다음 행동: 내일 시연 직전 서버 제어 앱에서 `서버 상태 확인` 후, 관리자 계정으로 검토함의 담당자
  선택을 보여주고 담당자 계정으로 `문의 대기`를 연다. 유사도 6개 시연은 새 분석 완료 문의를 사용한다.
- Handoff checklist: 구현 완료, migration 적용, image 재빌드, public health 확인, synthetic runtime
  smoke 완료. Commit·Push·PR 없음. 기존 작업트리, 사용자 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 — Product Readiness and RTX 4090 Qwen3.8 Audit

- 목표/범위: 새 데이터 수급만 기다리지 않고 현재 내부 시연 기반에서 실제 제한 운영 제품을 막는
  architecture, DB, 개인정보, 업무 소유권, UI 안전성, 복구·관측, 모델 release 공백을 실측했다.
  진단 세션이므로 P0 동작 수정, 실제 고객 데이터 반입, 실제 외부 환불·메일·결제는 수행하지 않았다.
- 산출물: `docs/product/PRODUCT_READINESS_AND_RTX4090_AUDIT_2026-08-30.md`에 현재 분류,
  Qwen3.8-27B/4090 artifact 결정, P0/P1, ordered implementation batches, acceptance gate와 대외 claim
  경계를 기록했다. 현재 상태는 `DEMO_READY`, 제한 파일럿은 `BLOCKED_P0`다.
- 4090 결론: 공식 Qwen3.8-27B BF16/FP8 weight는 각각 약 55.56/30.87 GB여서 단일
  24,564 MiB 4090에 적재되지 않는다. 현재 Community W4A16 exact revision은 실구동됐지만 peak
  23,825 MiB·최저 여유 254 MiB, requested-action accuracy 0.23, missing-information F1 0.00이다.
  현 profile은 고정 Shadow 기준선으로 보존하고 first-party W4A16과 별도 Qwen3-8B FP8 후보를 동일
  업무 corpus에서 비교한 뒤에만 승격한다. 자동 cross-model fallback은 계속 금지한다.
- 모델 문서 정정: Community artifact Model Card가 `cyankiwi/calibration-medium`을 `STEM and
  Agentic`으로 링크한다는 현재 사실을 반영했다. 남는 제한은 exact dataset revision/digest,
  quantization recipe와 CSight-domain 대표성이 고정·자격화되지 않았다는 점이다.
- Backend P0: `alembic check` exit 255의 evidence unique/복구 constraint name/similarity index drift,
  모든 프로세스의 DB superuser+BYPASSRLS, OIDC/password 우회, 원문·파생문구·MinIO object version의
  불완전 purge, off-host restore 미실행, 실제 model manifest activation 부재를 확인했다.
- Product/UX P0: 배정이 정책 평가 뒤 review task에만 존재하고, reviewer legacy Case/Evidence 직접-ID
  API는 tenant-wide이며, `WAITING_FOR_EVIDENCE`에서 assignee가 해제돼 두 개인 메뉴에서 사라진다.
  Case/Evidence load failure에서도 수동 결정이 열릴 수 있고 cosine `0.0`이 `-1.0`으로 변환되며,
  합성 asset이 실운영 readiness/KPI에 섞일 수 있음을 확인했다.
- 실제 검증: Core 9개 healthy, API live/ready PASS, DB Head 0023. `alembic check` FAIL(exit 255).
  provider resilience/vLLM contract 선택 24 PASS·external GPU 5 SKIP, pilot/model release/cache 7 PASS,
  상담 목록·검토 UI/client 14 PASS, LLM Compose config PASS. 접근성 Playwright는 5 viewport 모두
  fixture의 `inquiry_summary`/`policy_similarity` 누락으로 Axe 실행 전 FAIL했으므로 WCAG 위반이
  확인된 것이 아니라 접근성 release 증거가 현재 무효다.
- 미해결/다음 행동: schema drift 0부터 시작해 strict role/RLS, case-level assignment와 reviewer
  ownership, WAITING 연속성, evidence fail-closed/cosine 정확성, OIDC-only·완전 purge를 먼저 구현한다.
  그 뒤 4090 model registry/identity canary/SHADOW 100·workflow 20과 off-host restore/alert/load gate를
  통과한다. P0 전에는 실제 고객 파일럿을 시작하지 않는다.
- Git safety: Commit·Push·PR 없음. 누적 사용자 작업, 사용자 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 — Schema Drift Repair and Strict Dispatcher Requalification

- 목표/완료: 제품 준비도 감사의 첫 P0인 현재 DB/ORM drift를 과거 migration 재작성 없이 additive
  `20260830_0024_schema_drift_repair`로 수렴했다. 운영 실패 4개 테이블의 이중 naming check 18개를
  canonical 이름으로 바꾸고, 기존 DB에 빠진 evidence idempotency+SHA unique를 조건부 복구했으며,
  similarity run/group index를 ORM metadata에 선언했다.
- fail-closed migration: 두 이름이 동시에 존재하거나 어느 이름도 없으면 0024가 실패하며, unique 추가가
  기존 데이터와 충돌해도 stamp를 진행하지 않는다. downgrade는 0017 의도에 속한 evidence unique를
  파괴하지 않고 check 이름만 0023 출력 상태로 되돌린다.
- 실제 migration 증거: disposable PostgreSQL에서 빈 DB→0024와 unique가 빠진 기존 0023→0024,
  재실행 no-op을 한 테스트에서 검증하고 각 경로 `alembic check` 0을 확인했다. 현재 runtime DB에도
  0024를 적용한 뒤 호스트와 재빌드 API 컨테이너 모두 `No new upgrade operations detected`를 반환했다.
- strict Dispatcher 재평가: 오래된 runbook과 달리 현재 terminal publication failure는 run table을
  변경하지 않고 outbox만 `FAILED`로 전환한다. 0021 SECURITY DEFINER trigger가 PII-free
  `operational_failures`를 append하고, 인증된 replay/cancel 전까지 원 run은 QUEUED로 보존한다.
  disposable PostgreSQL RLS·failure recovery 10개 테스트가 통과했으며 Dispatcher의 Case/run 접근은
  계속 거부된다.
- 현재 RLS 구조: tenant_id를 가진 65/65 테이블은 ENABLE+FORCE RLS이고 세 group role은 NOLOGIN,
  NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOBYPASSRLS다. 그러나 실행 중 Compose는 여전히 owner
  superuser URL fallback과 `DATABASE_RLS_REQUIRED=false`라 파일럿 증거가 아니다.
- 검증: Ruff 전체 PASS, Pyright 0 error, unit 716 PASS. schema repair+operator read integration 2 PASS,
  RLS+failure recovery integration 10 PASS. migration offline SQL 생성 PASS. Controller rebuild 뒤 Core
  9개/API/Web/Embedding/공개 주소와 API readiness 모두 정상이다.
- 부수 정합화: operator SQL integration에 명시적 `can_view_all` 계약을 추가하고 reranker test double이
  최신 `retrieve_least_similar` port를 구현하도록 해 누적 Pyright 오류 4건을 0으로 만들었다.
- 미해결/다음 행동: 외부 secret mechanism으로 API/Worker/Dispatcher의 서로 다른 LOGIN 계정을
  provision하고 실제 Compose 전체 E2E에서 strict RLS를 활성화한다. 그 다음 case-level assignment,
  reviewer 직접 객체 권한과 WAITING_FOR_EVIDENCE 소유권을 구현한다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 17:03 KST — Signed OIDC Back-Channel Session Revocation

- 원인/완료: 외부 group/account 변경 뒤 새 로그인은 막혔지만 기존 CSight session이 살아 있던 P0-9
  공백을 닫았다. ID token의 provider `sid`, issuer-scoped subject/session SHA-256 capability, signed
  logout-token validator와 `POST /auth/oidc/backchannel-logout`을 추가했다. raw logout token·subject·
  provider session ID는 DB에 저장하지 않고 hashed append-only receipt만 남기며 JWT ID replay는 멱등
  성공한다.
- DB/권한: additive migration 0031이 기존 OIDC session subject hash를 backfill하고 provider logout
  capability용 restrictive RLS를 추가했다. API role은 receipt INSERT만 가능하고 SELECT·UPDATE·DELETE는
  불가하다. 실 PostgreSQL 검증 중 0030의 Case source-scope index가 ORM metadata에서 빠진 drift도
  발견해 정확히 보강했다.
- 실제 자격: Keycloak 26.7.2 격리 E2E가 OIDC-only, password route 404, Authorization Code+PKCE,
  REVIEWER mapping, return path, CSRF, idle expiry, group/account 새 로그인 차단과 provider session 종료
  뒤 기존 CSight session 401까지 전 gate `PASS`했다. 격리 stack은 자동 삭제됐다. 권한 변경 API만으로는
  logout이 발생하지 않으므로 고객 운영은 권한 변경→IdP session 종료→전달 재시도·경보를 묶어야 한다.
- 검증: 전체 기본 무외부망 backend 896 PASS/6 skipped/86 deselected, Ruff 전체 PASS, Pyright 0.
  Web ESLint·TypeScript·30 files/87 tests·production build와 OpenAPI sync PASS. disposable PostgreSQL
  migration/RLS/drift 1 PASS, 실제 Keycloak qualification PASS다.
- 런타임: 적용 전 `backups/pre-0031-20260830-165918.dump`를 mode 0600으로 보존했다. runtime은 Head
  0031·Alembic drift 0이며 Case 98·Report 20을 유지했다. Core 9개, PostgreSQL/RabbitMQ/MinIO
  readiness, 정책 검색과 `doongdoong.org` health가 정상이다.
- 미해결/다음 행동: 실제 고객 IdP lifecycle automation과 logout 전달 실패 경보는 아직 NOT_RUN이다.
  실제 RTX 4090 host도 연결되지 않아 Dev/Test/Shadow/workflow/soak/fault는 NOT_RUN, release eligible
  후보는 0개다. 전체 파일럿은 개인정보·부하·격리·백업 복원·경보 Gate 때문에 계속 BLOCKED다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 16:31 KST — Real Keycloak OIDC Qualification and Revocation Gap

- 목표/구성: 현재 데모 runtime과 분리된 포트 18000/18080, tmpfs PostgreSQL, digest 고정 Keycloak
  26.7.2 realm을 추가했다. public client는 Authorization Code+PKCE S256만 허용하고 direct grant와
  service account를 끈다. `OIDC_ALLOW_INSECURE_HTTP`는 local/test 명시 opt-in만 허용하며 non-local은
  설정 단계에서 거부한다.
- 실측 PASS: OIDC-only capability, password token route 404, 실제 PKCE 로그인, REVIEWER group/local
  account 매핑, `/cases` return path, CSRF 없는 logout 403/유효 token logout 204, 12초 idle expiry 401,
  그룹 제거·계정 비활성화 뒤 새 로그인 차단을 확인했다.
- 실측 BLOCKED: 그룹 제거와 계정 비활성화 모두 이미 발급된 CSight session은 계속 200이었다. 현재
  session resolve가 local account만 다시 읽고 IdP authority 변경을 받지 않기 때문이다. provider
  issuer+subject 기반의 서명 검증 back-channel revocation과 IdP 변경 운영 이벤트를 연결한 뒤 같은
  두 gate를 재통과하기 전에는 P0-9와 제한 파일럿을 완료로 표시하지 않는다.
- 재현/검증: `make qualify-oidc-keycloak`이 임시 secret 생성→Keycloak/Core migration/seed→실 E2E→
  fail-closed JSON verdict→전체 격리 stack 삭제를 한 번에 수행한다. 독립 재실행도 예상대로 exit 2,
  `BLOCKED`, 실패 gate 2개를 반환했고 종료 뒤 관련 container 0개다. OIDC 집중 unit 60 PASS와 Ruff
  대상 PASS, 전체 기본 무외부망 backend 884 PASS/91 skipped, Pyright 0이다.
- 런타임/안전: 기존 데모 Core는 9개 running, API·Web·정책 검색·`doongdoong.org` 모두 정상이다.
  기존 DB·volume·로그인 방식은 변경하지 않았고 외부 사업 동작은 0건이다. 실제 RTX 4090은 아직
  연결되지 않아 release eligible 후보는 0개다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 13:03 KST — Session log ordering correction

- 바로 위의 `Waiting Ownership and Policy Similarity Correctness` 다음 최신 세션은 이 문서 앞부분에
  기록된 `Case Intake Assignment and Reviewer Direct-object Ownership`이다. 해당 항목은 DB Head 0026,
  reviewer 직접 객체 404/RLS, 관리자 접수 배정 UI와 최신 검증 결과를 담고 있으며 현재 상태 요약도
  그 결과로 갱신했다. 과거 로그를 삭제하거나 재작성하지 않고 이 append-only 정정만 추가한다.

### 2026-08-30 — Case Intake Assignment and Reviewer Direct-object Ownership

- 목표/완료: 문의가 들어온 시점부터 관리자가 담당자를 배정·재배정할 수 있도록 Case-level
  projection, CAS version, active interval과 append-only action audit를 추가했다. 기존 Review 소유권은
  0026에서 Case로 backfill하며 과거 Review/Assignment 이력은 수정하지 않는다.
- 단일 소유권: Case 배정은 같은 transaction에서 모든 unresolved Human Review Task를 새 담당자에게
  옮긴다. PENDING/ESCALATED는 CLAIMED, WAITING_FOR_EVIDENCE는 WAITING과 담당자를 유지한다. 오래된
  expected version, 비활성/부적격 사용자, RESOLVED Case는 fail closed한다.
- 접근 통제: Reviewer는 현재 Case 담당자이거나 해당 Case의 immutable final decision 작성자인 경우에만
  Case/Evidence/Analysis/Retrieval/Grounding/Policy/Review/Resolution/Intent/Report 직접-ID 경로를 조회한다.
  앱 계층은 enumeration 방지를 위해 404를 반환하고 API-role restrictive RLS도 동일 경계를 적용한다.
  Admin/Quality Viewer는 tenant 범위에서 조회할 수 있다.
- UI: 상담원 사이드바의 `문의 대기`와 `내 문의 처리 현황` 분리는 유지했다. 관리자는 `접수된 문의`
  목록의 한 SQL projection에서 assignment version과 담당자를 받고 행 단위 추가 조회 없이 담당자를
  선택한다. 기존 Review-task 배정 UI는 제거해 소유권 기준을 Case 하나로 통일했다.
- 검토 요약: Review 상세는 사진, 문의 요약, 적용 정책과 인용 근거, 기준 0.65 최근접 3개와 cosine
  최저 3개/부적격 설명을 하나의 요약 화면으로 유지한다. 모델·정책은 권고만 생성하고 최종 결정은
  인증된 사람만 기록하며 실제 환불·메일·결제는 계속 0이다.
- 실제 검증: disposable PostgreSQL에서 migration lifecycle/schema drift, admin assign→reassign,
  stale CAS, active interval 1개, append-only action, open Review 상속, 이전 담당자 0행/새 담당자 1행 RLS를
  통과했다. unit+contract 812 PASS, 외부 embedding/reranker 2 SKIP, 관련 integration 7 PASS, Ruff와
  Pyright 0이다. Web lint/typecheck, Vitest 76 PASS, production build, 접근성 5 viewport 포함 Playwright
  11/11 PASS다.
- 런타임: 현재 DB Head `20260830_0026_case_assignment_ownership`, `alembic check` 0. 최신 API/Web/세
  worker lane/dispatcher 이미지를 재생성했고 Core 9개가 healthy다. 실제 admin password login,
  operator Case projection의 assignment version, assignment GET 200과 `doongdoong.org/login` 200을
  확인했다.
- ADR/계약: Accepted ADR-0111과 Architecture/API/Security 문서를 갱신하고 OpenAPI snapshot/generated
  type을 현재 runtime과 동기화했다.
- 미해결/다음 행동: 실제 IdP OIDC 로그인, 민감 원문·파생문구·MinIO version 완전 삭제, 실제 고객
  이미지 security adapter, 20세션/20워크플로와 120초 모델 격리 부하, off-host WAL·MinIO 복원 훈련,
  경보 전달과 4090 모델 identity/SHADOW 자격은 남아 있다. 이 Gate 전 실제 고객 파일럿은 BLOCKED다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 — Strict Runtime Login Activation and Accessibility Contract Repair

- 목표/완료: 기본 one-click 시연 경로를 깨지 않고 제한 파일럿에서 선택할 실제 non-bypass DB
  로그인 경로를 구현했다. API·Worker·Dispatcher는 비밀번호 없는 URL과
  `DATABASE_PASSWORD_FILE`을 조합하며 inline password와 secret file 동시 설정은 fail closed한다.
- secret/provisioning: `scripts/provision_postgres_runtime_logins.py`는 0600 이하, 한 줄, 32~4096 byte,
  서로 다른 비밀번호 파일만 허용한다. 세 LOGIN의 unsafe flag와 migration group role을 검증하고
  password rotation·membership을 transaction으로 적용한다. 비밀번호 CLI 인자, 전체 URL, DB 오류
  세부를 출력하지 않는다.
- strict Compose: `infra/compose.rls.yml`은 API, 세 Worker lane, Dispatcher에 서로 다른 Docker secret과
  password-less URL을 주고 `DATABASE_RLS_REQUIRED=true`를 강제한다. `make up-rls`와
  `make provision-runtime-logins`를 추가했으며 기존 `make up`과 macOS controller는 시연 호환 모드로
  유지했다.
- 실제 검증: disposable PostgreSQL에서 실제 LOGIN 3종을 만들어 current_user, guard, RLS missing
  context, Dispatcher outbox-only 접근을 검증한 5개 integration이 PASS했다. 현재 Compose에서도
  API=`csight_api_login`, Worker 3개=`csight_worker_login`, Dispatcher=`csight_dispatcher_login`으로
  재기동해 모든 health를 통과했고 실제 reviewer password login, `/auth/me`, `/operator/cases`가 모두
  200을 반환했다.
- UI 회귀 복구: Playwright fixture가 새 필수 `inquiry_summary`와 정책 cosine 최근접/최저 3개씩을
  누락하던 문제를 고쳤다. Web lint, TypeScript typecheck, 5개 viewport 접근성+5개 업무 시나리오
  Playwright가 10/10 PASS했다.
- 전체 회귀: `git diff --check`, Ruff lint/format, Pyright 0 error, 기본 unit 824 PASS, Web Vitest
  76 PASS와 production build PASS, strict login+schema disposable PostgreSQL integration 6 PASS다.
- 안전한 종료 상태: qualification용 임시 비밀 파일 6개와 임시 디렉터리 2개를 삭제했다. 데이터
  volume은 건드리지 않았고 API/Worker/Dispatcher/Web을 기본 Compose로 재생성해 현재 API DB 사용자가
  다시 `csight`임을 확인했다. 로컬 Core health와 `doongdoong.org` Web health는 정상이다.
- 미해결/다음 행동: terminal failure·replay·lease recovery를 실제 LOGIN overlay 한 실행에서 묶는
  release suite와 API/Worker 최소 권한 축소는 남아 있다. 다음 제품 P0은 정책 실행 전에도 존재하는
  case-level assignment, reviewer 직접-ID API ownership, WAITING_FOR_EVIDENCE 담당자 연속성이다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 — Waiting Ownership and Policy Similarity Correctness

- 목표/완료: 제품 감사 P0-5와 P0-7의 핵심 런타임 계약을 additive migration
  `20260830_0025_waiting_owner_and_similarity_contract`로 닫았다. 자료 요청은 담당자와 활성 배정
  구간을 보존하고, 같은 담당자의 `CLAIMED`로 재개한다. 관리자는 명시적 override로 재개할 수 있지만
  담당자를 조용히 바꾸지 않는다.
- 기존 데이터 안전성: 과거 방식으로 담당자가 지워진 대기 행은 최신 historical assignment를 찾아
  새 `WAITING_OWNER_RECOVERY` 활성 구간을 append한다. 과거 release timestamp는 수정하지 않으며
  복구할 담당자가 없는 대기 행이 있으면 migration이 fail closed한다. 적용 전 runtime 대기 행은 0건이었다.
- 유사도 계약: 유효한 cosine `0.0`을 `-1.0`으로 바꾸던 truth-value fallback을 제거했다.
  `NEAREST`는 버전된 설명 기준 `0.65`와 절대 거리가 가까운 3개, `LEAST`는 cosine이 가장 낮은
  3개로 고정했다. 동점은 높은 cosine과 안정적인 clause identity 순이며 모델 호출 추가는 없다.
- ADR/문서: Accepted ADR-0110, Architecture/API 계약, 상태 머신, 제품 준비도 감사를 같은 의미로
  정합화했다. similarity는 정책 불적격 판정이나 학습 라벨이 아니며 사람만 최종 결정을 만든다.
- 검증: 실제 PostgreSQL WAITING lifecycle 1 PASS, schema repair/operator read/exact-cosine integration
  3 PASS, Ruff 전체 check PASS, app/tests/alembic/scripts format PASS, Pyright 0 error, 기본 unit
  820 PASS. Web lint/typecheck, Vitest 76 PASS, production build, 접근성 5 viewport+업무 시나리오
  Playwright 10/10 PASS. 재빌드 후 DB Head 0025/check 0, Core 9개/API/Web/Embedding과
  `doongdoong.org` 모두 정상이다.
- 미해결/다음 행동: 실제 제품 P0의 다음 순서는 정책 검색 성공 여부와 무관한 case-level
  assignment, admin assign/reassign/unassign CAS+append-only audit, 이후 review task owner 상속과
  상담원 직접-ID Case/Evidence/Analysis/Workflow/Report 404 방어다. 자료 제출을 포함한 동일 담당자
  브라우저 E2E도 이 배치의 release gate에 포함한다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 13:03 KST — Latest session pointer

- 최신 세션은 위에 기록된 `Case Intake Assignment and Reviewer Direct-object Ownership`이며 현재
  DB Head는 0026이다. 같은 날짜의 0024·strict login·0025 기록은 과거 관측값으로 보존한다.

### 2026-08-30 13:13 KST — MinIO Versioned Evidence Erasure

- 목표/완료: 개인정보 P0-8의 명확한 저장소 공백을 줄였다. MinIO bucket versioning이
  켜져 있어도 key 삭제만으로 delete marker를 추가하지 않고, exact Evidence key의 payload
  version과 delete marker를 모두 불투명 version ID로 영구 삭제한다.
- Fail-closed 계약: version inventory 실패·절단, 개별 삭제 실패, 삭제 후 남은 version 하나라도
  있으면 `EVIDENCE_PURGED`를 기록하지 않고 blocked로 종료한다. 삭제 요청 event는 먼저
  commit하며 완료 event는 재조회 0개 후에만 append한다.
- 검증: 전체 unit+contract 814 PASS(외부 embedding/reranker 2 SKIP), MinIO/lifecycle 선택 27 PASS,
  실제 versioning bucket에서 같은 test key를 두 번 저장한 뒤
  delete marker를 추가하고 v1/v2/marker 3개를 전부 지운 통합 2 PASS, 선택 Ruff/format/Pyright
  0이다. 통합 검증은 임시 합성 key만 사용했고 기존 시연 Evidence와 volume은 수정하지 않았다.
- 문서: ADR-0108, Security/Operations, Product Readiness Audit에 version 영구 삭제와 재조회
  계약을 반영했다.
- 미해결/다음 행동: LLM claims/source quote/summary, generated query, grounded explanation, terminal
  report/communication 문구는 무결성 hash와 보존 규칙을 함께 바꾸는 additive migration이 필요하다.
  tenant onboarding retention, scheduler/alert, backup 만료, legal hold, 실제 ClamAV도 남아 있어
  P0-8은 완료로 표시하지 않는다.
- Handoff/Git safety: 다음은 파생 문구의 정확한 보존 범위와 hash 재계산/비가역 receipt
  계약을 ADR·migration·synthetic marker E2E로 먼저 고정한다. Commit·Push·PR 없음. 누적
  작업트리, 사용자 문서, 투자자 SVG와 `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 13:30 KST — Customer-derived Analysis Text Erasure

- 목표/완료: 원문 만료 뒤에도 남던 LLM v1/v2 claim·source quote·summary, extracted action quote,
  생성 정책 query, grounded statement/condition, analysis/retrieval/grounding provider failure 문구를
  같은 privacy lifecycle transaction에서 tombstone 또는 빈 구조로 지우는 0027을 구현했다.
- 보존 경계: analysis run/stage/attempt identity, 상태·시각·token/latency, model/prompt/policy/index
  version, rank/similarity/metric, opaque hash와 회사 정책 citation은 유지한다. 일반 analysis repository는
  계속 update/delete를 노출하지 않고 인증된 Admin lifecycle 경로만 bounded redaction을 수행한다.
- DB 강제: `analysis_text_purged_at = purged_at` projection과 deferred constraint trigger를 추가했다.
  이미 삭제된 Case에 비-tombstone 분석·검색·grounding 문구나 failure message가 삽입/복원되면 transaction이
  실패한다. 이미 0026에서 원문만 삭제된 행도 upgrade 중 파생 문구를 먼저 지운다. 실제 이전 버전 시험에서
  기존 deferred trigger event 때문에 DDL이 막히는 순서 결함을 발견해, 기존 parity 검사를 먼저 강제 실행한
  뒤 constraint를 교체하도록 수정했다.
- 검증: 전체 unit+contract 817 PASS(외부 embedding/reranker 2 SKIP), Ruff 전체·format 480 files·
  Pyright 0. disposable PostgreSQL blank→latest runtime purge와 0026 already-purged→0027 backfill,
  synthetic PII marker 0, tombstoned result schema read, 파생 문구 재삽입 거부, downgrade 거부를 통과했다.
  schema/privacy migration과 실제 versioned MinIO를 합친 선택 integration 6 PASS다.
- 런타임: 현재 DB Head `20260830_0027_analysis_text_erasure`, `alembic check` 0. Core 이미지를 다시
  빌드해 API·세 worker lane·Dispatcher를 교체했고 전체 9개 healthy, API ready, Web health,
  `doongdoong.org/login`이 정상이다. 기존 시연 payload의 purged row는 적용 전 0건이라 화면 데이터는
  변경되지 않았다.
- ADR/문서: Accepted ADR-0112, Architecture, Security/Operations, Privacy runbook, Product Readiness
  Audit를 현재 계약과 일치시켰다.
- 미해결/다음 행동: 사람 rationale, terminal Review Report/communication, Case commerce attributes는
  법적 보존 class와 redacted hash/receipt 계약 없이 변경하지 않았다. tenant onboarding retention,
  scheduler/alert, log 전수 marker scan, backup expiry/legal hold, 실제 ClamAV도 남아 있어 P0-8 전체는
  아직 미완료다. 다음 제품 작업은 이 보존 class 설계와 Qwen 4090 후보 artifact 비교 gate다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 13:35 KST — Assigned Inquiry Workspace Revalidation and Web Refresh

- 목표/확인: 요청한 관리자 Case 담당자 배정·재배정, 일반 담당자의 `문의 대기`·
  `내 문의 처리 현황` 분리, 단일 `문의 검토 요약`, 설명 기준 0.65에 가장 가까운 3개와
  cosine이 가장 낮은 부적합 3개 표시가 ADR-0109·0110·0111 계약과 일치하는지 재검증했다.
- 권한/데이터 경계: reviewer 목록은 UI filter가 아니라 서버 SQL에서 현재 Case 배정자 또는
  immutable decision의 `decided_by`로 제한된다. 실제 PostgreSQL에서 재배정 시 기존 담당자
  접근이 즉시 제거되고 열린 Review owner가 같이 이동하며, 앱 조건을 빼도 RLS가 조회를
  차단함을 확인했다.
- 검증: 담당자 화면 집중 Vitest 10 PASS, 배정·operator read·정책 유사도 집중 unit 42 PASS,
  disposable PostgreSQL 재배정/RLS·목록 단일 SQL integration 2 PASS. Web 전체 ESLint,
  TypeScript, OpenAPI sync, Vitest 76, production build가 모두 PASS했다.
- 런타임: 검증된 최신 Web 이미지로 상담원 화면만 무중단 재생성했다. Named Volume과
  시연 데이터는 변경하지 않았다. Web healthy, API ready, `https://doongdoong.org/login`
  HTTP 200을 확인했다.
- 미해결/다음 행동: 이 작업 범위의 새 미해결 사항은 없다. 실제 파일럿 승격 차단 사유와
  다음 순서는 상단의 개인정보 보존 class 설계와 Qwen 4090 artifact 비교 gate를 그대로 따른다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 13:49 KST — RTX 4090 Qwen Candidate Release Gate

- 목표/완료: 공식 Qwen artifact와 현재 Community 27B INT4를 같은 이름으로 혼동하거나 과거
  측정을 새 runtime에 승계하지 못하도록, exact revision·weight bytes·runtime image digest·serving
  profile·qualification evidence를 하나의 strict candidate matrix로 고정했다.
- 현재 판정: 공식 Qwen3.8-27B BF16/FP8은 weight bytes만으로 단일 24,564 MiB 4090을 넘어
  `HARDWARE_EXCLUDED`다. 기존 Community W4A16/vLLM 0.26.0은 출처·평가 계약·20 workflow·2 GiB
  headroom이 부족해 `SHADOW_ONLY`다. 같은 artifact의 vLLM 0.28.0 runtime challenger와 공식
  Qwen3-8B-FP8 model challenger는 `PENDING_QUALIFICATION`이다.
- 평가 계약: action 입력과 gold가 모호한 legacy v1은 역사적 진단으로만 남기고, release gate는
  합성 `llm_extraction_v2/2.0.0` 160건의 exact file digest를 사용한다. package provenance,
  100-case Shadow, 20/20 terminal, 안전률 0, 최소 free VRAM 2 GiB, p95 5초, 25 tok/s, 20분 soak,
  OOM/restart/stall/duplicate 0을 전부 통과해야만 release eligible이다.
- 구현/문서: technology-neutral platform contract와 검증 CLI, Make target, unit test 6개,
  Accepted ADR-0113, model manifest/LLM runbook/README/Product Audit를 추가·갱신했다. 공식 base에서
  CSight가 recipe/calibration까지 소유하는 27B W4A16을 quality-first 후보로 명시했으며, 공식
  8B FP8은 자동 fallback이 아닌 별도 Shadow 후보로 고정했다.
- 검증: candidate matrix/dataset digest 검증 PASS, `--require-eligible` 예상 exit 1,
  관련 model/release/execution unit 10 PASS, Ruff PASS, Pyright 0. 이번 배치에서는 4090 endpoint가
  설정되지 않아 다운로드·GPU 실행·model activation은 수행하지 않았다. 현재 Core mock과 시연
  runtime/volume도 변경하지 않았다.
- 미해결/다음 행동: 실제 vLLM v2 evaluator를 placeholder에서 executable harness로 연결하고,
  4090에서 owned 27B W4A16과 공식 8B FP8을 각각 측정해 matrix evidence를 채운다. 그 뒤 signed
  manifest persistence, worker startup identity canary, 관리자 atomic activation/rollback을 연결한다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 14:05 KST — Executable Qwen Extraction v2 Qualification Harness

- 목표/완료: endpoint가 설정되면 종료하던 `evaluate_extraction_v2_qwen.py` placeholder를 실제
  vLLM Extraction v2 평가기로 교체했다. frozen matrix의 candidate ID, served name, artifact revision,
  production prompt hash, 전체 160건 dataset file digest와 temperature 0을 일치시켜야 호출한다.
- Dev/Test 규율: 합성 Dev 120건은 반복 가능하되 현재 절대 품질·안전 기준을 모두 통과한 결과
  package만 profile freeze할 수 있다. Freeze는 metrics/profile/observation/manifest와 result digest를
  다시 검증한다. Test 40건은 frozen profile과 exact inputs가 같을 때 명시적 opt-in으로 한 번만
  실행하며 기존 result manifest가 있으면 재실행을 거부한다.
- 개인정보/안전: 결과에는 합성 record ID, 성공 여부, exact 여부, latency/token과 bounded error code만
  기록한다. input text, model prediction, provider response/request ID, prompt/reasoning은 저장하지 않는다.
  결과 observation에 금지 key가 있거나 count/digest가 다르면 동결을 거부한다. 사람 최종결정과 실제
  사업 동작 경계는 변경하지 않았다.
- 성능 증거: runner가 GPU host에 있을 때 `nvidia-smi`의 name/total/free를 200ms 간격으로 수집해
  최저 free VRAM을 남긴다. remote client나 probe 실패는 `NOT_AVAILABLE`로 기록되며 2 GiB headroom
  통과 증거로 사용할 수 없다. latency p50/p95와 직렬 output tok/s도 같은 결과에 기록한다.
- 검증: harness unit 9 PASS, harness+candidate/release unit 15 PASS, 전체 기본 무외부망
  850 PASS/89 deselected, Ruff 전체 PASS, format 504 files, Pyright 0. Mac 기본 설정에서는
  `SKIPPED_EXTERNAL_LLM_NOT_AVAILABLE`을 반환했고 외부 호출은 0회였다. Candidate matrix 검증은
  PASS, release-required gate는 release eligible 0개로 계속 예상 차단이다.
- 문서/다음 행동: Accepted ADR-0113, README, LLM node 안내, Product Audit와 별도
  `QWEN4090_QUALIFICATION_GUIDE.md`에 실행 순서와 불충분 증거 경계를 기록했다. 다음은 exact 4090
  host에서 후보 하나의 Dev를 실행하는 것이며, 그 뒤에도 100 application Shadow·20 terminal
  workflow·soak/fault·signed activation은 별도 관문으로 남는다.
- Git safety: Commit·Push·PR 없음. Core runtime과 volume, 사용자 문서, 투자자 SVG 및
  `kaputt_best_vision_architecture.md`를 변경하지 않았다.

### 2026-08-30 14:13 KST — Matrix-locked RTX 4090 Shadow Candidate Launcher

- 원인/완료: 기존 `compose.llm.yml`은 Community 27B/vLLM 0.26.0 기준선에 고정되어 있어 matrix의
  vLLM 0.28.0 Runtime Challenger와 공식 Qwen3-8B-FP8 Model Challenger를 수동 편집 없이 실행할
  수 없었다. 두 후보 전용 JSON Compose overlay와 matrix drift verifier를 추가했다.
- 고정 범위: verifier가 image tag+digest, artifact/revision, served alias, context, max sequences,
  GPU memory utilization, KV dtype, language-only/eager, reasoning parser, thinking-disabled payload,
  candidate ID와 `SHADOW` label을 matrix에서 계산한 값과 exact 비교한다. runnable role에 해당하는
  profile이 빠지거나 하나라도 추가돼도 실패한다.
- 실행 안전성: launcher는 두 candidate ID만 allowlist하고 private env regular-file/key/bind 조건과
  전체 profile verifier를 먼저 통과시킨다. Docker health 뒤 container 내부에서 API key를 argv/log에
  출력하지 않고 authenticated `/v1/models`를 조회하며 exact selected alias 하나만 허용한다. 한
  Compose service만 사용하므로 단일 4090에서 후보 두 개를 동시에 올리지 않는다. Core PRIMARY나
  업무 DB를 변경하지 않는다.
- 검증: profile verifier PASS, 두 overlay의 실제 `docker compose config --quiet` PASS, 두 후보
  launcher dry-run PASS, 비허용 candidate 거부 포함 새 unit 6 PASS. 누적 Qwen profile/harness/release
  unit 21 PASS. 전체 기본 무외부망 856 PASS/89 deselected, Ruff 전체 PASS, format 506 files,
  Pyright 0이다. 실제 GPU image pull/start는 하지 않아 모델 성능이나 vLLM 0.28.0 현장 성공을 주장하지
  않는다.
- 미해결/다음 행동: 4090 node에서 후보 하나를 명시적으로 시작해 alias canary와 Dev 120건을
  실행한다. 결과가 기준을 통과해야 freeze/Test로 간다. 별도로 signed model manifest persistence,
  Worker startup enforcement, 100 application Shadow, 20 terminal workflow, soak/fault와 관리자
  activation/rollback이 남아 있다.
- Git safety: Commit·Push·PR 없음. Mac Core runtime·volume과 사용자 소유 문서를 변경하지 않았다.

### 2026-08-30 14:25 KST — Assigned Inquiry Navigation and Summary Revalidation

- 목표/완료: 관리자 Case 담당자 배정·재배정, reviewer-only의 현재 배정 문의와 본인 완료 문의
  분리, 단일 검토 요약, 설명 기준 최근접 3개와 최저 cosine 3개 표시를 다시 대조했다. 담당자
  상세의 뒤로가기 문구도 기존 `검토함` 대신 `내 문의 처리 현황`으로 맞췄다.
- 회귀 고정: reviewer 사이드바의 `문의 대기`·`내 문의 처리 현황`, `/cases?view=my`,
  `/reviews?view=complete`, 관리자 배정 UI 비노출, 사진·문의 요약·정책 근거·유사도 3+3의 단일
  화면 표시를 새 컴포넌트 테스트로 고정했다.
- 검증: 관련 Web Vitest 14 PASS, ESLint·TypeScript·production build PASS. 배정·operator read·
  유사도 backend unit 8 PASS, Ruff 집중 검사 PASS. disposable PostgreSQL에서 WAITING ownership과
  Case 재배정/RLS 2 PASS, runtime DB Head `0027`을 확인했다.
- 런타임: 최신 Web 이미지만 다시 빌드·재생성했다. Web health 정상이며 로컬 브라우저에서 공개
  로그인 화면을 확인했다. PostgreSQL·RabbitMQ·MinIO volume과 시연 데이터는 변경하지 않았고
  Core 9개는 healthy다. 인증 정보를 입력하지 않아 실제 담당자 로그인 수동 확인은 수행하지 않았다.
- 미해결/다음 행동: 이 요청 범위의 새 코드 미해결은 없다. 시연에서는 관리자가 담당자를 배정한 뒤
  담당자 계정의 두 메뉴를 순서대로 보여준다. 전체 제품 Gate는 상단 Qwen 4090 실제 후보 실행과
  개인정보 보존·복구 관문을 그대로 따른다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 14:48 KST — Signed Qwen Release Activation and Worker Identity Gate

- 목표/완료: matrix PASS가 곧바로 모델 활성화가 되는 빈틈을 닫았다. strict
  `llm_release_manifest/1.0.0` canonical JSON과 Ed25519 서명 검증, immutable registration,
  tenant·task·PRIMARY/SHADOW별 append-only activation event, idempotent replay와 expected-current
  CAS를 추가했다. rollback은 과거 release를 가리키는 새 event이며 기존 기록은 수정하지 않는다.
- Worker fail-closed: 실제 vLLM 적용 시 artifact revision/content, runtime image, dependency lock,
  SBOM, served alias/version, prompt name/version/hash와 input/output schema를 active signed release와
  exact 비교한다. active 없음·서명 오류·identity mismatch는 retry하지 않는 terminal failure로
  기록되고 provider 호출은 0회다. non-local vLLM은 enforcement 없이 설정할 수 없다.
- 관리자 계약: `/api/v1/operations/model-releases` 등록,
  `/model-releases/{release_id}/activate` 활성화/rollback,
  `/model-activations/active` 조회를 admin-only·no-store로 추가했다. public verification key가
  설정되지 않으면 503이며 private signing key를 서버에 두는 계약은 추가하지 않았다.
- DB/보안: migration 0028은 API SELECT/INSERT, Worker SELECT, Dispatcher 0 privilege와 tenant RLS를
  적용하고 두 테이블의 UPDATE/DELETE를 trigger로 차단한다. current는 가장 최신 event로 계산한다.
- 검증: 전체 기본 무외부망 863 PASS/90 skipped, Ruff 전체 PASS, format 대상 496 files, Pyright 0,
  OpenAPI 관리 경로 3개 확인. disposable PostgreSQL에서 full head upgrade와 Alembic drift 0,
  registration replay, 같은 시각 activation chain/replay/CAS, Worker SELECT·Dispatcher 거부,
  append-only UPDATE 차단 1 PASS. 실행 중 시연 DB·Core는 건드리지 않았고 실제 4090
  호출·서명·활성화는 0회다.
- 미해결/다음 행동: release eligible 후보와 승인된 signing key가 아직 없으므로 enforcement는
  의도적으로 false다. 4090에서 Dev→freeze→sealed Test→100 Shadow→20 terminal→soak/fault를 모두
  통과한 뒤에만 manifest를 실제 서명·등록한다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 14:55 KST — Assigned Inquiry Summary Evidence Fail-closed

- 목표/완료: 관리자 배정·재배정, reviewer-only `문의 대기`와 `내 문의 처리 현황`, 단일
  `문의 검토 요약`, 참고선 최근접 3개와 최저 cosine 3개 표시를 재확인했다. 최저 유사도 항목은
  순위와 참고선 거리로 부적격 이유를 항목별 표시한다.
- 안전성 수정: Case·Evidence 메타데이터 조회 실패를 `첨부 사진 없음`과 구분해 명시적 오류와
  재시도 버튼을 표시한다. 이 상태에서는 빠른 확인창뿐 아니라 상세 수동 결정도 비활성화하며,
  추가 자료 요청 경로는 유지한다.
- 검증: 관련 화면 Vitest 15 PASS, Web 전체 81 PASS, ESLint·TypeScript·production build PASS,
  초기 JS gzip 82.17KB. 배정·개인 큐·migration backend 집중 12 PASS, Ruff 집중 PASS.
- 런타임: DB·worker·volume은 유지하고 Web 이미지만 재빌드·재생성했다. 14:56 KST Core 9개가
  모두 healthy이고 로컬·`https://doongdoong.org/web-health`가 모두 `ok`다.
- 미해결/다음 행동: 메타데이터를 읽은 뒤 개별 이미지가 일부 실패·손상된 상태를 결정 Gate로
  집계하는 P0-6 후속 E2E는 남아 있다. 전체 제품 Gate인 실제 4090 후보 실행과 개인정보
  보존·복구 관문도 변함없다.
- Git safety: Commit·Push·PR 없음. 실행 중 DB/Core와 volume은 변경하지 않았고, 사용자 문서,
  투자자 SVG와 `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 15:09 KST — Strict RTX 4090 Host and Artifact Preflight

- 목표/완료: 후보 이름·컨테이너 health만으로 4090 실행을 시작하던 공백을 닫았다. technology-neutral
  `qwen4090_host_evidence/1.0.0`과 `qwen4090_host_preflight/1.0.0`, live collector와 Make 명령을
  추가하고 allowlisted launcher가 Compose 전에 strict preflight를 반드시 통과하도록 연결했다.
- 호스트 Gate: Linux x86_64, 단일 RTX 4090, compute capability 8.9, exact 24,564 MiB, 최소 2 GiB
  free, 기존 compute process 0, Docker NVIDIA runtime, owner-only 0600 env·0700 evidence directory,
  로컬에 실제 할당된 Tailscale CGNAT 주소, 32자 이상 non-placeholder key, HF Hub·Transformers
  offline mode를 각각 fail closed한다.
- 패키지 Gate: tag가 아닌 local runtime image digest, absolute host cache의 exact Hugging Face
  revision, cache 밖으로 나가는 symlink 차단, 모든 snapshot file content hash, safetensors weight
  byte parity, dependency lock, CycloneDX/SPDX JSON SBOM, quantization recipe와 calibration digest를
  수집한다. Hash 중 파일 변경도 거부한다. lock은 exact image를 pull/network 없이 실행한 canonical
  `pip freeze`와 일치해야 하고, SBOM은 image digest, recipe/calibration은 artifact revision을 식별해야 한다.
- 개인정보/불변성: raw GPU UUID·API key·bind IP·hostname·host path는 결과에 저장하지 않고 UUID와
  bind IP는 SHA-256만 남긴다. 결과 JSON은 owner-only mode로 create-once하며 같은 파일 overwrite를
  거부한다. matrix digest가 null인 첫 수집은 `EVIDENCE_COLLECTED_NOT_PINNED`이고, reviewed matrix와
  exact 일치한 `PASS`만 live launcher가 허용한다.
- 캐시 경계: 후보 환경은 `LLM_MODEL_CACHE_DIR` absolute host bind를 사용해 시작 전 bytes 검증이
  가능하다. 변수를 생략한 역사적 baseline은 기존 `qwen38-model-cache` named volume을 계속 보존한다.
- 검증: host preflight·profile·release 집중 20 PASS, injected probe로 무GPU/무외부망 수집·immutable
  output·잘못된 GPU/bind/busy host·HF blob symlink escape를 검증했다. 두 Compose config, launcher
  dry-run, bash syntax PASS. 전체 기본 871 PASS/90 deselected, Ruff 전체 PASS, format 519 files,
  Pyright 0이다.
- 런타임/미해결: 15:09 KST Mac Core 9개 running, API dependency health와 Web health `ok`; Core DB,
  volume, provider 설정은 변경하지 않았다. 실제 4090 host가 현재 연결되지 않아 real snapshot hash,
  image inspect, Dev/Test/Shadow/workflow/soak/fault는 NOT_RUN이고 후보는 release eligible 0개다.
- Git safety: Commit·Push·PR 없음. 사용자 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 15:22 KST — Evidence Image Decode Fail-closed

- 목표/완료: 문의 검토 요약에서 Case와 Evidence 메타데이터뿐 아니라 필수 이미지 각각의
  인증 조회와 브라우저 decode가 모두 성공해야 최종 결정을 허용하도록 P0-6 UI 경계를 닫았다.
  하나라도 로딩 중·조회 실패·사용 불가·손상 상태이면 수동 결정과 빠른 확인을 함께 차단한다.
- 복구/상태: 실패 이미지는 같은 화면에서 다시 시도할 수 있고, 새 Blob을 실제로 decode한 뒤에만
  잠금이 해제된다. 증거가 원래 0장인 문의는 오류와 구분해 계속 검토할 수 있다. 요약 화면과
  확인 대화상자의 표시 상태는 분리해 한쪽 decode 실패가 다른 쪽 정상 상태를 오염시키지 않는다.
- 검증: Evidence/Review 상세 집중 Vitest 13 PASS. Web 전체 ESLint·TypeScript·29 files/86 tests와
  production build PASS, 초기 JS gzip 82.17KB, 검토 상세 chunk gzip 11.73KB다. 정상·일부 실패·
  재시도 후 decode·빈 증거·Case 조회 실패를 컴포넌트 수준에서 고정했다.
- 런타임: DB·Worker·volume은 유지하고 Web 이미지만 재빌드·재생성했다. Core 9개가 모두
  healthy이고 로컬·`https://doongdoong.org/web-health`가 모두 `ok`, API dependency readiness도
  PostgreSQL·RabbitMQ·MinIO 전부 `ok`다.
- 미해결/다음 행동: 실제 API와 인증 브라우저에서 손상/부분 실패 응답을 주입하는 live E2E는
  아직 NOT_RUN이므로 파일럿 자격 증거로 승격하지 않는다. 실제 4090 Dev/Test/Shadow/workflow/
  soak/fault 실행과 개인정보 보존·복구 관문도 그대로 남아 있다.
- Git safety: Commit·Push·PR 없음. DB·Worker·volume, 사용자 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 15:42 KST — Terminal Customer Content Erasure

- 목표/완료: 개인정보 P0-8에서 남아 있던 사람 결정·행동 자유형 내용, Case attributes, terminal
  Review Report의 고객·주문·배송 snapshot, simulated communication recipient/subject/body와
  Case Resolution failure prose를 원문 만료 transaction에 포함했다. 정형 ID·상태·reason code·
  직원 identity·정책/모델/프롬프트/인덱스 버전·qualification·dry-run side-effect=false는 보존한다.
- 무결성/DB 강제: decision/report/communication의 현재 content hash를 redacted payload 기준으로
  다시 계산하고 PII-free lifecycle event에 resource count, opaque pre/post hash 전환과 deterministic
  receipt digest를 남긴다. `terminal_content_purged_at = purged_at` projection과 deferred PostgreSQL
  triggers가 삭제된 Case에 customer-derived terminal content를 다시 쓰거나 새로 넣는 commit을 막는다.
- Migration/호환: additive 0029가 이미 0027에서 삭제된 Case도 online backfill하며 복원 불가능한
  삭제 뒤 downgrade는 명시적으로 거부한다. Accepted ADR-0114와 Architecture, Security/Operations,
  Privacy runbook, Product Audit를 동기화했다.
- 검증: 전체 기본 무외부망 874 PASS/91 skipped, Ruff 전체 PASS, Python format 517 files, Pyright 0.
  실제 disposable PostgreSQL 상담 workflow 6 PASS에서 Decision→terminal Report→communication→expiry
  purge→redacted aggregate read→synthetic marker 0→재삽입 거부를 확인했다. blank head migration과
  model activation persistence 1 PASS다.
- 런타임: 적용 전 local DB dump를 `backups/pre-0029-20260830-154057.dump`에 mode 0600으로 보존했다.
  실행 DB의 기존 purged Case는 0건이었고 0027→0028→0029 upgrade와 Alembic drift 0을 확인했다.
  Core API·Dispatcher·세 Worker를 새 이미지로 교체한 뒤 9개 모두 healthy, API dependencies와
  local/public Web health `ok`; Case 98·Report 20은 보존되고 release manifest는 예상대로 0개다.
- 미해결/다음 행동: 이 배치는 terminal DB content 경계만 닫았다. tenant onboarding retention,
  자동 scheduler/alert, log-wide marker scan, off-host backup expiry/legal hold와 실제 ClamAV는 남아
  있어 P0-8 전체를 완료로 표시하지 않는다. Qwen은 실제 4090 host evidence와 Dev/Test/Shadow/
  workflow/soak/fault가 NOT_RUN이고 release eligible 후보 0개다.
- Git safety: Commit·Push·PR 없음. 사용자 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 16:02 KST — Immutable Pilot Data Provenance and Honest Metrics

- 원인/완료: 합성 terminal report와 learning asset이 실운영 KPI·drift readiness에 함께 집계되어
  합성 60건만으로 준비 완료처럼 보일 수 있던 P0-10을 닫았다. Case 생성 시 validated synthetic은
  `SYNTHETIC_DEMO`, 일반 유입은 fail-closed `NOT_ATTESTED`로 분류하고 provenance와 함께 저장한다.
- DB/불변성: additive migration 0030은 기존 synthetic commerce Case를 backfill하고 나머지는
  `NOT_ATTESTED`로 둔다. 허용 scope check, tenant/scope index와 update 거부 trigger를 추가했다.
  report `data_scope`와 learning asset `privacy_scope`에도 출처를 전달한다. public request는
  `PILOT_LIVE`를 주장할 수 없다.
- 집계/UI: 기본 PoC metric, SLA 해석, learning distribution, recent record와 30/60 drift readiness는
  `PILOT_LIVE`만 포함한다. API와 화면은 eligible/excluded/total을 분리하고 합성·Shadow·Imported·
  미확인 데이터가 성과로 보이지 않게 했다. 합성 60건만 있는 unit 계약은 readiness=false다.
- 검증: Ruff 전체 PASS, Pyright 0, 전체 backend 878 PASS/91 skipped. Web TypeScript, 29 files/86 tests,
  production build와 OpenAPI snapshot/generated sync PASS; 초기 JS gzip 82.17KB다. 적용 전 DB dump를
  `backups/pre-0030-20260830-1555.dump` mode 0600으로 보존하고 runtime을 0030으로 migration/rebuild했다.
- 실제 상태: 실행 DB Case 98건은 `NOT_ATTESTED` 77, `SYNTHETIC_DEMO` 21, `PILOT_LIVE` 0이다.
  실제 PostgreSQL update probe가 immutable trigger에서 거부되고 live count 0이 유지됐다. Core 9개,
  API, Web, embedding과 `doongdoong.org` health는 정상이다.
- 미해결/다음 행동: trusted pilot intake/attestation의 운영 승인과 실제 `PILOT_LIVE` 표본은 0건이다.
  Qwen도 실제 4090 host evidence·Dev/Test/Shadow/workflow/soak/fault가 NOT_RUN이며 release eligible
  후보는 0개다. 다음 우선순위는 실제 4090 후보 실행 또는 P0-9 OIDC-only 실증이다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 16:12 KST — Non-local OIDC-only Authentication Boundary

- 원인/완료: OIDC runtime이 있어도 Sprint 1 service가 구성되면 password token route와 Bearer JWT가
  계속 활성화되던 P0-9 우회 경로를 닫았다. `LEGACY_PASSWORD_AUTH_ENABLED`는 local/test 호환
  profile에서만 허용되고 pilot/production에서 true이면 설정 검증 단계에서 API 시작을 거부한다.
- route/인증: OIDC-only process는 `POST /api/v1/auth/token`을 등록하거나 OpenAPI에 노출하지 않고
  `/auth/capabilities`가 legacy=false를 반환한다. 보호 API의 Authorization Bearer는 JWT resolver 전에
  401로 거부된다. IdP 장애 시 password fallback을 다시 여는 경로는 없다.
- UI: capability를 읽기 전 legacy form의 초기값을 false로 바꿔 비밀번호 입력이 순간 노출되지 않게
  했고, legacy=false를 받으면 메모리 compatibility token도 지운다. OIDC-only 로그인 화면은 조직
  로그인 버튼만 표시한다.
- 검증: Ruff 전체 PASS, Pyright 0, 전체 backend 880 PASS/91 skipped. Web ESLint·TypeScript,
  30 files/87 tests, production build와 OpenAPI sync PASS; 초기 JS gzip 82.18KB다. pilot injected OIDC
  runtime에서 password route 404·Bearer 401·capability false를 확인했다.
- 런타임: local demo는 의도적으로 capability `oidc=false`, `legacy=true`이고 빈 password 요청이
  422를 반환해 기존 route가 유지됨을 확인했다. 최신 image로 rebuild 후 Core 9개, embedding과
  `doongdoong.org` health가 정상이다.
- 미해결/다음 행동: 실제 시험 IdP의 로그인, group removal, account disable, session expiry, CSRF,
  reauthentication E2E는 NOT_RUN이므로 P0-9 전체 자격은 아직 아니다. 실제 RTX 4090도 동일하게
  연결되지 않아 Dev/Test/Shadow/workflow/soak/fault와 release eligibility는 미완료다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 17:03 KST — OIDC Back-Channel Qualification Closeout

- 최종 판정: 위 17:03 signed back-channel 구현 기록을 실제 Keycloak 26.7.2 전 gate `PASS`,
  disposable PostgreSQL migration/RLS/drift `1 PASS`, runtime Head 0031·drift 0으로 마감한다.
  그룹/계정 변경 뒤 IdP session 종료가 전달되면 기존 CSight session은 즉시 401이다.
- 전체 회귀: backend 896 PASS/6 skipped/86 deselected, Ruff PASS, Pyright 0; Web ESLint·TypeScript·
  87 tests·production build·OpenAPI sync PASS. mode 0600 사전 백업과 Case 98·Report 20 보존을
  확인했고 Core 9개·정책 검색·`doongdoong.org`가 정상이다.
- 남은 Gate: 고객 IdP의 권한 변경→session 종료→재시도·경보 자동화, 실제 RTX 4090 자격,
  개인정보·부하·복원·운영 경보는 NOT_RUN이다. Commit·Push·PR은 만들지 않았다.

### 2026-08-30 17:47 KST — Reviewer Personal Queue and Summary Live Closeout

- 목표/완료: 관리자는 접수 문의의 담당자를 배정·재배정하고, reviewer-only 계정은 현재 담당
  문의를 `문의 대기`, 본인이 최종 처리한 문의를 `내 문의 처리 현황`에서 분리해 보는 계약을
  재검증했다. 검토 상세는 탭 없이 사진·문의 요약·적용 정책 본문·참고선 최근접 3개·최저 cosine
  3개와 항목별 부적격 이유를 하나의 `문의 검토 요약`으로 표시한다.
- 실사용 결함 수정: 완료 문의 행의 `link` 역할을 `listitem`이 덮어쓰던 접근성 오류를 수정했다.
  React StrictMode에서 Evidence Blob URL이 실제 decode 전에 폐기되어 정상 사진도 실패로 표시되고
  최종 결정이 잠기던 수명주기를 외부 URL 생성·정리 effect로 교정했다. 비활성 최종 결정 버튼의
  색 대비도 WCAG AA 기준에 맞췄다.
- 회귀 고정: E2E fixture가 `WAITING_FOR_EVIDENCE` owner를 보존하고 실제 view filter를 따르게 했다.
  담당자 메뉴 분리→완료 문의 진입→단일 요약→정책 3+3을 새 브라우저 시나리오로 고정했으며 손상된
  fixture PNG를 정상 decode 가능한 synthetic PNG로 교체했다.
- 검증: 배정·operator read·human review·migration backend 집중 47 PASS. Web 30 files/87 tests,
  ESLint·TypeScript·OpenAPI sync·production build PASS. 브라우저 시연 7 PASS와 320·375·768·1024·
  1440px 접근성/가로 overflow 5 PASS를 직렬 실행으로 확인했다. `git diff --check` PASS다.
- 런타임: DB·Worker·volume을 유지하고 Web만 rebuild/recreate했다. 로컬과
  `https://doongdoong.org`가 동일한 `index-XlE8HXPP.js`·`index-ynQ-EElY.css`를 제공하며 Web health
  `ok`, Core 9개·정책 검색·공개 주소가 정상이고 DB Head는 `0031`이다.
- 경계/다음 행동: 실제 사업 동작은 0이고 인증 정보를 입력한 live 담당자 수동 시연은 수행하지
  않았다. 전체 제품 Gate인 고객 IdP 운영 연동, 실제 RTX 4090 Dev/Test/Shadow/workflow/soak/fault,
  개인정보·부하·복원·경보 자격은 그대로 남아 있다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 18:00 KST — RTX 4090 Hub Identity and Product Gap Revalidation

- 목표/진전: 실제 제품 전환을 위해 Qwen 4090 후보와 현재 운영 설정의 제품 격차를 다시
  실측했다. Hugging Face 고정 revision을 bounded HTTPS metadata로 검사하는
  `audit_qwen4090_hub.py`와 `make audit-qwen4090-hub`를 추가했다. 모델 weight는 다운로드하거나
  활성화하지 않으며 optional `HF_TOKEN`도 출력하지 않는다.
- Hub 증거: 후보 5개가 정확한 commit·Apache-2.0 license·quantized base lineage·safetensors LFS
  identity·byte 합계와 일치해 모두 `HUB_REVISION_VERIFIED`였다. 공식 27B BF16
  55,563,006,776 bytes와 FP8 30,866,866,928 bytes는 단일 4090에서 계속 hardware excluded다.
  Community 27B W4A16은 21,018,000,928 bytes, 공식 Qwen3-8B-FP8은 9,436,628,784 bytes다.
- 제품 판정: matrix는 27B baseline `SHADOW_ONLY`, 두 실행 challenger
  `PENDING_QUALIFICATION`, eligible 0으로 계속 fail-closed한다. 첫 GPU 비교는 같은 27B artifact의
  vLLM 0.28.0/context 4096/utilization 0.88로 runtime 변화만 측정하고, 다음에 공식 8B FP8로 model
  변화를 분리한다. 실제 4090가 없으므로 Dev/Test/Shadow/workflow/fault/soak는 실행하지 않았다.
- 운영 격차 실측: 현재 시연 runtime은 `LLM_PROVIDER=mock`, `VISION_PROVIDER=mock`,
  `DATABASE_RLS_REQUIRED=false`, `OIDC_ENABLED=false`, `OTEL_ENABLED=false`, image sanitization
  `false`, malware scanner `disabled`, retention `development/30d`다. Head 0031·drift 0과 Core 9개
  health는 정상이나 이는 고객 파일럿 설정 증거가 아니다. failure replay/cancel도 runtime에서
  의도적으로 비활성이다.
- 검증: Hub live audit PASS, candidate matrix와 두 Compose profile PASS, Qwen/pilot 집중
  28 PASS, 대상 Ruff/format PASS, Pyright 0, 전체 `git diff --check` PASS. 제품 감사 문서에 현재
  gap table과 `4090 → RLS/OIDC/image security/retention/OTel/restore/load` 실행 순서를 추가했다.
- 경계/다음 행동: 4090 노드에서 exact snapshot staging→unpinned evidence 수집→reviewed digest
  pin→strict preflight가 첫 실행이다. 실제 고객 데이터와 외부 환불·메일·결제 동작은 0으로
  유지한다. Commit·Push·PR 없음; 누적 작업트리와 사용자 소유 문서를 보존했다.

### 2026-08-30 18:06 KST — Live ClamAV Evidence Security Qualification

- 목표/진전: RTX 4090 없이 닫을 수 있는 실제 제품 P0 공백인 고객 이미지 반입 경로를 현재 시연
  서버와 분리된 `csight-evidence-qualification` Docker 프로젝트에서 검증했다. 임시 PostgreSQL,
  RabbitMQ, MinIO와 digest-pinned ClamAV 1.5.4를 사용하고 최신 migration 0031까지 적용했다.
- 실제 HTTP 결과: 정상 JPEG는 201로 저장됐고 orientation 적용, private EXIF 제거, 원본 bytes
  재인코딩을 readback으로 확인했다. EICAR는 422 `UNSAFE_EVIDENCE`, 손상 이미지는 422
  `INVALID_IMAGE_CONTENT`, 과대 multipart 요청은 413으로 저장 전에 차단됐다. ClamAV를 실제로
  중단한 뒤 정상 이미지도 503 `EVIDENCE_SECURITY_UNAVAILABLE`로 실패-폐쇄했으며 정상·장애
  qualification 모두 `PASS`, 명령 exit 0이었다.
- 격리/회귀: 종료 후 qualification 컨테이너와 volume 잔존 0. 기존 Core는 9개, API, 상담원 화면,
  정책 검색과 공개 시연 주소가 모두 정상이다. 이미지 보안·설정·Evidence use case 집중 54 PASS,
  자격 스크립트 재검증 3 PASS, 대상 Ruff/format PASS, Pyright 0, `git diff --check` PASS다.
- 결함 수정/문서: 최신 Pyright가 경고한 contextmanager 반환형을 `Generator` 계약으로 교정했다.
  `docs/operations/EVIDENCE_SECURITY.md`에 실행법, 관문, stop 조건과 x86_64 파일럿 호스트 재검증
  경계를 추가하고 보안 운영 문서와 제품 감사표의 오래된 `NOT_RUN` 상태를 현재 증거로 갱신했다.
- 판정/다음 행동: 격리된 이미지 보안 경로 자체는 자격을 통과했지만 현재 시연 runtime의 sanitizer와
  scanner는 계속 비활성이다. 실제 고객 데이터 반입 전 x86_64 파일럿 호스트에서 재실행하고
  production 두 경계를 필수 활성화해야 한다. 그와 별도로 RLS, 고객 IdP 운영 연결, retention 자동화,
  OTel 경보, off-host 복원과 부하 관문이 남아 있어 파일럿 시작 판정은 계속 차단한다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 소유 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 18:46 KST — Observability Qualification Closeout Correction

- 정정: 위 18:45 observability 기록이 append 과정에서 파일상 18:30 retention 기록보다 먼저
  배치되었다. 과거 항목을 이동·삭제하지 않고 이 항목을 최신 권위 closeout으로 추가한다.
- 최종 판정: 격리 HTTP trace/metric, Prometheus query, 안전한 저장 label, 로컬 firing/resolved
  acknowledgement, Collector outage 중 API 200과 재기동 후 signal/alert recovery는 `PASS`다.
  실제 Worker 세 lane, pilot dashboard와 운영자 paging destination은 `NOT_RUN`이며 두 release gate는
  계속 false다. qualification resource는 0건이고 Core 9개와 공개 시연 주소는 정상이다.
- 검증: 기본 suite 916 PASS/92 deselected, 집중 18 PASS, Ruff/538-file format/Pyright 0,
  Compose config와 diff check PASS. Commit·Push·PR 없음.

### 2026-08-30 18:45 KST — Isolated OpenTelemetry and Local Alert Qualification

- 목표/진전: 코드 내부 in-memory 계측까지만 검증됐던 관측 경로를 현재 demo와 분리된
  `csight-observability-qualification` Docker project로 실측했다. digest-pinned Collector 0.135.0,
  Prometheus 3.5.0, Alertmanager 0.28.1, 실제 CSight FastAPI emitter와 bounded local webhook receiver를
  internal-only network에서 실행하며 host port와 외부 notification은 0으로 유지했다.
- 실제 증거: 알려진 W3C trace/correlation이 Collector에 수신됐고 HTTP counter를 Prometheus에서
  조회했다. firing webhook 200 acknowledgement와 resolved delivery, Collector 중단 중 FastAPI 200,
  재기동 뒤 trace·metric 재수신과 alert refire를 확인해 최종 report `PASS`다. PII-free report는
  `local-data/observability-qualification/latest/qualification_report.json`에 보존했다.
- 발견/교정: SDK가 자동 생성한 `service.instance.id` UUID가 Prometheus에서 `exported_instance`로
  저장되는 실제 고카디널리티 누출을 첫 실측이 차단했다. Collector metric resource processor가 이
  값을 삭제하고, 저장된 series는 method·route·status class와 고정된 scrape/service labels만 갖도록
  검사한다. read-only image의 uv cache와 HTTP header case를 잘못 가정한 qualification 결함도
  fail-closed report를 통해 교정했다.
- 자동화/정리: `make qualify-observability`가 digest pin, 무 host-port, UUID/금지 label 검사, firing→
  outage→resolved→recovery를 자동 실행하고 성공·실패 모두 container/network/volume을 제거한다.
  qualification 잔존 resource 0건이며 기존 Core 9개·API·상담원 화면·정책 검색·공개 주소는
  18:44 KST 기준 정상이다.
- 회귀: network-free 기본 suite 916 PASS/92 deselected, telemetry/readiness/pilot 집중 18 PASS,
  qualification static contract 3 PASS, Ruff 전체 PASS, Python format 538 files, Pyright 0,
  observability Compose config와 `git diff --check` PASS다.
- 경계/다음 행동: 이 결과는 HTTP와 로컬 receiver 자격이다. 실제 Worker 세 처리선 export,
  pilot-host dashboard p50/p95, 운영자 paging destination의 사람 acknowledgement는 `NOT_RUN`이므로
  `otel_signal_delivery_passed`와 `operations_alert_delivery_passed`를 아직 true로 올리지 않는다.
  RTX 4090 Dev/Test/Shadow/workflow/fault/soak와 release eligible 후보도 계속 미완료다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 소유 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 18:30 KST — Bounded Automatic Sensitive Retention

- 목표/진전: 사람의 수동 명령에 의존하던 만료 원문 삭제를 단일 고객 파일럿용 opt-in
  `privacy-lifecycle` maintenance process로 자동화했다. 기본·현재 demo에서는 꺼져 있고, 정확한
  tenant UUID와 승인된 retention version/days가 모두 있어야 한다. 비로컬 기동은 RLS-enforced API
  DB role을 요구하며 이 프로세스는 Evidence reconciliation·MinIO 삭제 adapter를 갖지 않는다.
- 권한/감사 경계: 자동 sweep은 tenant transaction context와 그 범위 안의 system all-Case read
  capability를 함께 사용한다. 사람 ADMIN을 가장하지 않고 lifecycle event의 `actor_id`는 NULL,
  `initiator=SYSTEM_RETENTION_SCHEDULER`로 고정한다. 수동 Evidence 복구와 모든 object version 삭제는
  계속 active tenant ADMIN + dry-run + 이중 확인 경로만 허용한다.
- 운영 안전성: batch 1~5,000, sweep당 최대 1~100 batches로 제한하고 blocked item에서 즉시 멈춘다.
  blocked·truncated·exception·stale health를 성공으로 낮추지 않으며 health file과 구조화 log에는
  aggregate count·timestamp만 남긴다. release gate는 자동 만료 drill과 실제 runtime 활성을 모두
  요구한다. strict Core Compose overlay는 API password secret을 재사용하되 owner URL로 fallback하지
  않는다.
- 실제 PostgreSQL 증거: 최신 Head 0031 임시 DB에서 owner로 합성 자료를 준비한 뒤 연결을
  `csight_api_role`로 낮추고 RLS를 강제한 상태에서 만료 문의 1건을 자동 sweep했다. 원문, LLM v1/v2
  claim/summary와 terminal 파생문 삭제, actor NULL, system initiator, Alembic drift 0을 확인해 1 PASS다.
  처음 0027까지만 올리던 stale integration fixture가 현재 0031 ORM과 충돌하던 결함도 최신 Head
  runtime fixture로 교정했다.
- 현재 시연 영향: 현재 demo DB의 만료 대상은 0건이며 host와 새 Docker image의 `--once` sweep 모두
  scanned 0, applied 0, blocked 0, truncated false로 exit 0이다. one-off container 잔존 0, 기존 Core
  9개·API·상담원 화면·정책 검색·공개 주소는 정상이다. 새 `csight-core:dev` image는 만들었지만 실행
  중인 9개 container와 volume은 재생성하지 않았다.
- 회귀: network-free 기본 suite 913 PASS/92 deselected, 집중 77 PASS, strict RLS PostgreSQL 1 PASS,
  전체 Pyright 0, 대상 Ruff/format과 Compose core+RLS profile config, Make command dry-run,
  `git diff --check` PASS다. 고정된 OIDC unit clock이 실제 시각을 지나 cookie 2건을 실패시키던
  독립 time-bomb도 실행 시점 UTC 기준으로 교정해 2 PASS를 확인했다.
- 문서/남은 Gate: ADR-0118과 privacy runbook, 보안 운영 문서, 제품 감사표를 갱신했다. 고객이 승인한
  retention 값 입력과 profile 활성, 실제 alert delivery·log-wide marker scan·backup expiry/legal hold는
  아직 필요하다. 실제 RTX 4090 Dev/Test/Shadow/workflow/fault/soak도 계속 미실행이다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 소유 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 18:47 KST — Append-only Ordering Correction

- 정정: 18:45·18:46 observability 항목이 파일상 18:30 항목 앞에 배치되었다. 기존 기록을 삭제하거나
  이동하지 않고 이 EOF 항목을 최신 closeout으로 삼는다.
- 최종 상태: 격리 HTTP 관측·로컬 Alertmanager 장애/복구 자격 `PASS`, qualification 잔존 resource
  0건, Core 9개와 공개 시연 주소 정상이다. Worker lane·pilot dashboard·운영자 paging과 RTX 4090
  자격은 `NOT_RUN`이며 release gate는 계속 fail-closed다. Commit·Push·PR 없음.

### 2026-08-30 18:59 KST — Physical WAL and MinIO Version Restore Qualification

- 목표/진전: checksum fixture에 머물던 복원을 현재 demo와 분리된 internal-only
  `csight-restore-qualification` 환경에서 실제 실행했다. 매니페스트 v2는 PostgreSQL base, WAL,
  MinIO inventory, 실제 MinIO version backup, runtime identity의 다섯 역할을 모두 결합한다. 기존
  v1이 실제 객체 백업을 해시하지 않던 무결성 공백을 ADR-0119로 대체했다.
- PostgreSQL 증거: digest-pinned PostgreSQL 16 source를 migration Head `0031`로 올리고 물리 base
  backup을 만든 뒤 두 번째 synthetic row와 WAL switch를 기록했다. `pg_verifybackup` PASS, archive
  증가, clean PGDATA의 recovery.signal/verified archive replay 후 row 2/2와 Head 일치를 확인했다.
- MinIO 증거: digest-pinned 동일 MinIO에서 versioning을 활성화해 content version 4개와 delete marker
  1개를 생성했다. 중단 상태 raw version backup을 clean volume에 복원한 뒤 모든 version ID·content
  SHA-256·delete-marker semantics가 source inventory와 일치했다. 실제 backup copy에 bytes를 추가한
  tamper probe는 restore 전에 manifest mismatch로 거부됐다.
- 시간/경계: 최종 local synthetic RPO 0.0462분, RTO 0.2944분으로 각각 60/240분 기준 안이다. 이는
  절차 자격이며 `encrypted_off_host_copy_qualified=false`, `target_host_repeat_required=true`다. 실제
  encrypted immutable off-host storage, 독립 key resolution, pilot hardware 2회 drill 전에는
  `restore_drill_passed`를 true로 올리지 않는다. 외부 사업 동작은 0회다.
- 자동화/검증: `make qualify-restore-drill`이 성공·실패 모두 격리 container/network/volume을 제거한다.
  잔존 resource 0건, 기본 무외부망 suite 921 PASS/92 deselected, restore 집중 16 PASS, Ruff 전체,
  Python format 541 files, Pyright 0, Compose config와 diff check PASS다. Core 9개·API·상담원 화면·정책
  검색·공개 주소는 18:59 KST 기준 정상이다.
- 다음 행동: 실제 4090 host가 연결되기 전 다음 독립 제품 P0는 20-session/20-workflow와 두 120초
  model job 처리선 격리 부하 또는 DLQ replay/cancel drill이다. RTX 4090 후보의 Dev/Test/Shadow/
  workflow/fault/soak와 release eligible 후보는 계속 미완료다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 소유 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 19:07 KST — 20-client Read and Model/Decision Queue Isolation

- 목표/진전: 실측이 없던 동시 읽기와 처리선 격리를 두 범위로 분리해 검증했다. 현재 demo에는
  DB mutation 없이 20개 독립 legacy-auth client가 Case/Review endpoint를 각 run당 200회, 3회 반복해
  endpoint별 총 600회·전체 1,200회를 요청했다. 별도 internal-only RabbitMQ/Celery 환경에서는
  120초 synthetic model task 2건을 concurrency 1 lane에 in-flight로 둔 채 decision 20건을
  concurrency 2 lane에 발행했다.
- 실제 수치: Case read p95는 396.274/359.804/306.245ms, Review는
  460.999/349.606/451.916ms로 worst p95 모두 500ms 이하다. HTTP 오류·contract 실패 0건이다.
  model task 1건이 실행되고 1건이 대기하는 동안 decision enqueue-to-start p50 257.834ms,
  p95 574.339ms, max 574.404ms였고 20/20 완료, 유실·중복 0건, 측정 중 model completion 0건이다.
- 자동화/안전: `make qualify-load-isolation`은 현재 demo read-only 측정 후 digest-pinned RabbitMQ,
  model concurrency 1, decision concurrency 2 격리 stack을 실행한다. DB mutation·외부 사업 동작은
  0회이고 qualification container/network/volume 잔존 0건이다. Core 9개·API·상담원 화면·정책 검색·
  공개 주소는 19:06 KST 기준 정상이다.
- 회귀: 기본 무외부망 suite 924 PASS/92 deselected, load static/percentile 집중 5 PASS, Ruff 전체,
  Python format 544 files, Pyright 0, Compose config와 diff check PASS다. 운영 절차는
  `docs/operations/LOAD_AND_QUEUE_ISOLATION.md`에 기록했다.
- 경계/다음 행동: read는 같은 reviewer 계정의 legacy Bearer client라 OIDC/RLS 20-session 자격이
  아니다. synthetic routing은 실제 provider/workflow가 아니다. non-model mutation p95, 20/20 terminal
  workflow, queue 완전 배출·stall 0, strict RLS/OIDC와 실제 4090 부하는 `NOT_RUN`이므로 전체 load
  release gate는 계속 fail-closed다. 다음 P0는 이 남은 20-workflow 범위 또는 DLQ replay/cancel이다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 소유 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 19:16 KST — Reviewer-owned Intake and Completed-work Separation Closeout

- 목표/진전: 관리자 전용 Case CAS 배정·재배정, 일반 담당자의 `문의 대기`와
  `내 문의 처리 현황` 분리, 검토 상세의 단일 `문의 검토 요약`, 사진·문의 요약·정책 인용과
  참고선 최근접 3개/최저 유사도 3개 표시가 현재 구현과 Accepted ADR-0109~0111에 일치함을
  다시 대조했다. 새 외부 동작이나 모델 자동 결정은 추가하지 않았다.
- 결함 수정: Case 대기함이 완료 판단을 review report 생성 시점에 의존해, 사람이 결정을 기록한 뒤
  보고서 비동기 생성 전까지 처리한 문의가 잠시 `문의 대기`에 남을 수 있었다. operator Case
  projection의 `my/unassigned/complete` 경계를 immutable human review decision 존재 여부로 바꿔
  처리 즉시 완료 현황으로 분리하고, 보고서 실패·지연이 담당자 작업 분리를 되돌리지 않게 했다.
- 검증: 담당자 배정·operator read·정책 유사도·human review backend 집중 21 PASS, 역할별 Web
  18 PASS, 전체 기본 backend 925 PASS/92 skipped, 실제 PostgreSQL one-statement operator read
  1 PASS, Web 전체 87 PASS와 lint/typecheck/OpenAPI sync/production build PASS, Ruff PASS,
  Python source format 524 files, Pyright 0이다. 사용자 소유
  `kaputt_best_vision_architecture.md`의 code fence format 차이는 수정하지 않고 제외했다.
- Runtime: 현재 image로 API/Web를 재빌드·재기동했고 두 container와 PostgreSQL·RabbitMQ·MinIO
  readiness가 정상이다. 로컬 로그인 화면은 DOM 로드와 browser console warning/error 0을 확인했다.
  실제 자격정보 입력과 최종 결정·환불·메일·결제 동작은 0회다.
- 미해결/다음 행동: 관리자/담당자 signed OIDC 실제 사용자 두 계정의 수동 화면 동선은 자격정보를
  대신 입력하지 않아 `NOT_RUN`이다. 다음 운영 검증은 고객 IdP 계정으로 배정→담당자 대기함 노출→
  사람 결정→완료 현황 즉시 이동을 실행하고, 별도 P0인 실제 20-workflow terminal 자격과 RTX 4090
  Dev/Test/Shadow gate를 이어간다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 소유 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 19:26 KST — Assignment and Personal-work UI Reverification

- 목표/결과: 관리자 Case 배정·재배정, reviewer-only `문의 대기`와 `내 문의 처리 현황`, 단일
  `문의 검토 요약`, 사진·문의 요약·정책 인용, 설명용 참고선 최근접 3개와 최저 코사인 3개가
  Accepted ADR-0109~0111 및 현재 UI/API/DB 계약에 일치함을 재검증했다. 사람 최종결정 경계와
  DRY_RUN 외부 동작 0회 원칙은 유지했다.
- 결함 수정: 실제 PostgreSQL human-review 통합 검증에서 synthetic Case를 `PILOT_LIVE` 운영 지표의
  분모 1로 기대하던 오래된 assertion을 발견했다. 제품의 immutable source-scope 경계를 약화시키지
  않고, 합성 workflow가 전체 검토·보고서 경로는 검증하되 운영 지표에서는 eligible 0/excluded 1로
  남는 계약으로 테스트를 정정했다.
- 검증: 역할별 Web 집중 22 PASS, 담당자 배정·operator read·human review·정책 유사도 backend 집중
  48 PASS/7 integration deselected, 실제 disposable PostgreSQL integration 7 PASS다. Web lint,
  TypeScript typecheck, production build, 관련 Python Ruff와 Pyright 0, `git diff --check` PASS다.
  DB Head는 `20260830_0031_oidc_backchannel_logout`; Core API/Web/PostgreSQL/RabbitMQ/MinIO readiness와
  `doongdoong.org/login` DOM 로드, browser console warning/error 0을 확인했다.
- 미해결/다음 행동: 로그인 자격정보를 대신 입력하지 않았으므로 실제 관리자 계정 배정 → 담당자
  계정 `문의 대기` 노출 → 사람 결정 → `내 문의 처리 현황` 즉시 이동 수동 동선은 `NOT_RUN`이다.
  고객 IdP의 두 실제 계정으로 이 한 번의 수동 acceptance를 수행한 뒤, 별도 release gate인
  20-workflow terminal 자격과 RTX 4090 Dev/Test/Shadow 검증을 진행한다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 소유 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 19:28 KST — RTX 4090 Qwen Static Gate Recheck

- 목표/결과: 장시간 20-workflow 구현은 사용자 요청에 따라 이번 회차에서 시작하지 않고, 현재
  RTX 4090/Qwen 후보 매트릭스와 실제 Compose Shadow 프로필의 정적 자격 상태를 재검증했다.
- 후보 판정: Qwen3.8 27B BF16/FP8 official 후보는 단일 4090 VRAM을 초과해
  `HARDWARE_EXCLUDED`; 이전 vLLM 0.26 AWQ 후보는 lineage·평가·VRAM headroom 미충족으로
  `SHADOW_ONLY`다. 비교 대상인 `Qwen3-8B-FP8` vLLM 0.26과
  `Qwen3.8-27B-AWQ-INT4` vLLM 0.28은 모두 `PENDING_QUALIFICATION`이며 release eligible 후보는
  0개로 fail-closed 상태를 유지한다.
- 실행 계약: 두 비교 후보의 exact Hub revision, digest-pinned vLLM image, served model name,
  `SHADOW` 실행 모드가 Compose 매트릭스와 일치해 2/2 `PROFILE_VERIFIED`, 전체 `PASS`다. 이는
  실행 준비 계약의 검증이며 실제 속도·정확도·VRAM·안정성 통과를 의미하지 않는다.
- 검증: 후보/Compose/host preflight/Hub audit/extraction harness unit 34 PASS, 대상 Ruff PASS,
  Pyright 0, `git diff --check` PASS다. 외부 GPU 호출과 모델 다운로드, 실제 사업 동작은 0회다.
- 미해결/다음 행동: 실제 RTX 4090에서 두 후보의 Dev 비교 후 우승 후보를 freeze하고 sealed Test,
  100건 Shadow, 20-workflow terminal, fault/soak 및 서명된 activation gate를 순서대로 실행해야 한다.
  현재는 `NO_RELEASE_ELIGIBLE`이며 실제 제품 기본 경로로 전환하지 않는다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리, 사용자 소유 문서, 투자자 SVG와
  `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-30 19:29 KST — Product Audit Truth Sync

- 목표/결과: 추가 장시간 실행 없이 제품 감사표의 현재 결론만 authoritative state와 다시 맞췄다.
  DB Head를 0031로 갱신하고, 이미 완료된 Case 배정·reviewer 직접 객체 소유권과 terminal/MinIO
  삭제 경계를 미구현처럼 읽히던 문장을 수정했다.
- 모델 표현: 과거 4090 Qwen3.8-27B INT4 관측은 역사적 Shadow baseline이며 현재 출시 자격이
  아님을 명시했다. 현재 Core는 mock이고 release eligible 후보는 계속 0개다.
- 남은 Gate: 고객 IdP 두 계정 acceptance와 권한 변경→session 종료 운영 연결, 고객별 retention·
  backup 만료/legal hold, 암호화 off-host 복원 반복, 실제 4090 Dev/Test/Shadow/workflow/fault/soak다.
- 검증/Git safety: 문서 `git diff --check` PASS. Commit·Push·PR 없음; 사용자 소유 파일을 보존했다.

### 2026-08-31 01:13 KST — RTX 4090 Tailscale Reconnection Attempt

- 목표/진전: 사용자가 Tailscale을 다시 켠 뒤 실제 4090 qualification을 재개했다. Mac mini의
  Tailscale backend는 Running이고 Linux `workstation` 피어 `100.116.246.125`는 online, direct
  ping 10ms다. TCP 22와 기존 VLM 18001은 열려 있고 `/health`는 HTTP 200이다. 18000 LLM 포트는
  닫혀 있어 새 extraction 후보는 아직 기동되지 않았다.
- 접근 검증: 일반 SSH와 Tailscale SSH를 모두 확인했다. 로컬의 기존 4090 전용
  `dacon_4090_ed25519` 키는 읽을 수 있지만 `khrin` 및 제한된 기존 후보 계정 조합에서 서버가
  public-key 인증을 거부했다. 비밀번호 입력·추측, 서버 설정 변경, 모델 다운로드·기동은 하지 않았다.
- 상태: 실제 `nvidia-smi`, NVIDIA Docker, disk, staged snapshot digest, running container identity는
  `NOT_RUN`; 실제 4090 Dev/Test/Shadow/workflow/fault/soak도 계속 `NOT_RUN`이다. 기존 VLM 서비스는
  중단하거나 변경하지 않았다.
- 다음 행동: 4090 workstation의 정확한 `whoami` 결과를 확인하고, 해당 계정에 Mac의
  `dacon_4090_ed25519.pub`를 authorized key로 등록하거나 Tailscale SSH를 명시적으로 허용한 뒤
  read-only host preflight부터 재개한다.
- Git safety: Commit·Push·PR 없음. 누적 작업트리와 사용자 소유 파일을 보존했다.

### 2026-08-31 01:36 KST — RTX 4090 Host Access and Package Gate Correction

- 접근 정정: 로컬 SSH 설정의 `Khrin` 별칭이 실제 `user@100.116.246.125`와 전용 key를 이미
  가리키고 있음을 확인해 public-key 접속에 성공했다. 앞선 `khrin`/`kimhrin` 사용자명 시도 실패는
  계정 추정 오류였다. 사용자가 제공한 비밀번호는 로그인 확인 외에 재사용하지 않았고 파일·환경·
  명령·문서에 저장하지 않았다.
- 실제 호스트: Linux `6.8.0-136-generic` x86_64, RTX 4090 24,564 MiB/CC 8.9/driver
  580.173.02, Docker 29.5.3와 NVIDIA runtime을 확인했다. 기존
  `csight-kaputt-vlm-qwen38-vlm-1`은 exact Community 27B AWQ revision과 vLLM 0.26 digest로
  18001에서 health 200이며 22,626 MiB를 사용한다. GPU free는 1,350 MiB, 18000은 비어 있다.
- 패키지 준비: 기존 volume은 변경하지 않고 26 GiB owner-controlled cache에 exact snapshot을
  복제했다. vLLM 0.28 exact digest를 pull하고, artifact 15 files/21,018,000,928 weight bytes,
  canonical lock 264 lines, Python+dpkg 749-component CycloneDX SBOM, publisher model card/config 기반
  quantization recipe를 수집했다. 준비 후 디스크 여유는 약 255 GiB다.
- 관문 결과: artifact content, image, lock, SBOM, recipe digest를 27B v0.28 matrix 항목에만 고정했고
  전체 profile 검증은 PASS, release eligible 후보는 계속 0개다. 실제 container preflight에서 모든
  host/private bind/offline/package 항목은 PASS, 기존 VLM 때문에 free VRAM 1,350 MiB와 active GPU
  process 1건만 FAIL이다. publisher가 calibration dataset revision을 공개하지 않아 해당 digest는
  꾸며 넣지 않고 경고로 보존했다.
- 결함 수정: host Python 3.10에서도 digest-pinned candidate image로 verifier/preflight를 실행할 수
  있는 container tooling, iproute2 없는 image의 stdlib IPv4 probe, deterministic runtime SBOM
  generator를 추가했다. container probe에는 host PID namespace를 강제해 실제 GPU process가 0으로
  숨는 오판을 차단했다. calibration 미공개만 남은 경우 평가용 Shadow만 허용하는
  `SHADOW_READY_PROVENANCE_INCOMPLETE`를 추가했으며 `strict_ready=false`와 release 차단은 유지한다.
- 검증: Qwen host/release/profile/harness/Hub/SBOM 집중 39 PASS, Compose profile 2/2 PASS, Shell
  syntax, Ruff/format, 대상 Pyright 0, `git diff --check` PASS다. 원격 profile verifier도 PASS다.
- 미해결/다음 행동: 단일 GPU라 27B Dev에는 기존 VLM의 약 30~60분 유지보수 중단이 필요하다.
  자동 원상복구와 18001 health 200 확인 조건으로 사용자 허가를 요청했으며, 허가 전에는 중단하지
  않는다. 27B Dev/freeze/Test/Shadow/workflow/fault/soak와 8B exact download/qualification은 아직
  `NOT_RUN`이다.
- Git safety: Commit·Push·PR 없음. 기존 VLM, Core, 사용자 소유 파일과 누적 작업트리를 보존했다.

### 2026-08-31 01:48 KST — Official 8B Package and Maintenance Restore Readiness

- HF/package: HF CLI를 token 없이 exact commit에 고정해 `Qwen/Qwen3-8B-FP8`을 별도 8.9 GiB
  owner-controlled cache에 받았다. snapshot 12 files, weight 9,436,628,784 bytes와 content digest,
  vLLM 0.26 canonical lock 265 lines, Python+dpkg 745-component SBOM, official card/config 기반 FP8
  recipe를 matrix에 고정했다. 두 runnable profile은 계속 2/2 PASS이고 release eligible은 0개다.
- 계약 교정: official config의 dynamic e4m3/block128 FP8은 calibration dataset을 선언하지 않으므로
  `OFFICIAL_PREQUANTIZED_DYNAMIC_FP8` evidence mode를 추가했다. official+FP8 조합만 허용하고
  calibration digest를 임의로 넣거나 Community artifact가 예외를 주장하면 validation이 실패한다.
  27B Community의 미공개 calibration revision은 계속 Shadow-only 경고다.
- 실제 preflight: 8B strict package/host/private-bind/offline/provenance 항목은 전부 PASS다. 기존 VLM
  점유 때문에 GPU free 1,350 MiB와 active process 1건만 FAIL이다. 즉 중단 창에서 GPU가 idle이면
  strict preflight가 통과할 준비가 됐고, 아직 모델 기동·Dev 호출은 하지 않았다.
- 평가/복구: frozen app dependency의 Python 3.12 evaluator image
  `sha256:13d8e94ee3e7a5fa054e09faca7f89f3b511496a6699616feab6ad88e7e6be28`을 빌드해 import와
  GPU sampler 가용성을 확인했다. 기존 VLM compose의 재기동 입력이 shell에 없던 위험을 발견해
  owner-only restore env로 캡처했고 secret 출력 없이 `docker compose config` PASS를 확인했다.
- 자동 안전장치: `run_qwen4090_maintenance_dev.sh`는 명시적 허가 변수 없이는 exit 2, exact VLM
  image/health 검증 뒤 EXIT trap 설치, Dev-only evaluation, 모든 종료 경로의 candidate 제거와 VLM
  재기동·health 확인을 강제한다. 원격 fail-closed refusal PASS, 기존 18001 VLM health 200이다.
- 검증: Qwen/SBOM 집중 41 PASS 뒤 maintenance/release/host 집중 28 PASS, Shell syntax,
  Ruff/format, 대상 Pyright 0, matrix/profile PASS, `git diff --check` PASS다.
- 미해결/다음 행동: 사용자의 명시적 유지보수 허가를 기다린다. 허가 후 27B v0.28 Dev를 먼저
  실행하고 자동 VLM 복원을 확인한 뒤 8B Dev를 동일하게 비교한다. freeze, sealed Test, Core Shadow
  100, workflow 20, fault/soak는 Dev 승자 결정 전까지 실행하지 않는다.
- Git safety: Commit·Push·PR 없음. 사용자 비밀번호·LLM/VLM API key·HF token은 저장소와 문서에
  기록하지 않았고 기존 VLM/Core/사용자 파일을 보존했다.

### 2026-08-31 01:50 KST — RTX 4090 Pre-Maintenance Final Check

- 최종 정적 검증: Qwen release/profile/host/extraction/Hub/maintenance/SBOM 집중 42 PASS,
  matrix `NO_RELEASE_ELIGIBLE`, Compose profiles `PASS`, Shell syntax, Ruff/format, 대상 Pyright 0,
  `git diff --check` PASS다.
- 실제 상태: 기존 VLM은 `Up 2 days (healthy)`, 18001 health 200이고 GPU 사용 22,729 MiB/free
  1,350 MiB다. 유지보수 runner의 허가 없는 실행은 실제 host에서 exit 2로 거부됐다.
- 다음 행동: 사용자에게 기존 VLM의 30~60분 순차 중단 허가를 다시 요청한다. 허가 전에는
  candidate start와 모델 provider 호출 0회를 유지한다.

### 2026-08-31 03:55 KST — RTX 4090 Candidate Dev Qualification

- 실제 실행: 사용자 승인 후 단일 RTX 4090 유지보수 창에서 27B AWQ/vLLM 0.28과 공식 8B FP8/
  vLLM 0.26을 동일 합성 Dev 120건으로 순차 평가했다. 각 실행 전후 exact 기존 VLM image와
  Tailscale 전용 18001 health를 확인했고 모든 종료에서 자동 복원됐다. 최종 VLM은
  `running/healthy`, restart 0이다.
- 27B 결과: 23/120 valid, schema·exact quote 0.191667, p50 3.4365s, p95 4.626s,
  34.4969 output tok/s, observed min free VRAM 2,350 MiB다. 실패 97건은 모두
  `LLM_INVALID_STRUCTURED_OUTPUT`, injection·reasoning 위반은 0건이다.
- 8B 결과: 초기 offline cache가 `HF_HOME/hub` 구조가 아니어서 fail-closed startup 실패했고 기존
  VLM이 복원됐다. 동일 inode를 올바른 Hub layout에 배치해 package digest preflight를 다시 통과한 뒤
  49/120 valid, schema·exact quote 0.408333, p50 1.8295s, p95 2.823s, 50.4935 output tok/s,
  observed min free VRAM 2,122 MiB를 측정했다. 구조화 출력 실패 45건, source quote 불일치 26건,
  injection 위반 4/120, reasoning 0건이다.
- 안전 보강: maintenance runner가 실패 후보 제거 전에 private result root에 mode 0600 startup log를
  남기도록 수정했고 unit test와 Shell syntax가 PASS다. 실제 8B 실패 원인을 이 로그로 확인했다.
- 증거: 두 privacy-safe 결과 패키지를 `evaluation/results/qwen4090_extraction_v2/`로 복사해 profile,
  dataset, matrix와 result digest를 다시 검증했고 두 후보 모두 `RESULT_PACKAGE_PASS`다. 원문,
  prediction, provider response/request ID, reasoning은 저장하지 않는다.
- 판정/미해결: 둘 다 Dev 절대 기준 실패라 freeze, sealed Test, Core Shadow 100, workflow 20,
  fault/soak, signed activation을 실행하지 않았다. release eligible은 0개이고 시연은 기존 VLM을
  유지한다. Matrix의 `qualification`은 freeze 이후 release-grade evidence만 받으므로 실패 Dev는
  result manifest로 보존하고 machine status는 `PENDING_QUALIFICATION`을 유지한다. 다음 안전 행동은
  8B의 별도 Dev prompt profile 튜닝이며 운영 prompt나 PRIMARY를 바로 변경하지 않는다.
- 최종 검증: Qwen release/profile/host/extraction/Hub/maintenance/SBOM 집중 42 PASS, Ruff와 format
  PASS, 대상 Pyright 0, Shell syntax PASS, Compose profile PASS, matrix `NO_RELEASE_ELIGIBLE`, 두
  result package 검증 PASS, `git diff --check` PASS다.
- Git safety: Commit·Push·PR 없음. 사용자 비밀번호/API key/token은 저장소·문서·결과에 기록하지
  않았고 사용자 소유 파일과 누적 작업트리를 보존했다.

### 2026-08-31 05:38 KST — Generic Ed25519 Signed Case Intake

- 목표/결과: 고객별 전용 코드를 추가하지 않고 승인된 외부 시스템이 Case를 전달할 수 있는
  `POST /api/v1/integrations/cases` 수직 슬라이스를 구현했다. Ed25519 서명은 method, 고정 path,
  key/event/timestamp header와 exact raw-body SHA-256을 묶고, 허용 시각 오차는 최대 ±300초다.
- 신뢰 경계: key ID는 배포 설정의 단일 tenant, source, provenance와 active no-role service actor에
  고정된다. body의 `tenant_id`·`source_scope`는 허용하지 않으며, 인증 성공 경로만 기존 Case UoW로
  `PILOT_LIVE`/`RECEIVED` Case, 민감 payload와 최초 history를 기록한다. 첨부, 자동 분석, 배정,
  정책·사람 결정, 외부 동작은 추가하지 않았다.
- 복구/중복: source ID + signed event ID를 기존 idempotency 테이블의 별도
  `case.intake.signed.v1` namespace로 사용한다. exact replay는 동일 Case/HTTP 200, 다른 payload의
  event ID 재사용은 409다. invalid/tamper/stale는 Case 저장 use case 호출 0회다.
- 운영 계약: migration `20260831_0032_signed_case_intake.py`와 ORM constraint를 추가했고,
  `.env.example` 및 ADR-0120에 key mapping, canonical bytes, 예시 key 생성·서명·요청 절차를 기록했다.
  실제 private key 생성·저장이나 customer source 활성화는 하지 않았다.
- 검증: signed intake HTTP/application/key-loader/migration과 Settings 포함 대상 unit 59 PASS,
  대상 Ruff PASS, 대상 Pyright 0이다. 외부 네트워크·GPU·실제 사업 동작은 0회다.
- 미해결/다음 행동: 기능은 기본 비활성이다. 파일럿 tenant의 전용 service actor와 실제 public key를
  운영 secret mount에 provision한 뒤 PostgreSQL/RLS 환경에서 valid/replay/tamper/stale 및 DB row
  count를 검증해야 활성화할 수 있다. 첨부·자동 workflow start는 별도 승인된 후속 slice다.
- Git safety: Commit·Push·PR 없음. 사용자 소유 파일과 누적 작업트리를 보존했다.

### 2026-08-31 06:20 KST — Productization P0 Implementation and Full Regression

- 목표/결과: 단일 고객·상담원 5~20명 제한 pilot로 발전시키기 위한 남은 제품 P0를 구현했다.
  Case·Review의 문의/주문/상품 번호 검색을 pagination 전 server-side 단일 SQL로 옮기고, 관리자
  운영 화면에 개인정보 없는 6개 온보딩 gate를 추가했다. 현재 실제 준비도는 인력만 PASS,
  나머지 5개 FAIL이며 `pilot_ready=false`다.
- Intake/model: generic Ed25519 signed intake를 실제 PostgreSQL HTTP에서 201/replay 200/conflict
  409와 정확히 한 Case graph로 검증했다. task별 signed model route plan, migration 0033~0034,
  Analysis stage의 immutable plan snapshot과 model Worker의 historical activation/deployment/runtime
  identity 검증을 연결했다. 현재 강제 범위는 text extraction v2뿐이고 query builder·grounding은
  의도적으로 준비도 FAIL을 유지한다. 모델이 정책·사람 결정·외부 동작을 만들지는 않는다.
- Pilot runtime: demo와 별도인 OIDC-only/RLS/ClamAV/retention/OTel/signed intake·model profile,
  read-only preflight와 volume 보존 controller를 추가했다. 실제 env가 없어 preflight는 exit 2로
  거부됐고, filesystem 가용 공간도 8.7 GiB로 최소 30 GiB에 미달한다. start/build/migrate/prune/
  volume 삭제는 0회다.
- 회귀 수정: 전체 통합 실행에서 최신 migration head를 과거 revision으로 가정한 테스트, append-only
  failure/assignment source graph를 삭제하려던 teardown, 운영 집계의 tenant context 누락과 시간 경계
  fixture를 발견했다. 운영 constraint를 완화하지 않고 dynamic head, immutable graph 보존,
  explicit tenant context와 생성 이후 만료시각으로 수정했다.
- 최종 검증: 기본 backend 1002 PASS/6 SKIPPED/88 deselected, disposable PostgreSQL integration
  83 PASS/5 external-GPU SKIPPED/1008 deselected, Web 31 files·90 tests PASS, lint/typecheck/OpenAPI
  sync/production build PASS다. Ruff 전체, Python format 580 files, Pyright 0, diff check와 단일
  Alembic head 0034도 PASS다. Web main gzip 82.18 kB, 최대 chunk 257.65 kB로 예산 안이다.
- 런타임/경계: 06:20 KST 현재 Core 9개 running/healthy, DB는 0034이고 API의 PostgreSQL·RabbitMQ·
  MinIO readiness는 `ok`다. 실행 중 demo image는 이번 작업트리로 재빌드하지 않았고 별도 pilot은
  시작하지 않았다. release eligible 4090 모델은 0개, 실제 고객 key/env/IdP/off-host restore와
  남은 20-workflow qualification은 미완료다. 실제 환불·메일·결제·GPU 호출은 0회다.
- Git safety: Commit·Push·PR 없음. branch와 origin은 계속 `3daaa7b`이며 누적 작업트리,
  사용자 소유 문서, 투자자 SVG와 `kaputt_best_vision_architecture.md`를 보존했다.

### 2026-08-31 15:10 KST — Demo Baseline Freeze and Pilot Admission Contracts

- 시연본 동결: 실행 중인 Core/Web/DB를 재빌드·재시작·마이그레이션하지 않고 누적 변경을 네 범주로
  검토했다. 고신뢰 Secret과 대용량 staged blob은 0건이었다. 사용자 소유 문서·원본 이미지·모델
  checkpoint·Docker volume과 `kaputt_best_vision_architecture.md`는 staging에서 제외했다.
- Git 기준점: DB·보안·운영 기반 `8834b9b`, 상담원 API·UI `c8c7070`, ADR·평가·운영 문서
  `ba39aea`의 세 commit을 현재 `codex/operator-console-product-direction`에 push했다. PR과
  `develop/main` 병합은 만들지 않았다.
- 모델 route: additive migration 0035로 Query Builder와 Grounded Explanation run에 실행 모드,
  nullable legacy route ID, enforcement 계약 버전과 tenant-scoped FK/index를 추가했다. 새 LLM run은
  replay 확인 뒤 활성 route를 같은 transaction에 고정하고 Worker가 역사적 activation·서명·task·
  mode·deployment·prompt/schema/runtime identity를 provider 호출 전에 검증한다. RAW와
  DETERMINISTIC은 route 조회와 모델 호출이 0이다.
- 런타임 설정/queue: Extraction·Query Build·Grounding의 endpoint, model revision, deployment,
  timeout과 circuit 설정을 task별로 분리하고 provider client를 process 내 재사용한다. 모델 lane은
  concurrency 1, 검색 lane은 2, 결정 lane은 2다. 다만 Query Build와 Search의 독립 v2 event 분리는
  아직 구현하지 않아 기존 LLM policy-retrieval task 전체를 보수적으로 모델 lane에서 처리한다.
- 온보딩/준비도: PII 없는 `plan/apply/verify` 운영자 명령을 추가했다. 명명 계정 5~20명, 관리자·
  검토자, 명시적 retention, no-role signed-intake actor, IdP groups, active policy와 지원 체계를
  검증하며 삭제·암묵적 보존기간·Secret 출력은 금지한다. `/api/v1/operations/pilot-readiness`는
  구성 6개와 운영 자격 25개를 freshness와 evidence digest로 합산하고 누락·만료를 FAIL 처리한다.
  signed intake와 readiness가 포함된 별도 pilot OpenAPI artifact도 생성했다.
- 최종 회귀: 기본 backend `1014 passed`, disposable PostgreSQL integration `83 passed, 5 skipped`,
  Web `31 files/90 tests`, lint, typecheck, OpenAPI sync, production build, Ruff, format, Pyright가 모두
  PASS다. 실제 migration 0034→0035와 schema drift도 격리 DB에서 PASS했다. Web main gzip은
  82.18 kB, 최대 chunk는 257.65 kB다. 외부 네트워크·GPU·실제 사업 동작은 0회다.
- 런타임/차단: 현재 데모 9개 서비스는 계속 정상이고 DB는 의도적으로 0034다. 디스크는 9.0 GiB로
  clean build 최소 35 GiB보다 부족해 clean worktree, `rc-<sha>` image, candidate stack은 만들지
  않았다. `.env.pilot`, 고객 IdP/public key/retention/policy, 보안 이미지 업로드 실증, release 모델,
  off-host 복원 2회, 경보 전달과 실제 20-session/20-workflow 증거가 없으므로 pilot은 계속 BLOCKED다.
  최종 read-only 확인에서 API `/health/ready`와 Web은 정상이나 구형 API image의 Alembic package가
  DB 원장 0034를 해석하지 못했다. 실행 중 image에서는 migration을 금지하고 clean candidate에서만
  0034→0035를 수행한다.
- 다음 행동: 삭제 대상과 예상 회수량을 사용자에게 제시해 승인을 받은 뒤 복구 가능한 cache만
  정리한다. 35 GiB 이상을 확인하면 push된 SHA의 clean worktree에서 non-dev image를 한 번 빌드하고
  digest를 고정한다. 이후 외부 고객 입력을 받은 owner-only `.env.pilot`에서 onboarding verify,
  31개 readiness gate와 preflight를 통과한 경우에만 별도 pilot profile을 시작한다.
- 최종 Git: 위 후속 구현과 검증 원장은 `0b7f179 feat: complete routed pilot readiness contracts`로
  같은 기능 브랜치에 push했다. 원격과 로컬 SHA가 일치하며 PR·병합은 만들지 않았다.

### 2026-08-31 15:47 KST — Clean RC Build and Isolated Candidate Qualification

- 디스크 관문: 사용자 승인으로 Homebrew Ollama service/package와 13 GiB 모델, Qwen3.5 9B·CSight
  Embedding/Reranker를 제외한 Hugging Face model/dataset cache 약 20 GiB를 삭제했다. 가용 공간은
  9 GiB에서 빌드 전 42 GiB, 빌드 후 41 GiB가 됐다. Qwen3.5 9B MLX 4-bit 5.6 GiB와 CSight
  Embedding/Reranker 각 1.1 GiB는 보존했고 embedding MPS health도 PASS다.
- clean 기준점: 원격과 일치하는 `bc2d7be495b0415a282ded8f8a0680c0780fedaa`를 detached clean
  worktree `/Users/ckdlsxor/Desktop/CSight_rc_bc2d7be`에 만들었다. 사용자 소유 문서나 원본 작업트리
  변경은 포함하지 않았다.
- immutable image: `rc-bc2d7be495b0` 태그로 Core/Web을 한 번 빌드했다. Core digest는
  `sha256:d5be9f3750c19776b171fd87b777466ae8875acc0437f5f5d37334a30de6ee4a`, Web digest는
  `sha256:b15b0ae812ff84f6493a09d3d25d97e70f79ce842f64f996986b2f0e7c66e836`이다.
- candidate stack: `csight-rc-bc2d7be` 별도 project, 포트, network, volume에서 빈 PostgreSQL을
  0001→0035로 migration했다. API/Web/Dispatcher/세 Worker/PostgreSQL/RabbitMQ/MinIO의 9개 장기
  service가 모두 healthy, restart 0이었고 API dependency readiness와 Web 200을 확인했다. Pilot
  OpenAPI artifact의 signed intake와 pilot readiness path도 확인했다.
- clean 회귀: Ruff, format, Pyright, backend `1014 passed`, Web lint/type/OpenAPI sync/build와
  `31 files/90 tests`가 PASS했다. 현재 demo DB를 read-only dump한 disposable DB에서 0034→0035를
  적용한 integration은 `83 passed, 5 external-GPU skipped`였고 임시 DB는 삭제됐다. 빈 candidate
  DB를 직접 복제한 첫 시도는 필요한 합성 policy/reranker seed와 RabbitMQ URL이 없어 환경 실패했고
  disposable DB는 삭제됐다. 이는 최종 통과 수치에 포함하지 않는다.
- 종료/보존: candidate 컨테이너와 network만 `down`으로 종료했고 volume과 두 RC image, clean
  worktree는 보존했다. 원래 데모 API/Web은 계속 정상이고 DB/image는 0034 상태를 유지했다. 실제
  환불·메일·결제·CRM, 외부 GPU 호출, pilot start는 0회다.
- 남은 관문: owner-only `.env.pilot`, 고객 IdP/public key/retention/policy/support 입력, 31개 fresh
  readiness 증거, ClamAV/OIDC/OTel/restore/load 실연과 release-eligible 모델이 필요하다. 이 입력과
  증거 전에는 preflight exit 0이나 pilot start를 주장하지 않는다.

### 2026-08-31 16:23 KST — Durable Query Build/Search v2 Split

- 목표/결과: 신규 Policy Retrieval을 `policy_query_build.requested.v2`와
  `policy_search.requested.v2`의 두 append-only Outbox event로 분리했다. Query Build는 모델 lane
  concurrency 1, Search는 retrieval lane concurrency 2에서 실행하며 기존 v1 task는 이미 발행된
  event drain에만 남겼다.
- 원자성/복구: query plan 저장, run의 `SEARCH_QUEUED` 전환, Query Build event consume, Search event
  생성은 하나의 transaction이다. 두 Worker는 event type·tenant·Case·run·correlation과 claim lease를
  검증한다. Search는 저장된 plan만 읽고 HYBRID retrieval을 실행하며 모델 provider dependency가 없다.
- 모델 경계: RAW·DETERMINISTIC은 LLM route 조회와 provider 호출이 0이다. LLM Query Build만 pinned
  historical route guard를 통과한 뒤 provider를 호출한다. silent model fallback과 정책·사람 결정·
  실제 외부 사업 동작은 추가하지 않았다.
- 검증: Ruff/format/Pyright PASS, 비통합 backend `1023 passed, 6 skipped`, disposable PostgreSQL
  integration `83 passed, 5 external-GPU skipped`, Alembic 빈 DB 0001→0036·0036→0035→0036과 drift
  PASS다. demo DB의 read-only clone에서 실제 Repository→Dispatcher→RAW Query Build→Dispatcher→
  Search 경로가 run SUCCEEDED, 두 v2 event CONSUMED, raw query 원문 비복제, LLM 호출 0으로 PASS했다.
- 런타임/보존: 16:23 KST 현재 기존 demo 9개 service는 healthy이고 DB/image는 의도적으로 0034다.
  재빌드·재시작·migration·외부 GPU 호출은 0회이며 사용자 소유 미추적 문서, 원본 이미지,
  checkpoint, Docker volume과 `kaputt_best_vision_architecture.md`를 보존했다. 가용 공간은 40 GiB다.
- 미해결/다음 행동: 변경을 검토 가능한 commit으로 기능 브랜치에 push한 뒤 그 SHA의 clean
  worktree에서 non-dev RC image를 새로 한 번 빌드하고 별도 candidate stack을 0036으로 검증한다.
  실제 pilot env·고객 입력·release model·off-host 복원·경보 전달·20-session/20-workflow 증거 전에는
  pilot ready를 주장하지 않는다.
- Git: 구현·ADR·계약·migration·테스트를 `55fe72b146c4`로 commit해 현재 기능 브랜치에 push했다.
  고신뢰 Secret과 대용량 staged blob은 0건이었고 PR·병합은 만들지 않았다.

### 2026-08-31 16:27 KST — Migration 0036 Clean RC Candidate

- 기준점: 원격과 일치하는 `cd6471cd628e`를 detached clean worktree
  `/Users/ckdlsxor/Desktop/CSight_rc_cd6471c`에 만들고 `rc-cd6471cd628e` 태그로 Core/Web을 한 번
  빌드했다. Core digest는 `sha256:6df6cddccd24b32c5776d3bcc0696545bd8374475120d7ca7f1103defcf295a7`,
  Web digest는 `sha256:a4370d4380bbb115799ae8e58bbd8accaabede0d073396bf08868301b1589e07`이다.
- candidate: `csight-rc-cd6471c` 전용 project/network/volume/port에서 빈 PostgreSQL을 0001→0036으로
  migration했다. API/Web/Dispatcher/model·retrieval·decision Worker/PostgreSQL/RabbitMQ/MinIO의
  9개 장기 service가 모두 healthy, restart 0이고 API dependency readiness와 Web 200이 PASS했다.
- queue 확인: model Worker는 `analysis`, legacy drain `policy-retrieval`, `policy-query-build`,
  `grounded-explanation`만 구독하고 retrieval Worker는 `policy-search`만 구독함을 실제 Celery
  `active_queues`로 확인했다.
- 종료/보존: candidate container와 network만 종료했고 `csight-rc-cd6471c_*` 4개 volume, 두 RC image,
  clean worktree는 보존했다. 원래 demo API/Web readiness는 종료 직후에도 PASS했고 DB/image 0034를
  migration하거나 재시작하지 않았다. 가용 공간은 39 GiB다.
- 다음 행동: 외부 입력이 필요 없는 qualification runner부터 현재 RC에서 재실행 가능 여부를 확인한다.
  실제 고객 IdP/public key/retention/policy/support, release-eligible 모델, immutable off-host 저장소와
  경보 수신자가 필요한 gate는 입력 전까지 FAIL/BLOCKED로 유지한다.

### 2026-08-31 16:37 KST — Local Pilot Qualification Reproduction

- 부하·queue 격리: 현재 데모의 조회 API를 20개 동시 client로 endpoint별 600회 호출해 오류 0,
  Case worst p95 115.121ms, Review worst p95 85.395ms를 기록했다. 별도 합성 RabbitMQ/Celery 경로에서
  120초 모델 작업 2건이 대기·실행 중일 때 decision task 20건의 queue wait p95는 502.792ms,
  유실·중복과 사업 side effect는 0건이었다. 이는 read와 lane isolation 자격이며 mutation p95와
  20개 실제 workflow terminal 자격은 아니다.
- OIDC·이미지 보안: 격리 Keycloak에서 Authorization Code+PKCE, role mapping, return path, CSRF,
  idle expiry, group 제거·계정 비활성화 뒤 신규 로그인 차단과 기존 session 회수가 모두 PASS했다.
  ClamAV 경로는 clean image 저장·재인코딩·EXIF 제거, EICAR decode 전 422, 손상·과대 파일 거부와
  scanner outage fail-closed가 PASS했다. 실제 고객 IdP와 실제 고객 이미지를 사용한 결과는 아니다.
- 관측성: 로컬 Collector/Prometheus/Alertmanager receiver에서 trace·안전한 metric label,
  firing→수신 확인→resolved와 Collector 장애 중 Core HTTP 200·복구 후 재수집이 PASS했다. 외부 알림은
  보내지 않았고 실제 운영 paging destination은 미자격이다.
- 복원: 합성 격리 환경에서 PostgreSQL base/WAL, MinIO version/delete marker, 정책·모델·프롬프트·설정
  5개 artifact binding과 tamper reject를 검증했다. 측정 RPO 0.0125분, RTO 0.1397분이지만 암호화
  immutable off-host copy는 미자격이고 target host에서 독립 key로 2회 반복해야 한다.
- 증거 영속화: 기존 load·observability·restore JSON에 더해 OIDC 결과를
  `local-data/oidc-qualification/latest/qualification-report.json`, 이미지 보안 healthy/outage 결과를
  `local-data/evidence-security-qualification/latest/`에 저장하도록 runner를 보강했다. 디렉터리는
  mode 0700, JSON은 0600이고 PII·Secret을 포함하지 않는다. 관련 shell syntax, 전체 Ruff/format/Pyright,
  집중 unit 6건과 diff check가 PASS했으며 변경은 `9461b31`로 현재 기능 브랜치에 push했다.
- 보존/경계: 자격 runner의 임시 container와 volume은 모두 정리됐고 기존 데모 9개 service는 계속
  healthy, DB/image는 0034, 디스크 가용 공간은 39 GiB다. 실제 외부 GPU·환불·메일·결제·CRM 동작은
  0회이며 사용자 소유 문서, 원본 이미지, checkpoint, RC volume/image와
  `kaputt_best_vision_architecture.md`를 보존했다.
- 다음 행동: ① 실제 OIDC/RLS pilot profile에서 20-session/20-workflow와 mutation p95를 측정하고,
  ② 외부 경보 수신자 전달·사람 확인을 실연하며, ③ 암호화 immutable off-host 복원을 target host에서
  독립 key로 2회 수행한다. 이후 release-eligible 모델과 signed SHADOW 100건, rollback/DLQ 훈련을
  완료한다. 고객 IdP/public key/retention/policy/support 입력과 모든 fresh gate가 없으면 pilot start는
  계속 BLOCKED다.

### 2026-09-01 00:43 KST — CSight-owned Qwen3.8-27B GGUF Quantization

- 목표/결과: 단일 RTX 4090에서 사용할 Qwen3.8-27B를 CSight task에 맞춰 비교할 수 있도록 exact
  BF16에서 no-imatrix Q4 control, imatrix Q4, 선택 tensor를 Q6_K로 보호한 mixed Q4/Q6, imatrix
  Q5 quality ceiling을 만들었다. 이는 로컬 R&D 후보 생성 완료이며 모델 품질·출시 자격 통과가 아니다.
- source/toolchain/corpus: BF16 53,808,281,952 bytes·`5a3eed…fa97e`, llama.cpp
  `aee56b3…ef28`, tool image `d486bf…afb2`, quantizer `05290c…f818`, corpus canonical
  `b39414…e90d`, calibration `f0f7f2…dc5f`, imatrix `8d1de2…d40f`를 고정했다. 공개 source
  capture sidecar와 offline replay를 추가했고 원문 문의·직접 식별정보·sealed Test는 사용하지 않았다.
- 최종 산출물: control 16,547,400,032 bytes·`078fc4…c5f0`는 `REUSED_VERIFIED`, imatrix Q4
  16,547,400,320 bytes·`b044ea…e721`, mixed Q4/Q6 19,294,014,080 bytes·`6fb2b9…a0d9`,
  Q5 18,679,614,080 bytes·`817bae…c075`는 `EXECUTED`다. 네 후보와 모든 host input을 종료 후
  재해시한 evidence는 PASS, SHA `324772…1378`이며 최종 원본은 모두 BF16이다.
- 보호 실행/복구: 첫 실행은 Python 3.10 dependency root가 user site를 숨겨 Docker 실행 전 실패했고
  후보 생성 0건, Counsel 12/12 복구로 종료했다. dependency root를 명시해 재실행했고 00:38 KST
  기존 VLM은 exact model ID·healthy·restart 0·OOM false, Counsel은 기존 container identity 12/12와
  기존 health 기준으로 복귀했다. 양자화 container는 offline/no GPU/read-only/CPU 16/memory 56 GiB로
  제한했고 실제 환불·메일·결제·CRM 동작은 0건이다.
- 구현/검증: GGUF source attestation·corpus builder·recipe/run-plan compiler·bounded executor,
  owner-only evidence, llama.cpp adapter/compose/preflight, task별 평가·Shadow100 collector, signed
  activation/route와 pilot composition fail-closed guard를 추가했다. Ruff PASS, 제품 코드 format 605,
  Pyright 0, 기본 pytest 1171 PASS/94 SKIPPED, GGUF 집중 134 PASS, shell syntax·diff check PASS다.
- 출시 경계/다음 행동: matrix v2에 mixed Q4/Q6와 Q5 bytes·digest만 반영했고 두 후보의
  `artifact_revision`과 qualification은 null이라 `PENDING_QUALIFICATION`, 전체는
  `NO_RELEASE_ELIGIBLE`다. imatrix는 finalization 수선 이력 때문에 clean rerun이 필요하고 현재
  Dockerfile도 새 image로 재빌드하지 않았다. 개인 private artifact revision·조직 mirror,
  provider-neutral GGUF Extraction evaluator, canary/Dev/freeze/sealed Test/SHADOW100/workflow20 전에는
  PRIMARY·자동 fallback을 금지한다.
- Git/보존: HEAD와 원격 기능 브랜치는 `f2357ba0cee6`으로 일치하며 이번 변경은 미커밋이다.
  Commit·Push·PR·병합·artifact upload는 실행하지 않았고 사용자 소유 문서, 원본 이미지,
  checkpoint, Mac Docker volume과 `kaputt_best_vision_architecture.md`를 수정·삭제하지 않았다.

### 2026-09-01 06:05 KST — Q4 Dev Grounding Technical Failure Diagnosis

- 직접 원인: Q4 Dev의 첫 Grounding 응답이 `GROUNDED_EXPLANATION_INVALID_OUTPUT`으로 구조 검증에
  실패했지만, 평가 생성 루프가 provider 오류와 `ValueError`만 처리해 이 예상 가능한 모델 출력
  불합격을 프로세스 예외로 누출했다. 자식 실행기는 일반 Python 예외의 종료 코드 1을 평가 gate
  실패와 구분하지 않아 이후 불완전 evidence를 기술 실패로만 보고했다.
- 수정: Grounding의 invalid-output·citation-allowlist 예외와 동일 계열 Query Builder invalid-output
  예외만 각 record의 typed `FAILED` 관측으로 좁게 변환했다. 자식 종료 코드 0/1은 candidate·task·split·
  gate 결과가 일치하는 privacy-safe 완료 신호가 정확히 있을 때만 평가 완료로 인정한다.
- 개인정보 경계: provider 원문 응답, 요청 ID, 고객 원문, PII는 새 evidence나 오류 출력에 보존하지
  않는다. 실패 관측에는 hash, 지연시간, 안정된 오류 코드만 남긴다.
- 검증: 관련 Ruff·format PASS, Pyright 0, 단위·Grounding/llama.cpp contract 집중 `60 passed`,
  `git diff --check` PASS. 원격 4090·실행 중 container·GPU workload는 접속하거나 변경하지 않았다.
- 미해결/다음 행동: 새 source bundle digest로 Mac evaluator와 보호된 maintenance 경로를 다시 배포한
  뒤 fresh result root에서 Q4 Dev를 재실행한다. 이 정적 수정만으로 Grounding 품질 gate 통과나 Q4
  우승을 주장하지 않으며, Q4 복구 확인 후에만 Q5 후보로 진행한다.

### 2026-09-01 07:10 KST — Clean imatrix and Actual Q4/Q5 Dev Selection

- clean 자산: owner-only 합성 calibration에서 clean one-pass imatrix를 재생성해
  `sha256:8d1de263…7c4d40f`로 고정했다. pinned llama.cpp b10419 image는
  `sha256:c85eec9b…618ef`, binary `ec759347…0aeb`, build manifest `3f02184c…9d8e`, SBOM
  `137cc423…dfb6`이다. 최종 pair evidence `18f33eda…a31d`는 mixed Q4/Q6
  19,294,014,080 bytes·`318c244e…248f`와 Q5 18,679,614,080 bytes·`d709a46e…2219`를 PASS로 묶는다.
- 평가 복구: 첫 Q4 Grounding 기술 중단은 예상 가능한 구조 불합격을 프로세스 오류로 누출한 평가기
  문제였다. task별 invalid-output을 hash·지연·안정 오류 코드만 가진 typed 실패로 기록하고, 정확한
  privacy-safe child completion signal을 요구하도록 수정했다. 별도 Q4 Grounding 진단은 일반 37/40,
  injection 16/20까지 완주해 수정 경로를 확인했고 qualification 입력에는 사용하지 않았다.
- 동일 실행 계약: matrix `038617a1…ba64`, source bundle `cc9dddee…f39c`, lock
  `0b6a6483…7456`, synthetic Dev only, llama.cpp concurrency 1로 Q4와 Q5를 fresh `results-run3`에서
  각각 Extraction 120·Query 80·Grounding 40+Injection 20건 실제 RTX 4090 추론했다. sealed Test,
  freeze, route activation, 고객 데이터와 실제 사업 동작은 사용하지 않았다.
- Q4 결과: Extraction 13/120 구조 유효, p95 4,419.851 ms, 37.341 tok/s. Query는 Recall@10
  0.8375·exact coverage 0.5625·MRR 0.602788·nDCG 0.573787, p95 4,721.933 ms. Grounding은
  37/40, citation precision/recall 1.0, required fact 0.875, unresolved recall 0, deterministic replay
  0.925, p95 9,110.941 ms; Injection은 16/20·violation 0.20이다. 세 task gate 모두 FAIL이며 실행
  manifest는 `982bf190…b4f5`다.
- Q5 결과: Extraction 16/120 구조 유효, p95 4,249.741 ms, 37.392 tok/s. Query는 Recall@10
  0.85·exact coverage 0.725·MRR 0.6575·nDCG 0.652255, p95 4,816.867 ms. Grounding은 39/40,
  citation precision/recall 1.0, required fact 0.95, unresolved recall 0, deterministic replay 0.975,
  p95 9,290.092 ms; Injection은 20/20이지만 violation 0.25다. 세 task gate 모두 FAIL이며 실행
  manifest는 `01bc23f5…ab93`다.
- 선정: `absolute-gates-then-maximin/1.0.0`은 `NO_CANDIDATE_PASSED_ALL_THREE_DEV_GATES`로
  `NO_WINNER`를 기록했다. selection manifest SHA는 `5f56b3f7…e521`이고 Q5는 다음 Dev 개선의
  상대 우세 기준일 뿐 winner·release·PRIMARY가 아니다. Test evidence, artifact revision, 조직 mirror,
  signed activation과 자동 fallback은 0이다.
- 보호 실행/복구: Q4·Q5 각각 fresh completion state와 post-start evidence를 사용했다. 두 실행 뒤
  candidate container/network/process/`:18002` 잔여 0, 기존 VLM exact container/image/config/model
  identity·healthy·restart 0·OOM false, Counsel identity 12/12·running 12/12·OOM 0을 독립 확인했다.
  baseline healthy 10개는 10/10 healthy, API healthcheck none과 STT starting도 기준선 그대로다.
- 검증/Git: 기본 pytest `1230 passed, 94 skipped`, Ruff PASS, format 576 PASS, Pyright 0, shell
  syntax·`git diff --check` PASS, 기계적 test format 이후 영향 테스트 24 PASS. HEAD와 원격 기능
  브랜치는 `f2357ba0cee6`으로 유지했고 Commit·Push·PR·병합·artifact upload는 실행하지 않았다.
  사용자 소유 문서·원본 이미지·checkpoint·Docker volume과 `kaputt_best_vision_architecture.md`를
  수정·삭제하지 않았다.
- 미해결/다음 행동: Q5 profile에서 Extraction JSON/source quote 준수, Query Builder RAW 기준선,
  Grounding unresolved-condition recall과 injection safety를 Dev에서 먼저 개선한다. Q4는 고정 baseline으로
  보존한다. fresh Dev 세 gate를 모두 통과한 후보가 생길 때만 freeze→sealed Test 1회로 진행한다.

### 2026-09-01 12:23 KST — Q5 Extraction Inference-contract Recovery

- 목표/판단: Q5 Extraction 16/120 실패를 바로 QLoRA 문제로 단정하지 않고 prompt·schema·llama.cpp
  계약부터 진단했다. 기존 v2 실패가 모두 `LLM_INVALID_STRUCTURED_OUTPUT`로 합쳐져 있었고, 실제 Q5
  평가는 MLX Dev에서 선택했던 `2.0.0-local.2`가 아니라 production `2.0.0`만 사용했음을 확인했다.
- 구현: strict JSON decode 뒤 Pydantic error type만으로 invalid JSON, token truncation, missing field,
  enum/literal, extra field, schema constraint를 분류한다. 원문·field path·validation message·provider
  response는 보존하지 않는다. typed observation evidence에는 정렬된 안정 오류 코드별 count만 추가했다.
  `screen_qwen4090_extraction_prompts.py`는 고정 synthetic Dev 20건 production/local.2 비교와, canary
  통과 후 local.2 단독 전체 Dev 120건만 허용한다. Test·freeze·release·Core route 기능은 없다.
- Q5 canary: 동일 candidate/runtime에서 production은 3/20, schema constraint 17건이었다. local.2는
  20/20 구조 유효·exact quote 1.0, issue F1 0.947368, requested-action F1 0.933333, p95
  4,456.622 ms·40.433559 tok/s, prompt-injection/reasoning/forbidden-field 0으로 선두였다. owner-only
  report SHA는 `ff3d7bbf…45f1b`이며 raw input/prediction/request ID는 없다.
- Q5 전체 Dev: local.2는 115/120 구조 유효·exact quote 0.958333으로 production 16/120 대비 크게
  개선됐다. 남은 실패 5건은 모두 `LLM_SOURCE_QUOTE_MISMATCH`다. issue F1 0.947368,
  requested-action F1 0.905028, p95 4,478.511 ms·40.648919 tok/s와 세 안전 지표 0은 PASS다.
  그러나 system-missing 0.941667, action-consistency 0.85, text-ambiguity F1 0.224299 및 100% 구조·
  인용 gate가 FAIL이라 Extraction 전체 gate는 아직 FAIL이다. report SHA는 `eadea5c0…b06fb`다.
- 보호 실행/복구: 두 실행 모두 fresh completion state와 이중 watchdog을 사용했고 post-start SHA는
  각각 `0cdddacf…751f`, `5eeaddea…3e70`이다. 각 종료 뒤 기존 VLM exact image/config/model identity,
  healthy·restart 0·OOM false, Counsel 기존 container identity 12/12·running 12/12, 후보
  container/network/process/`:18002` 잔여 0을 독립 확인했다.
- 검증/보존: Ruff PASS, 제품 코드·scripts·tests format 578 PASS, Pyright 0, 기본 pytest
  `1240 passed, 94 skipped`, `git diff --check` PASS다. 전체 repo format check의 유일한 지적은 사용자
  소유 `kaputt_best_vision_architecture.md` 기존 코드블록이며 지침대로 수정하지 않았다. Commit·Push·
  PR·Test·freeze·Shadow·route activation·실제 사업 동작은 0이다.
- 미해결/다음 행동: local.2 스키마와 구조는 유지하고 exact substring 복사 규칙과 Dev의 ambiguity
  taxonomy만 보강한 새 Dev-only prompt를 만든다. 고정 20건에서 local.2 대비 안전·구조 회귀 없이
  개선될 때만 전체 Dev 120건으로 확장한다. 이 단계가 정체된 뒤에만 별도 합성 학습 데이터와 사람
  검수 라벨을 사용한 Extraction QLoRA를 검토한다. Query Builder와 Grounding gate는 별도 미해결이다.

### 2026-09-01 14:42 KST — Q5 Extraction Dev-only Prompt Recovery Closeout

- 범위/안전: sealed Test를 열지 않고 고정 synthetic Dev만 사용해 Q5의 `local.2` 대비
  `local.4`·`local.5`·`local.6`을 순서대로 진단했다. 세 후보는 runtime prompt registry와
  `__all__`에서 제외했고 freeze·release·PRIMARY·Core route·실제 사업 동작을 만들지 않았다.
- 20건 canary: `local.4`는 ambiguity F1 `0.869565`까지 개선했지만 action F1 `0.857143`, p95
  `6,203.244 ms`로 회귀해 중단했다. `local.5`는 구조·정확 인용 20/20, issue/action F1 1.0,
  ambiguity F1 `0.666667`, p95 `5,070.952 ms`, 안전 위반 0이었다. 압축 확인용 `local.6`은
  ambiguity F1 `0.516129`, p95 `5,017.840 ms`라 중단했다. 각 보고서 SHA는 `874f77de…35fb`,
  `980b8752…744`, `52ba228b…fe9e`다.
- 전체 Dev 판정: 의미 품질이 더 안정적인 `local.5`를 한 번만 120건으로 확장했다. 구조·Pydantic·
  정확 인용은 120/120, issue F1 1.0, requested-action F1 `0.976744`, action consistency
  `0.966667`, system-missing 1.0, ambiguity F1 `0.697674`, p95 `5,084.207 ms`, throughput
  `40.808092 tok/s`, injection/reasoning/forbidden-field 위반 0이다. 보고서 SHA는
  `e574f9a5…196c1`이다.
- Gate/판단: ambiguity `0.7`과 p95 `5,000 ms`를 근소하게 못 넘어 Extraction은 여전히 FAIL이다.
  `local.5`는 Dev-only·unregistered로 보존하고 Test·freeze는 금지한다. 구조·인용 문제는 닫혔으므로
  즉시 QLoRA로 가지 않고 PII 없는 ambiguity confusion aggregate와 결정론적 검증·latency correction을
  먼저 한 번 검증한다.
- 보호 복구: 완료 manifest를 정상 전달한 뒤 VLM은 기존 container ID, exact image/config/model,
  healthy, restart 0, OOM false로 복구됐다. Counsel은 identity 12/12·running 12/12·OOM 0이며 후보
  container/network/`:18002` 잔여는 0이다. post-start evidence SHA는 `a830f292…d705`다.
- 검증/보존: 관련 52 tests, Ruff, Pyright 0 PASS. 전체 회귀 결과는 아래 최종 검증 후 메타데이터에
  반영한다. Commit·Push·PR 없음; 사용자 문서·원본 이미지·checkpoint·Docker volume과
  `kaputt_best_vision_architecture.md`를 변경·삭제하지 않았다.
- 미해결/다음 행동: Extraction aggregate ambiguity TP/FP/FN을 추가해 실패 방향을 확인하고,
  결정론적 ambiguity guard와 llama.cpp p95를 분리 조정한다. 두 gate가 닫히지 않을 때만 별도 합성
  학습 데이터·사람 검수 라벨 기반 Extraction QLoRA를 설계한다. Query Builder와 Grounding은 계속
  별도 FAIL이며 세 task fresh Dev PASS 전에는 Test를 열지 않는다.

### 2026-09-01 14:44 KST — Q5 Prompt Recovery Final Regression

- 전체 회귀: 기본 pytest `1243 passed, 94 skipped`, Ruff PASS, 제품 코드·scripts·tests format
  `578 files already formatted`, Pyright 0, `git diff --check` PASS다.
- 최종 경계: `local.5`는 여전히 Dev-only FAIL이며 runtime 선택·Test·freeze·route 변경 0이다.
  Commit·Push·PR은 수행하지 않았다.

### 2026-09-01 17:40 KST — Q5 Extraction Synthetic-Dev Gate Closure

- 진단 계약: Extraction prompt screen evidence schema를 `1.3`으로 올리고 원문·예측·request ID 없이
  ambiguity 전체/label별 TP·FP·FN, provider/end-to-end/adapter-overhead p50·p95를 남긴다. `local.5`
  20건은 `TP=10/FP=8/FN=2`; provider p95 `5,111 ms`, adapter overhead p95 `5.184 ms`로 잔여
  지연이 모델 제공 경로에 집중됨을 확인했다.
- bounded 후보: `local.7`은 p95 `4,646.459 ms`였지만 issue/action/guarded ambiguity F1이
  `0.75/0.888889/0.514286`로 회귀해 20건에서 중단했다. `local.5` 계약을 보존하고 summary만 한 문장
  120자로 제한한 `local.8`과 version/hash 고정 Dev-only ambiguity guard는 canary 20/20, 세 F1 1.0,
  p95 `4,801.166 ms`, 안전 위반 0을 달성해 전체 Dev로 확장했다.
- 전체 Dev: guarded `local.8` Q5는 120/120 구조·Pydantic·정확 인용, issue F1 `0.987448`, action
  F1 `0.976744`, system-missing 1.0, action consistency `0.966667`, ambiguity F1 1.0
  (`TP=72/FP=0/FN=0`), p95 `4,908.237 ms`, `40.432121 tok/s`, 안전 위반 0이다. canonical
  Extraction gate 15/15 PASS, report SHA `2612cbed…b14a`, scoring profile `b6ea1403…d882`, gate
  digest `6f5cfb97…336fa`다.
- 경계: 이는 synthetic Dev의 Extraction만 PASS한 결과다. `local.8`과 guard는 runtime registry에
  등록하지 않았고 Query Builder·Grounding은 계속 FAIL이므로 전체는 `NO_WINNER`·
  `NO_RELEASE_ELIGIBLE`다. sealed Test·freeze·Shadow·PRIMARY·route activation·실제 사업 동작은
  0이며 Extraction QLoRA는 보류한다.
- 보호 실행/복구: completion signal 뒤 기존 VLM container/image/ref/config/model exact identity,
  healthy·restart 0·OOM false를 독립 확인했다. Counsel은 identity 12/12·running 12/12·OOM 0,
  candidate container/network/`:18002` 잔여 0이다. post-start evidence SHA는 `95e8feb1…50ecc`다.
- 검증/보존: 기본 pytest `1253 passed, 94 skipped`, Ruff PASS, format `580 files already formatted`,
  Pyright 0, `git diff --check` PASS다. Commit·Push·PR 없음; 사용자 문서·원본 이미지·checkpoint·
  Docker volume과 `kaputt_best_vision_architecture.md`를 수정·삭제하지 않았다.
- 다음 행동: Grounding의 미해결 조건 recall과 injection safety를 고정 20건 canary로 진단·복구한 뒤
  fresh Dev로 확장한다. 그 다음 LLM Query Builder가 RAW→HYBRID 기준선을 모든 고정 지표에서 이길
  때만 PRIMARY 후보로 검토한다. 세 task fresh Dev PASS 전에는 sealed Test를 열지 않는다.

### 2026-09-01 18:19 KST — Q5 Grounding Synthetic-Dev Gate Closure

- 실패 분리: 기존 Q5 production `1.1.0`은 정상 39/40, required fact `0.95`, unresolved recall 0,
  replay `0.975`였고 공격 20건 중 5건이 거부 설명에서 위험 단어를 되풀이해 injection violation
  `0.25`였다. 인용 precision/recall/completeness는 이미 1.0이어서 모델 지식보다 prompt/runtime
  identity 불일치가 우선 병목이었다.
- 구현: `generate_grounding_raw_observations`와 scorer에 기본값을 유지한 prompt·고정 record 주입점을
  추가하고 `screen_qwen4090_grounding_prompts.py`를 만들었다. screen은 synthetic Dev만 허용하고
  aggregate metrics·안정 실패 코드·prompt/profile/result digest만 보존하며 Test·freeze·selection·
  route 기능은 없다. 새 단위 테스트는 고정 12+8 canary, 공격 범주 8개, 전체 40+20, PII 없는 보고서와
  owner-only fresh output을 검증한다.
- canary: 기존 runtime prompt `1.1.0-local.2`를 Q5에서 정상 12건+공격 범주별 8건으로 실행해
  canonical gate 25/25 PASS를 확인했다. 모든 grounding 의미/안전 지표는 1.0/0 기준을 충족했고 report
  SHA는 `e752095d…b3b7`이다.
- 전체 Dev: 정상 40건은 각각 deterministic replay를 포함하고 공격 20건은 단일 호출했다. 정상·공격
  성공 40/40·20/20, JSON/Pydantic·citation validity/precision/recall/completeness·required fact·
  unresolved recall·replay 모두 1.0, allowlist/unknown/cross-tenant/wrong-version/duplicate citation·
  forbidden claim/field·overstatement·injection·reasoning leakage 모두 0이다. 정상 이중 replay p95
  `7,985.891 ms`, 공격 p95 `3,517.389 ms`; report SHA `a36f3881…40cf`, prompt hash
  `e375f153…2297`, profile digest `2f862cfa…5515`, result-set digest `e0cc6e6c…b762`다.
- 경계: 기존 runtime prompt의 synthetic Dev Grounding task gate만 통과했다. Extraction과 Grounding은
  개별 PASS지만 Query Builder가 RAW→HYBRID 기준 미달이고 최종 prompt/runtime identity로 joint 세 task
  rerun을 하지 않았으므로 전체는 계속 `NO_WINNER`·`NO_RELEASE_ELIGIBLE`다. sealed Test·freeze·
  Shadow 승격·PRIMARY·route activation·실제 사업 동작은 0이다.
- 보호 복구: report SHA로 completion을 정상 전달했다. 기존 VLM exact container/image/ref/config/model
  identity·healthy·restart 0·OOM false, Counsel identity 12/12·running 12/12·OOM 0, candidate
  container/network/`:18002` 잔여 0을 독립 확인했다. post-start evidence SHA는 `c03c6e78…740c`다.
- 검증/보존: 관련 41 tests PASS 후 기본 pytest `1257 passed, 94 skipped`, Ruff PASS, format
  `582 files already formatted`, Pyright 0, `git diff --check` PASS다. Commit·Push·PR 없음; 사용자
  문서·원본 이미지·checkpoint·Docker volume과 `kaputt_best_vision_architecture.md`를 변경·삭제하지
  않았다.
- 다음 행동: LLM Query Builder의 실패를 query purpose/filter와 실제 retrieval Recall@10·coverage·
  MRR·nDCG로 분리한다. frozen RAW→HYBRID 기준선을 모두 이기는 bounded prompt가 없으면 LLM Query
  Builder를 SHADOW에 남기고 RAW를 기본 경로로 유지한다.

### 2026-09-01 23:37 KST — GX10 Model-engine Session Handoff

- 사용자 입력: GB10 기반 ASUS DGX Spark 계열 장비를 확보했고 Tailscale 장비 이름은
  `gx10-ade1`이다. Mac에서 4090과 GX10을 직접 제어하고 compact 결과만 회수해 다음 Codex 세션의
  컨텍스트 사용과 반복 원격 조작을 줄이려 한다.
- 인계: `SESSION_HANDOFF_2026-09-01_GX10_MODEL_ENGINE.md`에 새 세션용 복사 프롬프트, 현재 Q5
  artifact/runtime digest, Extraction·Grounding PASS와 Query Builder FAIL, 장비 역할, 안전 경계,
  읽기 전용 inventory→ARM64 runner→동일 Q5 benchmark→BF16/QLoRA 순서를 기록했다.
- 검증: Git branch `codex/operator-console-product-direction`, HEAD/원격 `f2357ba0cee6`, dirty
  worktree와 candidate matrix의 clean imatrix `8d1de2…d40f`, Q5 `d709a4…2219`, llama.cpp b10419
  image `c85eec…18ef`를 읽기 전용으로 재확인했다. Accepted ADR-0002·0113·0125와 4090 Dev
  runbook을 다시 읽었다.
- 미실행: GX10 접속·인벤토리·설치·파일 전송·llama.cpp build·모델 canary·benchmark·QLoRA는 모두
  `NOT_RUN`이다. 문서 행동만 변경했으므로 전체 backend/Web/GPU 회귀도 `NOT_RUN`이다.
- 보존: 기존 미커밋 변경, 사용자 문서·원본 이미지·checkpoint·Docker volume,
  `kaputt_best_vision_architecture.md`, 4090 VLM/Counsel 상태를 변경하지 않았다. Secret을 인계 문서에
  기록하지 않았고 Commit·Push·PR·route activation·sealed Test·실제 사업 동작은 0이다.

### 2026-09-01 23:44 KST — GX10 Reachability and SSH Authentication Gate

- 문서/로컬 기준: 지시된 AGENTS→CURRENT_STATUS→GX10 handoff 순서와 handoff가 지정한 Accepted
  ADR-0002·0113·0125, 4090 Dev runbook을 완독했다. Git branch/HEAD/upstream 일치와 dirty entry
  103개를 읽기 전용으로 확인하고 기존 변경을 그대로 보존했다.
- 도달성: `gx10-ade1`은 Tailscale peer online·active, Linux 표기, ping 128 ms로 `PASS`다. 주소와
  사용자명은 결과 원장에 기록하지 않았다.
- 인증 Gate: password·keyboard-interactive를 비활성화한 공개키-only batch SSH가 인증 거부로
  `BLOCKED`됐다. 비밀번호를 요청·사용·저장하지 않았고 GX10에서 실행된 원격 명령은 0개다.
- 결과: `gx10_inventory/1.0.0` compact JSON을 owner-only mode 0600의 Git 제외 경로
  `local-data/gx10-inventory/2026-09-01T234449+0900/inventory.json`에 기록했다. hardware/OS/CUDA/
  Docker/storage/network/temperature/power/service inventory는 모두 `NOT_RUN`이다.
- 보존/미실행: 설치·upgrade·reboot·prune·파일/모델 전송·ARM64 build·canary·benchmark·PRIMARY/
  route 변경·4090 서비스 변경·Commit·Push·PR은 모두 0이다.
- 다음 행동: 사용자가 직접 인증해 공개키 SSH를 허용한 뒤 같은 read-only inventory를 재개한다.

### 2026-09-02 00:12 KST — GX10 Read-only Inventory and Execution-plan Closeout

- 인증/인벤토리: 사용자 측 공개키 등록을 확인한 뒤 password·keyboard-interactive를 비활성화한
  batch SSH로 `gx10-ade1` inventory를 완료했다. 첫 수집은 command transport quoting 오류로 실패했지만
  원격 변경 0인 상태에서 안전한 전달 방식으로 재실행해 `PASS`했다. ASUS GX10, aarch64, GB10 CC 12.1,
  memory 130,663,038,976 bytes, NVMe 4,096,805,658,624 bytes, Ubuntu 24.04.4, driver/CUDA
  580.173.02/13.0, Docker 29.2.1 arm64와 NVIDIA CDI를 확인했다.
- 미검증 경계: 10GbE는 지원하지만 link down이어서 negotiated speed/throughput은 `NOT_RUN`; 실제 GPU
  container canary도 `NOT_RUN`이다. CDI discovery를 runtime qualification으로 승격하지 않았다.
- compact evidence: inventory는 owner-only mode 0600의
  `local-data/gx10-inventory/2026-09-02T000756+0900/inventory.json`, SHA-256
  `ed46bce6…e59a`다. ARM64 build·control input·Khrin→GX10 direct transfer 계획은
  `local-data/gx10-plan/2026-09-02T001239+0900/plan.json`에 exact path/bytes/SHA-256/rollback과
  confirmation gate를 기록했다.
- artifact 재확인: Khrin 원본 Q5는 18,679,614,080 bytes/`d709a4…2219`, clean imatrix는
  13,663,264 bytes/`8d1de2…d40f`로 기존 원장과 일치했다. Q5는 Mac을 경유하지 않는 direct transfer,
  owner-only unique partial, destination hash 검증 후 atomic rename으로만 계획했다.
- 4090 보존: read-only 확인에서 VLM은 healthy, Counsel 12개 container는 running이었다. STT container
  1개는 기존 `unhealthy`로 관측됐으며 원인 조사·restart·변경을 하지 않았다. 이번 단계의 4090 service
  mutation은 0이다.
- 보존/미실행: 비밀번호 요청·사용·저장, GX10/Khrin remote write, 설치·upgrade·reboot·prune,
  파일/모델 전송, ARM64 build, container start/stop, canary·benchmark, sealed Test·freeze·PRIMARY·route
  activation, Commit·Push·PR은 모두 0이다. 다음 행동은 원격 변경 없이 GX10 로컬 runner를 구현·검증하는
  것이다.

### 2026-09-02 00:30 KST — GX10 Runner, Control Transfer, and Q5 Transport Gate

- 구현: 기존 4090 `linux/amd64`·sm_89 build 파일은 수정하지 않고 GX10 전용 `linux/arm64`·sm_121
  Dockerfile/build script, CDI Compose, remote engine과 Mac controller를 추가했다. 7개 phase는
  `status/prepare/serve/canary/evaluate/report/stop`으로 분리되고 state-changing phase는 local/remote
  `ALLOW_GX10_MUTATION=YES`, bounded append-only run ID, owner-only env/evidence, stale project 검사와 failed
  serve exact-project cleanup을 요구한다. PRIMARY/core route/automatic fallback label은 모두 false다.
- 로컬 검증: shell syntax PASS, GX10+기존 4090 build contract focused pytest 9/9 PASS, Ruff·format·
  `git diff --check` PASS다. 실제 controller `status`도 Docker active, model absent, service absent,
  changes 0의 compact `csight_gx10_status/1.0.0`으로 PASS했다.
- 준비/control: 사용자 진행 확인 뒤 `/home/aidi_lab/csight-gx10` owner-only layout을 만들었다. reviewed
  GX10 Dockerfile/build/Compose/remote runner/candidate matrix 5개, 합계 22,198 bytes를 fresh staging으로
  보내 local/remote bytes·SHA-256 일치와 final path 부재를 확인한 뒤 새 control path로 이동했다.
  기존 경로 overwrite 0, staging은 비운 뒤 제거했다.
- Q5 Gate: Khrin 원본 Q5 18,679,614,080 bytes/`d709a4…2219`, GX10 final/partial 부재와 가용
  3,678,448,889,856 bytes를 재확인했다. Khrin→GX10 표준 public-key SSH와 Tailscale SSH는 인증
  `BLOCKED`다. Taildrop send/receive CLI는 PASS지만 receiver가 uninspected inbox 전체를 이동하므로
  다른 파일 보호를 위해 시작하지 않았다. 모델 bytes·partial·image build·container change 0이다.
- 안전 보강: 최종 검토에서 content-addressed path와 bytes뿐 아니라 full Q5 SHA-256을 serve 전 다시
  확인하도록 runner를 보강했다. bash/focused 9/Ruff/format/diff를 재통과했고 8,648 bytes,
  `f81d7e…d812` 파일을 기존 control file을 덮어쓰지 않는 새 이름으로 remote SHA 검증 후 배치했다.
- compact evidence: runner `local-data/gx10-runner/2026-09-02T002522+0900/result.json`, prepare
  `local-data/gx10-prepare/2026-09-02T002700+0900/result.json`, control transfer
  `local-data/gx10-control-transfer/2026-09-02T002800+0900/result.json`, blocked model transfer
  `local-data/gx10-model-transfer/2026-09-02T003000+0900/result.json`을 owner-only로 기록했다.
- 보존: password 요청·사용·저장, 기존 4090 VLM/Counsel mutation, Docker prune, model transfer,
  image build, container start/stop, canary·benchmark, sealed Test·freeze·PRIMARY·route activation,
  Commit·Push·PR은 0이다. 다음 행동은 persistent dedicated key 또는 bounded one-shot Tailnet server 중
  안전한 direct transport 하나를 사용자가 선택하는 것이다.

### 2026-09-02 00:57 KST — GX10 Q5 One-shot Direct Transfer

- 구현/검증: exact source/client/token/file 하나만 허용하고 Khrin Tailscale 주소의 임시 port 1개에
  bind하며 단일 request 뒤 종료하는 Python server, GX10 owner-only content-addressed finalizer와 remote
  receiver를 구현했다. source symlink/bytes/SHA, client IP, constant-time token route, fresh partial/final,
  allowed root, atomic move와 final mode 0600을 fail closed로 검증한다. Ruff·format·shell syntax와 GX10
  runner/build 포함 focused pytest 13/13 PASS다.
- 실패 분리: 첫 command는 실행 전 cleanup 명령 안전 정책으로 거부돼 remote change 0이었다. 다음 시도는
  SSH가 curl `write-out`의 공백 인자를 재분리해 binary를 stdout으로 보냈고 즉시 중단했다. 확인 결과
  partial/final은 absent, one-shot server process도 absent였다. 실패 시도에서 생성된 빈 owner-only incoming
  directory 하나는 자동 삭제하지 않고 보존했다.
- 성공 전송: remote receiver로 모든 curl argument를 GX10 내부에서 고정한 fresh run은 HTTP 200,
  18,679,614,080 bytes, 597.393114초, 평균 31,268,546 B/s로 완료됐다. Mac은 orchestration만 했고 Q5
  data path는 Khrin→GX10 Tailnet direct다.
- integrity/finalize: Khrin server는 serve 전 source bytes/SHA를 확인했다. GX10은 fresh partial의 bytes와
  SHA `d709a4…2219`를 확인한 뒤 content-addressed final path로 atomic move하고 final bytes/SHA를 다시
  확인했다. final owner는 `aidi_lab`, mode 0600, 종료 후 가용 공간은 3,659,767,762,944 bytes다.
- 복구/보존: one-shot server process와 GX10 model container는 absent다. 4090 VLM은 healthy, Counsel
  12개는 running이며 기존 STT unhealthy 상태는 변경하지 않았다. 기존 4090 service mutation,
  GX10 image build/container start/stop, imatrix transfer, sealed Test·freeze·PRIMARY·route activation,
  Commit·Push·PR은 0이다.
- compact evidence: owner-only
  `local-data/gx10-model-transfer/2026-09-02T005727+0900/result.json`에 성공 결과와 실패 시도 경계를
  append-only로 기록했다. 다음 행동은 host package 설치 없이 pinned llama.cpp source를 준비하고 기존
  CUDA 13 image identity로 ARM64 build preflight를 수행하는 것이다.

### 2026-09-02 01:27 KST — GX10 ARM64 Build, Isolated Q5 Canary, and Safe Stop

- source/build: GX10에 host package를 설치하지 않고 pinned llama.cpp b10419 exact commit
  `aee56b3…ef28` clean source와 기존 CUDA 13.0.1 arm64 base로 build했다. 첫 시도는
  `GGML_CPU_ALL_VARIANTS=ON`이 GCC 미지원 ARMv9.2 SME를 강제해 실패했다. 해당 build root와 child만
  TERM으로 종료하고 process 0/image absent를 확인한 뒤, GX10 전용 Dockerfile만 `OFF`로 고쳐
  `csight/llama.cpp:b10419-cuda13.0.1-arm64-gb10`, image ID `b664e8…9ac4`, architecture arm64,
  6,732,715,596 bytes로 PASS했다. 기존 4090 amd64/sm_89 계약은 수정하지 않았다.
- GPU/runtime Gate: 새 image를 network none/read-only/CDI `nvidia.com/gpu=all`로 실행해 NVIDIA GB10,
  124,609 MiB reported memory를 확인하고 container residue 0으로 종료했다. Q5는 owner/mode 0600과
  full SHA `d709a4…2219`, image exact ID를 serve 전 재검증했다. API key는 GX10에서 생성해 mode 0600
  env에만 두고 Mac stdout/file로 가져오지 않았다.
- 실패/복구: 첫 serve는 pinned b10419 CLI가 reasoning `none`을 거부했다. runner가 container log를
  owner-only로 보존하고 stable error를 반환하도록 보강했으며, 재현 run도 exact Compose project
  container/network residue 0을 확인했다. 지원 값 `off`로 새 content-addressed Compose와 fresh runtime
  env를 만들고 run `20260902T013000` serve를 PASS했다.
- canary/report: synthetic connectivity canary는 p95 695.668ms/TTFT 695.560ms, 단일 synthetic
  performance smoke는 p95 579.507ms/TTFT 579.411ms로 PASS했다. remote evidence directory는 0700,
  file은 0600이며 report digest는 `bc45d35b…cef3`다. 이는 health/경로 smoke일 뿐 Dev quality 또는
  4090 대비 성능 자격이 아니다. decode tok/s, peak unified memory, 4K/16K/32K와 세 task Dev는
  `NOT_RUN`이다.
- stop/preservation: report 후 exact candidate project만 stop해 GX10 candidate container/network 0,
  service false, Q5 present를 재확인했다. RTX 4090 VLM은 healthy, Counsel 12개 running, 기존 STT 1개
  unhealthy unchanged다. 설치·upgrade·reboot·prune, PRIMARY·route·fallback·freeze·sealed Test,
  Commit·Push·PR은 0이다. 기존 dirty worktree, 사용자 문서와 `kaputt_best_vision_architecture.md`를
  보존했다.
- compact evidence: owner-only `local-data/gx10-build/2026-09-02T011100+0900/result.json`과
  `local-data/gx10-{serve,canary,evaluate,report,stop}/2026-09-02T013000+0900/result.json`에 각 phase를
  기록했다. 최종 집중 pytest 14/14, Ruff check·format, 5개 shell syntax, 15개 GX10 JSON parse/mode
  0600, `git diff --check`가 PASS했다. 전체 제품 회귀는 infra-only 범위여서 `NOT_RUN`이다. 다음 행동은
  이 runner를 확장해 동일 고정 입력의 warmup·반복 측정, decode/peak memory, 4K/16K/32K와 4090 동일
  Dev task 비교를 수행하는 것이다.

### 2026-09-02 01:55 KST — GX10 Q5 Context and Concurrency Benchmark

- 구현/계약: 합성 prompt만 생성하고 `/tokenize`로 각 context slot의 output/headroom 640 tokens를 남긴
  입력을 만든다. strict JSON schema, temperature 0, streaming first content와 usage token을 검증하고
  warmup을 제외한 p50/p95, per-request decode와 wall throughput, system/GPU memory·온도·전력을 owner-only
  report에 남긴다. prompt는 SHA만 저장하고 raw prompt/response/API key는 Mac으로 회수하지 않는다.
  runtime env writer는 per-slot context와 parallel을 받아 total context를 곱해 고정하며 PRIMARY/route
  identity를 포함하지 않는다.
- 첫 4K 시도/복구: 모델 요청 5/5는 성공했지만 GB10의 `nvidia-smi memory.used`가 N/A라 compact parser의
  peak memory 필수 Gate가 실패했다. report `7e7383…acec`과 원격 evidence를 덮지 않고 candidate를 stop했다.
  `PROC_MEMINFO_SYSTEM_USED` fallback을 출처 필드와 함께 추가하고 parser 실패를 traceback 대신
  `GX10_BENCHMARK_RESULT_INVALID`로 바꿨다. 이 memory 수치는 절대 host-used unified 표본이며 모델 단독
  allocation으로 해석하지 않는다.
- 4K concurrency 축: 동일 prompt SHA `d8a954…eb43`, input mean 3,495 tokens다. c1은 5/5,
  TTFT p50/p95 167.577/193.291ms, latency 3,129.124/3,159.736ms, decode 11.486934 tok/s, wall
  10.849114 tok/s, peak 26,622,164,992 bytes·50°C·43.71W다. c2는 6/6지만 TTFT/latency p95
  6,448.638/9,924.916ms와 decode 7.903149 tok/s, c4는 8/8지만 18,539.903/23,028.159ms와
  4.285165 tok/s로 tail latency와 per-request decode가 악화됐다. c4 peak는 28,937,760,768 bytes,
  61°C, 78.03W다.
- context 축: concurrency 1에서 16K는 input mean 15,780 tokens, 3/3, TTFT/latency p95
  207.330/3,671.047ms, decode 10.533026 tok/s, peak 27,223,945,216 bytes다. 32K는 input mean
  32,173 tokens, 2/2, 241.216/3,566.045ms, decode 10.580458 tok/s, peak 27,914,141,696 bytes,
  63°C다. 다섯 profile 합계 24/24, timeout/schema failure 0이다. full context×concurrency cross-product와
  soak/fault는 `NOT_RUN`이다.
- 비교/판정: 4090 역사적 Q5 Extraction은 p95 4,908.237ms/40.432121 tok/s, Grounding 정상 p95
  7,985.891ms지만 실제 task Dev라 이번 short-output synthetic hardware profile과 동일 workload가 아니다.
  기존 VLM/Counsel을 보호하기 위해 live same-harness 4090은 `NOT_RUN`이며 직접 numeric ranking을 하지
  않는다. 32K 기술 수용과 큰 memory headroom은 Model Lab에 유용하지만 c2/c4 latency 악화, 동일 세 task
  Dev·4090 same-harness 부재 때문에 GX10은 `MODEL_LAB_SHADOW_CANDIDATE`, PRIMARY는 `BLOCKED`다.
- 종료/보존: 매 profile report 후 exact Compose project만 stop했다. 최종 GX10 candidate container/network
  0, Q5/image/evidence present다. 01:55 KST Khrin VLM healthy, Counsel 12 running, 기존 STT unhealthy
  unchanged다. 비밀번호, 설치·upgrade·reboot·prune, PRIMARY·route·fallback·freeze·sealed Test,
  Commit·Push·PR은 0이고 dirty worktree와 `kaputt_best_vision_architecture.md`를 보존했다.
- 최종 검증: benchmark/runtime/GX10 build·transfer focused pytest 17/17, Ruff check·format, shell syntax,
  compact result JSON parse/mode 0600과 `git diff --check`가 PASS했다. 최종 live status도 GX10 service
  false/model present, Khrin VLM healthy/Counsel 12 running이다. 전체 제품 회귀와 live Dev는 `NOT_RUN`이다.
- compact evidence: owner-only
  `local-data/gx10-benchmark/2026-09-02T015520+0900/result.json`에 다섯 profile, 첫 실패, source와
  comparison boundary를 기록했다. 다음은 기존 서비스 중단 없이 GX10 세 task Dev를 실행할 안전한
  evaluator 경로를 설계하거나, 별도 사용자 승인 아래 4090 VLM unconditional restore가 있는 same-harness
  maintenance window를 여는 것이다.
- three-task Dev preflight: 기존 evaluator의 live task 함수만 직접 호출하는 우회도 matrix runtime
  identity와 post-start evidence binding을 건너뛰므로 거부했다. owner-only
  `local-data/gx10-dev-preflight/2026-09-02T015846+0900/result.json`에
  `GX10_DEV_RUNTIME_IDENTITY_CONTRACT_MISSING`을 기록했다. 이 단계의 endpoint call, API key copy,
  candidate/container 변경은 0이다.

### 2026-09-02 02:07 KST — GX10 Operational Latency Requirement Reinterpretation

- 사용자 요구: 절대 저지연보다 하루 유입 문의량과 사람의 처리 한계가 중요하며, 모델이 문서 1건당
  5분 이상 걸리지 않으면 운영상 허용 가능하다. 이를 300,000ms/document의 현재 운영 latency 기준으로
  기록했다. daily inquiry, peak-hour arrival, reviewer count와 human documents/day는 아직 입력되지 않았다.
- 판정 변경: benchmark의 최악 p95는 4K c4의 23,028.159ms로 한도의 7.676%, headroom
  276,971.841ms다. 따라서 c2/c4 tail latency 증가는 운영 blocker가 아니라 비용·효율 최적화 항목이다.
  latency만으로 GX10을 Model Lab에 제한하지 않는다.
- 남은 Gate: 현재 benchmark는 34~36 output tokens의 synthetic schema 응답이라 실제 문서 1건의 전체
  Extraction→Query→Grounding 처리시간이나 documents/day를 증명하지 않는다. representative synthetic
  workflow로 end-to-end 성공률, queue wait, p95<300초와 일일 수요 대비 capacity headroom을 측정해야 한다.
  GX10 runtime identity 부재, three-task Dev 미실행, Query Builder `NO_WINNER`, PRIMARY 금지는 그대로다.
- 변경/증거: 모델·서비스·route 변경 0. owner-only
  `local-data/gx10-operational-capacity/2026-09-02T020730+0900/result.json`에 요구, 관측값, 미실행
  capacity와 다음 Gate를 기록했다. Commit·Push·PR 없음.

### 2026-09-02 02:12 KST — GX10 Quality-first Qualification Priority

- 요구/판정: LLM이 CSight의 Extraction, 검색 query 생성, 근거 설명에서 큰 역할을 담당하므로 semantic
  quality를 최상위 Gate로 둔다. 세 task는 모두 absolute PASS여야 하며 weighted average로 Query Builder
  실패를 Extraction/Grounding 성공이 덮을 수 없다. latency 300초 상한은 fail-safe 운영 기준이지만
  모델 선택의 주 최적화 목표가 아니다.
- quality Gate: Extraction은 strict structure·exact quote와 기존 issue/action/missing/consistency/ambiguity
  하한, safety violation 0을 요구한다. Query Builder는 frozen RAW→HYBRID 대비 Recall@10, exact coverage,
  MRR@10, nDCG@10을 모두 이겨야 하며 아니면 SHADOW에 남고 RAW가 기본이다. Grounding은 citation/fact/
  unresolved/replay 1.0과 citation·injection violation 0을 요구한다.
- 현재 상태: 4090 Q5의 Extraction과 Grounding은 개별 synthetic Dev PASS지만 Query Builder는 FAIL이고
  final identity joint rerun도 없다. GX10은 additive runtime identity contract가 없어 three-task Dev
  `BLOCKED`다. 따라서 전체는 `NO_WINNER`·`NO_RELEASE_ELIGIBLE`, PRIMARY·Test·freeze 0이다.
- 안전 경계/증거: 모델은 evidence analysis와 advisory output만 만들고 versioned policy와 인증된 사람
  검토가 최종 결정을 소유한다. 실제 환불·메일·결제·배송·CRM action 0. 기존 frozen matrix, 모델,
  서비스, route를 변경하지 않았다. owner-only
  `local-data/gx10-quality-priority/2026-09-02T021200+0900/result.json`에 우선순위와 all-task Gate를 기록했다.

### 2026-09-02 20:01 KST — GX10 User-installed Qwen3.8 Read-only Verification

- 읽기 전용 인벤토리: password/interactive auth를 금지한 공개키-only SSH로 확인했다. 기존 CSight Q5
  artifact는 18,679,614,080 bytes와 SHA `d709a4…2219`, pinned llama.cpp image는 `b664e8…9ac4`로
  그대로다. 별도로 사용자 설치 `vllm_node` 한 개가 host network에서 port 8000을 listen하며
  `RadixArk/Qwen3.8-27B-NVFP4`를 제공했다. health/models는 모두 HTTP 200, GPU process가 존재하고
  container restart는 0이다.
- runtime/capacity snapshot: vLLM은 `0.26.1rc1.dev1231+g7a9993878.d20260826`, API max context는
  32,768이다. 원본 config의 max position은 262,144지만 현재 endpoint 능력은 32,768로 해석한다.
  container memory는 약 24.29GiB, host unified memory available은 30,684,598,272 bytes였고 GPU
  utilization 0%, 34°C에서 관측했다. 장시간 soak, 실제 documents/day와 동시성 capacity는 `NOT_RUN`이다.
- text canary: 무상태 단일 요청이 HTTP 200/2.659초, strict JSON을 반환하고 명시 정책에 따라 환불
  비대상을 선택했다. 그러나 `human_review_required=false`를 반환했으므로 CSight의 사람 최종결정 경계는
  model compliance로 증명되지 않았다. 최종결정·외부 action은 계속 application/policy/authenticated
  human-review 계층이 강제하며 이 모델 출력은 advisory로만 취급한다.
- VLM canary: cached config는 `Qwen3_5ForConditionalGeneration`, vision config와 image/video token을
  포함한다. 메모리에만 생성한 96x64 합성 이미지에서 왼쪽 red, 오른쪽 blue, 가운데 green을 HTTP
  200/2.368초 strict JSON exact match로 식별했다. 이는 multimodal data path의 최소 연결 증거일 뿐,
  실제 문의 이미지·OCR·미세 결함·비교 이미지·공식 Kaputt label/E3 정확도 자격은 아니다.
- 변경/경계: GX10/4090의 container·model·service·route를 시작·중지·재기동·전환하지 않았고 설치,
  다운로드, 모델 전송, PRIMARY/fallback/freeze/Test, 비밀번호·API key 접근, Commit·Push·PR은 0이다.
  기존 dirty worktree와 `kaputt_best_vision_architecture.md`를 보존했다. 세 task joint Dev와 Query Builder
  gate는 여전히 미통과이므로 `NO_WINNER`·`NO_RELEASE_ELIGIBLE`, PRIMARY 금지를 유지한다.
- compact evidence: owner-only
  `local-data/gx10-live-{inventory,text-canary,model-metadata,vlm-canary}/20260902T200111+0900/result.json`에
  raw prompt/response와 credential 없이 네 단계 결과를 기록했다. 다음 행동은 사용자 설치 vLLM identity를
  additive GX10 runtime 계약에 고정한 뒤 frozen Dev의 Extraction→Query Builder→Grounding을 동일 identity로
  실행하는 것이다.

### 2026-09-09 — 출시 잔여 범위 문서 검토

- 검증: `PASS` — 현재 상태 원장, README, pilot readiness/onboarding 계약과 ADR-0103을 대조했다.
  이번 검토는 문서 기반이다. 최신 runtime 실측은 2026-09-02 기록이며 9월 9일 GPU·Core·고객 환경
  재검증과 새 모델 품질 평가는 `NOT_RUN`이다. 코드·서비스·route·Git staging 변경은 없다.
- 출시 순서 제안: 첫 고객/상품군 범위 확정 → 해당 고객 정책·대표 문의·사람 정답 준비 → GX10
  runtime identity와 Extraction/Query/Grounding 품질 검증 → Vision 적용 범위·권리 검토 → 고객별
  접근권한·개인정보·복원·장애·부하 검증 → 제한 파일럿 → 운영 결과로 정식 출시 범위 확정.
  이미 구현된 hybrid RAG, Citation Pack, 정책 engine, 사람 결정·상담원 UI를 새로 구축하는 작업은 아니다.
- 미해결: Query Builder와 GX10 final identity joint Dev, 대표 실제 상품 이미지 평가, 사용권 확인,
  고객 정책/IdP/retention/intake, 외부 백업 복원 2회·경보 수신, 20-session/20-workflow와
  release 모델·배포 artifact가 남아 있다. 파일럿 시작은 기존 구성 6개·운영 25개 gate를 따른다.
- 정정: 9월 2일 임의 text canary에는 사람 검토를 항상 true로 반환하라는 규칙이 없었고 CSight
  application의 실제 승인 경로를 호출하지 않았다. 따라서 `human_review_required=false` 한 건으로
  기존 application의 사람 승인 통제가 실패하거나 미구현이라고 판정할 수 없다. 해당 canary의
  CSight 안전 자격은 `NOT_RUN`으로 해석한다. 사람 최종결정 원칙은 기존 구현/계약에 이미 존재하며
  새 모델을 연결한 실제 전체 경로에서 재검증해야 한다. 과거 출력과 기록은 보존한다.
- 다음 체크리스트: [ ] GX10 현재 identity를 재확인하고 전용 평가 계약을 준비한다.
  [ ] 첫 고객의 상품군·정책·평가 자료를 확정한다. [ ] 위 AI 품질 및 고객 운영 gate를 완료한 후
  제한 파일럿을 판정한다. 모델 추가 학습·속도 최적화·범용 상품 확장·실제 자동 환불은 첫 출시의
  기본 선행 작업으로 추가하지 않는다. 코드 테스트·원격 실행은 이번 문서 검토에서 `NOT_RUN`이다.

### 2026-09-09 — Vision/LLM 주요 엔진 개선 검토

- 확인 `PASS`: Vision port와 canonical schema는 이미지 단위 assessment와 위치 detection을 구분한다.
  원장에는 Claim↔Detection/Evidence Alignment가 미구현이며 실제 E3의 정책 입력 연결도 미확정으로
  기록돼 있다. 두 모델 결합으로 품질이 개선됐다는 실측 근거는 이번 검토에서 확보하지 않았다.
- 개선 제안(미구현): 상품군별 정상/결함/촬영불량·미지원 입력과 사람 정답 구축, 결함 위치·기준 이미지
  비교와 판단 보류 평가, 고객 주장과 이미지 관찰의 지지/모순/판단불가 대조, LLM의 예외 정책 검색과
  인용 검증을 우선한다. 이미지에서 관찰 불가능한 냄새·작동불량 등의 주장을 시각 미검출로 반박하지 않는다.
- 모델 자체 개선 후보: 실제 반복 오류를 근거로 vision 도메인 적응과 LLM/VLM의 검수 데이터 기반
  추가 학습을 검토한다. 양자화 정밀도 차이는 동일 입력·설정으로 비교하고 성능 향상을 가정하지 않는다.
  기존 paired VLM 결함 평가 실패는 reference/crop 입력만으로 해결됐다고 재해석하지 않는다.
- 평가 제안: 상품/주문/유사 이미지 누출을 막은 holdout에서 vision-only, text-only, 결합 결과를 비교하고
  오탐·미탐·근거 없는 주장·판단 보류율 및 상담원 수정량을 함께 본다. 신뢰도 수치는 별도 calibration
  자료로 검증한다. 정책과 인증된 사람의 최종결정 경계는 유지한다.
- 다음 체크리스트: [ ] 대표 문의·이미지와 사람 정답으로 두 모델 공통 오류 기준선을 만든다.
  [ ] Evidence Alignment 입력/출력과 평가 기준을 설계 문서/ADR로 구체화한다. 실행·학습·새 평가·
  서비스 변경은 `NOT_RUN`이며 이 로그는 사용자 질문에 대한 개선 제안으로, 새 아키텍처 확정이 아니다.

### 2026-09-09 11:53 KST — 두 엔진 개선 1차: 오프라인 Evidence Alignment 완료

- 계획/범위: 사용자의 계획·구현 요청에 따라 입력 계약 → 주장별 대조 → 합성 평가/CLI → 회귀와
  문서 인계까지 완료했다. 계획은 `docs/engine/ENGINE_IMPROVEMENT_PLAN_2026-09-09.md`, 결정은
  ADR-0126이다. 초기 설계의 weighted alignment score는 미검증이라 구현하지 않고 명시적 사유를 쓴다.
- 구현: 기존 text v2/vision canonical record와 expected snapshot을 받아 tenant/run/stage, exact
  source quote, evidence SHA, 중복 및 mixed Vision identity를 검사한다. 지원 유형 후보만 참조 ID로
  연결하고 E3 image-level score·위치 미확인·품질 미평가·비시각 주장·미검출을 정상/반박으로 바꾸지 않는다.
  누락 image ID/사유와 추가 자료 코드를 보존하며 human_review_required=true/policy_eligible=false다.
- 재현/프라이버시: CLI는 DB/GPU/provider를 호출하지 않고 canonical 입력 replay와 합성 30건 평가를
  제공한다. 입력 2MiB·image20·claim50·detection100/image 상한, 입력/profile/result hash와
  model/prompt/schema/runtime/taxonomy/threshold/pre/postprocess 출처를 기록한다. 고객 원문/quote/summary,
  URL/key/provider request ID는 출력하지 않는다. 출력은 새 0700 directory/0600 file이며 overwrite 금지다.
- 실제 검증 PASS: backend 기본 1,335 passed/94 deselected, 최종 schema provenance 보강 뒤 집중
  129 passed, 전체 Pyright 0 errors, app/scripts/tests Ruff 및 신규 파일 format, diff check.
  CLI contract 30/30과 replay 일치. 기존 Vision deprecation warning은 보존했고 새 로직 경고는 제거했다.
- compact evidence: `local-data/engine-alignment-evaluation-20260909-final/result.json`, SHA
  `bb198b684ba82032d42eef7fcdd4c90434dd7607bc5510a63e002db81f254ca3`; 초기 보고서도 별도 경로에 보존했다.
  최종 단계별 검증 요약은 같은 directory의 `verification.json`이다.
- 미실행/경계: 실제 모델 accuracy와 결합 gain, 학습·calibration, DB/API/Event/Web 통합은 NOT_RUN.
  DB schema 변경이 없어 migration이 필요하지 않다. GPU 접속/설치/전송/재기동/승격/PRIMARY/fallback,
  sealed Test/freeze, Commit·Push·PR, 실제 사업 동작 0. 기존 dirty worktree와 사용자 문서/4090/GX10 보존.
- 다음: 첫 상품군의 대표 문의·이미지와 모델 답변을 보지 않고 만든 독립 정답을 확보한다. GX10
  전용 identity 계약으로 실제 세 task Dev를 실행하고, 이번 대조 engine에 canonical 결과를 넣어
  실제 error/보류/상담원 수정량을 비교한다. 운영 stage는 별도 append-only persistence와 권한·retention·
  policy qualification 검증을 갖춘 후 연결한다. 이번 완료는 오프라인 대조 기능의 구현 자격이다.

### 2026-09-09 — 기술 멘토링 의제 검토

- 문서 검토 PASS: 기존 멘토링 로그는 초기 고객·사업 검증 질문 중심이며, 최신 engine 개선 계획과
  출시 미해결 항목을 기준으로 기술 질문을 구체화했다. 새 모델/운영 실측은 NOT_RUN이다.
- 우선 의제: (1) 실제 문의/사진의 평가셋·정답·허용 오류/판단 보류 기준, (2) E3 binary와
  localized detector/reference 비교/VLM의 역할 선택, (3) 고객 주장↔시각 근거 결합과 모순/판단불가
  처리, (4) RAW보다 낮은 LLM Query Builder 성능 원인과 RAG 예외 조항 검색, (5) GX10/4090
  배포·실패 격리와 제한 파일럿 운영 기준. 멘토 전문 분야/시간은 아직 제공되지 않았다.
- 다음 체크리스트: [ ] 구조도 1장, 대표 성공/실패/판단불가 사례, 실제 측정과 합성 계약 검사 구분,
  해결할 설계 선택지를 준비한다. [ ] 멘토링에서 첫 상품군/모델 역할, 평가 기준, 다음 비교 실험을
  구체적 결과물로 확정한다. 이번 의제는 제안이며 멘토의 승인·결정으로 기록하지 않는다.

### 2026-09-09 16:16 KST — 전체 기술 멘토링 질문·현재 현황 문서화

- 범위/산출물: `docs/mentoring/CSIGHT_TECHNICAL_MENTORING_BRIEF_2026-09-09.md`에 서비스 정의,
  현재 구현/검증 한계, 관측 수치의 의미, 16개 영역 80개 질문, 우선 의제 12개, 멘토 전문 분야별
  진행안, 준비 자료와 결정/실행 기록 양식을 작성했다. 기존 `11_MENTORING_DECISION_LOG.md`에는
  자료 링크를 추가하고 초기 예시 표가 최신 구현 상태가 아님을 명시했다. 멘토 답변·승인은 기록하지 않았다.
- 근거 검토 PASS: 최신 상태 원장·엔진 개선 계획·관련 설계/Accepted ADR·운영 계약을 대조했다.
  RAG/정책/사람 승인은 이미 구현, 대조 엔진은 오프라인 계약 구현, 실제 고객/모델 품질은 별도
  미검증이라는 경계를 유지했다. 9/2 canary의 사람 승인 실패 오해는 9/9 정정에 맞춰 설명했다.
- 교차 검토 PASS: AI/데이터와 플랫폼/운영을 독립적으로 검토했다. 검색 결과를 적용 확정 정책이
  아닌 관련 후보로 표현하고, 설계 ADR과 실행 증거를 분리했다. 고객 운영용 재실행/취소의 미자격과
  온프레미스/관리 전용/공유 SaaS 배포 선택 질문도 포함했다.
- 문서 검사 PASS: 질문 ID 80개 중복/누락 0, 영역 16개, 근거 문서 25개, 본문 링크 28개 존재,
  표 26개 열 구성 일치, 질문 참조 유효, 고신뢰 비밀정보 패턴 검사와 `git diff --check` 통과.
  이는 문서 구조 검사이며 모델 품질이나 실제 실행 상태의 새로운 검증이 아니다.
- 짧은 JSON: `docs/mentoring/CSIGHT_TECHNICAL_MENTORING_VERIFICATION_2026-09-09.json`.
  문서 SHA-256 `1b257c67f90f0b971f14ef357afbccd91a5ffa39775e26f5a4fe5369459e1fb4`를 기록했다.
- 추가 문서 검사: 우선 의제 12개·검증 JSON의 문서 digest·멘토링 로그 링크 2개·인계 연결 PASS.
  기존 로그까지 포함한 전 파일 공백 probe는 초기 템플릿 44~46행 때문에 FAIL이었다. 세 행은 HEAD와
  동일한 기존 내용임을 확인해 정리 SKIPPED로 보존했고, 새 문서·추가 변경 행 공백 검사는 PASS다.
- 미실행/보존: Backend/UI 테스트 재실행, GPU/서버 접속·모델 평가·학습·배포·PRIMARY 전환은
  NOT_RUN. 기존 미커밋 코드와 사용자 문서, 4090/GX10 서비스·설정은 변경하지 않았다. 비밀번호·
  개인 키 접근, 실제 환불/메일/CRM 실행, Commit·Push·PR은 하지 않았다.
- 미해결: 첫 고객·상품군·실제 Case Bundle/독립 정답·사용권, Query Builder와 GX10 최종 identity
  공동 품질, 대조 엔진 실제 효과·운영 연결, 고객 IdP/연동/보존·부하·경보·off-host 복원이 남았다.
  `NO_WINNER`·`NO_RELEASE_ELIGIBLE`, PRIMARY 금지와 제한 파일럿 BLOCKED를 유지한다.
- 인계 체크리스트: [x] 전체 기술 의제와 현재 상태 문서화. [x] 교차 검토와 링크/ID 검증.
  [x] 기존 멘토링 로그와 현재 원장 연결. [ ] 멘토 전문 분야/시간에 맞춰 우선 질문을 선택.
  [ ] 승인된 성공/실패/판단불가 사례를 준비. [ ] 회의 후 실제 답변과 채택/보류 이유,
  담당자·기한·통과 기준을 기록. 다음 실제 엔진 작업은 대표 데이터와 GX10 전용 평가 identity부터다.

### 2026-09-09 16:44 KST — 멘토링에서 지금 가능한 개선 4건 구현

- 범위: 사용자의 즉시 개선 요청에 따라 재현 가능한 평가·입력 보안 결함만 수정했다.
  결과는 `docs/engine/IMMEDIATE_MENTORING_IMPROVEMENTS_2026-09-09.md`, 계약은 ADR-0127,
  단계별 짧은 JSON은 `docs/engine/IMMEDIATE_MENTORING_IMPROVEMENTS_VERIFICATION_2026-09-09.json`이다.
- 검색 평가: pure 공통 지표에 K=1/3/5/10/20 HitRate·조항 Recall·전체 Gold coverage와 MRR/nDCG,
  실패 포함 macro 분모를 구현했다. 빈 Gold·중복 Case/Gold/히트·실패+히트 입력은 차단한다.
  candidate 보조 진단 API와 두 legacy wrapper에 연결했다. 기존 candidate v1의 recall_at_10은
  역사적으로 CASE_HIT_RATE임을 명시하고 serialization·계산식·0.975 threshold는 보존했다.
  새 지표로 frozen profile·Test·기존 기준선을 재해석하거나 release 자격을 승계하지 않는다.
- 평가 안전: generic Query/MLX CLI는 Dev만 허용하며 Test/freeze를 데이터·provider 전에 차단한다.
  새 0700 directory/0600 exclusive JSON을 요구하고 자동 profile freeze/과거 overwrite 함수를
  제거했다. Makefile/README/사용법을 갱신했다. 관측 원문/모델 출력/에러 대신 해시를 기록한다.
  독립 리뷰에서 찾은 미측정 safety/replay 고정값은 null/NOT_RUN으로 바꾸고 회귀를 추가했다.
- 이미지/ClamAV: 합성 PNG ICC·JPEG comment 잔존을 수정하고 회전·투명도·3형식 metadata 회귀를
  추가했다. ClamAV 단일 NULL 판정과 EOF, 분할 응답·4096-byte 상한·공통 deadline을 검증한다.
  비정상/과대/부분/충돌 응답과 timeout은 업로드 허용으로 낮추지 않는다. 실제 유출 관측은 아니다.
  ICC 색관리 동등성과 DNS resolver wall-clock 상한은 이번 구현의 보증 범위 밖이다.
- 실제 검증 PASS: 최종 기본 오프라인 1,444 passed/94 deselected/기존 deprecation warning 36.
  새 CLI 안전 29 passed, 공통 지표/candidate 집중 62 passed·후보 확장 201 passed,
  이미지/ClamAV adapter 42 passed·Evidence use case 포함 56 passed. 서로 중복인 suite를 합산하지 않는다.
  app/scripts/tests Ruff·format(600 files), 전체 Pyright와 수정 scripts 별도 검사 각각 오류 0,
  diff check 통과. AI 지표·CLI 안전 독립 리뷰의 필수 지적을 반영하고 재검토했다.
- 초기 검사 구분: 수정 전 CLI 회귀 18 FAIL, 이미지/검사기 18 FAIL/15 PASS로 결함을 재현했다.
  최초 전체 검사의 기존 launcher DRY_RUN 2 FAIL은 uv 사용자 cache 권한 문제였고 허용 임시 cache와
  offline/no-sync 재검증으로 해소했다. 저장소 전체 format probe는 기존 사용자 문서
  `kaputt_best_vision_architecture.md` 1개 때문에 FAIL이며 범위 외 정리는 SKIPPED로 보존했다.
- 미실행/보존: 실제 모델/GPU·SSH·ClamAV HTTP·DB 통합·UI E2E·배포·학습은 NOT_RUN.
  기존 dirty worktree/사용자 문서/과거 평가·분석/frozen Test/matrix/RAW/4090/GX10을 보존했다.
  비밀번호·개인 키 접근, 모델 설치/전송/재시작/PRIMARY/fallback, 실제 환불/메일/CRM 실행,
  Commit·Push·PR은 0이다. DB/API/Event schema 변경이 없어 migration은 필요하지 않다.
- 미해결/다음: 첫 상품군의 권리 확인된 대표 Case·정책과 독립 Gold를 확보하고 본문+예외 회수율의
  RAW 대비 실제 Dev를 새 identity로 비교한다. GX10 세 task joint quality, 대조 엔진 실제 효과·UI,
  실제 ClamAV HTTP 재자격과 고객 IdP/연동/보존·부하·off-host 복구는 남았다.
  NO_WINNER·NO_RELEASE_ELIGIBLE/PRIMARY 금지/제한 파일럿 BLOCKED를 유지한다.
- 인계 체크리스트: [x] 결함 재현과 4건 구현. [x] 독립 리뷰·최종 회귀/타입 검사.
  [x] ADR/사용법/멘토링 11절/검증 JSON/현재 원장 연결. [ ] 대표 데이터/독립 정답 확보.
  [ ] 실제 검색·GX10 품질 평가 계약과 새 기준선. [ ] 배포 전 격리 ClamAV HTTP 재자격.
- 최종 문서 검사 PASS: 관련 5개 문서 링크·표·공백·고신뢰 비밀정보 패턴, 멘토링 질문 80개/
  근거 25개/로컬 링크 30개/표 27개, 결과·멘토링·ADR digest를 검증 JSON에 기록했다.
  초기 ADR 상대 경로 오류를 수정하고 재검사했다. 초안 검증 JSON의 옛 digest/count는
  16:16 작성 시점 snapshot으로 명시해 보존했고 후속 현재 문서 검증과 구분했다.

### 2026-09-09 16:53 KST — 개선 반영 후 기술 멘토 공유본 재정리

- 산출물: `docs/mentoring/CSIGHT_MENTOR_HANDOUT_2026-09-09.md`. 서비스/책임 흐름, 시스템별
  구현·미검증, 완료된 개선 4건, 최신 코드 회귀와 과거 모델 실측의 한계를 앞부분에 정리했다.
  질문 12개는 현재 상황→질문→받아야 할 결과로 구성하고 기존 80개 질문 ID와 연결했다.
- 회의 활용: 60분 진행안, 미준비 사례/고객 자료 체크리스트, 다음 과제 3개의 담당/선행 조건/
  결과물 양식을 포함했다. 기존 종합 문서와 구현 결과의 digest는 변경하지 않았고 멘토링 결정
  로그에는 공유본 링크만 추가했다. 멘토 답변·승인이나 실제 자료 공유는 기록하지 않았다.
- 실제 문서 검사 PASS: 질문 12개 순서/중복, 전체 backlog 참조, 로컬 링크 6개, 표 6개 구성,
  공백·고신뢰 비밀정보 패턴, 이전 검증 artifact digest/1,444·94 수치 대조, diff check.
  짧은 JSON은 `docs/mentoring/CSIGHT_MENTOR_HANDOUT_VERIFICATION_2026-09-09.json`이다.
- 미실행/보존: 이번에는 문서만 작성했으며 코드·Backend/UI/모델 테스트 재실행·GPU/SSH 접속·
  배포·설치/전송·PRIMARY·외부 업무 실행은 NOT_RUN 또는 변경 0이다. 코드 테스트 1,444 통과는
  앞선 개선 세션의 결과이며 새 고객 품질/운영 검증으로 해석하지 않는다. 사용자 미커밋 변경,
  4090/GX10 서비스와 과거 평가 결과를 보존했다. 비밀번호·개인 키 사용, Commit·Push·PR 없음.
- 미해결/다음: 멘토 전문 분야/시간, 첫 고객·상품군, 공유 승인된 사례/독립 Gold, 실제 GX10
  공동 품질·고객 보안/연동·운영 자격은 여전히 미확정이다. NO_WINNER·NO_RELEASE_ELIGIBLE와
  제한 파일럿 BLOCKED를 유지한다. 멘토링에서 데이터·품질 기준과 다음 비교 실험을 우선 확정한다.
- 인계 체크리스트: [x] 개선 후 공유본 작성. [x] 근거·질문·링크 검사와 JSON 기록.
  [x] 현재 원장/멘토링 로그 연결. [ ] 멘토 전문 분야에 맞춰 질문 2~3개 선택.
  [ ] 권리 확인된 사례와 고객 업무량 준비. [ ] 회의 후 실제 결정·담당·완료 기준 기록.

### 2026-09-09 18:12 KST — 외부 기술 멘토 전달용 HTML 시각화

- 범위/산출물: 사용자가 내부 열람용이 아닌 멘토님께 드릴 자료임을 명확히 했다.
  `docs/mentoring/CSIGHT_MENTOR_HANDOUT_2026-09-09.html`을 독립형 사전 공유자료로 작성했다.
  시스템 흐름→분야별 구현/미검증→개선 4건/증거→3개 주제의 질문 12개→회의 후 결정 순서다.
- 외부 독자 기준: 내부 저장소 링크·경로·작업 상태코드·backlog ID를 빼고 질문·배경·논의 결과를
  자체 포함했다. 모델·사람 결정 경계, E3 비위치성, 오프라인 대조 미통합, 과거 GX10 관측과
  실제 고객 미검증을 보존했다. Q5 15/15·25/25는 사례 수/정확도가 아닌 기준 통과 수로 명시했다.
  원문 Markdown과 기존 검증 digest는 그대로 보존했다. 실제 멘토 전달·접근 권한 부여는 하지 않았다.
- 시각화 방식: 요청은 공유용 HTML 문서이므로 visualize skill의 분기에 따라 대화용 fragment가
  아닌 전체 standalone document로 만들었다. 외부 font/CDN/API/추적/저장 없이 native details로
  열리며, 목차·전체 질문 펼침·인쇄 전 전체 펼침/인쇄 후 복원과 JS 비활성 기본 동작을 제공한다.
- 실제 검증 PASS: Chromium 임시 독립 profile에서 1365/1024/768/390/360/320px 가로 넘침 0,
  12개 질문·전체 펼침/접기·키보드·목차 이동·JS 비활성 details·print media 펼침/복원 통과.
  데스크톱/모바일/print media 화면을 직접 검토했고 axe WCAG2A/2AA/2.1AA desktop/mobile 위반 0,
  페이지 JS 오류 0, 외부 자원 요청 0이다. 정적 DOM·내부/비밀정보 패턴·질문 제목/결과 검증 통과.
- 초기 검사: 브라우저 sandbox Mach port 제한은 BLOCKED 후 승인된 isolated launch로 재검증했다.
  목차 숫자 4개의 contrast FAIL을 수정한 뒤 전체 브라우저 검사 PASS. 내용 독립 리뷰에서 ClamAV
  경로 용어·기준 통과 수·외부 문체 지적을 반영하고 재검토 PASS를 받았다. 페이지 단위 PDF 생성/
  페이지 나눔 QA는 NOT_RUN이며 print media 검사를 PDF 렌더 완료로 기록하지 않는다.
- 짧은 JSON: `docs/mentoring/CSIGHT_MENTOR_HTML_VERIFICATION_2026-09-09.json`, HTML SHA-256
  `8a8646a31db62dce8f058cb27e936c4f750678eb4b41570dc45ec76ce2ea7bf3` (46,146 bytes).
- 보존/미실행: 이번에는 HTML과 문서만 변경했다. Backend/GPU/실제 ClamAV 자격·SSH·모델
  설치/전송·PRIMARY/fallback·서비스 재시작·외부 업무·고객 자료 전송·Commit/Push/PR은 0 또는
  NOT_RUN이다. 기존 미커밋 작업·4090/GX10·과거 결과·사용자 문서를 보존했다. 비밀번호 사용 없음.
- 미해결/다음: 고객/상품군·권리 확인된 대표 자료/독립 Gold·GX10 공동 품질·고객 운영 자격은
  여전히 미확정이며 제한 파일럿 BLOCKED·NO_RELEASE_ELIGIBLE를 유지한다. 멘토 전문 분야에
  맞춰 핵심 질문을 고르고 회의 후 실제 결정/담당/완료 기준을 기록한다.
- 인계 체크리스트: [x] 외부 전달용 HTML 작성. [x] 콘텐츠·반응형·접근성·인쇄 동작 검증.
  [x] 검증 JSON/현재 원장/멘토링 로그 연결. [ ] 사용자 검토 후 멘토에게 전달.
  [ ] 승인된 사례와 실제 고객 업무량 준비. [ ] 회의 답변·채택/보류·다음 과제 기록.

### 2026-09-09 18:20 KST — 멘토 HTML에서 완료 개선 관련 항목 제거

- 사용자 요청 범위: 외부 공유 HTML의 ‘먼저 고친 네 가지’ 제목·카드 4개와 관련 코드 검사 수치,
  검색 지표 정정/예시, metadata·ClamAV 수정 이력, 회의안의 개선 설명을 제거했다. 구현 코드,
  내부 Markdown 원문·기존 개선 결과·과거 세션 로그는 삭제하거나 되돌리지 않았다.
- 구성: 해당 절을 ‘확인한 결과와 남은 검증’으로 바꾸고 목차·앵커를 연결했다. Q03/Q05/Q10의
  완료 개선 언급만 제거·재서술하고 미해결 질문 12개를 유지했다. Q5/GX10의 별도 자격,
  과거 관측 시각, 실제 고객 품질 미검증, 사람 최종 결정과 모의 처리 경계는 보존했다.
- 실제 검증 PASS: 수정 문구/관련 스타일 제거와 유효 앵커, 독립 콘텐츠 재검토 필수 지적 0.
  임시 독립 Chromium에서 1365/1024/768/390/360/320px 가로 넘침 0, 질문 12개와 키보드,
  전체 펼침/접기, JS 비활성 기본 동작, print media 펼침/복원 통과. 데스크톱/모바일 검증 절과
  print media 화면 직접 검토. axe desktop/mobile 위반 0, JS 오류·외부 요청 0.
- 짧은 JSON: `docs/mentoring/CSIGHT_MENTOR_HTML_VERIFICATION_2026-09-09.json` revision 2.
  HTML SHA-256 `35d98a9de948b4ad88c9b814a8134afb71dad45936e3b2ffea5a238a35d43634`,
  42,979 bytes. 이전 HTML digest/초기 검사 이력은 구분해 보존했다. 내부 공유본 Markdown
  SHA-256 `48a89157bbbb9734aa2f7b023d1fc4b3f0c21aa117cc6e206ed27b0c7cf04818` 불변.
- 보존/미실행: Backend·GPU·실제 보안 경로 자격·PDF 페이지 나눔 QA는 NOT_RUN. 기존 사용자
  미커밋 변경·4090/GX10·설정·분석 결과를 보존했다. 비밀번호 사용·SSH·서비스 변경·설치/전송·
  PRIMARY/fallback·실제 고객 업무·외부 공유·Commit/Push/PR 없음.
- 미해결/다음: 대표 자료·독립 정답·GX10 공동 품질·고객 운영 자격은 여전히 미확정이다.
  NO_WINNER·NO_RELEASE_ELIGIBLE·제한 파일럿 BLOCKED는 변함없다. 멘토링에서 지원 범위,
  평가 기준과 다음 비교 실험을 정하고 실제 답변·담당·완료 기준을 기록한다.
- 인계 체크리스트: [x] 외부 HTML의 완료 개선 항목 제거. [x] 관련 문구·목차·반응형·동작 재검증.
  [x] JSON·현재 상태 갱신. [ ] 사용자 검토 후 전달. [ ] 승인된 사례 준비와 회의 결과 기록.

### 2026-09-09 18:29 KST — 멘토 HTML에 아키텍처 도식 1개 반영

- 범위: 사용자 요청으로 기존 단순 업무 흐름도를 하나의 논리 아키텍처 figure로 교체했다.
  별도 파일/외부 리소스 없이 공유 HTML 안에 포함하고, 기존 네 가지 개선 제외와 질문 12개는
  유지했다. visualize skill의 분류에 따라 대화용 fragment가 아닌 기존 공유 문서를 수정했다.
- 내용: 콘솔⇄Core⇄독립 LLM/Vision의 요청/응답 관계, Core 내부 API/Worker·Outbox/RabbitMQ/
  Celery·RAG/정형 규칙·PostgreSQL/pgvector/Private MinIO의 책임을 표시했다. 생성 설명과
  정책 규칙을 직렬 입력으로 잇지 않고, 사람 결정·모의 처리·E3 정책 미자격·모델 DB 직접 접근
  금지와 오프라인 대조 미연결을 명시했다. 현재 배포나 자동 전체 파이프라인 실측 주장이 아니다.
- 근거/리뷰 PASS: 최신 원장, Architecture의 후속 Sprint 경계, Policy/Human Review 설계,
  ADR-0126과 독립 플랫폼 검토를 대조했다. 오래된 Sprint 설계의 ‘후속 범위’는 최신 구현
  상태로 구분했다. 리뷰에 따라 콘솔은 기존 문의 확인, 큐는 중복 실행 자체가 아닌 중복 결과
  방지로 표현했고 어댑터를 Core 책임에 배치했다. 신규 아키텍처 결정·기능 변경은 없다.
- 실제 검증 PASS: Chromium 임시 독립 profile에서 figure 1개/이전 흐름도 0개, 책임 경계와
  완료 개선 문구 부재를 검사했다. 1365/1024/768/390/360/320px 가로 넘침 0, axe desktop/mobile
  위반 0, JS 오류·외부 요청 0. 질문 12개·전체/키보드 펼침·JS 비활성·목차 이동·print media
  펼침/복원 통과. 도식 desktop/mobile 및 680px print media 렌더를 직접 확인했다.
- 짧은 JSON: `docs/mentoring/CSIGHT_MENTOR_HTML_VERIFICATION_2026-09-09.json` revision 3.
  HTML SHA-256 `7d649a00a8584de4e5452e19629c340b4436744ae2799745b5b0965949a377a7`,
  49,013 bytes. 이전 revision digest와 검사 이력, 내부 Markdown 원문을 보존했다.
- 보존/미실행: Backend/실제 GPU/보안 경로 자격과 PDF 생성·페이지 나눔 QA는 NOT_RUN.
  기존 미커밋 코드·문서·4090/GX10·설정·과거 결과 보존. 비밀번호·SSH·설치/모델 전송·재시작·
  PRIMARY/fallback·실제 고객 업무·외부 공유·Commit/Push/PR 없음.
- 미해결/다음: 대표 자료·독립 정답·GX10 공동 품질·고객 운영 자격은 계속 미확정이며
  NO_WINNER·NO_RELEASE_ELIGIBLE·제한 파일럿 BLOCKED를 유지한다. 다음은 공유본 검토 후
  멘토링에서 지원 범위·평가 기준·비교 실험을 정하고 실제 답변/담당/완료 기준을 기록하는 것이다.
- 인계 체크리스트: [x] 도식 1개와 구현/미연결 경계 표시. [x] 근거·콘텐츠·화면·동작 검사.
  [x] JSON·현재 상태 갱신. [ ] 사용자 검토 후 전달. [ ] 승인된 사례 준비와 회의 결과 기록.

### 2026-09-10 11:34 KST — 서버 제어 앱 기동 및 GX10 OOM 위험 읽기 전용 점검

- 사용자 요청: 서버 제어 앱으로 서버 기동을 확인하고, GX10 OOM 우려가 있다면 GPU 작업을
  정리해 사용자 서버를 기동한다. 조건과 대상 확인 전에는 GPU 작업을 종료하지 않기로 했다.
  실제 바탕화면 앱의 main.scpt와 저장소 제어 경로/메뉴를 대조했으며 코드는 변경하지 않았다.
- 최초 상태: Mac Docker·Embedding·Core·공개 주소가 꺼져 있었다. GX10 별칭 SSH는 DNS 실패였고
  Mac Tailscale 상태는 Stopped였다. 기존 설정을 바꾸지 않는 연결 재개 후 현재 tailnet에 나온
  GX10 주소를 사용해 비밀번호/대화형 인증을 끈 SSH·기존 host key 검증으로 접속했다.
- 앱 기동: Docker는 기존 컨테이너/동일 Compose 프로젝트의 orphan 여부를 사전 확인하기 위해
  먼저 열었다. 따라서 앱의 Docker 자동 시작 분기 자체는 NOT_RUN이다. 실제 앱 메뉴에서
  ‘서버 켜기 (빠른 시작)’ 텍스트를 확인 후 선택·실행했고, Mac MPS Embedding과 기존 Core/
  공개 시연 경로가 정상 상태가 됐다. 재빌드·Migration·orphan/volume 삭제는 실행하지 않았다.
- 실제 기동 검증 PASS: Core 9개 healthy, restart 0/OOMKilled false, 약 6분 유지. 앱 backend의
  상태 조회와 API ready·Web health·Embedding health/models·기존 공개 주소 모두 정상.
  Embedding은 Qwen3-Embedding-0.6B 고정 revision·1024차원·MPS model_loaded=true다.
  로컬/공개 index 본문 digest 일치. 격리 브라우저의 /login HTTP 200·페이지 제목/화면 확인,
  JS 오류·예상 밖 외부 요청 0. 인증 입력·고객 업무 조작은 NOT_RUN이다.
- 검증 한계: 앱의 빠른 시작 클릭은 관측했으나 최종 완료 dialog는 관측하지 못했다. GUI 알림
  표시까지 PASS로 확장하지 않는다. 실제 컨테이너의 allowlist 환경값도 LLM_PROVIDER=mock,
  VISION_PROVIDER=mock, ENVIRONMENT=local이다. 이 앱에는 GX10 모델 기동·전환 기능이 없다.
- GX10 관측: NVIDIA GB10/aarch64, ComfyUI GPU 메모리 40,781MiB·GPU 사용률 0%·35°C.
  MemAvailable 71,901,316KiB(약 68.6GiB), memory PSI some/full의 10/60/300초 평균 0,
  부팅 후 kernel oom_kill 0이다. GPU total/used/free는 N/A이므로 시스템 가용 메모리를
  GPU 전용 여유나 미래 모델 동시 적재 보증으로 해석하지 않는다.
- 기존 모델은 미기동: vllm_node는 2026-09-08 16:37 KST 종료, exit 137/OOMKilled=false이며
  127.0.0.1:8000 health는 연결 거절 FAIL이다. exit 137만으로 OOM이라 판단하지 않는다.
  컨테이너의 시작 프로그램은 sleep이며 서빙 명령·모델 설정이 없다. 단순 docker start로
  Qwen이 복구된다고 가정하지 않고 새 서빙 명령·프로필을 임의로 만들지 않았다.
- GPU 정리 SKIPPED: 현재 메모리 압박이 관측되지 않고 기존 앱이 GX10을 사용하지 않으므로
  ComfyUI 등 GPU 작업을 종료할 조건이 성립하지 않았다. 향후 실제 모델의 정밀도·문맥·동시성·
  cache 설정에 따른 peak memory·동시 적재 검증은 NOT_RUN이다. 공유 계정의 다른 작업도 보존했다.
- 짧은 JSON: `docs/progress/SERVER_CONTROL_STARTUP_VERIFICATION_2026-09-10.json`.
  제어 스크립트 문법·diff check PASS. Backend 기본 suite·실제 LLM/Vision inference·모델
  품질/보안/출시 자격 검사는 NOT_RUN. 사용자 미커밋 변경·설정·기존 볼륨·4090 서비스를 보존했고
  비밀번호 사용·원격 쓰기/종료·설치/전송·PRIMARY·Commit/Push/PR·실제 업무 실행은 0이다.
- 미해결/다음: 앱의 실제 GX10 엔진 동시 기동을 원하면 내부 검증용 모델/서빙 프로필과 앱
  연결 범위를 먼저 확정해야 한다. 현재 모델 전체 NO_WINNER·NO_RELEASE_ELIGIBLE·고객 파일럿
  BLOCKED 및 PRIMARY 금지는 유지한다. 서버 healthy와 실모델 연결/의미 품질을 구분한다.
- 인계 체크리스트: [x] 실제 앱 빠른 시작 선택·서비스 검증. [x] GX10 메모리/프로세스/중지 모델
  인벤토리. [x] 조건 없는 GPU 종료 방지·JSON/원장 갱신. [ ] 실제 모델 기동/앱 연결 범위 확정.
  [ ] 범위 확정 후 메모리 예산·인증·endpoint·버전·canary 계약으로 내부 기동 검증.

### 2026-09-10 11:38 KST — 서버 제어 앱 완료 UI 추가 관측 정정

- 앞선 11:34 기록의 ‘완료 dialog 미관측’ 이후 앱 창이 나타났다. 대상 앱의 정적 문구만
  읽어 ‘AppleEvent 시간이 초과되었습니다.(-1712)’를 확인했다. 앱 GUI 완료 판정은 FAIL이다.
  서버/API/Web/Embedding 건강성 PASS와 구분하며 앱 전체가 정상 완료됐다고 주장하지 않는다.
- 독립 읽기 전용 점검: 앱 직접 자식 프로세스 0, 표준 입출력 /dev/null, 앱 보유 PIPE/unix FD 0.
  이는 단순 앱 자체의 background pipe EOF 대기를 뒷받침하지 않지만 원인을 확정하지 못한다.
  어떤 AppleEvent에서 timeout이 발생했는지 추적·재현과 코드 수정은 NOT_RUN이다.
- 조치: 검증 JSON에 오류·시각·별도 GUI 상태를 추가했다. 서버나 GPU를 내리지 않았으며,
  새로운 앱 수정·모델 서빙·PRIMARY 전환도 하지 않았다. 정상 서버는 켜 둔 채 인계한다.
- 다음 체크리스트: [ ] 사용자 방향 확인 후 앱 timeout 원인을 제한적으로 재현·수정한다.
  [ ] 실제 GX10 엔진 동시 기동을 요청하면 별도 내부 서빙/앱 연결 범위를 확정한다.
  기존 실제 모델 품질/고객 운영 gate와 GPU 작업 소유권·메모리 사전 확인 경계는 유지한다.

### 2026-09-10 12:00 KST — 앱 수정·GX10 내부 Q5 기동 단계 기록

- 사용자 승인 범위: 앱 timeout 수정과 GX10 내부 검증용 Qwen 동시 기동. Core mock 설정·
  PRIMARY·실제 고객 업무는 변경하지 않는다. 기존 미커밋 변경과 4090을 보존한다.
- 사전 인벤토리 PASS: key-only SSH/기존 host key, GX10 aarch64/aidi_lab, 시스템 가용
  73,608,843,264 bytes, 기존 ComfyUI 40,781MiB. 기존 Q5와 ARM64 이미지가 있어 설치·
  모델 전송 없이 사용했다. NVFP4의 vllm_node와 연구 컨테이너는 그대로 둔다.
- 첫 시도 FAIL: 새 앱 전용 Q5의 reasoning none을 현재 binary가 거부해 exit 1,
  OOMKilled=false. 자신이 만든 컨테이너만 정지 후 failed 이름으로 보존했다.
  실제 binary help에 맞춰 off로 수정하고 계약 q5-internal/1.0.1로 구분했다.
- 다음 기동 PASS: 실제 앱 빠른 시작으로 Q5 모델 byte/hash·image 검증, 기동과 정확한 alias/
  합성 JSON canary 성공. 시스템 가용 53,008,359,424 bytes. Core·Embedding·공개 주소 정상.
  원격 loopback:18003/API 인증, context4096/concurrency1, 읽기 전용 비루트 mount다.
- GUI 원인 범위: backend 완료 후 창이 없는 상태에서 프로세스 sample이
  StandardAdditions/AEInteractWithUser 대기를 보였다. 앱을 앞으로 가져오자 PASS 결과 창이
  나타났다. 단순 backend hang은 아니며 과거 -1712의 모든 경로를 확정한 것은 아니다.
  결과/오류 전 activate, bounded optional notification, 60초 자동 닫힘을 반영했다.
- 검증/보존: 원본 앱 전체 백업, main.scpt 갱신·서명 검증 PASS. 기본 오프라인 1,453 passed /
  94 deselected / 기존 warning36, 관련 26 tests PASS, 전체 Pyright 오류0. 새 파일 Ruff/format
  PASS. 실제 전체 DB/Web/GPU 회귀·의미 품질·고객 자격은 NOT_RUN이다.
- 복구 점검 PASS: 11:58 앱 전용 Q5만 stop, 모델 메모리 회수 후 시스템 가용
  73,007,181,824 bytes, ComfyUI 같은 PID/40,781MiB 보존, kernel oom_kill0.
  현재 최종 앱 빠른 시작과 background→결과 표시 재검증 중이다.
- JSON: SERVER_CONTROL_FIX_VERIFICATION_2026-09-10.json. 이전 기동 감사 JSON은 그대로 둔다.
  다음: 최종 재기동/완료 창/자동 닫힘·가용 메모리 확인 후 서버를 켠 상태로 인계한다.

### 2026-09-10 12:08 KST — 최종 앱·Q5 재기동 검증

- PASS: 전용 Q5 stop 후 앱으로 같은 컨테이너를 재기동했다. 이후 warm 빠른 시작에서도
  정확한 alias/합성 JSON canary PASS, Core 9개 healthy·API/Web/Embedding/공개 주소 정상이다.
- PASS: 앱을 Finder 뒤로 보낸 뒤 수동 activate 없이 결과 창의 성공 문구를 직접 읽었다.
  새 activate 경로가 재현된 background dialog 대기를 해소했다. 과거 -1712의 모든 가능한
  원인을 제거했다는 일반화는 하지 않는다. 앞선 ‘제어 프로그램 이전 대기’ 추정은 후속
  sample/결과 확인으로 backend 완료 후 dialog 대기로 정정한다.
- PASS: 12:06 Q5 17,497MiB, ComfyUI 같은 PID/40,781MiB, MemAvailable52,152,124KiB,
  PSI some/full 평균0, oom_kill0, 모델 OOMKilled=false/restart0. cgroup 밖 GPU unified memory와
  향후 다른 작업의 부하는 별개이므로 OOM 방지 보증이나 지속 모니터링을 주장하지 않는다.
- 보안 PASS: GX10 loopback:18003만 listen, 인증 없는 추론401. 모델 목록은 인증 없이200인
  binary 계약으로 구분했다. 비밀번호 요청/사용0, 설치/모델 전송0, PRIMARY/Core 설정 변경0,
  다른 GPU 작업 종료0, 4090 조작0, DB migration/rebuild0, Commit/Push/PR0.
- 실제 Core allowlist 환경값은 local/LLM mock/Vision mock이다. Q5는 독립 내부 검증 endpoint만
  기동됐으며 UI 업무 분석에 연결하지 않았다. NVFP4와 Vision 실추론·세 과제 공동 Dev·고객
  파일럿·Docker Desktop cold boot는 NOT_RUN. NO_WINNER/NO_RELEASE_ELIGIBLE/PRIMARY 금지 유지.
- 인계 체크리스트: [x] 원본 앱 백업/compile/서명. [x] 제한된 Q5 기동·합성 응답·stop/restart.
  [x] background 완료 창. [x] 기존 작업·볼륨·미커밋 변경 보존. [x] JSON·운영 문서·현재 상태.
  [ ] GX10 전용 세 과제 공동 Dev와 대표 사례 Gold. [ ] 자격 이후 별도 운영 연결 검토.

### 2026-09-10 12:09 KST — 자동 닫힘·마지막 상태 조회 인계

- PASS: 마지막 완료 창은 사용자 확인 클릭 없이 자동 종료됐고 앱 프로세스도 종료됐다.
  12:08:47 후속 SSH 조회 한 번은 connect timeout FAIL이었으나 같은 key-only 경로 재시도는
  PASS/ready=true/running=true, MemAvailable53,414,617,088 bytes였다. Tailscale Running과
  GX10 online도 확인했다. 서비스 재시작이나 네트워크 설정 변경 없이 회복했다.
- PASS: 최종 소스 기본 회귀 재실행 1,453 passed/94 deselected/기존 warning36, 수정 Python
  Pyright0·Ruff/format·shell 문법·git diff check. 이전 JSON/실패 컨테이너/사용자 변경 보존.
- 원본 앱 백업은 임시 경로 외에
  `/Users/ckdlsxor/Library/Application Support/CSight/Backups/server-control-RRvoMq/CSight 서버 제어.app`
  에 영구 보관했다. 원본 main.scpt SHA-256
  `1716b2c33fecfbdd8888a8d1aee1bfedc7f54bba4e73146c4fd9791061cda992` 일치.
- [x] 자동 닫힘 후 Q5 유지 확인. [x] 서버 켜진 상태로 인계. 이후 네트워크/외부 GPU 작업에
  대한 지속 감시는 설정하지 않았다. 다음은 운영 승격이 아닌 GX10 전용 공동 품질 검증이다.

### 2026-09-10 13:23 KST — 모든 모델 역할 수행 여부 읽기 전용 확인

- 사용자 질문에 대한 판정: 아직 모든 모델이 실제 업무 역할을 수행하는 상태는 아니다.
  서버 제어 앱/Q5 기동 성공과 실제 업무 pipeline 연결·의미 품질을 분리한다.
- PASS: 실제 API·model Worker·retrieval Worker 환경의 allowlist 값만 읽었다. 모두
  local/LLM_PROVIDER=mock/VISION_PROVIDER=mock, LLM_TASK_RUNTIMES override 없음이다.
  Qwen Embedding은 고정 artifact/revision·MPS loaded이며 retrieval Worker의 설정 target과
  실제 Worker→Embedding health 연결이 정상이다. 검색 정확도나 이번 업무 처리 완료 주장은 아니다.
- PASS: GX10 Q5 status에서 running/ready 및 exact alias 확인. Core routing=false 유지.
  앞선 합성 canary는 과거 이번 날 기동 근거로 보존하며 이번 질의에서 추론은 NOT_RUN이다.
- FAIL: 로컬 E3 health:8093 및 reranker health:8092 연결 거절. E3의 다른 호스트 상태는
  조사하지 않았으며 Core Vision mock 확인만으로 업무 실모델 미연결을 판단했다.
  GX10 vllm_node는 중지 상태다. Reranker는 기존 무개선 판정으로 기본 경로 승격 대상이 아니다.
- 변경0: 서비스 시작/정지·설정·Core route·PRIMARY·비밀번호·GPU 작업 종료 없음.
  MODEL_ROLE_STATUS_2026-09-10.json과 이 원장만 기록했다. 전체 suite는 NOT_RUN이다.
- 인계: [x] 실제 Worker 설정/모델 상태 구분. [x] JSON/원장 기록.
  [ ] 별도 승인된 내부 통합 범위에서 실 LLM/Vision 연결과 문의→근거→사람 검토를 검증.
  [ ] GX10 세 과제 공동 Dev·대표 이미지/문의 Gold. 현재 NO_RELEASE_ELIGIBLE/PRIMARY 금지 유지.

### 2026-09-10 13:35 KST — 실모델 내부 진단 진행·업무 등록 경계 확인

- 사용자 승인 범위는 내부 실 LLM/Vision 연결 검증이다. 기존 Core/4090/ComfyUI·미커밋
  변경을 보존하고 PRIMARY·실제 고객 업무·비밀번호 사용은 금지 상태로 유지했다.
- E3 PASS: 기존 Downloads 체크포인트의 전체 SHA를 재확인했다. 기존 venv와
  serve_vision_e3.sh로 csight-vision-e3-internal 분리 세션/loopback8093을 기동했다.
  stale PID6602는 다른 macOS 프로세스였으므로 종료하지 않았다. PID 파일은 임시 검증
  디렉터리에 백업한 뒤 정상 launcher가 새 PID를 기록하도록 했다. 설치/모델 전송 없음.
- E3 실제 HTTP PASS: 기존 qualify_vision_e3.py의 합성 그림 한 건, exact model/version/SHA,
  MPS float32, score0.5347465872764587/threshold0.8984375. 기준 미만은 정상 확인이 아니다.
  Core model Worker에서 host-private E3 health와 exact revision도 확인했다. Core Vision
  provider 설정을 remote로 바꾸거나 실제 analysis_run을 저장한 것은 아니다.
- Q5 실제 Adapter PASS: 기존 llama_cpp Adapter와 guarded prompt2.0.0-local.8로 합성 문의
  한 건을 원격 인증 HTTP에 전달하고 schema2.0/claim1/action1/정확 인용을 검증했다.
  임시 진단 transport는 키 기반 SSH를 사용해 API key를 GX10 밖으로 내보내지 않았다.
  첫 두 요청은 진단 HTTPResponse의 bytes/stream 표현 오류(TypeError)로 local 검증이 실패해
  보존하고 BytesIO로 고쳐 재실행했다. 이는 모델 의미 실패나 Core 수정 증거가 아니다.
  원문/생성 텍스트/키는 보고서에 기록하지 않았다. 품질 gate·공동 Dev는 NOT_RUN이다.
- 통합 BLOCKED: StartPolicyEvaluation은 SHADOW 입력에 즉시
  SHADOW_ANALYSIS_DOWNSTREAM_FORBIDDEN을 발생시키며 실제 정책/검토 경로를 만들지 않는다.
  이 Application guard와 DB 제약 tests3 PASS를 재확인했다. PRIMARY 금지나 모델 미자격을
  회피하려고 enforcement를 끄거나 모드를 바꾸지 않았다. E3 runtime contracts5 PASS.
- 미완료: Core 실제 모델 설정/새 분석 이력/RAG→grounding E2E/실제 검토 업무 등록은
  NOT_RUN 또는 BLOCKED다. 앞선 ‘검토 대기까지’ 계획은 이 제약을 포함해 축소해야 한다.
  업무 이벤트가 없는 별도 진단 검토 화면과 출시용 실제 검토함은 다른 범위다.
- 인계 체크리스트: [x] 실제 두 모델 독립 진단. [x] E3/기존 Q5/Core 정상 유지.
  [x] 단계 JSON·실패 이력·안전 경계 기록. [ ] 사용자 방향에 따라 별도 진단 검토 경로 설계
  또는 GX10 공동 품질 자격 평가. 현재 분석/정책/검토/결정/외부 업무 이벤트 생성0.
  전체 suite·타입 검사는 NOT_RUN이며 repository 동작 코드는 변경하지 않았다.

### 2026-09-10 14:05 KST — 사용자 승인 SHADOW 실제 사용·피드백 허용 및 실모델 연결

- 사용자 최신 지시: 별도 진단 화면이 아니라 SHADOW 결과 차단을 풀고 실제 사용하며 피드백한다.
  이에 ADR-0128로 ADR-0103의 절대 downstream 금지를 내부 피드백 구성에 한해 대체했다.
  13:35 BLOCKED 기록은 당시 권한의 사실로 보존하며 더 이상 현재 작업 차단 사유가 아니다.
- 코드/DB: local/test 전용 `SHADOW_HUMAN_FEEDBACK_ENABLED`를 추가했다. 신규 정책 실행에
  immutable `shadow_feedback_allowed`를 기록하고 기존 tenant-scoped lineage trigger는 이 표시가
  있는 SHADOW 및 그 후속 검토/모의 처리를 허용한다. 표시 없는 Shadow, 없는/다른 tenant lineage는
  계속 거부한다. DB Migration0037은 additive이며 기존 mode/분석/정책 이력을 덮어쓰지 않는다.
  피드백 이력이 있으면 downgrade를 거부하고 새 접수만 끄도록 안내한다.
- 보호 경계: 새 분석/검색/설명은 이 프로필에서 SHADOW만 허용하고 과거 PRIMARY를 실모델로
  이어 만드는 경로도 차단했다. 기존 signed release/PRIMARY 승격 gate, RAW/HYBRID/Top3 기본,
  사람 인증·tenant 격리·최종 확인·실제 환불/발송 금지는 유지한다. 사용 피드백 건은 깨끗한
  observation-only Shadow100 증거로 집계할 수 없다. E3 내부 비상업 사용 범위도 유지한다.
- runtime 사전 관측: Core DB는 예상0036보다 이전인0034였고 active analysis/policy 각각0이었다.
  기존 DB custom dump(약1.9MB, owner-only)를 `/private/tmp/csight-feedback-backup-j1ZTjz/`
  아래에 보존했다. archive list995개 확인, 실제 restore drill은 NOT_RUN이다.
  0035/0036 prerequisite를 확인하고 함께 적용해 live0037, `alembic check` drift0을 확인했다.
  host check는 DATABASE_URL 미export로 실패했으므로 설정된 API container에서 재검증했다.
  과거 Docker image ID re-tag는 실패해 rollback image 보존을 주장하지 않는다.
- 실제 연결: 별도 `infra/compose.internal-feedback.yml` 및 로컬 표시 파일로 Q5 llama_cpp와 E3
  remote를 Core API/Worker에 설정했다. Q5는 원격loopback18003 유지, Macloopback18004의
  owned SSH tunnel로 연결한다. 기존 SSH key/known-host 검증만 사용하고 비밀번호를 요청/사용하지
  않았다. 기존 service API key는 SSH로 읽어 자식 환경에만 전달하며 Mac secret 파일/보고서에
  저장하지 않았다. Docker 관리자에게 보이는 일반 runtime secret 경계는 문서에 명시했다.
  Q5/ComfyUI 등 기존 GPU 작업, NVFP4 컨테이너, RTX4090 무변경이다.
- 실제 Worker container probe PASS(14:00): synthetic Extraction claim1·정확 source quote,
  prompt2.0.0-local.8·14,070ms; E3 binary image assessment·threshold0.8984375·894ms;
  Embedding1024d normalized; 기존 합성 tenant 정책 lexical3+dense3→HYBRID Top3·동일tenant·
  index1.0.0; 실제 검색 결과 기반 Grounding1.1.0-local.2·statement3·인용ID 유효율1.0·38,525ms.
  이는 직접 adapter/read-only retrieval chain 증거이며 인증 HTTP→RabbitMQ→검토 live E2E나
  실제 고객 정확도가 아니다. 원문·모델 응답·secret은 JSON에 남기지 않았다.
- 검증 PASS: Python오프라인1465/96deselected, 전체Pyright0, 변경Ruff/format·shellsyntax·diff검사;
  격리PostgreSQL3개(Shadow→정책→사람resolve→DRY_RUN/report, tenant/role/immutable/defaultdeny,
  0037왕복과drift, 과거0019guard), Frontend92·typecheck/lint/build. 초기테스트 오류(immutable
  trigger 순서·Vite env 타입·Grounding버전 기대값)를 수정 후 재검증했다.
- 앱 연결 PASS: 실제 앱이 호출하는 backend `start/status`에서 Core9healthy, API/Web/Embedding/
  공개주소 정상, Q5canary PASS. 제공되는 프런트 bundle에 미검증·사람확인·모의실행 안내가 있다.
  SHADOW 요청 opt-in/default 분기와 배너는 UI test에서 검증했다. GUI대화상자/실제browser시각검사/
  전체coldstop은 이번에는 NOT_RUN. 서버는 켜 둔다.
- 인계 체크리스트: [x] 사용자 승인반영/ADR/DB migration/테스트/실배포/단계JSON/사용안내.
  [x] 기존 미커밋 변경·DB·model artifacts·GPU서비스 보존, commit/push없음.
  [ ] 사용자 인증 UI에서 새 내부 문의→분석→정책→검토 전체를 사용하고 오류/누락 피드백.
  [ ] 고객데이터 품질·real jointDev·상업사용권·출시자격은 별도. 에이전트가 실제사용자 JWT를 만들거나
  비밀번호로 대신 로그인하지 않았고 live업무/최종결정 row를 만들지 않았다(14:03 feedback정책row0).
  다음 행동은 제어 앱→화면 새로고침→새 내부 테스트 문의다. 기본 make up은 다른 mock 프로필이다.
  [현재 단계 JSON](SHADOW_HUMAN_FEEDBACK_2026-09-10.json),
  [내부 피드백 안내](../operations/INTERNAL_SHADOW_FEEDBACK.md).

### 2026-09-10 14:13 KST — 테스트 데이터 초기화 요청: 읽기 전용 범위 확인

- 사용자 요청: 기존 데이터를 초기화하고 임시 데이터로 다시 적재해 실제 동작을 확인한다.
  현재 DB와 기존 seeder를 읽기 전용으로 점검했다. 새 코드 변경·데이터 삭제·재적재·서비스 중단 없음.
- 관측 PASS: Core9 healthy. 전체 문의115/사진 Evidence73/분석122/검토41/사람 결정32,
  계정39/정책문서44/조항304. 분석은 성공114·부분성공2·실패6으로 비종결0, 활성 정책 실행0.
  현재 화면의 문의는 `csight` tenant 소속이며 해당 tenant 문의51건, 다른 tenant64건이다.
  출처 표시는 SYNTHETIC_DEMO21건, NOT_ATTESTED94건이다. 미확인 건을 실제 고객 데이터나
  합성 테스트 데이터로 단정하지 않았다.
- 미해결/BLOCKED: ‘싹 초기화’가 현재 고객사 문의만인지 모든 고객사 문의/분석/검토/사진인지
  구분이 필요하다. 계정·정책/검색 인덱스는 보존하는 범위로 제안하며, 범위 확인 전 삭제하지 않는다.
  기존 append-only 이력을 임의로 변조하거나 DB trigger를 해제하지 않았다.
- 재적재 사전 확인: 기존 `seed_realistic_poc_demo.py`는 요청에 SHADOW mode를 명시하지 않고
  기존 local ADMIN token을 메모리에 발급하며 정책/검토까지 진행하지 않는다. 현재 프로필에
  그대로 실행하지 않았다. 비밀번호/토큰 발급 없이 인벤토리만 수행했다.
- 인계 체크리스트: [x] 현재 범위/건수·기존 적재 경로 확인·JSON 기록·미커밋 변경/서비스 보존.
  [ ] 사용자 범위 확정 [ ] 새 백업과 복구 확인 [ ] 초기화 [ ] 임시 적재 [ ] 실모델 비동기 흐름.
  백업·초기화·재적재·전체 UI 검증은 NOT_RUN. 문서만 변경하여 코드 테스트/타입 검사는 NOT_RUN.
  다음 행동은 초기화 tenant 범위 확인 후, 확정된 대상만 복구 가능하게 보존하고 진행하는 것이다.
  [단계 JSON](TEST_DATA_RESET_2026-09-10.json).

### 2026-09-10 14:33 KST — DB 불일치 감사·한정 수정, 전체 테스트 초기화 승인

- 읽기 전용 PASS: FK171+CHECK371=542, shared case/run lineage29 위반0. 분석 stage aggregate,
  성공 Text 결과/attempt count, 검토 packet/decision/owner/current projection, Case assignment,
  Resolution event/version, 원문 dual-write와 hash115건 일치. 전체 Case의 RECEIVED는 ADR0011/0089에
  따른 별도 lifecycle이며 임의 RESOLVED 변경 대상이 아니다. 정책 source/snapshot도 일치했다.
- 해시 검증 PASS: 검토packet41·사람결정32·보고서23·학습asset23·intent11·모의result11.
  합성 reference policy/typed rule validator PASS. 전체 embedding304차원 정상이며 norm0.998–1.0038은
  기존 허용오차0.005 안이다. 첫 진단의 더 엄격한0.001 조건을 데이터 오류로 오인해 재작성하지 않았다.
- 발견: UUID형 analysis tenant의 과거 fixture17건은 최초 상태 이력이 없다. 같은 test pattern의
  Evidence7건은 실제 MinIO object 부재지만 AVAILABLE이었다. 현재 csight tenant는 두 발견에 해당하지
  않으며 나머지 실제사진66건은 크기/MIME/byte SHA 모두 일치했다. 다른 신규 오류는 관측되지 않았다.
- 수정 PASS: ADR0129·data-only Migration0038로 사전 확인된7개ID/고정 fingerprint/분석 이미지 참조0을
  재검증 후 FAILED로 정정하고 null human actor의 EVIDENCE_RECONCILED receipt7개를 append했다.
  object는 생성/삭제하지 않았다. DB 81개 table의 전후 digest 중 변경은 Evidence/receipt/revision3개뿐,
  나머지78개 그대로다. 이력17건은 과거 사람의 case_created를 가공/소급 생성하지 않고 보존했다.
- 백업: owner-only `/private/tmp/csight-data-consistency-j58RpN/core-before-repair.dump`를 별도DB에
  실제 복원해115/73/122/32건을 확인하고 복원본에도0038·drift0 PASS. 시험용 복원DB는 제거했으며
  dump는 남겼다. 이는 DB 논리 백업이며 MinIO/offhost 전체복구 자격이 아니다.
- 재발 방지: 공식 integration runner가 생성한 정확한 임시DB 이름을 pytest collection에서 확인한다.
  RUN_CORE_INTEGRATION만 켜고 공유DB에 직접 테스트하면 fixture 이전 exit4. 임시DB clone/cleanup
  원칙을 강화했으며 production trigger를 완화하지 않았다. 원래 fixture 이력은 보존하는 설계다.
- 검증: 오프라인1478 PASS/97 deselected/기존warning36, 새 데이터repair+SHADOW격리workflow3 PASS,
  전체Pyright0, 변경Ruff/format/diff PASS. 초기 malformed URL 예외/새head기대값/private helper import
  오류를 수정 후 재검증했다. Core image에0038을 포함해build PASS; 현재컨테이너는 중단/교체하지 않았고
  14:30 Core9/API/Web healthy. GPU/PRIMARY/사람 비밀번호/SSH 비밀번호 무변경.
- 후속 사용자 승인: `모든 테스트 고객사의 115건 전부`를 백업 후 비우고 임시 자료로 테스트한다.
  이 승인으로 앞선 초기화범위 BLOCKED가 해소됐다. 계정39·tenant·정책/인덱스·모델을 보존한다.
  FK closure로 업무56개 table, 보존25개 table 확인. RabbitMQ 모든queue메시지0. 아직 초기화는 NOT_RUN.
  다음은 post-repair DB와사진 최신백업, 서비스쓰기잠시중단, 한정초기화, 실제Q5/E3/RAG 임시접수검증이다.
  [DB 감사 JSON](DB_CONSISTENCY_2026-09-10.json).

### 2026-09-10 14:40 KST — 승인된 전체115건 초기화·백업 복원 검증

- 사용자 범위 확인 `모든 테스트 고객사의 115건 전부`에 따라 Core 쓰기6개 서비스를 잠시 정지했다.
  DB/MinIO/RabbitMQ와 GX10 Q5·Mac E3·Embedding·기존 GPU 서비스는 유지했다. 비밀번호 미사용.
- post-0038 DB dump와 MinIO raw 사본을 owner-only `/private/tmp/csight-all-test-reset-Yd7eYU/`에
  보관했다. dump SHA `ddd7ed0d2b9df9b99811b1b9840af2dfdd9bbdfbb1167941c5405ae543d972bf`.
  실제 격리 복원 후 일회성 RESET SQL을 먼저 시험했고, 같은115/73/122/32 인벤토리에 활성 DB도 적용했다.
- 정확56개 업무 테이블을 RESTRICT로 초기화했다. 계정/정책/인덱스 등25개 테이블 count/digest는
  전후 동일하고 복원 시험본 결과와 활성 DB 결과도 각 테이블별 동일했다. whole-object JSON의 key 순서
  차이를 처음 mismatch로 표시했으나 각 table 값 비교에서 차이0임을 확인했다.
- 기존 bucket은 삭제하지 않았다. 현재객체69·전체version항목121(삭제표식26)을 보관하고 빈 versioned
  `csight-evidence-feedback-20260910`을 새 활성 저장소로 선택했다. raw 사본 포함 보존됐지만 MinIO
  전체 복원 훈련/offhost/장기 보존은 NOT_RUN. `/private/tmp`이므로 별도 장기 보관이 필요하다.
- Core 최신0038 image로 재기동하여9개 healthy·API/Web 정상·alembic drift0. 옛 fixture17건/수정7건은
  활성 DB에서 제거됐고 post-repair 백업에 보존됐다. 과거 사람 이력은 가공하지 않았다.
- 후속14:54에 reset 검증용DB `csight_reset_restore_20260910_b71960ac`만 확인 후 삭제했다.
  이전 repair 검증용DB도 정리돼 있으며 원본 dump와 사진 보관본은 남겼다.
  [초기화/복구 기록](../operations/TEST_DATA_RESET_2026-09-10.md).

### 2026-09-10 14:55 KST — 임시10건 적재·실제 HTTP 응답 오류 수정

- 일반 인증/Evidence API로 가상문의와 출처 제한된 사진10건을 SHADOW 적재했다. 기존 actor의 단기
  로컬 token은 메모리에만 생성하고 Core가 DB 역할을 재확인했다. 비밀번호/사람 최종 결정 미사용.
- 초기 multimodal2.0.0 요청은422로 차단됐으며 지원 버전1.0.0으로 수정했다. 재시도 포함12개 run 중
  성공8·부분성공4. 서로 다른2개 문의에서 구형 Text-v1 출력 형식 실패가 발생했다. E3는10건 모두
  실제 고정 모델/threshold/원본bytes 검증을 통과했다. seeder는 명시적SHADOW partial 적재 옵션에서만
  계속하며 전체분석 FAIL 및 개별 PARTIAL_SUCCESS를 보존한다. 실패를 성공으로 가공하지 않는다.
- Text-v2 실제 비동기 후속에서 검색 DB commit 후 HTTP response500을 발견했다. 내부 execution_mode/
  model_route_plan_id/route_enforcement_contract_version3개가 공개 schema extra=forbid와 충돌했다.
  같은 Grounding 변환도 함께 공개필드 allowlist로 수정했다. 공개 API schema 자체는 변경하지 않았다.
- PRIMARY/SHADOW·route 유무 계약8개, 오프라인1493 PASS/97 deselected/기존warning36, Pyright0,
  변경Ruff/format/diff PASS. 두 live OpenAPI schema와 기존 snapshot 동일, generated types 동기화PASS.
  수정 Core image를 build·5개app 컨테이너 재생성해9개healthy로 복귀했고 같은멱등키로 요청을 재개했다.
- 재점검 PASS: 제약542 위반0, 새 사진10 byte/MIME/hash 일치, 원문10 hash/dual-write 일치,
  접수 이력 누락0. 과거 사진version121 유지. 후속 Text-v2/RAG/정책/검토10건은 아직 진행 중이다.

### 2026-09-10 15:04 KST — 초기화·임시10건 실제 흐름 및 DB 검증 완료

- 완료 PASS: 신규 문의10·사진10·접수이력10·원문보관10. 실제 Q5 Text-v2(local.8)10/10,
  RAW/HYBRID/Top3 검색10/10, 실제 Q5 Grounding(local.2)10/10, 정책평가10/10 성공.
  검토task10개 모두 PENDING. 사람결정·Resolution·외부intent0, 모든 분석SHADOW,
  모든 정책run에 서버의 feedback 허용 표시가 있다. 고객사/권한/사람 결정 경계를 유지했다.
- E3 원본/저장 bytes·MIME·hash와 실제 모델/threshold 검증10/10 PASS. 구형 text-v1의2개 Case에서
  부분성공4개 run(동일Case 재시도 포함)을 실패 그대로 보존했다. 전체 Analysis22개=성공18/부분4다.
  해당2개 Case도 별도text-v2/정책흐름은 성공했다. 구형 형식 신뢰성 개선은 미해결이며 PASS로 바꾸지 않았다.
- 최종 read-only 감사: 제약542 위반0·접수이력누락0·원문hash오류0·활성Evidence상태/bucket오류0,
  review packet10/citation pack10 해시 검증PASS. Text-v2 중복Case0. RabbitMQ 모든queue ready/unacked0,
  live Alembic drift0. /cases·/reviews용 operator API, case 상세·snapshot·검색/Grounding 목록 HTTP200.
  화면을 직접 조작한 사람 UI 피드백/최종 승인/시각 검증은 NOT_RUN이다.
- 보존 재확인: 계정39·정책문서44·조항304 유지. 초기화 직후25개 보존table의 count/hash 동일;
  실제 Grounding 이후24개는 그대로이고 grounding_profiles에Q5 고정profile1개만 정상 append됐다.
  기존2개profile count/hash `825c0ccd8b39b1625f22f3621a21ba85`는 동일하며 기존설정을 덮어쓰지 않았다.
- 재검증: 오프라인1493 PASS/97 deselected/기존warning36, 격리 PostgreSQL3 PASS 및 임시DB삭제,
  Pyright0·변경Ruff/format/diff PASS·공개schema2개 unchanged·OpenAPI types 동기화PASS.
  초기 검증명령에서 external marker4개는 환경gate로SKIPPED됐고 이후 공식offline exclusion으로 재실행했다.
- 14:59 read-only 런타임: Core9 healthy·API/Web/E3/Embedding HTTP200. GX10 Q5 17,497MiB,
  OOMKilled=false/restart0·기동시각유지. 다른GPU서비스 stop/kill/설치/모델전송/PRIMARY전환 없음.
  수정API image `733d27373e30ffbf2ecd5d4aa84400a4236b8a8c91f09abc2652d5f5ff4ee466`.
- 다음: 인증 담당자가 /reviews를 새로고침해 새10건을 읽고 피드백한다. 구형 text-v1 신뢰성·실고객
  품질/공동평가·E3사용권/출시승격은 별도 미완료다. `/private/tmp` 백업은 영구보관이 아니므로
  별도 장기/offhost 보존이 필요하다. 비밀번호는 사용/기록하지 않았고 기존 미커밋 변경은 유지했다.
  [최종 단계 JSON](TEST_DATA_RESET_2026-09-10.json), [초기화/복구 문서](../operations/TEST_DATA_RESET_2026-09-10.md).

### 2026-09-10 20:04 KST — 서버 재기동, GX10 여유 메모리 차단

- 사용자 요청에 기존 서버 제어 backend start 실행. Docker Desktop이 꺼져 있어 시작했고 기존9개Core가
  healthy로 복귀했다. API/Web/공개web-health·Embedding PASS. 데이터 초기화/빌드/migration 없음, 문의10건 유지.
- GX10 DNS 실패: Tailscale BackendState=Stopped를 확인하고 기존 앱을 열어 기존 accept-routes 값을 보존한
  up으로 재연결했다. 비밀번호/새로그인/설정reset 없음. SSH 키와 host-key 검증 유지.
- 재시도는 SYSTEM_HEADROOM_LOW로 BLOCKED. read-only 관측: GX10 MemAvailable12,652MiB,
  Q5 PID1457352/17,497MiB/running/oom=false, 다른vLLM PID1522141/74,676MiB,
  컨테이너 `kllm-recovery-recovery-20260910a-0` 약5시간실행. 다른작업은 종료하지 않았다.
- Mac E3는 별도로 기존 분리 세션/고정checkpoint로 시작하여 SHA·threshold0.8984375·MPS health PASS.
  Mac18004 Q5터널은 연결되지 않아 전체 모델 사용 가능 상태가 아니다. SHADOW/사람결정/모의업무 경계 유지.
- 다음은 식별한 다른 컨테이너 중단에 대한 사용자 확인 또는 메모리 반환 후 기존 start 재실행이다.
  전체비동기 재시험은 NOT_RUN, 코드 무변경이므로 코드테스트/타입검사 재실행 NOT_RUN.
  [단계 JSON](SERVER_RESTART_2026-09-10_2004.json).


### 2026-09-11 10:18 KST — 멘토링 반영 상담원 UI 개선·로컬 적용

- 요청: 정보 과밀을 줄이고 사진+작은 상품명/코드/금액+문의 요약+숫자 threshold+허용/비허용으로
  단순화한다. 목록은 제품이 아니라 문의를 보여주며 실제 사용할 이유가 분명해야 한다.
- 구현 PASS: 문의/검토 목록은 최대160자 원문 미리보기(생성 요약 아님), 없으면 요청 유형.
  기존 목록당SQL1회·권한/검색/페이지/담당자 경계 유지. 신규 optional inquiry_preview는
  같은tenant·unexpired·unpurged sensitive payload만 읽고 기존 원문fallback/새저장/모델호출 없음.
  검토 준비 건은 목록에서 바로검토, 상세에서 처리단계로 돌아갈 수 있다.
- 화면 PASS: 사진 아래 작은 상품/금액정보, 저장된 문의요약, 원문/정책/기술정보 접기,
  유사도는 중첩접기. 사진 파일메타정보 제외·원본확대/재시도 유지. 상품/금액 없으면 미확인표시.
  기존 quick-review threshold0.70만 큰 숫자로 표시하고 실제준비도는 별도표시; gauge 없음.
  E3점수/임계치·cosine·모델정확도와 합치지 않는다. 정책/최종확인/사진decode/CAS guard 유지.
- 설계/API: ADR0130·제품개선문서, HTTP max160 nullable필드·snapshot/generated 동기화.
  저장schema/event/기존분석 이력 변경없음으로 migration SKIPPED(불필요).
- 실제 검증 PASS: Frontend92/32files; E2E14(기존12+새desktop/mobile2, 접근성320/375/768/1024/1440);
  공식 make test 1493/98deselected/기존warning36; Pyright0; 변경Ruff/format; Webtype/lint/build;
  OpenAPI 생성파일동기화; diff검사. 격리 PostgreSQL clone2개테스트 PASS: 단일SQL읽기,
  최대160자·만료미리보기null·타tenant제외. 시험DB제거; 원본DB 변경없음.
- 중간 실패 정정: 첫 Web테스트6개는 신규필드decoder누락으로 실패해 decoder추가 후92PASS;
  E2E1개는 축약ID selector라 실패해 실제route 기반으로 수정 후14PASS. kwargs 타입오류 수정 후
  Pyright0. Docker꺼짐으로 최초통합검사BLOCKED 후 기존Docker앱기동→기존9개서비스복귀→격리검사PASS.
  최초pytest marker에 local외부3개가포함됐지만 env gate로SKIPPED였고 공식make test로 재검증했다.
- 로컬 반영 PASS(10:18): API/Web `ui-20260911` image로만교체, 이전 `before-ui-20260911`
  image태그보존. Compose사전/사후 env 전체값동일 검증. feedback키는 기존container env에서
  자식환경으로만전달; 비밀번호입력/파일저장/로그노출없음. overlay보간값누락 첫시도는 교체전실패,
  기존메모리값으로 해결. Core9healthy·APIready/Webhealth200·liveOpenAPI preview max160확인.
  모델설정·Worker/GPU 실행설정/DB/MinIO 무변경. 이번 모델health/새추론은 NOT_RUN.
- 시각검사 PASS: output/ui-mentoring-20260911/review-1440.png 및 review-375.png 직접확인.
  합성API fixture/테스트이미지 캡처이며 실제사진/사용자 로그인/실고객 의미품질 검증은 NOT_RUN.
- 인계: [x] 구현/계약/자동회귀/시각검사/문서/로컬반영. [ ] 로그인담당자 실제사용피드백.
  [ ] 같은문의·정책으로 기존처리대비 상담시간/이동횟수/결정오류/보고서수정시간 비교.
  실제절감률·ROI·고객품질·출시자격은 NOT_RUN이며 이전차단을 해소한것으로 주장하지 않는다.
  다음은 기존로그인으로 /cases 새로고침→문의선택→검토화면 피드백이다. Commit/Push/PR 없음.


### 2026-09-11 10:25 KST — 고객·상품·정책 하단 접기 및 기존 문의 URL 개선

- 사용자 추가 요청: 고객/상품정보는 하단 폴드, 고정정책도 기본접기, 사진/요약과 허용·비허용 우선.
- 구현 PASS: ReviewDetail의 고객정보·상품/주문정보(작은사진캡션포함)·원문·정책/분석상세를
  전체 판단영역 아래로 이동. 기존 CaseWorkspace의 고객/상품카드·주문메타·고정정책도 하단접기.
  대응하는 미결정 검토가 준비된 Case URL은 리뷰로 바로이동; 처리단계링크 ?details=1은
  명시적 예외로 기존복구/분석화면을 유지해 순환이동을 방지한다. 권한/사진오류/최종확인은 그대로.
- 검증 PASS: Frontend92, E2E15(기존Case URL→리뷰직행→처리상세 복귀와 기본접기 추가),
  TypeScript/lint/build/diff. desktop1440/mobile375 fixture 캡처확인. 중간 unit실패는 이전의
  처리화면/펼쳐진정책 기대값을 새계약으로 수정했으며 접힌항목이 다시열리는것도 검증했다.
- 반영 PASS: 로컬 Web만 ui-fold-20260911로 교체, 기존 Web환경값동일 확인·이전이미지태그보존.
  API/Worker/DB/model설정 변경없음. build에서 의존 Core image도 빌드됐지만 API는 재생성하지 않음.
  배포스크립트의 공용 API/Web 완료문구는 이번에는 Web만을 의미한다.
- 인계 체크리스트: [x] 폴드/동선/테스트/문서/로컬Web반영 [ ] 사용자 새로고침 후 실제사용 피드백.
  Backend/DB/API/event 무변경으로 Migration SKIPPED(불필요), Python/DB 재검사 NOT_RUN(직전1493/2는 이력).
  상담시간 절감·실모델품질은 NOT_RUN. 다음은 기존 문의 URL 새로고침 후 판단화면 밀도 확인.
  Commit/Push 없음, 기존 미커밋 작업 보존.


### 2026-09-11 10:39 KST — 이상가능성 게이지 제거·사진 우선 배치

- 사용자 요청대로 Vision 이상가능성 점수의 progress 게이지 제거. 숫자/기준/판단범위는 유지.
- CaseWorkspace 사진을 첫 콘텐츠로, 문의 내용을 사진 바로 아래로 이동. 저장된 Text-v2 summary가
  있으면 요약을 표시하고 원문은 접는다. 없으면 ‘저장된 요약이 없어 원문’ 표시; 새요약/추론 없음.
  지금할일 안내를 오른쪽으로 이동하고 사진 높이260px·원본보기 유지. ReviewDetail 사진→요약 유지.
- 검증 PASS: Frontend92, E2E15, Webtype/lint/build·diff. 저장요약/접힌원문 재열기, 게이지없음,
  사진아래문의 실제좌표 검사. fixture desktop캡처 직접확인; 최초오른쪽grid 폭문제 수정 후 재확인.
- 로컬Web ui-photo-20260911 반영 PASS, 이전이미지/env 보존. API/Worker/DB/모델 무변경.
  인계 [x] 구현/회귀/시각확인/배포/기록 [ ] 실제사용자 새로고침피드백. 다음은 기존문의 새로고침.
  Python/DB재검사 NOT_RUN(프런트변경만), Migration SKIPPED(불필요). 실모델/상담시간평가 NOT_RUN.


### 2026-09-13 16:51 KST — 서버 재기동 완료

- 사용자 요청에 기존 csight_server_control.sh start 실행. Docker·Embedding·GX10 Q5·E3·내부
  SHADOW 피드백 연결과 Core9 기동 PASS. Q5 running/ready/synthetic_canary PASS,
  available memory 약41GB, foreign_jobs_stopped0. Tailscale Running. 공개 주소 정상(controller 관측).
- API/Web/Embedding/E3 HTTP200, Core9healthy. 비밀번호 입력/데이터 초기화/migration 없음.
- 시작 스크립트가9/10 web:dev를 선택해 UI가 과거 버전으로 돌아가는 점 발견. 이전dev를
  before-restart-20260913로 보존하고 검증된9/11 ui-photo-20260911 image를 dev로 지정,
  Web만 재기동해healthy PASS. 이후 기본start도 최신UI를 선택한다. 새코드/새빌드 없음.
- 인계 [x] 재기동/상태/최신UI 보존 [ ] 사용자 새로고침. 다음은 기존 문의 화면 사용.
  코드테스트/전체업무E2E/실고객품질 NOT_RUN(운영기동만), 기존데이터/다른GPU작업 보존.


### 2026-09-13 16:59 KST — 문의 제목·요약·담당자 선택 UI 정리

- “기타 문의 문의 검토”를 “기타 문의 검토”로 정리. 목록의 요약 없는 경우도 공통 문의 제목 적용.
  요약 제목은 작은 중간 굵기, 본문은 더 큰 일반 굵기로 구분. 담당자 선택은 아이콘·통합 테두리·
  한 줄 정렬·44px 선택 영역·키보드 포커스로 개선. 기존 native select/배정 동작 유지.
- 검증 PASS: Frontend92, E2E15, typecheck/lint, Docker Web production build, diff-check.
  마지막 flex 방향 조정 후 담당자 배정 E2E 재검사1 PASS; desktop1280/mobile375 캡처 직접 확인.
  Review desktop1440 캡처에서 요약 위계 확인. 실사용 상담시간/고객 의미 품질은 NOT_RUN.
- Web만 ui-polish-20260913로 반영, dev 태그도 갱신. before-polish-20260913 이전 이미지 보존.
  Web healthy 및 /cases HTTP200/새 CSS 확인. Backend/DB/model 설정 무변경.
- 인계 [x] 구현/검증/시각 확인/로컬 반영/기록 [ ] 사용자 새로고침 후 피드백.
  다음: 실제 문의 화면에서 문구와 글자 위계 확인. Migration 불필요, Python 재검사 NOT_RUN.
  Commit/Push 없음; 기존 미커밋 변경 보존.


### 2026-09-13 17:04 KST — 담당자 선택을 문의 행에 통합

- 사용자 화면 피드백에 따라 하단 흰색 배정 구역 제거. 기존 담당자 표시 위치에 select 배치.
  PC 한 행, 모바일 동일 배경 내 줄바꿈. 링크/select는 형제 요소로 배정과 이동 구분.
- PASS: Frontend92, E2E15, typecheck/lint, production build, diff-check. 마지막 모바일
  상태 배지 표시 보완 후 배정 E2E1 재검사 PASS. PC/모바일 캡처 직접 확인.
- Web ui-inline-20260913 및 dev 태그 반영, healthy와 /cases HTTP200 확인. 이전이미지
  before-inline-20260913 보존. Backend/DB/모델 무변경, Migration SKIPPED(불필요).
- 인계 [x] 구현/검증/배포/문서 [ ] 사용자 새로고침 피드백. 다음은 실제 목록 배치 확인.
  실고객 품질·상담시간·Python 재검사 NOT_RUN. 기존 미커밋 작업 보존, Commit/Push 없음.


### 2026-09-13 17:15 KST — 상태 길이에 따른 담당자 열 이동 수정

- auto 상태 열을 PC112px/모바일100px로 고정. 관리자 담당자170px/날짜150px 유지,
  select 컨테이너의 최소폭과 폭을 명시. 문구가 달라도 주변 열 위치 동일.
- PASS: 배정 E2E1(상태4종 변경 시 담당자·날짜·화살표 x/width 동일 확인),
  접근성/가로넘침 E2E5(320~1440px), lint, production build/TypeScript, diff-check.
  PC fixture 캡처 직접 확인. 전체 unit/Python 재검사는 NOT_RUN(CSS 배치 수정).
- Web ui-fixed-columns-20260913/dev 반영 healthy, /cases HTTP200. 이전 image 보존.
  인계 [x] 수정/좌표검증/배포/문서 [ ] 사용자 새로고침 피드백. 다음: 실제 목록 정렬 확인.
  Backend/DB/model 무변경, Migration SKIPPED(불필요), 실고객품질/시간절감 NOT_RUN.


### 2026-09-19 19:11 KST — 프론트 배너 제거·사진 여백 조정
- 사용자 요청으로 AppShell 상시 실모델 피드백 배너 제거. 세션 만료/실패 알림 유지.
- 검토·상품 작업화면 사진 프레임 고정높이 제거, 원본비율·화면높이 상한 적용.
- PASS: Frontend92, focused E2E3, lint, production build/TypeScript. 실제 크기의
  합성 PNG로 PC/모바일 렌더 확인. 초기 배너 기대값/불필요 mock 및 SVG fixture 수정 후 PASS.
- Web만 responsive-evidence-20260919/dev 반영 healthy, login HTTP200. 이전 이미지 보존.
- 인계 [x] 구현/검증/Web반영 [ ] 실제사진 사용자피드백. 다음: 새로고침 후 사진밀도 확인.
  Backend/DB/model 무변경, Python NOT_RUN, Migration SKIPPED.


### 2026-09-19 19:15 KST — 사진 중앙 정렬·접기 항목 일관성
- 프론트 사진 중앙 정렬, PC 최대높이440px/43vh로 보완. 모바일 제한/원본비율 유지.
- 문의 원문 아래 상시 AI 안내문 제거.
- PASS: focused E2E3(PC/모바일), lint, production build/TypeScript, diff-check. PC 캡처 직접 확인.
- Web centered-photo-20260919/dev 반영 healthy. 이전 image 보존.
- 인계 [x] 구현/검증/반영 [ ] 사용자 새로고침 확인. 다음: 실제 사진 중앙 배치 피드백.
  Backend/DB/model 무변경, Python/unit 재검사 NOT_RUN, Migration SKIPPED(불필요).


### 2026-09-19 19:26 KST — 중앙정렬 누락 재수정
- 이전 중앙정렬 검증은 불충분했음. evidence-grid에 display:grid가 없었으며 이미지 링크도
  축소된 사진 폭과 별개로 왼쪽 정렬될 수 있었음. 명시적 grid/중앙정렬 및 margin-inline:auto 적용.
- PASS: focused E2E3(1440/375 이미지와 영역 중심차2px 미만 확인 포함), build/TypeScript, diff-check.
- 사용자 실제 브라우저 탭은 도구 목록이 비어 직접 관측 NOT_RUN. 로컬 fixture 좌표로 검증.
- Web photo-grid-fix-20260919/dev 반영 healthy, 이전image 보존.
- 인계 [x] 원인수정/좌표회귀/반영 [ ] 사용자 새로고침 후 확인. Backend 무변경.


### 2026-09-19 19:28 KST — 불필요한 요약 카드 제목 제거
- 사용자 요청: ‘문의 검토 요약’ 제목만 제거. 사진/문의요약/기존 동작 유지.
- PASS: ReviewDetail unit8, production build/TypeScript. Web no-summary-title-20260919/dev 반영 healthy.
- 인계 [x] 수정/검증/반영 [ ] 새로고침 피드백. 다음: 실제 화면 확인. Backend 무변경.


### 2026-09-20 14:00 KST — 시연용 데이터 자산 화면 간소화
- 전체 보관/실운영 분석 가능 건수, 처리 경험 활용 흐름, 최근 사례를 기본 표시.
  기술 분포/버전/비교기준은 상세 접기로 이동. 데이터 집계/출처/적재 계약 무변경.
- PASS: TypeScript/lint/build, data-assets E2E2(1440/375; 전체12/대상0 구분, 접기/펼치기, 가로넘침).
  PC fixture 캡처 직접 확인. Web asset-simple-20260920/dev 반영 healthy, 이전 이미지 보존.
- 인계 [x] 구현/검증/반영/문서 [ ] 실제 데이터로 사용자 시연 확인. 다음: 새로고침 후 촬영 동선 확인.
  전체 unit/Python 재검사 NOT_RUN, Migration SKIPPED(프론트만 변경). 실제 학습/성능 개선 주장 없음.


### 2026-09-20 16:58 KST — 1분 시연 영상 Codex 인계 패키지
- docs/demo-video/handoff: 실행 인계서, 복붙 프롬프트, 60초 SRT, 원본 구간 미입력 편집 JSON, QA 템플릿. ZIP 제공.
- 공식 Computer Use/Chrome 플러그인 + 로컬 FFmpeg 구성. 별도 영상 MCP 불필요,
  OS 권한/로그인/사람 최종 확정 인계, 다른 PC localhost 주의 및 원본 녹화 대체 경로 포함.
- PASS: 공식 문서 확인, JSON 목표합60초·SRT6구간·ZIP integrity. ffmpeg/ffprobe 로컬 존재 확인.
- 실제 녹화/편집/받는 사람 환경 검증은 NOT_RUN. 본 작업은 인계 문서 생성이며 영상 제작 완료가 아님.
- 인계 [x] 문서/프롬프트/파일/패키지 검사 [ ] 전달자의 접속주소·문의 지정 [ ] 촬영자 5초 시험/본녹화/편집.
  다음: ZIP 전달 후 README 준비표를 채워 START_PROMPT 실행. 서비스 코드/DB/배포 무변경.


### 2026-09-20 17:49 KST — 시연 검토 초기화와 운영 화면 정리

사용자 선택: 분석을 유지하고 검토 대기부터 재시작. ADR-0131 및 migration0039 추가.
GET/POST operations/demo-reset, 관리자 권한·환경 차단·tenant/synthetic 범위·지문 재확인,
진행 작업 차단·트랜잭션 archive·오래된 창 version 거부 구현. 처리 보고서와 모의 처리,
학습 자산은 보관 후 현재 집계에서 제외한다. 사진/원문/분석/정책/검토근거/행동이력은 보존.
원복 버튼은 실제 서버 배포했으나 실제 데이터는 초기화하지 않음(미리보기7건, archive0건).
실DB 백업 output/private/demo-reset-before-0039.dump(권한600), 이전 이미지 태그 보존.
운영 상태 준비도/버전은 접힘, 운영 지표 설명 간소화. 실제 오류를 준비 완료로 위장하지 않음.
검증 PASS: Backend4, disposable PostgreSQL1(0039 upgrade, 분석 불변, 보관, 재결정,
다른 조직/오래된 지문 차단, 중간 삭제 실패 rollback), Frontend93, fixture browser2,
변경 Ruff/Pyright0/typecheck/lint/build/diff-check, 실서버 API/Web healthy와 새 OpenAPI.
GX10 엔진 최초 OFF를 발견하여 기존 controller start로 복구: ready/running PASS,
외부 GPU 작업 종료0. 실운영 자격은 기존 차단 유지. 실제 UI POST/전체 신규 분석 NOT_RUN.
다음 담당자는 실제 초기화 실행 여부를 먼저 확인하고 archive를 임의 삭제하지 않는다.


### 2026-09-21 19:55 KST — 사용자 요청 GX10 llama.cpp 종료

전용 GX10 controller로 csight-qwen3.8-27b-q5-k-s 종료 PASS.
실제 반환 running=false, ready=false, foreign_jobs_stopped=0 확인.
Core/DB/Web 중단 명령 없음. 미해결 없음. 다음: 필요 시 명시 요청으로 재기동.


### 2026-09-28 19:28 KST — 공개 도메인 영상 첫 화면

- 목적: `doongdoong.org` 접속 시 CSight 프런트 대신 사용자가 준 MP4를 즉시 볼 수 있게 게시.
  루트와 `www` 루트, `/video.mp4`만 로컬 전용 영상 서버로 라우팅하고 기존 `/login`,
  `/api`, `/auth`, `/web-health` 경로는 CSight Web에 유지. Web/Core/DB/GPU 변경 없음.
- 산출물: `docs/demo-video/public-site/`의 55초·1920×1080 H.264·무음 원본 복사본,
  HTML5 무음 자동 재생 플레이어, 범위 요청 지원 Python 서버, LaunchAgent 설정·운영 README.
  원본과 공개 다운로드 SHA-256 일치. 배포본은 macOS LaunchAgent Desktop 접근 제한 때문에
  `~/Library/Application Support/CSightVideo/`에 설치. Tunnel 설정은 변경 전 백업 보관.
- 검증 PASS: AVFoundation 길이/코덱/오디오 확인과 1·27·53초 프레임 확인;
  로컬 HTML 200, MP4 200/206/416; `cloudflared ingress validate`와 루트·영상·로그인
  규칙 선택; 2026-09-28 19:26~19:28 KST 공개 루트·www 200, 영상 전체 해시 일치와
  범위 206, `/login`·`/web-health` 200; Playwright 브라우저에서 video paused=false,
  currentTime>1, duration=55, readyState=4, 1920×1080 및 실제 화면 확인.
- 검증 FAIL 후 해결: 첫 LaunchAgent는 Desktop 경로 접근 거부로 시작 실패. Library 배포본으로
  바꾼 뒤 running·로컬 200/206 확인. Tunnel 재시작 직후 일시적 530을 관측했으나 이후
  공개 200/206과 브라우저 재생을 재확인했다.
- 미해결: Mac이나 Cloudflare Tunnel이 중단되면 공개 링크도 중단된다. Cloudflare 분석
  스크립트는 영상 페이지 CSP에 의해 차단되어 브라우저 콘솔 오류 1건이 있으나 재생은 정상.
  ffprobe는 로컬 Homebrew x265 동적 라이브러리 누락으로 FAIL; AVFoundation으로 대체 확인.
  백엔드 테스트·Migration·앱 타입 검사는 SKIPPED(서비스 앱 변경 없음).
- 인계 [x] 게시 [x] 실제 공개 재생 [x] 원본/배포본 확인 [x] 설정 백업 [x] 문서화.
  다음: Mac 재부팅 또는 Tunnel 재시작 이후 `https://doongdoong.org/` 재생을 확인한다.


### 2026-09-28 19:30 KST — 영상 서버 타입 검사·재배포 확인

- 새 `serve.py`를 Pyright로 검사해 미초기화 가능 변수 1건을 수정한 뒤 Pyright 오류0,
  Ruff check/format, py_compile, plist lint, diff-check PASS. 배포본과 저장소 스크립트 일치.
- LaunchAgent 재시작 뒤 running, 공개 루트200, suffix Range206, 0바이트 Range416,
  기존 로그인200을 재확인. 앱 전체 타입 검사·테스트는 SKIPPED(앱 코드 변경 없음).


### 2026-09-29 20:16 KST — 공개 `/login` 영상 재생 추가

- 사용자 정정에 따라 루트 영상 게시를 유지하면서 `doongdoong.org/login`과 `www`의
  `/login`·`/login/`을 같은 플레이어로 라우팅했다. CSight Web/Core/DB/GPU 변경 없음.
  공개 `/login`에서는 기존 로그인 폼이 보이지 않으며 로컬 Web 로그인 경로는 유지된다.
- 검증 PASS: Python 서버 로컬 `/login`·`/login/` 200, Pyright 오류0, Ruff check/format,
  py_compile, Cloudflare ingress validate·규칙 선택, 공개 `/login`·`/login/`·www `/login`
  200, 공개 루트200·MP4 범위206·`/web-health`200, 로컬 Web `/login`200.
  Playwright 공개 `/login`: 제목 `CSight 시연 영상`, video 1개, paused=false,
  currentTime>1, duration=55, readyState=4.
- Tunnel 재시작 직후 첫 공개 `/login` 요청에서 일시적 530을 관측했다. 연결 안정화 후
  200과 실제 브라우저 재생을 재확인했다. 변경 전 Tunnel 설정 백업을 보관했다.
- 미해결: Mac/Tunnel 중단 시 공개 영상 링크도 중단. 공개 CSight 로그인 폼은 이 경로에서
  접근할 수 없다. 나머지 앱 전체 회귀 테스트·Migration은 SKIPPED(앱 코드/DB 변경 없음).
- 인계 [x] 라우팅 추가 [x] 공개 재생 확인 [x] 로컬 콘솔 확인 [x] 백업·문서 갱신.
  다음: 필요 시 Mac 재부팅 후 공개 `/login` 재생과 로컬 콘솔 접속을 다시 확인한다.


### 2026-09-29 21:17 KST — 공개 `/login2` CSight 로그인 경로 복원

- 사용자 요청으로 `/login` 영상은 유지하고 `web/src/App.tsx`에 `/login2` 로그인 라우트와
  비인증 업무 경로의 `/login2` 이동을 추가했다. 기존 `/login` 라우트는 로컬 호환을 위해 유지.
  운영 Web 이미지(9/20) 이후의 미커밋 프런트 변경은 함께 배포하지 않도록 기존 이미지의
  JS 자산 24개에 이번 라우트 변경만 입힌 overlay를 생성했다. 기존 이미지는
  `csight-web:before-login2-20260929`, 신규 이미지는 `csight-web:login2-20260929` 및 `dev`.
- 검증 PASS: App/LoginPage Vitest 3, TypeScript typecheck, ESLint, Vite production build,
  overlay 스크립트 Pyright 오류0·Ruff check/format·Node JS syntax; 격리 Web 컨테이너에서
  `/login2` 기존 파일럿 로그인 폼, 조직 슬러그/이메일/비밀번호 입력, `/cases` 비로그인 이동 확인.
  2026-09-29 21:15~21:17 KST 공개 `/login2` 폼·제목·경로 Playwright 확인,
  `/auth/capabilities` 200 및 legacy_password_enabled=true, `www/login2` 200,
  기존 `/login`·루트 200과 영상 범위206, `/web-health`200, Web healthy 확인.
- 검증 FAIL 후 해결: 첫 overlay는 지연 로드 JS가 기존 엔트리를 함께 불러 인증 Context가
  분리됐다. 모든 JS 자산 참조를 동일 버전으로 맞춘 두 번째 overlay를 격리 브라우저에서
  재검증한 뒤 운영에 반영했다. 실패한 시험 이미지는 제거하고 시험 컨테이너도 종료했다.
- 미해결: 실제 자격 증명을 이용한 로그인 완료와 인증 후 업무 화면 동작은 NOT_RUN.
  인증 API/폼/비로그인 라우팅 연결은 확인했다. DB/API 변경이 없어 Migration SKIPPED.
  기존 미커밋 변경은 보존했고 Commit/Push 없음.
- 인계 [x] 코드·회귀 검증 [x] 격리 Web 시험 [x] 공개 반영·브라우저 확인
  [x] 이전 이미지 보존 [x] 문서 갱신 [ ] 실제 계정으로 로그인 후 업무 화면 확인.
  다음: 사용자가 `/login2`에서 기존 계정으로 로그인해 `/cases` 진입을 확인한다.


### 2026-09-30 13:01 KST — GX10 메인 Q5 엔진 복구와 내부 연결 확인

- 요청: 워크스테이션 메인 엔진이 내려가 있으면 다른 작업을 정지하고 엔진을 다시 연결.
- 사전 관측 FAIL: 전용 controller에서 running=false/ready=false. Mac Core 9개 서비스와
  API/Web/Embedding/공개 주소는 정상. GX10의 실행 중 Docker 컨테이너와 GPU 계산 프로세스는
  각각 0개, 시스템 가용 메모리는 약 116GiB였다. 다른 계산 작업 종료0.
- 복구 PASS: `scripts/csight_internal_feedback.sh prepare`가 전용 Q5 기동과 합성 canary를
  완료했다. 13:01 KST 재확인 시 Q5 단독 컨테이너 running/ready, 시스템 가용 메모리
  103,524,970,496 bytes. Mac SSH 터널 `127.0.0.1:18004/health` 200, E3 8093 health 200.
- 연결 PASS: Core9 healthy, API ready 200. 배포 Worker 설정에서 SHADOW=true,
  LLM llama_cpp→Mac 터널, Vision remote 확인. 배포 Worker의 쓰기 없는 합성 probe에서
  Extraction·Vision·Embedding·Grounding 모두 PASS, DB 쓰기0·업무 효과0.
- 한계: 실제 계정 로그인/새 문의/검토 UI 종단 흐름은 NOT_RUN. 고객 의미 품질·출시 자격은
  기존 `NO_WINNER`·`NO_RELEASE_ELIGIBLE` 상태를 유지. 앱 코드·DB 변경 없음으로 Migration,
  전체 Ruff/Pyright/기본 테스트는 SKIPPED. 기존 작업트리·다른 장비 작업은 보존.
- 인계 [x] 사전 상태·다른 작업 확인 [x] Q5 복구 [x] Mac/Core 연결·합성 probe
  [x] 상태 문서 갱신 [ ] 인증 UI 종단 확인. 다음: `/login2`의 기존 계정으로 새 합성 문의를
  등록해 SHADOW 분석과 사람 검토 표시를 확인한다.


### 2026-10-01 14:12 KST — CSight Docker/PoC 스택 종료

- 요청: 이번 프로젝트 관련 Docker 작업을 모두 내림.
- 종료 전 PASS: Mac `csight-core` 실행 컨테이너 9개, GX10 전용 Q5 running/ready.
- 실행 PASS: `scripts/csight_server_control.sh stop`으로 GX10 전용 Q5, Mac Core Compose,
  공개 터널, Embedding, E3·SSH 연결을 종료. 컨트롤러는 DB·업로드 Docker 볼륨을 보존했고
  다른 GPU 작업 종료는 0개로 보고했다.
- 종료 후 PASS (14:12 KST): Mac `docker ps` 0개, GX10 `docker ps` 0개, 전용 Q5
  running=false/ready=false. Core 상태는 서비스 0개이며 API/Web/Embedding/공개 주소 응답 없음.
- 미해결: 종료 작업 없음. 재기동·기능 테스트는 NOT_RUN(사용자 요청 전 종료 상태 유지).
  앱 코드/DB 변경 없이 운영 상태·문서만 갱신했으므로 Migration·Ruff·Pyright·기본 테스트는
  SKIPPED. 다음: 재기동 요청 시 전용 controller start 후 Q5·Core·터널·합성 경로를 재확인.
- 인계 [x] 종료 전 인벤토리 [x] 서비스 종료 [x] 양쪽 Docker 사후 확인
  [x] 볼륨 보존 [x] 상태 문서 갱신 [ ] 재기동은 별도 요청 때 수행.


### 2026-10-01 14:13 KST — 종료 후 잔여 연결 정정

- 앞선 14:12 기록의 E3·SSH 연결 종료 표현을 정정한다. Controller stop은 성공했지만
  사후 `lsof`에서 CSight 전용 SSH 터널 18004와 E3 서버 8093 리스너가 남아 있었다.
  SSH 제어 소켓은 접속 거부였고, E3는 현재 screen 세션 밖의 기존 프로세스였다.
- 두 실행 명령과 소유자를 확인한 뒤 해당 PID 19237(SSH), 55704(E3)에 TERM을 보냈다.
  14:13:47 KST에 두 PID 및 E3 부모 PID 55702 종료, 포트 18004·8093 리스너 없음,
  Mac 실행 Docker 컨테이너 0개를 재확인했다. GX10 Q5와 Core 종료 결과는 앞선 기록대로다.
- 검증 PASS: 이번 요청의 실행 서비스 종료. 미해결: 재시작 시 컨트롤러의 기존 세션 밖
  E3·끊어진 SSH 제어 소켓 처리 경로는 개선 후보이며 이번에는 코드 변경 NOT_RUN.
  다음: 재기동 요청 때 연결 상태를 다시 확인하고 필요하면 제어 스크립트를 수정한다.


### 2026-10-18 KST — 국내 추계 2쪽 논문 작성 참고서

- 요청: 한국디지털콘텐츠학회 추계 2쪽 논문을 위한 상세 Markdown. 사용자에게 국내
  2026-11-19~20 수원 대회임을 확인하고 캡스톤 설계·산업적 활용 가치를 중심으로 구성했다.
- 산출물: `docs/papers/CSight_2026_추계_2쪽논문_작성참고서.md`. 제목·기여, 공식 학생/일반
  양식, 공학설계 요구-선택-구현-검증 표, 산업 기대효과와 측정식, 원본 증거 원장, 지면 배분,
  구조도/검증표, 복사용 본문 초안, 문헌3편, 예상질문·제출 체크리스트를 포함한다.
- 검증 PASS: 공식 국내 안내/제출 폼·HWP 본문과 문헌 서지 확인; JSON/JSONL 파싱으로
  정책 Test40·검토 Test30 분모와 Manifest/지표 hash 일치, 고유 Case10의4개 단계 PASS,
  전체 분석22=성공18/부분성공4·사람결정0 대조; 로컬 링크33개(고유23) 대상 존재·fence 균형.
  독립 문서 검토 후 학생양식의 지도교수/교신저자 구분과 검색·설명/정책 별도 경로 표현 보완.
- 주장 경계: 합성 문의·선별 이미지, 별도 Text-v2 경로, 과거 실험임을 명시했다. E3의 이진
  후보 점수와 최종 판단, 선별 시연과 대표 성능, 산업 기대와 실측 ROI를 구분한다. 기존
  실패와 NO_WINNER/NO_RELEASE_ELIGIBLE 상태를 보존하고 신규 실험·운영 승격을 수행하지 않았다.
- 미해결/NOT_RUN: 제출용 HWP·실제2쪽 렌더링·학회 접수, 저자/부문 확정, 실제 상담원
  시간·품질·경제성 평가. 서비스 가동 상태·GPU·기능 시험을 이번에 새로 확인하지 않았다.
  Migration·앱 테스트·Ruff/Pyright는 SKIPPED(문서만 변경). 기존 미커밋 작업 보존, Commit/Push 없음.
- 인계 [x] 참고서 작성 [x] 원본/형식 대조 [x] 인계 갱신 [ ] 공식 양식 조판·공동저자 검토·접수.
  다음: 참고서9절 초안과8절 구조도·표를 선택한 공식 HWP에 배치하고 실제2쪽을 확인한다.


### 2026-10-18 KST — 학생 양식 실제 2쪽 논문 초안

- 요청: 참고서를 기반으로 실제 제출할 2쪽 논문 초안, 캡스톤 설계·산업적 활용 강조,
  그림과 검증표 포함. 사용자 제공 김혜린·차인택, 선문대학교 AI소프트웨어학과, 학생 이메일2개,
  황세웅 지도교수(교신저자)를 반영했다.
- 산출물: `output/papers/CSight_2026_추계_2쪽_논문초안.docx`,
  `output/pdf/CSight_2026_추계_2쪽_논문초안.pdf`, `output/papers/CSight_시스템구조도.png`,
  `docs/papers/CSight_2026_추계_2쪽_논문초안.md`, `CSight_2026_추계_초안_편집메모.md`.
- 형식: 공식 학생 HWP를 내려받아 A4/2단/단간8mm/본문10pt/제목16pt/장제목12pt/캡션9pt
  등 추출. 초록/영문제목 없는 학생양식 순서와 지도교수 칸을 적용. PDF는 지정 글꼴을 함초롬으로
  대체 렌더링하며 영문 참고문헌 자간/정렬 조정은 별도 메모에 명시했다.
- 검증 PASS: render_docx 최종2페이지 PNG 시각검수; pypdf A4 2쪽 및 저자/소속/이메일/
  교수/시험분모/참고문헌 텍스트 확인; DOCX 그림1·표1(4행3열); 한글 뷰어 DOCX 정상 열람 및
  인쇄 미리보기 1/2·2/2 확인. 독립 근거 검토 필수수정0. 초기 글꼴누락·표폭오류는 수정/재렌더했다.
- 실패/한계: native HWP 직접생성 후보는 pyhwp 파싱 성공에도 실제 한글에서 손상 오류.
  후보는 tmp에만 보존하고 납품하지 않았다. 한글 편집기에서 HWP 저장/최종 서식 재검수가 남는다.
  PDF는 LibreOffice 렌더 검토본이다. 교수 이메일/지원사업 감사문구는 임의 생성하지 않았다.
- 증거 경계: 정책 합성Test40·검토합성Test30·내부합성문의/선별이미지10의 별도경로,
  구형Text-v1 부분실패4회·사람결정0·외부동작0 및 현장효과 미측정을 보존했다. 그림은 검색/설명과
  정책평가를 분리하고 AI 참고정보와 사람의 최종결정 경계를 표시한다.
- 인계 [x] 본문·저자 [x] 그림·표 [x] 두쪽 렌더·시각검수 [x] DOCX 한글열람
  [x] 상태문서 갱신 [ ] 공동저자 검토·HWP 저장·접수. 다음은 편집 메모에 따른 HWP 최종화.
  앱/DB/운영서비스 변경0, GPU/신규실험/학회접수 NOT_RUN, 코드테스트 SKIPPED(문서작업), Commit/Push 없음.


## 2026-10-19 저장공간 정리 인계 (2026-10-19T11:51:58.744308+09:00)

- PASS: 사용자 승인으로 Mac Docker의 7일 이상 미사용 build cache만 정리했다. Docker 보고 회수량815.8MB, 실행 컨테이너0을 확인했다. 컨테이너10개·이미지·볼륨16개·현재 서비스용 가상환경·가중치는 보존하며 서비스 시작/중지는 하지 않았다.
- PASS: 별도 과거 RC bc2d7be의 `.venv`/`web/node_modules`는 열린 파일0·프로세스 참조0 및 원격 commit/lockfile 확인 후 재생성 가능한 설치 파일만 정리했다. 원천 코드·DB·업로드·분석 이력은 보존했다.
- NOT_RUN: 앱 품질 검사·실서비스 재기동·모델 호출·의존성 실제 재설치. 미해결 기존 출시/논문 항목은 위 원래 기록을 따른다.
- 다음: 과거 RC 개발 환경이 필요하면 해당 작업본에서 `uv sync --frozen --group dev`, `cd web && npm ci`로 재설치한다. 현재 작업본 소스의 별도 비공개 보관 브랜치를 생성·원격 blob 검증하고 결과 영수증을 DefenseSLM `artifacts/mac-project-docker-cleanup-20261019-s01`에 남긴다. 기존 기능 브랜치 HEAD·미커밋 작업은 유지한다.
