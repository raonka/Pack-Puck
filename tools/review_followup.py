#!/usr/bin/env python3
"""Pack Pucks: analysis follow-up to the external review of 2026-11-10.

Numbers only; no paper text. Raw CSVs read-only (through
tools/per_marker_tables.py build, the same loader and discard as every other
analysis output).

  1. Offset-removed MAE at the markers, cross-tier. For each bandwidth:
       hand-held e_k minus that bandwidth's static-tier mean signed error;
       static e_k minus that bandwidth's hand-held mean signed error.
     The offset is taken from the other tier, so it is not fitted to the
     markers it corrects. MAE per tier and bandwidth, the paired ratio
     MAE(406.25) / MAE(1625), and 95 % bootstrap intervals over markers with
     the conventions of tools/uncertainty.py (seed 20261025, 10,000
     replicates, markers resampled with replacement, the same resampled
     markers for both bandwidths and both tiers in a replicate, so the
     offset is re-estimated in every replicate; percentile interval,
     statistics.quantiles method "inclusive"). Also the mean-IQR ratio
     MAE-style, from the per-marker IQRs rounded to 0.1 m as in Table II
     (Section IV-D definition), with the same bootstrap.
  2. (Removed 2026-11-10: the 15 August session is exploratory validation
     data and is not analysed. Section numbers 3 and 4 are kept so that
     references to them stay valid.)
  3. Three reviewer discrepancies, recomputed: the mean IQR from rounded
     against unrounded per-marker IQRs; the 1625 kHz static-minus-hand-held
     difference at 60 m from unrounded against rounded medians; the
     hand-held positive ground-truth bound at 300 m with and without the
     "sideways" carried-end term (docs/ground_truth_tolerance.md section 3).
  4. Why the static-tier N_k take only the values 82, 92, 102, 122: row
     counts per file, the rows removed by the 5 s discard, and the firmware
     flush interval.

Output: data/analysis/review_followup.md

Usage:
    python tools/review_followup.py
"""

from __future__ import annotations

import math
import random
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import per_marker_tables as pmt  # noqa: E402
import uncertainty as unc  # noqa: E402  (SEED, REPS, pct95)

OUT = Path("data/analysis/review_followup.md")
FW = Path("firmware/03_ranging/03_initiator/03_initiator.ino")
BWS = ("406.25", "1625")
TIERS = (("static", "static"), ("stop-and-go", "hand-held"))


def r1(v: float) -> float:
    """Round half away from zero to 0.1, as the published tables print."""
    return math.copysign(math.floor(abs(v) * 10 + 0.5) / 10, v)


def sg(v: float, nd: int = 1) -> str:
    return f"{v:+.{nd}f}"


# ---------------------------------------------------------------------------
# 1. Offset-removed MAE and mean-IQR ratio
# ---------------------------------------------------------------------------


