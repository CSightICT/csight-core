"""One-statement PostgreSQL adapter for low-cardinality operations reads."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.tenant_context import tenant_context
from app.platform.operations import (
    ActiveVersionSnapshot,
    ComponentFailureSummary,
    OperationsFailures,
    OperationsOverview,
    ProcessingOperationsSnapshot,
    QueueOperationsSnapshot,
)

_RELIABLE_OUTBOXES: tuple[tuple[str, str, str], ...] = (
    ("policy_retrieval", "policy_retrieval", "policy_retrieval_outbox_events"),
    ("grounded_explanation", "grounded_explanation", "grounded_explanation_outbox_events"),
    ("policy_evaluation", "policy_evaluation", "policy_evaluation_outbox_events"),
    ("human_review", "human_review", "human_review_request_events"),
    ("case_resolution", "case_resolution", "case_resolution_request_events"),
    ("action_simulation", "action_simulation", "external_action_simulation_request_events"),
)


def _reliable_queue_select(queue: str, table: str) -> str:
    return f"""
        SELECT '{queue}'::text AS queue,
               status,
               created_at,
               status IN ('PENDING','PROCESSING','PUBLISHED') AS is_backlog,
               status = 'PENDING' AS is_pending,
               status = 'PROCESSING' AS is_processing,
               status = 'PUBLISHED' AS is_published_unconsumed,
               status = 'FAILED' AS is_failed,
               (status IN ('PENDING','PROCESSING','PUBLISHED')
                   AND (attempt_count > 1 OR consumer_attempt_count > 1)) AS is_retry,
               ((status = 'PENDING' AND available_at <= :stalled_before)
                   OR (status = 'PROCESSING' AND claimed_at <= :stalled_before)
                   OR (status = 'PUBLISHED' AND published_at <= :stalled_before)) AS is_stalled,
               CASE WHEN status = 'CONSUMED' THEN consumed_at END AS healthy_at
          FROM {table}
         WHERE tenant_id = CAST(:tenant_id AS uuid)
    """


_QUEUE_EVENTS_SQL = "\nUNION ALL\n".join(
    (
        """
        SELECT 'analysis_dispatch'::text AS queue,
               status,
               created_at,
               status IN ('PENDING','PROCESSING') AS is_backlog,
               status = 'PENDING' AS is_pending,
               status = 'PROCESSING' AS is_processing,
               false AS is_published_unconsumed,
               status = 'FAILED' AS is_failed,
               (status IN ('PENDING','PROCESSING') AND attempt_count > 1) AS is_retry,
               ((status = 'PENDING' AND available_at <= :stalled_before)
                   OR (status = 'PROCESSING' AND claimed_at <= :stalled_before)) AS is_stalled,
               CASE WHEN status = 'PUBLISHED' THEN published_at END AS healthy_at
          FROM outbox_events
         WHERE tenant_id = CAST(:tenant_id AS uuid)
        """,
        *(_reliable_queue_select(queue, table) for queue, _component, table in _RELIABLE_OUTBOXES),
    )
)

_OVERVIEW_SQL = f"""
WITH queue_catalog(queue, ordinal) AS (
    VALUES ('analysis_dispatch', 1),
           ('policy_retrieval', 2),
           ('grounded_explanation', 3),
           ('policy_evaluation', 4),
           ('human_review', 5),
           ('case_resolution', 6),
           ('action_simulation', 7)
),
queue_events AS (
    {_QUEUE_EVENTS_SQL}
),
queue_stats AS (
    SELECT queue,
           count(*) FILTER (WHERE is_backlog)::integer AS backlog_count,
           count(*) FILTER (WHERE is_pending)::integer AS pending_count,
           count(*) FILTER (WHERE is_processing)::integer AS processing_count,
           count(*) FILTER (WHERE is_published_unconsumed)::integer
               AS published_unconsumed_count,
           count(*) FILTER (WHERE is_failed)::integer AS failed_count,
           count(*) FILTER (WHERE is_retry)::integer AS retry_count,
           count(*) FILTER (WHERE is_stalled)::integer AS stalled_count,
           min(created_at) FILTER (WHERE is_backlog) AS oldest_backlog_at,
           max(healthy_at) AS last_healthy_at
      FROM queue_events
     GROUP BY queue
),
process_catalog(component, ordinal) AS (
    VALUES ('analysis', 1),
           ('policy_retrieval', 2),
           ('grounded_explanation', 3),
           ('policy_evaluation', 4),
           ('human_review', 5),
           ('case_resolution', 6),
           ('action_simulation', 7)
),
process_events AS (
    SELECT 'analysis'::text AS component,
           status IN ('QUEUED','RUNNING','RETRY_WAITING') AS is_backlog,
           status = 'RUNNING' AS is_running,
           status = 'RETRY_WAITING' AS is_retry,
           status = 'PARTIAL_SUCCESS' AS is_partial,
           status = 'FAILED' AS is_failed,
           (
               (status = 'QUEUED' AND requested_at <= :stalled_before)
               OR (status = 'RUNNING' AND EXISTS (
                   SELECT 1 FROM analysis_stage_runs AS stalled_stage
                    WHERE stalled_stage.tenant_id = analysis_runs.tenant_id
                      AND stalled_stage.analysis_run_id = analysis_runs.id
                      AND stalled_stage.status = 'RUNNING'
                      AND stalled_stage.lease_expires_at <= :now
               ))
               OR (status = 'RETRY_WAITING' AND EXISTS (
                   SELECT 1 FROM analysis_stage_runs AS retry_stage
                    WHERE retry_stage.tenant_id = analysis_runs.tenant_id
                      AND retry_stage.analysis_run_id = analysis_runs.id
                      AND retry_stage.status = 'RETRY_WAITING'
                      AND retry_stage.next_attempt_at <= :stalled_before
               ))
           ) AS is_stalled,
           requested_at AS backlog_at,
           CASE WHEN status = 'SUCCEEDED' THEN completed_at END AS healthy_at
      FROM analysis_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid)
    UNION ALL
    SELECT 'policy_retrieval',
           status IN ('QUEUED','RUNNING'),
           status = 'RUNNING',
           status = 'QUEUED' AND execution_attempt_count > 0,
           false,
           status = 'FAILED',
           ((status = 'RUNNING' AND lease_expires_at <= :now)
              OR (status = 'QUEUED' AND created_at <= :stalled_before AND (
                  NOT EXISTS (
                      SELECT 1 FROM policy_retrieval_outbox_events AS event
                       WHERE event.tenant_id = policy_retrieval_runs.tenant_id
                         AND event.retrieval_run_id = policy_retrieval_runs.id
                  )
                  OR EXISTS (
                      SELECT 1 FROM policy_retrieval_outbox_events AS event
                       WHERE event.tenant_id = policy_retrieval_runs.tenant_id
                         AND event.retrieval_run_id = policy_retrieval_runs.id
                         AND ((event.status = 'PENDING' AND event.available_at <= :stalled_before)
                           OR (event.status = 'PROCESSING'
                               AND event.claimed_at <= :stalled_before)
                           OR (event.status = 'PUBLISHED'
                               AND event.published_at <= :stalled_before))
                  )
              ))),
           created_at,
           CASE WHEN status = 'SUCCEEDED' THEN completed_at END
      FROM policy_retrieval_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid)
    UNION ALL
    SELECT 'grounded_explanation',
           status IN ('QUEUED','RUNNING'),
           status = 'RUNNING',
           status = 'QUEUED' AND execution_attempt_count > 0,
           false,
           status = 'FAILED',
           ((status = 'RUNNING' AND lease_expires_at <= :now)
              OR (status = 'QUEUED' AND created_at <= :stalled_before AND (
                  NOT EXISTS (
                      SELECT 1 FROM grounded_explanation_outbox_events AS event
                       WHERE event.tenant_id = grounded_explanation_runs.tenant_id
                         AND event.grounded_explanation_run_id = grounded_explanation_runs.id
                  )
                  OR EXISTS (
                      SELECT 1 FROM grounded_explanation_outbox_events AS event
                       WHERE event.tenant_id = grounded_explanation_runs.tenant_id
                         AND event.grounded_explanation_run_id = grounded_explanation_runs.id
                         AND ((event.status = 'PENDING' AND event.available_at <= :stalled_before)
                           OR (event.status = 'PROCESSING'
                               AND event.claimed_at <= :stalled_before)
                           OR (event.status = 'PUBLISHED'
                               AND event.published_at <= :stalled_before))
                  )
              ))),
           created_at,
           CASE WHEN status = 'SUCCEEDED' THEN completed_at END
      FROM grounded_explanation_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid)
    UNION ALL
    SELECT 'policy_evaluation',
           status IN ('QUEUED','RUNNING'),
           status = 'RUNNING',
           status = 'QUEUED' AND execution_attempt_count > 0,
           false,
           status = 'FAILED',
           ((status = 'RUNNING' AND lease_expires_at <= :now)
              OR (status = 'QUEUED' AND created_at <= :stalled_before AND (
                  NOT EXISTS (
                      SELECT 1 FROM policy_evaluation_outbox_events AS event
                       WHERE event.tenant_id = policy_evaluation_runs.tenant_id
                         AND event.policy_evaluation_run_id = policy_evaluation_runs.id
                  )
                  OR EXISTS (
                      SELECT 1 FROM policy_evaluation_outbox_events AS event
                       WHERE event.tenant_id = policy_evaluation_runs.tenant_id
                         AND event.policy_evaluation_run_id = policy_evaluation_runs.id
                         AND ((event.status = 'PENDING' AND event.available_at <= :stalled_before)
                           OR (event.status = 'PROCESSING'
                               AND event.claimed_at <= :stalled_before)
                           OR (event.status = 'PUBLISHED'
                               AND event.published_at <= :stalled_before))
                  )
              ))),
           created_at,
           CASE WHEN status = 'SUCCEEDED' THEN completed_at END
      FROM policy_evaluation_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid)
    UNION ALL
    SELECT 'human_review',
           status <> 'RESOLVED',
           status = 'CLAIMED',
           false,
           false,
           false,
           false,
           created_at,
           CASE WHEN status = 'RESOLVED' THEN resolved_at END
      FROM human_review_tasks
     WHERE tenant_id = CAST(:tenant_id AS uuid)
    UNION ALL
    SELECT 'case_resolution',
           status IN ('DECISION_RECORDED','ACTION_READY','ACTION_DRY_RUN_PENDING'),
           status = 'ACTION_DRY_RUN_PENDING',
           status IN ('DECISION_RECORDED','ACTION_READY') AND execution_attempt_count > 0,
           false,
           status = 'ACTION_DRY_RUN_FAILED' OR failure_code IS NOT NULL,
           ((status = 'ACTION_DRY_RUN_PENDING' AND lease_expires_at <= :now)
              OR (status IN ('DECISION_RECORDED','ACTION_READY')
                  AND updated_at <= :stalled_before)),
           created_at,
           CASE WHEN status IN (
               'ACTION_NOT_REQUIRED','MANUAL_FOLLOW_UP_REQUIRED','ACTION_NEEDS_INPUT',
               'ACTION_DRY_RUN_VALIDATED'
           ) THEN updated_at END
      FROM case_resolutions
     WHERE tenant_id = CAST(:tenant_id AS uuid)
    UNION ALL
    SELECT 'action_simulation',
           status = 'RUNNING',
           status = 'RUNNING',
           false,
           false,
           status = 'FAILED',
           status = 'RUNNING' AND started_at <= :stalled_before,
           started_at,
           CASE WHEN status = 'SUCCEEDED' THEN completed_at END
      FROM external_action_simulation_attempts
     WHERE tenant_id = CAST(:tenant_id AS uuid)
),
process_stats AS (
    SELECT component,
           count(*) FILTER (WHERE is_backlog)::integer AS backlog_count,
           count(*) FILTER (WHERE is_running)::integer AS running_count,
           count(*) FILTER (WHERE is_retry)::integer AS retry_count,
           count(*) FILTER (WHERE is_partial)::integer AS partial_success_count,
           count(*) FILTER (WHERE is_failed)::integer AS failed_count,
           count(*) FILTER (WHERE is_stalled)::integer AS stalled_count,
           min(backlog_at) FILTER (WHERE is_backlog) AS oldest_backlog_at,
           max(healthy_at) AS last_healthy_at
      FROM process_events
     GROUP BY component
),
latest_analysis_stage AS (
    SELECT DISTINCT ON (stage_type)
           stage_type, model_name, model_version, model_revision,
           prompt_name, prompt_version, created_at
      FROM analysis_stage_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid)
     ORDER BY stage_type, created_at DESC, id DESC
),
latest_grounding_result AS (
    SELECT result.*
      FROM grounded_explanation_results AS result
     WHERE result.tenant_id = CAST(:tenant_id AS uuid)
     ORDER BY result.created_at DESC, result.id DESC
     LIMIT 1
),
active_policy AS (
    SELECT rule_set.rule_set_name, rule_set.rule_set_version,
           activation.activated_at
      FROM policy_rule_set_activations AS activation
      JOIN policy_rule_sets AS rule_set
        ON rule_set.tenant_id = activation.tenant_id
       AND rule_set.id = activation.rule_set_id
     WHERE activation.tenant_id = CAST(:tenant_id AS uuid)
       AND activation.retired_at IS NULL
),
active_index AS (
    SELECT index_version.*, embedding.model_artifact AS embedding_model,
           embedding.model_revision AS embedding_revision,
           embedding.profile_version AS embedding_version
      FROM policy_index_versions AS index_version
      JOIN policy_embedding_profiles AS embedding
        ON embedding.id = index_version.embedding_profile_id
     WHERE index_version.tenant_id = CAST(:tenant_id AS uuid)
       AND index_version.status = 'ACTIVE'
),
active_reranker AS (
    SELECT profile.profile_name, profile.profile_version,
           reranker.model_artifact, reranker.model_revision,
           profile.activated_at, profile.created_at
      FROM policy_retrieval_execution_profiles AS profile
      JOIN active_index AS index_version
        ON index_version.id = profile.base_index_version_id
      JOIN policy_reranker_profiles AS reranker
        ON reranker.id = profile.reranker_profile_id
     WHERE profile.status = 'ACTIVE'
),
latest_threshold AS (
    SELECT result.threshold_version, assessment.threshold, result.created_at
      FROM vision_image_assessments AS assessment
      JOIN vision_analysis_results AS result
        ON result.tenant_id = assessment.tenant_id
       AND result.id = assessment.vision_result_id
     WHERE assessment.tenant_id = CAST(:tenant_id AS uuid)
     ORDER BY result.created_at DESC, result.id DESC
     LIMIT 1
),
version_rows AS (
    SELECT 'model'::text AS kind,
           'analysis_' || lower(stage_type) AS component,
           model_name AS name,
           model_version AS version,
           model_revision AS revision,
           NULL::double precision AS numeric_value,
           'latest_run_snapshot'::text AS source,
           created_at AS observed_at
      FROM latest_analysis_stage
    UNION ALL
    SELECT 'prompt', 'analysis_' || lower(stage_type), prompt_name, prompt_version,
           NULL, NULL, 'latest_run_snapshot', created_at
      FROM latest_analysis_stage
    UNION ALL
    SELECT 'model', 'grounded_explanation', model_name, model_version, model_revision,
           NULL, 'latest_succeeded_result', created_at
      FROM latest_grounding_result
    UNION ALL
    SELECT 'prompt', 'grounded_explanation', prompt_name, prompt_version, NULL,
           NULL, 'latest_succeeded_result', created_at
      FROM latest_grounding_result
    UNION ALL
    SELECT 'policy', 'policy_evaluation', rule_set_name, rule_set_version, NULL,
           NULL, 'active_record', activated_at
      FROM active_policy
    UNION ALL
    SELECT 'index', 'policy_retrieval', index_name, index_version, NULL,
           NULL, 'active_record', COALESCE(activated_at, created_at)
      FROM active_index
    UNION ALL
    SELECT 'model', 'policy_embedding', embedding_model, embedding_version,
           embedding_revision, NULL, 'active_record', COALESCE(activated_at, created_at)
      FROM active_index
    UNION ALL
    SELECT 'model', 'policy_reranker', model_artifact, profile_version, model_revision,
           NULL, 'active_record', COALESCE(activated_at, created_at)
      FROM active_reranker
    UNION ALL
    SELECT 'threshold', 'vision_any_defect', 'any_defect_threshold', threshold_version,
           NULL, threshold, 'latest_succeeded_result', created_at
      FROM latest_threshold
),
bounded_version_rows AS (
    SELECT *
      FROM version_rows
     ORDER BY kind, component, name, version
     LIMIT 64
),
response_rows AS (
    SELECT 'queue'::text AS section, catalog.ordinal,
           jsonb_build_object(
               'queue', catalog.queue,
               'backlog_count', COALESCE(stats.backlog_count, 0),
               'pending_count', COALESCE(stats.pending_count, 0),
               'processing_count', COALESCE(stats.processing_count, 0),
               'published_unconsumed_count',
                   COALESCE(stats.published_unconsumed_count, 0),
               'failed_count', COALESCE(stats.failed_count, 0),
               'retry_count', COALESCE(stats.retry_count, 0),
               'stalled_count', COALESCE(stats.stalled_count, 0),
               'oldest_backlog_age_seconds', CASE
                   WHEN stats.oldest_backlog_at IS NULL THEN NULL
                   ELSE GREATEST(
                       0,
                       floor(extract(epoch FROM (:now - stats.oldest_backlog_at)))::bigint
                   )
               END,
               'last_healthy_at', stats.last_healthy_at
           ) AS payload
      FROM queue_catalog AS catalog
      LEFT JOIN queue_stats AS stats ON stats.queue = catalog.queue
    UNION ALL
    SELECT 'processing', 100 + catalog.ordinal,
           jsonb_build_object(
               'component', catalog.component,
               'backlog_count', COALESCE(stats.backlog_count, 0),
               'running_count', COALESCE(stats.running_count, 0),
               'retry_count', COALESCE(stats.retry_count, 0),
               'partial_success_count', COALESCE(stats.partial_success_count, 0),
               'failed_count', COALESCE(stats.failed_count, 0),
               'stalled_count', COALESCE(stats.stalled_count, 0),
               'oldest_backlog_age_seconds', CASE
                   WHEN stats.oldest_backlog_at IS NULL THEN NULL
                   ELSE GREATEST(
                       0,
                       floor(extract(epoch FROM (:now - stats.oldest_backlog_at)))::bigint
                   )
               END,
               'last_healthy_at', stats.last_healthy_at
           )
      FROM process_catalog AS catalog
      LEFT JOIN process_stats AS stats ON stats.component = catalog.component
    UNION ALL
    SELECT 'version', 200 + row_number() OVER (
               ORDER BY kind, component, name, version
           )::integer,
           jsonb_build_object(
               'kind', kind,
               'component', component,
               'name', name,
               'version', version,
               'revision', revision,
               'numeric_value', numeric_value,
               'source', source,
               'observed_at', observed_at
           )
      FROM bounded_version_rows
)
SELECT section, payload
  FROM response_rows
 ORDER BY ordinal
