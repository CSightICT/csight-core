# CSight Runtime Memory Usage Baseline

이 문서는 CSight 로컬 PoC 런타임의 메모리 사용량을 서비스별로 기록하는 운영 기준선이다.
숫자는 부하 테스트 결과가 아니라 아래 시각에 실행 중이던 서비스의 **단일 시점 실측값**이다.

## 1. 기준점 요약

| 항목 | 값 |
|---|---:|
| 측정 시각 | 2026-08-28 16:28 KST |
| 호스트 물리 메모리 | 32 GiB |
| CSight 귀속 합계 | 약 4.21 GiB (4,312.87 MiB) |
| 호스트 물리 메모리 대비 | 약 13.16% |
| 모델 서비스 합계 | 약 3.23 GiB, CSight 합계의 76.6% |
| Docker Core 7개 합계 | 약 0.94 GiB, CSight 합계의 22.3% |
| 메모리 압력 여유 지표 | 80% |
| Swap | 측정 시점 swap-in/out 0 |

`memory_pressure`의 80%는 macOS가 계산한 압력 여유 지표이며, 물리 메모리의 80%가 완전히
비어 있다는 뜻은 아니다. 현재 스냅샷에서는 메모리 압력과 swap 징후가 없었다.

## 2. 서비스 그룹별 사용량

| 서비스 그룹 | 현재 사용량 | 전체 비중 | 상태와 해석 |
|---|---:|---:|---|
| Embedding endpoint | 약 1,732.5 MiB | 40.2% | MPS endpoint 1,723 MiB + helper 9.5 MiB; healthy |
| Vision E3 endpoint | 1,570 MiB | 36.4% | E3 checkpoint, MPS float32; healthy |
| Docker Core 7개 | 961.95 MiB | 22.3% | API, Worker, Dispatcher, DB, Broker, Object Storage, Web 모두 healthy |
| Cloudflare tunnel | 48.42 MiB | 1.1% | `doongdoong.org` 공개 터널 프로세스 |
| Reranker endpoint | 0 MiB | 0% | 현재 비활성, 8092 listener 없음 |
| Local LLM endpoint | 0 MiB | 0% | 현재 비활성, MLX server process 없음 |
| **합계** | **4,312.87 MiB / 4.21 GiB** | **100%** | 공유 page와 cache 때문에 시스템 전체 사용량과 정확히 일치하지 않을 수 있음 |

### 모델 메모리의 주요 구성

- Vision E3의 1,570 MiB 중 약 1,120 MiB가 MPS/graphics 영역이다. 이 프로세스에서 관측된
  physical-footprint peak는 2,935 MiB다.
- Embedding의 1,723 MiB 중 약 1,209 MiB가 MPS/graphics 영역이다. 이 프로세스에서 관측된
  physical-footprint peak는 1,767 MiB다.
- 따라서 단순 Python RSS만 보면 Apple 통합 GPU 메모리를 놓치므로, 모델 서비스는
  `footprint`의 physical footprint를 기준으로 기록한다.
- 두 peak는 각 프로세스의 개별 누적 최대값이며 같은 시점에 동시에 발생했다는 뜻은 아니다.

## 3. Docker Core 내부 구성

| 모듈 | 현재 사용량 | Docker Core 내 비중 | 역할 |
|---|---:|---:|---|
| Worker | 258.7 MiB | 26.9% | 비동기 분석·정책·검토·Resolution 작업 |
| MinIO | 153.2 MiB | 15.9% | 비공개 Evidence/Object 저장 |
| PostgreSQL | 149.3 MiB | 15.5% | 업무·감사·append-only 데이터 |
| API | 141.9 MiB | 14.8% | Core HTTP API |
| RabbitMQ | 131.9 MiB | 13.7% | 비동기 broker |
| Dispatcher | 117.8 MiB | 12.2% | durable outbox 전달 |
| Web | 9.152 MiB | 1.0% | React 정적 파일과 `/api` proxy |
| **합계** | **961.95 MiB** | **100%** | Docker cgroup 단일 시점 측정 |

Docker Desktop VM의 설정 상한은 약 7.65 GiB다. 이는 CSight가 현재 실제로 사용 중인 양이
아니며, 위 컨테이너 합계 약 0.94 GiB와 구분한다. Docker Desktop 자체의 host/VM overhead도
공유 page 중복 가능성 때문에 CSight 귀속 합계에는 더하지 않았다.

## 4. 판정과 다음 측정

현재 32 GiB 개발 환경에서는 CSight 귀속 사용량이 약 13%이고 메모리 압력도 낮아 내부 데모를
막는 수준은 아니다. 다만 모델 두 개가 전체의 약 76.6%를 차지하므로 다음 순서로 관찰한다.

1. 대표 10 Case 연속 처리 중 Vision·Embedding의 current/peak를 5초 간격으로 기록한다.
2. Worker concurrency를 바꾸지 않은 상태에서 API latency, queue depth, 실패율과 함께 비교한다.
3. Reranker 또는 Local LLM을 켤 때는 각각 별도 기준점을 먼저 만들고 동시에 활성화하지 않는다.
4. 10 Case 측정 뒤 모델 유휴 종료·필요 시 기동과 상시 적재 중 어느 방식이 데모 안정성에 맞는지
   결정한다.
5. 부하 구간 p95와 peak가 확보되기 전에는 운영 메모리 용량 또는 비용 절감 수치를 주장하지 않는다.

## 5. 측정 계약

- Docker 서비스: `docker stats --no-stream`의 container cgroup memory 사용량
- Host MPS 모델: macOS `footprint -p <pid>`의 `phys_footprint`
- 작은 helper/tunnel: `ps`의 RSS
- System headroom: `sysctl hw.memsize`, `memory_pressure`, `vm_stat`
- 모든 수치는 시각, 활성 서비스, 모델 device를 함께 기록한다.
- 공유 라이브러리, file cache, compressed memory, Docker VM accounting 때문에 서비스 합계는
  시스템 전체 resident memory와 산술적으로 정확히 일치하지 않는다.

다음 재측정에서는 이 문서의 기준점을 덮어쓰지 않고 아래에 날짜별 스냅샷을 append-only로
추가한다.

## 6. 스냅샷 로그

### 2026-08-28 16:28 KST — Idle/Ready Baseline

- Core 7개 healthy, Vision E3와 Embedding endpoint healthy.
- Vision device `mps`, precision `float32`, threshold `0.8984375`.
- Embedding device `mps`, model loaded, endpoint-reported allocated bytes 약 1.11 GiB.
- Reranker와 Local LLM은 실행하지 않음.
- 실제 Case batch, 동시 사용자, queue backlog를 가하지 않은 ready 상태 기준점.
