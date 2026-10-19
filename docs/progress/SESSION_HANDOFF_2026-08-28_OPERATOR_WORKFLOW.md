# CSight 다음 세션 인계 요약 — 운영형 상담원 워크플로우

- 작성 시각: 2026-08-28 23:02 KST
- 저장소: `CSightICT/csight-core`
- 작업 브랜치: `codex/operator-console-product-direction`
- 원격 HEAD: `3daaa7bff56fa0e25f7ca69bf6bc31d68a2cdb79`
- 목적: 다음 세션이 현재 제품 방향, 구현 범위, 검증 상태와 안전 경계를 다시 조사하지 않고 바로
  후속 작업을 시작할 수 있게 한다.

## 1. 한 문장 현재 상태

CSight는 실제 E3 이진 결함 후보 분석, 정책 검색·평가, 사람 검토, 처리 사전 확인, 환불 확인서,
발송 전 고객 안내 메일과 비식별 데이터 자산을 하나의 한글 상담원 흐름으로 연결한 내부 운영형
제품이며, 실제 결제 취소·환불·CRM·물류·메일 발송은 아직 수행하지 않는다.

## 2. 이번 세션에서 제품 방향이 바뀐 이유

초기 목표는 Vision·LLM·검색·정책 엔진·Human Review가 기술적으로 이어지는지 검증하는 것이었다.
이 경로는 완성됐지만 화면에는 `APPROVE_REFUND`, `REQUIRES_HUMAN_REVIEW`, qualification JSON과
같은 내부 계약이 노출됐고, 고객·주문·결제·배송 문맥이 부족해 실제 상담 제품보다는 개발 콘솔처럼
보였다.

비전 담당자가 전달한 E3 checkpoint는 실제로 연결했지만 계약은 이미지 단위 `any-defect` 이진
점수다. 상품명·결함 유형·위치·환불 여부를 예측하지 않으므로 점수를 업무 의미로 과잉 해석할 수
없었다. Kaputt에도 상품명이 없어 Qwen3.8 VLM으로 후보 메타데이터를 만들었지만 Human Gold와
taxonomy 정합성이 부족했고 defect-positive 재현도 통과하지 못했다. Qwen 결과는 공식 라벨이나
온라인 결정 경로가 아니라 오프라인 후보 생성으로 유지했다.

실제 기업 데이터는 사용하지 않으면서도 서비스 동작을 현실적으로 보여주기 위해, 검증된 이미지에
가상 상품명·SKU·가격대·긴 문의 내용과 합성 고객·주문·결제·배송 문맥을 연결했다. 이후 중심 목표를
“AI가 자동으로 환불하는 화면”이 아니라 “AI와 정책이 근거를 준비하고 사람이 결정한 뒤 문서와
감사 기록까지 안전하게 이어지는 상담 업무 제품”으로 전환했다.

상세 근거는 [`PRODUCT_DIRECTION_EVOLUTION_2026-08-28.md`](../product/PRODUCT_DIRECTION_EVOLUTION_2026-08-28.md)에
정리돼 있다.

## 3. 현재 구현된 범위

### 분석·정책·사람 검토

- Tenant 격리 Case와 Private Evidence 저장
- Text/Vision 비동기 분석, durable outbox, lease/fencing, append-only Run·Attempt·Result
- 정책 문서 적재, RAW+HYBRID 검색, Top-3 Citation, Grounding과 버전 관리 정책 평가
- 인증된 담당자만 확정할 수 있는 Human Review와 immutable Decision
- 빠른 허용·비허용은 자동 승인 기능이 아니라 담당자 결정을 짧게 기록하는 UI

### Vision·데이터 시나리오

- 전달받은 SHA 고정 E3 checkpoint의 실제 MPS Runtime과 Core 결과 저장 경로
- E3 점수는 `any-defect` 후보 선별에만 사용하고 정상 확정·결함 종류·업무 조치를 추론하지 않음
- 사람 승인 closed set 20건: 결함 후보 12건, 기준 미만 사람 확인 참고 8건
- 네 상품군과 세 결함군을 표현하지만 클래스별 정확도·calibration 평가가 아님
- 현실적인 한글 상품명, SKU, 가격대, 이미지 정합 문의와 합성 Commerce Context
- Qwen3.8 27B VLM은 4090의 Kaputt 오프라인 enrichment 경로로만 사용; 온라인 상담 결정에 미사용

### 상담원 콘솔

