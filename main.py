"""gta6-twitch-ccu-forecast-01 entry in Python 3.13 (standard library only):
a launch-day shape forecaster.

The house baseline (the kit's starter) says every hour of release day draws as
many concurrent Twitch viewers as hour 1 did, with a spread that widens like a
random walk. That is wrong in a predictable way: a big console launch does not
stay flat. Hour 1 is the small hours of the UTC day, when only New Zealand,
Australia, Asia and (from 23:00Z the day before) central Europe have unlocked.
Viewers dip through the small hours, then climb as the UK unlocks at midnight
UTC, the US east coast at 05:00 UTC and the west coast at 08:00 UTC, and peak
in the US evening (hours 20-21). The shape is visible in every past big
launch the case hands over as a comparable, so this program learns it from
them instead of assuming it:

  1. Each comparable's launch-day curve is its 24 hourly viewer counts from
     its day_start, normalised by its hour-1 count: r_h = viewers_h / viewers_1.
  2. The relevant set is the comparables whose hour 1 is a real launch hour:
     hour-1 viewers >= 10,000. Games below that had not unlocked anywhere by
     00:00 UTC and explode 100-2000x later in the day; they belong to a
     different unlock structure and would poison the shape. Console-only
     launches (no PC in their platforms) are preferred when at least five
     exist, because Grand Theft Auto VI is console-only with a rolling
     midnight-local unlock, and their shapes are far tighter than the mixed
     set's. The case's own game is excluded by name: its pre-release history
     sits among the comparables and is not a launch curve.
  3. For each hour, the forecast median is the relevant set's median ratio,
     and the spread is lognormal with log-sd (ln q75 - ln q25) / 1.349 from
     the ratios pooled across every big launch (hour 1 >= 10,000), floored at
     0.15 and capped at 0.80. The relevant set alone is too small (about
     seven console-only games) for its own interquartile range to say how far
     a launch day can run from its median shape; the pooled spread is the
     honest one. The quantiles are q_tau = p1 * m_h * exp(z_tau * s_h).
  4. Size flattening: the bigger hour 1 is, the flatter the launch day.
     Across the big launches, log(peak / hour 1) = 3.755 - 0.260 * log(hour 1)
     on the console-only set (R2 = 0.50). The median's deviation from 1 is
     scaled by f = peak(p1) / peak(median hour 1 of the set), clamped to
     [0.5, 1.15], and the log-spread by sqrt(f). A record hour 1 flattens the
     whole curve toward 1.0; a modest one keeps the full evening rise.

Fallbacks keep every case valid: an hour with fewer than three ratios in the
relevant set falls back to all hour-1 >= 10k games for that hour, then to the
persistence baseline for that hour; a case with no usable comparables at all
is forecast with the baseline throughout. Nothing here uses the clock, the
network or any randomness, so two runs write the same bytes.

How the grader runs it: `python3 -P -s /bot/main.py` (PYTHONHASHSEED=0) in
python:3.13-slim, standard library only: no network, no pip packages. -P keeps
this file's directory OFF sys.path, so a module shipped beside main.py imports
only after the sys.path line below, which puts the directory first; -s drops
user site-packages.

What an entry must do:
  - read every <id>.in in the input directory (the grader runs one case at a
    time, with only that case's file there): JSON
    {"schema": "makefun/twitch-ccu-case/v1", "id", "game", "day_start",
    "checkpoint", "levels", "known", "forecast", "history", "history_hourly",
    "streams", "categories_hourly", "comparables", "notes"}, where `known`
    holds hour 1's print {hour: 1, from, until, viewers, channels, reads} and
    `forecast` lists the hours to forecast, 2..24;
  - write <id>.out to the output directory: {"hours": [{"hour": 2, "q": [q05,
    q25, q50, q75, q95]}, ...]}, exactly 23 rows, hours 2..24 each once, no
    other key, each q five finite numbers above 0 and at most 1e9 (viewers;
    fractions allowed), non-decreasing; at most 65,536 bytes. Anything else
    is an invalid case, scored as if every quantile equalled hour 1's print,
    and an entry with an invalid case takes no prize.

Outside the grader's container, MAKEFUN_INPUT_DIR and MAKEFUN_OUTPUT_DIR stand
in for /input and /output:
    mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so `import model` finds a model.py shipped beside this file.
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# The quantile levels the contest scores, in the order each row lists them.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# The standard normal's quantile at each level.
Z = [-1.645, -0.674, 0, 0.674, 1.645]
# The baseline's spread of an hour's move, in natural-log units per square-root hour.
SIGMA = 0.15

# A comparable only counts as a real launch hour when its hour-1 print is at
# least this many viewers; below it the game had not unlocked anywhere by
# 00:00 UTC and its curve is a different shape altogether.
MIN_HOUR1 = 10000
# Prefer the console-only set when it holds at least this many games.
MIN_CONSOLE_ONLY = 5
# An hour needs at least this many ratios before its own set is trusted.
MIN_RATIOS = 3
# The log-spread of an hour's ratio, floored and capped.
SPREAD_FLOOR = 0.15
SPREAD_CAP = 0.80
# Size-flattening factor, clamped: a record hour 1 flattens the curve, a
# modest one never steepens it by more than 15%.
FLATTEN_MIN = 0.5
FLATTEN_MAX = 1.15
# log(peak / hour 1) = PEAK_A + PEAK_B * log(hour 1), fitted on the
# console-only big launches (R2 = 0.50): bigger hour 1, flatter launch day.
PEAK_A = 3.755
PEAK_B = -0.260


def round2(x: float) -> float | int:
    """x rounded to 2 decimals, half up, as JavaScript's Math.round(x * 100) / 100 rounds it.

    A whole number comes back as an int, so json.dumps writes 1240 where JavaScript writes 1240 (not 1240.0).
    """
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value.is_integer() else value


def parse_time(s: str) -> datetime:
    """An ISO 8601 UTC timestamp from the case files, as an aware datetime."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def quantile(sorted_values: list[float], q: float) -> float:
    """The q-quantile of an already sorted list, linear interpolation."""
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    pos = (n - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_values[lo]
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def median(values: list[float]) -> float:
    """The median of a non-empty list."""
    return quantile(sorted(values), 0.5)


def normal_quantile(p: float) -> float:
    """The standard normal's quantile at p, Acklam's approximation.

    Only used when a case asks for levels other than the contest's five; the
    five standard levels use the exact Z table above.
    """
    if p <= 0.0 or p >= 1.0:
        raise ValueError(f"level {p} is outside (0, 1)")
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]
    plow = 0.02425
    phigh = 1 - plow
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
                ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def launch_curve(comp: dict) -> list:
    """A comparable's launch-day curve: 24 hourly viewer counts, hours 1..24.

    Index 0 is unused; a missing hour stays None. Points outside the launch
    day are ignored.
    """
    start = parse_time(comp["day_start"])
    curve: list = [None] * 25
    for point in comp.get("hourly") or []:
        viewers = point.get("viewers")
        if viewers is None:
            continue
        hour = int((parse_time(point["from"]) - start).total_seconds() // 3600) + 1
        if 1 <= hour <= 24:
            curve[hour] = viewers
    return curve


def is_console_only(comp: dict) -> bool:
    """True when the comparable launched on consoles only (no PC)."""
    platforms = comp.get("platforms") or ""
    return "pc" not in platforms.lower()


def baseline_quantiles(p1: float, h: int, z_values: list[float]) -> list[float]:
    """The persistence forecast of hour h: hour 1's print, widening spread."""
    return [p1 * math.exp(z * SIGMA * math.sqrt(h - 1)) for z in z_values]


def forecast_case(case: dict, name: str) -> dict:
    levels = case.get("levels") or LEVELS
    if list(levels) == list(LEVELS):
        z_values = list(Z)
    else:
        z_values = [normal_quantile(float(level)) for level in levels]
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1, first["viewers"])

    own_name = (case.get("game") or {}).get("name") or ""
    # Every comparable with a real launch hour, as (hour-1 viewers, curve).
    big = []
    for comp in case.get("comparables") or []:
        if (comp.get("name") or "") == own_name:
            continue
        curve = launch_curve(comp)
        hour1 = curve[1]
        if hour1 is None or hour1 < MIN_HOUR1:
            continue
        big.append((hour1, curve, is_console_only(comp)))
    # The console-only set when it is big enough, else every big launch.
    console = [entry for entry in big if entry[2]]
    relevant = console if len(console) >= MIN_CONSOLE_ONLY else big
    if not relevant:
        return {"hours": [{"hour": row["hour"], "q": [round2(q) for q in baseline_quantiles(p1, row["hour"], z_values)]}
                         for row in case["forecast"]]}

    p1_med = median([entry[0] for entry in relevant])

    def peak_ratio(p: float) -> float:
        return math.exp(PEAK_A + PEAK_B * math.log(max(1.0, p)))

    flatten = peak_ratio(p1) / peak_ratio(p1_med)
    flatten = min(FLATTEN_MAX, max(FLATTEN_MIN, flatten))
    spread_scale = math.sqrt(flatten)

    hours = []
    for row in case["forecast"]:
        h = row["hour"]
        # Ratios of this hour to hour 1 across the relevant set; fall back to
        # the full big set when this hour is too thinly covered, then to the
        # baseline for this hour alone. The spread is always pooled from the
        # full big set (see step 3 in the module docstring).
        ratios = sorted(entry[1][h] / entry[1][1] for entry in relevant
                        if entry[1][h] is not None and entry[1][1])
        pool = sorted(entry[1][h] / entry[1][1] for entry in big
                      if entry[1][h] is not None and entry[1][1])
        if len(ratios) < MIN_RATIOS:
            ratios = pool
        if len(ratios) < MIN_RATIOS:
            qs = baseline_quantiles(p1, h, z_values)
        else:
            m = quantile(ratios, 0.5)
            q25 = quantile(pool, 0.25)
            q75 = quantile(pool, 0.75)
            spread = (math.log(q75) - math.log(q25)) / 1.349 if q25 > 0 and q75 > 0 else SPREAD_FLOOR
            spread = min(SPREAD_CAP, max(SPREAD_FLOOR, spread)) * spread_scale
            # Flatten the median's deviation from 1.0 for a huge hour 1.
            m_adj = 1.0 + (m - 1.0) * flatten
            if m_adj <= 0:
                m_adj = m
            qs = [p1 * m_adj * math.exp(z * spread) for z in z_values]
        # Round half up, keep the row non-decreasing, above 0 and <= 1e9.
        rounded = []
        prev = 0.01
        for q in qs:
            value = round2(min(1e9, max(0.01, q)))
            if value < prev:
                value = prev
            rounded.append(value)
            prev = value
        hours.append({"hour": h, "q": rounded})
    return {"hours": hours}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
