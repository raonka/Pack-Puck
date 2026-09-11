# Pack Pucks

**An open, commodity-hardware platform for peer-to-peer radio ranging — and the field data it has produced.**

Two matchbox-sized devices tell each other how far apart they are, using nothing but
the travel time of a 2.4 GHz radio signal between them. No GPS. No phone. No cloud.
No fixed anchors. Each device shows the distance as a colour on an LED ring.

The point is what happens when infrastructure isn't there. A group spread out across a
forest, a tunnel, a trailhead or a construction site has no reliable way to answer
"how far away is everyone?" GPS needs sky, mesh radios need a network, and phones need
both. Two pucks need only each other.

This repository is the platform and its measurements: firmware, the offload and QC
tooling, the raw datasets from every outing, and the analysis that produced every
figure below.

---

## Findings

Everything here comes from a single outing — **22 August 2026**, ten surveyed cones at
30 m spacing from 30 m to 300 m, both bandwidths run back to back on the same line, at
the same spreading factor, the same power, within hours of each other. That matching is
the point: it is what isolates bandwidth from everything else.

Across both campaign outings, **8,000 ranging exchanges completed with zero timeouts
and zero errors.**

### Bandwidth dominates everything

![Ranging accuracy by bandwidth](data/analysis/figures/bandwidth_accuracy.png)

At **1625 kHz** the system holds inside ±5 m across the whole 30–300 m span. At
**406.25 kHz** it doesn't — and the error is a *systematic positive bias*, not scatter.
Distances come back consistently too long, by about 10 m, at almost every marker.

| | 406.25 kHz | 1625 kHz |
|---|---|---|
| Mean absolute error — static | 11.1 m | **1.7 m** |
| Mean absolute error — semi-mobile | 12.1 m | **1.7 m** |
| Worst marker — static | 29.9 m | **3.2 m** |
| Signed bias — static | **+10.5 m** | +0.4 m |
| Signed bias — semi-mobile | **+12.1 m** | −0.2 m |
| Mean spread (IQR) — static | 5.2 m | **1.7 m** |

That is roughly a **7× accuracy advantage** and a **3× precision advantage** for the
wider bandwidth, under conditions matched in every other respect.

### Walking costs almost nothing — at the right bandwidth

![Effect of motion](data/analysis/figures/motion_effect.png)

Carrying one endpoint at walking pace, stopping at each cone, leaves 1625 kHz accuracy
**unchanged**: 1.7 m static, 1.7 m semi-mobile. The 406.25 kHz bias is if anything
slightly worse in motion (11.1 → 12.1 m).

This is the measurement that motivated the work. Published SX1280 ranging studies have
compared bandwidths while standing still, or walked at a single bandwidth — the matched
comparison under motion is the gap this fills. Ground truth for the moving runs comes
from a stopwatch lap log taken as the carried device reached each cone, so dwell
windows are operator-attributed rather than inferred from the data.

### Precision holds across the range

![Precision by bandwidth](data/analysis/figures/bandwidth_precision.png)

1625 kHz stays between 1 and 3 m of spread from 30 m all the way out to 300 m.
406.25 kHz runs 3–8.5 m and degrades with distance.

### The wider bandwidth is nearly free

Ranging cadence is set by the blocking radio call, not by software pacing:

| Bandwidth | Cycle time | Rate |
|---|---|---|
| 1625 kHz | **655 ms** | 1.53 Hz |
| 406.25 kHz | 686 ms | 1.46 Hz |

Cutting bandwidth by 4× buys only **4.7 %** more time per cycle, because fixed overhead
— not airtime — dominates the exchange. So the narrow setting costs 7× accuracy and
returns almost nothing.

**Practical conclusion: use 1625 kHz.** Reach is not the trade-off either — a separate
pilot outing ranged out to a **365 m** median and was still working when the ground ran
out.

### What these numbers do not say

A short, honest list. The detail is in [`data/README.md`](data/README.md) and the
per-session logs.

- **No error bound on the ground truth.** Cones were surveyed with a class III
  fibreglass tape, whose instrument tolerance is ±1.3 cm at 30 m and ±12 cm at 300 m.
  But tape sag, tension and leapfrog accumulation across ten segments were never
  measured, so **no total tolerance is stated** and none has been invented. Treat the
  accuracy figures as having no error bars yet.
- **One outing carries the comparison.** The matched 406.25-vs-1625 kHz result rests on
  22 August alone. The 15 August outing ran one bandwidth and is explicitly *not*
  contribution-grade — attempt counts below specification, no arrival log.
- **The 240 m cone misbehaves, repeatably.** It deviates on both outings and far more at
  the lower bandwidth (+29.9 m at 406.25 kHz against +3.2 m at 1625 kHz), beside a
  recorded structure. That looks like multipath at a fixed reflector, but two outings at
  one cone is an observation, not a result. It is flagged for targeted re-measurement,
  not interpreted.
