# CSight 현재 상태 및 세션 인계

이 문서는 다음 작업 세션의 시작점이다. 최신 상태 요약은 갱신할 수 있지만, 세션 로그는
append-only로 유지한다. 상세 Sprint 0 증거는 `SPRINT_0_FOUNDATION.md`를 참조한다.

## 0. 문서 메타데이터

| 항목 | 값 |
|---|---|
| 현재 완료 단계 | Sprint 0 — Foundation; CV E1~E3 학습과 held-out 평가 완료 |
| 진행 중 작업 | Vision 모델 패키징과 Sprint 1 Case/Evidence 구현 준비 |
| 마지막 갱신일 | 2026-08-27, Asia/Seoul |
| 연결 GitHub 계정 | `kimhrin` |
| 원격 저장소 | Private `CSightICT/csight-core` |
| 로컬 Git | `main`·`develop`, Foundation 초기 커밋 `6fc20d3` |
| 마지막 런타임 관측 | 2026-08-27 19:02 KST, E3 12 epochs 정상 종료; OOM·NaN·traceback 없음 |

## 1. 다음 세션 시작 체크리스트

- [ ] `CSight_project_docs/AGENTS.md`, 관련 설계 문서, Accepted ADR을 읽는다.
- [ ] 이 문서의 진행 중 작업, 미해결 사항, 다음 작업을 확인한다.
- [ ] `pwd`, `git status --short --branch`, `git remote -v`로 실제 저장소 상태를 확인한다.
- [ ] 필요하면 `docker compose --env-file .env -f infra/compose.core.yml ps`로 런타임을
  다시 확인한다.
- [ ] 변경 전 관련 테스트, Migration, API/Event 계약을 확인한다.
- [ ] 이번 세션의 범위와 하지 않을 일을 명시한다.
- [ ] 아래의 첫 번째 미완료 실행 항목부터 진행한다.

## 2. 단계별 상태

| 단계 | 상태 | 근거 또는 다음 조건 |
|---|---|---|
| Sprint 0 Foundation 구현 | PASS | 상세 기록과 2026-08-26 검증 결과 존재 |
| GitHub 협업 문서·템플릿 | PASS | 브랜치 규칙, PR·Issue 템플릿, CODEOWNERS 작성 |
| 초기 Git 안전성 감사 | PASS | 고신뢰 Secret·5 MiB 초과 파일 없음, 방어 Ignore 보강 |
| 로컬 Git 초기화 | PASS | `main` 초기 커밋 `6fc20d3`, 로컬 `develop` 준비 |
| GitHub 조직·저장소 | PASS | Private `CSightICT/csight-core`, `develop` 및 feature branch 확인 |
| 원격 브랜치·보호 규칙 | IN_PROGRESS | `feature/3-kaputt-dinov2-training`과 draft PR #4 생성; 보호 규칙은 별도 확인 필요 |

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
- [x] GitHub Actions 원격 실행: latest push #98 / PR #99 성공

## 4. GitHub 협업 구축 체크리스트

- [x] 연결 계정 `it0615` 확인
- [x] 경량 GitFlow와 브랜치 명명 규칙 문서화
- [x] PR 템플릿과 Issue Form 작성
- [x] 초기 CODEOWNERS를 `@it0615`로 지정
- [x] 모든 세션 종료 시 상태 문서를 갱신하도록 `AGENTS.md`에 규칙 추가
- [x] 초기 커밋 대상의 Secret·대용량·Binary 안전성 감사
- [x] 로컬 Git을 `main`으로 초기화
- [x] 로컬 Foundation 초기 커밋 `6fc20d3` 생성
- [x] 로컬 `develop` 장기 브랜치 생성
- [ ] 조직 handle과 저장소 이름·공개 범위 확정
- [ ] GitHub 브라우저 로그인
- [ ] 조직 생성 및 소유자 확인
- [ ] Private 저장소 생성
- [ ] 원격 `main` Push
- [ ] `develop` 장기 브랜치 생성
- [ ] `main`과 `develop` Branch protection 적용
- [ ] 첫 GitHub Actions 성공 후 Required check Context 확정
- [ ] 팀·협업자 권한과 조직 단위 CODEOWNERS 갱신

## 5. 마지막 검증 원장

| 날짜 | 명령·검사 | 상태 | 실제 결과 |
|---|---|---|---|
| 2026-08-26 | `uv sync --frozen --group dev` | PASS | Python 3.12 환경과 lockfile 설치 |
| 2026-08-26 | Ruff / Ruff Format | PASS | 76 files |
| 2026-08-26 | Pyright strict | PASS | 0 errors, 0 warnings |
| 2026-08-26 | 기본 pytest | PASS | 37 passed |
| 2026-08-26 | Core Integration | PASS | 4 passed |
| 2026-08-26 | Architecture / Contract / E2E | PASS | 2 / 14 / 3 passed |
| 2026-08-26 | `make test-all` | PASS | 기본 37 + Integration 4 |
| 2026-08-26 | Compose와 Health 장애·복구 | PASS | 정상 200, RabbitMQ 장애 503, 복구 200 |
| 2026-08-26 | Git 초기 커밋 안전성 | PASS | 고신뢰 Secret·5 MiB 초과 파일 없음, Ignore 적용 확인 |
| 2026-08-26 | 협업 문서 YAML | PASS | Issue Form 4개와 CI Workflow 파싱 |
| 2026-08-26 | Foundation 초기 커밋 | PASS | `main` commit `6fc20d3` |
| 2026-08-26 | GitHub 원격 CI | NOT_RUN | 원격 저장소 미생성 |
| 2026-08-27 | GitHub Actions #98 / #99 | PASS | Ruff lint/format, Pyright, fast tests 성공 |

