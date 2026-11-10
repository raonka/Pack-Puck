#!/usr/bin/env python3
"""Pack Pucks: C2 walking-segment analysis, 22 Aug 2026 hand-held runs.

Exploratory. Analyses the Initiator rows logged while the operator walked
between markers in the two single-boot hand-held runs (406.25 kHz restarted
run pucklog_D4DB1C_18.csv; 1625 kHz pucklog_D4DB1C_11.csv), which the paper
(Section IV-B) leaves out.

Walk segments
  Taken from the dwell windows of tools/per_marker_tables.py
  (dwell_windows: spurious laps < 1 s dropped, odd laps are dwells). Walk j
  is the gap between dwell j (marker d_from) and dwell j+1 (marker d_to):
  from the end of the dwell lap to the end of the following walk lap, which
  is the start of the next dwell. No second lap parser is used. Rows strictly
  inside the gap belong to the walk. Only the nine walks between 300 and
  30 m are used; the walk-in below the 30 m marker is excluded.

Ground truth (ASSUMPTION: constant walking speed within each walk)
  d_true(t) = d_from + (d_to - d_from) * (t - t_start) / (t_end - t_start)

Stopwatch offset
  file_time = lap_time + offset. Baseline offset 0 s (as in the paper);
  sensitivity at +0.2 and +1.1 s (the two best fits) and at -0.2 and -1.1 s
  (the sign convention of the original scan is not recorded in code). The
  offset moves the dwell windows and the walk windows together.

Metrics (residual = reading - d_true, SUCCESS rows)
  per segment: median residual, MAE (mean |residual|), residual IQR,
  N rows (all outcomes), N non-SUCCESS, offset-corrected MAE (residual minus
  the static-tier mean signed error of the bandwidth, read from
  data/analysis/aggregates.md), least-squares slope of reading vs time
  against the true speed, and a lag estimate (time shift tau in -3..+3 s,
  0.1 s steps, reading(t) compared with d_true(t - tau), positive tau =
  readings late). The lag uses the rows within 10 s either side of the walk
  with the truth held at the marker distance outside the walk, because
  inside a constant-speed ramp a time shift is the same as a constant range
  offset. Two criteria are reported: A minimises the mean |residual| (as
  specified); B minimises the mean |residual - median residual| (removes a
  constant bias, which otherwise drives A).
  Moving vs stationary: each walk against the mean of the two end-marker
  dwells of the same run (post-discard dwell windows of
  tools/per_marker_tables.py lap_run, same offset).

Uncertainty
  Bootstrap over the nine walk segments, 10,000 replicates,
  random.Random(SEED), 95 % percentile intervals (statistics.quantiles,
  method "inclusive"). The bandwidth comparison is paired by segment (same
  resampled indices at both bandwidths), and the moving-vs-stationary
  comparison pairs each walk with its own end dwells.

Sensitivity: trim 0, 2, 4 s from each end of every walk x offsets above.

Motion onset and offset delays (added 2026-11-05)
  Premise from the operator: the lap boundaries are the true walk start
  and end. Per walk, the times t1 and t2 at which the reading starts and
  stops changing are fitted (held / constant-speed ramp / held, free
  constant). Onset delay = t1 - t_start, offset delay = t2 - t_end, lag
  component = their mean, speed-profile component = half their difference.
  Start-overshoot rows are left out of the fit. Two searches (wide, main;
  narrow, sensitivity); fits on a bound are censored. Plus the slope of
  reading vs time in the 5 s after (and before) each walk end with a
  t-interval, and a per-bandwidth classification: non-uniform walking
  speed, reading lag, or mixed / censored.

Inputs read: raw Initiator CSVs, lap sheets, session plans,
data/analysis/aggregates.md (static bias only). Raw files are read-only.
Outputs:
  data/analysis/c2_walking.md
  data/analysis/figures/c2_walking.png
  data/analysis/figures/c2_walking_paper.png (print variant, paper Fig. 1)

Usage:
    python tools/c2_walking.py
"""

from __future__ import annotations

import math
import re
import statistics
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import per_marker_tables as pmt  # noqa: E402  (RUNS_D2, load_plan, dwell_windows, lap_run)
import qc_session as qc          # noqa: E402  (parse_csv_file, q1_q3)
import uncertainty as unc        # noqa: E402  (t_quantile)

import matplotlib                # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = Path("data/analysis/c2_walking.md")
FIG = Path("data/analysis/figures/c2_walking.png")
FIG_PAPER = Path("data/analysis/figures/c2_walking_paper.png")
AGG = Path("data/analysis/aggregates.md")

SEED = 20261105
REPS = 10_000
TRIMS = (0.0, 2.0, 4.0)
OFFSETS = (0.0, 0.2, 1.1, -0.2, -1.1)
LAG_STEPS = range(-30, 31)          # x 0.1 s -> -3.0 .. +3.0 s
LAG_PAD_S = 10.0
FEW_ROWS = 30                       # analysis flag threshold, not a rule
BWS = ("406.25", "1625")
C_BW = {"406.25": "#d1495b", "1625": "#1f6f8b"}
MARKERS_DESC = sorted(pmt.MARKERS, reverse=True)
ASSUME = "interpolated truth assumes constant walking speed"


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def static_bias() -> dict:
    """Static-tier mean signed error per bandwidth, post-discard column."""
    text = AGG.read_text(encoding="utf-8")
    out = {}
    for bw in BWS:
        m = re.search(r"\| Signed bias, " + re.escape(bw)
                      + r" kHz \| static \| ([+\-−]?[\d.]+) m \|", text)
        if not m:
            sys.exit(f"error: static signed bias for {bw} kHz not in {AGG}")
        out[bw] = float(m.group(1).replace("−", "-"))
    return out


def load_run(bw: str) -> dict:
    cfg = pmt.RUNS_D2[bw]
    plan = pmt.load_plan(cfg["plan"])
    (name,) = plan["stop_and_go"]["files"]       # discarded files dropped
    cf = qc.parse_csv_file(cfg["raw"] / name)
    dws = pmt.dwell_windows(cfg["laps"])
    assert len(dws) == len(MARKERS_DESC), (bw, len(dws))
    walks = []
    for j in range(len(dws) - 1):
        a, b = dws[j][1], dws[j + 1][0]
        assert b > a, (bw, j, a, b)
        walks.append({"j": j + 1, "a": a, "b": b, "d_from": MARKERS_DESC[j],
                      "d_to": MARKERS_DESC[j + 1]})
    return {"bw": bw, "cfg": cfg, "file": name, "rows": cf.rows,
            "dwells": dws, "walks": walks}


# ---------------------------------------------------------------------------
# Per-segment computation
# ---------------------------------------------------------------------------


def ramp(w: dict, a: float, b: float):
    """d_true(t), constant walking speed; held at the marker outside [a, b]."""
    def f(t: float) -> float:
        if t <= a:
            return float(w["d_from"])
        if t >= b:
            return float(w["d_to"])
        return w["d_from"] + (w["d_to"] - w["d_from"]) * (t - a) / (b - a)
    return f


def lsq_slope(x: list[float], y: list[float]) -> float:
    mx, my = statistics.fmean(x), statistics.fmean(y)
    sxx = sum((v - mx) ** 2 for v in x)
    return sum((u - mx) * (v - my) for u, v in zip(x, y)) / sxx


def lag(rows: list, w: dict, a: float, b: float) -> tuple[float, float]:
    """(lag_A, lag_B) in s: argmin over tau of the two criteria."""
    pts = [(r.timestamp_ms / 1000, r.raw_distance_m) for r in rows
           if r.status == "SUCCESS"
           and a - LAG_PAD_S < r.timestamp_ms / 1000 < b + LAG_PAD_S]
    f = ramp(w, a, b)
    best = {"A": None, "B": None}
    for k in LAG_STEPS:
        tau = k / 10
        res = [d - f(t - tau) for t, d in pts]
        med = statistics.median(res)
        crit = {"A": statistics.fmean(abs(x) for x in res),
                "B": statistics.fmean(abs(x - med) for x in res)}
        for c, v in crit.items():
            key = (round(v, 9), abs(k), k)
            if best[c] is None or key < best[c][0]:
                best[c] = (key, tau)
    return best["A"][1], best["B"][1]


def segment(run: dict, w: dict, off: float, trim: float, bias: float) -> dict:
    a, b = w["a"] + off, w["b"] + off
    rows = [r for r in run["rows"]
            if a + trim < r.timestamp_ms / 1000 < b - trim]
    succ = [r for r in rows if r.status == "SUCCESS"]
    f = ramp(w, a, b)
    t = [r.timestamp_ms / 1000 for r in succ]
    d = [r.raw_distance_m for r in succ]
    res = [x - f(s) for s, x in zip(t, d)]
    q1, q3 = qc.q1_q3(res)
    true_v = (w["d_to"] - w["d_from"]) / (b - a)
    slope = lsq_slope(t, d)
    icpt = statistics.fmean(d) - slope * statistics.fmean(t)
    dq1, dq3 = qc.q1_q3([x - (icpt + slope * s) for s, x in zip(t, d)])
    lag_a, lag_b = lag(run["rows"], w, a, b)
    return {"j": w["j"], "d_from": w["d_from"], "d_to": w["d_to"],
            "a": a, "b": b, "dur": b - a, "N": len(rows),
            "n_ns": len(rows) - len(succ),
            "n_neg": sum(1 for x in d if x < 0),
            "med": statistics.median(res), "iqr": q3 - q1,
            "iqr_dt": dq3 - dq1,
            "mae": statistics.fmean(abs(x) for x in res),
            "mae_c": statistics.fmean(abs(x - bias) for x in res),
            "true_v": true_v, "slope": slope, "slope_ratio": slope / true_v,
            "lag_a": lag_a, "lag_b": lag_b}


