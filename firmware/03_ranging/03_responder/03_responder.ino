#include <RadioLib.h>
#include <SPI.h>

// T3-S3 V1.2 SPI bus
SPIClass spi(FSPI);

// SX1280: CS=7, DIO1=9, RESET=8, BUSY=36 (Without PA) — IR-2.1
SX1280 radio = new Module(7, 9, 8, 36, spi);

// Must match initiator — FR-3.1
#define RADIO_ADDRESS 0x12345678

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("=== PackPucks Ranging RESPONDER ===");
  Serial.println("Firmware: 1.0-dev | Role: RESPONDER | Addr: 0x12345678");
  Serial.println("Radio: 2400.0 MHz | BW: 1625.0 kHz | SF6");

  spi.begin(5, 3, 6, 7); // SCK, MISO, MOSI, CS

  int state = radio.begin(2400.0, 1625.0, 6);
  if (state != RADIOLIB_ERR_NONE) {
    Serial.print("[FAIL] Radio init error: ");
    Serial.println(state);
    while (true);
  }

  Serial.println("[OK] Radio initialised");
  Serial.println("Listening for ranging requests...");
  Serial.println("timestamp_ms,event,rssi_dbm");
}

void loop() {
  // FR-3.1, FR-3.2 — listen and auto-reply
  int state = radio.range(false, RADIO_ADDRESS);

  if (state == RADIOLIB_ERR_NONE) {
    // FR-3.3 — log timestamp and RSSI
    Serial.print(millis());
    Serial.print(",RESPONSE_SENT,");
    Serial.println((int)radio.getRSSI());

  } else if (state != RADIOLIB_ERR_RX_TIMEOUT) {
    Serial.print(millis());
    Serial.print(",ERROR,0 (code=");
    Serial.print(state);
    Serial.println(")");
  }
}
