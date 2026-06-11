"""Lambda entry point for incremental table sync: RDS -> S3 Parquet."""

import logging
import os

from db_connection import DbConnection
from extraction import DbExtraction
from s3_writer import S3Writer
from watermark import Watermark

logger = logging.getLogger()
logger.setLevel(logging.INFO)

BRONZE_BUCKET = os.environ["BRONZE_BUCKET"]
DB_SECRET_ARN = os.environ["DB_SECRET_ARN"]
SSM_PREFIX = os.environ["SSM_PREFIX"]


def lambda_handler(event, context):
    """
    Expected event shape (from Step Functions Map iterator):
      { "table": "assessment" }
    """
    table = event["table"]
    logger.info("Starting sync for table: %s", table)

    watermark = Watermark(SSM_PREFIX)
    last_updated_at = watermark.get(table)

    db = DbConnection(DB_SECRET_ARN)
    extractor = DbExtraction(db)
    writer = S3Writer(BRONZE_BUCKET)

    try:
        df, new_watermark = extractor.extract_incremental(table, last_updated_at)

        if df.empty:
            logger.info("No new rows for %s since %s", table, last_updated_at)
            return {"table": table, "rows_synced": 0}

        s3_key = writer.write_parquet(df, table)
        watermark.set(table, new_watermark)

        logger.info("Synced %d rows for %s -> s3://%s/%s", len(df), table, BRONZE_BUCKET, s3_key)
        return {"table": table, "rows_synced": len(df), "s3_key": s3_key}

    finally:
        db.close()