def dwell_stats(run: dict, off: float, bias: float) -> dict:
    """Post-discard end-marker dwells at this offset (pmt.lap_run)."""
    wins = [(s + off, e + off) for s, e in run["dwells"]]
    st = pmt.lap_run(run["cfg"]["raw"], run["file"], wins, discard=True)
    out = {}
    for m, s in st.items():
        rd = [r.raw_distance_m for r in s["rows"] if r.status == "SUCCESS"]
        out[m] = {"med": s["err"], "iqr": s["iqr"], "N": s["N"],
                  "mae": statistics.fmean(abs(x - m) for x in rd),
                  "mae_c": statistics.fmean(abs(x - m - bias) for x in rd)}
    return out


SEG_KEYS = ("med", "mae", "iqr", "mae_c")


def attach_dwells(segs: list, dw: dict) -> None:
    for s in segs:
        e0, e1 = dw[float(s["d_from"])], dw[float(s["d_to"])]
        for k in SEG_KEYS:
            s["dw_" + k] = (e0[k] + e1[k]) / 2
            s["mv_" + k] = s[k] - s["dw_" + k]
        s["dw_iqr_dt"] = s["dw_iqr"]          # a dwell has no trend to remove
        s["mv_iqr_dt"] = s["iqr_dt"] - s["dw_iqr"]


def compute(runs: dict, bias: dict, off: float, trim: float) -> dict:
    out = {}
    for bw, run in runs.items():
        segs = [segment(run, w, off, trim, bias[bw]) for w in run["walks"]]
        attach_dwells(segs, dwell_stats(run, off, bias[bw]))
        out[bw] = segs
    return out


# ---------------------------------------------------------------------------
# Pooling and bootstrap
# ---------------------------------------------------------------------------

POOLED = (  # key, per-segment field, label
    ("mean_med", "med", "mean of per-segment median residual (m)"),
    ("mae", "mae", "MAE, mean of per-segment MAE (m)"),
    ("mean_iqr", "iqr", "mean residual IQR (m)"),
    ("mean_iqr_dt", "iqr_dt", "mean detrended IQR (m), supplementary"),
    ("mae_c", "mae_c", "offset-corrected MAE (m)"),
    ("mean_abs_med", None, "mean |per-segment median residual| (m)"),
    ("slope_ratio", "slope_ratio", "mean slope ratio (fitted / true speed)"),
    ("lag_b", "lag_b", "mean lag, criterion B (s)"),
    ("lag_a", "lag_a", "mean lag, criterion A (s)"),
)
MOVING = (("med", "median signed error (m)"), ("mae", "MAE (m)"),
          ("iqr", "IQR (m)"), ("mae_c", "offset-corrected MAE (m)"),
          ("iqr_dt", "detrended IQR (m), supplementary"))


def pool(segs: list, idx: list) -> dict:
    p = {}
    for key, fld, _ in POOLED:
        if fld is None:
            p[key] = statistics.fmean(abs(segs[i]["med"]) for i in idx)
        else:
            p[key] = statistics.fmean(segs[i][fld] for i in idx)
    for k, _ in MOVING:
        p["dw_" + k] = statistics.fmean(segs[i]["dw_" + k] for i in idx)
        p["mv_" + k] = statistics.fmean(segs[i]["mv_" + k] for i in idx)
    return p


def all_stats(res: dict) -> dict:
    """{name: value} for every pooled statistic and paired difference."""
    n = len(res[BWS[0]])
    idx = list(range(n))
    return stats_for(res, idx)


def stats_for(res: dict, idx: list) -> dict:
    out = {}
    pl = {bw: pool(res[bw], idx) for bw in BWS}
    for bw in BWS:
        for k, v in pl[bw].items():
            out[(bw, k)] = v
    for k in pl[BWS[0]]:
        out[("diff", k)] = pl["406.25"][k] - pl["1625"][k]
    for k in ("mae", "mae_c", "mean_iqr"):
        out[("ratio", k)] = pl["406.25"][k] / pl["1625"][k]
    return out


def pct95(v: list[float]) -> tuple[float, float]:
    q = statistics.quantiles(v, n=40, method="inclusive")
    return q[0], q[-1]


def bootstrap(res: dict) -> dict:
    n = len(res[BWS[0]])
    rng = random.Random(SEED)
    reps: dict = {}
    for _ in range(REPS):
        idx = [rng.randrange(n) for _ in range(n)]
        for k, v in stats_for(res, idx).items():
            reps.setdefault(k, []).append(v)
    return {k: pct95(v) for k, v in reps.items()}


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def sg(v: float, nd: int = 1) -> str:
    s = f"{v:+.{nd}f}"
    return "+0." + "0" * nd if s in ("-0." + "0" * nd,) else s


def ci(lo_hi: tuple, nd: int = 1, signed: bool = True) -> str:
    lo, hi = lo_hi
    if signed:
        return f"[{sg(lo, nd)}, {sg(hi, nd)}]"
    return f"[{lo:.{nd}f}, {hi:.{nd}f}]"


UNSIGNED = {"mae", "mean_iqr", "mae_c", "mean_abs_med", "slope_ratio",
            "mean_iqr_dt"}


def fv(group: str, key: str, v: float, nd: int = 1) -> str:
    """Signed for signed quantities and differences, plain otherwise."""
    if group in BWS and key in UNSIGNED:
        return f"{v:.{nd}f}"
    return sg(v, nd)


def fci(group: str, key: str, lo_hi: tuple, nd: int = 1) -> str:
    return ci(lo_hi, nd, signed=not (group in BWS and key in UNSIGNED))


def excl0(lo_hi: tuple) -> bool:
    return lo_hi[0] > 0 or lo_hi[1] < 0


# ---------------------------------------------------------------------------
# Figure
# ---------------------------------------------------------------------------


def figure(runs: dict) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(12, 8.2), sharex=True)
    for ax, bw in zip(axes, BWS):
        run = runs[bw]
        dws = run["dwells"]
        for k, (s, e) in enumerate(dws):
            ax.axvspan(s, e, color="#e3e3e3", zorder=0,
                       label="dwell (lap window)" if k == 0 else None)
            ax.plot([s, e], [MARKERS_DESC[k]] * 2, color="#222",
                    linewidth=1.2, zorder=3,
                    label="marker / interpolated truth" if k == 0 else None)
        for k, w in enumerate(run["walks"]):
            ax.axvspan(w["a"], w["b"], color="#f3dfa2", zorder=0,
                       label="walk (analysed)" if k == 0 else None)
            ax.plot([w["a"], w["b"]], [w["d_from"], w["d_to"]],
                    color="#222", linewidth=1.2, zorder=3)
        t_end = run["rows"][-1].timestamp_ms / 1000
        ax.axvspan(dws[-1][1], t_end, facecolor="none", edgecolor="#999",
                   hatch="//", linewidth=0, zorder=0,
                   label="walk-in below 30 m (excluded)")
        t = [r.timestamp_ms / 1000 for r in run["rows"]
             if r.status == "SUCCESS"]
        d = [r.raw_distance_m for r in run["rows"] if r.status == "SUCCESS"]
        ax.plot(t, d, ".", markersize=2.2, color=C_BW[bw], zorder=2,
                label=f"reading, {bw} kHz")
        ax.set_ylabel("distance (m)")
        ax.set_title(f"{bw} kHz hand-held run, {run['file']} "
                     "(stopwatch offset 0 s)", fontsize=11)
        ax.grid(True, alpha=0.3, linewidth=0.6)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.legend(fontsize=8, loc="upper right", ncol=2, framealpha=0.9)
    axes[-1].set_xlabel("time since boot (s)")
    fig.text(0.01, 0.005, "Walk truth is a straight line between markers: "
             + ASSUME + ".", fontsize=8, color="#555")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG, dpi=150, bbox_inches="tight")
    plt.close(fig)


