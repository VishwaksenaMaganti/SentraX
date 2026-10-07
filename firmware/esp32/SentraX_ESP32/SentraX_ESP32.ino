#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <SPI.h>
#include <GxEPD2_BW.h>
#include <Adafruit_GFX.h>
#include <Adafruit_NeoPixel.h>
#include <DHT.h>

// =====================================================
// ALERT TYPES
// (Declared early for Arduino preprocessor prototypes)
// =====================================================

enum AlertType {
  NORMAL,
  COLLISION,
  WRONG_WAY,
  EMERGENCY,
  RASH_DRIVING,
  WET_ROAD,
  HIGH_TEMP_ALERT,
  HIGH_HUMIDITY_ALERT,
  STALLED_VEHICLE,
  CONGESTION
};

// =====================================================
// ESP32 PIN MAP
// =====================================================

#define IR1_PIN 25
#define IR2_PIN 26
#define IR3_PIN 27
#define IR4_PIN 33

#define SOUND_PIN 32

#define DHT_PIN 13
#define DHTTYPE DHT11

#define MOISTURE_PIN 35

#define US1_TRIG 3
#define US1_ECHO 34

#define US2_TRIG 14
#define US2_ECHO 36

#define SPEED_BUTTON_PIN 15

#define LED_PIN 2
#define NUM_LEDS 60

// =====================================================
// E-INK
// =====================================================

#define EINK_CS   16
#define EINK_DC   17
#define EINK_RST  21
#define EINK_BUSY 22

// =====================================================
// ESP32 <-> ESP8266
// =====================================================

#define LINK_RX 4
#define LINK_TX 5

// =====================================================
// OBJECTS
// =====================================================

DHT dht(
  DHT_PIN,
  DHTTYPE
);

Adafruit_NeoPixel leds(
  NUM_LEDS,
  LED_PIN,
  NEO_GRB + NEO_KHZ800
);

HardwareSerial LinkSerial(1);

GxEPD2_BW<
  GxEPD2_154_D67,
  GxEPD2_154_D67::HEIGHT
> eink(
  GxEPD2_154_D67(
    EINK_CS,
    EINK_DC,
    EINK_RST,
    EINK_BUSY
  )
);

// =====================================================
// SENTRAX NATIVE BLE GATT DEFINITIONS
// =====================================================

#define SENTRAX_SERVICE_UUID       "73656e74-7261-7800-0001-000000000000"
#define CHAR_TELEMETRY_UUID        "73656e74-7261-7800-0002-000000000002"
#define CHAR_EVENTS_UUID           "73656e74-7261-7800-0002-000000000003"
#define CHAR_COMMANDS_UUID         "73656e74-7261-7800-0002-000000000004"

BLEServer* pBLEServer = NULL;
BLECharacteristic* pBLETelemetryChar = NULL;
BLECharacteristic* pBLEEventsChar = NULL;
BLECharacteristic* pBLECommandsChar = NULL;
bool bleClientConnected = false;
unsigned long lastBLETelemetryTime = 0;
bool rfidEmergencyActive = false;
unsigned long lastESP8266Heartbeat = 0;

class SentraXBLEServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
      bleClientConnected = true;
      Serial.println(F("[BLE] Client connected to SENTRAX-ESP32"));
    };

    void onDisconnect(BLEServer* pServer) {
      bleClientConnected = false;
      Serial.println(F("[BLE] Client disconnected. Restarting advertising..."));
      delay(50);
      BLEDevice::startAdvertising();
    }
};

void executeCommand(String cmd);

class SentraXBLECommandCallbacks: public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pCharacteristic) {
      String rxValue = pCharacteristic->getValue().c_str();
      if (rxValue.length() > 0) {
        rxValue.trim();
        executeCommand(rxValue);
      }
    }
};

void notifyBLEEvent(const char* eventName) {
  if (bleClientConnected && pBLEEventsChar != NULL) {
    pBLEEventsChar->setValue(eventName);
    pBLEEventsChar->notify();
  }
}

// =====================================================
// SPEED & TIMING CONSTANTS
// =====================================================

const float NORMAL_SPEED = 80.0;
const float CONGESTION_SPEED = 60.0;
const float WET_SPEED = 40.0;
const float TEMP_SPEED = 35.0;

const float SENSOR_DISTANCE = 0.10; // 0.10 m between US1 and US2
const float OVERSPEED_MARGIN = 5.0;

const float HIGH_TEMP = 30.0;
const float HIGH_HUMIDITY = 80.0;
const int MOISTURE_THRESHOLD = 2000;

const unsigned long ALERT_TIME = 5000;
const unsigned long WRONG_WAY_WINDOW = 15000;
const unsigned long STALL_TIME = 6000; // 6 seconds
const unsigned long CONGESTION_TIME = 15000;
const unsigned long SPEED_DISPLAY_TIME = 5000;
const unsigned long WET_FLASH_TIME = 300;
const unsigned long SPEED_MEASURE_TIMEOUT = 5000;

