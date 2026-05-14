#include <RadioLib.h>
#include <SPI.h>

SPIClass spi(FSPI);
SX1280 radio = new Module(7, 9, 8, 36, spi);

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("=== PackPucks RX ===");

  spi.begin(5, 3, 6, 7); // SCK, MISO, MOSI, CS

  int state = radio.begin(2400.0, 1625.0, 6);
  if (state != RADIOLIB_ERR_NONE) {
    Serial.print("[FAIL] Radio init error: ");
    Serial.println(state);
    while (true);
  }

  Serial.println("[OK] Radio initialised");
  Serial.println("Listening for packets...");

  radio.startReceive();
}

void loop() {
  // DIO1 (GPIO 9) goes HIGH when a packet is ready
  if (digitalRead(9)) {
    String received = "";
    int state = radio.readData(received);

    if (state == RADIOLIB_ERR_NONE) {
      Serial.print("[RX] ");
      Serial.print(received);
      Serial.print("  |  RSSI: ");
      Serial.print(radio.getRSSI());
      Serial.println(" dBm");
    } else {
      Serial.print("[ERR] Read error: ");
      Serial.println(state);
    }

    // Re-arm for next packet
    radio.startReceive();
  }
}
