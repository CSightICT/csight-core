# ADR-0117: OIDC back-channel logout and identity lifecycle coupling
- Status: Accepted
- Date: 2026-08-30

## Context

OIDC-only login, local-account checks, and short server sessions prevent new unauthorized logins,
but an already issued CSight session cannot observe an external group removal or account disable by
itself. Polling the identity provider on every request would add a remote dependency to every
operator action and would make provider failure an application-wide outage.

## Decision

- Pilot identity providers must support OIDC Back-Channel Logout 1.0 or an equivalent signed,
  server-to-server revocation event. CSight exposes `POST /auth/oidc/backchannel-logout` only when
  the OIDC runtime is configured.
- The API accepts a signed logout token from the configured issuer. It validates the asymmetric
  signature, algorithm, issuer, audience, expiry, issued-at time, JWT ID, logout event claim, and a
  provider subject or session ID. A nonce is prohibited.
- Provider subject and session identifiers are stored with an issuer-scoped SHA-256 capability.
  Logout revokes matching active sessions atomically without tenant context. Replay of the same
  token JWT ID is an idempotent success.
- The append-only logout receipt contains only issuer, opaque hashes, receipt time, and revoked
  count. It never stores the raw token, subject, session ID, access token, or refresh token.
- Group removal and account disable are not considered complete operator actions until the IdP also
  terminates that user's provider session and successfully delivers back-channel logout. A failed
  delivery is an identity-operations incident; CSight does not open password fallback.
- Local/test password compatibility is unchanged. No external business action is introduced.

## Consequences

- An IdP-delivered logout revokes existing CSight sessions without adding a provider call to normal
  API requests.
- A group or account mutation alone does not prove immediate revocation. Pilot onboarding must
  verify the customer's lifecycle automation and retry/alert behavior.
- Provider-wide or browser-initiated logout UX remains a separate concern from the receiving
  security boundary.

## Standard

- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html)

## Related decisions

- [ADR-0104](0104-oidc-pkce-server-session-and-csrf.md)
- [ADR-0116](0116-non-local-oidc-only-authentication.md)
