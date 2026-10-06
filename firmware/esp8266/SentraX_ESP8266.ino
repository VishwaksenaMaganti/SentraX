#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_GC9A01A.h>
#include <MFRC522.h>
#include <SoftwareSerial.h>

// =====================================================
// GC9A01
// =====================================================

#define TFT_CS D4
#define TFT_DC D3

Adafruit_GC9A01A tft(
  TFT_CS,
  TFT_DC,
  -1
);

// =====================================================
// RFID
// =====================================================

#define RFID_SS D8
#define RFID_RST 3

MFRC522 rfid(
  RFID_SS,
  RFID_RST
);

// =====================================================
// ESP32 COMMUNICATION
// =====================================================

#define LINK_RX D0
#define LINK_TX D1

SoftwareSerial linkSerial(
  LINK_RX,
  LINK_TX
);

// =====================================================
// LDR
// =====================================================

#define LDR_PIN A0

#define DARK_WHEN_HIGH true

#define NIGHT_THRESHOLD 500

// =====================================================
// BUZZER
// =====================================================

#define BUZZER_PIN D2

// =====================================================
// IMPORTANT
// =====================================================
//
// GPIO1/TX was previously used for the LED strip.
//
// ESP32 is now the ONLY LED data driver.
//
// The ESP8266 LED data pin must NOT be configured
// as an output.
//
// If the physical LED data wire is still connected
// to GPIO1, this code leaves it high impedance.
// =====================================================

#define LED_DATA_PIN 1

// =====================================================
// STATE
// =====================================================

bool nightMode =
  false;

String currentStatus =
  "NORMAL";

int currentSpeed =
  80;

unsigned long lastHeartbeat =
  0;

// =====================================================
// BUZZER STATE
// =====================================================

bool buzzerActive =
  false;

int beepStep =
  0;

unsigned long beepTimer =
  0;

// RFID-specific beep control
bool rfidBuzzerMode = false;
int completedBeeps = 0;
const int RFID_BEEP_COUNT = 5;

// =====================================================
// BLANK DISPLAY
// =====================================================

void blankLCD() {

  tft.fillScreen(
    GC9A01A_BLACK
  );
}

// =====================================================
// NIGHT NORMAL
// =====================================================

void showNightNormal() {

  tft.fillScreen(
    GC9A01A_BLACK
  );

  tft.setTextColor(
    GC9A01A_GREEN
  );

  tft.setTextSize(2);

  tft.setCursor(
    40,
    15
  );

  tft.println(
    "SENTRAX"
  );

  tft.setTextColor(
    GC9A01A_WHITE
  );

  tft.setTextSize(5);

  tft.setCursor(
    40,
    55
  );

  tft.println(
    currentSpeed
  );

  tft.setTextSize(2);

  tft.setCursor(
    110,
    75
  );

  tft.println(
    "KM/H"
  );

  tft.setTextSize(1);

  tft.setCursor(
    55,
    130
  );

  tft.println(
    "ROAD CLEAR"
  );

  tft.setCursor(
    60,
    150
  );

  tft.println(
    "NIGHT MODE"
  );
}

// =====================================================
// COLLISION
// =====================================================

void showCollision() {

  tft.fillScreen(
    GC9A01A_BLACK
  );

  tft.setTextColor(
    GC9A01A_RED
  );

  tft.setTextSize(3);

  tft.setCursor(
    25,
    25
  );

  tft.println(
    "COLLISION"
  );

  tft.setTextColor(
    GC9A01A_WHITE
  );

  tft.setTextSize(2);

  tft.setCursor(
    50,
    90
  );

  tft.println(
    "ACCIDENT"
  );

  tft.setCursor(
    65,
    120
  );

  tft.println(
    "DETECTED"
  );
}

// =====================================================
// WRONG WAY
// =====================================================

void showWrongWay() {

  tft.fillScreen(
    GC9A01A_BLACK
  );

  tft.setTextColor(
    GC9A01A_RED
  );

  tft.setTextSize(3);

  tft.setCursor(
    20,
    25
  );

  tft.println(
    "WRONG WAY"
  );

  tft.setTextColor(
    GC9A01A_WHITE
  );

  tft.setTextSize(2);

  tft.setCursor(
    50,
    95
  );

  tft.println(
    "VEHICLE"
  );

  tft.setCursor(
    45,
    125
  );

  tft.println(
    "APPROACHING"
  );
}

