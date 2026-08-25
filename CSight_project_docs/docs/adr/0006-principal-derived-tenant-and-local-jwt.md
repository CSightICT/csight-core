# ADR-0006: 인증 Principal 기반 Tenant 경계와 로컬 JWT 채택

- 상태: Accepted
- 일자: 2026-08-26

## Context

초기 API 초안은 Case 생성 Body에 `tenant_id`를 포함했다. 외부 입력의 Tenant 식별자를
신뢰하면 사용자가 다른 고객사의 리소스를 생성하거나 조회하는 취약점이 생길 수 있다.
Sprint 1에는 로컬·PoC 인증이 필요하지만 기업용 OIDC, SSO, Refresh Token, 다중 Tenant
전환까지 구현하는 것은 범위를 벗어난다.

JWT 안의 역할만 권한 판단의 기준으로 삼으면 토큰 발급 후 사용자가 비활성화되거나 역할이
회수되어도 토큰 만료 전까지 이전 권한이 남는 문제도 있다.

## Decision

- 공개 요청 Body, Query, Multipart Form에서 `tenant_id`를 받지 않는다.
- `tenant_id`는 검증된 Bearer Token과 현재 사용자 레코드로 구성한 `Principal`에서만
  가져온다.
- 모든 Case·Evidence Repository 연산은 명시적인 `tenant_id`를 요구한다.
- 다른 Tenant의 Case 또는 Evidence를 요청하면 존재 여부를 감추기 위해 `403`이 아닌
  `404 CASE_NOT_FOUND` 또는 `404 EVIDENCE_NOT_FOUND`를 반환한다. `ADMIN`도 Sprint 1에는
  자신의 Tenant 범위를 넘을 수 없다.
- 로컬·PoC 로그인은 Tenant 간 동일 이메일을 구분할 수 있도록 `tenant_slug`, `email`,
  `password`를 받는다.
- 비밀번호는 Argon2id Hash로 저장한다. 잘못된 사용자와 잘못된 비밀번호는 동일한
  `INVALID_CREDENTIALS` 응답을 사용하고, 존재하지 않는 사용자도 Dummy Verify를 수행한다.
- Access Token은 HS256으로 서명하며 `sub`, `tenant_id`, `roles`, `iss`, `aud`, `iat`,
  `exp`, `jti` Claim을 포함한다. 알고리즘은 HS256 Allowlist로 고정하고 Issuer, Audience,
  만료와 필수 Claim을 검증한다.
- 각 인증 요청에서 Token을 검증한 뒤 `(tenant_id, sub)`로 DB를 다시 조회한다. 현재
  Tenant와 사용자가 활성 상태인지 확인하고, 권한은 Token의 역할 Snapshot이 아니라 DB의
  현재 역할로 다시 구성한다.
- 역할은 `ADMIN`, `REVIEWER`, `QUALITY_VIEWER`를 사용한다. `ADMIN`과 `REVIEWER`는 Case
  생성·조회와 Evidence 업로드가 가능하고, `QUALITY_VIEWER`는 조회만 가능하다.
- JWT Codec, Password Hasher, Identity Repository는 Port로 두어 Application과 Platform이
  JWT·Hash·ORM 구현 라이브러리에 의존하지 않게 한다.
- 기업 PoC에서는 동일한 Application 경계를 유지한 채 OIDC/OAuth2 기반 Identity
  Provider Adapter로 교체한다.

## Consequences

### 장점

- 사용자가 요청 값으로 Tenant 경계를 우회할 수 없다.
- 역할 회수와 계정 비활성화가 기존 Access Token에도 다음 요청부터 반영된다.
- Domain과 Application은 HS256, Argon2id, SQLAlchemy 구현으로부터 독립적이다.
- 향후 OIDC 전환 시 Case·Evidence Use Case를 변경하지 않아도 된다.

### 비용과 제한

- 인증된 요청마다 사용자와 역할을 조회하므로 DB 부하가 증가한다.
- Sprint 1은 Access Token만 제공한다. Refresh Token, Token Revocation 목록, 회원가입,
  비밀번호 재설정, 다중 Tenant 전환은 지원하지 않는다.
- HS256 Secret의 안전한 배포와 Rotation은 운영 환경에서 별도 절차가 필요하다.
- PostgreSQL RLS는 적용하지 않으므로 Repository Tenant 필터와 격리 테스트가 필수다.

## Guardrails

- `JWT_SECRET_KEY`는 저장소에 Commit하지 않고 운영 Secret Store에서 주입한다.
- 인증 실패 로그에 Password, 전체 JWT, Credential을 기록하지 않는다.
- 개발 Seed는 `local` 또는 `test` 환경에서만 명시적으로 실행하며 운영에서 자동 실행하지
  않는다.
- 공개 Schema에 `tenant_id` 입력이 다시 추가되는지 Contract Test로 감시한다.
