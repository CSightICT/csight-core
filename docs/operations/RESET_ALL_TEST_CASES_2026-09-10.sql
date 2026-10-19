-- One-time owner-authorized data maintenance, not an application schema migration.
-- Requires quiesced Core writers, verified post-0038 backup, archived original MinIO,
-- and the exact 115-Case inventory. Never run during normal application startup.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
DO $$ BEGIN
    IF current_database() NOT IN ('csight', 'csight_reset_restore_20260910_b71960ac') THEN
        RAISE EXCEPTION 'Unexpected reset database';
    END IF;
    IF (SELECT version_num FROM alembic_version) <> '20260910_0038_fixture_evidence_repair'
       OR (SELECT count(*) FROM cases) <> 115
       OR (SELECT count(*) FROM case_evidence) <> 73
       OR (SELECT count(*) FROM analysis_runs) <> 122
       OR (SELECT count(*) FROM human_review_decisions) <> 32 THEN
        RAISE EXCEPTION 'Reset inventory changed; stop and inspect';
    END IF;
    IF EXISTS (SELECT 1 FROM analysis_runs WHERE status IN ('QUEUED','RUNNING','RETRY_WAITING'))
       OR EXISTS (SELECT 1 FROM policy_evaluation_runs WHERE status IN ('QUEUED','RUNNING'))
       OR EXISTS (SELECT 1 FROM policy_retrieval_runs WHERE status NOT IN ('SUCCEEDED','FAILED'))
       OR EXISTS (SELECT 1 FROM grounded_explanation_runs WHERE status NOT IN ('SUCCEEDED','FAILED')) THEN
        RAISE EXCEPTION 'Active work prevents reset';
    END IF;
END $$;
-- Exact audited FK closure plus polymorphic operational-failure/idempotency roots.
-- RESTRICT makes an unknown dependency abort, never broadens deletion through CASCADE.
TRUNCATE TABLE
    analysis_request_idempotency_records,
    analysis_run_evidence,
    analysis_runs,
    analysis_stage_attempts,
    analysis_stage_runs,
    case_assignment_actions,
    case_assignments,
    case_evidence,
    case_learning_assets,
    case_resolution_events,
    case_resolution_request_events,
    case_resolutions,
    case_sensitive_payloads,
    case_status_history,
    cases,
    customer_communication_simulations,
    data_lifecycle_events,
    external_action_intents,
    external_action_simulation_attempts,
    external_action_simulation_request_events,
    external_action_simulation_results,
    grounded_explanation_outbox_events,
    grounded_explanation_results,
    grounded_explanation_runs,
    human_review_actions,
    human_review_assignments,
    human_review_decision_basis,
    human_review_decisions,
    human_review_packets,
    human_review_request_events,
    human_review_tasks,
    idempotency_records,
    llm_extraction_results,
    llm_extraction_results_v2,
    operational_failure_recovery_events,
    operational_failure_recovery_runs,
    operational_failure_resolutions,
    operational_failures,
    outbox_events,
    policy_citation_pack_items,
    policy_citation_packs,
    policy_condition_evaluation_results,
    policy_evaluation_effects,
    policy_evaluation_input_snapshots,
    policy_evaluation_outbox_events,
    policy_evaluation_runs,
    policy_retrieval_outbox_events,
    policy_retrieval_run_hits,
    policy_retrieval_run_queries,
    policy_retrieval_runs,
    policy_retrieval_similarity_evidence,
    policy_rule_evaluation_results,
    review_reports,
    vision_analysis_results,
    vision_detections,
    vision_image_assessments
RESTRICT;
COMMIT;
