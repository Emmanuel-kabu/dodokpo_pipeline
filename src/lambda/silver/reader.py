"""Reads the latest bronze snapshot for a given (database, table) pair.

Bronze layout (produced by the platform engineer's export job):
    raw/<database>/<Table>/load_date=YYYY-MM-DD/part-<hash>.snappy.parquet
"""

import io
import logging
import re

import boto3
import pandas as pd

logger = logging.getLogger(__name__)

_LOAD_DATE_RE = re.compile(r"load_date=(\d{4}-\d{2}-\d{2})/")


class BronzeReader:
    def __init__(self, bucket: str):
        self._bucket = bucket
        self._s3 = boto3.client("s3")

    def read_latest(self, database: str, table: str) -> tuple[str, pd.DataFrame]:
        """
        List all load_date partitions under raw/<database>/<table>/, pick the
        max, and concat every part-*.parquet inside it. Returns the load_date
        and the combined DataFrame.
        """
        prefix = f"raw/{database}/{table}/"
        load_dates = self._list_load_dates(prefix)
        if not load_dates:
            raise FileNotFoundError(f"No load_date partitions under s3://{self._bucket}/{prefix}")

        latest = max(load_dates)
        partition_prefix = f"{prefix}load_date={latest}/"
        keys = self._list_parquet_keys(partition_prefix)
        if not keys:
            raise FileNotFoundError(f"Partition exists but no parquet files: s3://{self._bucket}/{partition_prefix}")

        frames = [self._read_parquet(k) for k in keys]
        df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
        logger.info(
            "Loaded %d rows from %s/%s load_date=%s (%d part files)",
            len(df), database, table, latest, len(keys),
        )
        return latest, df

    def _list_load_dates(self, prefix: str) -> list[str]:
        paginator = self._s3.get_paginator("list_objects_v2")
        dates = set()
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix, Delimiter="/"):
            for cp in page.get("CommonPrefixes", []):
                m = _LOAD_DATE_RE.search(cp["Prefix"])
                if m:
                    dates.add(m.group(1))
        return sorted(dates)

    def _list_parquet_keys(self, prefix: str) -> list[str]:
        paginator = self._s3.get_paginator("list_objects_v2")
        return [
            obj["Key"]
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix)
            for obj in page.get("Contents", [])
            if obj["Key"].endswith(".parquet")
        ]

    def _read_parquet(self, key: str) -> pd.DataFrame:
        response = self._s3.get_object(Bucket=self._bucket, Key=key)
        return pd.read_parquet(io.BytesIO(response["Body"].read()), engine="pyarrow")