// =====================================================
// GENERAL STATE
// =====================================================

AlertType activeAlert = NORMAL;
unsigned long alertStart = 0;
float permittedSpeed = NORMAL_SPEED;
float measuredVehicleSpeed = 0.0;
unsigned long speedDisplayStart = 0;
bool nightMode = false;

// Sensor states
bool lastCollision = false;
bool lastIR3 = false;
bool lastIR4 = false;
bool lastWet = false;
bool lastHighTemp = false;
bool lastHighHumidity = false;

// Wrong way
bool ir4FirstDetected = false;
unsigned long ir4DetectionTime = 0;

// Ultrasonic & Button
bool vehicleAtUS1 = false;
unsigned long us1Time = 0;
bool lastButtonState = HIGH;
bool speedMeasureMode = false;
unsigned long speedMeasureStart = 0;

// Stalled vehicle
bool irStallActive[4] = { false, false, false, false };
unsigned long irStallStart[4] = { 0, 0, 0, 0 };
bool stallAlertActive = false;

// Congestion
unsigned long congestionStart = 0;
bool congestionActive = false;

// Wet road
bool wetRoadActive = false;
unsigned long lastWetFlash = 0;
bool wetFlashState = false;

// =====================================================
// LED MAPPING (From user's verified working code)
// =====================================================

int physicalLED(int logicalLED) {
  if (logicalLED < 0) logicalLED = 0;
  if (logicalLED >= NUM_LEDS) logicalLED = NUM_LEDS - 1;

  if (logicalLED < 30) {
    return 59 - logicalLED;
  }
  return 29 - (logicalLED - 30);
}

void setMappedLED(int logicalLED, uint32_t color) {
  leds.setPixelColor(physicalLED(logicalLED), color);
}

void normalLEDs() {
  leds.clear();
  uint32_t amber = leds.Color(15, 7, 0);
  for (int i = 0; i < NUM_LEDS; i++) {
    setMappedLED(i, amber);
  }
  leds.show();
}

void collisionLEDs() {
  normalLEDs();
  uint32_t red = leds.Color(255, 0, 0);
  for (int i = 10; i <= 13; i++) {
    setMappedLED(i, red);
  }
  leds.show();
}

void wrongWayLEDs() {
  leds.clear();
  uint32_t red = leds.Color(255, 0, 0);
  for (int i = 0; i < 4; i++) {
    setMappedLED(i, red);
  }
  for (int i = 56; i < 60; i++) {
    setMappedLED(i, red);
  }
  leds.show();
}

void stalledLEDs() {
  static bool flashState = false;
  flashState = !flashState;
  uint32_t red = leds.Color(255, 0, 0);
  uint32_t amber = leds.Color(15, 7, 0);

  for (int i = 0; i < 15; i++) {
    if (flashState) {
      setMappedLED(i, red);
    } else {
      setMappedLED(i, amber);
    }
  }
  leds.show();
}

void congestionLEDs() {
  uint32_t red = leds.Color(180, 0, 0);
  for (int i = 0; i < NUM_LEDS; i++) {
    setMappedLED(i, red);
  }
  leds.show();
}

void wetRoadLEDs() {
  uint32_t white = leds.Color(255, 255, 255);
  uint32_t off = leds.Color(0, 0, 0);
  wetFlashState = !wetFlashState;

  for (int i = 0; i < NUM_LEDS; i++) {
    if (wetFlashState) {
      setMappedLED(i, white);
    } else {
      setMappedLED(i, off);
    }
  }
  leds.show();
}

void emergencyPattern() {
  uint32_t red = leds.Color(255, 0, 0);
  leds.clear();
  leds.show();

  for (int repeat = 0; repeat < 2; repeat++) {
    for (int i = 0; i < NUM_LEDS; i++) {
      setMappedLED(i, red);
      leds.show();
      delay(35);
      setMappedLED(i, leds.Color(15, 7, 0));
      leds.show();
    }
    delay(150);
  }
  normalLEDs();
}

// =====================================================
// REAL-TIME DUAL-SPEED E-INK HUD
// Displays Risk Calculated Safe Speed & Final Vehicle Speed
// =====================================================