- 로그인, 문의 목록·생성·상세, Evidence 업로드와 분석 진행 상태
- 상품명 중심 상담 케이스와 검토 대기함
- 문의 내용·이미지 근거·정책 권고를 한 화면에 배치한 전체 폭 검토 화면
- 내부 enum과 qualification JSON 대신 자연스러운 한글 업무 문구 사용
- 데스크톱에서 기능 없는 닫기 버튼 제거, 모바일 전용으로 제한
- 한국 효력일 기준 정책 요청으로 `이어하기` 422 오류 수정
- 담당자 허용·비허용 선택 후 검토 기록과 후속 문서를 생성하는 빠른 검토 흐름

### 처리·문서·데이터 자산

- Human Decision 이후 Case와 분리된 Resolution Projection·Event
- 명시된 Action 입력만 사용하는 immutable Action Intent
- 환불액·통화 등 필수값이 없으면 `처리 정보 보완 필요`로 종료하고 Attempt/Result를 만들지 않음
- 네트워크를 사용하지 않는 결정론적 처리 사전 확인; `LIVE`는 항상 fail-closed
- 고객·주문·결제·배송·결정 근거를 담은 환불 처리 확인서와 인쇄 화면
- 실제 SMTP 전송 없이 발송 전 고객 안내 메일을 생성·열람
- 최종 보고서 기준 상품·결정·결과·모델·정책 metadata를 tenant별 append-only 학습 자산으로 저장
- 학습 자산에는 고객 문의 원문, 이름, 전화번호, 주소 같은 직접 개인정보를 저장하지 않음

## 4. 화면 표현과 내부 진실의 구분

상담원 화면에서는 `PoC`, `Mock`, `DRY-RUN`, `시뮬레이션` 같은 개발 용어를 제거하고 실제 업무
표현을 사용한다. 이는 제품 사용성을 위한 표시 계층 변경이며 다음 기술적 한계를 없앤 것이 아니다.

- 정책과 Commerce Context는 실제 고객사 자료가 아니라 합성 시나리오다.
- Vision은 실제 E3 checkpoint이지만 현재 상품별 실제 운영 성능을 입증하지 않았다.
- Qwen VLM 후보는 공식 라벨이 아니며 온라인 최종 판단에 사용하지 않는다.
- 환불·교환·재배송·수리·메일은 외부 시스템에 반영되지 않는다.
- 최종 결정은 로그인한 사람의 명시적 행동으로만 생성된다.
- 금액·통화·수량·배송지 참조는 문의, 주문 금액, 모델 설명에서 추론하지 않는다.

문서와 감사 기록에서는 이 한계를 계속 명시해야 하며, 실제 고객 성능·자동화율·시간 절감·ROI로
주장하면 안 된다.

## 5. Git과 검증 기준점

### 현재 브랜치

- 기준 브랜치: `feature/scenario-poc-hard-plastic`의 `dfaa373`
- 현재 브랜치: `codex/operator-console-product-direction`
- 원격과 로컬 HEAD: `3daaa7bff56fa0e25f7ca69bf6bc31d68a2cdb79`
- PR, `develop/main` 병합, tag, release: 없음

주요 커밋:

- `c90357d` — 누적 운영형 상담원 워크플로우
- `dac2447` — 방향 전환과 Git 인계 원장
- `42616a4` — 자연어 UI에 맞춘 5개 브라우저 시나리오
- `7ad1b9f` — 성공한 기능 기준점과 상태 문서
- `3daaa7b` — 중복 상태 badge에 안정적인 E2E assertion

### 마지막 확인 결과

- 로컬: Ruff PASS, Format 392 files PASS, Pyright 0 errors
- Backend 기본 회귀: 686 PASS, 65 deselected
- Web: ESLint, TypeScript, OpenAPI sync, 24 files/63 tests, production build PASS
- Playwright 필수 시나리오: 5/5 PASS
- GitHub Actions Run `33177793237`: Quality와 Consultant console 모두 PASS
- DB: `20260828_0016_communication_learning_assets (head)`
- 2026-08-28 23:02 KST Core 7개 컨테이너 모두 healthy
- 같은 시각 `https://doongdoong.org/web-health` 응답 `ok`
- Web bundle 500 kB 초과 권고는 남아 있으나 build 실패가 아니며 후속 분할 대상

`7ad1b9f`의 Run `33177439114`는 `추가 자료 필요`가 두 곳에 표시될 수 있는 UI에서 E2E가 정확히
한 요소만 가정해 실패했다. 제품 동작 실패가 아니며 `3daaa7b`에서 selector를 안정화한 후 최종
GitHub CI가 통과했다. 실패 기록은 감사 원장에 그대로 보존한다.

## 6. 건드리지 말아야 할 로컬 파일

다음 파일은 사용자 소유 미추적 문서이며 현재 브랜치의 커밋·Push에서 제외했다. 다음 세션도 별도
요청 없이 수정, 삭제, Stage, Commit하지 않는다.

