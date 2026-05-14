# Pack Pucks — Functional Specification Document (FSD)

**Document Version:** 1.0  
**Date:** 13 May 2026  
**Status:** Active — covers June 15, 2026 demo scope  
**Owner:** Ishan Raonka 

---

## 1. Document Purpose & Conventions

### 1.1 Purpose
This document defines the functional and non-functional requirements of the
Pack Pucks system for the June 15, 2026 demo and the July 2026 arXiv preprint
(Part 1). It is the single source of truth for system behaviour. Firmware
implementation references this document by requirement ID. Methodology
sections of the preprint reference this document for system definition.

### 1.2 How to Read This Document
Every requirement has a stable identifier (e.g. `FR-3.2`, `NFR-1`). When
firmware code implements a requirement, the code comment cites the ID. When
the preprint references system behaviour, it cites the ID. This makes the
system traceable end-to-end — from spec to code to paper.

### 1.3 Requirement Identifier Scheme
- `FR-*` — Functional Requirement (what the system must do)
- `NFR-*` — Non-Functional Requirement (performance, reliability, etc.)
- `BR-*` — Behavioural Requirement (state-based behaviour)
- `IR-*` — Interface Requirement (hardware/software interfaces)
- `DR-*` — Data Requirement (logging, formats)
- `AC-*` — Acceptance Criterion (demo-ready definition)
- `OUT-*` — Explicitly out of scope (documented to prevent scope creep)

### 1.4 Document Scope Boundary
This FSD covers ONLY the June 15, 2026 demo. Post-demo features (crash
detection, haptic feedback, battery integration, mesh expansion) are
documented in §16 Future Scope but not specified here. When those features
are scheduled, this document is revised or a separate FSD is created.

---

## 2. Executive Summary

Pack Pucks is a screenless, peer-to-peer proximity tracking device for group
coordination in GPS-denied environments. Each "puck" is a self-contained
edge device that measures its distance to one or more peer pucks using
SX1280 Time-of-Flight (ToF) ranging at 2.4 GHz, and indicates that distance
via a passive LED colour code.

The demo system consists of two identical Pack Puck devices operating in
a paired configuration: one Initiator, one Responder. The Initiator
performs ranging continuously and displays the result on its LED ring.
The Responder passively replies to ranging requests.

No GPS. No smartphone. No cloud. No infrastructure. The system functions
identically in a Faraday cage, a tunnel, or an open field — wherever both
pucks are within radio range of each other.

---

## 3. System Overview

### 3.1 What the System Does
Each puck continuously measures its distance to its paired peer, in metres,
using radio signal time-of-flight. The measured distance is mapped to a
colour (green / amber / red) and displayed on a 16-LED ring on the device.
A user observing the LED ring can immediately gauge whether the paired
peer is close, drifting, or separated — without any screen, app, or
infrastructure.

### 3.2 Primary Use Case (Demo)
Two motorcyclists ride together. Each wears or mounts a puck. While riding
in formation, both see green. If they separate, the LED transitions through
amber to red. When they regroup, the LED returns to green. No looking at
phones, no GPS, no cellular.

### 3.3 Research Framing
The demo validates Contribution 1 of the preprint: GPS-denied relative
proximity detection using SX1280 ToF ranging is viable on mobile,
infrastructure-free, low-power edge hardware with passive on-device
feedback. The demo also generates experimental data for ranging accuracy
characterisation in real-world (non-laboratory) conditions.

---

## 4. Stakeholders

| Stakeholder | Role | Concern |
|---|---|---|
| Ishaan | Builder, primary user | System must work for June 15 demo |

---

## 5. Glossary & Acronyms

