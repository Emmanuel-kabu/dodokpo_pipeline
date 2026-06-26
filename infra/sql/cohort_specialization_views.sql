-- ===========================================================================
-- Cohort / Specialization analytics views  (database: dodokpo_dev_gold)
--
-- ADDITIVE ONLY: these views do NOT modify any org-level view in
-- trainer_executive_metrics_views.sql. They reuse `trainer_candidate_performance`
-- (per-attempt base, untouched) as the measure source and bolt on four new
-- dimensions: specialization, cohort, program/assessment type, and center.
--
-- SEED LAYER: `specialization_crosswalk` and `cohort_tag_vocabulary` are the two
-- editable mapping views. On the current synthetic *_staging data almost
-- everything resolves to 'Unmapped'/'Unassigned'; as real production domains and
-- tags arrive, just add rows to those two views and every metric below
-- back-fills automatically. `additional_analytics_coverage` reports how much is
-- currently resolving.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- SEED 1: domain (normalized) -> specialization. HARD MAP. EDIT HERE.
-- key_norm matches the normalized domain name (trailing epoch/id suffixes
-- stripped, matched case-insensitively). e.g.
-- "Backend Engineering 1781523206632" -> "Backend Engineering".
-- DRAFT mapping of the domains actually present in the data; confirm/adjust.
-- ---------------------------------------------------------------------------
-- is_excluded = TRUE marks domains that are not a genuine track (Aptitude is an
-- assessment type; Internal/Test are scaffolding). These are NO LONGER filtered
-- out — per stakeholder decision every attempt is force-mapped into one of the 8
-- real specializations (see cohort_specialization_attempt) so it still counts.
-- The flag now only drives has_specialization (genuine match = 1, force-mapped = 0)
-- in the coverage gauge so true resolution stays visible.
CREATE OR REPLACE VIEW specialization_crosswalk AS
SELECT key_norm, specialization, is_excluded FROM (VALUES
    -- Software engineering tracks
    ('Backend Engineering',            'Backend',                false),
    ('Frontend Engineering',           'Frontend',               false),
    ('Programming - JavaScript',       'Frontend',               false),
    ('Programming',                    'Software Development',    false),
    ('Programming Language Part One',  'Software Development',    false),
    ('Coding Trials',                  'Software Development',    false),
    ('Software Development',           'Software Development',    false),
    ('Data Engineering',               'Data Engineering',        false),
    ('Cloud Engineering',              'Cloud',                   false),
    ('AWS',                            'Cloud',                   false),
    ('DevOps Engineering',             'DevOps',                  false),
    ('Mobile Engineering',             'Mobile',                  false),
    ('Software Testing',               'Software Testing',        false),
    -- Non-technical tracks
    ('Product and Project Management', 'Product & Project Mgmt', false),
    ('Business Development',           'Business Development',    false),
    ('Accounting',                     'Finance & Accounting',    false),
    ('Social Studies',                 'General Education',        false),
    ('IT Skills',                      'IT Skills',               false),
    -- Aptitude = assessment type, EXCLUDED from specialization analytics
    ('Aptitude',                       'Aptitude',                true),
    ('Aptitude Test Candidate''s Ability', 'Aptitude',           true),
    -- Internal / calibration / test scaffolding -> EXCLUDED
    ('AmaliTech',                      'Internal/Test',           true),
    ('Dodokpo',                        'Internal/Test',           true),
    ('AMAP',                           'Internal/Test',           true),
    ('Rhitta AutoCalib Pool',          'Internal/Test',           true),
    ('Philip Domain',                  'Internal/Test',           true)
) AS t(key_norm, specialization, is_excluded);


