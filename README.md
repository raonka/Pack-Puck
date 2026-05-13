# Pack Pucks

A screenless, peer-to-peer proximity tracking device for group coordination
in GPS-denied environments. No GPS. No smartphone. No cloud. No infrastructure.

Two devices communicate via SX1280 2.4 GHz LoRa Time-of-Flight ranging.
Distance is measured directly from radio signal travel time and indicated
on a 16-LED ring: green (in group), amber (drifting), red (separated).

The system functions identically in a tunnel, a forest, underground, or an
open field — wherever both devices are within radio range of each other.

## Hardware

| Component | Part |
|---|---|
| MCU + Radio | LILYGO T3-S3 V1.2 (ESP32-S3 + SX1280 Without PA) × 2 |
| Output | WS2812B 16-LED NeoPixel ring × 2 |


## Getting Started

### Prerequisites
- Arduino IDE 2.x with ESP32 board support
- RadioLib library (via Arduino Library Manager)
- FastLED library (via Arduino Library Manager)
- Two LILYGO T3-S3 boards with SMA antennas attached

### Flash
1. Open the sketch from `firmware/` for the desired phase
2. Set board to **LilyGo T3-S3**, Board Revision **Radio-SX1280**
3. Enable **USB CDC On Boot**, set PSRAM to **QSPI PSRAM**
4. Flash Initiator firmware to Board 1, Responder firmware to Board 2
5. Open Serial Monitor at 115200 baud

See `docs/FIRMWARE_PLAN.md` for the complete step-by-step guide.

## Documentation

| Document | Purpose |
|---|---|
| `docs/FSD.md` | Functional specification — system behaviour, requirements, acceptance criteria |
| `docs/FIRMWARE_PLAN.md` | Firmware bring-up plan — phased build guide from first boot to demo |
| `docs/State.md` | Current project state — hardware inventory, decisions, milestones |


## License

TBD — to be decided before first public release.