import os

esp8266_src = r"C:\Users\vishw\OneDrive\Documents\Arduino\ESP8266_RFID_5_BEEPS_LCD_FIXED\ESP8266_RFID_5_BEEPS_LCD_FIXED.ino"

with open(esp8266_src, "r") as f:
    content = f.read()

# Make sure ESP8266 handles both direct state words (like COLLISION) and STATE:COLLISION
target = '    else if (\n      msg.startsWith(\n        "STATE:"\n      )\n    ) {\n\n      String state =\n        msg.substring(\n          6\n        );'

replacement = '''    else if (
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

      String state = msg.startsWith("STATE:") ? msg.substring(6) : msg;'''

if target in content:
    content = content.replace(target, replacement)
    print("Enhanced ESP8266 message reception for direct + STATE: protocols.")
else:
    print("Note: target pattern not matched verbatim, writing exact file as authoritative.")

with open(r"firmware\esp8266\SentraX_ESP8266.ino", "w") as f:
    f.write(content)

with open(r"firmware\esp8266\ESP8266_RFID_5_BEEPS_LCD_FIXED.ino", "w") as f:
    f.write(content)

print("ESP8266 firmware saved successfully.")