def figure_paper(runs: dict) -> None:
    """Print variant for the paper (Fig. 1): both runs side by side at IEEE
    full-text width, no file names, one shared legend."""
    plt.rcParams.update({"font.size": 8})
    fig, axes = plt.subplots(1, 2, figsize=(7.16, 2.9), sharey=True)
    handles = {}
    for ax, bw in zip(axes, BWS):
        run = runs[bw]
        dws = run["dwells"]
        for k, (s, e) in enumerate(dws):
            h = ax.axvspan(s, e, color="#e3e3e3", zorder=0, linewidth=0)
            handles.setdefault("dwell at a marker", h)
            h, = ax.plot([s, e], [MARKERS_DESC[k]] * 2, color="#222",
                         linewidth=1.0, zorder=3)
            handles.setdefault("marker distance, constant-pace line", h)
        for w in run["walks"]:
            h = ax.axvspan(w["a"], w["b"], color="#f3dfa2", zorder=0,
                           linewidth=0)
            handles.setdefault("walk between markers", h)
            ax.plot([w["a"], w["b"]], [w["d_from"], w["d_to"]],
                    color="#222", linewidth=1.0, zorder=3)
        t_end = run["rows"][-1].timestamp_ms / 1000
        h = ax.axvspan(dws[-1][1], t_end, facecolor="none", edgecolor="#999",
                       hatch="//", linewidth=0, zorder=0)
        handles.setdefault("walk-in below 30 m (excluded)", h)
        t = [r.timestamp_ms / 1000 for r in run["rows"]
             if r.status == "SUCCESS"]
        d = [r.raw_distance_m for r in run["rows"] if r.status == "SUCCESS"]
        h, = ax.plot(t, d, ".", markersize=1.2, color=C_BW[bw], zorder=2)
        handles[f"reading, {bw} kHz"] = h
        ax.set_title(f"{bw} kHz", fontsize=9)
        ax.set_xlabel("time since boot (s)")
        ax.grid(True, alpha=0.3, linewidth=0.5)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[0].set_ylabel("distance (m)")
    fig.legend(list(handles.values()), list(handles.keys()), loc="lower center",
               ncol=3, fontsize=7, frameon=False, markerscale=4,
               bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    fig.savefig(FIG_PAPER, dpi=300, bbox_inches="tight")
    plt.close(fig)
    plt.rcParams.update(plt.rcParamsDefault)


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def seg_tables(res: dict, bias: dict) -> list[str]:
    L = []
    for bw in BWS:
        L += [f"### {bw} kHz, per walk segment (trim 0 s, offset 0 s; "
              f"{ASSUME})", "",
              "| j | from -> to m | window s | dur s | true speed m/s | N rows "
              "| N non-SUCCESS | median residual m | MAE m | residual IQR m | "
              "offset-corr. MAE m | fitted slope m/s | slope ratio | "
              "lag A s | lag B s | detrended IQR m |",
              "|" + "---|" * 16]
        for s in res[bw]:
            L.append(
                f"| {s['j']} | {s['d_from']} -> {s['d_to']} | "
                f"{s['a']:.2f} to {s['b']:.2f} | {s['dur']:.2f} | "
                f"{s['true_v']:+.2f} | {s['N']} | {s['n_ns']} | "
                f"{sg(s['med'])} | {s['mae']:.1f} | {s['iqr']:.1f} | "
                f"{s['mae_c']:.1f} | {s['slope']:+.2f} | "
                f"{s['slope_ratio']:.2f} | {sg(s['lag_a'])} | "
                f"{sg(s['lag_b'])} | {s['iqr_dt']:.1f} |")
        L += ["", f"Offset correction: residual minus {sg(bias[bw])} m "
              "(static-tier mean signed error, `data/analysis/aggregates.md`).",
              ""]
        L += [f"### {bw} kHz, moving vs stationary per segment (trim 0 s, "
              f"offset 0 s; {ASSUME})", "",
              "Dwell value = mean of the two end-marker dwells "
              "(post-discard windows). Delta = walk minus dwell.", "",
              "| j | from -> to m | walk median m | dwell median m | delta | "
              "walk MAE m | dwell MAE m | delta | walk IQR m | dwell IQR m | "
              "delta | walk corr. MAE m | dwell corr. MAE m | delta |",
              "|" + "---|" * 14]
        for s in res[bw]:
            L.append(
                f"| {s['j']} | {s['d_from']} -> {s['d_to']} | "
                f"{sg(s['med'])} | {sg(s['dw_med'])} | {sg(s['mv_med'])} | "
                f"{s['mae']:.1f} | {s['dw_mae']:.1f} | {sg(s['mv_mae'])} | "
                f"{s['iqr']:.1f} | {s['dw_iqr']:.1f} | {sg(s['mv_iqr'])} | "
                f"{s['mae_c']:.1f} | {s['dw_mae_c']:.1f} | "
                f"{sg(s['mv_mae_c'])} |")
        L.append("")
    return L


def pooled_table(st: dict, cis: dict) -> list[str]:
    L = [f"## Pooled over the nine walks (trim 0 s, offset 0 s; {ASSUME})", "",
         "Intervals: 95 % bootstrap percentile over walk segments, paired "
         "by segment for the difference column.", "",
         "| statistic | 406.25 kHz | 95 % CI | 1625 kHz | 95 % CI | "
         "406.25 minus 1625 | 95 % CI (paired) |",
         "|---|---|---|---|---|---|---|"]
    for key, _, label in POOLED:
        nd = 2 if key == "slope_ratio" else 1
        L.append(f"| {label} | {fv('406.25', key, st[('406.25', key)], nd)} | "
                 f"{fci('406.25', key, cis[('406.25', key)], nd)} | "
                 f"{fv('1625', key, st[('1625', key)], nd)}"
                 f" | {fci('1625', key, cis[('1625', key)], nd)} | "
                 f"{sg(st[('diff', key)], nd)} | {ci(cis[('diff', key)], nd)} |")
    for k, label in (("mae", "MAE ratio 406.25 / 1625"),
                     ("mae_c", "offset-corrected MAE ratio"),
                     ("mean_iqr", "mean residual IQR ratio")):
        L.append(f"| {label} | | | | | {st[('ratio', k)]:.2f}x | "
                 f"{ci(cis[('ratio', k)], 2, signed=False)} |")
    L += ["", f"## Moving vs stationary, pooled (trim 0 s, offset 0 s; "
          f"{ASSUME})", "",
          "Walk minus the mean of its two end-marker dwells, averaged over "
          "the nine walks; interval paired by segment.", "",
          "| statistic | 406.25 walk | 406.25 dwell | 406.25 walk minus dwell "
          "| 95 % CI | 1625 walk | 1625 dwell | 1625 walk minus dwell | "
          "95 % CI |", "|---|---|---|---|---|---|---|---|---|"]
    walk_key = {"med": "mean_med", "mae": "mae", "iqr": "mean_iqr",
                "mae_c": "mae_c", "iqr_dt": "mean_iqr_dt"}
    for k, label in MOVING:
        row = f"| {label} |"
        for bw in BWS:
            sgn = k == "med"
            f_ = sg if sgn else (lambda v: f"{v:.1f}")
            row += (f" {f_(st[(bw, walk_key[k])])} | {f_(st[(bw, 'dw_' + k)])}"
                    f" | {sg(st[(bw, 'mv_' + k)])} | "
                    f"{ci(cis[(bw, 'mv_' + k)])} |")
        L.append(row)
    return L + [""]


SENS_COLS = (  # (group, key, label, nd)
    ("406.25", "mae", "406 MAE", 1),
    ("1625", "mae", "1625 MAE", 1),
    ("diff", "mae", "MAE diff 406-1625", 1),
    ("406.25", "mae_c", "406 corr. MAE", 1),
    ("1625", "mae_c", "1625 corr. MAE", 1),
    ("diff", "mae_c", "corr. MAE diff", 1),
    ("406.25", "mean_iqr", "406 mean IQR", 1),
    ("1625", "mean_iqr", "1625 mean IQR", 1),
    ("diff", "mean_iqr", "IQR diff", 1),
    ("406.25", "mean_iqr_dt", "406 detr. IQR", 1),
    ("1625", "mean_iqr_dt", "1625 detr. IQR", 1),
    ("diff", "mean_iqr_dt", "detr. IQR diff", 1),
    ("406.25", "mean_med", "406 mean median", 1),
    ("1625", "mean_med", "1625 mean median", 1),
    ("406.25", "mv_mae", "406 walk-dwell MAE", 1),
    ("1625", "mv_mae", "1625 walk-dwell MAE", 1),
    ("406.25", "mv_iqr", "406 walk-dwell IQR", 1),
    ("1625", "mv_iqr", "1625 walk-dwell IQR", 1),
    ("406.25", "mv_iqr_dt", "406 walk-dwell detr. IQR", 1),
    ("1625", "mv_iqr_dt", "1625 walk-dwell detr. IQR", 1),
    ("406.25", "mv_med", "406 walk-dwell median", 1),
    ("1625", "mv_med", "1625 walk-dwell median", 1),
    ("406.25", "slope_ratio", "406 slope ratio", 2),
    ("1625", "slope_ratio", "1625 slope ratio", 2),
    ("406.25", "lag_b", "406 lag B", 1),
    ("1625", "lag_b", "1625 lag B", 1),
)
FLIP_KEYS = (  # comparisons whose sign is checked for flips
    ("diff", "mae"), ("diff", "mae_c"), ("diff", "mean_iqr"),
    ("diff", "mean_iqr_dt"), ("406.25", "mv_iqr_dt"), ("1625", "mv_iqr_dt"),
    ("406.25", "mv_mae"), ("1625", "mv_mae"), ("406.25", "mv_iqr"),
    ("1625", "mv_iqr"), ("406.25", "mv_med"), ("1625", "mv_med"),
    ("406.25", "mv_mae_c"), ("1625", "mv_mae_c"),
)


self_summary: list[str] = []


def sens_section(sens: dict, base: tuple) -> tuple[list[str], list[str]]:
    L = [f"## Sensitivity: end trim x stopwatch offset ({ASSUME})", "",
         "Each row recomputes every walk (and, for the offset, every dwell "
         "window) and pools over the nine walks. Point estimates; the "
         "interval columns are the 95 % paired bootstrap for the "
         "comparisons whose sign is checked below. Lag does not depend on "
         "the trim (it uses the full walk plus 10 s either side).", "",
         "| trim s | offset s | " + " | ".join(c[2] for c in SENS_COLS) + " |",
         "|" + "---|" * (len(SENS_COLS) + 2)]
    for (trim, off), (st, _) in sens.items():
        L.append(f"| {trim:g} | {sg(off)} | " + " | ".join(
            fv(g, k, st[(g, k)], nd) for g, k, _, nd in SENS_COLS) + " |")
    L += ["", "### Intervals for the checked comparisons", "",
          "| trim s | offset s | " + " | ".join(
              f"{g} {k}" for g, k in FLIP_KEYS) + " |",
          "|" + "---|" * (len(FLIP_KEYS) + 2)]
    for (trim, off), (_, cis) in sens.items():
        L.append(f"| {trim:g} | {sg(off)} | " + " | ".join(
            ci(cis[gk]) for gk in FLIP_KEYS) + " |")
    st0, ci0 = sens[base]
    L += ["", "### How far each metric moves from the baseline "
          "(trim 0 s, offset 0 s)", "",
          "| metric | baseline | min | max | largest abs change |",
          "|---|---|---|---|---|"]
    for g, k, label, nd in SENS_COLS:
        vals = [s[(g, k)] for s, _ in sens.values()]
        L.append(f"| {label} | {fv(g, k, st0[(g, k)], nd)} | "
                 f"{fv(g, k, min(vals), nd)} | {fv(g, k, max(vals), nd)} | "
                 f"{max(abs(v - st0[(g, k)]) for v in vals):.{nd}f} |")
    flags = []
    for gk in FLIP_KEYS:
        s0 = st0[gk] > 0
        e0 = excl0(ci0[gk])
        for cond, (st, cis) in sens.items():
            if (st[gk] > 0) != s0:
                flags.append(f"SIGN FLIP: {gk[0]} {gk[1]} is {sg(st0[gk])} at "
                             f"baseline and {sg(st[gk])} at trim {cond[0]:g} s,"
                             f" offset {sg(cond[1])} s")
            if excl0(cis[gk]) != e0:
                flags.append(f"INTERVAL CHANGE: {gk[0]} {gk[1]} 95 % CI "
                             f"{'excludes' if e0 else 'includes'} 0 at "
                             f"baseline {ci(ci0[gk])} and "
                             f"{'excludes' if excl0(cis[gk]) else 'includes'}"
                             f" 0 at trim {cond[0]:g} s, offset "
                             f"{sg(cond[1])} s {ci(cis[gk])}")
    summ = []
    for gk in FLIP_KEYS:
        ns = sum(1 for s_, _ in sens.values() if (s_[gk] > 0) != (st0[gk] > 0))
        nc = sum(1 for _, c_ in sens.values()
                 if excl0(c_[gk]) != excl0(ci0[gk]))
        if ns or nc:
            summ.append(f"**{gk[0]} {gk[1]}**: baseline {sg(st0[gk])} "
                        f"{ci(ci0[gk])}; sign flips in {ns} of {len(sens)} "
                        f"rows; interval changes whether it excludes 0 in "
                        f"{nc} of {len(sens)} rows.")
    stable = [f"{g} {k}" for g, k in FLIP_KEYS
              if not any(f"**{g} {k}**" in x for x in summ)]
    summ.append("Stable in every row (same sign, same interval status): "
                + ", ".join(stable) + ".")
    self_summary[:] = summ
    L += ["", "### Flip check", ""]
    L += [f"- **{f}**" for f in flags] or [
        "- No sign flip and no change in whether the 95 % interval "
        "excludes 0, for any checked comparison, under any trim or offset."]
    return L + [""], flags


def main() -> int:
    bias = static_bias()
    runs = {bw: load_run(bw) for bw in BWS}

    # Dwell windows at offset 0 must reproduce per_marker_tables.build.
    ref = pmt.build(discard=True)
    for bw, run in runs.items():
        dw = dwell_stats(run, 0.0, bias[bw])
        for m, s in ref[("22 Aug", bw, "stop-and-go")].items():
            assert abs(dw[m]["med"] - s["err"]) < 1e-9 and dw[m]["N"] == s["N"]

    sens, min_n = {}, {}
    for trim in TRIMS:
        for off in OFFSETS:
            res = compute(runs, bias, off, trim)
            sens[(trim, off)] = (all_stats(res), bootstrap(res))
            min_n[(trim, off)] = min(x["N"] for bw in BWS for x in res[bw])
            if (trim, off) == (0.0, 0.0):
                base_res = res
            print(f"trim {trim:g} offset {off:+.1f} done")
    base = (0.0, 0.0)
    st, cis = sens[base]

    figure(runs)
    figure_paper(runs)

    L = ["# Pack Pucks: C2 walking-segment analysis (22 Aug 2026, hand-held "
         "runs)", "",
         "Generated by `tools/c2_walking.py` (raw CSVs read-only). "
         "Exploratory. Every number below is script output.", "",
         "## Inputs", ""]
    for bw in BWS:
        c = runs[bw]["cfg"]
        L += [f"- {bw} kHz: `{(c['raw'] / runs[bw]['file']).as_posix()}`, "
              f"`{c['laps'].as_posix()}`, `{c['plan'].as_posix()}`"]
    L += [f"- Static-tier mean signed error, post-discard: `{AGG.as_posix()}` "
          f"({sg(bias['406.25'])} m at 406.25 kHz, {sg(bias['1625'])} m at "
          "1625 kHz)",
          "- Walk and dwell windows: `tools/per_marker_tables.py` "
          "(`dwell_windows`, `lap_run`); no separate lap parser.", "",
          "## Definitions and assumptions", "",
          "- **Walk segment j:** Initiator rows strictly between the end of "
          "the dwell lap at d_from and the end of the following walk lap "
          "(the start of the dwell at d_to). Nine walks per run, 300 -> 30 m;"
          " the walk-in below 30 m is excluded.",
          "- **Interpolated truth:** d_true(t) = d_from + (d_to - d_from) * "
          "(t - t_start) / (t_end - t_start). **Assumption: constant walking "
          "speed within each walk.** Every residual, MAE, IQR, slope ratio "
          "and lag below depends on it.",
          "- **Residual:** reading minus d_true, SUCCESS rows. Median "
          "residual, MAE = mean |residual|, residual IQR (linear "
          "interpolation, as for the dwell IQRs).",
          "- **Offset-corrected MAE:** mean |residual minus the static-tier "
          "mean signed error of the bandwidth|.",
          "- **Slope ratio:** least-squares slope of reading vs time over the "
          "segment, divided by the true speed (-30 m / walk duration).",
          f"- **Lag:** time shift tau from -3.0 to +3.0 s in 0.1 s steps, "
          f"reading(t) against d_true(t - tau); positive tau = readings late. "
          f"Rows within {LAG_PAD_S:g} s either side of the walk are used, "
          "with the truth held at the marker distance outside the walk, "
          "because inside a constant-speed ramp a time shift is "
          "indistinguishable from a constant range offset. Criterion A "
          "minimises mean |residual|; criterion B minimises mean |residual "
          "minus its median| (removes a constant bias). The estimate is "
          "driven by the two walk ends, where the constant-speed assumption "
          "is weakest.",
          "- **Moving vs stationary:** each walk against the mean of its two "
          "end-marker dwells in the same run (dwell windows after the 5 s "
          "warm-up discard of Methodology 7.2; dwell MAE and corrected MAE "
          "use the row-level definition above with the marker as truth). "
          "Averaging over the nine walks counts the 300 m and 30 m dwells "
          "once and every other dwell twice, so the pooled dwell values "
          "differ from the per-run aggregates in `aggregates.md`.",
          "- **Stopwatch offset:** file time = lap time + offset. Baseline 0 s"
          " as in the paper; +0.2 and +1.1 s are the two best fits, -0.2 and "
          "-1.1 s cover the unrecorded sign convention. The offset moves walk"
          " and dwell windows together.",
          f"- **Bootstrap:** {REPS:,} resamples of the nine walks, "
          f"`random.Random({SEED})` (reseeded per sensitivity row), 95 % "
          "percentile intervals; the bandwidth difference pairs the same "
          "walks at both bandwidths.",
          f"- **Few-row flag:** a segment with fewer than {FEW_ROWS} rows "
          "after trimming (an analysis threshold, not a protocol rule).", ""]
    sens_lines, flips = sens_section(sens, base)
    L += ["## Sensitivity flips: summary", "",
          "Key: `diff` = 406.25 minus 1625 (paired); `mv_` = walk minus "
          "end-marker dwells; `mae_c` = offset-corrected MAE; `_dt` = "
          "detrended. 15 rows = trims 0, 2, 4 s x offsets 0, +0.2, +1.1, "
          "-0.2, -1.1 s. Details in the sensitivity section.", ""]
    L += [f"- {x}" for x in self_summary] + [""]
    L += seg_tables(base_res, bias)
    L += pooled_table(st, cis)
    mot_lines, mot = motion_section(runs, base_res, bias)
    scale_lines, scale = scale_section()
    exc_lines, exc = excursion_section(runs, bias)
    L += mot_lines + exc_lines + scale_lines
    L += sens_lines

    # Data flags
    L += ["## Data flags", ""]
    flags = data_flags(runs, sens, base_res)
    L += [f"- {f}" for f in flags] + [""]

    L += findings(st, cis, base_res, sens, flips, mot, scale, min_n, exc)
    text = "\n".join(L) + "\n"
    lint(text)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}\nwrote {FIG}")
    for f in flips:
        print("FLIP:", f)
    return 0


