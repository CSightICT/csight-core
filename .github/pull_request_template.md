## 변경 목적

<!-- 무엇을 왜 변경했는지 설명해 주세요. -->

관련 Issue: <!-- Closes #123 -->

## 변경 내용

-

## 범위 밖

-

## 아키텍처·데이터 영향

- [ ] `app/platform`과 `app/domains`의 Framework 독립성을 유지했습니다.
- [ ] 외부 기술은 Port/Adapter를 통해 연결했습니다.
- [ ] Migration 변경 없음 / Migration과 롤백 영향을 검토했습니다.
- [ ] 공개 API·Event 계약 변경 없음 / 계약과 테스트를 갱신했습니다.
- [ ] AI 결과가 최종 업무 결정을 소유하지 않습니다.

## 보안·개인정보

- [ ] Secret, 고객 원문, 이미지 URL이 코드·로그·PR에 포함되지 않습니다.
- [ ] 새로운 권한·외부 전송·데이터 보존 영향이 없습니다 / 아래에 설명했습니다.

## 검증

<!-- 실제 실행한 명령과 결과만 적어 주세요. -->

```text
make lint:
make format-check:
make typecheck:
make test:
make test-integration:
```

## 위험과 롤백

- 위험:
- 롤백:

## 인계

- [ ] `docs/progress/CURRENT_STATUS.md`를 갱신했습니다.
- [ ] 남은 작업과 필요한 사용자 결정을 기록했습니다.
