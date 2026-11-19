"""Loading the blast-cooled starter generator wear database.

The source is the ``DataString`` sheet of the original comparison workbook (or any
.xlsx/.xlsm/.csv laid out the same way): one row per test, with a test ID column,
a brush grade column, a notes column and one column per ``Segment <n> <metric>``.

Segment and metric columns are discovered from the headers, so adding segments or
new wear metrics to the sheet needs no code change.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DEFAULT_SHEET = "DataString"

_SEGMENT_COL = re.compile(r"^seg(?:ment)?\.?\s*(\d+)\s*[-_:]?\s*(.+)$", re.IGNORECASE)
_ID_NAMES = ("test set number", "test set", "test #", "test no", "test number", "test id", "test")
_GRADE_NAMES = ("brush grade", "grade")
_NOTES_NAMES = ("notes", "note", "comments", "comment")


class DataFormatError(ValueError):
    """The input file does not look like a wear database."""


def normalize_grade(grade: str) -> str:
    """Grade key that ignores case and punctuation, so ``T479`` == ``T-479``."""
    return re.sub(r"[^0-9A-Z]", "", str(grade).upper())


def natural_key(text: str) -> list:
    """Sort key that orders ``23-9`` before ``23-10``."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(text))]


@dataclass
class WearDatabase:
    """All tests from the source file.

    ``catalog`` is indexed by a unique test *label* and has columns
    ``test_id``, ``grade``, ``notes`` and ``row`` (source order).  The label is the
    test ID, except that repeated IDs become ``"23-13 (1)"``, ``"23-13 (2)"`` ...

    ``values`` is indexed by label with ``(metric, segment)`` MultiIndex columns.
    Missing measurements are NaN (never zero).
    """

    catalog: pd.DataFrame
    values: pd.DataFrame
    metrics: list[str]
    segments: list[int]
    source: str

    @property
    def labels(self) -> list[str]:
        return list(self.catalog.index)

    @property
    def duplicate_ids(self) -> list[str]:
        counts = self.catalog["test_id"].value_counts()
        return sorted(counts[counts > 1].index, key=natural_key)

    def metric_table(self, metric: str, labels: list[str], segments: list[int]) -> pd.DataFrame:
        """Tests x segments table for one metric."""
        table = self.values.loc[labels, metric].reindex(columns=segments)
        table.columns.name = "segment"
        return table

    def segments_with_data(self, labels: list[str]) -> dict[str, int]:
        """Number of segments that have at least one measurement, per test."""
        present = self.values.loc[labels].notna().T.groupby(level="segment").any().T
        return present.sum(axis=1).astype(int).to_dict()


def _norm_header(value) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def _find_column(columns: list[str], names: tuple[str, ...], required: bool, what: str):
    lookup = {c.lower(): c for c in columns}
    for name in names:
        if name in lookup:
            return lookup[name]
    if required:
        raise DataFormatError(
            f"Could not find the {what} column. Expected one of: {', '.join(names)}. "
            f"Found: {', '.join(columns[:10])}{'...' if len(columns) > 10 else ''}"
        )
    return None


def _clean_id(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _read_frame(path: Path, sheet: str | None) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".txt"}:
        return pd.read_csv(path, dtype=object)
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        with warnings.catch_warnings():
            # openpyxl warns about Excel extensions (data validation, etc.) it skips.
            warnings.simplefilter("ignore", UserWarning)
            with pd.ExcelFile(path) as xl:
                if sheet is None:
                    sheet = DEFAULT_SHEET if DEFAULT_SHEET in xl.sheet_names else xl.sheet_names[0]
                elif sheet not in xl.sheet_names:
                    raise DataFormatError(
                        f"Sheet {sheet!r} not found in {path.name}. Sheets: {', '.join(xl.sheet_names)}"
                    )
                return xl.parse(sheet, dtype=object)
    raise DataFormatError(f"Unsupported file type {suffix!r}; use .xlsx, .xlsm, .xls or .csv")


def load_database(path: str | Path, sheet: str | None = None) -> WearDatabase:
    """Read a wear database from an Excel workbook or CSV file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    frame = _read_frame(path, sheet)
    frame.columns = [_norm_header(c) for c in frame.columns]
    columns = list(frame.columns)

    id_col = _find_column(columns, _ID_NAMES, True, "test ID")
    grade_col = _find_column(columns, _GRADE_NAMES, False, "grade")
    notes_col = _find_column(columns, _NOTES_NAMES, False, "notes")

    value_cols: dict[tuple[str, int], str] = {}
    metrics: list[str] = []
    for col in columns:
        match = _SEGMENT_COL.match(col)
        if not match:
            continue
        segment, metric = int(match.group(1)), match.group(2).strip()
        metric = metric[:1].upper() + metric[1:]
        if metric.lower() not in {m.lower() for m in metrics}:
            metrics.append(metric)
        metric = next(m for m in metrics if m.lower() == metric.lower())
        value_cols[(metric, segment)] = col
    if not value_cols:
        raise DataFormatError(
            "No 'Segment <n> <metric>' columns found (e.g. 'Segment 1 Riser Wear')."
        )
    segments = sorted({seg for _, seg in value_cols})

    frame = frame.assign(_id=frame[id_col].map(_clean_id))
    frame = frame[frame["_id"] != ""].reset_index(drop=True)
    if frame.empty:
        raise DataFormatError(f"No tests found in {path.name}.")

    ids = frame["_id"]
    totals = ids.map(ids.value_counts())
    occurrence = ids.groupby(ids).cumcount() + 1
    labels = [
        f"{tid} ({n})" if total > 1 else tid for tid, n, total in zip(ids, occurrence, totals)
    ]

    def text(col):
        if col is None:
            return [""] * len(frame)
        return [("" if pd.isna(v) else str(v).strip()) for v in frame[col]]

    catalog = pd.DataFrame(
        {"test_id": list(ids), "grade": text(grade_col), "notes": text(notes_col), "row": range(len(frame))},
        index=pd.Index(labels, name="test"),
    )

    keys = [(m, s) for m in metrics for s in segments]
    data = {
        key: pd.to_numeric(frame[value_cols[key]], errors="coerce") if key in value_cols else float("nan")
        for key in keys
    }
    values = pd.DataFrame(data, index=range(len(frame))).astype(float)
    values.index = catalog.index
    values.columns = pd.MultiIndex.from_tuples(keys, names=["metric", "segment"])

    return WearDatabase(catalog=catalog, values=values, metrics=metrics, segments=segments, source=str(path))