// =====================================================
// EMERGENCY
// =====================================================

void showEmergency() {

  tft.fillScreen(
    GC9A01A_RED
  );

  tft.setTextColor(
    GC9A01A_WHITE
  );

  tft.setTextSize(3);

  tft.setCursor(
    25,
    35
  );

  tft.println(
    "EMERGENCY"
  );

  tft.setTextSize(2);

  tft.setCursor(
    50,
    90
  );

  tft.println(
    "AMBULANCE"
  );

  tft.setCursor(
    60,
    120
  );

  tft.println(
    "DETECTED"
  );
}

// =====================================================
// RASH DRIVING
// =====================================================

void showRash() {

  tft.fillScreen(
    GC9A01A_BLACK
  );

  tft.setTextColor(
    GC9A01A_RED
  );

  tft.setTextSize(3);

  tft.setCursor(
    20,
    25
  );

  tft.println(
    "RASH"
  );

  tft.setCursor(
    15,
    60
  );

  tft.println(
    "DRIVING"
  );

  tft.setTextColor(
    GC9A01A_WHITE
  );

  tft.setTextSize(2);

  tft.setCursor(
    35,
    110
  );

  tft.println(
    "OVERSPEED!"
  );

  tft.setCursor(
    70,
    145
  );

  tft.print(
    currentSpeed
  );

  tft.println(
    " KM/H"
  );
}

// =====================================================
// WET ROAD
// =====================================================

void showWet() {

  tft.fillScreen(
    GC9A01A_BLACK
  );

  tft.setTextColor(
    GC9A01A_BLUE
  );

  tft.setTextSize(3);

  tft.setCursor(
    40,
    40
  );

  tft.println(
    "ROAD WET"
  );

  tft.setTextColor(
    GC9A01A_WHITE
  );

  tft.setTextSize(2);

  tft.setCursor(
    45,
    100
  );

  tft.println(
    "SPEED 40"
  );

  tft.setCursor(
    50,
    130
  );

  tft.println(
    "SLOW DOWN"
  );
}

// =====================================================
// HIGH TEMP
// =====================================================

void showTemp() {

  tft.fillScreen(
    GC9A01A_BLACK
  );

  tft.setTextColor(
    GC9A01A_RED
  );

  tft.setTextSize(3);

  tft.setCursor(
    30,
    35
  );

  tft.println(
    "HIGH TEMP"
  );

  tft.setTextColor(
    GC9A01A_WHITE
  );

  tft.setTextSize(2);

  tft.setCursor(
    55,
    100
  );

  tft.println(
    "SPEED 35"
  );

  tft.setCursor(
    65,
    130
  );

  tft.println(
    "SLOW"
  );
}

// =====================================================
// HUMIDITY
// =====================================================

void showHumidity() {

  tft.fillScreen(
    GC9A01A_BLACK
  );

  tft.setTextColor(
    GC9A01A_WHITE
  );

  tft.setTextSize(3);

  tft.setCursor(
    15,
    35
  );

  tft.println(
    "HUMIDITY"
  );

  tft.setTextSize(2);

  tft.setCursor(
    45,
    105
  );

  tft.println(
    "REDUCE SPEED"
  );

  tft.setCursor(
    65,
    135
  );

  tft.println(
    "CAUTION"
  );
}

// =====================================================
// STALLED
// =====================================================

void showStalled() {

  tft.fillScreen(
    GC9A01A_BLACK
  );

  tft.setTextColor(
    GC9A01A_RED
  );

  tft.setTextSize(3);

  tft.setCursor(
    15,
    30
  );

  tft.println(
    "VEHICLE"
  );

  tft.setCursor(
    15,
    70
  );

  tft.println(
    "STOPPED"
  );

  tft.setTextColor(
    GC9A01A_WHITE
  );

  tft.setTextSize(2);

  tft.setCursor(
    45,
    125
  );

  tft.println(
    "WARNING"
  );
}

