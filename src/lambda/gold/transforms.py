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
        # columns to drop
        columnns_to_drop = ["description", "organiizationid", "createdat", "updatedat", "system"]

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
        columns_to_drop = ["showresults", "showclock", "conductsurvey",
                           "commencedate", "expirydate", "assessmentlink", "starttime",
                           "endtime", "invalid", "proctor", 
                           "estimatedendtime", "genericid", "screenshotsinterval", 
                           "camerashotsinterval", "dispatcher", "submissiontype", "dispatchid",
                           "reportcallbackurl", "originalassessmenttakerid","createdat", "updatedat",
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
        # Dropping unwanted columns 
        columns_to_drop = ["organizationid", "system", "createdat", "updatedat", "load_date"]
        load_date, df = self.reader.read_latest("dodokpo_test_creation_staging", "Domain")
        for unwanted_column in columns_to_drop:
            if unwanted_column in df.columns:
                df.drop(columns=[unwanted_column], inplace=True)

        # write the transformed data to the gold layer
        return self.writer.write_parquet(df, "dodokpo_test_creation_staging", "Domain", load_date)

    def transform_test_execution_questionflag(self):
        # transforming test execution question flag 
        # Dropping unwanted columns 
        columns_to_drop = ["organizationid", "createdat", "updatedat", "load_date", 
                           "questiontext", "organizationid" ]
        load_date, df = self.reader.read_latest("dodokpo_test_execution_staging", "QuestionFlag")
        for unwanted_column in columns_to_drop:
            if unwanted_column in df.columns:
                df.drop(columns=[unwanted_column], inplace=True)

        # write the transformed data to the gold layer
        return self.writer.write_parquet(df, "dodokpo_test_execution_staging", "QuestionFlag", load_date)

    def transform_test_execution_testresult(self):
        # transforming test execution test result 
        # Dropping unwanted columns 
        columns_to_drop = ["organizationid", "createdat", "updatedat", "order", "finishtime", "starttime","testwindowviolationduration",
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
        # Dropping unwanted columns 
        columns_to_drop = ["organizationid", "system", "description", "instructions", "passage", 
                           "createdat", "updatedat", "hash", "archivedat", "archivedby", "load_date"]
        
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
        # Dropping unwanted columns 
        columns_to_drop = ["organizationid", "system", "questiontext", "createdat", "updatedat", 
                           "hash", "archivedat", "archivedby", "load_date"]
        
        load_date, df = self.reader.read_latest("dodokpo_test_creation_staging", "Question")
        for unwanted_column in columns_to_drop:
            if unwanted_column in df.columns:
                df.drop(columns=[unwanted_column], inplace=True)

        # write the transformed data to the gold layer
        return self.writer.write_parquet(df, "dodokpo_test_creation_staging", "Question", load_date)

    def transform_test_creation_assessment(self):
        # transforming test creation assessment 
        # Dropping unwanted columns 
        columns_to_drop = ["organizationid", "system", "instructions", "createdat", "updatedat", 
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
        # Dropping unwanted columns 
        columns_to_drop = ["organizationid", "system", "description", "tags", "createdat", "updatedat", "load_date"]
        
        load_date, df = self.reader.read_latest("dodokpo_test_creation_staging", "Skill")
        for unwanted_column in columns_to_drop:
            if unwanted_column in df.columns:
                df.drop(columns=[unwanted_column], inplace=True)

        # write the transformed data to the gold layer
        return self.writer.write_parquet(df, "dodokpo", "test_creation_skill", load_date)

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
    }
    
    if dataset not in mapping:
        raise ValueError(f"Unknown gold dataset: {dataset}")
        
    return mapping[dataset]()
            
    