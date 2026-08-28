# CSight 경질 플라스틱 시나리오 PoC 팩 v1

이 디렉터리는 실제 기업·고객 자료를 쓰지 않고 **가상 브랜드와 합성 Case로 오늘 실행할
기술 데모**를 위한 고정 입력 팩이다. 상품은 반복 촬영과 안전한 부품 분리가 쉬운 경질
플라스틱 `HDP-100 수동 펌프형 디스펜서`로 한정한다.

## 사실과 가정의 경계

- Vision 근거는 Kaputt held-out test에 대한 두 내부 보고서다. E3 epoch 10 후보의 전체
  test AP/AUROC와 고정 threshold 결과를 `model_manifest.json`에 그대로 기록했다.
- Kaputt에는 사람이 읽을 수 있는 상품명/SKU가 없으므로 디스펜서는 **합성 시나리오용
  선택**이지 Kaputt에서 검증된 개별 상품이 아니다.
- E3는 `any defect` 이진 분류기다. 결함 유형, 위치, bbox, mask를 출력하지 않는다.
- `deconstruction`은 텍스트·사진 검토를 거쳐 CSight `BREAKAGE`로 다룰 수 있지만, 모델
  점수만으로 그 유형을 확정하지 않는다.
- `actuation`은 CSight `FUNCTIONAL_FAILURE` 텍스트 주장으로 취급한다. 정지 이미지로
  작동 여부를 확인할 수 없으면 추가 동영상/수동 펌프 시험 또는 사람 검토가 필요하다.
- 점수가 threshold 미만이라는 사실은 `정상`을 뜻하지 않는다.
- 모든 최종 결정은 사람만 내린다. 완전한 명시 입력이 있는 결정만 DRY-RUN Action을
  만들며 실제 환불·교환·수리·고객 알림은 수행하지 않는다.
- 이 팩으로 실제 환경 성능, 비용 절감, ROI를 주장할 수 없다.

## 파일

| 파일 | 역할 |
|---|---|
| `manifest.json` | 팩 범위, 출처, 레코드 수, 모든 핵심 파일 해시 |
| `brand_product.json` | 가상 브랜드·상품·촬영 상태 정의 |
| `model_manifest.json` | E3 offline 결과와 이진 모델 사용 경계 |
| `policy.json` | 버전·효력일을 가진 합성 정책 Clause와 Rule |
| `cases.jsonl` | 다양한 한국어 자연어 문의 36건 |
| `gold.jsonl` | Case별 기대 근거·정책·Human Review·Resolution 결과 |
| `demo_scenarios.json` | 오늘 시연할 5개 핵심 흐름 |
| `schemas/` | 핵심 Artifact JSON Schema |
| `validate.py` | 구조·참조·안전 경계·해시를 fail-closed 검증 |

## 검증

저장소 루트에서 다음을 실행한다.

```bash
.venv/bin/python evaluation/scenario_poc_hard_plastic_v1/validate.py
.venv/bin/pytest -q tests/unit/test_scenario_poc_hard_plastic_v1.py
```

검증기는 Case/Gold 1:1 대응, 30건 이상, 정확히 5개 Demo, Policy 출처 연결, 모델의 이진
출력 한계, 낮은 점수의 `NOT_NORMAL` 처리, 자동 승인 금지, Action 명시 입력, DRY-RUN의
무부작용, Artifact hash와 pack hash를 확인한다.

## 오늘 보여줄 대표 시나리오

| ID | 입력과 확인 지점 | 기대 종착점 |
|---|---|---|
| `DEMO-01` | 사진에서 사람이 확인한 펌프 분리 + 완전한 교환 입력 | Human Decision 후 `ACTION_DRY_RUN_VALIDATED`, 실제 부작용 0 |
| `DEMO-02` | 파손 환불 요청, 환불액·통화 미제출 | `ACTION_NEEDS_INPUT`, Intent·Attempt·Result 0 |
| `DEMO-03` | 펌프 공회전 텍스트 주장, 정지 이미지만 존재 | 작동 영상/수동 시험 요청, Decision·Action 0 |
| `DEMO-04` | 날카로운 파단면과 누출 위험 | Reviewer 차단, Admin만 Resolve, DRY-RUN만 수행 |
| `DEMO-05` | Vision Timeout + 텍스트 분석 성공 | `PARTIAL_SUCCESS`, Human Review, 자동 Decision·Action 0 |

## 실행 시 주의

`human_decision`은 시스템 권고가 아니라 시나리오의 **사람 결정 Gold**다. 이미지 경로는
합성 Fixture 참조이며 실제 사진이 포함되어 있다는 뜻이 아니다. 2026-08-28 별도 host-private
E3 endpoint와 synthetic connectivity image의 실제 forward는 통과했지만, 다섯 시나리오의
대표 이미지·Human Gold·제품 domain 평가는 아직 없다. 그러므로 각 Scenario의 Vision 단계는
대표 이미지 평가를 추가하기 전까지 fixture/advisory임을 화면에 표시해야 한다.
