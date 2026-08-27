# GitHub CV 학습 브랜치 동기화 감사

- 점검일: 2026-08-27, Asia/Seoul
- 저장소: `CSightICT/csight-core`
- 대상 브랜치: `feature/3-kaputt-dinov2-training`
- 기준 브랜치: `develop`
- Pull Request: #4

## 1. 결론

CV 학습 파일은 GitHub 업로드에 실패한 것이 아니라 feature 브랜치에 정상 반영돼
있었다. 대상 브랜치는 `develop`보다 38 commits 앞서 있고 0 commits 뒤처져 있으며,
GitHub compare API에서 CV 파일 17개와 상태 문서 1개를 확인했다.

로컬 `ml/cv` 파일 17개를 feature 브랜치의 같은 경로와 줄바꿈을 정규화해 대조한 결과
17/17개가 일치했다. `develop`에는 PR이 아직 merge되지 않았으므로 같은 파일이 보이지
않는 것이 정상이다.

## 2. 오류처럼 보인 원인

1. 확인 위치가 저장소 브랜치 화면이 아닌 GitHub `/notifications` 페이지였다.
2. 저장소 기본·`develop` 브랜치에는 아직 PR #4가 merge되지 않아 CV 파일이 없다.
3. GitHub commit search는 새 private feature branch의 커밋을 즉시 반환하지 않았지만,
   branch compare, exact-ref file fetch, commit SHA 직접 fetch는 모두 성공했다.
4. 현재 로컬 Windows workspace와 원격 학습 디렉터리는 실제 `csight-core` Git clone이
   아니다. 따라서 일반적인 `git status` → commit → push 검증을 사용할 수 없어 GitHub
   Contents API로 파일별 커밋을 만들었고, 변경이 여러 커밋으로 나뉘었다.
5. Windows PowerShell을 통해 파일 내용을 전달하는 과정에서 LF/CRLF가 달라져 Git blob
   SHA는 달랐다. 줄바꿈을 정규화한 본문은 17/17개가 일치했으며 코드 누락은 없었다.
6. 별도로 발생한 `scp` 오류는 Codex 실행 PowerShell의 `PATH`에 OpenSSH가 없어서였다.
   `C:\Windows\System32\OpenSSH\scp.exe` 절대 경로로 해결했으며 GitHub 업로드와는
   무관하다.

## 3. 재발 방지 규칙

1. 업로드 대상 저장소, branch, PR 번호를 작업 시작 전에 고정한다.
2. 파일 쓰기는 동일 branch에만 수행하고, 기본 브랜치 화면으로 업로드 성공 여부를
   판단하지 않는다.
3. 업로드 후 반드시 다음 세 가지를 모두 검사한다.
   - exact-ref file fetch
   - 기준 branch와 feature branch compare
   - 생성된 commit SHA direct fetch
4. 로컬과 원격 내용을 줄바꿈 정규화 후 전수 대조하고 `N/N match`를 기록한다.
5. 여러 파일 변경은 가능하면 실제 Git clone에서 단일 commit으로 push한다. Git clone을
   사용할 수 없으면 GitHub Tree/Commit API로 한 번에 원자적 commit을 만들고 ref를
   이동한다. 파일별 Contents API 커밋은 긴급 수정에만 사용한다.
6. PR 본문과 `docs/progress/CURRENT_STATUS.md`에 마지막 검증 commit과 상태를 기록한다.
7. merge는 별도 승인 후 수행한다. 업로드와 merge를 같은 의미로 취급하지 않는다.

## 4. 이번 점검 증거

- branch compare: ahead 38, behind 0
- 변경 경로: 18개(CV 17개 + `docs/progress/CURRENT_STATUS.md`)
- 로컬/원격 정규화 본문 일치: 17/17
- E3 config exact-ref fetch: 성공
- 상태 문서 commit `1d427a4a905b5c6315cc031229fbd3de298bed37` direct fetch: 성공
- 누락 파일: 0


