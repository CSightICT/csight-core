# macOS 제어 앱의 GX10 내부 Q5 엔진

2026-09-10 추가. 이 경로는 ADR-0002/0012/0103/0113/0125의 독립 모델·비공개 인증·
승격 금지 경계를 유지한다. 고객 파일럿과 PRIMARY 모델 경로가 아니다.

## 고정 프로필

- 모델: 기존 CSight Qwen3.8-27B Q5_K_S, 18,679,614,080 bytes,
  SHA-256 `d709a46e48db256ac0bb3eee7fb2cdcfd087820eb4701b1af5dda84db41a2219`.
- 이미지: 기존 ARM64/CUDA13 llama.cpp b10419,
  `sha256:b664e8d60f09f87d062319bdb94ca8e8cf04ceba69ed08a5f3b08fb8ba579ac4`.
- 앱 전용 컨테이너: `csight-gx10-desktop-q5`, 계약 `q5-internal/1.0.1`.
- 문맥 4096, 동시성 1, Q8_0 K/V, full GPU offload, reasoning off, Web UI/요청 로그 off.
- GX10 loopback `127.0.0.1:18003`에만 노출하고 API 인증 필수. Mac은 SSH로 상태와
  합성 canary를 실행한다. Mac HTTP tunnel과 Core 모델 경로는 추가하지 않는다.
- 인증 없는 실제 추론은 HTTP 401을 확인했다. `/v1/models` 메타데이터는 인증 없이
  200인 현재 binary 동작이며, 이것을 인증 검증 성공으로 사용하지 않는다.
- 모델 읽기 전용 mount, 비루트 UID/GID, read-only rootfs, no-new-privileges,
  capability 제거, CPU cgroup 메모리 32GiB·추가 swap 금지. 기존 이미지 pull 금지.
- GPU unified memory는 cgroup만으로 제한된다고 가정하지 않는다. 기동 전 시스템
  MemAvailable 40GiB 이상, 로딩 중·canary 후 16GiB 이상을 별도 검사한다. 이 수치는
  GPU 전용 여유가 아니며 향후 부하나 외부 작업에 대한 OOM 방지 보증도 아니다.

## 실행·정지 경계

`scripts/csight_gx10_desktop.sh {status|start|stop}`는 검토된 Python 소스만 SSH 표준입력으로
전달한다. `.env`, 비밀번호, 고객 데이터, 모델 파일은 전송하지 않는다. DNS 이름은 기존에
신뢰한 GX10 host key alias로 검증하며 키/호스트 변경 시 자동 수락하지 않고 실패한다.

원격 기존 `runtime/gx10-q5-bench-4k-c1-v2.env`의 API key만 읽고 출력하지 않는다.
docker 인자 대신 자식 환경으로 전달한다. API 요청 원문·응답은 기록하지 않고 모델 alias와
합성 JSON 일치 여부만 반환한다. 이것은 의미 품질, Grounding, Query Builder 평가가 아니다.

시작·정지·상태는 전용 lock으로 직렬화한다. 기존 컨테이너는 label뿐 아니라 이미지·명령·
사용자·키·mount·네트워크·포트·메모리 설정도 대조한다. 불일치 시 재사용/정지하지 않는다.
실패한 신규 기동은 자신이 시작한 정확한 컨테이너만 정지한다. 컨테이너·로그는 보존하며,
기존 정상 서비스·ComfyUI·NVFP4·4090을 제거하거나 대체하지 않는다.

앱의 빠른 시작과 재빌드 후 시작 모두 내부 Q5를 확인한다. GX10 실패는 전체 시작 실패로
표시하되 이미 정상인 Core를 내리지 않는다. 정지는 GX10 확인 실패 시 나머지도 보존한다.
기동 시 canary는 소량의 합성 입력 한 건이며 상태 조회는 추론하지 않는다.

## 앱 오류 대응과 복구

기존 -1712는 관측됐지만 warm 상태 조회에서는 재현되지 않았다. 후속 빠른 시작에서는
서비스/canary가 성공한 뒤 앱이 `StandardAdditions → AEInteractWithUser`에서 대기하며 창이
보이지 않는 현상을 재현했다. 앱을 앞으로 가져오자 완료 창이 나타났다. 새 앱은 결과/오류
표시 전에 명시적으로 활성화한다. 과거 오류의 모든 경로를 확정했다는 주장은 하지 않는다.
UI 대기는 명시적으로 제한하고 선택적 알림은 3초 이내 실패해도 계속하며 결과/오류 창은
60초 후 닫는다. 서버 수명과 창 수명은 독립적이다.

원본 앱 전체를 별도 백업하고 main.scpt만 갱신한 뒤 기존 식별자/권한 메타데이터를 유지해
로컬 서명을 갱신한다. 최신 검증 JSON에 백업 경로와 실제 GUI 검증을 기록한다. 되돌릴 때는
앱을 닫은 후 해당 백업을 새 경로에 복사해 비교하고 복구한다. 모델 정지는 위 `stop`만
사용한다. 데이터 볼륨 삭제·Docker prune·포괄적인 GPU kill은 복구 절차가 아니다.

첫 개발 시도는 reasoning `none`을 현재 binary가 거부해 exit 1이었다. `off`로 수정했으며
실패 컨테이너는 별도 이름으로 보존했다. 과거 성공 프로필이나 failed evidence는 덮어쓰지 않는다.
실측·미실행 항목은 `docs/progress/SERVER_CONTROL_FIX_VERIFICATION_2026-09-10.json`을 본다.
