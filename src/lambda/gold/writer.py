"""Writes Parquet files to S3 for transformation Lambdas."""

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

    def write_parquet(self, df: pd.DataFrame, database: str, table: str, load_date: str = None) -> str:
        """
        Writes df to s3://<bucket>/<database>/<table>/load_date=<load_date>/<timestamp>.parquet
        Returns the S3 key.
        """
        if load_date is None:
            load_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        timestamp = datetime.now(timezone.utc).strftime("%H%M%S")
        key = f"{database}/{table}/load_date={load_date}/{timestamp}.parquet"

        buffer = io.BytesIO()
        df.to_parquet(buffer, engine="pyarrow", compression="snappy", index=False)
        buffer.seek(0)

        self._s3.put_object(Bucket=self._bucket, Key=key, Body=buffer.getvalue())
        logger.info("Written %d rows to s3://%s/%s", len(df), self._bucket, key)
        return key