- `CSight_MASTER_HANDOFF_2026-08-27.md`
- `ecommerce_vibe_coding_cs_automation_market_research.md`
- `kaputt_best_vision_architecture.md`

모델 checkpoint, 원본 Kaputt, Top-100과 정상 이미지도 Git에 넣지 않는다. Secret, 비밀번호,
Presigned URL, 직접 개인정보를 인계 문서나 로그에 기록하지 않는다.

## 7. 다음 세션의 권장 첫 작업

가장 먼저 인증된 상담원 계정으로 공개 화면을 수동 검증한다. 계정 정보는 문서에 기록하지 말고
사용자가 직접 로그인한 세션을 사용한다.

1. `doongdoong.org`에서 대표 환불 케이스를 연다.
2. 문의 목록 → 상세 → 이미지/정책 근거 → 검토 대기함 → 허용/비허용을 순서대로 확인한다.
3. 환불 처리 확인서와 안내 메일 화면에서 잔여 개발 용어, 중복 정보, 실제 실행으로 오해할 표현을
   찾는다.
4. 1440px 이상 화면에서 검토 버튼과 주요 근거가 첫 화면에 보이는지 확인한다.
5. 그 다음 20건 연속 처리의 시간, 실패·부분 완료, queue 상태와 메모리 peak를 측정한다.
6. 결과가 안정적이면 별도 커밋으로 번들 분할을 진행한다.
7. 리뷰용 PR은 사용자가 명시적으로 요청할 때만 만든다.

실제 고객 단계로 승격하려면 상품·결함 taxonomy, 비식별 실제 Case와 Gold, 실제 정책, Vision
qualification, Shadow Mode, 개인정보 및 외부 연동 승인이 별도로 필요하다.

## 8. 다음 세션 시작 명령

```bash
cd /Users/ckdlsxor/Desktop/CSight_proejct
git status --short --branch
git log --oneline --decorate -8
docker compose --env-file .env -f infra/compose.core.yml ps
docker compose --env-file .env -f infra/compose.core.yml exec -T api uv run alembic current
```

변경 전에는 반드시 `CSight_project_docs/AGENTS.md`, `docs/progress/CURRENT_STATUS.md`, 관련 ADR과
이 문서를 읽는다. 기본 검증 명령은 다음과 같다.

```bash
make lint format-check typecheck test
make web-lint web-typecheck web-openapi web-test web-build
make web-e2e
```

기본 테스트에서는 외부 GPU를 호출하지 않는다.

## 9. 관련 문서

- [`CURRENT_STATUS.md`](CURRENT_STATUS.md)
- [`PRODUCT_DIRECTION_EVOLUTION_2026-08-28.md`](../product/PRODUCT_DIRECTION_EVOLUTION_2026-08-28.md)
- [`SPRINT_5C_CASE_RESOLUTION_CONSOLE.md`](SPRINT_5C_CASE_RESOLUTION_CONSOLE.md)
- [`SCENARIO_POC_ACCEPTANCE_RUNNER.md`](SCENARIO_POC_ACCEPTANCE_RUNNER.md)
- [`MEMORY_USAGE_BASELINE.md`](MEMORY_USAGE_BASELINE.md)
- [`KAPUTT_QWEN38_VLM_ENRICHMENT.md`](../data/KAPUTT_QWEN38_VLM_ENRICHMENT.md)
- [`REFUND_PROCESSING_CONFIRMATION.md`](../resolution/REFUND_PROCESSING_CONFIRMATION.md)
- [`ADR-0098`](../../CSight_project_docs/docs/adr/0098-synthetic-commerce-context-separate-from-action-input.md)
- [`ADR-0099`](../../CSight_project_docs/docs/adr/0099-offline-qwen-vlm-label-enrichment.md)
- [`ADR-0100`](../../CSight_project_docs/docs/adr/0100-curated-closed-set-poc-admission.md)

## 10. 다음 세션에 그대로 전달할 시작 문구

> `docs/progress/SESSION_HANDOFF_2026-08-28_OPERATOR_WORKFLOW.md`와
> `docs/progress/CURRENT_STATUS.md`를 먼저 읽고, 현재 Git·DB·서비스 상태를 다시 확인해. 기존의 사람
> 최종 결정, 명시 Action 입력, 외부 시스템 미반영, 합성 데이터와 실제 성능 주장 분리 원칙을 유지해.
> 먼저 공개 상담원 화면에서 대표 환불 흐름을 수동 QA하고 발견한 문제를 근거와 함께 수정한 뒤 관련
> 회귀를 실행해. Commit·Push·PR은 내가 명시적으로 요청하기 전에는 하지 마.
