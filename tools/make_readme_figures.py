#!/usr/bin/env python3
"""Pack Pucks — README figure generator.

Builds the cross-bandwidth comparison figures used in README.md from the
authoritative day-2 comparison tables. Those tables recompute the
stop-and-go rows on operator lap-log windows and supersede the QC tool's
heuristic dwell segmentation, so they -- not the per-run QC reports --
are the source for anything comparing 406.25 kHz against 1625 kHz.

Default input is the post-discard tables (Methodology §7.2 first-5-s
discard, written by tools/per_marker_tables.py). The pre-discard
figures (bandwidth_accuracy.png etc.) were built from
2026-08-22_GMATownship_day2_qc_tables.md and are kept; the default
--suffix writes the post-discard set alongside them rather than over
them. Reproduce the old set with:
    --tables data/analysis/2026-08-22_GMATownship_day2_qc_tables.md --suffix ""

Input:  data/analysis/2026-08-22_GMATownship_day2_tables_discard5s.md (TABLE 2, TABLE 3)
Output: data/analysis/figures/*<suffix>.png

Reads only; writes nothing outside the output directory.

Usage:
    python tools/make_readme_figures.py [--out data/analysis/figures]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TABLES = Path("data/analysis/2026-08-22_GMATownship_day2_tables_discard5s.md")
SUFFIX = "_discard5s"

# 406.25 kHz vs 1625 kHz, held consistent across every figure.
C_406 = "#d1495b"
C_1625 = "#1f6f8b"
BAND = "#e8e8e8"


def parse_table(text: str, heading: str) -> list[dict]:
    """Pull one matched-marker table: marker, per-bandwidth IQR and signed error."""
    try:
        block = text.split(heading, 1)[1].split("\n## ", 1)[0]
    except IndexError:
        sys.exit(f"error: heading not found: {heading}")
    rows = []
    for line in block.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 9 and re.fullmatch(r"\d+", cells[0]):
            rows.append({
                "marker": int(cells[0]),
                "iqr_406": float(cells[2]),
                "err_406": float(cells[3]),
                "iqr_1625": float(cells[5]),
                "err_1625": float(cells[6]),
            })
    if not rows:
        sys.exit(f"error: no data rows parsed under {heading}")
    return rows


def style(ax, xlabel, ylabel, title):
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=11)
    ax.grid(True, alpha=0.3, linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def fig_accuracy(static, sng, out: Path):
    """Signed error vs distance, both bandwidths, both tiers."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
    for ax, rows, tier in ((axes[0], static, "Static"),
                           (axes[1], sng, "Semi-mobile (stop-and-go)")):
        x = [r["marker"] for r in rows]
        ax.axhspan(-5, 5, color=BAND, zorder=0)
        ax.axhline(0, color="#444", linewidth=1, linestyle="--", zorder=1)
        ax.plot(x, [r["err_406"] for r in rows], "o-", color=C_406,
                label="406.25 kHz", linewidth=1.8, markersize=5.5, zorder=3)
        ax.plot(x, [r["err_1625"] for r in rows], "s-", color=C_1625,
                label="1625 kHz", linewidth=1.8, markersize=5.5, zorder=3)
        style(ax, "true distance (m)", "signed error (m)", tier)
        ax.set_xticks(x)
        ax.tick_params(labelsize=9)
    axes[0].legend(frameon=False, loc="upper left")
    axes[0].text(0.02, 0.06, "shaded band = ±5 m", transform=axes[0].transAxes,
                 fontsize=8, color="#666")
    fig.suptitle("Ranging accuracy by bandwidth — matched conditions, 22 Aug 2026, SF8",
                 fontsize=12.5, y=1.0)
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_precision(static, sng, out: Path):
    """Spread (IQR of SUCCESS rows) vs distance."""
    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    x = [r["marker"] for r in static]
    ax.plot(x, [r["iqr_406"] for r in static], "o-", color=C_406,
            label="406.25 kHz — static", linewidth=1.8, markersize=5.5)
    ax.plot(x, [r["iqr_406"] for r in sng], "o--", color=C_406, alpha=0.55,
            label="406.25 kHz — stop-and-go", linewidth=1.5, markersize=4.5)
    ax.plot(x, [r["iqr_1625"] for r in static], "s-", color=C_1625,
            label="1625 kHz — static", linewidth=1.8, markersize=5.5)
    ax.plot(x, [r["iqr_1625"] for r in sng], "s--", color=C_1625, alpha=0.55,
            label="1625 kHz — stop-and-go", linewidth=1.5, markersize=4.5)
    style(ax, "true distance (m)", "IQR of readings (m)",
          "Precision by bandwidth — lower is tighter")
    ax.set_xticks(x)
    ax.tick_params(labelsize=9)
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_motion(static, sng, out: Path):
    """Does motion degrade ranging? Absolute error, static vs stop-and-go."""
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    n = len(static)
    idx = range(n)
    w = 0.2
    mean = lambda v: sum(v) / len(v)

    series = [
        ("406.25 kHz static", [abs(r["err_406"]) for r in static], C_406, 1.0, -1.5),
        ("406.25 kHz stop-and-go", [abs(r["err_406"]) for r in sng], C_406, 0.5, -0.5),
        ("1625 kHz static", [abs(r["err_1625"]) for r in static], C_1625, 1.0, 0.5),
        ("1625 kHz stop-and-go", [abs(r["err_1625"]) for r in sng], C_1625, 0.5, 1.5),
    ]
    for label, vals, colour, alpha, off in series:
        ax.bar([i + off * w for i in idx], vals, width=w, color=colour,
               alpha=alpha, label=f"{label}  (mean {mean(vals):.1f} m)")

    ax.set_xticks(list(idx))
    ax.set_xticklabels([str(r["marker"]) for r in static])
    style(ax, "true distance (m)", "absolute error (m)",
          "Effect of motion — accuracy holds at 1625 kHz, not at 406.25 kHz")
    ax.tick_params(labelsize=9)
    ax.legend(frameon=False, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def parse_run(text: str, bw: str, tier: str) -> dict[int, dict]:
    """One per-run table ("### <bw> kHz <U+2014> <tier>"): marker -> median, Q1, Q3, err.
    Columns are found by header name, so the static and stop-and-go layouts
    (the latter has an extra "window s" column) both parse."""
    heading = f"### {bw} kHz \u2014 {tier}"  # the source heading's dash
    try:
        block = text.split(heading, 1)[1].split("\n#", 1)[0]
    except IndexError:
        sys.exit(f"error: heading not found: {heading}")
    lines = [l for l in block.splitlines() if l.startswith("|")]
    head = [c.strip() for c in lines[0].strip().strip("|").split("|")]
    i_med, i_q, i_err = (head.index("median m"), head.index("Q1–Q3 m"),
                         head.index("signed err m"))
    out = {}
    for line in lines[2:]:
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        q1, q3 = c[i_q].split("–")
        out[int(c[0])] = {"med": float(c[i_med]), "q1": float(q1),
                          "q3": float(q3), "err": float(c[i_err])}
    return out


def fig_accuracy_paper(text: str, static, sng, out: Path):
    """Print variant of fig_accuracy for the paper (Fig. 2): one IEEE column,
    caption-size fonts, IQR bars, zero line, shared y-axis. The README figure
    (fig_accuracy) is left unchanged."""
    runs = {}
    for tier, rows in (("static", static), ("stop-and-go", sng)):
        for bw, key in (("406.25", "err_406"), ("1625", "err_1625")):
            run = parse_run(text, bw, tier)
            if sorted(run) != [r["marker"] for r in rows]:
                sys.exit(f"error: {bw} {tier}: per-run markers differ from TABLE 2/3")
            for r in rows:
                p = run[r["marker"]]
                # The plotted point is the TABLE 2/3 signed error; it must equal
                # the per-run table's, and median - marker, to the printed 0.1 m.
                if p["err"] != r[key] or round(p["med"] - r["marker"], 1) != p["err"]:
                    sys.exit(f"error: {bw} {tier} {r['marker']} m: signed error "
                             "differs between tables")
                if not p["q1"] <= p["med"] <= p["q3"]:
                    sys.exit(f"error: {bw} {tier} {r['marker']} m: median outside Q1-Q3")
            runs[(tier, bw)] = run

    plt.rcParams.update({"font.size": 8})
    fig, axes = plt.subplots(1, 2, figsize=(3.5, 2.55), sharey=True)
    handles = []
    for ax, tier, title in ((axes[0], "static", "Static"),
                            (axes[1], "stop-and-go", "Hand-held")):
        ax.axhline(0, color="#444", linewidth=0.6, zorder=1)
        for bw, colour, fmt, dx in (("406.25", C_406, "o", -3), ("1625", C_1625, "s", 3)):
            run = runs[(tier, bw)]
            xs = sorted(run)
            ys = [run[x]["err"] for x in xs]
            lo = [run[x]["med"] - run[x]["q1"] for x in xs]
            hi = [run[x]["q3"] - run[x]["med"] for x in xs]
            h = ax.errorbar([x + dx for x in xs], ys, yerr=[lo, hi], fmt=fmt + "-",
                            color=colour, markersize=2.6, linewidth=0.8,
                            elinewidth=0.7, capsize=1.2, zorder=3,
                            label=f"{bw} kHz")
            if tier == "static":
                handles.append(h)
        ax.set_title(title, fontsize=8, pad=3)
        ax.set_xticks([30, 90, 150, 210, 270])
        ax.set_xlim(15, 315)
        ax.tick_params(labelsize=7, length=2.5, pad=2)
        ax.grid(True, alpha=0.3, linewidth=0.5)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[0].set_ylabel("signed error (m)")
    # Site note at 240 m, static panel only (the text reports the structure there;
    # no cause is claimed).
    p240 = runs[("static", "406.25")][240]
    y240 = p240["err"]
    axes[0].annotate("structure nearby", xy=(240 - 3 - 5, y240 + 0.5),
                     xytext=(222 - 5, y240 + 2.2), ha="right", va="center",
                     fontsize=6.5, color="#444",
                     arrowprops=dict(arrowstyle="-", color="#888", linewidth=0.5,
                                     shrinkA=1, shrinkB=0))
    axes[1].legend(handles, [h.get_label() for h in handles], loc="upper left",
                   fontsize=7, frameon=False, handlelength=2.2,
                   borderaxespad=0.2)
    fig.tight_layout(rect=(0, 0.05, 1, 1), w_pad=0.6)
    fig.text(0.53, 0.015, "marker distance (m)", ha="center", va="bottom",
             fontsize=8)
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    plt.rcParams.update(plt.rcParamsDefault)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tables", type=Path, default=TABLES)
    ap.add_argument("--out", type=Path, default=Path("data/analysis/figures"))
    ap.add_argument("--suffix", default=SUFFIX,
                    help="appended to each figure filename")
    args = ap.parse_args()

    if not args.tables.is_file():
        sys.exit(f"error: {args.tables} not found (run from the repository root)")
    text = args.tables.read_text(encoding="utf-8")
    static = parse_table(text, "## TABLE 2")
    sng = parse_table(text, "## TABLE 3")
    if [r["marker"] for r in static] != [r["marker"] for r in sng]:
        sys.exit("error: static and stop-and-go tables cover different markers")

    args.out.mkdir(parents=True, exist_ok=True)
    for name, fn in (("bandwidth_accuracy", fig_accuracy),
                     ("bandwidth_precision", fig_precision),
                     ("motion_effect", fig_motion)):
        path = args.out / f"{name}{args.suffix}.png"
        fn(static, sng, path)
        print(f"wrote {path}  ({len(static)} markers)")
    path = args.out / f"bandwidth_accuracy{args.suffix}_paper.png"
    fig_accuracy_paper(text, static, sng, path)
    print(f"wrote {path}  (paper Fig. 2, {len(static)} markers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
