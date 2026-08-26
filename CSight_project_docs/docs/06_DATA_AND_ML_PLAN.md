# 06. Data and ML Plan

## 1. 핵심 데이터 단위: Case Bundle

모델 학습과 서비스 평가의 기본 단위는 이미지 한 장이 아니라 다음 묶음이다.

```text
고객 문의 텍스트
+ 첨부 이미지
+ 상품·주문 정보
+ 적용 가능한 정책
+ 상담원의 최종 처리 결과
```

## 2. 필요한 데이터 필드

### 공통

- Case ID
- Tenant ID
- 상품군·상품 식별자
- 주문일·접수일
- 고객 문의 원문
- 고객 요청사항
- 이미지 참조
- 정책 버전
- 최종 처리 결과
- 상담원 수정 여부와 이유

### Vision 라벨

- 정상 / 결함 의심 / 결함 확인
- 결함 유형
- 결함 위치
- Bounding Box 또는 Mask
- 심각도
- 이미지 품질
- 상품·결함 부위 노출 여부

### LLM·Alignment 라벨

- 결함 주장
- 주장 위치
- 고객 요청
- 누락 정보
- 텍스트·이미지 유형 일치
- 텍스트·이미지 위치 일치
- Evidence Sufficiency

## 3. 데이터 확보 전략

### 단계 1: 프로토타입

- 공개 결함 이미지 데이터
- 팀 직접 촬영 데이터
- 통제된 방식의 결함 재현 이미지
- 공개 CS 텍스트 또는 자체 작성 사례
- 가상 주문정보와 정책

### 단계 2: 멘토링·기업 검증

- 비식별화된 과거 문의 샘플
- 문의 텍스트와 이미지의 실제 연결 여부 확인
- 최종 처리 결과와 수정 이유 확보 가능성 검증
- 상품별 정책 문서 형식 파악

### 단계 3: PoC

- 특정 상품군과 결함 2~3개
- 과거 Case Replay
- Shadow Mode
- Limited Recommendation

## 4. 데이터 분할

- 동일 상품 또는 동일 촬영 세션이 Train과 Test에 동시에 들어가지 않게 한다.
- 증강본은 원본과 같은 Split에 둔다.
- 동일 고객 문의의 여러 이미지는 하나의 Case로 함께 분할한다.
- 시간 기반 일반화가 중요하면 최신 기간을 Test로 둔다.
- 정책 버전이 다른 Case는 별도 분석이 가능하도록 메타데이터를 보존한다.

권장 Split 예시:

```text
Train 70%
Dev 15%
Test 15%
```

데이터 규모가 작을 경우 K-fold보다 Case 단위 고정 Test를 우선한다.

## 5. Vision 모델 범위

아래 Vision 범위와 산출물은 Sprint 3 이후 계획이다. Sprint 2는 Vision Provider를 실행하거나
Vision Result, Alignment를 저장하지 않는다.

### 담당 기능

- 이미지 품질 판정
- 상품 및 결함 부위 가시성
- 결함 Detection 또는 Segmentation
- 결함 유형과 신뢰도
- 필요 시 심각도 추정

### Vision 담당자의 산출물

```text
model.onnx 또는 model.plan
labels.json
preprocess.yaml
postprocess.yaml
thresholds.json
sample_inputs/
sample_outputs/
model_card.md
evaluation_report.md
```

### 필수 계약 정보

- 입력 크기
- RGB/BGR
- 정규화 방식
- Resize 또는 Letterbox
- Class 목록
- Class별 Threshold
- NMS 설정
- 좌표 체계
- 모델 버전
- 주요 실패 조건

## 6. LLM 범위

### Sprint 2 구현 범위

- Pipeline: `product_defect_text_extraction` `1.0.0`
- 실행 Stage: `TEXT_EXTRACTION`
- Prompt Manifest: `product_defect_text_extraction` `1.0.1` (Sprint 2.5 taxonomy·set guardrail)
- Input/Output Schema Version: `1.0`
- Provider: 결정적·Network-free Mock 또는 OpenAI-compatible vLLM Adapter
- 재시도·복구 상태: Celery Retry가 아니라 PostgreSQL Run/Stage/Attempt와 미래 Outbox Event
- 입력 Allowlist: `customer_message`, `order_ref`, `product_ref`, `requested_action`,
  `schema_version`
- 실행 Metadata: Provider/Model/Version/Revision, Provider Request ID, Input/Output Token 수,
  Latency

Mock은 성공, Timeout, Transient/Permanent 실패, 잘못된 Schema, 잘못된 Quote와 Prompt
Injection 입력을 결정적으로 재현한다. vLLM Adapter는 연결·읽기 Timeout, 입력·출력 상한,
TLS 검증, 낮은 Temperature와 `response_format=json_schema`를 적용한다. 기본 검증은 외부 GPU를
호출하지 않으며 실제 vLLM Smoke Test는 명시적인 `external_gpu` 실행으로 분리한다.

