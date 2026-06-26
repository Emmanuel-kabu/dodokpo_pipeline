-- Athena Views for Dodokpo Gold Layer
-- Database: dodokpo_dev_gold
--
-- IMPORTANT: Source tables read from the SILVER database because the gold
-- crawler only registered the latest partition (the gold lambda overwrites
-- instead of accumulating). Silver retains full history across all load_dates
-- but contains duplicates from repeated incremental extracts, so each table
-- is deduplicated in a CTE by its primary key, keeping the most recent row
-- per load_date.
--
-- Silver source tables (in dodokpo_dev_silver):
--   test_execution_testresult     -> attempts (no surrogate id; natural key
--                                    = assessmenttakerid + testid + attemptnumber)
--   test_creation_assessmenttaker -> candidates (id is PK)
--   test_creation_test            -> tests     (id is PK)
--   test_creation_assessment      -> assessments (id is PK)
--   test_creation_question        -> questions (id is PK)

-- ---------------------------------------------------------------------------
-- 1. Detailed candidate performance per attempt (time-aware)
--
-- NOTE: Gold dimension tables contain duplicate rows (each entity appears
-- ~5× because the silver/gold lambdas write full snapshots instead of upserts).
-- These dedup CTEs keep the latest version per primary key based on load_date,
-- so each testresult joins to exactly one assessmenttaker and one test.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW trainer_candidate_performance AS
WITH testresult_dedup AS (
    SELECT assessmenttakerid, testid, attemptnumber, starttime, finishtime,
           duration, testpercentage, passstatus, title,
           testwindowviolationcount, testwindowviolationduration,
           numberofquestionsfailed, numberofquestions, load_date
    FROM (
        SELECT assessmenttakerid, testid, attemptnumber, starttime, finishtime,
               duration, testpercentage, passstatus, title,
               testwindowviolationcount, testwindowviolationduration,
               numberofquestionsfailed, numberofquestions, load_date,
            ROW_NUMBER() OVER (
                PARTITION BY assessmenttakerid, testid, attemptnumber
                ORDER BY load_date DESC, finishtime DESC
            ) AS _rn
        FROM dodokpo_dev_silver.test_execution_testresult
        WHERE starttime IS NOT NULL
          AND starttime <> ''
          AND SUBSTR(starttime, 1, 4) BETWEEN '2020' AND '2099'
    )
    WHERE _rn = 1
),
assessmenttaker_dedup AS (
    -- Silver does not carry the derived `candidatename` column (it is added in
    -- the gold lambda). We replicate the same derivation here: title-case the
    -- email local-part with dots converted to spaces.
    SELECT
        id,
        email,
        REPLACE(SUBSTR(email, 1, STRPOS(email, '@') - 1), '.', ' ') AS candidatename,
        assessmentid,
        organizationid
    FROM (
        SELECT id, email, assessmentid, organizationid, load_date,
            ROW_NUMBER() OVER (PARTITION BY id ORDER BY load_date DESC) AS _rn
        FROM dodokpo_dev_silver.test_creation_assessmenttaker
    )
    WHERE _rn = 1
),
-- Organization name lookup (user-mgt schema). Silver carries duplicate rows
-- per primary key, so dedup by id keeping the most recent load_date.
organization_dedup AS (
    SELECT id, organizationname
    FROM (
        SELECT id, organizationname, load_date,
            ROW_NUMBER() OVER (PARTITION BY id ORDER BY load_date DESC) AS _rn
        FROM dodokpo_dev_silver.user_mgt_organizations
    )
    WHERE _rn = 1
),
test_dedup AS (
    SELECT id, title, difficultylevel
    FROM (
        SELECT id, title, difficultylevel, load_date,
            ROW_NUMBER() OVER (PARTITION BY id ORDER BY load_date DESC) AS _rn
        FROM dodokpo_dev_silver.test_creation_test
    )
    WHERE _rn = 1
),
attempt_metrics AS (
    SELECT
        tr.assessmenttakerid                                            AS assessment_taker_id,
        at.candidatename,
        at.email,
        SUBSTR(at.email, STRPOS(at.email, '@') + 1)                    AS email_domain,
        at.organizationid                                               AS organization_id,
        COALESCE(o.organizationname, at.organizationid, 'Unknown')      AS organization_name,
        at.assessmentid                                                 AS assessment_id,
        tr.testid                                                       AS test_id,
        tr.title                                                        AS test_title,
        tr.starttime                                                    AS start_time_raw,
        tr.finishtime                                                   AS finish_time_raw,
        TRY(CAST(REPLACE(SUBSTR(tr.starttime, 1, 19), 'T', ' ') AS TIMESTAMP)) AS start_time,
        -- Silver stores duration in SECONDS (gold lambda converts to minutes).
        -- Convert here since we now source from silver.
        TRY(CAST(tr.duration AS DOUBLE)) / 60.0                          AS duration_min,
        CAST(tr.testpercentage AS DOUBLE)                               AS score_pct,
        CASE WHEN UPPER(tr.passstatus) = 'PASS' THEN 'passed' ELSE 'failed' END AS pass_status,
        tr.attemptnumber                                                AS attempt_number,
        tr.testwindowviolationcount                                     AS violation_count,
        tr.testwindowviolationduration                                  AS violation_duration_sec,
        tr.numberofquestionsfailed                                      AS questions_failed,
        tr.numberofquestions                                            AS questions_total,
        tr.load_date,
        SUBSTR(tr.starttime, 1, 7)                                     AS attempt_month,
        SUBSTR(tr.starttime, 1, 4)                                     AS attempt_year,
        CASE
            WHEN SUBSTR(tr.starttime, 6, 2) IN ('01','02','03') THEN CONCAT(SUBSTR(tr.starttime,1,4),'-Q1')
            WHEN SUBSTR(tr.starttime, 6, 2) IN ('04','05','06') THEN CONCAT(SUBSTR(tr.starttime,1,4),'-Q2')
            WHEN SUBSTR(tr.starttime, 6, 2) IN ('07','08','09') THEN CONCAT(SUBSTR(tr.starttime,1,4),'-Q3')
            ELSE CONCAT(SUBSTR(tr.starttime,1,4),'-Q4')
        END                                                             AS attempt_quarter,
        t.difficultylevel                                               AS test_difficulty,
        CASE
            WHEN CAST(tr.testpercentage AS DOUBLE) >= 80 THEN 'Advanced'
            WHEN CAST(tr.testpercentage AS DOUBLE) >= 50 THEN 'Intermediate'
            ELSE 'Beginner'
        END                                                             AS proficiency_level,
        CASE WHEN tr.finishtime IS NOT NULL AND tr.finishtime <> '' THEN 1 ELSE 0 END AS is_complete
    FROM testresult_dedup tr
    LEFT JOIN assessmenttaker_dedup at
           ON tr.assessmenttakerid = at.id
    LEFT JOIN test_dedup t
           ON tr.testid = t.id
    LEFT JOIN organization_dedup o
           ON at.organizationid = o.id
),
attempt_counts AS (
    SELECT
        assessment_taker_id,
        test_id,
        COUNT(*) AS total_attempts_before_pass
    FROM attempt_metrics
    GROUP BY assessment_taker_id, test_id
)
SELECT
    a.*,
    p.total_attempts_before_pass,
    CASE WHEN a.pass_status = 'passed' THEN 1 ELSE 0 END               AS is_pass,
    CASE
        WHEN LOWER(a.email_domain) LIKE '%amalitech%' THEN 'Internal'
        ELSE 'External'
    END                                                                 AS candidate_source
