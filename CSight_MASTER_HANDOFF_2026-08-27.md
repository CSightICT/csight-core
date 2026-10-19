# CSight 마스터 인수인계 문서
**기준 시각:** 2026-08-27 KST  
**대상:** 새로운 ChatGPT Pro / Codex 세션  
**목적:** 새 세션이 지금까지의 제품 방향, 아키텍처, 모델 선택, LLM·RAG·Vision·Policy·Human Review 구현 상태, 실험 결과, Git 상태, 미해결 위험과 다음 작업을 한 번에 이해하고 중복 구현 없이 바로 이어서 작업하게 한다.

> 이 문서는 대화에서 보고된 작업 결과를 종합한 인수인계 문서다. 실제 작업 시 신뢰 우선순위는 **현재 저장소 코드·테스트·Migration·Git 상태 → 저장소의 `CURRENT_STATUS.md`와 Sprint 원장 → 이 문서** 순서다. 충돌이 있으면 저장소를 직접 감사하고 차이를 보고한다.

---

# 0. 새 세션이 가장 먼저 알아야 할 것

## 0.1 현재 프로젝트 상태 한 문장

> **CSight는 Case·Evidence 접수부터 비동기 LLM 분석, Mock Vision 멀티모달 파이프라인, 합성 정책 Hybrid RAG, Citation Guardrail, 결정론적 Policy Engine, Append-only Human Review와 사람만 생성할 수 있는 Final Decision까지 구현됐다. 현재 Sprint 5B가 완료됐지만 미커밋 상태이며, 다음 작업은 Sprint 5B Closeout 후 `Case Resolution Projection + DRY-RUN External Action Adapter`를 구현하는 Sprint 5C다.**

## 0.2 현재 Git 상태

```text
예상 저장소 경로:
  /Users/ckdlsxor/Desktop/CSight_proejct
  반드시 pwd로 재확인

현재 Branch:
  feature/sprint-5b-human-review-workflow

마지막 확정 Commit:
  67eafdd feat: add versioned policy engine core

현재 Sprint 5B:
  구현 완료
  미커밋
  미Push
  미PR
  Staged file 0

사용자 소유 미추적 파일:
  kaputt_best_vision_architecture.md

절대 금지:
  해당 파일 수정
  삭제
  이동
  Stage
  Commit 포함
```

## 0.3 현재 안전한 기본 제품 경로

```text
고객 Case
→ Text Extraction v2
→ RAW Query Strategy
→ Frozen HYBRID Policy Retrieval
   ├─ Exact Robertson BM25
   ├─ Qwen3-Embedding-0.6B
   └─ Weighted RRF
→ Top-3 Immutable Citation Pack
→ Local MLX Grounded Explanation
→ Citation Allowlist Validation
→ Versioned Deterministic Policy Engine
→ Human Review Task
→ 인증된 사람의 Final Decision
```

현재 기본 비활성 또는 실험 경로:

```text
Qwen3 Reranker
  이유: 검색 품질 개선 없음

LLM Policy Query Builder
  이유: Local Test에서 RAW보다 낮음

Top-10 Citation Pack
  이유: Local 4096 Context 초과, Fail-closed

실제 Vision 기반 자동 근거
  이유: Real Vision 미Qualification

실제 환불·교환·재배송·수리 실행
  이유: 미구현
```

## 0.4 다음 즉시 작업

```text
1. Sprint 5B Closeout Audit
2. Sprint 5B 로컬 Commit
   feat: add human review workflow
3. 새 Branch
   feature/sprint-5c-case-resolution-external-action
4. Sprint 5C 구현
   Human Decision
   → Case Resolution Projection
   → Typed External Action Intent
   → DRY-RUN Adapter
5. 실제 외부 환불·교환·CRM 변경은 금지
```

---

# 1. 프로젝트 정의

## 1.1 제품 한 줄 정의

**CSight는 고객 문의 텍스트와 상품 이미지를 하나의 Case로 분석하여 결함 근거를 구조화하고, 기업 정책 검색·평가와 상담원 검토를 연결하는 B2B 상품 불량 CS 의사결정 지원 시스템이다.**

## 1.2 해결하려는 업무 문제

현재 상품 불량 CS는 일반적으로 다음과 같이 처리된다.

```text
문의 텍스트와 이미지 접수
→ 상담원 수동 확인
→ 주문·상품·정책 별도 조회
→ 환불·교환 등 처리 판단
→ 근거와 결과 수기 기록
```

핵심 문제:

- 문의량 증가에 따른 인력·운영비 증가
- 상담원별 판단 편차
- 결함 근거와 정책 근거의 비정형 기록
- 단순 문의와 고위험 문의의 동일 Queue 처리
- 상품·기간·금액·결함별 정책 적용 오류
- CS 결과가 품질관리 데이터로 축적되지 않음

## 1.3 제품 철학

```text
AI가 분석
정책 엔진이 구조화 규칙 평가
사람이 최종 결정
외부 시스템은 별도 Adapter가 실행
```

절대 유지할 경계:

1. **LLM·Vision은 분석자다.**
2. **RAG는 관련 정책 근거를 찾는다.**
3. **Policy Engine은 Version된 정형 Rule만 실행한다.**
4. **Final Decision은 인증된 사람만 생성한다.**
5. **Human Decision과 실제 환불·교환 실행은 별개다.**
6. **모델·Prompt·Rule·Policy·Threshold·Taxonomy·결과는 버전과 이력으로 남긴다.**

---

# 2. PoC와 사업 방향

## 2.1 초기 고객 가설

> 자체 온라인몰을 운영하고 이미지 기반 불량 문의가 반복되는 중소·중견 브랜드사의 CS 조직

이유:

- 상품과 정책을 직접 관리
- CS 텍스트·이미지·처리 결과 보유 가능성
- 특정 상품군과 결함 유형으로 PoC 범위를 좁히기 쉬움
- CS와 품질관리 데이터 연결 가능
- 대형 오픈마켓보다 초기 의사결정 구조가 단순할 가능성

## 2.2 PoC 범위

```text
1개 고객 환경
× 1개 상품군
× 2~3개 결함 유형
```

포함:

- 문의 텍스트·이미지 접수
- 텍스트 구조화
- 이미지 품질·결함 분석
- 정책 검색
- 정책 규칙 평가
- 사람 검토
- 검토 근거 및 결정 이력

제외:

- AI 단독 고액 환불
- 사기·허위 신고 확정
- 법적 책임 확정
- 모든 상품·결함 범용화
- 사람 없는 완전 자동 처리
- 실제 결제 취소·CRM 변경

## 2.3 PoC 운영 단계

```text
Offline Evaluation
→ Shadow Mode
→ Limited PoC
```

초기 목표는 자동화율 극대화가 아니라 다음이다.

- 위험한 오승인·오거절 최소화
- 상담원 검토시간 감소
- 근거 기록 표준화
- 고신뢰 사례의 반복 업무 감소

---

# 3. 핵심 아키텍처

## 3.1 논리 계층

```text
Interface Layer
  FastAPI REST / Worker / Event / Webhook
        ↓
Application Use Cases
        ↓
Reusable Platform Core
  Case / Evidence / Analysis / Policy / Review / Audit
        ↓
┌────────────────────────┬──────────────────────────┐
│ Domain Modules         │ Provider Adapters        │
│ product_defect_cs      │ LLM / Vision / Storage   │
│                        │ DB / MQ / Vector / Action │
└────────────────────────┴──────────────────────────┘
```

## 3.2 의존성 방향

```text
Interface
→ Application
→ Platform / Domain
→ Ports

Adapters
→ Ports 구현
```

금지:

```text
platform/domain에서 FastAPI import
platform/domain에서 SQLAlchemy import
platform/domain에서 Celery import
platform/domain에서 HTTPX import
platform/domain에서 모델 SDK import
```

## 3.3 물리 배포

### Core Application & Data Plane

현재 Mac의 Docker Core:

```text
FastAPI API
Celery Worker
Outbox Dispatcher
PostgreSQL + pgvector
RabbitMQ
MinIO
```

### Host-native Local AI

```text
Qwen3.5-9B MLX 4-bit
Qwen3-Embedding-0.6B on MPS
Qwen3-Reranker-0.6B on MPS
```

Docker Worker는 Host AI 서비스에 다음으로 접근한다.

```text
host.docker.internal
```

### Target GPU LLM Node

```text
RTX 4090
Qwen3.8-27B AWQ INT4
vLLM
Tailscale Private Network
```

현재는 과거 Qualification 완료 상태지만 항상 사용할 수 있는 장비가 아니다.

### Vision Node

별도 GPU 서버 예정.

현재 Backend 계약과 Mock Pipeline은 완료됐지만 실제 모델 Qualification은 미완료다.

---

# 4. 핵심 설계 원칙

1. **Append-only Analysis**  
   재분석은 새 Run을 만든다. 기존 결과를 덮어쓰지 않는다.

2. **Transactional Outbox**  
   DB 저장과 메시지 발행의 Dual-write 문제를 피한다.

3. **Identifier-only Queue**  
   고객 원문, 이미지 Binary, Signed URL, JWT, Prompt 전체를 Queue에 넣지 않는다.

4. **Tenant-first Security**  
   Tenant는 인증 Principal에서 결정한다. 다른 Tenant Resource는 `404`.

5. **Model Server Stateless**  
   모델 서버는 Core DB를 직접 조회하거나 상태를 바꾸지 않는다.

6. **Provider Adapter**  
   모델 고유 출력은 Adapter에서 Canonical Schema로 변환한다.

7. **Version Everything**  
   Model, Revision, Prompt, Schema, Retrieval Profile, Rule Set, Threshold, Taxonomy를 기록한다.

8. **Fail-closed**  
   Invalid JSON, Unknown Citation, Wrong Version, Missing Parameter는 성공으로 보정하지 않는다.

9. **No Silent Fallback**  
   Provider 장애를 Mock 결과로 성공 처리하지 않는다.

10. **Human-only Final Decision**  
    Worker, LLM, Vision, RAG, Policy Engine은 Final Decision을 생성할 수 없다.

---

# 5. Git·협업 상태

## 5.1 Remote

```text
GitHub 조직:
CSightICT

저장소:
CSightICT/csight-core

Visibility:
Private

연결 계정:
it0615
```

## 5.2 브랜치 전략

```text
main
develop
feature/*
chore/*
```

## 5.3 거버넌스

완료:

- PR·Issue Template
- CODEOWNERS 초기 설정
- GitHub Actions
- `Quality and fast tests`
- Squash/Merge 설정
- 원격 main/develop/작업 브랜치

제한:

- Private 저장소 현재 플랜에서 Branch Protection API가 HTTP 403
- Issue #1에서 추적
- `kimhrin`은 read 권한으로 승인 Reviewer가 아님
- 권한 상승은 사용자 승인 없이 하지 않는다

---

# 6. Commit 타임라인

| 단계 | Commit | 메시지 |
|---|---|---|
| 초기 Foundation | `6fc20d3` | 초기 Foundation 기준점 |
| Sprint 2 | `294cb5b` | `feat: complete append-only LLM analysis pipeline` |
| Sprint 2.5 | `7d63cbb` | `chore: qualify qwen3.8 27b serving on single 4090` |
| Sprint 3 | `330cbdb` | `feat: complete multimodal vision analysis pipeline` |
| Sprint 4A | `6f3a667` | `feat: add LLM contract v2 and policy reference corpus` |
| Sprint 4B | `4216028` | `feat: add hybrid policy retrieval baseline` |
| Sprint 4C-1 | `14cae29` | `chore: qualify qwen3 policy reranker` |
| Sprint 4C-2 | `a282817` | `feat: add case-based policy retrieval query planning` |
| Sprint 4C-3A | `72cbe12` | `feat: add citation grounding guardrails` |
| Sprint 4C-3B | `d0950f6` | `feat: add local MLX LLM grounding PoC` |
| Sprint 5A | `67eafdd` | `feat: add versioned policy engine core` |
| Sprint 5B | 미커밋 | 완료 상태, Closeout 필요 |