| Term | Definition |
|---|---|
| **Puck** | One Pack Pucks device — a single physical unit |
| **Peer** | The other puck a given puck is paired with |
| **Initiator** | The puck that starts each ranging exchange and receives the distance result |
| **Responder** | The puck that passively replies to ranging requests |
| **ToF** | Time of Flight — measuring distance by radio signal travel time |
| **RSSI** | Received Signal Strength Indicator — radio signal strength in dBm |
| **SF** | Spreading Factor — LoRa modulation parameter |
| **BW** | Bandwidth — radio bandwidth in kHz |
| **LoRa** | Long Range — radio modulation scheme used by SX1280 |
| **LED ring** | 16-LED WS2812B circular array used for proximity display |
| **Ranging cycle** | One complete request-response exchange producing a distance reading |
| **GPIO** | General Purpose Input/Output pin |
| **SPI** | Serial Peripheral Interface — communication protocol |
| **MCU** | Microcontroller Unit |
| **BMS** | Battery Management System |
| **NFR** | Non-Functional Requirement |
| **PA** | Power Amplifier — SX1280 H658 variant (not used; we use Without PA H594) |

---

## 6. System Architecture

### 6.1 Architectural Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Pack Puck (Initiator)                 │
│                                                          │
│  ┌──────────────┐    SPI     ┌──────────────────────┐  │
│  │  ESP32-S3    │◄──────────►│  SX1280 (Internal)   │  │
│  │  (Arduino)   │            │  - Ranging Engine    │  │
│  │              │            │  - LoRa Modem        │  │
│  │              │            └──────────┬───────────┘  │
│  │              │                       │              │
│  │              │                  RF (2.4GHz)         │
│  │              │                       │              │
│  │              │ GPIO 38               │              │
│  │              ├──────────►┌──────────▼───────────┐  │
│  │              │  Data     │  SMA Antenna         │  │
│  │              │           └──────────────────────┘  │
│  │              │                                      │
│  │              │     ┌─────────────────────┐         │
│  │              ├────►│  WS2812B LED Ring   │         │
│  │              │     │  (16 LEDs, RGB)     │         │
│  │              │     └─────────────────────┘         │
│  └──────┬───────┘                                      │
│         │ USB-C                                        │
└─────────┼──────────────────────────────────────────────┘
          │
          ▼
       Laptop (Power + Serial Debug)


            ◄═══ RF (2.4 GHz LoRa Ranging) ═══►


┌─────────────────────────────────────────────────────────┐
│                    Pack Puck (Responder)                 │
│  (Identical hardware, different firmware role)           │
└─────────────────────────────────────────────────────────┘
```

### 6.2 Firmware Architecture
Single-threaded Arduino main loop. No FreeRTOS tasks for demo scope —
complexity not justified at this stage. Decision revisited if integration
shows blocking behaviour problems.

**Modules:**
- `radio.cpp` — Wraps RadioLib SX1280 ranging
- `led.cpp` — Wraps FastLED WS2812B control
- `pack_pucks.ino` — Main loop, mode logic, glue
- `display.cpp` — Wraps SSD1306 OLED output. Active only when `ENABLE_DISPLAY` 
  is defined. Data collection tool only — excluded from demo builds.
  OLED pins: SDA=17, SCL=18 (onboard, internal I2C bus).

### 6.3 Initiator vs Responder
The two pucks run different firmware variants. Hardware is identical.
Role is selected at compile time via a `#define` flag:

```cpp
#define ROLE_INITIATOR  // for Board 1
// #define ROLE_RESPONDER  // for Board 2
```

Runtime role-switching is **out of scope** (see `OUT-1`).

---

## 7. Hardware Architecture

### 7.1 Bill of Materials (per puck)
| Component | Part | Quantity |
|---|---|---|
| MCU + Radio | LILYGO T3-S3 V1.2 (ESP32-S3 + SX1280 Without PA) | 1 |
| LED Ring | WS2812B 16-LED NeoPixel ring | 1 |
| Decoupling Cap | Rubycon 1000µF 10V electrolytic | 1 |
| Antenna | SMA 2.4 GHz stubby (shipped with T3-S3) | 1 |
| Power | USB-C cable to laptop (demo); battery deferred | 1 |

### 7.2 Pin Map (T3-S3 V1.2)

**Radio — all internal, no user wiring:**