- **The pilot outing has no ground truth at all.** Its 365 m reach is a range
  demonstration; distances were paced, not surveyed. No accuracy figure is derivable
  from it.

### Reproducing all of it

Raw CSVs are opened read-only and never modified — no ground truth was ever written back
into them. Every report and figure regenerates from the published data:

```bash
python tools/qc_session.py --data-dir data/ranging_experiments/2026-08-22_GMATownship_session02/raw/20260822_174415-Initiator --out qc_out --session-plan data/analysis/2026-08-22_GMATownship_174415_qc/session_plan.json --expect-bw 1625.0
```

```bash
python tools/make_readme_figures.py
```

`data/README.md` documents the sites, the weather, every session's provenance and the
deviations recorded in the field — including the runs that went wrong, and why.

---

## Build it yourself

### Hardware

| Component | Part |
|---|---|
| MCU + radio | LILYGO T3-S3 V1.2 — ESP32-S3 + Semtech SX1280, *Without PA* (H594) × 2 |
| Output | WS2812B 16-LED ring × 2, on GPIO 38 |
| Power | USB-C — laptop, wall adapter or power bank |
| Antenna | SMA, finger-tight |

Both boards run the same code with one compile-time switch. One is the Initiator and
drives the exchange; the other answers.

### Toolchain

Arduino IDE 2.x with ESP32 board support, plus **RadioLib** (Jan Gromeš) and
**FastLED** (Daniel Garcia) from the Library Manager.

### Flash

1. Open the sketch for the phase you want from `firmware/`.
2. Board **LilyGo T3-S3**, Board Revision **Radio-SX1280**.
3. Enable **USB CDC On Boot**; PSRAM **QSPI PSRAM**; Partition Scheme
   **Default 4MB with spiffs**.
4. Set the role — `#define ROLE_INITIATOR` on one board, `#define ROLE_RESPONDER` on the
   other. There is no runtime switching.
5. Flash both, then open Serial Monitor at 115200 baud.

The boot banner reports firmware version, board ID and the full radio configuration, and
confirms WiFi and Bluetooth are off. If either fails to disable, the board faults rather
than collecting data.

### Radio configuration

One `#define` block drives `radio.begin()`, the boot banner and the CSV header, so every
logged file self-describes the settings that produced it.

```cpp
#define RADIO_FREQ_MHZ     2400.0f  // MHz
#define RADIO_BW_KHZ       1625.0f  // kHz — or 406.25f
#define RADIO_SF           8        // spreading factor
#define RADIO_CR           7        // coding rate 4/7
#define RADIO_TX_POWER_DBM 12       // H594 hardware max ~12.5 dBm
#define RADIO_ADDRESS      0x12345678
```

Two notes that cost time to discover. Semtech's documentation labels the 1625 kHz
setting "1600 kHz", but the hardware register is 52 MHz / 32 = 1625 kHz — and RadioLib
rejects `1600.0` and `400.0` outright. The address must match on both boards or they
will never pair.

### Collecting data

Logs are written to on-board flash as CSV and pulled off over serial afterwards:

```bash
python tools/offload/offload.py --port COM8 --session-id 20260822_site
```

The script prompts for session metadata, converts local timestamps to UTC, verifies
every file against a byte-count manifest, and only then offers to wipe the flash. Wipe
it between outings — leaving it unwiped is how one of our own offloads ended up mixing
three firmware versions' worth of stale recordings into what looked like a single
session.

---

## Repository layout

```
firmware/   Arduino sketches by phase — 01_blink, 02_radio_comms, 03_ranging
tools/      offload.py (flash → CSV), qc_session.py (QC + figures), make_readme_figures.py
data/       raw CSVs, session logs, field notes, weather, and generated analysis
docs/       FSD.md — functional specification, requirements, interfaces
```

---

## Status

Working today: two-board ranging at both bandwidths, on-device CSV logging, the offload
and QC pipeline, and three completed field outings across two sites.

Next: closing the ground-truth error bound, re-measuring the 240 m anomaly at both
bandwidths, and a second matched outing so the bandwidth comparison rests on more than
one day. A Part 1 preprint covering the platform and this characterisation is in
preparation; the full experimental protocol (`Methodology.md`) is published alongside it
and is available on request before then.

Out of scope for now: battery operation, crash detection, indoor multipath
characterisation, and ranging between more than two devices.

---

## Documentation

| Document | Purpose |
|---|---|
| [`docs/FSD.md`](docs/FSD.md) | Functional specification — requirements, interfaces, data schemas, acceptance criteria |
| [`data/README.md`](data/README.md) | Datasets — sites, conditions, per-session provenance, limitations, reproduction |
| [`tools/qc_session.py`](tools/qc_session.py) | Session QC tool — generates every report and figure under `data/analysis/` |

## License

TBD.
