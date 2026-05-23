# Pack Pucks — Functional Specification Document (FSD)

**Status:** Active. Living document for the June 15, 2026 demo and the Part 1 data campaign.
**Authoritative for:** System behaviour, requirements, interfaces, data formats, and acceptance criteria for the Part 1 deliverable.
**Audience:** Internal during development; public on Part 1 submission alongside `methodology.md`.
**Document Version:** 1.5
**Last Revised:** 23 May 2026
**Owner:** Ishaan

---

## 1. Document Purpose & Conventions

### 1.1 Purpose
This document defines the functional and non-functional requirements of the Pack Pucks system for the June 15, 2026 demo and the Part 1 arXiv preprint. It is the single source of truth for system behaviour. Firmware implementation references this document by requirement ID. `methodology.md` (the experimental protocol) references this document for system definition.

### 1.2 How to Read This Document
Every requirement has a stable identifier (e.g. `FR-3.2`, `NFR-1`). When firmware code implements a requirement, the code comment cites the ID. When `methodology.md` or the paper references system behaviour, it cites the ID. The system is traceable end-to-end — from spec to code to paper.

### 1.3 Requirement Identifier Scheme
- `FR-*` — Functional Requirement (what the system must do)
- `NFR-*` — Non-Functional Requirement (performance, reliability, etc.)
- `BR-*` — Behavioural Requirement (state-based behaviour)
- `IR-*` — Interface Requirement (hardware/software interfaces)
- `DR-*` — Data Requirement (logging, formats)
- `AC-*` — Acceptance Criterion (demo-ready definition)
- `OUT-*` — Explicitly out of scope (documented to prevent scope creep)

### 1.4 Document Scope Boundary
This FSD covers the June 15, 2026 demo and the data collection campaign for the Part 1 arXiv preprint. Post-Part-1 features (crash detection, haptic feedback, battery integration, mesh expansion) are documented in §16 (Future Scope) but not specified here. When those features are scheduled, this document is revised or a separate FSD is created.

### 1.5 Versioning
Each revision is committed to git with a change-log entry in §20. The running firmware/configuration used for any deployed dataset is the canonical source of truth for that dataset. When this document and the running firmware disagree, the contradiction must be resolved before the next data-collection session.

---

## 2. Executive Summary

Pack Pucks is a screenless, peer-to-peer proximity tracking device for group coordination in environments where GPS-based methods may be limited or unavailable. Each "puck" is a self-contained edge device that measures its distance to its paired peer puck using SX1280 Time-of-Flight (ToF) ranging at 2.4 GHz, and indicates that distance via a passive LED colour code.

The demo system consists of two identical Pack Pucks devices operating in a paired configuration: one Initiator, one Responder. The Initiator performs ranging continuously and displays the result on its LED ring. The Responder passively replies to ranging requests.

The system is GPS-independent by design: no GPS receiver, no cellular base station, no cloud service, no smartphone, and no fixed radio anchors are part of the deployed system. Whether the system operates correctly in any specific GPS-denied environment is an empirical question and is addressed by the data collection campaign, not claimed architecturally.

---

## 3. System Overview

### 3.1 What the System Does
Each puck continuously measures its distance to its paired peer, in metres, using radio signal time-of-flight. The measured distance is mapped to a colour (green / amber / red) and displayed on a 16-LED ring on the device. A user observing the LED ring can immediately gauge whether the paired peer is close, drifting, or separated — without any screen, app, or infrastructure.

### 3.2 Primary Use Case (Demo)
Two members of a small outdoor group — e.g., two hikers, two trekkers in a guided group, or two members of a convoy — are each associated with a puck. One puck operates as Initiator (the active device whose LED ring reflects proximity to its peer); the other operates as Responder (passive, displays the cyan ready-state per FR-3.4 and does not show distance). While the pair is together, the Initiator displays green. As they separate, it transitions through amber to red. When they regroup, it returns to green. No screens to check, no smartphone needed, no cellular signal required.

Part 1 evaluates Initiator-side proximity display only. A symmetric display (both pucks showing distance simultaneously) is achievable but is post-demo polish, not a Part 1 deliverable; see `open_decisions.md` `OD-FSD-4`.

Motorcyclists are a forward-looking application for the system. Motorcycle field testing under vibration and at vehicular speeds is deferred (see `OUT-11`); motorcyclists are not the primary evaluated use case in Part 1.

### 3.3 Research Framing
The demo and the accompanying data collection campaign support Contribution 1 of the Part 1 arXiv preprint: characterisation of SX1280 Time-of-Flight ranging in a mobile, peer-to-peer, infrastructure-free setting.

Published characterisations of SX1280 ToF ranging have primarily evaluated static, anchor-based, or infrastructure-supported configurations (Andersen et al. 2020; arXiv 2509.23125). To the best of our knowledge, there is limited published characterisation of low-cost SX1280 peer-to-peer proximity classification when one or both endpoints are mobile and no fixed ranging infrastructure is used. Pack Pucks addresses this gap.

**"Infrastructure-free"** in this context means no fixed radio anchors, GPS receivers, cellular base stations, cloud services, smartphones, or pre-deployed communication infrastructure are part of the deployed system. Experimental tools used only during measurement — tripods, cones, tape measures, laptops, distance markers — are not part of the deployed system and are permitted during data collection.

The system produces **categorical proximity feedback** (green / amber / red), not precise localisation: there is no coordinate output, no heading, and no fused position estimate. Filter behaviour, indoor multipath effects, and timeout/failure characteristics are reported as part of the characterisation; see `methodology.md` for the experimental protocol.

