# ETL & Medallion Data Processing Flow

This page describes the data transformation lifecycle from raw ingestion to business-ready gold datasets.  
Source: `src/lambda/` — three independent Lambda functions, each with its own Docker image.

---

## 1. Medallion Architecture

| Layer | Purpose | File Format | Compression | S3 Key Pattern | Partition Column |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Bronze** | Raw snapshot from source PostgreSQL | Parquet | Snappy | `table={table}/date={YYYY-MM-DD}/{HHMMSS}.parquet` | `date` |
| **Silver** | Cleaned copy of bronze data | Parquet | Snappy | `{database}/{table}/load_date={YYYY-MM-DD}/part-{HHMMSS}.snappy.parquet` | `load_date` |
| **Gold** | Business-ready analytical datasets | Parquet | Snappy | `dodokpo/{dataset}/load_date={YYYY-MM-DD}/{HHMMSS}.parquet` | `load_date` |

---

## 2. Layer 1 — Bronze Sync

**Source**: `src/lambda/handler.py`, `extraction.py`, `watermark.py`, `s3_writer.py`, `db_connection.py`

### How it works

The Bronze Lambda implements **watermark-based incremental extraction**. It reads credentials from AWS Secrets Manager to open a read-only psycopg2 connection to the source PostgreSQL database.

**Step Functions event shape**:
```json
{ "table": "Assessment" }
```

**Extraction logic** (`extraction.py`):
- Watermark column: `updated_at` (required on every source table)
- First run (no watermark in SSM): `SELECT * FROM {table} ORDER BY updated_at` — full extract
- Subsequent runs: `SELECT * FROM {table} WHERE updated_at > {last_watermark} ORDER BY updated_at` — incremental
- SQL injection protection: table name is validated against `^[a-zA-Z_][a-zA-Z0-9_]*$` before query construction; column/table names are passed through `psycopg2.sql.Identifier`, never string-formatted.

**Watermark persistence** (`watermark.py`):
- After a successful write, the new watermark (`max(updated_at)` ISO timestamp) is stored in SSM at `{SSM_PREFIX}/{table}`.
- On the next run, this value is retrieved and used as the filter threshold.
- If no rows are returned, the previous watermark is retained unchanged.

**S3 output** (`s3_writer.py`):
- DataFrame written as Snappy-compressed Parquet.
- Key: `table={table}/date={YYYY-MM-DD}/{HHMMSS}.parquet`

**Return value to Step Functions**:
```json
{ "table": "Assessment", "rows_synced": 142, "s3_key": "table=Assessment/date=2026-05-31/143022.parquet" }
```

### Source tables

Three PostgreSQL schemas are ingested:

| Schema prefix | Example tables |
| :--- | :--- |
| `test_creation` | Assessment, AssessmentTaker, Test, Question, Domain, Category, Skill |
| `test_execution` | TestResult, QuestionFlag |
| `user_mgt` | organizations (id → organizationName lookup for org-level slicing) |

---

## 3. Layer 2 — Silver Transform

**Source**: `src/lambda/silver/handler.py`, `reader.py`, `transforms.py`, `writer.py`

### How it works

The Silver Lambda reads the latest bronze partition for a given `(database, table)` pair, applies a cleaning function, and writes the result to the silver bucket.

**Step Functions event shape**:
```json
{ "database": "dodokpo_test_creation_staging", "table": "Assessment" }
```

**Reader** (`reader.py`):
- Lists all `load_date` partitions under `{database}/{table}/` in the bronze bucket.
- Selects the **maximum** `load_date` partition (most recent).
- Concatenates all Parquet part files within that partition into a single DataFrame.

**Cleaning dispatch** (`transforms.py`):
```
clean(df, database, table)
  └─► _DISPATCH.get((database, table), _passthrough)(df)
```

> **Current status**: The `_DISPATCH` dictionary is empty — all tables are currently **pass-through** (bronze data is copied to silver unchanged). Per-table cleaning rules will be registered in `_DISPATCH` as data contracts are agreed with the source team.

**Intended cleaning rules** (to be implemented per table):
- Drop internal system metadata columns
- Standardise date/time formats
- Cast string columns to typed equivalents where known

**S3 output** (`writer.py`):
- Key: `{database}/{table}/load_date={load_date}/part-{HHMMSS}.snappy.parquet`

**Idempotency**: The writer checks whether a `load_date` partition already exists before writing. If it does, the run is skipped.

### Silver database names

| Silver DB | Source schema |
| :--- | :--- |
| `dodokpo_test_creation_staging` | `test_creation_*` tables |
| `dodokpo_test_execution_staging` | `test_execution_*` tables |
| `dodokpo_user_mgt_staging` | `user_mgt_*` tables (crawled to `user_mgt_organizations`) |

