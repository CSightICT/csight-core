"""Ports for signed model release verification and append-only activation."""

from datetime import datetime
from typing import Protocol

from app.platform.analysis.enums import AnalysisExecutionMode
from app.platform.model_activation import (
    ActiveLLMRelease,
    ModelActivationEvent,
    ModelReleaseTask,
    RegisteredLLMRelease,
    RuntimeLLMIdentityContract,
    SignedLLMReleaseManifest,
)


class ModelReleaseSignatureVerifier(Protocol):
    def verify(self, value: SignedLLMReleaseManifest) -> bool: ...


class ModelActivationRepository(Protocol):
    def register_release(
        self,
        *,
        tenant_id: str,
        release_id: str,
        value: SignedLLMReleaseManifest,
        registered_by: str,
        registered_at: datetime,
    ) -> tuple[RegisteredLLMRelease, bool]: ...

    def get_release(
        self,
        *,
        tenant_id: str,
        release_id: str,
    ) -> RegisteredLLMRelease | None: ...

    def activate(
        self,
        *,
        event: ModelActivationEvent,
        expected_current_activation_id: str | None,
    ) -> tuple[ModelActivationEvent, bool]: ...

    def get_active(
        self,
        *,
        tenant_id: str,
        task: ModelReleaseTask,
        execution_mode: AnalysisExecutionMode,
    ) -> ActiveLLMRelease | None: ...

    def get_by_activation_id(
        self,
        *,
        tenant_id: str,
        activation_id: str,
    ) -> ActiveLLMRelease | None: ...


class ModelReleaseExecutionGuard(Protocol):
    @property
    def runtime_identity(self) -> RuntimeLLMIdentityContract: ...

    def execute(
        self,
        *,
        tenant_id: str,
        execution_mode: AnalysisExecutionMode,
        task: ModelReleaseTask = ModelReleaseTask.PRODUCT_DEFECT_TEXT_EXTRACTION_V2,
    ) -> ActiveLLMRelease: ...


__all__ = [
    "ModelActivationRepository",
    "ModelReleaseExecutionGuard",
    "ModelReleaseSignatureVerifier",
]
