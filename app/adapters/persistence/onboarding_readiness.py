"""Single-statement PostgreSQL onboarding readiness projection."""

import json
from datetime import date
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.tenant_context import tenant_context
from app.platform.errors import InconsistentPersistenceStateError
from app.platform.onboarding_readiness import OnboardingReadinessFacts

_READINESS_SQL = """
WITH target_tenant AS (
    SELECT slug, is_active
      FROM tenants
     WHERE id = CAST(:tenant_id AS uuid)
),
active_roles AS (
    SELECT count(DISTINCT users.id) FILTER (WHERE roles.name = 'ADMIN')::integer
               AS active_admin_count,
           count(DISTINCT users.id) FILTER (WHERE roles.name = 'REVIEWER')::integer
               AS active_reviewer_count
      FROM users
      LEFT JOIN user_roles
        ON user_roles.tenant_id = users.tenant_id
       AND user_roles.user_id = users.id
      LEFT JOIN roles ON roles.id = user_roles.role_id
     WHERE users.tenant_id = CAST(:tenant_id AS uuid)
       AND users.is_active = true
),
configured_actor_ids AS (
    SELECT value::uuid AS actor_id
      FROM jsonb_array_elements_text(CAST(:configured_actor_ids_json AS jsonb))
),
configured_actors AS (
    SELECT count(DISTINCT users.id)::integer AS configured_no_role_actor_count
      FROM users
      JOIN configured_actor_ids ON configured_actor_ids.actor_id = users.id
     WHERE users.tenant_id = CAST(:tenant_id AS uuid)
       AND users.is_active = true
       AND NOT EXISTS (
           SELECT 1
             FROM user_roles
            WHERE user_roles.tenant_id = users.tenant_id
              AND user_roles.user_id = users.id
       )
),
active_policy AS (
    SELECT (
        SELECT count(*)::integer
          FROM policy_index_versions
         WHERE tenant_id = CAST(:tenant_id AS uuid)
           AND status = 'ACTIVE'
           AND expected_clause_count > 0
           AND indexed_clause_count = expected_clause_count
    ) AS active_policy_index_count,
    (
        SELECT count(DISTINCT activations.id)::integer
          FROM policy_rule_set_activations AS activations
          JOIN policy_rule_sets AS rule_sets
            ON rule_sets.tenant_id = activations.tenant_id
           AND rule_sets.id = activations.rule_set_id
         WHERE activations.tenant_id = CAST(:tenant_id AS uuid)
           AND activations.retired_at IS NULL
           AND rule_sets.effective_from <= CAST(:as_of_date AS date)
           AND (rule_sets.effective_to IS NULL
                OR rule_sets.effective_to >= CAST(:as_of_date AS date))
    ) AS active_rule_set_count
),
current_activations AS (
    SELECT activation.id, activation.task, activation.execution_mode
      FROM llm_model_activation_events AS activation
     WHERE activation.tenant_id = CAST(:tenant_id AS uuid)
       AND activation.execution_mode = 'PRIMARY'
       AND NOT EXISTS (
           SELECT 1
             FROM llm_model_activation_events AS child
            WHERE child.tenant_id = activation.tenant_id
              AND child.task = activation.task
              AND child.execution_mode = activation.execution_mode
              AND child.previous_activation_id = activation.id
       )
),
current_routes AS (
    SELECT route.task, route.execution_mode, route.model_activation_id
      FROM llm_model_route_plans AS route
     WHERE route.tenant_id = CAST(:tenant_id AS uuid)
       AND route.execution_mode = 'PRIMARY'
       AND NOT EXISTS (
           SELECT 1
             FROM llm_model_route_plans AS child
            WHERE child.tenant_id = route.tenant_id
              AND child.task = route.task
              AND child.execution_mode = route.execution_mode
              AND child.previous_route_plan_id = route.id
       )
),
primary_routes AS (
    SELECT count(DISTINCT route.task)::integer AS active_primary_model_route_count
      FROM current_routes AS route
      JOIN current_activations AS activation
        ON activation.task = route.task
       AND activation.execution_mode = route.execution_mode
       AND activation.id = route.model_activation_id
     WHERE route.task IN (
         'PRODUCT_DEFECT_TEXT_EXTRACTION_V2',
         'POLICY_QUERY_BUILDER_V1',
         'GROUNDED_POLICY_EXPLANATION_V1'
     )
)
SELECT tenant.slug AS tenant_slug,
       tenant.is_active AS tenant_is_active,
       active_roles.active_admin_count,
       active_roles.active_reviewer_count,
       configured_actors.configured_no_role_actor_count,
       active_policy.active_policy_index_count,
       active_policy.active_rule_set_count,
       primary_routes.active_primary_model_route_count
  FROM target_tenant AS tenant
 CROSS JOIN active_roles
 CROSS JOIN configured_actors
 CROSS JOIN active_policy
 CROSS JOIN primary_routes
"""


class SQLAlchemyOnboardingReadinessRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._factory = session_factory

    def get_facts(
        self,
        *,
        tenant_id: str,
        configured_signed_actor_ids: tuple[str, ...],
        as_of_date: date,
    ) -> OnboardingReadinessFacts:
        normalized_tenant_id = str(UUID(tenant_id))
        normalized_actor_ids = tuple(
            dict.fromkeys(str(UUID(actor_id)) for actor_id in configured_signed_actor_ids)
        )
        with tenant_context(normalized_tenant_id), self._factory() as session:
            row = (
                session.execute(
                    text(_READINESS_SQL),
                    {
                        "tenant_id": normalized_tenant_id,
                        "configured_actor_ids_json": json.dumps(normalized_actor_ids),
                        "as_of_date": as_of_date,
                    },
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise InconsistentPersistenceStateError(
                "The onboarding-readiness tenant does not exist."
            )
        return OnboardingReadinessFacts.model_validate(dict(row))


__all__ = ["SQLAlchemyOnboardingReadinessRepository"]
