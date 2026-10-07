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
// (Declared at top for Arduino preprocessor prototype scope)
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
// SPEED SETTINGS
// =====================================================

const float NORMAL_SPEED = 80.0;
const float CONGESTION_SPEED = 60.0;
const float WET_SPEED = 40.0;

const float TRAFFIC_SPEED_1 = 70.0;
const float TRAFFIC_SPEED_2 = 60.0;
const float TRAFFIC_SPEED_3 = 50.0;

// Distance between ultrasonic sensors
const float SENSOR_DISTANCE = 0.10;

// Overspeed margin
const float OVERSPEED_MARGIN = 5.0;

// =====================================================
// TEMPERATURE & HUMIDITY
// =====================================================

const float HIGH_TEMP = 30.0;
const float HIGH_HUMIDITY = 80.0;

// =====================================================
// MOISTURE
// =====================================================

const int MOISTURE_THRESHOLD = 2000;

// =====================================================
// TIMERS
// =====================================================

const unsigned long ALERT_TIME = 5000;
const unsigned long WRONG_WAY_WINDOW = 15000;

// Stalled vehicle delay: updated to 6 seconds as requested
const unsigned long STALL_TIME = 6000;

// Congestion delay: 15 seconds continuous 2+ sensor blockage
const unsigned long CONGESTION_TIME = 15000;

const unsigned long SPEED_DISPLAY_TIME = 5000;
const unsigned long WET_FLASH_TIME = 300;

// =====================================================
// GENERAL STATE
// =====================================================

AlertType activeAlert = NORMAL;
unsigned long alertStart = 0;
float permittedSpeed = NORMAL_SPEED;
float measuredVehicleSpeed = 0;
unsigned long speedDisplayStart = 0;
bool nightMode = false;

// =====================================================
// SENSOR STATES
// =====================================================

bool lastCollision = false;
bool lastIR3 = false;
bool lastIR4 = false;
bool lastWet = false;
bool lastHighTemp = false;
bool lastHighHumidity = false;

// =====================================================
// WRONG WAY
// =====================================================

bool ir4FirstDetected = false;
unsigned long ir4DetectionTime = 0;

// =====================================================
// ULTRASONIC
// =====================================================

bool vehicleAtUS1 = false;
unsigned long us1Time = 0;

// =====================================================
// STALLED VEHICLE
// =====================================================

bool irStallActive[4] = { false, false, false, false };
unsigned long irStallStart[4] = { 0, 0, 0, 0 };
bool stallAlertActive = false;

// =====================================================
// CONGESTION
// =====================================================

unsigned long congestionStart = 0;
bool congestionActive = false;

// =====================================================
// WET ROAD
// =====================================================

bool wetRoadActive = false;
unsigned long lastWetFlash = 0;
bool wetFlashState = false;

// =====================================================
// LED MAPPING
// =====================================================
// Physical LEFT  = LEDs 0-29
// Physical RIGHT = LEDs 30-59
// Logical LEFT  -> physical RIGHT (59 - logicalLED)
// Logical RIGHT -> physical LEFT (29 - (logicalLED - 30))
// =====================================================

int physicalLED(int logicalLED) {
  if (logicalLED < 0) {
    logicalLED = 0;
  }
  if (logicalLED >= NUM_LEDS) {
    logicalLED = NUM_LEDS - 1;
  }

  // LOGICAL LEFT -> PHYSICAL RIGHT
  if (logicalLED < 30) {
    return 59 - logicalLED;
  }

  // LOGICAL RIGHT -> PHYSICAL LEFT
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

  // LOGICAL LEFT END
  for (int i = 0; i < 4; i++) {
    setMappedLED(i, red);
  }

  // LOGICAL RIGHT END
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

  // LOGICAL LEFT
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
// E-INK SCREENS
// =====================================================

void showNormalScreen() {
  eink.setFullWindow();
  eink.firstPage();
  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    eink.setTextSize(2);
    eink.setCursor(55, 25);
    eink.println("SENTRAX");

    // BIG SPEED
    eink.setTextSize(8);
    String speedText = String((int)permittedSpeed);
    int width = speedText.length() * 48;
    int x = (200 - width) / 2;
    if (x < 0) x = 0;

    eink.setCursor(x, 110);
    eink.println(speedText);

    eink.setTextSize(2);
    eink.setCursor(65, 140);
    eink.println("KM/H");

    eink.setTextSize(1);
    eink.setCursor(55, 170);
    eink.println("ROAD CLEAR");
  } while (eink.nextPage());
}

