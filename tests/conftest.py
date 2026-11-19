"""Synthetic wear database shaped like the DataString sheet of the original workbook."""

import math

import pandas as pd
import pytest

from bcsg_compare import load_database

METRICS = ["Riser Wear", "Bearing Wear", "Average Wear", "Positive Wear", "Negative Wear"]

# (test id, grade, notes, segments without data)
ROWS = [
    ("16-01", "T479", None, ()),
    ("16-02", "T-479", None, ()),
    ("23-13", "ASG4", "825Kwh Rerun", (4, 5)),
    ("23-13", "ASG4", "825Kwh", (4, 5)),
    ("25-09", "ASG4", "Q2-DC Diagonal", (4, 5)),
    ("25-12", "ASG4", "Q3-DC", (4, 5)),
    ("26-01", "ASG4", "Q1-DC", (4, 5, 7, 8)),
]


def value(row: int, seg: int, metric: int) -> float:
    return 100.0 * (row + 1) + 10.0 * seg + metric


def make_frame() -> pd.DataFrame:
    records = []
    for r, (tid, grade, notes, missing) in enumerate(ROWS):
        rec = {"Test Set Number": tid, "Brush Grade": grade}
        for seg in range(1, 9):
            for m, metric in enumerate(METRICS):
                rec[f"Segment {seg} {metric}"] = math.nan if seg in missing else value(r, seg, m)
        rec["Notes"] = notes
        records.append(rec)
    return pd.DataFrame(records)


@pytest.fixture
def workbook(tmp_path):
    path = tmp_path / "data.xlsx"
    with pd.ExcelWriter(path) as xl:
        pd.DataFrame({"x": [1]}).to_excel(xl, sheet_name="Report", index=False)
        make_frame().to_excel(xl, sheet_name="DataString", index=False)
    return path


@pytest.fixture
def db(workbook):
    return load_database(workbook)
