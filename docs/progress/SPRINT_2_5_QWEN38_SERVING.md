# Sprint 2.5 — Qwen3.8-27B 실제 서빙 검증

- 일자: 2026-08-26 (Asia/Seoul)
- Branch: `feature/sprint-2-5-qwen38-serving`
- Base: Sprint 2 Closeout `294cb5b`
- 현재 판정: `QUALIFIED_WITH_LIMITATIONS`
- Push·PR: 금지

## 1. 고정 경계

- Artifact `cyankiwi/Qwen3.8-27B-AWQ-INT4`와 revision
  `63768c10df38c0395e12ef49edac1bd539eaeeea`만 사용한다.
- Service name은 `csight-qwen3.8-27b`, text-only, non-thinking, strict structured output이다.
- Qwen Vision, Vision Stage, Alignment, Policy, Routing, Review, Report와 RAG는 범위 밖이다.
- 합성 데이터만 사용하고 Secret·Raw Prompt·Raw Response·Reasoning을 저장하지 않는다.

## 2. 환경 감사

| 항목 | 실제 값 |
|---|---|
| OS | Ubuntu 22.04, kernel 6.8.0-136-generic |
| GPU | NVIDIA GeForce RTX 4090 |
| VRAM | 24,564 MiB |
| Driver / CUDA | 580.173.02 / 13.0 |
| RAM | 62 GiB total, 감사 시 47 GiB available |
| Disk | 916 GiB total, 감사 시 344 GiB available |
| Docker | Client/Server 29.5.3 |
| NVIDIA container toolkit | `nvidia-container-cli` 1.19.1, NVIDIA runtime 확인 |
| Python | Host 3.10.12; vLLM image Python 3.12 |
| 기존 GPU 작업 | Compute process 없음; 기존 Container를 종료하지 않음 |
| Network | 기존 private/Tailscale 연결 사용; 공인 Port 개방 없음 |
| Port | 기존 8000 listener 보존, 전용 private port 18000 선택 |

## 3. Artifact와 런타임 감사

- Hugging Face API로 revision, Apache-2.0 license, 21,041,255,795 byte 파일 합계와 다섯
  Safetensors shard를 확인했다.
- Config는 `Qwen3_5ForConditionalGeneration`, `qwen3_5`, `compressed-tensors` packed
  asymmetric INT4 group size 32다.
- vLLM image는 `0.26.0` tag와 digest를 모두 고정했다. 실제 image 내부는 Transformers
  5.14.1, PyTorch 2.11.0+cu130이다.
- 실제 `vllm serve --help=all`에서 revision, language-model-only, max length/sequences,
  GPU utilization, FP8 KV cache, eager, reasoning parser, default chat kwargs와 API 인증 옵션을
  확인했다.
- 시작 로그에서 revision, `quantization=compressed-tensors`, max length 8192,
  `language_model_only=True`와 multimodal modality limit 0을 확인했다.

## 4. 보안 관측과 조치

- 초기 후보는 `--api-key` CLI 인자를 사용했다. 준비 전 process audit에서 Secret이 명령행에
  나타나는 것을 발견해 해당 일회용 key를 즉시 폐기·회전하고 Container를 제거했다.
- vLLM `0.26.0` 소스가 `VLLM_API_KEY`를 지원함을 확인한 뒤 Compose에서 CLI 인자를 제거하고
  환경변수 주입으로 변경했다. 재시작 process command에 Secret이 없음을 검증했다.
- Endpoint는 private Tailscale 주소에만 publish하고 Public wildcard publish를 사용하지 않는다.

## 5. 합성 평가셋

| 범주 | 건수 |
|---|---:|
| 명확한 단일 결함 | 40 |
| 복수 결함 | 20 |
| 위치 모호 | 15 |
| 고객 요청 없음 | 10 |
| 결함 불명확 | 5 |
| 장문·오탈자·구어체 | 5 |
| Prompt injection | 5 |
| 합계 | 100 |

모든 행은 요구된 issue/action/missing information/source quote/forbidden output Gold를
포함하며 애매한 문항에는 `manual_review` 또는 `acceptable_answers`를 사용한다.

## 6. 실행 원장

