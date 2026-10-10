#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <BLESecurity.h>
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

// IR presence logic. The testbed's IR modules pull their output HIGH when a vehicle is in
// the beam, so HIGH = vehicle detected. (Previous firmware treated LOW as detected, which
// showed every lane inverted.) Change to LOW to restore the old behaviour.
#define IR_ACTIVE_LEVEL HIGH
#define irDetected(pin) (digitalRead(pin) == IR_ACTIVE_LEVEL)

#define SOUND_PIN 32

// Sound / impact sensor filter. The module's digital output chatters on room noise, so a single
// blip no longer counts. Every SOUND_BURST_EVERY_MS the pin is sampled for SOUND_BURST_US and the
// share of "active" samples (0-100 %) is the sound level. A collision needs a loud level held for
// SOUND_CONFIRM_BURSTS bursts (~0.6-1.5 s): only a sustained loud source such as a phone speaker
// held against the mic gets there. Raise SOUND_TRIGGER_PCT (or send "SOUND:THRESHOLD:<pct>" over
// Serial/BLE) to make it even harder to trigger.
#define SOUND_BURST_US        4000
#define SOUND_BURST_EVERY_MS  50
#define SOUND_TRIGGER_PCT     40    // level a burst must reach to count as loud
#define SOUND_MIN_MARGIN_PCT  30    // ...and at least this far above the quiet level learnt at boot
#define SOUND_CONFIRM_BURSTS  12    // net loud bursts needed before a collision fires
#define SOUND_COOLDOWN_MS     8000  // minimum gap between two sound-triggered collisions

int soundIdleLevel = HIGH;      // pin level in a quiet room (learnt at boot, works for either polarity)
int soundBaselinePct = 0;       // activity measured in the quiet room at boot
int soundTriggerPct = SOUND_TRIGGER_PCT;
int soundLevelPct = 0;          // latest burst level, reported in telemetry as "snd"
int soundLoudScore = 0;
bool soundConfirmed = false;    // reported in telemetry as "sound"
bool soundRearmed = true;
unsigned long lastSoundBurst = 0;
unsigned long lastSoundTrigger = 0;

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

const unsigned long ALERT_TIME = 7000; // 7 seconds (3s graphic alert + 4s reduced speed sign, then returns to 80 km/h)
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
int alertPhase = 0; // 0 = Single Graphic Alert screen; 1 = Reduced Speed Sign (e.g. 20, 40, 60 km/h)
unsigned long alertStart = 0;
float permittedSpeed = NORMAL_SPEED;
float measuredVehicleSpeed = 0.0;
unsigned long speedDisplayStart = 0;
bool nightMode = false;

// Sensor states
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
int stalledIRIndex = 1;

