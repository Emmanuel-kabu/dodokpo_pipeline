"""Incremental extraction from RDS into pandas DataFrames.

Assumes every source table exposes an `updated_at` timestamp column used as
the watermark. If the source schema diverges, this module needs a per-table
column-name mapping.
"""

import logging
import re
from typing import Tuple

import pandas as pd
from psycopg2 import sql

logger = logging.getLogger(__name__)

WATERMARK_COLUMN = "updated_at"
_TABLE_NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class DbExtraction:
    def __init__(self, db):
        self._db = db

    def extract_incremental(
        self, table: str, last_updated_at: str | None
    ) -> Tuple[pd.DataFrame, str | None]:
        """
        Read rows from `table` where updated_at > last_updated_at (or all rows
        when no watermark exists). Returns the DataFrame and the new watermark
        (max updated_at in the batch). If the batch is empty, returns the
        previous watermark unchanged.
        """
        if not _TABLE_NAME_PATTERN.match(table):
            raise ValueError(f"Invalid table name: {table!r}")

        if last_updated_at:
            query = sql.SQL(
                "SELECT * FROM {table} WHERE {col} > %s ORDER BY {col}"
            ).format(
                table=sql.Identifier(table),
                col=sql.Identifier(WATERMARK_COLUMN),
            )
            params: tuple = (last_updated_at,)
            logger.info("Incremental extract for %s since %s", table, last_updated_at)
        else:
            query = sql.SQL("SELECT * FROM {table} ORDER BY {col}").format(
                table=sql.Identifier(table),
                col=sql.Identifier(WATERMARK_COLUMN),
            )
            params = ()
            logger.info("Full extract for %s (no watermark yet)", table)

        with self._db.conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]

        df = pd.DataFrame(rows, columns=columns)

        if df.empty:
            return df, last_updated_at

        new_watermark = pd.Timestamp(df[WATERMARK_COLUMN].max()).isoformat()
        return df, new_watermark
