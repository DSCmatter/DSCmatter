"""Koi geometry: a length-preserving travelling-wave spine, fins, patterns,
and SMIL keyframes for one swimming body."""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass

TAU = 2 * math.pi
KEYFRAMES = 14           # body poses per tail beat


# ----------------------------------------------------------------- utilities

def seeded(*parts) -> random.Random:
    h = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return random.Random(int(h[:16], 16))


def clamp(x, a, b):
    return max(a, min(b, x))


def fmt(v: float) -> str:
    s = f"{v:.1f}"
    return "0" if s in ("0.0", "-0.0") else s.rstrip("0").rstrip(".")


def pt(p) -> str:
    return f"{fmt(p[0])} {fmt(p[1])}"


def mid(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def smooth_closed(pts) -> str:
    n = len(pts)
    mids = [mid(pts[i], pts[(i + 1) % n]) for i in range(n)]
    d = [f"M{pt(mids[-1])}"]
    for i in range(n):
        d.append(f"Q{pt(pts[i])} {pt(mids[i])}")
    return "".join(d) + "Z"


def smooth_open(pts) -> str:
    if len(pts) == 2:
        return f"M{pt(pts[0])}L{pt(pts[1])}"
    d = [f"M{pt(pts[0])}"]
    for i in range(1, len(pts) - 1):
        m = pts[i + 1] if i == len(pts) - 2 else mid(pts[i], pts[i + 1])
        d.append(f"Q{pt(pts[i])} {pt(m)}")
    return "".join(d)


# ------------------------------------------------------------------ the body

BODY_LEN = 100.0          # spine length, head to peduncle, in local units
HALF_W = 16.5             # maximum half width


def halfwidth(s: float) -> float:
    if s < 0.27:
        u = s / 0.27
        return HALF_W * math.sqrt(max(0.0, 1 - (1 - u) ** 2)) ** 0.9
    u = (s - 0.27) / 0.73
    return HALF_W * (1 - 0.83 * u ** 1.6)


SPINE_S = [(i / 25) ** 1.25 for i in range(26)]


@dataclass
class Frame:
    p: list      # spine points
    t: list      # unit tangents, pointing tailward
    n: list      # unit normals (left side)
    w: list      # half widths

    def at(self, s: float):
        s = clamp(s, 0.0, 1.0)
        for i in range(1, len(SPINE_S)):
            if SPINE_S[i] >= s:
                break
        a, b = SPINE_S[i - 1], SPINE_S[i]
        f = (s - a) / (b - a) if b > a else 0
        lerp = lambda u, v: (u[0] + (v[0] - u[0]) * f, u[1] + (v[1] - u[1]) * f)
        return (lerp(self.p[i - 1], self.p[i]), lerp(self.t[i - 1], self.t[i]),
                lerp(self.n[i - 1], self.n[i]), self.w[i - 1] + (self.w[i] - self.w[i - 1]) * f)

    def sv(self, s: float, v: float):
        p, _, n, w = self.at(s)
        return (p[0] + n[0] * w * v, p[1] + n[1] * w * v)


def make_frame(phase: float, amp: float, wavelength: float) -> Frame:
    """Spine as a travelling bending wave, head to tail, length-preserving."""
    def heading(s):
        return amp * (0.07 + 0.93 * s ** 1.5) * math.sin(TAU * (phase - s / wavelength))

    pts, tans = [(0.0, 0.0)], []
    for i in range(1, len(SPINE_S)):
        s0, s1 = SPINE_S[i - 1], SPINE_S[i]
        th = math.pi + heading((s0 + s1) / 2)
        ds = (s1 - s0) * BODY_LEN
        x, y = pts[-1]
        pts.append((x + ds * math.cos(th), y + ds * math.sin(th)))
    for s in SPINE_S:
        th = math.pi + heading(s)
        tans.append((math.cos(th), math.sin(th)))
    ws = [halfwidth(s) for s in SPINE_S]

    # keep the body centred on its trajectory and its mean heading level
    tot = sum(ws)
    cx = sum(p[0] * w for p, w in zip(pts, ws)) / tot
    cy = sum(p[1] * w for p, w in zip(pts, ws)) / tot
    mean_h = sum(heading(s) * w for s, w in zip(SPINE_S, ws)) / tot
    c, s_ = math.cos(-mean_h), math.sin(-mean_h)
    rot = lambda v: (v[0] * c - v[1] * s_, v[0] * s_ + v[1] * c)
    pts = [rot((x - cx + 22, y - cy)) for x, y in pts]   # +22: nose leads the pivot
    tans = [rot(t) for t in tans]
    norms = [(-t[1], t[0]) for t in tans]
    return Frame(pts, tans, norms, ws)


def rotate(v, a):
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def add(p, v, k=1.0):
    return (p[0] + v[0] * k, p[1] + v[1] * k)


# ------------------------------------------------------------------ patterns

@dataclass
class Blob:
    s: float
    v: float
    rs: float
    rv: float
    tone: str           # "wash" | "sumi" | "red"
    wobble: tuple


def blob(rng, s, v, rs, rv, tone):
    return Blob(s, v, rs, rv, tone,
                (rng.uniform(0.08, 0.2), rng.randint(2, 4), rng.uniform(0, TAU),
                 rng.uniform(0.04, 0.12), rng.randint(4, 6), rng.uniform(0, TAU)))


def make_pattern(rng: random.Random, kind: str, main_tone: str):
    b = []
    if kind in ("kohaku", "sanke"):
        s = rng.uniform(0.07, 0.14)
        while s < 0.82:
            rs = rng.uniform(0.07, 0.14)
            b.append(blob(rng, s + rs * 0.8, rng.uniform(-0.35, 0.35), rs,
                          rng.uniform(0.75, 1.35), main_tone))
            s += rs * 2 + rng.uniform(0.04, 0.12)
        if kind == "sanke":
            for _ in range(rng.randint(3, 6)):
                b.append(blob(rng, rng.uniform(0.3, 0.85), rng.uniform(-0.8, 0.8),
                              rng.uniform(0.02, 0.045), rng.uniform(0.18, 0.4), "sumi"))
    elif kind == "showa":
        b.append(blob(rng, 0.1, rng.uniform(-0.3, 0.3), 0.08, 1.1, "sumi"))
        for _ in range(rng.randint(3, 4)):
            side = rng.choice((-1, 1))
            b.append(blob(rng, rng.uniform(0.25, 0.85), side * rng.uniform(0.3, 0.8),
                          rng.uniform(0.07, 0.13), rng.uniform(0.6, 1.0), "sumi"))
        for _ in range(2):
            b.append(blob(rng, rng.uniform(0.2, 0.7), rng.uniform(-0.3, 0.3),
                          rng.uniform(0.06, 0.1), rng.uniform(0.5, 0.8), main_tone))
    elif kind == "bekko":
        for _ in range(rng.randint(4, 7)):
            b.append(blob(rng, rng.uniform(0.2, 0.85), rng.uniform(-0.4, 0.4),
                          rng.uniform(0.025, 0.05), rng.uniform(0.25, 0.5), "sumi"))
    elif kind == "tancho":
        b.append(Blob(0.115, 0.0, 0.045, 0.62, main_tone, (0.04, 3, 0.0, 0.0, 4, 0.0)))
    return b


def blob_points(fr: Frame, bl: Blob, m=16):
    a1, k1, p1, a2, k2, p2 = bl.wobble
    out = []
    for i in range(m):
        a = TAU * i / m
        r = 1 + a1 * math.sin(k1 * a + p1) + a2 * math.sin(k2 * a + p2)
        s = clamp(bl.s + bl.rs * r * math.cos(a), 0.035, 0.975)
        v = clamp(bl.v + bl.rv * r * math.sin(a), -0.96, 0.96)
        out.append(fr.sv(s, v))
    return out


# --------------------------------------------------------------- one pose

def fins(fr: Frame, phase: float, amp: float, wavelength: float, rays_only=False):
    """Caudal, pectoral and pelvic fins as (fill path, ray path)."""
    fill, rays = [], []

    # caudal fin: a forked fan that lags behind the body wave
    root, tan, nor, w = fr.at(1.0)
    base = math.atan2(tan[1], tan[0])
    flex = amp * 0.75 * math.sin(TAU * (phase - 1.2 / wavelength))
    tips, mids, roots = [], [], []
    R = 15
    for j in range(R):
        u = -1 + 2 * j / (R - 1)
        length = 40 * (0.5 + 0.5 * abs(u) ** 1.5)
        r0 = add(root, nor, w * 0.9 * u)
        a_mid = base + u * 0.5 + flex * 0.45
        a_tip = base + u * 0.78 + flex
        m = add(r0, (math.cos(a_mid), math.sin(a_mid)), length * 0.5)
        t = add(m, (math.cos(a_tip), math.sin(a_tip)), length * 0.5)
        roots.append(r0); mids.append(m); tips.append(t)
        rays.append(smooth_open([r0, m, add(m, (math.cos(a_tip), math.sin(a_tip)), length * 0.36)]))
    fill.append(smooth_closed([roots[0], mids[0]] + tips + [mids[-1], roots[-1]]))

    # paired fins
    for s_at, length, spread, beat, gain in ((0.24, 24, 1.0, 0.0, 0.24), (0.58, 14, 1.1, 0.5, 0.16)):
        p, tan, nor, w = fr.at(s_at)
        body_a = math.atan2(tan[1], tan[0])
        for side in (1, -1):
            flap = spread + gain * math.sin(TAU * (phase + beat) + side * 0.6)
            a0 = body_a + side * flap
            b0 = add(p, nor, side * w * 0.8)
            pts = [add(b0, tan, -length * 0.12)]
            for k in range(7):
                a = a0 + side * (-0.42 + 0.14 * k)
                L = length * (1.0 - 0.07 * k - 0.1 * math.sin(math.pi * k / 6))
                tip = add(b0, (math.cos(a), math.sin(a)), L)
                rays.append(f"M{pt(b0)}L{pt(add(b0, (math.cos(a), math.sin(a)), L * 0.78))}")
                pts.append(tip)
            pts.append(add(b0, tan, length * 0.18))
            fill.append(smooth_closed(pts))
    return "".join(fill), "".join(rays)


def pose(phase, amp, wavelength, pattern):
    fr = make_frame(phase, amp, wavelength)
    left = [add(p, n, w) for p, n, w in zip(fr.p, fr.n, fr.w)]
    right = [add(p, n, -w) for p, n, w in zip(fr.p, fr.n, fr.w)]
    body = smooth_closed(left[1:] + right[::-1])

    lines = []
    lines.append(smooth_open([fr.sv(s, 0) for s in (0.14, 0.3, 0.45, 0.6, 0.75, 0.9, 0.99)]))
    for v in (0.58, -0.58):
        lines.append(smooth_open([fr.sv(s, v) for s in (0.2, 0.35, 0.5, 0.65, 0.8, 0.93)]))
    lines.append(smooth_open([fr.sv(0.205 - 0.04 * (1 - v * v), v) for v in (-0.92, -0.5, 0, 0.5, 0.92)]))
    whisk = []
    for side in (1, -1):
        a, b = fr.sv(0.02, side * 0.55), fr.sv(-0.0, side * 0.5)
        _, tan, nor, _ = fr.at(0.02)
        tip = add(add(a, tan, -6), nor, side * 4)
        whisk.append(f"M{pt(a)}Q{pt(add(a, tan, -4))} {pt(tip)}")
    lines.append("".join(whisk))

    eyes = []
    for side in (1, -1):
        c = fr.sv(0.085, side * 0.66)
        r = 1.5
        eyes.append(f"M{fmt(c[0]-r)} {fmt(c[1])}a{r} {r} 0 1 0 {fmt(2*r)} 0a{r} {r} 0 1 0 {fmt(-2*r)} 0")

    tones = {}
    for bl in pattern:
        tones.setdefault(bl.tone, []).append(smooth_closed(blob_points(fr, bl)))

    fin_fill, fin_rays = fins(fr, phase, amp, wavelength)
    return {
        "finfill": fin_fill, "finrays": fin_rays, "body": body,
        "wash": "".join(tones.get("wash", [])) or None,
        "sumi": "".join(tones.get("sumi", [])) or None,
        "red": "".join(tones.get("red", [])) or None,
        "lines": "".join(lines), "eyes": "".join(eyes),
    }




# ------------------------------------------------------------ SMIL output

def _animate(values, dur):
    v = ";".join(values + values[:1])
    return f'<animate attributeName="d" dur="{dur:.2f}s" repeatCount="indefinite" values="{v}"/>'


def koi_svg(key, motion, scale, depth, beat, amp, kind, main_tone, body_dark):
    """Return (koi group, shadow group). `motion` is an <animateMotion> element."""
    rng = seeded("pattern", key, kind)
    pattern = make_pattern(rng, kind, main_tone)
    poses = [pose(i / KEYFRAMES, amp, 1.05, pattern) for i in range(KEYFRAMES)]

    def el(name, cls):
        if poses[0][name] is None:
            return ""
        vals = [p[name] for p in poses]
        return f'<path class="{cls}" d="{vals[0]}">{_animate(vals, beat)}</path>'

    sw = 1 / scale
    blur = f' filter="url(#d{round(depth * 3)})"' if depth > 0.17 else ""
    body_cls = "inkfill" if body_dark else "paperfill"
    sumi_cls = "paperfill" if body_dark else "inkfill"
    koi = (
        f'<g opacity="{1 - 0.6 * depth:.2f}"{blur}>{motion}<g transform="scale({scale:.3f})">'
        f'{el("finfill", "fin")}'
        f'<g style="stroke-width:{0.55*sw:.2f}">{el("finrays", "ray")}</g>'
        f'<g class="{body_cls}" style="stroke-width:{0.85*sw:.2f}">'
        f'<path id="{key}b" d="{poses[0]["body"]}">{_animate([p["body"] for p in poses], beat)}</path></g>'
        f'<g filter="url(#rough)">{el("wash", "wash")}{el("red", "red")}{el("sumi", sumi_cls + " nostroke")}</g>'
        f'<g style="stroke-width:{0.6*sw:.2f}">{el("lines", "line")}</g>'
        f'{el("eyes", "eye")}'
        f'</g></g>')
    off = 4 + 9 * (1 - depth)
    shadow = (f'<g transform="translate({off:.1f} {off*1.3:.1f})" opacity="{0.16*(1-depth)+0.03:.2f}">'
              f'<g>{motion}<g transform="scale({scale:.3f})"><use href="#{key}b" class="shadow"/></g></g></g>')
    return koi, shadow