def data_flags(runs: dict, sens: dict, base_res: dict) -> list[str]:
    out = []
    for bw in BWS:
        lap_lens = []
        for line in runs[bw]["cfg"]["laps"].read_text(
                encoding="utf-8").splitlines()[1:]:
            p = [x.strip() for x in line.split(",")]
            if len(p) >= 4 and p[0].isdigit():
                lap_lens.append((int(p[0]), pmt.mmss(p[3])))
        short = [(n, v) for n, v in lap_lens if v < pmt.SPURIOUS_LAP_S]
        out.append(f"{bw} kHz lap sheet: {len(lap_lens)} laps; laps under "
                   f"{pmt.SPURIOUS_LAP_S:g} s dropped by `dwell_windows`: "
                   + (", ".join(f"lap {n} ({v:.2f} s)" for n, v in short)
                      or "none") + ".")
        durs = [s["dur"] for s in base_res[bw]]
        med = statistics.median(durs)
        for s in base_res[bw]:
            if s["dur"] > 1.25 * med:
                out.append(f"{bw} kHz walk {s['j']} ({s['d_from']} -> "
                           f"{s['d_to']} m) lasts {s['dur']:.1f} s against a "
                           f"median walk of {med:.1f} s: the constant-speed "
                           "truth is least reliable here.")
        t_last = runs[bw]["rows"][-1].timestamp_ms / 1000
        out.append(f"{bw} kHz: walk-in after {runs[bw]['dwells'][-1][1]:.2f} s"
                   f" excluded; last logged row at {t_last:.2f} s.")
    for trim in TRIMS:
        res = compute(runs, static_bias(), 0.0, trim)
        for bw in BWS:
            m = min(res[bw], key=lambda s: s["N"])
            few = [s for s in res[bw] if s["N"] < FEW_ROWS]
            out.append(f"trim {trim:g} s, {bw} kHz: smallest walk N = {m['N']}"
                       f" (walk {m['j']}); walks below {FEW_ROWS} rows: "
                       + (", ".join(str(s["j"]) for s in few) or "none")
                       + f"; non-SUCCESS rows: "
                       f"{sum(s['n_ns'] for s in res[bw])}; negative "
                       f"readings: {sum(s['n_neg'] for s in res[bw])}.")
    for bw in BWS:
        for crit in ("lag_a", "lag_b"):
            at = [s["j"] for s in base_res[bw] if abs(s[crit]) >= 3.0 - 1e-9]
            out.append(f"{bw} kHz {crit.replace('_', ' ')}: walks at the "
                       "+/-3 s search bound: "
                       + (", ".join(map(str, at)) or "none") + ".")
    return out


