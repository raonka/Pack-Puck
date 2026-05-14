# Pack Pucks — Firmware Bring-Up Plan
## From boards-in-hand to working demo (June 15, 2026)

---

## How This Document Works

This is the step-by-step playbook for everything between receiving hardware
and having a working demo. Each phase has:
- What you need before starting
- Exact steps
- What success looks like
- What to do if it fails

Read the entire phase before doing anything in it.

---

## Toolchain Overview

Three tools. Each has a specific role. They work together.

| Tool | Role | When you use it |
|---|---|---|
| **Arduino IDE** | Compiles firmware and flashes it to the board | Every time you want code to run on hardware |
| **Claude Code** | Writes, edits, and debugs firmware code | Every time you need code written or changed |
| **Serial Monitor** (inside Arduino IDE) | Shows output from the running board | Every time you need to see what the board is doing |

**The workflow loop:**
```
Claude Code writes code
  → Arduino IDE compiles + flashes
    → Serial Monitor shows output
      → Paste output back to Claude Code if debugging
        → Claude Code fixes code
          → repeat
```

Think of Arduino IDE as your compiler and deployment tool.
Think of Claude Code as your coding pair.
Think of Serial Monitor as your console.log.

---

## Phase 0: Physical Preparation
### Do this RIGHT NOW. Takes 2 minutes.

**Prerequisites:** T3-S3 boards in hand, SMA antenna in box.

**What is an SMA antenna?**
The T3-S3 ships with a small stubby antenna and a gold-coloured threaded
connector on the board. SMA is just the name of that connector standard —
like how USB-A is a connector standard. The antenna screws onto the board's
SMA port. You'll see it on the bottom edge of the board near the gold cylinder.

**Why this must happen before anything else:**
The SX1280 transmits RF energy. Without an antenna, that energy has nowhere
to go and reflects back into the chip. This can permanently damage the SX1280.
This isn't recoverable. Board destroyed, ₹3,341 gone.

**Steps:**
1. Take the antenna from the box
2. Align the threaded base with the gold SMA connector on the board
3. Screw clockwise until finger-tight — don't overtighten, don't force it
4. Repeat for both boards

**Success:** Antenna is upright, snug, not wobbly.

---

## Phase 1: Development Environment Setup
### Do this RIGHT NOW. Takes 30-45 minutes.

**Prerequisites:** Laptop, internet connection. Boards not needed yet.

---

### Step 1.1 — Install Arduino IDE

Download Arduino IDE 2.x from arduino.cc/en/software
Install it normally. Open it once to verify it launches.

---

### Step 1.2 — Add ESP32-S3 Board Support

**What this does:** Arduino IDE doesn't know about ESP32-S3 by default.
You're adding the ESP32 board definitions so Arduino IDE can compile
code for it and talk to it over USB.

Think of it like installing a runtime for a new language — Arduino IDE
is the IDE, ESP32 board support is the SDK.

1. Open Arduino IDE
2. Go to: File → Preferences
3. In "Additional boards manager URLs" paste this exact URL:
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
4. Click OK
5. Go to: Tools → Board → Boards Manager
6. Search: "esp32"
7. Find "esp32 by Espressif Systems" — install the latest version
8. Wait — this downloads ~200MB, takes 5-10 minutes

---

### Step 1.3 — Configure Board Settings

**This is critical. Wrong settings = board won't flash or behave strangely.**

Go to Tools menu and set EVERY option exactly as follows:

| Setting | Value |
|---|---|
| Board | **LilyGo T3-S3** |
| Board Revision | **Radio-SX1280** ← critical |
| USB CDC On Boot | **Enable** ← critical for Serial Monitor |
| CPU Frequency | 240MHz (WiFi) |
| Core Debug Level | None |
| USB DFU On Boot | Disable |
| Events Run On | Core1 |
| Arduino Runs On | Core1 |
| USB Firmware MSC On Boot | Disable |
| Partition Scheme | Default 4MB with spiffs (1.2MB APP/1.5MB SPIFFS) |
| PSRAM | **QSPI PSRAM** ← critical |
| Upload Mode | **UART0/Hardware CDC** |
| Upload Speed | 921600 |
| USB Mode | **CDC and JTAG** |

**Why "USB CDC On Boot: Enable" matters:**
CDC (Communications Device Class) is what allows the board to appear as
a serial port to your computer over USB. Without it, Serial Monitor shows
nothing. Think of it as enabling stdout over USB.

---

### Step 1.4 — Install RadioLib

