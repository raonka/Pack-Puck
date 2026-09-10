# Pack Pucks — Day 2 QC tables (2026-08-22, GMA township)

Generated 2026-08-22 from `tools/qc_session.py` v1.0.0 outputs plus recomputation
on the same raw CSVs. Raw CSVs are read-only and unmodified.

**Numbers only. No interpretation or conclusions are recorded in this file.**

## Provenance

| run | offload set | BW (header) | files | QC verdict | report |
|---|---|---|---|---|---|
| 406.25 static | `20260822_162424-Initiator` | 406.25 | 14 (10 kept, 4 discarded) | **HOLD** | `2026-08-22_GMATownship_162424_qc/static/report.md` |
| 406.25 stop-and-go | `20260822_162424-Initiator` | 406.25 | 2 (1 kept, 1 discarded) | **PASS** | `2026-08-22_GMATownship_162424_qc/stop_and_go/report.md` |
| 1625 static | `20260822_174415-Initiator` | 1625.00 | 10 | **PASS** | `2026-08-22_GMATownship_174415_qc/static/report.md` |
| 1625 stop-and-go | `20260822_174415-Initiator` | 1625.00 | 1 | **PASS** | `2026-08-22_GMATownship_174415_qc/stop_and_go/report.md` |

Empty boot stubs `pucklog_D4DB1C_16.csv` and `_17.csv` (header only, 0 data rows)
are unassigned and excluded from every table.

## Ground-truth caveat

Marker distances are tape-survey cone positions (Methodology §5.2). The
ground-truth **tolerance is OPEN** (Methodology §5.3 / OD-METH-3: tape accuracy
class not yet read). Every signed-error column below inherits that open item.

## Dwell attribution — operator arrival log (Methodology §7.3)

Operator arrival logs **exist for both stop-and-go runs** and are the ground truth
used for every stop-and-go row below:

- `data/ranging_experiments/2026-08-22_GMATownship_session02/stopwatch_laps_data_406.csv` — 20 laps
- `data/ranging_experiments/2026-08-22_GMATownship_session02/stopwatch_laps_data_1625.csv` — 21 laps

Both are phone-stopwatch lap sheets in `Lap Number, Start Time, End Time, Lap Time,
Total Time` form. The operator pressed **lap at the end of each dwell and at the end
of each walk transit**, so laps alternate long (dwell, ~70.5 s) and short (walk,
~27–44 s). Odd laps are dwells; even laps are transits.

- 406.25: 20 laps = **10 dwells + 10 transits**, no spurious presses.
- 1625: 21 laps = **10 dwells + 10 transits + one spurious 0.13 s double-press
  (lap 4)**, which is dropped.

**Stopwatch-to-file alignment.** The lap sheet spans 1032.5 s (406.25) and 1027.2 s
(1625) against CSV spans of 1027.7 s and 1028.5 s, i.e. the stopwatch was started at
puck boot. A least-spread offset scan over ±30 s in 0.1 s steps returns **+1.1 s
(406.25)** and **+0.2 s (1625)**, both inside the ±1 s alignment that Methodology §7.3
calls adequate at this cadence. **Offset 0 s is used throughout**; the fitted optima
change no median by more than 0.1 m.

Both runs are a single monotonic 300→30 descent visiting all ten markers, confirmed
by the lap log. Dwell→marker assignment is therefore **operator-confirmed, not
heuristic**.

**Relation to the `qc_session.py` reports.** The tool's own nearest-marker heuristic
disagrees with the lap log at 406.25 kHz — it returned no dwell for the 180 m and
240 m markers, split the 240 m dwell in two and matched both halves to 270 m, and
matched the 180 m dwell to 210 m. At 1625 kHz the tool and the lap log agree at all
ten markers. The tool's reports are left as generated; the stop-and-go tables below
are recomputed on lap windows and supersede them.

## Column definitions

`med` = median of SUCCESS rows. `IQR` = Q3−Q1 (linear interpolation) of SUCCESS
rows. `err` = med − marker distance. `N` = attempts, all outcomes. `RSSI` = median dBm over SUCCESS rows.

**Timeout rate is 0.0 % and ERROR rate is 0.0 % in every file of both offload
sets** (0 TIMEOUT, 0 ERROR across all 27 data-bearing day-2 files). The timeout
column is therefore constant and is omitted from the tables below rather than
repeated as a column of zeros.

---


### 406.25 kHz — PER-CONE BOUNDARY AGREEMENT (lap log = ground truth, offset 0 s)

