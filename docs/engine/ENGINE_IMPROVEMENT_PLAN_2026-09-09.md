# CSight 두 엔진 개선 계획과 1차 구현 결과

작성일: 2026-09-09. 우선순위: 업무 품질 → 불확실성/안전 → 처리량/안정성 → 문서당 300초.

## 이번 작업의 완료 범위

두 엔진이 이미 반환한 결과를 받아 고객 주장별로 이미지 근거 후보와 미확인 이유를 계산하는
**오프라인 대조 엔진 1.0**을 구현했다. 실행 도구, 재현 가능한 합성 계약 평가, 무결성·안전 테스트와
ADR-0126까지 포함한다. 기존 모델 가중치, 운영 서비스, PRIMARY, 정책 입력, 상담원 화면은 변경하지 않았다.

이 완료 범위는 실제 모델 정확도 향상, 모델 학습 완료 또는 출시 자격을 뜻하지 않는다.

| 단계 | 완료 기준 | 현재 상태 |
|---|---|---|
| 입력 계약과 개선 계획 | 현재 text v2/Vision schema로 표현 가능한 근거와 불가능한 추론 구분 | PASS |
| 주장별 대조 엔진 | 출처·스냅샷 검증, 유형 후보 연결, 판단 불가·추가 자료 코드 | PASS |
| 오프라인 실행/평가 | canonical 입력 replay, 합성 30건, 결과 불변 보존 | PASS |
| 회귀·정적 검사 | 기본 backend 1,335건, Ruff, 집중 Pyright | PASS |
| 실제 모델 공통 평가 | 모델을 실행한 대표 문의/사진과 독립 정답 비교 | NOT_RUN |
| 상담원 화면·정책 연결 | 별도 qualification, 영속화·권한·보존·전체 workflow 검증 | NOT_RUN |

## 1. 두 엔진을 연결하는 현재 규칙

| 입력 상황 | 반환 | 의미 |
|---|---|---|
| 명시한 점수 기준 이상, 사용 가능한 사진, 지원하는 결함 유형 일치 | TYPE_CANDIDATE | 같은 유형의 모델 관찰 후보가 있음. 고객 주장의 진위 확정 아님 |
| 위치가 있는 주장 | CLAIM_LOCATION_UNVERIFIED | 이미지 좌표만으로 상품 안쪽/윗부분을 추론하지 않음 |
| E3 전체 결함 점수만 있음 | UNRESOLVED / IMAGE_LEVEL_ONLY | 점수를 결함 종류·위치로 바꾸지 않음 |
| 검출 없음 또는 다른 종류 검출 | UNRESOLVED | 정상/고객 주장 오류로 단정하지 않음 |
| 흐림·가림·품질 미평가 | UNRESOLVED + 사진 재촬영/품질 확인 요청 | 불충분한 입력을 보존 |
| 작동 불량 | UNRESOLVED + 비시각적 증거 요청 | 정지 사진으로 작동을 증명하지 않음 |
| 누수·오염·부품 누락·오배송 등 | UNRESOLVED + 기준 자료/설명 요청 | 현재 입력에 없는 구성품·제품 확인·인과관계를 발명하지 않음 |
| 일부 이미지 분석 실패 | 성공한 이미지 후보 + 누락 ID와 사유 | 성공 근거를 잃거나 실패를 숨기지 않음 |
| 고객사/실행/스냅샷/SHA 불일치, 중복, 한 stage의 모델 혼합 | 전체 입력 거부 | 다른 근거를 합쳐 결과를 만들지 않음 |

첫 버전의 유형 후보 연결 대상은 DENT, CRACK, BREAKAGE, PACKAGING_DAMAGE 네 개다.
더 넓은 canonical label을 임의로 같은 뜻으로 합치지 않는다. 구조상 bbox는 원본 Vision result에
있고 결과는 result/detection ID로 참조한다. bbox를 제품 부품 위치로 변환하는 모델은 아직 없다.

`detection_min_score`는 입력 profile에 명시해야 한다. 합성 평가의 0.8은 테스트 값이며 E3의 운영
threshold를 바꾸지 않는다. 모든 보고서는 advisory_only=true, human_review_required=true,
policy_eligible=false, model_quality_qualified=false다. 어떤 조건에서도 최종 결정 필드가 없다.

## 2. 실행과 산출물

저장소 루트에서 기존 가상환경을 사용한다. output directory는 매번 새 이름이어야 하고 부모만
미리 존재해야 한다. 기존 디렉터리/파일을 덮어쓰지 않는다.

```sh
.venv/bin/python -m scripts.evaluate_engine_alignment evaluate \
  --output-dir local-data/alignment-contract-new-run

.venv/bin/python -m scripts.evaluate_engine_alignment replay \
  --input /absolute/path/approved-canonical-bundle.json \
  --output-dir local-data/alignment-replay-new-run
```

- 입력 계약: `app/domains/product_defect_cs/evidence_alignment.py`의 `AlignmentInput`.
- 합성 입력 예제 구성: `scripts/engine_alignment_fixtures.py`의 `make_input`.
- 평가 자료: `evaluation/engine_alignment_v1/dev_contract.jsonl`.
- 출력: 새 directory 0700, `result.json` 0600. 정상 stdout은 요약 JSON 한 건이다.
- 입력은 2 MiB, 이미지 20개, claim 50개, 이미지당 detection 100개로 제한한다.
- 실제 입력은 승인된 내부 canonical 결과만 사용한다. 이 도구는 DB 인증을 대신하지 않으며,
  operator 입력의 SHA 선언을 실제 checkpoint 검증이나 release 서명으로 취급하지 않는다.