## 6. CV 학습 상태 (Kaputt DINOv2)

- [x] Issue #3, feature branch `feature/3-kaputt-dinov2-training`, draft PR #4 생성
- [x] 공식 parquet 행 수와 item 식별자 split 중복 검사
- [x] 전체 이미지 존재 검사: train 85,326 / validation 4,874 / test 10,067, 누락 0
- [x] RTX 4090 1024px W&B 온라인 스모크 런 `72pfb9n1`
- [x] W&B에 loss, learning rate, AP, AUROC와 시스템 지표 동기화 확인
- [x] E1을 epoch 4 checkpoint까지 보존 후 중단: 최고 validation AP 0.306988, W&B run `93fdt5a0`
- [x] Full-frame resize + AdamW E2 완료: 8 epochs, AP 0.839467, AUROC 0.917615, W&B run `0kitqdog`
- [x] E2 validation AP 기준 best checkpoint 확정
- [x] E3: E2 best 가중치 초기화, batch 16, fused AdamW, 12 epochs 완료 (`e33m1xdx`)
- [x] E3 validation AP 기준 epoch 10 best checkpoint 확정: AP 0.847034, AUROC 0.922177
- [x] Validation에서 threshold 0.8984375 동결 후 test split 1회 평가: AP 0.884863, precision 0.954333, recall 0.508422
- [x] 재질·결함군별 PoC 분석: 경질 플라스틱 + deconstruction/actuation 추천
- [x] Test prediction 원본 SHA-256 기록; 데이터·checkpoint는 GitHub 미업로드

## 7. 미해결 사항과 사용자 결정

- 실제 PoC 상품 1종과 재현 가능한 결함 정의를 확정해야 한다.
- 현재 CV 모델은 이진 분류기이므로 결함 유형·위치 출력 방식(VLM 또는 별도 head)을 정해야 한다.
- 정책 표현, 개인정보 보존 기간, 인증·Tenant 범위는 다음 Sprint의 ADR 대상으로 남아 있다.
- PR #4는 draft이며 최종 review와 merge는 별도 승인 후 진행한다.

## 8. 다음 실행 항목

1. E3 모델·전처리·threshold를 버전된 Vision inference package로 묶는다.
2. Sprint 1 Case/Evidence CRUD, MinIO 업로드, 실제 Alembic migration을 구현한다.
3. Append-only Analysis Run과 실제 Vision HTTP adapter를 연결한다.
4. 경질 플라스틱 1종의 deconstruction/actuation Shadow Mode 평가를 준비한다.

## 9. 세션 종료 체크리스트

- [ ] 변경한 파일과 목적을 기록했다.
- [ ] 실제 실행한 검증 명령과 결과만 기록했다.
- [ ] 실패·미실행·Skip을 `PASS`로 표현하지 않았다.
- [ ] 외부 서비스 상태에 관측 날짜를 붙였다.
- [ ] 남은 Blocker와 필요한 사용자 결정을 적었다.
- [ ] 다음 작업을 한 개 이상의 실행 가능한 체크박스로 남겼다.
- [ ] Secret, 고객 원문, 전체 URL을 기록하지 않았다.
- [ ] 아래 세션 로그를 추가했다.

## 10. 세션 로그

### 2026-08-26 — Sprint 0 Foundation 완료

- 목표: 실행 가능한 FastAPI/Celery/PostgreSQL/RabbitMQ/MinIO Foundation 구축
- 완료: API, Port/Adapter, Mock AI, Migration, Worker, Compose, CI, 테스트, 문서
- 검증: 기본 37건과 Integration 4건을 포함한 `make test-all`, 실제 장애·복구 경로 통과
- 미실행: GitHub 원격 CI
- 다음 작업: GitHub 협업 기반 생성 후 Sprint 1 Case/Evidence 경계 구현

### 2026-08-26 — GitHub 협업 기반 준비

- 목표: 조직 저장소, 장기 브랜치, PR 중심 협업, 세션 간 인계 체계 구축
- 완료: GitHub 계정 확인, 브랜치 정책, 기여 규칙, PR·Issue 템플릿, 체크리스트,
  초기 커밋 안전성 감사, 로컬 `main`·`develop`과 Foundation 초기 커밋
