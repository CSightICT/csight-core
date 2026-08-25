# 02. Product Requirements

## 1. 요구사항 표기

- `P0`: MVP에 반드시 필요
- `P1`: PoC 품질 향상에 필요
- `P2`: 상용화 또는 확장 단계

## 2. 주요 사용자 시나리오

### 상담원

1. 자신의 Tenant로 로그인한다.
2. 상품 불량 문의 Case를 만들고 고객 원문, 주문정보, 이미지를 등록한다.
3. Case 목록·상세에서 원문, Evidence 메타데이터와 상태 이력을 확인한다.
4. 시스템이 추출한 결함 주장과 고객 요청을 확인한다.
5. 이미지 위 결함 후보와 신뢰도를 확인한다.
6. 적용 정책과 처리 권고를 확인한다.
7. 승인, 수정, 추가 자료 요청, 이관 중 하나를 선택한다.
8. 수정 이유를 기록하고 검토 문서를 저장한다.

### 관리자

1. 기업 정책과 Threshold를 버전별로 등록한다.
2. 사용자 권한과 고객사별 설정을 관리한다.
3. 처리시간, 오버라이드율, 실패율, 반복 불량을 조회한다.

### 품질 담당자

1. 상품·결함 유형별 Case를 조회한다.
2. 반복 결함과 증거 이미지를 확인한다.
3. 상담원이 확정한 결과를 품질 분석에 사용한다.

## 3. 기능 요구사항

### Case 및 Evidence

| ID | 우선순위 | 요구사항 | 인수조건 |
|---|---:|---|---|
| CASE-001 | P0 | Case 생성 | 텍스트, 주문 식별자, 고객 요청을 저장하고 Case ID 반환 |
| CASE-002 | P0 | 목록·상세 조회 | 필터·페이지 기반 목록과 Evidence·상태 이력이 포함된 상세 조회 가능 |
| CASE-003 | P0 | 상태 이력 | 모든 상태 전환의 시각, 주체, 사유 보존 |
| CASE-004 | P0 | 생성 Idempotency | Tenant별 동일 Key·동일 Body는 기존 Case를 재생하고 다른 Body는 충돌 처리 |
| EVID-001 | P0 | 이미지 업로드 | 원본은 Object Storage, 메타데이터는 DB에 저장 |
| EVID-002 | P0 | 파일 검증 | 실제 Decode, MIME, 확장자, 크기, Pixel 수, 해시를 검증 |
| EVID-003 | P0 | 제한된 이미지 접근 | Private Object를 짧은 만료시간의 Signed URL로만 조회 |
| EVID-004 | P1 | 개인정보 마스킹 | 테스트·PoC 정책에 따라 원문 또는 파생본 관리 |

### 인증과 Tenant

| ID | 우선순위 | 요구사항 | 인수조건 |
|---|---:|---|---|
| AUTH-001 | P0 | 로컬·PoC 로그인 | Tenant Slug, 이메일, 비밀번호로 만료되는 JWT Access Token 발급 |
| AUTH-002 | P0 | 역할 권한 | Admin·Reviewer는 생성/조회/업로드, QualityViewer는 조회만 가능 |
| AUTH-003 | P0 | Tenant 격리 | 요청 Body의 Tenant를 신뢰하지 않고 다른 Tenant 리소스는 404 처리 |
| AUTH-004 | P0 | 개발 Identity Seed | local/test에서만 명시적으로 Tenant 1개와 역할별 사용자 3명 생성 |

### AI 분석

| ID | 우선순위 | 요구사항 | 인수조건 |
|---|---:|---|---|
| AI-001 | P0 | LLM 문의 구조화 | 결함 주장, 위치, 요청사항, 누락정보를 Schema에 맞춰 반환 |
| AI-002 | P0 | Vision 분석 | 이미지 품질, 결함 유형, 위치, 신뢰도, 모델 버전 반환 |
| AI-003 | P0 | 정합성 분석 | 텍스트 주장과 Vision 결과의 유형·위치 일치도를 산출 |
| AI-004 | P0 | 비동기 실행 | API 요청과 분석 실행을 분리하고 202 응답 반환 |
| AI-005 | P0 | 부분 실패 관리 | LLM 또는 Vision 단일 실패를 구분해 저장 |
| AI-006 | P1 | 재분석 | 모델·프롬프트 버전을 지정해 새 Analysis Run 생성 |
| AI-007 | P1 | 재촬영 가이드 | 이미지 품질 부족 사유에 맞는 촬영 요청 생성 |

### 정책과 라우팅

| ID | 우선순위 | 요구사항 | 인수조건 |
|---|---:|---|---|
| POL-001 | P0 | 정책 버전 관리 | 적용 시작·종료일과 버전 보존 |
| POL-002 | P0 | 정형 규칙 평가 | 기간, 금액, 상품군, 결함, 위험 조건을 코드가 평가 |
| POL-003 | P1 | 비정형 정책 검색 | 정책 문서에서 관련 조항을 검색하고 근거 위치 반환 |
| ROUTE-001 | P0 | 처리 경로 추천 | 승인 후보, 검토, 추가 자료, 이관 중 하나 반환 |
| ROUTE-002 | P0 | 고위험 우선 이관 | 고액·안전사고·분쟁 조건은 자동 승인 후보 금지 |
| ROUTE-003 | P1 | Threshold 설정 | 고객사·상품군·결함별 Threshold 버전 관리 |

### Human Review