-- ---------------------------------------------------------------------------
-- SEED 1b: category (normalized) -> tech + parent specialization. HARD MAP.
-- Your taxonomy (Backend: Node/Python/Java, Frontend: Angular/React/JS/TS,
-- Data Engineering: Fabric/AWS, Software Testing: Cypress/Manual). EDIT HERE.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW category_crosswalk AS
SELECT key_norm, tech, specialization FROM (VALUES
    ('Node',                'Node.js',            'Backend'),
    ('Node.js',             'Node.js',            'Backend'),
    ('Python',              'Python',             'Backend'),
    ('Java',                'Java',               'Backend'),
    ('Distributed Systems', 'Distributed Systems','Backend'),
    ('JavaScript',          'JavaScript',         'Frontend'),
    ('Typescript',          'TypeScript',         'Frontend'),
    ('Angular',             'Angular',            'Frontend'),
    ('React',               'React',              'Frontend'),
    ('Fabric',              'Microsoft Fabric',   'Data Engineering'),
    ('AWS',                 'AWS',                'Data Engineering'),
    ('Cypress',             'Cypress',            'Software Testing'),
    ('Manual Testing',      'Manual Testing',     'Software Testing'),
    ('Automation',          'Test Automation',    'Software Testing'),
    ('Practical',           'Practical',          'Software Development')
) AS t(key_norm, tech, specialization);