| cone m | lap window s | heuristic window s | start d s | end d s | dwell len s | lap N | heur N |
|---|---|---|---|---|---|---|---|
| 300 | 0.0–70.8 | 0–71 | +0.0 | +0.2 | 70.8 | 95 | 95 |
| 270 | 105.6–176.2 | 105–169 | -0.6 | -7.2 | 70.6 | 103 | 93 |
| 240 | 219.8–290.4 | 211–283 | -8.8 | -7.4 | 70.6 | 103 | 105 |
| 210 | 325.2–396.2 | 320–374 | -5.2 | -22.2 | 71.0 | 103 | 79 |
| 180 | 423.4–493.8 | 409–486 | -14.4 | -7.8 | 70.4 | 103 | 112 |
| 150 | 523.6–594.2 | 515–592 | -8.6 | -2.2 | 70.5 | 103 | 112 |
| 120 | 622.8–693.2 | 618–692 | -4.8 | -1.2 | 70.4 | 102 | 108 |
| 90 | 723.3–793.8 | 716–799 | -7.3 | +5.2 | 70.5 | 103 | 122 |
| 60 | 822.7–897.4 | 814–893 | -8.7 | -4.4 | 74.8 | 109 | 116 |
| 30 | 926.5–997.2 | 915–991 | -11.5 | -6.2 | 70.7 | 103 | 110 |

Start d: mean -7.0 s, range -14.4..+0.0 s
End d:   mean -5.3 s, range -22.2..+5.2 s
Cone ORDER and COUNT: lap log 10 dwells 300->30; heuristic 10 windows 300->30. AGREE.

### 406.25 kHz — PER-MARKER STATS ON LAP-DERIVED WINDOWS (authoritative)

| marker m | N | median m | IQR m | signed err m | median RSSI | (heuristic median) | d vs heur |
|---|---|---|---|---|---|---|---|
| 300 | 95 | 309.5 | 4.6 | +9.5 | -87 | 309.5 | +0.0 |
| 270 | 103 | 282.6 | 4.7 | +12.6 | -88 | 282.0 | +0.6 |
| 240 | 103 | 255.6 | 6.4 | +15.6 | -86 | 255.6 | +0.1 |
| 210 | 103 | 219.1 | 7.8 | +9.1 | -85 | 219.1 | +0.0 |
| 180 | 103 | 199.6 | 3.7 | +19.6 | -83 | 199.6 | +0.0 |
| 150 | 103 | 163.9 | 2.9 | +13.9 | -77 | 164.2 | -0.3 |
| 120 | 102 | 128.8 | 3.3 | +8.8 | -76 | 128.8 | +0.0 |
| 90 | 103 | 97.0 | 2.7 | +7.0 | -70 | 97.5 | -0.5 |
| 60 | 109 | 72.6 | 4.5 | +12.6 | -73 | 72.7 | -0.1 |
| 30 | 103 | 42.5 | 4.1 | +12.5 | -66 | 42.6 | -0.0 |

### 1625 kHz — PER-CONE BOUNDARY AGREEMENT (lap log = ground truth, offset 0 s)

| cone m | lap window s | heuristic window s | start d s | end d s | dwell len s | lap N | heur N |
|---|---|---|---|---|---|---|---|
| 300 | 0.0–70.8 | 0–67 | +0.0 | -3.8 | 70.8 | 99 | 94 |
| 270 | 99.8–170.3 | 87–165 | -12.8 | -5.3 | 70.6 | 107 | 119 |
| 240 | 201.3–272.4 | 193–268 | -8.3 | -4.4 | 71.0 | 108 | 114 |
| 210 | 302.6–374.2 | 292–370 | -10.6 | -4.2 | 71.6 | 109 | 119 |
| 180 | 407.6–479.0 | 391–475 | -16.6 | -4.0 | 71.4 | 109 | 128 |
| 150 | 518.6–589.3 | 496–584 | -22.6 | -5.3 | 70.8 | 108 | 134 |
| 120 | 618.2–688.9 | 609–686 | -9.2 | -2.9 | 70.7 | 108 | 118 |
| 90 | 720.8–791.3 | 706–786 | -14.8 | -5.3 | 70.6 | 107 | 122 |
| 60 | 819.8–891.5 | 811–890 | -8.8 | -1.5 | 71.7 | 110 | 120 |
| 30 | 923.4–995.0 | 910–995 | -13.4 | -0.0 | 71.6 | 110 | 129 |