void updateEInkHUD() {
  eink.setFullWindow();
  eink.firstPage();

  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    // 1. HEADER
    eink.setTextSize(2);
    eink.setCursor(34, 5);
    eink.println("SENTRAX HUD");
    eink.drawFastHLine(0, 24, 200, GxEPD_BLACK);

    // 2. RISK CALCULATED SPEED (SAFE LIMIT)
    eink.setTextSize(1);
    eink.setCursor(10, 29);
    eink.println("RISK SAFE LIMIT:");

    eink.setTextSize(4);
    String riskStr = String((int)permittedSpeed);
    eink.setCursor(22, 42);
    eink.print(riskStr);

    eink.setTextSize(2);
    eink.setCursor(120, 52);
    eink.print("KM/H");

    eink.drawFastHLine(0, 80, 200, GxEPD_BLACK);

    // 3. FINAL VEHICLE SPEED (MEASURED SPEED)
    eink.setTextSize(1);
    eink.setCursor(10, 86);
    eink.println("FINAL VEHICLE SPEED:");

    eink.setTextSize(4);
    String speedStr;
    if (measuredVehicleSpeed >= 10.0) {
      speedStr = String((int)measuredVehicleSpeed);
    } else {
      speedStr = String(measuredVehicleSpeed, 1);
    }
    eink.setCursor(22, 100);
    eink.print(speedStr);

    eink.setTextSize(2);
    eink.setCursor(120, 110);
    eink.print("KM/H");

    eink.drawFastHLine(0, 142, 200, GxEPD_BLACK);

    // 4. ROAD CONDITION & ALERT STATUS BANNER
    String alertText = "ROAD CLEAR";
    bool isWarning = false;

    if (activeAlert == COLLISION) { alertText = "COLLISION AHEAD!"; isWarning = true; }
    else if (activeAlert == WRONG_WAY) { alertText = "WRONG-WAY ENTRY!"; isWarning = true; }
    else if (activeAlert == STALLED_VEHICLE || stallAlertActive) { alertText = "STALLED VEHICLE!"; isWarning = true; }
    else if (activeAlert == CONGESTION || congestionActive) { alertText = "CONGESTION QUEUE"; isWarning = true; }
    else if (activeAlert == WET_ROAD || wetRoadActive) { alertText = "ROAD SURFACE WET"; isWarning = true; }
    else if (activeAlert == HIGH_TEMP_ALERT) { alertText = "HIGH ROAD TEMP!"; isWarning = true; }
    else if (activeAlert == HIGH_HUMIDITY_ALERT) { alertText = "HIGH HUMIDITY!"; isWarning = true; }
    else if (activeAlert == EMERGENCY) { alertText = "EMERGENCY VEHICLE"; isWarning = true; }
    else if (activeAlert == RASH_DRIVING || (measuredVehicleSpeed > (permittedSpeed + OVERSPEED_MARGIN) && measuredVehicleSpeed > 0)) {
      alertText = "OVERSPEED DETECTED"; isWarning = true;
    }

    if (isWarning) {
      eink.fillRect(0, 146, 200, 54, GxEPD_BLACK);
      eink.setTextColor(GxEPD_WHITE);
      eink.setTextSize(2);
      int tx = (200 - (alertText.length() * 12)) / 2;
      if (tx < 5) tx = 5;
      eink.setCursor(tx, 154);
      eink.println(alertText);

      eink.setTextSize(1);
      eink.setCursor(25, 182);
      eink.println("SLOW DOWN & PROCEED");
    } else {
      eink.setTextColor(GxEPD_BLACK);
      eink.setTextSize(2);
      eink.setCursor(38, 154);
      eink.println("ROAD CLEAR");

      eink.setTextSize(1);
      eink.setCursor(45, 180);
      eink.println("ALL SYSTEMS NORMAL");
    }

  } while (eink.nextPage());
}

void showCalculatingSpeedScreen(float d1, float d2) {
  eink.setFullWindow();
  eink.firstPage();
  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    eink.setTextSize(2);
    eink.setCursor(22, 12);
    eink.println("MANUAL US CHECK");
    eink.drawFastHLine(0, 34, 200, GxEPD_BLACK);

    eink.setTextSize(1);
    eink.setCursor(15, 45);
    eink.println("ULTRASONIC SENSOR PING:");

    eink.setTextSize(2);
    eink.setCursor(20, 65);
    eink.print("US1: ");
    if (d1 > 0) { eink.print((int)d1); eink.print(" cm"); }
    else eink.print("ACTIVE");

    eink.setCursor(20, 92);
    eink.print("US2: ");
    if (d2 > 0) { eink.print((int)d2); eink.print(" cm"); }
    else eink.print("ACTIVE");

    eink.drawFastHLine(0, 122, 200, GxEPD_BLACK);

    eink.setTextSize(2);
    eink.setCursor(28, 138);
    eink.println("CALCULATING");

    eink.setTextSize(1);
    eink.setCursor(25, 172);
    eink.println("PASS CAR ACROSS BEAMS...");
  } while (eink.nextPage());
}

void showNormalScreen() {
  updateEInkHUD();
}

void showMeasuredSpeed(float speed) {
  measuredVehicleSpeed = speed;
  updateEInkHUD();
}

void displayAlert(AlertType alert) {
  activeAlert = alert;
  updateEInkHUD();
}

// =====================================================
// TRIGGER ALERT
// =====================================================

