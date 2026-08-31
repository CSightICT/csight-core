# ADR-0116: Non-local OIDC-only authentication boundary

- Status: Accepted
- Date: 2026-08-30
- Owners: CSight Platform and Security
- Supersedes: the non-local compatibility allowance in ADR-0104
- Extends: ADR-0104

## Context

OIDC Authorization Code + PKCE and hashed server sessions were implemented, but the password-token router and
Bearer JWT resolver remained active whenever Sprint 1 services were composed. Enabling OIDC therefore did not
make a pilot deployment OIDC-only, and a legacy token could bypass session revocation, group changes, and CSRF.

## Decision

`LEGACY_PASSWORD_AUTH_ENABLED` is a deployment control. It defaults to enabled only for `local` and `test`, and
to disabled elsewhere. Any non-local configuration that explicitly enables it is rejected during settings
validation before the API starts.

When disabled:

1. `POST /api/v1/auth/token` is not registered and is absent from OpenAPI;
2. `/auth/capabilities` reports `legacy_password_enabled=false`;
3. an `Authorization: Bearer ...` request to a protected API is rejected with 401 before JWT resolution; and
4. the browser does not render or briefly assume the password form and clears any in-memory compatibility token.

The Sprint 1 service container remains available for Case and Evidence use cases. Its legacy token codec is not
an admitted authentication path in the OIDC-only process.

## Consequences

- Local demonstrations keep the explicit compatibility login until their environment is migrated.
- Pilot and production deployments require a complete HTTPS OIDC configuration and cannot fall back to password
  authentication when the provider is unavailable.
- Plain HTTP is available only through the explicit `OIDC_ALLOW_INSECURE_HTTP=true` control in `local`/`test`;
  non-local settings reject that control before startup.
- Provider outage degrades login availability; it never re-enables legacy credentials.
- The 2026-08-30 Keycloak qualification proved new-login group/account enforcement, PKCE, CSRF, return path, and
  idle expiry. It also proved that already-issued CSight sessions are not immediately revoked by IdP group removal
  or account disablement. A standard revocation propagation mechanism remains required before pilot admission.

## Verification

- Settings tests reject non-local legacy authentication.
- An injected OIDC runtime under the `pilot` profile exposes no password route and rejects Bearer JWT.
- Login UI test proves that OIDC-only capability never displays password controls.
- Default local tests remain compatible and network-free.
- `make qualify-oidc-keycloak` starts a pinned, isolated Keycloak 26.7.2 stack, returns a fail-closed verdict, and
  removes its temporary containers and database on exit.