---

## 4. Stakeholders

| Stakeholder | Role | Concern |
|---|---|---|
| Ishaan | Builder, primary user | System must work for the June 15 demo and produce paper-grade data for Part 1 |

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
| **SPIFFS** | SPI Flash File System — on-chip filesystem used for on-device CSV logging |
| **MCU** | Microcontroller Unit |
| **BMS** | Battery Management System |
| **NFR** | Non-Functional Requirement |
| **PA** | Power Amplifier — SX1280 H658 variant (not used; we use H594 Without PA) |
| **eFuse MAC** | Hardware-burned unique identifier accessible via `ESP.getEfuseMac()`; serves as the per-puck Board ID |
| **Infrastructure-free** | No fixed radio anchors, GPS, cellular, cloud, smartphone, or pre-deployed communication infrastructure in the deployed system. Experimental measurement tools (tripods, cones, tape, laptops, distance markers) are permitted during data collection. |

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
│  │              │                                      │
│  │              │     ┌─────────────────────┐         │
│  │              ├────►│  SPIFFS (on-chip)   │         │
│  │              │     │  CSV log file       │         │
│  │              │     └─────────────────────┘         │
│  └──────┬───────┘                                      │
│         │ USB-C                                        │
└─────────┼──────────────────────────────────────────────┘
          │
          ▼
       Power source (laptop / USB power bank)
       + Serial for debug and post-session offload


            ◄═══ RF (2.4 GHz LoRa Ranging) ═══►


┌─────────────────────────────────────────────────────────┐
│                    Pack Puck (Responder)                 │
│  (Identical hardware, different firmware role)           │
└─────────────────────────────────────────────────────────┘
```

### 6.2 Firmware Architecture
Single-threaded Arduino main loop. No FreeRTOS tasks for demo scope — complexity not justified at this stage. Decision revisited if integration shows blocking behaviour problems.

**Modules:**
- `radio.cpp` — Wraps RadioLib SX1280 ranging
- `led.cpp` — Wraps FastLED WS2812B control
- `logger.cpp` — Wraps SPIFFS on-device CSV logging (per FR-5.4)
- `pack_pucks.ino` — Main loop, mode logic, glue
- `display.cpp` — Wraps SSD1306 OLED output. Active only when `ENABLE_DISPLAY` is defined. Data-collection tool only — excluded from demo builds. OLED pins: SDA=17, SCL=18 (onboard internal I2C bus).

### 6.3 Initiator vs Responder
The two pucks run different firmware variants. Hardware is identical. Role is selected at compile time via a `#define` flag:

```cpp
#define ROLE_INITIATOR  // for Board A
// #define ROLE_RESPONDER  // for Board B
```

Runtime role-switching is **out of scope** (see `OUT-1`).

---

## 7. Hardware Architecture

### 7.1 Bill of Materials (per puck)
| Component | Part | Quantity |
|---|---|---|
| MCU + Radio | LILYGO T3-S3 V1.2 (ESP32-S3 + SX1280 Without PA, variant H594) | 1 |
| LED Ring | WS2812B 16-LED NeoPixel ring | 1 |
| Decoupling Cap | Rubycon 1000µF 10V electrolytic | 1 |
| Antenna | SMA 2.4 GHz stubby (shipped with T3-S3) | 1 |
| Enclosure | 3D-printed case + tripod-mount adapter | 1 |
| Power | USB-C cable to laptop or USB power bank | 1 |

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
| OLED SDA / SCL | 17 / 18 | Onboard SSD1306; data-collection builds only |

### 7.3 Power Architecture
All Part 1 operation (demo + paper data collection) uses USB-C power: laptop USB, USB-C wall adapter, or USB-C power bank. The T3-S3 onboard regulators provide 3.3V for logic and SX1280, and pass through 5V for WS2812B.

Battery operation is **out of scope** for Part 1 (see `NFR-10`, `OUT-2`).

---

## 8. Functional Requirements (FR)

### 8.1 Boot & Initialisation

**FR-1.1** — On power-up, the puck shall initialise the SX1280 radio within 3 seconds.

**FR-1.2** — On power-up, the puck shall initialise the WS2812B LED ring within 1 second.

**FR-1.3** — During initialisation, the LED ring shall display solid blue at 25% brightness to indicate boot state.

**FR-1.4** — If radio initialisation fails, the LED ring shall flash red at 1 Hz indefinitely and the puck shall enter the FAULT state (`BR-1.5`).

**FR-1.5** — On successful initialisation, the puck shall print a boot banner to Serial at 115200 baud containing, at minimum: firmware version, board ID (from `ESP.getEfuseMac()`), role (Initiator/Responder), CSV schema version (per DR-3), radio settings, RF-state flags per FR-1.6, the mode-select window duration (`MODE_SELECT_WINDOW_MS`), the SPIFFS log filename (or `<none>` in OFFLOAD mode), and the resolved boot mode (`MODE: OFFLOAD` or `MODE: NORMAL`) per FR-5.7.

**FR-1.6** — On boot, *before* SX1280 initialisation, the puck shall disable WiFi by calling `WiFi.mode(WIFI_OFF)` and Bluetooth by calling `btStop()`. The boot banner shall include `WIFI_OFF=<0|1>` and `BT_OFF=<0|1>` reflecting the success of those API calls. If either API call reports failure, the corresponding flag shall be `0` and the puck shall enter the FAULT state (`BR-1.5`). This requirement supports the 2.4 GHz interference discipline of the Part 1 data collection campaign.