---

## 4. Layer 3 — Gold Transform

**Source**: `src/lambda/gold/handler.py`, `reader.py`, `transforms.py`, `writer.py`

### How it works

The Gold Lambda reads silver data, applies dataset-specific business logic (column pruning, type conversions, derived fields), and writes the result to the gold bucket.

**Step Functions event shapes**:
```json
{ "dataset": "test_creation_test" }
```
or a batch:
```json
{ "datasets": ["test_creation_test", "test_creation_question"] }
```

**What Gold transforms actually do**:  
Gold Lambdas perform **column pruning and type normalisation only**. Complex analytical logic (joins, proficiency scoring, risk scoring, aggregations) is implemented as **Athena SQL views** on top of the gold tables — see `infra/sql/trainer_executive_metrics_views.sql`.

### The 9 Gold Datasets

| Dataset | Silver source | Key transforms |
| :--- | :--- | :--- |
| `test_creation_category` | `dodokpo_test_creation_staging / Category` | Drops description, organizationid, createdat, updatedat |
| `test_creation_assessmenttaker` | `dodokpo_test_creation_staging / AssessmentTaker` | Drops 17 internal columns; **keeps `organizationid`** (org-level slicing dimension); converts `duration` seconds → minutes; derives `candidatename` from email prefix (before `@`), title-cased |
| `test_creation_domain` | `dodokpo_test_creation_staging / Domain` | Drops organizationid, system, createdat, updatedat |
| `test_creation_test` | `dodokpo_test_creation_staging / Test` | Drops instructions, passage, hash, archivedat; converts `duration` seconds → minutes |
| `test_creation_question` | `dodokpo_test_creation_staging / Question` | Drops questiontext, hash, archivedat, system columns |
| `test_creation_assessment` | `dodokpo_test_creation_staging / Assessment` | Drops instructions, hash, archivedat; converts `duration` seconds → minutes |
| `test_creation_skill` | `dodokpo_test_creation_staging / Skill` | Drops description, tags, system columns |
| `test_execution_testresult` | `dodokpo_test_execution_staging / TestResult` | Drops starttime, finishtime, status, result, screenshot counts; converts `duration` seconds → minutes |
| `test_execution_questionflag` | `dodokpo_test_execution_staging / QuestionFlag` | Drops questiontext, organizationid, createdat, updatedat |

**S3 output** (`writer.py`):
- Key: `dodokpo/{dataset}/load_date={load_date}/{HHMMSS}.parquet`

**Error handling**: Each dataset is transformed independently inside a `try/except`. A single dataset failure is logged and returned as `"status": "failed"` without stopping the other datasets in the same invocation.

---

## 5. Analytical Layer — Athena SQL Views

Athena views defined in `infra/sql/trainer_executive_metrics_views.sql` sit on top of the gold tables and implement all joins and complex metric calculations. These views are the direct data source for the Streamlit dashboard.

| View | Purpose | Key logic |
| :--- | :--- | :--- |
| `trainer_candidate_performance` | Per-attempt candidate results with domain/category/org context | Joins AssessmentTaker → Test → Domain → Category → Organization; derives `proficiency_level`, `candidate_source`, `attempt_month`, `organization_name` |
| `trainer_quality_violations` | Violation analysis per test | Joins TestResult → Test → Domain; derives `violation_severity_slice`; carries `organization_id`/`organization_name` |
| `organization_overview_kpis` | Per-organization rollup (the ~17 orgs in assessment data) | Aggregates `trainer_candidate_performance` by `organization_id`/`organization_name`: attempts, pass rate, avg score/duration, violations, unique candidates/tests |
| `executive_trainer_kpis` | Trainer question productivity | Aggregates Question table by creator; counts by difficulty and active status |
| `senior_analytics_insights` | Integrity risk scoring and funnel | Weighted risk formula; question completion funnel percentage |
| `gold_data_freshness` | Pipeline health monitor | `MAX(load_date)` per gold table |
| `candidate_growth_tracking` | Score progression across attempts | `LAG(score_pct)` window function over `trainer_candidate_performance` |

---

## 6. Reliability & Idempotency

| Concern | Mechanism |
| :--- | :--- |
| **Retry on failure** | Step Functions exponential backoff: 30s initial delay, max 3 attempts per Lambda invocation |
| **Idempotent bronze** | Watermark advances only after a successful S3 write; if Lambda errors before write, the next run re-extracts the same rows |
| **Idempotent silver** | Silver writer checks for existing `load_date` partition before writing |
| **Parallel safety** | Step Functions Map states run tables in parallel; each table has its own SSM watermark key — no cross-table state collision |
| **Observability** | All Lambdas log at INFO level to CloudWatch; Step Functions logs all states to a dedicated CloudWatch log group |
