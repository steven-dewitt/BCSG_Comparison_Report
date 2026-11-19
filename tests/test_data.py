import math

import pandas as pd
import pytest

from bcsg_compare import DataFormatError, load_database
from bcsg_compare.data import natural_key, normalize_grade

from .conftest import METRICS, make_frame, value


def test_reads_datastring_sheet_and_discovers_layout(db):
    assert db.metrics == METRICS
    assert db.segments == list(range(1, 9))
    assert len(db.labels) == 7


def test_repeated_ids_get_unique_labels(db):
    assert "23-13 (1)" in db.labels and "23-13 (2)" in db.labels
    assert "23-13" not in db.labels
    assert db.catalog.at["23-13 (2)", "notes"] == "825Kwh"
    assert db.duplicate_ids == ["23-13"]


def test_missing_values_stay_nan_not_zero(db):
    assert math.isnan(db.values.at["26-01", ("Riser Wear", 7)])
    assert db.values.at["26-01", ("Bearing Wear", 2)] == value(6, 2, 1)


def test_segments_with_data(db):
    counts = db.segments_with_data(db.labels)
    assert counts["16-01"] == 8 and counts["25-09"] == 6 and counts["26-01"] == 4


def test_csv_input(tmp_path):
    path = tmp_path / "data.csv"
    make_frame().to_csv(path, index=False)
    db = load_database(path)
    assert db.labels[0] == "16-01" and len(db.labels) == 7


def test_extra_segments_and_metrics_are_picked_up(tmp_path):
    frame = make_frame()
    frame["Segment 9 Riser Wear"] = 1.0
    frame["Segment 1 Edge Chipping"] = 2.0
    path = tmp_path / "data.csv"
    frame.to_csv(path, index=False)
    db = load_database(path)
    assert db.segments[-1] == 9
    assert db.metrics[-1] == "Edge Chipping"
    assert math.isnan(db.values.at["16-01", ("Edge Chipping", 2)])


def test_bad_file_raises(tmp_path):
    path = tmp_path / "bad.csv"
    pd.DataFrame({"foo": [1]}).to_csv(path, index=False)
    with pytest.raises(DataFormatError):
        load_database(path)
    other = tmp_path / "x.json"
    other.write_text("{}")
    with pytest.raises(DataFormatError, match="Unsupported"):
        load_database(other)
    with pytest.raises(FileNotFoundError):
        load_database(tmp_path / "missing.xlsx")


def test_missing_sheet(workbook):
    with pytest.raises(DataFormatError, match="Sheets"):
        load_database(workbook, sheet="Nope")


def test_helpers():
    assert normalize_grade("T-479") == normalize_grade("t479")
    assert sorted(["23-10", "23-9", "23-09-2"], key=natural_key) == ["23-9", "23-09-2", "23-10"]
