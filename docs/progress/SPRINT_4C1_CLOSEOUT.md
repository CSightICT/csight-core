# Sprint 4C-1 Closeout Audit

- 감사 일자: 2026-08-27 (Asia/Seoul)
- 감사 브랜치: `feature/sprint-4c1-policy-reranker`
- 기준 Commit: `4216028e787d0cc8c163cdef4f72e8f3379d96bf`
- 승인된 Commit message: `chore: qualify qwen3 policy reranker`
- Push / PR: 수행하지 않음
- 판정: `SPRINT_4C1_CLOSEOUT=PASS`
- 품질 판정 유지: `RERANKER_NO_MEASURABLE_GAIN`

## 감사 결론

P0 미해결 0, P1 미해결 0이다. 감사 중 표준 `make format-check`가 새
`infra/reranker`를 포함하지 않는 P1 1건을 발견해 전체 `infra`를 검사하도록 수정했고 234개
파일이 통과했다. 기본 Retrieval mode는 `HYBRID`이고 `HYBRID_RERANKED`는 별도 실험 mode다.
Locked Test의 no-gain 결과를 숨기거나 기본 profile로 승격하지 않았다.

## 집중 감사 결과

- Candidate K 10/20/30/50 artifact와 Gold 기반 oracle 계산을 검증했다. Dev/Test K20 recall은
  0.9375이고 K30/50은 추가 이득이 없다. Candidate set mutation은 0이다.
- Model artifact/revision은 `Qwen/Qwen3-Reranker-0.6B` /
  `e61197ed45024b0ed8a2d74b80b4d909f1255473`이고 공식 yes/no next-token 두 label 정규화 점수를
  사용한다. 정책·승인 확률로 표현하지 않는다.
- Unknown/duplicate/missing candidate, rank, score range와 NaN/Inf는 fail-closed다.
- `LEXICAL`, `DENSE`, `HYBRID` 의미는 유지되고 reranker down에서 세 mode는 200,
  `HYBRID_RERANKED`만 503 `RERANKER_PROVIDER_UNAVAILABLE`이다. Core readiness는 200이다.
- Dev에서 profile을 freeze한 뒤 Test 40을 한 번만 호출했다. Test nDCG 개선 17/악화 23,
  parent+exception 악화를 포함한 slice를 보존했고 이후 profile 변경은 없다.
- Migration `20260826_0007`은 기존 revision을 수정하지 않는다. Empty/previous/round-trip 세
  경로와 drift 0, 반복 activation profile 1/execution 2를 검증했다.

## 실제 실패·수정 기록

- 첫 Closeout `make format-check`는 명령 자체는 통과했지만 대상이 `infra/embedding`으로 한정돼
  reranker service를 검사하지 않았다. Make target을 `infra` 전체로 넓힌 뒤 재실행했다.
- `analyze_policy_candidates.py --split dev` 직접 재실행은 봉인 artifact 덮어쓰기를 막는 guard로
  `candidate upper bound already evaluated`를 반환했다. artifact를 삭제하지 않고 verifier로
  Dev 80을 재계산해 mismatch 0을 확인했으며 Test는 호출하지 않았다.
- Make background model process는 실행 도구의 셸 종료와 함께 사라졌다. 두 모델을 독립
  foreground 세션으로 실행해 실제 external contract를 검증했다.

## 최종 검증 원장

| 검사 | 실제 결과 |
|---|---|
| Ruff | PASS |
| Ruff format | PASS, 234 files |
| Pyright strict | PASS, 0 errors/warnings |
| Fast regression | PASS, 402 passed, 50 deselected, 31 warnings |
| Unit | PASS, 319 passed, 17 warnings |
| Architecture | PASS, 8 passed |
| Contract | PASS, 69 passed, 2 deselected, 6 warnings |
| E2E | PASS, 6 passed, 8 warnings |
| Core integration | PASS, 42 passed, 5 external GPU skipped, 405 deselected |
| External embedding | PASS, 1 passed, 451 deselected, MPS |
| External reranker | PASS, 1 passed, 451 deselected, MPS |
| Retrieval artifact verifier | PASS, Dev 80/Test 40 locked |
| Reranker verifier | PASS, Dev 80 recomputed, Test not called, mutation 0 |
| Policy DB | PASS, tenant/document/clause/embedding/index 2/24/168/168/2 |
| Reranker profile activation | PASS, repeat created 0, profile 1/execution 2 retained |
| API smoke | PASS, two tenant×three base mode and two reranked requests |
| Provider down | PASS, base modes 200, reranked 503, Core ready 200 |
| Migration | PASS, empty/previous/round-trip to `20260826_0007`, drift 0 |
| Docker health | PASS, Core 6 services healthy |
| `git diff --check` | PASS |

## 인계 체크리스트

- [x] Candidate/oracle/profile/Test lock 재감사
- [x] Reranker contract, allowlist, score 의미와 장애 격리 재감사
- [x] 정적·전체 회귀·대상별·Integration 재검증
- [x] External embedding/reranker Skip 0 재검증
- [x] Migration 세 경로·drift·profile idempotency 재검증
- [x] Core 6개 Healthy와 provider-independent readiness 확인
- [x] P1 Format target 누락 수정
- [x] `kaputt_best_vision_architecture.md` 미수정·미삭제·미Stage 확인
- [ ] 승인된 Sprint 4C-1 파일만 로컬 Commit
- [ ] Commit SHA를 상태 문서에 기록
- [ ] `feature/sprint-4c2-policy-query-builder` 전용 브랜치 생성

다음 작업은 Sprint 4C-1 Commit에서 새 브랜치를 만들고, 기존 retrieval Test를 튜닝에 쓰지 않는
새 `policy_query_builder_v1` Dev 80/Test 40 sealed dataset부터 구축하는 것이다.