# Fit searches: (onset delay range s, offset delay range s, row pad s).
# "wide" is the main search (widened 2026-11-05); "narrow" is the search
# before widening, kept as a sensitivity check.
SEARCHES = {"wide": ((-10.0, 20.0), (-20.0, 20.0), 25.0),
            "narrow": ((-10.0, 20.0), (-20.0, 10.0), 15.0)}
ONSET_RANGE, OFFD_RANGE, FIT_PAD_S = SEARCHES["wide"]
FIT_STEP = 0.5
MIN_MOTION_S = 10.0
POST_S = 5.0                  # window after (and before) the walk end
LAG_OFFSETS = (0.0, 0.2, 1.1)


def grid(lo: float, hi: float) -> list[float]:
    return [lo + i * FIT_STEP for i in range(round((hi - lo) / FIT_STEP) + 1)]


def dwell_levels(run: dict, bias: float) -> dict:
    """Median reading of each hand-held dwell (post-discard, offset 0 s)."""
    return {m: m + v["med"] for m, v in dwell_stats(run, 0.0, bias).items()}


def overshoot_ts(run: dict, w: dict, lev0: float) -> set:
    """Timestamps (ms) of start-overshoot rows: SUCCESS rows in the opening
    EXC_S of the walk whose 3-row rolling median (over the walk's rows) is
    more than EXC_M above the level of the dwell just left. Same rule as
    the excursion check; applied at both bandwidths. Offset 0 s."""
    succ = [r for r in run["rows"] if r.status == "SUCCESS"
            and w["a"] < r.timestamp_ms / 1000 < w["b"]]
    rm = qc.rolling_median([r.raw_distance_m for r in succ], 3)
    return {r.timestamp_ms for r, v in zip(succ, rm)
            if r.timestamp_ms / 1000 < w["a"] + EXC_S and v > lev0 + EXC_M}


def motion_fit(run: dict, w: dict, bias: float, mask: set,
               off: float = 0.0, search: str = "wide") -> dict:
    """Fit the times t1, t2 at which the reading starts and stops changing.
    Model: reading = constant + a truth held at d_from until t1, falling at
    constant speed to d_to at t2, then held at d_to. Criterion: mean
    |residual - median residual| (criterion B of the lag search). Grid:
    onset delay t1 - t_start in ONSET_RANGE, offset delay t2 - t_end in
    OFFD_RANGE, 0.5 s steps, t2 - t1 >= 10 s. Rows in `mask` (start
    overshoots) are left out of the fit. t_start, t_end = lap times + off."""
    on_rng, od_rng, pad = SEARCHES[search]
    a, b = w["a"] + off, w["b"] + off
    pts = [(r.timestamp_ms / 1000, r.raw_distance_m) for r in run["rows"]
           if r.status == "SUCCESS" and r.timestamp_ms not in mask
           and a - pad < r.timestamp_ms / 1000 < b + pad]
    best = None
    for on in grid(*on_rng):
        for od in grid(*od_rng):
            t1, t2 = a + on, b + od
            if t2 - t1 < MIN_MOTION_S:
                continue
            f = ramp(w, t1, t2)
            res = [d - f(t) for t, d in pts]
            med = statistics.median(res)
            key = (round(statistics.fmean(abs(x - med) for x in res), 9),
                   abs(on) + abs(od), on, od)
            if best is None or key < best[0]:
                best = (key, on, od)
    _, on, od = best
    t1, t2 = a + on, b + od
    f = ramp(w, t1, t2)
    mv = [d - f(t) for t, d in pts if t1 < t < t2]
    q1, q3 = qc.q1_q3(mv)
    return {"j": w["j"], "onset": on, "offd": od,
            "lag": (on + od) / 2, "prof": (on - od) / 2,
            "on_cens": on in on_rng, "off_cens": od in od_rng,
            "ratio": (b - a) / (t2 - t1), "n_mask": len(mask),
            "n_mv": len(mv), "med": statistics.median(mv), "iqr": q3 - q1,
            "mae": statistics.fmean(abs(x) for x in mv),
            "mae_c": statistics.fmean(abs(x - bias) for x in mv)}


def slope_ci(pts: list) -> tuple[float, float, float, int]:
    """Least-squares slope of reading vs time with a 95 % t-interval."""
    t = [x for x, _ in pts]
    d = [y for _, y in pts]
    n = len(pts)
    sl = lsq_slope(t, d)
    mt, md = statistics.fmean(t), statistics.fmean(d)
    sxx = sum((x - mt) ** 2 for x in t)
    ssr = sum((y - (md + sl * (x - mt))) ** 2 for x, y in pts)
    half = unc.t_quantile(0.975, n - 2) * math.sqrt(ssr / (n - 2) / sxx)
    return sl, sl - half, sl + half, n


def end_slopes(run: dict, w: dict) -> dict:
    """Slope in the POST_S after the walk end and in the POST_S before it
    (offset 0 s, SUCCESS rows)."""
    out = {}
    for key, lo, hi in (("post", w["b"], w["b"] + POST_S),
                        ("pre", w["b"] - POST_S, w["b"])):
        pts = [(r.timestamp_ms / 1000, r.raw_distance_m) for r in run["rows"]
               if r.status == "SUCCESS" and lo < r.timestamp_ms / 1000 <= hi]
        out[key] = slope_ci(pts)
    return out


def boot_means(vals: dict, rng: random.Random) -> dict:
    """Percentile intervals for the mean of each list in `vals` (all the
    same length), resampling one shared index set per replicate (paired)."""
    n = len(next(iter(vals.values())))
    reps = {k: [] for k in vals}
    for _ in range(REPS):
        idx = [rng.randrange(n) for _ in range(n)]
        for k, v in vals.items():
            reps[k].append(statistics.fmean(v[i] for i in idx))
    return {k: (statistics.fmean(vals[k]),) + pct95(reps[k]) for k in vals}


NONUNIFORM = "non-uniform walking speed (ground-truth model)"
LAG = "reading lag"
MIXED = "mixed"


def classify(onset: list, offd: list) -> tuple[str, dict]:
    """Rule from the 2026-11-05 brief, on 95 % bootstrap intervals of the
    mean delays: onset > 0 and offset < 0 -> non-uniform speed; onset > 0
    and offset > 0 with similar size (interval of mean onset - offset
    includes 0) -> reading lag; anything else -> mixed."""
    b = boot_means({"on": onset, "off": offd,
                    "gap": [x - y for x, y in zip(onset, offd)]},
                   random.Random(SEED))
    on_pos = b["on"][1] > 0
    if on_pos and b["off"][2] < 0:
        return NONUNIFORM, b
    if on_pos and b["off"][1] > 0 and not excl0(b["gap"][1:]):
        return LAG, b
    return MIXED, b