FROM attempt_metrics a
LEFT JOIN attempt_counts p
       ON a.assessment_taker_id = p.assessment_taker_id
      AND a.test_id              = p.test_id;

-- ---------------------------------------------------------------------------
-- 2. Executive overview KPIs — single-row aggregate of all top-line metrics
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW executive_overview_kpis AS
WITH attempt_pairs AS (
    SELECT
        assessment_taker_id,
        test_id,
        start_time,
        attempt_number,
        LAG(start_time) OVER (
            PARTITION BY assessment_taker_id, test_id
            ORDER BY attempt_number
        ) AS prev_start_time
    FROM dodokpo_dev_gold.trainer_candidate_performance
    WHERE start_time IS NOT NULL
),
retake_intervals AS (
    SELECT
        date_diff('day', prev_start_time, start_time) AS days_between_attempts
    FROM attempt_pairs
    WHERE prev_start_time IS NOT NULL
),
attempts AS (
    SELECT
        COUNT(*)                                                       AS total_attempts,
        COUNT(DISTINCT test_id)                                        AS total_unique_tests_taken,
        AVG(duration_min)                                              AS avg_duration_min,
        SUM(violation_count)                                           AS total_violations,
        SUM(is_pass)                                                   AS total_pass,
        SUM(1 - is_pass)                                               AS total_fail,
        AVG(score_pct)                                                 AS avg_score_pct
    FROM dodokpo_dev_gold.trainer_candidate_performance
)
SELECT
    a.total_attempts,
    a.total_unique_tests_taken,
    a.avg_duration_min,
    a.total_violations,
    a.total_pass,
    a.total_fail,
    CAST(a.total_pass AS DOUBLE) / NULLIF(a.total_attempts, 0) * 100   AS pass_rate_pct,
    a.avg_score_pct,
    -- Catalog counts source from silver (full history) and use DISTINCT id
    -- because silver also contains duplicate rows per primary key.
    (SELECT COUNT(DISTINCT id) FROM dodokpo_dev_silver.test_creation_assessment)
                                                                        AS total_assessments_created,
    (SELECT COUNT(DISTINCT id) FROM dodokpo_dev_silver.test_creation_assessment
        WHERE isdispatched = TRUE)                                      AS total_assessments_dispatched,
    (SELECT COUNT(DISTINCT id) FROM dodokpo_dev_silver.test_creation_test)
                                                                        AS total_tests_created,
    (SELECT COUNT(DISTINCT id) FROM dodokpo_dev_silver.test_creation_question)
                                                                        AS total_questions_created,
    (SELECT AVG(days_between_attempts) FROM retake_intervals)          AS avg_retake_days,
    (SELECT APPROX_PERCENTILE(days_between_attempts, 0.5)
        FROM retake_intervals)                                         AS median_retake_days