- 검증: GitHub 플러그인에서 연결 계정 `it0615` 확인, 새 조직 미존재 확인. 고신뢰
  Secret과 5 MiB 초과 커밋 후보가 없고 Issue Form YAML이 파싱됨을 확인. Ruff, Format,
  Pyright, 기본 37건과 Core Integration 4건 재통과
- Blocker: 조직 handle 미확정, 브라우저 GitHub 로그인 필요
- 다음 작업: Git 안전성 감사 후 로컬 초기화, 조직·저장소 생성, Push, 보호 규칙 적용

### 2026-08-27 — Kaputt DINOv2 전체 파인튜닝 시작

- 목표: 이틀 내 CSight 시각 결함 분류 PoC의 재현 가능한 기준 모델 확보
- 완료: DINOv2 ViT-S/14 전체 이미지 학습 코드, W&B 추적, 데이터 무결성 검사,
  guarded launcher, Issue #3·feature branch·draft PR #4 구성
- 검증: Ruff/format, compileall, pytest 1건, split 중복 0건, 이미지 누락 0건,
  RTX 4090 온라인 스모크 런 통과
- 실행 중: 1024px, batch 8, BF16, Adam 5e-6, cosine, seed 42, 8 epochs 전체 파인튜닝
- 다음 작업: validation AP 추적, best checkpoint 고정, test split 1회 평가 및 결과 문서화

### 2026-08-27 — E1 중단 및 full-frame E2 시작

- E1 완료 범위: epoch 4 validation과 checkpoint 저장 후 중단, 최고 AP(any) 0.306988
- 원인 진단: timm 기본 RandomResizedCrop의 최소 면적 8%가 작은 결함을 제거할 가능성
- E2 변경: 전체-frame resize, AdamW, backbone/head LR 분리, 5% warmup,
  bias·LayerNorm weight decay 제외, gradient checkpointing 해제
- 검증: Ruff/format, compileall, pytest 4건, 1024px batch 8 스모크와 약 8.9GiB peak 확인
- 실행 중: W&B run `0kitqdog`; test split 미사용

### 2026-08-27 — Full-frame E2 완료

- 완료: 8 epochs, 85,328 updates, W&B state finished, best/last checkpoint 저장
- 최종 validation: loss 0.320136, AP(any) 0.839467, AUROC 0.917615,
  Recall@50% precision 0.938820, Recall@1% FPR 0.355426
- 비교: E1 대비 AP +0.532479, AUROC +0.382968
- 제한: 여러 학습 요소를 함께 변경했으므로 개선을 resize 하나에만 귀속할 수 없음
- 미실행: test split 평가
- 다음 작업: best checkpoint와 임계값을 동결한 뒤 test split을 한 번만 평가

### 2026-08-27 — E3 stage-2 연속 학습 시작

- 목적: E2가 마지막 epoch까지 개선된 점을 근거로 E2 best 가중치에서 저학습률 연속 학습
- 변경: optimizer/scheduler는 새로 초기화, batch 16, backbone LR `2e-6`, classifier LR `3e-5`, 2% warmup, fused AdamW
- VRAM 판단: batch 16 약 17.5GiB·27.2 images/s, batch 20 약 21.8GiB·28.9 images/s로 측정해 장시간 안정 여유가 큰 batch 16 채택
- 검증: Ruff/format, compileall, pytest 5건, 1024px batch 16 weights-only 스모크 통과
- 실행 중: W&B run `e33m1xdx`; 초기 GPU 100%, VRAM 19,051/24,564MiB, OOM·NaN·traceback 없음
- 미실행: test split 평가
- 다음 작업: validation 지표와 early stopping을 감시하고 최종 best checkpoint를 동결


### 2026-08-27 — E3 종료, held-out 평가와 PoC 범위 분석

- 완료: E3 12 epochs 정상 종료, validation AP 기준 epoch 10 `best.pt` 확정
- Validation: AP(any) 0.847034, AUROC 0.922177
- Test 1회: AP(any) 0.884863, AUROC 0.931604
- Threshold: validation에서 0.8984375로 동결; test precision 0.954333, recall 0.508422
- PoC 후보: 경질 플라스틱 상품군의 `deconstruction`과 `actuation`
- 코드: 그룹 분석, metadata 보존, 단위 테스트, 기존 Ruff 오류 수정 반영
- 제한: 이진 분류 모델은 결함 유형·위치를 직접 출력하지 않으며 사람의 최종 결정을 대체하지 않음
- 다음 작업: CI 통과 확인, 모델 패키징, Case/Evidence와 실제 Vision adapter 구현


### 2026-08-27 — PR #4 누락 반영과 CI 복구

- 업로드: E3 최종 보고서, PoC 추천, 구현 공백 점검, 그룹 분석 코드와 테스트
- 수정: prediction grouping metadata, Python 3.12 UTC, Ruff import/format 호환
- 검증: GitHub Actions push #98과 pull request #99 모두 success
- 브랜치: `develop` 대비 ahead, behind 0; PR #4는 draft 유지