Start d: mean -11.7 s, range -22.6..+0.0 s
End d:   mean -3.7 s, range -5.3..-0.0 s
Cone ORDER and COUNT: lap log 10 dwells 300->30; heuristic 10 windows 300->30. AGREE.

### 1625 kHz — PER-MARKER STATS ON LAP-DERIVED WINDOWS (authoritative)

| marker m | N | median m | IQR m | signed err m | median RSSI | (heuristic median) | d vs heur |
|---|---|---|---|---|---|---|---|
| 300 | 99 | 299.8 | 2.8 | -0.2 | -90 | 299.8 | -0.0 |
| 270 | 107 | 274.8 | 1.4 | +4.8 | -88 | 274.8 | +0.0 |
| 240 | 108 | 240.7 | 3.3 | +0.7 | -88 | 240.7 | +0.0 |
| 210 | 109 | 211.3 | 1.1 | +1.3 | -86 | 211.4 | -0.0 |
| 180 | 109 | 179.1 | 1.9 | -0.9 | -85 | 179.4 | -0.2 |
| 150 | 108 | 148.6 | 1.6 | -1.4 | -81 | 148.9 | -0.3 |
| 120 | 108 | 118.3 | 1.2 | -1.7 | -79 | 118.3 | +0.0 |
| 90 | 107 | 90.8 | 1.3 | +0.8 | -76 | 90.6 | +0.2 |
| 60 | 110 | 55.8 | 2.0 | -4.2 | -75 | 56.0 | -0.2 |
| 30 | 110 | 29.0 | 0.9 | -1.0 | -72 | 29.2 | -0.1 |

---


## TABLE 1 — Per-marker, each day-2 run (SUCCESS rows; N = attempts, all outcomes)

| marker m | 406 static med | IQR | err | N | RSSI | 406 s&g med | IQR | err | N | RSSI | 1625 static med | IQR | err | N | RSSI | 1625 s&g med | IQR | err | N | RSSI |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 30 | 38.9 | 3.6 | +8.9 | 100 | -66 | 42.5 | 4.1 | +12.5 | 103 | -66 | 29.8 | 1.1 | -0.2 | 100 | -70 | 29.0 | 0.9 | -1.0 | 110 | -72 |
| 60 | 70.3 | 3.4 | +10.3 | 90 | -71 | 72.6 | 4.5 | +12.6 | 109 | -73 | 60.4 | 1.2 | +0.4 | 100 | -75 | 55.8 | 2.0 | -4.2 | 110 | -75 |
| 90 | 99.3 | 4.2 | +9.3 | 90 | -71 | 97.0 | 2.7 | +7.0 | 103 | -70 | 87.1 | 2.0 | -2.9 | 110 | -75 | 90.8 | 1.3 | +0.8 | 107 | -76 |
| 120 | 134.0 | 3.4 | +14.0 | 90 | -76 | 128.8 | 3.3 | +8.8 | 102 | -76 | 121.9 | 1.1 | +1.9 | 110 | -77 | 118.3 | 1.2 | -1.7 | 108 | -79 |
| 150 | 161.9 | 4.3 | +11.9 | 110 | -79 | 163.9 | 2.9 | +13.9 | 103 | -77 | 147.5 | 1.3 | -2.5 | 110 | -80 | 148.6 | 1.6 | -1.4 | 108 | -81 |
| 180 | 184.0 | 8.5 | +4.0 | 100 | -87 | 199.6 | 3.7 | +19.6 | 103 | -83 | 181.3 | 1.6 | +1.3 | 110 | -82 | 179.1 | 1.9 | -0.9 | 109 | -85 |
| 210 | 207.3 | 7.3 | -2.7 | 100 | -87 | 219.1 | 7.8 | +9.1 | 103 | -85 | 210.6 | 1.9 | +0.6 | 110 | -86 | 211.3 | 1.1 | +1.3 | 109 | -86 |
| 240 | 269.9 | 6.3 | +29.9 | 90 | -88 | 255.6 | 6.4 | +15.6 | 103 | -86 | 243.2 | 3.2 | +3.2 | 110 | -89 | 240.7 | 3.3 | +0.7 | 108 | -88 |
| 270 | 285.0 | 6.3 | +15.0 | 90 | -89 | 282.6 | 4.7 | +12.6 | 103 | -88 | 272.9 | 1.8 | +2.9 | 110 | -90 | 274.8 | 1.4 | +4.8 | 107 | -88 |
| 300 | 304.6 | 4.3 | +4.6 | 90 | -89 | 309.5 | 4.6 | +9.5 | 95 | -87 | 299.3 | 2.1 | -0.7 | 130 | -91 | 299.8 | 2.8 | -0.2 | 99 | -90 |

