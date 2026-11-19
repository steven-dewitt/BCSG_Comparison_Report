"""Self-contained HTML comparison report (inline SVG charts, no external files).

Opens in any browser, can be emailed, and prints to PDF.
"""

from __future__ import annotations

import html
import math
from pathlib import Path

import pandas as pd

from .colors import BAD, GOOD, MID, NEG, POS, ZERO, palette, three_color

_CSS = """
:root { --ink:#1f2937; --muted:#6b7280; --line:#d1d5db; --head:#1F4E78; --bg:#ffffff; }
* { box-sizing: border-box; }
body { margin: 0; padding: 24px 16px 48px; font: 14px/1.45 system-ui, -apple-system, "Segoe UI", Arial, sans-serif;
       color: var(--ink); background: var(--bg); }
main { max-width: 1400px; margin: 0 auto; }
h1 { font-size: 22px; margin: 0 0 4px; color: #1F3864; }
h2 { font-size: 17px; margin: 36px 0 8px; color: #1F3864; border-bottom: 2px solid #1F3864; padding-bottom: 4px; }
h3 { font-size: 14px; margin: 18px 0 6px; }
.meta { color: var(--muted); margin: 2px 0; }
.scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
table { border-collapse: collapse; margin: 6px 0 4px; font-variant-numeric: tabular-nums; }
th, td { border: 1px solid var(--line); padding: 3px 8px; white-space: nowrap; }
th { background: var(--head); color: #fff; font-weight: 600; text-align: center; }
td.num { text-align: right; }
td.label { font-weight: 600; }
tr.baseline td.label { background: #DDEBF7; }
tr.stat td { background: #f3f4f6; font-style: italic; }
.legend { display: flex; flex-wrap: wrap; gap: 4px 14px; margin: 4px 0 0; font-size: 12px; }
.legend span::before { content: ""; display: inline-block; width: 11px; height: 11px; margin-right: 5px;
                       vertical-align: -1px; background: var(--c); border-radius: 2px; }
svg text { font-family: inherit; }
.note { color: var(--muted); font-size: 12px; }
@media print { body { padding: 0; } h2 { break-before: page; } .scroll { overflow: visible; } }
"""


def _esc(v) -> str:
    return html.escape(str(v))


def _fmt(v, pct=False) -> str:
    if v is None or pd.isna(v):
        return ""
    return f"{v:+.1%}" if pct else f"{v:,.0f}"


def _nice_max(v: float) -> tuple[float, float]:
    """Axis maximum and tick step for data whose maximum is ``v``."""
    if not v or v <= 0 or math.isnan(v):
        return 1.0, 0.2
    raw = v / 5
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    return step * math.ceil(v / step), step


