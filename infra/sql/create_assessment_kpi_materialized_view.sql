-- Athena materialized view for the gold assessment KPI layer.
-- Replace the placeholders with the deployed Athena database names if you run
-- this outside the provisioning workflow.

CREATE MATERIALIZED VIEW IF NOT EXISTS __ATHENA_DATABASE__.mv_assessment_kpis AS
SELECT
    assessment_id,
    assessment_title,
    organization_id,
    status,
    duration_minutes,
    total_takers,
    started_takers,
    completed_takers,
    completion_rate_pct,
    graded_attempts,
    average_score,
    average_percentage,
    pass_rate_pct,
    average_duration_minutes,
    max_duration_minutes,
    violation_count,
    question_flag_count
FROM __GOLD_DATABASE__.assessment_summary;