FROM attempts a;

-- ---------------------------------------------------------------------------
-- 3. Monthly assessment trend — time-series for charts
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW monthly_assessment_trend AS
SELECT
    attempt_month,
    attempt_quarter,
    attempt_year,
    test_difficulty,
    organization_id,
    organization_name,
    COUNT(*)                                                            AS attempts,
    SUM(is_pass)                                                        AS passes,
    SUM(1 - is_pass)                                                    AS fails,
    CAST(SUM(is_pass) AS DOUBLE) / NULLIF(COUNT(*), 0) * 100           AS pass_rate_pct,
    AVG(score_pct)                                                      AS avg_score_pct,
    AVG(duration_min)                                                   AS avg_duration_min,
    SUM(violation_count)                                                AS total_violations,
    COUNT(DISTINCT assessment_taker_id)                                 AS unique_candidates
FROM dodokpo_dev_gold.trainer_candidate_performance
WHERE attempt_month IS NOT NULL AND attempt_month <> ''
GROUP BY attempt_month, attempt_quarter, attempt_year, test_difficulty,
         organization_id, organization_name;

-- ---------------------------------------------------------------------------
-- 4. Retake interval distribution
-- ---------------------------------------------------------------------------
-- A retake is the SAME person re-sitting the SAME test. In this source each
-- sitting is a separate assessmenttaker (one per dispatch) and `attemptnumber`
-- is always 1 — so the real retake sequence must be reconstructed by ordering a
-- person's sittings of a test by start_time, partitioned on (email, test_id).
-- (The previous version partitioned on assessment_taker_id + attempt_number,
-- which gave one row per partition → LAG always NULL → the view was empty, so the
-- Executive retake histogram silently showed nothing.)
CREATE OR REPLACE VIEW candidate_retake_intervals AS
WITH attempt_pairs AS (
    SELECT
        assessment_taker_id,
        candidatename,
        email,
        test_id,
        test_title,
        start_time,
        score_pct,
        is_pass,
        pass_status,
        attempt_year,
        attempt_quarter,
        attempt_month,
        ROW_NUMBER() OVER (PARTITION BY email, test_id ORDER BY start_time)    AS sitting_no,
        LAG(start_time) OVER (PARTITION BY email, test_id ORDER BY start_time) AS prev_start_time,
        LAG(score_pct)  OVER (PARTITION BY email, test_id ORDER BY start_time) AS prev_score_pct
    FROM dodokpo_dev_gold.trainer_candidate_performance
    WHERE start_time IS NOT NULL
)
SELECT
    assessment_taker_id,
    candidatename,
    email,
    test_id,
    test_title,
    sitting_no,
    start_time,
    prev_start_time,
    score_pct,
    prev_score_pct,
    score_pct - prev_score_pct                                          AS score_delta,
    is_pass,
    pass_status,
    attempt_year,
    attempt_quarter,
    attempt_month,
    date_diff('second', prev_start_time, start_time) / 86400.0          AS days_between_attempts,
    date_diff('hour', prev_start_time, start_time)                      AS hours_between_attempts
