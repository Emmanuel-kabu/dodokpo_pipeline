"""Helpers for loading gold datasets for the Streamlit dashboard."""

from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass, field

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GoldDatasetReader:
    bucket: str

    def __post_init__(self) -> None:
        import boto3  # lazy — not needed in demo mode
        object.__setattr__(self, "_s3", boto3.client("s3"))

    def read_latest(self, dataset: str) -> pd.DataFrame:
        new_prefix = f"dodokpo/{dataset}/"
        legacy_prefix = f"layer=gold/table={dataset}/"

        keys = self._list_parquet_keys(new_prefix)
        if not keys:
            keys = self._list_parquet_keys(legacy_prefix)

        if not keys:
            return pd.DataFrame()

        frames = [self._read_parquet(key) for key in keys]
        return pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]

    def _list_parquet_keys(self, prefix: str) -> list[str]:
        paginator = self._s3.get_paginator("list_objects_v2")
        return [
            obj["Key"]
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix)
            for obj in page.get("Contents", [])
            if obj["Key"].endswith(".parquet")
        ]

    def _read_parquet(self, key: str) -> pd.DataFrame:
        response = self._s3.get_object(Bucket=self.bucket, Key=key)
        return pd.read_parquet(io.BytesIO(response["Body"].read()), engine="pyarrow")


# ---------------------------------------------------------------------------
# Athena view reader — queries Athena SQL views and returns DataFrames
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AthenaViewReader:
    database: str
    workgroup: str
    results_bucket: str
    region: str = "eu-west-1"

    def query_view(self, view_name: str, limit: int | None = 50_000, order_by: str | None = None) -> pd.DataFrame:
        sql = f'SELECT * FROM "{self.database}"."{view_name}"'
        if order_by:
            sql += f" ORDER BY {order_by}"
        if limit:
            sql += f" LIMIT {limit}"
        return self.run_sql(sql, output_subdir=view_name)

    def run_sql(self, sql: str, output_subdir: str = "adhoc") -> pd.DataFrame:
        """Execute an arbitrary SQL string against the configured Athena workgroup."""
        import boto3  # lazy — not needed in demo mode
        client = boto3.client("athena", region_name=self.region)

        resp = client.start_query_execution(
            QueryString=sql,
            QueryExecutionContext={"Database": self.database},
            ResultConfiguration={
                "OutputLocation": f"s3://{self.results_bucket}/dashboard-cache/{output_subdir}/"
            },
            WorkGroup=self.workgroup,
        )
        qid = resp["QueryExecutionId"]

        # Poll until the query finishes (max 90 s)
        for _ in range(90):
            status = client.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
            state = status["State"]
            if state == "SUCCEEDED":
                break
            if state in ("FAILED", "CANCELLED"):
                reason = status.get("StateChangeReason", "")
                raise RuntimeError(f"Athena query {state}: {reason}")
            time.sleep(1)
        else:
            raise TimeoutError("Athena query timed out after 90 s")

        # Page through results and build DataFrame
        paginator = client.get_paginator("get_query_results")
        columns: list[str] | None = None
        rows: list[list[str]] = []

        for page in paginator.paginate(QueryExecutionId=qid):
            rs = page["ResultSet"]
            if columns is None:
                columns = [c["Label"] for c in rs["ResultSetMetadata"]["ColumnInfo"]]
                data_rows = rs["Rows"][1:]   # first row is the header
            else:
                data_rows = rs["Rows"]
            for row in data_rows:
                rows.append([f.get("VarCharValue", "") for f in row["Data"]])

        df = pd.DataFrame(rows, columns=columns or [])

        # Cast columns to numeric where all non-empty values parse successfully
        for col in df.columns:
            numeric = pd.to_numeric(df[col], errors="coerce")
            if numeric.notna().sum() > 0 and numeric.isna().sum() <= df[col].eq("").sum():
                df[col] = numeric

        return df


# ---------------------------------------------------------------------------
# Demo datasets — mimic each Athena view's output schema exactly
# ---------------------------------------------------------------------------

