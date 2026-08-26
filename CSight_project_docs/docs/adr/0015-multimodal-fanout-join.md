# ADR-0015: Multimodal Fan-out과 Join

- 상태: Accepted
- 일자: 2026-08-26

## Context

Text와 Vision은 서로의 결과를 입력으로 요구하지 않는다. Celery chord를 상태의 Source of
Truth로 만들면 Broker 복구와 업무 상태가 결합된다.

## Decision

- Pipeline `product_defect_multimodal_analysis` `1.0.0`은 독립적인
  `TEXT_EXTRACTION`, `VISION_ANALYSIS` Stage와 Outbox Event를 같은 트랜잭션에 만든다.
- Queue payload는 기존 여섯 reference ID만 포함하며 Binary, Signed URL, Evidence object key와
  credential을 포함하지 않는다.
- Worker entry point는 Stage type을 조회해 Application use case로 라우팅한다.
- 각 Stage가 상태를 변경할 때 PostgreSQL의 모든 Stage 상태로 Run을 재계산한다.
- 한 Vision Stage가 Snapshot 이미지들을 안정 순서로 처리하고 이미지별 Result를 append한다.

## Consequences

Text와 Vision은 순서 강제 없이 fan-out되고 Celery chord 없이 join된다. 중복 delivery는 Stage
claim/lease fencing과 `(tenant, run, evidence)` result unique constraint로 안전하게 No-op된다.
