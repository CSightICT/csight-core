"""Typed services exposed only to the signed integration intake router."""

from dataclasses import dataclass
from typing import Protocol

from app.application.cases import CreateCaseResult, CreateSignedIntakeCaseCommand
from app.platform.signed_intake import AuthenticatedSignedIntake, SignedIntakeProof


class AuthenticateSignedIntakeService(Protocol):
    def execute(self, proof: SignedIntakeProof) -> AuthenticatedSignedIntake: ...


class CreateSignedIntakeCaseService(Protocol):
    def execute(
        self,
        *,
        authenticated: AuthenticatedSignedIntake,
        command: CreateSignedIntakeCaseCommand,
    ) -> CreateCaseResult: ...


@dataclass(frozen=True, slots=True)
class SignedIntakeServiceContainer:
    authenticate: AuthenticateSignedIntakeService
    create_case: CreateSignedIntakeCaseService
    max_body_bytes: int


__all__ = ["SignedIntakeServiceContainer"]