def demo_candidate_performance() -> pd.DataFrame:
    """Mirrors trainer_candidate_performance view output."""
    rows = [
        {"assessment_taker_id": "t001", "candidatename": "Alice Mensah", "email": "alice.mensah@amalitech.com",
         "email_domain": "amalitech.com", "organization_id": "org-01", "organization_name": "AmaliTech",
         "assessment_id": "a001", "test_id": "test-001",
         "test_title": "Python Fundamentals", "duration_min": 27.4, "score_pct": 86.0, "pass_status": "passed",
         "attempt_number": 1, "load_date": "2026-05-01", "attempt_month": "2026-05",
         "test_difficulty": "medium", "domain_name": "Engineering", "category_name": "Backend",
         "proficiency_level": "Advanced", "total_attempts_before_pass": 1, "is_pass": 1,
         "is_complete": 1, "candidate_source": "Internal"},
        {"assessment_taker_id": "t001", "candidatename": "Alice Mensah", "email": "alice.mensah@amalitech.com",
         "email_domain": "amalitech.com", "organization_id": "org-01", "organization_name": "AmaliTech",
         "assessment_id": "a001", "test_id": "test-001",
         "test_title": "Python Fundamentals", "duration_min": 29.1, "score_pct": 91.0, "pass_status": "passed",
         "attempt_number": 2, "load_date": "2026-05-15", "attempt_month": "2026-05",
         "test_difficulty": "medium", "domain_name": "Engineering", "category_name": "Backend",
         "proficiency_level": "Advanced", "total_attempts_before_pass": 2, "is_pass": 1,
         "is_complete": 1, "candidate_source": "Internal"},
        {"assessment_taker_id": "t002", "candidatename": "Bob Asante", "email": "bob@external.com",
         "email_domain": "external.com", "organization_id": "org-02", "organization_name": "Beta Corp",
         "assessment_id": "a002", "test_id": "test-002",
         "test_title": "SQL Readiness", "duration_min": 30.0, "score_pct": 62.0, "pass_status": "passed",
         "attempt_number": 1, "load_date": "2026-04-10", "attempt_month": "2026-04",
         "test_difficulty": "easy", "domain_name": "Data", "category_name": "Analytics",
         "proficiency_level": "Intermediate", "total_attempts_before_pass": 1, "is_pass": 1,
         "is_complete": 1, "candidate_source": "External"},
        {"assessment_taker_id": "t003", "candidatename": "Carol Boateng", "email": "carol@external.com",
         "email_domain": "external.com", "organization_id": "org-02", "organization_name": "Beta Corp",
         "assessment_id": "a001", "test_id": "test-001",
         "test_title": "Python Fundamentals", "duration_min": 25.0, "score_pct": 38.0, "pass_status": "failed",
         "attempt_number": 1, "load_date": "2026-04-20", "attempt_month": "2026-04",
         "test_difficulty": "medium", "domain_name": "Engineering", "category_name": "Backend",
         "proficiency_level": "Beginner", "total_attempts_before_pass": 1, "is_pass": 0,
         "is_complete": 1, "candidate_source": "External"},
        {"assessment_taker_id": "t003", "candidatename": "Carol Boateng", "email": "carol@external.com",
         "email_domain": "external.com", "organization_id": "org-02", "organization_name": "Beta Corp",
         "assessment_id": "a001", "test_id": "test-001",
         "test_title": "Python Fundamentals", "duration_min": 28.0, "score_pct": 55.0, "pass_status": "passed",
         "attempt_number": 2, "load_date": "2026-05-05", "attempt_month": "2026-05",
         "test_difficulty": "medium", "domain_name": "Engineering", "category_name": "Backend",
         "proficiency_level": "Intermediate", "total_attempts_before_pass": 2, "is_pass": 1,
         "is_complete": 1, "candidate_source": "External"},
        {"assessment_taker_id": "t004", "candidatename": "David Ofori", "email": "david@amalitech.com",
         "email_domain": "amalitech.com", "organization_id": "org-01", "organization_name": "AmaliTech",
         "assessment_id": "a003", "test_id": "test-003",
         "test_title": "Promotion Review", "duration_min": 24.8, "score_pct": 72.0, "pass_status": "passed",
         "attempt_number": 1, "load_date": "2026-03-15", "attempt_month": "2026-03",
         "test_difficulty": "hard", "domain_name": "Engineering", "category_name": "Leadership",
         "proficiency_level": "Intermediate", "total_attempts_before_pass": 1, "is_pass": 1,
         "is_complete": 1, "candidate_source": "Internal"},
        {"assessment_taker_id": "t005", "candidatename": "Esi Quaye", "email": "esi@amalitech.com",
         "email_domain": "amalitech.com", "organization_id": "org-03", "organization_name": "Gamma Labs",
         "assessment_id": "a002", "test_id": "test-002",
         "test_title": "SQL Readiness", "duration_min": 20.0, "score_pct": 45.0, "pass_status": "failed",
         "attempt_number": 1, "load_date": "2026-03-20", "attempt_month": "2026-03",
         "test_difficulty": "easy", "domain_name": "Data", "category_name": "Analytics",
         "proficiency_level": "Beginner", "total_attempts_before_pass": 1, "is_pass": 0,
         "is_complete": 1, "candidate_source": "Internal"},
        {"assessment_taker_id": "t006", "candidatename": "Frank Adu", "email": "frank@external.com",
         "email_domain": "external.com", "organization_id": "org-02", "organization_name": "Beta Corp",
         "assessment_id": "a003", "test_id": "test-003",
         "test_title": "Promotion Review", "duration_min": 15.0, "score_pct": 29.0, "pass_status": "failed",
         "attempt_number": 1, "load_date": "2026-02-10", "attempt_month": "2026-02",
         "test_difficulty": "hard", "domain_name": "Engineering", "category_name": "Leadership",
         "proficiency_level": "Beginner", "total_attempts_before_pass": 1, "is_pass": 0,
         "is_complete": 0, "candidate_source": "External"},
    ]
    return pd.DataFrame(rows)