## TABLE 2 — Matched-marker 406.25 vs 1625, STATIC

| marker m | 406 med | 406 IQR | 406 err | 1625 med | 1625 IQR | 1625 err | err diff (406-1625) | IQR ratio |
|---|---|---|---|---|---|---|---|---|
| 30 | 38.9 | 3.6 | +8.9 | 29.8 | 1.1 | -0.2 | +9.0 | 3.4x |
| 60 | 70.3 | 3.4 | +10.3 | 60.4 | 1.2 | +0.4 | +9.9 | 2.9x |
| 90 | 99.3 | 4.2 | +9.3 | 87.1 | 2.0 | -2.9 | +12.3 | 2.1x |
| 120 | 134.0 | 3.4 | +14.0 | 121.9 | 1.1 | +1.9 | +12.1 | 3.0x |
| 150 | 161.9 | 4.3 | +11.9 | 147.5 | 1.3 | -2.5 | +14.4 | 3.2x |
| 180 | 184.0 | 8.5 | +4.0 | 181.3 | 1.6 | +1.3 | +2.7 | 5.3x |
| 210 | 207.3 | 7.3 | -2.7 | 210.6 | 1.9 | +0.6 | -3.3 | 3.9x |
| 240 | 269.9 | 6.3 | +29.9 | 243.2 | 3.2 | +3.2 | +26.7 | 2.0x |
| 270 | 285.0 | 6.3 | +15.0 | 272.9 | 1.8 | +2.9 | +12.2 | 3.5x |
| 300 | 304.6 | 4.3 | +4.6 | 299.3 | 2.1 | -0.7 | +5.3 | 2.1x |

## TABLE 3 — Matched-marker 406.25 vs 1625, STOP-AND-GO

| marker m | 406 med | 406 IQR | 406 err | 1625 med | 1625 IQR | 1625 err | err diff (406-1625) | IQR ratio |
|---|---|---|---|---|---|---|---|---|
| 30 | 42.5 | 4.1 | +12.5 | 29.0 | 0.9 | -1.0 | +13.5 | 4.6x |
| 60 | 72.6 | 4.5 | +12.6 | 55.8 | 2.0 | -4.2 | +16.8 | 2.2x |
| 90 | 97.0 | 2.7 | +7.0 | 90.8 | 1.3 | +0.8 | +6.2 | 2.0x |
| 120 | 128.8 | 3.3 | +8.8 | 118.3 | 1.2 | -1.7 | +10.5 | 2.8x |
| 150 | 163.9 | 2.9 | +13.9 | 148.6 | 1.6 | -1.4 | +15.3 | 1.8x |
| 180 | 199.6 | 3.7 | +19.6 | 179.1 | 1.9 | -0.9 | +20.5 | 1.9x |
| 210 | 219.1 | 7.8 | +9.1 | 211.3 | 1.1 | +1.3 | +7.8 | 6.8x |
| 240 | 255.6 | 6.4 | +15.6 | 240.7 | 3.3 | +0.7 | +15.0 | 1.9x |
| 270 | 282.6 | 4.7 | +12.6 | 274.8 | 1.4 | +4.8 | +7.8 | 3.4x |
| 300 | 309.5 | 4.6 | +9.5 | 299.8 | 2.8 | -0.2 | +9.6 | 1.7x |

## TABLE 4 — Static vs stop-and-go WITHIN each bandwidth

| marker m | 406 static err | 406 s&g err | 406 delta | 1625 static err | 1625 s&g err | 1625 delta |
|---|---|---|---|---|---|---|
| 30 | +8.9 | +12.5 | -3.7 | -0.2 | -1.0 | +0.8 |
| 60 | +10.3 | +12.6 | -2.3 | +0.4 | -4.2 | +4.6 |
| 90 | +9.3 | +7.0 | +2.3 | -2.9 | +0.8 | -3.7 |
| 120 | +14.0 | +8.8 | +5.2 | +1.9 | -1.7 | +3.5 |
| 150 | +11.9 | +13.9 | -1.9 | -2.5 | -1.4 | -1.1 |
| 180 | +4.0 | +19.6 | -15.5 | +1.3 | -0.9 | +2.2 |
| 210 | -2.7 | +9.1 | -11.9 | +0.6 | +1.3 | -0.8 |
| 240 | +29.9 | +15.6 | +14.2 | +3.2 | +0.7 | +2.5 |
| 270 | +15.0 | +12.6 | +2.4 | +2.9 | +4.8 | -2.0 |
| 300 | +4.6 | +9.5 | -4.9 | -0.7 | -0.2 | -0.5 |