def offset_removed(res: dict) -> tuple[list[str], dict]:
    err, iqr = {}, {}
    for bw in BWS:
        for run, _ in TIERS:
            st = res[("22 Aug", bw, run)]
            assert len(st) == 10
            ms = sorted(st)
            err[(bw, run)] = [st[m]["err"] for m in ms]
            iqr[(bw, run)] = [r1(st[m]["iqr"]) for m in ms]
    other = {"static": "stop-and-go", "stop-and-go": "static"}

    def stats(idx):
        out = {}
        for bw in BWS:
            for run, _ in TIERS:
                e = [err[(bw, run)][i] for i in idx]
                off = statistics.fmean(err[(bw, other[run])][i] for i in idx)
                out[("raw", bw, run)] = statistics.fmean(abs(x) for x in e)
                out[("corr", bw, run)] = statistics.fmean(abs(x - off) for x in e)
                out[("off", bw, run)] = off
                out[("iqr", bw, run)] = statistics.fmean(iqr[(bw, run)][i] for i in idx)
        for kind in ("raw", "corr", "iqr"):
            for run, _ in TIERS:
                out[(kind, "ratio", run)] = (out[(kind, "406.25", run)]
                                             / out[(kind, "1625", run)])
        return out

    point = stats(list(range(10)))
    rng = random.Random(unc.SEED)
    reps: dict = {k: [] for k in point}
    for _ in range(unc.REPS):
        idx = [rng.randrange(10) for _ in range(10)]
        for k, v in stats(idx).items():
            reps[k].append(v)
    ci = {k: unc.pct95(v) for k, v in reps.items()}

    L = ["## 1. Offset-removed MAE at the markers (cross-tier)", "",
         "Inputs: unrounded post-discard per-marker signed errors e_k, 22 Aug, "
         "ten markers per run (`tools/per_marker_tables.py` build). Offset for a "
         "tier = mean signed error of the *other* tier at the same bandwidth "
         "(hand-held corrected by the static mean, static by the hand-held mean). "
         f"Bootstrap: `random.Random({unc.SEED})`, {unc.REPS:,} replicates, ten "
         "markers resampled with replacement; in each replicate the same markers "
         "are used for both bandwidths and both tiers, and the offset is "
         "re-estimated from the resampled other tier. Interval: 95 % percentile "
         "(`statistics.quantiles`, method \"inclusive\"), as `uncertainty.py`.", "",
         "| tier | bandwidth | offset removed (m) | MAE raw (m) | MAE offset-removed (m) "
         "| 95 % interval, offset-removed (m) |", "|---|---|---|---|---|---|"]
    for run, label in TIERS:
        for bw in BWS:
            lo, hi = ci[("corr", bw, run)]
            L.append(f"| {label} | {bw} kHz | {sg(point[('off', bw, run)], 2)} "
                     f"(from {'hand-held' if run == 'static' else 'static'}) | "
                     f"{point[('raw', bw, run)]:.2f} | {point[('corr', bw, run)]:.2f} "
                     f"| {lo:.2f} to {hi:.2f} |")
    L += ["", "### Paired ratio MAE(406.25) / MAE(1625)", "",
          "| tier | raw | 95 % interval | offset-removed | 95 % interval |",
          "|---|---|---|---|---|"]
    for run, label in TIERS:
        a, b = ci[("raw", "ratio", run)]
        c, d = ci[("corr", "ratio", run)]
        L.append(f"| {label} | {point[('raw', 'ratio', run)]:.2f}× | {a:.2f}× to "
                 f"{b:.2f}× | {point[('corr', 'ratio', run)]:.2f}× | {c:.2f}× to "
                 f"{d:.2f}× |")
    L += ["", "The raw ratios reproduce `uncertainty.md` section 1 (6.8×, 7.2× at one "
          "decimal) as a check of the resampling.", "",
          "### Mean-IQR ratio, mean IQR(406.25) / mean IQR(1625)", "",
          "Per-marker IQRs rounded to 0.1 m before averaging (Section IV-D "
          "definition, as Table II). Same bootstrap, paired by marker.", "",
          "| tier | mean IQR 406.25 (m) | mean IQR 1625 (m) | ratio | 95 % interval |",
          "|---|---|---|---|---|"]
    for run, label in TIERS:
        a, b = ci[("iqr", "ratio", run)]
        L.append(f"| {label} | {point[('iqr', '406.25', run)]:.2f} | "
                 f"{point[('iqr', '1625', run)]:.2f} | "
                 f"{point[('iqr', 'ratio', run)]:.2f}× | {a:.2f}× to {b:.2f}× |")
    L.append("")
    return L, point


# ---------------------------------------------------------------------------
# 3. Reviewer discrepancies
# ---------------------------------------------------------------------------


def discrepancies(res: dict) -> list[str]:
    L = ["## 3. Reviewer discrepancies", "",
         "### (a) Mean IQR: rounded against unrounded per-marker IQRs", "",
         "| run | mean of rounded IQR_k (m) | mean of unrounded IQR_k (m) |",
         "|---|---|---|"]
    for bw in BWS:
        for run, label in TIERS:
            st = res[("22 Aug", bw, run)]
            rnd = statistics.fmean(r1(st[m]["iqr"]) for m in st)
            unr = statistics.fmean(st[m]["iqr"] for m in st)
            L.append(f"| {bw} kHz {label} | {rnd:.3f} | {unr:.3f} |")
    L += ["", "### (b) 1625 kHz static minus hand-held signed error at 60 m", ""]
    s = res[("22 Aug", "1625", "static")][60.0]["err"]
    h = res[("22 Aug", "1625", "stop-and-go")][60.0]["err"]
    L += [f"- unrounded: static {s:+.3f} m, hand-held {h:+.3f} m, difference "
          f"{s - h:+.3f} m, printed {sg(r1(s - h))} m;",
          f"- from the printed (0.1 m) values: {sg(r1(s))} minus {sg(r1(h))} = "
          f"{sg(r1(r1(s) - r1(h)))} m.", "",
          "### (c) Hand-held positive ground-truth bound at 300 m", "",
          "Formulas of `docs/ground_truth_tolerance.md` section 3 at cone k = 10 "
          "(D = 300 m), in mm: systematic either sign 12.6 k; random RSS "
          "sqrt(400 k + 10 000) for one static end (the hand-held tier) and "
          "sqrt(400 k + 20 000) for two (the static tier); the carried-end "
          "\"sideways\" term (a 0.6 m perpendicular offset, section 2.7) is computed "
          "here from the geometry, sqrt(D^2 + 0.6^2) - D, positive only. Note: the "
          "section 3 formula table writes this term as 360 / D mm, which is twice "
          "the geometric value; section 2.7 itself gives +0.6 mm at 300 m, which "
          "matches the geometry (180 / D mm).", ""]
    k, D = 10, 300.0
    sys_ = 12.6 * k
    zig = 16.7 * k
    rss_h = math.sqrt(400 * k + 10_000)
    rss_s = math.sqrt(400 * k + 20_000)
    side = (math.sqrt(D ** 2 + 0.6 ** 2) - D) * 1000
    side_table = 360 / D
    L += [f"- static: delta+ = {sys_ + rss_s:.1f} mm, delta- = "
          f"{-(sys_ + zig + rss_s):.1f} mm;",
          f"- hand-held, puck on the mark (no sideways term): delta+ = "
          f"{sys_ + rss_h:.1f} mm, delta- = {-(sys_ + zig + rss_h):.1f} mm;",
          f"- hand-held, sideways term included (geometric, {side:.2f} mm): delta+ = "
          f"{sys_ + rss_h + side:.1f} mm (delta- unchanged; the term is positive only);",
          f"- for comparison, with the table's 360 / D ({side_table:.2f} mm): delta+ = "
          f"{sys_ + rss_h + side_table:.1f} mm.", ""]
    return L


