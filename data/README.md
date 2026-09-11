# Pack Pucks — Ranging Datasets

Raw and analysed field data from SX1280 2.4 GHz Time-of-Flight ranging between two
peer devices, with no fixed anchors, no GPS and no infrastructure of any kind.

This directory is part of contribution **C1** of the Part 1 preprint: an open,
commodity-hardware platform for SX1280 peer-to-peer ToF ranging research, published
with its raw datasets and the analysis script that produced every reported figure.

---

## Availability of the methodology document

The full experimental protocol (`Methodology.md`) — ground-truth survey procedure,
sample sizes, session structure, environmental logging, and the discard criteria the
QC tool enforces — **will be published when the Part 1 preprint goes live.**

Until then it is available on request. Reports and logs in this directory cite it by
section number (e.g. `Methodology 7.2`); those citations resolve against the document
that ships with the preprint. **If you need a copy before then, get in touch and one
will be sent** — open an issue on this repository and ask.

---

## Sites

The campaign runs at **two sites in different cities**, roughly 1100 km apart. This is
deliberate, not a transcription error.

| Site | Location | Coordinates | Used for |
|---|---|---|---|
| **GMA township** | Kota, Rajasthan | 25.224075, 75.814061 | Both campaign outings (15 & 22 Aug) |
| **Parade Ground** | Secunderabad, Hyderabad, Telangana | 17.444183, 78.492827 | 13 July pilot |

Coordinates are operator-supplied and have not been independently surveyed.

## Environmental conditions

Recorded from phone weather at the times shown. Gaps are stated rather than filled.

| | 13 Jul, 07:12 | 15 Aug, 18:27 | 22 Aug, 15:07 |
|---|---|---|---|
| Conditions | Partly cloudy | Cloudy | Partly cloudy |
| Temperature | 26 °C (feels 28) | 30 °C (feels 36) | 34 °C (feels 40) |
| Humidity | 73 % (dew pt 21°) | **not captured** | 56 % (dew pt 24°) |
| Wind | 21 kph W | 10 kph W | 11 kph W |
| Pressure | 1007 hPa | — | 1002 hPa |
| Visibility | 16 km | — | 16 km |
| Air quality | 40 (good) | — | 82 (satisfactory) |
| Rain, day total | <1.3 mm | <1.3 mm | <1.3 mm |

Screenshots are in each session's `environment/` directory. Two honest gaps: 15 August
humidity was never captured (the screenshot pair ends above the humidity card), and
22 August has **one** reading only — the later 16:43 capture re-displays the same 15:07
data with the phone in airplane mode, so no mid- or end-of-session conditions exist.
None of the three outings logged wall-clock start/end times in the field.

---

## Hardware and radio configuration

Identical on both devices, unchanged during every session below.

| | |
|---|---|
| Board | LILYGO T3-S3 V1.2 — ESP32-S3 + Semtech SX1280 (H594, *Without PA*) × 2 |
| Frequency | 2400.0 MHz |
| Spreading factor | **SF8** across all campaign data, held constant between bandwidths |
| Bandwidth | **406.25 kHz** and **1625 kHz** (the register value Semtech labels "1600 kHz"; 52 MHz / 32) |
| Coding rate | 4/7 |
| Output power | 12 dBm (H594 hardware maximum ≈ 12.5 dBm) |
| Ranging address | `0x12345678` |
| WiFi / Bluetooth | disabled at boot, self-reported in the boot banner |
| Initiator board ID | `0x541BBDD4DB1C` |
| Responder board ID | `0x5CD85EDB5110` |

**Measured ranging cadence** — set by the blocking RadioLib `range()` call, not by
software pacing:

| Bandwidth | Cycle time | Rate | Basis |
|---|---|---|---|
| 1625 kHz | **≈ 655 ms** | ≈ 1.53 Hz | pooled median, 2649 inter-row deltas |
| 406.25 kHz | **≈ 686 ms** | ≈ 1.46 Hz | pooled median, 3084 inter-row deltas |

A 4× bandwidth reduction costs only ≈ 31 ms per cycle (+4.7 %), which is consistent
with fixed overhead dominating airtime. A cycle that receives *no* response is far
longer — RadioLib runs out a fixed 10 s guard (≈ 10.6 s measured) — so cadence
degrades sharply wherever timeouts are frequent. Both GMA township outings recorded
**zero timeouts**.

---

## Layout

