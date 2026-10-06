"""
SentraX BLE Signal Diagnostic Tool
Scans for nearby Bluetooth Low Energy (BLE) peripherals and verifies if SENTRAX-ESP32 is actively broadcasting.
"""

import asyncio
import sys

try:
    from bleak import BleakScanner
except ImportError:
    print("[ERROR] 'bleak' is not installed. Run: pip install bleak")
    sys.exit(1)


async def main():
    print("=" * 65)
    print("      SENTRAX BLE DIAGNOSTIC SCANNER")
    print("      Scanning for nearby BLE devices (5 seconds)...")
    print("=" * 65)

    try:
        devices = await BleakScanner.discover(timeout=5.0, return_adv=True)
    except Exception as e:
        print(f"[ERROR] Failed to access Bluetooth hardware on your PC: {e}")
        print("Please ensure your Windows Bluetooth is turned ON in Settings.")
        return

    found_esp32 = False
    print(f"\nTotal BLE advertisements detected: {len(devices)}\n")

    for address, (device, adv) in devices.items():
        name = device.name or adv.local_name or "Unknown / Unnamed"
        rssi = adv.rssi

        if "SENTRAX" in name.upper() or (adv.service_uuids and any("73656e74" in u.lower() for u in adv.service_uuids)):
            found_esp32 = True
            print("*" * 65)
            print(f" [SUCCESS] FOUND SENTRAX ESP32!")
            print(f"  - Advertised Name:  {name}")
            print(f"  - MAC / Address:    {device.address}")
            print(f"  - Signal Strength:  {rssi} dBm (RSSI)")
            print(f"  - Service UUIDs:    {adv.service_uuids}")
            print("*" * 65)
        else:
            if name != "Unknown / Unnamed":
                print(f"  • {name} [{device.address}] - RSSI: {rssi} dBm")

    print("\n" + "=" * 65)
    if found_esp32:
        print("RESULT: SUCCESS - The ESP32 IS ACTIVELY BROADCASTING A BLUETOOTH SIGNAL!")
    else:
        print("RESULT: 'SENTRAX-ESP32' WAS NOT DETECTED IN THIS SCAN.")
        print("\nTroubleshooting Checklist:")
        print(" 1. Is the ESP32 powered on? (Red power LED solid ON)")
        print(" 2. Did you flash firmware/esp32/SentraX_ESP32.ino with BLEDevice::init(\"SENTRAX-ESP32\")?")
        print(" 3. Open Arduino IDE Serial Monitor (115200 baud) on ESP32 COM port and look for:")
        print("    '[SENTRAX] BLE Active. Broadcast Name: SENTRAX-ESP32'")
        print(" 4. Make sure your PC Bluetooth is switched ON in Windows Settings.")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
