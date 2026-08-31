"""Typed service container for operator read projections."""

from dataclasses import dataclass

from app.application.operator_read import (
    GetWorkflowSnapshot,
    ListOperatorCases,
    ListOperatorReviews,
)


@dataclass(frozen=True, slots=True)
class OperatorReadServiceContainer:
    list_cases: ListOperatorCases
    list_reviews: ListOperatorReviews
    get_workflow_snapshot: GetWorkflowSnapshot


__all__ = ["OperatorReadServiceContainer"]