void showCongestionScreen() {
  eink.setFullWindow();
  eink.firstPage();
  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    // LARGE WARNING TRIANGLE
    eink.drawTriangle(100, 35, 40, 125, 160, 125, GxEPD_BLACK);

    eink.setTextSize(3);
    eink.setCursor(35, 160);
    eink.println("CONGESTION");

    eink.setTextSize(2);
    eink.setCursor(55, 190);
    eink.print("SPEED ");
    eink.print((int)permittedSpeed);
  } while (eink.nextPage());
}

void showMeasuredSpeed(float speed) {
  eink.setFullWindow();
  eink.firstPage();
  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    eink.setTextSize(2);
    eink.setCursor(35, 25);
    eink.println("VEHICLE SPEED");

    eink.setTextSize(7);
    String s = String((int)speed);
    int width = s.length() * 42;
    int x = (200 - width) / 2;
    if (x < 0) x = 0;

    eink.setCursor(x, 110);
    eink.println(s);

    eink.setTextSize(2);
    eink.setCursor(65, 140);
    eink.println("KM/H");

    eink.setTextSize(1);
    eink.setCursor(40, 170);
    eink.print("LIMIT ");
    eink.print((int)permittedSpeed);
    eink.print(" KM/H");
  } while (eink.nextPage());
}

void showCollisionScreen() {
  eink.setFullWindow();
  eink.firstPage();
  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    eink.drawLine(35, 40, 165, 125, GxEPD_BLACK);
    eink.drawLine(165, 40, 35, 125, GxEPD_BLACK);

    eink.setTextSize(3);
    eink.setCursor(30, 165);
    eink.println("COLLISION");
  } while (eink.nextPage());
}

void showWrongWayScreen() {
  eink.setFullWindow();
  eink.firstPage();
  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    eink.drawLine(100, 125, 100, 45, GxEPD_BLACK);
    eink.drawLine(100, 45, 65, 80, GxEPD_BLACK);
    eink.drawLine(100, 45, 135, 80, GxEPD_BLACK);

    eink.setTextSize(3);
    eink.setCursor(25, 165);
    eink.println("WRONG WAY");
  } while (eink.nextPage());
}

void showRashScreen() {
  eink.setFullWindow();
  eink.firstPage();
  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    // SPEEDOMETER
    eink.drawCircle(100, 80, 42, GxEPD_BLACK);
    eink.drawLine(100, 80, 130, 53, GxEPD_BLACK);

    eink.setTextSize(3);
    eink.setCursor(15, 160);
    eink.println("OVERSPEED!");

    eink.setTextSize(2);
    eink.setCursor(45, 190);
    eink.println("RASH DRIVING");
  } while (eink.nextPage());
}

void showWetScreen() {
  eink.setFullWindow();
  eink.firstPage();
  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    // WATER DROPS
    eink.fillCircle(70, 70, 18, GxEPD_BLACK);
    eink.fillCircle(100, 90, 18, GxEPD_BLACK);
    eink.fillCircle(130, 70, 18, GxEPD_BLACK);

    eink.setTextSize(3);
    eink.setCursor(45, 145);
    eink.println("ROAD WET");

    eink.setTextSize(2);
    eink.setCursor(45, 180);
    eink.println("SPEED 40");
  } while (eink.nextPage());
}

void showHighTempScreen() {
  eink.setFullWindow();
  eink.firstPage();
  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    eink.setTextSize(3);
    eink.setCursor(30, 35);
    eink.println("HIGH TEMP");

    eink.drawCircle(100, 110, 22, GxEPD_BLACK);
    eink.drawLine(100, 50, 100, 110, GxEPD_BLACK);

    eink.setTextSize(2);
    eink.setCursor(65, 160);
    eink.println("SLOW");
  } while (eink.nextPage());
}

