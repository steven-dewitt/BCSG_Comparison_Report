# BCSG Comparison Report

A Python replacement for `Blast-Cooled_Starter_Generator_Comparison_Spreadsheet.xlsm`.
It reads the same test data and builds a comparison report for **any number of tests**,
instead of the workbook's five fixed slots.

The workbook stays the place where test data lives. The tool reads its `DataString`
sheet directly, so you keep adding tests there exactly as before.

## Setup

Requires Python 3.9 or newer.

```bash
pip install -r requirements.txt
```

## Usage

Run from this folder (or `pip install .` to get a `bcsg-compare` command).

**List the tests in the workbook** (this replaces the *Test No* / *Grade* sort buttons):

```bash
python -m bcsg_compare list Blast-Cooled_Starter_Generator_Comparison_Spreadsheet.xlsm --sort grade
```

**Compare tests.** List as many as you like, in the order you want them shown:

```bash
python -m bcsg_compare report Blast-Cooled_Starter_Generator_Comparison_Spreadsheet.xlsm 26-01 26-02 25-13 25-12 25-09 25-08 25-07
```

This writes `BCSG_Comparison_Report.xlsx`. Add `--html report.html` to also get a
self-contained web page that opens in any browser and can be emailed or printed to PDF.

More examples:

```bash
# Every 2025 test, compared with 25-09 as the baseline (adds % difference tables)
python -m bcsg_compare report DATA.xlsm "25-*" --baseline 25-09 -o 2025_vs_25-09.xlsx

# All ASG4 tests whose notes mention "Diagonal"
python -m bcsg_compare report DATA.xlsm --grade ASG4 --notes diagonal

# The 10 most recent tests, HTML only
python -m bcsg_compare report DATA.xlsm --all --last 10 --no-excel --html latest.html

# A saved comparison set: one test per line, '#' starts a comment
python -m bcsg_compare report DATA.xlsm --tests-file q-dc_tests.txt

# Only some segments, sorted by grade
python -m bcsg_compare report DATA.xlsm 16-01 16-02 19-04 --segments 1 2 3 --sort grade
```

Run `python -m bcsg_compare report --help` to see every option.

### Choosing tests

| You give | It selects |
|---|---|
| `25-09` | that test |
| `"25-*"`, `"2[45]-0?"` | every matching test (`*`, `?` and `[...]` wildcards; quote them in bash) |
| `23-13` when the ID appears twice | both runs, labelled `23-13 (1)` and `23-13 (2)` |
| `"23-13 (2)"` | only the second run |
| `--all` | every test in the file |
| `--grade T479` | that grade; case and punctuation are ignored, so `T479` = `T-479` |
| `--notes rerun` | tests whose notes contain the text |
| `--last N` | the last N tests of the selection |

Filters can be combined with each other and with test IDs. A test ID that isn't in the
data stops the run with a "did you mean ..." suggestion instead of silently showing
`#N/A`.

## What's in the Excel report

* **Summary**: the compared tests (grade, notes, how many segments have data, mean of
  each wear metric, and % vs the baseline if you set one), followed by a column chart for
  each metric: Riser, Bearing, Average, Positive and Negative wear.
* **One sheet per metric**: a tests × segments table coloured per segment (green =
  highest), with group mean/min/max rows and, with `--baseline`, a % difference table.
  Means, statistics and percentages are live Excel formulas, so they update if you edit
  a value.
* **Data (long)**: one row per test / metric / segment, ready for pivot tables.
* **Test Catalog**: every test in the data file, with filters and the tests in this
  report highlighted.

Charts are native Excel charts, so you can restyle them. Up to 8 tests are clustered by
segment, like the original workbook. With more tests, they're clustered by test with
one colour per segment, so the legend stays readable. Use `--group-by segment` or
`--group-by test` to choose.

## Improvements over the spreadsheet

* **Any number of tests** instead of five fixed slots wired to `test1`…`test5`.
* **Missing data is shown as missing.** VLOOKUP turned blank cells into `0`, so a
  segment that wasn't measured (for example 26-01 segments 7–8) was charted as zero
  wear life. It now shows as a gap or a blank cell.
* **Empty segments are dropped automatically.** The workbook hid segments 4 and 5 from
  every chart by hand. They are now left out only when none of the selected tests has
  data for them (or pick segments with `--segments`).
* **Repeated test IDs are handled.** `23-13` and `23-14` each appear twice in
  `DataString`, and VLOOKUP always returned the first row. Each run is now shown and
  labelled separately.
* **Baseline comparison** (`--baseline`) shows the % change of every value.
* **No macros**, and the layout is read from the column headers: adding a
  `Segment 9 …` column or a new `Segment n <metric>` metric needs no code change.

## Data format

Excel (`.xlsx`, `.xlsm`, `.xls`) or CSV with one row per test. The tool uses the
`DataString` sheet if it exists, otherwise the first sheet (or pass `--sheet NAME`).
Columns:

* `Test Set Number`: the test ID
* `Brush Grade` (optional)
* `Notes` (optional)
* `Segment <n> <Metric>`: for example `Segment 1 Riser Wear`, in hrs/in

Blank or non-numeric value cells count as "not measured".

## Development

```bash
python -m pytest
```

The tests use a small synthetic dataset, so the real test data is not needed (or
stored) in this repository.