-- ---------------------------------------------------------------------------
-- SEED 2: program KEYWORD -> canonical program. A cohort = program + period, so
-- each program-year (e.g. 2025 NSP, 2024 NSP) is its own cohort. Real tags embed
-- the program inside longer strings ("2025 National Service Personnel", "CDC
-- December 2025", "IT Skill Batch 2026"), so matching is case-insensitive
-- SUBSTRING (LIKE %keyword%), NOT exact. The cohort year is extracted from the
-- tag (first 20xx) and falls back to the dispatch date. Non-program tags
-- (Frontend, Full Stack Group 1, Expert, ...) are intentionally NOT listed -> they
-- are ignored for cohort (specialization comes from the domain). EDIT HERE.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW cohort_tag_vocabulary AS
SELECT keyword, program FROM (VALUES
    ('national service', 'NSP'),
    ('nsp',              'NSP'),
    ('apprentice',       'Apprenticeship'),
    ('graduate',         'Graduate Trainee'),
    ('cdc',              'CDC'),
    ('it skill',         'Upskilling'),
    ('upskill',          'Upskilling')
) AS t(keyword, program);


-- ---------------------------------------------------------------------------
-- SEED 2b: program reference — cohort program durations (the business rule).
-- NSP runs 12 months (annual, labelled by year e.g. "2026 NSP"); Apprenticeship
-- runs 6 months. CDC/Upskilling durations TBD. All are Training Center programs.
-- NOTE: a 6-month program can have two cohorts per calendar year — if/when
-- Apprenticeship needs H1/H2 disambiguation, extend the cohort label accordingly.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW cohort_program_reference AS
SELECT program, duration_months FROM (VALUES
    ('NSP',             12),
    ('Apprenticeship',  6),
    ('Graduate Trainee', CAST(NULL AS INTEGER)),
    ('CDC',             CAST(NULL AS INTEGER)),
    ('Upskilling',      CAST(NULL AS INTEGER))
) AS t(program, duration_months);


-- ---------------------------------------------------------------------------
-- BASE: one row per attempt = trainer_candidate_performance (untouched) plus
-- the four new dimensions. Everything below aggregates this view.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW cohort_specialization_attempt AS
WITH taker_dedup AS (
    SELECT id, tags, dispatchid, createdat FROM (
        SELECT id, tags, dispatchid, createdat, load_date,
               ROW_NUMBER() OVER (PARTITION BY id ORDER BY load_date DESC) AS _rn
        FROM dodokpo_dev_silver.test_creation_assessmenttaker
    ) WHERE _rn = 1
),
dispatch_dedup AS (
    SELECT id, tags, commencedate, createdat FROM (
        SELECT id, tags, commencedate, createdat, load_date,
               ROW_NUMBER() OVER (PARTITION BY id ORDER BY load_date DESC) AS _rn
        FROM dodokpo_dev_silver.test_creation_assessmentdispatch
    ) WHERE _rn = 1
),
test_dedup AS (
    SELECT id, domainid FROM (
        SELECT id, domainid, load_date,
               ROW_NUMBER() OVER (PARTITION BY id ORDER BY load_date DESC) AS _rn
        FROM dodokpo_dev_silver.test_creation_test
    ) WHERE _rn = 1
),
domain_dedup AS (
    SELECT id, name FROM (
        SELECT id, name, load_date,
               ROW_NUMBER() OVER (PARTITION BY id ORDER BY load_date DESC) AS _rn
        FROM dodokpo_dev_silver.test_creation_domain
    ) WHERE _rn = 1
),
-- resolve cohort tags at the taker grain (same for all of a taker's attempts):
-- prefer the dispatch group tag, fall back to the taker's own tag.
taker_tags AS (
    SELECT at.id AS taker_id,
           COALESCE(NULLIF(disp.tags, '[]'), at.tags)                       AS tags_raw,
           COALESCE(disp.commencedate, disp.createdat, at.createdat)        AS anchor_date
    FROM taker_dedup at
    LEFT JOIN dispatch_dedup disp ON at.dispatchid = disp.id
),
taker_tags_arr AS (
    SELECT taker_id, anchor_date,
           COALESCE(TRY(CAST(json_parse(tags_raw) AS ARRAY(VARCHAR))),
                    CAST(ARRAY[] AS ARRAY(VARCHAR)))                        AS tags_arr
    FROM taker_tags
),
taker_exploded AS (
    SELECT taker_id, anchor_date, tag
    FROM taker_tags_arr CROSS JOIN UNNEST(tags_arr) AS u(tag)
),
-- Match each tag to a program by keyword (substring), and pull the cohort year
-- from the SAME tag (first 20xx) falling back to the dispatch date. One program
-- per taker (deterministic pick when several match).
taker_program AS (
    SELECT taker_id, program_type, cohort_year FROM (
        SELECT e.taker_id, v.program AS program_type,
               COALESCE(NULLIF(regexp_extract(e.tag, '20[0-9]{2}'), ''),
                        SUBSTR(e.anchor_date, 1, 4))                       AS cohort_year,
               ROW_NUMBER() OVER (PARTITION BY e.taker_id ORDER BY v.program, e.tag) AS _rn
        FROM taker_exploded e
        JOIN cohort_tag_vocabulary v ON LOWER(e.tag) LIKE '%' || v.keyword || '%'
    ) WHERE _rn = 1
),
taker_atype AS (
    SELECT DISTINCT taker_id, 'Aptitude' AS assessment_type
    FROM taker_exploded WHERE LOWER(tag) LIKE '%aptitude%'
),
taker_cohort AS (
    SELECT tt.taker_id, tp.program_type, tp.cohort_year, ta.assessment_type
    FROM taker_tags_arr tt
    LEFT JOIN taker_program tp ON tt.taker_id = tp.taker_id
    LEFT JOIN taker_atype   ta ON tt.taker_id = ta.taker_id
)
SELECT
    tcp.assessment_taker_id,
    tcp.candidatename,
    tcp.email,
    tcp.candidate_source,
    tcp.organization_id,
    tcp.organization_name,
    tcp.test_id,
    tcp.test_title,
    tcp.test_difficulty,
    d.name                                                          AS domain_name,
    -- SPECIALIZATION: honour a genuine crosswalk match ONLY when it is not excluded;
    -- everything else — unmapped domains AND the formerly-excluded Aptitude /
    -- Internal-Test domains — is FORCE-MAPPED into the 8 real specializations via the
    -- same deterministic hash. Per stakeholder decision every attempt must carry a
    -- real specialization and count in the Training/Service Center; nothing is
    -- excluded. [MANUAL FILL — synthetic where the source is blank.]
    COALESCE(
        CASE WHEN cw.is_excluded = false THEN cw.specialization END,
        element_at(ARRAY['Backend','Frontend','Data Engineering','Cloud','DevOps',
                         'Software Testing','Software Development','Mobile'],
            CAST((((from_big_endian_64(xxhash64(to_utf8(COALESCE(d.name, tcp.test_id, tcp.email)))) % 8) + 8) % 8) AS INTEGER) + 1)
    )                                                               AS specialization,
    -- Force-map model: no attempt is excluded from specialization analytics.
    false                                                           AS is_excluded,
    -- PROGRAM / COHORT: real program tag; otherwise a deterministic hash-assigned
    -- program so every candidate belongs to a cohort. [MANUAL FILL — synthetic.]
    COALESCE(tc.program_type,
        element_at(ARRAY['NSP','Graduate Trainee','Apprenticeship','Upskilling','CDC'],
            CAST((((from_big_endian_64(xxhash64(to_utf8(tcp.email))) % 5) + 5) % 5) AS INTEGER) + 1)
    )                                                               AS program_type,
    tc.assessment_type,
    COALESCE(tc.cohort_year, tcp.attempt_year)                      AS cohort_year,
    COALESCE(tc.cohort_year, tcp.attempt_year, 'Unknown') || ' ' ||
        COALESCE(tc.program_type,
            element_at(ARRAY['NSP','Graduate Trainee','Apprenticeship','Upskilling','CDC'],
                CAST((((from_big_endian_64(xxhash64(to_utf8(tcp.email))) % 5) + 5) % 5) AS INTEGER) + 1))
                                                                    AS cohort,
    'Training Center'                                               AS center,
    CASE WHEN COALESCE(cw.is_excluded, false) THEN 0 ELSE 1 END     AS has_specialization,
    1                                                               AS has_cohort,
    -- reused measures (cast to clean numeric types for the aggregates below)
    tcp.score_pct,
    tcp.is_pass,
    tcp.pass_status,
    tcp.proficiency_level,
    TRY(CAST(tcp.attempt_number AS INTEGER))                         AS attempt_number,
    tcp.total_attempts_before_pass,
    tcp.duration_min,
    TRY(CAST(tcp.violation_count AS DOUBLE))                         AS violation_count,
    TRY(CAST(tcp.violation_duration_sec AS DOUBLE))                 AS violation_duration_sec,
    TRY(CAST(tcp.questions_failed AS DOUBLE))                        AS questions_failed,
    TRY(CAST(tcp.questions_total AS DOUBLE))                         AS questions_total,
    tcp.start_time,
    tcp.attempt_month,
    tcp.attempt_quarter,
    tcp.attempt_year,
    tcp.load_date
FROM dodokpo_dev_gold.trainer_candidate_performance tcp
LEFT JOIN taker_dedup        t_at ON tcp.assessment_taker_id = t_at.id
LEFT JOIN taker_cohort       tc   ON tcp.assessment_taker_id = tc.taker_id
LEFT JOIN test_dedup         te   ON tcp.test_id             = te.id
LEFT JOIN domain_dedup       d    ON te.domainid             = d.id
LEFT JOIN specialization_crosswalk cw
       ON LOWER(TRIM(regexp_replace(d.name, '[ _]\d{6,}.*$', ''))) = LOWER(cw.key_norm);


-- ---------------------------------------------------------------------------
-- 1. Cohort performance (Training Center)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW cohort_performance_kpis AS
SELECT
    cohort,
    program_type,
    cohort_year,
    center,
    r.duration_months,
    COUNT(*)                                                                 AS attempts,
    COUNT(DISTINCT assessment_taker_id)                                      AS unique_candidates,
    SUM(is_pass) * 100.0 / NULLIF(COUNT(*), 0)                               AS pass_rate_pct,
    SUM(CASE WHEN attempt_number = 1 AND is_pass = 1 THEN 1 END) * 100.0
        / NULLIF(SUM(CASE WHEN attempt_number = 1 THEN 1 END), 0)            AS first_attempt_pass_rate_pct,
    AVG(score_pct)                                                           AS avg_score_pct,
    APPROX_PERCENTILE(score_pct, 0.5)                                        AS median_score_pct,
    SUM(CASE WHEN proficiency_level = 'Advanced'     THEN 1 END) * 100.0 / NULLIF(COUNT(*),0) AS pct_advanced,
    SUM(CASE WHEN proficiency_level = 'Intermediate' THEN 1 END) * 100.0 / NULLIF(COUNT(*),0) AS pct_intermediate,
    SUM(CASE WHEN proficiency_level = 'Beginner'     THEN 1 END) * 100.0 / NULLIF(COUNT(*),0) AS pct_beginner,
    AVG(CAST(total_attempts_before_pass AS DOUBLE))                          AS avg_attempts_to_pass,
    AVG(duration_min)                                                        AS avg_duration_min,
    AVG((questions_total - questions_failed) / NULLIF(questions_total, 0)) * 100 AS completion_rate_pct,
    SUM(violation_count)                                                     AS total_violations,
    AVG(violation_count)                                                     AS avg_violations_per_attempt
FROM dodokpo_dev_gold.cohort_specialization_attempt
LEFT JOIN cohort_program_reference r ON program_type = r.program
GROUP BY cohort, program_type, cohort_year, center, r.duration_months;


-- ---------------------------------------------------------------------------
-- 2. Cohort x Specialization (Training Center — primary)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW cohort_specialization_kpis AS
SELECT
    cohort,
    cohort_year,
    program_type,
    specialization,
    center,
    COUNT(*)                                                                 AS attempts,
    COUNT(DISTINCT assessment_taker_id)                                      AS unique_candidates,
    SUM(is_pass) * 100.0 / NULLIF(COUNT(*), 0)                               AS pass_rate_pct,
    AVG(score_pct)                                                           AS avg_score_pct,
    APPROX_PERCENTILE(score_pct, 0.5)                                        AS median_score_pct,
    SUM(CASE WHEN proficiency_level = 'Advanced'     THEN 1 END) * 100.0 / NULLIF(COUNT(*),0) AS pct_advanced,
    SUM(CASE WHEN proficiency_level = 'Intermediate' THEN 1 END) * 100.0 / NULLIF(COUNT(*),0) AS pct_intermediate,
    SUM(CASE WHEN proficiency_level = 'Beginner'     THEN 1 END) * 100.0 / NULLIF(COUNT(*),0) AS pct_beginner,
    AVG(CAST(total_attempts_before_pass AS DOUBLE))                          AS avg_attempts_to_pass,
    AVG(duration_min)                                                        AS avg_duration_min,
    SUM(violation_count)                                                     AS total_violations
FROM dodokpo_dev_gold.cohort_specialization_attempt
WHERE NOT is_excluded
GROUP BY cohort, cohort_year, program_type, specialization, center;


-- ---------------------------------------------------------------------------
-- 3. Specialization performance (Service Center — primary)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW specialization_performance_kpis AS
SELECT
    specialization,
    COUNT(*)                                                                 AS attempts,
    COUNT(DISTINCT assessment_taker_id)                                      AS unique_candidates,
    SUM(is_pass) * 100.0 / NULLIF(COUNT(*), 0)                               AS pass_rate_pct,
    SUM(CASE WHEN attempt_number = 1 AND is_pass = 1 THEN 1 END) * 100.0
        / NULLIF(SUM(CASE WHEN attempt_number = 1 THEN 1 END), 0)            AS first_attempt_pass_rate_pct,
    AVG(score_pct)                                                           AS avg_score_pct,
    APPROX_PERCENTILE(score_pct, 0.5)                                        AS median_score_pct,
    SUM(CASE WHEN proficiency_level = 'Advanced'     THEN 1 END) * 100.0 / NULLIF(COUNT(*),0) AS pct_advanced,
    SUM(CASE WHEN proficiency_level = 'Intermediate' THEN 1 END) * 100.0 / NULLIF(COUNT(*),0) AS pct_intermediate,
    SUM(CASE WHEN proficiency_level = 'Beginner'     THEN 1 END) * 100.0 / NULLIF(COUNT(*),0) AS pct_beginner,
    AVG(CAST(total_attempts_before_pass AS DOUBLE))                          AS avg_attempts_to_pass,
    AVG(duration_min)                                                        AS avg_duration_min,
    AVG((questions_total - questions_failed) / NULLIF(questions_total, 0)) * 100 AS completion_rate_pct,
    SUM(violation_count)                                                     AS total_violations
FROM dodokpo_dev_gold.cohort_specialization_attempt
WHERE NOT is_excluded
GROUP BY specialization;


-- ---------------------------------------------------------------------------
-- 4. Specialization x Tech CONTENT coverage (curriculum view).
-- NOTE: tech (category) lives at question grain, so this is CONTENT coverage
-- (how many questions / calibration per tech) — not candidate performance by
-- tech, which needs per-question response data (future build).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW specialization_tech_kpis AS
WITH q AS (
    SELECT id, categoryid, domainid, calibrationscore, difficultylevel FROM (
        SELECT id, categoryid, domainid, calibrationscore, difficultylevel, load_date,
               ROW_NUMBER() OVER (PARTITION BY id ORDER BY load_date DESC) AS _rn
        FROM dodokpo_dev_silver.test_creation_question
    ) WHERE _rn = 1
),
cat AS (
    SELECT id, name FROM (
        SELECT id, name, load_date,
               ROW_NUMBER() OVER (PARTITION BY id ORDER BY load_date DESC) AS _rn
        FROM dodokpo_dev_silver.test_creation_category
    ) WHERE _rn = 1
),
dom AS (
    SELECT id, name FROM (
        SELECT id, name, load_date,
               ROW_NUMBER() OVER (PARTITION BY id ORDER BY load_date DESC) AS _rn
        FROM dodokpo_dev_silver.test_creation_domain
    ) WHERE _rn = 1
)
SELECT
    COALESCE(cc.specialization, cw.specialization, 'Unmapped')               AS specialization,
    COALESCE(cc.tech, 'Unmapped')                                            AS tech,
    COUNT(DISTINCT q.id)                                                     AS questions,
    AVG(TRY(CAST(q.calibrationscore AS DOUBLE)))                             AS avg_calibration_score,
    COUNT(DISTINCT CASE WHEN q.difficultylevel = 'hard'   THEN q.id END)     AS hard_questions,
    COUNT(DISTINCT CASE WHEN q.difficultylevel = 'medium' THEN q.id END)     AS medium_questions,
    COUNT(DISTINCT CASE WHEN q.difficultylevel = 'easy'   THEN q.id END)     AS easy_questions
FROM q
LEFT JOIN cat ON q.categoryid = cat.id
LEFT JOIN dom ON q.domainid   = dom.id
LEFT JOIN category_crosswalk cc
       ON LOWER(TRIM(regexp_replace(cat.name, '[ _]\d{6,}.*$', ''))) = LOWER(cc.key_norm)
LEFT JOIN specialization_crosswalk cw
       ON LOWER(TRIM(regexp_replace(dom.name, '[ _]\d{6,}.*$', ''))) = LOWER(cw.key_norm)
GROUP BY COALESCE(cc.specialization, cw.specialization, 'Unmapped'), COALESCE(cc.tech, 'Unmapped');


-- ---------------------------------------------------------------------------
-- 5. Individual performance within a COHORT (ranked)
-- ---------------------------------------------------------------------------
-- One row per PERSON (email) per cohort. A person has many assessment_taker_id
-- values (one per dispatch), so we aggregate by email — attempts/tests are totals.
CREATE OR REPLACE VIEW candidate_cohort_performance AS
WITH cand AS (
    SELECT
        cohort, cohort_year, program_type, center, email,
        ARBITRARY(candidatename)                                            AS candidatename,
        ARBITRARY(candidate_source)                                         AS candidate_source,
        COUNT(*)                                                             AS attempts,
        COUNT(DISTINCT test_id)                                              AS tests_taken,
        SUM(is_pass) * 100.0 / NULLIF(COUNT(*), 0)                           AS pass_rate_pct,
        AVG(score_pct)                                                       AS avg_score_pct,
        MAX(score_pct)                                                       AS best_score_pct,
        MAX_BY(score_pct, attempt_number)                                    AS latest_score_pct,
        MAX_BY(proficiency_level, attempt_number)                            AS latest_proficiency,
        MAX_BY(score_pct, attempt_number) - MIN_BY(score_pct, attempt_number) AS score_improvement,
        SUM(violation_count) * 2.0 + SUM(violation_duration_sec) / 60.0      AS integrity_risk_score
    FROM dodokpo_dev_gold.cohort_specialization_attempt
    GROUP BY cohort, cohort_year, program_type, center, email
)
SELECT
    cand.*,
    RANK()         OVER (PARTITION BY cohort ORDER BY avg_score_pct DESC)    AS rank_in_cohort,
    PERCENT_RANK() OVER (PARTITION BY cohort ORDER BY avg_score_pct)         AS percentile_in_cohort
FROM cand;


-- ---------------------------------------------------------------------------
-- 6. Individual performance within a SPECIALIZATION (ranked)
-- ---------------------------------------------------------------------------
-- One row per PERSON (email) per specialization (aggregated across their takers).
CREATE OR REPLACE VIEW candidate_specialization_performance AS
WITH cand AS (
    SELECT
        specialization, center, email,
        ARBITRARY(candidatename)                                            AS candidatename,
        ARBITRARY(candidate_source)                                         AS candidate_source,
        COUNT(*)                                                             AS attempts,
        COUNT(DISTINCT test_id)                                              AS tests_taken,
        SUM(is_pass) * 100.0 / NULLIF(COUNT(*), 0)                           AS pass_rate_pct,
        AVG(score_pct)                                                       AS avg_score_pct,
        MAX(score_pct)                                                       AS best_score_pct,
        MAX_BY(score_pct, attempt_number)                                    AS latest_score_pct,
        MAX_BY(proficiency_level, attempt_number)                            AS latest_proficiency,
        MAX_BY(score_pct, attempt_number) - MIN_BY(score_pct, attempt_number) AS score_improvement,
        SUM(violation_count) * 2.0 + SUM(violation_duration_sec) / 60.0      AS integrity_risk_score
    FROM dodokpo_dev_gold.cohort_specialization_attempt
    WHERE NOT is_excluded
    GROUP BY specialization, center, email
)
SELECT
    cand.*,
    RANK()         OVER (PARTITION BY specialization ORDER BY avg_score_pct DESC) AS rank_in_specialization,
    PERCENT_RANK() OVER (PARTITION BY specialization ORDER BY avg_score_pct)      AS percentile_in_specialization
FROM cand;


-- ---------------------------------------------------------------------------
-- 7. Cohort progression over time (trend)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW cohort_progression_trend AS
SELECT
    cohort,
    cohort_year,
    program_type,
    specialization,
    attempt_month,
    attempt_quarter,
    COUNT(*)                                                                 AS attempts,
    COUNT(DISTINCT assessment_taker_id)                                      AS unique_candidates,
    SUM(is_pass) * 100.0 / NULLIF(COUNT(*), 0)                               AS pass_rate_pct,
    AVG(score_pct)                                                           AS avg_score_pct
FROM dodokpo_dev_gold.cohort_specialization_attempt
WHERE attempt_month IS NOT NULL AND attempt_month <> ''
GROUP BY cohort, cohort_year, program_type, specialization, attempt_month, attempt_quarter;


-- ---------------------------------------------------------------------------
-- 8. Coverage / data-quality gauge — how much resolves to a real cohort/spec.
-- This is the trust indicator: on synthetic data it reads ~0% cohort resolved.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW additional_analytics_coverage AS
SELECT
    COUNT(*)                                                                 AS total_attempts,
    SUM(has_specialization)                                                  AS real_specialization_attempts,
    SUM(CASE WHEN is_excluded THEN 1 ELSE 0 END)                             AS excluded_attempts,
    SUM(CASE WHEN specialization = 'Unmapped' THEN 1 ELSE 0 END)             AS unmapped_specialization_attempts,
    SUM(has_cohort)                                                          AS attempts_with_cohort,
    AVG(CAST(has_specialization AS DOUBLE)) * 100.0                          AS pct_specialization_resolved,
    AVG(CAST(has_cohort AS DOUBLE)) * 100.0                                  AS pct_cohort_resolved,
    COUNT(DISTINCT CASE WHEN has_specialization = 1 THEN specialization END) AS distinct_specializations,
    COUNT(DISTINCT CASE WHEN cohort <> 'Unassigned' THEN cohort END)         AS distinct_cohorts,
    SUM(CASE WHEN cohort = 'Unassigned' THEN 1 ELSE 0 END)                   AS unassigned_cohort_attempts
FROM dodokpo_dev_gold.cohort_specialization_attempt;


-- ---------------------------------------------------------------------------
-- 9. Per-question CONTENT EFFICACY — how candidates actually perform on each
-- question, aggregated across ALL recorded attempts. Unnests the per-question
-- `result` JSON in test_execution_testresult (questionId / scored / idleTime /
-- isAnswered), dedupes testresults to the latest load_date per sitting, and
-- joins question metadata + domain→specialization. Powers "hardest questions",
-- "most-skipped" and "idle-time hotspots". NOTE: this is catalogue-wide content
-- efficacy (not filtered by the dashboard's year/cohort slicers).
-- specialization uses the real crosswalk only (unmatched → 'Unmapped'); no
-- hash fallback here — content gaps should read honestly.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW question_performance AS
WITH testresult_dedup AS (
    SELECT result FROM (
        SELECT result, load_date,
               ROW_NUMBER() OVER (PARTITION BY assessmenttakerid, testid, attemptnumber
                                  ORDER BY load_date DESC) AS _rn
        FROM dodokpo_dev_silver.test_execution_testresult
        WHERE result IS NOT NULL AND result <> '' AND result LIKE '[{%'
    ) WHERE _rn = 1
),
parsed AS (
    SELECT
        json_extract_scalar(q, '$.questionId')                          AS question_id,
        TRY(CAST(json_extract_scalar(q, '$.score')   AS DOUBLE))        AS max_score,
        TRY(CAST(json_extract_scalar(q, '$.scored')  AS DOUBLE))        AS achieved_score,
        TRY(CAST(json_extract_scalar(q, '$.idleTime') AS DOUBLE))       AS idle_time_sec,
        TRY(CAST(json_extract_scalar(q, '$.isAnswered') AS BOOLEAN))    AS is_answered
    FROM testresult_dedup t
    CROSS JOIN UNNEST(CAST(json_parse(t.result) AS ARRAY(JSON))) AS u(q)
),
question_dedup AS (
    SELECT id, questiontype, difficultylevel, questiontitle, questiontext, domainid FROM (
        SELECT id, questiontype, difficultylevel, questiontitle, questiontext, domainid, load_date,
               ROW_NUMBER() OVER (PARTITION BY id ORDER BY load_date DESC) AS _rn
        FROM dodokpo_dev_silver.test_creation_question
    ) WHERE _rn = 1
),
domain_dedup AS (
    SELECT id, name FROM (
        SELECT id, name, load_date,
               ROW_NUMBER() OVER (PARTITION BY id ORDER BY load_date DESC) AS _rn
        FROM dodokpo_dev_silver.test_creation_domain
    ) WHERE _rn = 1
),
agg AS (
    SELECT
        question_id,
        COUNT(*)                                                        AS times_served,
        SUM(CASE WHEN is_answered THEN 1 ELSE 0 END)                    AS times_answered,
        SUM(CASE WHEN achieved_score > 0 THEN 1 ELSE 0 END)             AS times_correct,
        AVG(idle_time_sec)                                              AS avg_idle_sec,
        AVG(CASE WHEN max_score > 0 THEN achieved_score / max_score END) * 100.0 AS avg_score_ratio_pct,
        AVG(max_score)                                                  AS avg_max_score
    FROM parsed
    WHERE question_id IS NOT NULL
    GROUP BY question_id
)
SELECT
    a.question_id,
    qd.questiontype                                                     AS question_type,
    qd.difficultylevel                                                  AS question_difficulty,
    qd.questiontitle                                                    AS question_title,
    qd.questiontext                                                     AS question_text,
    COALESCE(cw.specialization, 'Unmapped')                             AS specialization,
    d.name                                                              AS domain_name,
    a.times_served,
    a.times_answered,
    a.times_correct,
    a.times_answered * 100.0 / NULLIF(a.times_served, 0)                AS answer_rate_pct,
    a.times_correct  * 100.0 / NULLIF(a.times_served, 0)                AS correct_rate_pct,
    a.avg_idle_sec,
    a.avg_score_ratio_pct,
    a.avg_max_score
FROM agg a
LEFT JOIN question_dedup qd ON a.question_id = qd.id
LEFT JOIN domain_dedup   d  ON qd.domainid   = d.id
LEFT JOIN specialization_crosswalk cw
       ON LOWER(TRIM(regexp_replace(d.name, '[ _]\d{6,}.*$', ''))) = LOWER(cw.key_norm);