| Signal | GPIO |
|---|---|
| SX1280 MOSI | 6 |
| SX1280 MISO | 3 |
| SX1280 SCK | 5 |
| SX1280 CS | 7 |
| SX1280 BUSY | 36 |
| SX1280 DIO1 | 9 |
| SX1280 RESET | 8 |

**User-wired peripherals:**

| Signal | GPIO | Notes |
|---|---|---|
| WS2812B Data | 38 | Single data line |
| Onboard LED | 37 | Available for boot/status |

### 7.3 Power Architecture
For demo: USB-C from laptop powers both pucks. T3-S3 onboard regulators
provide 3.3V for logic and SX1280, and pass through 5V for WS2812B.
Battery operation is **out of scope** (`OUT-2`).

---

## 8. Functional Requirements (FR)

### 8.1 Boot & Initialisation

**FR-1.1** — On power-up, the puck shall initialise the SX1280 radio
within 3 seconds.

**FR-1.2** — On power-up, the puck shall initialise the WS2812B LED ring
within 1 second.

**FR-1.3** — During initialisation, the LED ring shall display solid blue
at 25% brightness to indicate boot state.

**FR-1.4** — If radio initialisation fails, the LED ring shall flash red
at 1 Hz indefinitely and the puck shall halt further execution.

**FR-1.5** — On successful initialisation, the puck shall print a boot
banner to Serial at 115200 baud containing: firmware version, board ID,
role (Initiator/Responder), and radio settings.

### 8.2 Ranging Loop (Initiator)

**FR-2.1** — The Initiator shall perform one ranging cycle every 500ms
(±50ms tolerance).

**FR-2.2** — Each ranging cycle shall use radio address `0x12345678`.

**FR-2.3** — Each ranging cycle shall produce one of three outcomes:
SUCCESS (distance reading), TIMEOUT (no response), or ERROR (radio fault).

**FR-2.4** — On SUCCESS, the puck shall record: timestamp, distance in
metres, and RSSI in dBm.

**FR-2.5** — On TIMEOUT, the puck shall increment a consecutive-failure
counter. The counter resets to zero on any SUCCESS.

**FR-2.6** — On ERROR, the puck shall log the error to Serial and attempt
to recover by re-initialising the radio. If recovery fails after 3
attempts, the puck shall enter the FAULT state (see `BR-1.4`).

### 8.3 Ranging Loop (Responder)

**FR-3.1** — The Responder shall continuously listen for ranging requests
matching address `0x12345678`.

**FR-3.2** — The Responder shall reply to valid ranging requests
automatically via the SX1280 ranging engine.

**FR-3.3** — On each successful response, the Responder shall log to
Serial: timestamp, RSSI of the request packet.

**FR-3.4** — The Responder's LED ring shall display solid cyan at 10%
brightness to indicate "Responder ready" — distinct from Initiator states.
This is purely a visual confirmation during development; in final
deployment Responder role is identical to Initiator.

### 8.4 Proximity Display (Initiator)

**FR-4.1** — On each SUCCESS ranging cycle, the Initiator shall update
the LED ring colour according to the mapping in `BR-2`.

**FR-4.2** — LED transitions shall complete within 100ms of the ranging
result being available.

**FR-4.3** — When consecutive-failure count reaches 3, the LED ring shall
display solid white at 25% brightness to indicate "peer lost."

**FR-4.4** — When a SUCCESS occurs after a "peer lost" state, the LED
ring shall return to the appropriate colour per `BR-2` on the next cycle.

### 8.5 Serial Logging

**FR-5.1** — All ranging results shall be logged to Serial in CSV format
on a single line (see `DR-1` for schema).

**FR-5.2** — Serial baud rate shall be 115200.

**FR-5.3** — Logging shall be non-blocking — Serial output must not delay
the ranging cycle.

---

## 9. Behavioural Specification (BR)

### 9.1 Puck State Machine (Initiator)

