"""charts.py - the portal's charts, drawn on the server as inline SVG: no chart library, no script, nothing fetched. Any module draws one from rows it already has (BI.Charts.xy / bars / spark).
Colours come from the theme (--accent, --text, --text_muted, --border) with fixed fallbacks; a series gets a stable hue from its name, so the same model or machine has the same colour in every chart. Every point and bar has a <title>, which the browser shows on hover or long press.
Moved from AI Tools' Fleet (viz.py), with: points without a line (scatter), a log scale on either axis, the y axis not forced to start at zero when asked, and the legend laid out under the plot so long names are not cut."""
import math, zlib, html

TEXT, MUTED, GRID, ACCENT = "var(--text, #ddd)", "var(--text_muted, #999)", "var(--border, #555)", "var(--accent, #4aa3df)"

def esc(s) -> str: return html.escape(str(s), quote=True)
def hue(name) -> str: return f"hsl({zlib.crc32(str(name).encode()) % 360},55%,52%)"   # the same name always gets the same colour
def num(v) -> str: return "-" if v is None else f"{v:.3g}" if isinstance(v, float) else str(v)

def _svg(w: int, h: float, body: str, label: str = "") -> str: return f"""<svg viewBox="0 0 {w} {h:.0f}" width="{w}" preserveAspectRatio="xMinYMin meet" style="max-width:100%;height:auto;display:block;font-family:var(--font-main, sans-serif)" role="img" aria-label="{esc(label)}">{body}</svg>"""   # drawn at its own size, smaller where the page is narrower

def _scale(lo: float, hi: float, log: bool, a: float, b: float):
    """value -> position between a and b, linear or log10 (values at or below zero are put at the bottom of a log axis)."""
    f = (lambda v: math.log10(max(v, 1e-12))) if log else (lambda v: v)
    lo, hi = f(lo), f(hi)
    return lambda v: a + (f(v) - lo) / ((hi - lo) or 1) * (b - a)

def _ticks(lo: float, hi: float, log: bool, n: int = 5) -> list:
    """Round values to label an axis: powers of ten on a log axis, steps of 1, 2 or 5 times a power of ten on a linear one."""
    if log: return [10 ** e for e in range(math.floor(math.log10(max(lo, 1e-12))), math.ceil(math.log10(max(hi, 1e-12))) + 1)]
    step = 10 ** math.floor(math.log10(((hi - lo) or abs(hi) or 1) / n))
    step *= next((m for m in (1, 2, 5, 10) if (hi - lo) / (step * m) <= n), 10)
    return [round(math.floor(lo / step) * step + i * step, 12) for i in range(int((hi - lo) / step) + 3) if math.floor(lo / step) * step + i * step <= hi + step * 0.001 and math.floor(lo / step) * step + i * step >= lo - step * 0.001]

