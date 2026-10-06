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

// Waveshare 1.54" V2 (GDEH0154D67 controller - standard):
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
// NOTE: If you have an older Waveshare 1.54" V1 module (SSD1681 / GDEP0154D00) that remains blank,
// comment out GxEPD2_154_D67 above and uncomment this line:
// GxEPD2_BW<GxEPD2_154, GxEPD2_154::HEIGHT> eink(GxEPD2_154(EINK_CS, EINK_DC, EINK_RST, EINK_BUSY));


// =====================================================
// SENTRAX NATIVE BLE GATT DEFINITIONS
// =====================================================

#define SENTRAX_SERVICE_UUID        "73656e74-7261-7800-0001-000000000000"
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

class SentraXBLEServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
      bleClientConnected = true;
    };

    void onDisconnect(BLEServer* pServer) {
      bleClientConnected = false;
      // Restart advertising so clients can reconnect
      pServer->getAdvertising()->start();
    }
};

class SentraXBLECommandCallbacks: public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pCharacteristic) {
      String rxValue = pCharacteristic->getValue().c_str();
      if (rxValue.length() > 0) {
        rxValue.trim();
        // Handle command
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

// Congestion speed
const float CONGESTION_SPEED = 60.0;

// Wet road speed
const float WET_SPEED = 40.0;
const float TEMP_SPEED = 35.0;

// Existing traffic levels
const float TRAFFIC_SPEED_1 = 70.0;
const float TRAFFIC_SPEED_2 = 60.0;
const float TRAFFIC_SPEED_3 = 50.0;

// Distance between ultrasonic sensors
const float SENSOR_DISTANCE = 0.30;

#define SPEED_BUTTON_PIN 15
const float DEMO_SPEED = 4.5;
const char VEHICLE_NUMBER[] = "CZO5";

// Overspeed margin
const float OVERSPEED_MARGIN = 5.0;

// Mandatory SentraX Change: Toy-car low-speed overspeed detection threshold
// ROAD RECOMMENDATION remains NORMAL_SPEED (80.0 km/h)
// Physical toy vehicle demonstration overspeed threshold:
const float DEMO_OVERSPEED_LIMIT = 4.0;

// =====================================================
// TEMPERATURE
// =====================================================

// Low threshold for demonstration
const float HIGH_TEMP = 30.0;

// =====================================================
// HUMIDITY
// =====================================================

const float HIGH_HUMIDITY = 80.0;

// =====================================================
// MOISTURE
// =====================================================

const int MOISTURE_THRESHOLD = 2000;

// =====================================================
// TIMERS
// =====================================================

// Normal alert duration
const unsigned long ALERT_TIME = 7000;
const unsigned long SPEED_MEASURE_TIMEOUT = 10000;

// Wrong way window
const unsigned long WRONG_WAY_WINDOW = 15000;

// Stalled vehicle
const unsigned long STALL_TIME = 6000;

// Congestion
// Mandatory SentraX Change: 5 seconds congestion detection
const unsigned long CONGESTION_TIME = 5000;

// Speed display
const unsigned long SPEED_DISPLAY_TIME = 5000;

// Wet LED flashing
const unsigned long WET_FLASH_TIME = 300;

// =====================================================
// ALERT TYPES
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

AlertType activeAlert = NORMAL;

// =====================================================
// GENERAL STATE
// =====================================================

unsigned long alertStart = 0;

float permittedSpeed = NORMAL_SPEED;

float measuredVehicleSpeed = DEMO_SPEED;

unsigned long speedDisplayStart = 0;

bool speedMeasureMode = false;
unsigned long speedMeasureStart = 0;
bool lastButtonState = HIGH;
bool lastUS1Detected = false;
bool lastUS2Detected = false;

bool highTemperatureActive = false;

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

bool irStallActive[4] = {
  false,
  false,
  false,
  false
};

unsigned long irStallStart[4] = {
  0,
  0,
  0,
  0
};

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
//
// 60 WS2812B LEDs total on road track:
// Logical Left side:   0 to 29
// Logical Right side: 30 to 59
//
// SWAP SIDES: Logical Left -> Physical Right (30..59)
//             Logical Right -> Physical Left (0..29)
//
int physicalLED(
  int logicalLED
) {

  if (logicalLED < 0)
    logicalLED = 0;

  if (logicalLED >= NUM_LEDS)
    logicalLED = NUM_LEDS - 1;

  // Swap Left (0..29) and Right (30..59) halves
  if (logicalLED < 30) {
    return logicalLED + 30;
  } else {
    return logicalLED - 30;
  }
}

// =====================================================
// MAPPED LED
// =====================================================

void setMappedLED(
  int logicalLED,
  uint32_t color
) {

  leds.setPixelColor(
    physicalLED(logicalLED),
    color
  );
}

// =====================================================
// NORMAL AMBER
// =====================================================

void normalLEDs() {

  leds.clear();

  uint32_t yellow =
    leds.Color(
      255,
      180,
      0
    );

  for (
    int i = 0;
    i < NUM_LEDS;
    i++
  ) {

    setMappedLED(
      i,
      yellow
    );
  }

  leds.show();
}

// =====================================================
// COLLISION LEDs
// =====================================================
//
// LOGICAL LEFT
// Due to side switching, this now appears
// physically on the opposite side.
// =====================================================

void collisionLEDs() {

  normalLEDs();

  uint32_t red =
    leds.Color(
      255,
      0,
      0
    );

  for (
    int i = 10;
    i <= 13;
    i++
  ) {

    setMappedLED(
      i,
      red
    );
  }

  leds.show();
}

// =====================================================
// WRONG WAY LEDs
// =====================================================

void wrongWayLEDs() {

  static bool flashState = false;
  static unsigned long lastFlash = 0;

  if (
    millis() -
    lastFlash >=
    250
  ) {

    lastFlash =
      millis();

    flashState =
      !flashState;
  }

  leds.clear();

  uint32_t red =
    leds.Color(
      255,
      0,
      0
    );

  if (
    flashState
  ) {

    // Opposite-side warning.
    // Logical LEFT = physical LEDs 30-59
    // Logical RIGHT = physical LEDs 0-29
    //
    // Both halves flash red for the wrong-way warning.
    // The actual side reversal is handled by physicalLED().
    for (
      int i = 30;
      i <= 59;
      i++
    ) {

      leds.setPixelColor(
        physicalLED(i),
        red
      );
    }

    for (
      int i = 0;
      i <= 29;
      i++
    ) {

      leds.setPixelColor(
        physicalLED(i),
        red
      );
    }
  }

  leds.show();
}

// =====================================================
// STALLED VEHICLE LEDs
// =====================================================

void stalledLEDs() {

  uint32_t yellow =
    leds.Color(
      255,
      180,
      0
    );


  static bool flashState = false;

  flashState =
    !flashState;

  uint32_t red =
    leds.Color(
      255,
      0,
      0
    );

  uint32_t amber =
    leds.Color(
      15,
      7,
      0
    );

  // LOGICAL LEFT
  for (
    int i = 0;
    i < 15;
    i++
  ) {

    if (flashState) {

      setMappedLED(
        i,
        red
      );

    } else {

      setMappedLED(
        i,
        yellow
      );
    }
  }

  leds.show();
}

// =====================================================
// CONGESTION LEDs
// =====================================================
//
// Both sides glow red/orange to indicate congestion.
// =====================================================

void congestionLEDs() {

  uint32_t red =
    leds.Color(
      180,
      0,
      0
    );

  for (
    int i = 0;
    i < NUM_LEDS;
    i++
  ) {

    setMappedLED(
      i,
      red
    );
  }

  leds.show();
}

// =====================================================
// WET ROAD LEDS
// =====================================================
//
// ALL 60 LEDs FLASH WHITE.
// =====================================================

void wetRoadLEDs() {

  uint32_t white =
    leds.Color(
      255,
      255,
      255
    );

  uint32_t off =
    leds.Color(
      0,
      0,
      0
    );

  wetFlashState =
    !wetFlashState;

  for (
    int i = 0;
    i < NUM_LEDS;
    i++
  ) {

    if (wetFlashState) {

      setMappedLED(
        i,
        white
      );

    } else {

      setMappedLED(
        i,
        off
      );
    }
  }

  leds.show();
}

// =====================================================
// RFID EMERGENCY PATTERN
// =====================================================
//
// RED sequential pattern twice.
// =====================================================

void emergencyPattern() {

  uint32_t red =
    leds.Color(
      255,
      0,
      0
    );

  leds.clear();
  leds.show();

  for (
    int repeat = 0;
    repeat < 2;
    repeat++
  ) {

    for (
      int i = 0;
      i < NUM_LEDS;
      i++
    ) {

      setMappedLED(
        i,
        red
      );

      leds.show();

      delay(35);

      setMappedLED(
        i,
        leds.Color(
          255,
          70,
          0
        )
      );

      leds.show();
    }

    delay(150);
  }

  normalLEDs();
}

// =====================================================
// NORMAL E-INK
// =====================================================

void showNormalScreen() {

  eink.setFullWindow();

  eink.firstPage();

  do {

    eink.fillScreen(
      GxEPD_WHITE
    );

    eink.setTextColor(
      GxEPD_BLACK
    );

    eink.setTextSize(2);

    eink.setCursor(
      55,
      25
    );

    eink.println(
      "SENTRAX"
    );

    // BIG SPEED
    eink.setTextSize(8);

    String speedText =
      String(
        (int)permittedSpeed
      );

    int width =
      speedText.length() * 48;

    int x =
      (200 - width) / 2;

    if (x < 0) {
      x = 0;
    }

    eink.setCursor(
      x,
      110
    );

    eink.println(
      speedText
    );

    eink.setTextSize(2);

    eink.setCursor(
      65,
      140
    );

    eink.println(
      "KM/H"
    );

    eink.setTextSize(1);

    eink.setCursor(
      55,
      170
    );

    eink.println(
      "ROAD CLEAR"
    );

  } while (
    eink.nextPage()
  );
}

// =====================================================
// CONGESTION SCREEN
// =====================================================

void showCongestionScreen() {

  eink.setFullWindow();

  eink.firstPage();

  do {

    eink.fillScreen(
      GxEPD_WHITE
    );

    eink.setTextColor(
      GxEPD_BLACK
    );

    // LARGE WARNING TRIANGLE
    eink.drawTriangle(
      100,
      35,
      40,
      125,
      160,
      125,
      GxEPD_BLACK
    );

    eink.setTextSize(3);

    eink.setCursor(
      35,
      160
    );

    eink.println(
      "CONGESTION"
    );

    eink.setTextSize(2);

    eink.setCursor(
      55,
      190
    );

    eink.print(
      "SPEED "
    );

    eink.print(
      (int)permittedSpeed
    );

  } while (
    eink.nextPage()
  );
}

// =====================================================
// CALCULATING SPEED SCREEN
// =====================================================

void showCalculatingSpeedScreen() {

  eink.setFullWindow();
  eink.firstPage();

  do {

    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    eink.setTextSize(3);
    eink.setCursor(15, 65);
    eink.println("CALCULATING");

    eink.setCursor(55, 115);
    eink.println("SPEED");

    eink.setTextSize(2);
    eink.setCursor(65, 160);
    eink.println(VEHICLE_NUMBER);

  } while (eink.nextPage());
}

// =====================================================
// VEHICLE SPEED SCREEN
// =====================================================

void showMeasuredSpeed(
  float speed
) {

  eink.setFullWindow();
  eink.firstPage();

  do {

    eink.fillScreen(GxEPD_WHITE);
    eink.setTextColor(GxEPD_BLACK);

    eink.setTextSize(2);
    eink.setCursor(30, 25);
    eink.print("VEHICLE ");
    eink.println(VEHICLE_NUMBER);

    eink.setTextSize(7);

    String s = String(speed, 1);
    int width = s.length() * 42;
    int x = (200 - width) / 2;

    if (x < 0)
      x = 0;

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


// =====================================================
// COLLISION SCREEN
// =====================================================

void showCollisionScreen() {

  eink.setFullWindow();

  eink.firstPage();

  do {

    eink.fillScreen(
      GxEPD_WHITE
    );

    eink.setTextColor(
      GxEPD_BLACK
    );

    eink.drawLine(
      35,
      40,
      165,
      125,
      GxEPD_BLACK
    );

    eink.drawLine(
      165,
      40,
      35,
      125,
      GxEPD_BLACK
    );

    eink.setTextSize(3);

    eink.setCursor(
      30,
      165
    );

    eink.println(
      "COLLISION"
    );

  } while (
    eink.nextPage()
  );
}

// =====================================================
// WRONG WAY SCREEN
// =====================================================

void showWrongWayScreen() {

  eink.setFullWindow();

  eink.firstPage();

  do {

    eink.fillScreen(
      GxEPD_WHITE
    );

    eink.setTextColor(
      GxEPD_BLACK
    );

    eink.drawLine(
      100,
      125,
      100,
      45,
      GxEPD_BLACK
    );

    eink.drawLine(
      100,
      45,
      65,
      80,
      GxEPD_BLACK
    );

    eink.drawLine(
      100,
      45,
      135,
      80,
      GxEPD_BLACK
    );

    eink.setTextSize(3);

    eink.setCursor(
      25,
      165
    );

    eink.println(
      "WRONG WAY"
    );

  } while (
    eink.nextPage()
  );
}

// =====================================================
// RASH DRIVING SCREEN
// =====================================================

void showRashScreen() {

  eink.setFullWindow();

  eink.firstPage();

  do {

    eink.fillScreen(
      GxEPD_WHITE
    );

    eink.setTextColor(
      GxEPD_BLACK
    );

    // SPEEDOMETER
    eink.drawCircle(
      100,
      80,
      42,
      GxEPD_BLACK
    );

    eink.drawLine(
      100,
      80,
      130,
      53,
      GxEPD_BLACK
    );

    eink.setTextSize(3);

    eink.setCursor(
      15,
      160
    );

    eink.println(
      "OVERSPEED!"
    );

    eink.setTextSize(2);

    eink.setCursor(
      45,
      190
    );

    eink.println(
      "RASH DRIVING"
    );

  } while (
    eink.nextPage()
  );
}

// =====================================================
// WET ROAD SCREEN
// =====================================================

void showWetScreen() {

  eink.setFullWindow();

  eink.firstPage();

  do {

    eink.fillScreen(
      GxEPD_WHITE
    );

    eink.setTextColor(
      GxEPD_BLACK
    );

    // WATER DROPS
    eink.fillCircle(
      70,
      70,
      18,
      GxEPD_BLACK
    );

    eink.fillCircle(
      100,
      90,
      18,
      GxEPD_BLACK
    );

    eink.fillCircle(
      130,
      70,
      18,
      GxEPD_BLACK
    );

    eink.setTextSize(3);

    eink.setCursor(
      45,
      145
    );

    eink.println(
      "ROAD WET"
    );

    eink.setTextSize(2);

    eink.setCursor(
      45,
      180
    );

    eink.println(
      "SPEED 40"
    );

  } while (
    eink.nextPage()
  );
}

// =====================================================
// HIGH TEMPERATURE SCREEN
// =====================================================

void showHighTempScreen() {

  eink.setFullWindow();

  eink.firstPage();

  do {

    eink.fillScreen(
      GxEPD_WHITE
    );

    eink.setTextColor(
      GxEPD_BLACK
    );

    eink.setTextSize(3);

    eink.setCursor(
      30,
      35
    );

    eink.println(
      "HIGH TEMP"
    );

    eink.drawCircle(
      100,
      110,
      22,
      GxEPD_BLACK
    );

    eink.drawLine(
      100,
      50,
      100,
      110,
      GxEPD_BLACK
    );

    eink.setTextSize(2);

    eink.setCursor(
      65,
      160
    );

    eink.println(
      "SLOW"
    );

  } while (
    eink.nextPage()
  );
}

// =====================================================
// HIGH TEMPERATURE SCREEN
// =====================================================


// =====================================================
// HUMIDITY SCREEN
// =====================================================

void showHumidityScreen() {

  eink.setFullWindow();

  eink.firstPage();

  do {

    eink.fillScreen(
      GxEPD_WHITE
    );

    eink.setTextColor(
      GxEPD_BLACK
    );

    eink.setTextSize(3);

    eink.setCursor(
      10,
      35
    );

    eink.println(
      "HUMIDITY"
    );

    eink.drawCircle(
      100,
      90,
      35,
      GxEPD_BLACK
    );

    eink.setTextSize(2);

    eink.setCursor(
      65,
      160
    );

    eink.println(
      "SLOW"
    );

  } while (
    eink.nextPage()
  );
}

// =====================================================
// EMERGENCY SCREEN
// =====================================================

void showEmergencyScreen() {

  eink.setFullWindow();

  eink.firstPage();

  do {

    eink.fillScreen(
      GxEPD_WHITE
    );

    eink.setTextColor(
      GxEPD_BLACK
    );

    eink.drawLine(
      40,
      45,
      160,
      125,
      GxEPD_BLACK
    );

    eink.drawLine(
      160,
      45,
      40,
      125,
      GxEPD_BLACK
    );

    eink.setTextSize(3);

    eink.setCursor(
      15,
      165
    );

    eink.println(
      "EMERGENCY"
    );

  } while (
    eink.nextPage()
  );
}

// =====================================================
// STALLED VEHICLE SCREEN
// =====================================================

void showStalledScreen() {

  eink.setFullWindow();

  eink.firstPage();

  do {

    eink.fillScreen(
      GxEPD_WHITE
    );

    eink.setTextColor(
      GxEPD_BLACK
    );

    eink.drawTriangle(
      100,
      40,
      45,
      130,
      155,
      130,
      GxEPD_BLACK
    );

    eink.setTextSize(3);

    eink.setCursor(
      20,
      165
    );

    eink.println(
      "VEHICLE STOP"
    );

  } while (
    eink.nextPage()
  );
}

// =====================================================
// DISPLAY ALERT
// =====================================================

void displayAlert(
  AlertType alert
) {

  switch (alert) {

    case COLLISION:
      notifyBLEEvent("COLLISION");
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

void triggerAlert(
  AlertType alert
) {

  activeAlert =
    alert;

  alertStart =
    millis();

  switch (alert) {

    case COLLISION:
      notifyBLEEvent("COLLISION");

      collisionLEDs();

      LinkSerial.println(
        "COLLISION"
      );

      break;

    case WRONG_WAY:

      wrongWayLEDs();

      LinkSerial.println(
        "WRONG"
      );

      break;

    case RASH_DRIVING:

      LinkSerial.println(
        "RASH"
      );

      break;

    case WET_ROAD:

      permittedSpeed = WET_SPEED;

      LinkSerial.println("WET");
      LinkSerial.print("LIMIT:");
      LinkSerial.println((int)permittedSpeed);

      break;

    case HIGH_TEMP_ALERT:

      permittedSpeed = TEMP_SPEED;

      LinkSerial.println("TEMP");
      LinkSerial.print("LIMIT:");
      LinkSerial.println((int)permittedSpeed);

      break;

    case HIGH_HUMIDITY_ALERT:

      LinkSerial.println(
        "HUMIDITY"
      );

      break;

    case STALLED_VEHICLE:

      LinkSerial.println(
        "STALLED"
      );

      stallAlertActive =
        true;

      break;

    case CONGESTION:

      LinkSerial.println("CONGESTION");

      congestionActive = true;
      permittedSpeed = CONGESTION_SPEED;

      LinkSerial.print("LIMIT:");
      LinkSerial.println((int)permittedSpeed);

      congestionLEDs();

      break;

    case EMERGENCY:

      emergencyPattern();

      LinkSerial.println(
        "RFID"
      );

      break;

    default:

      break;
  }

  displayAlert(
    alert
  );
}

// =====================================================
// STALLED VEHICLE
// =====================================================

void checkStalledVehicle() {

  int pins[4] = {
    IR1_PIN,
    IR2_PIN,
    IR3_PIN,
    IR4_PIN
  };

  bool anyStalled =
    false;

  for (
    int i = 0;
    i < 4;
    i++
  ) {

    bool blocked =
      digitalRead(
        pins[i]
      ) == LOW;

    if (blocked) {

      if (!irStallActive[i]) {

        irStallActive[i] =
          true;

        irStallStart[i] =
          millis();
      }

      if (
        millis() -
        irStallStart[i] >=
        STALL_TIME
      ) {

        anyStalled =
          true;
      }

    } else {

      irStallActive[i] =
        false;

      irStallStart[i] =
        0;
    }
  }

  if (
    anyStalled &&
    !stallAlertActive &&
    !congestionActive
  ) {

    triggerAlert(
      STALLED_VEHICLE
    );
  }

  if (stallAlertActive) {

    static unsigned long
      lastFlash = 0;

    if (
      millis() -
      lastFlash >=
      300
    ) {

      stalledLEDs();

      lastFlash =
        millis();
    }
  }
}

// =====================================================
// CONGESTION DETECTION
// =====================================================
//
// ANY TWO OR MORE IR SENSORS must remain blocked
// continuously for 15 seconds.
//
// =====================================================

void checkCongestion() {

  int occupied = 0;

  int pins[4] = {
    IR1_PIN,
    IR2_PIN,
    IR3_PIN,
    IR4_PIN
  };

  for (
    int i = 0;
    i < 4;
    i++
  ) {

    if (
      digitalRead(
        pins[i]
      ) == LOW
    ) {

      occupied++;
    }
  }

  // ---------------------------------------------------
  // TWO OR MORE VEHICLES / SENSORS ACTIVE
  // ---------------------------------------------------

  if (occupied >= 2) {

    if (
      congestionStart == 0
    ) {

      congestionStart =
        millis();
    }

    if (
      millis() -
      congestionStart >=
      CONGESTION_TIME
    ) {

      if (!congestionActive) {

        congestionActive =
          true;

        triggerAlert(
          CONGESTION
        );
      }
    }

  } else {

    congestionStart =
      0;

    if (congestionActive) {

      congestionActive =
        false;

      updateSpeedLimit();

      LinkSerial.print("LIMIT:");
      LinkSerial.println((int)permittedSpeed);
    }
  }
}

// =====================================================
// WRONG WAY
// =====================================================
//
// IR4 -> IR3 = WRONG
// IR3 -> IR4 = NORMAL
// =====================================================

void checkWrongWay() {

  bool ir3 =
    digitalRead(
      IR3_PIN
    ) == LOW;

  bool ir4 =
    digitalRead(
      IR4_PIN
    ) == LOW;

  // IR3 first = normal
  if (
    ir3 &&
    !lastIR3
  ) {

    if (!ir4FirstDetected) {

      ir4FirstDetected =
        false;
    }
  }

  // IR4 first
  if (
    ir4 &&
    !lastIR4
  ) {

    ir4FirstDetected =
      true;

    ir4DetectionTime =
      millis();
  }

  // IR4 -> IR3
  if (
    ir3 &&
    !lastIR3 &&
    ir4FirstDetected
  ) {

    unsigned long elapsed =
      millis() -
      ir4DetectionTime;

    if (
      elapsed <=
      WRONG_WAY_WINDOW
    ) {

      triggerAlert(
        WRONG_WAY
      );
    }

    ir4FirstDetected =
      false;
  }

  // Timeout
  if (
    ir4FirstDetected &&
    millis() -
    ir4DetectionTime >
    WRONG_WAY_WINDOW
  ) {

    ir4FirstDetected =
      false;
  }

  lastIR3 =
    ir3;

  lastIR4 =
    ir4;
}

// =====================================================
// ULTRASONIC DISTANCE
// =====================================================

float getDistance(
  int trig,
  int echo
) {

  digitalWrite(
    trig,
    LOW
  );

  delayMicroseconds(
    2
  );

  digitalWrite(
    trig,
    HIGH
  );

  delayMicroseconds(
    10
  );

  digitalWrite(
    trig,
    LOW
  );

  unsigned long duration =
    pulseIn(
      echo,
      HIGH,
      20000
    );

  if (
    duration == 0
  ) {

    return -1;
  }

  return
    duration *
    0.0343 /
    2.0;
}

// =====================================================
// VEHICLE SPEED
// =====================================================
//
// US1 detects vehicle
//       ↓
// start timer
//       ↓
// US2 detects vehicle
//       ↓
// calculate actual speed
//       ↓
// display speed
//       ↓
// if speed > permitted speed + margin
// show OVERSPEED / RASH DRIVING
//
// =====================================================

void checkVehicleSpeed() {

  if (!speedMeasureMode)
    return;

  // No vehicle detected -> requested demo value.
  if (
    millis() - speedMeasureStart >=
    SPEED_MEASURE_TIMEOUT
  ) {

    measuredVehicleSpeed = DEMO_SPEED;

    showMeasuredSpeed(DEMO_SPEED);

    LinkSerial.print("SPEED:");
    LinkSerial.println(DEMO_SPEED, 1);

    speedMeasureMode = false;
    speedDisplayStart = millis();

    return;
  }

  float d1 =
    getDistance(
      US1_TRIG,
      US1_ECHO
    );

  bool us1Detected =
    d1 > 0 &&
    d1 < 40;

  if (
    us1Detected &&
    !lastUS1Detected
  ) {

    vehicleAtUS1 = true;
    us1Time = micros();
  }

  lastUS1Detected = us1Detected;

  float d2 =
    getDistance(
      US2_TRIG,
      US2_ECHO
    );

  bool us2Detected =
    d2 > 0 &&
    d2 < 40;

  if (
    us2Detected &&
    !lastUS2Detected &&
    vehicleAtUS1
  ) {

    unsigned long elapsed =
      micros() - us1Time;

    if (
      elapsed >= 10000 &&
      elapsed <= 10000000UL
    ) {

      float seconds =
        elapsed / 1000000.0;

      float speed =
        (
          SENSOR_DISTANCE /
          seconds
        ) * 3.6;

      if (
        speed > 0 &&
        speed < 200
      ) {

        measuredVehicleSpeed = speed;
        speedDisplayStart = millis();
        speedMeasureMode = false;

        LinkSerial.print("SPEED:");
        LinkSerial.println(speed, 1);

        // Mandatory SentraX Change: Compare against toy-car low-speed threshold
        if (
          speed >
          DEMO_OVERSPEED_LIMIT
        ) {

          triggerAlert(RASH_DRIVING);

        } else {

          activeAlert = NORMAL;
          showMeasuredSpeed(speed);
        }
      }
    }

    vehicleAtUS1 = false;
  }

  lastUS2Detected = us2Detected;

  if (
    vehicleAtUS1 &&
    micros() - us1Time >
    10000000UL
  ) {

    vehicleAtUS1 = false;
  }
}

void checkSpeedButton() {

  bool state =
    digitalRead(
      SPEED_BUTTON_PIN
    );

  if (
    state == LOW &&
    lastButtonState == HIGH
  ) {

    speedMeasureMode = true;
    speedMeasureStart = millis();

    vehicleAtUS1 = false;
    lastUS1Detected = false;
    lastUS2Detected = false;

    measuredVehicleSpeed = DEMO_SPEED;
    speedDisplayStart = 0;
    activeAlert = NORMAL;

    showCalculatingSpeedScreen();

    LinkSerial.println("SPEED_MODE");

    delay(50);
  }

  lastButtonState = state;
}


// =====================================================
// SPEED LIMIT
// =====================================================
//
// Priority:
//
// 1. Wet road = 40
// 2. Congestion = 60
// 3. Normal = 80
//
// =====================================================

void updateSpeedLimit() {

  if (wetRoadActive) {
    permittedSpeed = WET_SPEED;
    return;
  }

  if (highTemperatureActive) {
    permittedSpeed = TEMP_SPEED;
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

  while (
    LinkSerial.available()
  ) {

    String msg =
      LinkSerial.readStringUntil(
        '\n'
      );

    msg.trim();

    if (
      msg ==
      "ESP8266_READY"
    ) {

      LinkSerial.println(
        "ESP32_READY"
      );
    }

    else if (
      msg ==
      "NIGHT"
    ) {

      nightMode =
        true;
    }

    else if (
      msg ==
      "DAY"
    ) {

      nightMode =
        false;
    }

    else if (
      msg ==
      "RFID"
    ) {

      rfidEmergencyActive = true;
      triggerAlert(
        EMERGENCY
      );
    }
  }
}

// =====================================================
// SETUP
// =====================================================

void setup() {
  // ===================================================
  // SERIAL & BLE INITIALIZATION
  // ===================================================
  Serial.begin(115200);

  BLEDevice::init("SENTRAX-ESP32");
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
  pBLEAdvertising->setScanResponse(true);
  pBLEAdvertising->setMinPreferred(0x06);
  pBLEAdvertising->setMinPreferred(0x12);
  BLEDevice::startAdvertising();


  // ===================================================
  // COMMUNICATION
  // ===================================================

  LinkSerial.begin(
    9600,
    SERIAL_8N1,
    LINK_RX,
    LINK_TX
  );

  // ===================================================
  // IR
  // ===================================================

  pinMode(
    IR1_PIN,
    INPUT
  );

  pinMode(
    IR2_PIN,
    INPUT
  );

  pinMode(
    IR3_PIN,
    INPUT
  );

  pinMode(
    IR4_PIN,
    INPUT
  );

  // ===================================================
  // SOUND
  // ACTIVE HIGH
  // ===================================================

  pinMode(
    SOUND_PIN,
    INPUT
  );

  pinMode(
    SPEED_BUTTON_PIN,
    INPUT_PULLUP
  );

  // ===================================================
  // MOISTURE
  // ===================================================

  pinMode(
    MOISTURE_PIN,
    INPUT
  );

  // ===================================================
  // ULTRASONIC 1
  // ===================================================

  pinMode(
    US1_TRIG,
    OUTPUT
  );

  pinMode(
    US1_ECHO,
    INPUT
  );

  // ===================================================
  // ULTRASONIC 2
  // ===================================================

  pinMode(
    US2_TRIG,
    OUTPUT
  );

  pinMode(
    US2_ECHO,
    INPUT
  );

  // ===================================================
  // DHT11
  // ===================================================

  dht.begin();

  // ===================================================
  // LED STRIP
  // ===================================================

  leds.begin();

  leds.setBrightness(
    50
  );

  normalLEDs();

  // ===================================================
  // E-INK SPI & INITIALIZATION
  // ===================================================

  // Explicitly initialize ESP32 VSPI pins for Waveshare E-Paper:
  // SCK = GPIO 18, MISO = GPIO 19, MOSI = GPIO 23, SS = GPIO 16 (EINK_CS)
  SPI.begin(18, 19, 23, EINK_CS);

  pinMode(EINK_BUSY, INPUT);
  pinMode(EINK_RST, OUTPUT);
  pinMode(EINK_DC, OUTPUT);
  pinMode(EINK_CS, OUTPUT);

  // Initialize GxEPD2 with a reliable 20ms reset duration for Waveshare
  eink.init(
    115200,
    true,
    20,
    false
  );

  showNormalScreen();

  delay(300);

  LinkSerial.println(
    "ESP32_READY"
  );
}

// =====================================================
// MAIN LOOP
// =====================================================

void loop() {

  // ===================================================
  // ESP8266 COMMUNICATION
  // ===================================================

  receiveESP8266();

  // ===================================================
  // SPEED BUTTON
  // ===================================================

  checkSpeedButton();

  // ===================================================
  // CONGESTION
  // ===================================================

  checkCongestion();

  // ===================================================
  // WRONG WAY
  // ===================================================

  checkWrongWay();

  // ===================================================
  // STALLED VEHICLE
  // ===================================================

  checkStalledVehicle();

  // ===================================================
  // COLLISION / SOUND SENSOR
  // ACTIVE HIGH
  // ===================================================

  bool collision =
    digitalRead(
      SOUND_PIN
    ) == HIGH;

  if (
    collision &&
    !lastCollision
  ) {

    triggerAlert(
      COLLISION
    );
  }

  lastCollision =
    collision;

  // ===================================================
  // ULTRASONIC
  // ===================================================

  checkVehicleSpeed();

  // ===================================================
  // DHT11
  // ===================================================

  float temperature =
    dht.readTemperature();

  float humidity =
    dht.readHumidity();

  // ===================================================
  // TEMPERATURE
  // ===================================================

  if (
    !isnan(
      temperature
    )
  ) {

    bool highTemp =
      temperature >=
      HIGH_TEMP;

    if (
      highTemp &&
      !lastHighTemp
    ) {

      highTemperatureActive = true;
      permittedSpeed = TEMP_SPEED;

      triggerAlert(
        HIGH_TEMP_ALERT
      );
    }

    if (!highTemp) {
      highTemperatureActive = false;
    }

    lastHighTemp =
      highTemp;
  }

  // ===================================================
  // HUMIDITY
  // ===================================================

  if (
    !isnan(
      humidity
    )
  ) {

    bool highHumidity =
      humidity >=
      HIGH_HUMIDITY;

    if (
      highHumidity &&
      !lastHighHumidity
    ) {

      triggerAlert(
        HIGH_HUMIDITY_ALERT
      );
    }

    lastHighHumidity =
      highHumidity;
  }

  // ===================================================
  // MOISTURE / WATER SENSOR
  // ===================================================

  int moisture =
    analogRead(
      MOISTURE_PIN
    );

  bool wet =
    moisture <
    MOISTURE_THRESHOLD;

  // ---------------------------------------------------
  // ROAD BECOMES WET
  // ---------------------------------------------------

  if (
    wet &&
    !lastWet
  ) {

    wetRoadActive =
      true;

    permittedSpeed =
      WET_SPEED;

    triggerAlert(
      WET_ROAD
    );
  }

  // ---------------------------------------------------
  // ROAD REMAINS WET
  // ---------------------------------------------------

  if (wet) {

    wetRoadActive =
      true;

    permittedSpeed =
      WET_SPEED;

    // Flash ALL LEDs white
    if (
      millis() -
      lastWetFlash >=
      WET_FLASH_TIME
    ) {

      wetRoadLEDs();

      lastWetFlash =
        millis();
    }

    // Keep wet-road screen active
    if (
      activeAlert != WET_ROAD
    ) {

      activeAlert =
        WET_ROAD;

      showWetScreen();
    }
  }

  // ---------------------------------------------------
  // ROAD BECOMES DRY
  // ---------------------------------------------------

  if (
    !wet &&
    lastWet
  ) {

    wetRoadActive =
      false;

    updateSpeedLimit();

    activeAlert =
      NORMAL;

    normalLEDs();

    showNormalScreen();

    LinkSerial.println("NORMAL");
    LinkSerial.print("LIMIT:");
    LinkSerial.println((int)permittedSpeed);
  }

  lastWet =
    wet;

  // ===================================================
  // UPDATE SPEED PRIORITY
  // ===================================================

  updateSpeedLimit();

  // ===================================================
  // CONGESTION DISPLAY
  // ===================================================

  if (
    congestionActive &&
    !wetRoadActive &&
    activeAlert == CONGESTION
  ) {

    showCongestionScreen();

    congestionLEDs();
  }

  // ===================================================
  // ALERT TIMEOUT
  // ===================================================

  if (
    activeAlert != NORMAL &&
    activeAlert != WET_ROAD &&
    activeAlert != CONGESTION &&
    millis() -
    alertStart >=
    ALERT_TIME
  ) {

    activeAlert =
      NORMAL;

    stallAlertActive =
      false;

    rfidEmergencyActive =
      false;

    updateSpeedLimit();

    normalLEDs();

    LinkSerial.println("NORMAL");
    LinkSerial.print("LIMIT:");
    LinkSerial.println((int)permittedSpeed);

    showNormalScreen();
  }

  // ===================================================
  // SPEED SCREEN TIMEOUT
  // ===================================================

  if (
    speedDisplayStart > 0 &&
    millis() -
    speedDisplayStart >=
    SPEED_DISPLAY_TIME
  ) {

    speedDisplayStart = 0;

    updateSpeedLimit();

    activeAlert = NORMAL;

    showNormalScreen();

    LinkSerial.println("NORMAL");
    LinkSerial.print("LIMIT:");
    LinkSerial.println((int)permittedSpeed);
  }

  // ===================================================
  // WET ROAD ALWAYS HAS PRIORITY
  // ===================================================

  if (wetRoadActive) {

    permittedSpeed =
      WET_SPEED;

    activeAlert =
      WET_ROAD;

    if (
      millis() -
      lastWetFlash >=
      WET_FLASH_TIME
    ) {

      wetRoadLEDs();

      lastWetFlash =
        millis();
    }
  }

  
  // ===================================================
  // BLE & SERIAL LIVE TELEMETRY BROADCAST
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
    teleJson += "\"alert\":\"" + alertStr + "\"}";

    // Broadcast over BLE if client connected
    if (bleClientConnected && pBLETelemetryChar != NULL) {
      pBLETelemetryChar->setValue(teleJson.c_str());
      pBLETelemetryChar->notify();
    }

    // Also output on USB Serial for direct COM port live cable ingestion
    Serial.println(teleJson);
  }
delay(10);
}