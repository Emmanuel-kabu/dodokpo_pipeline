"""Gold Lambda: reshape and apply business logic on silver data, write to gold layer."""

import logging
import os

import boto3

from reader import S3Reader
from writer import S3Writer
from transforms import transform

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SILVER_BUCKET = os.environ["SILVER_BUCKET"]
GOLD_BUCKET = os.environ["GOLD_BUCKET"]
DEFAULT_DATASETS = [
    "test_creation_category",
    "test_creation_assessment_taker",
    "test_creation_domain",
    "test_execution_questionflag",
    "test_execution_testresult",
    "test_creation_test",
    "test_creation_question",
    "test_creation_assessment",
    "test_creation_skill",
]


def lambda_handler(event, context):
    """
    Expected event shape:
      { "dataset": "test_creation_test" }
    or
      { "datasets": ["test_creation_test", "test_creation_question"] }

    Each gold dataset may read from multiple silver tables.
    """
    datasets = event.get("datasets")
    if datasets is None:
        dataset = event.get("dataset")
        datasets = [dataset] if dataset else DEFAULT_DATASETS

    logger.info("Gold transform starting for datasets: %s", ", ".join(datasets))

    reader = S3Reader(SILVER_BUCKET)
    writer = S3Writer(GOLD_BUCKET)

    results = []
    for dataset in datasets:
        logger.info("Gold transform starting for dataset: %s", dataset)
        try:
            out_key = transform(dataset, reader, writer)
            logger.info("Gold transform complete for %s -> %s", dataset, out_key)
            results.append({"dataset": dataset, "s3_key": out_key, "status": "success"})
        except Exception as e:
            logger.error("Failed to transform %s: %s", dataset, str(e))
            results.append({"dataset": dataset, "error": str(e), "status": "failed"})

    return {"results": results}