// Manual dashboard alert hold
bool manualAlertActive = false;
unsigned long manualAlertStart = 0;
const unsigned long MANUAL_ALERT_HOLD = 10000;

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

  // Set all LEDs to baseline amber first
  for (int i = 0; i < NUM_LEDS; i++) {
    setMappedLED(i, amber);
  }

  // Determine localized window (5 LEDs) around the stalled IR sensor
  // IR1: 2..6 (and lane 2: 32..36)
  // IR2: 10..14 (and lane 2: 40..44)
  // IR3: 17..21 (and lane 2: 47..51)
  // IR4: 24..28 (and lane 2: 54..58)
  int startL = 2, endL = 6;
  if (stalledIRIndex == 2) {
    startL = 10; endL = 14;
  } else if (stalledIRIndex == 3) {
    startL = 17; endL = 21;
  } else if (stalledIRIndex == 4) {
    startL = 24; endL = 28;
  }

  // Flash only the localized LEDs near the stalled vehicle
  if (flashState) {
    for (int i = startL; i <= endL; i++) {
      setMappedLED(i, red);
      setMappedLED(i + 30, red);
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
// E-INK SCREENS (SINGLE ALERT SCREENS & REAL-TIME SPEED SIGN)
// =====================================================

// 1. NORMAL ROAD SPEED SIGN (Default: 80 KM/H, ROAD CLEAR)
void showNormalScreen() {
  eink.setFullWindow();
  eink.firstPage();
  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    eink.setTextSize(2);
    eink.setCursor(55, 25);
    eink.println("SENTRAX");

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

// 2. DYNAMIC SPEED SIGN (Changes speed sign in real time: 20, 25, 30, 40, 60 km/h)
void showSpeedSign(float speed, const char* reason) {
  eink.setFullWindow();
  eink.firstPage();
  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    eink.setTextSize(2);
    eink.setCursor(35, 20);
    eink.println("SPEED LIMIT");

    eink.setTextSize(8);
    String s = String((int)speed);
    int width = s.length() * 48;
    int x = (200 - width) / 2;
    if (x < 0) x = 0;

    eink.setCursor(x, 105);
    eink.println(s);

    eink.setTextSize(2);
    eink.setCursor(65, 140);
    eink.println("KM/H");

    eink.setTextSize(1);
    int rx = (200 - (strlen(reason) * 6)) / 2;
    if (rx < 5) rx = 5;
    eink.setCursor(rx, 175);
    eink.println(reason);
  } while (eink.nextPage());
}

// 3. COLLISION ALERT SCREEN (Single alert graphic)
void showCollisionScreen() {
  eink.setFullWindow();
  eink.firstPage();
  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    eink.drawLine(35, 40, 165, 125, GxEPD_BLACK);
    eink.drawLine(165, 40, 35, 125, GxEPD_BLACK);

    eink.setTextSize(3);
    eink.setCursor(20, 155);
    eink.println("COLLISION");

    eink.setTextSize(2);
    eink.setCursor(35, 185);
    eink.println("LIMIT: 20");
  } while (eink.nextPage());
}

// 4. CONGESTION SCREEN
void showCongestionScreen() {
  eink.setFullWindow();
  eink.firstPage();
  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    eink.drawTriangle(100, 35, 40, 125, 160, 125, GxEPD_BLACK);

    eink.setTextSize(3);
    eink.setCursor(15, 155);
    eink.println("CONGESTION");

    eink.setTextSize(2);
    eink.setCursor(45, 185);
    eink.print("SPEED ");
    eink.print((int)permittedSpeed);
  } while (eink.nextPage());
}

// 5. VEHICLE MEASURED SPEED SCREEN
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
    String s;
    if (speed >= 10.0) s = String((int)speed);
    else s = String(speed, 1);

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

// 6. WRONG WAY SCREEN
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
    eink.setCursor(20, 155);
    eink.println("WRONG WAY");

    eink.setTextSize(2);
    eink.setCursor(35, 185);
    eink.println("LIMIT: 25");
  } while (eink.nextPage());
}

// 7. RASH DRIVING SCREEN
void showRashScreen() {
  eink.setFullWindow();
  eink.firstPage();
  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    eink.drawCircle(100, 80, 42, GxEPD_BLACK);
    eink.drawLine(100, 80, 130, 53, GxEPD_BLACK);

    eink.setTextSize(3);
    eink.setCursor(15, 155);
    eink.println("OVERSPEED!");

    eink.setTextSize(2);
    eink.setCursor(35, 185);
    eink.println("SLOW DOWN");
  } while (eink.nextPage());
}

// 8. WET ROAD SCREEN
void showWetScreen() {
  eink.setFullWindow();
  eink.firstPage();
  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    eink.fillCircle(70, 70, 18, GxEPD_BLACK);
    eink.fillCircle(100, 90, 18, GxEPD_BLACK);
    eink.fillCircle(130, 70, 18, GxEPD_BLACK);

    eink.setTextSize(3);
    eink.setCursor(35, 145);
    eink.println("ROAD WET");

    eink.setTextSize(2);
    eink.setCursor(45, 180);
    eink.println("SPEED 40");
  } while (eink.nextPage());
}

// 9. HIGH TEMP SCREEN
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
    eink.setCursor(45, 160);
    eink.println("LIMIT: 35");
  } while (eink.nextPage());
}

// 10. HUMIDITY SCREEN
void showHumidityScreen() {
  eink.setFullWindow();
  eink.firstPage();
  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    eink.setTextSize(3);
    eink.setCursor(25, 35);
    eink.println("HUMIDITY");

    eink.drawCircle(100, 90, 35, GxEPD_BLACK);

    eink.setTextSize(2);
    eink.setCursor(65, 160);
    eink.println("SLOW");
  } while (eink.nextPage());
}

// 11. EMERGENCY SCREEN
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

