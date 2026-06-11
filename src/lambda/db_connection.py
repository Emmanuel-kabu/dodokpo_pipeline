"""RDS connection management for the bronze sync Lambda.

Pulls credentials from Secrets Manager (JSON keys: host, port, username,
password, dbname) and opens a read-only psycopg2 connection.
"""

import json
import logging

import boto3
import psycopg2

logger = logging.getLogger(__name__)


class DbConnection:
    def __init__(self, secret_arn: str):
        creds = self._fetch_creds(secret_arn)
        self._conn = psycopg2.connect(
            host=creds["host"],
            port=int(creds.get("port", 5432)),
            user=creds["username"],
            password=creds["password"],
            dbname=creds["dbname"],
            connect_timeout=10,
        )
        self._conn.set_session(readonly=True, autocommit=True)
        logger.info(
            "Connected to %s:%s/%s as %s (read-only)",
            creds["host"], creds.get("port", 5432), creds["dbname"], creds["username"],
        )

    @staticmethod
    def _fetch_creds(secret_arn: str) -> dict:
        client = boto3.client("secretsmanager")
        response = client.get_secret_value(SecretId=secret_arn)
        return json.loads(response["SecretString"])

    @property
    def conn(self):
        return self._conn

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()
            logger.info("DB connection closed.")
