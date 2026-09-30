#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Dynamically identify the real non-root user running the script
REAL_USER="${SUDO_USER:-$USER}"
USER_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
APP_DIR="$USER_HOME/allsky_guard"
VENV_DIR="$APP_DIR/venv"

echo "===================================================="
echo "🚀 Starting All-Sky Guard HUD System Installer"
echo "Target User: $REAL_USER"
echo "Home Directory: $USER_HOME"
echo "App Directory: $APP_DIR"
echo "===================================================="

# 1. Detect Operating System Family
OS_FAMILY="unknown"

if [ -f /etc/os-release ]; then
    . /etc/os-release
    case "$ID" in
        arch|manjaro|endeavouros)
            OS_FAMILY="arch"
            ;;
        debian|ubuntu|raspbian)
            OS_FAMILY="debian"
            ;;
        *)
            if [[ "$ID_LIKE" == *"arch"* ]]; then
                OS_FAMILY="arch"
            elif [[ "$ID_LIKE" == *"debian"* || "$ID_LIKE" == *"ubuntu"* ]]; then
                OS_FAMILY="debian"
            fi
            ;;
    esac
fi

echo "🔍 Detected OS Family: ${OS_FAMILY^^} (${NAME:-Unknown OS})"

# 2. Install Native Dependencies based on OS
case "$OS_FAMILY" in
    arch)
        echo "📦 Updating Arch Linux package databases and installing dependencies..."
        sudo pacman -Sy --needed --noconfirm \
            python python-pip python-pillow python-tk \
            i2c-tools bluez bluez-utils desktop-file-utils
        ;;
    debian)
        echo "📦 Updating Debian/Ubuntu package lists and installing dependencies..."
        sudo apt-get update -y
        sudo apt-get install -y \
            python3-pip python3-venv python3-dev \
            python3-tk python3-pil python3-pil.imagetk \
            i2c-tools bluetooth bluez desktop-file-utils
        ;;
    *)
        echo "❌ Unsupported OS family detected. Please install dependencies manually."
        exit 1
        ;;
esac

# 3. Configure Bluetooth to Auto-Enable
echo "🔵 Configuring Bluetooth to auto-enable on boot..."
if [ -f /etc/bluetooth/main.conf ]; then
    sudo sed -i -E 's/^[# ]*AutoEnable\s*=\s*.*/AutoEnable=true/' /etc/bluetooth/main.conf
fi

# 4. Set up Python Virtual Environment (venv)
echo "🐍 Setting up Python venv at $VENV_DIR..."
mkdir -p "$APP_DIR"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

echo "📦 Installing required Python packages into venv..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install smbus2 bme280 requests matplotlib numpy opencv-python bleak pyserial RPi.GPIO

# Ensure the non-root user owns the app directory and venv
chown -R "$REAL_USER":"$REAL_USER" "$APP_DIR"

# 5. Set User Group Permissions Safely
echo "🔐 Configuring hardware access user permissions..."
for grp in dialout i2c gpio uucp bluetooth; do
    if getent group "$grp" >/dev/null 2>&1; then
        sudo usermod -a -G "$grp" "$REAL_USER"
        echo "   - Added $REAL_USER to group: $grp"
    fi
done

# 6. Create background Systemd Service for sensor_worker
echo "⚙️ Creating sensor_worker systemd background service..."
sudo bash -c "cat > /etc/systemd/system/sensor_worker.service <<EOF
[Unit]
Description=All-Sky Guard Sensor Worker Service
After=network.target bluetooth.service

[Service]
ExecStart=$VENV_DIR/bin/python $APP_DIR/sensor_worker.py
WorkingDirectory=$APP_DIR
StandardOutput=inherit
StandardError=inherit
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF"

# 7. Create Desktop Shortcut for HUD GUI
echo "🖥️ Creating Desktop shortcut for HUD GUI..."
DESKTOP_DIR="$USER_HOME/Desktop"
mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_DIR/allsky_hud.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=All-Sky Guard HUD
Comment=Launch All-Sky Guard Display Interface
Exec=$VENV_DIR/bin/python $APP_DIR/hud.py
Icon=utilities-system-monitor
Path=$APP_DIR
Terminal=false
StartupNotify=true
Categories=Utility;
EOF

# Set ownership and permissions for the desktop entry
chown "$REAL_USER":"$REAL_USER" "$DESKTOP_DIR/allsky_hud.desktop"
chmod +x "$DESKTOP_DIR/allsky_hud.desktop"

# Authorize launcher on desktop environments that require it
if command -v gio >/dev/null 2>&1; then
    sudo -u "$REAL_USER" gio trust "$DESKTOP_DIR/allsky_hud.desktop" || true
fi

# 8. Reload systemd daemon and enable services
echo "🔄 Initializing background system service..."
sudo systemctl daemon-reload
sudo systemctl enable sensor_worker.service
sudo systemctl restart bluetooth

echo "===================================================="
echo "✅ Installation Completed Successfully!"
echo "📌 Target Environment: $OS_FAMILY"
echo "📌 Desktop Shortcut: $DESKTOP_DIR/allsky_hud.desktop"
echo "⚠️ Please REBOOT your system to apply group permission changes."
echo "===================================================="