```
        ┌─────────┐
        │  BOOT   │
        └────┬────┘
             │ Init success
             ▼
        ┌─────────┐
   ┌───►│ RANGING │◄───┐
   │    └────┬────┘    │
   │         │         │
   │ Success │ Timeout │
   │  / cont.│         │
   │         ▼         │
   │    ┌─────────┐    │
   │    │  DISPLAY│    │ ≤2 consecutive
   │    └────┬────┘    │  timeouts
   │         │         │
   └─────────┴─────────┘
             │
             │ 3+ consecutive timeouts
             ▼
        ┌─────────┐
        │  PEER_  │  Re-enters RANGING
        │  LOST   │  on next cycle
        └────┬────┘
             │
             │ 3 consecutive init failures
             │ or hardware fault
             ▼
        ┌─────────┐
        │  FAULT  │  (terminal — requires reset)
        └─────────┘
```

**BR-1.1 (BOOT state):** Solid blue LED, 25% brightness. Lasts until
radio + LED init complete.

**BR-1.2 (RANGING state):** Active ranging cycle in progress. LED retains
previous colour.

**BR-1.3 (DISPLAY state):** LED updated to colour matching latest distance
per `BR-2`. Immediately transitions back to RANGING.

**BR-1.4 (PEER_LOST state):** Solid white LED at 25%. Continues attempting
ranging — exits state on next SUCCESS.

**BR-1.5 (FAULT state):** Flashing red LED at 1 Hz. Halts ranging. Recovery
requires power cycle.

### 9.2 Distance-to-Colour Mapping

**BR-2** — The Initiator shall map measured distance to LED colour as:

| Distance (metres) | Colour | RGB | Meaning |
|---|---|---|---|
| 0 ≤ d ≤ 50 | Green | (0, 255, 0) | In group |
| 50 < d ≤ 200 | Amber | (255, 191, 0) | Drifting |
| d > 200 | Red | (255, 0, 0) | Separated |
| Ranging failed (peer lost) | White | (255, 255, 255) | Unknown |
| Boot | Blue | (0, 0, 255) | Initialising |
| Fault | Red, flashing 1 Hz | (255, 0, 0) | Hardware error |

**BR-2.1** — All LEDs in the ring shall display the same colour
simultaneously. No per-LED variation in v1.

**BR-2.2** — Brightness shall be fixed at 25% (FastLED brightness 64) to
prevent eye strain at close range and to manage WS2812B current draw.

**BR-2.3** — Thresholds (50m, 200m) shall be defined as `#define`
constants for empirical tuning during demo prep.

### 9.3 Failure Recovery

**BR-3.1** — Transient radio errors (RadioLib returns non-zero status)
shall trigger one automatic radio re-init attempt. If re-init succeeds,
ranging resumes. If it fails 3 consecutive times, the puck enters FAULT.

**BR-3.2** — Loss of peer for >1.5 seconds (3 consecutive timeouts at
500ms cycle) shall trigger PEER_LOST state but not interrupt ranging.

**BR-3.3** — No automatic power-cycle or reset is performed by firmware.
Recovery from FAULT requires physical reset.

---

## 10. Interface Requirements (IR)

### 10.1 Hardware Interfaces

**IR-1.1 — USB-C** (T3-S3 onboard): 5V power input. USB CDC for serial
data over the same connector.

**IR-1.2 — SMA Antenna** (T3-S3 onboard): 50Ω impedance, 2.4 GHz band.
Antenna MUST be attached before any RF transmission per LILYGO
documentation warning.

**IR-1.3 — WS2812B Data Line** (GPIO 38 → ring DIN): Single-wire data
at WS2812B protocol timing. Cable length ≤ 30cm to minimise signal
integrity issues. 1000µF capacitor across ring power pins is mandatory.

### 10.2 Software Interfaces

**IR-2.1 — RadioLib** (Jan Gromeš): Used for all SX1280 access. Constructor:
`SX1280 radio = new Module(7, 9, 8, 36);` (CS, DIO1, RESET, BUSY).