| ID | 우선순위 | 요구사항 | 인수조건 |
|---|---:|---|---|
| REV-001 | P0 | 승인·수정·이관 | 상담원이 권고 결과를 확정 또는 변경 가능 |
| REV-002 | P0 | 수정 이유 | 오버라이드 시 이유 코드 또는 메모 필수 |
| REV-003 | P0 | 원본 보존 | AI 권고와 최종 결정 모두 보존 |
| REV-004 | P1 | 재검토 | 상급자 검토 Workflow 지원 |

### 보고서와 감사

| ID | 우선순위 | 요구사항 | 인수조건 |
|---|---:|---|---|
| REP-001 | P0 | 검토 문서 생성 | 문의, 이미지 근거, 분석, 정책, 권고, 확정 이력 포함 |
| REP-002 | P1 | 문서 Export | HTML 또는 PDF Export 가능 |
| AUD-001 | P0 | 감사 로그 | 주요 조회·변경·결정 행위 기록 |
| AUD-002 | P0 | 버전 추적 | 결과에 모델·프롬프트·정책·Threshold 버전 연결 |

### 운영 분석

| ID | 우선순위 | 요구사항 | 인수조건 |
|---|---:|---|---|
| MET-001 | P0 | 처리시간 측정 | 접수·분석·검토·확정 시각 저장 |
| MET-002 | P0 | 오버라이드율 | AI 권고와 최종 판단 차이 집계 |
| MET-003 | P1 | 반복 불량 통계 | 상품·판매자·결함별 집계 |
| MET-004 | P1 | 모델 운영 지표 | Latency, 실패율, 보류율, Schema 오류율 집계 |

## 4. 비기능 요구사항

| ID | 영역 | 요구사항 |
|---|---|---|
| NFR-001 | 보안 | 외부에는 Web/API만 공개하고 DB·GPU API는 사설망으로 제한 |
| NFR-002 | 개인정보 | 원문·이미지 접근권한, 보관기간, 삭제 정책 지원 |
| NFR-003 | 감사 | 처리 결과 재현에 필요한 모든 버전과 입력 참조 보존 |
| NFR-004 | 복원력 | 외부 모델 Timeout, Retry, DLQ, Partial Failure 지원 |
| NFR-005 | 이식성 | Core와 모델 서버의 API 계약을 유지한 채 장비 이전 가능 |
| NFR-006 | 확장성 | Domain Module과 Provider Adapter 교체 가능 |
| NFR-007 | 관측성 | Case 단위 Trace 및 시스템·모델·업무 지표 제공 |
| NFR-008 | 유지보수 | Migration, Type Check, Test, ADR 기반 변경 관리 |
| NFR-009 | Tenant 격리 | 인증 Principal과 Repository 필터로 모든 업무 조회·쓰기 Scope 제한 |
| NFR-010 | 파일 일관성 | DB와 Object Storage 부분 실패를 상태와 최선 노력 보상으로 추적 |

## 5. MVP 인수 시나리오

### 시나리오 A: 명확한 결함

- 선명한 이미지와 누액 주장이 제출된다.
- LLM과 Vision 분석이 성공한다.
- 정책 조건이 충족된다.
- 시스템은 `APPROVAL_CANDIDATE`를 반환한다.
- 상담원이 승인하면 최종 결정과 보고서가 저장된다.

### 시나리오 B: 이미지 부족

- 결함 부위가 보이지 않는 이미지가 제출된다.
- Vision 품질 검사가 실패 사유를 반환한다.
- 시스템은 `ADDITIONAL_EVIDENCE_REQUIRED`로 라우팅한다.
- 구체적인 재촬영 가이드가 제공된다.

### 시나리오 C: 고위험 조건

- 고액 상품 또는 예외 정책 조건이 충족된다.
- 모델 신뢰도가 높더라도 자동 승인 후보를 생성하지 않는다.
- 상급자 또는 전문 담당자 이관 이력이 남는다.

### 시나리오 D: 모델 부분 실패

- Vision 서버가 Timeout되고 LLM은 성공한다.
- Case 데이터는 유실되지 않는다.
- `PARTIAL_SUCCESS` 또는 `HUMAN_REVIEW_REQUIRED`로 처리된다.
- 재시도 이력과 실패 원인이 기록된다.

## 6. Sprint 1 인수 시나리오

Sprint 1은 AI 분석을 시작하지 않는 Case/Evidence Vertical Slice다.

### 시나리오 E: 인증된 Case와 Evidence 접수

- Reviewer가 개발용 Tenant로 로그인한다.
- `tenant_id`가 없는 요청으로 Case를 생성한다.
- Case는 `RECEIVED`로 저장되고 `from_status = null`, `to_status = RECEIVED`,
  `reason = case_created`인 최초 이력이 함께 저장된다.
- JPEG, PNG 또는 WebP 원본을 업로드하면 Private MinIO Object와 PostgreSQL 메타데이터가
  생성되고 Evidence는 `AVAILABLE`이 된다.
- 목록에는 고객 문의 원문이나 Signed URL이 포함되지 않는다.
- 상세에서 Evidence 메타데이터와 상태 이력을 확인하고, 별도 API로 짧게 만료되는 접근
  URL을 발급한다.
- 이 흐름은 Analysis Run을 만들거나 LLM·Vision 작업을 Queue에 등록하지 않는다.

### 시나리오 F: Tenant와 역할 격리

- QualityViewer는 목록·상세 조회는 가능하지만 Case 생성과 Evidence 업로드는 `403`이다.
- Tenant A의 Token으로 Tenant B의 Case/Evidence를 조회하면 존재 여부를 노출하지 않고
  `404`를 반환한다.
- 동일 Tenant·Operation·Idempotency Key로 같은 Case 요청을 반복하면 기존 결과를
  `200`으로 재생하고, 다른 Body로 재사용하면 `409`를 반환한다.
