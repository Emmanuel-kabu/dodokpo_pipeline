"""Silver Lambda: read the latest bronze snapshot for one (database, table)
and write a cleaned copy to the silver bucket."""

import logging
import os

from reader import BronzeReader
from writer import SilverWriter
from transforms import clean

logger = logging.getLogger()
logger.setLevel(logging.INFO)

BRONZE_BUCKET = os.environ["BRONZE_BUCKET"]
SILVER_BUCKET = os.environ["SILVER_BUCKET"]


def lambda_handler(event, context):
    """
    Expected event shape (from Step Functions Map iterator):
      { "database": "dodokpo_test_creation_staging", "table": "Assessment" }
    """
    database = event["database"]
    table = event["table"]
    logger.info("Silver starting for %s/%s", database, table)

    reader = BronzeReader(BRONZE_BUCKET)
    writer = SilverWriter(SILVER_BUCKET)

    load_date, df = reader.read_latest(database, table)
    df = clean(df, database, table)

    s3_key = writer.write(df, database, table, load_date)
    logger.info("Silver complete: %s/%s load_date=%s rows=%d -> s3://%s/%s",
                database, table, load_date, len(df), SILVER_BUCKET, s3_key)

    return {
        "database": database,
        "table": table,
        "load_date": load_date,
        "rows": len(df),
        "s3_key": s3_key,
    }
