import re

import openpyxl
import pytest

from bcsg_compare import build_comparison
from bcsg_compare.cli import main
from bcsg_compare.excel_report import write_excel_report
from bcsg_compare.html_report import write_html_report

from .conftest import METRICS


def _charts(path):
    import zipfile
    with zipfile.ZipFile(path) as z:
        return [z.read(n).decode() for n in z.namelist() if re.match(r"xl/charts/chart\d+\.xml", n)]


@pytest.mark.parametrize("group_by", ["segment", "test"])
def test_excel_report_structure(db, tmp_path, group_by):
    labels = ["25-09", "25-12", "26-01", "23-13 (1)"]
    cmp = build_comparison(db, labels, baseline="25-09", group_by=group_by)
    out = write_excel_report(cmp, tmp_path / "r.xlsx")
    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["Summary", *METRICS, "Data (long)", "Test Catalog"]

    ws = wb["Riser Wear"]
    assert [c.value for c in ws[4]][:8] == ["Test", "Grade", "Seg 1", "Seg 2", "Seg 3", "Seg 6", "Seg 7", "Seg 8"]
    assert ws["A5"].value == "25-09"
    assert ws["C5"].value == cmp.table("Riser Wear").loc["25-09", 1]
    assert ws["G7"].value is None  # 26-01 seg 7 is missing -> blank, not 0
    assert ws["I5"].value.startswith("=IF(COUNT(C5:H5)")

    charts = _charts(out)
    assert len(charts) == len(METRICS)
    n_series = len(labels) if group_by == "segment" else len(cmp.segments)
    assert all(c.count("<c:ser>") == n_series for c in charts)
    # "gap" is xlsxwriter's (and Excel's) default, so the element is omitted; it must not be "zero".
    assert not any('dispBlanksAs val="zero"' in c for c in charts)

    long_rows = wb["Data (long)"].max_row - 1
    assert long_rows == int(sum(cmp.table(m).notna().sum().sum() for m in METRICS))
    cat = wb["Test Catalog"]
    assert cat.max_row == len(db.labels) + 1


def test_excel_cached_values(db, tmp_path):
    cmp = build_comparison(db, ["25-09", "26-01"], baseline="25-09")
    out = write_excel_report(cmp, tmp_path / "r.xlsx")
    ws = openpyxl.load_workbook(out, data_only=True)["Summary"]
    assert ws["B7"].value == "25-09"
    assert ws["F7"].value == pytest.approx(cmp.summary().at["25-09", "Riser Wear mean"])
    assert ws["K7"].value == 0


def test_many_tests(db, tmp_path):
    cmp = build_comparison(db, db.labels * 1)
    write_excel_report(cmp, tmp_path / "r.xlsx")
    html = write_html_report(cmp, tmp_path / "r.html").read_text()
    assert html.count("<svg") == len(METRICS)


def test_html_report(db, tmp_path):
    cmp = build_comparison(db, ["25-09", "26-01"], baseline="25-09")
    html = write_html_report(cmp, tmp_path / "r.html").read_text()
    assert html.startswith("<!doctype html>")
    assert "% difference vs baseline 25-09" in html
    assert html.count("<svg") == len(METRICS)


def test_cli_report_and_list(workbook, tmp_path, capsys):
    out, html = tmp_path / "out.xlsx", tmp_path / "out.html"
    tests_file = tmp_path / "tests.txt"
    tests_file.write_text("# comparison set\n25-09\n25-12  # Q3\n")
    assert main(["report", str(workbook), "26-01", "--tests-file", str(tests_file),
                 "-o", str(out), "--html", str(html)]) == 0
    assert out.exists() and html.exists()
    assert "Comparing 3 tests: 26-01, 25-09, 25-12" in capsys.readouterr().out

    assert main(["list", str(workbook), "--sort", "grade"]) == 0
    assert "23-13 (2)" in capsys.readouterr().out


def test_cli_errors(workbook, tmp_path, capsys):
    assert main(["report", str(workbook), "99-99", "-o", str(tmp_path / "x.xlsx")]) == 2
    assert "No test matches '99-99'" in capsys.readouterr().err
    assert main(["report", str(workbook), "--all", "16-01"]) == 2
    assert main(["report", str(tmp_path / "missing.xlsm"), "--all"]) == 2
