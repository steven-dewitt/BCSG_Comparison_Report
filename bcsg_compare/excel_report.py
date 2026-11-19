"""Excel (.xlsx) comparison report with native, editable charts.

Sheets:

* **Summary**: the compared tests with per-metric means, followed by one
  clustered column chart per wear metric (the layout of the original Report sheet).
* **One sheet per metric**: tests x segments table with per-segment colour scales,
  group mean/min/max rows and, with a baseline, a %-difference table.
  Means and statistics are live Excel formulas.
* **Data (long)**: one row per test/metric/segment value, ready for pivot tables.
* **Test Catalog**: every test in the source, filterable and sortable.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pandas as pd
import xlsxwriter
from xlsxwriter.utility import xl_rowcol_to_cell

from .colors import BAD, GOOD, MID, NEG, POS, ZERO, palette
from .compare import Comparison

_HEADER_ROW = 3  # 0-based row of the column headers on metric sheets
_SUMMARY_HEADER_ROW = 5


def _sheet_name(name: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", "-", name).strip("'")[:31] or "Sheet"
    candidate, n = base, 2
    while candidate.lower() in used:
        suffix = f" ({n})"
        candidate, n = base[: 31 - len(suffix)] + suffix, n + 1
    used.add(candidate.lower())
    return candidate


def _quote(sheet: str) -> str:
    return "'" + sheet.replace("'", "''") + "'"


def _value(v):
    return "" if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)


class _Formats:
    def __init__(self, wb: xlsxwriter.Workbook):
        border = {"border": 1, "border_color": "#BFBFBF"}
        self.title = wb.add_format({"bold": True, "font_size": 16, "font_color": "#1F3864"})
        self.subtitle = wb.add_format({"bold": True, "font_size": 12, "font_color": "#1F3864"})
        self.note = wb.add_format({"italic": True, "font_color": "#595959"})
        self.header = wb.add_format(
            {"bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E78", "text_wrap": True,
             "valign": "vcenter", "align": "center", **border}
        )
        self.text = wb.add_format(border)
        self.bold_text = wb.add_format({"bold": True, **border})
        self.number = wb.add_format({"num_format": "0", **border})
        self.integer = wb.add_format({"num_format": "0", "align": "center", **border})
        self.pct = wb.add_format({"num_format": "+0.0%;-0.0%;0.0%", **border})
        self.stat_label = wb.add_format({"bold": True, "italic": True, "bg_color": "#F2F2F2", **border})
        self.stat_number = wb.add_format({"num_format": "0", "italic": True, "bg_color": "#F2F2F2", **border})
        self.baseline_text = wb.add_format({"bold": True, "bg_color": "#DDEBF7", **border})
        self.selected = wb.add_format({"bg_color": "#E2EFDA", **border})


def _scale(higher_is_better: bool) -> dict:
    low, high = (BAD, GOOD) if higher_is_better else (GOOD, BAD)
    return {"type": "3_color_scale", "min_color": low, "mid_color": MID, "max_color": high}


def _write_metric_sheet(wb, ws, cmp: Comparison, metric: str, fmt: _Formats) -> dict:
    """Write one metric's tables; return cell positions for charts and the summary."""
    table = cmp.table(metric)
    means = cmp.row_means(metric)
    n, segs = len(cmp.labels), cmp.segments
    first_val_col, last_val_col = 2, 1 + len(segs)
    mean_col = last_val_col + 1
    first_row, last_row = _HEADER_ROW + 1, _HEADER_ROW + n

    ws.write(0, 0, f"{metric} ({cmp.units})", fmt.title)
    better = "highest" if cmp.higher_is_better else "lowest"
    ws.write(1, 0, f"Each column is coloured across the compared tests; green = {better}. "
                   "Blank cells = no measurement.", fmt.note)
    ws.write_row(_HEADER_ROW, 0, ["Test", "Grade"] + [f"Seg {s}" for s in segs] + ["Mean"], fmt.header)

    for i, label in enumerate(cmp.labels):
        r = first_row + i
        name_fmt = fmt.baseline_text if label == cmp.baseline else fmt.bold_text
        ws.write_string(r, 0, label, name_fmt)
        ws.write_string(r, 1, cmp.info(label)["grade"], fmt.text)
        for j, seg in enumerate(segs):
            v = table.at[label, seg]
            if pd.isna(v):
                ws.write_blank(r, first_val_col + j, None, fmt.number)
            else:
                ws.write_number(r, first_val_col + j, float(v), fmt.number)
        rng = f"{xl_rowcol_to_cell(r, first_val_col)}:{xl_rowcol_to_cell(r, last_val_col)}"
        ws.write_formula(r, mean_col, f'=IF(COUNT({rng})=0,"",AVERAGE({rng}))', fmt.number,
                         _value(means[label]))

    stats_row = last_row + 2
    for k, (name, func, method) in enumerate(
        [("Group mean", "AVERAGE", "mean"), ("Group min", "MIN", "min"), ("Group max", "MAX", "max")]
    ):
        r = stats_row + k
        ws.write_string(r, 0, name, fmt.stat_label)
        ws.write_blank(r, 1, None, fmt.stat_label)
        for c in range(first_val_col, mean_col + 1):
            col = table.iloc[:, c - first_val_col] if c <= last_val_col else means
            cached = getattr(col, method)(skipna=True)
            rng = f"{xl_rowcol_to_cell(first_row, c)}:{xl_rowcol_to_cell(last_row, c)}"
            ws.write_formula(r, c, f'=IF(COUNT({rng})=0,"",{func}({rng}))', fmt.stat_number,
                             _value(cached))

    for c in range(first_val_col, mean_col + 1):
        ws.conditional_format(first_row, c, last_row, c, _scale(cmp.higher_is_better))

    pct = cmp.pct_vs_baseline(metric)
    if pct is not None:
        base_row = first_row + cmp.labels.index(cmp.baseline)
        top = stats_row + 5
        ws.write(top, 0, f"% difference vs baseline {cmp.baseline}", fmt.subtitle)
        hdr = top + 1
        ws.write_row(hdr, 0, ["Test", "Grade"] + [f"Seg {s}" for s in segs] + ["Mean"], fmt.header)
        base_means = means[cmp.baseline]
        bound = 0.1
        for i, label in enumerate(cmp.labels):
            r, src = hdr + 1 + i, first_row + i
            name_fmt = fmt.baseline_text if label == cmp.baseline else fmt.bold_text
            ws.write_string(r, 0, label, name_fmt)
            ws.write_string(r, 1, cmp.info(label)["grade"], fmt.text)
            for c in range(first_val_col, mean_col + 1):
                if c <= last_val_col:
                    cached = pct.at[label, segs[c - first_val_col]]
                else:
                    cached = means[label] / base_means - 1 if base_means else float("nan")
                if not pd.isna(cached):
                    bound = max(bound, abs(float(cached)))
                cell = xl_rowcol_to_cell(src, c)
                base = xl_rowcol_to_cell(base_row, c, row_abs=True)
                ws.write_formula(
                    r, c, f'=IFERROR(IF(OR({cell}="",{base}=""),"",{cell}/{base}-1),"")', fmt.pct,
                    _value(cached),
                )
        neg, pos = (NEG, POS) if cmp.higher_is_better else (POS, NEG)
        ws.conditional_format(
            hdr + 1, first_val_col, hdr + n, mean_col,
            {"type": "3_color_scale", "min_type": "num", "min_value": -bound, "mid_type": "num",
             "mid_value": 0, "max_type": "num", "max_value": bound,
             "min_color": neg, "mid_color": ZERO, "max_color": pos},
        )

    ws.set_column(0, 0, max(12, min(30, max(len(lbl) for lbl in cmp.labels) + 2)))
    ws.set_column(1, 1, 12)
    ws.set_column(first_val_col, mean_col, 10)
    ws.freeze_panes(first_row, 2)
    ws.set_landscape()
    ws.fit_to_pages(1, 0)
    return {"first_row": first_row, "last_row": last_row, "first_val_col": first_val_col,
            "last_val_col": last_val_col, "mean_col": mean_col}