**IR-2.2 — FastLED** (Daniel Garcia): Used for WS2812B control. Configured
for 16 LEDs on GPIO 38, RGB colour order.

**IR-2.3 — Arduino Serial** (built-in): 115200 baud, 8N1, USB CDC.

### 10.3 Radio Protocol

**IR-3.1** — Frequency: 2400.0 MHz  
**IR-3.2** — Modulation: LoRa  
**IR-3.3** — Bandwidth: 1600 kHz  
**IR-3.4** — Spreading Factor: 6  
**IR-3.5** — Coding Rate: 4/5 (RadioLib default)  
**IR-3.6** — Sync Address: 0x12345678 (32-bit, must match on both pucks)  
**IR-3.7** — Ranging Mode: SX1280 hardware ranging engine  
**IR-3.8** — Output Power: 12.5 dBm (Without PA maximum, RadioLib default)

These settings replicate the DTU/IEEE paper baseline for 0–400m operation,
enabling direct comparison of experimental results.

---

## 11. Data Requirements (DR)

### 11.1 Serial Log Format

**DR-1** — Initiator Serial output, per ranging cycle, shall be a single
CSV line:

```
<timestamp_ms>,<status>,<distance_m>,<rssi_dbm>,<state>
```

Where:
- `timestamp_ms`: uint32, milliseconds since boot
- `status`: string, one of {SUCCESS, TIMEOUT, ERROR}
- `distance_m`: float, metres (NaN if not SUCCESS)
- `rssi_dbm`: int, dBm (0 if not SUCCESS)
- `state`: string, one of {BOOT, RANGING, DISPLAY, PEER_LOST, FAULT}

Example:
```
12345,SUCCESS,12.34,-45,DISPLAY
12845,TIMEOUT,NaN,0,RANGING
13345,SUCCESS,15.12,-48,DISPLAY
```

**DR-2** — A separate header line shall be printed once at boot:
```
timestamp_ms,status,distance_m,rssi_dbm,state
```

This enables direct CSV ingestion by analysis tools without manual editing.

### 11.2 Experimental Data Capture

**DR-3** — Ranging experiments for the preprint shall be captured by
redirecting Serial output to a file (Arduino Serial Monitor → File, or
`screen` / `cu` / `pyserial` on the command line).

**DR-4** — Each experiment file shall include a header comment line
prefixed `#` with: experimental conditions (indoor/outdoor, time of day,
measured distance, weather), and the line shall be added manually.

---

## 12. Non-Functional Requirements (NFR)

### 12.1 Performance
**NFR-1** — Ranging update rate: 2 Hz minimum (500ms cycle).
**NFR-2** — LED response latency: ≤ 100ms from distance result to LED update.
**NFR-3** — Cold boot to first ranging result: ≤ 5 seconds.

### 12.2 Reliability
**NFR-4** — Continuous operation: ≥ 30 minutes without crash, hang, or
manual intervention. (Acceptance baseline for demo.)
**NFR-5** — Transient ranging failure recovery: automatic within 1 cycle
(500ms) on next SUCCESS.

### 12.3 Range
**NFR-6** — Demo range: 0–50m indoor, 0–400m outdoor (line of sight),
matching DTU/IEEE baseline operating envelope.

### 12.4 Accuracy
**NFR-7** — Distance accuracy: within ±20% of physical distance for d ≥ 5m
in line-of-sight conditions. (Tighter targets are research outputs, not
specification.)

### 12.5 Environmental
**NFR-8** — Operating temperature: 10°C to 40°C (indoor/outdoor Indian
conditions in May–June).
**NFR-9** — Indoor multipath tolerance: system shall produce distance
readings indoors with metallic walls/furniture present, though accuracy
may degrade beyond NFR-7 in these conditions. Degradation is documented,
not corrected.

### 12.6 Power
**NFR-10** — Demo power: USB-C 5V from laptop. Battery power is out of
scope for the June 15 demo.

---

## 13. Configuration Parameters

All tunable parameters shall be defined as `#define` constants in a single
configuration header (`config.h`). This enables empirical tuning without
hunting through firmware. Demo-time values:

```cpp
// === Firmware Identity ===
#define FW_VERSION         "1.0-demo"
#define BOARD_ID           1  // Set to 1 for Initiator, 2 for Responder

// === Role Selection ===
#define ROLE_INITIATOR
// #define ROLE_RESPONDER

// === Radio Settings (DTU/IEEE baseline) ===
#define RADIO_FREQUENCY    2400.0  // MHz
#define RADIO_BANDWIDTH    1600.0  // kHz
#define RADIO_SF           6       // Spreading Factor
#define RADIO_CR           5       // Coding Rate 4/5
#define RADIO_POWER        12      // dBm (max for Without PA)
#define RADIO_ADDRESS      0x12345678

// === Ranging Loop ===
#define RANGING_INTERVAL_MS         500
#define RANGING_TIMEOUT_MS          200
#define MAX_CONSECUTIVE_TIMEOUTS    3
#define MAX_INIT_RETRIES            3

// === LED Mapping ===
#define LED_PIN              38
#define LED_COUNT            16
#define LED_BRIGHTNESS       64    // 0-255 (25%)
#define DIST_GREEN_THRESH    50.0  // metres
#define DIST_AMBER_THRESH    200.0 // metres
```

---

## 14. Error Handling & Edge Cases

### 14.1 Documented Edge Cases

| Case | System Behaviour |
|---|---|
| Antenna disconnected at boot | Radio init may still succeed; first TX attempt may damage SX1280. **Hardware-level user error — firmware cannot detect.** Documented in user instructions. |
| Antenna disconnected at runtime | Same as above; firmware cannot detect. |
| Responder powered off mid-session | Initiator sees consecutive timeouts → PEER_LOST state (white LED). Auto-recovers when Responder returns. |
| Both pucks configured as Initiator | No ranging exchanges occur. Both display PEER_LOST. Firmware does not detect this case — it is a build/config error. |
| Both pucks configured as Responder | Same — no exchanges. Both LEDs remain in boot/idle state. |
| Radio packet collision with WiFi | RSSI may be degraded; ranging may timeout. System recovers on next cycle. **Not specified to be robust against active WiFi interference for demo.** |
| Distance > radio range (~500m) | Consecutive timeouts → PEER_LOST. |
| Very close range (< 1m) | Ranging may return values close to zero or small negative. Negative values shall be clamped to 0 in firmware (`FR-4.5` implied — see code). |
| Battery connected without BMS | **Hardware damage risk.** Firmware does not detect. Out of scope per `NFR-10` and battery warning in State.md. |

### 14.2 Explicitly Not Handled

The system does **not** handle:
- Tampering or attacker-injected ranging frames (no authentication)
- Long-term clock drift across pucks (irrelevant for demo timescale)
- Power-fail mid-operation (no persistence; recovery is reboot)
- More than two pucks (see `OUT-3`)

---

## 15. Acceptance Criteria (AC)

The June 15, 2026 demo shall be considered SUCCESSFUL if and only if all
of the following are demonstrably true:

**AC-1** — Both pucks boot to operational state (RANGING) within 5 seconds
of USB-C connection.

**AC-2** — Initiator displays correct LED colour per `BR-2` at three
demonstration distances: < 5m (green), ~75m (amber), > 250m (red).
Tolerance: colour transitions occur within ±20% of the threshold distance.

**AC-3** — System runs continuously for 30 minutes without hang, crash,
LED freeze, or unexplained colour change. Transient timeouts are
acceptable provided recovery is automatic within 2 seconds.

**AC-4** — Serial output captures ≥ 95% of ranging cycles in CSV format
during the 30-minute test (≥ 3,420 lines for 30 min × 2 Hz × 95%).

**AC-5** — A demo video records the full colour progression
(green → amber → red → amber → green) with both pucks visible. Recorded
outdoors if possible; indoor acceptable if 100m of clear space is
unavailable.

**AC-6** — Methodology document (`docs/methodology.md`) is complete and
references this FSD by ID for each system characteristic.