### 8.2 Ranging Loop (Initiator)

**FR-2.1** — The Initiator shall perform one ranging cycle every 500 ms (±50 ms tolerance).

**FR-2.2** — Each ranging cycle shall use radio address `0x12345678`.

**FR-2.3** — Each ranging cycle shall produce one of three outcomes: SUCCESS (distance reading), TIMEOUT (no response), or ERROR (radio fault).

**FR-2.4** — On SUCCESS, the puck shall record: sequence number, timestamp, distance in metres, RSSI in dBm, and the RadioLib status code.

**FR-2.5** — On TIMEOUT, the puck shall increment a consecutive-failure counter. The counter resets to zero on any SUCCESS.

**FR-2.6** — On ERROR, the puck shall log the error to Serial and SPIFFS and attempt to recover by re-initialising the radio. If recovery fails after 3 consecutive attempts, the puck shall enter FAULT (`BR-1.5`).

### 8.3 Ranging Loop (Responder)

**FR-3.1** — The Responder shall continuously listen for ranging requests matching address `0x12345678`.

**FR-3.2** — The Responder shall reply to valid ranging requests automatically via the SX1280 ranging engine.

**FR-3.3** — On each successful response, the Responder shall log to Serial and SPIFFS: sequence number, timestamp, event tag (`RANGING_REQ`), RSSI of the incoming request packet, state, and RadioLib status code.

**FR-3.4** — The Responder's LED ring shall display solid cyan at 10% brightness to indicate "Responder ready." This is a development-time visual confirmation; behaviour may be revised post-demo (see `open_decisions.md` `OD-FSD-4`).

### 8.4 Proximity Display (Initiator)

**FR-4.1** — On each SUCCESS ranging cycle, the Initiator shall update the LED ring colour according to the mapping in `BR-2`.

**FR-4.2** — LED transitions shall complete within 100 ms of the ranging result being available.

**FR-4.3** — When the consecutive-failure count reaches 3, the LED ring shall display solid white at 25% brightness to indicate "peer lost."

**FR-4.4** — When a SUCCESS occurs after a "peer lost" state, the LED ring shall return to the appropriate colour per `BR-2` on the next cycle.

**FR-4.5** — Distance values used for LED colour mapping shall be clamped to ≥ 0 (negative raw distances are mapped as if 0). This clamping applies only to colour-mapping logic; the logged CSV value (`raw_distance_m`, per DR-1) is never clamped.

### 8.5 Logging

**FR-5.1** — All ranging results (Initiator and Responder) shall be logged to Serial in CSV format on a single line per cycle/event (see DR-1, DR-2 for schemas).

**FR-5.2** — Serial baud rate shall be 115200.

**FR-5.3** — Serial logging shall be non-blocking — Serial output must not delay the ranging cycle.

**FR-5.4** — The puck shall additionally log to on-device SPIFFS storage in CSV format. One file per boot. Append per ranging cycle. The file shall be flushed every 10 ranging cycles (≈ 5 seconds at 2 Hz) to bound data loss on unexpected power-off.

**FR-5.5** — On boot, the firmware shall scan SPIFFS for existing `pucklog_*` files and open the next available index. Filename: `pucklog_<board_id_short>_<boot_seq>.csv`, where `<board_id_short>` is a short form of the eFuse MAC and `<boot_seq>` is a monotonically increasing per-boot counter.

**FR-5.6** — USB Serial commands shall provide SPIFFS access from a connected laptop: `LIST` (enumerate all files; output framed with `---BEGIN LIST---` / `---END LIST---` markers, one `<filename> <size_bytes>` entry per line), `DUMP <filename>` (stream file byte-exact, framed with `---BEGIN <filename>---` / `---END <filename>---`), `DELETE <filename>`, and `FORMAT`. The framed LIST and DUMP output is consumed by the automated offload script (`tools/offload/offload.py`).

**FR-5.7** — At each boot, after printing the boot banner header lines and before opening a new pucklog file, the firmware shall open a mode-select window of `MODE_SELECT_WINDOW_MS` milliseconds. If the exact string `OFFLOAD` (terminated with `\n`) is received during the window, the puck shall boot into **OFFLOAD mode**: no pucklog file is opened, no CSV headers are written, the ranging loop is not entered, and the main loop services only the FR-5.6 Serial commands. Otherwise the puck boots into **NORMAL mode** (existing behaviour). The FR-1.6 WiFi/BT fault check shall occur before the window opens — a faulty puck must not wait for OFFLOAD.

---

## 9. Behavioural Specification (BR)

### 9.1 Puck State Machine (Initiator)

```
        ┌─────────┐
        │  BOOT   │
        └────┬────┘
             │ Init success (radio + WiFi/BT off OK)
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
             │ 3 consecutive init failures,
             │ WiFi/BT API failure,
             │ or hardware fault
             ▼
        ┌─────────┐
        │  FAULT  │  (terminal — requires reset)
        └─────────┘
```

**BR-1.1 (BOOT state):** Solid blue LED, 25% brightness. Lasts until radio + LED init complete and WiFi/BT off API calls succeed.

**BR-1.2 (RANGING state):** Active ranging cycle in progress. LED retains previous colour.

**BR-1.3 (DISPLAY state):** LED updated to colour matching latest distance per `BR-2`. Immediately transitions back to RANGING.

**BR-1.4 (PEER_LOST state):** Solid white LED at 25%. Continues attempting ranging — exits state on next SUCCESS.

