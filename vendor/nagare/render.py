"""Snapshot -> animated SVG."""

from __future__ import annotations

import datetime as dt
import math

from . import flow
from .koi import TAU, clamp, fmt, koi_svg, pt, seeded, smooth_open

W, H = 900, 360
MAX_KOI = 8

PAPER = ":root{--paper:#f4f0e8;--ink:#1d252b;--red:#c2402e;--wash:#1d252b;--shade:#1d252b}"
NIGHT = ":root{--paper:#1d252b;--ink:#f4f0e8;--red:#d65a43;--wash:#f4f0e8;--shade:#0b0f12}"
THEMES = {
    "auto": PAPER + "@media (prefers-color-scheme:dark){" + NIGHT + "}",
    "paper": PAPER,
    "night": NIGHT,
}

STYLE = """
.bg{fill:var(--paper)}
.vg stop{stop-color:var(--shade)}
.paperfill{fill:var(--paper);stroke:var(--ink)}
.inkfill{fill:var(--ink);stroke:var(--ink)}
.nostroke{stroke:none}
.fin{fill:var(--ink);fill-opacity:.15;stroke:var(--ink);stroke-opacity:.3;stroke-width:.7}
.ray,.line,.stream,.bank{fill:none;stroke:var(--ink)}
.bank{stroke-width:.8;stroke-opacity:.55}
.ray{stroke-opacity:.32}
.line{stroke-opacity:.35}
.stream{stroke-width:.55;stroke-linecap:round;stroke-dasharray:90 3;animation:flow 10s linear infinite}
@keyframes flow{to{stroke-dashoffset:-93}}
.wash{fill:var(--wash);fill-opacity:.62}
.red{fill:var(--red);fill-opacity:.92}
.eye{fill:var(--ink)}
.shadow{fill:var(--shade)}
.ripple{fill:none;stroke:var(--ink);stroke-width:.7}
.label{fill:var(--ink);fill-opacity:.62;font:10px 'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;letter-spacing:.04em;paint-order:stroke;stroke:var(--paper);stroke-width:3px;stroke-opacity:.85}
.label.other{fill-opacity:.4;font-style:italic}
.month{fill:var(--ink);fill-opacity:.42;font:10px 'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;letter-spacing:.06em}
.cap{fill:var(--ink);fill-opacity:.62;font:11px 'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;letter-spacing:.06em}
"""


def ripple_svg(x, y, i, n):
    dur = 7.0
    out = []
    for ring in range(2):
        begin = -(i * dur / max(n, 1)) + ring * 0.7
        out.append(
            f'<circle class="ripple" cx="{fmt(x)}" cy="{fmt(y)}" r="0" stroke-opacity="0">'
            f'<animate attributeName="r" values="1;{20 - ring*7}" dur="{dur}s" begin="{begin:.1f}s" '
            f'repeatCount="indefinite" calcMode="spline" keySplines="0.2 0.6 0.4 1"/>'
            f'<animate attributeName="stroke-opacity" values="0;0.35;0" keyTimes="0;0.06;1" dur="{dur}s" '
            f'begin="{begin:.1f}s" repeatCount="indefinite"/></circle>')
    return "".join(out)