// =====================================================
// CONGESTION
// =====================================================

void showCongestion() {

  tft.fillScreen(
    GC9A01A_BLACK
  );

  tft.setTextColor(
    GC9A01A_YELLOW
  );

  tft.setTextSize(3);

  tft.setCursor(
    20,
    35
  );

  tft.println(
    "CONGESTION"
  );

  tft.setTextColor(
    GC9A01A_WHITE
  );

  tft.setTextSize(4);

  tft.setCursor(
    65,
    90
  );

  tft.println(
    "60"
  );

  tft.setTextSize(2);

  tft.setCursor(
    105,
    105
  );

  tft.println(
    "KM/H"
  );

  tft.setTextSize(2);

  tft.setCursor(
    45,
    145
  );

  tft.println(
    "SLOW TRAFFIC"
  );
}

// =====================================================
// VEHICLE SPEED
// =====================================================

void showSpeed(
  float speed
) {

  tft.fillScreen(
    GC9A01A_BLACK
  );

  tft.setTextColor(
    GC9A01A_WHITE
  );

  tft.setTextSize(2);

  tft.setCursor(
    30,
    10
  );

  tft.println(
    "VEHICLE CZO5"
  );

  tft.setTextSize(2);

  tft.setCursor(
    65,
    38
  );

  tft.println(
    "SPEED"
  );

  tft.setTextSize(5);

  tft.setCursor(
    35,
    65
  );

  tft.println(
    speed,
    1
  );

  tft.setTextSize(2);

  tft.setCursor(
    110,
    85
  );

  tft.println(
    "KM/H"
  );
}

// =====================================================
// BUZZER
// =====================================================

void startBuzzer() {

  buzzerActive =
    true;

  rfidBuzzerMode =
    false;

  completedBeeps =
    0;

  beepStep =
    0;

  beepTimer =
    millis();
}

void startRFIDBuzzer() {

  buzzerActive =
    true;

  rfidBuzzerMode =
    true;

  completedBeeps =
    0;

  beepStep =
    0;

  beepTimer =
    millis();
}

void stopBuzzer() {

  buzzerActive =
    false;

  noTone(
    BUZZER_PIN
  );

  beepStep =
    0;

  completedBeeps =
    0;

  rfidBuzzerMode =
    false;
}

// =====================================================
// DUAL BEEP
// =====================================================

void processBuzzer() {

  if (
    !buzzerActive
  ) {
    return;
  }

  unsigned long now =
    millis();

  switch (
    beepStep
  ) {

    case 0:

      tone(
        BUZZER_PIN,
        2200
      );

      beepTimer =
        now;

      beepStep =
        1;

      break;

    case 1:

      if (
        now -
        beepTimer >=
        120
      ) {

        noTone(
          BUZZER_PIN
        );

        beepTimer =
          now;

        beepStep =
          2;
      }

      break;

    case 2:

      if (
        now -
        beepTimer >=
        100
      ) {

        tone(
          BUZZER_PIN,
          2200
        );

        beepTimer =
          now;

        beepStep =
          3;
      }

      break;

    case 3:

      if (
        now -
        beepTimer >=
        120
      ) {

        noTone(
          BUZZER_PIN
        );

        // One complete dual-beep finished.
        completedBeeps++;

        beepTimer =
          now;

        beepStep =
          4;
      }

      break;

    case 4:

      // RFID: stop immediately after exactly 5
      // complete dual-beep cycles.
      if (
        rfidBuzzerMode &&
        completedBeeps >=
        RFID_BEEP_COUNT
      ) {

        noTone(
          BUZZER_PIN
        );

        buzzerActive =
          false;

        rfidBuzzerMode =
          false;

        beepStep =
          0;

        completedBeeps =
          0;

        // End RFID alert on LCD.
        currentStatus =
          "NORMAL";

        if (
          nightMode
        ) {

          showNightNormal();

        } else {

          blankLCD();
        }

      } else if (
        now -
        beepTimer >=
        700
      ) {

        beepStep =
          0;
      }

      break;
  }
}

// =====================================================
// RFID
// =====================================================

