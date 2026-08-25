# CSight

> 이미지·텍스트 기반 상품 불량 CS 의사결정 지원 플랫폼

CSight는 고객이 제출한 문의 텍스트, 상품 이미지, 주문정보를 하나의 **Case**로 묶어 분석하고, 결함 근거와 기업 정책을 결합해 처리 경로와 검토 문서를 생성하는 B2B CS 운영 서비스다.

초기 목표는 상담원을 대체하는 완전 자동화가 아니다. **명확한 사례의 반복 검토를 줄이고, 모호하거나 위험한 사례를 근거와 함께 담당자에게 전달하는 Human-in-the-loop 시스템**을 구현한다.

---

## 1. 프로젝트 목표

- 고객 문의의 결함 주장과 요청사항을 구조화한다.
- 이미지 품질, 결함 유형, 결함 위치, 신뢰도를 분석한다.
- 텍스트 주장과 이미지 증거의 정합성을 계산한다.
- 기업별 정책을 적용해 승인 후보, 담당자 검토, 추가 자료 요청, 전문 부서 이관으로 라우팅한다.
- 분석 근거, 적용 정책, 권고 조치, 담당자 확정 이력을 표준 문서로 남긴다.
- 상담원 수정·오버라이드 데이터를 모델과 정책 개선에 활용한다.
- Core를 재사용하고 Domain Module과 Provider Adapter를 교체할 수 있는 구조로 개발한다.

## 2. 핵심 원칙

1. **LLM과 Vision 모델은 분석하고, 정책 엔진과 담당자가 결정한다.**
2. **모델 서버는 Stateless이며 업무 DB에 직접 접근하지 않는다.**
3. **분석 결과는 덮어쓰지 않고 모델·프롬프트·정책 버전과 함께 보존한다.**
4. **장시간 AI 작업은 HTTP 요청에서 분리해 비동기로 처리한다.**
5. **초기 PoC에서는 자동 처리율보다 안전성, 검토시간 절감, 오버라이드율을 우선한다.**
6. **FastAPI로 빠르게 개발하되 Domain과 인프라 의존성은 분리한다.**

## 3. MVP 범위

### 포함

- 문의 텍스트·이미지·주문정보 접수
- LLM 기반 문의 구조화
- 이미지 품질 검사
- 기본 결함 Detection 또는 Segmentation
- 주장-증거 정합성 분석
- 기업 정책 기반 라우팅
- 상담원 승인·수정·이관
- 검토 보고서 생성
- 분석·정책·검토 이력 저장

### 제외

- AI 단독 고액 환불 승인
- 고객의 사기·허위 신고 확정
- 판매자·배송사 법적 책임 단독 판단
- 모든 상품군과 결함 유형의 범용 지원
- 상담원 개입 없는 완전 자동 처리

## 4. 기술 스택

| 영역 | 선택 |
|---|---|
| Backend | Python, FastAPI, Pydantic |
| ORM / Migration | SQLAlchemy 2, Alembic |
| Database | PostgreSQL, pgvector |
| Async Job | Celery, RabbitMQ |
| Object Storage | MinIO |
| LLM Serving | 별도 GPU 노드의 vLLM |
| Vision Serving | 별도 GPU 노드의 FastAPI, 안정화 후 Triton 검토 |
| Private Network | Tailscale |
| Deployment | Docker Compose |
| Test / Quality | pytest, Ruff, Pyright 또는 mypy |

Redis, Kafka, Kubernetes, Keycloak은 MVP 필수 구성요소가 아니다. 실제 요구가 발생할 때 도입한다.

## 5. 문서 구조