**AC-7** — Raw experimental data files exist in
`data/ranging_experiments/` for ≥ 5 distinct distances (1m, 5m, 25m, 100m,
200m minimum), each with ≥ 20 readings.

---

## 16. Future Scope (Post-Demo, Not Specified Here)

Documented to preserve project direction. **Not implemented for June 15.**

- **Crash detection** (Contribution 2): MPU6050-based three-phase signature
  (freefall → impact → static). Specified in a separate FSD when scheduled.
- **Haptic feedback**: ERM motor pulses on PEER_LOST or major state change.
- **Battery operation**: Requires BMS-protected battery and validated
  charge/discharge circuit.
- **Mesh expansion**: Support for 3+ pucks via time-multiplexed ranging.
- **Adaptive thresholds**: Distance thresholds adapt to group velocity.
- **OLED debug display**: Implemented in Phase 4.5 as a data-collection tool
  only, gated by `#define ENABLE_DISPLAY`. Not part of demo scope.
- **Persistent logging**: Log to SPIFFS for offline experiments without
  laptop tether.
- **Power management**: Sleep modes between ranging cycles for battery life.

---

## 17. Explicitly Out of Scope (OUT)

These are documented to prevent scope creep and to make the demo boundary
unambiguous.

**OUT-1** — Runtime role-switching between Initiator and Responder.
Role is compile-time only.

**OUT-2** — Battery-powered operation. Demo runs on USB-C only.

**OUT-3** — Support for more than two pucks. Pair-only.

**OUT-4** — Encryption or authentication of ranging frames.

**OUT-5** — OTA firmware updates.

**OUT-6** — Smartphone companion app.

**OUT-7** — GPS integration of any kind.

**OUT-8** — Cellular, WiFi, or Bluetooth connectivity (WiFi/BT on
ESP32-S3 is unused and disabled in firmware).

**OUT-9** — Crash detection (deferred to Contribution 2 / Part 2 paper).

**OUT-10** — Production-grade enclosure or mechanical design. Bare boards
for demo.

---

## 18. Open Decisions

Items requiring resolution before or during firmware implementation:

**OD-1** — Should the 50m / 200m thresholds be revised after empirical
testing? Answer: yes, expected. Re-tune during demo prep. Document final
values in this FSD upon decision.

**OD-2** — Should WiFi/Bluetooth be explicitly disabled at boot to reduce
2.4 GHz self-interference? Answer: yes, add `WiFi.mode(WIFI_OFF);` and
`btStop();` at boot. Add to firmware as `FR-1.6`.

**OD-3** — Is 500ms ranging interval appropriate, or should it be faster
(e.g., 250ms) for smoother LED response? Answer: start at 500ms. Reduce
if LED feels laggy in demo testing.

**OD-4** — What does the Responder LED show? Per `FR-3.4` solid cyan, but
this is dev-time only. Consider making Responder LED mirror Initiator
behaviour by listening to ranging traffic. Deferred — not blocking.

---

## 19. References

### 19.1 Project Documents
- `FIRMWARE_PLAN.md` — Step-by-step firmware bring-up plan
- `Project Instructions` (Claude project) — Project-level conventions

### 19.2 External References
- LILYGO T3-S3 hardware documentation:
  https://github.com/Xinyuan-LilyGO/LilyGo-LoRa-Series
- Semtech SX1280 datasheet (Rev 3.2, July 2020)
- RadioLib documentation: https://github.com/jgromes/RadioLib
- DTU/IEEE: "Ranging Capabilities of LoRa 2.4 GHz" (baseline paper)
- arXiv 2509.08488 — SX1280 IoT localisation (related work, contrast)

### 19.3 Standards
- IEEE 802.15.4 — referenced for general 2.4 GHz coexistence considerations
  only; not implemented.

---

## 20. Document Change Log

| Version | Date | Changes |
|---|---|---|
| 1.0 | 13 May 2026 | Initial FSD for June 15 demo. |