# PoC readiness evidence manifest

`current_gate.json`은 실제 고객 PoC 승격에 필요한 증거의 존재 여부만 기록한다. 고객 원문,
개인정보, 정책 원문이나 접근 토큰은 이 디렉터리에 저장하지 않는다. `evidence_ref`에는 승인된
증거 원장의 불투명 식별자나 비민감 경로만 기록한다.

기본 명령은 현재 판정을 출력하며 미충족 상태도 정상적으로 보고한다.

```bash
make verify-poc-readiness
```

승격 Gate에서는 하나라도 미충족이면 실패 코드로 종료한다.

```bash
make require-limited-poc
```

현재 manifest는 실제 고객·정책·Case·Vision·Shadow Mode 증거가 없음을 명시하므로 판정은
`SYNTHETIC_MOCK_SIMULATION_DEMO`다. 체크 값을 근거 없이 바꾸어서는 안 된다.
