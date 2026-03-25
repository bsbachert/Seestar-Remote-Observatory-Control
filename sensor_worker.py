import smbus2, bme280, time, os, subprocess, threading, math, serial
import RPi.GPIO as GPIO

# --- CONFIG ---
BME_ADDR = 0x76  
RAIN_PIN = 18  
ROOF_PIN = 17  
DEW_HEATER_PIN = 12  # PWM Signal to MOSFET [cite: 2026-02-03]
USB_PORT = "/dev/ttyUSB0" # Arduino Source
PATH_SENSORS = "/home/pi/allsky_guard/sensors.txt"
PATH_HOURS = "/home/pi/allsky_guard/hours.txt"

# --- GLOBAL DATA HOLDERS ---
latest_sky_temp = "WAIT..."
latest_wind_speed = 0.0

# --- HARDWARE SETUP ---
GPIO.setmode(GPIO.BCM)
GPIO.setup(RAIN_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def connect_serial():
    """Establishes a clean connection to the Arduino with buffer clearing."""
    try:
        # Check if the device path actually exists before trying to open
        if not os.path.exists(USB_PORT):
            return None
            
        s = serial.Serial(USB_PORT, 9600, timeout=2)
        time.sleep(2) # Wait for Arduino reset/bootup
        s.reset_input_buffer() # Clear any junk data from the freeze
        s.flush()
        print(f"Successfully connected to Arduino on {USB_PORT}")
        return s
    except Exception as e:
        print(f"Serial Connection Failed: {e}")
        return None

def arduino_reader():
    """Reads comma-separated Sky and Wind data with auto-reconnect logic."""
    global latest_sky_temp, latest_wind_speed
    ser = connect_serial()
    
    while True:
        if ser and ser.is_open:
            try:
                if ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    # Expecting format: "SKY TEMP:46.09,WIND:0.00"
                    if "SKY TEMP" in line and "WIND" in line:
                        parts = line.split(",")
                        temp_raw = parts[0].split(":")[1].strip()
                        latest_sky_temp = f"{temp_raw} F"
                        try:
                            latest_wind_speed = float(parts[1].split(":")[1].strip())
                        except:
                            pass
            except (serial.SerialException, OSError) as e:
                print(f"Lost Arduino connection: {e}")
                if ser: ser.close()
                ser = None # Trigger reconnect logic below
        else:
            # Reconnect attempt
            time.sleep(5) # Don't hammer the CPU/USB port
            ser = connect_serial()
            
        time.sleep(0.1)

def get_bme_data():
    try:
        bus = smbus2.SMBus(1)
        params = bme280.load_calibration_params(bus, BME_ADDR)
        data = bme280.sample(bus, BME_ADDR, params)
        bus.close()
        return (data.temperature * 9/5) + 32, data.humidity, f"{data.pressure:.1f} hPa"
    except:
        return None, None, "--"

def set_heater_state(is_on):
    state = "dh" if is_on else "dl"
    try:
        subprocess.run(["sudo", "pinctrl", "set", str(DEW_HEATER_PIN), "op", state], check=True)
    except:
        pass

# Start background thread for Arduino data
threading.Thread(target=arduino_reader, daemon=True).start()

last_check = time.time()
print("Sensor Worker started (Integrated Arduino Wind/Sky with Auto-Reconnect)...")

while True:
    time.sleep(5) 
    
    # --- 1. COLLECT DATA ---
    amb_f, hum_val, pre_str = get_bme_data()
    is_wet = GPIO.input(RAIN_PIN) == GPIO.LOW
    speed = latest_wind_speed 
    
    # --- 2. LOGIC ---
    heater_status = "OFF"
    if amb_f is not None and hum_val is not None:
        T = (amb_f - 32) * 5/9
        gamma = (math.log(hum_val/100) + ((17.27 * T) / (237.3 + T)))
        dew_f = ((237.3 * gamma) / (17.27 - gamma) * 9/5) + 32
        
        if (amb_f - dew_f) <= 5.0:
            set_heater_state(True)
            heater_status = "ON (DEW RISK)"
        else:
            set_heater_state(False)
    
    # Safety logic: If wind is excessive or rain detected, command roof close
    if is_wet or speed > 20.0:
        subprocess.run(["pinctrl", "set", str(ROOF_PIN), "dh"])
        status = "CLOSED/LOCKED"
    else:
        subprocess.run(["pinctrl", "set", str(ROOF_PIN), "dl"])
        status = "OPEN/SAFE"

    # --- OPERATION HOURS & CLEANING REMINDER [cite: 2026-01-17] ---
    now = time.time()
    elapsed = (now - last_check) / 3600.0
    last_check = now
    total = 0.0
    maint_alert = ""
    try:
        if os.path.exists(PATH_HOURS):
            with open(PATH_HOURS, "r") as hf: total = float(hf.read().strip())
        new_total = total + elapsed
        with open(PATH_HOURS, "w") as hf: hf.write(f"{new_total:.4f}")
        
        # [cite: 2026-01-17]
        if new_total >= 1000.0:
            maint_alert = "CLEANING REQUIRED"
    except:
        new_total = 0.0

    # --- 3. WRITE TO FILE ---
    try:
        with open(PATH_SENSORS, "w") as f:
            f.write(f"ROOF: {status}\n")
            f.write(f"HEATER: {heater_status}\n")
            f.write(f"SKY TEMP: {latest_sky_temp}\n") 
            f.write(f"AMB TEMP: {f'{amb_f:.1f} F' if amb_f else '--'}\n")
            f.write(f"HUMIDITY: {f'{hum_val:.1f} %' if hum_val else '--'}\n")
            f.write(f"PRESSURE: {pre_str}\n")
            f.write(f"WIND SPD: {speed:.1f} MPH\n")
            f.write(f"PRECIP: {'WET' if is_wet else 'DRY'}\n")
            f.write(f"TOTAL RUN: {new_total:.1f} HRS\n")
            if maint_alert:
                f.write(f"MAINT: {maint_alert}\n")
    except Exception as e:
        print(f"File Write Error: {e}")