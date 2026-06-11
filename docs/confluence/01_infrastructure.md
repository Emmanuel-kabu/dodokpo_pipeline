# Dodokpo Data Pipeline Infrastructure & Cloud Architecture

This page details the serverless AWS architecture powering the Dodokpo Medallion Pipeline.  
All infrastructure is defined as code using **Terraform v1.x** in the `infra/` directory.

---

## 1. High-Level Architecture

```
Source PostgreSQL (RDS)
        │  Secrets Manager credentials
        ▼
  Bronze Lambda  ──►  S3 Bronze Bucket  (table=X/date=YYYY-MM-DD/*.parquet)
        │                    │
  SSM Parameter Store        │  Glue Crawler (bronze)
  (watermark state)          ▼
                       Glue Catalog (bronze DB)
                             │
                       Silver Lambda  ──►  S3 Silver Bucket  (database/table/load_date=X/)
                                                 │
                                           Glue Crawler (silver)
                                                 │
                                           Gold Lambda  ──►  S3 Gold Bucket  (dodokpo/dataset/load_date=X/)
                                                                   │
                                                             Glue Crawler (gold)
                                                                   │
                                                             Athena (SQL views)
                                                                   │
                                                         Streamlit Dashboard

Orchestration:  EventBridge Scheduler  ──►  AWS Step Functions  ──►  Lambda (all 3 layers)
Monitoring:     CloudWatch Alarms  ──►  SNS Topic  ──►  Email alerts
```

---

## 2. Infrastructure Components

### Storage — Amazon S3
Three dedicated buckets following the naming convention `{project}-{env}-{layer}`:

| Bucket | Purpose | Key Pattern |
| :--- | :--- | :--- |
| `{project}-{env}-bronze` | Raw Parquet snapshots from source PostgreSQL | `table={table}/date={YYYY-MM-DD}/{HHMMSS}.parquet` |
| `{project}-{env}-silver` | Cleaned, pass-through copies of bronze data | `{database}/{table}/load_date={YYYY-MM-DD}/part-{HHMMSS}.snappy.parquet` |
| `{project}-{env}-gold` | Business-ready analytical datasets | `dodokpo/{dataset}/load_date={YYYY-MM-DD}/{HHMMSS}.parquet` |
| `{project}-{env}-athena-results` | Athena query result storage | Managed by Athena workgroup |

All buckets have: AES-256 encryption, versioning enabled, public-access blocked, and a bucket policy denying unencrypted transport (`aws:SecureTransport: false`).

### Compute — AWS Lambda (Docker)
Three Lambda functions, each deployed as a **Docker container image** stored in ECR. Docker is required due to the Pandas and PyArrow dependencies that exceed the standard Lambda layer size limit.

| Function | ECR Repository | Trigger |
| :--- | :--- | :--- |
| Bronze Sync | `{project}-bronze-sync` | Step Functions Map state |
| Silver Transform | `{project}-silver-transform` | Step Functions Map state |
| Gold Transform | `{project}-gold-transform` | Step Functions Map state |

Each Lambda's ECR repository has a lifecycle policy retaining the 5 most recent image versions.

### Orchestration — AWS Step Functions
A single state machine manages the full pipeline in three stages:

1. **BronzeSync** — Invokes the Bronze Lambda once per configured table via a `Map` state.
2. **SilverTransform** — Invokes the Silver Lambda for each `(database, table)` pair via a `Map` state (max concurrency: **10**).
3. **GoldTransform** — Invokes the Gold Lambda for each analytical dataset via a `Map` state (max concurrency: **5**).

All Lambda invocations have **retry logic**: exponential backoff starting at 30 seconds, maximum 3 attempts.

The state machine is triggered on a cron schedule by **EventBridge Scheduler**.

### Scheduling — Amazon EventBridge Scheduler
A scheduled rule fires the Step Functions state machine at the configured `sync_schedule` (default: daily). The input payload carries the `tables` array (for bronze) and `datasets` array (for gold).

### Schema & Query — AWS Glue + Amazon Athena
- **Glue Crawlers**: One crawler per S3 layer (bronze, silver, gold) automatically discovers schemas and registers tables in the Glue Data Catalog.
- **Silver crawlers**: Two additional crawlers specifically for `dodokpo_test_creation_staging` and `dodokpo_test_execution_staging` database prefixes.
- **Athena Workgroup**: Configured with a 1 GB per-query data scan limit, SSE-S3 result encryption, and CloudWatch metrics enabled.
- **Athena Named Queries**: The trainer metrics SQL views (`infra/sql/trainer_executive_metrics_views.sql`) are registered as a named query for easy deployment.

---

## 3. Secrets & State Management

| Service | Purpose | What is stored |
| :--- | :--- | :--- |
| **AWS Secrets Manager** | Database credentials | Host, port, username, password for source PostgreSQL |
| **AWS SSM Parameter Store** | Watermark state | Per-table `updated_at` timestamp of the last successful extract, stored at `{SSM_PREFIX}/{table_name}` |

The Bronze Lambda reads its DB credentials exclusively from Secrets Manager — no credentials are stored in environment variables or code.

---

## 4. Security & Networking

- **IAM Roles — Least Privilege**:
  - Lambda execution role: `s3:GetObject`, `s3:PutObject`, `secretsmanager:GetSecretValue`, `ssm:GetParameter`, `ssm:PutParameter`, `ecr:GetAuthorizationToken`, `logs:CreateLogGroup`, `logs:PutLogEvents`.
  - Step Functions execution role: `lambda:InvokeFunction`, `logs:CreateLogDelivery`.
  - EventBridge Scheduler role: `states:StartExecution`.
  - Glue Crawler role: `AWSGlueServiceRole` managed policy + `s3:GetObject` on each layer bucket.
- **VPC Endpoints**: S3 and Glue VPC endpoints ensure data traffic stays within the AWS network backbone and does not traverse the public internet.
- **Encryption at rest**: AES-256 on all S3 buckets.
- **Encryption in transit**: Enforced by bucket policy (denies HTTP).

---

## 5. Monitoring & Alerting

| Resource | Condition | Action |
| :--- | :--- | :--- |
| CloudWatch Alarm (Lambda errors) | `Errors > 0` in any Lambda function | Publishes to SNS topic |
| CloudWatch Alarm (Step Functions failures) | `ExecutionsFailed > 0` | Publishes to SNS topic |
| SNS Topic | Alert received | Sends email to `alert_email` configured in Terraform variables |

CloudWatch Log Groups are created for all three Lambda functions with a configurable retention period (`log_retention_days` Terraform variable).

---

## 6. Terraform Module Structure

```
infra/
├── main.tf              # Root: calls all modules
├── variables.tf         # 13 input variables (project, env, region, db_secret_arn, ...)
├── outputs.tf           # 15 outputs (bucket names, ARNs, Lambda ARNs, ECR URLs, ...)
└── modules/
    ├── s3/              # 4 buckets + policies
    ├── iam/             # Lambda, Step Functions, EventBridge roles
    ├── lambda/          # 3 ECR repos + 3 Lambda functions + log groups
    ├── glue/            # 3 catalog DBs + 5 crawlers + crawler IAM role
    ├── step_functions/  # State machine definition + CloudWatch log group
    ├── athena/          # Workgroup + named query
    ├── eventbridge/     # Scheduler rule
    └── monitoring/      # SNS topic + 2 CloudWatch alarms
```
