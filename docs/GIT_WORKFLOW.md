# CSight GitHub 협업 규칙

이 문서는 CSight의 브랜치, Pull Request, 리뷰, 병합 규칙을 정의한다. 프로젝트 규모에
맞게 `main`과 `develop`만 장기 브랜치로 유지하는 경량 GitFlow를 사용한다.

## 1. 장기 브랜치

| 브랜치 | 역할 | 직접 Push |
|---|---|---|
| `main` | 항상 배포·태깅 가능한 릴리스 기준 | 금지 |
| `develop` | 다음 Sprint 변경을 통합하는 기준 | 금지 |

`main`과 `develop`의 변경은 Pull Request와 필수 CI를 통해서만 병합한다.

## 2. 단기 브랜치

| 패턴 | 시작점 | PR 대상 | 용도 |
|---|---|---|---|
| `feature/<issue>-<slug>` | `develop` | `develop` | 신규 기능 |
| `fix/<issue>-<slug>` | `develop` | `develop` | 아직 릴리스되지 않은 버그 수정 |
| `chore/<issue>-<slug>` | `develop` | `develop` | CI, 문서, 리팩터링, 의존성, 인프라 |
| `release/vX.Y.Z` | `develop` | `main` | 실제 릴리스 안정화가 필요할 때만 사용 |
| `hotfix/<issue>-<slug>` | `main` | `main` | 운영 릴리스 긴급 수정 |

- 이름은 소문자와 하이픈을 사용한다.
- Issue가 있으면 번호를 포함한다. 작은 문서 정정에는 Issue를 강제하지 않는다.
- 단기 브랜치는 병합 후 삭제한다.
- Hotfix는 `main` 반영 후 `develop`에도 forward-port한다.

## 3. Pull Request

- PR 하나는 하나의 검토 가능한 목적만 가진다.
- 일반 기능 PR은 `develop`, 릴리스·Hotfix PR은 `main`을 대상으로 한다.
- Draft PR을 조기에 열어 설계와 CI 상태를 공유할 수 있다.
- PR 본문에는 변경 이유, 범위 밖 항목, 실제 검증 결과, Migration/API/Event 계약,
  보안·개인정보 영향, 롤백 방법을 기록한다.
- 변경과 함께 `docs/progress/CURRENT_STATUS.md`를 갱신한다.
- 리뷰 대화와 필수 CI가 모두 해결된 뒤 병합한다.

## 4. 병합 방식

- `feature/*`, `fix/*`, `chore/*`에서 `develop`으로 가는 일반 PR은 Squash merge한다.
- PR 제목을 Squash commit 제목으로 사용하며 Conventional Commit 형식을 권장한다.
- `develop` 또는 `release/*`에서 `main`으로 승격할 때는 두 장기 브랜치의 ancestry를
  보존하기 위해 Merge commit을 사용한다.
- Rebase merge는 사용하지 않는다.

예시:

```text
feat(api): add case creation endpoint
fix(worker): preserve analysis idempotency
chore(ci): require architecture tests
docs(workflow): record sprint handoff
```

## 5. Branch protection 목표 설정

### `main`

- Pull Request 필수
- 승인 1명 이상 및 Code Owner review 필수
- 새 커밋 Push 시 기존 승인 무효화
- 모든 리뷰 대화 해결 필수
- `CI / Quality and fast tests` 성공 필수
- 병합 전 최신 기준 브랜치 반영 필수
- Force push와 브랜치 삭제 금지
- 일반 구성원의 우회 금지

### `develop`

- Pull Request와 승인 1명 이상 필수
- Code Owner review와 리뷰 대화 해결 필수
- `CI / Quality and fast tests` 성공 필수
- Force push와 브랜치 삭제 금지
- 작은 팀의 불필요한 재실행을 줄이기 위해 최신 `develop` 반영 강제는 초기에는 사용하지
  않는다.

Required check 이름은 첫 GitHub Actions 성공 실행 후 GitHub가 표시한 실제 Context와
대조한다. Job 이름이 바뀌면 보호 규칙도 함께 수정한다.

## 6. 코드 소유권

초기 `CODEOWNERS`는 저장소 관리자 `@it0615`를 기본 소유자로 둔다. 조직 팀과 담당자가
확정되면 `backend-maintainers`, `platform-maintainers` 같은 팀 단위 소유권으로 교체한다.
Placeholder 팀명은 실제 팀과 권한이 생기기 전에는 추가하지 않는다.

## 7. 표준 작업 흐름

```bash
git switch develop
git pull --ff-only
git switch -c feature/123-case-create

# 구현 및 검증
make lint
make format-check
make typecheck
make test

git push -u origin feature/123-case-create
```

PR 병합 후 로컬 단기 브랜치는 삭제하고 `develop`을 갱신한다. 외부 GPU 테스트와 운영
Secret은 기본 PR 검증에 포함하지 않는다.
