"""Разбор и нормализация данных SVG-пути (атрибут d). Без Qt.

Нормализованная форма — абсолютные команды M, L, C, Z. H/V → L; Q/T → C; S → C; A → набор C.
Это упрощает преобразования, границы и экспорт и делает хранение детерминированным.
"""

from __future__ import annotations

import math
import re

MAX_PATH_LEN = 1_000_000
MAX_SEGMENTS = 200_000
_TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}

Seg = tuple  # ("M", x, y) | ("L", x, y) | ("C", x1, y1, x2, y2, x, y) | ("Z",)


class PathError(ValueError):
    pass


def _arc_to_cubic(x1, y1, rx, ry, phi, fa, fs, x2, y2) -> list[Seg]:
    if rx == 0 or ry == 0:
        return [("L", x2, y2)]
    rx, ry = abs(rx), abs(ry)
    cp, sp = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = (x1p / rx) ** 2 + (y1p / ry) ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coef = math.sqrt(max(0.0, num / den)) if den else 0.0
    if fa == fs:
        coef = -coef
    cxp, cyp = coef * rx * y1p / ry, -coef * ry * x1p / rx
    cx = cp * cxp - sp * cyp + (x1 + x2) / 2
    cy = sp * cxp + cp * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not fs and dt > 0:
        dt -= 2 * math.pi
    elif fs and dt < 0:
        dt += 2 * math.pi
    n = max(1, math.ceil(abs(dt) / (math.pi / 2)))
    step = dt / n
    k = 4 / 3 * math.tan(step / 4)
    segs = []
    for i in range(n):
        a1, a2 = t1 + i * step, t1 + (i + 1) * step
        c1, s1, c2, s2 = math.cos(a1), math.sin(a1), math.cos(a2), math.sin(a2)
        p1 = (c1 - k * s1, s1 + k * c1)
        p2 = (c2 + k * s2, s2 - k * c2)
        p3 = (c2, s2)

        def tr(p):
            px, py = p[0] * rx, p[1] * ry
            return cp * px - sp * py + cx, sp * px + cp * py + cy
        (ax, ay), (bx, by), (ex, ey) = tr(p1), tr(p2), tr(p3)
        segs.append(("C", ax, ay, bx, by, ex, ey))
    return segs


def parse(d: str) -> list[Seg]:
    if not isinstance(d, str):
        raise PathError("Путь должен быть строкой")
    if len(d) > MAX_PATH_LEN:
        raise PathError("Слишком длинный путь")
    rest = _TOKEN.sub("", d)
    if rest.replace(",", "").strip():
        raise PathError(f"Недопустимые символы в пути: {rest.strip()[:20]!r}")
    tokens = _TOKEN.findall(d)
    out: list[Seg] = []
    i, cmd = 0, None
    cx = cy = sx = sy = 0.0
    last_c2 = last_q = None
    while i < len(tokens):
        t = tokens[i]
        if t.isalpha():
            cmd = t
            i += 1
            if cmd in "Zz":
                out.append(("Z",))
                cx, cy = sx, sy
                last_c2 = last_q = None
                continue
        elif cmd is None:
            raise PathError("Путь должен начинаться с команды")
        up = cmd.upper()
        n = _ARGS[up]
        if up == "Z":
            raise PathError("Лишние числа после Z")
        if i + n > len(tokens) or any(tokens[j].isalpha() for j in range(i, i + n)):
            raise PathError(f"Недостаточно чисел для команды {cmd}")
        a = [float(tokens[j]) for j in range(i, i + n)]
        if any(not math.isfinite(v) or abs(v) > 1e7 for v in a):
            raise PathError("Недопустимое число в пути")
        i += n
        rel = cmd.islower()
        if up in "ML":
            x, y = (a[0] + cx, a[1] + cy) if rel else (a[0], a[1])
            if up == "M":
                out.append(("M", x, y))
                sx, sy = x, y
                cmd = "l" if rel else "L"  # следующие пары — неявные L
            else:
                out.append(("L", x, y))
            cx, cy = x, y
            last_c2 = last_q = None
        elif up == "H":
            cx = a[0] + cx if rel else a[0]
            out.append(("L", cx, cy))
            last_c2 = last_q = None
        elif up == "V":
            cy = a[0] + cy if rel else a[0]
            out.append(("L", cx, cy))
            last_c2 = last_q = None
        elif up == "C":
            p = [a[k] + (cx if k % 2 == 0 else cy) if rel else a[k] for k in range(6)]
            out.append(("C", *p))
            last_c2, last_q = (p[2], p[3]), None
            cx, cy = p[4], p[5]
        elif up == "S":
            p = [a[k] + (cx if k % 2 == 0 else cy) if rel else a[k] for k in range(4)]
            c1 = (2 * cx - last_c2[0], 2 * cy - last_c2[1]) if last_c2 else (cx, cy)
            out.append(("C", c1[0], c1[1], p[0], p[1], p[2], p[3]))
            last_c2, last_q = (p[0], p[1]), None
            cx, cy = p[2], p[3]
        elif up in "QT":
            if up == "Q":
                p = [a[k] + (cx if k % 2 == 0 else cy) if rel else a[k] for k in range(4)]
                q, end = (p[0], p[1]), (p[2], p[3])
            else:
                end = (a[0] + cx, a[1] + cy) if rel else (a[0], a[1])
                q = (2 * cx - last_q[0], 2 * cy - last_q[1]) if last_q else (cx, cy)
            c1 = (cx + 2 / 3 * (q[0] - cx), cy + 2 / 3 * (q[1] - cy))
            c2 = (end[0] + 2 / 3 * (q[0] - end[0]), end[1] + 2 / 3 * (q[1] - end[1]))
            out.append(("C", *c1, *c2, *end))
            last_q, last_c2 = q, None
            cx, cy = end
        elif up == "A":
            x2, y2 = (a[5] + cx, a[6] + cy) if rel else (a[5], a[6])
            out.extend(_arc_to_cubic(cx, cy, a[0], a[1], a[2], int(a[3]) != 0, int(a[4]) != 0, x2, y2))
            cx, cy = x2, y2
            last_c2 = last_q = None
        if len(out) > MAX_SEGMENTS:
            raise PathError("Слишком много сегментов")
    if out and out[0][0] != "M":
        raise PathError("Путь должен начинаться с M")
    return out


