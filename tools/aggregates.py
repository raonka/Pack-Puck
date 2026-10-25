#!/usr/bin/env python3
"""Pack Pucks — campaign aggregates (the numbers README.md quotes).

Computes every aggregate the README headline and Results quote, from:

  - the matched-marker tables (TABLE 2 static, TABLE 3 stop-and-go) of
    data/analysis/2026-08-22_GMATownship_day2_tables_discard5s.md
    (post-discard; current), and of
    data/analysis/2026-08-22_GMATownship_day2_qc_tables.md
    (pre-discard; superseded, reported for comparison only);
  - the raw Initiator CSVs of both campaign outings (cadence, exchange
    total), opened read-only.

Every aggregate here is an unweighted mean over the ten markers. In the
current (post-discard) column, MAE, signed bias and the MAE ratio are
computed from the unrounded per-marker medians (tools/per_marker_tables.py);
the other aggregates use the tables' 0.1 m-
rounded values. The pre-discard column keeps the rounded-table method so it
reproduces the README figures. Cycle-time p05 / p95 use linear interpolation
(statistics.quantiles, method "inclusive", as for the IQRs).

Output: data/analysis/aggregates.md

Usage:
    python tools/aggregates.py
"""

from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_session as qc  # noqa: E402  (parse_csv_file)
import per_marker_tables as pmt  # noqa: E402  (build: unrounded per-marker stats)

AN = Path("data/analysis")
NEW = AN / "2026-08-22_GMATownship_day2_tables_discard5s.md"
OLD = AN / "2026-08-22_GMATownship_day2_qc_tables.md"
OUT = AN / "aggregates.md"

# Canonical Initiator offload sets of the two campaign outings. All files
# count toward the exchange total, operator-discarded retakes included;
# the superseded 15 Aug partial set (20260815_173207) is excluded.
CADENCE_SETS = {
    "1625": [Path("data/ranging_experiments/2026-08-22_GMATownship_session02"
                  "/raw/20260822_174415-Initiator")],
    "406.25": [Path("data/ranging_experiments/2026-08-22_GMATownship_session02"
                    "/raw/20260822_162424-Initiator")],
}
TOTAL_SETS = [
    Path("data/ranging_experiments/2026-08-15_GMATownship_session01"
         "/raw/20260815_184714-Initiator"),
    *CADENCE_SETS["406.25"], *CADENCE_SETS["1625"],
]


def matched_table(path: Path, n: int) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    block = text.split(f"## TABLE {n}", 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in block.splitlines():
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) >= 7 and re.fullmatch(r"\d+", c[0]):
            rows.append({"marker": int(c[0]),
                         "iqr_406": float(c[2]), "err_406": float(c[3]),
                         "iqr_1625": float(c[5]), "err_1625": float(c[6])})
    if len(rows) != 10:
        sys.exit(f"error: {path} TABLE {n}: {len(rows)} rows, want 10")
    return rows


def mean(v):
    return sum(v) / len(v)


def linfit(xs: list[float], ys: list[float]) -> dict:
    """Ordinary least squares y = a + b x, with the standard error of b."""
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    res = [y - (a + b * x) for x, y in zip(xs, ys)]
    se_b = (sum(r * r for r in res) / (len(xs) - 2) / sxx) ** 0.5
    return {"n": len(xs), "slope": b, "intercept": a, "se_slope": se_b}


def tier_aggs(rows: list[dict]) -> dict:
    a = {}
    for bw in ("406", "1625"):
        e = [r[f"err_{bw}"] for r in rows]
        i = [r[f"iqr_{bw}"] for r in rows]
        a[f"mae_{bw}"] = mean([abs(x) for x in e])
        a[f"bias_{bw}"] = mean(e)
        a[f"iqr_{bw}"] = mean(i)
        a[f"iqrmin_{bw}"], a[f"iqrmax_{bw}"] = min(i), max(i)
        a[f"maxabs_{bw}"] = max(abs(x) for x in e)
        w = max(rows, key=lambda r: abs(r[f"err_{bw}"]))
        a[f"worst_{bw}"] = (w[f"err_{bw}"], w["marker"])
        a[f"npos_{bw}"] = sum(1 for x in e if x > 0)
    a["mae_ratio"] = a["mae_406"] / a["mae_1625"]
    a["iqr_ratio"] = a["iqr_406"] / a["iqr_1625"]
    return a


