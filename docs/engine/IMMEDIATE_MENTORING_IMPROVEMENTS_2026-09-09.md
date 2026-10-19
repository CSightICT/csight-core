# 멘토링 후속 — 지금 가능한 개선의 구현·검증 결과

작성일: 2026-09-09 · 범위: 로컬 코드와 오프라인 회귀 검사

멘토링 종합 자료에서 고객 자료나 새 모델/서버 승인이 없어도 재현·수정할 수 있는 네 항목을
구현했다. **검색 평가의 정확성과 입력 보안을 개선한 것이며, 실제 모델 정확도가 올랐다는
결과는 아니다.** 80개 기술 질문 전체가 해결된 것도, 멘토의 승인을 받은 것도 아니다.

## 1. 완료 항목

| 항목 / 질문 연결 | 재현된 문제 | 이번에 반영한 개선 | 남은 확인 |
|---|---|---|---|
| 검색 품질 측정 / F04·I01 | 필요한 두 조항 중 하나만 검색해도 일부 Recall 지표가 100%. 빈 Gold·중복 히트가 점수를 왜곡 | HitRate·조항 Recall·전체 Gold coverage 분리, K=1/3/5/10/20. 실패 Case도 분모에 포함. 비정상 입력 거부 | 대표 고객 정책/독립 정답으로 실제 검색 성능 비교 |
| 평가 기록·Test 보호 / I05·P02 | generic Query CLI가 기본적으로 Test까지 평가하고 고정 경로 결과/선택 profile을 덮어쓸 수 있음. MLX도 과거 경로 재사용 | 두 legacy CLI를 Dev 전용으로 변경. 새 0700 directory/0600 exclusive file 필수. Test·freeze 차단, 원문 미출력, 미측정 안전 지표 null/NOT_RUN | 새 지표의 독립 threshold·identity·qualification 설계. 실제 Dev 재측정 |
| 이미지 숨은 정보 / L03 | 합성 PNG ICC와 JPEG comment가 정화된 결과에도 남음 | 회전/투명도를 픽셀에 적용한 뒤 원본 metadata 제거. JPEG/PNG/WebP 회귀 확장 | 실제 HTTP 업로드·저장 readback, 색관리 영향, 파일럿 호스트 보안 자격 |
| 악성 파일 검사 판정 / L03·P02 | TCP 한 번의 수신·문자열 끝 비교에 의존하여 분할 또는 잘못된 응답을 올바르게 처리하지 못함 | 제한된 단일 NULL 응답과 EOF, 정확한 판정 문자열, 4,096-byte 상한·공통 deadline·오류 시 업로드 차단 | 실제 고정 버전 ClamAV와 HTTP 통합 재검증 |

질문 ID는 [멘토링 종합 자료](../mentoring/CSIGHT_TECHNICAL_MENTORING_BRIEF_2026-09-09.md)의
질문을 가리킨다. 이 표는 질문의 일부 실행 가능한 하위 항목만 완료한 것이다.

## 2. 검색 지표: 무엇이 달라졌나

Gold가 `본문 규정`과 `예외 조항` 두 개이고 검색 결과에는 본문만 있다고 하자.

| 지표 | 같은 합성 사례의 의미와 결과 |
|---|---|
| HitRate@3 | 필요한 조항을 하나라도 찾았으므로 1.0 |
| Clause Recall@3 | 필요한 두 조항 중 하나만 찾았으므로 0.5 |
| Exact Gold coverage@3 | 모든 필요한 조항을 찾지 못했으므로 0.0 |

이제 예외를 누락한 검색이 성공 한 숫자에 가려지지 않는다. 지표는 Case별 macro 평균이며
검색 실패도 분모에 남는다. 예를 들어 위 성공 Case와 히트 없는 실패 Case가 하나씩 있으면
HitRate는 0.5, 조항 Recall은 0.25다. 이는 합성 계산 예시이지 우리 모델 실측 수치가 아니다.

빈 Gold는 별도 no-answer 평가 계약이 필요하므로 이 지표에서 자동 만점 처리하지 않는다.
중복 Case ID·빈/공백 ID·중복 Gold·중복 순위 히트·실패인데 히트가 있는 입력은 거부한다.
MRR@10/nDCG@10과 zero-result rate도 공통 순수 함수로 계산한다.

중요한 호환성 경계:

- 새 공통 계약은 `retrieval_ranking_metrics/1.0.0`, candidate 보조 진단 API는
  `query_retrieval_diagnostics/1.0.0`이다. 둘 다 `release_eligible=false`다.
- 기존 candidate v1의 `recall_at_10`은 역사적으로 Case HitRate다. 기존 serialization,
  계산식과 0.975 gate는 바꾸지 않았다. 이 값을 조항 Recall 기준선으로 해석하면 안 된다.
