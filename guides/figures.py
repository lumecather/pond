"""Guide illustrations: candles and patterns drawn as SVG in code.

A guide inserts a picture with a [[fig:name]] line (names are the keys of FIGURES below).
Colors come from the app's CSS variables, so pictures follow the light and dark themes.
"""
from html import escape

W, H = 340, 176
TOP, BOTTOM = 36, H - 14


def _bars(path, seed=1):
    """Closing prices -> candles (open = previous close) with small wicks."""
    out = []
    for i in range(1, len(path)):
        o, c = path[i - 1], path[i]
        body = abs(c - o)
        up = 0.25 * body + 0.5 * ((i * 7 + seed * 3) % 5) / 5 + 0.15
        dn = 0.25 * body + 0.5 * ((i * 5 + seed * 11) % 5) / 5 + 0.15
        out.append((o, max(o, c) + up, min(o, c) - dn, c))
    return out


def _panel(x0, width, p):
    bars = p.get("bars") or _bars(p["path"], p.get("seed", 1))
    lines, marks = p.get("lines", []), p.get("marks", [])
    values = [v for b in bars for v in (b[1], b[2])]
    values += [l[1] for l in lines if l[0] == "h"] + [v for l in lines if l[0] == "seg" for v in (l[2], l[4])]
    lo, hi = min(values), max(values)
    pad = (hi - lo) * 0.08 or 1
    lo, hi = lo - pad, hi + pad
    y = lambda v: BOTTOM - (v - lo) / (hi - lo) * (BOTTOM - TOP)
    left, right = x0 + 10, x0 + width - 10
    step = (right - left) / len(bars)
    bw = min(step * 0.62, 16)
    cx = lambda i: left + step * (i + 0.5)
    s, labels = [], []
    if p.get("title"):
        s.append(f'<text class="t ttl" x="{x0 + width / 2:.0f}" y="14" text-anchor="middle">{escape(p["title"])}</text>')
    for kind, *a in lines:
        if kind == "h":  # horizontal level: value, label
            s.append(f'<line class="lvl" x1="{left}" x2="{right}" y1="{y(a[0]):.1f}" y2="{y(a[0]):.1f}"/>')
            if len(a) > 1:  # level labels are drawn last, on top of the candles
                labels.append(f'<text class="t" x="{left + 2}" y="{y(a[0]) - 4:.1f}">{escape(a[1])}</text>')
        else:  # segment: candle, value, candle, value
            s.append(f'<line class="trend" x1="{cx(a[0]):.1f}" y1="{y(a[1]):.1f}" x2="{cx(a[2]):.1f}" y2="{y(a[3]):.1f}"/>')
    for i, (o, h, l, c) in enumerate(bars):
        cls = "up" if c >= o else "dn"
        top, height = y(max(o, c)), max(abs(y(o) - y(c)), 1.5)
        hl = " hl" if i in p.get("hl", ()) else ""
        s.append(f'<g class="{cls}{hl}"><line x1="{cx(i):.1f}" x2="{cx(i):.1f}" y1="{y(h):.1f}" y2="{y(l):.1f}"/>'
                 f'<rect x="{cx(i) - bw / 2:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{height:.1f}" rx="1"/></g>')
    for i, v, text, *pos in marks:  # label at a candle: index, value, text, [above|below]
        dy = -8 if (pos[0] if pos else "above") == "above" else 14
        s.append(f'<text class="t mk" x="{cx(i):.1f}" y="{y(v) + dy:.1f}" text-anchor="middle">{escape(text)}</text>')
    return "".join(s + labels)


def _figure(panels, caption):
    width = W / len(panels)
    body = "".join(_panel(i * width, width, p) for i, p in enumerate(panels))
    seps = "".join(f'<line class="sep" x1="{i * width:.0f}" x2="{i * width:.0f}" y1="6" y2="{H - 6}"/>' for i in range(1, len(panels)))
    return (f'<figure class="fig"><svg viewBox="0 0 {W} {H}" role="img" aria-label="{escape(caption)}">{seps}{body}</svg>'
            f"<figcaption>{escape(caption)}</figcaption></figure>")


