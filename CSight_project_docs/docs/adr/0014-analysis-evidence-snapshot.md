# ADR-0014: Analysis Evidence Snapshot

- 상태: Accepted
- 일자: 2026-08-26

## Context

Analysis Run 시작 뒤 Case에 Evidence가 추가될 수 있다. Worker가 실행 시점의 Case 목록을 다시
사용하면 동일 Run의 입력이 바뀌고 결과를 재현할 수 없다.

## Decision

- Multimodal Run 생성 트랜잭션에서 당시 `AVAILABLE` Image Evidence를
  `analysis_run_evidence`에 저장한다.
- Snapshot은 `position`, `evidence_id`, `sha256`를 보존하며 순서는 Evidence repository의
  `created_at`, `id` 안정 정렬을 따른다.
- Worker는 Snapshot만 읽고 private Object Storage에서 bounded read 후 SHA-256을 재검증한다.
- Run 이후 추가 Evidence는 기존 Snapshot을 바꾸지 않으며 재분석은 새 Run으로 수행한다.
- AVAILABLE 이미지가 없으면 Run을 만들지 않고 `IMAGE_EVIDENCE_REQUIRED`로 거부한다.

## Consequences

입력 집합과 순서가 재현 가능하다. Evidence/Object 유실이나 digest 불일치는 명시적 Vision
failure가 되며 Signed URL이나 Storage credential을 Queue/Provider에 전달하지 않는다.