void checkRFID() {

  if (
    !rfid.PICC_IsNewCardPresent()
  ) {

    return;
  }

  if (
    !rfid.PICC_ReadCardSerial()
  ) {

    return;
  }

  // RFID event goes to ESP32.
  // ESP32 controls the LED pattern.
  linkSerial.println(
    "RFID"
  );

  // Night display immediately shows it.
  currentStatus =
    "EMERGENCY";

  startRFIDBuzzer();

  if (
    nightMode
  ) {

    showEmergency();
  }

  rfid.PICC_HaltA();

  rfid.PCD_StopCrypto1();

  delay(300);
}

// =====================================================
// ESP32 MESSAGE
// =====================================================

void receiveESP32() {

  while (
    linkSerial.available()
  ) {

    String msg =
      linkSerial.readStringUntil(
        '\n'
      );

    msg.trim();

    if (
      msg.length() == 0
    ) {

      continue;
    }

    // -------------------------------------------------
    // READY
    // -------------------------------------------------

    if (
      msg ==
      "ESP32_READY"
    ) {

      linkSerial.println(
        "ESP8266_READY"
      );
    }

    // -------------------------------------------------
    // STATE
    // -------------------------------------------------

    else if (
      msg.startsWith("STATE:") ||
      msg == "COLLISION" ||
      msg == "WRONG" ||
      msg == "EMERGENCY" ||
      msg == "RASH" ||
      msg == "WET" ||
      msg == "TEMP" ||
      msg == "HUMIDITY" ||
      msg == "STALLED" ||
      msg == "CONGESTION"
    ) {

      String state = msg.startsWith("STATE:") ? msg.substring(6) : msg;

      currentStatus =
        state;

      if (
        state ==
        "COLLISION"
      ) {

        startBuzzer();

        if (nightMode)
          showCollision();

      }

      else if (
        state ==
        "WRONG"
      ) {

        startBuzzer();

        if (nightMode)
          showWrongWay();

      }

      else if (
        state ==
        "EMERGENCY"
      ) {

        if (
          !rfidBuzzerMode
        ) {

          startBuzzer();
        }

        if (nightMode)
          showEmergency();

      }

      else if (
        state ==
        "RASH"
      ) {

        startBuzzer();

        if (nightMode)
          showRash();

      }

      else if (
        state ==
        "WET"
      ) {

        startBuzzer();

        if (nightMode)
          showWet();

      }

      else if (
        state ==
        "TEMP"
      ) {

        startBuzzer();

        if (nightMode)
          showTemp();

      }

      else if (
        state ==
        "HUMIDITY"
      ) {

        startBuzzer();

        if (nightMode)
          showHumidity();

      }

      else if (
        state ==
        "STALLED"
      ) {

        startBuzzer();

        if (nightMode)
          showStalled();

      }

      else if (
        state ==
        "CONGESTION"
      ) {

        startBuzzer();

        if (nightMode)
          showCongestion();

      }

      else if (
        state ==
        "NORMAL"
      ) {

        stopBuzzer();

        if (nightMode)
          showNightNormal();
        else
          blankLCD();
      }
    }

    // -------------------------------------------------
    // LIMIT
    // -------------------------------------------------

    else if (
      msg.startsWith(
        "LIMIT:"
      )
    ) {

      currentSpeed =
        msg.substring(
          6
        ).toInt();

      if (
        currentStatus ==
        "NORMAL" &&
        nightMode
      ) {

        showNightNormal();
      }
    }

    // -------------------------------------------------
    // SPEED
    // -------------------------------------------------

    else if (
      msg.startsWith(
        "SPEED:"
      )
    ) {

      float speed =
        msg.substring(
          6
        ).toFloat();

      currentStatus =
        "SPEED";

      if (
        nightMode
      ) {

        showSpeed(
          speed
        );
      }
    }

    // -------------------------------------------------
    // SPEED MODE
    // -------------------------------------------------

    else if (
      msg ==
      "SPEED_MODE"
    ) {

      currentStatus =
        "SPEED";

      if (
        nightMode
      ) {

        tft.fillScreen(
          GC9A01A_BLACK
        );

        tft.setTextColor(
          GC9A01A_WHITE
        );

        tft.setTextSize(2);

        tft.setCursor(
          30,
          35
        );

        tft.println(
          "VEHICLE CZO5"
        );

        tft.setCursor(
          50,
          80
        );

        tft.println(
          "MEASURING..."
        );
      }
    }

    // -------------------------------------------------
    // NORMAL
    // -------------------------------------------------

    else if (
      msg ==
      "NORMAL"
    ) {

      currentStatus =
        "NORMAL";

      stopBuzzer();

      if (
        nightMode
      ) {

        showNightNormal();

      } else {

        blankLCD();
      }
    }

    // -------------------------------------------------
    // NIGHT
    // -------------------------------------------------

    else if (
      msg ==
      "NIGHT"
    ) {

      nightMode =
        true;

      if (
        currentStatus ==
        "NORMAL"
      ) {

        showNightNormal();

      } else {

        redrawCurrentStatus();
      }
    }

    // -------------------------------------------------
    // DAY
    // -------------------------------------------------

    else if (
      msg ==
      "DAY"
    ) {

      nightMode =
        false;

      blankLCD();
    }
  }
}

