# Dashboard & Analytics Interface — User Guide

The Streamlit dashboard is the visual intelligence layer for the Dodokpo pipeline.  
It reads directly from the Athena view datasets (or demo data when no S3 bucket is configured) and is designed as an executive BI tool — not a raw data viewer.

**File**: `dashboard/app.py`  
**Data layer**: `dashboard/data_access.py`  
**Start**: `streamlit run dashboard/app.py`  
**Env var**: `GOLD_BUCKET` — set to the gold S3 bucket name to load live data.

---

## 1. Global Controls (Sidebar)

| Control | Type | Purpose |
| :--- | :--- | :--- |
| **Gold S3 Bucket** | Text input | Connects the dashboard to live gold data. Leave blank to use built-in demo data. |
| **Period (Month)** | Multi-select | Filters all panels to selected calendar months (`YYYY-MM`). Defaults to the most recent 3 months. |
| **Domain** | Multi-select | Filters by test domain (e.g., Engineering, Data). |
| **Category** | Multi-select | Filters by test sub-category. |
| **Difficulty** | Multi-select | Filters by test difficulty level: easy / medium / hard. |
| **Proficiency** | Multi-select | Filters by candidate proficiency tier: Beginner / Intermediate / Advanced. |
| **Candidate Source** | Multi-select | Filters by Internal (AmaliTech) or External candidates. |

All filters are multi-select — you can combine multiple values in any filter simultaneously. Selecting nothing in a filter means "show all."

An **Export CSV** button in the top-right of the main panel downloads the currently filtered dataset.

---

## 2. KPI Strip — Executive Pulse

Six metric cards run across the top of every page:

| Card | Metric | Delta shown |
| :--- | :--- | :--- |
| Unique Assessments | Count of distinct test IDs in the filtered view | — |
| Candidates | Count of distinct assessment taker IDs | — |
| Avg Score | Mean score % across all filtered attempts | ▲▼ vs prior calendar month |
| Pass Rate | % of attempts with `pass_status = 'passed'` | ▲▼ vs prior calendar month |
| Avg Duration | Mean attempt duration in minutes | — |
| Internal % | % of filtered candidates who are AmaliTech employees | — |

The delta indicators on Avg Score and Pass Rate use the immediately preceding calendar month as the baseline. Green delta = improvement, red = decline.

---

## 3. Strategic Layer — Primary Charts

### Pass Rate & Avg Score Trend (Monthly Line Chart)
- **X axis**: Calendar month (`attempt_month`)
- **Y axis**: Pass Rate % (solid line, indigo) and Avg Score % (dotted line, green)
- **Purpose**: The primary executive chart. Shows whether outcome quality is improving or declining over time. A widening gap between score and pass rate indicates the pass threshold may be miscalibrated.

### Integrity Risk Composition (Donut Chart)
- **Segments**: Low Risk · Medium Risk · High Risk, sized by candidate count
- **Colour**: Green / Amber / Red
- **Purpose**: Instant read on the integrity posture of the current candidate pool. High Risk > 10% warrants investigation.

---

## 4. Analytical Layer — Secondary Charts

### Score Distribution & Outlier Identification (Box Plot)
- **X axis**: Assessment title
- **Y axis**: Score %
- **Colour**: Proficiency level (Advanced=green, Intermediate=amber, Beginner=red)
- **Points**: All individual attempts shown as dots
- **Purpose**: The IQR box shows where the majority of candidates score; dots outside the whiskers are outliers. High-scoring outliers in low-pass-rate assessments identify top talent. Low-scoring outliers in high-pass-rate assessments flag curriculum gaps.

### Completion Funnel (Funnel Chart)
- **Stages**: Registered → Submitted → Passed
- **Purpose**: Shows exactly where candidates drop out. A large Registered→Submitted gap indicates abandonment; a large Submitted→Passed gap indicates difficulty calibration issues.

### Avg Score Heatmap — Domain × Difficulty (Heatmap)
- **Rows**: Domain names
- **Columns**: Difficulty levels (easy / medium / hard)
- **Cell value**: Mean score %
- **Colour scale**: Red (low) → Amber → Green (high)
- **Purpose**: Curriculum gap radar. Red cells identify domain-difficulty combinations where candidates consistently underperform — these need syllabus review.