> 정확한 전체 이력은 반드시 `git log --oneline --decorate --graph`로 재확인한다.

---

# 7. Migration 타임라인

| Revision | 목적 |
|---|---|
| `20260826_0001` | Foundation / pgvector baseline |
| `20260826_0002` | Tenant·User·Case·Evidence·Idempotency |
| `20260826_0003` | Analysis Run·Stage·Attempt·LLM Result·Outbox |
| `20260826_0004` | Vision Snapshot·Result·Detection |
| `20260826_0005` | LLM Contract v2 append-only child |
| `20260826_0006` | Policy Corpus Ingestion·Embedding·Index |
| `20260826_0007` | Reranker Profile·Execution Profile |
| `20260826_0008` | Policy Query Builder·Retrieval Run |
| `20260827_0009` | Citation Pack·Grounding Run·Result |
| `20260827_0010` | Versioned Policy Engine |
| `20260827_0011` | Human Review Workflow |
| 다음 예정 `0012` | Case Resolution·External Action DRY-RUN |

모든 완료 Migration에서 다음을 반복 검증했다.

```text
Empty DB → Head
Previous Head → New Head
New Head → Previous → New Head
Drift 0
```

---

# 8. Sprint별 구현 상태

# 8.1 Sprint 0 — Foundation

상태:

```text
PASS
```

구현:

- Python 3.12
- `uv.lock`
- FastAPI
- Pydantic Settings
- SQLAlchemy / Alembic
- PostgreSQL / pgvector
- RabbitMQ
- MinIO
- Celery
- Health / Readiness
- Mock LLM / Vision Port
- Architecture Test
- Ruff / Pyright / pytest
- Docker Compose
- GitHub Actions

---

# 8.2 Sprint 1 — Case & Evidence

상태:

```text
PASS
```

구현:

```text
JWT / Role / Tenant
Case 생성·목록·상세
Case Status History
Case Idempotency

JPEG / PNG / WebP 검증
실제 Decode
SHA-256
Width / Height / Pixel Limit

Private MinIO
Signed URL
Storage/DB 보상
Cross-Tenant 404
```

중요 경계:

- 이미지 Binary는 PostgreSQL에 저장하지 않음
- Object Key는 서버가 생성
- Case 접수만으로 AI 분석 자동 시작 안 함

---

# 8.3 Sprint 2 — Append-only LLM Analysis

상태:

```text
PASS
```

Pipeline:

```text
POST Analysis Run
→ Run + Stage + Idempotency + Outbox Transaction
→ 202
→ Dispatcher
→ RabbitMQ
→ Celery
→ LLM Provider
→ Strict Pydantic Validation
→ Append-only Result
```

구현:

- Lease / Claim Token / Fencing
- Duplicate Delivery No-op
- Retry / Timeout / Max Attempt
- Prompt Registry
- Mock / vLLM Adapter
- Raw Prompt·Response·Reasoning 비저장

---

# 8.4 Sprint 2.5 — Qwen3.8 Target Qualification

상태:

```text
QUALIFIED_WITH_LIMITATIONS
```

모델:

```text
Artifact:
cyankiwi/Qwen3.8-27B-AWQ-INT4

Revision:
63768c10df38c0395e12ef49edac1bd539eaeeea

vLLM:
0.26.0

GPU:
RTX 4090 24 GB

Mode:
Text-only
Non-thinking
Max Context 8192
Max Sequences 1
FP8 KV Cache
CPU Offload 없음
```

성능:

| Metric | 값 |
|---|---:|
| Cache-hit Cold Start | 97초 |
| Idle VRAM | 23,009 MiB |
| Peak VRAM | 23,825 MiB |
| TTFT p50 / p95 | 0.089 / 0.176초 |
| Latency p50 / p95 | 1.470 / 1.558초 |
| Output Token/s | 36.36 |

품질 100건:

| Metric | 값 |
|---|---:|
| Schema Valid | 100% |
| Source Quote | 100% |
| Issue Type F1 | 0.95 |
| Requested Action Accuracy | 0.23 |
| Missing Information F1 | 0.00 |
| Injection Violation | 0 |
| Reasoning Leakage | 0 |

해석:

- 서빙과 구조적 출력은 우수
- Action/Missing 품질은 자동 Workflow 결정에 부적합
- Human Review와 Deterministic Rule 경계 유지
- VRAM 여유가 작으므로 Sequence 1 권장

---

# 8.5 Sprint 3 — Vision Pipeline

상태:

```text
MOCK_QUALIFIED
REAL_MODEL_NOT_AVAILABLE
```

구현:

- `VISION_ANALYSIS` Stage
- Immutable Evidence Snapshot
- Text/Vision Outbox Fan-out
- DB 기반 Join
- `PARTIAL_SUCCESS`
- Image별 Append-only Result
- Normalized XYXY Geometry
- Native→Canonical Taxonomy Adapter
- Remote multipart Adapter Contract
- 10개 Deterministic Mock Scenario

중요 제한:

- KAPUT 참고 자료는 image-level multi-label + item mask 중심
- 실제 defect bbox qualification 아님
- Mapping은 실제 모델 검증 전 계약 가설
- Multi-image는 한 Stage에서 순차 처리
- Image Quality 미지원 Provider는 `NOT_EVALUATED/null`