def render(snap: dict, theme: str = "auto") -> str:
    """theme: auto (follows the reader), paper or night."""
    login = snap["login"]
    observed = snap["observed_on"]
    days = sorted(snap["days"], key=lambda d: d["date"])
    rng = seeded("nagare", login)

    # the profile repository (named like the login) is README upkeep, not a project
    repos = sorted((r for r in snap["repos"] if r["contributions"] > 0 and (r.get("name") or "").lower() != login.lower()),
                   key=lambda r: -r["contributions"])[:MAX_KOI]
    x0, x1 = 40, W - 64
    river = flow.build_river(snap, repos, W, H, x0, x1, centre=H / 2 - 14, max_thickness=0.6 * H, gap=7.0)

    # ---- the water
    # what GitHub counts but cannot attribute: mostly private work, if the snapshot says so
    other = next((c for c in river.currents if c.is_other), None)
    other_total = sum(other.weekly) if other else 0
    private = snap.get("private_contributions") or 0
    other_label = "private work" if other_total and private >= 0.6 * other_total else "other activity"
    water, labels, label_boxes = [], [], []
    named_i = 0
    for c in river.currents:
        mw = max(c.width) if c.width else 0
        if mw < 0.6:
            continue
        n = int(clamp(round(mw / 7), 2, 10))
        inner_op = (0.42, 0.27)[named_i % 2]     # alternate tone so neighbours read apart
        named_i += 1
        for line in flow.streamlines(river, c, n):
            pts = line[::2] + ([line[-1]] if len(line) % 2 == 0 else [])
            water.append(f'<path class="stream" stroke-opacity="{inner_op}" d="{smooth_open(pts)}"/>')
        label = other_label if c.is_other else c.label
        if True:
            if label and mw >= 6:
                # try the widest points first, skip spots that would overlap another label
                half = len(label) * 3.1 + 4
                for j in sorted(range(len(river.xs)), key=lambda j: -c.width[j])[::3][:40]:
                    if c.width[j] < 6:
                        break
                    x = river.xs[j]
                    if not (half + 10 <= x <= W - half - 10):
                        continue
                    y = c.lower[j] - c.width[j] / 2 + 3.5
                    box = (x - half, y - 10, x + half, y + 3)
                    if all(box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3] for b in label_boxes):
                        label_boxes.append(box)
                        cls = "label other" if c.is_other else "label"
                        labels.append(f'<text class="{cls}" x="{fmt(x)}" y="{fmt(y)}" text-anchor="middle">{label}</text>')
                        break

    months = []
    seen = set()
    for wi, (wk, wx) in enumerate(zip(river.weeks, river.week_x)):
        first = wk + dt.timedelta(days=(7 - wk.weekday()) % 7)
        m = (wk + dt.timedelta(days=6)).replace(day=1)
        if m in seen or not (wk <= m <= wk + dt.timedelta(days=6)):
            continue
        seen.add(m)
        step = river.week_x[min(wi + 1, 51)] - river.week_x[min(wi, 50)]
        x = wx + (m - wk).days / 7 * step
        if x > W - 90:
            continue
        months.append(f'<text class="month" x="{fmt(x)}" y="{H - 40}">{m:%b}</text>')

    # ---- the koi
    quiet = 0
    for d in reversed(days):
        if d["count"]:
            break
        quiet += 1
    calm = clamp((quiet - 7) / 21, 0, 1)

    by_key = {c.key: c for c in river.currents}
    # vermilion marks the project touched most recently (ties: the busier one)
    red_id = max(repos, key=lambda r: (r.get("last_contribution") or "", r["contributions"]))["id"] if repos else None
    patterns = iter(("showa", "sanke", "tancho", "bekko", "sanke", "showa", "kohaku", "bekko"))
    swimmers = [(r, by_key.get(f"r{r['id']}")) for r in repos]
    if other and other_total:
        last = next((wk + dt.timedelta(days=6) for wk, v in zip(reversed(river.weeks), reversed(other.weekly)) if v), None)
        last = min(last, dt.date.fromisoformat(observed)).isoformat() if last else None
        swimmers.append(({"id": "other", "contributions": other_total, "last_contribution": last}, other))
    swimmers = [(r, c) for r, c in swimmers if c]
    # size and depth are relative to this account: its biggest project gets the biggest koi,
    # its most recent one swims at the surface
    def days_since(r):
        return max(0, (dt.date.fromisoformat(observed) - dt.date.fromisoformat(r.get("last_contribution") or observed)).days)
    max_c = max([r["contributions"] for r, _ in swimmers] + [1])
    min_since = min([days_since(r) for r, _ in swimmers] + [0])
    koi_items = []
    for i, (r, c) in enumerate(swimmers):
        krng = seeded("koi", r["id"])
        size = clamp(math.log1p(r["contributions"]) / math.log1p(max_c), 0, 1)
        scale = 0.3 + 0.22 * size
        path = flow.swim_path(river, c, min_width=2.5)
        if len(path) < 2:
            continue
        pts = path[::3] + ([path[-1]] if (len(path) - 1) % 3 else [])
        length = sum(math.dist(pts[q], pts[q + 1]) for q in range(len(pts) - 1))
        if length < 60:
            continue
        since = max(0, days_since(r) - min_since)
        # a week off is still the surface; half a year away is the bottom
        depth = clamp((math.log2(1 + since) - 3) / (math.log2(181) - 3) + 0.2 * calm, 0, 1)
        speed = (24 - 9 * depth) * krng.uniform(0.85, 1.15)
        dur = length / speed
        begin = -krng.random() * dur
        fade = clamp(45 / length, 0.04, 0.3)
        motion = (f'<animateMotion dur="{dur:.1f}s" begin="{begin:.1f}s" repeatCount="indefinite" '
                  f'rotate="auto" path="{smooth_open(pts)}"/>')
        fader = (f'<animate attributeName="opacity" dur="{dur:.1f}s" begin="{begin:.1f}s" repeatCount="indefinite" '
                 f'values="0;1;1;0" keyTimes="0;{fade:.3f};{1 - fade:.3f};1"/>')
        top = r["id"] == red_id
        is_other = r["id"] == "other"
        kind = "bekko" if is_other else "kohaku" if top else next(patterns)
        koi, shadow = koi_svg(
            f"k{i}", motion, scale=scale, depth=depth,
            beat=clamp(2.0 * 24 / speed, 1.4, 3.2), amp=krng.uniform(0.5, 0.6),
            kind=kind, main_tone="red" if top else "wash",
            body_dark=is_other or (not top and kind == "bekko" and i % 2 == 0))
        koi_items.append((depth, f"<g>{fader}{koi}</g>", f"<g>{fader}{shadow}</g>"))
    koi_items.sort(key=lambda t: -t[0])

    # ---- surface: ripples for the last week at today's edge
    recent = [d for d in days[-7:] if d["count"] > 0]
    ripples = []
    for i, d in enumerate(recent):
        rr = seeded("ripple", login, d["date"])
        wd = dt.date.fromisoformat(d["date"]).weekday()
        ripples.append(ripple_svg(x1 + rr.uniform(-30, 10), river.centre + (wd - 3) * 22 + rr.uniform(-8, 8), i, len(recent)))

    total = sum(d["count"] for d in days[-365:])
    caption = f"{login}  ·  a year of work as a river, oldest on the left  ·  {total:,} contributions"
    if quiet >= 14:
        caption += f"  ·  still water, {quiet} quiet days"

    defs = (
        '<radialGradient id="vg" class="vg" cx="50%" cy="50%" r="75%">'
        '<stop offset="55%" stop-opacity="0"/><stop offset="100%" stop-opacity=".09"/></radialGradient>'
        '<linearGradient id="edgefade" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        '<stop offset=".06" stop-color="#fff"/><stop offset=".94" stop-color="#fff"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        f'<mask id="fade"><rect width="{W}" height="{H}" fill="url(#edgefade)"/></mask>'
        '<filter id="shadowblur" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="3"/></filter>'
        '<filter id="rough" x="-10%" y="-10%" width="120%" height="120%">'
        '<feTurbulence type="fractalNoise" baseFrequency=".12" numOctaves="2" seed="7"/>'
        '<feDisplacementMap in="SourceGraphic" scale="2"/></filter>'
        + "".join(f'<filter id="d{i}" x="-20%" y="-20%" width="140%" height="140%">'
                  f'<feGaussianBlur stdDeviation="{0.4 * i:.2f}"/></filter>' for i in range(1, 4))
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'role="img" aria-label="nagare: {login}\'s year of work as a river with koi">'
        f'<title>{login} — nagare</title><style>{THEMES[theme]}{STYLE}</style><defs>{defs}</defs>'
        f'<rect class="bg" width="{W}" height="{H}"/>'
        f'<g mask="url(#fade)">{"".join(water)}</g>'
        f'{"".join(labels)}'
        f'<g filter="url(#shadowblur)">{"".join(s for _, _, s in koi_items)}</g>'
        f'{"".join(k for _, k, _ in koi_items)}'
        f'{"".join(ripples)}'
        f'{"".join(months)}'
        f'<rect width="{W}" height="{H}" fill="url(#vg)"/>'
        f'<text class="cap" x="22" y="{H - 18}">{caption}</text>'
        f'</svg>'
    )