def motion_section(runs: dict, base_res: dict, bias: dict
                   ) -> tuple[list[str], dict]:
    out = {}
    lv = {bw: dwell_levels(runs[bw], bias[bw]) for bw in BWS}
    masks = {bw: [overshoot_ts(runs[bw], w, lv[bw][float(w["d_from"])])
                  for w in runs[bw]["walks"]] for bw in BWS}
    for bw in BWS:
        ws = runs[bw]["walks"]
        out[bw] = [motion_fit(runs[bw], w, bias[bw], m)
                   for w, m in zip(ws, masks[bw])]
        out[(bw, "unmasked")] = [motion_fit(runs[bw], w, bias[bw], set())
                                 for w in ws]
        out[(bw, "slopes")] = [end_slopes(runs[bw], w) for w in ws]
        out[(bw, "narrow")] = [motion_fit(runs[bw], w, bias[bw], m,
                                          search="narrow")
                               for w, m in zip(ws, masks[bw])]

    L = ["## Motion onset and offset delays (supplementary)", "",
         "Premise (operator, 2026-11-05): the lap log marks the true start "
         "and end of each walk, so t_start and t_end are taken as the true "
         "motion times. For each walk the reading is fitted with a truth held"
         " at d_from until t1, falling at constant speed to d_to at t2, then "
         "held, plus a free constant; criterion B of the lag search. "
         "**Onset delay** = t1 - t_start; **offset delay** = t2 - t_end "
         "(positive = reading still changing after the walk ended). Search: "
         f"onset {sg(ONSET_RANGE[0])} to {sg(ONSET_RANGE[1])} s, offset "
         f"{sg(OFFD_RANGE[0])} to {sg(OFFD_RANGE[1])} s, {FIT_STEP:g} s "
         f"steps, at least {MIN_MOTION_S:g} s of motion, rows within "
         f"{FIT_PAD_S:g} s either side of the walk, offset 0 s. A fit on a "
         "search bound is censored (marked `c`). Start-overshoot rows (the "
         "rows behind the start excursions of the excursion check: 3-row "
         f"rolling median more than {EXC_M:g} m above the level of the dwell"
         f" just left, within {EXC_S:g} s of t_start) are left out of the "
         "fit at both bandwidths; the unmasked onset is listed for "
         "comparison. Under a pure reading lag both delays equal the lag; "
         "under a walking speed that is slower at the ends than in the "
         "middle the onset is positive and the offset negative. Hence "
         "**lag component** = (onset + offset) / 2 and **speed-profile "
         "component** = (onset - offset) / 2. A stopwatch offset moves both "
         "delays by the same amount, so it moves the lag component one for "
         "one and leaves the speed-profile component unchanged.", "",
         "| BW kHz | " + " | ".join(f"walk {j}" for j in range(1, 10))
         + " | mean | 95 % CI |", "|" + "---|" * 12]

    def cell(f, fld, cens):
        return sg(f[fld]) + (" c" if f[cens] else "")

    for bw in BWS:
        fits, um = out[bw], out[(bw, "unmasked")]
        b = boot_means({k: [f[k] for f in fits]
                        for k in ("onset", "offd", "lag", "prof", "ratio")},
                       random.Random(SEED))
        b["onset_um"] = boot_means({"x": [f["onset"] for f in um]},
                                   random.Random(SEED))["x"]
        for fld, label, cens in (("onset", "onset delay s", "on_cens"),
                                 ("offd", "offset delay s", "off_cens")):
            L.append(f"| {bw} {label} | " + " | ".join(
                cell(f, fld, cens) for f in fits)
                + f" | {sg(b[fld][0])} | {ci(b[fld][1:])} |")
        L.append(f"| {bw} onset delay, unmasked s | " + " | ".join(
            cell(f, "onset", "on_cens") for f in um)
            + f" | {sg(b['onset_um'][0])} | {ci(b['onset_um'][1:])} |")
        for fld, label in (("lag", "lag component s"),
                           ("prof", "speed-profile component s")):
            L.append(f"| {bw} {label} | " + " | ".join(
                sg(f[fld]) for f in fits)
                + f" | {sg(b[fld][0])} | {ci(b[fld][1:])} |")
        L.append(f"| {bw} speed ratio | " + " | ".join(
            f"{f['ratio']:.2f}" for f in fits)
            + f" | {b['ratio'][0]:.2f} | {ci(b['ratio'][1:], 2, False)} |")
        drop = [lv[bw][float(w["d_from"])] - lv[bw][float(w["d_to"])]
                for w in runs[bw]["walks"]]
        out[(bw, "drop")] = drop
        L.append(f"| {bw} reading change between end dwells m | " + " | ".join(
            f"{v:.1f}" for v in drop) + f" | {statistics.fmean(drop):.1f} | |")
        L.append(f"| {bw} start-overshoot rows left out | " + " | ".join(
            str(f["n_mask"]) for f in fits)
            + f" | {sum(f['n_mask'] for f in fits)} in total | |")
        out[(bw, "pool")] = b
        out[(bw, "cens")] = [f["j"] for f in fits
                             if f["on_cens"] or f["off_cens"]]
        out[(bw, "cens_um")] = [f["j"] for f in um
                                if f["on_cens"] or f["off_cens"]]

    # Paired difference between bandwidths, walk by walk.
    pd = boot_means({k: [x[k] - y[k] for x, y in zip(out["406.25"],
                                                     out["1625"])]
                     for k in ("onset", "offd", "lag", "prof")},
                    random.Random(SEED))
    out["pdiff"] = pd
    L += ["", "Censored fits (`c`): " + "; ".join(
        f"{bw} kHz " + (", ".join(f"walk {j}" for j in out[(bw, 'cens')])
                        or "none") for bw in BWS)
        + ". Unmasked, with the same widened bounds: " + "; ".join(
        f"{bw} kHz " + (", ".join(f"walk {j}" for j in out[(bw, 'cens_um')])
                        or "none") for bw in BWS)
        + ". Speed ratio = walk duration / fitted motion duration. The "
        "model holds the reading change across a walk at 30 m; the row "
        "'reading change between end dwells' gives the change the dwells "
        "actually show (median dwell readings).", "",
        "Paired difference, 406.25 minus 1625 (same walk at both "
        "bandwidths), 95 % bootstrap:", "",
        "| delay | mean difference s | 95 % CI |", "|---|---|---|"]
    for k, label in (("onset", "onset delay"), ("offd", "offset delay"),
                     ("lag", "lag component"),
                     ("prof", "speed-profile component")):
        L.append(f"| {label} | {sg(pd[k][0])} | {ci(pd[k][1:])} |")

    # Reading change after (and before) the walk end.
    L += ["", "### Does the reading change after the walk ends?", "",
          f"Least-squares slope of reading vs time over the {POST_S:g} s after"
          f" t_end (post) and, for comparison, the {POST_S:g} s before it "
          "(pre), with 95 % t-intervals (n - 2 degrees of freedom), offset "
          "0 s. The true speed during a walk is about -1 m/s; after t_end it"
          " is 0. `*` = interval excludes 0.", "",
          "| BW kHz | window | " + " | ".join(f"walk {j}" for j in range(1, 10))
          + " | walks with change | mean slope m/s | 95 % CI | "
          "median interval half-width m/s |",
          "|" + "---|" * 15]
    for bw in BWS:
        sl = out[(bw, "slopes")]
        for key in ("post", "pre"):
            v = [x[key] for x in sl]
            nchg = sum(1 for x in v if x[1] > 0 or x[2] < 0)
            nneg = sum(1 for x in v if x[2] < 0)
            b = boot_means({"x": [x[0] for x in v]}, random.Random(SEED))["x"]
            hw = statistics.median((x[2] - x[1]) / 2 for x in v)
            out[(bw, key)] = (nchg, b, [x[3] for x in v], nneg, hw)
            L.append(f"| {bw} | {key} | " + " | ".join(
                f"{x[0]:+.2f} [{x[1]:+.2f}, {x[2]:+.2f}]"
                + ("*" if x[1] > 0 or x[2] < 0 else "") for x in v)
                + f" | {nchg} of 9 | {b[0]:+.2f} | {ci(b[1:], 2)} | "
                f"{hw:.2f} |")
    nmin = min(n for bw in BWS for key in ("post", "pre")
               for n in out[(bw, key)][2])
    L += ["", f"Rows per {POST_S:g} s window: at least {nmin}.", ""]

    # Lag component at the stopwatch offsets.
    L += ["### Lag component at the stopwatch offsets", "",
          "The masked fit rerun with the walk boundaries moved by the offset "
          "(file time = lap time + offset).", "",
          "| BW kHz | offset s | mean lag component s | 95 % CI | mean "
          "speed-profile component s | 95 % CI | censored fits |",
          "|---|---|---|---|---|---|---|"]
    for bw in BWS:
        for off in LAG_OFFSETS:
            fits = out[bw] if off == 0.0 else [
                motion_fit(runs[bw], w, bias[bw], m, off)
                for w, m in zip(runs[bw]["walks"], masks[bw])]
            b = boot_means({k: [f[k] for f in fits] for k in ("lag", "prof")},
                           random.Random(SEED))
            nc = sum(1 for f in fits if f["on_cens"] or f["off_cens"])
            out[(bw, "lag_off", off)] = b
            L.append(f"| {bw} | {sg(off)} | {sg(b['lag'][0])} | "
                     f"{ci(b['lag'][1:])} | {sg(b['prof'][0])} | "
                     f"{ci(b['prof'][1:])} | {nc} |")

    # Classification.
    L += ["", "### Classification per bandwidth", "",
          "Rule (on the 95 % intervals of the mean delays): onset > 0 and "
          "offset < 0 -> non-uniform walking speed (ground-truth model); "
          "onset > 0 and offset > 0 with similar size (interval of mean "
          "onset minus offset includes 0) -> reading lag; otherwise mixed. "
          "If any fit is censored the rule is repeated without the censored "
          "walks, and the result is reported as censored when the two "
          "disagree. Each bandwidth is classified under the main (wide) "
          "search and the narrower search used before widening.", "",
          "| BW kHz | search | mean onset s | mean offset s | walks with "
          "onset > 0, offset < 0 | walks with both > 0 | other walks | "
          "class, all walks | class, uncensored walks | result |",
          "|" + "---|" * 10]
    for bw in BWS:
        for search in ("wide", "narrow"):
            fits = out[bw] if search == "wide" else out[(bw, "narrow")]
            on = [f["onset"] for f in fits]
            od = [f["offd"] for f in fits]
            n_nu = sum(1 for x, y in zip(on, od) if x > 0 and y < 0)
            n_lag = sum(1 for x, y in zip(on, od) if x > 0 and y > 0)
            c_all, bb = classify(on, od)
            unc_f = [f for f in fits if not (f["on_cens"] or f["off_cens"])]
            if len(unc_f) >= 5:
                c_unc = classify([f["onset"] for f in unc_f],
                                 [f["offd"] for f in unc_f])[0]
            else:
                c_unc = "too few walks"
            ncens = len(fits) - len(unc_f)
            if ncens == 0:
                res = c_all
            elif c_unc == c_all:
                res = (f"{c_all} ({ncens} censored fit(s); same class "
                       "without them)")
            else:
                res = (f"censored ({ncens} censored fit(s) change the "
                       "class)")
            if c_all == LAG:
                res += f"; lag estimate {sg(bb['on'][0])} s"
            out[(bw, "class", search)] = (res, c_all, c_unc, n_nu, n_lag,
                                          ncens, bb)
            o_rng, d_rng, pad = SEARCHES[search]
            L.append(f"| {bw} | {search} (offset {sg(d_rng[0])} to "
                     f"{sg(d_rng[1])} s, pad {pad:g} s) | "
                     f"{sg(bb['on'][0])} {ci(bb['on'][1:])} | "
                     f"{sg(bb['off'][0])} {ci(bb['off'][1:])} | {n_nu} | "
                     f"{n_lag} | {9 - n_nu - n_lag} | {c_all} | {c_unc} | "
                     f"{res} |")
    L.append("")

    # Moving-only rows, fitted timing, against the end-marker dwells.
    L += ["### Moving rows only, fitted timing (supplementary)", "",
          "Rows with t1 < t < t2 only (start-overshoot rows left out), truth "
          "= the fitted ramp (constant speed between t1 and t2). Dwell = mean"
          " of the two end-marker dwells, as above. The fit uses the readings"
          " to place t1 and t2, so the spread here is, if anything, an "
          "underestimate. Intervals: 95 % bootstrap over walks, paired by "
          "segment.", "",
          "| statistic | 406.25 moving | 406.25 dwell | walk minus dwell | "
          "95 % CI | 1625 moving | 1625 dwell | walk minus dwell | 95 % CI | "
          "406.25 minus 1625 (moving) | 95 % CI |",
          "|" + "---|" * 11]
    keys = (("med", "median signed error (m)"), ("mae", "MAE (m)"),
            ("iqr", "IQR (m)"), ("mae_c", "offset-corrected MAE (m)"))
    rng = random.Random(SEED)
    reps = {}
    for _ in range(REPS):
        idx = [rng.randrange(9) for _ in range(9)]
        for k, _l in keys:
            mvs = {}
            for bw in BWS:
                mvs[bw] = statistics.fmean(out[bw][i][k] for i in idx)
                reps.setdefault((bw, k), []).append(mvs[bw] - statistics.fmean(
                    base_res[bw][i]["dw_" + k] for i in idx))
            reps.setdefault(("diff", k), []).append(mvs["406.25"]
                                                    - mvs["1625"])
    for k, label in keys:
        f_ = sg if k == "med" else (lambda v: f"{v:.1f}")
        row = f"| {label} |"
        mv = {}
        for bw in BWS:
            mv[bw] = statistics.fmean(x[k] for x in out[bw])
            dw = statistics.fmean(x["dw_" + k] for x in base_res[bw])
            out[("mv", bw, k)] = (mv[bw] - dw,) + pct95(reps[(bw, k)])
            row += (f" {f_(mv[bw])} | {f_(dw)} | {sg(mv[bw] - dw)} | "
                    f"{ci(pct95(reps[(bw, k)]))} |")
        out[("mvdiff", k)] = ((mv["406.25"] - mv["1625"],)
                              + pct95(reps[("diff", k)]))
        row += (f" {sg(mv['406.25'] - mv['1625'])} | "
                f"{ci(pct95(reps[('diff', k)]))} |")
        L.append(row)
    nmv = {bw: [x["n_mv"] for x in out[bw]] for bw in BWS}
    L += ["", "Moving rows per walk: " + "; ".join(
        f"{bw} kHz {min(nmv[bw])} to {max(nmv[bw])}" for bw in BWS) + ".", ""]
    return L, out


