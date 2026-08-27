# 시나리오 기술 PoC Acceptance Runner

## 목적

`scripts/verify_scenario_poc.py`는 경질 플라스틱 합성 시나리오 팩이 오늘의 오프라인 기술
데모에 필요한 최소 조건을 만족하는지 fail-closed 방식으로 검사한다. 기존
`scripts/verify_poc_readiness.py`의 Limited PoC 승격 판정은 변경하거나 대체하지 않는다.

두 판정은 독립적이다.

- `OFFLINE_SCENARIO_PACK_READY`: 합성 Case·Gold·정책·다섯 안전 시나리오와 보고서 기반
  모델 명세가 봉인되어 재현 가능한 상태
- `RUNTIME_VISION_INTEGRATION_READY`: 실제 checkpoint identity와 private Vision endpoint를
  별도 live probe가 검증했을 때만 사용할 수 있는 예약 상태

따라서 endpoint와 checkpoint가 없어도 오프라인 팩이 완전하면 최상위 verdict는
`SCENARIO_TECH_POC_READY`일 수 있다. 이때 runtime 상태는 별도로
`RUNTIME_VISION_INTEGRATION_BLOCKED`이며 실제 Vision 연결 성공을 의미하지 않는다.
이 Runner 자체는 네트워크를 사용하지 않으므로 manifest의 `AVAILABLE`/`READY` 선언만으로
runtime을 승격하지 않고 항상 `VISION_RUNTIME_PROBE_NOT_EXECUTED`를 남긴다.

## 검사 범위

Runner는 `evaluation/scenario_poc_hard_plastic_v1`에서 다음을 검사한다.

1. `manifest.json`과 다섯 필수 산출물의 존재
2. 각 산출물 raw SHA-256과 canonical `pack_hash`
3. 합성 출처 표시, 최소 30개 Case, 고유 ID, 선언된 split 합계
4. Case마다 하나씩 존재하는 구조화 Gold와 모든 안전 결과 필드
5. 정책 문서 version·효력일과 Clause 존재
6. 아래 다섯 경계의 정확한 ID, Case 연결, 기대 assertion
   - 완전한 가시 파손 → Human Decision → DRY-RUN validated
   - 환불 금액·통화 누락 → 입력 보류, Attempt/Result 0
   - 정지 이미지로 기능 이상 미확인 → 추가 증거 요청
   - Safety Case → Reviewer 차단, Admin Resolve
   - Vision timeout → Partial Success·Human Review, 자동 Action 0
7. E1~E3 보고서에 근거한 이진 any-defect 모델 명세와 안전한 해석
8. 실제 endpoint/checkpoint package의 별도 가용 상태

## 실행

```bash
make verify-scenario-poc
```

이 Make Gate는 먼저 팩의 상세 fail-closed validator를 실행한 뒤 Acceptance Runner를 실행한다.

검증 결과는 터미널에 JSON으로 출력되고 기본적으로 다음 위치에도 저장된다.

```text
evaluation/scenario_poc_hard_plastic_v1/results/acceptance_report.json
```

기존 보고서의 schema와 자체 hash를 다시 검증하려면 다음을 실행한다.

```bash
uv run python scripts/verify_scenario_poc.py \
  --verify-report evaluation/scenario_poc_hard_plastic_v1/results/acceptance_report.json
```

실제 Vision runtime까지 필수 조건으로 걸려면 아래 명령을 사용한다. 현재 Runner에는 live probe가
없으므로 manifest가 endpoint/checkpoint를 선언하더라도 의도대로 종료 코드 1을 반환한다. 실제
runtime 승격은 별도 external contract smoke의 검증 증거를 Acceptance에 연결한 뒤에만 가능하다.

```bash
uv run python scripts/verify_scenario_poc.py --require-runtime-vision
```

## 보고 한계

허용되는 표현은 `합성 시나리오 기반 기술 PoC`뿐이다. 이 결과를 Limited PoC, 실제 고객
성능, 실제 기업 정책 검증, 자동 정상 판정, 비용 절감 또는 ROI의 증거로 사용하지 않는다.
Threshold 미만 결과도 `정상`이 아니라 `고신뢰 결함 후보 기준 미만`으로 해석한다.
