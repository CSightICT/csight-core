# CSight GX10 모델 엔진 전환 세션 인계

> 작성 시각: 2026-09-01 23:37 KST  
> 저장소: `/Users/ckdlsxor/Desktop/CSight_proejct`  
> 목적: 새 Codex 세션이 긴 대화 기록 없이도 RTX 4090 기준선과 신규 ASUS GB10 장비를
> 안전하게 이어서 검증하도록 한다.

## 1. 새 세션에 그대로 붙여 넣을 시작 프롬프트

```text
CSight AI 엔진 작업을 이어서 진행해줘.

먼저 다음 문서를 순서대로 완전히 읽고, 문서의 사실을 현재 장비 상태로 오해하지 말고
읽기 전용 확인부터 해줘.

1. CSight_project_docs/AGENTS.md
2. docs/progress/CURRENT_STATUS.md
3. docs/progress/SESSION_HANDOFF_2026-09-01_GX10_MODEL_ENGINE.md
4. CSight_project_docs/docs/adr/0002-separate-inference-nodes.md
5. CSight_project_docs/docs/adr/0113-rtx4090-qwen-candidate-release-gate.md
6. CSight_project_docs/docs/adr/0125-csight-gguf-quantization-and-llama-cpp-shadow-runtime.md
7. docs/llm/QWEN4090_GGUF_DEV_SELECTION_RUNBOOK.md

이번 세션의 우선 목표는 Tailscale 장비 `gx10-ade1`의 실제 하드웨어·OS·CUDA·디스크·
네트워크 상태를 비파괴적으로 확인하고, Mac에서 GX10을 직접 제어하는 토큰 효율적인
llama.cpp 실행 구조를 설계·구현하는 것이다. 먼저 계획과 현재 관측을 짧게 보고한 뒤
안전한 범위에서 계속 진행해줘.

중요 경계:
- `gx10-ade1`이 ASUS Ascent GX10/GB10일 것으로 예상하지만 실제 인벤토리 전에는 확정하지 않는다.
- 비밀번호를 요청·입력·문서화하지 않는다. 기존 대화에 나온 Credential도 재사용하지 않는다.
- 원격 접속이 인증을 요구하면 사용자가 직접 인증하도록 멈추고, Secret 없는 설정만 안내한다.
- 현재 작업트리는 미커밋 변경이 많다. 기존 변경을 덮어쓰거나 정리하지 않는다.
- 사용자 소유 문서, 원본 이미지, checkpoint, Docker volume과
  `kaputt_best_vision_architecture.md`를 수정·삭제·stage하지 않는다.
- 별도 요청 전에는 Commit·Push·PR·develop/main 병합을 하지 않는다.
- 4090의 기존 VLM/Counsel 서비스는 보호한다. 임의로 중단하지 않는다.
- 모델과 정책은 권고만 생성한다. 실제 환불·메일·결제·배송·CRM 동작은 만들지 않는다.
- sealed Test, freeze, Shadow 승격, PRIMARY 전환은 현재 금지다.

실행 순서:
1. Mac 저장소의 branch/HEAD/dirty 상태와 Tailscale에서 `gx10-ade1`의 도달 가능성만 확인한다.
2. GX10에 변경을 가하지 않고 CPU architecture, GB10/GPU, 128GB memory 여부, NVMe 여유,
   OS, kernel, driver, CUDA, Docker/Container Toolkit, Tailscale 주소, 10GbE, 온도·전력을 조사한다.
3. 결과를 원문 장문 로그가 아니라 Secret/PII 없는 작은 JSON과 Markdown 요약으로 남긴다.
4. `status`, `prepare`, `serve`, `canary`, `evaluate`, `report`, `stop`으로 나뉜 GX10 실행기를
   설계한다. 정상 출력은 compact JSON, 상세 로그는 원격 파일, 실패 시에만 bounded tail을 쓴다.
5. 코드/스크립트는 Mac을 기준점으로 동기화하되, 대형 GGUF/BF16/imatrix는 Mac을 경유하지 않고
   Khrin RTX 4090 노드에서 GX10으로 직접 전송하는 계획을 세운다. 실제 전송 전 SHA-256, 대상 경로,
   필요 공간과 회수 가능성을 먼저 제시한다.
6. ARM64 + CUDA 13 + Blackwell(sm_121)용 pinned llama.cpp를 별도 이미지로 빌드한다.
   기존 x86_64/CUDA 12.8 이미지의 자격을 승계하지 않는다.
7. 동일 Q5_K_S, 동일 prompt/schema/context/concurrency로 GX10 canary와 Dev benchmark를 실행한 뒤
   4090 기준선과 TTFT, decode tok/s, p50/p95, peak unified memory, 4K/16K/32K context,
   concurrency 1/2/4, 온도와 안정성을 비교한다.
8. 비교가 끝난 뒤에만 GX10의 역할을 Model Lab/SHADOW 또는 PRIMARY 후보 중 하나로 판단한다.
   기본 예상 역할은 Model Lab/SHADOW이고, 4090은 현재 저지연 기준선으로 유지한다.
9. 27B BF16 기준선과 소규모 QLoRA feasibility는 Q5 비교 다음 단계다. 전체 fine-tuning은 범위 밖이다.
10. Query Builder는 frozen RAW→HYBRID 기준선을 Recall@10, exact coverage, MRR@10, nDCG@10
    모두 이기는 경우에만 후보가 된다. 못 이기면 SHADOW에 남기고 RAW를 기본으로 유지한다.

각 단계 후 CURRENT_STATUS.md의 검증 상태, 미해결 사항, 다음 행동과 append-only 세션 로그를
실측값으로 갱신해줘. 실행하지 않은 검사는 PASS로 쓰지 말아줘.
```