def xy(series: list, xlabel: str = "", ylabel: str = "", width: int = 640, height: int = 260, logx: bool = False, logy: bool = False, lines: bool = True, zero: bool = True, xfmt=None) -> str:
    """Points, joined per series unless lines is False: series = [{"name", "points": [(x, y, title)]}]. zero: the y axis starts at 0 (else at the smallest value). xfmt: fn(x) -> the label written under a tick (dates, sizes)."""
    pts = [p for s in series for p in s["points"] if p[0] is not None and p[1] is not None]
    if not pts: return '<div class="status-label">nothing to plot</div>'
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    y0 = min(ys) if (logy or not zero) else min(0, min(ys))
    L, R, T, B = 52, width - 10, 10, height - 34
    X, Y = _scale(min(xs), max(xs), logx, L, R), _scale(y0, max(ys), logy, B, T)
    body = f"""<line x1="{L}" x2="{R}" y1="{B}" y2="{B}" stroke="{GRID}"/><line x1="{L}" x2="{L}" y1="{T}" y2="{B}" stroke="{GRID}"/>"""
    body += "".join(f"""<line x1="{L}" x2="{R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{GRID}" stroke-width="0.4"/><text x="{L - 4}" y="{Y(v) + 3:.1f}" font-size="9" fill="{MUTED}" text-anchor="end">{v:.3g}</text>""" for v in _ticks(y0, max(ys), logy) if y0 <= v <= max(ys) or logy)
    distinct = sorted(set(xs))
    xt = distinct if len(distinct) <= 8 else _ticks(min(xs), max(xs), logx, 6)
    body += "".join(f"""<text x="{X(v):.1f}" y="{B + 12}" font-size="9" fill="{MUTED}" text-anchor="middle">{esc(xfmt(v) if xfmt else f"{v:g}")}</text>""" for v in xt if min(xs) <= v <= max(xs))
    body += f"""<text x="{(L + R) / 2}" y="{B + 25}" font-size="10" fill="{MUTED}" text-anchor="middle">{esc(xlabel)}{" (log)" if logx else ""}</text><text x="11" y="{(T + B) / 2}" font-size="10" fill="{MUTED}" transform="rotate(-90 11 {(T + B) / 2})" text-anchor="middle">{esc(ylabel)}{" (log)" if logy else ""}</text>"""
    legend, lx, ly = "", L, height + 4
    for s in series:
        sp, col = sorted((p for p in s["points"] if p[0] is not None and p[1] is not None), key=lambda p: p[0]), hue(s["name"])
        if lines and len(sp) > 1: body += f"""<polyline points="{" ".join(f"{X(p[0]):.1f},{Y(p[1]):.1f}" for p in sp)}" fill="none" stroke="{col}" stroke-width="1.5"/>"""
        body += "".join(f"""<circle cx="{X(p[0]):.1f}" cy="{Y(p[1]):.1f}" r="3.2" fill="{col}"><title>{esc(s["name"])}: {esc(p[2])}</title></circle>""" for p in sp)
        w = 16 + 6 * len(str(s["name"])[:40])
        if lx + w > R: lx, ly = L, ly + 14
        legend += f"""<rect x="{lx}" y="{ly}" width="9" height="9" fill="{col}"/><text x="{lx + 13}" y="{ly + 8}" font-size="10" fill="{TEXT}">{esc(str(s["name"])[:40])}</text>"""
        lx += w + 10
    return _svg(width, ly + 16, body + legend, f"{ylabel} by {xlabel}")

def bars(items: list, width: int = 560, unit: str = "") -> str:
    """Horizontal bars: [(label, value, title)], scaled to the largest value."""
    if not items: return ""
    top, left, row = max((v or 0) for _, v, _ in items) or 1, 190, 18
    body = "".join(f"""<g><title>{esc(title)}</title><text x="{left - 6}" y="{i * row + 12}" font-size="11" fill="{TEXT}" text-anchor="end">{esc(str(label)[:30])}</text><rect x="{left}" y="{i * row + 3}" width="{max(1, (v or 0) / top * (width - left - 70)):.1f}" height="{row - 6}" rx="2" fill="{hue(label)}" fill-opacity="0.8"/><text x="{left + max(1, (v or 0) / top * (width - left - 70)) + 4:.1f}" y="{i * row + 12}" font-size="10" fill="{MUTED}">{num(v)}{esc(unit)}</text></g>""" for i, (label, v, title) in enumerate(items))
    return _svg(width, len(items) * row + 4, body, "bars")

def spark(values: list, width: int = 220, height: int = 28, title: str = "") -> str:
    """A row of small bars, one per value: how something went over time at a glance."""
    if not values: return ""
    top, w = max(values) or 1, width / len(values)
    body = "".join(f"""<rect x="{i * w:.1f}" y="{height - max(1, v / top * height):.1f}" width="{max(1, w - 1):.1f}" height="{max(1, v / top * height):.1f}" fill="{ACCENT}" fill-opacity="{0.35 if v == 0 else 0.85}"><title>{v}</title></rect>""" for i, v in enumerate(values))
    return f"""<span title="{esc(title)}">{_svg(width, height, body, title)}</span>"""

class Charts:
    """The charts as one name for modules: BI.Charts.xy(...), BI.Charts.bars(...), BI.Charts.spark(...), BI.Charts.hue(name)."""
    xy, bars, spark, hue, esc = staticmethod(xy), staticmethod(bars), staticmethod(spark), staticmethod(hue), staticmethod(esc)
