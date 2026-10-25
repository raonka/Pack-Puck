# Pack Pucks — Ground-Truth Tolerance Derivation (GMA township marker line)

**Status (2026-10-10, revised same day).** Recomputed with operator upper-bound estimates. The first 2026-10-10 version stopped at "inputs missing"; this version supersedes it.

- **Tier 1 static: OD-METH-3 CLOSED.** The RSS bound at 300 m is −448 / +281 mm, inside ±50 cm.
- **Tier 2 stop-and-go: OD-METH-3 CLOSED (2026-10-10 close-out).** The carried puck was held on an upright pole, like a flag, at the cone mark: along-line offset negligible, sideways case applies. RSS −411 / +245 mm at 300 m, inside ±50 cm.
- **Tolerance work closed.** The largest term (~0.5 m at 300 m) is small against the observed 2.1–26.5 m bandwidth differences.
- **Paper sentence:** "Ground truth ±0.5 m at 300 m; cone-position error is shared by both bandwidths and cancels in the comparison; puck placement adds at most ~±0.2 m to the difference." The ±0.2 m is the RSS figure; the worst-case linear residual is ±0.4 m (§4).

**Prepared:** 2026-10-10.
**Scope:** the ten cone positions (30–300 m, 30 m spacing) laid by tape leapfrog on 15 Aug 2026. The same road-surface marks were reused on 22 Aug with no fresh survey. Every term in §2.1–§2.4 is therefore **common-mode** across both sessions, both bandwidths and both tiers.

---

## 1. Sign convention

- `D_k = 30·k` m is the nominal distance of cone *k*.
- `δ_k = true distance − D_k` is the ground-truth error.
- The paper's signed error is `err = median − D_k ≈ ranging error + δ_k`.

Geometric terms (zigzag; a carried puck held toward the static end) make the true distance **shorter** than nominal. They push `err` **negative**, so they appear on the negative side of the bound only.

## 2. Terms (all inputs are operator upper bounds unless marked SOURCED)

### 2.1 Instrument MPE, class III (systematic, either sign)

- **Tape.** Freemans Grey Magic, 30 m, fibreglass, accuracy class III (operator; class also recorded in both session logs 2026-09-11).
- **MPE per segment.** ±(0.6 + 0.4·30) mm = **±12.6 mm** (SOURCED: class III formula in the session logs).
  - One UK retailer listing gives "±4.6 mm over 10 m" for a Freeman class 3 fibreglass tape, which matches the same formula: https://www.neuff.co.uk/collections/vendors/products/measuring-tape-freeman-open
- **Accumulation.** The ten leapfrogged segments reuse the same 0–30 m graduation, so the error is correlated and accumulates linearly: **±12.6·k mm; ±126 mm at 300 m.**
  - This supersedes the ±120.6 mm (single 300 m length) first written in the session logs; both logs now carry a dated correction.

### 2.2 Tape stretch (treated as inside the MPE)

- **Not sourced.** The reference tension for the Grey Magic class III certification was not found. Searches on 2026-10-10 found retailer listings only, with no tension figure.
- **Treatment.** Per the operator ruling, stretch is treated as contained within the class MPE. Basis: the tape was hand-pulled taut on flat concrete, i.e. near a normal reading tension with full surface support.
- **This is an assumption, not a derivation.** If the reference tension is later sourced and the hand tension is shown to exceed it materially, a positive-sign term must be added.

### 2.3 Lateral zigzag (systematic, always negative)

- **Input.** The tape was laid by eye along the road edge, and every cone sits within ±0.5 m of the straight line. The offset difference between consecutive cones is therefore Δ ≤ 1.0 m.
- **Shortening per segment.** Δ²/(2L) = 1.0² / (2·30) m = **16.7 mm**, always negative.
- **Accumulated.** −16.7·k mm; **−167 mm at 300 m.**
- **Conservatism.** The first segment starts at the origin (offset 0), so its Δ ≤ 0.5 m and its shortening ≤ 4.2 mm. Using that would give −154 mm. The simpler, more conservative −167 mm is used.
- **Corroboration.** An operator photo of the 15 Aug survey (not published: it shows an identifiable person) shows the tape run out flat on the concrete, along the road's right edge.

### 2.4 Graduation-to-mark transfer (random, per segment)

- **Input.** ±20 mm per segment, independent between segments.
- **Accumulated.** Linear ±20·k mm; RSS ±20·√k mm. At 300 m: **±200 mm linear, ±63 mm RSS.**

### 2.5 Slope (assumed negligible)

- **Assumption.** Flat concrete road; slope treated as negligible.
- **Why only grade changes would matter.** A uniform grade affects the tape and the ranging path equally, because both antennas are at matched 150 cm height above local ground. Only grade *changes* along the line would open a gap between them.
- **Status.** No road profile exists; this assumption is not checked against data.