**What is RadioLib?**
A library is pre-written code someone else wrote that you import into
your project. RadioLib is the library that knows how to talk to the SX1280
chip — it wraps all the low-level SPI commands into clean function calls
like `startRanging()` and `getRangingResult()`.

1. Go to: Tools → Manage Libraries
2. Search: "RadioLib"
3. Find "RadioLib by Jan Gromeš"
4. Install the latest version

---

### Step 1.5 — Install Claude Code

**What is Claude Code?**
Claude Code is a command-line tool that runs in your terminal and can
read, write, and edit files in your project directory. You'll use it to
write firmware sketches, and to debug by pasting in Serial Monitor output.

Install it:
```bash
npm install -g @anthropic-ai/claude-code
```

Requires Node.js. If you don't have it: download from nodejs.org first.

Verify install:
```bash
claude --version
```

**How you'll use it during this project:**
```bash
# Navigate to your firmware folder
cd ~/PackPucks/firmware

# Start Claude Code
claude

# Then describe what you want in plain English:
# "Write an Arduino sketch that blinks the LED on GPIO 37 every 500ms"
# "Here's my Serial Monitor output, why is ranging returning 0?"
```

---

### Step 1.6 — Create Project Folder Structure

Create this folder structure on your laptop:

```
PackPucks/
  firmware/
    01_blink/
    02_radio_comms/
    03_ranging/
    04_led_test/
    05_integration/
  data/
    ranging_experiments/
  docs/
```

This is where Claude Code will write firmware files.
Each numbered folder is one phase of firmware development.

---

## Phase 2: First Boot Verification
### Proves the board is alive and talking to your laptop.

**Prerequisites:** Phase 1 complete, one T3-S3 board with antenna attached.

**What we're doing and why:**
Before writing any project-specific code, verify the board boots, the LED
works, and Serial Monitor shows output. This eliminates hardware failure
as a variable before you write a single line of radio code. If something
goes wrong in Phase 3, you'll know it's the radio code, not the board.

---

### Step 2.1 — Connect Board to Laptop

Connect Board 1 to your laptop via USB-C cable.

**What happens when you connect it:**
The ESP32-S3 boots immediately. The onboard charging circuit activates.
Your laptop should recognise a new USB device. On Windows, check Device
Manager for a new COM port. On Mac/Linux, check /dev/tty* for a new entry.

In Arduino IDE, go to Tools → Port. A new port should appear.
Select it. This is your communication channel to the board.

**If no port appears:**
The board may need a driver. Search "ESP32-S3 USB driver Windows" and
install the CP2102 or CH340 driver depending on your OS. Then reconnect.

---

### Step 2.2 — Write and Flash Blink Sketch via Claude Code

Open terminal, navigate to PackPucks/firmware/01_blink, start Claude Code:

```bash
cd ~/PackPucks/firmware/01_blink
claude
```

Tell Claude Code:
> "Write an Arduino sketch for LILYGO T3-S3 that blinks the onboard LED
> on GPIO 37 every 500ms and prints 'Blink' to Serial at 115200 baud
> every time it toggles."

Claude Code will create a .ino file. Open it in Arduino IDE.

Click the Upload button (right arrow icon). Arduino IDE compiles and flashes.

**What "flashing" means:**
Compiling turns your code into machine instructions the ESP32-S3 can execute.
Flashing writes those instructions to the board's flash memory — the same
concept as deploying code, except the target is a chip not a server.
The board resets and immediately runs your code.

---

### Step 2.3 — Verify via Serial Monitor

In Arduino IDE: Tools → Serial Monitor. Set baud rate to 115200.

**Success:** You see "Blink" printing every 500ms. The small LED on the
board flashes.

**If upload fails:**
- Check the port is selected in Tools → Port
- Try pressing the BOOT button on the board during upload
- Verify Upload Mode is set to "UART0/Hardware CDC"

**If Serial Monitor shows garbage:**
- Baud rate mismatch. Set to 115200 in Serial Monitor dropdown.

---

## Phase 3: Radio Basic Communication
### Proves the SX1280 radio is working before attempting ranging.

**Prerequisites:** Phase 2 complete. Both boards. Both antennas attached.

**What we're doing and why:**
Before ranging, verify basic LoRa packet transmission and reception.
Ranging is a more complex operation — if you go straight to ranging and
it fails, you don't know if the radio is broken or your ranging code is wrong.
Basic TX/RX first eliminates that ambiguity.

Think of it like testing a network socket before testing an HTTP endpoint.

**What is TX/RX?**
TX = Transmit (sending a radio packet).
RX = Receive (listening for and receiving a radio packet).
One board broadcasts a packet. The other board listens and receives it.

