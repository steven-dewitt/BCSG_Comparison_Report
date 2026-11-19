"""Command-line interface.

Examples::

    # List every test in the workbook, sorted by grade
    python -m bcsg_compare list Blast-Cooled_Starter_Generator_Comparison_Spreadsheet.xlsm --sort grade

    # Compare any number of tests (wildcards allowed) against a baseline
    python -m bcsg_compare report DATA.xlsm 26-01 26-02 25-13 25-12 25-09 --baseline 25-09

    # Every 2025 test, plus an HTML copy
    python -m bcsg_compare report DATA.xlsm "25-*" -o 2025.xlsx --html 2025.html
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .compare import GROUP_CHOICES, SORT_CHOICES, SelectionError, build_comparison, select_tests, sort_labels
from .data import DataFormatError, load_database


def _add_data_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("data", type=Path, help="Workbook (.xlsm/.xlsx) or CSV holding the test data")
    p.add_argument("--sheet", help="Sheet with the data (default: 'DataString', else the first sheet)")


def _add_filter_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--grade", action="append", default=[], metavar="GRADE",
                   help="Only tests of this brush grade (case/punctuation ignored, so T479 = T-479). Repeatable.")
    p.add_argument("--notes", metavar="TEXT", help="Only tests whose notes contain TEXT (case ignored)")
    p.add_argument("--last", type=int, metavar="N", help="Only the last N tests of the selection")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bcsg-compare",
        description="Compare any number of blast-cooled starter generator brush wear tests.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    ls = sub.add_parser("list", help="List the tests in the data file")
    _add_data_args(ls)
    ls.add_argument("tests", nargs="*", help="Optional test IDs / wildcard patterns to show")
    _add_filter_args(ls)
    ls.add_argument("--sort", choices=("test", "grade", "input"), default="input",
                    help="Sort order (default: as in the file)")

    rp = sub.add_parser("report", help="Build a comparison report")
    _add_data_args(rp)
    rp.add_argument("tests", nargs="*",
                    help="Test IDs to compare, in order. Wildcards allowed ('25-*'). A repeated ID such as "
                         "23-13 selects every run; use '23-13 (2)' for one.")
    rp.add_argument("--all", action="store_true", help="Compare every test in the file")
    rp.add_argument("--tests-file", type=Path, metavar="FILE",
                    help="Text file with one test ID / pattern per line (# starts a comment)")
    _add_filter_args(rp)
    rp.add_argument("--baseline", metavar="TEST",
                    help="Add %%-difference tables relative to this test (added to the comparison if needed)")
    rp.add_argument("--segments", type=int, nargs="+", metavar="N",
                    help="Segments to include (default: all segments that have data for the chosen tests)")
    rp.add_argument("--keep-empty-segments", action="store_true",
                    help="Keep segments with no data instead of dropping them")
    rp.add_argument("--sort", choices=SORT_CHOICES, default="input",
                    help="Order of tests in the report (default: the order given)")
    rp.add_argument("--group-by", choices=GROUP_CHOICES, default="auto",
                    help="Chart clusters: 'segment' (one bar per test in each segment cluster, like the original "
                         "workbook) or 'test' (one bar per segment in each test cluster). 'auto' uses 'segment' "
                         "for up to 8 tests, else 'test'.")
    rp.add_argument("-o", "--output", type=Path, default=Path("BCSG_Comparison_Report.xlsx"),
                    help="Excel report path (default: %(default)s)")
    rp.add_argument("--html", type=Path, metavar="FILE", help="Also write a self-contained HTML report")
    rp.add_argument("--no-excel", action="store_true", help="Skip the Excel report (use with --html)")
    rp.add_argument("--title", default="Blast-Cooled Starter Generator Comparison", help="Report title")
    rp.add_argument("--units", default="hrs/in", help="Units label for values (default: %(default)s)")
    rp.add_argument("--lower-is-better", action="store_true",
                    help="Colour low values green instead of high values")
    return parser


def _read_tests_file(path: Path) -> list[str]:
    tests = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            tests.append(line)
    return tests


def _cmd_list(args) -> int:
    db = load_database(args.data, args.sheet)
    if args.tests or args.grade or args.notes or args.last:
        labels = select_tests(db, args.tests, grades=args.grade, notes=args.notes, last=args.last)
    else:
        labels = db.labels
    labels = sort_labels(db, labels, args.sort)
    counts = db.segments_with_data(labels)
    cat = db.catalog
    w_test = max(4, *(len(lbl) for lbl in labels))
    w_grade = max(5, *(len(cat.at[lbl, "grade"]) for lbl in labels))
    print(f"{'Test':<{w_test}}  {'Grade':<{w_grade}}  Segs  Notes")
    for lbl in labels:
        print(f"{lbl:<{w_test}}  {cat.at[lbl, 'grade']:<{w_grade}}  {counts[lbl]:>4}  {cat.at[lbl, 'notes']}")
    print(f"\n{len(labels)} of {len(db.labels)} tests · segments {db.segments[0]}-{db.segments[-1]} · "
          f"metrics: {', '.join(db.metrics)}")
    if db.duplicate_ids:
        print(f"Note: repeated test IDs {', '.join(db.duplicate_ids)} are labelled 'ID (1)', 'ID (2)', ...")
    return 0


def _cmd_report(args) -> int:
    if args.no_excel and not args.html:
        raise SelectionError("--no-excel needs --html, otherwise nothing would be written.")
    db = load_database(args.data, args.sheet)
    patterns = list(args.tests)
    if args.tests_file:
        patterns += _read_tests_file(args.tests_file)
    if args.all and patterns:
        raise SelectionError("Use either --all or a list of tests, not both.")
    labels = select_tests(db, patterns, all_tests=args.all, grades=args.grade, notes=args.notes, last=args.last)
    cmp = build_comparison(
        db, labels, segments=args.segments, baseline=args.baseline, sort=args.sort, group_by=args.group_by,
        keep_empty_segments=args.keep_empty_segments, units=args.units, title=args.title,
        higher_is_better=not args.lower_is_better,
    )

    print(f"Comparing {len(cmp.labels)} tests: {', '.join(cmp.labels)}")
    print(f"Segments: {', '.join(map(str, cmp.segments))}"
          + (f" (dropped {', '.join(map(str, cmp.dropped_segments))}: no data)" if cmp.dropped_segments else ""))
    repeated = sorted({db.catalog.at[lbl, "test_id"] for lbl in cmp.labels} & set(db.duplicate_ids))
    if repeated:
        print(f"Note: {', '.join(repeated)} appear more than once in the data; each run is shown separately.")

    if not args.no_excel:
        from .excel_report import write_excel_report
        print(f"Excel report: {write_excel_report(cmp, args.output)}")
    if args.html:
        from .html_report import write_html_report
        print(f"HTML report:  {write_html_report(cmp, args.html)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _cmd_list(args) if args.command == "list" else _cmd_report(args)
    except (SelectionError, DataFormatError, FileNotFoundError, PermissionError) as exc:
        if isinstance(exc, PermissionError):
            exc = f"{exc} (is the file open in Excel?)"
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
