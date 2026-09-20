#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "===================================================="
echo "🚀 Starting All-Sky Guard HUD System Installer"
echo "===================================================="

# 1. Update system packages
echo "📦 Updating system package lists..."
sudo apt-get update -y

# 2. Install native system dependencies
echo "🛠️ Installing native prerequisites..."
sudo apt-get install -y python3-pip python3-venv python3-dev \
                         python3-tk python3-pil python3-pil.imagetk \
                         python3-matplotlib python3-numpy python3-opencv \
                         bluetooth bluez i2c-tools

# 3. Enable Auto-Enable for Bluetooth on boot
echo "🔵 Configuring Bluetooth to auto-enable..."
sudo sed -i 's/#AutoEnable=false/AutoEnable=true/' /etc/bluetooth/main.conf

# 4. Handle Python package manager dependencies globally
# Added 'bleak' to the list of pip packages
echo "🐍 Installing system-wide Python dependencies (including Bleak)..."
sudo pip install smbus2 bme280 requests matplotlib numpy opencv-python bleak --break-system-packages

# 5. Set User Group Permissions
echo "🔐 Setting up user permissions for Serial, I2C, GPIO, and Bluetooth..."
sudo usermod -a -G dialout pi
sudo usermod -a -G i2c pi
sudo usermod -a -G gpio pi
sudo usermod -a -G bluetooth pi

# 6. Build the background System Service configuration for sensor_worker
echo "⚙️ Creating sensor_worker background system service..."
sudo bash -c 'cat > /etc/systemd/system/sensor_worker.service <<EOF
[Unit]
Description=All-Sky Guard Sensor Worker Service
After=network.target bluetooth.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/allsky_guard/sensor_worker.py
WorkingDirectory=/home/pi/allsky_guard
StandardOutput=inherit
StandardError=inherit
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF'

# 7. Reload and enable background daemon
echo "🔄 Initializing background service..."
sudo systemctl daemon-reload
sudo systemctl enable sensor_worker.service
sudo systemctl restart bluetooth

echo "===================================================="
echo "✅ Installation Completed Successfully!"
echo "⚠️ Please REBOOT, then verify pairing with your device."
echo "===================================================="