#include <RadioLib.h>
#include <SPI.h>
#include <WiFi.h>
#include <esp_bt.h>
#include <SPIFFS.h>
#include <FS.h>

// Uncomment to enable OLED display — data collection builds only (Step 4.5)
#define ENABLE_DISPLAY
#ifdef ENABLE_DISPLAY
  #warning "COMMENT OUT BEFORE NO DISPLAY BUILD — see FIRMWARE_PLAN Step 4.5.3"
#endif

#ifdef ENABLE_DISPLAY
#include <U8g2lib.h>
// SW_I2C confirmed: SCL=17, SDA=18, addr=0x3C
U8G2_SSD1306_128X64_NONAME_F_SW_I2C u8g2(U8G2_R0, 17, 18, U8X8_PIN_NONE);
#endif

// T3-S3 V1.2 SPI bus
SPIClass spi(FSPI);

// SX1280: CS=7, DIO1=9, RESET=8, BUSY=36 (Without PA) — IR-2.1
SX1280 radio = new Module(7, 9, 8, 36, spi);

// ── Config ────────────────────────────────────────────────────────────────────
#define FW_VERSION               "0.7-offload-mode"
#define CSV_SCHEMA_V             1
#define ONBOARD_LED              37
#define RANGING_INTERVAL_MS      500
#define MAX_CONSECUTIVE_FAILURES 3
#define RADIO_ADDRESS            0x12345678
#define SPIFFS_FLUSH_EVERY       10   // FR-5.4: flush every 10 cycles ≈ 5 s
#define MODE_SELECT_WINDOW_MS    3000 // boot-time window to type "OFFLOAD"
// Radio config (FSD §10.3 — locked). Single source for radio.begin(), the
// boot banner, and the per-CSV header line — never edit one without the others.
//
// Build modes (selected at compile time — see ENABLE_DISPLAY above):
//   collection — ENABLE_DISPLAY on; OLED is the in-field readout (dist/RSSI/state/fails).
//                LED ring not required. Run once at BW=406.25f and once at BW=1625.0f
//                for the Part 1 two-bandwidth sweep (FSD IR-3.3, methodology §3).
//   demo       — ENABLE_DISPLAY off; LED ring on; BW=1625.0f only (FSD §10.3, demo scope).
#define RADIO_FREQ_MHZ           2400.0f  // IR-3.2
// IR-3.3: the only valid SX1280 values for the Part 1 campaign are 406.25f and
// 1625.0f. RadioLib rejects 400.0f / 1600.0f with INVALID_BANDWIDTH (-8). Flip
// this one line and reflash both pucks for each bandwidth sweep run; the CSV
// header (DR-1.1) self-describes the BW that produced each file.
#define RADIO_BW_KHZ             1625.0f  // IR-3.3
#define RADIO_SF                 8        // IR-3.4 — held constant across both bandwidths
#define RADIO_CR                 7        // IR-3.5 — RadioLib cr=7 → register 0x03 (4/7)
#define RADIO_TX_POWER_DBM       12       // IR-3.8

// ── State ─────────────────────────────────────────────────────────────────────
enum PuckState { ST_BOOT, ST_RANGING, ST_DISPLAY, ST_PEER_LOST, ST_FAULT };
PuckState currentState = ST_BOOT;
int  consecutiveFailures = 0;
float lastDistance = 0.0;
int   lastRSSI     = 0;
bool  offloadMode  = false;

const char* stateStr(PuckState s) {
  switch (s) {
    case ST_BOOT:      return "BOOT";
    case ST_RANGING:   return "RANGING";
    case ST_DISPLAY:   return "DISPLAY";
    case ST_PEER_LOST: return "PEER_LOST";
    case ST_FAULT:     return "FAULT";
    default:           return "UNKNOWN";
  }
}

// ── SPIFFS logging ─────────────────────────────────────────────────────────────
File   logFile;
bool   spiffsOk  = false;
uint32_t seqNum  = 0;
uint32_t loopCount = 0;
char   boardIdShort[7];   // 6 hex chars + null
char   logFilename[40];

// Write one CSV line to Serial and SPIFFS — FR-5.1, FR-5.4
void logLine(const char* line) {
  Serial.println(line);
  if (spiffsOk && logFile) {
    logFile.println(line);
  }
}

void flushLog() {
  if (spiffsOk && logFile && (loopCount % SPIFFS_FLUSH_EVERY == 0)) {
    logFile.flush();
  }
}