// =====================================================
// REDRAW CURRENT EVENT
// =====================================================

void redrawCurrentStatus() {

  if (!nightMode) {

    blankLCD();

    return;
  }

  if (
    currentStatus ==
    "COLLISION"
  ) {

    showCollision();

  } else if (
    currentStatus ==
    "WRONG"
  ) {

    showWrongWay();

  } else if (
    currentStatus ==
    "EMERGENCY"
  ) {

    showEmergency();

  } else if (
    currentStatus ==
    "RASH"
  ) {

    showRash();

  } else if (
    currentStatus ==
    "WET"
  ) {

    showWet();

  } else if (
    currentStatus ==
    "TEMP"
  ) {

    showTemp();

  } else if (
    currentStatus ==
    "HUMIDITY"
  ) {

    showHumidity();

  } else if (
    currentStatus ==
    "STALLED"
  ) {

    showStalled();

  } else if (
    currentStatus ==
    "CONGESTION"
  ) {

    showCongestion();

  } else {

    showNightNormal();
  }
}

// =====================================================
// LDR
// =====================================================

void checkLDR() {

  int light =
    analogRead(
      LDR_PIN
    );

  bool newNight;

#if DARK_WHEN_HIGH

  newNight =
    light >
    NIGHT_THRESHOLD;

#else

  newNight =
    light <
    NIGHT_THRESHOLD;

#endif

  if (
    newNight !=
    nightMode
  ) {

    nightMode =
      newNight;

    if (
      nightMode
    ) {

      linkSerial.println(
        "NIGHT"
      );

      redrawCurrentStatus();

    } else {

      linkSerial.println(
        "DAY"
      );

      blankLCD();
    }
  }
}

// =====================================================
// SETUP
// =====================================================

void setup() {

  // Buzzer
  pinMode(
    BUZZER_PIN,
    OUTPUT
  );

  noTone(
    BUZZER_PIN
  );

  // IMPORTANT:
  // ESP8266 does NOT drive the LED strip.
  // Keep GPIO1 high impedance.
  pinMode(
    LED_DATA_PIN,
    INPUT
  );

  // Communication
  linkSerial.begin(
    9600
  );

  // SPI / RFID
  SPI.begin();

  rfid.PCD_Init();

  // TFT
  tft.begin();

  blankLCD();

  // Initial LDR
  int light =
    analogRead(
      LDR_PIN
    );

#if DARK_WHEN_HIGH

  nightMode =
    light >
    NIGHT_THRESHOLD;

#else

  nightMode =
    light <
    NIGHT_THRESHOLD;

#endif

  if (
    nightMode
  ) {

    showNightNormal();
  }

  linkSerial.println(
    "ESP8266_READY"
  );
}

// =====================================================
// LOOP
// =====================================================

void loop() {

  checkRFID();

  receiveESP32();

  checkLDR();

  processBuzzer();

  if (
    millis() -
    lastHeartbeat >=
    1500
  ) {

    linkSerial.println(
      "ESP8266_HEARTBEAT"
    );

    lastHeartbeat =
      millis();
  }

  delay(5);
}