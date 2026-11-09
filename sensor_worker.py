#!/usr/bin/env python3
import os
import time
import math
import tempfile
import serial

APP = "/home/pi/allsky_guard"
PORTS = ("/dev/ttyUSB0", "/dev/ttyACM0", "/dev/ttyUSB1", "/dev/ttyACM1")
BAUD = 9600
PATH_SENSORS = APP + "/sensors.txt"
PATH_HOURS = APP + "/hours.txt"
PATH_DEW_CMD = APP + "/dew_cmd.txt"

ser = None
last_seen = None
last_mode_sent = None
last_tick = time.monotonic()
last_hours_save = 0.0
last_status_save = 0.0
total_hours = 0.0

data = {"wind": None, "amb": None, "hum": None,
        "pres": None, "rain": None, "heater": None}


def atomic_write(path, content):
    fd, temp = tempfile.mkstemp(dir=APP, prefix=".asg-")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    except Exception:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def load_hours():
    try:
        with open(PATH_HOURS) as f:
            value = float(f.read().strip())
        if not math.isfinite(value) or value < 0:
            raise RuntimeError(
                "[Worker] SAFETY STOP: hours.txt contains an invalid value; "
                "maintenance hours were NOT reset."
            )
        return value
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            "[Worker] SAFETY STOP: hours.txt is missing or invalid; "
            "maintenance hours were NOT reset."
        ) from exc


def read_mode():
    try:
        with open(PATH_DEW_CMD) as f:
            mode = f.read().strip().upper()
    except OSError:
        mode = "AUTO"
    return mode if mode in ("AUTO", "ON", "OFF") else "AUTO"


def connect():
    global ser, last_mode_sent
    for port in PORTS:
        try:
            if not os.path.exists(port):
                continue
            candidate = serial.Serial(port, BAUD, timeout=0.25, write_timeout=1)
            time.sleep(2)
            candidate.reset_input_buffer()
            ser = candidate
            last_mode_sent = None
            print("[Worker] Nano connected: " + port, flush=True)
            return
        except (serial.SerialException, OSError) as exc:
            print("[Worker] Connection error: " + str(exc), flush=True)
    ser = None


def parse_telemetry(line):
    global last_seen
    if not line.startswith("WEATHER:"):
        return
    fields = {}
    for item in line[len("WEATHER:"):].split(","):
        if ":" in item:
            k, v = item.split(":", 1)
            fields[k.strip().upper()] = v.strip()
    last_seen = time.monotonic()

    try:
        v = float(fields["WIND"])
        data["wind"] = v if math.isfinite(v) and v >= 0 else None
    except (KeyError, ValueError):
        data["wind"] = None

    try:
        amb = float(fields["AMB"])
        hum = float(fields["HUM"])
        pres = float(fields["PRES"])
        valid = (math.isfinite(amb) and math.isfinite(hum) and
                 math.isfinite(pres) and 0 < hum <= 100 and pres > 0)
        data["amb"], data["hum"], data["pres"] = (
            (amb, hum, pres) if valid else (None, None, None))
    except (KeyError, ValueError):
        data["amb"] = data["hum"] = data["pres"] = None

    try:
        data["rain"] = int(fields["RAIN"]) == 1
    except (KeyError, ValueError):
        data["rain"] = None

    try:
        data["heater"] = int(fields["HEATER"]) == 1
    except (KeyError, ValueError):
        data["heater"] = None


def service_serial():
    global ser, last_mode_sent
    try:
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        if line:
            parse_telemetry(line)
        mode = read_mode()
        if mode != last_mode_sent:
            ser.write(("HEATER:" + mode + "\n").encode("ascii"))
            ser.flush()
            last_mode_sent = mode
            print("[Worker] Heater mode: " + mode, flush=True)
    except (serial.SerialException, OSError) as exc:
        print("[Worker] Serial error: " + str(exc), flush=True)
        try:
            ser.close()
        except Exception:
            pass
        ser = None
        last_mode_sent = None


def update_hours():
    global total_hours, last_tick, last_hours_save
    now = time.monotonic()
    total_hours += max(0.0, now - last_tick) / 3600.0
    last_tick = now
    if now - last_hours_save >= 2:
        try:
            atomic_write(PATH_HOURS, f"{total_hours:.4f}\n")
            last_hours_save = now
        except OSError as exc:
            print("[Worker] hours.txt write error: " + str(exc), flush=True)


def update_status():
    global last_status_save
    now = time.monotonic()
    if now - last_status_save < 1:
        return
    last_status_save = now

    fresh = last_seen is not None and now - last_seen <= 10
    v = data if fresh else {}
    wind, amb, hum, pres = (v.get(k) for k in ("wind", "amb", "hum", "pres"))
    rain, heater = v.get("rain"), v.get("heater")
    mode = read_mode()

    if heater is None:
        heater_text = "UNKNOWN"
    elif mode == "AUTO":
        heater_text = "ON (AUTO)" if heater else "OFF (AUTO)"
    else:
        heater_text = "ON (MANUAL)" if heater else "OFF (MANUAL)"

    lines = [
        "ROOF: NOT COMMISSIONED",
        "HEATER: " + heater_text,
        f"AMB TEMP: {amb:.1f} F" if amb is not None else "AMB TEMP: --",
        f"HUMIDITY: {hum:.1f} %" if hum is not None else "HUMIDITY: --",
        f"PRESSURE: {pres:.1f} hPa" if pres is not None else "PRESSURE: --",
        f"WIND SPD: {wind:.1f} MPH" if wind is not None else "WIND SPD: --",
        "PRECIP: UNKNOWN" if rain is None else
        ("PRECIP: WET" if rain else "PRECIP: DRY"),
        f"TOTAL RUN: {total_hours:.1f} HRS",
    ]
    if total_hours >= 1000:
        lines.append("MAINT: CLEANING REQUIRED")
    try:
        atomic_write(PATH_SENSORS, "\n".join(lines) + "\n")
    except OSError as exc:
        print("[Worker] sensors.txt write error: " + str(exc), flush=True)


def main():
    global total_hours
    total_hours = load_hours()
    if not os.path.exists(PATH_DEW_CMD):
        atomic_write(PATH_DEW_CMD, "AUTO\n")
    connect()
    while True:
        if ser is None:
            time.sleep(3)
            connect()
        else:
            service_serial()
        update_hours()
        update_status()
        time.sleep(0.1)


if __name__ == "__main__":
    main()