## 2. 현재 확정된 상태

### 저장소

- Branch: `codex/operator-console-product-direction`
- HEAD: `f2357ba0cee6`; 같은 원격 기능 브랜치와 일치한다.
- GGUF/runtime/evaluator 관련 변경은 미커밋 상태다.
- Commit·Push·PR·`develop/main` 병합은 이번 인계 작성 시점까지 추가로 수행하지 않았다.
- clean RC worktree `/Users/ckdlsxor/Desktop/CSight_rc_cd6471c`와 기존 데모/RC volume은 보존한다.

### RTX 4090 모델 기준선

- 호스트 별칭: Khrin. 정확한 주소·사용자명·Credential은 이 문서에 기록하지 않는다.
- 모델: CSight-owned Qwen3.8-27B Q5_K_S GGUF.
- GGUF 크기: `18,679,614,080` bytes.
- GGUF digest: `sha256:d709a46e48db256ac0bb3eee7fb2cdcfd087820eb4701b1af5dda84db41a2219`.
- clean imatrix digest:
  `sha256:8d1de26320c4ccafc238fabc337b822c37051b1ebdf9ae65043c5a3657c4d40f`.
- pinned llama.cpp: `b10419`.
- 4090 runtime image digest:
  `sha256:c85eec9b41ccfc14d596946085125577dae0066d23f1dee4491a5c3a5cd618ef`.
- 현재 이미지는 x86_64/CUDA 12.8 계열이므로 ARM64 GX10에 그대로 재사용하지 않는다.

### 실제 synthetic Dev 결과

- Extraction: guarded `local.8`, canonical gate `15/15 PASS`.
  - 120/120 구조·Pydantic·정확 인용
  - issue F1 `0.987448`
  - requested-action F1 `0.976744`
  - ambiguity F1 `1.0`
  - p95 `4,908.237 ms`
  - throughput `40.432121 tok/s`
  - 안전 위반 0
- Grounding: runtime prompt `1.1.0-local.2`, canonical gate `25/25 PASS`.
  - 정상 40/40, 공격 20/20
  - citation/fact/unresolved/replay `1.0`
  - 안전 위반 0
  - 정상 이중 replay 포함 p95 `7,985.891 ms`
  - 공격 p95 `3,517.389 ms`
- Query Builder: frozen `RAW → HYBRID` 기준선을 이기지 못했다.
- 전체 판정: `NO_WINNER`, `NO_RELEASE_ELIGIBLE`.
- Extraction QLoRA와 Grounding 추가 튜닝은 현재 보류다.
- sealed Test·freeze·Shadow100·PRIMARY·route activation·실제 사업 동작은 모두 0이다.

## 3. 신규 GX10에 대해 아는 것과 모르는 것

### 사용자가 제공한 정보

