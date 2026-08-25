"""pwdlib Argon2 password-hashing adapter."""

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError


class Argon2PasswordHasher:
    """Use pwdlib's recommended Argon2id profile and a dummy verification path."""

    def __init__(self) -> None:
        self._password_hash = PasswordHash.recommended()
        self._dummy_hash = self._password_hash.hash("csight-dummy-password")

    def hash_password(self, password: str) -> str:
        return self._password_hash.hash(password)

    def verify_password(self, password: str, encoded_hash: str | None) -> bool:
        candidate_hash = encoded_hash if encoded_hash is not None else self._dummy_hash
        try:
            verified = self._password_hash.verify(password, candidate_hash)
        except UnknownHashError:
            self._password_hash.verify(password, self._dummy_hash)
            return False
        return verified if encoded_hash is not None else False
