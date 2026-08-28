# 이커머스 문의 확장 팩 v3

기존 `realistic-internal-demo-v2` 10건을 수정하지 않고 서로 다른 이미지와 주문으로 10건을
추가하는 내부 시연 팩이다. 두 팩을 합치면 **결함 후보 12건 + 사람 확인 저점수 참고 8건 =
20건**이다. 상품군은 뷰티·개인관리, 식품·건강보조제, 생활화학·접착제, 주방·수납의 4개를
모두 표현한다.

이 팩의 상품명·SKU·고객·주문·가격·배송·문의는 모두 합성이다. 사진은 Private Evidence에만
저장하며, 재배포 권리를 확인한 공개 데이터라는 뜻이 아니다. E3는 이미지 단위 any-defect
점수만 만들고 상품명·결함 종류·정책·업무 결정을 추론하지 않는다.

## 구성과 Gate

- Manifest: `realistic_internal_demo_v3/manifest.json`
- Dataset: `realistic-internal-demo-v3`
- Narrative revision: `CLOSED_SET_EXPANSION_R3`
- Closed-set registry: `evaluation/poc_closed_set_v2/registry.json`
- 결함 후보 6건: rank 1, 9, 22, 31, 73, 79, 실제 E3 점수 `>= 0.95`
- 저점수 참고 4건: rank 1, 20, 65, 67, 실제 E3 점수 `<= 0.10`
- 운영 E3 threshold: `0.8984375` 유지

저점수 참고는 정상 확정이 아니다. 점수 구간과 SHA Allowlist를 통과해도 최종 판단은 인증된
사람에게만 있으며, 이 시드는 Policy·Review·Decision·Resolution·Action을 만들지 않는다.

## 실행

```bash
uv run python scripts/seed_realistic_poc_demo.py \
  --top100-source /absolute/path/to/top100_e3_correct_test_images_2026-08-28 \
  --normal-source /absolute/path/to/normal_images \
  --manifest evaluation/realistic_internal_demo_v3/manifest.json \
  --env-file .env
```

Core API와 Worker는 동일한 E3 provider/model snapshot으로 실행해야 한다. 명령은 고정된 최대 두
번의 분석 재시도 키를 사용해 실패 이력은 보존하고, 성공 Run만 최종 원장에 채택한다. 같은 명령을
다시 실행하면 Case·Evidence·성공 Analysis Run을 재사용하고 Private Evidence SHA를 다시 검증한다.

결과는 Git에서 제외된 `local-data/realistic-internal-demo-v3/seed_report.json`에 저장한다.