FROM attempt_pairs
WHERE prev_start_time IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 5. Violation analysis per test (reads from already-deduped parent view)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW trainer_quality_violations AS
SELECT
    test_id,
    test_title,
    organization_id,
    organization_name,
    questions_failed                                                    AS number_of_questions_failed,
    violation_count                                                     AS test_window_violation_count,
    violation_duration_sec                                              AS test_window_violation_duration,
    load_date,
    test_difficulty,
    CASE
        WHEN violation_count = 0            THEN 'No Violations'
        WHEN violation_count BETWEEN 1 AND 5 THEN 'Low Violations'
        ELSE 'High Violations'
    END                                                                 AS violation_severity_slice
FROM dodokpo_dev_gold.trainer_candidate_performance;

-- ---------------------------------------------------------------------------
-- 5b. Organization overview — one row per organization that appears in the
-- assessment data (naturally the ~17 orgs present in AssessmentTaker).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW organization_overview_kpis AS
SELECT
    organization_id,
    organization_name,
    COUNT(*)                                                            AS attempts,
    COUNT(DISTINCT assessment_taker_id)                                 AS unique_candidates,
    COUNT(DISTINCT test_id)                                             AS unique_tests,
    SUM(is_pass)                                                        AS passes,
    SUM(1 - is_pass)                                                    AS fails,
    CAST(SUM(is_pass) AS DOUBLE) / NULLIF(COUNT(*), 0) * 100           AS pass_rate_pct,
    AVG(score_pct)                                                      AS avg_score_pct,
    AVG(duration_min)                                                   AS avg_duration_min,
    SUM(violation_count)                                                AS total_violations
FROM dodokpo_dev_gold.trainer_candidate_performance
GROUP BY organization_id, organization_name;

