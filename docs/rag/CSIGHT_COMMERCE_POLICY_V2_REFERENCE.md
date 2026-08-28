# CSight Commerce 운영규정 v2 Reference Map

> 이 문서는 CSight PoC용 완전 가상 정책의 탐색 지도다. 실제 기업 정책, 약관, 운영 관행이나
> 법률 자문이 아니다.

| 문서 | 주요 검토 범위 | 대표 조항 |
|---|---|---|
| `CSC-OPS-RET-001/2.0.0` | 반품·교환·환불, 개봉 초기불량, 정보 안내, 단순변심, 환불 시점 | C1~C8 |
| `CSC-OPS-FUL-002/2.0.0` | 배송손상, 오배송, 누락, 재배송 입력 | C1~C6 |
| `CSC-OPS-REP-003/2.0.0` | 기능 이상, 수리·교환 후보, 안전한 증거 | C1~C6 |
| `CSC-OPS-SAF-004/2.0.0` | 누액·오염, 사용 중지, 안전 관리자 이관 | C1~C6 |
| `CSC-OPS-EVD-005/2.0.0` | 주문·상품 참조, 이미지, 무결성, 입력 비추론 | C1~C6 |
| `CSC-OPS-FIN-006/2.0.0` | 금액·통화, 고액, 반품비, 환불 단계 | C1~C8 |
| `CSC-OPS-SLA-007/2.0.0` | 7·14·30일 검토 구간과 예외 | C1~C6 |
| `CSC-OPS-GOV-008/2.0.0` | 사람 전용 최종 결정, 근거 hash, LIVE 차단 | C1~C6 |

## Scenario-to-reference routing

| 문의 유형 | 우선 검색어 | 기대 Reference |
|---|---|---|
| 무하자 단순변심 반품 | 단순변심, 미사용, 포장상태, 반품비 | RET C7, FIN C7, SLA C2 |
| 배송비·취소·환불 시점 문의 | 반품비 부담, 취소 가능 상태, 입고, 검수, 환불 시점 | FIN C7~C8, RET C8 |
| 파손·포장손상 | 배송손상, 외부 포장, 송장, 손상 부위 | FUL C1~C2 |
| 오배송·누락·재배송 | 상품 참조, 수량, 배송지, 재배송 | FUL C3, EVD C1·C3 |
| 개봉 후 초기불량 | 개봉, 초기불량, 시험 사용, 기능 이상 | RET C3, REP C1·C3 |
| 수리 문의 | 증상, 수리, 부품, 비용 | REP C1~C5, FIN C1·C3 |
| 누액·오염 | 사용 중지, 접촉 최소화, 안전 이관 | SAF C1~C6 |
| 이미지 부족 | 상품 전체, 결함 부위, 추가자료 | EVD C2, FUL C2 |
| 기간 초과 | 14일 초과, 30일 초과, 예외 | RET C4, SLA C4~C6 |
| 복합·상충 문의 | 복수 주장, 상충 증거, 관리자 | EVD C6, GOV C4·C6 |

typed rule source link는 materialize 시 해당 조항의 document ID, version, source SHA-256으로
고정된다. 검색 인용과 rule effect는 상담원 검토를 돕는 근거이며 승인·거절·환불·교환·재배송·
수리의 최종 결정이 아니다.

문서·조항·retrieval index 버전은 `2.0.0`, ACTIVE typed rule set과 각 rule 버전은 `2.0.1`이다.
초기 로컬 시연에서 생성된 noncanonical rule set `2.0.0`은 존재하는 경우에만 frozen hash로
검증한 뒤 RETIRED 감사 이력으로 보존하며, clean 환경에서는 생성하지 않는다.
