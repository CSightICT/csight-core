# ADR-0017: Model-native Taxonomy와 Canonical Taxonomy 분리

- 상태: Accepted
- 일자: 2026-08-26

## Context

KAPUT 참고 데이터의 image-level 7개 native label은 CSight 업무 taxonomy와 이름·범위가
다르며 defect bounding-box ground truth를 의미하지 않는다. Native class ID를 DB 업무 계약으로
사용하면 Dataset/model 교체가 Domain migration이 된다.

## Decision

- Adapter가 `model_class_id`, `model_class_name`을 provenance로 보존하면서 별도의
  `canonical_label`로 매핑한다.
- KAPUT mapping v1은 penetration→CRACK, deformation→DENT, actuation→FUNCTIONAL_FAILURE,
  deconstruction→BREAKAGE, spillage→LEAKAGE, superficial→SURFACE_DAMAGE,
  missing_unit→MISSING_COMPONENT이며 알 수 없는 class는 `UNKNOWN`이다.
- Dataset taxonomy version과 CSight canonical taxonomy version을 별도로 기록한다.
- KAPUT item mask/image label을 존재하지 않는 defect bbox ground truth로 표현하지 않는다.

## Consequences

모델 provenance를 감사할 수 있으면서 업무 코드는 canonical enum만 사용한다. Mapping, threshold,
Dataset 변경은 version 변경과 재평가 대상이다.