- candidate 보조 진단은 별도 API이며 기존 후보 평가 실행기에 자동 결합하거나 기존 보고서를
  재계산하지 않았다. 두 generic/MLX wrapper에는 새 공통 지표를 실제 연결했다.
- 기존 frozen Dev/Test·candidate matrix·RAW 선택을 덮어쓰거나 새 지표로 자동 승계하지 않는다.
  신규 threshold와 정식 qualification 전까지 새 진단으로 모델 승격할 수 없다.

## 3. 평가 도구의 안전한 사용

일반 Query Builder와 local MLX 평가 도구는 이제 Dev 진단용이다. 사용자가 명시적으로 실행하면
설정된 검색/MLX 서비스에 접속하므로 아래는 **실행 예시일 뿐 이번 작업에서는 호출하지 않았다.**

```sh
make evaluate-query-builder EVALUATION_OUTPUT_DIR=local-data/query-dev-unique-run
make evaluate-local-query-builder EVALUATION_OUTPUT_DIR=local-data/mlx-query-dev-unique-run
```

`local-data` 같은 부모 directory는 존재해야 하며 마지막 run directory는 새 이름이어야 한다.
기존 경로는 비어 있어도 거부한다. 출력 경로가 없으면 Make 단계에서 중단하고, CLI에서도
설정/provider 생성 전에 거부한다. 파일은 exclusive create로 생성해 기존 파일·leaf symlink를
덮어쓰지 않는다. 실패 뒤 남은 run directory도 재사용하지 않고 보존한다.

`--split test`, MLX의 `--freeze`/`--allow-sealed-test`는 데이터/provider 접근 전에 차단한다.
자동 profile freeze/전략 선택과 사용하지 않는 과거 overwrite 함수도 제거했다. 별도 candidate
qualification 실행기의 정식 freeze/Test 계약은 변경하지 않았고 이번에는 실행하지 않았다.

새 보고서는 `query_builder_dev_evaluation/2.0.0` 또는 `local_mlx_dev_evaluation/2.0.0`이다.
`profile_frozen=false`, `release_eligible=false`이며 관측 행에는 원문 질문·인용문·모델 출력·
에러 메시지·식별자를 그대로 저장하지 않고 해시만 기록한다. 해시는 익명화 보증이 아니므로
여전히 비공개 산출물로 취급한다. 오류 출력에는 고정 코드만 남긴다.

독립 리뷰에서 추가로 발견한 고정값도 수정했다. 전용 관측이 없던 tenant/version/미래·폐기 정책
위반율과 determinism, generic direct 검사, MLX citation 검사 placeholder는 새 보고서에서
`null`과 `unmeasured_checks: NOT_RUN`이다. 미측정을 ‘위반 0/성공 100%’로 표시하지 않는다.
이 변경은 실제 공격/운영 격리 검증을 새로 수행했다는 뜻이 아니다.

## 4. 이미지·검사기 보안의 경계

이미지 회전, RGBA/palette 투명도와 허용 형식을 유지하면서 원본 EXIF·ICC·XMP·comment/text가
encoder에 재사용되지 않도록 했다. 원본과 정화본 모두 악성 파일 검사 호출을 유지한다.
합성 이미지에서 재현한 결함이며 실제 고객 정보 유출을 관측한 것은 아니다.

원본 ICC를 제거하는 기존 metadata-free 계약을 보강한 것이다. 새 색상 프로필 변환을 구현하거나
색관리 기반 외관 동일성을 보증하지 않는다. 향후 실제 시각 품질 비교에서 색상 영향도 확인한다.

ClamAV는 TCP 분할을 정상 처리하되 정확한 단일 `stream: OK` NULL 프레임만 clean으로 인정한다.
악성 판정, 잘못된 접두사·부분 응답·NULL 누락·복수/충돌 프레임·과대 응답·timeout은 차단된다.
연결/송신/수신/EOF 대기에 공통 deadline을 적용한다. 플랫폼 DNS resolver 자체를 취소하는 기능은
추가하지 않았으므로 DNS wall-clock 상한까지 증명한 것은 아니다. 프로토콜 근거와 운영 재검증은
[Evidence Security](../../CSight_project_docs/docs/operations/EVIDENCE_SECURITY.md)에 정리했다.

## 5. 실제 검증 결과