---

## 5. Operational Layer — Audit Trail

A full sortable data table shows every row in the filtered dataset. Click any row to open the **Candidate Drill-Down Modal**.

### Candidate Drill-Down Modal
Triggered by selecting a table row. Shows all attempts by the same candidate on the same test:

- **Cohort Avg Score**: Mean score across the candidate's attempts
- **Integrity Profile**: Most common integrity label for that candidate
- **Total Score Gain**: Sum of all `score_improvement` deltas across attempts
- **Detail table**: All attempts with score, pass/fail, proficiency, attempt number, and score improvement
- **Score Progression Chart** (shown when ≥ 2 attempts exist): Line chart of score % by attempt number — visualises learning velocity

---

## 6. Role-Based Tabs

### 🎓 Training Center
Audience: Trainers and Training Managers

- **Assessment Performance Summary table**: Aggregated per assessment — taker count, avg score, pass rate, avg duration, avg attempts
- **Score Progression chart**: Line chart showing how returning candidates' scores change across attempts (source: `candidate_growth_tracking`)
- **Internal vs External Pass Rate bar chart**: Compares pass rates between AmaliTech employees and external candidates. Includes a 70% target reference line.

### 🛡 Service Center
Audience: Exam proctors and integrity officers

- **Violations by Assessment bar chart**: Grouped bars showing violation counts per assessment, coloured by severity tier
- **Violations vs Questions Failed scatter**: Correlation between violation count and question failure count — High Risk outliers appear top-right
- **Violation audit table**: Sortable table of all test results with violation counts, severity, domain, and difficulty

### 👥 HR / CDC
Audience: HR teams and Curriculum Development Coordinators

- **Proficiency Distribution donut**: Breakdown of Beginner / Intermediate / Advanced candidates in the filtered cohort
- **Attempts Needed to Pass histogram**: Distribution of how many attempts passing candidates required — spikes at attempt > 2 indicate poorly calibrated assessments
- **Time to Finish vs Score Quality scatter**: Duration (x) vs score (y), coloured by proficiency — candidates in the bottom-right (long duration, low score) need targeted support

### 📊 Executive
Audience: Training Center leadership and C-level

- **Executive Summary table**: One row per assessment — taker count, avg score, pass rate, avg attempts, sortable by pass rate
- **Score Quality vs Pass Rate bubble chart**: Each bubble is one assessment. X = avg score, Y = pass rate, bubble size = total takers. Colour gradient: red (low pass rate) → green (high pass rate). A 70% pass rate reference line is shown. Assessments below the line need attention.
- **Trainer Question Output stacked bar**: Per-trainer breakdown of questions created by difficulty (easy=green, medium=amber, hard=red)
- **Trainer Calibration Score bar chart**: Per-trainer average calibration score with an 80-point target reference line. Bars below target are flagged visually by the red→green colour scale.

---

## 7. Data Freshness Footer

A dark status bar at the bottom of the page shows the most recent `load_date` for each gold table (sourced from the `gold_data_freshness` Athena view). Use this to confirm that the pipeline has run recently before acting on dashboard insights.

---

## 8. Demo Mode

When no S3 bucket is configured (the Gold S3 Bucket field is empty), the dashboard loads synthetic demo data that mirrors the exact column schemas of all Athena views. Demo mode covers:
- `demo_candidate_performance()` → mirrors `trainer_candidate_performance`
- `demo_quality_violations()` → mirrors `trainer_quality_violations`
- `demo_executive_trainer_kpis()` → mirrors `executive_trainer_kpis`
- `demo_senior_analytics()` → mirrors `senior_analytics_insights`
- `demo_candidate_growth()` → mirrors `candidate_growth_tracking`
- `demo_data_freshness()` → mirrors `gold_data_freshness`

Demo data is defined in `dashboard/data_access.py`.

---

## 9. Data Caching

All S3 reads are wrapped with `@st.cache_data(ttl=300)`. The dashboard re-fetches data from S3 at most every **5 minutes**. To force a refresh, use the Streamlit menu → Clear cache.