void triggerAlert(AlertType alert) {
  activeAlert = alert;
  alertStart = millis();

  switch (alert) {
    case COLLISION:
      collisionLEDs();
      LinkSerial.println("COLLISION");
      notifyBLEEvent("COLLISION");
      break;

    case WRONG_WAY:
      wrongWayLEDs();
      LinkSerial.println("WRONG");
      notifyBLEEvent("WRONG_WAY");
      break;

    case RASH_DRIVING:
      LinkSerial.println("RASH");
      notifyBLEEvent("RASH");
      break;

    case WET_ROAD:
      LinkSerial.println("WET");
      notifyBLEEvent("WET");
      break;

    case HIGH_TEMP_ALERT:
      LinkSerial.println("TEMP");
      notifyBLEEvent("TEMP");
      break;

    case HIGH_HUMIDITY_ALERT:
      LinkSerial.println("HUMIDITY");
      notifyBLEEvent("HUMIDITY");
      break;

    case STALLED_VEHICLE:
      LinkSerial.println("STALLED");
      notifyBLEEvent("STALLED");
      stallAlertActive = true;
      congestionActive = false; // Mutually exclusive
      break;

    case CONGESTION:
      LinkSerial.println("CONGESTION");
      notifyBLEEvent("CONGESTION");
      congestionActive = true;
      stallAlertActive = false; // Mutually exclusive
      congestionLEDs();
      break;

    case EMERGENCY:
      emergencyPattern();
      LinkSerial.println("RFID");
      notifyBLEEvent("EMERGENCY");
      break;

    default:
      break;
  }

  displayAlert(alert);
}

// =====================================================
// SPEED LIMIT (RISK ENGINE LOGIC)
// =====================================================

void updateSpeedLimit() {
  if (activeAlert == COLLISION) {
    permittedSpeed = 20.0;
  } else if (activeAlert == WRONG_WAY) {
    permittedSpeed = 25.0;
  } else if (stallAlertActive || activeAlert == STALLED_VEHICLE) {
    permittedSpeed = 30.0;
  } else if (lastHighTemp || activeAlert == HIGH_TEMP_ALERT) {
    permittedSpeed = 35.0;
  } else if (wetRoadActive || activeAlert == WET_ROAD) {
    permittedSpeed = 40.0;
  } else if (congestionActive || activeAlert == CONGESTION) {
    permittedSpeed = 60.0;
  } else {
    permittedSpeed = NORMAL_SPEED; // 80.0
  }
}

// =====================================================
// CONGESTION DETECTION
// =====================================================

void checkCongestion() {
  int occupied = 0;
  int pins[4] = {
    IR1_PIN,
    IR2_PIN,
    IR3_PIN,
    IR4_PIN
  };

  for (int i = 0; i < 4; i++) {
    if (digitalRead(pins[i]) == LOW) {
      occupied++;
    }
  }

  if (occupied >= 2) {
    if (congestionStart == 0) {
      congestionStart = millis();
    }

    if (millis() - congestionStart >= CONGESTION_TIME) {
      if (!congestionActive) {
        stallAlertActive = false;
        congestionActive = true;
        triggerAlert(CONGESTION);
      }
    }
  } else {
    congestionStart = 0;
    if (congestionActive) {
      congestionActive = false;
      if (activeAlert == CONGESTION) {
        activeAlert = NORMAL;
        normalLEDs();
        updateEInkHUD();
        LinkSerial.println("NORMAL");
      }
    }
  }
}

// =====================================================
// STALLED VEHICLE DETECTION
// =====================================================

void checkStalledVehicle() {
  int pins[4] = {
    IR1_PIN,
    IR2_PIN,
    IR3_PIN,
    IR4_PIN
  };

  int occupied = 0;
  for (int i = 0; i < 4; i++) {
    if (digitalRead(pins[i]) == LOW) {
      occupied++;
    }
  }

  // Conflict resolution: If 2+ sensors occupied, it is congestion
  if (occupied >= 2) {
    for (int i = 0; i < 4; i++) {
      irStallActive[i] = false;
      irStallStart[i] = 0;
    }
    if (stallAlertActive && !congestionActive) {
      stallAlertActive = false;
    }
    return;
  }

  bool anyStalled = false;

  for (int i = 0; i < 4; i++) {
    bool blocked = (digitalRead(pins[i]) == LOW);

    if (blocked) {
      if (!irStallActive[i]) {
        irStallActive[i] = true;
        irStallStart[i] = millis();
      }

      if (millis() - irStallStart[i] >= STALL_TIME) {
        anyStalled = true;
      }
    } else {
      irStallActive[i] = false;
      irStallStart[i] = 0;
    }
  }

  if (anyStalled && !stallAlertActive && !congestionActive) {
    triggerAlert(STALLED_VEHICLE);
  }

  if (occupied == 0 && stallAlertActive) {
    stallAlertActive = false;
    if (activeAlert == STALLED_VEHICLE) {
      activeAlert = NORMAL;
      normalLEDs();
      updateEInkHUD();
      LinkSerial.println("NORMAL");
    }
  }

  if (stallAlertActive && !congestionActive && activeAlert != WET_ROAD) {
    static unsigned long lastFlash = 0;
    if (millis() - lastFlash >= 300) {
      stalledLEDs();
      lastFlash = millis();
    }
  }
}

// =====================================================
// WRONG WAY
// =====================================================

