# ADR-0016: Partial Success Semantics

- 상태: Accepted
- 일자: 2026-08-26

## Context

Multimodal Run의 한 Stage 실패가 이미 검증·저장된 다른 Stage 결과를 삭제해서는 안 된다.
동시에 부분 결과를 전체 성공이나 자동 결정으로 오인해서도 안 된다.

## Decision

| Text | Vision | Run |
|---|---|---|
| `SUCCEEDED` | `SUCCEEDED` | `SUCCEEDED` |
| `SUCCEEDED` | `FAILED` | `PARTIAL_SUCCESS` |
| `FAILED` | `SUCCEEDED` | `PARTIAL_SUCCESS` |
| `FAILED` | `FAILED` | `FAILED` |

- `QUEUED` 또는 `RUNNING` Stage가 있으면 Run은 `RUNNING`이다.
- Terminal Stage와 `RETRY_WAITING` Stage가 섞이면 Run은 `RETRY_WAITING`이다.
- 성공한 Stage Result는 다른 Stage 실패/재시도와 독립된 append-only record로 유지한다.
- `PARTIAL_SUCCESS`는 Policy/Approval 후보가 아니며 향후 Review 입력일 뿐이다.

## Consequences

부분 분석 가치는 보존하면서 실패 사실을 API `failed_stages`에 드러낸다. Run failure metadata는
모든 Stage가 실패한 `FAILED`에만 aggregate failure로 기록한다.
