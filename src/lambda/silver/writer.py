"""Writes a cleaned DataFrame to the silver bucket, mirroring the bronze layout.

Output layout:
    <database>/<Table>/load_date=YYYY-MM-DD/part-<HHMMSS>.snappy.parquet
"""

import io
import logging
from datetime import datetime, timezone

import boto3
import pandas as pd

logger = logging.getLogger(__name__)


class SilverWriter:
    def __init__(self, bucket: str):
        self._bucket = bucket
        self._s3 = boto3.client("s3")

    def write(self, df: pd.DataFrame, database: str, table: str, load_date: str) -> str:
        """
        Writes df to s3://<silver-bucket>/<database>/<table>/load_date=<load_date>/part-<HHMMSS>.snappy.parquet
        Returns the S3 key.
        """
        timestamp = datetime.now(timezone.utc).strftime("%H%M%S")
        key = f"{database}/{table}/load_date={load_date}/part-{timestamp}.snappy.parquet"

        buffer = io.BytesIO()
        df.to_parquet(buffer, engine="pyarrow", compression="snappy", index=False)
        buffer.seek(0)

        self._s3.put_object(Bucket=self._bucket, Key=key, Body=buffer.getvalue())
        logger.info("Wrote %d rows to s3://%s/%s", len(df), self._bucket, key)
        return key