### 2.6 Static puck centring over the mark (random, not common-mode)

- **Input.** Tripod straddling the mark: ±100 mm at each end, including the origin.
- **Combined.** Two ends: ±200 mm linear, ±141 mm RSS.
- **Not common-mode.** The pucks were re-placed for every run, so this term does not cancel between runs (§4).

### 2.7 Carried puck (stop-and-go)

The operator instruction gave the holding direction as two unresolved alternatives: "[SIDEWAYS, perpendicular to the line / TOWARD THE STATIC PUCK at arm's reach ~0.6 m]". Both are computed below. The static (origin) end keeps its ±100 mm centring in both cases.

- **Sideways, 0.6 m perpendicular.** Distance becomes `√(D² + 0.6²)`, i.e. `+0.36/(2D)` m. That is +6 mm at 30 m and +0.6 mm at 300 m: positive and negligible.
- **Toward the static puck, 0.6 m.** The carried antenna is 0.6 m closer than the mark: **−600 mm**, systematic, at every marker.
  - This is a *known offset*. It could be applied as a correction (ground truth `D_k − 0.6 m`) instead of carried as error. That would shift every stop-and-go signed error by +0.6 m, and leave as residual only the (unestimated) variability of the arm's-reach distance.
- **Not estimated in either case.** No along-line placement tolerance was given for where the pole stood relative to the mark. It is omitted below, so the stop-and-go rows are slightly optimistic relative to the static row.

## 3. Bounds

**Method.**
- *Worst-case linear:* every term at its limit, summed.
- *RSS:* the random terms (§2.4, §2.6, carried-end placement) combined in quadrature; the systematic terms (§2.1 MPE, §2.3 zigzag, §2.7 offset) added linearly.
- The ± limits are treated as tolerance bounds. RSS here is a tolerance-stack combination, not a k = 2 statistical interval.

**Formulas at cone *k*** (mm; D = 30k m):

| term | static | stop-and-go |
|---|---|---|
| systematic, either sign | 12.6 k | 12.6 k |
| systematic, negative only | 16.7 k | 16.7 k (+ 600 if "toward") |
| systematic, positive only | 0 | 0 (+ 360/D if "sideways") |
| random, linear | 20 k + 200 | 20 k + 100 |
| random, RSS | √(400 k + 20 000) | √(400 k + 10 000) |

**Per marker** (mm, negative side / positive side):

| marker m | static linear | static RSS | s&g sideways linear | s&g sideways RSS | s&g toward linear | s&g toward RSS |
|---|---|---|---|---|---|---|
| 30 | −249 / +233 | −172 / +155 | −149 / +139 | −131 / +121 | −749 / +133 | −731 / +115 |
| 60 | −299 / +265 | −203 / +169 | −199 / +168 | −162 / +132 | −799 / +165 | −762 / +129 |
| 90 | −348 / +298 | −233 / +183 | −248 / +200 | −194 / +146 | −848 / +198 | −794 / +144 |
| 120 | −397 / +330 | −264 / +197 | −297 / +232 | −225 / +160 | −897 / +230 | −825 / +158 |
| 150 | −446 / +363 | −295 / +211 | −346 / +264 | −256 / +174 | −946 / +263 | −856 / +173 |
| 180 | −496 / +396 | −325 / +225 | −396 / +297 | −287 / +188 | −996 / +296 | −887 / +187 |
| 210 | −545 / +428 | −356 / +239 | −445 / +329 | −318 / +202 | −1045 / +328 | −918 / +201 |
| 240 | −594 / +461 | −386 / +253 | −494 / +362 | −349 / +216 | −1094 / +361 | −949 / +216 |
| 270 | −643 / +493 | −417 / +267 | −543 / +394 | −380 / +231 | −1143 / +393 | −980 / +230 |
| **300** | **−693 / +526** | **−448 / +281** | **−593 / +427** | **−411 / +245** | **−1193 / +426** | **−1011 / +244** |

**At 300 m against ±50 cm:**
- **Static.** RSS within (−448 / +281). Worst-case linear exceeds it (−693 / +526).
- **Stop-and-go, sideways.** RSS within (−411 / +245). Linear exceeds it on the negative side (−593).
- **Stop-and-go, toward, uncorrected.** Both methods exceed it (RSS −1011).

## 4. Common-mode and the bandwidth comparison

The cone-position terms (§2.1 MPE, §2.3 zigzag, §2.4 transfer, §2.5 slope) are identical for every run: same marks, both sessions, both bandwidths, both tiers. **They cancel exactly in the 406.25-vs-1625 kHz error difference and limit only absolute-accuracy statements.**