| 문서 | 내용 |
|---|---|
| [01_PROJECT_CHARTER.md](docs/01_PROJECT_CHARTER.md) | 문제, 고객, 가치, 범위, 가설 |
| [02_PRODUCT_REQUIREMENTS.md](docs/02_PRODUCT_REQUIREMENTS.md) | 기능·비기능 요구사항과 인수조건 |
| [03_ARCHITECTURE.md](docs/03_ARCHITECTURE.md) | 3-Node 배포 및 모듈형 아키텍처 |
| [04_DOMAIN_MODEL_AND_WORKFLOW.md](docs/04_DOMAIN_MODEL_AND_WORKFLOW.md) | Domain 모델, 상태 머신, 라우팅 규칙 |
| [05_API_AND_EVENT_CONTRACTS.md](docs/05_API_AND_EVENT_CONTRACTS.md) | HTTP API, Event, LLM·CV 계약 |
| [06_DATA_AND_ML_PLAN.md](docs/06_DATA_AND_ML_PLAN.md) | 데이터, 라벨, 모델, RAG, 평가 계획 |
| [07_DATABASE_DESIGN.md](docs/07_DATABASE_DESIGN.md) | 테이블, 버전, 인덱스, 권한 설계 |
| [08_SECURITY_AND_OPERATIONS.md](docs/08_SECURITY_AND_OPERATIONS.md) | 보안, 네트워크, 장애 대응, 운영 |
| [09_TESTING_AND_EVALUATION.md](docs/09_TESTING_AND_EVALUATION.md) | 테스트 전략과 PoC 성공 기준 |
| [10_ROADMAP_AND_BACKLOG.md](docs/10_ROADMAP_AND_BACKLOG.md) | Agile Sprint와 우선순위 Backlog |
| [11_MENTORING_DECISION_LOG.md](docs/11_MENTORING_DECISION_LOG.md) | 멘토링 질문, 결정, 후속 과업 기록 |
| [AGENTS.md](AGENTS.md) | Codex 등 코딩 에이전트 작업 규칙 |
| [ADR](docs/adr/) | 주요 아키텍처 의사결정 기록 |

## 6. 권장 저장소 구조

```text
csight/
├── app/
│   ├── main.py
│   ├── interface/
│   │   ├── http/
│   │   ├── workers/
│   │   └── events/
│   ├── application/
│   │   ├── create_case.py
│   │   ├── analyze_case.py
│   │   ├── evaluate_case.py
│   │   ├── review_case.py
│   │   └── generate_report.py
│   ├── platform/
│   │   ├── case/
│   │   ├── evidence/
│   │   ├── analysis/
│   │   ├── workflow/
│   │   ├── policy/
│   │   ├── decision/
│   │   ├── review/
│   │   ├── report/
│   │   ├── audit/
│   │   └── tenant/
│   ├── domains/
│   │   └── product_defect_cs/
│   ├── ports/
│   │   ├── llm.py
│   │   ├── vision.py
│   │   ├── storage.py
│   │   ├── repository.py
│   │   ├── message_queue.py
│   │   └── vector_store.py
│   ├── adapters/
│   │   ├── persistence/
│   │   ├── llm/
│   │   ├── vision/
│   │   ├── storage/
│   │   ├── messaging/
│   │   └── vector_store/
│   └── bootstrap/
├── alembic/
├── tests/
├── docs/
├── infra/
│   ├── compose.core.yml
│   ├── compose.llm.yml
│   └── compose.vision.yml
├── pyproject.toml
├── .env.example
├── AGENTS.md
└── README.md
```

## 7. 팀 역할

| 영역 | 주담당 |
|---|---|
| Backend API, Domain, DB | 차인택 |
| Celery·RabbitMQ·MinIO | 차인택 |
| RAG·정책 검색·LLM 연동 | 차인택 |
| vLLM 배포 및 운영 | 차인택 |
| Vision 서버 통합 및 계약 검증 | 차인택 |
| Vision 모델·데이터·학습·평가 | Vision 담당자 |
| 프론트엔드 | 팀 내 담당자 확정 필요 |
| 사업 가설·고객 인터뷰·PoC | 공동 |

## 8. 시작 순서

1. 문서의 Open Question과 멘토링 결정사항을 확정한다.
2. `Sprint 0`에서 저장소, Docker Compose, DB Migration, CI를 구성한다.
3. Case·Evidence CRUD와 MinIO 업로드를 구현한다.
4. RabbitMQ와 Celery 기반 분석 실행을 구성한다.
5. vLLM 문의 구조화 계약을 먼저 연결한다.
6. Vision API 계약을 확정하고 Mock → 실제 모델 순으로 연결한다.
7. 정책 엔진, 라우팅, 상담원 Review를 구현한다.
8. 보고서, Audit, KPI 측정을 추가한다.
9. Offline Evaluation → Shadow Mode → Limited PoC 순으로 검증한다.
