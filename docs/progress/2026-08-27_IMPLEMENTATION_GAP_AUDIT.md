# CSight 저장소 구현 공백 점검

작성일: 2026-08-27  
점검 대상: `CSightICT/csight-core`, `develop` 및 PR #4 기능 브랜치

## 1. 현재 구현 수준

현재 저장소는 Sprint 0 Foundation 수준이다. FastAPI 실행 골격, health/readiness,
Celery 작업 골격, PostgreSQL/MinIO/RabbitMQ 연결 준비, LLM·Vision Mock adapter,
공통 AI schema와 기초 테스트는 있다. 반면 실제 업무 Case를 접수해 이미지 분석 결과를
저장하고 상담원이 결정하는 기능은 아직 없다.

| 영역 | 현재 상태 | 근거 경로 |
|---|---|---|
| 앱/설정/Health | 골격 구현 | `app/main.py`, `app/bootstrap`, `app/interface/http/routers` |
| AI 공통 schema | 기초 구현 | `app/platform/analysis` |
| LLM/Vision | Mock만 구현 | `app/adapters/llm/mock.py`, `app/adapters/vision/mock.py` |
| 분석 use case | Mock 기반 골격 | `app/application/analyze_case.py` |
| Worker | Celery 골격 | `app/interface/workers` |
| DB | Engine/session과 빈 baseline migration | `app/adapters/persistence`, `alembic/versions/20260825_0001_baseline.py` |
| Case/Evidence | 패키지 표지만 존재 | `app/platform/case`, `app/platform/evidence` |
| 정책/결정/검토/보고서/감사 | 패키지 표지만 존재 | `app/platform/policy`, `decision`, `review`, `report`, `audit` |
| 상품 불량 도메인 | 빈 패키지 | `app/domains/product_defect_cs` |
| CV 학습 | E1~E3 학습·평가 완료 | `ml/cv` |

## 2. Vision 담당자가 바로 구현해야 할 부분

저장소의 역할 분담 문서에서 Vision 담당자의 책임은 taxonomy 협의, 데이터·라벨링,
모델 학습·평가, export와 전처리·후처리 명세, class별 threshold와 실패 사례 제공이다.
현재 완료된 것은 이진 모델 학습·평가와 PoC 후보 분석까지다. 다음이 직접 남아 있다.

### P0 — PoC 연결에 필수

1. **모델 패키지 확정**
   - E3 epoch 10 checkpoint 식별자
   - 입력 1024×1024, RGB, resize, ImageNet 정규화 명세
   - threshold `0.8984375`와 validation 선택 근거
   - 모델/데이터/preprocess/threshold version
2. **Vision inference adapter 또는 독립 API**
   - `app/ports/vision.py` 계약에 맞는 HTTP adapter 추가
   - 실제 모델 서버는 DB에 직접 접근하지 않음
   - 입력 검증, timeout, model version, latency, 실패 코드 반환
3. **공통 출력 계약 조정**
   - 현재 모델은 bounding box와 결함 유형을 출력하지 않음
   - 이진 결과를 `defect_probability`, `decision_support_band`, `model_version`으로 명확히
     표현하고, 없는 geometry/type을 만들어내지 않음
4. **재현 산출물**
   - `model_card.md`, `evaluation_report.md`, `preprocess.yaml`, `postprocess.yaml`,
     `thresholds.json`, `labels.json`, `sample_inputs/`, `sample_outputs/`
   - checkpoint와 실제 이미지는 GitHub가 아닌 원격 모델 저장소에 두고 checksum만 기록
5. **실제 상품 domain-shift 평가**
   - 경질 플라스틱 상품 1종, `deconstruction`/`actuation` 두 결함군
   - 상품/촬영 세션 누수 없는 split
   - 오류 사례와 이미지 품질 실패 조건 기록

### P1 — 결함 설명 기능

