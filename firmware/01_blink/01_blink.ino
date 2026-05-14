#define LED_PIN 37

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
}

void loop() {
  digitalWrite(LED_PIN, HIGH);
  Serial.println("Blink");
  delay(500);
  digitalWrite(LED_PIN, LOW);
  Serial.println("Blink");
  delay(500);
}