def _anatomy():
    def candle(x, o, c, cls, labels, side):
        hi, lo = 22, 150
        s = (f'<g class="{cls}"><line x1="{x}" x2="{x}" y1="{hi}" y2="{lo}"/>'
             f'<rect x="{x - 15}" y="{min(o, c)}" width="30" height="{abs(o - c)}" rx="2"/></g>')
        for yy, text in labels:
            tx, anchor, x1, x2 = (x + 62, "start", x + 17, x + 58) if side == "r" else (x - 62, "end", x - 17, x - 58)
            s += f'<line class="lead" x1="{x1}" x2="{x2}" y1="{yy}" y2="{yy}"/><text class="t" x="{tx}" y="{yy + 4}" text-anchor="{anchor}">{text}</text>'
        return s
    body = candle(118, 122, 52, "up", [(22, "high"), (52, "close"), (122, "open"), (150, "low")], "l")
    body += candle(222, 52, 122, "dn", [(22, "high"), (52, "open"), (122, "close"), (150, "low")], "r")
    body += '<text class="t ttl" x="118" y="170" text-anchor="middle">price went up</text><text class="t ttl" x="222" y="170" text-anchor="middle">price went down</text>'
    caption = "A candle: the thick part is the body (open to close), the thin lines are the wicks (high and low)."
    return f'<figure class="fig"><svg viewBox="0 0 {W} {H}" role="img" aria-label="{caption}">{body}</svg><figcaption>{caption}</figcaption></figure>'


