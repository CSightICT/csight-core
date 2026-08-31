# Keycloak OIDC 격리 자격 검증

## 목적과 경계

이 검증은 현재 시연 서버와 분리된 `18000`(CSight API), `18080`(Keycloak) 포트와 임시 PostgreSQL을
사용한다. Keycloak은 digest로 고정된 26.7.2 이미지이며 Authorization Code + PKCE만 허용한다.
검증 중 생성되는 비밀번호는 프로세스 메모리와 환경 변수에만 존재하고, 종료 시 컨테이너·네트워크·
임시 DB를 제거한다. 기본 테스트와 시연 서버 설정에는 포함되지 않는다.

## 실행

```sh
make qualify-oidc-keycloak
```

모든 관문이 통과하면 exit 0과 `PASS`, 제품 차단 항목이 있으면 exit 2와 `BLOCKED`, 구성 또는 실행
오류는 exit 1과 `ERROR`를 반환한다. 실패를 성공으로 바꾸거나 password fallback을 열지 않는다.
PII와 Secret이 없는 결과는 mode `0600`의
`local-data/oidc-qualification/latest/qualification-report.json`에 저장한다. 디렉터리는 mode
`0700`이며 운영 증거 수집기는 파일 내용과 수정 시각을 함께 검증해야 한다.

## 2026-08-30 실측 결과

통과:

- OIDC-only capability와 legacy password token route 404
- 실제 Keycloak Authorization Code + PKCE 로그인
- `csight-reviewers` 그룹의 로컬 REVIEWER 계정 매핑
- `/cases` return path 복귀
- CSRF 없는 logout 403, 유효 CSRF logout 204
- 그룹 제거와 계정 비활성화 이후 새 로그인 차단
- 그룹 제거·계정 비활성화 뒤 Keycloak 사용자 session 종료가 보낸 서명 back-channel logout으로
  기존 CSight session 즉시 401
- 12초 qualification idle timeout 이후 세션 401

판정은 `PASS`다. CSight는 raw token·subject·provider session ID를 기록하지 않고 issuer-scoped hash로
세션을 폐기하며 같은 logout JWT ID의 재전달은 멱등 성공한다. 다만 Keycloak의 그룹 제거·계정
비활성화 API 자체는 logout event를 만들지 않는다. 운영 자동화는 권한 변경과 `POST
/admin/realms/{realm}/users/{user-id}/logout` 또는 동등한 IdP session 종료를 반드시 묶고, 전달 실패를
재시도·경보해야 한다. 이 고객별 운영 연결을 검증하지 않은 배포는 자격이 없다.

## 운영 금지

- `OIDC_ALLOW_INSECURE_HTTP=true`는 이 격리된 local/test 자격 환경에서만 사용한다.
- pilot/production은 HTTPS, TLS 검증, Secure cookie를 모두 요구한다.
- IdP 권한 변경만 수행하고 provider session 종료를 생략해서는 안 된다.
- 이 결과는 현재 데모 로그인 방식을 변경하지 않으며 외부 사업 동작을 수행하지 않는다.