---

# 8.6 Sprint 4A — LLM Contract v2와 Reference Data

상태:

```text
REFERENCE_DATA_QUALIFIED_WITH_LIMITATIONS
```

LLM Contract v2:

```text
Declared Requested Action
≠
Extracted Requested Actions

LLM Text Ambiguities
≠
Backend System Missing Information
```

Corpus:

| Metric | 값 |
|---|---:|
| Tenant | 2 |
| Document Version | 24 |
| Clause | 168 |
| Policy Type | 9 |
| Exception | 48 |
| Evidence Requirement | 48 |
| Active / Retired | 18 / 6 |
| Duplicate | 0 |

모든 정책은:

```text
SYNTHETIC_REFERENCE
```

Evaluation Dataset:

| Dataset | Dev | Test | Total |
|---|---:|---:|---:|
| Extraction v2 | 120 | 40 | 160 |
| Retrieval v1 | 80 | 40 | 120 |
| Grounding v1 | 40 | 10 | 50 |
| Injection v1 | 20 | 10 | 30 |
| Demo Pack | - | - | 10 |

---

# 8.7 Sprint 4B — Hybrid Policy Retrieval

상태:

```text
HYBRID_RETRIEVAL_QUALIFIED_WITH_LIMITATIONS
```

Lexical:

```text
Exact Robertson BM25
Tokenizer: ko_policy_lexical 1.0.0
k1 = 1.2
b = 0.75
```

Embedding:

```text
Qwen/Qwen3-Embedding-0.6B
Revision:
97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3

Dimension:
1024

Pooling:
Last-token

Normalization:
L2 true

Device:
Apple M4 MPS
```

Hybrid:

```text
Weighted RRF
k = 20
Lexical weight = 1.5
Dense weight = 0.5
```

Test 40:

| Metric | BM25 | Dense | Hybrid |
|---|---:|---:|---:|
| Recall@1 | 0.1250 | 0.1250 | 0.1250 |
| Recall@3 | 0.4125 | 0.4375 | 0.4375 |
| Recall@5 | 0.7000 | 0.7125 | 0.7000 |
| Recall@10 | 0.9250 | 0.9250 | 0.9250 |
| MRR@10 | 0.5250 | 0.5163 | 0.5383 |
| nDCG@10 | 0.5943 | 0.5992 | 0.5984 |
| Exact Coverage@10 | 0.8500 | 0.8500 | 0.8500 |

Correctness:

```text
Cross-Tenant 0
Wrong Version 0
Future Policy 0
Retired Policy 0
Duplicate Hit 0
NaN / Inf 0
Determinism 100%
```

---

# 8.8 Sprint 4C-1 — Reranker

상태:

```text
RERANKER_NO_MEASURABLE_GAIN
```

모델:

```text
Qwen/Qwen3-Reranker-0.6B
Revision:
e61197ed45024b0ed8a2d74b80b4d909f1255473

Device:
Apple MPS

Candidate K:
20

Final K:
10
```

Test:

| Metric | Hybrid | Reranked |
|---|---:|---:|
| Recall@10 | 0.9250 | 0.9250 |
| MRR@10 | 0.53833 | 0.51250 |
| nDCG@10 | 0.59841 | 0.59802 |

결론:

```text
Reranker는 기본 경로에서 비활성
HYBRID_RERANKED는 실험 Mode로만 보존
```

---

# 8.9 Sprint 4C-2 — Query Builder

상태:

```text
Case 기반 Query Run 구현 완료
RAW 전략 선택
```

비교 결과 Test 40:

| Metric | RAW | Deterministic |
|---|---:|---:|
| Recall@1 | 0.6000 | 0.6250 |
| Recall@3 | 0.9250 | 0.7500 |
| Recall@5 | 0.9250 | 0.8500 |
| Recall@10 | 0.9750 | 1.0000 |
| MRR@10 | 0.739236 | 0.724544 |
| nDCG@10 | 0.741392 | 0.657571 |
| Exact Coverage@10 | 0.8500 | 0.8250 |

해석:

- Deterministic는 일부 Recall을 높였지만 전체 순위와 Exact Coverage 악화
- RAW를 잠정 기본으로 선택
- Local LLM Query Builder는 이후 Sprint 4C-3B에서 실제 평가

---

# 8.10 Sprint 4C-3A — Citation Guardrail

상태:

```text
STRUCTURAL_GROUNDING_QUALIFIED
```

구현:

- Immutable Citation Pack
- Citation Allowlist
- Decision-free Grounding Schema
- Append-only Grounding Run / Result
- Outbox / Celery
- Cross-Tenant·Wrong Version Fail-closed
- Statement별 Citation 필수

구조 평가:

```text
Grounding 50
Injection 30
구조 위반 0
Replay 100%
```

---

# 8.11 Sprint 4C-3B — Local MLX LLM/RAG PoC

상태:

```text
LOCAL_MLX_POC_QUALIFIED_WITH_LIMITATIONS
LOCAL_GROUNDING_POC_QUALIFIED_WITH_LIMITATIONS
```

모델:

```text
Artifact:
mlx-community/Qwen3.5-9B-MLX-4bit

Revision:
938d891... 정확한 전체 값은 Manifest 확인

MLX:
0.32.2

mlx-vlm:
0.6.17

Device:
Apple M4 / Unified Memory 32 GB

Stability:
2시간 34분 이상

RSS:
약 6.50 GB

Swap:
0
```

Extraction Test 40:

| Metric | 값 |
|---|---:|
| Schema / Source Quote | 100% |
| Issue F1 | 0.8533 |
| Action F1 | 0.1935 |
| Ambiguity F1 | 0.1951 |

Query Builder Test 40:

```text
Local LLM Recall@10:
0.90

RAW Recall@10:
0.975

결론:
RAW_REMAINS_SELECTED
```