def _f(v: float) -> str:
    s = f"{round(v, 3):.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def to_string(segs: list[Seg]) -> str:
    parts = []
    for s in segs:
        parts.append(s[0] + (" " + " ".join(_f(v) for v in s[1:]) if len(s) > 1 else ""))
    return " ".join(parts)


def normalize(d: str) -> str:
    return to_string(parse(d)) if d.strip() else ""


def transform(segs: list[Seg], m: tuple[float, float, float, float, float, float]) -> list[Seg]:
    """Аффинное преобразование (a, b, c, d, e, f) как в SVG matrix()."""
    a, b, c, d, e, f = m
    out = []
    for s in segs:
        if s[0] == "Z":
            out.append(s)
            continue
        pts = s[1:]
        new = []
        for k in range(0, len(pts), 2):
            x, y = pts[k], pts[k + 1]
            new += [a * x + c * y + e, b * x + d * y + f]
        out.append((s[0], *new))
    return out


def bounds(segs: list[Seg]) -> tuple[float, float, float, float] | None:
    xs, ys = [], []
    for s in segs:
        pts = s[1:]
        xs += pts[0::2]
        ys += pts[1::2]
    if not xs:
        return None
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def rect_path(x, y, w, h, rx=0.0, ry=None) -> str:
    ry = rx if ry is None else ry
    rx, ry = min(rx, w / 2), min(ry, h / 2)
    if rx <= 0 or ry <= 0:
        return to_string([("M", x, y), ("L", x + w, y), ("L", x + w, y + h), ("L", x, y + h), ("Z",)])
    return normalize(f"M {x + rx} {y} H {x + w - rx} A {rx} {ry} 0 0 1 {x + w} {y + ry} V {y + h - ry} "
                     f"A {rx} {ry} 0 0 1 {x + w - rx} {y + h} H {x + rx} A {rx} {ry} 0 0 1 {x} {y + h - ry} "
                     f"V {y + ry} A {rx} {ry} 0 0 1 {x + rx} {y} Z")


def ellipse_path(cx, cy, rx, ry) -> str:
    return normalize(f"M {cx - rx} {cy} A {rx} {ry} 0 1 0 {cx + rx} {cy} A {rx} {ry} 0 1 0 {cx - rx} {cy} Z")
