import asyncio
from bleak import BleakClient

# Device details
ADDRESS = "E1:6A:83:06:38:48"
WRITE_UUID = "cba20002-224d-11e6-9fb8-0002a5d5c51b" # The one you just found!
PRESS_COMMAND = bytearray([0x57, 0x01, 0x01])

async def trigger_seestar():
    print(f"Connecting to Seestar Fingerbot...")
    try:
        async with BleakClient(ADDRESS) as client:
            print("Connected. Sending press command...")
            # Send the press
            await client.write_gatt_char(WRITE_UUID, PRESS_COMMAND, response=True)
            print("Command sent. Waiting 8 seconds...")
            await asyncio.sleep(8)
            print("Clear skies, Brian!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(trigger_seestar())