Grounding:

```text
Grounding Test 10
Injection Test 10

Citation precision / recall:
100%

Required fact:
100%

Unresolved condition:
100%

Forbidden decision:
0

Injection violation:
0

Reasoning leakage:
0

Human Spot-check:
Dev 20 / Test 10 전체 통과
```

중요 제한:

```text
Top-10 Citation Pack:
4096 Context 초과
Fail-closed

기본:
Top-3 Citation Pack
```

실제 Local E2E:

```text
Case 10/10

Extraction v2
→ RAW Hybrid Retrieval
→ Top-3 Citation Pack
→ Local Grounded Explanation
→ Citation Validation
```

---

# 8.12 Sprint 5A — Policy Engine

상태:

```text
POLICY_ENGINE_CORE_QUALIFIED_WITH_LIMITATIONS
```

Rule Artifact:

| Metric | 값 |
|---|---:|
| Tenant | 2 |
| Rule Set | 2 |
| Rule | 24 |
| Source Clause Link | 24 |
| Version | 1.0.0 |

Condition Semantics:

```text
SATISFIED
UNSATISFIED
UNKNOWN
NOT_EVALUATED
NOT_APPLICABLE
```

허용 Operator:

```text
EQ NE LT LTE GT GTE
IN NOT_IN
CONTAINS CONTAINS_ANY CONTAINS_ALL
EXISTS NOT_EXISTS
```

금지:

```text
eval
exec
Raw SQL
Arbitrary Expression
JSONPath Code Execution
```

Dev 80 / Test 40:

```text
Rule Set Selection 1.0
Rule Match Exact 1.0
Condition Status 1.0
Effect F1 1.0
Summary Status 1.0
Source Clause Validity 1.0
Deterministic Replay 1.0
Forbidden Decision 0
```

해석:

- 합성 Rule/Gold 기준 구조적 정확성
- 실제 기업 정책 정확성이나 법적 효력 증거 아님

---

# 8.13 Sprint 5B — Human Review Workflow

상태:

```text
HUMAN_REVIEW_WORKFLOW_QUALIFIED_WITH_LIMITATIONS
미커밋
```

구현:

- Policy Effect → Versioned Review Task
- Task + Immutable Packet + CREATED Action 원자 생성
- CAS Claim
- 동시 Claim 1 성공 / 1 충돌
- Release
- Evidence Request
- Resume
- Escalate
- Admin/Reviewer Resolve
- Rationale와 Decision Basis 검증
- Append-only Action·Assignment·Decision·Basis
- Viewer 읽기 전용
- Manager/Safety ADMIN-only
- Cross-Tenant 404
- Worker/Policy/LLM/Vision/RAG의 Final Decision 생성 차단

Migration:

```text
20260827_0011_human_review
```

평가 Dev 60 / Test 30:

```text
Task Mapping / Priority 1.0
State Transition 1.0
Authorization / Assignment 1.0
Decision Basis / Outcome 1.0
Audit / Replay 1.0
```

최종 검증:

```text
Default Regression:
484 passed, 57 deselected

Integration:
46 passed, 5 external GPU skipped

Docker:
6/6 Healthy

Queue:
6개 application queue
consumer 1
depth 0

Live E2E:
Task / Packet / Created / Claimed / Resolved / Decision / Basis 각 1
```

현재 제한:

- Review UI 없음
- 외부 환불·교환 실행 없음
- Decision Amendment 없음
- 자동 Assignment·SLA 없음
- Final Report 없음

---

# 9. 현재 LLM 전략

## 9.1 Production Target

```text
Qwen3.8-27B AWQ INT4
RTX 4090
vLLM
```

용도:

- 최종 성능 Qualification
- 실제 데모 품질 검증
- 모델 기준점

## 9.2 Local PoC

```text
Qwen3.5-9B MLX 4-bit
Mac M4 32 GB
```

용도:

- 개발
- Prompt 반복
- 전체 E2E
- Local Demo
- Grounding 검증

## 9.3 LLM 입력 사용 규칙

Hard Rule에 사용 가능한 정보:

```text
Case declared action
Case metadata
System missing information
Typed date/amount/category
Evidence count
```

Advisory 또는 Human Review가 필요한 정보:

```text
LLM issue_types
LLM claims
LLM extracted actions
LLM text ambiguities
```

특히 Local 모델의 Action/Ambiguity F1이 낮으므로 자동 자격판정 Hard Input으로 사용하지 않는다.

---

# 10. 현재 RAG 전략

## 10.1 Default

```text
Query Strategy:
RAW

Retriever:
HYBRID

Lexical:
Exact BM25

Dense:
Qwen3-Embedding-0.6B

Fusion:
Weighted RRF

Reranker:
Disabled

Citation Pack:
Top-3

Grounded Explanation:
Local MLX PoC 사용 가능
```

## 10.2 Reranker 제외 이유

```text
Recall 개선 없음
MRR 하락
nDCG 하락
Latency 증가
```

## 10.3 Query Builder 제외 이유

```text
Local LLM Recall@10 0.90
RAW Recall@10 0.975
```

## 10.4 RAG의 책임

허용:

- 관련 정책 Clause 검색
- Source Version·Effective Date 보존
- Citation 근거 제공
- 상담원용 정책 설명

금지:

- 환불 승인
- 교환 승인
- 사기 판정
- 책임 확정
- Policy Rule 자동 생성·실행
- Final Decision

---

# 11. 현재 Vision 전략

현재 상태:

```text
Backend Vision Pipeline:
MOCK_QUALIFIED

Remote Adapter:
CONTRACT_ONLY

Real Vision:
NOT_AVAILABLE
```

실제 Vision 학습 후 필요한 것:

```text
Model Artifact
Model Revision
Dataset Version
Taxonomy Version
Threshold Version
Preprocess / Postprocess Version
Sample Input / Output
Class별 Precision / Recall / AP
BBox Qualification
Latency
Known Failure Cases
```

실제 모델 검증 전:

- Mock 결과를 실제 결함 증거로 사용하지 않는다.
- Policy Condition은 `NOT_EVALUATED`.
- Evidence Alignment는 보류한다.

---

# 12. 주요 API 목록

## Auth

```text
POST /api/v1/auth/token
GET  /api/v1/auth/me
```

## Case / Evidence

```text
POST /api/v1/cases
GET  /api/v1/cases
GET  /api/v1/cases/{case_id}
GET  /api/v1/cases/{case_id}/status-history

POST /api/v1/cases/{case_id}/evidence
GET  /api/v1/cases/{case_id}/evidence
GET  /api/v1/cases/{case_id}/evidence/{evidence_id}
POST /api/v1/cases/{case_id}/evidence/{evidence_id}/access-url
```

## Analysis

```text
POST /api/v1/cases/{case_id}/analysis-runs
GET  /api/v1/cases/{case_id}/analysis-runs
GET  /api/v1/cases/{case_id}/analysis-runs/{run_id}
```

## Policy Retrieval

```text
POST /api/v1/policy-retrieval/search
```

Mode:

```text
LEXICAL
DENSE
HYBRID
HYBRID_RERANKED
```

기본:

```text
HYBRID
```

## Case-based Retrieval

```text
POST /api/v1/cases/{case_id}/policy-retrieval-runs
GET  /api/v1/cases/{case_id}/policy-retrieval-runs
GET  /api/v1/cases/{case_id}/policy-retrieval-runs/{run_id}
```

## Grounding

Case 하위 Citation/Grounding Run API가 구현돼 있으며 정확한 Path는 저장소 OpenAPI와 `SPRINT_4C3A_CITATION_GROUNDING.md`를 확인한다.

## Policy Evaluation

```text
POST /api/v1/cases/{case_id}/policy-evaluation-runs
GET  /api/v1/cases/{case_id}/policy-evaluation-runs
GET  /api/v1/cases/{case_id}/policy-evaluation-runs/{run_id}
```

## Human Review

```text
GET  /api/v1/human-review-tasks
GET  /api/v1/human-review-tasks/{task_id}

POST /api/v1/human-review-tasks/{task_id}/claim
POST /api/v1/human-review-tasks/{task_id}/release
POST /api/v1/human-review-tasks/{task_id}/request-additional-evidence
POST /api/v1/human-review-tasks/{task_id}/resume
POST /api/v1/human-review-tasks/{task_id}/escalate
POST /api/v1/human-review-tasks/{task_id}/resolve
```

---

# 13. 평가 데이터와 봉인 규칙

## 13.1 Dataset

```text
llm_extraction_v2:
Dev 120 / Test 40

policy_retrieval_v1:
Dev 80 / Test 40

grounding_v1:
Dev 40 / Test 10

prompt_injection_v1:
Dev 20 / Test 10

policy_query_builder_v1:
Dev 80 / Test 40

policy_engine_v1:
Dev 80 / Test 40

human_review_workflow_v1:
Dev 60 / Test 30
```

## 13.2 실험 원칙

- Dev에서만 Prompt·Rule·Profile 조정
- Test는 Freeze 후 1회
- Test 결과로 재튜닝 금지
- Gold 오류 발견 시 새 Dataset Version
- Mock Self-check를 실제 모델 성능으로 보고 금지
- 실제 Qwen·Vision 미실행은 Skip으로 기록

---

# 14. 중요한 음성 결과와 교훈

## 14.1 Reranker

```text
Qwen3-Reranker-0.6B
→ 서비스는 정상
→ 품질 개선 없음
→ 기본 경로 제외
```

교훈:

- 모델을 추가했다고 성능이 자동 상승하지 않는다.
- Candidate recall과 Oracle 상한을 먼저 봐야 한다.

## 14.2 Query Builder

```text
RAW가 Local LLM Query Builder보다 우수
```

교훈:

- 작은 구조화 Query가 원문의 유용한 검색 단서를 삭제할 수 있다.
- LLM Query Builder는 “스마트해 보인다”는 이유로 선택하지 않는다.

## 14.3 Local LLM Extraction

```text
Issue Type은 준수
Action / Ambiguity는 낮음
```

교훈:

- 모든 LLM Field를 동일 신뢰도로 다루면 안 된다.
- Hard Rule과 Advisory Field를 분리해야 한다.

## 14.4 Citation Context

```text
Top-10 Citation
→ 4096 Context 초과

Top-3 Citation
→ 안정
```

교훈:

- 검색 Recall과 생성 Context는 별도 최적화 대상
- 현재 Local PoC는 Top-3
- 향후 Context 확장 전 재Qualification 필요

## 14.5 Policy Engine 1.0

```text
합성 Rule/Gold에서 1.0
```

교훈:

- 구조적 정확성은 검증됐지만 실제 기업 정책 정확성은 미검증
- 1.0을 사업 성능으로 과장하지 않는다

---

# 15. 현재 주요 위험과 Blocker

## P0/P1에 가까운 제품 위험

1. **실제 Vision 모델 미검증**
2. **실제 기업 정책 데이터 부재**
3. **실제 고객 Query 분포 미검증**
4. **Local LLM Action/Ambiguity 품질 낮음**
5. **외부 환불·교환 실행 경계 미구현**
6. **Review UI 없음**
7. **개인정보·Retention 정책 미확정**

## 운영 위험

- Evidence 업로드 Reconciliation / Orphan Cleanup 미구현
- Evidence Upload Idempotency 미구현
- EXIF 제거·Virus Scan·PII Masking 미구현
- OIDC / SSO / Refresh Token / RLS 미구현
- DLQ·Manual Retry·Cancel API 미구현
- Production Supervisor·Secret Rotation 미검증
- Mac MPS 서비스 Concurrency 제한
- Qwen3.8 VRAM 여유 매우 작음