// ── Serial command processor — FR-5.6 ─────────────────────────────────────────
void processSerialCommands() {
  static char buf[64];
  static int  len = 0;

  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (len == 0) return;
      buf[len] = '\0';
      String cmd = String(buf);
      cmd.trim();
      len = 0;

      if (cmd == "LIST") {
        // Framed for tools/offload/offload.py — markers match the DUMP style.
        // Each row: "<filename> <size_bytes>" with a single space separator.
        Serial.println("---BEGIN LIST---");
        File root = SPIFFS.open("/");
        File f = root.openNextFile();
        while (f) {
          String name = f.name();
          if (!name.startsWith("/")) name = "/" + name; // match DUMP marker form
          Serial.print(name);
          Serial.print(' ');
          Serial.println(f.size());
          f = root.openNextFile();
        }
        Serial.println("---END LIST---");

      } else if (cmd.startsWith("DUMP ")) {
        String fname = cmd.substring(5);
        fname.trim();
        if (!fname.startsWith("/")) fname = "/" + fname;
        // Flush current log before dumping so all data is readable
        if (spiffsOk && logFile) logFile.flush();
        if (SPIFFS.exists(fname)) {
          File f = SPIFFS.open(fname, "r");
          Serial.print("---BEGIN "); Serial.print(fname); Serial.println("---");
          uint8_t dumpBuf[256];
          while (f.available()) {
            size_t n = f.read(dumpBuf, sizeof(dumpBuf));
            Serial.write(dumpBuf, n);
          }
          Serial.print("---END ");   Serial.print(fname); Serial.println("---");
          f.close();
        } else {
          Serial.print("File not found: "); Serial.println(fname);
        }

      } else if (cmd.startsWith("DELETE ")) {
        String fname = cmd.substring(7);
        fname.trim();
        if (!fname.startsWith("/")) fname = "/" + fname;
        Serial.println(SPIFFS.remove(fname) ? "Deleted." : "Delete failed.");

      } else if (cmd == "FORMAT") {
        Serial.println("Formatting SPIFFS...");
        if (logFile) logFile.close();
        SPIFFS.format();
        spiffsOk = false;
        Serial.println("Done. Reboot to re-init logging.");
      }
      // Unrecognised lines silently ignored per FR-5.6
    } else if (len < 63) {
      buf[len++] = c;
    }
  }
}

// ── SPIFFS init — FR-5.5 ──────────────────────────────────────────────────────
// Mount SPIFFS and derive boardIdShort. Both modes need this so LIST/DUMP work
// in OFFLOAD; the new pucklog file is only created in NORMAL via createLogFile().
bool mountSpiffs() {
  if (!SPIFFS.begin(true)) return false;
  // board_id_short: lower 6 hex digits of eFuse MAC
  snprintf(boardIdShort, sizeof(boardIdShort), "%06X",
           (uint32_t)(ESP.getEfuseMac() & 0xFFFFFF));
  return true;
}

// NORMAL-mode only: choose next boot_seq, open the log file, write headers.
bool createLogFile() {
  // Scan for highest existing boot_seq and increment
  int bootSeq = 1;
  // f.name() on ESP32 SPIFFS omits the leading '/' — normalise before comparing
  String prefix = String("pucklog_") + boardIdShort + "_";
  File root = SPIFFS.open("/");
  File f = root.openNextFile();
  while (f) {
    String name = String(f.name());
    if (name.startsWith("/")) name = name.substring(1); // strip leading slash
    if (name.startsWith(prefix) && name.endsWith(".csv")) {
      int n = name.substring(prefix.length(), name.length() - 4).toInt();
      if (n >= bootSeq) bootSeq = n + 1;
    }
    f = root.openNextFile();
  }

  snprintf(logFilename, sizeof(logFilename),
           "/pucklog_%s_%d.csv", boardIdShort, bootSeq);

  logFile = SPIFFS.open(logFilename, "w");
  if (!logFile) return false;

  // Firmware-written header line 1 — DR-1.1.
  // Includes radio config so each CSV is self-describing across firmware
  // versions — even if SPIFFS holds files written by older firmware with
  // different radio settings, the per-file header is authoritative.
  uint64_t mac = ESP.getEfuseMac();
  char h[192];
  snprintf(h, sizeof(h),
    "# CSV_SCHEMA_V=%d, FW=%s, BOARD_ID=0x%04X%08X, ROLE=INITIATOR, BOOT_MS=0, "
    "FREQ=%.1f, BW=%.1f, SF=%d, CR=%d, TXPOWER=%d",
    CSV_SCHEMA_V, FW_VERSION,
    (uint16_t)(mac >> 32), (uint32_t)mac,
    RADIO_FREQ_MHZ, RADIO_BW_KHZ, RADIO_SF, RADIO_CR, RADIO_TX_POWER_DBM);
  logFile.println(h);

  // Column header — DR-1
  logFile.println("seq,timestamp_ms,status,raw_distance_m,rssi_dbm,state,consecutive_failures,radio_status_code");
  logFile.flush();
  return true;
}