## TABLE 5 — 1625 continuity: day 1 (15 Aug) vs day 2 (22 Aug), STATIC

| marker m | D1 med | D1 IQR | D1 err | D1 N | D2 med | D2 IQR | D2 err | D2 N | err drift |
|---|---|---|---|---|---|---|---|---|---|
| 30 | 32.0 | 1.3 | +2.0 | 70 | 29.8 | 1.1 | -0.2 | 100 | -2.2 |
| 60 | 59.5 | 1.1 | -0.5 | 60 | 60.4 | 1.2 | +0.4 | 100 | +0.8 |
| 90 | 96.0 | 1.0 | +6.0 | 70 | 87.1 | 2.0 | -2.9 | 110 | -9.0 |
| 120 | 117.4 | 1.3 | -2.6 | 70 | 121.9 | 1.1 | +1.9 | 110 | +4.5 |
| 150 | 145.1 | 1.6 | -4.9 | 100 | 147.5 | 1.3 | -2.5 | 110 | +2.4 |
| 180 | 176.8 | 1.5 | -3.2 | 70 | 181.3 | 1.6 | +1.3 | 110 | +4.5 |
| 210 | 205.0 | 2.5 | -5.0 | 70 | 210.6 | 1.9 | +0.6 | 110 | +5.6 |
| 240 | 243.3 | 5.5 | +3.3 | 70 | 243.2 | 3.2 | +3.2 | 110 | -0.1 |
| 270 | 276.6 | 2.4 | +6.6 | 70 | 272.9 | 1.8 | +2.9 | 110 | -3.7 |
| 300 | — | — | — | — | 299.3 | 2.1 | -0.7 | 130 | — |

---

## Figures

Emitted by `qc_session.py` per run:

- `2026-08-22_GMATownship_162424_qc/static/overview.png` — 406.25 static
- `2026-08-22_GMATownship_162424_qc/stop_and_go/overview.png` — 406.25 stop-and-go
- `2026-08-22_GMATownship_162424_qc/outing_comparison.png` — 406.25 static vs stop-and-go
- `2026-08-22_GMATownship_174415_qc/static/overview.png` — 1625 static
- `2026-08-22_GMATownship_174415_qc/stop_and_go/overview.png` — 1625 stop-and-go
- `2026-08-22_GMATownship_174415_qc/outing_comparison.png` — 1625 static vs stop-and-go

Stop-and-go figures are drawn from the tool's heuristic segmentation, not from the
lap windows; the tables above supersede them for stop-and-go numbers.

## Cadence (OD-METH-4 input)

| BW | run | pooled inter-row deltas | median ms | p05 | p95 | min | max | per-file median range |
|---|---|---|---|---|---|---|---|---|
| 406.25 | static (files 1–14) | 1186 | **686** | 685 | 691 | 685 | 691 | 686–686 |
| 406.25 | stop-and-go (files 15, 18) | 1898 | **686** | 685 | 691 | 685 | 693 | 686–686 |
| 406.25 | both pooled | 3084 | **686** | 686 | 691 | 685 | 693 | 686–686 |
| 1625 | static (files 1–10) | 1090 | 655 | 655 | 660 | 654 | 661 | 655–656 |
| 1625 | stop-and-go (file 11) | 1559 | 655 | 655 | 661 | 654 | 663 | 655–655 |
| 1625 | both pooled | 2649 | 655 | 655 | 660 | 654 | 663 | 655–656 |

All day-2 cycles are successful exchanges (zero timeouts), so these are
successful-cycle cadences throughout.

Derived dwell arithmetic at 406.25 kHz: 100 attempts x 686 ms = 68.6 s;
plus the Methodology §7.2 first-5-s discard = 73.6 s.

**Measured dwell lengths actually run** (from the lap logs): 70.4–74.8 s per marker
at 406.25 kHz and 70.6–71.7 s at 1625 kHz — i.e. a ~70 s dwell at both bandwidths.
Resulting attempts per stop-and-go dwell: 95–109 at 406.25 kHz, 99–110 at 1625 kHz.
The 406.25 static run, by contrast, ran ~61 s dwells (N=90 on six of ten markers).