def all_aggs(path: Path) -> dict:
    return {"static": tier_aggs(matched_table(path, 2)),
            "s&g": tier_aggs(matched_table(path, 3))}


def unrounded_mae_bias(aggs: dict) -> dict:
    """Replace MAE, signed bias and the MAE ratio with values computed from
    the unrounded post-discard per-marker medians (22 Aug)."""
    res = pmt.build(discard=True)
    for tier, run in (("static", "static"), ("s&g", "stop-and-go")):
        for bw, key in (("406", "406.25"), ("1625", "1625")):
            e = [st["err"] for st in res[("22 Aug", key, run)].values()]
            assert len(e) == 10
            aggs[tier][f"mae_{bw}"] = mean([abs(x) for x in e])
            aggs[tier][f"bias_{bw}"] = mean(e)
        aggs[tier]["mae_ratio"] = aggs[tier]["mae_406"] / aggs[tier]["mae_1625"]
    return aggs


def raw_counts() -> tuple[dict, int, list[str]]:
    cad = {}
    for bw, dirs in CADENCE_SETS.items():
        deltas = []
        for d in dirs:
            for p in sorted(d.glob("pucklog_*.csv")):
                ts = [r.timestamp_ms for r in qc.parse_csv_file(p).rows]
                deltas += [b - a for a, b in zip(ts, ts[1:])]
        q = statistics.quantiles(deltas, n=20, method="inclusive")
        cad[bw] = (statistics.median(deltas), len(deltas), q[0], q[-1])
    total, per_set = 0, []
    for d in TOTAL_SETS:
        n = sum(len(qc.parse_csv_file(p).rows)
                for p in sorted(d.glob("pucklog_*.csv")))
        per_set.append(f"`{d.as_posix()}/` — {n} rows")
        total += n
    return cad, total, per_set


# (label, tier, key, format, README.md value at README precision)
ROWS = [
    ("MAE, 406.25 kHz", "static", "mae_406", "{:.1f} m", "11.1 m"),
    ("MAE, 1625 kHz", "static", "mae_1625", "{:.1f} m", "1.7 m"),
    ("MAE ratio 406.25 / 1625", "static", "mae_ratio", "{:.1f}×", "6.7×"),
    ("MAE, 406.25 kHz", "s&g", "mae_406", "{:.1f} m", "12.1 m"),
    ("MAE, 1625 kHz", "s&g", "mae_1625", "{:.1f} m", "1.7 m"),
    ("MAE ratio 406.25 / 1625", "s&g", "mae_ratio", "{:.1f}×", "7.1×"),
    ("Signed bias, 406.25 kHz", "static", "bias_406", "{:+.1f} m", "+10.5 m"),
    ("Signed bias, 1625 kHz", "static", "bias_1625", "{:+.1f} m", "+0.4 m"),
    ("Signed bias, 406.25 kHz", "s&g", "bias_406", "{:+.1f} m", "+12.1 m"),
    ("Signed bias, 1625 kHz", "s&g", "bias_1625", "{:+.1f} m", "−0.2 m"),
    ("Mean IQR, 406.25 kHz", "static", "iqr_406", "{:.1f} m", "5.2 m"),
    ("Mean IQR, 1625 kHz", "static", "iqr_1625", "{:.1f} m", "1.7 m"),
    ("Mean IQR ratio 406.25 / 1625", "static", "iqr_ratio", "{:.1f}×", "3.0×"),
    ("Mean IQR, 406.25 kHz", "s&g", "iqr_406", "{:.1f} m", "4.5 m"),
    ("Mean IQR, 1625 kHz", "s&g", "iqr_1625", "{:.1f} m", "1.8 m"),
    ("Mean IQR ratio 406.25 / 1625", "s&g", "iqr_ratio", "{:.1f}×", "2.6×"),
    ("Markers with positive error, 406.25 kHz", "static", "npos_406",
     "{} of 10", "9 of 10"),
    ("Markers with positive error, 406.25 kHz", "s&g", "npos_406",
     "{} of 10", "10 of 10"),
    ("Max |error|, 1625 kHz (README: \"inside ±5 m at every marker\")",
     "static", "maxabs_1625", "{:.1f} m", "< 5 m"),
    ("Max |error|, 1625 kHz (README: \"inside ±5 m at every marker\")",
     "s&g", "maxabs_1625", "{:.1f} m", "< 5 m"),
]