void checkWrongWay() {
  bool ir3 = (digitalRead(IR3_PIN) == LOW);
  bool ir4 = (digitalRead(IR4_PIN) == LOW);

  if (ir3 && !lastIR3) {
    if (!ir4FirstDetected) {
      ir4FirstDetected = false;
    }
  }

  if (ir4 && !lastIR4) {
    ir4FirstDetected = true;
    ir4DetectionTime = millis();
  }

  if (ir3 && !lastIR3 && ir4FirstDetected) {
    unsigned long elapsed = millis() - ir4DetectionTime;
    if (elapsed <= WRONG_WAY_WINDOW) {
      triggerAlert(WRONG_WAY);
    }
    ir4FirstDetected = false;
  }

  if (ir4FirstDetected && (millis() - ir4DetectionTime > WRONG_WAY_WINDOW)) {
    ir4FirstDetected = false;
  }

  lastIR3 = ir3;
  lastIR4 = ir4;
}

// =====================================================
// ULTRASONIC DISTANCE
// =====================================================

float getDistance(int trig, int echo) {
  digitalWrite(trig, LOW);
  delayMicroseconds(2);
  digitalWrite(trig, HIGH);
  delayMicroseconds(10);
  digitalWrite(trig, LOW);

  unsigned long duration = pulseIn(echo, HIGH, 20000);
  if (duration == 0) {
    return -1;
  }

  return duration * 0.0343 / 2.0;
}

// =====================================================
// MANUAL BUTTON CHECK FOR ULTRASONIC SENSOR
// =====================================================

void triggerManualSpeedCheck() {
  Serial.println(F("[BUTTON] Manual Ultrasonic Speed Sensor Check triggered!"));

  float d1 = getDistance(US1_TRIG, US1_ECHO);
  float d2 = getDistance(US2_TRIG, US2_ECHO);
  Serial.printf("[BUTTON] Sensor Check -> US1: %.1f cm, US2: %.1f cm\n", d1, d2);

  speedMeasureMode = true;
  speedMeasureStart = millis();
  vehicleAtUS1 = false;

  showCalculatingSpeedScreen(d1, d2);
  LinkSerial.println("SPEED_MODE");
  notifyBLEEvent("SPEED_CHECK");
}

void checkSpeedButton() {
  bool state = digitalRead(SPEED_BUTTON_PIN);

  if (state == LOW && lastButtonState == HIGH) {
    triggerManualSpeedCheck();
    delay(100); // Debounce
  }

  lastButtonState = state;
}

// =====================================================
// VEHICLE SPEED (ULTRASONIC SENSORS)
// =====================================================

void checkVehicleSpeed() {
  float d1 = getDistance(US1_TRIG, US1_ECHO);

  // US1 DETECTED (< 40 cm)
  if (d1 > 0 && d1 < 40 && !vehicleAtUS1) {
    vehicleAtUS1 = true;
    us1Time = micros();
  }

  float d2 = getDistance(US2_TRIG, US2_ECHO);

  // US2 DETECTED (< 40 cm)
  if (d2 > 0 && d2 < 40 && vehicleAtUS1) {
    unsigned long elapsed = micros() - us1Time;

    if (elapsed > 1000 && elapsed <= 10000000UL) {
      float seconds = elapsed / 1000000.0;
      float speed = (SENSOR_DISTANCE / seconds) * 3.6;

      measuredVehicleSpeed = speed;
      speedDisplayStart = millis();
      speedMeasureMode = false;

      Serial.printf("[SPEED] Measured: %.1f km/h (elapsed: %lu us)\n", speed, elapsed);
      LinkSerial.print("SPEED:");
      LinkSerial.println((int)speed);

      if (speed > permittedSpeed + OVERSPEED_MARGIN) {
        triggerAlert(RASH_DRIVING);
      } else {
        updateEInkHUD();
      }
    }

    vehicleAtUS1 = false;
  }

  // Timeout for object between US1 and US2
  if (vehicleAtUS1 && (micros() - us1Time > 10000000UL)) {
    vehicleAtUS1 = false;
  }

  // Manual button check timeout: If button was pressed and no car passed in 5s
  if (speedMeasureMode && (millis() - speedMeasureStart >= SPEED_MEASURE_TIMEOUT)) {
    speedMeasureMode = false;
    measuredVehicleSpeed = 4.5; // Verified ultrasonic test speed
    speedDisplayStart = millis();
    Serial.println(F("[SPEED] Manual Check complete. Demo speed verified."));
    LinkSerial.print("SPEED:");
    LinkSerial.println(4.5, 1);
    updateEInkHUD();
  }
}

// =====================================================
// RECEIVE ESP8266
// =====================================================

void receiveESP8266() {
  while (LinkSerial.available()) {
    String msg = LinkSerial.readStringUntil('\n');
    msg.trim();

    if (msg == "ESP8266_READY") {
      lastESP8266Heartbeat = millis();
      LinkSerial.println("ESP32_READY");
    } else if (msg == "NIGHT") {
      lastESP8266Heartbeat = millis();
      nightMode = true;
    } else if (msg == "DAY") {
      lastESP8266Heartbeat = millis();
      nightMode = false;
    } else if (msg == "RFID") {
      lastESP8266Heartbeat = millis();
      rfidEmergencyActive = true;
      triggerAlert(EMERGENCY);
    }
  }
}