Puck placement (§2.6, §2.7) is **not** common-mode: the pucks were re-placed for each run, so it does not cancel. Its residual in a per-marker bandwidth difference:

| comparison | linear | RSS | basis |
|---|---|---|---|
| Static | ±400 mm | ±200 mm | four independent end placements, ±100 mm each |
| Stop-and-go | ±200 mm | ±141 mm | two origin placements; carried-end terms excluded, not estimated |
| Observed \|406.25 − 1625\| differences | — | — | static 2.1–26.5 m (discard5s TABLE 2); stop-and-go 6.2–20.5 m (TABLE 3). The smallest (2.1 m) is about 5× the static linear residual |

## 5. 1625 kHz signed errors against the bound

Errors are unrounded post-discard medians (`tools/per_marker_tables.py`, 22 Aug).

**Static (bound: static column):**

| marker m | err | inside RSS? | inside linear? |
|---|---|---|---|
| 30 | −0.219 m | no (−0.172) | yes (−0.249) |
| 60 | +0.352 m | no | no |
| 90 | −2.977 m | no | no |
| 120 | +1.898 m | no | no |
| 150 | −2.558 m | no | no |
| 180 | +1.167 m | no | no |
| 210 | +0.509 m | no | no |
| 240 | +3.164 m | no | no |
| 270 | +2.867 m | no | no |
| 300 | −0.586 m | no (−0.448) | yes (−0.693) |
| **mean signed bias** | **+0.362 m** | no (mean of per-marker RSS +side 0.218 m) | yes (mean linear +side 0.379 m) |

**Stop-and-go (bound depends on §2.7):**

| marker m | err | sideways RSS | toward RSS |
|---|---|---|---|
| 300 | −0.180 m | **inside** | **inside** |
| 180 | −0.883 m | no | **inside** (−0.887) |
| 30, 60, 90, 120, 150, 210, 240, 270 | −4.05 to +4.85 m | no | no |
| **mean signed bias** | **−0.167 m** | **inside** (mean of per-marker RSS −side 0.271 m) | **inside** |

**Summary.** Of the 1625 kHz figures, these fall inside the ground-truth bound:
- the stop-and-go 300 m marker (both carry cases);
- the stop-and-go mean bias (−0.17 m);
- the static 30 m and 300 m markers and the static mean bias (+0.36 m), on the linear bound only;
- the stop-and-go 180 m marker, in the "toward" case only.

Every other per-marker 1625 kHz error, 0.35–4.85 m in magnitude, exceeds the ground-truth bound. Those errors are **not** explained by ground truth.

## 6. Result

- **Tier 1 static.** The RSS bound at 300 m is −448 / +281 mm, within ±50 cm. **OD-METH-3 closed for Tier 1**, and the ±50 cm target bound for surveyed-cone ground truth (Methodology §5.3) is backed for static data on the RSS basis.
- **Tier 2 stop-and-go: CLOSED 2026-10-10.** Upright pole at the mark (sideways case): RSS −411 / +245 mm at 300 m, within ±50 cm. The "toward" alternatives below are retained for the record only.
  - If **sideways:** RSS −411 / +245 mm, within ±50 cm. OD-METH-3 closes for Tier 2 too.
  - If **toward, uncorrected:** RSS −1011 / +244 mm. In that case the derived bound would replace ±50 cm as the stated stop-and-go tolerance.
  - If **toward, with the 0.6 m applied as a correction:** the residual needs an arm's-reach variability estimate.

  The 2026-10-10 close-out selected the sideways case.

## 7. Input register

| Input | Value | Status |
|---|---|---|
| Tape | Freemans Grey Magic 30 m, fibreglass, class III | operator; class SOURCED in session logs |
| MPE formula | ±(0.6 + 0.4 L) mm | SOURCED (session logs; consistent with retailer listing) |
| Reference tension | — | **NOT SOURCED**; stretch treated as within MPE |
| Sag | none (flat on concrete) | operator; a 15 Aug survey photo (unpublished) is consistent |
| Lateral | each cone within ±0.5 m; Δ ≤ 1.0 m | operator upper bound |
| Transfer | ±2 cm per segment | operator upper bound |
| Slope | negligible | **ASSUMPTION** (no profile) |
| Static centring | ±10 cm each end | operator upper bound |
| Carried puck | upright pole at the cone mark (sideways case) | operator, 2026-10-10 |
| Carried along-line placement | negligible (pole stood at the mark) | operator, 2026-10-10 |
| Tape stretch | within class MPE | **STATED ASSUMPTION** |
| Thermal expansion | — | not estimated (not requested) |