// Mode-select window: poll Serial for up to MODE_SELECT_WINDOW_MS at ~50 ms
// granularity. Returns true on an exact-match "OFFLOAD" line (\r and \n trimmed).
// RX buffer is NOT flushed first — bytes that arrived during banner print count.
bool pollForOffloadCommand() {
  char buf[32];
  int  len = 0;
  bool overflow = false;
  uint32_t start = millis();
  while ((millis() - start) < MODE_SELECT_WINDOW_MS) {
    while (Serial.available()) {
      char c = (char)Serial.read();
      if (c == '\n') {
        if (!overflow) {
          buf[len] = '\0';
          if (strcmp(buf, "OFFLOAD") == 0) return true;
        }
        len = 0;
        overflow = false;
      } else if (c == '\r') {
        // skip — \r\n trimmed before exact-match compare
      } else if (!overflow) {
        if (len < (int)sizeof(buf) - 1) {
          buf[len++] = c;
        } else {
          overflow = true; // ignore rest of this oversized line
        }
      }
    }
    delay(50);
  }
  return false;
}

// ── Radio init ────────────────────────────────────────────────────────────────
bool initRadio() {
  spi.begin(5, 3, 6, 7); // SCK, MISO, MOSI, CS
  if (radio.begin(RADIO_FREQ_MHZ, RADIO_BW_KHZ, RADIO_SF, RADIO_CR) != RADIOLIB_ERR_NONE)
    return false;
  // begin() default is 10 dBm — must set explicitly to honour IR-3.8.
  return radio.setOutputPower(RADIO_TX_POWER_DBM) == RADIOLIB_ERR_NONE;
}

// ── FAULT — BR-1.5 ────────────────────────────────────────────────────────────
void enterFault(const char* reason) {
  Serial.print("FAULT: "); Serial.println(reason);
  if (logFile) logFile.close();
  pinMode(ONBOARD_LED, OUTPUT);
#ifdef ENABLE_DISPLAY
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_6x10_tf);
  u8g2.drawStr(0, 20, "FAULT");
  u8g2.drawStr(0, 35, reason);
  u8g2.drawStr(0, 50, "Reset board");
  u8g2.sendBuffer();
#endif
  while (true) {
    digitalWrite(ONBOARD_LED, HIGH); delay(500);
    digitalWrite(ONBOARD_LED, LOW);  delay(500);
  }
}

// ── OLED display update ───────────────────────────────────────────────────────
#ifdef ENABLE_DISPLAY
void updateDisplay(float distance, int rssi, PuckState state, int fails) {
  char buf[24];
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_6x10_tf);
  u8g2.drawStr(0, 10, "PackPucks v1.0");
  u8g2.drawHLine(0, 13, 128);

  if (state == ST_PEER_LOST) {
    u8g2.drawStr(0, 26, "Dist:  --- m");
  } else {
    snprintf(buf, sizeof(buf), "Dist: %6.2f m", distance);
    u8g2.drawStr(0, 26, buf);
  }

  snprintf(buf, sizeof(buf), "RSSI: %4d dBm", rssi);
  u8g2.drawStr(0, 39, buf);

  snprintf(buf, sizeof(buf), "State: %s", stateStr(state));
  u8g2.drawStr(0, 52, buf);

  snprintf(buf, sizeof(buf), "Fails: %d", fails);
  u8g2.drawStr(0, 63, buf);

  u8g2.sendBuffer();
}
#endif