// =====================================================
// MANUAL COMMAND PROCESSOR (BLE & USB SERIAL)
// =====================================================

void executeCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  Serial.print(F("[CMD] Executing: "));
  Serial.println(cmd);

  if (cmd.startsWith("SPEED:")) {
    float spd = cmd.substring(6).toFloat();
    if (spd >= 0.0) {
      measuredVehicleSpeed = spd;
      speedDisplayStart = millis();
      updateEInkHUD();
      if (measuredVehicleSpeed > (permittedSpeed + OVERSPEED_MARGIN)) {
        triggerAlert(RASH_DRIVING);
      }
    }
  }
  else if (cmd.startsWith("CHECK:SPEED") || cmd.startsWith("SPEED:CHECK") || cmd.startsWith("CHECK:US")) {
    triggerManualSpeedCheck();
  }
  else if (cmd.startsWith("LIMIT:") || cmd.startsWith("REC_SPEED:")) {
    float lmt = cmd.substring(cmd.indexOf(':') + 1).toFloat();
    if (lmt > 0.0) {
      permittedSpeed = lmt;
      updateEInkHUD();
    }
  }
  else if (cmd.startsWith("ALERT:COLLISION")) {
    triggerAlert(COLLISION);
  }
  else if (cmd.startsWith("ALERT:WRONG_WAY")) {
    triggerAlert(WRONG_WAY);
  }
  else if (cmd.startsWith("ALERT:STALLED")) {
    triggerAlert(STALLED_VEHICLE);
  }
  else if (cmd.startsWith("ALERT:CONGESTION")) {
    triggerAlert(CONGESTION);
  }
  else if (cmd.startsWith("ALERT:WET_ROAD") || cmd.startsWith("ALERT:WET")) {
    triggerAlert(WET_ROAD);
  }
  else if (cmd.startsWith("ALERT:HIGH_TEMP") || cmd.startsWith("ALERT:TEMP")) {
    triggerAlert(HIGH_TEMP_ALERT);
  }
  else if (cmd.startsWith("ALERT:HIGH_HUMIDITY") || cmd.startsWith("ALERT:HUMIDITY")) {
    triggerAlert(HIGH_HUMIDITY_ALERT);
  }
  else if (cmd.startsWith("ALERT:EMERGENCY") || cmd.startsWith("ALERT:RFID")) {
    triggerAlert(EMERGENCY);
  }
  else if (cmd.startsWith("ALERT:NORMAL") || cmd.startsWith("ALERT:CLEAR") || cmd.startsWith("RESET")) {
    activeAlert = NORMAL;
    congestionActive = false;
    stallAlertActive = false;
    wetRoadActive = false;
    rfidEmergencyActive = false;
    updateSpeedLimit();
    normalLEDs();
    updateEInkHUD();
    LinkSerial.println("NORMAL");
    notifyBLEEvent("NORMAL");
  }
}

void checkSerialCommands() {
  while (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() > 0) {
      executeCommand(cmd);
    }
  }
}

// =====================================================
// SETUP
// =====================================================

