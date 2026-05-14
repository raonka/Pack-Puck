#include <RadioLib.h>
#include <SPI.h>

// Uncomment to enable OLED display — data collection builds only (Step 4.5)
#define ENABLE_DISPLAY

#ifdef ENABLE_DISPLAY
#include <U8g2lib.h>
// SW_I2C (bit-banged). Confirmed pins: SCL=17, SDA=18, addr=0x3C
U8G2_SSD1306_128X64_NONAME_F_SW_I2C u8g2(U8G2_R0, 17, 18, U8X8_PIN_NONE);
#endif

// T3-S3 V1.2 SPI bus
SPIClass spi(FSPI);

// SX1280: CS=7, DIO1=9, RESET=8, BUSY=36 (Without PA) — IR-2.1
SX1280 radio = new Module(7, 9, 8, 36, spi);

// Config — FR-2.1, FR-2.2, BR-2.3
#define RANGING_INTERVAL_MS      500
#define MAX_CONSECUTIVE_TIMEOUTS 3
#define RADIO_ADDRESS            0x12345678

enum State { RANGING_STATE, PEER_LOST, FAULT };
State currentState = RANGING_STATE;
int consecutiveTimeouts = 0;
float lastDistance = 0.0;
int lastRSSI = 0;

#ifdef ENABLE_DISPLAY
void updateDisplay(float distance, int rssi, State state, int fails) {
  char buf[24];
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_6x10_tf);

  u8g2.drawStr(0, 10, "PackPucks v1.0");
  u8g2.drawHLine(0, 13, 128);

  if (state == PEER_LOST) {
    u8g2.drawStr(0, 26, "Dist:  --- m");
  } else {
    snprintf(buf, sizeof(buf), "Dist: %6.2f m", distance);
    u8g2.drawStr(0, 26, buf);
  }

  snprintf(buf, sizeof(buf), "RSSI: %4d dBm", rssi);
  u8g2.drawStr(0, 39, buf);

  const char* stateStr = "RANGING";
  if (state == PEER_LOST) stateStr = "PEER_LOST";
  else if (state == FAULT)  stateStr = "FAULT";
  snprintf(buf, sizeof(buf), "State: %s", stateStr);
  u8g2.drawStr(0, 52, buf);

  snprintf(buf, sizeof(buf), "Fails: %d", fails);
  u8g2.drawStr(0, 63, buf);

  u8g2.sendBuffer();
}
#endif

bool initRadio() {
  spi.begin(5, 3, 6, 7); // SCK, MISO, MOSI, CS
  int state = radio.begin(2400.0, 1625.0, 6);
  return (state == RADIOLIB_ERR_NONE);
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("=== PackPucks Ranging INITIATOR ===");
  Serial.println("Firmware: 1.0-dev | Role: INITIATOR | Addr: 0x12345678");
  Serial.println("Radio: 2400.0 MHz | BW: 1625.0 kHz | SF6");

#ifdef ENABLE_DISPLAY
  u8g2.begin();
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_6x10_tf);
  u8g2.drawStr(0, 20, "PackPucks v1.0");
  u8g2.drawStr(0, 35, "Initialising...");
  u8g2.sendBuffer();
  Serial.println("[OK] OLED initialised");
#endif

  if (!initRadio()) {
    Serial.println("[FAIL] Radio init failed — halting");
#ifdef ENABLE_DISPLAY
    u8g2.clearBuffer();
    u8g2.drawStr(0, 20, "RADIO FAULT");
    u8g2.drawStr(0, 35, "Reset board");
    u8g2.sendBuffer();
#endif
    while (true);
  }

  Serial.println("[OK] Radio initialised");

  // CSV header — DR-2
  Serial.println("timestamp_ms,status,distance_m,rssi_dbm,consecutive_timeouts");
}

void loop() {
  uint32_t t = millis();

  int state = radio.range(true, RADIO_ADDRESS);

  if (state == RADIOLIB_ERR_NONE) {
    // FR-2.3 SUCCESS
    lastDistance = radio.getRangingResult();
    lastRSSI = (int)radio.getRSSI();
    consecutiveTimeouts = 0;
    currentState = RANGING_STATE;

    Serial.print(t);
    Serial.print(",SUCCESS,");
    Serial.print(lastDistance, 2);
    Serial.print(",");
    Serial.print(lastRSSI);
    Serial.print(",");
    Serial.println(consecutiveTimeouts);

  } else if (state == RADIOLIB_ERR_RX_TIMEOUT || state == -901) {
    // FR-2.3 TIMEOUT — -901 = RADIOLIB_ERR_RANGING_TIMEOUT
    consecutiveTimeouts++;
    if (consecutiveTimeouts >= MAX_CONSECUTIVE_TIMEOUTS) {
      currentState = PEER_LOST; // BR-1.4, FR-4.3
    }

    Serial.print(t);
    Serial.print(",TIMEOUT,NaN,0,");
    Serial.println(consecutiveTimeouts);

  } else {
    // FR-2.3 ERROR
    currentState = FAULT;
    Serial.print(t);
    Serial.print(",ERROR,NaN,0,");
    Serial.print(consecutiveTimeouts);
    Serial.print(" (code=");
    Serial.print(state);
    Serial.println(")");
  }

#ifdef ENABLE_DISPLAY
  updateDisplay(lastDistance, lastRSSI, currentState, consecutiveTimeouts);
#endif

  delay(RANGING_INTERVAL_MS);
}
