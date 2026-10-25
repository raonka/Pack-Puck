#!/usr/bin/env python3
"""Pack Pucks — per-marker tables with the Methodology §7.2 warm-up discard.

Regenerates the per-marker statistics for the two GMA township campaign
outings (15 Aug and 22 Aug 2026) with the first-5-s discard of
Methodology §7.2 applied, alongside (never over) the existing tables:

  - data/analysis/2026-08-22_GMATownship_day2_qc_tables.md   (kept as-is)
  - data/analysis/2026-08-15_GMATownship_184714_qc/*/report.md (kept as-is)

Discard rule (Methodology §7.2; first applied 2026-10-10):
  - Static (one boot per marker): drop every row whose timestamp is
    <= 5.0 s after the file's first logged row. This is the same window
    qc_session.py reports as "warm-up" in §3 of each QC report.
  - Stop-and-go, 22 Aug (operator arrival log): each dwell window is a
    dwell lap of the stopwatch sheet, on the file's timestamp_ms axis
    (stopwatch started at puck boot, offset 0 s). Drop every row <= 5.0 s
    after the first logged row inside that window.
  - Stop-and-go, 15 Aug (no arrival log): dwell windows are
    qc_session.py's heuristic plateaus (same defaults as the published
    report); same per-window rule.

Before writing anything, the no-discard recomputation is checked against
the published values (median, IQR, N per marker). A mismatch aborts.

Raw CSVs are opened read-only. Outputs:
  data/analysis/2026-08-22_GMATownship_day2_tables_discard5s.md
  data/analysis/2026-08-15_GMATownship_day1_tables_discard5s.md
  data/analysis/achieved_n.md
  data/analysis/f4_discard_delta.md

Usage:
    python tools/per_marker_tables.py
"""

from __future__ import annotations

import json
import math
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qc_session as qc  # noqa: E402  (parse_csv_file, dist_stats, segment_dwells)

DISCARD_S = 5.0
FLOOR_N = 80          # analysis floor, Methodology §7.2; reported, not enforced
MARKERS = [30, 60, 90, 120, 150, 180, 210, 240, 270, 300]
SPURIOUS_LAP_S = 1.0  # laps shorter than this are double-presses

D2 = Path("data/ranging_experiments/2026-08-22_GMATownship_session02")
D1 = Path("data/ranging_experiments/2026-08-15_GMATownship_session01")
AN = Path("data/analysis")

RUNS_D2 = {
    "406.25": {
        "raw": D2 / "raw/20260822_162424-Initiator",
        "plan": AN / "2026-08-22_GMATownship_162424_qc/session_plan.json",
        "laps": D2 / "stopwatch_laps_data_406.csv",
    },
    "1625": {
        "raw": D2 / "raw/20260822_174415-Initiator",
        "plan": AN / "2026-08-22_GMATownship_174415_qc/session_plan.json",
        "laps": D2 / "stopwatch_laps_data_1625.csv",
    },
}
RUN_D1 = {
    "raw": D1 / "raw/20260815_184714-Initiator",
    "plan": AN / "2026-08-15_GMATownship_184714_qc/session_plan.json",
    "report_static": AN / "2026-08-15_GMATownship_184714_qc/static/report.md",
    "report_sng": AN / "2026-08-15_GMATownship_184714_qc/stop_and_go/report.md",
}
PUBLISHED_D2 = AN / "2026-08-22_GMATownship_day2_qc_tables.md"

OUT_D2 = AN / "2026-08-22_GMATownship_day2_tables_discard5s.md"
OUT_D1 = AN / "2026-08-15_GMATownship_day1_tables_discard5s.md"
OUT_N = AN / "achieved_n.md"
OUT_DELTA = AN / "f4_discard_delta.md"


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def load_plan(path: Path) -> dict:
    """{run_id: {"kind", "files": {name: truth_m}}}, discarded files dropped."""
    plan = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for run in plan["runs"]:
        files = {}
        for name, v in run["files"].items():
            if isinstance(v, dict):
                if v.get("disposition") == "discarded":
                    continue
                v = v.get("true_m")
            files[name] = v
        out[run["run_id"]] = {"kind": run["kind"], "files": files,
                              "markers": run.get("markers_m",
                                                 plan.get("markers_m"))}
    return out