```
data/
├── ranging_experiments/
│   ├── 2026-07-13_ParadeGround_pilot/      pilot — range progression, not campaign data
│   ├── 2026-08-15_GMATownship_session01/   campaign outing 1 — 1625 kHz only
│   ├── 2026-08-22_GMATownship_session02/   campaign outing 2 — both bandwidths
│   └── undated_SF6_range_walk/             single SF6 file supporting one FSD figure
└── analysis/                               QC reports and figures (generated)
```

Each session directory holds:

| Path | Contents |
|---|---|
| `raw/<offload-session>/` | `pucklog_*.csv` exactly as offloaded, plus the `manifest.txt` byte-count record |
| `raw/superseded/` | recordings kept for provenance but excluded from analysis |
| `*.session.txt` | the session log — setup, deviations, file dispositions, open items |
| `environment/` | weather screenshots for the outing |
| `field_notes-*.txt` | notes written in the field |
| `stopwatch_laps_data_*.csv` | operator arrival logs (stop-and-go runs only) |

---

## Sessions

### 2026-08-22 — GMA township, session 02 *(the strongest data here)*

Both bandwidths, both tiers, ten cones at 30 m spacing from 30–300 m. Sweep order
406.25 kHz then 1625 kHz, leading with the bandwidth not run on 15 August.

| Run | Directory | Files | Tool verdict |
|---|---|---|---|
| 406.25 kHz static | `raw/20260822_162424-Initiator/` | 14 of 18 | **HOLD** — see below |
| 406.25 kHz stop-and-go | same | 2 of 18 | PASS |
| 406.25 kHz responder | `raw/20260822_163115-Responder/` | 1 | — |
| 1625 kHz static | `raw/20260822_174415-Initiator/` | 10 of 11 | PASS |
| 1625 kHz stop-and-go | same | 1 of 11 | PASS |

Both stop-and-go runs carry **operator arrival logs** (`stopwatch_laps_data_*.csv`) —
phone stopwatch laps taken as the carried device reached each cone, giving directly
attributed ground truth rather than an inferred plateau. This is the strongest ground
truth in the dataset. Note that `qc_session.py`'s nearest-marker heuristic disagrees
with the lap log on two of ten markers at 406.25 kHz; where they disagree,
`analysis/2026-08-22_GMATownship_day2_qc_tables.md` recomputes on the lap windows and
**supersedes the tool's stop-and-go numbers**.

**The 406.25 kHz static HOLD.** Two files exceed the tool's 15 m rolling-median drift
limit: `_8` (180 m, drift 19.7 m) and `_9` (210 m, drift 15.9 m). Both were **kept**.
Each carries the full N=100 with zero timeouts and zero errors, the 180 m excursion
has a recorded physical cause in the field notes ("180m — few people walked by"), and
both sit inside a strictly ascending median sequence. The tool's HOLD verdict is left
standing and unmodified; the operator disposition — keep, with the anomaly documented
— sits alongside it rather than overriding it. See deviation D5.

### 2026-08-15 — GMA township, session 01

First campaign outing. **1625 kHz only** — the 406.25 kHz sweep was not run. Same ten
cones. Static sweep and semi-mobile stop-and-go, both at 1625 kHz.

- `raw/20260815_184714-Initiator/` — 13 files, the canonical sweep. QC **PASS**.
- `raw/superseded/20260815_173207-Initiator/` — 2 files at the 30 m and 60 m markers.

  These are **not** an earlier version of the canonical files. A `SPIFFS.format()`
  ran between the two offloads, which reset the firmware's boot index to 1, so both
  sets contain a `pucklog_D4DB1C_1.csv` and `_2.csv` that are *different physical
  runs*. An MD5 cross-check of all 15 files across both sets found no matching pair.
  Retained so the reindexing trap is visible rather than silently discarded; see the
  session log, item T6, for the full diagnosis.

*Known limitations* — recorded in the session log, not corrected after the fact:
attempt counts fall short of the N=100 specification on most markers; there is no
operator arrival log for the stop-and-go run; per-file operator metadata was not
written; humidity was not captured. **This session is not contribution-grade.**

### 2026-07-13 — Parade Ground pilot *(not campaign data)*

First outdoor outing of the project, published for provenance. **Excluded from every
reported result.** Its purpose was to establish that ranging worked beyond the bench
and to find the practical maximum reach at 1625 kHz / SF8 — which is what set the
300 m ceiling later used for the GMA township marker line.

Eight positions, ascending, at 25 m then 50 m spacing:

| File | N | Median | Nominal position |
|---|---|---|---|
| `_1` | 120 | 25.1 m | 25 |
| `_2` | 120 | 46.7 m | 50 |
| `_3` | 99 | 91.8 m | 100 |
| `_4` | 100 | 158.7 m | 150 |
| `_5` | 79 | 219.4 m | 200 |
| `_6` | 68 | 278.4 m | 250 |
| `_8` | 98 | 313.1 m | 300 |
| `_9` | 90 | 365.3 m | 350 |

**Maximum reach 365 m** — 65 m beyond the longest GMA township cone. Ranging did not
fail at the far end; the session ended because the ground ran out. 350 m was the last
position attempted, not a measured limit. Boot 7 is absent from the offload.

⚠️ **There is no ground truth for this outing.** No tape survey was run — the position
labels are nominal operator targets, paced not measured. Read the table as a
demonstration of range progression, never as an accuracy result: the apparent offsets
carry no meaning. This is why no QC report exists for this session.

A second offload directory from the same morning (`20260713_052019`) is **not
published**. It turned out to be an accumulated flash backlog spanning three firmware
eras rather than that day's work — 14 of its 18 files contain zero successful
readings, and 15 of the 18 predate the outing by weeks. The one usable file from it is
published separately, below. Full diagnosis in the session log, deviation D1.

### `undated_SF6_range_walk/`

A single file, published because it is the measured basis for a figure `docs/FSD.md`
FR-2.1 already states: the SF6 cycle time of **648 ms**, against 655 ms at SF8. It is
a continuous out-and-back walk at SF6 / 1625 kHz, peaking at 175 m.

Its filename claims 13 July 2026 and a static hold at 52 m. **Both are wrong** — the
name was typed at offload time and the firmware stamp proves the recording predates
22 June. The filename is left unchanged because raw CSVs are never edited. See that
directory's README before using it for anything.

---

## Two things to read before using these numbers

**1. Ground-truth tolerance has a floor but no total.** Cone positions were surveyed
with a taut fibreglass tape by two-person leapfrog, read from the 0 graduation against
a pre-written cumulative tally sheet, with every cone numbered at placement and a full
recount after layout.

The tape is **accuracy class III**, whose maximum permissible error is
±(0.6 + 0.4 L) mm with L rounded up to whole metres:

| Distance | Instrument MPE |
|---|---|
| 30 m | ±1.3 cm |
| 300 m | ±12.1 cm |

**That is the instrument floor, not the error budget.** Tape sag, tension variation,
leapfrog accumulation across ten segments and cone-placement precision are all
unquantified — none were recorded in the field. No total ground-truth bound is stated,
and none has been invented. Every signed-error figure in this dataset carries that
open item with it, and closing it requires a sag/tension estimate on a future outing.

**2. The 240 m marker deviates on both outings, and bandwidth-dependently.**

| Outing | Bandwidth | Observation |
|---|---|---|
| 15 Aug | 1625 kHz | IQR 5.5 m static / 4.6 m stop-and-go, vs 1.0–2.5 m at neighbouring markers |
| 22 Aug | 406.25 kHz | signed error **+29.9 m** static, +15.6 m stop-and-go |
| 22 Aug | 1625 kHz | signed error **+3.2 m** static, +0.7 m stop-and-go |

The same cone, the same recorded structure, across two outings, with an effect roughly
an order of magnitude larger at the lower bandwidth. That is the profile of multipath
at a fixed reflector. It is **recorded as an observation, not claimed as a result** —
two outings at one cone is not evidence. A targeted re-measurement at both bandwidths,
with site photographs, is the first item of the next outing.

---

## Reproducing the analysis

Every report and figure under `analysis/` is generated by `tools/qc_session.py`. Raw
CSVs are opened **read-only and are never modified** — no ground truth was written
back into them, which is why per-file truth lives in `session_plan.json` instead.

```bash
python tools/qc_session.py \
  --data-dir data/ranging_experiments/2026-08-22_GMATownship_session02/raw/20260822_174415-Initiator \
  --out qc_out \
  --session-plan data/analysis/2026-08-22_GMATownship_174415_qc/session_plan.json \
  --expect-bw 1625.0
```

For the 406.25 kHz run add `--expect-bw 406.25 --cadence-ms 686.0`.

Regenerating reproduces the committed reports exactly; only the generation timestamp
differs. Session paths in the reports are repo-relative, so they match for anyone who
clones.
