# ADR-0104: OIDC PKCE with server-side sessions and CSRF protection

- Status: Accepted
- Date: 2026-08-29

## Context

The local password and bearer-token path is useful for development but is not a sufficient pilot
identity boundary. Browser credentials must not expose access tokens to JavaScript, and a tenant or
role asserted only by an external group must not bypass the locally authorized identity record.

## Decision

- Pilot authentication uses OpenID Connect Authorization Code flow with PKCE S256. Login state,
  nonce, verifier, and the allowlisted return path are single-use server records.
- The API exchanges the code over a pooled backchannel and validates an asymmetric signed ID token
  against an allowlist of algorithms, issuer, audience, expiry, nonce, and JWKS. A key miss permits
  one JWKS refresh; it never permits unsigned or symmetric fallback.
- IdP groups map through configuration to exactly one tenant and an allowed role set. A normalized
  email must also match one active local user; the local tenant and roles are authoritative and the
  intersection must be non-empty.
- Browser sessions use an opaque random identifier. Only its SHA-256 digest is stored in the
  database. The cookie is `Secure`, `HttpOnly`, and `SameSite=Lax`. Default absolute expiry is eight
  hours, idle expiry is 30 minutes, and the UI warns five minutes before effective expiry.
- Unsafe requests authenticated by the session cookie require a matching CSRF header. CSRF material
  is held in browser memory, not persistent browser storage. Reauthentication carries an allowlisted
  relative return path back to the current screen.
- Existing bearer authentication remains for one compatibility release. Non-local startup and
  release qualification fail closed when the complete OIDC configuration is absent.

## Consequences

- The browser does not receive an IdP access or refresh token and cannot read the session cookie.
- Session revocation, idle extension, absolute expiry, and CSRF rotation remain server controlled.
- Actual identity-provider login, logout propagation, group mapping, expiry warning, and reentry on
  each target network remain required security E2E evidence; unit tests do not qualify a customer IdP.
- Signed back-channel logout and the required identity-lifecycle coupling are defined by ADR-0117.

## Standard

The protocol baseline is
[OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0-18.html).

## Related decisions

- [ADR-0006](0006-principal-derived-tenant-and-local-jwt.md)
- [ADR-0101](0101-explicit-confirmation-for-quick-review.md)
- [ADR-0105](0105-postgresql-process-roles-and-tenant-rls.md)
- [ADR-0117](0117-oidc-backchannel-logout-and-identity-lifecycle.md)
