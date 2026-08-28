# 이커머스 문의형 내부 데모 시드 v2

이 팩은 다중 판매자 온라인 마켓에서 접수되는 반품·교환·환불 문의처럼 보이는 고정 10건을
상담원 콘솔에 추가한다. 실제 회사·고객·주문·상품·정책과 관련 없는 한국어 합성
시나리오이며, UI 표시명은 **문의 내용**이다. Backend 계약의 필드명 `customer_message`는
하위 호환을 위해 바꾸지 않는다.

v1 Case나 원장을 수정하지 않는다. v2는 별도 `dataset_id`, `demo_id`, 주문번호,
Idempotency Key namespace와 결과 경로를 사용한다. 현재 문의 revision은 사진을 다시 대조하고
합성 Commerce 스냅샷을 추가한 `COMMERCE_CONTEXT_R2_E3`이며, 같은 revision 재실행만 기존
Case·Evidence·Analysis Run을 재사용한다.
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

## 가상 상품·가격 시나리오

상담원 화면은 `product_ref`를 `web/src/demo/productScenarioCatalog.ts`의 표시 전용 가상
카탈로그와 연결한다. 상품명과 가격대는 사진에서 실제 SKU나 판매가를 식별한 결과가 아니라
내부 PoC를 실제 주문처럼 읽기 쉽게 만든 **합성 데모 설정**이다. 대표값도 외부 Action의
환불 금액으로 자동 복사하지 않는다.

| 사진 시나리오 | 가상 상품명 | 가상 SKU | 합성 가격대 |
|---|---|---|---:|
| 결함 후보 01 | 루미에어 미스트 에센스 120 | `CS-DEMO-SPR-001` | 19,000~29,000원 |
| 결함 후보 02 | 화이트랩 바디 로션 300 | `CS-DEMO-FLP-002` | 15,000~25,000원 |
| 결함 후보 03 | 바이올렛 리페어 에센스 100 | `CS-DEMO-SPR-003` | 21,000~35,000원 |
| 결함 후보 04 | 골드리프 펌프 세럼 50 | `CS-DEMO-PMP-004` | 24,000~42,000원 |
| 결함 후보 05 | 로즈핏 헤어 미스트 150 | `CS-DEMO-SPR-005` | 14,000~24,000원 |
| 결함 후보 06 | 듀얼캡 리필 디스펜서 400 | `CS-DEMO-NOZ-006` | 8,000~15,000원 |
| 임계값 미만 참고 01 | 모듈박스 미니 수납함 3단 | `CS-DEMO-PKG-007` | 16,000~25,000원 |
| 임계값 미만 참고 02 | 롱스택 원통 수납통 1L | `CS-DEMO-CYL-008` | 14,000~23,000원 |
| 임계값 미만 참고 03 | 멀티홈 욕실 정리세트 4P | `CS-DEMO-SET-009` | 18,000~32,000원 |
| 임계값 미만 참고 04 | 플랫케이스 오거나이저 2P | `CS-DEMO-REC-010` | 15,000~27,000원 |

목록 검색은 가상 상품명도 지원한다. Case 상세에는 가상 상품 배지, 상품군, 가격대,
문의 목적과 `실제 판매가/환불 금액 아님` 경계를 함께 표시한다. 카탈로그에 없는 일반 Case는
기존 주문번호·`product_ref` 표시를 그대로 유지하고 상품을 추정하지 않는다.

## 합성 고객·주문·배송 스냅샷

10건 각각은 Case JSONB의 `attributes.synthetic_commerce_context`에 서로 다른 가상 고객과 주문
스냅샷을 저장한다. 고객 ID·이름·멤버십, 마스킹 연락처, 판매 채널·판매자, 상품명·SKU·수량,
상품금액·배송비·할인·결제금액, 마스킹 결제수단, 수령인·가상 배송지·배송사·마스킹 운송장을
포함한다. 전화번호와 외부 시스템 식별자는 직접 연락하거나 조회할 수 없는 형태다.

두 REFUND Case의 명시적 환불 입력은 결제금액과 일치한다.

| 주문 | 고객 | 결제금액 | 명시적 환불액 |
|---|---|---:|---:|
| `DEMO-R2-ORD-20260828-002` | 김하늘 / `CUST-DEMO-100002` | 18,900원 | 18,900원 |
| `DEMO-R2-ORD-20260828-010` | 송아린 / `CUST-DEMO-100010` | 15,900원 | 15,900원 |

결제금액은 표시·대조용이며 Action 입력원이 아니다. 환불 Intent는 기존처럼 오직
`external_action_input.amount/currency`를 사용한다. 다른 주문 금액, 상품 가격대, 문의 내용으로
누락 값을 채우지 않는다. 이 경계는 ADR-0098에 고정한다.

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

## 닫힌 클래스와 채택 기준

이 v2 팩은 `evaluation/poc_closed_set_v1/registry.json`을 기본 채택 원장으로 사용한다. 상품군
4개와 결함군 3개를 고정하되 현재 10건에서 실제 표현되는 상품군은 뷰티·개인관리 용기와
주방·수납용 경질 플라스틱 2개뿐이다. 식품·건강보조제와 생활화학·접착제는 후속 승인 이미지가
들어오기 전까지 coverage로 주장하지 않는다.

결함 후보는 사람 승인 상품군, Kaputt 원천 라벨과 E3 점수 `0.95 이상`을 모두 요구한다.
저점수 참고는 사람이 참고 표본으로 승인하고 E3 `0.10 이하`일 때만 사용한다. 중간 점수는
선별 데모에서 제외하거나 담당자 검토로 보낸다. 이 점수 구간은 데이터 채택 기준이며 E3의
동결 운영 임계치 `0.8984375`를 변경하지 않는다. 자세한 계약은
`docs/data/POC_CLOSED_SET_V1.md`와 ADR-0100에 기록한다.

## 버전과 실행

고정 계약은 다음과 같다.

- Manifest schema: `2.0.0`
- Dataset: `realistic-internal-demo-v2`
- Narrative revision: `COMMERCE_CONTEXT_R2_E3`
- Commerce schema: `synthetic_commerce_context/1.0.0`
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

v2에서는 `--closed-set-registry`를 생략하면
`evaluation/poc_closed_set_v1/registry.json`을 사용한다. 다른 원장을 시험할 때만 명시적으로
경로를 넘기며, 원장과 source identity·라벨·SHA가 다르면 fail-closed 처리한다.

`--output`을 생략하면 v2 전용 기본 경로가 선택된다. v2 Manifest에 v1 기본 결과 경로를
지정하거나 그 반대로 지정하면 실행 전에 거부하여 기존 원장을 보호한다. 이 명령은
`local`/`test`, loopback PostgreSQL·Core·Vision, 활성 `csight` ADMIN 조건에서만 동작한다.
