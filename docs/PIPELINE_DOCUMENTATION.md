# Dodokpo Medallion Pipeline — Master Documentation

This is the top-level reference for the Dodokpo data pipeline. Each section summarises a domain; detailed pages are in `docs/confluence/`.

---

## 1. Infrastructure (IaC)

Full detail: [`docs/confluence/01_infrastructure.md`](confluence/01_infrastructure.md)

The pipeline is deployed entirely on AWS using **Terraform v1.x** (`infra/` directory). All components are serverless.

### Core AWS Services

| Service | Role |
| :--- | :--- |
| **Amazon S3** | Three-layer data lake: bronze, silver, gold + Athena results bucket |
| **AWS Lambda** | ETL compute — three Docker-containerised functions (bronze, silver, gold) |
| **AWS Step Functions** | Pipeline orchestration — sequential stages with parallel Map states |
| **Amazon EventBridge Scheduler** | Triggers the Step Functions state machine on a cron schedule |
| **AWS Glue + Amazon Athena** | Schema discovery (crawlers) and serverless SQL query layer |
| **AWS Secrets Manager** | Stores PostgreSQL credentials (read by Bronze Lambda at runtime) |
| **AWS SSM Parameter Store** | Stores per-table watermark timestamps for incremental extraction |
| **Amazon ECR** | Hosts Docker images for all three Lambda functions |
| **Amazon CloudWatch + SNS** | Alarms on Lambda errors and Step Functions failures → email alerts |

### Step Functions Pipeline Stages

```
EventBridge Scheduler
        │
        ▼
Step Functions State Machine
  ├─ BronzeSync Map (1 Lambda per table)
  ├─ SilverTransform Map (max 10 concurrent Lambdas)
  └─ GoldTransform Map (max 5 concurrent Lambdas)
```

All Lambda invocations retry with exponential backoff (30s initial, max 3 attempts).

---

## 2. ETL Processing

Full detail: [`docs/confluence/02_etl_processing.md`](confluence/02_etl_processing.md)

The pipeline implements a **Medallion Architecture** (Bronze → Silver → Gold).

### Bronze — Incremental Extraction
- Reads from source PostgreSQL using watermark-based incremental extraction (`updated_at` column).
- First run: full table extract. Subsequent runs: rows where `updated_at > last_watermark`.
- Watermark stored in SSM; advances only after a successful S3 write.
- Output format: Snappy-compressed Parquet. Key: `table={table}/date={YYYY-MM-DD}/{HHMMSS}.parquet`

### Silver — Cleaning (Pass-Through)
- Reads the latest bronze partition for each `(database, table)` pair.
- Applies a cleaning dispatch function (`transforms.py`). **Currently pass-through** — all tables copy bronze data unchanged. Per-table cleaning rules will be registered as data contracts are confirmed.
- Two silver database names: `dodokpo_test_creation_staging`, `dodokpo_test_execution_staging`

### Gold — Column Pruning & Type Normalisation
Gold Lambdas perform three operations only: drop internal/metadata columns, convert `duration` from seconds to minutes, and derive `candidatename` from email (for AssessmentTaker). **No joins or aggregations occur in Lambda** — those are handled by Athena views.

**9 Gold datasets**:
`test_creation_category` · `test_creation_assessmenttaker` · `test_creation_domain` · `test_creation_test` · `test_creation_question` · `test_creation_assessment` · `test_creation_skill` · `test_execution_testresult` · `test_execution_questionflag`

### Athena SQL Views (Analytical Layer)
Six views in `infra/sql/trainer_executive_metrics_views.sql` implement all joins and metric calculations on top of the gold tables:

| View | Purpose |
| :--- | :--- |
| `trainer_candidate_performance` | Per-attempt results with domain, category, proficiency, and source context |
| `trainer_quality_violations` | Violation audit per test with severity tiers |
| `executive_trainer_kpis` | Trainer productivity — questions created, active, calibration score, difficulty mix |
| `senior_analytics_insights` | Integrity risk scoring and question-level completion funnel |
| `gold_data_freshness` | Latest `load_date` per gold table — pipeline health monitor |
| `candidate_growth_tracking` | Score delta across attempts using `LAG` window function |

---

## 3. KPI & Business Metrics

Full detail: [`docs/confluence/03_kpi_dictionary.md`](confluence/03_kpi_dictionary.md)

### Candidate Performance
| Metric | Formula | Source View |
| :--- | :--- | :--- |
| Pass Rate | `(passed attempts / total attempts) × 100` | `trainer_candidate_performance` |
| Average Score | `AVG(score_pct)` | `trainer_candidate_performance` |
| Proficiency Level | Advanced ≥80% · Intermediate 50–79% · Beginner <50% | `trainer_candidate_performance` |
| Attempts to Pass | `COUNT(*) GROUP BY taker + test` | `trainer_candidate_performance` |
| Score Improvement | `score_pct − LAG(score_pct)` | `candidate_growth_tracking` |

