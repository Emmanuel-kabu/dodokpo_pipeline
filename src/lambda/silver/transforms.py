"""Silver cleaning transforms — pass-through for now.

Each table can have its own cleaning function registered in the dispatch
dict below. Until rules are written, every table goes through
`_passthrough`, which returns the bronze DataFrame unchanged. This keeps
the pipeline flowing while you decide per-table rules.
"""

import pandas as pd


def clean(df: pd.DataFrame, database: str, table: str) -> pd.DataFrame:
    """Dispatch to the registered cleaning function for (database, table),
    falling back to a pass-through if no rule is registered yet."""
    fn = _DISPATCH.get((database, table), _passthrough)
    return fn(df)


def _passthrough(df: pd.DataFrame) -> pd.DataFrame:
    return df


# Register per-(database, table) cleaning functions here as rules are agreed:
#   _DISPATCH[("dodokpo_test_creation_staging", "Assessment")] = clean_assessment
#
# Example function signature:
#   def clean_assessment(df: pd.DataFrame) -> pd.DataFrame:
#       df["title"] = df["title"].str.strip()
#       return df
_DISPATCH: dict = {}