def _add_chart(wb, cmp: Comparison, metric: str, sheet: str, pos: dict, colors_by_test, colors_by_seg):
    chart = wb.add_chart({"type": "column"})
    fr, lr = pos["first_row"], pos["last_row"]
    fc, lc = pos["first_val_col"], pos["last_val_col"]
    n_tests, n_segs = len(cmp.labels), len(cmp.segments)

    if cmp.group_by == "segment":
        n_cat, n_ser = n_segs, n_tests
        for i in range(n_tests):
            r = fr + i
            chart.add_series({
                "name": [sheet, r, 0], "categories": [sheet, _HEADER_ROW, fc, _HEADER_ROW, lc],
                "values": [sheet, r, fc, r, lc],
                "fill": {"color": colors_by_test[i]}, "border": {"none": True},
            })
        axis_name = "Segment"
    else:
        n_cat, n_ser = n_tests, n_segs
        for j in range(n_segs):
            c = fc + j
            chart.add_series({
                "name": [sheet, _HEADER_ROW, c], "categories": [sheet, fr, 0, lr, 0],
                "values": [sheet, fr, c, lr, c],
                "fill": {"color": colors_by_seg[j]}, "border": {"none": True},
            })
        axis_name = "Test"

    width = int(max(780, min(4000, 160 + n_cat * (n_ser * 13 + 26))))
    height = 380
    chart.set_title({"name": f"{metric} ({cmp.units})", "name_font": {"size": 13}})
    x_axis = {"name": axis_name}
    if n_cat > 12:
        x_axis["num_font"] = {"rotation": -45}
    chart.set_x_axis(x_axis)
    chart.set_y_axis({"name": cmp.units, "num_format": "0",
                      "major_gridlines": {"visible": True, "line": {"color": "#D9D9D9"}}})
    chart.set_legend({"position": "right" if n_ser > 8 else "bottom"})
    chart.show_blanks_as("gap")
    chart.set_size({"width": width, "height": height})
    chart.set_chartarea({"border": {"color": "#BFBFBF"}})
    return chart, height


