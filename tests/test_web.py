"""Browser tests for BCSG_Comparison.html (skipped when Node + Playwright are unavailable).

The page is driven in headless Chromium and its results are checked against the
Python implementation, including a cell-by-cell comparison of the Excel exports.
"""

import csv
import json
import math
import shutil
import subprocess
from pathlib import Path

import openpyxl
import pytest

from bcsg_compare import build_comparison
from bcsg_compare.excel_report import write_excel_report

from .conftest import make_frame

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "BCSG_Comparison.html"
DRIVER = Path(__file__).parent / "web" / "driver.cjs"


def _playwright_available() -> bool:
    if not shutil.which("node"):
        return False
    probe = subprocess.run(["node", "-e", "require('playwright')"], capture_output=True)
    return probe.returncode == 0


pytestmark = pytest.mark.skipif(not _playwright_available(), reason="needs node with playwright")


def drive(data: Path, out: Path, search: str, baseline: str = "") -> dict:
    proc = subprocess.run(["node", str(DRIVER), str(HTML), str(data), str(out), search, baseline],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["errors"] == []
    return result


def assert_same_workbook(expected: Path, actual: Path) -> None:
    for data_only in (False, True):
        a = openpyxl.load_workbook(expected, data_only=data_only)
        b = openpyxl.load_workbook(actual, data_only=data_only)
        assert a.sheetnames == b.sheetnames
        for name in a.sheetnames:
            wa, wb = a[name], b[name]
            for r in range(1, max(wa.max_row, wb.max_row) + 1):
                if name == "Summary" and r == 2:  # "Generated <time>" line
                    continue
                for c in range(1, max(wa.max_column, wb.max_column) + 1):
                    x, y = wa.cell(r, c).value, wb.cell(r, c).value
                    if isinstance(x, float) and isinstance(y, (int, float)):
                        assert math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-9), (name, r, c, x, y)
                    elif x not in (None, "") or y not in (None, ""):
                        assert x == y, (name, wa.cell(r, c).coordinate, x, y)
            if not data_only:
                assert len(wa.conditional_formatting) == len(wb.conditional_formatting), name
                assert wa.freeze_panes == wb.freeze_panes, name
                assert wa.auto_filter.ref == wb.auto_filter.ref, name
    assert len(openpyxl.load_workbook(actual)["Summary"]._charts) == 5


def test_browser_matches_python(workbook, db, tmp_path):
    result = drive(workbook, tmp_path, "26-01 25-09 23-13", baseline="25-09")
    # typed order is kept, and a repeated ID adds every run
    assert result["selected"] == ["26-01", "25-09", "23-13 (1)", "23-13 (2)"]
    assert result["afterReload"] == result["selected"]
    assert result["svgCount"] == 5
    assert "% difference vs baseline 25-09" in result["headings"]

    cmp = build_comparison(db, result["selected"], baseline="25-09")
    summary = cmp.summary()
    for row in result["summary"][: len(cmp.labels)]:
        label, mean = row[1], float(row[5].replace(",", ""))
        assert mean == round(summary.at[label, "Riser Wear mean"])

    expected = write_excel_report(cmp, tmp_path / "expected.xlsx")
    assert_same_workbook(expected, Path(result["exportXlsx"]))

    with open(result["exportCsv"], encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == int(sum(cmp.table(m).notna().sum().sum() for m in cmp.metrics))
    html = Path(result["exportHtml"]).read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>") and html.count("<svg") == 5


def test_browser_reads_csv(tmp_path):
    path = tmp_path / "data.csv"
    make_frame().to_csv(path, index=False)
    result = drive(path, tmp_path, "16-*")
    assert result["selected"] == ["16-01", "16-02"]
    assert "7 tests" in result["status"]


def test_browser_reports_bad_file(tmp_path):
    path = tmp_path / "bad.xlsx"
    path.write_bytes(b"not a workbook")
    proc = subprocess.run(["node", str(DRIVER), str(HTML), str(path), str(tmp_path), "x"],
                          capture_output=True, text=True, timeout=120)
    assert "not an .xlsx/.xlsm workbook" in json.loads(proc.stdout)["loadError"]