**BR-1.5 (FAULT state):** Flashing red LED at 1 Hz. Halts ranging. Recovery requires power cycle. Triggers: SX1280 init failure (per `BR-3.1`), WiFi/BT API failure (per `FR-1.6`), or unrecoverable runtime error.

### 9.2 Distance-to-Colour Mapping

**BR-2** — The Initiator shall map measured distance (after clamping per FR-4.5) to LED colour as:

| Distance (metres) | Colour | RGB | Meaning |
|---|---|---|---|
| 0 ≤ d ≤ 50 | Green | (0, 255, 0) | In group |
| 50 < d ≤ 200 | Amber | (255, 191, 0) | Drifting |
| d > 200 | Red | (255, 0, 0) | Separated |
| Ranging failed (peer lost) | White | (255, 255, 255) | Unknown |
| Boot | Blue | (0, 0, 255) | Initialising |
| Fault | Red, flashing 1 Hz | (255, 0, 0) | Hardware error |

**BR-2.1** — All LEDs in the ring shall display the same colour simultaneously. No per-LED variation in v1.

**BR-2.2** — Brightness shall be fixed at 25% (FastLED brightness 64) to prevent eye strain at close range and to manage WS2812B current draw.

**BR-2.3** — Thresholds (50 m, 200 m) are demo-tunable per `open_decisions.md` `OD-FSD-1` and are not research claims.

### 9.3 Failure Recovery

**BR-3.1** — Transient radio errors (RadioLib returns non-zero status) shall trigger one automatic radio re-init attempt. If re-init succeeds, ranging resumes. If it fails 3 consecutive times, the puck enters FAULT.

**BR-3.2** — Loss of peer for >1.5 seconds (3 consecutive timeouts at 500 ms cycle) shall trigger PEER_LOST state but not interrupt ranging.

**BR-3.3** — No automatic power-cycle or reset is performed by firmware. Recovery from FAULT requires physical reset.

---

## 10. Interface Requirements (IR)

### 10.1 Hardware Interfaces

**IR-1.1 — USB-C** (T3-S3 onboard): 5V power input. USB CDC for serial data over the same connector.

**IR-1.2 — SMA Antenna** (T3-S3 onboard): 50Ω impedance, 2.4 GHz band. Antenna **must** be attached before any RF transmission per LILYGO documentation warning.

**IR-1.3 — WS2812B Data Line** (GPIO 38 → ring DIN): Single-wire data at WS2812B protocol timing. Cable length ≤ 30 cm to minimise signal integrity issues. 1000 µF capacitor across ring power pins is mandatory.

### 10.2 Software Interfaces

**IR-2.1 — RadioLib** (Jan Gromeš): Used for all SX1280 access. Constructor:
`SX1280 radio = new Module(7, 9, 8, 36);` (CS, DIO1, RESET, BUSY).

**IR-2.2 — FastLED** (Daniel Garcia): Used for WS2812B control. Configured for 16 LEDs on GPIO 38, RGB colour order.

**IR-2.3 — SPIFFS** (Arduino-ESP32 built-in): Used for on-device CSV logging per FR-5.4. Partition: 1.5 MB (default 4 MB partition scheme).

**IR-2.4 — Arduino Serial** (built-in): 115200 baud, 8N1, USB CDC.

### 10.3 Radio Protocol

**IR-3.1** — Frequency: 2400.0 MHz  
**IR-3.2** — Modulation: LoRa  
**IR-3.3** — Bandwidth: **1625 kHz** (the SX1280 register-level value; Semtech documentation labels this setting as "1600 kHz"). The hardware value is derived from the SX1280's 52 MHz crystal: 52 / 32 = 1.625 MHz. Both labels refer to the same setting.  
**IR-3.4** — Spreading Factor: 6  
**IR-3.5** — Coding Rate: 4/7 — RadioLib SX128x begin() passes cr=7 by default; setCodingRate maps this to register 0x03 (RADIOLIB_SX128X_LORA_CR_4_7). Confirmed against RadioLib 7.6.0 source.  
**IR-3.6** — Sync Address: 0x12345678 (32-bit, must match on both pucks)  
**IR-3.7** — Ranging Mode: SX1280 hardware ranging engine  
**IR-3.8** — Output Power: 12 dBm (firmware configuration). The H594 variant's hardware maximum is approximately 12.5 dBm; the firmware uses 12 dBm as a slightly conservative setting compatible with RadioLib defaults.

These settings replicate the Andersen et al. (2020) baseline for 0–400 m operation, enabling direct comparison of experimental results.

---

## 11. Data Requirements (DR)

### 11.1 Initiator CSV (DR-1)

**DR-1** — Initiator output, per ranging cycle, shall be a single CSV line:

```
<seq>,<timestamp_ms>,<status>,<raw_distance_m>,<rssi_dbm>,<state>,<consecutive_failures>,<radio_status_code>
```