| 검사 | 실제 결과 | 해석 |
|---|---|---|
| 수정 전 안전 CLI/검색 wrapper 회귀 | 18 FAIL | 새 회귀가 기존 결함을 재현함. 당시 수정 전 결과 |
| 수정 전 이미지/ClamAV 확장 회귀 | 18 FAIL / 15 PASS | 합성 이미지·가짜 socket으로 결함 재현 |
| 최종 기본 오프라인 테스트 | 1,444 PASS / 94 deselected / 기존 deprecation warning 36 | DB·외부 GPU·실제 ClamAV·UI 브라우저 E2E 자격과 별개 |
| 공통 지표·candidate 집중 검사 | 62 PASS | 후보 확장 회귀 201 PASS도 확인. 전체 회귀와 중복 집계 금지 |
| 새 wrapper 안전 검사 | 29 PASS | 새 경로·충돌·Test/freeze·민감정보·미측정 수치·Make dry-run |
| 이미지/ClamAV adapter 집중 검사 | 42 PASS | 기존 Evidence use case 포함 56 PASS |
| app/scripts/tests Ruff | PASS | 검사 대상 코드 전체 |
| 전체 Pyright + 수정 wrapper/helper 별도 Pyright | PASS, 각각 오류 0 | 새 타입 오류를 수정하고 재검사 |
| app/scripts/tests format | PASS, 600 files | 무관한 사용자 문서는 정리하지 않음 |
| 저장소 전체 format probe | FAIL, 사용자 문서 1개 | `kaputt_best_vision_architecture.md`의 기존 코드 블록 서식. 이번 범위 외, 보존 |
| 독립 리뷰 | PASS | CLI 권한/출력 안전 및 지표 의미. 미측정 placeholder 지적을 반영 |
| diff 공백 검사 | PASS | 기존 미커밋 작업을 되돌리지 않음 |

처음 전체 검사에서 기존 launcher DRY_RUN 테스트 2개가 사용자 uv cache 읽기 권한 때문에
실패했다(1,333 PASS / 2 FAIL). 허용된 임시 cache와 offline/no-sync 설정으로 재검사하여
해소했다. 의존성을 설치하거나 launcher의 실제 서비스를 시작하지 않았다. 그 환경 실패를
제품 코드 결함이나 모델 추론 실패로 계산하지 않는다.

재현용 최종 검사 형태:

```sh
UV_NO_SYNC=1 UV_OFFLINE=1 UV_CACHE_DIR=/private/tmp/csight-validation-cache.BbZdK7 \
  .venv/bin/python -m pytest -q -m 'not integration and not external_gpu and not external_vision and not external_embedding and not external_reranker and not external_local_llm'
.venv/bin/ruff check app scripts tests
.venv/bin/ruff format --check app scripts tests
.venv/bin/pyright
.venv/bin/pyright scripts/evaluation_reporting.py scripts/evaluate_policy_query_builder.py scripts/evaluate_local_mlx.py
```

임시 cache 경로는 이번 세션용이다. 다음 세션에서는 접근 가능한 새 임시 directory를 사용한다.
단계별 짧은 증거는 [검증 JSON](IMMEDIATE_MENTORING_IMPROVEMENTS_VERIFICATION_2026-09-09.json),
결정은 [ADR-0127](../../CSight_project_docs/docs/adr/0127-explicit-retrieval-diagnostics-and-legacy-dev-only-evaluation.md)에 있다.

## 6. 보존·미실행과 다음 순서

- 보존: 기존 미커밋 변경, 과거 평가/분석 결과, frozen profile·sealed Test, candidate matrix,
  RAW runtime 설정, 사용자 문서, 4090/GX10 서비스. DB/API/Event 계약이 없어 migration 불필요.
- NOT_RUN: 새 GPU/SSH 확인·실제 모델/검색 평가·학습·ClamAV HTTP 자격·실제 DB 통합·UI E2E,
  모델 설치/전송·서비스 재시작·배포·PRIMARY/fallback 변경·실제 고객 업무 동작.
- 비밀번호·개인 키를 요청하거나 사용하지 않았다. Commit·Push·PR·병합도 하지 않았다.
- `NO_WINNER`·`NO_RELEASE_ELIGIBLE`와 제한 파일럿 BLOCKED를 유지한다. GX10 관측은 계속
  9/2 runtime canary이며 현재 상태나 CSight 품질 재확인을 이번 검사로 대체하지 않는다.

다음은 첫 상품군의 권리 확인된 대표 문의·사진/정책과 독립 정답을 확보하고, 같은 입력·정답에서
RAW와 후보의 **본문+예외 회수율**을 측정하는 것이다. GX10은 별도 model/runtime/quantization
identity 계약으로 세 task Dev를 검증해야 한다. 보안 변경은 배포 전 격리된 실제 ClamAV HTTP
자격을 재실행해야 하며, UI 대조 연결·실제 고객 IdP/보존·부하·off-host 복구는 별도 후속 과제다.
사용자/고객/멘토의 자료·의사결정이 필요한 항목을 임의의 합성 성능으로 완료 처리하지 않는다.