---

### Step 3.1 — Write TX Sketch (Board 1)

In terminal, navigate to PackPucks/firmware/02_radio_comms, start Claude Code:

```bash
cd ~/PackPucks/firmware/02_radio_comms
claude
```

Tell Claude Code:
> "Write an Arduino sketch for LILYGO T3-S3 V1.2 with SX1280. Use RadioLib.
> SX1280 pins: CS=7, DIO1=9, RESET=8, BUSY=36. No TX_EN or RX_EN (Without PA).
> The sketch should transmit a LoRa packet containing 'PackPucks TX' every 1 second.
> Print transmission status to Serial at 115200 baud.
> Use frequency 2400.0 MHz, bandwidth 1600.0 kHz, spreading factor 6."

**Why those radio settings?**
These are the DTU/IEEE paper's recommended settings for 0-400m range.
BW 1600 kHz + SF6 = optimal for your use case. Using these now means
your ranging experiments later use the same settings as your baseline paper.

---

### Step 3.2 — Write RX Sketch (Board 2)

Same session or new Claude Code session:

Tell Claude Code:
> "Write a matching receive sketch for the same board. Listen for LoRa packets
> on 2400.0 MHz, BW 1600 kHz, SF6. When a packet is received, print its
> content and RSSI to Serial."

**What is RSSI?**
Received Signal Strength Indicator. A measure of how strong the received
radio signal is, in dBm (decibels relative to milliwatt). More negative
= weaker signal. -40 dBm = strong. -100 dBm = barely audible.
Useful for sanity-checking that the radio is actually receiving.

---

### Step 3.3 — Flash and Test