def fmt_worst(a, bw):
    e, m = a[f"worst_{bw}"]
    return f"{e:+.1f} m (at {m} m)"


def main() -> int:
    new, old = unrounded_mae_bias(all_aggs(NEW)), all_aggs(OLD)
    cad, total, per_set = raw_counts()
    c1625, c406 = cad["1625"][0], cad["406.25"][0]
    cyc = (c406 - c1625) / c1625 * 100

    L = ["# Pack Pucks — Campaign aggregates", "",
         "Generated by `tools/aggregates.py`. **Numbers only.**", "",
         "## Inputs", "",
         f"- Current (post-discard): `{NEW.as_posix()}` — TABLE 2 (static), "
         "TABLE 3 (stop-and-go)",
         f"- Superseded (pre-discard, comparison only): `{OLD.as_posix()}` — "
         "TABLE 2, TABLE 3",
         "- Raw Initiator CSVs (cadence, exchange total):"]
    L += [f"  - {s}" for s in per_set]
    L += ["", "Definitions: MAE = mean over the ten markers of |per-marker "
          "median − marker|. Signed bias = mean of the same signed errors. "
          "Mean IQR = mean of per-marker IQRs. Ratios = 406.25 value / 1625 "
          "value. Current column: MAE, signed bias and MAE ratio from the "
          "unrounded per-marker medians (`tools/per_marker_tables.py`); "
          "mean IQR, IQR ratio, ranges, counts and worst marker from the "
          "tables' 0.1 m-rounded values. Pre-discard column: all from the "
          "0.1 m-rounded tables (reproduces README.md).", "",
          "## Accuracy and precision (22 Aug, matched session)", "",
          "| aggregate | tier | post-discard (current) | pre-discard | "
          "README.md | changed at README precision? |",
          "|---|---|---|---|---|---|"]
    changed = []
    for label, tier, key, f, readme in ROWS:
        nv, ov = f.format(new[tier][key]), f.format(old[tier][key])
        ch = "**yes**" if nv != ov else "no"
        if nv != ov:
            changed.append(f"{label} ({tier}): {ov} → {nv}")
        L.append(f"| {label} | {tier} | {nv} | {ov} | {readme} | {ch} |")
    for bw, lbl, readme in (("406", "406.25", "+29.9 m (at 240 m)"),
                            ("1625", "1625", "+3.2 m (at 240 m)")):
        nv, ov = fmt_worst(new["static"], bw), fmt_worst(old["static"], bw)
        ch = "**yes**" if nv != ov else "no"
        if nv != ov:
            changed.append(f"Worst single marker {lbl} (static): {ov} → {nv}")
        L.append(f"| Worst single marker, {lbl} kHz | static | {nv} | {ov} | "
                 f"{readme} | {ch} |")
    for bw, lbl, readme in (("406", "406.25", "2.7–8.5 m"),
                            ("1625", "1625", "0.9–3.3 m")):
        def rng(a):
            lo = min(a["static"][f"iqrmin_{bw}"], a["s&g"][f"iqrmin_{bw}"])
            hi = max(a["static"][f"iqrmax_{bw}"], a["s&g"][f"iqrmax_{bw}"])
            return f"{lo:.1f}–{hi:.1f} m"
        nv, ov = rng(new), rng(old)
        ch = "**yes**" if nv != ov else "no"
        if nv != ov:
            changed.append(f"IQR range {lbl} (both tiers): {ov} → {nv}")
        L.append(f"| Per-marker IQR range, {lbl} kHz | both | {nv} | {ov} | "
                 f"{readme} | {ch} |")
    L += ["", "## Cadence and exchange count (raw CSVs; not affected by the "
          "discard)", "",
          "| aggregate | value | README.md |", "|---|---|---|",
          f"| Cycle time, 1625 kHz (pooled median, {cad['1625'][1]} "
          f"inter-row deltas, 22 Aug) | {c1625:g} ms | 655 ms (2,649 deltas) |",
          f"| Cycle time, 406.25 kHz (pooled median, {cad['406.25'][1]} "
          f"inter-row deltas, 22 Aug) | {c406:g} ms | 686 ms (3,084 deltas) |",
          f"| Cycle time p05 / p95, 1625 kHz (linear interpolation) | "
          f"{cad['1625'][2]:g} / {cad['1625'][3]:g} ms | — |",
          f"| Cycle time p05 / p95, 406.25 kHz (linear interpolation) | "
          f"{cad['406.25'][2]:g} / {cad['406.25'][3]:g} ms | — |",
          f"| Cycle-time cost of 406.25 vs 1625 | {cyc:.1f} % | 4.7 % |",
          f"| Cycle-time difference, 406.25 − 1625 | {c406 - c1625:g} ms | — |",
          f"| Bandwidth-scaled part of the 1625 kHz cycle, if it scales with "
          f"symbol duration (×4 at 406.25): (686 − 655) / 3 | "
          f"{(c406 - c1625) / 3:.1f} ms | — |",
          f"| Bandwidth-independent remainder of the 1625 kHz cycle | "
          f"{c1625 - (c406 - c1625) / 3:.1f} ms "
          f"({(c1625 - (c406 - c1625) / 3) / c1625:.1%}) | — |",
          f"| Ranging exchanges, both campaign outings (all Initiator rows "
          f"in the canonical offload sets, discarded retakes included) | "
          f"{total:,} | 7,860 |", "",
          "## Changed vs the pre-discard / README values (at README display "
          "precision; includes the discard and, for MAE / signed bias / MAE "
          "ratio, the switch to unrounded per-marker values)", ""]
    L += [f"- {c}" for c in changed] or ["- none"]
    L.append("")

    # Least-squares line of signed error vs marker distance, 406.25 kHz
    # Inputs: the post-discard TABLE 2 / 3
    # per-marker signed errors (0.1 m-rounded, as tabulated).
    L += ["## Signed error vs distance, 406.25 kHz: least-squares line "
          "(post-discard)", "",
          f"Input: `{NEW.as_posix()}` TABLE 2 (static) and TABLE 3 "
          "(stop-and-go), column \"406 err\", against marker distance. "
          "Model: signed error = intercept + slope × distance. Numbers "
          "only.", "",
          "| tier | markers | n | slope (m/m) | slope standard error (m/m) | "
          "intercept (m) | \\|slope\\| < standard error? |",
          "|---|---|---|---|---|---|---|"]
    for n, tier in ((2, "static"), (3, "stop-and-go")):
        rows = matched_table(NEW, n)
        for label, keep in (("all ten", lambda m: True),
                            ("without 240 m", lambda m: m != 240)):
            sel = [r for r in rows if keep(r["marker"])]
            f = linfit([float(r["marker"]) for r in sel],
                       [r["err_406"] for r in sel])
            L.append(f"| {tier} | {label} | {f['n']} | {f['slope']:+.4f} | "
                     f"{f['se_slope']:.4f} | {f['intercept']:+.2f} | "
                     f"{'yes' if abs(f['slope']) < f['se_slope'] else 'no'} |")
    L.append("")
    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {OUT}")
    print("changed after the discard:" if changed else "changed after the discard: none")
    for c in changed:
        print("  " + c.replace("→", "->").replace("×", "x"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