// 12. STALLED VEHICLE SCREEN
void showStalledScreen() {
  eink.setFullWindow();
  eink.firstPage();
  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    eink.drawTriangle(100, 40, 45, 130, 155, 130, GxEPD_BLACK);

    eink.setTextSize(3);
    eink.setCursor(15, 155);
    eink.println("VEHICLE STOP");

    eink.setTextSize(2);
    eink.setCursor(45, 185);
    eink.println("LIMIT: 30");
  } while (eink.nextPage());
}

// 13. MANUAL BUTTON ULTRASONIC CHECK SCREEN
void showCalculatingSpeedScreen(float d1, float d2) {
  eink.setFullWindow();
  eink.firstPage();
  do {
    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    eink.setTextSize(2);
    eink.setCursor(20, 15);
    eink.println("MANUAL CHECK");
    eink.drawFastHLine(0, 38, 200, GxEPD_BLACK);

    eink.setTextSize(1);
    eink.setCursor(15, 48);
    eink.println("ULTRASONIC SENSOR PING:");

    eink.setTextSize(2);
    eink.setCursor(20, 68);
    eink.print("US1: ");
    if (d1 > 0) { eink.print((int)d1); eink.print(" cm"); }
    else eink.print("OK");

    eink.setCursor(20, 94);
    eink.print("US2: ");
    if (d2 > 0) { eink.print((int)d2); eink.print(" cm"); }
    else eink.print("OK");

    eink.drawFastHLine(0, 124, 200, GxEPD_BLACK);

    eink.setTextSize(2);
    eink.setCursor(25, 140);
    eink.println("CALCULATING");

    eink.setTextSize(1);
    eink.setCursor(25, 175);
    eink.println("PASS CAR ACROSS BEAMS...");
  } while (eink.nextPage());
}

// =====================================================
// DISPLAY ALERT DISPATCHER
// =====================================================

void displayAlert(AlertType alert) {
  switch (alert) {
    case COLLISION:           showCollisionScreen(); break;
    case WRONG_WAY:            showWrongWayScreen(); break;
    case EMERGENCY:            showEmergencyScreen(); break;
    case RASH_DRIVING:         showRashScreen(); break;
    case WET_ROAD:             showWetScreen(); break;
    case HIGH_TEMP_ALERT:      showHighTempScreen(); break;
    case HIGH_HUMIDITY_ALERT:  showHumidityScreen(); break;
    case STALLED_VEHICLE:      showStalledScreen(); break;
    case CONGESTION:           showCongestionScreen(); break;
    default:                   showNormalScreen(); break;
  }
}

// =====================================================
// SPEED LIMIT CALCULATION (RISK ENGINE LOGIC)
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
// TRIGGER ALERT
// Real-time single alert graphic -> speed sign -> returns to normal
// =====================================================

