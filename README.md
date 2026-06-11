# Dodokpo Analytics Pipeline

## Analytics Goal

The purpose of this project is to **create detailed visualizations that help trainers
understand their candidates' performance trends over periods of time.** Trainers can see
how individual candidates and cohorts progress across attempts, months, quarters, and
years — pass rates, score improvement, time spent, retake behaviour, and integrity
signals — so they can spot who is improving, who is struggling, and how their assessments
perform across the organizations they serve.

The analytics surface answers questions such as:

- How is a candidate's score trending across repeated attempts and over time?
- Are pass rates and average scores improving month-over-month and quarter-over-quarter?
- Which tests, difficulty levels, or organizations drive the most attempts and the lowest pass rates?
- How long do candidates take, how often do they retake, and where do integrity violations cluster?
- How does performance break down **by organization** (sliceable across all 17 organizations present in the data)?

These are delivered through an interactive **Streamlit dashboard** (`dashboard/`) backed by
Athena SQL views over a medallion data lake.

---

## How It Works

The pipeline follows a **Medallion Architecture** (Bronze → Silver → Gold) on AWS, all
serverless and deployed with Terraform.

```
PostgreSQL (source)
      │  watermark-based incremental extract
      ▼
Bronze (raw Parquet, S3)
      │  Silver Lambda — cleaning / pass-through
      ▼
Silver (S3 + Glue/Athena)
      │  Gold Lambda — column pruning & type normalisation
      ▼
Gold (S3 + Glue/Athena)
      │  Athena SQL views — joins, aggregations, trends, org slicing
      ▼
Streamlit dashboard (trainer-facing visualizations)
```

- **Analytical logic lives in Athena SQL views** (`infra/sql/trainer_executive_metrics_views.sql`),
  not in the Lambdas. `trainer_candidate_performance` is the base view; trend, violation,
  retake, organization, and KPI views build on top of it.
- **Organization slicing**: candidate performance and catalog KPIs can be sliced by
  organization, resolved to readable names via the `organizations` lookup
  (`user_mgt` schema) joined on `organizationid`.

---

## Repository Layout

| Path | Purpose |
| :--- | :--- |
| `infra/` | Terraform IaC (S3, Lambda, Step Functions, Glue, Athena, EventBridge) |
| `infra/sql/` | Athena SQL views — the analytical layer powering the dashboard |
| `src/lambda/` | Bronze / Silver / Gold ETL Lambda code |
| `dashboard/` | Streamlit trainer dashboard (`app.py`) + data access helpers |
| `docs/` | Detailed documentation — see below |

---

## Running the Dashboard

```bash
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
```

With AWS credentials configured, the dashboard queries the live Athena views. Without a
configured gold bucket it falls back to synthetic demo data that mirrors each view's schema.

---

## Documentation

- **Master reference**: [`docs/PIPELINE_DOCUMENTATION.md`](docs/PIPELINE_DOCUMENTATION.md)
- Infrastructure: [`docs/confluence/01_infrastructure.md`](docs/confluence/01_infrastructure.md)
- ETL processing: [`docs/confluence/02_etl_processing.md`](docs/confluence/02_etl_processing.md)
- KPI dictionary: [`docs/confluence/03_kpi_dictionary.md`](docs/confluence/03_kpi_dictionary.md)
- Dashboard guide: [`docs/confluence/04_dashboard_guide.md`](docs/confluence/04_dashboard_guide.md)