void showHumidityScreen() {
  eink.setFullWindow();
  eink.firstPage();
  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    eink.setTextSize(3);
    eink.setCursor(10, 35);
    eink.println("HUMIDITY");

    eink.drawCircle(100, 90, 35, GxEPD_BLACK);

    eink.setTextSize(2);
    eink.setCursor(65, 160);
    eink.println("SLOW");
  } while (eink.nextPage());
}

void showEmergencyScreen() {
  eink.setFullWindow();
  eink.firstPage();
  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    eink.drawLine(40, 45, 160, 125, GxEPD_BLACK);
    eink.drawLine(160, 45, 40, 125, GxEPD_BLACK);

    eink.setTextSize(3);
    eink.setCursor(15, 165);
    eink.println("EMERGENCY");
  } while (eink.nextPage());
}

void showStalledScreen() {
  eink.setFullWindow();
  eink.firstPage();
  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    eink.drawTriangle(100, 40, 45, 130, 155, 130, GxEPD_BLACK);

    eink.setTextSize(3);
    eink.setCursor(20, 165);
    eink.println("VEHICLE STOP");
  } while (eink.nextPage());
}

// =====================================================
// DISPLAY ALERT
// =====================================================

void displayAlert(AlertType alert) {
  switch (alert) {
    case COLLISION:
      showCollisionScreen();
      break;
    case WRONG_WAY:
      showWrongWayScreen();
      break;
    case EMERGENCY:
      showEmergencyScreen();
      break;
    case RASH_DRIVING:
      showRashScreen();
      break;
    case WET_ROAD:
      showWetScreen();
      break;
    case HIGH_TEMP_ALERT:
      showHighTempScreen();
      break;
    case HIGH_HUMIDITY_ALERT:
      showHumidityScreen();
      break;
    case STALLED_VEHICLE:
      showStalledScreen();
      break;
    case CONGESTION:
      showCongestionScreen();
      break;
    default:
      showNormalScreen();
      break;
  }
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
      // White flashing handled continuously
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
      congestionActive = false; // Resolved conflict: Mutually exclusive
      break;

    case CONGESTION:
      LinkSerial.println("CONGESTION");
      notifyBLEEvent("CONGESTION");
      congestionActive = true;
      stallAlertActive = false; // Resolved conflict: Mutually exclusive
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
// CONGESTION DETECTION
// =====================================================
// ANY TWO OR MORE IR SENSORS must remain blocked
// continuously for CONGESTION_TIME (15 seconds).
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

  // ---------------------------------------------------
  // TWO OR MORE VEHICLES / SENSORS ACTIVE -> CONGESTION
  // ---------------------------------------------------
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
        showNormalScreen();
        LinkSerial.println("NORMAL");
      }
    }
  }
}

// =====================================================
// STALLED VEHICLE DETECTION
// =====================================================
// Exactly ONE vehicle blocked continuously for STALL_TIME (6s).
// Resolves conflict: If occupied >= 2, this is CONGESTION,
// so stalled timers are reset and stalled alert does not fire.
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

  // Two or more sensors blocked = Traffic queue / Congestion.
  // Suppress stalled vehicle alert and reset individual stall timers.
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

  // When vehicle clears (sensor becomes unblocked), restore road state
  if (occupied == 0 && stallAlertActive) {
    stallAlertActive = false;
    if (activeAlert == STALLED_VEHICLE) {
      activeAlert = NORMAL;
      normalLEDs();
      showNormalScreen();
      LinkSerial.println("NORMAL");
    }
  }

  // Flash stalled vehicle LEDs (amber/red on left lane)
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
// IR4 -> IR3 = WRONG
// IR3 -> IR4 = NORMAL
// =====================================================