- GB10 기반 DGX Spark 계열의 ASUS 장비를 새로 확보했다.
- Tailscale 장비 이름은 `gx10-ade1`이다.
- 사용자는 llama.cpp를 선호하며 Ollama는 제거한 상태다.
- 목표는 Mac을 제어석으로 사용하고 4090과 GX10을 직접 제어해 반복 대화와 긴 로그로 인한
  Codex 컨텍스트 사용을 줄이는 것이다.

### 아직 확인하지 않은 정보

- 정확한 ASUS 제품명과 SKU
- 128GB unified memory의 실제 인식 상태
- NVMe 용량·가용 공간과 파일시스템
- CPU architecture, OS image, kernel, firmware
- NVIDIA driver, CUDA, Container Toolkit, Docker 상태
- Tailscale SSH 또는 일반 SSH의 실제 접근 가능 여부
- 온도·전력·네트워크 상태
- llama.cpp ARM64/Blackwell build 가능 여부와 Qwen3.8 호환성
- 기존 파일·서비스·사용자 데이터 존재 여부

따라서 GX10에 모델을 복사하거나 패키지를 설치하기 전에 읽기 전용 인벤토리를 먼저 수행한다.

## 4. 장비 역할에 대한 현재 권고

```text
Mac
 ├─ CSight Core/API/DB/Web/Queue
 ├─ 평가 orchestration
 └─ compact 결과 수집

RTX 4090 Khrin
 ├─ 검증된 Q5 저지연 기준선
 ├─ 기존 VLM/Counsel 서비스 보존
 └─ GX10 비교가 끝날 때까지 PRIMARY 후보 기준 장비

ASUS GX10 / gx10-ade1
 ├─ 27B BF16 기준선
 ├─ Q4~Q8 양자화 비교와 clean imatrix
 ├─ 27B QLoRA feasibility
 ├─ 70B급 quantized 실험
 ├─ 긴 context와 multi-model 동시 적재
 └─ 기본 역할: Model Lab + SHADOW
```

GB10의 128GB unified memory는 연구 가능한 모델 크기와 동시 적재 능력을 크게 늘리지만,
273 GB/s급 메모리 대역폭과 초기 ARM64 생태계 때문에 4090보다 decode latency가 빠르다고 가정하지
않는다. 27B BF16 가중치는 약 54GB라 실행 기준선은 가능하지만, gradients와 optimizer state를 포함한
27B full fine-tuning은 여전히 범위 밖이다. 4-bit QLoRA는 유력한 후보지만 실제 batch/context/속도는
측정 전에는 보장하지 않는다.

공식 참고:

- NVIDIA DGX Spark hardware:
  <https://docs.nvidia.com/dgx/dgx-spark/hardware.html>
- NVIDIA GB10 porting guide:
  <https://docs.nvidia.com/dgx/dgx-spark-porting-guide/overview.html>
- NVIDIA release notes:
  <https://docs.nvidia.com/dgx/dgx-spark/release-notes.html>
- ASUS Ascent GX10 datasheet:
  <https://dlcdnwebimgs.asus.com/files/media/202506/5c0fb57c-4e48-4e96-8c97-04bf8df2677c/asus-ascent-gx10-datasheet.pdf>

## 5. Codex 컨텍스트 사용을 줄이는 실행 계약

원격 실행기는 정상 상태에서 장문 로그를 stdout으로 내보내지 않는다.

```json
{
  "schema": "csight_gx10_run_summary/1.0.0",
  "host": "gx10-ade1",
  "phase": "benchmark",
  "candidate_id": "qwen38-27b-csight-q5-k-s-llama-cpp",
  "status": "PASS_OR_FAIL",
  "ttft_ms_p95": null,
  "latency_ms_p95": null,
  "decode_tokens_per_second": null,
  "peak_unified_memory_bytes": null,
  "errors": [],
  "report_digest": "sha256:..."
}
```

- 전체 로그: GX10의 owner-only 디렉터리에 보존한다.
- 정상 출력: 위와 같은 compact JSON 한 건만 반환한다.
- 실패 출력: 안정적인 오류 코드와 마지막 bounded log tail만 반환한다.
- 재실행: 같은 결과 파일을 덮어쓰지 않고 새 run ID와 새 디렉터리를 사용한다.
- 상태 확인: 프로세스 이름이나 PID만 믿지 않고 health/model identity/checksum을 함께 확인한다.
- 결과 비교: 4090과 GX10 결과를 동일 schema의 작은 JSON으로 맞춘다.
- Secret·원문 inquiry·provider raw response·전체 경로는 요약에 기록하지 않는다.

