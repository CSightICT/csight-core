# LLM Extraction v2 Guide

Pipeline `product_defect_text_extraction`은 v1 `1.0.0`을 그대로 유지하고 v2 `2.0.0`을 추가한다.
v2 Prompt/Schema는 `2.0.0/2.0`이며 고객 문장에 명시된 결함·요청만 추출한다.

- `case.requested_action`: UI/API가 선언한 값
- `requested_actions[]`: 자유 텍스트의 exact quote가 있는 명시적 요청
- `text_ambiguities[]`: 문장 자체의 모호성
- `system_missing_information[]`: Backend completeness rule `1.0.0`의 결정적 결과
- `action_consistency`: LLM이 아닌 Application이 계산한 관계

Source quote는 비어 있을 수 없고 고객 원문의 연속 부분 문자열이 아니면 저장하지 않는다.
승인·거절·사기·책임·정책 결정 field는 v2 schema에 없다. 실제 Qwen 없이 실행하는
`make evaluate-extraction-v2`는 Gold self-check이며 모델 품질 평가가 아니다.