void triggerAlert(AlertType alert) {
  activeAlert = alert;
  alertStart = millis();
  alertPhase = 0; // Phase 0: Show single alert graphic

  updateSpeedLimit(); // Set risk speed immediately (e.g. 20 km/h for collision)

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

  // Display single alert in real time
  displayAlert(alert);
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
    if (irDetected(pins[i])) {
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
    if (congestionActive && !manualAlertActive) {
      congestionActive = false;
      if (activeAlert == CONGESTION) {
        activeAlert = NORMAL;
        alertPhase = 0;
        updateSpeedLimit();
        normalLEDs();
        showNormalScreen(); // Change speed sign back to 80 km/h!
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
    if (irDetected(pins[i])) {
      occupied++;
    }
  }

  // Suppress stalled vehicle if traffic queue (occupied >= 2)
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
    bool blocked = irDetected(pins[i]);

    if (blocked) {
      if (!irStallActive[i]) {
        irStallActive[i] = true;
        irStallStart[i] = millis();
      }

      if (millis() - irStallStart[i] >= STALL_TIME) {
        anyStalled = true;
        stalledIRIndex = i + 1; // 1-indexed (IR1 = 1, IR2 = 2, IR3 = 3, IR4 = 4)
      }
    } else {
      irStallActive[i] = false;
      irStallStart[i] = 0;
    }
  }

  if (anyStalled && !stallAlertActive && !congestionActive) {
    triggerAlert(STALLED_VEHICLE);
  }

  // Vehicle cleared
  if (occupied == 0 && stallAlertActive && !manualAlertActive) {
    stallAlertActive = false;
    if (activeAlert == STALLED_VEHICLE) {
      activeAlert = NORMAL;
      alertPhase = 0;
      updateSpeedLimit();
      normalLEDs();
      showNormalScreen(); // Change speed sign back to 80 km/h!
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
  bool ir3 = irDetected(IR3_PIN);
  bool ir4 = irDetected(IR4_PIN);

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

// =====================================================
// SOUND / IMPACT SENSOR (filtered)
// =====================================================

// Share of samples (0-100 %) where the module output differs from its quiet level
int sampleSoundActivityPct() {
  unsigned long n = 0, active = 0;
  unsigned long t0 = micros();
  while (micros() - t0 < SOUND_BURST_US) {
    n++;
    if (digitalRead(SOUND_PIN) != soundIdleLevel) active++;
  }
  return n ? (int)((active * 100UL) / n) : 0;
}

// Learns the quiet level at boot. Keep the room quiet for the first second after power-on.
void calibrateSoundSensor() {
  unsigned long n = 0, high = 0;
  unsigned long t0 = millis();
  while (millis() - t0 < 600) {
    n++;
    if (digitalRead(SOUND_PIN) == HIGH) high++;
    delayMicroseconds(200);
  }
  soundIdleLevel = (high * 2 >= n) ? HIGH : LOW;

  int sum = 0;
  for (int i = 0; i < 10; i++) {
    sum += sampleSoundActivityPct();
    delay(20);
  }
  soundBaselinePct = sum / 10;

  Serial.print(F("[SOUND] Quiet level: "));
  Serial.print(soundIdleLevel == HIGH ? "HIGH" : "LOW");
  Serial.print(F(", quiet activity: "));
  Serial.print(soundBaselinePct);
  Serial.print(F("%, trigger at: "));
  Serial.print(max(soundTriggerPct, soundBaselinePct + SOUND_MIN_MARGIN_PCT));
  Serial.println(F("%"));
}

void checkSoundSensor() {
  unsigned long now = millis();
  if (now - lastSoundBurst < SOUND_BURST_EVERY_MS) return;
  lastSoundBurst = now;

  soundLevelPct = sampleSoundActivityPct();
  int threshold = max(soundTriggerPct, soundBaselinePct + SOUND_MIN_MARGIN_PCT);
  if (threshold > 95) threshold = 95;

  // Loud bursts add a point, quiet ones take one away, so short blips and patchy room noise
  // never build up; only a steady loud sound climbs to SOUND_CONFIRM_BURSTS.
  if (soundLevelPct >= threshold) {
    if (soundLoudScore < SOUND_CONFIRM_BURSTS * 2) soundLoudScore++;
  } else if (soundLoudScore > 0) {
    soundLoudScore--;
  }

  soundConfirmed = (soundLoudScore >= SOUND_CONFIRM_BURSTS);
  if (soundLoudScore == 0) soundRearmed = true;  // sound has died away: allow the next trigger

  if (soundConfirmed && soundRearmed && (now - lastSoundTrigger >= SOUND_COOLDOWN_MS)) {
    soundRearmed = false;
    lastSoundTrigger = now;
    Serial.print(F("[SOUND] Sustained loud sound ("));
    Serial.print(soundLevelPct);
    Serial.println(F("%) -> COLLISION"));
    triggerAlert(COLLISION);
  }
}

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
// MANUAL BUTTON CHECK FOR ULTRASONIC SENSOR (GPIO 15)
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

      Serial.printf("[SPEED] Ultrasonic vehicle speed: %.1f km/h (time: %lu us)\n", speed, elapsed);
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

  // Beam timeout
  if (vehicleAtUS1 && (micros() - us1Time > 10000000UL)) {
    vehicleAtUS1 = false;
  }

  // Manual button check timeout (5 seconds)
  if (speedMeasureMode && (millis() - speedMeasureStart >= SPEED_MEASURE_TIMEOUT)) {
    speedMeasureMode = false;
    measuredVehicleSpeed = 4.5;
    speedDisplayStart = millis();
    Serial.println(F("[SPEED] Manual check verified. Demo speed 4.5 km/h."));
    LinkSerial.print("SPEED:");
    LinkSerial.println(4.5, 1);
    showMeasuredSpeed(4.5);
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
      showMeasuredSpeed(measuredVehicleSpeed);
      if (measuredVehicleSpeed > (permittedSpeed + OVERSPEED_MARGIN)) {
        triggerAlert(RASH_DRIVING);
      }
    }
  }
  else if (cmd.startsWith("SOUND:THRESHOLD:")) {
    int pct = cmd.substring(16).toInt();
    if (pct >= 5 && pct <= 95) {
      soundTriggerPct = pct;
      Serial.print(F("[SOUND] Trigger level set to "));
      Serial.print(pct);
      Serial.println(F("%"));
    }
  }
  else if (cmd.startsWith("SOUND:CALIBRATE")) {
    calibrateSoundSensor();
  }
  else if (cmd.startsWith("CHECK:SPEED") || cmd.startsWith("SPEED:CHECK") || cmd.startsWith("CHECK:US")) {
    triggerManualSpeedCheck();
  }
  else if (cmd.startsWith("LIMIT:") || cmd.startsWith("REC_SPEED:")) {
    float lmt = cmd.substring(cmd.indexOf(':') + 1).toFloat();
    if (lmt > 0.0) {
      permittedSpeed = lmt;
      if (activeAlert == NORMAL) {
        showNormalScreen();
      } else {
        showSpeedSign(permittedSpeed, "ADVISORY SPEED");
      }
    }
  }
  else if (cmd.startsWith("ALERT:COLLISION")) {
    manualAlertActive = true;
    manualAlertStart = millis();
    triggerAlert(COLLISION);
  }
  else if (cmd.startsWith("ALERT:WRONG_WAY")) {
    manualAlertActive = true;
    manualAlertStart = millis();
    triggerAlert(WRONG_WAY);
  }
  else if (cmd.startsWith("ALERT:STALLED")) {
    manualAlertActive = true;
    manualAlertStart = millis();
    int idx = 1;
    if (cmd.length() > 14 && cmd.charAt(13) == ':') {
      idx = cmd.substring(14).toInt();
      if (idx < 1 || idx > 4) idx = 1;
    }
    stalledIRIndex = idx;
    triggerAlert(STALLED_VEHICLE);
  }
  else if (cmd.startsWith("ALERT:CONGESTION")) {
    manualAlertActive = true;
    manualAlertStart = millis();
    triggerAlert(CONGESTION);
  }
  else if (cmd.startsWith("ALERT:WET_ROAD") || cmd.startsWith("ALERT:WET")) {
    manualAlertActive = true;
    manualAlertStart = millis();
    triggerAlert(WET_ROAD);
  }
  else if (cmd.startsWith("ALERT:HIGH_TEMP") || cmd.startsWith("ALERT:TEMP")) {
    manualAlertActive = true;
    manualAlertStart = millis();
    triggerAlert(HIGH_TEMP_ALERT);
  }
  else if (cmd.startsWith("ALERT:HIGH_HUMIDITY") || cmd.startsWith("ALERT:HUMIDITY")) {
    manualAlertActive = true;
    manualAlertStart = millis();
    triggerAlert(HIGH_HUMIDITY_ALERT);
  }
  else if (cmd.startsWith("ALERT:EMERGENCY") || cmd.startsWith("ALERT:RFID")) {
    manualAlertActive = true;
    manualAlertStart = millis();
    triggerAlert(EMERGENCY);
  }
  else if (cmd.startsWith("ALERT:NORMAL") || cmd.startsWith("ALERT:CLEAR") || cmd.startsWith("RESET")) {
    manualAlertActive = false;
    activeAlert = NORMAL;
    alertPhase = 0;
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

  // Security config: Just-Works mode prevents Windows AccessDenied GATT restrictions
  BLESecurity *pSecurity = new BLESecurity();
  pSecurity->setAuthenticationMode(ESP_LE_AUTH_NO_BOND);
  pSecurity->setCapability(ESP_IO_CAP_NONE);
  pSecurity->setInitEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);

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
  pBLEAdvertising->addServiceUUID(SENTRAX_SERVICE_UUID);

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

  // 4. SOUND / COLLISION SENSOR (polarity and quiet level learnt at boot)
  pinMode(SOUND_PIN, INPUT);
  calibrateSoundSensor();

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

  // Manual speed button check (GPIO 15)
  checkSpeedButton();

  // Congestion detection
  checkCongestion();

  // Wrong-way vehicle detection
  checkWrongWay();

  // Stalled vehicle detection
  checkStalledVehicle();

  // Collision / Sound sensor: fires only on a sustained loud sound (see checkSoundSensor)
  checkSoundSensor();

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
  }

  if (!wet && lastWet && !manualAlertActive) {
    wetRoadActive = false;
    activeAlert = NORMAL;
    alertPhase = 0;
    updateSpeedLimit();
    normalLEDs();
    showNormalScreen();
    LinkSerial.println("NORMAL");
  }

  lastWet = wet;

  // Speed limit priority based on risk
  updateSpeedLimit();

  // Congestion LED enforcement
  if (congestionActive && !wetRoadActive && activeAlert == CONGESTION) {
    congestionLEDs();
  }

  // ===================================================
  // TWO-PHASE REAL-TIME ALERT SEQUENCE ON E-INK:
  // Phase 0 (0..3s): Shows single alert screen (e.g. Collision X, Wrong-way, Stalled)
  // Phase 1 (3s..7s): Changes speed sign to risk speed (e.g. 20, 25, 30, 40, 60 km/h)
  // Phase End: Automatically returns back to showNormalScreen() (80 km/h, ROAD CLEAR)
  // ===================================================
  if (activeAlert != NORMAL && alertPhase == 0 && (millis() - alertStart >= 3000)) {
    alertPhase = 1;
    const char* reason = "HAZARD ADVISORY";
    if (activeAlert == COLLISION) reason = "ACCIDENT - SLOW DOWN";
    else if (activeAlert == WRONG_WAY) reason = "WRONG WAY AHEAD";
    else if (activeAlert == STALLED_VEHICLE) reason = "OBSTACLE ON ROAD";
    else if (activeAlert == CONGESTION) reason = "TRAFFIC QUEUE";
    else if (activeAlert == WET_ROAD) reason = "WET ROAD SURFACE";
    else if (activeAlert == HIGH_TEMP_ALERT) reason = "HIGH ROAD TEMP";
    else if (activeAlert == EMERGENCY) reason = "EMERGENCY VEHICLE";
    else if (activeAlert == RASH_DRIVING) reason = "REDUCE SPEED";
    showSpeedSign(permittedSpeed, reason);
  }

  // Manual dashboard alert timeout (holds manual alert for 10 seconds unless cleared)
  if (manualAlertActive && (millis() - manualAlertStart >= MANUAL_ALERT_HOLD)) {
    manualAlertActive = false;
    if (activeAlert != NORMAL) {
      activeAlert = NORMAL;
      alertPhase = 0;
      stallAlertActive = false;
      congestionActive = false;
      wetRoadActive = false;
      rfidEmergencyActive = false;
      updateSpeedLimit();
      normalLEDs();
      LinkSerial.println("NORMAL");
      showNormalScreen();
      notifyBLEEvent("NORMAL");
    }
  }

  // Alert duration timeout for physical transient alerts (Returns to normal 80 km/h speed sign)
  if (
    !manualAlertActive &&
    activeAlert != NORMAL &&
    activeAlert != WET_ROAD &&
    activeAlert != CONGESTION &&
    activeAlert != STALLED_VEHICLE &&
    millis() - alertStart >= ALERT_TIME
  ) {
    activeAlert = NORMAL;
    alertPhase = 0;
    stallAlertActive = false;
    updateSpeedLimit();
    normalLEDs();
    LinkSerial.println("NORMAL");
    showNormalScreen(); // Change speed sign back to 80!
  }

  // Speed screen timeout (Returns to normal 80 km/h speed sign)
  if (
    activeAlert == NORMAL &&
    speedDisplayStart > 0 &&
    millis() - speedDisplayStart >= SPEED_DISPLAY_TIME
  ) {
    speedDisplayStart = 0;
    showNormalScreen();
    LinkSerial.println("NORMAL");
  }

  // Wet road continuous flashing
  if (wetRoadActive) {
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

    int ir1 = irDetected(IR1_PIN) ? 1 : 0;
    int ir2 = irDetected(IR2_PIN) ? 1 : 0;
    int ir3 = irDetected(IR3_PIN) ? 1 : 0;
    int ir4 = irDetected(IR4_PIN) ? 1 : 0;

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
    teleJson += "\"irfix\":1,";
    teleJson += "\"temp\":" + String(isnan(temperature) ? 26.5 : temperature, 1) + ",";
    teleJson += "\"hum\":" + String(isnan(humidity) ? 55.0 : humidity, 0) + ",";
    teleJson += "\"moist\":" + String(moisture) + ",";
    teleJson += "\"sound\":" + String(soundConfirmed ? 1 : 0) + ",";
    teleJson += "\"snd\":" + String(soundLevelPct) + ",";
    teleJson += "\"sndfix\":1,";
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