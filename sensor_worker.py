import smbus2, bme280, time, os, threading, math, serial
import RPi.GPIO as GPIO

# --- CONFIG ---
ROOF_PIN = 17  
DEW_HEATER_PIN = 12  
USB_PORT = "/dev/ttyUSB0" 
PATH_SENSORS = "/home/pi/allsky_guard/sensors.txt"
PATH_HOURS = "/home/pi/allsky_guard/hours.txt"

# --- GPIO SETUP ---
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(ROOF_PIN, GPIO.OUT)
GPIO.setup(DEW_HEATER_PIN, GPIO.OUT)

# --- GLOBAL DATA HOLDERS ---
latest_wind_dir = "--"
latest_amb_temp = None
latest_humidity = None
latest_pressure = "--"
latest_wind_speed = 0.0
latest_rain_state = "DRY"

def connect_serial():
    try:
        if not os.path.exists(USB_PORT): return None
        s = serial.Serial(USB_PORT, 9600, timeout=2)
        time.sleep(2)
        s.reset_input_buffer()
        return s
    except: return None

def arduino_reader():
    global latest_wind_dir, latest_wind_speed, latest_amb_temp, latest_humidity, latest_pressure, latest_rain_state
    ser = connect_serial()
    while True:
        if ser and ser.is_open:
            try:
                if ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line.startswith("WEATHER:"):
                        clean_line = line.replace("WEATHER:", "")
                        parts = [item for item in clean_line.split(",") if ":" in item]
                        data = dict(item.split(":", 1) for item in parts)
                        
                        if 'PRES' in data: latest_pressure = f"{data.get('PRES', '--')} hPa"
                        if 'RAIN' in data: latest_rain_state = "WET" if data.get('RAIN') == "1" else "DRY"
                        
                        try:
                            if 'AMB' in data: latest_amb_temp = float(data.get('AMB'))
                            if 'HUM' in data: latest_humidity = float(data.get('HUM'))
                            if 'WIND' in data: latest_wind_speed = float(data.get('WIND'))
                        except: pass
            except: ser = None
        else:
            time.sleep(5)
            ser = connect_serial()
        time.sleep(0.1)

threading.Thread(target=arduino_reader, daemon=True).start()
last_check = time.time()

while True:
    time.sleep(2)
    
    amb_f = latest_amb_temp
    hum_val = latest_humidity
    speed = latest_wind_speed
    is_wet = (latest_rain_state == "WET")
    
    # --- Dew Heater Logic ---
    heater_status = "OFF"
    if amb_f and hum_val:
        try:
            T = (amb_f - 32) * 5/9
            gamma = (math.log(hum_val/100) + ((17.27 * T) / (237.3 + T)))
            dew_f = ((237.3 * gamma) / (17.27 - gamma) * 9/5) + 32
            if (amb_f - dew_f) <= 5.0:
                GPIO.output(DEW_HEATER_PIN, GPIO.HIGH)
                heater_status = "ON (DEW RISK)"
            else:
                GPIO.output(DEW_HEATER_PIN, GPIO.LOW)
        except: pass

    # --- Roof Safety Logic ---
    status = "CLOSED/LOCKED" if (is_wet or speed > 20.0) else "OPEN/SAFE"
    GPIO.output(ROOF_PIN, GPIO.HIGH if status == "CLOSED/LOCKED" else GPIO.LOW)

    # --- Maintenance Logging ---
    now = time.time()
    elapsed = (now - last_check) / 3600.0
    last_check = now
    total = 0.0
    try:
        if os.path.exists(PATH_HOURS):
            with open(PATH_HOURS, "r") as hf: total = float(hf.read().strip())
        new_total = total + elapsed
        with open(PATH_HOURS, "w") as hf: hf.write(f"{new_total:.4f}")
    except: new_total = 0.0

    # --- Output to sensors.txt ---
    try:
        with open(PATH_SENSORS, "w") as f:
            f.write(f"ROOF: {status}\nHEATER: {heater_status}\n")
            f.write(f"AMB TEMP: {f'{amb_f:.1f} F' if amb_f is not None else '--'}\n")
            f.write(f"HUMIDITY: {f'{hum_val:.1f} %' if hum_val is not None else '--'}\n")
            f.write(f"PRESSURE: {latest_pressure}\n")
            f.write(f"WIND SPD: {speed:.1f} MPH\n")
            f.write(f"PRECIP: {latest_rain_state}\n")
            f.write(f"TOTAL RUN: {new_total:.1f} HRS\n")
            if new_total >= 1000.0: f.write("MAINT: CLEANING REQUIRED\n")
    except: pass