def demo_quality_violations() -> pd.DataFrame:
    """Mirrors trainer_quality_violations view output."""
    rows = [
        {"test_id": "test-001", "test_title": "Python Fundamentals", "number_of_questions_failed": 3,
         "test_window_violation_count": 2, "test_window_violation_duration": 120.0,
         "result_status": "completed", "load_date": "2026-05-01",
         "test_difficulty": "medium", "domain_name": "Engineering",
         "violation_severity_slice": "Low Violations"},
        {"test_id": "test-002", "test_title": "SQL Readiness", "number_of_questions_failed": 1,
         "test_window_violation_count": 0, "test_window_violation_duration": 0.0,
         "result_status": "completed", "load_date": "2026-04-10",
         "test_difficulty": "easy", "domain_name": "Data",
         "violation_severity_slice": "No Violations"},
        {"test_id": "test-003", "test_title": "Promotion Review", "number_of_questions_failed": 7,
         "test_window_violation_count": 9, "test_window_violation_duration": 540.0,
         "result_status": "completed", "load_date": "2026-03-15",
         "test_difficulty": "hard", "domain_name": "Engineering",
         "violation_severity_slice": "High Violations"},
        {"test_id": "test-001", "test_title": "Python Fundamentals", "number_of_questions_failed": 0,
         "test_window_violation_count": 1, "test_window_violation_duration": 45.0,
         "result_status": "completed", "load_date": "2026-05-15",
         "test_difficulty": "medium", "domain_name": "Engineering",
         "violation_severity_slice": "Low Violations"},
    ]
    return pd.DataFrame(rows)


def demo_executive_trainer_kpis() -> pd.DataFrame:
    """Mirrors executive_trainer_kpis view output."""
    rows = [
        {"trainer_id": "trainer-001", "total_questions_created": 45, "active_questions": 38,
         "avg_calibration_score": 82.4, "live_questions": 38,
         "hard_questions_created": 12, "medium_questions_created": 21, "easy_questions_created": 12},
        {"trainer_id": "trainer-002", "total_questions_created": 31, "active_questions": 28,
         "avg_calibration_score": 76.1, "live_questions": 28,
         "hard_questions_created": 5, "medium_questions_created": 14, "easy_questions_created": 12},
        {"trainer_id": "trainer-003", "total_questions_created": 67, "active_questions": 60,
         "avg_calibration_score": 88.9, "live_questions": 60,
         "hard_questions_created": 20, "medium_questions_created": 30, "easy_questions_created": 17},
        {"trainer_id": "trainer-004", "total_questions_created": 22, "active_questions": 18,
         "avg_calibration_score": 71.3, "live_questions": 18,
         "hard_questions_created": 3, "medium_questions_created": 9, "easy_questions_created": 10},
    ]
    return pd.DataFrame(rows)