## GitHub 운영

- Branch Protection 플랜 제약
- 유효 Reviewer 권한 결정 필요
- PR #2 병합·거버넌스 정리 필요

---

# 16. 다음 작업: Sprint 5B Closeout

## 16.1 감사 포인트

- Final Decision 생성 경로가 Resolve API뿐인지
- Worker·Policy·LLM·Vision·RAG가 Decision 생성 불가인지
- Review Packet 불변성
- Basis Allowlist
- 동시 Claim
- Duplicate Resolve
- Role
- Cross-Tenant
- Migration `0011`
- Human Review Dataset 봉인 상태

## 16.2 Commit

조건 통과 시:

```text
feat: add human review workflow
```

Push / PR 금지.

---

# 17. 다음 작업: Sprint 5C 상세 계획

# 17.1 목표

> Human Decision을 Case Resolution Projection에 반영하고, 실제 외부 시스템을 변경하지 않는 Typed `DRY_RUN` External Action Intent와 Adapter를 구현한다.

## 17.2 핵심 경계

```text
Human Decision
≠
External Action Completion
```

예:

```text
APPROVE_REFUND
→ 환불 결정 기록

아직 아님:
REFUND_COMPLETED
```

## 17.3 Resolution Status

```text
DECISION_RECORDED
ACTION_NOT_REQUIRED
MANUAL_FOLLOW_UP_REQUIRED
ACTION_NEEDS_INPUT
ACTION_READY
ACTION_DRY_RUN_PENDING
ACTION_DRY_RUN_VALIDATED
ACTION_DRY_RUN_FAILED
```

금지:

```text
ACTION_CONFIRMED
CASE_CLOSED
REFUND_COMPLETED
EXCHANGE_COMPLETED
```

## 17.4 Decision Mapping

| Human Decision | Resolution | External Action |
|---|---|---|
| `APPROVE_REFUND` | Action required | `REFUND` |
| `APPROVE_EXCHANGE` | Action required | `EXCHANGE` |
| `APPROVE_RESHIPMENT` | Action required | `RESHIPMENT` |
| `APPROVE_REPAIR` | Action required | `REPAIR` |
| `REJECT_REQUEST` | `ACTION_NOT_REQUIRED` | 없음 |
| `NO_ACTION` | `ACTION_NOT_REQUIRED` | 없음 |
| `PROVIDE_INFORMATION` | `MANUAL_FOLLOW_UP_REQUIRED` | 없음 |

Version:

```text
human_decision_to_external_action
1.0.0
```

## 17.5 Typed Command

### Refund

필수:

```text
order_reference
refund_amount
currency
```

금지:

- 주문 금액을 자동 환불액으로 가정
- LLM에서 금액 추출
- Reviewer Rationale를 Provider Payload로 전달

### Exchange

필수:

```text
order_reference
product_reference
quantity
```

수량을 자동 1로 가정하지 않는다.

### Reshipment

필수:

```text
order_reference
product_reference
quantity
destination_reference
```

주소 원문 대신 Opaque Reference를 사용한다.

### Repair

필수:

```text
order_reference
product_reference
```

## 17.6 Execution Mode

현재 허용:

```text
DRY_RUN
```

금지:

```text
LIVE
```

`LIVE`는:

```text
LIVE_EXTERNAL_ACTION_DISABLED
```

로 Fail-closed.

## 17.7 Persistence 예정

Migration:

```text
20260827_0012_case_resolution_external_action
```

테이블:

```text
case_resolution_projections
case_resolution_events

external_action_intents
external_action_attempts
external_action_results
```

## 17.8 Worker

```text
case_resolution.requested.v1
→ Resolution Worker
→ Intent 생성
→ Completeness 평가
→ READY일 때 external_action.simulation_requested.v1
→ DRY-RUN Simulation Worker
```

Queue에는 Identifier만 전달한다.

## 17.9 API 예정

```text
GET /api/v1/cases/{case_id}/resolution
GET /api/v1/cases/{case_id}/resolution/events
GET /api/v1/cases/{case_id}/external-action-intents
GET /api/v1/external-action-intents/{intent_id}
```

이번 Sprint에는 Action 실행 POST API를 만들지 않는다.

## 17.10 필수 안전 Gate

```text
Live Execution 0
Premature Case Closure 0
Cross-Tenant 0
Duplicate Intent 0
Duplicate Result 0
Parameter Inference 0
Human Decision Mutation 0
Raw Provider Response 저장 0
```

---

# 18. Sprint 5C 이후 권장 Roadmap

## Track A — External Action / Resolution

```text
Sprint 5C
Case Resolution + DRY_RUN External Action

Sprint 5D
Action Parameter Completion
Decision Amendment
Manual Retry / Cancel

Sprint 6A
실제 Sandbox Provider Adapter
Provider Confirmation
Case Closure

Sprint 6B
Customer Notification
CRM Integration
```

## Track B — Vision

```text
Real Vision Training
→ Model Manifest
→ Threshold Calibration
→ Remote Provider Qualification
→ Evidence Alignment
```

## Track C — LLM / RAG

```text
Qwen3.8 Target Requalification
→ Extraction v2
→ Grounding
→ Local vs Target 비교

실제 기업 정책 Corpus 반입
→ Retrieval Re-evaluation
→ Policy Rule Curating
```

## Track D — UX

```text
Reviewer Web Console
Evidence Viewer
Policy / Citation Panel
Qualification Badge
Human Decision Form
Resolution / DRY-RUN Status
```

## Track E — Operations

```text
OIDC / SSO
RLS
Retention
PII Masking
Virus Scan
Reconciliation
DLQ / Manual Retry
Observability
Backup / Restore
Production Deployment
```

