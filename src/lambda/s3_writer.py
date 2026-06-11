"""Writes a DataFrame to S3 as Parquet with Snappy compression, date-partitioned."""

import io
import logging
from datetime import datetime, timezone

import boto3
import pandas as pd

logger = logging.getLogger(__name__)


class S3Writer:
    def __init__(self, bucket: str):
        self._bucket = bucket
        self._s3 = boto3.client("s3")

    def write_parquet(self, df: pd.DataFrame, table: str) -> str:
        """
        Writes df to s3://<bucket>/table=<table>/date=<YYYY-MM-DD>/<timestamp>.parquet
        Returns the S3 key.
        """
        now = datetime.now(timezone.utc)
        key = f"table={table}/date={now.strftime('%Y-%m-%d')}/{now.strftime('%H%M%S')}.parquet"

        buffer = io.BytesIO()
        df.to_parquet(buffer, engine="pyarrow", compression="snappy", index=False)
        buffer.seek(0)

        self._s3.put_object(Bucket=self._bucket, Key=key, Body=buffer.getvalue())
        logger.info("Written %d rows to s3://%s/%s", len(df), self._bucket, key)
        return key
