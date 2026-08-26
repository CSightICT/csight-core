# ADR-0012: Qwen3.8 고정 Artifact의 Private Text-only 서빙

- 상태: Accepted
- 일자: 2026-08-26

## Context

Sprint 2의 LLM Port와 vLLM Adapter를 실제 단일 RTX 4090 Inference Node에서 검증하려면
재현 가능한 Artifact, 런타임, 네트워크와 추론 모드를 고정해야 한다. 논리 Model Family와
Hugging Face Artifact, OpenAI API에 노출되는 Service Model Name은 서로 다른 식별자다.
`cyankiwi/Qwen3.8-27B-AWQ-INT4`는 Qwen3.8-27B 기반 Community 양자화 Artifact이며 원본
설정은 multimodal architecture를 포함한다. CSight Sprint 2는 텍스트 구조화 추출만 수행하고
Vision 결함 분석은 별도 Provider 계약으로 유지한다.

## Decision

- 논리 Family는 `Qwen3.8-27B`, Artifact는
  `cyankiwi/Qwen3.8-27B-AWQ-INT4`, Service Model Name은
  `csight-qwen3.8-27b`로 분리한다.
- Artifact revision을 `63768c10df38c0395e12ef49edac1bd539eaeeea`로 고정한다.
- vLLM `0.26.0` 이미지를 tag뿐 아니라 image digest로 고정한다.
- Checkpoint가 선언한 `compressed-tensors` INT4 설정을 자동 감지하게 하고 CLI에서
  `--quantization awq`를 강제하지 않는다.
- `--language-model-only`를 필수로 사용하고 multimodal modality 한도가 모두 0이라는
  시작 로그를 검증한다. Qwen의 Vision Encoder를 CSight 결함 Detection에 사용하지 않는다.
- 서버 기본값과 요청별 `chat_template_kwargs` 모두에서 `enable_thinking=false`와
  `preserve_thinking=false`를 명시한다. Strict JSON Schema 구조화 출력만 허용하며 Raw
  Reasoning, Prompt와 Provider Response는 저장하지 않는다.
- GPU Node는 Core와 분리하고 Tailscale private address에만 바인딩한다. API 인증은
  `VLLM_API_KEY` 환경변수로 주입해 Secret이 process arguments에 나타나지 않게 한다.
- Core readiness는 외부 LLM 상태와 분리한다. 장애는 Analysis Retry/Failure 경계로 격리한다.

## Consequences

- 같은 Artifact와 런타임으로 재검증할 수 있고 DB에는 Model Family와 immutable revision이
  Snapshot된다.
- Community 양자화 품질과 FP8 KV cache의 정확도 영향은 합성 평가 Baseline 및 후속 실제
  도메인 평가가 필요하다.
- 단일 24GB GPU는 Context·동시 처리량 여유가 작다. 초기 운영값은 8,192 token, 동시
  Sequence 1이며 변경은 재검증 대상이다.
- Private GPU Node와 Secret 회전·모니터링의 운영 부담이 추가된다.

## Guardrails

- Artifact, revision, vLLM image나 quantization을 암묵적으로 교체하지 않는다.
- Public wildcard address에 port를 publish하거나 인증 없는 Endpoint를 운영하지 않는다.
- API key, Hugging Face token, SSH credential을 명령행, 문서, 로그 또는 저장소에 남기지
  않는다.
- Vision, Policy, 최종 승인·거절·법적 책임을 이 모델 출력에 맡기지 않는다.
- 실제 고객 데이터 품질을 합성 Dataset 결과로 과장하지 않는다.