Flash TX sketch to Board 1. Flash RX sketch to Board 2.
Connect both to laptop (you'll need two USB ports or a hub).
Open Serial Monitor for each board (Arduino IDE supports multiple windows).

Place boards 1 metre apart on a desk.

**Success:** Board 2's Serial Monitor shows incoming packets with RSSI values.
RSSI at 1m will likely be around -30 to -50 dBm.

**If no packets received:**
- Verify both boards have antennas attached
- Verify both sketches use identical frequency and settings
- Check Serial Monitor on Board 1 for transmit errors

---

## Phase 4: Ranging Bring-Up
### The core of Contribution 1. First real ranging numbers.

**Prerequisites:** Phase 3 complete.

**What ranging is, explained from scratch:**
The SX1280 chip has a built-in ranging engine. Two chips exchange a series
of radio pulses. The chip measures how long those pulses take to travel
between them (Time of Flight). Since radio waves travel at the speed of
light, time × speed of light = distance.

This all happens inside the SX1280 chip. Your firmware just says "start
ranging" and "give me the result." RadioLib wraps this into two functions:
`startRanging()` and `getRangingResult()`.

**Initiator vs Responder — this is critical:**
Ranging requires exactly ONE initiator and ONE responder.

- **Initiator:** Starts the ranging exchange. Gets the distance result. This is Board 1.
- **Responder:** Listens for a ranging request, replies automatically. Doesn't get the result. This is Board 2.

If both boards are initiators: no ranging happens.
If both are responders: no ranging happens.
One of each, exactly.

---

### Step 4.1 — Write Ranging Initiator Sketch

```bash
cd ~/PackPucks/firmware/03_ranging
claude
```

Tell Claude Code:
> "Write an Arduino sketch for LILYGO T3-S3 V1.2 with SX1280 using RadioLib.
> Pins: CS=7, DIO1=9, RESET=8, BUSY=36. No TX_EN/RX_EN.
> This board is the RANGING INITIATOR.
> Settings: 2400.0 MHz, BW 1600 kHz, SF6.
> Every 500ms: start a ranging exchange, wait for result, print the distance
> in metres to Serial at 115200 baud.
> Also print if ranging failed.
> Use address 0x12345678 for both boards."

**What is the address?**
The address is like a channel identifier — both boards must use the same
address or they won't pair for ranging. Think of it as a shared secret.
Both boards must have identical addresses.

---

### Step 4.2 — Write Ranging Responder Sketch

Tell Claude Code (same session):
> "Write the matching RANGING RESPONDER sketch. Same pins, same settings,
> same address 0x12345678. The responder listens continuously and
> automatically replies to ranging requests. Print 'Ranging response sent'
> to Serial when it responds."

---

### Step 4.3 — Flash and Test

Flash initiator to Board 1. Flash responder to Board 2.
Open Serial Monitor on Board 1.

Place boards on a desk, physically measured distances apart.
Start with 1 metre, then 2m, 5m.

**Success:** Serial Monitor on Board 1 shows distance values updating
every 500ms. Values should roughly match your physical measurement.

**Record everything.** Open a text file and paste in the Serial Monitor
output with your actual measured distance noted. This is your first
experimental data for the paper.

**If ranging returns 0 or fails consistently:**
- Verify one board is initiator and the other is responder
- Verify addresses match exactly on both boards
- Verify antennas are attached
- Verify both boards are powered

---

### Step 4.4 — First Data Collection Session

Once ranging is stable, run a structured experiment. Do this properly —
it's paper data.

**Distances to test:** 1m, 2m, 5m, 10m, 20m (indoor corridor or outdoor).
**At each distance:** Record 20 readings. Note actual measured distance.
**Record in:** PackPucks/data/ranging_experiments/ as a CSV.

Ask Claude Code to write a CSV logger version of the initiator sketch
that outputs comma-separated values for easy data collection:
```
timestamp_ms, measured_distance_m, rssi
```

This gives you clean data for the paper from day one.

---

## Phase 5: Hardware Assembly
### Requires Robu order. Do after Phase 4 is stable.

**Prerequisites:** Robu order arrived. Soldering iron kit. Phase 4 complete.

**What header pin soldering is:**
The T3-S3 board has rows of holes along its long edges. These holes are
how you connect jumper wires to specific GPIO pins. Right now the holes
are empty — no way to attach wires.

Header pins are metal strips — a row of pins held in a plastic block.
Each pin has a long end and a short end. You insert the short end into
the holes from the top, then apply solder from underneath to permanently
join metal to board.

Once soldered, each hole becomes an accessible point you can plug
a jumper wire into, like a socket.

**Watch before doing:** Search YouTube "how to solder header pins Arduino."
Any top result. Watch it completely before picking up the iron.

---

### Step 5.1 — Solder Header Pins

1. Insert short end of pin strip into board holes from top
2. Rest the board on breadboard to hold pins upright while soldering
3. Heat iron for 2 minutes before use
4. Touch iron tip to the junction of pin + hole for 2-3 seconds
5. Feed a small amount of solder wire into the joint (not onto the iron)
6. Remove iron. Let joint cool 5 seconds before moving board.
7. Repeat for every pin on both boards

Good joint: shiny, volcano-shaped. Bad joint: dull, blobby, grey.
If a joint looks bad, reheat and try again.

---

### Step 5.2 — Wire WS2812B Ring

**What is a WS2812B?**
Each LED in the ring is an RGB LED with a tiny control chip built in.
They are chained together — data comes in on one end, passes through each
LED, and exits the other end. You control all 16 LEDs with just one wire
from the ESP32.

**Wiring:**
The ring has 3 connections:
- **5V / VCC** → connect to 5V pin on T3-S3 (or VBAT via capacitor)
- **GND** → connect to GND pin on T3-S3
- **DIN (Data In)** → connect to IO38 on T3-S3

**The 1000µF capacitor:**
Place it across the 5V and GND wires right at the ring's power connection.
Short end of capacitor (marked with a stripe) goes to GND.
Long end goes to 5V.

**Why the capacitor:**
When LEDs update, they briefly draw a large current spike. Without the
capacitor to absorb it, this spike causes a voltage dip that can corrupt
the data signal or damage the first LED. The capacitor acts as a local
buffer — like a small UPS just for the LED ring.

---

### Step 5.3 — Test WS2812B Independently

Before integrating with ranging, test the LED ring alone.

Install FastLED library: Tools → Manage Libraries → search "FastLED" → install.

```bash
cd ~/PackPucks/firmware/04_led_test
claude
```

Tell Claude Code:
> "Write an Arduino sketch for T3-S3 that uses FastLED to control a
> WS2812B 16-LED ring on GPIO 38. Cycle through: all green for 1 second,
> all amber for 1 second, all red for 1 second, repeat. Serial print
> current colour at 115200."

**Success:** LEDs cycle through green → amber → red continuously.

---

## Phase 6: Integration
### Combine ranging with LED. This is the demo firmware.

**Prerequisites:** Phase 4 and Phase 5 both working independently.

**What we're building:**
A continuous loop:
1. Initiate ranging → get distance in metres
2. Map distance to colour: green ≤ 50m, amber 50–200m, red > 200m
3. Set LED ring to that colour
4. Repeat every 500ms

---

### Step 6.1 — Write Integration Sketch

```bash
cd ~/PackPucks/firmware/05_integration
claude
```

Tell Claude Code:
> "Write an Arduino sketch for LILYGO T3-S3 V1.2 integrating SX1280
> ranging (RadioLib, pins CS=7, DIO1=9, RESET=8, BUSY=36) and
> WS2812B 16-LED ring on GPIO 38 (FastLED).
> 
> Ranging initiator mode. Address 0x12345678. 2400.0 MHz, BW 1600 kHz, SF6.
> 
> Every 500ms: get distance. If distance ≤ 50m: all LEDs green.
> If 50–200m: all LEDs amber. If > 200m: all LEDs red.
> If ranging fails: all LEDs white (unknown/error state).
> 
> Print distance and colour to Serial at 115200."

Responder board uses the same responder sketch from Phase 4 — no changes needed.

---

### Step 6.2 — Tune Thresholds

The 50m/200m thresholds are a starting point. Once both devices are
running, walk them apart and observe when colours change. Adjust thresholds
to feel right for your demo scenario.

Tell Claude Code the new thresholds and ask it to update the sketch.

---

### Step 6.3 — Stress Test

Run both devices for 30 continuous minutes. Observe:
- Does ranging stay stable or drift?
- Does it recover after a packet is missed?
- Do LEDs respond correctly at every distance?

Fix any issues found with Claude Code before recording the demo.

---

## Phase 7: Demo Preparation
### Turns working firmware into a documented research artefact.

**Prerequisites:** Phase 6 stable.

---

### Step 7.1 — Structured Data Collection

Run a final formal ranging experiment outdoors for paper data.

Distances: 1m, 5m, 10m, 25m, 50m, 100m, 200m, 400m.
At each: 50 readings. Note conditions (open field, time of day).
Export from Serial Monitor to CSV.

This is Experimental Section data for the arXiv Part 1 preprint.

---

### Step 7.2 — Record Demo Video

Setup: Both boards on a desk. One board is the "device under test."
Walk the second board away from the first while filming the LED ring.

The video should show:
- Starting close together — green LEDs
- Walking to medium distance — amber LEDs
- Walking to far distance — red LEDs
- Walking back — returning to green

Record outdoors for the full 0–400m demonstration if possible.

---

### Step 7.3 — Write Methodology Notes

In PackPucks/docs, write a markdown file covering:
- Hardware used (T3-S3, SX1280 spec, antenna type)
- Radio settings used (frequency, BW, SF, address)
- Experimental procedure (distances, number of readings, conditions)
- Raw data files location

This becomes Section 3 (Methodology) of the preprint.

---

## Phase Completion Summary

| Phase | Can start | Blocks |
|---|---|---|
| 0: Physical setup | Now | Everything else |
| 1: Dev environment | Now | All firmware phases |
| 2: Board verification | After Phase 1 | Phase 3 |
| 3: Radio comms | After Phase 2 | Phase 4 |
| 4: Ranging | After Phase 3 | Phase 6 |
| 5: Hardware assembly | After Robu arrives | Phase 6 |
| 6: Integration | After Phase 4 AND 5 | Phase 7 |
| 7: Demo prep | After Phase 6 | Preprint |

**Phases 0–4 can all happen this week, before Robu order arrives.**

---

## Battery Integration (Separate — Do After Demo)

The Pro-Range N18650CH battery has NO BMS.
The T3-S3 documentation requires a battery WITH protection.
Do NOT connect this battery to the T3-S3 until a protection circuit
(separate BMS module or TP4056 with protection) is correctly wired.

Battery integration is not needed for the June 15 demo — USB-C is sufficient.
Plan this separately before field testing.

---

## Quick Reference Card

**Board:** LilyGo T3-S3 V1.2 (ESP32-S3 + SX1280 Without PA)

**RadioLib constructor:**
```cpp
SX1280 radio = new Module(7, 9, 8, 36); // CS, DIO1, RESET, BUSY
```

**Recommended radio settings (DTU/IEEE baseline):**
```cpp
float frequency = 2400.0; // MHz
float bandwidth = 1600.0; // kHz
uint8_t spreadingFactor = 6;
```

**GPIO assignments:**
```
SX1280: All internal — CS=7, MOSI=6, MISO=3, SCK=5, BUSY=36, DIO1=9, RESET=8
WS2812B Data: GPIO 38
MPU6050 SDA: GPIO 33 (deferred)
MPU6050 SCL: GPIO 34 (deferred)
Onboard LED: GPIO 37
```

**Arduino IDE board settings (critical ones):**
```
Board Revision: Radio-SX1280
USB CDC On Boot: Enable
PSRAM: QSPI PSRAM
Upload Mode: UART0/Hardware CDC
```