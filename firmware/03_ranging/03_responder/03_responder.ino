#include <RadioLib.h>
#include <SPI.h>
#include <WiFi.h>
#include <esp_bt.h>
#include <SPIFFS.h>
#include <FS.h>

// T3-S3 V1.2 SPI bus
SPIClass spi(FSPI);

// SX1280: CS=7, DIO1=9, RESET=8, BUSY=36 (Without PA) — IR-2.1
SX1280 radio = new Module(7, 9, 8, 36, spi);

// ── Config ────────────────────────────────────────────────────────────────────
#define FW_VERSION    "0.7-offload-mode"
#define CSV_SCHEMA_V  1
#define ONBOARD_LED   37
#define RADIO_ADDRESS 0x12345678
#define SPIFFS_FLUSH_EVERY 10  // FR-5.4
#define MODE_SELECT_WINDOW_MS 3000 // boot-time window to type "OFFLOAD"
// Radio config (FSD §10.3 — locked). Single source for radio.begin(), the
// boot banner, and the per-CSV header line — never edit one without the others.
#define RADIO_FREQ_MHZ           2400.0f  // IR-3.2
#define RADIO_BW_KHZ             1625.0f  // IR-3.3
#define RADIO_SF                 6        // IR-3.4
#define RADIO_CR                 7        // IR-3.5 — RadioLib cr=7 → register 0x03 (4/7)
#define RADIO_TX_POWER_DBM       12       // IR-3.8

// ── State ─────────────────────────────────────────────────────────────────────
enum RespState { RS_BOOT, RS_LISTENING, RS_FAULT };
RespState currentState = RS_BOOT;
bool offloadMode = false;

const char* stateStr(RespState s) {
  switch (s) {
    case RS_BOOT:      return "BOOT";
    case RS_LISTENING: return "LISTENING";
    case RS_FAULT:     return "FAULT";
    default:           return "UNKNOWN";
  }
}

// ── SPIFFS logging ─────────────────────────────────────────────────────────────
File     logFile;
bool     spiffsOk  = false;
uint32_t seqNum    = 0;
char     boardIdShort[7];
char     logFilename[40];

void logLine(const char* line) {
  Serial.println(line);
  if (spiffsOk && logFile) {
    logFile.println(line);
  }
}

// FR-5.4: flush every SPIFFS_FLUSH_EVERY logged rows (not loop iterations —
// most responder loops are silenced timeouts and don't log).
void flushLog() {
  static uint16_t logsSinceFlush = 0;
  if (spiffsOk && logFile && ++logsSinceFlush >= SPIFFS_FLUSH_EVERY) {
    logFile.flush();
    logsSinceFlush = 0;
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
    } else if (len < 63) {
      buf[len++] = c;
    }
  }
}

// ── SPIFFS init ───────────────────────────────────────────────────────────────
// Mount SPIFFS and derive boardIdShort. Both modes need this so LIST/DUMP work
// in OFFLOAD; the new pucklog is only created in NORMAL via createLogFile().
bool mountSpiffs() {
  if (!SPIFFS.begin(true)) return false;
  snprintf(boardIdShort, sizeof(boardIdShort), "%06X",
           (uint32_t)(ESP.getEfuseMac() & 0xFFFFFF));
  return true;
}

// NORMAL-mode only: choose next boot_seq, open log file, write headers.
bool createLogFile() {
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

  // Firmware-written header — DR-2.1.
  // Includes radio config so each CSV is self-describing across firmware
  // versions — even if SPIFFS holds files written by older firmware with
  // different radio settings, the per-file header is authoritative.
  uint64_t mac = ESP.getEfuseMac();
  char h[192];
  snprintf(h, sizeof(h),
    "# CSV_SCHEMA_V=%d, FW=%s, BOARD_ID=0x%04X%08X, ROLE=RESPONDER, BOOT_MS=0, "
    "FREQ=%.1f, BW=%.1f, SF=%d, CR=%d, TXPOWER=%d",
    CSV_SCHEMA_V, FW_VERSION,
    (uint16_t)(mac >> 32), (uint32_t)mac,
    RADIO_FREQ_MHZ, RADIO_BW_KHZ, RADIO_SF, RADIO_CR, RADIO_TX_POWER_DBM);
  logFile.println(h);

  // Column header — DR-2
  logFile.println("seq,timestamp_ms,event,rssi_dbm,state,radio_status_code");
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
          overflow = true;
        }
      }
    }
    delay(50);
  }
  return false;
}

// ── FAULT — BR-1.5 ────────────────────────────────────────────────────────────
void enterFault(const char* reason) {
  Serial.print("FAULT: "); Serial.println(reason);
  if (logFile) logFile.close();
  pinMode(ONBOARD_LED, OUTPUT);
  while (true) {
    digitalWrite(ONBOARD_LED, HIGH); delay(500);
    digitalWrite(ONBOARD_LED, LOW);  delay(500);
  }
}

// ── setup ─────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(1000);
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

  // Boot banner part 1
  uint64_t mac = ESP.getEfuseMac();
  Serial.println("--- Pack Pucks Boot ---");
  Serial.print  ("FW_VERSION: ");   Serial.println(FW_VERSION);
  Serial.printf ("BOARD_ID: 0x%04X%08X\n", (uint16_t)(mac >> 32), (uint32_t)mac);
  Serial.println("ROLE: RESPONDER");
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

  spi.begin(5, 3, 6, 7); // SCK, MISO, MOSI, CS
  if (radio.begin(RADIO_FREQ_MHZ, RADIO_BW_KHZ, RADIO_SF, RADIO_CR) != RADIOLIB_ERR_NONE)
    enterFault("Radio init failed.");
  // begin() default is 10 dBm — must set explicitly to honour IR-3.8.
  if (radio.setOutputPower(RADIO_TX_POWER_DBM) != RADIOLIB_ERR_NONE)
    enterFault("setOutputPower failed.");

  Serial.println("[OK] Radio initialised");

  // Column header to Serial
  Serial.println("seq,timestamp_ms,event,rssi_dbm,state,radio_status_code");

  // Log BOOT and READY events — DR-2
  seqNum++;
  char line[80];
  snprintf(line, sizeof(line), "%lu,0,BOOT,0,BOOT,0", (unsigned long)seqNum);
  logLine(line);

  seqNum++;
  snprintf(line, sizeof(line), "%lu,%lu,READY,0,LISTENING,0",
           (unsigned long)seqNum, (unsigned long)millis());
  logLine(line);
  logFile.flush();

  currentState = RS_LISTENING;
}

// ── loop ──────────────────────────────────────────────────────────────────────
void loop() {
  if (offloadMode) {
    processSerialCommands();
    return;
  }
  processSerialCommands();

  // FR-3.1, FR-3.2 — listen and auto-reply
  int radioState = radio.range(false, RADIO_ADDRESS);

  // Silence timeouts — not a loggable event for the Responder
  if (radioState == RADIOLIB_ERR_RX_TIMEOUT || radioState == RADIOLIB_ERR_RANGING_TIMEOUT) return;

  seqNum++;
  char line[80];

  if (radioState == RADIOLIB_ERR_NONE) {
    // FR-3.3: log RANGING_REQ with RSSI — DR-2
    snprintf(line, sizeof(line), "%lu,%lu,RANGING_REQ,%d,LISTENING,0",
      (unsigned long)seqNum, (unsigned long)millis(),
      (int)radio.getRSSI());
  } else {
    snprintf(line, sizeof(line), "%lu,%lu,ERROR,0,LISTENING,%d",
      (unsigned long)seqNum, (unsigned long)millis(), radioState);
  }

  logLine(line);
  flushLog();
}
