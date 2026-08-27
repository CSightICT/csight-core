"""Typed application-service bundle consumed by the Sprint 1 HTTP interface.

The interface depends only on application use-case shapes.  Infrastructure
composition stays in the bootstrap layer and can inject this immutable bundle
into :func:`app.main.create_app`.
"""

from dataclasses import dataclass
from typing import BinaryIO, Protocol

from app.application.analysis import (
    AnalysisRunDetail,
    AnalysisRunPage,
    ListAnalysisRunsQuery,
    StartTextAnalysisCommand,
    StartTextAnalysisResult,
)
from app.application.auth import LoginCommand, LoginResult
from app.application.cases import (
    CasePage,
    CreateCaseCommand,
    CreateCaseResult,
    ListCasesQuery,
)
from app.application.evidence import EvidenceAccessUrl
from app.application.grounding import (
    GetGroundedExplanationRun,
    ListGroundedExplanationRuns,
    StartGroundedExplanation,
)
from app.application.human_review import (
    GetHumanReviewTask,
    HumanReviewActions,
    ListHumanReviewTasks,
)
from app.application.policy_engine import (
    GetPolicyEvaluation,
    ListPolicyEvaluations,
    StartPolicyEvaluation,
)
from app.application.policy_query_runs import (
    GetPolicyRetrievalRun,
    ListPolicyRetrievalRuns,
    StartPolicyRetrievalRun,
)
from app.application.policy_retrieval import SearchPolicyClauses
from app.platform.analysis import AnalysisRun
from app.platform.case import Case, CaseStatusTransition
from app.platform.evidence import EvidenceMetadata, EvidenceType
from app.platform.tenant import Principal


class AuthenticateUserService(Protocol):
    def execute(self, command: LoginCommand) -> LoginResult: ...


class ResolvePrincipalService(Protocol):
    def execute(self, token: str) -> Principal: ...


class CreateCaseService(Protocol):
    def execute(
        self,
        *,
        principal: Principal,
        command: CreateCaseCommand,
    ) -> CreateCaseResult: ...


class ListCasesService(Protocol):
    def execute(self, *, principal: Principal, query: ListCasesQuery) -> CasePage: ...


class GetCaseService(Protocol):
    def execute(self, *, principal: Principal, case_id: str) -> Case: ...


class GetCaseStatusHistoryService(Protocol):
    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
    ) -> tuple[CaseStatusTransition, ...]: ...


class AddImageEvidenceService(Protocol):
    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        content: BinaryIO,
        filename: str | None,
        declared_content_type: str | None,
        evidence_type: EvidenceType = EvidenceType.IMAGE,
    ) -> EvidenceMetadata: ...


class ListCaseEvidenceService(Protocol):
    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
    ) -> tuple[EvidenceMetadata, ...]: ...


class GetEvidenceMetadataService(Protocol):
    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        evidence_id: str,
    ) -> EvidenceMetadata: ...


class CreateEvidenceAccessUrlService(Protocol):
    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        evidence_id: str,
    ) -> EvidenceAccessUrl: ...


class StartTextAnalysisService(Protocol):
    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        command: StartTextAnalysisCommand,
    ) -> StartTextAnalysisResult: ...


class ListAnalysisRunsService(Protocol):
    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        query: ListAnalysisRunsQuery,
    ) -> AnalysisRunPage: ...


class GetAnalysisRunService(Protocol):
    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        analysis_run_id: str,
    ) -> AnalysisRunDetail: ...


class GetLatestAnalysisRunService(Protocol):
    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
    ) -> AnalysisRun | None: ...


@dataclass(frozen=True, slots=True)
class Sprint1ServiceContainer:
    """All Sprint 1 use cases required by the HTTP boundary."""

    authenticate_user: AuthenticateUserService
    resolve_principal: ResolvePrincipalService
    create_case: CreateCaseService
    list_cases: ListCasesService
    get_case: GetCaseService
    get_case_status_history: GetCaseStatusHistoryService
    add_image_evidence: AddImageEvidenceService
    list_case_evidence: ListCaseEvidenceService
    get_evidence_metadata: GetEvidenceMetadataService
    create_evidence_access_url: CreateEvidenceAccessUrlService


@dataclass(frozen=True, slots=True)
class Sprint2ServiceContainer:
    """Analysis use cases optionally composed into the HTTP application."""

    start_text_analysis: StartTextAnalysisService
    list_analysis_runs: ListAnalysisRunsService
    get_analysis_run: GetAnalysisRunService
    get_latest_analysis_run: GetLatestAnalysisRunService


@dataclass(frozen=True, slots=True)
class Sprint4BServiceContainer:
    """Read-only policy retrieval use cases composed by the bootstrap layer."""

    search_policy_clauses: SearchPolicyClauses


@dataclass(frozen=True, slots=True)
class Sprint4C2ServiceContainer:
    """Case-to-policy retrieval run services."""

    start_policy_retrieval_run: StartPolicyRetrievalRun
    list_policy_retrieval_runs: ListPolicyRetrievalRuns
    get_policy_retrieval_run: GetPolicyRetrievalRun


@dataclass(frozen=True, slots=True)
class Sprint4C3AServiceContainer:
    """Citation-pack and structurally grounded explanation services."""

    start_grounded_explanation: StartGroundedExplanation
    list_grounded_explanations: ListGroundedExplanationRuns
    get_grounded_explanation: GetGroundedExplanationRun


@dataclass(frozen=True, slots=True)
class Sprint5AServiceContainer:
    """Versioned deterministic policy evaluation services."""

    start_policy_evaluation: StartPolicyEvaluation
    list_policy_evaluations: ListPolicyEvaluations
    get_policy_evaluation: GetPolicyEvaluation


@dataclass(frozen=True, slots=True)
class Sprint5BServiceContainer:
    """Human-only review queue and action services."""

    list_tasks: ListHumanReviewTasks
    get_task: GetHumanReviewTask
    actions: HumanReviewActions
