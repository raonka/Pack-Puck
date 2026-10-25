#!/usr/bin/env python3
"""Pack Pucks — uncertainty of the headline aggregates and of the slope fits.

Two computations on the 22 Aug matched session (post-discard), added
2026-10-25: intervals for the headline aggregates and for the slopes:

  1. Bootstrap over markers. The ten markers of a run are resampled with
     replacement (10,000 replicates, fixed seed recorded below). Each
     replicate recomputes, per tier, from the unrounded per-marker signed
     errors of tools/per_marker_tables.py:
       - MAE and mean signed error at each bandwidth;
       - the paired ratio MAE(406.25) / MAE(1625), with the same resampled
         markers in numerator and denominator.
     Intervals are 95 % percentile intervals (2.5th and 97.5th
     percentiles of the replicates; statistics.quantiles, method
     "inclusive", the same linear interpolation as the IQRs).

  2. t-intervals for the four least-squares slopes of signed error vs
     distance at 406.25 kHz (tools/aggregates.py linfit, same inputs:
     TABLE 2 / TABLE 3 "406 err"). 95 % two-sided, df = n - 2 (8 for the
     ten-marker fits, 7 for the fits without 240 m); the df = 8 interval
     is also listed for the nine-marker fits. The implied change over the
     270 m span of the marker set (30 to 300 m) is slope x 270 m. The t
     quantile is computed here (regularised incomplete beta, bisection);
     no external statistics package is used.

Output: data/analysis/uncertainty.md

Usage:
    python tools/uncertainty.py
"""

from __future__ import annotations

import math
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aggregates as agg  # noqa: E402  (matched_table, linfit, NEW)
import per_marker_tables as pmt  # noqa: E402  (build: unrounded per-marker stats)

OUT = Path("data/analysis/uncertainty.md")
SEED = 20261025
REPS = 10_000
SPAN_M = 270.0   # marker set 30-300 m (methodology.md 5.1)
TIERS = (("static", "static"), ("s&g", "stop-and-go"))
BWS = (("406", "406.25"), ("1625", "1625"))


# ---------------------------------------------------------------------------
# Student t quantile
# ---------------------------------------------------------------------------


def betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta (modified Lentz)."""
    tiny, eps = 1e-300, 1e-15
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1) < eps:
            break
    return h


def betai(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbt = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
           + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return math.exp(lbt) * betacf(a, b, x) / a
    return 1 - math.exp(lbt) * betacf(b, a, 1 - x) / b


def t_cdf(t: float, df: int) -> float:
    p = 0.5 * betai(df / 2, 0.5, df / (df + t * t))
    return 1 - p if t > 0 else p


def t_quantile(p: float, df: int) -> float:
    lo, hi = 0.0, 100.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def pct95(v: list[float]) -> tuple[float, float]:
    q = statistics.quantiles(v, n=40, method="inclusive")
    return q[0], q[-1]


def bootstrap() -> dict:
    res = pmt.build(discard=True)
    rng = random.Random(SEED)
    out = {}
    for tier, run in TIERS:
        errs = {}
        for bw, key in BWS:
            st = res[("22 Aug", key, run)]
            assert len(st) == 10
            errs[bw] = [st[m]["err"] for m in sorted(st)]
        reps = {k: [] for k in ("mae_406", "mae_1625", "bias_406", "bias_1625",
                                "ratio")}
        for _ in range(REPS):
            idx = [rng.randrange(10) for _ in range(10)]
            for bw, _key in BWS:
                e = [errs[bw][i] for i in idx]
                reps[f"mae_{bw}"].append(statistics.fmean(abs(x) for x in e))
                reps[f"bias_{bw}"].append(statistics.fmean(e))
            reps["ratio"].append(reps["mae_406"][-1] / reps["mae_1625"][-1])
        point = {}
        for bw, _key in BWS:
            point[f"mae_{bw}"] = statistics.fmean(abs(x) for x in errs[bw])
            point[f"bias_{bw}"] = statistics.fmean(errs[bw])
        point["ratio"] = point["mae_406"] / point["mae_1625"]
        out[tier] = {k: (point[k],) + pct95(v) for k, v in reps.items()}
    return out


# ---------------------------------------------------------------------------
# Slope intervals
# ---------------------------------------------------------------------------


def slope_intervals() -> list[dict]:
    rows = []
    for tier, n_tab in (("static", 2), ("stop-and-go", 3)):
        tab = agg.matched_table(agg.NEW, n_tab)
        for label, keep in (("all ten", lambda r: True),
                            ("without 240 m", lambda r: r["marker"] != 240)):
            sel = [r for r in tab if keep(r)]
            f = agg.linfit([r["marker"] for r in sel], [r["err_406"] for r in sel])
            df = f["n"] - 2
            row = {"tier": tier, "markers": label, **f, "df": df}
            for name, d in (("own", df), ("df8", 8)):
                t = t_quantile(0.975, d)
                lo, hi = f["slope"] - t * f["se_slope"], f["slope"] + t * f["se_slope"]
                row[f"t_{name}"] = t
                row[f"ci_{name}"] = (lo, hi)
                row[f"span_{name}"] = (lo * SPAN_M, hi * SPAN_M)
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def sg(v: float, nd: int) -> str:
    return f"{v:+.{nd}f}"


def main() -> int:
    bs = bootstrap()
    fits = slope_intervals()
    L = ["# Pack Pucks — uncertainty of the matched-session aggregates and "
         "slope fits (22 Aug 2026, post-discard)", "",
         "Generated by `tools/uncertainty.py`. Raw CSVs read-only. "
         "**Numbers only.**", "",
         "## 1. Bootstrap over markers", "",
         f"Inputs: unrounded per-marker signed errors e_k (`tools/"
         f"per_marker_tables.py` build, post-discard), ten markers per run. "
         f"Resampling: the ten markers with replacement, {REPS:,} replicates, "
         f"`random.Random({SEED})`; within a tier the same resampled markers "
         f"are used at both bandwidths, so the ratio is paired by marker. "
         f"Interval: 95 % percentile (2.5th / 97.5th percentile of the "
         f"replicates, linear interpolation). Point values are the "
         f"full-sample statistics (they match `aggregates.md`).", "",
         "| tier | statistic | bandwidth | point (m) | 95 % interval (m) |",
         "|---|---|---|---|---|"]
    names = {"static": "static", "s&g": "stop-and-go"}
    for tier in ("static", "s&g"):
        for stat, key in (("MAE", "mae"), ("mean signed error", "bias")):
            for bw, label in (("406", "406.25 kHz"), ("1625", "1625 kHz")):
                p, lo, hi = bs[tier][f"{key}_{bw}"]
                f = (lambda v: f"{v:.1f}") if key == "mae" else (lambda v: sg(v, 1))
                L.append(f"| {names[tier]} | {stat} | {label} | {f(p)} | "
                         f"{f(lo)} to {f(hi)} |")
    L += ["", "### Paired MAE ratio, MAE(406.25) / MAE(1625)", "",
          "| tier | point | 95 % interval |", "|---|---|---|"]
    for tier in ("static", "s&g"):
        p, lo, hi = bs[tier]["ratio"]
        L.append(f"| {names[tier]} | {p:.1f}× | {lo:.1f}× to {hi:.1f}× |")
    L += ["", "## 2. Slope of signed error vs distance, 406.25 kHz: "
          "95 % t-intervals", "",
          "Inputs and fits as `aggregates.md` \"Signed error vs distance, "
          "406.25 kHz\" (TABLE 2 / TABLE 3 \"406 err\", 0.1 m-rounded). "
          "Interval: slope ± t(0.975, df) × standard error. Implied change "
          f"over the span = interval × {SPAN_M:.0f} m (markers 30 to 300 m).",
          "",
          "| tier | markers | n | df | slope (m/m) | standard error (m/m) | "
          "t(0.975, df) | 95 % interval (m/m) | implied change over 270 m (m) | "
          "interval contains 0? |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in fits:
        lo, hi = r["ci_own"]
        slo, shi = r["span_own"]
        L.append(f"| {r['tier']} | {r['markers']} | {r['n']} | {r['df']} | "
                 f"{sg(r['slope'], 4)} | {r['se_slope']:.4f} | "
                 f"{r['t_own']:.3f} | {sg(lo, 3)} to {sg(hi, 3)} | "
                 f"{sg(slo, 1)} to {sg(shi, 1)} | "
                 f"{'yes' if lo <= 0 <= hi else 'no'} |")
    L += ["", "### Same intervals at df = 8 for every fit", "",
          "The nine-marker fits (without 240 m) have df = 7; this table "
          "repeats them at df = 8 for comparison only.", "",
          "| tier | markers | t(0.975, 8) | 95 % interval (m/m) | implied "
          "change over 270 m (m) |", "|---|---|---|---|---|"]
    for r in fits:
        lo, hi = r["ci_df8"]
        slo, shi = r["span_df8"]
        L.append(f"| {r['tier']} | {r['markers']} | {r['t_df8']:.3f} | "
                 f"{sg(lo, 3)} to {sg(hi, 3)} | {sg(slo, 1)} to {sg(shi, 1)} |")
    L.append("")
    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