def mmss(s: str) -> float:
    m, sec = s.strip().split(":")
    return int(m) * 60 + float(sec)


def dwell_windows(lap_csv: Path) -> list[tuple[float, float]]:
    """Dwell windows (s on the file axis) from a lap sheet: spurious
    presses dropped, then odd laps (1st, 3rd, ...) are dwells."""
    laps = []
    for line in lap_csv.read_text(encoding="utf-8").splitlines()[1:]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4 or not parts[0].isdigit():
            continue
        start, end, lap = mmss(parts[1]), mmss(parts[2]), mmss(parts[3])
        if lap < SPURIOUS_LAP_S:
            continue
        laps.append((start, end))
    return laps[0::2]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def window_stats(rows: list, truth: float, discard: bool) -> dict:
    """Per-marker stats on one window of rows (all outcomes = attempts)."""
    if discard and rows:
        t0 = rows[0].timestamp_ms
        rows = [r for r in rows if r.timestamp_ms - t0 > DISCARD_S * 1000]
    succ = [r for r in rows if r.status == "SUCCESS"]
    st = qc.dist_stats([r.raw_distance_m for r in succ],
                       [r.rssi_dbm for r in succ])
    st["N"] = len(rows)
    st["marker"] = truth
    st["err"] = st["median"] - truth
    st["rows"] = rows   # the window's rows after the discard (all outcomes)
    return st


def static_run(raw: Path, files: dict, discard: bool) -> dict:
    out = {}
    for name, truth in files.items():
        cf = qc.parse_csv_file(raw / name)
        if not cf.rows or truth is None:
            continue
        st = window_stats(cf.rows, float(truth), discard)
        st["file"] = name
        out[float(truth)] = st
    return out


def lap_run(raw: Path, name: str, windows: list, discard: bool) -> dict:
    cf = qc.parse_csv_file(raw / name)
    out = {}
    for marker, (a, b) in zip(sorted(MARKERS, reverse=True), windows):
        rows = [r for r in cf.rows if a * 1000 <= r.timestamp_ms <= b * 1000]
        st = window_stats(rows, float(marker), discard)
        st["file"] = name
        st["window"] = (a, b)
        out[float(marker)] = st
    return out


def heuristic_run(raw: Path, name: str, markers: list, discard: bool) -> dict:
    """15 Aug stop-and-go: qc_session.py's own plateau segmentation."""
    args = qc.build_argparser().parse_args(
        ["--data-dir", str(raw), "--out", "unused"])
    cf = qc.parse_csv_file(raw / name)
    fq = qc.FileQC(f=cf, kind="stop_and_go")
    qc.segment_dwells(fq, args, [float(m) for m in markers])
    t_first = cf.rows[0].timestamp_ms
    out = {}
    for s in fq.segments:
        if s.get("marker") is None:
            continue
        a = t_first + round(s["start_s"] * 1000)
        b = t_first + round(s["end_s"] * 1000)
        rows = [r for r in cf.rows if a <= r.timestamp_ms <= b]
        st = window_stats(rows, float(s["marker"]), discard)
        st["file"] = name
        st["window"] = ((a - t_first) / 1000, (b - t_first) / 1000)
        out[float(s["marker"])] = st
    return out


def build(discard: bool) -> dict:
    """{(session, bw, tier): {marker: stats}}"""
    res = {}
    for bw, cfg in RUNS_D2.items():
        plan = load_plan(cfg["plan"])
        res[("22 Aug", bw, "static")] = static_run(
            cfg["raw"], plan["static"]["files"], discard)
        (sng_file,) = plan["stop_and_go"]["files"]
        res[("22 Aug", bw, "stop-and-go")] = lap_run(
            cfg["raw"], sng_file, dwell_windows(cfg["laps"]), discard)
    plan = load_plan(RUN_D1["plan"])
    res[("15 Aug", "1625", "static")] = static_run(
        RUN_D1["raw"], plan["static"]["files"], discard)
    (sng_file,) = plan["stop_and_go"]["files"]
    res[("15 Aug", "1625", "stop-and-go")] = heuristic_run(
        RUN_D1["raw"], sng_file, plan["stop_and_go"]["markers"], discard)
    return res