1. 이진 분류와 별도로 VLM(Vision-Language Model, 시각언어모델) 또는 multi-label/
   detection head를 통해 결함 유형·위치 후보를 제공한다.
2. Kaputt에는 한국어 문의가 없으므로 이미지와 한국어 고객 문의를 연결한 소규모 Bridge
   Dataset을 만든다.
3. 모델 confidence calibration과 `고신뢰/검토/추가 증거` 구간을 실제 PoC 데이터에서
   다시 정한다.

## 3. 백엔드와 공동으로 구현할 부분

### 우선순위 1 — Case/Evidence 접수

- `app/platform/case`, `app/platform/evidence`: entity와 상태 전환
- `app/ports/repository.py`, `app/ports/storage.py`: 구체 contract
- `app/adapters/persistence`: Case/Evidence repository와 SQLAlchemy model
- `alembic/versions`: 실제 schema migration
- `app/adapters/storage`: MinIO upload, MIME/크기/hash 검증
- `app/interface/http/routers`: Case CRUD와 evidence upload API

### 우선순위 2 — Append-only 분석과 실제 Vision 연결

- `analysis_runs`와 vision 결과를 덮어쓰지 않고 새 run으로 저장
- `Idempotency-Key`, retry, timeout, partial failure 구현
- `app/adapters/vision/http.py` 같은 실제 adapter와 contract test 추가
- 모델·preprocess·threshold version을 결과에 연결

### 우선순위 3 — Policy와 Human Review

- `app/domains/product_defect_cs`: 결함 taxonomy와 alignment 규칙
- `app/platform/policy`, `decision`: versioned rule evaluator와 routing
- `app/platform/review`, `audit`: 상담원 승인·수정·이관과 원본 권고 보존
- 고액·안전·분쟁 조건은 모델 점수와 무관하게 사람에게 이관

### 우선순위 4 — Report와 평가

- Case 단위 검토 보고서
- 모델·정책·프롬프트·threshold version 기반 재현
- Shadow Mode에서 검토시간, override, 위험 라우팅 오류 측정
- 실제 Case 접수부터 Review 확정까지 E2E(End-to-End) test

## 4. 2인 팀용 현실적 구현 순서

| 순서 | Vision 담당 | Backend 담당 | 공동 완료 기준 |
|---:|---|---|---|
| 1 | E3 모델 패키지·샘플 I/O | Case/Evidence DB·API·MinIO | 이미지가 포함된 Case 생성 |
| 2 | 로컬 Vision API와 contract test | Analysis Run·Celery·Vision adapter | 202 응답 후 결과 저장 |
| 3 | 경질 플라스틱 2결함 샘플 평가 | Alignment·routing rule | 고신뢰/검토/추가자료 분기 |
| 4 | 실패 사례·threshold 문서 | Human Review·Audit | AI 권고와 사람 결정을 모두 보존 |
| 5 | Shadow Mode 분석 | Report·KPI 집계 | PoC 평가 문서 생성 |

RAG(Retrieval-Augmented Generation, 검색증강생성), 고급 인증, Triton, UniVAD,
외부 CRM 연동, 상용 배포 최적화는 이 흐름이 동작한 뒤로 미룬다.

## 5. 이번 점검에서 확인된 GitHub 누락

- E3 완료 결과와 held-out test 결과가 기존 실험 보고서와 PR 설명에 반영되지 않음
- Validation/test 그룹 분석 재현 코드와 단위 테스트가 브랜치에 없음
- 평가 prediction에 `item_material`과 `defect_types`를 보존하는 코드가 브랜치에 없음
- 기존 CI 실패 원인인 Ruff import/UTC/list 구성 오류 수정이 브랜치에 없음
- `CURRENT_STATUS.md`가 E3 실행 중·test 미사용 상태로 남아 있음

위 항목은 PR #4 기능 브랜치에 코드·집계 문서 형태로 반영한다. 데이터셋, checkpoint,
개별 prediction은 보안·라이선스·용량상 업로드하지 않는다.