def demo_senior_analytics() -> pd.DataFrame:
    """Mirrors senior_analytics_insights view output."""
    rows = [
        {"assessment_taker_id": "t001", "test_id": "test-001", "test_title": "Python Fundamentals",
         "integrity_risk_score": 1.0, "completion_funnel_pct": 0.95, "integrity_label": "Low Risk",
         "load_date": "2026-05-01"},
        {"assessment_taker_id": "t002", "test_id": "test-002", "test_title": "SQL Readiness",
         "integrity_risk_score": 0.0, "completion_funnel_pct": 1.0, "integrity_label": "Low Risk",
         "load_date": "2026-04-10"},
        {"assessment_taker_id": "t003", "test_id": "test-001", "test_title": "Python Fundamentals",
         "integrity_risk_score": 6.5, "completion_funnel_pct": 0.82, "integrity_label": "Medium Risk",
         "load_date": "2026-04-20"},
        {"assessment_taker_id": "t004", "test_id": "test-003", "test_title": "Promotion Review",
         "integrity_risk_score": 0.0, "completion_funnel_pct": 0.90, "integrity_label": "Low Risk",
         "load_date": "2026-03-15"},
        {"assessment_taker_id": "t005", "test_id": "test-002", "test_title": "SQL Readiness",
         "integrity_risk_score": 4.2, "completion_funnel_pct": 0.70, "integrity_label": "Low Risk",
         "load_date": "2026-03-20"},
        {"assessment_taker_id": "t006", "test_id": "test-003", "test_title": "Promotion Review",
         "integrity_risk_score": 22.0, "completion_funnel_pct": 0.50, "integrity_label": "High Risk",
         "load_date": "2026-02-10"},
    ]
    return pd.DataFrame(rows)


def demo_candidate_growth() -> pd.DataFrame:
    """Mirrors candidate_growth_tracking view output."""
    rows = [
        {"assessment_taker_id": "t001", "candidatename": "Alice Mensah", "test_id": "test-001",
         "test_title": "Python Fundamentals", "attempt_number": 1, "score_pct": 86.0,
         "load_date": "2026-05-01", "previous_score": None, "score_improvement": None},
        {"assessment_taker_id": "t001", "candidatename": "Alice Mensah", "test_id": "test-001",
         "test_title": "Python Fundamentals", "attempt_number": 2, "score_pct": 91.0,
         "load_date": "2026-05-15", "previous_score": 86.0, "score_improvement": 5.0},
        {"assessment_taker_id": "t003", "candidatename": "Carol Boateng", "test_id": "test-001",
         "test_title": "Python Fundamentals", "attempt_number": 1, "score_pct": 38.0,
         "load_date": "2026-04-20", "previous_score": None, "score_improvement": None},
        {"assessment_taker_id": "t003", "candidatename": "Carol Boateng", "test_id": "test-001",
         "test_title": "Python Fundamentals", "attempt_number": 2, "score_pct": 55.0,
         "load_date": "2026-05-05", "previous_score": 38.0, "score_improvement": 17.0},
    ]
    return pd.DataFrame(rows)


def demo_data_freshness() -> pd.DataFrame:
    """Mirrors gold_data_freshness view output."""
    rows = [
        {"table_name": "test_creation_assessmenttaker", "last_updated": "2026-05-31"},
        {"table_name": "test_execution_testresult", "last_updated": "2026-05-31"},
        {"table_name": "test_creation_question", "last_updated": "2026-05-30"},
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Legacy demo data kept for backward compatibility
# ---------------------------------------------------------------------------

def demo_assessment_summary() -> pd.DataFrame:
    return pd.DataFrame([
        {"assessment_id": "a001", "assessment_title": "Python Fundamentals", "organization_id": "demo-org",
         "status": "active", "duration_minutes": 30, "total_takers": 42, "started_takers": 40,
         "completed_takers": 33, "completion_rate_pct": 78.6, "graded_attempts": 58,
         "average_score": 76.2, "average_percentage": 76.2, "pass_rate_pct": 69.0,
         "average_duration_minutes": 27.4, "max_duration_minutes": 30.0, "violation_count": 5,
         "question_flag_count": 3},
        {"assessment_id": "a002", "assessment_title": "SQL Readiness", "organization_id": "demo-org",
         "status": "active", "duration_minutes": 30, "total_takers": 31, "started_takers": 30,
         "completed_takers": 28, "completion_rate_pct": 90.3, "graded_attempts": 44,
         "average_score": 82.8, "average_percentage": 82.8, "pass_rate_pct": 83.9,
         "average_duration_minutes": 29.2, "max_duration_minutes": 30.0, "violation_count": 2,
         "question_flag_count": 1},
        {"assessment_id": "a003", "assessment_title": "Promotion Review", "organization_id": "demo-org",
         "status": "active", "duration_minutes": 30, "total_takers": 18, "started_takers": 18,
         "completed_takers": 15, "completion_rate_pct": 83.3, "graded_attempts": 23,
         "average_score": 71.1, "average_percentage": 71.1, "pass_rate_pct": 61.1,
         "average_duration_minutes": 24.8, "max_duration_minutes": 30.0, "violation_count": 1,
         "question_flag_count": 2},
    ])


def demo_taker_activity() -> pd.DataFrame:
    return demo_candidate_performance()