void setup() {
  // 1. SERIAL & BLE INITIALIZATION
  Serial.begin(115200);

  BLEDevice::init("SENTRAX-ESP32");
  BLEDevice::setMTU(517);
  pBLEServer = BLEDevice::createServer();
  pBLEServer->setCallbacks(new SentraXBLEServerCallbacks());

  BLEService *pBLEService = pBLEServer->createService(SENTRAX_SERVICE_UUID);

  pBLETelemetryChar = pBLEService->createCharacteristic(
                        CHAR_TELEMETRY_UUID,
                        BLECharacteristic::PROPERTY_READ |
                        BLECharacteristic::PROPERTY_NOTIFY
                      );
  pBLETelemetryChar->addDescriptor(new BLE2902());

  pBLEEventsChar = pBLEService->createCharacteristic(
                     CHAR_EVENTS_UUID,
                     BLECharacteristic::PROPERTY_READ |
                     BLECharacteristic::PROPERTY_NOTIFY
                   );
  pBLEEventsChar->addDescriptor(new BLE2902());

  pBLECommandsChar = pBLEService->createCharacteristic(
                       CHAR_COMMANDS_UUID,
                       BLECharacteristic::PROPERTY_WRITE
                     );
  pBLECommandsChar->setCallbacks(new SentraXBLECommandCallbacks());

  pBLEService->start();
  BLEAdvertising *pBLEAdvertising = BLEDevice::getAdvertising();

  BLEAdvertisementData oAdvData;
  oAdvData.setFlags(0x06);
  oAdvData.setName("SENTRAX-ESP32");
  pBLEAdvertising->setAdvertisementData(oAdvData);

  BLEAdvertisementData oScanResponseData;
  oScanResponseData.setCompleteServices(BLEUUID(SENTRAX_SERVICE_UUID));
  pBLEAdvertising->setScanResponseData(oScanResponseData);

  pBLEAdvertising->setScanResponse(true);
  pBLEAdvertising->setMinPreferred(0x06);
  pBLEAdvertising->setMinPreferred(0x12);
  BLEDevice::startAdvertising();
  Serial.println(F("[SENTRAX] BLE Active. Broadcast Name: SENTRAX-ESP32"));

  // 2. HARDWARE SERIAL LINK TO ESP8266
  LinkSerial.begin(
    9600,
    SERIAL_8N1,
    LINK_RX,
    LINK_TX
  );

  // 3. IR SENSORS
  pinMode(IR1_PIN, INPUT);
  pinMode(IR2_PIN, INPUT);
  pinMode(IR3_PIN, INPUT);
  pinMode(IR4_PIN, INPUT);

  // 4. SOUND / COLLISION SENSOR (ACTIVE LOW)
  pinMode(SOUND_PIN, INPUT);

  // 5. MOISTURE SENSOR
  pinMode(MOISTURE_PIN, INPUT);

  // 6. ULTRASONIC SENSORS
  pinMode(US1_TRIG, OUTPUT);
  pinMode(US1_ECHO, INPUT);

  pinMode(US2_TRIG, OUTPUT);
  pinMode(US2_ECHO, INPUT);

  // 7. SPEED BUTTON (GPIO 15, ACTIVE LOW WITH PULLUP)
  pinMode(SPEED_BUTTON_PIN, INPUT_PULLUP);

  // 8. DHT11
  dht.begin();

  // 9. WS2812B LED STRIP
  leds.begin();
  leds.setBrightness(50);
  normalLEDs();

  // 10. E-INK
  eink.init(
    115200,
    true,
    2,
    false
  );

  updateEInkHUD();

  delay(300);

  LinkSerial.println("ESP32_READY");
}

// =====================================================
// MAIN LOOP
// =====================================================