EXC_S = 10.0       # window at each walk end for the excursion check
EXC_M = 5.0        # reported threshold (m), an analysis choice


def excursion_section(runs: dict, bias: dict) -> tuple[list[str], dict]:
    """Supplementary: does the reading move away from the walk direction at
    the ends of a walk? Start: highest 3-row rolling median in the opening
    10 s of the walk minus the median reading of the dwell just left. End:
    lowest 3-row rolling median in the closing 10 s minus the median
    reading of the dwell just reached. Offset 0 s. Since the walk is a
    descent, a positive start value or a negative end value is a reading
    moving against the walk direction."""
    L = ["## Supplementary check: reading excursions at the walk ends", "",
         f"Start excursion = highest 3-row rolling median in the opening "
         f"{EXC_S:g} s of the walk minus the median reading of the dwell just"
         f" left; end excursion = lowest 3-row rolling median in the closing "
         f"{EXC_S:g} s minus the median reading of the dwell just reached "
         "(offset 0 s). The walks descend, so a positive start value or a "
         "negative end value is a reading moving against the walk "
         f"direction. Count = walks beyond {EXC_M:g} m (an analysis "
         "threshold).", "",
         "| BW kHz | " + " | ".join(f"walk {j}" for j in range(1, 10))
         + " | count |", "|" + "---|" * 11]
    out = {}
    for bw in BWS:
        run = runs[bw]
        dw = dwell_stats(run, 0.0, bias[bw])
        starts, ends = [], []
        for w in run["walks"]:
            succ = [r for r in run["rows"] if r.status == "SUCCESS"
                    and w["a"] < r.timestamp_ms / 1000 < w["b"]]
            t = [r.timestamp_ms / 1000 for r in succ]
            rm = qc.rolling_median([r.raw_distance_m for r in succ], 3)
            lev0 = w["d_from"] + dw[float(w["d_from"])]["med"]
            lev1 = w["d_to"] + dw[float(w["d_to"])]["med"]
            starts.append(max(v for v, s_ in zip(rm, t)
                              if s_ < w["a"] + EXC_S) - lev0)
            ends.append(min(v for v, s_ in zip(rm, t)
                            if s_ > w["b"] - EXC_S) - lev1)
        out[(bw, "start")] = sum(1 for v in starts if v > EXC_M)
        out[(bw, "end")] = sum(1 for v in ends if v < -EXC_M)
        out[(bw, "start_v")], out[(bw, "end_v")] = starts, ends
        L.append(f"| {bw} start m | " + " | ".join(sg(v) for v in starts)
                 + f" | {out[(bw, 'start')]} above +{EXC_M:g} |")
        L.append(f"| {bw} end m | " + " | ".join(sg(v) for v in ends)
                 + f" | {out[(bw, 'end')]} below -{EXC_M:g} |")
    return L + [""], out


def scale_section() -> tuple[list[str], dict]:
    """Supplementary: reading-vs-distance scale from the dwell medians."""
    ref = pmt.build(discard=True)
    L = ["## Supplementary check: reading scale from the stationary data", "",
         "Least-squares slope of the per-marker median reading against the "
         "marker distance (post-discard), 30 to 300 m. A slope of 1 means a "
         "30 m change in true distance gives a 30 m change in reading. This "
         "tests whether a reading scale factor could explain a walk slope "
         "ratio above 1.", "",
         "| BW kHz | static | hand-held dwells |", "|---|---|---|"]
    out = {}
    for bw in BWS:
        row = f"| {bw} |"
        for tier in ("static", "stop-and-go"):
            st = ref[("22 Aug", bw, tier)]
            ms = sorted(st)
            sl = lsq_slope(ms, [st[m]["median"] for m in ms])
            out[(bw, tier)] = sl
            row += f" {sl:.3f} |"
        L.append(row)
    return L + [""], out


