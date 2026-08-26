# ADR-0013: Canonical Vision Result Schema

- 상태: Accepted
- 일자: 2026-08-26

## Context

Vision 모델마다 class, 좌표, 품질 필드와 metadata가 다르다. 이를 Application이나 DB 계약에
직접 노출하면 모델 교체가 업무 계약 변경이 되고 pixel 좌표·미검사 품질 값이 모호해진다.

## Decision

- `VisionProvider` Adapter가 모델 응답을 strict schema `1.0`으로 정규화한다.
- Detection geometry의 현재 실행 형식은 `BOUNDING_BOX`와 `normalized_xyxy`이며 좌표 범위와
  순서를 검증한다. `MASK`는 향후 확장 가능한 enum 설계만 유지한다.
- 품질은 `USABLE`, `NOT_USABLE`, `NOT_EVALUATED`의 삼상태다. 미평가 세부 값은 `null`이다.
- 결과마다 provider/model/revision, dataset/taxonomy/threshold/preprocess/postprocess version,
  dimensions, latency를 저장하고 가능한 경우 framework/runtime/precision도 저장한다.
- Raw provider JSON, Binary, URL과 파일 경로는 저장하지 않는다.

## Consequences

Provider 교체와 pixel 좌표 입력을 Adapter 내부에 격리할 수 있다. Canonical schema나 version
field가 누락되거나 geometry가 잘못되면 permanent structured-output failure로 거부한다.