def svg_grouped_bars(categories: list[str], series: list[tuple[str, list[float]]], colors: list[str],
                     y_label: str, height: int = 340) -> str:
    n_cat, n_ser = len(categories), max(len(series), 1)
    rotate = n_cat > 12 or max((len(c) for c in categories), default=0) * n_cat > 110
    left, right, top = 64, 16, 14
    bottom = 78 if rotate else 40
    group_w = max(28.0, n_ser * 9 + 16)
    plot_w = max(640 - left - right, n_cat * group_w)
    width = int(left + plot_w + right)
    plot_h = height - top - bottom
    vmax = max((v for _, vals in series for v in vals if v is not None and not pd.isna(v)), default=0)
    ymax, step = _nice_max(vmax)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}" role="img">']
    t = 0.0
    while t <= ymax + 1e-9:
        y = top + plot_h - t / ymax * plot_h
        out.append(f'<line x1="{left}" x2="{left + plot_w:.1f}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e5e7eb"/>')
        out.append(f'<text x="{left - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="11" fill="#6b7280">'
                   f'{t:,.0f}</text>')
        t += step
    out.append(f'<text transform="translate(14 {top + plot_h / 2:.0f}) rotate(-90)" text-anchor="middle" '
               f'font-size="12" fill="#374151">{_esc(y_label)}</text>')

    slot = plot_w / max(n_cat, 1)
    inner = slot * 0.82
    bar_w = inner / n_ser
    for ci, cat in enumerate(categories):
        x0 = left + ci * slot + (slot - inner) / 2
        for si, (name, vals) in enumerate(series):
            v = vals[ci]
            if v is None or pd.isna(v):
                continue
            h = v / ymax * plot_h
            x = x0 + si * bar_w
            out.append(f'<rect x="{x:.1f}" y="{top + plot_h - h:.1f}" width="{max(bar_w - 1, 1):.1f}" '
                       f'height="{h:.1f}" fill="{colors[si]}"><title>{_esc(name)} · {_esc(cat)}: '
                       f'{v:,.0f}</title></rect>')
        cx = left + ci * slot + slot / 2
        ly = top + plot_h + 16
        if rotate:
            out.append(f'<text transform="translate({cx:.1f} {ly - 6}) rotate(-45)" text-anchor="end" '
                       f'font-size="11" fill="#374151">{_esc(cat)}</text>')
        else:
            out.append(f'<text x="{cx:.1f}" y="{ly}" text-anchor="middle" font-size="11" fill="#374151">'
                       f'{_esc(cat)}</text>')
    out.append(f'<line x1="{left}" x2="{left + plot_w:.1f}" y1="{top + plot_h}" y2="{top + plot_h}" '
               f'stroke="#9ca3af"/>')
    out.append("</svg>")
    return "".join(out)


def _legend(names: list[str], colors: list[str]) -> str:
    items = "".join(f'<span style="--c:{c}">{_esc(n)}</span>' for n, c in zip(names, colors))
    return f'<div class="legend">{items}</div>'


def _cell_color(v, lo, hi, higher_is_better) -> str:
    if v is None or pd.isna(v) or lo is None or hi is None or pd.isna(lo):
        return ""
    t = 0.5 if hi == lo else (v - lo) / (hi - lo)
    if not higher_is_better:
        t = 1 - t
    return f' style="background:{three_color(t, BAD, MID, GOOD)}"'


def _pct_color(v, bound, higher_is_better) -> str:
    if v is None or pd.isna(v):
        return ""
    t = 0.5 + max(-1.0, min(1.0, v / bound)) / 2
    if not higher_is_better:
        t = 1 - t
    return f' style="background:{three_color(t, NEG, ZERO, POS)}"'


def _metric_table(cmp, table: pd.DataFrame, means: pd.Series, pct: bool = False) -> str:
    segs = cmp.segments
    head = "".join(f"<th>Seg {s}</th>" for s in segs)
    rows = []
    cols = [table[s] for s in segs] + [means]
    bound = 0.1
    if pct:
        finite = pd.concat(cols).abs().dropna()
        bound = max(bound, float(finite.max()) if len(finite) else bound)
    for label in cmp.labels:
        cls = ' class="baseline"' if label == cmp.baseline else ""
        cells = []
        for col in cols:
            v = col[label]
            style = (_pct_color(v, bound, cmp.higher_is_better) if pct
                     else _cell_color(v, col.min(), col.max(), cmp.higher_is_better))
            cells.append(f'<td class="num"{style}>{_fmt(v, pct)}</td>')
        rows.append(f'<tr{cls}><td class="label">{_esc(label)}</td><td>{_esc(cmp.info(label)["grade"])}</td>'
                    + "".join(cells) + "</tr>")
    if not pct:
        for name, method in (("Group mean", "mean"), ("Group min", "min"), ("Group max", "max")):
            cells = "".join(f'<td class="num">{_fmt(getattr(c, method)())}</td>' for c in cols)
            rows.append(f'<tr class="stat"><td class="label">{name}</td><td></td>{cells}</tr>')
    return (f'<div class="scroll"><table><thead><tr><th>Test</th><th>Grade</th>{head}<th>Mean</th></tr>'
            f'</thead><tbody>{"".join(rows)}</tbody></table></div>')