def write_excel_report(cmp: Comparison, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = xlsxwriter.Workbook(str(path))
    fmt = _Formats(wb)
    used: set[str] = set()

    summary = wb.add_worksheet(_sheet_name("Summary", used))
    metric_sheets = {m: wb.add_worksheet(_sheet_name(m, used)) for m in cmp.metrics}
    long_ws = wb.add_worksheet(_sheet_name("Data (long)", used))
    catalog_ws = wb.add_worksheet(_sheet_name("Test Catalog", used))

    positions = {m: _write_metric_sheet(wb, ws, cmp, m, fmt) for m, ws in metric_sheets.items()}

    # ---- Summary -------------------------------------------------------------
    n = len(cmp.labels)
    src = Path(cmp.db.source).name
    summary.write(0, 0, cmp.title, fmt.title)
    summary.write(1, 0, f"Generated {cmp.generated:%Y-%m-%d %H:%M} from {src}", fmt.note)
    seg_text = ", ".join(str(s) for s in cmp.segments)
    line = f"{n} tests compared · segments {seg_text} · values in {cmp.units}"
    if cmp.dropped_segments:
        line += f" · segment(s) {', '.join(map(str, cmp.dropped_segments))} omitted (no data)"
    summary.write(2, 0, line, fmt.note)
    if cmp.baseline:
        summary.write(3, 0, f"Baseline: {cmp.baseline} (highlighted blue)", fmt.note)

    info = cmp.summary()
    headers = ["#", "Test", "Grade", "Notes", "Segments with data"]
    headers += [f"{m} mean" for m in cmp.metrics]
    if cmp.baseline:
        headers += [f"{m} vs baseline" for m in cmp.metrics]
    hr = _SUMMARY_HEADER_ROW
    summary.set_row(hr, 32)
    summary.write_row(hr, 0, headers, fmt.header)
    mean_col0 = 5
    base_idx = cmp.labels.index(cmp.baseline) if cmp.baseline else None
    for i, label in enumerate(cmp.labels):
        r = hr + 1 + i
        row = info.loc[label]
        name_fmt = fmt.baseline_text if label == cmp.baseline else fmt.bold_text
        summary.write_number(r, 0, i + 1, fmt.integer)
        summary.write_string(r, 1, label, name_fmt)
        summary.write_string(r, 2, row["Grade"], fmt.text)
        summary.write_string(r, 3, row["Notes"], fmt.text)
        summary.write_number(r, 4, int(row["Segments with data"]), fmt.integer)
        for k, metric in enumerate(cmp.metrics):
            pos = positions[metric]
            ref = f"={_quote(metric_sheets[metric].name)}!" + xl_rowcol_to_cell(pos["first_row"] + i, pos["mean_col"])
            summary.write_formula(r, mean_col0 + k, ref, fmt.number, _value(row[f"{metric} mean"]))
            if cmp.baseline:
                c = mean_col0 + len(cmp.metrics) + k
                cell = xl_rowcol_to_cell(r, mean_col0 + k)
                base = xl_rowcol_to_cell(hr + 1 + base_idx, mean_col0 + k, row_abs=True)
                base_v = info.loc[cmp.baseline, f"{metric} mean"]
                cached = row[f"{metric} mean"] / base_v - 1 if base_v else float("nan")
                summary.write_formula(r, c, f'=IFERROR(IF(OR({cell}="",{base}=""),"",{cell}/{base}-1),"")',
                                      fmt.pct, _value(cached))
    for k in range(len(cmp.metrics)):
        summary.conditional_format(hr + 1, mean_col0 + k, hr + n, mean_col0 + k, _scale(cmp.higher_is_better))
    if cmp.baseline:
        lo, hi = mean_col0 + len(cmp.metrics), mean_col0 + 2 * len(cmp.metrics) - 1
        neg, pos_c = (NEG, POS) if cmp.higher_is_better else (POS, NEG)
        summary.conditional_format(hr + 1, lo, hr + n, hi, {
            "type": "3_color_scale", "min_type": "num", "min_value": -0.25, "mid_type": "num",
            "mid_value": 0, "max_type": "num", "max_value": 0.25,
            "min_color": neg, "mid_color": ZERO, "max_color": pos_c})
    summary.set_column(0, 0, 5)
    summary.set_column(1, 1, max(12, min(30, max(len(lbl) for lbl in cmp.labels) + 2)))
    summary.set_column(2, 2, 13)
    summary.set_column(3, 3, 30)
    summary.set_column(4, 4, 11)
    summary.set_column(mean_col0, len(headers) - 1, 13)
    summary.freeze_panes(hr + 1, 2)
    summary.set_landscape()
    summary.fit_to_pages(1, 0)

    by_test = palette(n)
    by_seg = palette(len(cmp.segments))
    row = hr + n + 3
    summary.write(row - 1, 0, "Charts", fmt.subtitle)
    for metric in cmp.metrics:
        chart, height = _add_chart(wb, cmp, metric, metric_sheets[metric].name, positions[metric], by_test, by_seg)
        summary.insert_chart(row, 0, chart, {"object_position": 3})
        row += math.ceil(height / 20) + 2

    # ---- Data (long) ---------------------------------------------------------
    cols = ["Test", "Test ID", "Grade", "Notes", "Metric", "Segment", "Value"]
    long_ws.write_row(0, 0, cols, fmt.header)
    r = 1
    for label in cmp.labels:
        meta = cmp.info(label)
        for metric in cmp.metrics:
            for seg in cmp.segments:
                v = cmp.db.values.at[label, (metric, seg)]
                if pd.isna(v):
                    continue
                long_ws.write_row(r, 0, [label, meta["test_id"], meta["grade"], meta["notes"], metric, seg])
                long_ws.write_number(r, 6, float(v))
                r += 1
    long_ws.autofilter(0, 0, max(r - 1, 1), len(cols) - 1)
    long_ws.freeze_panes(1, 0)
    long_ws.set_column(0, 1, 12)
    long_ws.set_column(2, 2, 13)
    long_ws.set_column(3, 3, 28)
    long_ws.set_column(4, 4, 16)
    long_ws.set_column(5, 6, 10)

    # ---- Test Catalog --------------------------------------------------------
    cat = cmp.db.catalog
    seg_counts = cmp.db.segments_with_data(list(cat.index))
    selected = set(cmp.labels)
    cols = ["Test", "Test ID", "Grade", "Notes", "Segments with data", "In this report"]
    catalog_ws.write_row(0, 0, cols, fmt.header)
    for i, (label, meta) in enumerate(cat.iterrows(), start=1):
        f = fmt.selected if label in selected else fmt.text
        catalog_ws.write_string(i, 0, label, f)
        catalog_ws.write_string(i, 1, meta["test_id"], f)
        catalog_ws.write_string(i, 2, meta["grade"], f)
        catalog_ws.write_string(i, 3, meta["notes"], f)
        catalog_ws.write_number(i, 4, seg_counts[label], f)
        catalog_ws.write_string(i, 5, "Yes" if label in selected else "", f)
    catalog_ws.autofilter(0, 0, len(cat), len(cols) - 1)
    catalog_ws.freeze_panes(1, 0)
    catalog_ws.set_column(0, 1, 12)
    catalog_ws.set_column(2, 2, 14)
    catalog_ws.set_column(3, 3, 30)
    catalog_ws.set_column(4, 5, 12)

    summary.activate()
    wb.close()
    return path
