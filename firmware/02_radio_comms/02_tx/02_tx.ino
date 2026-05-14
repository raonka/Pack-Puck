#include <RadioLib.h>
#include <SPI.h>

// T3-S3 V1.2 custom SPI bus (non-default pins)
SPIClass spi(FSPI);

// SX1280: CS=7, DIO1=9, RESET=8, BUSY=36 (Without PA variant)
SX1280 radio = new Module(7, 9, 8, 36, spi);

int txCount = 0;

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("=== PackPucks TX ===");

  // Initialise SPI with T3-S3 V1.2 pin assignments
  spi.begin(5, 3, 6, 7); // SCK, MISO, MOSI, CS

  int state = radio.begin(2400.0, 1625.0, 6);
  if (state != RADIOLIB_ERR_NONE) {
    Serial.print("[FAIL] Radio init error: ");
    Serial.println(state);
    while (true);
  }

  Serial.println("[OK] Radio initialised");
  Serial.println("Transmitting every 1000ms...");
}

void loop() {
  txCount++;
  String msg = "PackPucks TX #" + String(txCount);

  Serial.print("Sending: ");
  Serial.print(msg);
  Serial.print(" ... ");

  int state = radio.transmit(msg);
  if (state == RADIOLIB_ERR_NONE) {
    Serial.println("OK");
  } else {
    Serial.print("FAILED (");
    Serial.print(state);
    Serial.println(")");
  }

  delay(1000);
}
