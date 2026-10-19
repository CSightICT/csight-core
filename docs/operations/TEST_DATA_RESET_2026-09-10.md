# 내부 테스트 데이터 초기화 및 복구 기록

사용자 승인 범위: 모든 테스트 고객사의 기존 문의115건과 사진·분석·검토·모의 처리 이력.
계정·정책·검색 인덱스·모델 서비스는 보존한다. 실제 고객 사용/출시 승인이나 사람 결정 대행은 아니다.

## 백업 및 초기화

- Post-0038 DB: `/private/tmp/csight-all-test-reset-Yd7eYU/core-before-reset.dump`
- SHA256: `ddd7ed0d2b9df9b99811b1b9840af2dfdd9bbdfbb1167941c5405ae543d972bf`
- 원래 MinIO 저장소 사본: `/private/tmp/csight-all-test-reset-Yd7eYU/minio-data/`
- 기존 `csight-evidence` bucket은 그대로 보관: 현재 객체69개, 전체 version 항목121개(삭제 표식26개 포함).
- 새 활성 bucket: `csight-evidence-feedback-20260910`, versioning 활성화. `.env`의 bucket 설정만 변경.

Core의 API·Dispatcher·Worker·Web만 멈춰 쓰기를 정지하고 DB 실제 복원을 시험했다.
[일회성 SQL](RESET_ALL_TEST_CASES_2026-09-10.sql)을 복원 DB에서 먼저 실행한 뒤 같은 고정 인벤토리의
활성 DB에 적용했다. 정확56개 업무 테이블을 RESTRICT로 비웠고,25개 보존 테이블의 count/content hash는
동일했다. 계정39명·정책 문서44개·조항304개가 유지됐다. 원래 bucket과 GPU 서비스는 내리거나 삭제하지 않았다.
기존 사진은 활성 저장소에서 분리한 것이며 영구 삭제하지 않았다.

이 SQL은 이미 실행 완료했다. 새로운 데이터를 다시 지우기 위한 일반 명령이 아니며,
현재 인벤토리에서는 보호 조건 때문에 재실행이 거부된다. 재초기화는 별도 범위 확인과 새 백업이 필요하다.

복구가 필요하면 먼저 현재 신규 데이터를 별도로 백업하고 쓰기를 정지한다. 위 dump를 **새 격리 DB**에
복원해 검증한 뒤 전환 범위를 결정한다. 원래 bucket과 DB를 짝지어야 한다. 활성 DB를 즉시 덮어쓰지 않는다.
DB 복원 시험은 PASS지만 MinIO 전체 복원 훈련·장기 보존·외부 백업은 NOT_RUN이다.
`/private/tmp`는 영구 백업 장소가 아니므로 별도 보존 매체로 옮길 필요가 있다.

## DB 불일치 및 재발 방지

초기 감사에서 발견한 파일 없는 fixture Evidence7건은 Migration0038로 FAILED와 기계 감사 기록을 남겼다.
진짜 접수 이력이 없는 과거 fixture 문의17건에는 허위 이력을 만들지 않았다. 이후 승인된 초기화로 두 종류의
과거 데이터 모두 활성 DB에서 제거됐으며, 위 post-repair 백업에는 당시 데이터와 감사 기록이 남아 있다.
통합 테스트는 runner가 만든 정확한 일회용 DB에만 연결하도록 검사해 공유 DB 오염을 예방한다.

## 새 임시 데이터 검증

10건의 가상 문의와 출처 제한된 시연 사진을 일반 인증 API로 적재한다. 이미지 출처·선정 편향·사용권 제한은
그대로 표시한다. 사진 점수는 정상 확정/결함 종류/정책 조건 정답으로 바꾸지 않는다.
local ADMIN의 기존 역할을 DB에서 확인하고 단기 토큰을 메모리에만 생성한다. 비밀번호는 사용하지 않는다.

- 기존 사진 통합 분석의 지원 버전은 `1.0.0`이다. `2.0.0` 요청은422로 거부됐고 버전을 바로잡았다.
- 현재 정책 흐름은 별도 text-v2 분석→RAW/HYBRID Top3→Grounding→버전 정책→사람 검토를 사용한다.
- 일부 구형 multimodal text-v1에서 `LLM_INVALID_STRUCTURED_OUTPUT`이 발생했다. 실패 이력을 보존한다.
- seeder의 명시적 `--execution-mode SHADOW --allow-partial-multimodal`은 사진 적재를 이어갈 때만 쓴다.
  실제 Vision 결과 검증은 계속 필수이며 PARTIAL_SUCCESS를 SUCCEEDED로 바꾸지 않는다. 보고서의 분석 상태는 FAIL이다.
- 기본 seeder는 여전히 전체 분석 성공을 요구한다. 내부 프로필에서는 SHADOW를 명시해야 한다.
- 실제 API 시험에서 검색·근거 설명 응답 변환이 내부 rollout 필드3개 때문에500을 내는 오류를 발견했다.
  DB에 이미 생성된 요청은 유지하고, 공개 응답 schema에 정의된 필드만 직렬화하도록 두 변환기를 수정했다.
  기존 API schema는 변경하지 않았다. PRIMARY/SHADOW·route 유무의 계약8개와 전체 오프라인1493개를 통과했다.
  수정 Core를 재배포하고 같은 idempotency key로 재개하여 새 중복 요청을 만들지 않는다.
- 최종 사람 결정·실제 환불/알림은 수행하지 않는다. 합성 연결 결과로 고객 정확도나 출시 자격을 주장하지 않는다.

최종 실행 수치와 남은 오류는 [단계 JSON](../progress/TEST_DATA_RESET_2026-09-10.json),
[현재 상태](../progress/CURRENT_STATUS.md)에 기록한다. 상세 개인정보 없는 실행 식별자는
`local-data/internal-feedback-reset-20260910/`에 보관한다.

15:04 최종 결과: 문의/사진10건, text-v2·검색·근거 설명·정책평가 각10건 성공, 검토10건 PENDING.
최종 사람 결정/실제 외부동작0. 기존 구형text-v1 부분실패2건(재시도 포함4개run)은 그대로 표시한다.
새DB 제약542·원문/사진10·검토packet/citation pack각10 무결성 PASS, schema drift0.
기존 계정/정책은 유지됐고 정상 실행에서 Q5 Grounding profile1개가 append됐으며 기존2개는 불변이다.
담당자는 `/reviews`를 새로고침해 새 자료를 검토한다. 실제 사람 피드백과 고객 품질 평가는 아직 미실행이다.
