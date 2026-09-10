# Undated SF6 range walk

One recording, published because it is the measured basis for a figure stated in
`docs/FSD.md` FR-2.1. Nothing else depends on it, and it is **not campaign data**.

## What it is

A continuous out-and-back walk at **SF6 / 1625 kHz**, logged in one boot. The carried
device was walked away from the stationary one to maximum reach and back again:

| Portion of run | Mean distance |
|---|---|
| 0–10 % | 1.9 m |
| 20–30 % | 40.5 m |
| 40–50 % | **125.0 m** (peak sample 175.3 m) |
| 60–70 % | 73.6 m |
| 90–100 % | 8.1 m |

305 successful readings, range −12.7 m to 175.3 m. A clean triangular profile out
and back.

## Why it is published

Its **median inter-row cadence is 648 ms**. `docs/FSD.md` FR-2.1 states that moving
SF6 → SF8 at 1625 kHz shifted the cycle time from ≈ 648 ms to ≈ 655 ms despite a 4×
increase in symbol time — the observation behind the conclusion that fixed overhead,
not airtime, dominates the ranging cycle. This file is where the 648 ms comes from.

Cadence is a property of the radio exchange, not of distance, so a walk is a valid
basis for it even though it is useless for accuracy.

## Provenance, and two things wrong with the filename

The file is `2026-07-13_ParadeGTest_T1_distance-52m_Initiator_S1_b3.csv`. **Both the
date and the distance in that name are wrong**, and the name is left unchanged
because raw CSVs are never edited in this project.

- **The date.** The name and the file's line-2 metadata say 13 July 2026. Both were
  typed by the operator at offload time on 13 July. The file's own firmware stamp
  reads `FW=0.7-offload-mode`, and v0.7 was replaced by v0.9 on 22 June 2026, so the
  recording necessarily predates 22 June. It reached the 13 July offload only because
  SPIFFS had never been formatted. Actual date: **unknown, before 22 June 2026.**
- **The distance.** `distance-52m` implies a static hold at 52 m. It is a walk from
  roughly 0 m to 175 m and back. The median of 48.5 m is the median of a walk and
  means nothing as a distance measurement.

Site is likewise unconfirmed — `ParadeGTest` in the label is the operator's
offload-time guess, not a field record.

`manifest.txt` is the original from the `20260713_052019-Initiator` offload and lists
all 18 files that offload contained. Only this one is published; the other 17 are
empty, contain only negative distances, or predate the outing. See
`../2026-07-13_ParadeGround_pilot/2026-07-13-ParadeGround-P1.session.txt`, deviation
D1, for the full diagnosis.

## Do not use this file for

Accuracy, signed error, or any per-distance statistic. There is no ground truth: no
tape survey, no markers, no arrival log. It supports exactly one claim — the SF6
cycle time — and nothing else.
