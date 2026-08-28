# `csight` 가상 Commerce 정책 Runtime v2 준비

이 경로는 이미 존재하는 `csight` 로그인으로 상담 흐름을 시연하기 위한 local/test 전용 절차다.
기존 `csight-demo-brand` 파생 v1을 immutable history로 보존하면서, 완전한 가상 조직
`CSight Commerce`의 사내 운영규정 v2를 추가하고 활성화한다.

> 모든 문서와 rule은 `SYNTHETIC_REFERENCE`·`FICTIONAL_DEMO_ONLY`이다. 실제 기업의 정책,
> 약관, 운영 관행 또는 법률 자문을 복제하거나 주장하지 않으며 고객 PoC qualification도
> 의미하지 않는다.

## v2 범위

가상 운영규정 8개 문서·52개 조항은 다음 상담 경로를 다룬다.

- 반품·교환·환불, 수리, 재배송, 정보 안내
- 배송손상, 개봉 후 초기불량, 기능 이상, 오배송·구성품 누락
- 누액·오염·안전 우선 처리
- 주문·상품 참조와 이미지 등 증거 요건
- 7일·14일·30일 검토 구간과 기간 예외
- 100000원 초과 관리자 검토, 금액·통화·수량·배송지의 명시적 입력
- 무하자 단순변심의 미사용·구성품·포장상태 및 반품비 부담 검토 후보
- 취소 상태·입고·검수·금액·통화를 구분한 환불 시점 정보 안내
- 복수 주장, 근거 충돌, 비정규 모델 qualification과 관리자 이관

기간과 금액은 가상 데모의 검토 임계값일 뿐 승인·거절·보상 기준이 아니다. 시스템은 비용,
통화, 완료일 또는 외부 실행 파라미터를 추론하지 않는다.

typed rule set `product_defect_policy/2.0.1`은 25개 rule로 위 조항을 참조한다. 닫힌 field,
operator, effect registry만 사용하고 모든 rule은 `prohibit_final_decision=true`이며 사람 또는
관리자 검토 효과를 포함한다. 정책 효과는 advisory 신호이고 최종 업무 결정은 인증된 Human
Review에서만 생성된다.

## 준비 동작

단일 명령은 다음을 순서대로 수행한다.

1. `local`/`test`, loopback PostgreSQL·embedding origin, 기존 `csight` tenant와 활성 사용자를
   확인한다. tenant와 사용자는 만들지 않는다.
2. 기존 v1 문서 12개·84개 조항과 rule 12개를 같은 identity·hash로 다시 검증한다.
3. `data/csight_commerce_policy_v2/raw/csight/`의 v2 문서와 rule blueprint를 읽고 원문
   SHA-256, clause content hash, 전체 corpus hash, typed rule source reference를 재계산한다.
4. v1+v2 전체 스냅샷을 `local-data/`에 원자적으로 materialize하고 byte-identical replay만
   허용한다.
5. 새 문서·조항과 embedding만 추가하고 `csight_policy_reference/2.0.0` index를 활성화한다.
   기존 `1.0.0` index row는 삭제하거나 내용을 바꾸지 않고 RETIRED history로 남긴다.
6. `product_defect_policy/1.0.0` row·rule·source link를 보존하고 canonical source/reference
   정렬 계약을 고정한 새 `2.0.1` activation을 추가한다. 기존 로컬 DB에 known-faulty
   noncanonical `2.0.0`이 있으면 immutable RETIRED history로 검증·보존하지만 clean 환경에는
   생성하지 않는다. 이전 activation history와 실패 evaluation run도 삭제하지 않는다.
7. 문서·조항·embedding·index·rule·source link의 전체 semantic/hash를 다시 확인한다.

준비 후 기본 경로는 `RAW + HYBRID + Top-3` 검색, grounding, typed policy evaluation과 Human
Review다. v1과 v2가 모두 DB에 남지만 ACTIVE index와 ACTIVE rule-set은 각각 v2 하나뿐이다.

## 실행

Core DB와 고정 Qwen embedding 서비스가 준비돼 있어야 한다.

```bash
make start-embedding
make health-embedding
make prepare-csight-policy-runtime
```

기본 파생 위치는 `local-data/csight-synthetic-policy-runtime-v2.0.1`이며 Git과 Docker build
context에서 제외된다. 다른 위치가 필요하면 반드시 `local-data/` 아래 경로만 지정한다.

```bash
make prepare-csight-policy-runtime \
  CSIGHT_POLICY_OUTPUT=local-data/my-csight-policy-runtime-v2.0.1
```

완료 출력의 `scope=SYNTHETIC_REFERENCE_FICTIONAL_DEMO_ONLY`가 경계 표식이다. 같은 입력으로
재실행하면 byte-identical bundle, immutable DB rows, embedding과 ACTIVE v2 activation을 재사용한다.

## Fail-closed 조건

다음 조건에서는 준비를 중단한다.

- 실행 환경 또는 DB·embedding origin이 local 계약을 벗어남
- `csight` tenant 또는 활성 사용자가 없음
- 파생 출력이 `local-data/` 밖이거나 기존 출력과 byte 단위로 다름
- 원본, 문서 또는 rule이 `SYNTHETIC_REFERENCE`가 아님
- v2 원문 disclaimer가 없거나 문서·조항·rule 수가 잠긴 값과 다름
- source hash, parent relation, typed rule source reference 또는 human-only boundary가 다름
- 기존 v1 document/clause/rule semantics가 바뀌었거나 알 수 없는 정책 identity가 존재함
- v1·v2 index activation이 허용된 전환 상태가 아님
- 2.0.1 외 rule set이 ACTIVE이거나 known-faulty 2.0.0이 frozen hash와 다름

이 절차는 기존 `csight` 사용자·Case·Evidence·Review·Decision·Action을 변경하지 않는다. v1의
immutable content도 덮어쓰거나 삭제하지 않는다. v2 활성화를 위해 versioned index와 rule-set의
activation 상태만 명시적으로 전환한다.
