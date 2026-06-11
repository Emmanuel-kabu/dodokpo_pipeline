"""Deploy all Athena SQL views to dodokpo_dev_gold.

Usage:
    python infra/sql/deploy_views.py

Requires AWS credentials with athena:StartQueryExecution and s3:PutObject on
the Athena results bucket.
"""

import re
import sys
import time
from pathlib import Path

import boto3

REGION          = "eu-west-1"
DATABASE        = "dodokpo_dev_gold"
WORKGROUP       = "dodokpo-dev-workgroup"
RESULTS_BUCKET  = "dodokpo-dev-athena-results"
SQL_FILE        = Path(__file__).parent / "trainer_executive_metrics_views.sql"


def _split_statements(sql: str) -> list[str]:
    """Split SQL file into individual CREATE VIEW statements."""
    # Strip comments that start with --
    cleaned = re.sub(r"--[^\n]*", "", sql)
    parts = re.split(r";\s*", cleaned, flags=re.IGNORECASE)
    return [p.strip() for p in parts if re.search(r"CREATE\s+OR\s+REPLACE\s+VIEW", p, re.IGNORECASE)]


def _run(client, sql: str, label: str) -> None:
    resp = client.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": DATABASE},
        ResultConfiguration={"OutputLocation": f"s3://{RESULTS_BUCKET}/view-deploy/"},
        WorkGroup=WORKGROUP,
    )
    qid = resp["QueryExecutionId"]
    print(f"  submitted {label} -> {qid}", flush=True)

    for _ in range(60):
        status = client.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        state = status["State"]
        if state == "SUCCEEDED":
            print(f"  OK {label}", flush=True)
            return
        if state in ("FAILED", "CANCELLED"):
            reason = status.get("StateChangeReason", "")
            print(f"  FAIL {label}: {state} - {reason}", file=sys.stderr, flush=True)
            sys.exit(1)
        time.sleep(1)

    print(f"  FAIL {label}: timed out after 60s", file=sys.stderr, flush=True)
    sys.exit(1)


def main() -> None:
    sql = SQL_FILE.read_text(encoding="utf-8")
    statements = _split_statements(sql)
    print(f"Found {len(statements)} view(s) to deploy to {DATABASE}\n")

    client = boto3.client("athena", region_name=REGION)

    for stmt in statements:
        # Extract view name for logging
        m = re.search(r"VIEW\s+(\S+)\s+AS", stmt, re.IGNORECASE)
        name = m.group(1) if m else "unknown"
        print(f"Deploying {name} …")
        _run(client, stmt, name)

    print(f"\nAll {len(statements)} views deployed successfully.")


if __name__ == "__main__":
    main()