# ---------------------------------------------------------------------------
# 4. Static-tier N_k
# ---------------------------------------------------------------------------


def n_values(res_raw: dict, res: dict) -> list[str]:
    fw = FW.read_text(encoding="utf-8")
    flush = re.search(r"#define SPIFFS_FLUSH_EVERY\s+(\d+)", fw).group(1)
    L = ["## 4. Why the static-tier N_k are 82, 92, 102 or 122", "",
         f"Firmware `{FW.as_posix()}`: `SPIFFS_FLUSH_EVERY` = {flush}; `flushLog()` "
         "calls `logFile.flush()` when `loopCount % SPIFFS_FLUSH_EVERY == 0`, and "
         "`loopCount` is incremented once per ranging cycle. A static file ends when "
         "the operator powers the puck off, so rows written after the last flush are "
         "lost and every file holds a multiple of the flush interval.", "",
         "| run | marker (m) | rows in file | rows mod 10 | last seq | rows removed by "
         "the 5 s discard | N_k |", "|---|---|---|---|---|---|---|"]
    counts = set()
    for day, bw in (("22 Aug", "406.25"), ("22 Aug", "1625"), ("15 Aug", "1625")):
        raw = res_raw[(day, bw, "static")]
        post = res[(day, bw, "static")]
        for m in sorted(raw):
            n0 = raw[m]["N"]
            seq = raw[m]["rows"][-1].seq if hasattr(raw[m]["rows"][-1], "seq") else "n/a"
            n1 = post[m]["N"]
            if day == "22 Aug":
                counts.add((n0 % 10, n0 - n1))
            L.append(f"| {day} {bw} kHz | {m:.0f} | {n0} | {n0 % 10} | {seq} | "
                     f"{n0 - n1} | {n1} |")
    L += ["", f"22 Aug static files: (rows mod 10, rows removed) takes only the "
          f"values {sorted(counts)}. So N_k = 10 m - 8 for a file of 10 m rows: "
          "90, 100, 110 and 130 rows give 82, 92, 102 and 122. The discard removes "
          "8 rows at both bandwidths because the cycle (655 to 686 ms, Section V-C) "
          "puts the eighth row before 5 s and the ninth after it. The hand-held "
          "N_k come from lap windows inside one file and are not multiples of the "
          "flush interval.", ""]
    return L


def main() -> int:
    res = pmt.build(discard=True)
    res_raw = pmt.build(discard=False)
    L = ["# Pack Pucks: review follow-up analysis (2026-11-10)", "",
         "Generated by `tools/review_followup.py`. Raw CSVs read-only. "
         "**Numbers only.**", ""]
    s1, _ = offset_removed(res)
    L += s1 + ["## 2. (Not included)", "",
               "The 15 August session is exploratory validation data, released but "
               "not analysed; this report does not compare it with 22 August. "
               "Section numbers are kept so that references to sections 3 and 4 "
               "stay valid.", ""]
    L += discrepancies(res) + n_values(res_raw, res)
    OUT.write_text("\n".join(L), encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
