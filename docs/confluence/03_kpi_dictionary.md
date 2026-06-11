# KPI and Business Metrics Dictionary

This page defines every metric used in the Dodokpo pipeline — how it is calculated, which Athena view or gold table is the source, and which dashboard panel surfaces it.

---

## 1. Candidate Performance Metrics

| Metric | Definition | Source | Formula |
| :--- | :--- | :--- | :--- |
| **Pass Rate** | Percentage of assessment attempts that meet or exceed the pass mark. | `trainer_candidate_performance` | `(COUNT WHERE pass_status = 'passed') / COUNT(*) × 100` |
| **Average Score** | Mean percentage score across all filtered attempts. | `trainer_candidate_performance.score_pct` | `AVG(CAST(test_percentage AS DOUBLE))` |
| **Proficiency Level** | Categorical tier assigned per attempt based on score. | `trainer_candidate_performance.proficiency_level` | Advanced ≥ 80% · Intermediate 50–79% · Beginner < 50% |
| **Attempts to Pass** | Total number of attempts a candidate made on a given test before first passing. | `trainer_candidate_performance.total_attempts_before_pass` | `COUNT(*) GROUP BY assessment_taker_id, test_id` |
| **Avg Duration** | Mean time from test start to submission, in minutes. | `trainer_candidate_performance.duration_min` | `AVG(duration)` where duration is pre-converted from seconds in the Gold Lambda |
| **Score Improvement** | Delta between a candidate's score on attempt N and attempt N−1 on the same test. | `candidate_growth_tracking.score_improvement` | `score_pct − LAG(score_pct) OVER (PARTITION BY assessment_taker_id, test_id ORDER BY attempt_number)` |

---

## 2. Candidate Segmentation Dimensions

| Dimension | Definition | Source | Values |
| :--- | :--- | :--- | :--- |
| **Candidate Source** | Whether the candidate is an internal AmaliTech employee or an external test-taker. | `trainer_candidate_performance.candidate_source` | `Internal` (email domain contains `amalitech`) · `External` (all others) |
| **Email Domain** | Raw domain extracted from the candidate's email address. | `trainer_candidate_performance.email_domain` | `SUBSTR(email, STRPOS(email, '@') + 1)` |
| **Attempt Month** | Calendar month of the attempt, used for trend slicing. | `trainer_candidate_performance.attempt_month` | `SUBSTR(load_date, 1, 7)` → format `YYYY-MM` |
| **Test Difficulty** | Difficulty level assigned to the test in the source system. | `test_creation_test.difficultylevel` | `easy` · `medium` · `hard` |
| **Domain Name** | Subject domain of the test (e.g., Engineering, Data, HR). | `test_creation_domain.name` | Free-text from source |
| **Category Name** | Sub-category within a domain. | `test_creation_category.title` | Free-text from source |
| **Organization** | Organization that owns/dispatched the assessment. Sliced by `organization_id`, labelled by `organization_name`. | `trainer_candidate_performance.organization_id` / `organization_name` (`AssessmentTaker.organizationid` → `user_mgt_organizations.organizationname`) | ~17 distinct orgs present in assessment data |

---

## 3. Testing Integrity & Risk Metrics

| Metric | Definition | Source | Formula |
| :--- | :--- | :--- | :--- |
| **Violation Count** | Number of times the candidate exited the test browser window or switched tabs during an attempt. | `test_execution_testresult.test_window_violation_count` | Raw integer from source |
| **Violation Duration** | Total time (seconds) the test window was inactive due to violations. | `test_execution_testresult.test_window_violation_duration` | Raw integer from source |
| **Integrity Risk Score** | Weighted composite score combining violation frequency and duration to flag suspicious behaviour. | `senior_analytics_insights.integrity_risk_score` | `(test_window_violation_count × 2.0) + (test_window_violation_duration ÷ 60.0)` |
| **Integrity Label** | Qualitative risk tier derived from the Integrity Risk Score. | `senior_analytics_insights.integrity_label` | High Risk: score > 10 · Medium Risk: score > 5 · Low Risk: score ≤ 5 |
| **Violation Severity** | Categorical label for operational filtering of test results. | `trainer_quality_violations.violation_severity_slice` | High Violations: count > 5 · Low Violations: count 1–5 · No Violations: count = 0 |
| **Questions Failed** | Number of individual questions a candidate answered incorrectly in one attempt. | `test_execution_testresult.number_of_questions_failed` | Raw integer from source |

---

## 4. Operational & Funnel Metrics

| Metric | Definition | Source | Formula |
| :--- | :--- | :--- | :--- |
| **Completion Funnel %** | Proportion of test questions answered out of the total assigned — measures test abandonment at question level. | `senior_analytics_insights.completion_funnel_pct` | `number_of_questions_answered ÷ NULLIF(number_of_questions, 0)` |
| **Internal %** | Proportion of the filtered candidate pool that are internal AmaliTech employees. | Derived from `candidate_source` | `(COUNT WHERE candidate_source = 'Internal') / COUNT(*) × 100` |

---

## 5. Trainer Productivity Metrics

Sourced from `executive_trainer_kpis` view, which aggregates `test_creation_question` by `creator`.

| Metric | Definition | Formula | Target |
| :--- | :--- | :--- | :--- |
| **Total Questions Created** | Total distinct questions authored by a trainer. | `COUNT(DISTINCT q.id)` | — |
| **Active Questions** | Questions with a non-null `activeversionid`. | `COUNT(DISTINCT activeversionid)` | — |
| **Live Questions** | Questions with `status = 'active'`. | `SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END)` | — |
| **Avg Calibration Score** | Mean calibration score across all of a trainer's questions. Measures how well questions discriminate between strong and weak candidates. | `AVG(CAST(calibrationscore AS DOUBLE))` | ≥ 80 |
| **Hard Questions Created** | Count of questions set to `difficultylevel = 'advanced'`. | `COUNT(DISTINCT CASE WHEN difficultylevel = 'hard' THEN id END)` | — |
| **Medium Questions Created** | Count of questions set to `difficultylevel = 'mintermediate'`. | `COUNT(DISTINCT CASE WHEN difficultylevel = 'medium' THEN id END)` | — |
| **Easy Questions Created** | Count of questions set to `difficultylevel = 'beginner'`. | `COUNT(DISTINCT CASE WHEN difficultylevel = 'easy' THEN id END)` | — |

---

## 6. Pipeline Health Metrics

| Metric | Definition | Source | Notes |
| :--- | :--- | :--- | :--- |
| **Data Freshness** | The most recent `load_date` for each gold table, indicating when data was last synced. | `gold_data_freshness` view | Displayed in the dashboard footer. A stale date (>24h behind today) indicates a pipeline failure. |