Sprint 2.5 qualification은 `cyankiwi/Qwen3.8-27B-AWQ-INT4`의 고정 revision을 단일 RTX
4090에서 text-only로 검증한다. 서버·요청 양쪽에서 Thinking을 끄고 100건 합성 Dataset으로
Schema, Pydantic, 정확한 Source Quote, 분류, 누락 정보와 Injection 안전성을 측정한다.
Community 양자화와 합성 평가 결과는 실제 고객 분포 성능으로 간주하지 않는다.

### 수행

- 문의 구조화
- 고객 요청 추출
- 누락 정보 탐지
- 정책 문서 근거 설명
- 상담원용 보고서 생성

### 금지

- 최종 환불·교환 결정
- 사기 판정
- 법적 책임 판정
- DB 상태 직접 변경

### 출력 원칙

- 자유 텍스트가 아니라 JSON Schema 기반 출력
- 추가 Field 거부, 입력 최대 20,000자와 구조화 출력 최대 32,000자 계약
- 낮은 Temperature
- Prompt Name/Version, Canonical SHA-256 Content Hash와 입·출력 Schema Version 기록
- Validation 실패 시 제한된 재시도
- 고객 입력을 JSON Escape한 단일 Placeholder의 Untrusted Data로 취급
- `source_quote`가 있으면 고객 원문의 정확한 연속 부분 문자열인지 재검증
- 검증된 구조화 결과만 저장하고 전체 Prompt, Raw Provider Response, Chain-of-thought는 저장하거나
  로그에 남기지 않음

### 구조화 결과 계약

- Issue Type은 정확히 `DENT`, `CRACK`, `BREAKAGE`, `LEAKAGE`, `MISSING_COMPONENT`,
  `WRONG_ITEM`, `CONTAMINATION`, `FUNCTIONAL_FAILURE`, `PACKAGING_DAMAGE`, `OTHER`,
  `UNKNOWN` 중 하나다.
- 결과는 `schema_version`, `language`, 중복 없는 `issue_types`, `claims`,
  `requested_action`, 중복 없는 `missing_information`, `summary`를 가진다.
- Claim은 Issue Type, Location, Description과 선택적 Exact `source_quote`를 가진다. 모든 Claim
  Type은 `issue_types`에도 존재해야 한다.
- `requested_action`은 텍스트에서 추출한 `REFUND`, `EXCHANGE`, `RESHIPMENT`, `REPAIR`,
  `INFORMATION`, `OTHER`, `UNKNOWN`이며 최종 업무 결정이 아니다.
- Confidence, 승인·거절, 보상, 사기, 책임 또는 정책 판정 Field는 제공하지 않는다.

Prompt Registry와 구조화 결과 보존 경계는
[ADR-0010](adr/0010-code-prompt-registry-and-structured-output-retention.md)을 따른다.

## 7. RAG 설계

RAG, Policy Document/Chunk 저장과 Retrieval Index는 Sprint 2에 구현되지 않았다. 아래는
Sprint 5 이후 목표다.

### 정형 정책

PostgreSQL의 구조화된 규칙으로 관리한다.

- 교환 가능 기간
- 금액 한도
- 상품군
- 결함 유형
- Evidence 필수 조건
- 상급자 승인 기준

### 비정형 정책

pgvector 기반 검색 대상으로 관리한다.

- CS 매뉴얼
- 예외 처리 지침
- 품질 기준서
- 판매자 계약 조항
- 배송 파손 책임 가이드

검색 순서:

```text
Tenant / Product / Policy Version Metadata Filter
→ Keyword + Vector Retrieval
→ 근거 문단 반환
→ LLM이 설명 생성
```

정책 검색 결과에는 문서, 섹션, 버전, 유효기간을 포함한다.

## 8. Feedback Loop

상담원 Review를 학습 데이터로 즉시 자동 반영하지 않는다.

```text
AI 권고
→ 상담원 최종 결정
→ 수정 이유 수집
→ 품질 검수
→ 정책 변경 또는 모델 학습 후보로 분리
```

정책 오류와 모델 오류를 분리해 라벨링한다.

## 9. 평가 지표

### Vision

- Class별 Precision / Recall
- mAP 또는 IoU
- Calibration
- 이미지 품질 판정 정확도
- 보류 또는 판정 불가 성능
- 추론 Latency

### LLM

- JSON Schema 성공률
- 필드별 Extraction F1 또는 Accuracy
- 누락 정보 탐지 정확도
- 근거 없는 정책 생성 비율
- Prompt Version별 실패율
- Latency와 Token 사용량

### End-to-End

- Routing Accuracy
- Approval Candidate 위험 오류율
- 상담원 Override율
- 평균 검토시간
- 재검토율
- 추가 자료 요청의 적절성

## 10. 모델 레지스트리

Sprint 2는 별도 Model Registry Table 대신 각 Stage와 Attempt에 실제 Provider/Model/Prompt/
Schema Snapshot을 저장한다. 다음 정식 Registry는 후속 범위이며 최소 항목은 아래와 같다.

- Model name / version
- Provider
- Checkpoint 또는 배포 식별자
- Input / Output Schema Version
- Preprocess / Postprocess Version
- Threshold Version
- Dataset Version
- Evaluation 결과
- 배포 시작·종료 시각
