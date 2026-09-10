#!/usr/bin/env python3
"""Pack Pucks — session QC tool (C1 reproducibility deliverable).

Runs data-quality checks on one offloaded Initiator session directory
(the output of tools/offload/offload.py: pucklog_*.csv + manifest.txt)
and writes markdown QC reports + overview figures to an analysis
output directory. Raw CSVs are treated as immutable inputs — this tool
opens them read-only and never writes inside --data-dir.

Checks implemented (references: docs/Methodology.md §4, §7.2, §11;
docs/FSD.md DR-1/DR-1.1/DR-3):

  1. Manifest integrity — expected == actual bytes per file, and
     manifest 'actual' == on-disk size; files missing from either side.
  2. Header checks — firmware header (DR-1.1) present and parsed:
     CSV_SCHEMA_V, FW, BOARD_ID, full radio config verified against the
     expected configuration; operator metadata line (SITE / SESSION_ID /
     BOOT_UTC / RUN_ID / TRUE_DISTANCE_M) read when present.
  3. Attempts per file vs the N=100 spec (Methodology §11).
  4. Cadence — median inter-row delta vs nominal, tolerance ±5%.
  5. Outcome tally — SUCCESS/TIMEOUT/ERROR counts and rates; ALL
     outcomes count toward the attempt denominator;
     radio_status_code distribution for every non-SUCCESS row.
  6. Per-marker stats on SUCCESS rows — median, IQR, min, max, median
     RSSI; signed error vs TRUE_DISTANCE_M where ground truth exists.
  7. Stability — rolling-median drift range per file (walk
     contamination / forgotten power-off); implausible readings;
     >10 consecutive ERROR rows (Methodology §7.2 abort criterion).
  8. Warm-up — first-5-s rows reported separately (Methodology §7.2
     discard rule sanity check).

Verdict: PASS / HOLD per run against the Methodology §11 discard
criteria. Only some §11 criteria are machine-checkable from CSVs
(mid-run reboot / power loss evidence, ERROR-streak abort); cone moves
and weather changes live in the session log and are listed as
log-only items in every report.

Ground truth: TRUE_DISTANCE_M is read from CSV line 2 (authoritative
when present, per FSD DR-1.1). When absent, an optional operator-
supplied session-plan JSON may provide it (and run grouping):

    {
      "outing": "free-text label",
      "markers_m": [30, 60, ...],
      "runs": [
        {"run_id": "static", "kind": "static",
         "files": {"pucklog_X_1.csv": 30.0,
                   "pucklog_X_5.csv": {"true_m": 150,
                                       "disposition": "discarded",
                                       "reason": "operator: bad run"},
                   ...}},
        {"run_id": "stop_and_go", "kind": "stop_and_go",
         "markers_m": [30, 60, ...],
         "files": {"pucklog_X_12.csv": null}}
      ]
    }

A run may carry its own "markers_m" (the markers that run actually
visited); it overrides the outing-level list for that run's dwell
matching and plausibility ceiling.

A file value may be a number (ground truth m), null (no truth), or an
object with "true_m" plus an optional operator "disposition":
"discarded" records that the operator declared the run bad (Methodology
§11: noted in the session log, CSV to be moved to data/discarded/ at
archive time). Discarded files are still fully QC'd but are excluded
from per-marker statistics, and reboot/power-loss evidence in them is
reported as a deviation rather than a HOLD (the operator disposition IS
the §11 confirmation).

kind "stop_and_go" triggers dwell-plateau segmentation (single-boot
continuous logs); per-file truth values are the marker distances.
If plan truth and CSV line-2 truth disagree, the report flags it —
nothing is corrected. Without a plan all files form one run and
per-marker error stats are only produced where CSVs carry truth.

Usage:
    python tools/qc_session.py --data-dir <offload session dir> \
        --out <analysis output dir> [--session-plan plan.json] ...

Session-agnostic: no hardcoded paths or session constants outside
argparse defaults.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

TOOL_VERSION = "1.0.0"
SUPPORTED_SCHEMA_V = 1
STATUSES = ("SUCCESS", "TIMEOUT", "ERROR")

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


@dataclass
class Row:
    seq: int
    timestamp_ms: int
    status: str
    raw_distance_m: float  # NaN on TIMEOUT/ERROR per DR-1
    rssi_dbm: int
    state: str
    consecutive_failures: int
    radio_status_code: int


@dataclass
class CsvFile:
    name: str
    path: Path
    header: dict = field(default_factory=dict)       # DR-1.1 line 1
    meta: dict | None = None                         # operator line 2
    rows: list[Row] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)


@dataclass
class FileQC:
    f: CsvFile
    run_id: str = "all"
    kind: str = "static"
    truth_m: float | None = None
    truth_source: str = "none"
    disposition: str | None = None      # e.g. "discarded" (operator, plan)
    disposition_reason: str | None = None
    flags: list[str] = field(default_factory=list)   # deviations / anomalies
    hold_reasons: list[str] = field(default_factory=list)
    # filled by checks:
    n_attempts: int = 0
    counts: dict = field(default_factory=dict)
    cadence_ms: float | None = None
    cadence_ok: bool | None = None
    nonsuccess_codes: dict = field(default_factory=dict)
    drift_range_m: float | None = None
    max_error_streak: int = 0
    warmup: dict = field(default_factory=dict)
    segments: list = field(default_factory=list)     # stop-and-go dwells


def parse_manifest(path: Path) -> tuple[dict, dict, list[str]]:
    """Return (banner, files{name: {expected, actual, status}}, problems)."""
    banner: dict = {}
    files: dict = {}
    problems: list[str] = []
    if not path.is_file():
        return banner, files, ["manifest.txt missing from data dir"]
    section = None
    file_re = re.compile(
        r"^/?(?P<name>\S+\.csv)\s+expected=(?P<exp>\d+)\s+actual=(?P<act>\d+)"
        r"\s+status=(?P<st>\S+)")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("["):
            section = line.strip("[]").upper()
            continue
        if section == "FILES":
            m = file_re.match(line)
            if m:
                files[m.group("name")] = {
                    "expected": int(m.group("exp")),
                    "actual": int(m.group("act")),
                    "status": m.group("st"),
                }
            else:
                problems.append(f"unparsed manifest [FILES] line: {line!r}")
        else:
            if ":" in line:
                k, v = line.split(":", 1)
                banner[k.strip()] = v.strip()
    return banner, files, problems


def parse_header_line(line: str) -> dict:
    """Parse a '# KEY=VAL, KEY=VAL' comment line into a dict."""
    out = {}
    for part in line.lstrip("#").split(","):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def parse_csv_file(path: Path) -> CsvFile:
    cf = CsvFile(name=path.name, path=path)
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        lines = fh.read().splitlines()
    idx = 0
    if idx < len(lines) and lines[idx].startswith("#"):
        cf.header = parse_header_line(lines[idx])
        idx += 1
    else:
        cf.parse_errors.append("firmware header line (DR-1.1) missing")
    if idx < len(lines) and lines[idx].startswith("#"):
        cf.meta = parse_header_line(lines[idx])
        idx += 1
    if idx < len(lines) and lines[idx].startswith("seq,"):
        expected_cols = ("seq,timestamp_ms,status,raw_distance_m,rssi_dbm,"
                         "state,consecutive_failures,radio_status_code")
        if lines[idx].strip() != expected_cols:
            cf.parse_errors.append(
                f"column header differs from DR-1: {lines[idx]!r}")
        idx += 1
    else:
        cf.parse_errors.append("DR-1 column header line missing")
    for ln, line in enumerate(lines[idx:], start=idx + 1):
        if not line.strip():
            continue
        parts = line.split(",")
        if len(parts) != 8:
            cf.parse_errors.append(f"line {ln}: {len(parts)} fields (want 8)")
            continue
        try:
            cf.rows.append(Row(
                seq=int(parts[0]), timestamp_ms=int(parts[1]),
                status=parts[2],
                raw_distance_m=float(parts[3]),
                rssi_dbm=int(parts[4]), state=parts[5],
                consecutive_failures=int(parts[6]),
                radio_status_code=int(parts[7]),
            ))
        except ValueError as e:
            cf.parse_errors.append(f"line {ln}: {e}")
    return cf


# ---------------------------------------------------------------------------
# Stats helpers (SUCCESS-row distance stats; the attempt
# denominator = all rows, handled separately in the outcome tally)
# ---------------------------------------------------------------------------


def q1_q3(values: list[float]) -> tuple[float, float]:
    if len(values) < 2:
        return (values[0], values[0]) if values else (math.nan, math.nan)
    q = statistics.quantiles(values, n=4, method="inclusive")
    return q[0], q[2]


def rolling_median(values: list[float], window: int) -> list[float]:
    half = window // 2
    out = []
    for i in range(len(values)):
        lo, hi = max(0, i - half), min(len(values), i + half + 1)
        out.append(statistics.median(values[lo:hi]))
    return out


def dist_stats(dists: list[float], rssis: list[int]) -> dict:
    if not dists:
        return {}
    q1, q3 = q1_q3(dists)
    return {
        "n": len(dists),
        "median": statistics.median(dists),
        "q1": q1, "q3": q3, "iqr": q3 - q1,
        "min": min(dists), "max": max(dists),
        "rssi_median": statistics.median(rssis) if rssis else math.nan,
    }


# ---------------------------------------------------------------------------
# Per-file checks
# ---------------------------------------------------------------------------


def check_file(qc: FileQC, args, markers: list[float] | None) -> None:
    f = qc.f
    rows = f.rows
    qc.n_attempts = len(rows)

    for e in f.parse_errors:
        qc.flags.append(f"parse: {e}")

    # -- header / config verification (check 2)
    h = f.header
    if h:
        try:
            if int(h.get("CSV_SCHEMA_V", -1)) != SUPPORTED_SCHEMA_V:
                qc.hold_reasons.append(
                    f"CSV_SCHEMA_V={h.get('CSV_SCHEMA_V')} unsupported "
                    f"(tool supports {SUPPORTED_SCHEMA_V}; DR-3)")
        except ValueError:
            qc.hold_reasons.append("CSV_SCHEMA_V unparseable")
        expect = {
            "FREQ": ("frequency MHz", args.expect_freq, 0.01),
            "BW": ("bandwidth kHz", args.expect_bw, 0.01),
            "SF": ("spreading factor", args.expect_sf, 0),
            "CR": ("coding rate denom", args.expect_cr, 0),
            "TXPOWER": ("TX power dBm", args.expect_txpower, 0),
        }
        for key, (label, want, tol) in expect.items():
            got = h.get(key)
            if got is None:
                qc.hold_reasons.append(f"header missing {key}")
                continue
            try:
                if abs(float(got) - float(want)) > tol:
                    qc.hold_reasons.append(
                        f"radio config mismatch: {key}={got}, "
                        f"expected {label} {want}")
            except ValueError:
                qc.hold_reasons.append(f"header {key}={got!r} unparseable")
        if h.get("ROLE") != "INITIATOR":
            qc.flags.append(f"ROLE={h.get('ROLE')!r} (expected INITIATOR)")
    else:
        qc.hold_reasons.append("firmware header line missing (DR-1.1)")

    # -- ground truth (CSV line 2 authoritative; plan may fill/conflict)
    csv_truth = None
    if f.meta:
        tv = f.meta.get("TRUE_DISTANCE_M", "NA")
        if tv not in ("NA", "", None):
            try:
                csv_truth = float(tv)
            except ValueError:
                qc.flags.append(f"TRUE_DISTANCE_M={tv!r} unparseable")
    else:
        qc.flags.append("operator metadata line (line 2) absent — "
                        "SITE/RUN_ID/TRUE_DISTANCE_M not recorded in file "
                        "(Methodology §7.4 step incomplete)")
    if csv_truth is not None:
        if qc.truth_m is not None and abs(qc.truth_m - csv_truth) > 0.5:
            qc.flags.append(
                f"session-plan truth {qc.truth_m} m disagrees with CSV "
                f"TRUE_DISTANCE_M={csv_truth} m — CSV kept, not corrected")
        qc.truth_m, qc.truth_source = csv_truth, "csv-line2"

    if not rows:
        qc.flags.append("no data rows (stub file — likely a boot into "
                        "NORMAL mode with no ranging logged)")
        return

    # -- seq / timestamp integrity
    seqs = [r.seq for r in rows]
    gaps = sum(1 for a, b in zip(seqs, seqs[1:]) if b != a + 1)
    if seqs[0] != 1:
        qc.flags.append(f"first seq={seqs[0]} (expected 1)")
    if gaps:
        qc.flags.append(f"{gaps} seq discontinuities (dropped log lines?)")
    ts = [r.timestamp_ms for r in rows]
    if any(b <= a for a, b in zip(ts, ts[1:])):
        qc.flags.append("non-monotonic timestamp_ms")

    # -- attempts vs spec (check 3)
    if qc.n_attempts < args.expect_n:
        qc.flags.append(
            f"N={qc.n_attempts} attempts vs spec N={args.expect_n} "
            f"(shortfall {args.expect_n - qc.n_attempts})")

    # -- cadence (check 4)
    if len(ts) >= 2:
        deltas = [b - a for a, b in zip(ts, ts[1:])]
        qc.cadence_ms = statistics.median(deltas)
        lo = args.cadence_ms * (1 - args.cadence_tol)
        hi = args.cadence_ms * (1 + args.cadence_tol)
        qc.cadence_ok = lo <= qc.cadence_ms <= hi
        if not qc.cadence_ok:
            qc.flags.append(
                f"median cadence {qc.cadence_ms:.0f} ms outside "
                f"{args.cadence_ms}±{args.cadence_tol*100:.0f}% ms")
        big = [d for d in deltas if d > 2 * args.cadence_ms]
        if big:
            qc.flags.append(
                f"{len(big)} inter-row gaps > 2x nominal cadence "
                f"(max {max(big)} ms)")

    # -- outcome tally (check 5); denominator = all attempts
    qc.counts = {s: 0 for s in STATUSES}
    for r in rows:
        qc.counts[r.status] = qc.counts.get(r.status, 0) + 1
    unknown = {k: v for k, v in qc.counts.items() if k not in STATUSES}
    if unknown:
        qc.flags.append(f"unknown status values: {unknown}")
    for r in rows:
        if r.status != "SUCCESS":
            qc.nonsuccess_codes[r.radio_status_code] = \
                qc.nonsuccess_codes.get(r.radio_status_code, 0) + 1

    # -- ERROR streak (Methodology §7.2 abort criterion)
    streak = best = 0
    for r in rows:
        streak = streak + 1 if r.status == "ERROR" else 0
        best = max(best, streak)
    qc.max_error_streak = best
    if best > args.error_streak:
        qc.hold_reasons.append(
            f"run of {best} consecutive ERROR rows exceeds abort "
            f"criterion (> {args.error_streak}, Methodology §7.2/§11)")

    succ = [r for r in rows if r.status == "SUCCESS"]
    dists = [r.raw_distance_m for r in succ]

    # -- implausible readings (check 7)
    neg = [d for d in dists if d < args.neg_limit]
    if neg:
        qc.flags.append(
            f"{len(neg)} SUCCESS readings below {args.neg_limit} m "
            f"(min {min(neg):.1f} m)")
    if markers:
        ceiling = max(markers) * (1 + args.max_over_frac)
        far = [d for d in dists if d > ceiling]
        if far:
            qc.flags.append(
                f"{len(far)} SUCCESS readings beyond {ceiling:.0f} m "
                f"(max marker {max(markers):.0f} m + "
                f"{args.max_over_frac*100:.0f}%); max {max(far):.1f} m")

    # -- warm-up (check 8): first N seconds relative to first logged row
    t0 = ts[0]
    warm = [r for r in succ if r.timestamp_ms - t0 <= args.warmup_s * 1000]
    rest = [r for r in succ if r.timestamp_ms - t0 > args.warmup_s * 1000]
    qc.warmup = {
        "n_warm": len(warm),
        "median_warm": statistics.median(
            [r.raw_distance_m for r in warm]) if warm else math.nan,
        "median_rest": statistics.median(
            [r.raw_distance_m for r in rest]) if rest else math.nan,
    }
    if warm and rest:
        qc.warmup["delta"] = qc.warmup["median_warm"] - qc.warmup["median_rest"]

    # -- stability / drift (check 7); static files only — a stop-and-go
    #    continuous log legitimately spans the whole course.
    if dists and qc.kind == "static":
        rm = rolling_median(dists, args.drift_window)
        qc.drift_range_m = max(rm) - min(rm)
        if qc.drift_range_m > args.drift_limit:
            qc.hold_reasons.append(
                f"rolling-median drift range {qc.drift_range_m:.1f} m "
                f"> {args.drift_limit} m (walk contamination or forgotten "
                f"power-off?)")

    # -- short-file heuristic: possible mid-run reboot / power loss (§11)
    if qc.kind == "static" and 0 < qc.n_attempts < args.expect_n * 0.5:
        msg = (f"only {qc.n_attempts} attempts (<50% of spec) — possible "
               f"mid-run power-cycle/reboot")
        if qc.disposition == "discarded":
            qc.flags.append(
                f"{msg}; operator disposition: DISCARDED "
                f"({qc.disposition_reason or 'no reason given'}) — "
                f"excluded from per-marker stats; move to data/discarded/ "
                f"at archive time (Methodology §11)")
        else:
            qc.hold_reasons.append(
                f"{msg}; confirm against session log "
                f"(Methodology §11 discard criterion)")


# ---------------------------------------------------------------------------
# Stop-and-go dwell segmentation (heuristic, reported as such)
# ---------------------------------------------------------------------------


def segment_dwells(qc: FileQC, args, markers: list[float] | None) -> None:
    """Detect stationary dwell plateaus in a continuous stop-and-go log.

    Heuristic: rolling median of SUCCESS distances; a cycle is
    'stationary' when the rolling median moves less than
    --dwell-slope-m over ±--dwell-halfwin cycles. Consecutive
    stationary cycles >= --dwell-min-cycles form a dwell segment.
    Segments are matched to the nearest plan marker; residual larger
    than half the minimum marker spacing is flagged as unmatched.
    """
    succ = [r for r in qc.f.rows if r.status == "SUCCESS"]
    if len(succ) < args.dwell_min_cycles:
        return
    dists = [r.raw_distance_m for r in succ]
    rm = rolling_median(dists, args.drift_window)
    hw = args.dwell_halfwin
    stationary = []
    for i in range(len(rm)):
        lo, hi = max(0, i - hw), min(len(rm) - 1, i + hw)
        stationary.append(abs(rm[hi] - rm[lo]) < args.dwell_slope_m)
    # group runs of stationary cycles
    segs = []
    start = None
    for i, s in enumerate(stationary + [False]):
        if s and start is None:
            start = i
        elif not s and start is not None:
            if i - start >= args.dwell_min_cycles:
                segs.append((start, i - 1))
            start = None
    half_gap = None
    if markers and len(markers) >= 2:
        ms = sorted(markers)
        half_gap = min(b - a for a, b in zip(ms, ms[1:])) / 2
    for s, e in segs:
        seg_rows = succ[s:e + 1]
        d = [r.raw_distance_m for r in seg_rows]
        st = dist_stats(d, [r.rssi_dbm for r in seg_rows])
        st["start_s"] = (seg_rows[0].timestamp_ms
                         - qc.f.rows[0].timestamp_ms) / 1000
        st["end_s"] = (seg_rows[-1].timestamp_ms
                       - qc.f.rows[0].timestamp_ms) / 1000
        st["marker"] = None
        if markers:
            nearest = min(markers, key=lambda m: abs(m - st["median"]))
            resid = st["median"] - nearest
            if half_gap is None or abs(resid) <= max(half_gap,
                                                     args.drift_limit):
                st["marker"] = nearest
            else:
                qc.flags.append(
                    f"dwell at {st['start_s']:.0f}-{st['end_s']:.0f} s "
                    f"(median {st['median']:.1f} m) matches no marker "
                    f"within tolerance — left unmatched")
        # attempt denominator within the segment window
        t_lo, t_hi = seg_rows[0].timestamp_ms, seg_rows[-1].timestamp_ms
        win = [r for r in qc.f.rows if t_lo <= r.timestamp_ms <= t_hi]
        st["attempts"] = len(win)
        st["timeouts"] = sum(1 for r in win if r.status == "TIMEOUT")
        st["errors"] = sum(1 for r in win if r.status == "ERROR")
        qc.segments.append(st)
    if markers:
        matched = {s["marker"] for s in qc.segments if s["marker"] is not None}
        missing = [m for m in markers if m not in matched]
        if missing:
            qc.flags.append(
                f"no dwell segment detected for marker(s) "
                f"{', '.join(f'{m:g}' for m in missing)} m "
                f"(heuristic segmentation — verify against session log)")


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def fmt(v, spec=".1f", na="—"):
    if v is None:
        return na
    if isinstance(v, float) and math.isnan(v):
        return na
    return format(v, spec)


def outcome_rates(qc: FileQC) -> str:
    n = qc.n_attempts or 1
    return " / ".join(
        f"{qc.counts.get(s, 0)} ({100*qc.counts.get(s,0)/n:.0f}%)"
        for s in STATUSES)


LOG_ONLY_CRITERIA = (
    "The following Methodology §11 discard criteria are **not machine-"
    "checkable from CSVs** and must be confirmed against the session "
    "log: (a) cone moved mid-session without re-measurement; "
    "(b) material weather change mid-session (rain start, wind category "
    "shift). This tool checks only: firmware reboot / power-loss "
    "evidence (short or truncated files), and the >10-consecutive-ERROR "
    "abort criterion."
)


def marker_stats_for_run(qcs: list[FileQC]) -> list[dict]:
    """Per-marker SUCCESS-row stats for a run (static: per file with
    truth; stop-and-go: per matched dwell segment)."""
    out = []
    for qc in qcs:
        if qc.disposition == "discarded":
            continue
        if qc.kind == "stop_and_go" and qc.segments:
            for s in qc.segments:
                if s.get("marker") is None:
                    continue
                d = dict(s)
                d["truth"] = s["marker"]
                d["truth_source"] = (f"{qc.truth_source} + dwell match"
                                     if qc.truth_source != "none"
                                     else "plan markers + dwell match")
                d["file"] = qc.f.name
                out.append(d)
        else:
            succ = [r for r in qc.f.rows if r.status == "SUCCESS"]
            if not succ:
                continue
            st = dist_stats([r.raw_distance_m for r in succ],
                            [r.rssi_dbm for r in succ])
            st["truth"] = qc.truth_m
            st["truth_source"] = qc.truth_source
            st["marker"] = qc.truth_m
            st["file"] = qc.f.name
            st["attempts"] = qc.n_attempts
            st["timeouts"] = qc.counts.get("TIMEOUT", 0)
            st["errors"] = qc.counts.get("ERROR", 0)
            out.append(st)
    out.sort(key=lambda d: (d["marker"] is None,
                            d["marker"] if d["marker"] is not None else 0))
    return out


def render_run_report(run_id: str, kind: str, qcs: list[FileQC],
                      session: dict, args, fig_name: str) -> str:
    L = []
    L.append(f"# QC report — run `{run_id}` ({kind})")
    L.append("")
    L.append(f"- Session dir: `{session['data_dir']}`")
    L.append(f"- Generated: {session['now']} by qc_session.py "
             f"v{TOOL_VERSION} (raw CSVs read-only, unmodified)")
    L.append(f"- Expected config: {args.expect_freq} MHz, "
             f"BW {args.expect_bw} kHz, SF{args.expect_sf}, "
             f"CR 4/{args.expect_cr}, {args.expect_txpower} dBm; "
             f"N={args.expect_n}/file; cadence {args.cadence_ms} ms "
             f"±{args.cadence_tol*100:.0f}%; drift limit "
             f"{args.drift_limit} m; warm-up window {args.warmup_s} s")
    if session.get("plan_note"):
        L.append(f"- Ground truth: {session['plan_note']}")
    L.append("")

    hold = [(qc.f.name, r) for qc in qcs for r in qc.hold_reasons]
    verdict = "HOLD" if hold else "PASS"
    L.append(f"## Verdict: **{verdict}**")
    L.append("")
    if hold:
        L.append("HOLD reasons (operator confirmation or action required "
                 "before this run enters the paper dataset):")
        for name, r in hold:
            L.append(f"- `{name}`: {r}")
    else:
        L.append("No machine-checkable Methodology §11 discard trigger "
                 "found in this run.")
    L.append("")
    L.append(f"> {LOG_ONLY_CRITERIA}")
    L.append("")

    # manifest table
    L.append("## 1. Manifest integrity")
    L.append("")
    L.append("| file | manifest expected | manifest actual | on-disk | "
             "status | ok |")
    L.append("|---|---|---|---|---|---|")
    for qc in qcs:
        m = session["manifest_files"].get(qc.f.name)
        disk = qc.f.path.stat().st_size
        if m is None:
            L.append(f"| `{qc.f.name}` | — | — | {disk} | NOT IN MANIFEST "
                     f"| ✗ |")
            continue
        ok = m["expected"] == m["actual"] == disk and m["status"] == "OK"
        L.append(f"| `{qc.f.name}` | {m['expected']} | {m['actual']} | "
                 f"{disk} | {m['status']} | {'✓' if ok else '✗'} |")
    L.append("")

    # per-file table
    L.append("## 2. Per-file checks")
    L.append("")
    L.append("| file | truth (src) | N | vs spec | cadence ms | "
             "S / T / E (rate) | max ERR streak | drift m | flags |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for qc in qcs:
        truth = (f"{fmt(qc.truth_m)} ({qc.truth_source})"
                 if qc.truth_m is not None else "—")
        vs = ("OK" if qc.n_attempts >= args.expect_n
              else f"-{args.expect_n - qc.n_attempts}")
        cad = fmt(qc.cadence_ms, ".0f")
        if qc.cadence_ok is False:
            cad += " ✗"
        nflags = len(qc.flags) + len(qc.hold_reasons)
        if qc.disposition == "discarded":
            vs += " DISCARDED"
        L.append(f"| `{qc.f.name}` | {truth} | {qc.n_attempts} | {vs} | "
                 f"{cad} | {outcome_rates(qc)} | {qc.max_error_streak} | "
                 f"{fmt(qc.drift_range_m)} | {nflags} |")
    L.append("")
    L.append("All three outcomes count toward the attempt denominator.")
    L.append("")

    # non-SUCCESS code distribution
    codes = {}
    for qc in qcs:
        for c, n in qc.nonsuccess_codes.items():
            codes[c] = codes.get(c, 0) + n
    L.append("### radio_status_code distribution (non-SUCCESS rows)")
    L.append("")
    if codes:
        L.append("| radio_status_code | rows |")
        L.append("|---|---|")
        for c in sorted(codes):
            L.append(f"| {c} | {codes[c]} |")
    else:
        L.append("No non-SUCCESS rows in this run.")
    L.append("")

    # warm-up
    L.append(f"## 3. Warm-up (first {args.warmup_s:g} s vs remainder, "
             "SUCCESS rows)")
    L.append("")
    L.append("| file | warm-up rows | warm-up median m | rest median m | "
             "delta m |")
    L.append("|---|---|---|---|---|")
    for qc in qcs:
        w = qc.warmup
        if not w:
            L.append(f"| `{qc.f.name}` | — | — | — | — |")
            continue
        L.append(f"| `{qc.f.name}` | {w.get('n_warm', 0)} | "
                 f"{fmt(w.get('median_warm'))} | "
                 f"{fmt(w.get('median_rest'))} | "
                 f"{fmt(w.get('delta'), '+.1f')} |")
    L.append("")
    L.append("Sanity check for the Methodology §7.2 first-5-s discard "
             "rule; large deltas indicate the discard window matters for "
             "that file.")
    L.append("")

    # dwell segments for stop-and-go
    sec = 4
    if kind == "stop_and_go":
        L.append(f"## {sec}. Dwell segmentation (heuristic)")
        sec += 1
        L.append("")
        L.append(f"Stationary plateaus detected via rolling-median slope "
                 f"< {args.dwell_slope_m} m over ±{args.dwell_halfwin} "
                 f"cycles, minimum {args.dwell_min_cycles} cycles. "
                 f"Segment→marker matching is nearest-marker; verify "
                 f"against the session log.")
        L.append("")
        L.append("| window s | matched marker | attempts | T / E | "
                 "median m | IQR m | median RSSI |")
        L.append("|---|---|---|---|---|---|---|")
        for qc in qcs:
            for s in qc.segments:
                mk = fmt(s["marker"], "g") if s["marker"] is not None \
                    else "unmatched"
                L.append(f"| {s['start_s']:.0f}–{s['end_s']:.0f} | {mk} | "
                         f"{s['attempts']} | {s['timeouts']} / "
                         f"{s['errors']} | {s['median']:.1f} | "
                         f"{s['iqr']:.1f} | {s['rssi_median']:.0f} |")
        L.append("")

    # per-marker stats
    L.append(f"## {sec}. Per-marker statistics (SUCCESS rows)")
    sec += 1
    L.append("")
    mstats = marker_stats_for_run(qcs)
    if mstats:
        L.append("| marker m | file | n | median m | Q1–Q3 m | IQR m | "
                 "min m | max m | median RSSI | signed err m |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for s in mstats:
            err = (f"{s['median'] - s['truth']:+.1f}"
                   if s.get("truth") is not None else "—")
            mk = fmt(s.get("marker"), "g") if s.get("marker") is not None \
                else "?"
            L.append(f"| {mk} | `{s['file']}` | {s['n']} | "
                     f"{s['median']:.1f} | {s['q1']:.1f}–{s['q3']:.1f} | "
                     f"{s['iqr']:.1f} | {s['min']:.1f} | {s['max']:.1f} | "
                     f"{s['rssi_median']:.0f} | {err} |")
        srcs = sorted({s["truth_source"] for s in mstats
                       if s.get("truth") is not None})
        if srcs:
            L.append("")
            L.append(f"Ground-truth source(s): {', '.join(srcs)}.")
        if any(s.get("truth") is None for s in mstats):
            L.append("")
            L.append("Rows with `—` signed error have no ground truth "
                     "available (no CSV TRUE_DISTANCE_M and no session-"
                     "plan value) — error stats cannot be computed as "
                     "specified for those files.")
    else:
        L.append("No SUCCESS rows / no marker-attributable data.")
    L.append("")

    # deviations
    L.append(f"## {sec}. Deviations and anomalies")
    L.append("")
    any_dev = False
    for qc in qcs:
        for fl in qc.hold_reasons:
            L.append(f"- **HOLD** `{qc.f.name}`: {fl}")
            any_dev = True
        for fl in qc.flags:
            L.append(f"- `{qc.f.name}`: {fl}")
            any_dev = True
    if not any_dev:
        L.append("None.")
    L.append("")
    L.append(f"![overview]({fig_name})")
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def make_run_figure(run_id: str, kind: str, qcs: list[FileQC],
                    out_path: Path, args) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plotted = [qc for qc in qcs if qc.f.rows]
    if not plotted:
        return
    if kind == "stop_and_go" and len(plotted) == 1:
        qc = plotted[0]
        fig, ax = plt.subplots(figsize=(12, 4.5))
        _plot_file(ax, qc, args)
        for s in qc.segments:
            ax.axvspan(s["start_s"], s["end_s"], color="tab:green",
                       alpha=0.12)
            label = (f"{s['marker']:g} m" if s["marker"] is not None
                     else "?")
            ax.text((s["start_s"] + s["end_s"]) / 2, s["max"] + 8, label,
                    ha="center", fontsize=7)
        ax.set_title(f"{run_id}: {qc.f.name} — dwell segments shaded "
                     "(heuristic)")
        ax.set_xlabel("elapsed s (from first logged row)")
        ax.set_ylabel("raw_distance_m")
    else:
        n = len(plotted)
        ncols = min(4, n)
        nrows = math.ceil(n / ncols)
        fig, axes = plt.subplots(nrows, ncols,
                                 figsize=(3.2 * ncols, 2.4 * nrows),
                                 squeeze=False, sharex=False)
        for ax in axes.flat[n:]:
            ax.axis("off")
        for ax, qc in zip(axes.flat, plotted):
            _plot_file(ax, qc, args)
            title = qc.f.name.replace("pucklog_", "")
            if qc.truth_m is not None:
                title += f" @ {qc.truth_m:g} m"
                ax.axhline(qc.truth_m, color="tab:red", lw=0.8, ls="--")
            ax.set_title(title, fontsize=8)
        fig.suptitle(f"{run_id} — raw distance vs elapsed time "
                     "(× = TIMEOUT/ERROR at 0)", fontsize=10)
        fig.supxlabel("elapsed s", fontsize=8)
        fig.supylabel("raw_distance_m", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _plot_file(ax, qc: FileQC, args) -> None:
    t0 = qc.f.rows[0].timestamp_ms
    xs = [(r.timestamp_ms - t0) / 1000 for r in qc.f.rows
          if r.status == "SUCCESS"]
    ys = [r.raw_distance_m for r in qc.f.rows if r.status == "SUCCESS"]
    xf = [(r.timestamp_ms - t0) / 1000 for r in qc.f.rows
          if r.status != "SUCCESS"]
    ax.plot(xs, ys, ".", ms=2.5, color="tab:blue")
    if xf:
        ax.plot(xf, [0] * len(xf), "x", ms=4, color="tab:red",
                label=f"{len(xf)} non-SUCCESS")
        ax.legend(fontsize=6)
    ax.axvspan(0, args.warmup_s, color="tab:orange", alpha=0.15)
    ax.tick_params(labelsize=7)
    ax.grid(alpha=0.3)


def make_comparison_figure(per_run: dict, out_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))
    for run_id, stats in per_run.items():
        stats = [s for s in stats if s.get("marker") is not None]
        if not stats:
            continue
        xs = [s["marker"] for s in stats]
        med = [s["median"] for s in stats]
        lo = [s["median"] - s["q1"] for s in stats]
        hi = [s["q3"] - s["median"] for s in stats]
        ax1.errorbar(xs, med, yerr=[lo, hi], marker="o", ms=4,
                     capsize=3, lw=1, label=run_id)
        ax2.plot(xs, [s["rssi_median"] for s in stats], marker="o",
                 ms=4, lw=1, label=run_id)
    lim = ax1.get_xlim()
    ax1.plot(lim, lim, ls=":", color="gray", lw=0.8)
    ax1.set_xlim(lim)
    ax1.set_xlabel("marker m")
    ax1.set_ylabel("median raw_distance_m (bars: Q1–Q3)")
    ax1.set_title("median ± IQR vs marker")
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.3)
    ax2.set_xlabel("marker m")
    ax2.set_ylabel("median RSSI dBm")
    ax2.set_title("median RSSI vs marker")
    ax2.legend(fontsize=8)
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def render_outing_summary(per_run: dict, verdicts: dict, session: dict,
                          fig_name: str | None) -> str:
    L = []
    L.append("# Outing summary — run comparison at matched markers")
    L.append("")
    L.append(f"- Session dir: `{session['data_dir']}`")
    L.append(f"- Generated: {session['now']} by qc_session.py "
             f"v{TOOL_VERSION}")
    for run_id, v in verdicts.items():
        L.append(f"- Run `{run_id}`: **{v}** (see `{run_id}/report.md`)")
    L.append("")
    runs = [r for r in per_run
            if any(s.get("marker") is not None for s in per_run[r])]
    skipped = [r for r in per_run if r not in runs]
    if skipped:
        L.append(f"Runs with no marker-attributable data (excluded from "
                 f"the comparison table): {', '.join(f'`{r}`' for r in skipped)}")
        L.append("")
    if len(runs) < 2:
        L.append("Only one run present — no cross-run comparison.")
        return "\n".join(L)
    by_marker: dict = {}
    for run_id, stats in per_run.items():
        for s in stats:
            if s.get("marker") is None:
                continue
            prev = by_marker.setdefault(s["marker"], {}).get(run_id)
            # duplicate files at one marker (e.g. abort + redo): keep
            # the larger-n entry; the run report lists both
            if prev is None or s["n"] > prev["n"]:
                by_marker[s["marker"]][run_id] = s
    L.append("| marker m | " + " | ".join(
        f"{r} median m | {r} IQR m | {r} err m | {r} T% | {r} RSSI"
        for r in runs) + " |")
    L.append("|---|" + "---|" * (5 * len(runs)))
    for mk in sorted(by_marker):
        cells = [f"{mk:g}"]
        for r in runs:
            s = by_marker[mk].get(r)
            if s is None:
                cells += ["—"] * 5
                continue
            err = (f"{s['median'] - s['truth']:+.1f}"
                   if s.get("truth") is not None else "—")
            att = s.get("attempts") or s["n"]
            t_pct = 100 * s.get("timeouts", 0) / att if att else 0
            cells += [f"{s['median']:.1f}", f"{s['iqr']:.1f}", err,
                      f"{t_pct:.0f}", f"{s['rssi_median']:.0f}"]
        L.append("| " + " | ".join(cells) + " |")
    L.append("")
    L.append("Timeout % uses the all-outcomes attempt denominator. "
             "Stop-and-go rows come from heuristic "
             "dwell segmentation — verify marker matching against the "
             "session log.")
    if fig_name:
        L.append("")
        L.append(f"![comparison]({fig_name})")
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--data-dir", required=True, type=Path,
                   help="offloaded session dir (pucklog_*.csv + "
                        "manifest.txt); opened read-only")
    p.add_argument("--out", required=True, type=Path,
                   help="analysis output dir for reports and figures")
    p.add_argument("--session-plan", type=Path, default=None,
                   help="optional operator-supplied JSON: run grouping, "
                        "markers, per-file ground truth (see module "
                        "docstring)")
    p.add_argument("--expect-freq", type=float, default=2400.0,
                   help="expected frequency MHz")
    p.add_argument("--expect-bw", type=float, default=1625.0,
                   help="expected bandwidth kHz")
    p.add_argument("--expect-sf", type=int, default=8,
                   help="expected spreading factor")
    p.add_argument("--expect-cr", type=int, default=7,
                   help="expected coding-rate denominator (CR 4/x)")
    p.add_argument("--expect-txpower", type=int, default=12,
                   help="expected TX power dBm")
    p.add_argument("--expect-n", type=int, default=100,
                   help="spec attempts per file (Methodology §11)")
    p.add_argument("--cadence-ms", type=float, default=655.0,
                   help="nominal inter-row cadence ms (500 ms interval + "
                        "ranging cycle time as observed on hardware)")
    p.add_argument("--cadence-tol", type=float, default=0.05,
                   help="cadence tolerance fraction")
    p.add_argument("--drift-limit", type=float, default=15.0,
                   help="rolling-median range limit m (static stability)")
    p.add_argument("--drift-window", type=int, default=15,
                   help="rolling-median window, cycles")
    p.add_argument("--warmup-s", type=float, default=5.0,
                   help="warm-up window s (Methodology §7.2 discard rule)")
    p.add_argument("--error-streak", type=int, default=10,
                   help="abort criterion: > this many consecutive ERRORs")
    p.add_argument("--neg-limit", type=float, default=-10.0,
                   help="implausible-negative threshold m")
    p.add_argument("--max-over-frac", type=float, default=0.25,
                   help="implausible-far threshold: max marker x (1+frac)")
    p.add_argument("--dwell-slope-m", type=float, default=5.0,
                   help="stop-and-go: max rolling-median movement over "
                        "the ± halfwin to count as stationary")
    p.add_argument("--dwell-halfwin", type=int, default=5,
                   help="stop-and-go: half-window (cycles) for slope test")
    p.add_argument("--dwell-min-cycles", type=int, default=30,
                   help="stop-and-go: minimum dwell length, cycles")
    return p


def _repo_relative(p: Path) -> str:
    """Path relative to the repository root, so generated reports are
    identical for anyone who clones and re-runs (C1 reproducibility).
    Falls back to the absolute path for data outside the repository."""
    try:
        return p.relative_to(Path(__file__).resolve().parent.parent).as_posix()
    except ValueError:
        return str(p)


def main(argv=None) -> int:
    args = build_argparser().parse_args(argv)
    data_dir: Path = args.data_dir.resolve()
    out_dir: Path = args.out.resolve()
    if not data_dir.is_dir():
        print(f"error: --data-dir {data_dir} is not a directory",
              file=sys.stderr)
        return 2
    if out_dir == data_dir or data_dir in out_dir.parents:
        print("error: --out must be outside --data-dir (raw data dir is "
              "immutable)", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)

    banner, manifest_files, manifest_problems = parse_manifest(
        data_dir / "manifest.txt")

    plan = None
    markers: list[float] | None = None
    plan_note = None
    if args.session_plan:
        plan = json.loads(args.session_plan.read_text(encoding="utf-8"))
        markers = [float(m) for m in plan.get("markers_m", [])] or None
        plan_note = (f"session plan `{args.session_plan.name}` "
                     f"(operator-supplied; used only where CSV line-2 "
                     f"TRUE_DISTANCE_M is absent)")

    csv_paths = sorted(data_dir.glob("*.csv"),
                       key=lambda p: [int(t) if t.isdigit() else t
                                      for t in re.split(r"(\d+)", p.name)])
    if not csv_paths:
        print(f"error: no *.csv in {data_dir}", file=sys.stderr)
        return 2

    # run assignment
    file_run: dict[str, tuple[str, str, float | None, dict]] = {}
    run_markers: dict[str, list[float]] = {}
    if plan:
        for run in plan.get("runs", []):
            if run.get("markers_m"):
                run_markers[run["run_id"]] = [float(m)
                                              for m in run["markers_m"]]
            for fname, val in run.get("files", {}).items():
                if isinstance(val, dict):
                    truth = val.get("true_m")
                    dispo = val
                else:
                    truth, dispo = val, {}
                file_run[fname] = (run["run_id"],
                                   run.get("kind", "static"),
                                   float(truth) if truth is not None
                                   else None,
                                   dispo)

    qcs: list[FileQC] = []
    for path in csv_paths:
        cf = parse_csv_file(path)
        run_id, kind, truth, dispo = file_run.get(
            cf.name,
            ("unassigned" if plan else "all", "static", None, {}))
        qc = FileQC(f=cf, run_id=run_id, kind=kind)
        if truth is not None:
            qc.truth_m, qc.truth_source = truth, "session-plan"
        qc.disposition = dispo.get("disposition")
        qc.disposition_reason = dispo.get("reason")
        eff_markers = run_markers.get(run_id, markers)
        check_file(qc, args, eff_markers)
        if kind == "stop_and_go":
            segment_dwells(qc, args, eff_markers)
        qcs.append(qc)

    # manifest cross-checks
    disk_names = {p.name for p in csv_paths}
    for qc in qcs:
        m = manifest_files.get(qc.f.name)
        if m is None:
            qc.hold_reasons.append("file absent from manifest.txt")
        else:
            disk = qc.f.path.stat().st_size
            if m["expected"] != m["actual"]:
                qc.hold_reasons.append(
                    f"manifest byte mismatch: expected={m['expected']} "
                    f"actual={m['actual']} (status={m['status']})")
            if m["actual"] != disk:
                qc.hold_reasons.append(
                    f"on-disk size {disk} != manifest actual "
                    f"{m['actual']} (file altered since offload?)")
            if m["status"] != "OK":
                qc.hold_reasons.append(
                    f"manifest status={m['status']}")
    session_flags = list(manifest_problems)
    for name in manifest_files:
        if name not in disk_names:
            session_flags.append(
                f"manifest lists `{name}` but it is not on disk")
    # cross-file consistency
    boards = {qc.f.header.get("BOARD_ID") for qc in qcs if qc.f.header}
    if len(boards) > 1:
        session_flags.append(f"multiple BOARD_IDs in one session: {boards}")
    fws = {qc.f.header.get("FW") for qc in qcs if qc.f.header}
    if len(fws) > 1:
        session_flags.append(f"multiple firmware versions: {fws}")
    if banner:
        if banner.get("WIFI_OFF") != "1" or banner.get("BT_OFF") != "1":
            session_flags.append(
                "manifest banner does not confirm WIFI_OFF=1/BT_OFF=1")
    else:
        session_flags.append("manifest banner absent — WiFi/BT-off "
                             "self-report not verifiable "
                             "from this directory")

    session = {
        "data_dir": _repo_relative(data_dir),
        "now": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "manifest_files": manifest_files,
        "plan_note": plan_note,
    }

    # group by run, render
    run_ids = []
    for qc in qcs:
        if qc.run_id not in run_ids:
            run_ids.append(qc.run_id)
    per_run_marker_stats = {}
    verdicts = {}
    for run_id in run_ids:
        group = [qc for qc in qcs if qc.run_id == run_id]
        kind = ("stop_and_go"
                if any(q.kind == "stop_and_go" for q in group) else "static")
        # session-level flags surface once, in the first run's report
        if run_id == run_ids[0]:
            for fl in session_flags:
                group[0].flags.append(f"[session] {fl}")
        rdir = out_dir / run_id
        rdir.mkdir(parents=True, exist_ok=True)
        fig_name = "overview.png"
        make_run_figure(run_id, kind, group, rdir / fig_name, args)
        report = render_run_report(run_id, kind, group, session, args,
                                   fig_name)
        (rdir / "report.md").write_text(report, encoding="utf-8")
        verdicts[run_id] = ("HOLD" if any(q.hold_reasons for q in group)
                            else "PASS")
        per_run_marker_stats[run_id] = marker_stats_for_run(group)
        print(f"run {run_id}: {verdicts[run_id]} "
              f"({len(group)} files) -> {rdir / 'report.md'}")

    fig_name = None
    if len([r for r in run_ids if per_run_marker_stats[r]]) >= 2:
        fig_name = "outing_comparison.png"
        make_comparison_figure(per_run_marker_stats, out_dir / fig_name)
    summary = render_outing_summary(per_run_marker_stats, verdicts,
                                    session, fig_name)
    (out_dir / "outing_summary.md").write_text(summary, encoding="utf-8")
    print(f"outing summary -> {out_dir / 'outing_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
