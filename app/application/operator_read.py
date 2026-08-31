"""Authorized operator queue and persisted workflow snapshot use cases."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from datetime import datetime
from typing import Literal, TypedDict, cast
from uuid import UUID

from app.platform.errors import CaseNotFoundError, ValidationError
from app.platform.operator_read import (
    OperatorCasePage,
    OperatorReviewPage,
    QueueSort,
    QueueView,
    WorkflowSnapshot,
)
from app.platform.tenant import Permission, Principal, Role
from app.ports.operator_read import OperatorReadRepository

_CURSOR_VERSION = 2
_MAX_CURSOR_LENGTH = 1024
_MAX_QUERY_LENGTH = 100


def _normalize_query(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    if not normalized:
        return None
    if len(normalized) > _MAX_QUERY_LENGTH:
        raise ValidationError(f"Search text must not exceed {_MAX_QUERY_LENGTH} characters.")
    return normalized


def _query_hash(value: str | None) -> str:
    return hashlib.sha256((value or "").casefold().encode("utf-8")).hexdigest()


class _CursorPayload(TypedDict):
    v: int
    queue: Literal["cases", "reviews"]
    view: str
    sort: str
    query_hash: str
    created_at: str
    id: str


def _decode_cursor(
    value: str | None,
    *,
    queue: Literal["cases", "reviews"],
    view: QueueView,
    sort: QueueSort,
    query: str | None,
) -> tuple[datetime | None, str | None]:
    if value is None:
        return None, None
    try:
        if not value or len(value) > _MAX_CURSOR_LENGTH:
            raise ValueError
        padded = value + "=" * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        raw = json.loads(decoded.decode("utf-8"))
        if not isinstance(raw, dict) or set(raw) != {
            "v",
            "queue",
            "view",
            "sort",
            "query_hash",
            "created_at",
            "id",
        }:
            raise ValueError
        payload = cast(_CursorPayload, raw)
        if (
            payload["v"] != _CURSOR_VERSION
            or payload["queue"] != queue
            or payload["view"] != view.value
            or payload["sort"] != sort.value
            or payload["query_hash"] != _query_hash(query)
        ):
            raise ValueError
        created_at = datetime.fromisoformat(payload["created_at"].replace("Z", "+00:00"))
        UUID(payload["id"])
        if created_at.tzinfo is None:
            raise ValueError
        return created_at, payload["id"]
    except (
        AttributeError,
        binascii.Error,
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        json.JSONDecodeError,
    ) as error:
        raise ValidationError(
            "The queue cursor is invalid for this view, sort, and search."
        ) from error


def _encode_cursor(
    *,
    queue: Literal["cases", "reviews"],
    view: QueueView,
    sort: QueueSort,
    query: str | None,
    created_at: datetime,
    item_id: str,
) -> str:
    payload: _CursorPayload = {
        "v": _CURSOR_VERSION,
        "queue": queue,
        "view": view.value,
        "sort": sort.value,
        "query_hash": _query_hash(query),
        "created_at": created_at.isoformat(),
        "id": item_id,
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


class ListOperatorCases:
    def __init__(self, repository: OperatorReadRepository) -> None:
        self._repository = repository

    def execute(
        self,
        *,
        principal: Principal,
        view: QueueView,
        sort: QueueSort,
        query: str | None,
        limit: int,
        cursor: str | None,
    ) -> OperatorCasePage:
        principal.require(Permission.HUMAN_REVIEW_READ)
        normalized_query = _normalize_query(query)
        after_at, after_id = _decode_cursor(
            cursor, queue="cases", view=view, sort=sort, query=normalized_query
        )
        page = self._repository.list_cases(
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            can_view_all=Role.REVIEWER not in principal.roles or Role.ADMIN in principal.roles,
            view=view,
            sort=sort,
            query=normalized_query,
            limit=limit,
            after_created_at=after_at,
            after_id=after_id,
        )
        next_cursor = None
        if page.has_more and page.items:
            last = page.items[-1]
            next_cursor = _encode_cursor(
                queue="cases",
                view=view,
                sort=sort,
                query=normalized_query,
                created_at=last.created_at,
                item_id=last.case_id,
            )
        return OperatorCasePage(items=page.items, counts=page.counts, next_cursor=next_cursor)


class ListOperatorReviews:
    def __init__(self, repository: OperatorReadRepository) -> None:
        self._repository = repository

    def execute(
        self,
        *,
        principal: Principal,
        view: QueueView,
        sort: QueueSort,
        query: str | None,
        limit: int,
        cursor: str | None,
    ) -> OperatorReviewPage:
        principal.require(Permission.HUMAN_REVIEW_READ)
        normalized_query = _normalize_query(query)
        after_at, after_id = _decode_cursor(
            cursor, queue="reviews", view=view, sort=sort, query=normalized_query
        )
        page = self._repository.list_reviews(
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            can_view_all=Role.REVIEWER not in principal.roles or Role.ADMIN in principal.roles,
            view=view,
            sort=sort,
            query=normalized_query,
            limit=limit,
            after_created_at=after_at,
            after_id=after_id,
        )
        next_cursor = None
        if page.has_more and page.items:
            last = page.items[-1]
            next_cursor = _encode_cursor(
                queue="reviews",
                view=view,
                sort=sort,
                query=normalized_query,
                created_at=last.created_at,
                item_id=last.review_task_id,
            )
        return OperatorReviewPage(items=page.items, counts=page.counts, next_cursor=next_cursor)


class GetWorkflowSnapshot:
    def __init__(self, repository: OperatorReadRepository) -> None:
        self._repository = repository

    def execute(self, *, principal: Principal, case_id: str) -> WorkflowSnapshot:
        principal.require(Permission.HUMAN_REVIEW_READ)
        snapshot = self._repository.get_workflow_snapshot(
            tenant_id=principal.tenant_id,
            case_id=case_id,
        )
        if snapshot is None:
            raise CaseNotFoundError()
        return snapshot


__all__ = ["GetWorkflowSnapshot", "ListOperatorCases", "ListOperatorReviews"]