Where:
- `seq`: uint32, monotonic counter from 1 on file open, +1 per ranging cycle.
- `timestamp_ms`: uint32, milliseconds since boot.
- `status`: string, one of `{SUCCESS, TIMEOUT, ERROR}`.
- `raw_distance_m`: float. On `SUCCESS`, this is the unmodified value returned by the RadioLib ranging API; negative values that occur at short range due to multipath are preserved as-is. On `TIMEOUT` or `ERROR`, this field is written as `NaN`. Any clamping is for display logic only (FR-4.5) and is never written back to the CSV.
- `rssi_dbm`: int, RSSI of the response packet. Written as `0` on TIMEOUT or ERROR (one convention, consistent across firmware versions).
- `state`: string, one of `{BOOT, RANGING, DISPLAY, PEER_LOST, FAULT}`.
- `consecutive_failures`: uint16, the firmware's internal counter per FR-2.5. Logged explicitly so analysis does not have to reconstruct it from `status`.
- `radio_status_code`: int16, RadioLib return code for the ranging operation (`0` = `RADIOLIB_ERR_NONE`; non-zero codes per RadioLib's `TypeDef.h`).

**DR-1.1** — Firmware-written header line at file open / boot:

```
# CSV_SCHEMA_V=<n>, FW=<fw_version>, BOARD_ID=<efuse_mac_hex>, ROLE=INITIATOR, BOOT_MS=0, FREQ=<mhz>, BW=<khz>, SF=<n>, CR=<n>, TXPOWER=<dbm>
seq,timestamp_ms,status,raw_distance_m,rssi_dbm,state,consecutive_failures,radio_status_code
```

Radio config fields (`FREQ`, `BW`, `SF`, `CR`, `TXPOWER`) are written from the firmware `#define` constants at compile time. Including them in the per-file header makes each CSV self-describing — if SPIFFS holds files from multiple firmware versions with different radio settings, the per-file header is authoritative for that file's radio config and the manifest or git history need not be consulted.

A second comment line (operator-completed metadata) is added at post-session offload per `methodology.md` §4.1. Schema:

```
# SITE=<site>, SESSION_ID=<session_id>, BOOT_UTC=<ISO8601>, RUN_ID=<run_id>, TRUE_DISTANCE_M=<value_or_NA>
```

`TRUE_DISTANCE_M` is the ground-truth distance for that run (laser-measured / cone-derived); `NA` for mobile tiers where a single true distance does not apply. `RUN_ID` is an operator-set identifier (e.g., `T1_100m_S1`) that makes each CSV self-identifying without depending on the filename. The operator-added line is not the firmware's concern — it is inserted at offload time by `tools/offload/offload.py`, which collects the values via interactive prompts and converts operator-entered IST timestamps to UTC.

### 11.2 Responder CSV (DR-2)

**DR-2** — Responder output, per ranging-related event, shall be a single CSV line:

```
<seq>,<timestamp_ms>,<event>,<rssi_dbm>,<state>,<radio_status_code>
```

Where:
- `seq`: uint32, monotonic counter from 1 on file open.
- `timestamp_ms`: uint32, ms since boot.
- `event`: string, one of `{BOOT, READY, RANGING_REQ, ERROR}`. `RANGING_REQ` is logged on each ranging request received from the Initiator.
- `rssi_dbm`: int, RSSI of the incoming request packet (Responder's perspective). Written as `0` for `BOOT`, `READY`, or `ERROR` events when no incoming packet is associated with the log line.
- `state`: string, one of `{BOOT, LISTENING, FAULT}`.
- `radio_status_code`: int16, RadioLib return code for the receive/reply operation.

**DR-2.1** — Firmware-written header line:

```
# CSV_SCHEMA_V=<n>, FW=<fw_version>, BOARD_ID=<efuse_mac_hex>, ROLE=RESPONDER, BOOT_MS=0, FREQ=<mhz>, BW=<khz>, SF=<n>, CR=<n>, TXPOWER=<dbm>
seq,timestamp_ms,event,rssi_dbm,state,radio_status_code
```

Same radio-config rationale as DR-1.1.

The Responder CSV is **diagnostic data**: it captures link quality from the Responder's side (request RSSI, error counts) but does not contain ranging distance values, which only the Initiator computes. See `methodology.md` §4.7.

### 11.3 Schema Versioning (DR-3)

**DR-3** — `CSV_SCHEMA_V` shall be incremented whenever any change is made to the column set or column semantics in DR-1 or DR-2. The schema version is recorded in the firmware-written header line. Analysis tools that parse Pack Pucks CSV data shall check `CSV_SCHEMA_V` for compatibility.

Current schema version: **1**.

### 11.4 Experimental Data Capture (DR-4)

**DR-4** — Detailed data-capture procedure for the Part 1 paper experiments — file naming, post-session metadata, environmental logging, ground-truth methodology, session structure — is specified in `methodology.md`. This FSD specifies what firmware emits; `methodology.md` specifies how it is used for paper-grade experiments. The two documents must remain consistent.

---

## 12. Non-Functional Requirements (NFR)

### 12.1 Performance
**NFR-1** — Ranging update rate: 2 Hz minimum (500 ms cycle).
**NFR-2** — LED response latency: ≤ 100 ms from distance result to LED update.
**NFR-3** — Cold boot to first ranging result: ≤ 5 seconds.

### 12.2 Reliability
**NFR-4** — Continuous operation: ≥ 30 minutes without crash, hang, or manual intervention. (Acceptance baseline for demo.)
**NFR-5** — Transient ranging failure recovery: automatic within 1 cycle (500 ms) on next SUCCESS.

### 12.3 Range
**NFR-6** — Demo range: 0–50 m indoor, 0–400 m outdoor (line of sight), matching the Andersen et al. baseline operating envelope.

### 12.4 Accuracy
**NFR-7** — Distance accuracy: characterisation reported quantitatively in the Part 1 preprint per the protocol in `methodology.md`. This FSD does not specify a single accuracy figure as a system-design target; accuracy is the research output, not a system spec.

### 12.5 Environmental
**NFR-8** — Operating temperature: 10°C to 40°C (typical Indian indoor/outdoor conditions in May–June).
**NFR-9** — Indoor multipath tolerance: system shall produce distance readings indoors with metallic walls/furniture present; accuracy degradation in such conditions is documented in the paper, not corrected by the system.

### 12.6 Power
**NFR-10** — All Part 1 operation (demo + paper data) uses USB-C power: laptop USB, USB-C wall adapter, or USB-C power bank. Battery operation is out of scope (see `OUT-2`).

---

## 13. Configuration Parameters

All tunable parameters shall be defined as `#define` constants in a single configuration header (`config.h`). Values at the time of this FSD revision:

```cpp
// === Firmware Identity ===
#define FW_VERSION         "0.7-offload-mode"
#define CSV_SCHEMA_V       1

// === Radio Settings (Andersen et al. baseline — FSD §10.3, locked) ===
// Single source for radio.begin(), the boot banner, and the per-CSV header.
#define RADIO_FREQ_MHZ     2400.0f // MHz (IR-3.2)
#define RADIO_BW_KHZ       1625.0f // kHz — Semtech labels this "1600 kHz" (IR-3.3)
#define RADIO_SF           6       // Spreading Factor (IR-3.4)
#define RADIO_CR           7       // CR 4/7; RadioLib cr=7 → register 0x03 (IR-3.5)
#define RADIO_TX_POWER_DBM 12      // dBm; H594 hardware max ≈ 12.5 dBm (IR-3.8)
#define RADIO_ADDRESS      0x12345678

// === Ranging Loop ===
#define RANGING_INTERVAL_MS         500
#define MAX_CONSECUTIVE_FAILURES    3

// === Offload Boot Mode ===
#define MODE_SELECT_WINDOW_MS       3000 // ms to type "OFFLOAD" at boot (FR-5.7)

// === LED Mapping (demo defaults; not research claims) ===
#define LED_PIN              38
#define LED_COUNT            16
#define LED_BRIGHTNESS       64    // 0–255 (25%)
#define DIST_GREEN_THRESH    50.0  // metres
#define DIST_AMBER_THRESH    200.0 // metres

// === Logging ===
#define SPIFFS_FLUSH_EVERY   10    // flush every N ranging cycles ≈ 5 s (FR-5.4)
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
| WiFi or Bluetooth API call fails at boot | Boot banner reports `WIFI_OFF=0` or `BT_OFF=0`. Puck enters FAULT per FR-1.6. Session cannot proceed. |
| Distance > radio range (~500 m) | Consecutive timeouts → PEER_LOST. |
| Very close range (< 1 m) | RadioLib may return negative or near-zero values due to multipath. Negative values are written as-is to the CSV (DR-1.2); LED colour mapping clamps to 0 (FR-4.5). |
| Battery connected without BMS | **Hardware damage risk.** Firmware does not detect. Battery operation is out of scope (`NFR-10`, `OUT-2`). |
| SPIFFS full | Logging halts; Serial logging continues. Operator should offload and clear SPIFFS between sessions. Not expected for any single-session Part 1 dataset (≤ 720 KB per worst-case session). |

### 14.2 Explicitly Not Handled

The system does **not** handle:
- Tampering or attacker-injected ranging frames (no authentication)
- Long-term clock drift across pucks (irrelevant for demo timescale)
- Power-fail mid-operation (no persistence beyond SPIFFS; recovery is reboot)
- More than two pucks (see `OUT-3`)

---

## 15. Acceptance Criteria (AC)

The June 15, 2026 demo shall be considered SUCCESSFUL if and only if all of the following are demonstrably true:

**AC-1** — Both pucks boot to operational state (RANGING) within 5 seconds of USB-C connection.

**AC-2** — Initiator displays correct LED colour per `BR-2` at three demonstration distances: < 5 m (green), ~75 m (amber), > 250 m (red). Tolerance: colour transitions occur within ±20% of the threshold distance.

**AC-3** — System runs continuously for 30 minutes without hang, crash, LED freeze, or unexplained colour change. Transient timeouts are acceptable provided recovery is automatic within 2 seconds.

**AC-4** — Serial *and* SPIFFS output capture ≥ 95% of ranging cycles in CSV format during the 30-minute test (≥ 3,420 lines for 30 min × 2 Hz × 95%). The two streams must agree (modulo flush timing).

**AC-5** — A demo video records the full colour progression (green → amber → red → amber → green) with both pucks visible. Recorded outdoors where space permits.

**AC-6** — `methodology.md` is complete and references this FSD by ID for each relevant system characteristic.

**AC-7** — Raw experimental data files exist in `data/ranging_experiments/` for ≥ 5 distinct distances per tier, each with ≥ 20 readings (with the full paper-grade campaign per `methodology.md` proceeding in parallel).

---

## 16. Future Scope (Post-Part-1)

Documented to preserve project direction. **Not implemented for June 15 or for the Part 1 paper.**

- **Crash detection** (Contribution 2): IMU-based three-phase signature (freefall → impact → static). Specified in a separate FSD when scheduled.
- **Haptic feedback**: ERM motor pulses on PEER_LOST or major state change.
- **Battery operation**: Requires BMS-protected battery and validated charge/discharge circuit. Pro-Range ICR cells (without integrated BMS) cannot be directly connected to the T3-S3. Part 2 / engineering future-work item.
- **Mesh expansion**: Support for 3+ pucks via time-multiplexed ranging.
- **Adaptive thresholds** (Contribution 3): Distance thresholds adapt to estimated group velocity.
- **OLED debug display**: Already implemented as a data-collection tool, gated by `#define ENABLE_DISPLAY`. Not part of demo scope.
- **Power management**: Sleep modes between ranging cycles for battery life.
- **Bike-mounted GPS-vs-Puck comparison**: Out of scope for Part 1 (`OUT-11`); candidate Part 2 experiment.

---

## 17. Explicitly Out of Scope (OUT)

Documented to prevent scope creep and to make the Part 1 boundary unambiguous.

**OUT-1** — Runtime role-switching between Initiator and Responder. Role is compile-time only.

**OUT-2** — Battery-powered operation. All Part 1 operation uses USB-C power.

**OUT-3** — Support for more than two pucks. Pair-only.

**OUT-4** — Encryption or authentication of ranging frames.

**OUT-5** — OTA firmware updates.

**OUT-6** — Smartphone companion app.

**OUT-7** — GPS integration of any kind. (Phones may carry GPS Loggers during the GPS-vs-Puck comparison sub-study, but GPS is never a system input.)

**OUT-8** — Cellular, WiFi, or Bluetooth connectivity. ESP32-S3's WiFi/BT are explicitly disabled at boot (FR-1.6).

**OUT-9** — Crash detection (deferred to Contribution 2 / Part 2 paper).

**OUT-10** — Production-grade enclosure or mechanical design. 3D-printed cases for demo and data collection.

**OUT-11** — Motorcycle field testing under vibration or at vehicular speeds. SX1280 ranging has not been independently characterised under such conditions; testing is deferred to Part 2.

---

## 18. Open Decisions

Open decisions are tracked centrally in `open_decisions.md`. Currently open items affecting this FSD: `OD-FSD-1` (50 m / 200 m thresholds), `OD-FSD-3` (500 ms ranging interval), `OD-FSD-4` (Responder LED behaviour). See `open_decisions.md` for current state and triggers.

---

## 19. References

### 19.1 Project Documents
- `methodology.md` — Experimental protocol for Part 1 data collection
- `open_decisions.md` — Central tracker of unresolved decisions
- `research_strategy.md` — Publication plan, contribution scope, novelty positioning (internal)
- `guardrails.md` — Project-internal rules on claims and rigour (internal)
- `FIRMWARE_PLAN.md` — Step-by-step firmware bring-up plan
- `State.md` — Current project status snapshot

Internal-only files (`research_strategy.md`, `guardrails.md`, `open_decisions.md`, `State.md`, `FIRMWARE_PLAN.md`) will be referenced only in the internal version of this FSD; the public Part 1 release strips internal cross-references.

### 19.2 External References
- LILYGO T3-S3 hardware documentation: <https://github.com/Xinyuan-LilyGO/LilyGo-LoRa-Series>
- Semtech SX1280 datasheet (Rev 3.2, July 2020)
- RadioLib documentation: <https://github.com/jgromes/RadioLib>
- Andersen et al. (2020), "Ranging Capabilities of LoRa 2.4 GHz" (DTU / IEEE) — baseline
- arXiv 2509.08488 — SX1280 IoT localisation (related work, contrast)
- arXiv 2509.23125 — Environmental factors in SX1280 ToF ranging (related work)

### 19.3 Standards
- IEEE 802.15.4 — referenced for general 2.4 GHz coexistence considerations only; not implemented.

---

## 20. Document Change Log

| Version | Date | Changes |
|---|---|---|
| 1.0 | 13 May 2026 | Initial FSD for June 15 demo. |
| 1.1 | 15 May 2026 | Cleanup pass against project guardrails and methodology. **§2** Removed the technically-incorrect Faraday-cage claim. **§2, §3.2** Reframed primary use case around outdoor group coordination (hiking/trekking/convoy); motorcyclists noted as forward-looking application only. **§3.3** Softened novelty claim per project novelty discipline; removed unhedged "no prior work" framing; added explicit definition of "infrastructure-free"; explicit statement that the system produces categorical proximity feedback, not localisation. **§5** Added glossary entries for SPIFFS, eFuse MAC, Infrastructure-free. **§6.2** Added `logger.cpp` module reflecting SPIFFS logging. **§6.1** Architectural diagram updated to show SPIFFS storage. **§8.1** Added **FR-1.6** promoting WiFi/BT-off-at-boot from prior OD-2 to a Functional Requirement, with boot-banner self-verification. Updated FR-1.5 to include board ID (from eFuse MAC) and CSV schema version. **§8.5** Expanded with FR-5.4, FR-5.5, FR-5.6 covering SPIFFS on-device CSV logging with flush cadence and download command. **§8.4** Added FR-4.5 making explicit that negative-distance clamping applies only to LED colour mapping. **§9.1, §9.3** Updated BR-1.5 (FAULT state) to include WiFi/BT API failure as a trigger; clarified BOOT-to-RANGING transition includes the WiFi/BT-off check. **§9.2** BR-2.3 reframed: thresholds are demo-tunable, not research claims (cross-references `OD-FSD-1`). **§10.2** Added IR-2.3 covering SPIFFS interface. **§10.3** Corrected IR-3.3 bandwidth: 1625 kHz (Semtech labels this setting as "1600 kHz"); both refer to the same hardware setting. **§11** Major revision: DR-1 updated to expanded Initiator schema (`seq, timestamp_ms, status, raw_distance_m, rssi_dbm, state, consecutive_failures, radio_status_code`) with `raw_distance_m` semantics; DR-2 added for Responder CSV; DR-3 added for schema versioning; DR-4 added pointing to `methodology.md` for full data-capture procedure. **§13** RADIO_BANDWIDTH corrected to 1625.0 kHz; added CSV_SCHEMA_V, BOARD identifiers, SPIFFS_FLUSH_EVERY_CYCLES. **§14** Battery row updated; SPIFFS-full row added; WiFi/BT API failure row added. **§15** AC-4 extended to require Serial and SPIFFS streams to agree; AC-5 motorcycle reference removed; AC-7 cross-referenced to `methodology.md` for full paper-grade campaign. **§16** Battery clarified as Part 2 work; Pro-Range cells noted; bike-mounted GPS comparison added. **§17** OUT-2 (battery) clarified; OUT-8 (cellular/WiFi/BT) updated to reference FR-1.6; OUT-11 added (motorcycle field testing). **§18** Reduced to a pointer; OD-1..OD-4 renamed `OD-FSD-1..OD-FSD-4` in `open_decisions.md`. **§19** Added project document references; noted public-release cross-reference handling. **Top of document:** Added metadata block (Status, Authoritative for, Audience, Version, Last Revised, Owner) following project file convention. **§1.5** Added Versioning subsection. |
| 1.2 | 15 May 2026 | Targeted clarifications. **§2** "one or more peer pucks" → "paired peer" — scopes the system description to the pair-only Part 1 deployment (OUT-3). **§3.2** Corrected LED display description: only the Initiator displays proximity colours; Responder is passive with cyan ready state (FR-3.4). Symmetric display noted as post-demo polish (`OD-FSD-4`). **DR-1** `raw_distance_m` clarified: RadioLib raw value on SUCCESS (negatives preserved); `NaN` on TIMEOUT/ERROR. **DR-2** `rssi_dbm` clarified: `0` for BOOT/READY/ERROR events when no incoming packet is associated. **DR-1.1** Operator metadata line schema updated: `RUN_DISTANCE_M` renamed to `TRUE_DISTANCE_M` for clarity (the field holds ground truth, not the firmware's measurement); `RUN_ID` added so each CSV is self-identifying without depending on the filename. Mobile-tier values are `NA`. **FR-5.5** SPIFFS filename pattern standardised to `pucklog_<board_id_short>_<boot_seq>.csv` (matching `methodology.md` on `<boot_seq>`). **IR-3.8 + §13** RADIO_POWER clarified: firmware configures 12 dBm; H594 hardware maximum is approximately 12.5 dBm; the 12 dBm setting is slightly conservative.<br><br>**Cross-file note:** This version creates two minor divergences with `methodology.md` (§4.1 operator metadata schema; §4.4 filename pattern using `<board_id>` instead of `<board_id_short>`). Methodology to be aligned in its next pass; FSD is the upstream specification for both fields. |
| 1.3 | 21 May 2026 | Firmware-alignment correction following the `v0.6-radio-config` tag on `main`. **§10.3 IR-3.5** Coding rate corrected from "4/5 (RadioLib default)" to **4/7** — RadioLib SX128x `begin()` passes `cr=7` by default; `setCodingRate(7)` maps to register `0x03` (`RADIOLIB_SX128X_LORA_CR_4_7`). Confirmed against RadioLib 7.6.0 source. The prior "4/5 default" assumption was incorrect for the SX128x driver (it is correct for SX127x). **§13 Configuration Parameters** `RADIO_CR` example updated from `5 // Coding Rate 4/5` to `7 // Coding Rate 4/7 (RadioLib SX128x default; see IR-3.5)` to match. No other normative requirements changed; this revision aligns the spec with what the firmware has always set on the wire. |
| 1.4 | 22 May 2026 | v0.7-offload-mode firmware alignment. **§8.1 FR-1.5** Boot banner now includes `MODE_SELECT_WINDOW_MS` and resolved `MODE:` line. **§8.5** `FR-5.6` rewritten: LIST output is now framed (`---BEGIN LIST---` / `---END LIST---`, one `<filename> <size_bytes>` per line) for machine consumption by `tools/offload/offload.py`; DUMP framing unchanged. **FR-5.7** added: OFFLOAD boot mode — 3 s mode-select window at boot; exact-match `OFFLOAD\n` triggers OFFLOAD mode (no log file opened, no ranging, Serial commands only); otherwise NORMAL mode. WiFi/BT fault check precedes the window. **§11.1 DR-1.1** and **§11.2 DR-2.1** firmware-written header line updated to include radio config fields (`FREQ`, `BW`, `SF`, `CR`, `TXPOWER`) — each CSV is now self-describing across firmware versions. **§13** `FW_VERSION` updated to `0.7-offload-mode`; radio `#define` names aligned to actual firmware constants (`RADIO_FREQ_MHZ`, `RADIO_BW_KHZ`, `RADIO_TX_POWER_DBM`); `MODE_SELECT_WINDOW_MS` added; stale `RANGING_TIMEOUT_MS` / `MAX_INIT_RETRIES` / `SPIFFS_FLUSH_EVERY_CYCLES` removed. |
| 1.5 | 23 May 2026 | No normative requirements changed; this revision documents post-tag refinements to `tools/offload/offload.py` that re-anchor the `v0.7-offload-mode` tag. **§11.1** Operator-metadata line 2 is now inserted at offload by the script, which prompts for SITE / TIER / DATE / S<n> once per session and for `distance_or_run`, `TRUE_DISTANCE_M`, `BOOT_UTC_IST` per file. IST timestamps are converted to UTC before being written to the CSV. SESSION_ID and RUN_ID are auto-derived. Operational details live in `methodology.md` §4.1 / §4.4. |