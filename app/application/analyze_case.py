"""Sprint 0 orchestration for structured LLM and Vision analysis."""

from pydantic import BaseModel, ConfigDict, Field

from app.platform.analysis import (
    AnalysisVersionReferences,
    CustomerRequest,
    LLMAnalysisRequest,
    LLMCaseExtraction,
    VisionAnalysisRequest,
    VisionAnalysisResult,
    VisionTask,
)
from app.ports.llm import LLMProvider
from app.ports.vision import VisionProvider

type ScalarAttribute = str | int | float | bool | None


class AnalyzeCaseCommand(BaseModel):
    """References required to run one append-only analysis run."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    case_id: str = Field(min_length=1)
    analysis_run_id: str = Field(min_length=1)
    customer_message: str = Field(min_length=1)
    image_references: tuple[str, ...] = Field(min_length=1)
    requested_action: CustomerRequest = CustomerRequest.UNSPECIFIED
    prompt_version: str = Field(default="sprint-0", min_length=1)
    vision_task: VisionTask = VisionTask.QUALITY_AND_DEFECT_DETECTION
    attributes: dict[str, ScalarAttribute] = Field(default_factory=dict)


class AnalyzeCaseResult(BaseModel):
    """Normalized provider observations for one run, before policy or review."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    analysis_run_id: str
    versions: AnalysisVersionReferences
    llm: LLMCaseExtraction
    vision: tuple[VisionAnalysisResult, ...]


class AnalyzeCase:
    """Coordinate AI ports without owning policy or final-decision behavior."""

    def __init__(self, llm_provider: LLMProvider, vision_provider: VisionProvider) -> None:
        self._llm_provider = llm_provider
        self._vision_provider = vision_provider

    def execute(self, command: AnalyzeCaseCommand) -> AnalyzeCaseResult:
        """Run provider analysis and return normalized, persistence-ready values.

        Provider exceptions intentionally propagate as typed platform errors. Retry,
        partial-failure persistence, and status transitions belong to later workflow
        and repository use cases rather than this Sprint 0 skeleton.
        """

        llm_result = self._llm_provider.extract_case(
            LLMAnalysisRequest(
                case_id=command.case_id,
                customer_message=command.customer_message,
                requested_action=command.requested_action,
                prompt_version=command.prompt_version,
                attributes=command.attributes,
            )
        )
        vision_results = tuple(
            self._vision_provider.analyze_image(
                VisionAnalysisRequest(
                    case_id=command.case_id,
                    image_reference=image_reference,
                    task=command.vision_task,
                )
            )
            for image_reference in command.image_references
        )
        return AnalyzeCaseResult(
            case_id=command.case_id,
            analysis_run_id=command.analysis_run_id,
            versions=AnalysisVersionReferences(
                llm_model=llm_result.model,
                vision_model=vision_results[0].model,
                prompt_version=command.prompt_version,
            ),
            llm=llm_result,
            vision=vision_results,
        )
