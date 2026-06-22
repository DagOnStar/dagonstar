#include "DHT.h"

#define DHTPIN 8        // Digital pin connected to the DHT11
#define DHTTYPE DHT11   // Sensor type

DHT dht(DHTPIN, DHTTYPE);

void setup() {
  Serial.begin(9600);
  Serial.println("Starting DHT11 sensor reading...");
  dht.begin();  // Initialize the sensor
}

void loop() {
  // Wait one second between readings
  delay(1000);

  // Read humidity and temperature
  float h = dht.readHumidity();
  float t = dht.readTemperature();        // Temperature in °C
  float f = dht.readTemperature(true);    // Temperature in °F

  // Check if any reading failed
  if (isnan(h) || isnan(t) || isnan(f)) {
    Serial.println("Error reading from DHT11 sensor");
    return;
  }

  // Calculate heat index (optional)
  float hif = dht.computeHeatIndex(f, h);
  float hic = dht.computeHeatIndex(t, h, false);

  // Print the values
  Serial.print("Humidity: ");
  Serial.print(h);
  Serial.print(" %  |  Temperature: ");
  Serial.print(t);
  Serial.print(" °C  ");
  Serial.print(f);
  Serial.print(" °F  |  Heat Index: ");
  Serial.print(hic);
  Serial.println(" °C");
}