-- ---------------------------------------------------------------------------
-- 5c. Organization catalog counts — assessments / tests / questions created
-- per organization. Lets the dashboard's catalog KPI row respond to the org
-- slicer (these counts come from the creation tables, not from attempts).
-- COUNT(DISTINCT id) already collapses the ~5x silver duplication per id.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW organization_catalog_kpis AS
WITH org_universe AS (
    SELECT organizationid AS oid FROM dodokpo_dev_silver.test_creation_assessment
    UNION SELECT organizationid FROM dodokpo_dev_silver.test_creation_test
    UNION SELECT organizationid FROM dodokpo_dev_silver.test_creation_question
),
a AS (
    SELECT organizationid AS oid,
           COUNT(DISTINCT id) AS assessments_created,
           COUNT(DISTINCT CASE WHEN isdispatched = TRUE THEN id END) AS assessments_dispatched
    FROM dodokpo_dev_silver.test_creation_assessment
    GROUP BY organizationid
),
t AS (
    SELECT organizationid AS oid, COUNT(DISTINCT id) AS tests_created
    FROM dodokpo_dev_silver.test_creation_test
    GROUP BY organizationid
),
q AS (
    SELECT organizationid AS oid, COUNT(DISTINCT id) AS questions_created
    FROM dodokpo_dev_silver.test_creation_question
    GROUP BY organizationid
),
org AS (
    SELECT id, organizationname
    FROM (
        SELECT id, organizationname,
            ROW_NUMBER() OVER (PARTITION BY id ORDER BY load_date DESC) AS _rn
        FROM dodokpo_dev_silver.user_mgt_organizations
    )
    WHERE _rn = 1
)
SELECT
    u.oid                                                  AS organization_id,
    COALESCE(org.organizationname, u.oid, 'Unknown')       AS organization_name,
    COALESCE(a.assessments_created, 0)                     AS assessments_created,
    COALESCE(a.assessments_dispatched, 0)                  AS assessments_dispatched,
    COALESCE(t.tests_created, 0)                           AS tests_created,
    COALESCE(q.questions_created, 0)                       AS questions_created
FROM org_universe u
LEFT JOIN a   ON u.oid = a.oid
LEFT JOIN t   ON u.oid = t.oid
LEFT JOIN q   ON u.oid = q.oid
LEFT JOIN org ON u.oid = org.id
WHERE u.oid IS NOT NULL AND u.oid <> '';

-- ---------------------------------------------------------------------------
-- 6. Trainer question productivity
-- Deduplicates question rows first (gold layer has ~5x duplication)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW executive_trainer_kpis AS
WITH question_dedup AS (
    SELECT id, creator, activeversionid, calibrationscore, status, difficultylevel
    FROM (
        SELECT id, creator, activeversionid, calibrationscore, status, difficultylevel, load_date,
            ROW_NUMBER() OVER (PARTITION BY id ORDER BY load_date DESC) AS _rn
        FROM dodokpo_dev_silver.test_creation_question
    )
    WHERE _rn = 1
)
SELECT
    q.creator                                                           AS trainer_id,
    COUNT(DISTINCT q.id)                                                AS total_questions_created,
    COUNT(DISTINCT q.activeversionid)                                   AS active_questions,
    AVG(CAST(q.calibrationscore AS DOUBLE))                             AS avg_calibration_score,
    SUM(CASE WHEN q.status = 'active' THEN 1 ELSE 0 END)               AS live_questions,
    COUNT(DISTINCT CASE WHEN q.difficultylevel = 'hard'   THEN q.id END) AS hard_questions_created,
    COUNT(DISTINCT CASE WHEN q.difficultylevel = 'medium' THEN q.id END) AS medium_questions_created,
    COUNT(DISTINCT CASE WHEN q.difficultylevel = 'easy'   THEN q.id END) AS easy_questions_created
FROM question_dedup q
WHERE q.creator IS NOT NULL
GROUP BY q.creator;

-- ---------------------------------------------------------------------------
-- 7. Pipeline data freshness
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW gold_data_freshness AS
SELECT 'assessmenttaker' AS table_name, MAX(load_date) AS last_updated
  FROM dodokpo_dev_silver.test_creation_assessmenttaker
UNION ALL
SELECT 'testresult',                    MAX(load_date)
  FROM dodokpo_dev_silver.test_execution_testresult
UNION ALL
SELECT 'question',                      MAX(load_date)
  FROM dodokpo_dev_silver.test_creation_question
UNION ALL
SELECT 'assessment',                    MAX(load_date)
  FROM dodokpo_dev_silver.test_creation_assessment
UNION ALL
SELECT 'test',                          MAX(load_date)
  FROM dodokpo_dev_silver.test_creation_test
UNION ALL
SELECT 'organization',                  MAX(load_date)
  FROM dodokpo_dev_silver.user_mgt_organizations;
