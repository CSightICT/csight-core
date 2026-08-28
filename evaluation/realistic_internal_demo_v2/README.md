# 이커머스 문의형 내부 데모 시드 v2

이 팩은 다중 판매자 온라인 마켓에서 접수되는 반품·교환·환불 문의처럼 보이는 고정 10건을
상담원 콘솔에 추가한다. 실제 회사·고객·주문·상품·정책과 관련 없는 한국어 합성
시나리오이며, UI 표시명은 **문의 내용**이다. Backend 계약의 필드명 `customer_message`는
하위 호환을 위해 바꾸지 않는다.

v1 Case나 원장을 수정하지 않는다. v2는 별도 `dataset_id`, `demo_id`, 주문번호,
Idempotency Key namespace와 결과 경로를 사용한다. 현재 문의 revision은 사진을 다시 대조한
`VISUAL_ALIGNED_R1`이며, 같은 revision 재실행만 기존 Case·Evidence·Analysis Run을 재사용한다.
이전 v2 초안은 append-only DB에 남더라도 상담원 목록에서는 최신 revision만 표시한다.

## 문의 구성

모든 문의는 4문장으로 작성했다. 주문·배송과 개봉 경위, 사용 여부 또는 고객이 해 본 확인,
문제가 된 이유, 원하는 처리를 자연스럽게 포함한다.

| 구분 | 문의 맥락 | 명시 요청 |
|---|---|---|
| 결함 후보 01 | 스프레이형 용기와 분리된 검은 보호캡 | 동일 상품 교환 |
| 결함 후보 02 | 덮개가 열린 플립탑 용기, 누수는 고객 진술 | 반품 후 환불 |
| 결함 후보 03 | 스프레이형 용기 캡 이탈·분사 이상 고객 진술 | 부품 수리·교체 |
| 결함 후보 04 | 소형 펌프형 용기와 분리된 투명 보호캡 | 동일 상품 재배송 |
| 결함 후보 05 | 스프레이 사용 중 액체가 튀었다는 안전 문의 | 하자 반품 |
| 결함 후보 06 | 노즐형 용기와 분리된 부품, 설명서 부재 | 조립·누락 정보 요청 |
| 임계값 미만 참고 01 | 포장된 소형 상품의 옵션 불일치 고객 진술 | 옵션 교환 |
| 임계값 미만 참고 02 | 포장된 원통형 상품의 단순 변심 | 미사용 반품 |
| 임계값 미만 참고 03 | 포장 물체 1개, 수량 누락 고객 진술 | 누락분 재배송 |
| 임계값 미만 참고 04 | 포장된 직사각형 상품의 색상 차이 고객 진술 | 단순 변심 환불 |

`requested_action` v1 계약에는 `RESHIPMENT` 값이 없으므로 재배송 두 건은 `OTHER`로 선언하고
문의 원문에 원하는 조치를 명시한다. 이는 LLM·정책·Action이 재배송을 자동 확정한다는 뜻이
아니다. 최종 업무 결정은 인증된 사람만 내린다.

## 이미지와 주장 경계

- 결함 후보 6건과 임계값 미만 참고 4건은 v1과 동일한 rank와 SHA-256을 사용한다.
- 결함 후보는 Kaputt `selected-correct positive-only` 표본이라 selection bias가 있다.
- 정상 참고는 사용자가 정상이라고 전달한 저점수 allowlist이며 독립 Gold가 아니다.
- `BELOW_HIGH_CONFIDENCE_THRESHOLD`는 정상 확인이 아니며 E3는 결함 유형·위치·bbox를 만들지
  않는다.
- Vision 결과는 정책 입력에 연결하지 않는다(`NOT_LINKED_TO_POLICY_INPUT`).
- `attributes.demo_image_observation`은 사진에서 직접 보이는 범위만 기록하고,
  `demo_claim_boundary=CUSTOMER_STATEMENT_ONLY_FOR_NON_VISIBLE_FACTS`는 배송·사용·누수·수량·
  옵션 같은 비가시 사실을 고객 진술로 분리한다.
- 실제 기업명, 기업 제휴·정책 사칭, 개인정보, 실주문번호를 포함하지 않는다.
- 원본 이미지는 Git/Web 정적 경로에 복사하지 않고 Private Evidence API로만 저장한다.
- Decision·Resolution·External Action은 이 시드가 만들지 않는다.

## 버전과 실행

고정 계약은 다음과 같다.

- Manifest schema: `2.0.0`
- Dataset: `realistic-internal-demo-v2`
- Narrative revision: `VISUAL_ALIGNED_R1`
- Provenance schema: `attributes.realistic_demo.schema_version=2.0`
- Scenario scope: `INTERNAL_CURATED_ECOMMERCE_INQUIRY_6_DEFECT_4_BELOW_THRESHOLD`
- 기본 결과 원장: `local-data/realistic-internal-demo-v2/seed_report.json`

실제 E3와 E3에 연결된 로컬 Core를 먼저 준비한 뒤 실행한다.

```bash
uv run python scripts/seed_realistic_poc_demo.py \
  --top100-source /absolute/path/to/top100_e3_correct_test_images_2026-08-28 \
  --normal-source /absolute/path/to/normal_images \
  --manifest evaluation/realistic_internal_demo_v2/manifest.json \
  --env-file .env
```

`--output`을 생략하면 v2 전용 기본 경로가 선택된다. v2 Manifest에 v1 기본 결과 경로를
지정하거나 그 반대로 지정하면 실행 전에 거부하여 기존 원장을 보호한다. 이 명령은
`local`/`test`, loopback PostgreSQL·Core·Vision, 활성 `csight` ADMIN 조건에서만 동작한다.