## 6. 권장 구현 묶음

다음 세션에서 한 번에 모든 모델 실험을 시작하지 않는다.

### A. 읽기 전용 GX10 인벤토리

- Mac에서 `gx10-ade1` 도달 가능 여부를 확인한다.
- 원격 상태를 변경하지 않고 hardware/runtime/storage/network 정보를 수집한다.
- 결과를 `gx10_inventory/1.0.0` JSON으로 정규화한다.
- 이 단계에서는 install, upgrade, reboot, Docker prune, 모델 전송을 하지 않는다.

### B. GX10 실행기 계약

- `status`, `prepare`, `serve`, `canary`, `evaluate`, `report`, `stop`을 분리한다.
- `prepare`의 package install/build 같은 변경은 인벤토리와 계획 검토 후 실행한다.
- 종료 trap과 stale process 검사를 둔다.
- owner-only runtime env를 사용하고 저장소 `.env`를 복사하지 않는다.

### C. 코드와 대형 산출물 이동

- 코드/스크립트: reviewed source bundle 또는 Git 기준으로 동기화한다.
- 현재 모델 스크립트가 미커밋이므로 원격 branch만 clone하면 동일 상태가 되지 않는다.
  먼저 Secret·대형 파일·사용자 소유 파일을 제외한 전송 범위를 검토한다.
- GGUF/BF16/imatrix: Khrin에서 GX10으로 직접 보낸다. Mac에 중복 보관하지 않는다.
- 복사 전후 SHA-256과 byte size를 비교한다.
- 기존 파일을 overwrite하지 않고 content-addressed/owner-only 경로를 사용한다.

### D. 동일 Q5 비교

- 첫 비교는 모델·prompt·schema·context 4096·concurrency 1을 고정한다.
- canary가 성공한 뒤에만 context 4K/16K/32K와 concurrency 1/2/4를 측정한다.
- health/canary 성공과 Dev quality PASS를 분리한다.
- GX10 결과가 느리더라도 실패로 단정하지 않고 Model Lab 역할 적합성을 별도로 판단한다.

### E. 이후 단계

1. 27B BF16 기준선으로 양자화 품질 손실을 측정한다.
2. Extraction/Grounding은 현재 Dev PASS를 보존하고, 새 문제가 입증될 때만 QLoRA를 검토한다.
3. Query Builder의 목적·필터 오류와 실제 retrieval 지표를 먼저 분리 진단한다.
4. Query Builder가 RAW 기준선을 이기지 못하면 모델 크기와 무관하게 SHADOW에 남긴다.

## 7. 이번 인계 작성 시 검증한 것

- `PASS`: 저장소 경로, branch, HEAD, 원격 기능 브랜치 일치 여부를 읽기 전용으로 확인했다.
- `PASS`: 현재 dirty worktree와 사용자 소유 미추적 파일이 있음을 확인했다.
- `PASS`: candidate matrix의 Q5/imatrix/runtime digest를 현재 파일에서 재확인했다.
- `PASS`: Accepted ADR-0002, ADR-0113, ADR-0125와 Qwen4090 runbook을 다시 읽었다.
- `NOT_RUN`: `gx10-ade1` Tailscale 도달성 및 SSH.
- `NOT_RUN`: GX10 hardware/OS/CUDA/Docker inventory.
- `NOT_RUN`: 파일·스크립트·모델 전송.
- `NOT_RUN`: ARM64 llama.cpp build, canary, benchmark, QLoRA.
- `NOT_RUN`: 이번 문서 작성에 대한 전체 backend/Web/GPU 회귀. 행동 변경이 없는 문서 작업이다.

## 8. 다음 세션의 첫 완료 조건

다음 세션의 첫 작은 완료점은 모델 실행이 아니라 아래 네 가지다.

1. `gx10-ade1`의 실제 인벤토리를 compact JSON으로 확보한다.
2. 기존 GX10 상태를 변경하지 않았음을 확인한다.
3. ARM64 llama.cpp 빌드·스크립트 이동·모델 직접 전송 계획에 정확한 경로, 크기, checksum,
   rollback을 적는다.
4. 사용자의 확인이 필요한 파괴적/대용량 단계와 자동으로 진행 가능한 단계를 분리한다.

그 다음에만 GX10 실행기 구현과 동일 Q5 canary로 진행한다.