void checkWrongWay() {
  bool ir3 = (digitalRead(IR3_PIN) == LOW);
  bool ir4 = (digitalRead(IR4_PIN) == LOW);

  // IR3 first = normal
  if (ir3 && !lastIR3) {
    if (!ir4FirstDetected) {
      ir4FirstDetected = false;
    }
  }

  // IR4 first
  if (ir4 && !lastIR4) {
    ir4FirstDetected = true;
    ir4DetectionTime = millis();
  }

  // IR4 -> IR3
  if (ir3 && !lastIR3 && ir4FirstDetected) {
    unsigned long elapsed = millis() - ir4DetectionTime;
    if (elapsed <= WRONG_WAY_WINDOW) {
      triggerAlert(WRONG_WAY);
    }
    ir4FirstDetected = false;
  }

  // Timeout
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
// VEHICLE SPEED
// =====================================================

void checkVehicleSpeed() {
  float d1 = getDistance(US1_TRIG, US1_ECHO);

  // US1 DETECTED
  if (d1 > 0 && d1 < 40 && !vehicleAtUS1) {
    vehicleAtUS1 = true;
    us1Time = micros();
  }

  float d2 = getDistance(US2_TRIG, US2_ECHO);

  // US2 DETECTED
  if (d2 > 0 && d2 < 40 && vehicleAtUS1) {
    unsigned long elapsed = micros() - us1Time;

    if (elapsed > 1000) {
      float seconds = elapsed / 1000000.0;
      float speed = (SENSOR_DISTANCE / seconds) * 3.6;

      measuredVehicleSpeed = speed;
      speedDisplayStart = millis();

      LinkSerial.print("SPEED:");
      LinkSerial.println((int)speed);

      if (speed > permittedSpeed + OVERSPEED_MARGIN) {
        triggerAlert(RASH_DRIVING);
      } else {
        showMeasuredSpeed(speed);
      }
    }

    vehicleAtUS1 = false;
  }

  // Safety timeout
  if (vehicleAtUS1 && (micros() - us1Time > 10000000UL)) {
    vehicleAtUS1 = false;
  }
}

// =====================================================
// SPEED LIMIT
// =====================================================

void updateSpeedLimit() {
  if (wetRoadActive) {
    permittedSpeed = WET_SPEED;
    return;
  }

  if (congestionActive) {
    permittedSpeed = CONGESTION_SPEED;
    return;
  }

  permittedSpeed = NORMAL_SPEED;
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
      showMeasuredSpeed(measuredVehicleSpeed);
      if (measuredVehicleSpeed > (permittedSpeed + OVERSPEED_MARGIN)) {
        triggerAlert(RASH_DRIVING);
      }
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
    showNormalScreen();
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

  // 7. DHT11
  dht.begin();

  // 8. WS2812B LED STRIP
  leds.begin();
  leds.setBrightness(50);
  normalLEDs();

  // 9. E-INK
  eink.init(
    115200,
    true,
    2,
    false
  );

  showNormalScreen();

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

  // Vehicle speed measurement
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
    permittedSpeed = WET_SPEED;
    triggerAlert(WET_ROAD);
  }

  if (wet) {
    wetRoadActive = true;
    permittedSpeed = WET_SPEED;

    // Flash ALL LEDs white
    if (millis() - lastWetFlash >= WET_FLASH_TIME) {
      wetRoadLEDs();
      lastWetFlash = millis();
    }

    if (activeAlert != WET_ROAD) {
      activeAlert = WET_ROAD;
      showWetScreen();
    }
  }

  if (!wet && lastWet) {
    wetRoadActive = false;
    activeAlert = NORMAL;
    permittedSpeed = NORMAL_SPEED;
    normalLEDs();
    showNormalScreen();
    LinkSerial.println("NORMAL");
  }

  lastWet = wet;

  // Speed limit priority
  updateSpeedLimit();

  // Congestion display & LED enforcement
  if (congestionActive && !wetRoadActive && activeAlert == CONGESTION) {
    showCongestionScreen();
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
    normalLEDs();
    LinkSerial.println("NORMAL");
    showNormalScreen();
  }

  // Speed screen timeout
  if (
    activeAlert == NORMAL &&
    speedDisplayStart > 0 &&
    millis() - speedDisplayStart >= SPEED_DISPLAY_TIME
  ) {
    speedDisplayStart = 0;
    showNormalScreen();
    LinkSerial.println("NORMAL");
  }

  // Wet road always has highest priority
  if (wetRoadActive) {
    permittedSpeed = WET_SPEED;
    activeAlert = WET_ROAD;
    if (millis() - lastWetFlash >= WET_FLASH_TIME) {
      wetRoadLEDs();
      lastWetFlash = millis();
    }
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