// ── setup ─────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(1000); // Field-ready: SPIFFS removes Serial dependency (was 3 s in Phase 4.6)
  pinMode(ONBOARD_LED, OUTPUT);

  // SPIFFS mount (no file opened yet — see createLogFile() for NORMAL mode).
  bool spiffsMounted = mountSpiffs();

  // FR-1.6: WiFi + BT off. The FAULT path stays ahead of the mode-select window —
  // a faulty puck must not sit waiting 3 s for OFFLOAD.
  bool wifiOff = WiFi.mode(WIFI_OFF);
  bool btOff   = btStop();
  if (!wifiOff || !btOff) {
    char reason[48];
    snprintf(reason, sizeof(reason), "WiFi/BT off failed (W=%d, BT=%d)", wifiOff, btOff);
    enterFault(reason);
  }

  if (!spiffsMounted) enterFault("SPIFFS init failed.");

  // Boot banner part 1 — FR-1.5 / FIRMWARE_PLAN §4.6
  uint64_t mac = ESP.getEfuseMac();
  Serial.println("--- Pack Pucks Boot ---");
  Serial.print  ("FW_VERSION: ");   Serial.println(FW_VERSION);
  Serial.printf ("BOARD_ID: 0x%04X%08X\n", (uint16_t)(mac >> 32), (uint32_t)mac);
  Serial.println("ROLE: INITIATOR");
  Serial.print  ("CSV_SCHEMA_V: "); Serial.println(CSV_SCHEMA_V);
  Serial.print  ("WIFI_OFF: ");     Serial.println(wifiOff ? 1 : 0);
  Serial.print  ("BT_OFF: ");       Serial.println(btOff   ? 1 : 0);
  Serial.printf ("RADIO: %.1f MHz, BW %.1f kHz, SF %d, CR 4/%d, %d dBm\n",
                 RADIO_FREQ_MHZ, RADIO_BW_KHZ, RADIO_SF, RADIO_CR, RADIO_TX_POWER_DBM);
  Serial.print  ("MODE_SELECT_WINDOW_MS: "); Serial.println(MODE_SELECT_WINDOW_MS);

  // Mode-select window — exact-match "OFFLOAD" line picks OFFLOAD, else NORMAL.
  offloadMode = pollForOffloadCommand();

  if (offloadMode) {
    Serial.println("SPIFFS_FILE: <none>");
    Serial.println("MODE: OFFLOAD");
    Serial.println("-----------------------");
    return; // loop() runs only the Serial command processor — no radio, no log.
  }

  // NORMAL mode: open the new pucklog file and finish the banner.
  spiffsOk = createLogFile();
  Serial.print  ("SPIFFS_FILE: ");  Serial.println(spiffsOk ? logFilename : "FAILED");
  Serial.println("MODE: NORMAL");
  Serial.println("-----------------------");

  if (!spiffsOk) enterFault("Log file open failed.");

#ifdef ENABLE_DISPLAY
  u8g2.begin();
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_6x10_tf);
  u8g2.drawStr(0, 20, "PackPucks v1.0");
  u8g2.drawStr(0, 35, "Initialising...");
  u8g2.sendBuffer();
#endif

  if (!initRadio()) enterFault("Radio init failed.");

  Serial.println("[OK] Radio initialised");

  // Column header to Serial — matches SPIFFS file (operator can verify alignment)
  Serial.println("seq,timestamp_ms,status,raw_distance_m,rssi_dbm,state,consecutive_failures,radio_status_code");

  currentState = ST_RANGING;
}

// ── loop ──────────────────────────────────────────────────────────────────────
void loop() {
  if (offloadMode) {
    processSerialCommands();
    return;
  }
  loopCount++;
  processSerialCommands();

  // DISPLAY is a transient state — always re-enters RANGING at cycle start
  if (currentState == ST_DISPLAY) currentState = ST_RANGING;

  uint32_t t = millis();
  int radioState = radio.range(true, RADIO_ADDRESS);
  seqNum++;

  char line[112];

  if (radioState == RADIOLIB_ERR_NONE) {
    // FR-2.3 SUCCESS
    float dist = radio.getRangingResult(); // raw — never clamped per methodology §4.2
    int   rssi = (int)radio.getRSSI();
    consecutiveFailures = 0;
    currentState = ST_DISPLAY;
    lastDistance = dist;
    lastRSSI     = rssi;

    snprintf(line, sizeof(line), "%lu,%lu,SUCCESS,%.4f,%d,%s,%d,0",
      (unsigned long)seqNum, (unsigned long)t,
      dist, rssi, stateStr(currentState), consecutiveFailures);

  } else if (radioState == RADIOLIB_ERR_RX_TIMEOUT || radioState == RADIOLIB_ERR_RANGING_TIMEOUT) {
    // FR-2.3 TIMEOUT
    consecutiveFailures++;
    currentState = (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES)
                   ? ST_PEER_LOST : ST_RANGING;

    snprintf(line, sizeof(line), "%lu,%lu,TIMEOUT,NaN,0,%s,%d,%d",
      (unsigned long)seqNum, (unsigned long)t,
      stateStr(currentState), consecutiveFailures, radioState);

  } else {
    // FR-2.3 ERROR
    currentState = ST_FAULT;
    snprintf(line, sizeof(line), "%lu,%lu,ERROR,NaN,0,%s,%d,%d",
      (unsigned long)seqNum, (unsigned long)t,
      stateStr(currentState), consecutiveFailures, radioState);
  }

  logLine(line);
  flushLog();

#ifdef ENABLE_DISPLAY
  // FR-4.5: clamp only for display, never for the logged value
  float displayDist = (lastDistance < 0.0f) ? 0.0f : lastDistance;
  updateDisplay(displayDist, lastRSSI, currentState, consecutiveFailures);
#endif

  // delay(RANGING_INTERVAL_MS) removed — the blocking radio.range() call itself
  // takes ~648ms at BW 1625 kHz / SF6 (measured from CSV timestamps, May 2026).
  // Adding 500ms on top produced ~1148ms cycles (~0.87 Hz), well below the
  // FR-2.1 target of 2 Hz. Without the delay, effective rate is ~1.5 Hz.
}
