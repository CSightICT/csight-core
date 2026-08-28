# 실사용형 내부 데모 시드 v1

이 팩은 상담원 콘솔에서 Case 접수 → 비공개 이미지 Evidence → 실제 E3 비동기 분석이
어떻게 보이는지 시연하기 위한 고정 10건 입력이다. 고객 문의·주문번호·상품명은 모두
가상이며, 이미지만 사용자가 전달한 내부 평가 자료를 원본 폴더에서 읽는다.

## 구성과 해석

- 결함 6건: Kaputt Top-100의 `selected-correct positive-only` 중 육안 검토된 경질
  플라스틱 rank `003, 032, 054, 058, 078, 080`
- 정상 참고 4건: 사용자가 정상이라고 전달한 폴더 중 육안 검토 및 E3 저점수 allowlist의
  rank `002, 008, 017, 023`
- 비율: 상담 문의 큐가 결함 사례에 치우친 상황을 보여주는 고정 `6:4`

이 비율과 표본은 성능평가용 무작위 표본이 아니다. 결함 이미지는 이미 모델이 맞힌 사례만
골라진 selection bias가 있고, 정상 참고 이미지는 독립 라벨 원장과 재사용 권리가 제공되지
않았다. 따라서 accuracy, recall, specificity, FPR, calibration, 상품군 qualification 또는
ROI를 주장할 수 없다.

`BELOW_HIGH_CONFIDENCE_THRESHOLD`는 정상 확인이 아니다. 모델은 이미지 수준의 결함 가능성
점수만 제공하고 결함 유형·위치·bbox를 만들지 않는다. 이번 시드는 Vision 결과를 정책 입력에
연결하지 않으며(`NOT_LINKED_TO_POLICY_INPUT`), Decision·Resolution·External Action도 만들지
않는다. 최종 업무 결정은 인증된 사람만 수행한다.

## 보안 경계

- JPEG 원본과 thumbnail을 Git 또는 Web 정적 디렉터리에 복사하지 않는다.
- 원본은 기존 Private Evidence API를 통해 MinIO에 저장한다.
- 짧은 JWT는 로컬 DB의 활성 `ADMIN` 주체와 로컬 설정으로 메모리에서만 발급한다. 평문
  비밀번호나 토큰은 입력·출력·보고서에 저장하지 않는다.
- API, E3, DB가 loopback이 아니거나 환경이 `local`/`test`가 아니면 실행을 거부한다.
- 결과 원장은 Git에서 제외된 `local-data/realistic-internal-demo-v1/`에 쓴다.

Case의 출처 표시는 `attributes.realistic_demo` 한 곳에만 저장한다. UI가 사용하는 고정
필드는 `schema_version=1.0`,
`scenario_scope=INTERNAL_CURATED_6_DEFECT_4_BELOW_THRESHOLD`, `source_grade`,
`selection_bias`, `rights_status=INTERNAL_RESTRICTED_PROVENANCE_UNVERIFIED`,
`policy_input_linkage=NOT_LINKED_TO_POLICY_INPUT`이다. 결함 source grade는
`KAPUTT_SELECTED_CORRECT_POSITIVE`, 정상 참고 source grade는
`USER_SUPPLIED_NORMAL_REFERENCE`로 구분한다.

## 실행

실제 E3와 E3에 연결된 Core 7개 서비스를 먼저 준비한 뒤, 전달 폴더를 명시한다.

```bash
make seed-realistic-poc-demo \
  REALISTIC_DEMO_TOP100_SOURCE=/absolute/path/to/top100_e3_correct_test_images_2026-08-28 \
  REALISTIC_DEMO_NORMAL_SOURCE=/absolute/path/to/normal_images
```

기본 대상은 `csight` Tenant와 `csight@csight.demo` 활성 관리자다. 같은 명령을 다시 실행하면
고정 Idempotency Key와 Evidence SHA를 사용해 같은 10개 Case·Evidence·Analysis Run을
재사용한다. 메타데이터만 신뢰하지 않고 인증된 same-origin content API로 각 Private Evidence를
다시 읽어 원본 크기와 SHA-256까지 확인한다. 기존 전용 Case의 Policy/Review/Decision/Action
상태는 변경하지 않고 실행 전후 count가 같은지 확인해 원장에 남긴다. 새로 생성한 Case에 이런
row가 이미 있거나 실행 중 count가 달라지면 귀속을 증명할 수 없으므로 fail-closed한다. 전용
Case의 Evidence가 여러 개이거나 고정 SHA와 다른 경우에도 원본 정체성이 깨졌으므로 중단한다.