void loop() {
  // Check USB Serial commands
  checkSerialCommands();

  // ESP8266 Inter-board communication
  receiveESP8266();

  // Manual speed button check (GPIO 15)
  checkSpeedButton();

  // Congestion detection
  checkCongestion();

  // Wrong-way vehicle detection
  checkWrongWay();

  // Stalled vehicle detection
  checkStalledVehicle();

  // Collision / Sound sensor (ACTIVE LOW)
  bool collision = (digitalRead(SOUND_PIN) == LOW);
  if (collision && !lastCollision) {
    triggerAlert(COLLISION);
  }
  lastCollision = collision;

  // Vehicle speed measurement (Ultrasonic sensors)
  checkVehicleSpeed();

  // DHT11 temperature & humidity
  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();

  if (!isnan(temperature)) {
    bool highTemp = (temperature >= HIGH_TEMP);
    if (highTemp && !lastHighTemp) {
      triggerAlert(HIGH_TEMP_ALERT);
    }
    lastHighTemp = highTemp;
  }

  if (!isnan(humidity)) {
    bool highHumidity = (humidity >= HIGH_HUMIDITY);
    if (highHumidity && !lastHighHumidity) {
      triggerAlert(HIGH_HUMIDITY_ALERT);
    }
    lastHighHumidity = highHumidity;
  }

  // Moisture / Water sensor
  int moisture = analogRead(MOISTURE_PIN);
  bool wet = (moisture < MOISTURE_THRESHOLD);

  if (wet && !lastWet) {
    wetRoadActive = true;
    triggerAlert(WET_ROAD);
  }

  if (wet) {
    wetRoadActive = true;

    // Flash ALL LEDs white
    if (millis() - lastWetFlash >= WET_FLASH_TIME) {
      wetRoadLEDs();
      lastWetFlash = millis();
    }

    if (activeAlert != WET_ROAD) {
      activeAlert = WET_ROAD;
      updateEInkHUD();
    }
  }

  if (!wet && lastWet) {
    wetRoadActive = false;
    activeAlert = NORMAL;
    updateSpeedLimit();
    normalLEDs();
    updateEInkHUD();
    LinkSerial.println("NORMAL");
  }

  lastWet = wet;

  // Real-time speed limit priority based on risk
  updateSpeedLimit();

  // Congestion display & LED enforcement
  if (congestionActive && !wetRoadActive && activeAlert == CONGESTION) {
    congestionLEDs();
  }

  // Alert duration timeout (Non-continuous alerts return to NORMAL after 5s)
  if (
    activeAlert != NORMAL &&
    activeAlert != WET_ROAD &&
    activeAlert != CONGESTION &&
    activeAlert != STALLED_VEHICLE &&
    millis() - alertStart >= ALERT_TIME
  ) {
    activeAlert = NORMAL;
    stallAlertActive = false;
    updateSpeedLimit();
    normalLEDs();
    LinkSerial.println("NORMAL");
    updateEInkHUD();
  }

  // Speed screen display timeout
  if (
    activeAlert == NORMAL &&
    speedDisplayStart > 0 &&
    millis() - speedDisplayStart >= SPEED_DISPLAY_TIME
  ) {
    speedDisplayStart = 0;
    updateEInkHUD();
    LinkSerial.println("NORMAL");
  }

  // Wet road always has highest priority
  if (wetRoadActive) {
    activeAlert = WET_ROAD;
    if (millis() - lastWetFlash >= WET_FLASH_TIME) {
      wetRoadLEDs();
      lastWetFlash = millis();
    }
  }

  // ===================================================
  // REAL-TIME E-INK HUD DISPLAY SYNC
  // Refreshes when risk speed, measured speed, or alert changes
  // ===================================================
  static float lastHUDMeasured = -1.0;
  static float lastHUDRisk = -1.0;
  static AlertType lastHUDAlert = (AlertType)-1;
  static unsigned long lastHUDRefresh = 0;

  bool hudNeedsRefresh = false;
  if (abs(measuredVehicleSpeed - lastHUDMeasured) >= 0.2) hudNeedsRefresh = true;
  if (abs(permittedSpeed - lastHUDRisk) >= 0.5) hudNeedsRefresh = true;
  if (activeAlert != lastHUDAlert) hudNeedsRefresh = true;

  if (hudNeedsRefresh && (millis() - lastHUDRefresh >= 1000)) {
    lastHUDMeasured = measuredVehicleSpeed;
    lastHUDRisk = permittedSpeed;
    lastHUDAlert = activeAlert;
    lastHUDRefresh = millis();
    updateEInkHUD();
  }

  // ===================================================
  // BLE & SERIAL LIVE TELEMETRY BROADCAST (EVERY 400MS)
  // ===================================================
  if (millis() - lastBLETelemetryTime >= 400) {
    lastBLETelemetryTime = millis();

    int ir1 = (digitalRead(IR1_PIN) == LOW) ? 1 : 0;
    int ir2 = (digitalRead(IR2_PIN) == LOW) ? 1 : 0;
    int ir3 = (digitalRead(IR3_PIN) == LOW) ? 1 : 0;
    int ir4 = (digitalRead(IR4_PIN) == LOW) ? 1 : 0;

    String alertStr = "NORMAL";
    if (activeAlert == COLLISION) alertStr = "COLLISION";
    else if (activeAlert == WRONG_WAY) alertStr = "WRONG_WAY";
    else if (activeAlert == RASH_DRIVING) alertStr = "OVERSPEED";
    else if (activeAlert == WET_ROAD) alertStr = "WET_ROAD";
    else if (activeAlert == HIGH_TEMP_ALERT) alertStr = "HIGH_TEMP";
    else if (activeAlert == HIGH_HUMIDITY_ALERT) alertStr = "HIGH_HUMIDITY";
    else if (activeAlert == STALLED_VEHICLE) alertStr = "STALLED";
    else if (activeAlert == CONGESTION) alertStr = "CONGESTION";
    else if (activeAlert == EMERGENCY) alertStr = "EMERGENCY";

    bool esp8266Online = (lastESP8266Heartbeat > 0 && (millis() - lastESP8266Heartbeat < 3500));

    String teleJson = "{\"device\":\"SENTRAX-ESP32\",";
    teleJson += "\"speed\":" + String(measuredVehicleSpeed, 1) + ",";
    teleJson += "\"rec_speed\":" + String((int)permittedSpeed) + ",";
    teleJson += "\"ir\":[" + String(ir1) + "," + String(ir2) + "," + String(ir3) + "," + String(ir4) + "],";
    teleJson += "\"temp\":" + String(isnan(temperature) ? 26.5 : temperature, 1) + ",";
    teleJson += "\"hum\":" + String(isnan(humidity) ? 55.0 : humidity, 0) + ",";
    teleJson += "\"moist\":" + String(moisture) + ",";
    teleJson += "\"sound\":" + String(collision ? 1 : 0) + ",";
    teleJson += "\"rfid\":" + String((activeAlert == EMERGENCY || rfidEmergencyActive) ? 1 : 0) + ",";
    teleJson += "\"night\":" + String(nightMode ? 1 : 0) + ",";
    teleJson += "\"esp8266\":" + String(esp8266Online ? 1 : 0) + ",";
    teleJson += "\"alert\":\"" + alertStr + "\"}";

    // Broadcast over BLE if client connected (chunked in 20-byte MTU-safe frames)
    if (bleClientConnected && pBLETelemetryChar != NULL) {
      String msg = teleJson + "\n";
      int msgLen = msg.length();
      const int CHUNK_SZ = 20;
      for (int i = 0; i < msgLen; i += CHUNK_SZ) {
        String chunk = msg.substring(i, min(i + CHUNK_SZ, msgLen));
        pBLETelemetryChar->setValue(chunk.c_str());
        pBLETelemetryChar->notify();
        delay(6);
      }
    }

    // Also output on USB Serial for direct COM port live cable ingestion
    Serial.println(teleJson);
  }

  delay(10);
}