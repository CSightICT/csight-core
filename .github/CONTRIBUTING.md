# CSight 기여 가이드

## 작업 전

1. `CSight_project_docs/AGENTS.md`와 관련 설계·ADR을 읽는다.
2. `docs/progress/CURRENT_STATUS.md`에서 진행 중 작업과 다음 항목을 확인한다.
3. `docs/GIT_WORKFLOW.md`에 따라 `develop`에서 단기 브랜치를 만든다.
4. Issue 또는 PR에 범위와 완료조건을 기록한다.

## 변경 중

- Domain/Platform 경계와 Port/Adapter 의존 방향을 유지한다.
- 외부 GPU는 기본 테스트에서 호출하지 않는다.
- 행동 변경에는 테스트, Migration, 계약, 문서를 함께 수정한다.
- Secret, 고객 원문, Presigned URL을 Commit·Issue·PR·로그에 넣지 않는다.

## Pull Request 전

```bash
make lint
make format-check
make typecheck
make test
```

DB·Broker·Object Storage 변경은 Core Stack을 실행한 뒤 `make test-integration` 또는
`make test-all`도 수행한다. 실행하지 않은 검증을 통과로 표시하지 않는다.

PR을 열기 전에 `docs/progress/CURRENT_STATUS.md`의 실제 검증 결과, 미해결 사항,
다음 작업, append-only 세션 로그를 갱신한다.

## 완료 정의

- 관련 인수조건과 테스트 통과
- Ruff와 Type Check 통과
- Migration과 롤백 영향 검토
- API/Event Schema와 문서 갱신
- 보안·개인정보 영향 검토
- 리뷰 대화와 필수 CI 해결
- 현재 상태 및 세션 인계 체크리스트 갱신
