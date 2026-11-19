"""Choosing tests and building the comparison tables used by every report format."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from datetime import datetime
from fnmatch import fnmatchcase

import pandas as pd

from .data import WearDatabase, natural_key, normalize_grade

SORT_CHOICES = ("input", "test", "grade")
GROUP_CHOICES = ("auto", "segment", "test")
# With more tests than this, "auto" groups charts by test (one cluster per test,
# one colour per segment) because a legend with dozens of colours is unreadable.
AUTO_GROUP_BY_TEST_ABOVE = 8


class SelectionError(ValueError):
    """The requested tests could not be resolved."""


def _match(db: WearDatabase, pattern: str) -> list[str]:
    """Labels matching one test pattern.

    A pattern matches a test's label (``23-13 (2)``) or its ID (``23-13``, which
    therefore selects every run of a repeated ID). ``*``, ``?`` and ``[...]`` act as
    wildcards. Matching ignores case.
    """
    pat = pattern.strip().lower()
    is_glob = any(ch in pat for ch in "*?[")
    hits = []
    for label, test_id in zip(db.catalog.index, db.catalog["test_id"]):
        keys = (label.lower(), test_id.lower())
        if (is_glob and any(fnmatchcase(k, pat) for k in keys)) or (not is_glob and pat in keys):
            hits.append(label)
    return hits


def select_tests(
    db: WearDatabase,
    patterns: list[str] | tuple[str, ...] = (),
    *,
    all_tests: bool = False,
    grades: list[str] | tuple[str, ...] = (),
    notes: str | None = None,
    last: int | None = None,
) -> list[str]:
    """Resolve a selection into an ordered list of unique test labels.

    ``patterns`` pick tests in the order given. Without patterns, ``all_tests`` or
    any filter starts from every test in source order. ``grades`` (punctuation and
    case ignored), ``notes`` (substring, case ignored) and ``last`` then narrow it.
    """
    if patterns:
        chosen: list[str] = []
        missing = []
        for pattern in patterns:
            hits = _match(db, pattern)
            if not hits:
                missing.append(pattern)
            chosen.extend(h for h in hits if h not in chosen)
        if missing:
            known = list(dict.fromkeys([*db.catalog.index, *db.catalog["test_id"]]))
            parts = []
            for m in missing:
                close = difflib.get_close_matches(m, known, n=3, cutoff=0.6)
                parts.append(f"{m!r}" + (f" (did you mean {', '.join(close)}?)" if close else ""))
            raise SelectionError("No test matches " + "; ".join(parts))
    elif all_tests or grades or notes or last:
        chosen = db.labels
    else:
        raise SelectionError(
            "No tests selected. Give test IDs (wildcards allowed, e.g. '25-*'), "
            "or use --all, --grade, --notes or --last."
        )

    cat = db.catalog
    if grades:
        wanted = {normalize_grade(g) for g in grades}
        chosen = [lbl for lbl in chosen if normalize_grade(cat.at[lbl, "grade"]) in wanted]
    if notes:
        needle = notes.lower()
        chosen = [lbl for lbl in chosen if needle in cat.at[lbl, "notes"].lower()]
    if last is not None:
        if last < 1:
            raise SelectionError("--last must be at least 1")
        chosen = chosen[-last:]
    if not chosen:
        raise SelectionError("The filters matched no tests.")
    return chosen


def sort_labels(db: WearDatabase, labels: list[str], by: str = "input") -> list[str]:
    cat = db.catalog
    if by == "input":
        return list(labels)
    if by == "test":
        return sorted(labels, key=lambda lbl: (natural_key(cat.at[lbl, "test_id"]), cat.at[lbl, "row"]))
    if by == "grade":
        return sorted(
            labels,
            key=lambda lbl: (normalize_grade(cat.at[lbl, "grade"]), natural_key(cat.at[lbl, "test_id"]),
                             cat.at[lbl, "row"]),
        )
    raise ValueError(f"sort must be one of {SORT_CHOICES}")


def resolve_baseline(db: WearDatabase, pattern: str) -> str:
    hits = _match(db, pattern)
    if not hits:
        raise SelectionError(f"Baseline {pattern!r} matches no test.")
    if len(hits) > 1:
        raise SelectionError(
            f"Baseline {pattern!r} matches several tests ({', '.join(hits)}); pick one label exactly."
        )
    return hits[0]


@dataclass
class Comparison:
    """A set of tests to compare, plus the options that shape the report."""

    db: WearDatabase
    labels: list[str]
    segments: list[int]
    baseline: str | None = None
    group_by: str = "segment"
    units: str = "hrs/in"
    title: str = "Blast-Cooled Starter Generator Comparison"
    higher_is_better: bool = True
    generated: datetime = field(default_factory=datetime.now)
    dropped_segments: list[int] = field(default_factory=list)

    @property
    def metrics(self) -> list[str]:
        return self.db.metrics

    def info(self, label: str) -> pd.Series:
        return self.db.catalog.loc[label]

    def table(self, metric: str) -> pd.DataFrame:
        return self.db.metric_table(metric, self.labels, self.segments)

    def row_means(self, metric: str) -> pd.Series:
        """Mean over the compared segments that have data (NaN when none do)."""
        return self.table(metric).mean(axis=1, skipna=True)

    def pct_vs_baseline(self, metric: str) -> pd.DataFrame | None:
        """Fractional difference from the baseline test, per segment."""
        if self.baseline is None:
            return None
        table = self.table(metric)
        return table.div(table.loc[self.baseline], axis=1) - 1

    def summary(self) -> pd.DataFrame:
        cat = self.db.catalog.loc[self.labels]
        out = pd.DataFrame(
            {"Test ID": cat["test_id"], "Grade": cat["grade"], "Notes": cat["notes"]}, index=cat.index
        )
        counts = self.db.metric_table(self.metrics[0], self.labels, self.segments).notna()
        for metric in self.metrics[1:]:
            counts |= self.table(metric).notna()
        out["Segments with data"] = counts.sum(axis=1).astype(int)
        for metric in self.metrics:
            out[f"{metric} mean"] = self.row_means(metric)
        return out


def build_comparison(
    db: WearDatabase,
    labels: list[str],
    *,
    segments: list[int] | None = None,
    baseline: str | None = None,
    sort: str = "input",
    group_by: str = "auto",
    keep_empty_segments: bool = False,
    **options,
) -> Comparison:
    """Validate options and assemble a :class:`Comparison`.

    Segments with no data for any selected test are dropped (the original workbook
    hid segments 4 and 5 by hand for this reason) unless ``keep_empty_segments``.
    """
    labels = list(dict.fromkeys(labels))
    if baseline is not None:
        baseline = resolve_baseline(db, baseline)
        if baseline not in labels:
            labels.insert(0, baseline)
    labels = sort_labels(db, labels, sort)

    if segments:
        unknown = sorted(set(segments) - set(db.segments))
        if unknown:
            raise SelectionError(
                f"Unknown segment(s) {unknown}; the data has segments {db.segments}."
            )
        requested = sorted(set(segments))
    else:
        requested = list(db.segments)

    has_data = db.values.loc[labels].notna().T.groupby(level="segment").any().any(axis=1)
    dropped = [] if keep_empty_segments else [s for s in requested if not has_data.get(s, False)]
    kept = [s for s in requested if s not in dropped]
    if not kept:
        raise SelectionError("None of the selected tests has data for the chosen segments.")

    if group_by not in GROUP_CHOICES:
        raise ValueError(f"group_by must be one of {GROUP_CHOICES}")
    if group_by == "auto":
        group_by = "test" if len(labels) > AUTO_GROUP_BY_TEST_ABOVE else "segment"

    return Comparison(
        db=db, labels=labels, segments=kept, baseline=baseline, group_by=group_by,
        dropped_segments=dropped, **options,
    )