---

# 19. 새 세션의 작업 규칙

새 GPT / Codex는 다음을 지킨다.

1. `AGENTS.md`를 먼저 읽는다.
2. `CURRENT_STATUS.md`와 가장 최근 Sprint 원장을 읽는다.
3. `pwd`, `git status`, `git log`, `git diff --check`로 실제 상태를 확인한다.
4. 완료된 Sprint를 다시 구현하지 않는다.
5. 코드보다 먼저 책임 경계와 ADR을 확인한다.
6. 기존 Prompt·Rule·Profile Version의 의미를 변경하지 않는다.
7. 봉인된 Test를 재튜닝에 사용하지 않는다.
8. 실제로 실행하지 않은 검사를 PASS로 쓰지 않는다.
9. 외부 Provider Skip을 구현 완료나 모델 성능으로 표현하지 않는다.
10. Mock Vision을 실제 근거로 사용하지 않는다.
11. Local MLX 결과를 Qwen3.8 Production 성능으로 표현하지 않는다.
12. Reranker와 LLM Query Builder를 기본 경로에 활성화하지 않는다.
13. Human Decision과 External Execution을 합치지 않는다.
14. 사용자 파일 `kaputt_best_vision_architecture.md`를 건드리지 않는다.
15. Commit·Push·PR 권한 범위를 지시문 그대로 따른다.

---

# 20. 새 세션 시작용 복붙 프롬프트

아래 문장을 새로운 ChatGPT Pro 또는 Codex 세션 첫 메시지로 사용할 수 있다.

```markdown
현재 열려 있는 폴더는 CSight 프로젝트 저장소다.

먼저 다음을 읽고 현재 상태를 직접 검증하라.

1. AGENTS.md
2. docs/progress/CURRENT_STATUS.md
3. docs/progress/SPRINT_5A_POLICY_ENGINE_CORE.md
4. docs/progress/SPRINT_5B_HUMAN_REVIEW_WORKFLOW.md
5. 이 인수인계 문서
6. 관련 ADR과 Migration 0010, 0011

그 후 다음을 실행하라.

- pwd
- git status --short --branch
- git diff --stat
- git diff --check
- git log -10 --oneline
- docker compose --env-file .env -f infra/compose.core.yml ps

현재 예상 상태는 다음과 같다.

- Branch: feature/sprint-5b-human-review-workflow
- Base Commit: 67eafdd feat: add versioned policy engine core
- Sprint 5B: 구현 완료, 미커밋
- Push/PR 없음
- kaputt_best_vision_architecture.md는 사용자 소유 파일이므로 수정·삭제·이동·Stage 금지

이번 세션에서는 다음 순서만 수행하라.

1. Sprint 5B 독립 Closeout Audit
2. P0/P1 0과 전체 Gate가 통과하면 다음 로컬 Commit 생성
   feat: add human review workflow
3. Push와 PR은 하지 않는다.
4. Clean Worktree에서 새 브랜치 생성
   feature/sprint-5c-case-resolution-external-action
5. Human Decision과 External Execution을 분리한 Sprint 5C를 구현한다.
6. Case Resolution Projection, Versioned Decision-to-Action Mapping, Typed External Action Intent, Parameter Completeness, DRY_RUN Adapter, Append-only Attempt/Result를 구현한다.
7. LIVE 실행, 실제 환불·교환, CRM 변경, Case Closure는 구현하지 않는다.
8. 실행하지 않은 검사를 성공했다고 보고하지 않는다.

기본 제품 경로는 유지한다.

- Local LLM: Qwen3.5-9B MLX 4-bit
- Query Strategy: RAW
- Retrieval: HYBRID
- Reranker: Disabled
- Citation Pack: Top-3
- Grounded Explanation: Advisory
- Policy Engine: Deterministic
- Final Decision: Human-only
- External Action: 아직 DRY_RUN only

먼저 저장소를 감사하고 실제 상태가 이 문서와 다르면 차이를 보고한 뒤 진행하라.
```

---

# 21. 현재 프로젝트의 성공 기준

현재 기술적 성과:

- End-to-End Backend 경계가 명확함
- Tenant·Audit·Idempotency·Retry가 구현됨
- LLM/RAG의 각 단계가 분리 평가됨
- 성능이 나쁜 Reranker/Query Builder를 억지로 기본 적용하지 않음
- Policy Rule과 RAG 설명이 분리됨
- Human Review만 Final Decision 생성
- 다음 단계에서 External Execution도 별도 경계로 분리 예정

프로젝트가 실제 기업 PoC 수준으로 가기 위해 남은 핵심:

1. 실제 Vision Qualification
2. 실제 기업 정책 반입
3. 실제 사용자 Query·CS 데이터 평가
4. Reviewer UI
5. DRY_RUN External Action
6. 실제 Sandbox Provider 연동
7. 개인정보·Retention·SSO·운영 보안
8. KPI·ROI 실측

---

# 22. 최종 요약

```text
완료:
Case / Evidence
LLM Analysis
Local LLM PoC
Mock Vision Pipeline
Policy Corpus
Hybrid RAG
Citation Guardrail
Policy Engine
Human Review
Human Final Decision

기본 선택:
RAW Query
HYBRID Retrieval
Reranker Off
Top-3 Citation
Local Grounding
Deterministic Policy
Human Decision

미완료:
Sprint 5B Commit
Case Resolution
DRY_RUN External Action
Real Vision
Evidence Alignment
Real Enterprise Data
Review UI
Real External Provider
Case Closure
Operations Hardening
```

> **다음 세션의 최우선 목표는 Sprint 5B를 안전한 로컬 기준점으로 고정한 뒤, 사람의 Decision과 실제 외부 실행을 분리하는 Sprint 5C를 구현하는 것이다.**