# ---------------------------------------------------------------------------
# Reproduction check against the published tables
# ---------------------------------------------------------------------------


def md_rows(text: str) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and re.fullmatch(r"\d+", cells[0]):
            rows.append(cells)
    return rows


def published() -> dict:
    """Published (median, IQR, N) per (session, bw, tier, marker)."""
    pub = {}
    text = PUBLISHED_D2.read_text(encoding="utf-8")
    block = text.split("## TABLE 1", 1)[1].split("\n## ", 1)[0]
    cols = {("406.25", "static"): 1, ("406.25", "stop-and-go"): 6,
            ("1625", "static"): 11, ("1625", "stop-and-go"): 16}
    for c in md_rows(block):
        for (bw, tier), i in cols.items():
            pub[("22 Aug", bw, tier, float(c[0]))] = (c[i], c[i + 1], c[i + 3])
    for tier, key in (("static", "report_static"), ("stop-and-go", "report_sng")):
        text = RUN_D1[key].read_text(encoding="utf-8")
        block = text.split("Per-marker statistics", 1)[1]
        for c in md_rows(block):
            pub[("15 Aug", "1625", tier, float(c[0]))] = (c[3], c[5], c[2])
    return pub


def check_reproduction(old: dict) -> list[str]:
    pub = published()
    bad = []
    for (sess, bw, tier), stats in old.items():
        for m, st in stats.items():
            key = (sess, bw, tier, m)
            if key not in pub:
                bad.append(f"{key}: not in published tables")
                continue
            p_med, p_iqr, p_n = pub[key]
            mine = (f"{st['median']:.1f}", f"{st['iqr']:.1f}", str(st["N"]))
            if mine != (p_med, p_iqr, p_n):
                bad.append(f"{key}: recomputed {mine} vs published "
                           f"{(p_med, p_iqr, p_n)}")
    missing = [k for k in pub if (k[0], k[1], k[2]) not in old
               or k[3] not in old[(k[0], k[1], k[2])]]
    bad += [f"{k}: published but not recomputed" for k in missing]
    return bad


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def f1(v):
    return "—" if v is None or (isinstance(v, float) and math.isnan(v)) \
        else f"{v:.1f}"


def sgn(v):
    return "—" if v is None else f"{v:+.1f}"


def per_marker_table(stats: dict, windows: bool) -> list[str]:
    head = "| marker m | file | "
    head += "window s | " if windows else ""
    head += ("N (post-discard) | median m | Q1–Q3 m | IQR m | signed err m "
             "| median RSSI |")
    L = [head, "|" + "---|" * (head.count("|") - 1)]
    for m in sorted(stats):
        s = stats[m]
        row = f"| {m:g} | `{s['file']}` | "
        if windows:
            row += f"{s['window'][0]:.1f}–{s['window'][1]:.1f} | "
        row += (f"{s['N']} | {s['median']:.1f} | {s['q1']:.1f}–{s['q3']:.1f} "
                f"| {s['iqr']:.1f} | {s['err']:+.1f} | {s['rssi_median']:.0f} |")
        L.append(row)
    return L


def preamble(title: str, sources: list[str]) -> list[str]:
    L = [f"# {title}", "",
         "Generated by `tools/per_marker_tables.py` (raw CSVs read-only, "
         "unmodified).", "",
         "**Numbers only. No interpretation or conclusions are recorded in "
         "this file.**", "",
         "## Discard rule (Methodology §7.2, applied 2026-10-10)", "",
         f"Every row whose `timestamp_ms` is ≤ {DISCARD_S:g} s after the first "
         "logged row of its window is dropped before any statistic is "
         "computed. Static window = the whole file (one boot per marker). "
         "Stop-and-go window = one dwell (see the per-run notes). "
         "`N` = post-discard attempts, all outcomes. `median`, `IQR` "
         "(Q3−Q1, linear interpolation), `RSSI` = SUCCESS rows. "
         "`err` = median − marker distance.", "",
         "## Inputs", ""]
    L += [f"- `{s}`" for s in sources]
    L += ["", "Ground-truth tolerance: OPEN (Methodology §5.3, OD-METH-3); "
          "every signed-error figure carries it. Timeout and ERROR counts "
          "are 0 in every window.", ""]
    return L


