"""Operating-system CSPRNG adapter for OIDC browser and CSRF bearer secrets."""

import secrets


class SystemSecureTokenGenerator:
    def token_urlsafe(self, *, entropy_bytes: int) -> str:
        if not 16 <= entropy_bytes <= 128:
            raise ValueError("entropy_bytes must be between 16 and 128")
        return secrets.token_urlsafe(entropy_bytes)