FIGURES = {
    "candle-anatomy": _anatomy,
    "candle-shapes": lambda: _figure([
        {"title": "strong rise", "bars": [(10, 20.5, 9.5, 20)], "lines": [("h", 6), ("h", 24)]},
        {"title": "calm", "bars": [(14.5, 16.5, 13.5, 15.5)], "lines": [("h", 6), ("h", 24)]},
        {"title": "bought back", "bars": [(17, 19.5, 8, 18.5)], "lines": [("h", 6), ("h", 24)]},
        {"title": "sold off", "bars": [(13, 22, 10.5, 11.5)], "lines": [("h", 6), ("h", 24)]},
    ], "A long body is a confident move. A short one means the market is undecided. A long wick means the price went there but was pushed back."),
    "model-hammer-star": lambda: _figure([
        {"title": "hammer", "bars": [(20, 20.5, 17.5, 18), (18, 18.3, 15.6, 16), (16, 16.2, 13.8, 14), (14, 14.6, 9.5, 14.4), (14.4, 17, 14.2, 16.6), (16.6, 18.6, 16.2, 18.2)],
         "hl": [3]},
        {"title": "shooting star", "bars": [(10, 12.2, 9.6, 12), (12, 14.3, 11.7, 14), (14, 16.4, 13.8, 16), (16, 20.6, 15.6, 15.8), (15.8, 16, 13, 13.4), (13.4, 13.8, 11.2, 11.6)],
         "hl": [3]},
    ], "A hammer shows up at the bottom after a fall, a shooting star at the top after a rise. Both say the move is running out of steam."),
    "model-engulfing": lambda: _figure([
        {"title": "bullish engulfing", "bars": [(20, 20.4, 17.6, 18), (18, 18.3, 15.7, 16), (16, 16.3, 14.6, 15), (14.7, 18, 14.3, 17.6), (17.6, 19.8, 17.2, 19.4)],
         "hl": [2, 3]},
        {"title": "bearish engulfing", "bars": [(10, 12.3, 9.7, 12), (12, 14.2, 11.6, 14), (14, 15.4, 13.7, 15), (15.3, 15.7, 12, 12.4), (12.4, 12.8, 10.2, 10.6)],
         "hl": [2, 3]},
    ], "Engulfing: the new candle's body fully covers the previous body and points the other way."),
    "model-doji": lambda: _figure([
        {"title": "doji", "bars": [(10, 12.3, 9.7, 12), (12, 14.3, 11.7, 14), (14, 16.2, 13.6, 16), (16, 17.6, 14.6, 16.1), (16.1, 16.4, 13.8, 14.2), (14.2, 14.5, 12, 12.4)],
         "hl": [3], "marks": [(3, 17.6, "open ≈ close", "above")]},
    ], "A doji is a candle with almost no body: buyers and sellers drew. On its own it means little; the next candle matters."),
    "trend": lambda: _figure([
        {"title": "up", "path": [10, 12, 11, 13.5, 12.5, 15, 14, 16.5, 15.5, 18], "lines": [("seg", 1, 10, 7, 14.6)], "seed": 2},
        {"title": "down", "path": [18, 16, 17, 14.5, 15.5, 13, 14, 11.5, 12.5, 10], "lines": [("seg", 1, 17.9, 7, 13.4)], "seed": 3},
        {"title": "sideways", "path": [14, 15.5, 13.5, 15, 13, 15.2, 13.4, 15, 13.6, 14.5], "lines": [("h", 16.2), ("h", 12.4)], "seed": 4},
    ], "Uptrend: each pullback ends higher than the last. Downtrend: each bounce ends lower. Sideways: the price moves in a range."),
    "levels": lambda: _figure([
        {"path": [14, 11.5, 13, 16, 18.5, 17, 14, 11.6, 13.5, 16.5, 18.4, 16, 13, 11.7, 14, 17, 18.3, 16.5],
         "lines": [("h", 19.3, "resistance: sellers are here"), ("h", 10.6, "support: buyers are here")], "seed": 5},
    ], "Levels: the price turns around at the same mark again and again. The more touches, the stronger the level."),
    "breakout": lambda: _figure([
        {"path": [12, 14, 12.6, 14.6, 13, 14.8, 13.4, 14.9, 14.2, 17, 18.2, 16.4, 15.4, 17, 19, 20.5],
         "lines": [("h", 15.2, "level: was resistance, now support")], "marks": [(9, 17.6, "breakout", "above"), (12, 15, "retest", "below")], "seed": 6},
    ], "Breakout: the price clears the level, comes back to test it from above and keeps going."),
    "false-breakout": lambda: _figure([
        {"path": [12, 14, 12.6, 14.6, 13, 14.8, 13.4, 14.9, 16.2, 14.4, 13, 11.8, 12.6, 11, 10],
         "lines": [("h", 15.2, "resistance")], "marks": [(8, 16.9, "false breakout", "above")], "seed": 7},
    ], "False breakout: the price pokes past the level and comes right back. Whoever bought the breakout is now at a loss."),
    "double": lambda: _figure([
        {"title": "double top", "path": [10, 13, 16, 18.5, 16.5, 14.5, 16.5, 18.4, 16, 13.8, 12, 10.5],
         "lines": [("h", 19.4), ("h", 14)], "seed": 8},
        {"title": "double bottom", "path": [19, 16, 13, 10.6, 12.6, 14.6, 12.6, 10.7, 13, 15.4, 17, 18.6],
         "lines": [("h", 9.7), ("h", 15.1)], "seed": 9},
    ], "Double top: two failed attempts to go higher; expect a drop once the lower line breaks. A double bottom is the mirror image."),
    "head-shoulders": lambda: _figure([
        {"path": [10, 12.5, 15, 13.2, 12, 15, 18.6, 16, 12.2, 13.6, 15.2, 13.4, 12, 10.4, 9],
         "lines": [("h", 11.6, "neckline")], "marks": [(1, 15.6, "shoulder", "above"), (5, 19.3, "head", "above"), (9, 15.8, "shoulder", "above")], "seed": 10},
    ], "Head and shoulders: three peaks, the middle one highest. The sell signal is a break below the neckline."),
    "triangle-flag": lambda: _figure([
        {"title": "triangle", "path": [10, 18, 11.5, 17, 12.6, 16.2, 13.4, 15.6, 14, 17.5, 19.5],
         "lines": [("seg", 0, 19, 8, 15.4), ("seg", 0, 10.2, 8, 13.6)], "seed": 11},
        {"title": "flag", "path": [9, 11.5, 14, 16.5, 18, 17.2, 17.6, 16.6, 17, 16, 16.5, 18.5, 20.5],
         "lines": [("seg", 4, 19, 10, 17.4), ("seg", 4, 17.2, 10, 15.6)], "seed": 12},
    ], "Triangle: the price squeezes, then breaks out. Flag: a short pause after a sharp rise, then the move continues."),
    "plan": lambda: _figure([
        {"path": [11, 12.4, 11.6, 13, 12.2, 13.6, 13, 14], "lines": [("h", 18, "take profit: +4"), ("h", 14, "entry"), ("h", 12, "stop-loss: −2")], "seed": 13},
    ], "A trade plan before entering: where I take profit and where I cut the loss. Here the reward is twice the risk (2:1)."),
}


def render(name: str) -> str:
    build = FIGURES.get(name)
    return build() if build else ""
