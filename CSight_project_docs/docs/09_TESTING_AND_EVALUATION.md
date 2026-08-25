# 09. Testing and Evaluation

## 1. 검증 단계

```text
Offline Evaluation
→ Shadow Mode
→ Limited PoC
→ High-confidence Automation 검토
```

### Offline Evaluation

- 고정 Test Case로 LLM, Vision, Alignment, Policy 평가
- 실제 업무 처리에 영향 없음

### Shadow Mode

- 상담원 기존 판단과 동시에 시스템 실행
- 시스템 결과는 실제 결정에 반영하지 않음
- 오버라이드와 오류 유형 비교

### Limited PoC

- 선택된 상품군과 결함 유형
- 상담원에게 근거와 처리 권고 제공
- 최종 결정은 상담원이 수행

## 2. 테스트 계층

### Unit Test

- Case 입력 검증, `RECEIVED` 초기 상태와 최초 이력
- Requested Action, Role Permission, Object Key 불변조건
- Canonical Request Hash와 Idempotency 재생·충돌
- JWT/Password Adapter와 현재 역할 재조회
- 독립 Hashing Port의 한 번의 제한된 Streaming Read, 크기·SHA-256과 Stream Rewind
- File Inspector의 이미지 Decode, MIME·확장자, 폭·높이·Pixel 검증
- Evidence `PENDING` → `AVAILABLE` 및 실패 보상
- Policy 조건
- Alignment 계산
- Workflow 상태 전환
- Domain Validation
- 버전 선택 로직

### Integration Test

- PostgreSQL Repository
- Alembic Migration
- MinIO Upload / Signed URL
- Tenant별 Case·Evidence·Identity 격리
- Case 목록 필터·페이지·안정 정렬
- Idempotency Unique Claim의 동시 요청
- Development Seed 반복 실행
- RabbitMQ와 Celery
- pgvector 검색

### Contract Test

- 인증·Case·Evidence HTTP Schema와 오류 Envelope
- Case 생성 Body의 `tenant_id` 거부
- Case 생성 `201`과 Idempotency 재생 `200`
- LLM Schema
- Vision Schema
- Event Schema
- API Response
- 모델 버전과 좌표 체계

### E2E Test

- Seed → 로그인 → Case 생성 → 이미지 업로드 → 목록·상세 → Signed URL → Object GET
- Tenant A의 Case를 Tenant B가 요청할 때 `404`
- Case 접수부터 Review 확정까지
- 추가 자료 요청 후 재접수
- 부분 실패와 재시도
- 정책 버전 변경 후 재분석

### Security Test

- Tenant 간 데이터 접근 차단
- 만료된 URL
- 만료·변조 JWT, 비활성 사용자, 현재 역할 회수
- `QUALITY_VIEWER`의 Case 생성·Evidence 업로드 차단
- 빈 파일, 과대 파일, 위장 이미지, Path Traversal 형태 원본 파일명
- 권한 없는 Review
- 위험 파일 업로드
- Prompt Injection 입력

## 3. 핵심 E2E 사례

1. 로컬 Seed → Reviewer 로그인 → `RECEIVED` Case와 최초 이력 생성
2. 유효 이미지 → Private MinIO Object와 `AVAILABLE` Evidence → Signed URL Object GET
3. 동일 Case Idempotency Key·Body → 기존 Case 재생, 중복 미생성
4. 동일 Key·다른 Body → `409 IDEMPOTENCY_KEY_REUSED`
5. Tenant A Case를 Tenant B가 조회 → `404`
6. QualityViewer 생성·업로드 → `403`, 조회 → 성공
7. 위장 이미지·빈 파일·과대 파일·과대 Pixel → 정의된 오류로 차단
8. Storage/DB 실패 → 성공 응답 없이 보상 경로 실행
9. 명확한 누액 → 승인 후보 → 상담원 승인 (Sprint 4 목표)
10. 흐린 이미지 → 추가 자료 요청 (Sprint 3~4 목표)
11. Vision Timeout → Partial Failure (Sprint 3 목표)
12. 모델 버전 변경 → 기존 결과 유지, 새 Run 추가 (Sprint 2 이후 목표)

## 4. 기술 지표와 업무 지표

### 기술 지표

- Vision Precision / Recall / mAP
- Calibration
- LLM 구조화 성공률
- 필드별 Extraction 정확도
- 평균 분석 Latency
- Timeout과 실패율

### 업무 지표

- 건당 평균 검토시간
- 상담원 1인당 처리건수
- 처리 경로 추천 정확도
- 고신뢰 권고 Override율
- 위험 라우팅 오류율
- 최초 응답시간
- 재문의·재검토율
- 건당 처리비용

## 5. PoC 핵심 KPI

### 1순위

1. 평균 검토시간
2. 고신뢰 권고 Override율
3. 위험 라우팅 오류율

### 2순위

- 추가 자료 요청 적절성
- 재검토율
- 문서 작성시간
- 반복 불량 탐지 활용도

정확한 목표값은 Baseline 측정과 기업 인터뷰 후 확정한다.

## 6. 안전성 Gate 예시

다음 값은 멘토와 협력 기업의 검증 후 숫자를 확정한다.

- 위험 오류가 허용 범위를 넘으면 자동 승인 후보 기능 비활성화
- Vision 품질이 최소 기준 미만이면 판정 중단
- Policy Version이 없으면 Human Review로 이동
- 모델 결과 Schema가 유효하지 않으면 Decision 생성 금지
- 고위험 Flag가 하나라도 존재하면 자동 처리 금지

## 7. ROI 측정

```text
월간 불량 문의 수
= 월간 전체 문의 수 × 불량 문의 비율

월간 시간 절감 가치
= 불량 문의 수 × 건당 절감시간 × 상담원 분당 인건비

월간 총 가치
= 시간 절감
+ 재검토 비용 감소
+ 오승인·오거절 비용 감소
- 시스템 운영비
```

필요 Baseline:

- 월간 문의량
- 이미지 첨부 문의 비율
- 평균 검토시간
- 재검토율
- 오승인·오거절 비용
- 상담원 인건비
- 현재 문서 작성시간

## 8. 품질 Gate

Pull Request 완료 전:

- Unit / Integration / Contract Test 통과
- Ruff와 Type Check 통과
- Migration 검증
- API Schema Diff 검토
- 개인정보 로그 노출 검사
- 주요 E2E Scenario 회귀 없음
