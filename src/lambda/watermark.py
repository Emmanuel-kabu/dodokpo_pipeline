"""SSM Parameter Store helpers for per-table watermark state."""

import logging

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class Watermark:
    def __init__(self, ssm_prefix: str):
        self._prefix = ssm_prefix.rstrip("/")
        self._ssm = boto3.client("ssm")

    def _param_name(self, table: str) -> str:
        return f"{self._prefix}/{table}"

    def get(self, table: str) -> str | None:
        try:
            response = self._ssm.get_parameter(Name=self._param_name(table))
            return response["Parameter"]["Value"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "ParameterNotFound":
                logger.info("No watermark found for %s — full extract will run.", table)
                return None
            raise

    def set(self, table: str, value: str):
        self._ssm.put_parameter(
            Name=self._param_name(table),
            Value=value,
            Type="String",
            Overwrite=True,
        )
        logger.info("Watermark updated for %s -> %s", table, value)