"""


def _legacy_failure_signals() -> str:
    return """
        SELECT 'analysis'::text AS component, 'FAILED'::text AS category,
               CASE WHEN last_error ~ '^[A-Z][A-Z0-9_]{1,127}$'
                    THEN last_error ELSE 'OUTBOX_DISPATCH_FAILED' END AS failure_code,
               updated_at AS occurred_at
          FROM outbox_events
         WHERE tenant_id = CAST(:tenant_id AS uuid)
           AND status = 'FAILED' AND updated_at >= :since
        UNION ALL
        SELECT 'analysis', 'RETRY', 'RETRY_SCHEDULED', updated_at
          FROM outbox_events
         WHERE tenant_id = CAST(:tenant_id AS uuid)
           AND attempt_count > 1 AND status IN ('PENDING','PROCESSING')
           AND updated_at >= :since
        UNION ALL
        SELECT 'analysis', 'STALLED', 'DELIVERY_STALLED', :now
          FROM outbox_events
         WHERE tenant_id = CAST(:tenant_id AS uuid)
           AND ((status = 'PENDING' AND available_at <= :stalled_before)
             OR (status = 'PROCESSING' AND claimed_at <= :stalled_before))
    """


def _reliable_failure_signals(component: str, table: str) -> str:
    return f"""
        SELECT '{component}'::text AS component, 'FAILED'::text AS category,
               CASE WHEN failure_code ~ '^[A-Z][A-Z0-9_]{{1,127}}$'
                    THEN failure_code ELSE 'UNCLASSIFIED_FAILURE' END AS failure_code,
               failed_at AS occurred_at
          FROM {table}
         WHERE tenant_id = CAST(:tenant_id AS uuid)
           AND status = 'FAILED' AND failed_at >= :since
        UNION ALL
        SELECT '{component}', 'RETRY', 'RETRY_SCHEDULED',
               GREATEST(created_at, available_at, claimed_at, published_at, consumed_at)
          FROM {table}
         WHERE tenant_id = CAST(:tenant_id AS uuid)
           AND status IN ('PENDING','PROCESSING','PUBLISHED')
           AND (attempt_count > 1 OR consumer_attempt_count > 1)
           AND GREATEST(created_at, available_at, claimed_at, published_at, consumed_at) >= :since
        UNION ALL
        SELECT '{component}', 'STALLED', 'DELIVERY_STALLED', :now
          FROM {table}
         WHERE tenant_id = CAST(:tenant_id AS uuid)
           AND ((status = 'PENDING' AND available_at <= :stalled_before)
             OR (status = 'PROCESSING' AND claimed_at <= :stalled_before)
             OR (status = 'PUBLISHED' AND published_at <= :stalled_before))
    """


_OUTBOX_FAILURE_SIGNALS = "\nUNION ALL\n".join(
    (
        _legacy_failure_signals(),
        *(
            _reliable_failure_signals(component, table)
            for _queue, component, table in _RELIABLE_OUTBOXES
        ),
    )
)

_FAILURES_SQL = f"""
WITH component_catalog(component, ordinal) AS (
    VALUES ('analysis', 1),
           ('policy_retrieval', 2),
           ('grounded_explanation', 3),
           ('policy_evaluation', 4),
           ('human_review', 5),
           ('case_resolution', 6),
           ('action_simulation', 7)
),
signals AS (
    SELECT 'analysis'::text AS component, 'FAILED'::text AS category,
           CASE WHEN failure_code ~ '^[A-Z][A-Z0-9_]{{1,127}}$'
                THEN failure_code ELSE 'UNCLASSIFIED_FAILURE' END AS failure_code,
           completed_at AS occurred_at
      FROM analysis_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid)
       AND status = 'FAILED' AND completed_at >= :since
    UNION ALL
    SELECT 'analysis', 'PARTIAL_SUCCESS', NULL, completed_at
      FROM analysis_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid)
       AND status = 'PARTIAL_SUCCESS' AND completed_at >= :since
    UNION ALL
    SELECT 'analysis', 'RETRY', 'RETRY_SCHEDULED', updated_at
      FROM analysis_stage_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid)
       AND status = 'RETRY_WAITING' AND updated_at >= :since
    UNION ALL
    SELECT 'analysis', 'STALLED', 'PROCESSING_STALLED', :now
      FROM analysis_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid)
       AND ((status = 'QUEUED' AND requested_at <= :stalled_before)
         OR (status = 'RUNNING' AND EXISTS (
             SELECT 1 FROM analysis_stage_runs AS stage
              WHERE stage.tenant_id = analysis_runs.tenant_id
                AND stage.analysis_run_id = analysis_runs.id
                AND stage.status = 'RUNNING' AND stage.lease_expires_at <= :now
         ))
         OR (status = 'RETRY_WAITING' AND EXISTS (
             SELECT 1 FROM analysis_stage_runs AS stage
              WHERE stage.tenant_id = analysis_runs.tenant_id
                AND stage.analysis_run_id = analysis_runs.id
                AND stage.status = 'RETRY_WAITING'
                AND stage.next_attempt_at <= :stalled_before
         )))
    UNION ALL
    SELECT 'policy_retrieval', 'FAILED',
           CASE WHEN failure_code ~ '^[A-Z][A-Z0-9_]{{1,127}}$'
                THEN failure_code ELSE 'UNCLASSIFIED_FAILURE' END,
           completed_at
      FROM policy_retrieval_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid)
       AND status = 'FAILED' AND completed_at >= :since
    UNION ALL
    SELECT 'policy_retrieval', 'RETRY', 'RETRY_SCHEDULED', created_at
      FROM policy_retrieval_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid)
       AND status = 'QUEUED' AND execution_attempt_count > 0 AND created_at >= :since
    UNION ALL
    SELECT 'policy_retrieval', 'STALLED', 'PROCESSING_STALLED', :now
      FROM policy_retrieval_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid)
       AND ((status = 'RUNNING' AND lease_expires_at <= :now)
         OR (status = 'QUEUED' AND created_at <= :stalled_before))
    UNION ALL
    SELECT 'grounded_explanation', 'FAILED',
           CASE WHEN failure_code ~ '^[A-Z][A-Z0-9_]{{1,127}}$'
                THEN failure_code ELSE 'UNCLASSIFIED_FAILURE' END,
           completed_at
      FROM grounded_explanation_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid)
       AND status = 'FAILED' AND completed_at >= :since
    UNION ALL
    SELECT 'grounded_explanation', 'RETRY', 'RETRY_SCHEDULED', created_at
      FROM grounded_explanation_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid)
       AND status = 'QUEUED' AND execution_attempt_count > 0 AND created_at >= :since
    UNION ALL
    SELECT 'grounded_explanation', 'STALLED', 'PROCESSING_STALLED', :now
      FROM grounded_explanation_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid)
       AND ((status = 'RUNNING' AND lease_expires_at <= :now)
         OR (status = 'QUEUED' AND created_at <= :stalled_before))
    UNION ALL
    SELECT 'policy_evaluation', 'FAILED',
           CASE WHEN failure_code ~ '^[A-Z][A-Z0-9_]{{1,127}}$'
                THEN failure_code ELSE 'UNCLASSIFIED_FAILURE' END,
           completed_at
      FROM policy_evaluation_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid)
       AND status = 'FAILED' AND completed_at >= :since
    UNION ALL
    SELECT 'policy_evaluation', 'RETRY', 'RETRY_SCHEDULED', created_at
      FROM policy_evaluation_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid)
       AND status = 'QUEUED' AND execution_attempt_count > 0 AND created_at >= :since
    UNION ALL
    SELECT 'policy_evaluation', 'STALLED', 'PROCESSING_STALLED', :now
      FROM policy_evaluation_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid)
       AND ((status = 'RUNNING' AND lease_expires_at <= :now)
         OR (status = 'QUEUED' AND created_at <= :stalled_before))
    UNION ALL
    SELECT 'case_resolution', 'FAILED',
           CASE WHEN failure_code ~ '^[A-Z][A-Z0-9_]{{1,127}}$'
                THEN failure_code ELSE 'UNCLASSIFIED_FAILURE' END,
           updated_at
      FROM case_resolutions
     WHERE tenant_id = CAST(:tenant_id AS uuid)
       AND (status = 'ACTION_DRY_RUN_FAILED' OR failure_code IS NOT NULL)
       AND updated_at >= :since
    UNION ALL
    SELECT 'case_resolution', 'RETRY', 'RETRY_SCHEDULED', updated_at
      FROM case_resolutions
     WHERE tenant_id = CAST(:tenant_id AS uuid)
       AND status IN ('DECISION_RECORDED','ACTION_READY')
       AND execution_attempt_count > 0 AND updated_at >= :since
    UNION ALL
    SELECT 'case_resolution', 'STALLED', 'PROCESSING_STALLED', :now
      FROM case_resolutions
     WHERE tenant_id = CAST(:tenant_id AS uuid)
       AND ((status = 'ACTION_DRY_RUN_PENDING' AND lease_expires_at <= :now)
         OR (status IN ('DECISION_RECORDED','ACTION_READY')
             AND updated_at <= :stalled_before))
    UNION ALL
    SELECT 'action_simulation', 'FAILED',
           CASE WHEN failure_code ~ '^[A-Z][A-Z0-9_]{{1,127}}$'
                THEN failure_code ELSE 'UNCLASSIFIED_FAILURE' END,
           completed_at
      FROM external_action_simulation_attempts
     WHERE tenant_id = CAST(:tenant_id AS uuid)
       AND status = 'FAILED' AND completed_at >= :since
    UNION ALL
    SELECT 'action_simulation', 'STALLED', 'PROCESSING_STALLED', :now
      FROM external_action_simulation_attempts
     WHERE tenant_id = CAST(:tenant_id AS uuid)
       AND status = 'RUNNING' AND started_at <= :stalled_before
    UNION ALL
    {_OUTBOX_FAILURE_SIGNALS}
),
component_stats AS (
    SELECT component,
           count(*) FILTER (WHERE category = 'FAILED')::integer AS failed_count,
           count(*) FILTER (WHERE category = 'PARTIAL_SUCCESS')::integer
               AS partial_success_count,
           count(*) FILTER (WHERE category = 'RETRY')::integer AS retry_count,
           count(*) FILTER (WHERE category = 'STALLED')::integer AS stalled_count,
           min(occurred_at) AS oldest_signal_at,
           max(occurred_at) AS latest_signal_at
      FROM signals
     GROUP BY component
),
code_counts AS (
    SELECT component, failure_code AS code, count(*)::integer AS count,
           max(occurred_at) AS latest_at
      FROM signals
     WHERE category = 'FAILED' AND failure_code IS NOT NULL
     GROUP BY component, failure_code
),
ranked_codes AS (
    SELECT code_counts.*,
           row_number() OVER (
               PARTITION BY component ORDER BY count DESC, latest_at DESC, code
           ) AS rank
      FROM code_counts
),
top_codes AS (
    SELECT component,
           jsonb_agg(
               jsonb_build_object('code', code, 'count', count)
               ORDER BY count DESC, latest_at DESC, code
           ) AS values
      FROM ranked_codes
     WHERE rank <= 3
     GROUP BY component
),
healthy_events AS (
    SELECT 'analysis'::text AS component, completed_at AS occurred_at
      FROM analysis_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid) AND status = 'SUCCEEDED'
    UNION ALL
    SELECT 'policy_retrieval', completed_at FROM policy_retrieval_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid) AND status = 'SUCCEEDED'
    UNION ALL
    SELECT 'grounded_explanation', completed_at FROM grounded_explanation_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid) AND status = 'SUCCEEDED'
    UNION ALL
    SELECT 'policy_evaluation', completed_at FROM policy_evaluation_runs
     WHERE tenant_id = CAST(:tenant_id AS uuid) AND status = 'SUCCEEDED'
    UNION ALL
    SELECT 'human_review', resolved_at FROM human_review_tasks
     WHERE tenant_id = CAST(:tenant_id AS uuid) AND status = 'RESOLVED'
    UNION ALL
    SELECT 'case_resolution', updated_at FROM case_resolutions
     WHERE tenant_id = CAST(:tenant_id AS uuid)
       AND status IN ('ACTION_NOT_REQUIRED','MANUAL_FOLLOW_UP_REQUIRED',
                      'ACTION_NEEDS_INPUT','ACTION_DRY_RUN_VALIDATED')
    UNION ALL
    SELECT 'action_simulation', completed_at FROM external_action_simulation_attempts
     WHERE tenant_id = CAST(:tenant_id AS uuid) AND status = 'SUCCEEDED'
),
healthy AS (
    SELECT component, max(occurred_at) AS last_healthy_at
      FROM healthy_events
     GROUP BY component
)
SELECT jsonb_build_object(
           'component', catalog.component,
           'failed_count', COALESCE(stats.failed_count, 0),
           'partial_success_count', COALESCE(stats.partial_success_count, 0),
           'retry_count', COALESCE(stats.retry_count, 0),
           'stalled_count', COALESCE(stats.stalled_count, 0),
           'oldest_signal_at', stats.oldest_signal_at,
           'latest_signal_at', stats.latest_signal_at,
           'last_healthy_at', healthy.last_healthy_at,
           'top_failure_codes', COALESCE(codes.values, '[]'::jsonb)
       ) AS payload
  FROM component_catalog AS catalog
  LEFT JOIN component_stats AS stats ON stats.component = catalog.component
  LEFT JOIN top_codes AS codes ON codes.component = catalog.component
  LEFT JOIN healthy ON healthy.component = catalog.component
 ORDER BY catalog.ordinal
