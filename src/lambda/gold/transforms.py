"""Gold transforms — dashboard-ready analytical datasets."""


import re

import pandas as pd

from reader import S3Reader
from writer import S3Writer

class Transformation():
    def __init__(self, reader: S3Reader, writer: S3Writer):
        self.reader = reader
        self.writer = writer

    def transform_test_creation_category(self):
        # Implementation for transforming test creation category
        # columns to drop. NOTE: createdAt/updatedAt are intentionally KEPT for
        # time-based analytics (cohort-year derivation, trends).
        columnns_to_drop = ["description", "organiizationid", "system"]

        # read latest data from the silver layer
        load_date, df = self.reader.read_latest("dodokpo_test_creation_staging", "Category")
        for unwanted_column in columnns_to_drop:
            if unwanted_column in df.columns:
                df.drop(columns=[unwanted_column], inplace=True)

        # write the transformed data to the gold layer
        return self.writer.write_parquet(df, "dodokpo_test_creation_staging", "Category", load_date)

    def transform_test_creation_assessment_taker(self):
        # Columns to drop
        # NOTE: organizationid is intentionally KEPT (org-level slicing dimension).
        # createdAt/updatedAt KEPT (cohort-year + time analytics).
        # dispatchId KEPT (joins taker -> AssessmentDispatch for cohort/group tags).
        columns_to_drop = ["showresults", "showclock", "conductsurvey",
                           "commencedate", "expirydate", "assessmentlink", "starttime",
                           "endtime", "invalid", "proctor",
                           "estimatedendtime", "genericid", "screenshotsinterval",
                           "camerashotsinterval", "dispatcher", "submissiontype",
                           "reportcallbackurl", "originalassessmenttakerid",
                             "load_date" ]
        # droping unwated columns
        load_date, df = self.reader.read_latest("dodokpo_test_creation_staging", "AssessmentTaker")
        for unwanted_column in columns_to_drop:
            if unwanted_column in df.columns:
                df.drop(columns=[unwanted_column], inplace=True)

        # covert duration from seconds to minutes
        if "duration" in df.columns:
            df["duration"] = df["duration"] / 60

        # extract name from email
        if "email" in df.columns:
            df["candidatename"] = df["email"].str.split("@").str[0].str.replace(".", " ", regex=False).str.title()

        # write the transformed data to the gold layer
        return self.writer.write_parquet(df, "dodokpo_test_creation_staging", "AssessmentTaker", load_date)

    def transform_test_creation_domain(self):
        # transforming test domain
        # Dropping unwanted columns. createdAt/updatedAt KEPT for time analytics.
        columns_to_drop = ["organizationid", "system", "load_date"]
        load_date, df = self.reader.read_latest("dodokpo_test_creation_staging", "Domain")
        for unwanted_column in columns_to_drop:
            if unwanted_column in df.columns:
                df.drop(columns=[unwanted_column], inplace=True)

        # write the transformed data to the gold layer
        return self.writer.write_parquet(df, "dodokpo_test_creation_staging", "Domain", load_date)

    def transform_test_execution_questionflag(self):
        # transforming test execution question flag
        # Dropping unwanted columns. createdAt/updatedAt KEPT for time analytics.
        columns_to_drop = ["organizationid", "load_date",
                           "questiontext", "organizationid" ]
        load_date, df = self.reader.read_latest("dodokpo_test_execution_staging", "QuestionFlag")
        for unwanted_column in columns_to_drop:
            if unwanted_column in df.columns:
                df.drop(columns=[unwanted_column], inplace=True)

        # write the transformed data to the gold layer
        return self.writer.write_parquet(df, "dodokpo_test_execution_staging", "QuestionFlag", load_date)

    def transform_test_execution_testresult(self):
        # transforming test execution test result
        # Dropping unwanted columns. startTime/finishTime KEPT — they are the ONLY
        # time dimension on TestResult (needed for trends, growth, cohort-year).
        columns_to_drop = ["organizationid", "order", "testwindowviolationduration",
                           "testtakershotcount", "testwindowshotcount", "status", "draftintervalassessmenttakershots",
                           "draftintervaltestwindowshots", "organizationid", "status", "result"]

        load_date, df = self.reader.read_latest("dodokpo_test_execution_staging", "TestResult")
        for unwanted_column in columns_to_drop:
            if unwanted_column in df.columns:
                df.drop(columns=[unwanted_column], inplace=True)

        # converting duration from seconds to minutes
        if "duration" in df.columns:
            df["duration"] = df["duration"] / 60

        # write the transformed data to the gold layer
        return self.writer.write_parquet(df, "dodokpo_test_execution_staging", "TestResult", load_date)

    def transform_test_creation_test(self):
        # transforming test creation test
        # Dropping unwanted columns. createdAt/updatedAt KEPT for time analytics.
        columns_to_drop = ["organizationid", "system", "description", "instructions", "passage",
                           "hash", "archivedat", "archivedby", "load_date"]

        load_date, df = self.reader.read_latest("dodokpo_test_creation_staging", "Test")
        for unwanted_column in columns_to_drop:
            if unwanted_column in df.columns:
                df.drop(columns=[unwanted_column], inplace=True)

        # converting duration from seconds to minutes
        if "duration" in df.columns:
            df["duration"] = df["duration"] / 60

        # write the transformed data to the gold layer
        return self.writer.write_parquet(df, "dodokpo_test_creation_staging", "Test", load_date)

    def transform_test_creation_question(self):
        # transforming test creation question
        # Dropping unwanted columns. createdAt/updatedAt KEPT for time analytics.
        columns_to_drop = ["organizationid", "system", "questiontext",
                           "hash", "archivedat", "archivedby", "load_date"]

        load_date, df = self.reader.read_latest("dodokpo_test_creation_staging", "Question")
        for unwanted_column in columns_to_drop:
            if unwanted_column in df.columns:
                df.drop(columns=[unwanted_column], inplace=True)

        # write the transformed data to the gold layer
        return self.writer.write_parquet(df, "dodokpo_test_creation_staging", "Question", load_date)

    def transform_test_creation_assessment(self):
        # transforming test creation assessment
        # Dropping unwanted columns. createdAt/updatedAt + tags KEPT for analytics.
        columns_to_drop = ["organizationid", "system", "instructions",
                           "hash", "archivedat", "archivedby", "load_date"]

        load_date, df = self.reader.read_latest("dodokpo_test_creation_staging", "Assessment")
        for unwanted_column in columns_to_drop:
            if unwanted_column in df.columns:
                df.drop(columns=[unwanted_column], inplace=True)

        # converting duration from seconds to minutes
        if "duration" in df.columns:
            df["duration"] = df["duration"] / 60

        # write the transformed data to the gold layer
        return self.writer.write_parquet(df, "dodokpo_test_creation_staging", "Assessment", load_date)

    def transform_test_creation_skill(self):
        # transforming test creation skill
        # Dropping unwanted columns. createdAt/updatedAt KEPT for time analytics.
        columns_to_drop = ["organizationid", "system", "description", "tags", "load_date"]

        load_date, df = self.reader.read_latest("dodokpo_test_creation_staging", "Skill")
        for unwanted_column in columns_to_drop:
            if unwanted_column in df.columns:
                df.drop(columns=[unwanted_column], inplace=True)

        # write the transformed data to the gold layer
        # FIX: was writing to ("dodokpo", "test_creation_skill") which produced a
        # stray gold prefix/table. Align with the standard <database>/<Table> layout.
        return self.writer.write_parquet(df, "dodokpo_test_creation_staging", "Skill", load_date)

    def transform_test_creation_assessment_dispatch(self):
        # AssessmentDispatch — carries `tags` (the cohort/group signal) and dispatch
        # timing. KEEP tags, dispatch metadata, allowedEmailList, and createdAt/updatedAt
        # for cohort-year derivation. Drop proctoring/config noise.
        # NOTE: exact-case names so the drops actually fire on the camelCase columns.
        columns_to_drop = ["dispatcher", "screenshotsInterval", "camerashotsInterval",
                           "showResults", "conductSurvey", "showClock", "dispatchLink",
                           "reportCallbackURL", "retakeDelayHours", "recallReason",
                           "recalledAt", "recalledBy", "load_date"]

        load_date, df = self.reader.read_latest("dodokpo_test_creation_staging", "AssessmentDispatch")
        for unwanted_column in columns_to_drop:
            if unwanted_column in df.columns:
                df.drop(columns=[unwanted_column], inplace=True)

        # write the transformed data to the gold layer
        return self.writer.write_parquet(df, "dodokpo_test_creation_staging", "AssessmentDispatch", load_date)

def transform(dataset: str, reader: S3Reader, writer: S3Writer) -> str:
    """Orchestrates the gold transformation for a specific dataset."""
    t = Transformation(reader, writer)

    # Mapping dataset names to transformation methods
    # Note: Using generic names or specific ones depending on how they are triggered
    mapping = {
        "test_creation_category": t.transform_test_creation_category,
        "test_creation_assessment_taker": t.transform_test_creation_assessment_taker,
        "test_creation_domain": t.transform_test_creation_domain,
        "test_execution_questionflag": t.transform_test_execution_questionflag,
        "test_execution_testresult": t.transform_test_execution_testresult,
        "test_creation_test": t.transform_test_creation_test,
        "test_creation_question": t.transform_test_creation_question,
        "test_creation_assessment": t.transform_test_creation_assessment,
        "test_creation_skill": t.transform_test_creation_skill,
        "test_creation_assessment_dispatch": t.transform_test_creation_assessment_dispatch,
    }

    if dataset not in mapping:
        raise ValueError(f"Unknown gold dataset: {dataset}")

    return mapping[dataset]()