| 시각·검사 | 결과 |
|---|---|
| Sprint 2 Closeout Commit | PASS — `294cb5b`, Push·PR 없음 |
| Branch 생성 | PASS — `feature/sprint-2-5-qwen38-serving` |
| GPU·Disk·RAM·Docker·Network 감사 | PASS — 다른 작업 중단 없음, private port 확보 |
| Artifact revision/API 감사 | PASS — immutable revision과 quantization 확인 |
| vLLM image pull | PASS — `0.26.0` digest 고정 |
| 실제 CLI option audit | PASS — 후보 Profile 옵션 지원 확인 |
| Local Compose 해석 | PASS |
| vLLM Adapter contract | PASS — 21 passed, non-thinking request assertion 포함 |
| 평가셋 구조·분포 | PASS — 100건, 40/20/15/10/5/5/5 |
| `/v1/models`·Text-only·Thinking off | PASS — model name 일치, reasoning 누출 0 |
| Cold start 재현 | PASS — 최초 8m06s, cache-hit 97s; 동일 Serve Profile |
| Stability | PASS — 26m19s, restart/OOM/error 0 |
| Quality Prompt 1.0.0 | FAIL — Pydantic 98%, duplicate issue type 2건 |
| vLLM `uniqueItems` 실험 | FAIL — HTTP 400, grammar keyword 미지원 |
| Quality Prompt 1.0.1 | PASS safety gate — 100건, issue F1 0.95 |
| Human spot-check | PASS safety 20/20; issue 19/20, action 10/20, missing 8/20 |
| Performance A/B/C/D | PASS — 요청 10/10/5/5, Timeout/OOM/Schema 실패 0 |
| External vLLM | PASS — 5 passed, 322 deselected, Skip 0 |
| Real Backend E2E | PASS — 실제 Qwen 성공 Run 10, Result 10, Attempt 10 |
| Duplicate delivery | PASS — 완료 Task 재전달 후 Result 1, Attempt 1 |
| Timeout retry | PASS — Timeout Retry 후 Attempt 2에서 Max Retry 종결 |
| Cleanup | PASS — 합성 Case/Run 22, Attempt/Outbox 23, Result 10 정리; Queue/Orphan 0 |
| Final Core runtime | PASS — 6개 Healthy, Worker Provider `mock` 복구 |
| Static/regression | PASS — Ruff, Format 162, Pyright 0, Fast 291, Integration 31 |

## 7. 완료 체크리스트

- [x] Sprint 2 Closeout Gate와 로컬 Commit
- [x] 새 Branch 생성, 사용자 Kaputt 파일 미수정·미Stage
- [x] GPU 환경과 기존 Service read-only 감사
- [x] Artifact revision·license·quantization 확인
- [x] vLLM/Transformers/CUDA/Driver version 고정
- [x] private bind와 API 인증 자산
- [x] text-only와 non-thinking 서버·요청 이중 설정
- [x] 100건 합성 Dataset과 평가기
- [x] `/v1/models`, warm-up, Structured Output
- [x] 두 번 Cold Start와 20분 Stability
- [x] 100건 품질·안전 평가와 20건 Spot-check
- [x] 성능 Profile A–D와 VRAM 측정
- [x] 기존 external GPU 5건 Skip 0
- [x] 실제 Backend E2E 10건, Metadata·Append-only·Retry·Duplicate 확인
- [x] 합성 Data·Queue 정리와 최종 Core/LLM Health
- [x] 전체 정적·회귀·문서 Gate
- [x] 승인된 범위를 이 문서를 포함한 로컬 Commit으로 확정; Push·PR 없음

## 8. 미해결·다음 작업

- Model card에 calibration dataset 설명이 없어 Known Limitation으로 유지한다.
- Action Accuracy 0.23, Missing Information F1 0.00이므로 Human Review 없이 Workflow 결정을
  자동화하지 않는다. 실제 고객 분포 반입 전 개인정보·Retention과 별도 Evaluation을 승인한다.
- VRAM Peak 23,825 MiB로 24GB 여유가 매우 작다. Context·동시성·CUDAGraph 변경은 별도
  requalification 대상이다. CPU Offload는 사용하지 않았다.
- 다음 작업은 `git log -1`의 로컬 Commit SHA를 인계하고 Push·PR 없이 Sprint 3 계약을
  준비하는 것이다.

## 9. 실제 성능 Profile

| Profile | 성공 | TTFT p50 / p95 | Latency p50 / p95 | Output token/s |
|---|---:|---:|---:|---:|
| A: short, concurrency 1 | 10/10 | 0.089 / 0.176s | 1.470 / 1.558s | 36.36 |
| B: short, concurrency 2 | 10/10 | 1.542 / 1.672s | 2.931 / 3.062s | 35.70 |
| C: long, concurrency 1 | 5/5 | 0.534 / 0.540s | 2.475 / 2.487s | 36.11 |
| D: injection, concurrency 1 | 5/5 | 0.090 / 0.097s | 2.268 / 2.272s | 35.88 |

Profile B는 안정적이지만 queue 대기로 latency가 두 배가 되어 초기값은 Sequence 1과 Celery
직렬화를 유지한다. 측정 중 Timeout, OOM, Schema failure는 모두 0이었다.

## 10. Backend E2E 감사

- Provider/Model/Revision/Prompt Snapshot은 10개 모두
  `vllm` / `csight-qwen3.8-27b` / 고정 Artifact revision / Prompt `1.0.1`로 일치했다.
- 성공 Run 10, Result 10, Attempt 10, Run당 Result 최대 1이었다.
- 준비 과정에서 API/Worker Prompt 또는 Provider Snapshot이 불일치한 11 Run은 실제 호출 전
  `LLM_PROVIDER_REQUEST_REJECTED`로 거부되어 version fencing을 확인했다.
- 별도 Timeout Run은 Attempt 1 `LLM_PROVIDER_TIMEOUT/RETRY_WAITING`, Attempt 2
  `ANALYSIS_MAX_RETRIES_EXCEEDED/FAILED`였다.
- Analysis 관련 Table의 Raw Prompt/Response/Reasoning Column 0, unsafe Outbox payload 0을
  실제 DB Schema/Data에서 확인했다.
- 검증 후 합성 Data와 Queue를 정리하고 Core는 Network-free Mock 기본값으로 복구했다.