- 요청/claim 원문은 메모리에서 exact quote 검사에만 사용한다. 보고서는 원문·요약·URL·API key·
  provider request ID를 포함하지 않고 opaque 참조, hash와 allowlisted version만 남긴다.
- DB/API/Event 변경이 없어 migration은 추가하지 않았다. 도구 rollback은 사용을 중단하는 것으로 충분하다.

최종 실행 증거는 `local-data/engine-alignment-evaluation-20260909-final/result.json`에 있다.
초기 보고서 `local-data/engine-alignment-evaluation-20260909T115036/result.json`도 보존했다.
30/30과 replay 일치는 **가상의 canonical 출력에 대한 계약 검사**다. 실제 Vision, LLM 또는
결합 모델 정확도나 baseline 대비 개선률로 인용해서는 안 된다. 기존 sealed Test를 열지 않았다.

## 3. 다음 모델 개선 실험의 순서

### A. 공통 평가 데이터와 오류 기준선

첫 상품군과 2~3개 결함을 정한 뒤, 비식별 문의·사진·정책 버전·사람 정답을 묶는다.
사진에는 정상, 실제 결함, 촬영불량, 미지원 상품, 판단불가를 모두 포함한다.
사람 정답은 모델 예측을 보기 전에 작성하고 이견을 조정한다. 데이터 사용권과 provenance도 기록한다.
현재 synthetic contract fixture나 E3가 이미 맞힌 selected-positive를 실제 성능 정답으로 대체하지 않는다.

동일 상품·촬영 세션·주문·원본/증강 이미지가 split을 넘지 않도록 그룹으로 분할한다.
개발 중 볼 수 있는 Dev와 마지막 Test를 분리한다. 모델/양자화/runtime/prompt/schema/threshold
버전과 input hashes를 평가마다 고정한다. GX10은 전용 runtime identity 계약이 먼저 필요하다.

### B. 작은 비교 실험으로 개선 대상을 선택

| 축 | 고정할 것 | 바꿀 것 | 판단 근거 |
|---|---|---|---|
| Vision | 동일 Dev와 source labels | 품질 필터, crop/reference, localization 후보 중 한 가지 | 오탐/미탐, 위치 정답, 판단 보류율, 입력 품질별 오류 |
| LLM/RAG | 동일 corpus/index/Dev/model | query 생성 또는 예외 검색 또는 설명 prompt 중 한 가지 | 검색 recall/coverage, 정확 인용, 미해결 조건, 주입 안전성 |
| 결합 | 동일 text/vision 예측과 사람 정답 | text-only, vision-only, alignment 조합 | 근거 없는 지지/반박, 판단 보류율, 상담원 수정량 |
| 정밀도/학습 | 동일 평가·prompt·입력 조건 | 검증 가능한 정밀도 또는 한 가지 추가학습 설정 | 품질 차이와 memory/latency; 향상을 사전 가정하지 않음 |

모든 경우 실패한 task를 평균으로 상쇄하지 않는다. LLM Query Builder는 기존 RAW→HYBRID보다
검색 지표가 나빠지면 기본 경로로 채택하지 않는다. 이번 구현이 그 품질 문제를 해결했다고 주장하지 않는다.
기존 paired VLM 결함 실험의 실패를 보존하고, 새 reference/crop 실험은 별도 증거로 평가한다.

### C. 근거가 생긴 뒤 학습·통합

- 반복적 시각 오류: 정상 기준 이미지 비교, 위치/분할 데이터, 해당 상품군 도메인 적응 검토.
- 검색 실패: chunk/예외 연결/metadata/query를 개선. 지식 누락을 LLM 추가학습으로 대체하지 않음.
- 검색 성공 후 오해: 검수된 reasoning-free 구조화 예시로 prompt 또는 소규모 추가학습 검토.
- Calibration은 별도 검증 자료에서 점수와 실제 정답률을 확인하며 모델 자가 확신은 정답 확률이 아님.
- 통합 시 새 append-only alignment result, tenant/Case 권한, 삭제·보존, UI의 근거 링크, review packet
  고정과 fail-closed policy qualification을 구현한다. 기존 packet/결정을 덮어쓰지 않는다.

첫 고객 자료·독립 정답이 아직 없으므로 실제 품질 향상과 학습은 후속 Gate다. 설치·모델 전송·
서비스 교체·PRIMARY 전환은 이 도구에 없으며 4090/GX10 기존 서비스와 미커밋 변경을 보존했다.

## 최종 검증 기록

- 기본 backend 회귀: 1,335 passed, 94 deselected. 외부 GPU/DB integration은 제외했다.
- 최종 출처 schema metadata 보강 후 집중 재검증: 129 passed.
- 전체 `app/scripts/tests` Ruff PASS, 신규 파일 format PASS, 전체 Pyright 0 errors.
- CLI 합성 평가: 30/30, replay 일치. 최종 report SHA-256:
  `bb198b684ba82032d42eef7fcdd4c90434dd7607bc5510a63e002db81f254ca3`.
- 보고서 directory/file 권한 0700/0600, 기존 결과 overwrite 거부와 민감 입력 오류 비출력 검증.
- `git diff --check` PASS. 기존 legacy Vision 필드 deprecation warning은 별도 기존 항목이다.
- 실제 모델 추론, 실제 이미지 정답 평가, DB migration, Web 변경/배포, Commit·Push·PR: NOT_RUN.
