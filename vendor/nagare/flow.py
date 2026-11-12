"""The year as a river.

Time runs left to right, from a year ago to today. Every repository is a
current in the river: its width at a given point is how much you worked on it
that week (contributions, smoothed with a Gaussian over neighbouring weeks,
then square-rooted so light projects stay visible beside heavy ones).
The currents are stacked around a centre line (a streamgraph), and each is
drawn as a bundle of ink streamlines. A current keeps the same number of
lines all along, so where it narrows the lines crowd together and where it
dries up they merge into a single thread.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field as dfield


@dataclass
class Current:
    key: str
    label: str | None
    weekly: list            # contributions per week, oldest first
    total: int
    last: str | None
    is_other: bool = False
    width: list = dfield(default_factory=list)    # sampled thickness
    lower: list = dfield(default_factory=list)    # sampled lower edge (screen y, larger = lower)


@dataclass
class River:
    xs: list                # sample x positions
    currents: list          # top to bottom
    week_x: list            # x of each week
    weeks: list             # Monday of each week
    centre: float


def week_index(weeks, date: dt.date):
    monday = date - dt.timedelta(days=date.weekday())
    try:
        return weeks.index(monday)
    except ValueError:
        return None


def build_river(snap, repos, width, height, x0, x1, centre, max_thickness, gap=3.0, step=5):
    observed = dt.date.fromisoformat(snap["observed_on"])
    last_monday = observed - dt.timedelta(days=observed.weekday())
    weeks = [last_monday - dt.timedelta(weeks=51 - i) for i in range(52)]
    # time axis: recent months get more room (slope 0.6 a year ago, 1.4 today)
    warp = lambda t: 0.6 * t + 0.4 * t * t
    week_x = [x0 + (x1 - x0) * warp(i / 51) for i in range(52)]
    table = [(x0 + (x1 - x0) * warp(k / 2000), 51 * k / 2000) for k in range(2001)]

    def week_at(x):
        """Fractional week index at screen x, extended linearly past both ends."""
        if x <= table[0][0]:
            return (x - x0) / ((x1 - x0) * 0.6 / 51)
        if x >= table[-1][0]:
            return 51 + (x - x1) / ((x1 - x0) * 1.4 / 51)
        lo, hi = 0, len(table) - 1
        while hi - lo > 1:
            m = (lo + hi) // 2
            if table[m][0] <= x:
                lo = m
            else:
                hi = m
        (xa, ua), (xb, ub) = table[lo], table[hi]
        return ua + (ub - ua) * (x - xa) / (xb - xa)

    def weekly_from(days):
        out = [0] * 52
        for d in days:
            i = week_index(weeks, dt.date.fromisoformat(d["date"]))
            if i is not None:
                out[i] += d["count"]
        return out

    total_weekly = weekly_from(snap["days"])
    currents = []
    for r in repos:
        w = weekly_from(r.get("days") or [])
        currents.append(Current(f"r{r['id']}", r.get("name"), w, r["contributions"], r.get("last_contribution")))
    rest = [max(0, t - sum(c.weekly[i] for c in currents)) for i, t in enumerate(total_weekly)]
    if sum(rest):
        currents.append(Current("other", None, rest, sum(rest), None, is_other=True))

    # inside-out order by onset: earliest work in the middle, later work outside
    def onset(c):
        tot = sum(c.weekly) or 1
        return sum(i * v for i, v in enumerate(c.weekly)) / tot
    named = sorted((c for c in currents if not c.is_other), key=onset)
    top, bottom = [], []
    for i, c in enumerate(named):
        (top if i % 2 == 0 else bottom).append(c)
    order = top[::-1] + bottom
    order += [c for c in currents if c.is_other]

    xs = [x for x in range(0, width + step, step)]
    sigma = 1.15                       # in weeks, so smoothing is even along the warped axis

    def smooth(series, x):
        u = week_at(x)
        return sum(v * math.exp(-((u - i) ** 2) / (2 * sigma * sigma))
                   for i, v in enumerate(series) if v)

    # square root keeps light projects readable beside heavy ones; order is preserved
    raw = {c.key: [math.sqrt(smooth(c.weekly, x)) for x in xs] for c in order}
    peak = max([sum(raw[c.key][j] for c in order) for j in range(len(xs))] + [1e-9])
    k = max_thickness / peak
    for c in order:
        c.width = [v * k for v in raw[c.key]]

    for j in range(len(xs)):
        total = sum(c.width[j] for c in order) + gap * (len(order) - 1)
        y = centre - total / 2
        for c in order:
            c.lower.append(y + c.width[j])
            y += c.width[j] + gap
    return River(xs, order, week_x, weeks, centre)


def streamlines(river: River, c: Current, n: int, min_width=0.6):
    """n lines spread across the current; each broken where the current dries up."""
    lines = []
    for k in range(n):
        f = (k + 0.5) / n
        rank = abs(k - (n - 1) / 2)          # middle lines survive longest
        need = max(min_width, 2.0 * rank * 2 + 0.6)
        seg = []
        for j, x in enumerate(river.xs):
            w = c.width[j]
            if w < need:
                if len(seg) > 2:
                    lines.append(seg)
                seg = []
                continue
            seg.append((x, c.lower[j] - w * f))
        if len(seg) > 2:
            lines.append(seg)
    return lines


def edges(river: River, c: Current, min_width=0.6):
    """Upper and lower banks of a current, split where it dries up."""
    out = []
    up, lo = [], []
    for j, x in enumerate(river.xs):
        w = c.width[j]
        if w < min_width:
            if len(up) > 2:
                out.append((up, lo))
            up, lo = [], []
            continue
        up.append((x, c.lower[j] - w))
        lo.append((x, c.lower[j]))
    if len(up) > 2:
        out.append((up, lo))
    return out


def swim_path(river: River, c: Current, min_width):
    """Longest stretch of the current's centre line wide enough for a koi."""
    best, cur = [], []
    for j, x in enumerate(river.xs):
        w = c.width[j]
        if w >= min_width:
            cur.append((x, c.lower[j] - w / 2))
        else:
            if len(cur) > len(best):
                best = cur
            cur = []
    if len(cur) > len(best):
        best = cur
    return best