### Integrity & Risk
| Metric | Formula | Source View |
| :--- | :--- | :--- |
| Integrity Risk Score | `(violation_count × 2.0) + (violation_duration ÷ 60.0)` | `senior_analytics_insights` |
| Integrity Label | High Risk >10 · Medium Risk >5 · Low Risk ≤5 | `senior_analytics_insights` |
| Violation Severity | High >5 · Low 1–5 · None = 0 | `trainer_quality_violations` |

### Trainer Productivity
| Metric | Formula | Source View |
| :--- | :--- | :--- |
| Total Questions Created | `COUNT(DISTINCT q.id)` | `executive_trainer_kpis` |
| Avg Calibration Score | `AVG(calibrationscore)` — target ≥ 80 | `executive_trainer_kpis` |

---

## 4. Dashboard

Full detail: [`docs/confluence/04_dashboard_guide.md`](confluence/04_dashboard_guide.md)

**Stack**: Streamlit + Plotly · File: `dashboard/app.py`  
**Data source**: Athena views read as Parquet from the gold S3 bucket (`GoldDatasetReader` in `data_access.py`)  
**Demo mode**: All panels render with synthetic data when no bucket is configured.

### User Roles & Tabs

| Tab | Primary Audience | Key Visualisations |
| :--- | :--- | :--- |
| 🎓 Training Center | Trainers, Training Managers | Assessment summary table · Score progression line chart · Internal vs External pass rate bar chart |
| 🛡 Service Center | Exam proctors, Integrity officers | Violations bar chart · Violations vs Questions Failed scatter · Violation audit table |
| 👥 HR / CDC | HR teams, Curriculum developers | Proficiency donut · Attempts-to-pass histogram · Duration vs Score scatter |
| 📊 Executive | Training leadership, C-level | Executive summary table · Score vs Pass Rate bubble chart · Trainer productivity bars · Calibration quality chart |

### Global Charts (above tabs, apply to all roles)

| Chart | Type | Purpose |
| :--- | :--- | :--- |
| KPI Strip | 6 metric cards with MoM delta | Pulse check: assessments, candidates, avg score, pass rate, duration, internal % |
| Pass Rate & Avg Score Trend | Monthly line chart | Primary executive trend — are outcomes improving? |
| Integrity Risk Composition | Donut chart | Risk posture of the current candidate pool |
| Score Distribution | Box plot per assessment | Outlier identification by proficiency tier |
| Completion Funnel | Funnel chart | Registered → Submitted → Passed dropout analysis |
| Domain × Difficulty Heatmap | Colour heatmap | Curriculum gap radar — identifies weak domain-difficulty combinations |
| Operational Audit Trail | Interactive data table | Full row-level drill-down via candidate modal |
| Data Freshness Footer | Status bar | Shows last sync date per gold table |

### Interactivity
- All sidebar filters are **multi-select** — multiple values can be combined in any filter.
- **Month filter** defaults to the last 3 calendar months.
- **Drill-down modal**: Selecting any audit trail row opens a per-candidate history modal with attempt table and score progression chart.
- **Export**: Filtered dataset downloadable as CSV from the top-right button.
- **Cache TTL**: S3 data is cached for 5 minutes per `@st.cache_data(ttl=300)`.

---

## 5. Cohort & Specialization Analytics

Full detail: [`docs/confluence/06_cohort_specialization_analytics.md`](confluence/06_cohort_specialization_analytics.md) (implementation & operations) · [`docs/confluence/05_cohort_specialization_kpis.md`](confluence/05_cohort_specialization_kpis.md) (KPI dictionary)

An **additive** analytics layer that takes reporting below the organization level — to
**cohort** (Training Center, filterable by specialization) and **specialization** (Service
Center / developers), with individual drill-down. It reuses the org-level
`trainer_candidate_performance` view as its measure source; the existing org views are
**unchanged**.

- **Views**: 13 views in `dodokpo_dev_gold` from `infra/sql/cohort_specialization_views.sql`
  (4 editable crosswalks, 1 base, 8 aggregates). Deployed via `python infra/sql/deploy_views.py`.
- **Dimensions**: specialization (from assessment domain), tech (from category), cohort
  (`<year> <program>` from dispatch tags), center.
- **Dashboards**: `dashboard/pages/1_Training_Center.py` and `dashboard/pages/2_Service_Center.py`,
  reachable from the Executive dashboard nav bar.
- **Coverage today**: ~47.6% of attempts resolve to a real specialization; cohort coverage is
  limited (~1.2%) by upstream program-tagging — see the operations guide.