def write_html_report(cmp, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(cmp.labels)
    test_colors, seg_colors = palette(n), palette(len(cmp.segments))
    better = "higher" if cmp.higher_is_better else "lower"

    parts = [f"<h1>{_esc(cmp.title)}</h1>",
             f'<p class="meta">Generated {cmp.generated:%Y-%m-%d %H:%M} from {_esc(Path(cmp.db.source).name)}</p>']
    line = (f"{n} tests compared · segments {', '.join(map(str, cmp.segments))} · values in {_esc(cmp.units)} "
            f"· colour scales: green = {better}")
    if cmp.dropped_segments:
        line += f" · segment(s) {', '.join(map(str, cmp.dropped_segments))} omitted (no data)"
    parts.append(f'<p class="meta">{line}</p>')
    if cmp.baseline:
        parts.append(f'<p class="meta">Baseline: <b>{_esc(cmp.baseline)}</b></p>')

    # Summary table
    info = cmp.summary()
    mean_cols = [f"{m} mean" for m in cmp.metrics]
    head = "".join(f"<th>{_esc(m)}<br>mean</th>" for m in cmp.metrics)
    if cmp.baseline:
        head += "".join(f"<th>{_esc(m)}<br>vs baseline</th>" for m in cmp.metrics)
    rows = []
    for i, label in enumerate(cmp.labels, start=1):
        r = info.loc[label]
        cls = ' class="baseline"' if label == cmp.baseline else ""
        cells = "".join(
            f'<td class="num"{_cell_color(r[c], info[c].min(), info[c].max(), cmp.higher_is_better)}>'
            f'{_fmt(r[c])}</td>' for c in mean_cols)
        if cmp.baseline:
            for c in mean_cols:
                base = info.at[cmp.baseline, c]
                v = r[c] / base - 1 if base and not pd.isna(base) else float("nan")
                cells += f'<td class="num"{_pct_color(v, 0.25, cmp.higher_is_better)}>{_fmt(v, True)}</td>'
        rows.append(f'<tr{cls}><td class="num">{i}</td><td class="label">{_esc(label)}</td>'
                    f'<td>{_esc(r["Grade"])}</td><td>{_esc(r["Notes"])}</td>'
                    f'<td class="num">{r["Segments with data"]}</td>{cells}</tr>')
    parts.append('<h2 style="break-before:auto">Tests compared</h2>')
    parts.append(f'<div class="scroll"><table><thead><tr><th>#</th><th>Test</th><th>Grade</th><th>Notes</th>'
                 f'<th>Segments<br>with data</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
    parts.append('<p class="note">Means are taken over the compared segments that have data for that test; '
                 'compare means only between tests with the same segment count.</p>')

    for metric in cmp.metrics:
        table = cmp.table(metric)
        means = cmp.row_means(metric)
        parts.append(f"<h2>{_esc(metric)} ({_esc(cmp.units)})</h2>")
        if cmp.group_by == "segment":
            cats = [f"Seg {s}" for s in cmp.segments]
            series = [(lbl, [table.at[lbl, s] for s in cmp.segments]) for lbl in cmp.labels]
            colors, names = test_colors, cmp.labels
        else:
            cats = list(cmp.labels)
            series = [(f"Seg {s}", [table.at[lbl, s] for lbl in cmp.labels]) for s in cmp.segments]
            colors, names = seg_colors, [f"Seg {s}" for s in cmp.segments]
        parts.append(f'<div class="scroll">{svg_grouped_bars(cats, series, colors, cmp.units)}</div>')
        parts.append(_legend(names, colors))
        parts.append("<h3>Values</h3>" + _metric_table(cmp, table, means))
        pct = cmp.pct_vs_baseline(metric)
        if pct is not None:
            base = means[cmp.baseline]
            pct_means = means / base - 1 if base else means * float("nan")
            parts.append(f"<h3>% difference vs baseline {_esc(cmp.baseline)}</h3>"
                         + _metric_table(cmp, pct, pct_means, pct=True))

    doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width, initial-scale=1">'
           f"<title>{_esc(cmp.title)}</title><style>{_CSS}</style></head>"
           f"<body><main>{''.join(parts)}</main></body></html>")
    path.write_text(doc, encoding="utf-8")
    return path
