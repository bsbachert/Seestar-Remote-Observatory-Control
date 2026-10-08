
<img width="1803" height="828" alt="image" src="https://github.com/user-attachments/assets/7094733c-ef4e-44da-9cb3-8c0a8a9a8ae0" />



An integrated automation and monitoring suite for a remote Seestar S50 / S30 / S30 Pro / S50 Pro observatory, powered by a Raspberry Pi 5 (8GB). This system manages everything from proactive dew prevention to structural roof automation, ensuring the telescope is protected and accessible from anywhere in the world.

🔭 Project Overview
This software provides a centralized "Heads Up Display" (HUD) and a background worker system. The Pi 5 is mounted directly inside the AllSky camera housing, which is secured to the observatory structure. The system is designed for high-availability, capable of running on Solar or Grid power, requiring only a WiFi internet connection for global remote access.

🚀 Key Features
Dual-MOSFET Control:
Heater: PWM-driven proactive dew prevention using a 5°F safety buffer.
Roof: Logic-level control for a Linear Actuator to open/close the observatory roof via the HUD.
Remote Power Management: Integration with a SwitchBot to remotely trigger the Seestar's physical power button.
Telescope Control: Use Seestar Apps Remote Telescope to control the telescope.
Global Access: Fully compatible with Raspberry Pi Connect and VNC for real-time control from anywhere.
Environmental Safety: * Wind Guard: Automatic roof closure if wind speeds exceed 15 MPH.
Rain Guard: Instant lockdown upon precipitation detection.

🛠 Hardware Configuration
Component
Connection / Pin
Purpose
Anemometer
GPIO 4
Wind Speed Monitoring
Dew Heater
GPIO 12 (MOSFET 1)
Proactive Condensation Prevention
Roof Actuator
GPIO 17 (MOSFET 2)
20" Actuator Drive (Open/Close)
Rain Sensor
GPIO 18
Precipitation Detection
SwitchBot
Bluetooth (BLE)
Seestar Power On/Off
BME280 / All sky Image Cloud detection
I2C Bus
Ambient Temperature with dew calculation

🌡 Dew Prevention Logic
The system proactively calculates the dew point. If the ambient temperature falls within 5°F of the dew point, the Pi 5 engages the MOSFET on GPIO 12:

This ensures the optics remain clear before moisture can settle.

📦 Software Structure
hud.py: The primary GUI providing the visual dashboard and manual roof/power controls.
sensor_worker.py: The background engine handling sensor data, wind pulse counting, and automated safety logic.
seestar_push.py: The Bluetooth script for SwitchBot/Fingerbot interaction.

Button Control:
Dew heater on, off, auto
Weather History - saves temp, wind, pressure,humidity, and focus drift. (Notifies when you need to refocus your Seestar) 
Dossier for note taking, setting IP's, weather station, clear sky clock, cloud detection radius, reset radar, and service hrs.
Power on Seestar with finger boot using Pi bluetooth
Seestar 1 and 2, select which to control
Seestar Pop to see the current image stacking. 

🔧 Installation & Remote Access
Clone & Setup:
Bash
git clone https://github.com/bsbachert/Seestar-Remote-Observatory-Control.git

cd allsky_guard
./install.sh

Connectivity: Ensure Raspberry Pi Connect or VNC Server is enabled via raspi-config.(sudo raspi-config)

Power: Designed for 12V DC input 5A, compatible with solar charge controllers or standard grid-tie adapters.

This is a work in Progress. Adding more as I 3D print the Seestar Observatory.