def render_d2(new: dict) -> str:
    srcs = []
    for cfg in RUNS_D2.values():
        srcs += [str(cfg["raw"]).replace("\\", "/") + "/",
                 str(cfg["plan"]).replace("\\", "/"),
                 str(cfg["laps"]).replace("\\", "/")]
    L = preamble("Pack Pucks — Day 2 per-marker tables, warm-up discarded "
                 "(2026-08-22, GMA township)", srcs)
    L += ["Supersedes, for every per-marker number: "
          "`data/analysis/2026-08-22_GMATownship_day2_qc_tables.md` (kept "
          "unmodified; its provenance, boundary-agreement, cadence and "
          "alignment sections are not regenerated here and remain the "
          "reference for those).", "",
          "Stop-and-go dwell windows: dwell laps of the operator stopwatch "
          f"sheet (spurious laps < {SPURIOUS_LAP_S:g} s dropped), file axis "
          "offset 0 s, single 300→30 descent. The 300 m window opens at "
          "boot; its discard counts from the first logged row (≈ 5.9 s).",
          "", "---", ""]
    for bw in RUNS_D2:
        for tier in ("static", "stop-and-go"):
            L += [f"### {bw} kHz — {tier}", ""]
            L += per_marker_table(new[("22 Aug", bw, tier)],
                                  windows=(tier == "stop-and-go"))
            L += [""]
    s = {k[1:]: v for k, v in new.items() if k[0] == "22 Aug"}
    L += ["---", "", "## TABLE 1 — Per-marker, each day-2 run "
          "(post-discard)", ""]
    hdr = "| marker m |"
    for bw in ("406.25", "1625"):
        for tier in ("static", "s&g"):
            hdr += (f" {bw} {tier} med | IQR | err | N | RSSI |")
    L += [hdr, "|" + "---|" * (hdr.count("|") - 1)]
    for m in MARKERS:
        row = f"| {m} |"
        for bw in ("406.25", "1625"):
            for tier in ("static", "stop-and-go"):
                x = s[(bw, tier)][float(m)]
                row += (f" {x['median']:.1f} | {x['iqr']:.1f} | "
                        f"{x['err']:+.1f} | {x['N']} | "
                        f"{x['rssi_median']:.0f} |")
        L.append(row)
    for n, tier, label in ((2, "static", "STATIC"),
                           (3, "stop-and-go", "STOP-AND-GO")):
        L += ["", f"## TABLE {n} — Matched-marker 406.25 vs 1625, {label} "
              "(post-discard)", "",
              "| marker m | 406 med | 406 IQR | 406 err | 1625 med | "
              "1625 IQR | 1625 err | err diff (406-1625) | IQR ratio |",
              "|---|---|---|---|---|---|---|---|---|"]
        for m in MARKERS:
            a, b = s[("406.25", tier)][float(m)], s[("1625", tier)][float(m)]
            L.append(f"| {m} | {a['median']:.1f} | {a['iqr']:.1f} | "
                     f"{a['err']:+.1f} | {b['median']:.1f} | {b['iqr']:.1f} | "
                     f"{b['err']:+.1f} | {a['err'] - b['err']:+.1f} | "
                     f"{a['iqr'] / b['iqr']:.1f}x |")
    L += ["", "## TABLE 4 — Static vs stop-and-go WITHIN each bandwidth "
          "(post-discard)", "",
          "| marker m | 406 static err | 406 s&g err | 406 delta | "
          "1625 static err | 1625 s&g err | 1625 delta |",
          "|---|---|---|---|---|---|---|"]
    for m in MARKERS:
        row = f"| {m} |"
        for bw in ("406.25", "1625"):
            a = s[(bw, "static")][float(m)]["err"]
            b = s[(bw, "stop-and-go")][float(m)]["err"]
            row += f" {a:+.1f} | {b:+.1f} | {a - b:+.1f} |"
        L.append(row)
    d1 = new[("15 Aug", "1625", "static")]
    L += ["", "## TABLE 5 — 1625 continuity: day 1 (15 Aug) vs day 2 "
          "(22 Aug), STATIC (post-discard)", "",
          "| marker m | D1 med | D1 IQR | D1 err | D1 N | D2 med | D2 IQR | "
          "D2 err | D2 N | err drift |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for m in MARKERS:
        b = s[("1625", "static")][float(m)]
        a = d1.get(float(m))
        if a:
            L.append(f"| {m} | {a['median']:.1f} | {a['iqr']:.1f} | "
                     f"{a['err']:+.1f} | {a['N']} | {b['median']:.1f} | "
                     f"{b['iqr']:.1f} | {b['err']:+.1f} | {b['N']} | "
                     f"{b['err'] - a['err']:+.1f} |")
        else:
            L.append(f"| {m} | — | — | — | — | {b['median']:.1f} | "
                     f"{b['iqr']:.1f} | {b['err']:+.1f} | {b['N']} | — |")
    return "\n".join(L) + "\n"


def render_d1(new: dict) -> str:
    srcs = [str(RUN_D1["raw"]).replace("\\", "/") + "/",
            str(RUN_D1["plan"]).replace("\\", "/")]
    L = preamble("Pack Pucks — Day 1 per-marker tables, warm-up discarded "
                 "(2026-08-15, GMA township, 1625 kHz only)", srcs)
    L += ["Supersedes, for every per-marker number: §4 of "
          "`2026-08-15_GMATownship_184714_qc/static/report.md` and §5 of "
          "`…/stop_and_go/report.md` (both kept unmodified as QC output).",
          "",
          "Stop-and-go windows are HEURISTIC (`qc_session.py` plateau "
          "segmentation, default parameters, identical to the published "
          "report) — no operator arrival log exists for this run (S1 log "
          "D2). Static: the 330 m file is an off-set marker (S1 log D5/D6); "
          "there is no 300 m static file.", "", "---", ""]
    for tier in ("static", "stop-and-go"):
        L += [f"### 1625 kHz — {tier}", ""]
        L += per_marker_table(new[("15 Aug", "1625", tier)],
                              windows=(tier == "stop-and-go"))
        L += [""]
    return "\n".join(L) + "\n"


def render_n(new: dict) -> str:
    L = ["# Pack Pucks — Achieved N per marker (post-discard)", "",
         "Generated by `tools/per_marker_tables.py` from the raw CSVs, "
         f"after the Methodology §7.2 first-{DISCARD_S:g}-s discard. "
         "N = attempts (all outcomes) remaining per marker per run. Every "
         "attempt in both outings was SUCCESS (0 TIMEOUT, 0 ERROR).", "",
         "Sources: `data/analysis/2026-08-22_GMATownship_day2_tables_"
         "discard5s.md`, `data/analysis/2026-08-15_GMATownship_day1_tables_"
         "discard5s.md` (same computation; see their Inputs sections).", "",
         "| session | BW kHz | tier | " + " | ".join(f"{m} m" for m in MARKERS)
         + " | 330 m | min N |",
         "|" + "---|" * (len(MARKERS) + 5)]
    mins = {}
    for (sess, bw, tier), st in new.items():
        cells = [str(st[float(m)]["N"]) if float(m) in st else "—"
                 for m in MARKERS + [330]]
        mn = min(x["N"] for x in st.values())
        mins[(sess, bw, tier)] = mn
        L.append(f"| {sess} | {bw} | {tier} | " + " | ".join(cells)
                 + f" | **{mn}** |")
    d2 = min(v for k, v in mins.items() if k[0] == "22 Aug")
    d1 = min(v for k, v in mins.items() if k[0] == "15 Aug")
    L += ["", f"- **N_min, 22 Aug (all four runs): {d2}**",
          f"- N_min, 15 Aug (both runs): {d1}",
          f"- **N_min overall: {min(d1, d2)}**", "",
          "15 Aug stop-and-go N comes from heuristic dwell windows (no "
          "arrival log). The 330 m column is the 15 Aug off-set static "
          "marker only.", ""]
    below = [(k, m, x["N"]) for k, st in new.items() if k[0] == "22 Aug"
             for m, x in st.items() if x["N"] < FLOOR_N]
    return "\n".join(L) + "\n", below, d2, d1


def render_delta(old: dict, new: dict) -> str:
    L = ["# Warm-up discard: old vs new per-marker medians and IQRs", "",
         "Generated by `tools/per_marker_tables.py`. "
         "Numbers only.", "",
         "\"Old\" = no discard, recomputed by the same script and verified "
         "equal (median, IQR to 0.1 m; N exact) to the published values at "
         "every marker of every run. \"New\" = first 5 s of each window "
         "discarded (Methodology §7.2). Δ = new − old.", "",
         "## Which files supersede which", "",
         "| Superseded (kept unmodified) | Superseded by |",
         "|---|---|",
         "| `data/analysis/2026-08-22_GMATownship_day2_qc_tables.md` — "
         "per-marker stats (lap-window tables, TABLE 1–5) | "
         "`data/analysis/2026-08-22_GMATownship_day2_tables_discard5s.md` |",
         "| `data/analysis/2026-08-22_GMATownship_{162424,174415}_qc/*/"
         "report.md` §4 / §5 per-marker stats | same (day-2 discard5s file) |",
         "| `data/analysis/2026-08-15_GMATownship_184714_qc/{static,"
         "stop_and_go}/report.md` §4 / §5 per-marker stats | "
         "`data/analysis/2026-08-15_GMATownship_day1_tables_discard5s.md` |",
         "| `data/analysis/2026-08-22_GMATownship_day2_qc_tables.md` — "
         "provenance, boundary agreement, alignment, cadence | NOT "
         "superseded (not affected by the discard) |",
         "| QC verdicts, drift checks, manifests in every `report.md` | NOT "
         "superseded |", "",
         "`tools/make_readme_figures.py` reads the post-discard day-2 file "
         "and writes `data/analysis/figures/*_discard5s.png` beside the "
         "pre-discard figures, which README.md still embeds.", ""]
    for key in old:
        sess, bw, tier = key
        L += [f"## {sess} — {bw} kHz — {tier}", "",
              "| marker m | old N | new N | old median | new median | "
              "Δ median | old IQR | new IQR | Δ IQR | old err | new err |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for m in sorted(old[key]):
            o, n = old[key][m], new[key][m]
            L.append(f"| {m:g} | {o['N']} | {n['N']} | {o['median']:.1f} | "
                     f"{n['median']:.1f} | {n['median'] - o['median']:+.1f} | "
                     f"{o['iqr']:.1f} | {n['iqr']:.1f} | "
                     f"{n['iqr'] - o['iqr']:+.1f} | {o['err']:+.1f} | "
                     f"{n['err']:+.1f} |")
        dm = [abs(new[key][m]["median"] - old[key][m]["median"])
              for m in old[key]]
        di = [abs(new[key][m]["iqr"] - old[key][m]["iqr"]) for m in old[key]]
        L += ["", f"Largest |Δ median| {max(dm):.2f} m; largest |Δ IQR| "
              f"{max(di):.2f} m.", ""]
    return "\n".join(L) + "\n"


def main() -> int:
    old = build(discard=False)
    bad = check_reproduction(old)
    if bad:
        print("REPRODUCTION CHECK FAILED — nothing written:", file=sys.stderr)
        for b in bad:
            print("  " + b, file=sys.stderr)
        return 1
    print("reproduction check: no-discard recompute matches published "
          "values at every marker")
    new = build(discard=True)
    OUT_D2.write_text(render_d2(new), encoding="utf-8")
    OUT_D1.write_text(render_d1(new), encoding="utf-8")
    text, below, d2, d1 = render_n(new)
    OUT_N.write_text(text, encoding="utf-8")
    OUT_DELTA.write_text(render_delta(old, new), encoding="utf-8")
    for p in (OUT_D2, OUT_D1, OUT_N, OUT_DELTA):
        print(f"wrote {p}")
    print(f"N_min 22 Aug = {d2}; N_min 15 Aug = {d1}")
    if below:
        print(f"22 Aug markers below N={FLOOR_N}:")
        for k, m, n in below:
            print(f"  {k} {m:g} m: N={n}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