"""


class SQLAlchemyOperationsReadRepository:
    """Read one tenant's aggregate operations state without loading ORM entities."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._factory = session_factory

    def get_overview(
        self,
        *,
        tenant_id: str,
        now: datetime,
        stalled_before: datetime,
    ) -> OperationsOverview:
        _validate_tenant_id(tenant_id)
        with tenant_context(tenant_id), self._factory() as session:
            rows = (
                session.execute(
                    text(_OVERVIEW_SQL),
                    {
                        "tenant_id": tenant_id,
                        "now": now,
                        "stalled_before": stalled_before,
                    },
                )
                .mappings()
                .all()
            )

        queues: list[QueueOperationsSnapshot] = []
        processing: list[ProcessingOperationsSnapshot] = []
        versions: list[ActiveVersionSnapshot] = []
        for row in rows:
            payload = _payload(row)
            if row["section"] == "queue":
                queues.append(QueueOperationsSnapshot.model_validate(payload))
            elif row["section"] == "processing":
                processing.append(ProcessingOperationsSnapshot.model_validate(payload))
            else:
                versions.append(ActiveVersionSnapshot.model_validate(payload))

        return OperationsOverview(
            generated_at=now,
            stalled_after_seconds=max(1, int((now - stalled_before).total_seconds())),
            total_backlog_count=sum(item.backlog_count for item in queues),
            total_stalled_count=(
                sum(item.stalled_count for item in queues)
                + sum(item.stalled_count for item in processing)
            ),
            queues=tuple(queues),
            processing=tuple(processing),
            active_versions=tuple(versions),
        )

    def get_failures(
        self,
        *,
        tenant_id: str,
        now: datetime,
        since: datetime,
        stalled_before: datetime,
    ) -> OperationsFailures:
        _validate_tenant_id(tenant_id)
        with tenant_context(tenant_id), self._factory() as session:
            rows = (
                session.execute(
                    text(_FAILURES_SQL),
                    {
                        "tenant_id": tenant_id,
                        "now": now,
                        "since": since,
                        "stalled_before": stalled_before,
                    },
                )
                .mappings()
                .all()
            )
        components = tuple(ComponentFailureSummary.model_validate(_payload(row)) for row in rows)
        return OperationsFailures(
            generated_at=now,
            lookback_seconds=max(1, int((now - since).total_seconds())),
            total_failed_count=sum(item.failed_count for item in components),
            total_partial_success_count=sum(item.partial_success_count for item in components),
            total_retry_count=sum(item.retry_count for item in components),
            total_stalled_count=sum(item.stalled_count for item in components),
            components=components,
        )


def _validate_tenant_id(value: str) -> None:
    UUID(value)


def _payload(row: RowMapping) -> Mapping[str, Any]:
    value = row["payload"]
    if not isinstance(value, Mapping):
        raise TypeError("operations SQL payload must be a JSON object")
    return {str(key): item for key, item in value.items()}


__all__ = ["SQLAlchemyOperationsReadRepository"]