def findings(st, cis, base_res, sens, flips, mot, scale, min_n, exc
             ) -> list[str]:
    """Observations only. Each qualitative word is checked by an assertion,
    so a change in the data stops the script instead of leaving stale text."""
    W, N = "406.25", "1625"
    rows = len(sens)

    def holds(gk, positive=True):
        """Rows where the comparison keeps its sign and its CI excludes 0."""
        return sum(1 for s_, c_ in sens.values()
                   if (s_[gk] > 0) == positive and excl0(c_[gk]))

    def rng_(gk):
        v = [s_[gk] for s_, _ in sens.values()]
        return min(v), max(v)

    n_seg = {bw: len(base_res[bw]) for bw in BWS}
    n_rows = {bw: [x["N"] for x in base_res[bw]] for bw in BWS}
    n_ns = sum(x["n_ns"] for bw in BWS for x in base_res[bw])
    n_neg = sum(x["n_neg"] for bw in BWS for x in base_res[bw])
    sr_gt1 = {bw: sum(1 for x in base_res[bw] if x["slope_ratio"] > 1)
              for bw in BWS}
    assert all(abs(v - 1) < 0.02 for v in scale.values())
    cls = {(bw, sr): mot[(bw, "class", sr)] for bw in BWS
           for sr in ("wide", "narrow")}
    assert all(cls[(N, sr)][1] == NONUNIFORM and cls[(N, sr)][5] == 0
               for sr in ("wide", "narrow"))
    assert all(cls[(W, sr)][1] == MIXED for sr in ("wide", "narrow"))
    assert mot[(W, "cens")] == [4] and mot[(N, "cens")] == []
    drop = mot[(W, "drop")]
    assert drop.index(min(drop)) == 3                 # walk 4
    pool = {bw: mot[(bw, "pool")] for bw in BWS}
    lagN = pool[N]["lag"]
    assert lagN[2] < 0                                # negative lag component
    post = {bw: mot[(bw, "post")] for bw in BWS}
    assert post[N][0] <= 1 and post[W][0] == 0 and post[W][4] > 1.0
    lag11 = mot[(N, "lag_off", 1.1)]["lag"]
    mask_shift = {bw: pool[bw]["onset"][0] - pool[bw]["onset_um"][0]
                  for bw in BWS}
    assert all(abs(v) < 0.5 for v in mask_shift.values())

    d_mae = holds(("diff", "mae"))
    assert d_mae == rows
    d_iqr = holds(("diff", "mean_iqr"))
    assert d_iqr == rows
    c_in = rows - holds(("diff", "mae_c"))
    c_flip = sum(1 for s_, _ in sens.values() if s_[("diff", "mae_c")] < 0)
    assert c_in > 0
    mv_iqr = {bw: holds((bw, "mv_iqr")) for bw in BWS}
    assert all(v == rows for v in mv_iqr.values())
    w_flip = sum(1 for s_, _ in sens.values() if s_[(W, "mv_med")] < 0)
    assert w_flip > 0
    assert all(k[1] == 1.1 for k, (s_, _) in sens.items()
               if s_[(W, "mv_med")] < 0)
    assert st[("diff", "mae_c")] < 0.5 * st[("diff", "mae")]
    n_med_in = rows - holds((N, "mv_med"), positive=False)
    lagA_bound = sum(1 for x in base_res[W] if abs(x["lag_a"]) >= 3 - 1e-9)
    lagB_bound = {bw: sum(1 for x in base_res[bw] if abs(x["lag_b"]) >= 3 - 1e-9)
                  for bw in BWS}
    mvN = mot[("mv", N, "med")]
    assert mvN[1] < 0 < mvN[2]                        # fitted motion: none
    assert cis[(N, "mv_med")][1] < 0                  # interpolated: shift
    mi = {bw: mot[("mv", bw, "iqr")] for bw in BWS}
    assert all(mi[bw][0] < st[(bw, "mv_iqr")] for bw in BWS)

    exN = exc[(N, "start")] + exc[(N, "end")]
    exW = exc[(W, "start")] + exc[(W, "end")]
    assert exN <= 1 and exW >= 5
    lo_d, hi_d = rng_(("diff", "mae"))
    lo_c, hi_c = rng_(("diff", "mae_c"))
    L = ["## Findings (observations only)", "",
         f"1. **Coverage.** {n_seg[W]} walks per run, {min(n_rows[W])} to "
         f"{max(n_rows[W])} rows per walk at 406.25 kHz and "
         f"{min(n_rows[N])} to {max(n_rows[N])} at 1625 kHz; {n_ns} "
         f"non-SUCCESS rows and {n_neg} negative readings across all 18 walks."
         " With the 4 s trim the smallest walk keeps "
         f"{min_n[(4.0, 0.0)]} rows.",
         f"2. **The constant-speed truth does not match the readings.** The "
         f"fitted slope of reading vs time exceeds the true mean walking "
         f"speed in {sr_gt1[W]} of 9 walks at 406.25 kHz and {sr_gt1[N]} of 9"
         f" at 1625 kHz (mean ratio {st[(W, 'slope_ratio')]:.2f} and "
         f"{st[(N, 'slope_ratio')]:.2f}), while the stationary per-marker "
         f"medians scale with distance at slopes of "
         f"{min(scale.values()):.3f} to {max(scale.values()):.3f}. Taking the"
         " lap boundaries as the true walk start and end, the onset delay is "
         f"{sg(pool[N]['onset'][0])} s {ci(pool[N]['onset'][1:])} and the "
         f"offset delay {sg(pool[N]['offd'][0])} s "
         f"{ci(pool[N]['offd'][1:])} at 1625 kHz (the reading stops changing"
         " before the walk ends); at 406.25 kHz they are "
         f"{sg(pool[W]['onset'][0])} s {ci(pool[W]['onset'][1:])} and "
         f"{sg(pool[W]['offd'][0])} s {ci(pool[W]['offd'][1:])} (finding 9)."
         " At 1625 kHz the walk-end "
         f"excursions exceed 5 m at {exN} of 18 walk ends, so the motion fit "
         "and the slope ratio there are not driven by them; at 406.25 kHz "
         "they are confounded with the excursions of finding 8.",
         f"3. **Bandwidth ordering while walking.** MAE against the "
         f"interpolated truth is {st[(W, 'mae')]:.1f} m at 406.25 kHz and "
         f"{st[(N, 'mae')]:.1f} m at 1625 kHz, paired difference "
         f"{sg(st[('diff', 'mae')])} m {ci(cis[('diff', 'mae')])}. The sign "
         f"holds and the interval excludes 0 in {d_mae} of {rows} sensitivity"
         f" rows (difference {sg(lo_d)} to {sg(hi_d)} m).",
         f"4. **Most of that difference is the fixed static bias.** After "
         f"subtracting the static-tier mean signed error, the paired MAE "
         f"difference is {sg(st[('diff', 'mae_c')])} m "
         f"{ci(cis[('diff', 'mae_c')])}. **Its interval includes 0 in {c_in} "
         f"of {rows} sensitivity rows and its sign flips in {c_flip}** "
         f"(range {sg(lo_c)} to {sg(hi_c)} m).",
         f"5. **Spread while walking.** The residual IQR is larger at "
         f"406.25 kHz than at 1625 kHz by {sg(st[('diff', 'mean_iqr')])} m "
         f"{ci(cis[('diff', 'mean_iqr')])} (interval excludes 0 in {d_iqr} of"
         f" {rows} rows), and larger while walking than at the end-marker "
         f"dwells at both bandwidths ({sg(st[(W, 'mv_iqr')])} and "
         f"{sg(st[(N, 'mv_iqr')])} m; all {rows} rows). Part of this excess is"
         f" the truth model: on moving rows only, with fitted timing, the "
         f"walk-minus-dwell IQR is {sg(mi[W][0])} m {ci(mi[W][1:])} at "
         f"406.25 kHz and {sg(mi[N][0])} m {ci(mi[N][1:])} at 1625 kHz.",
         f"6. **Signed error while walking vs stationary.** At 1625 kHz the "
         f"walk median residual is {sg(st[(N, 'mv_med')])} m "
         f"{ci(cis[(N, 'mv_med')])} relative to the end dwells against the "
         f"constant-speed interpolated truth (interval includes 0 in "
         f"{n_med_in} of {rows} rows), and {sg(mvN[0])} m {ci(mvN[1:])} on "
         f"moving rows against the fitted motion timing. At 406.25 kHz it "
         f"is {sg(st[(W, 'mv_med')])} m {ci(cis[(W, 'mv_med')])} and **its "
         f"sign flips in {w_flip} of {rows} rows** (all at offset +1.1 s).",
         f"7. **Lag.** The interpolation-based lag search is not "
         f"informative: criterion A sits on the +/-3 s bound in {lagA_bound} "
         f"of 9 walks at 406.25 kHz and criterion B in {lagB_bound[W]} and "
         f"{lagB_bound[N]} of 9 walks. The onset/offset decomposition gives a "
         f"lag component of {sg(lagN[0])} s {ci(lagN[1:])} at 1625 kHz "
         f"(offset 0 s; {sg(lag11[0])} s {ci(lag11[1:])} at offset +1.1 s), "
         "below zero, which a reading delay cannot produce. In the 5 s after "
         f"the walk ends the 1625 kHz reading changes in {post[N][0]} of 9 "
         f"walks (mean slope {post[N][1][0]:+.2f} m/s "
         f"{ci(post[N][1][1:], 2)}, median interval half-width "
         f"{post[N][4]:.2f} m/s). At 406.25 kHz the lag component is "
         f"{sg(pool[W]['lag'][0])} s {ci(pool[W]['lag'][1:])} and the reading "
         f"changes after the walk end in {post[W][0]} of 9 walks, but the "
         f"median interval half-width there is {post[W][4]:.2f} m/s, wider "
         "than the walking speed, so that check cannot detect a change of "
         "walking size. A stopwatch offset moves the lag component one for "
         f"one, so a lag no larger than the offset uncertainty (up to "
         f"{sg(max(LAG_OFFSETS))} s) is not separable from it.",
         f"8. **Excursions at the walk ends, 406.25 kHz.** The 3-row rolling "
         f"median rises more than 5 m above the level of the dwell just left "
         f"in {exc[(W, 'start')]} of 9 walk starts (largest "
         f"{sg(max(exc[(W, 'start_v')]))} m) and falls more than 5 m below "
         f"the level of the dwell just reached in {exc[(W, 'end')]} of 9 walk "
         f"ends (largest {sg(min(exc[(W, 'end_v')]))} m). At 1625 kHz the "
         f"counts are {exc[(N, 'start')]} and {exc[(N, 'end')]}. Both "
         "directions steepen the fitted slope of a walk.",
         f"9. **Classification (rule of the 2026-11-05 brief).** 1625 kHz: "
         f"**{cls[(N, 'wide')][0]}** under both fit searches; "
         f"{cls[(N, 'wide')][3]} of 9 walks have onset > 0 and offset < 0, "
         f"none is censored, and the speed-profile component is "
         f"{sg(pool[N]['prof'][0])} s {ci(pool[N]['prof'][1:])}. "
         f"406.25 kHz: **{cls[(W, 'wide')][0]}** under the main search and "
         f"**{cls[(W, 'narrow')][0]}** under the narrower one. Walk 4 "
         "(210 -> 180 m) is censored in both: its end dwells differ by "
         f"{min(drop):.1f} m in reading against 30 m of walk. Leaving the "
         "start-overshoot rows out of the fit moves the mean onset by "
         f"{sg(mask_shift[W])} s at 406.25 kHz and {sg(mask_shift[N])} s at "
         "1625 kHz.",
         ""]
    L += ["## Candidate explanations (untested by this analysis)", "",
          "- What makes the walking speed non-uniform at 1625 kHz "
          "(finding 9), for example slowing to set the carried tripod on the cone mark; "
          "there is no independent record of the motion within a walk.",
          "- Body shadowing, tripod sway or changing antenna orientation while "
          "walking, or while lifting and setting down the tripod (findings 5 "
          "and 8).",
          "- Position-dependent multipath along the walk (findings 5, 6).",
          "- A reading lag at 406.25 kHz (findings 7 and 9 leave it "
          "unresolved).", ""]
    return L


def lint(text: str) -> None:
    bad = []
    if chr(0x2014) in text:
        bad.append("em dash")
    if re.search(r"\bfirst\b", text, re.I):
        bad.append("priority wording")
    if re.search(r"\bnovel", text, re.I):
        bad.append("novelty wording")
    if bad:
        sys.exit("lint failed: " + ", ".join(bad))


if __name__ == "__main__":
    sys.exit(main())
