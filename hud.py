import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from PIL import Image, ImageTk, ImageDraw
import os, subprocess, random, math, sys, fcntl, socket, time
import smtplib
import requests
import webbrowser
from email.message import EmailMessage
from datetime import datetime, timedelta
import cv2
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import shutil

try:
    lock_file = open('/tmp/sumner_hud.lock', 'w')
    fcntl.lockf(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
except:
    sys.exit(0)

class SumnerHUD:
    def __init__(self, root):
        self.root = root
        self.root.attributes('-fullscreen', True)
        self.root.attributes("-topmost", True)
        self.root.config(bg='black')

        self.sw = self.root.winfo_screenwidth()
        self.sh = self.root.winfo_screenheight()

        # Existing Configuration
        self.email_sender = "bsbachert@gmail.com"
        self.email_pass = "pucapkfuesrrnasm" 
        self.path_email = "/home/pi/allsky_guard/email_receiver.txt"
        self.path_dew_cmd = "/home/pi/allsky_guard/dew_cmd.txt"
        self.email_receiver = "bsbachert@gmail.com"
        
        if os.path.exists(self.path_email):
            try:
                with open(self.path_email, "r") as f:
                    content = f.read().strip()
                    if content: self.email_receiver = content
            except: pass

        # File Paths
        self.path_allsky = "/var/www/html/allsky/images/latest.jpg"
        self.path_prev_sky = "/tmp/prev_allsky.jpg"
        self.path_radar = "/home/pi/allsky_guard/radar.png"
        self.path_clock = "/home/pi/allsky_guard/clock.png" 
        self.path_sensors = "/home/pi/allsky_guard/sensors.txt"
        self.path_sensors_log = "/home/pi/allsky_guard/sensors_24h.log" 
        self.path_hours = "/home/pi/allsky_guard/hours.txt"
        self.path_notes = "/home/pi/allsky_guard/dossier.txt"
        self.path_thresh = "/home/pi/allsky_guard/cloud_threshold.txt"
        self.path_seestar_ip = "/home/pi/allsky_guard/seestar_ip.txt"
        self.path_fingerbot_mac = "/home/pi/allsky_guard/fingerbot_mac.txt"
        self.path_roof_cmd = "/home/pi/allsky_guard/roof_cmd.txt"
        self.path_radar_id = "/home/pi/allsky_guard/radar_coords.txt"
        self.path_csk_id = "/home/pi/allsky_guard/csk_id.txt"
        self.path_sync_script = "/home/pi/allsky_guard/get_radar.py"

        self.img_all = None
        self.img_rad = None
        self.img_clk = None
        self.seestar_ip = "0.0.0.0"
        self.last_allsky_ts = 0
        self.last_log_time = 0 
        self.last_roof_safety_state = None
        self.emergency_sent = False
        self.dusk_sent_today = None
        self.ai_sky_status = "INITIALIZING"
        self.is_wet = False
        self.is_obscured = False
        self.maintenance_alerted = False

        self.cloud_motion_threshold = 8.0
        if os.path.exists(self.path_thresh):
            try:
                with open(self.path_thresh, "r") as f:
                    self.cloud_motion_threshold = float(f.read().strip())
            except: pass

        if os.path.exists(self.path_seestar_ip):
            try:
                with open(self.path_seestar_ip, "r") as f:
                    self.seestar_ip = f.read().strip()
            except: pass

        # UI Layout setup
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=10)
        self.root.grid_rowconfigure(2, weight=3)
        self.root.grid_columnconfigure(0, weight=3)
        self.root.grid_columnconfigure(1, weight=1)

        self.create_ui_elements()
        self.check_cleaning_reminder()
        self.send_email_notification("System Power Recovery", "The Observatory HUD has restarted successfully.")
        
        self.root.bind("<Configure>", self.on_window_resize)
        self.root.bind("<Map>", self.on_restore)
        
        self.fetch_online_wind_dir()
        self.fetch_radar_auto()
        self.update_loop()

    # --- Location Helper ---
    def get_radar_coords(self):
        try:
            with open(self.path_radar_id, 'r') as file:
                station_id = file.read().strip().upper()
        except:
            station_id = "GRR"
        
        radar_map = {
            "GRR": {"lat": "42.88", "lon": "-85.52"},
            "DTX": {"lat": "42.70", "lon": "-83.47"},
            "APX": {"lat": "44.91", "lon": "-84.72"},
        }
        return radar_map.get(station_id, radar_map["GRR"])

    # --- Existing Helper Methods ---
    def minimize_hud(self):
        self.root.attributes("-topmost", False)
        self.root.iconify()

    def on_restore(self, event):
        if event.widget == self.root and self.root.state() == 'normal':
            self.root.attributes("-topmost", True)

    def toggle_dew(self):
        current_text = self.btn_dew.cget("text")
        if "AUTO" in current_text:
            self.btn_dew.config(text="DEW HTR: ON", bg="#900")
            with open(self.path_dew_cmd, "w") as f: f.write("ON")
        else:
            self.btn_dew.config(text="DEW HTR: AUTO", bg="#333")
            with open(self.path_dew_cmd, "w") as f: f.write("OFF")

    def send_email_notification(self, subject, body):
        try:
            msg = EmailMessage()
            msg.set_content(body)
            msg['Subject'] = subject
            msg['From'] = self.email_sender
            msg['To'] = self.email_receiver
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(self.email_sender, self.email_pass)
            server.send_message(msg)
            server.quit()
        except Exception as e: print(f"Email Error: {e}")

    def log_sensor_data(self, amb, hum, wind, pres, sky_diff):
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"{now_str} | Amb:{amb:.1f} | Hum:{hum:.0f} | Wind:{wind:.1f} | Pres:{pres:.2f} | SkyDiff:{sky_diff:.1f}\n"
        try:
            with open(self.path_sensors_log, "a") as f: f.write(log_entry)
        except Exception as e: print(f"Logging Error: {e}")

    def shutdown(self):
        try:
            fcntl.lockf(lock_file, fcntl.LOCK_UN)
            lock_file.close()
            if os.path.exists('/tmp/sumner_hud.lock'): os.remove('/tmp/sumner_hud.lock')
        except Exception as e: print(f"Shutdown Error: {e}")
        self.root.destroy()
        sys.exit(0)

    def on_window_resize(self, event):
        if event.widget == self.root:
            self.sw = event.width
            self.sh = event.height

    def run_ai_clear_check(self, manual_click=False):
        if not os.path.exists(self.path_allsky): return
        
        current_img = cv2.imread(self.path_allsky)
        gray_curr = cv2.cvtColor(current_img, cv2.COLOR_BGR2GRAY)
        
        # --- NEW: MLX90614 FOV Simulation Mask with Offsets ---
        h, w = gray_curr.shape
        
        # OFFSETS: Adjust these to shift the mask away from trees/walls
        # Positive X moves right, Negative X moves left
        # Positive Y moves down, Negative Y moves up
        offset_x = 120  # Shifted right to avoid left-side trees
        offset_y = 0    # Keep vertically centered for now
        
        center = ((w // 2) + offset_x, (h // 2) + offset_y)
        
        # Shrunk radius slightly to 35% so it fits better when shifted off-center
        radius = int(min(h, w) * 0.35) 
        
        # Create a solid black mask and draw a white circle in the middle
        mask = np.zeros_like(gray_curr)
        cv2.circle(mask, center, radius, 255, -1)
        
        # Apply the mask (blacks out everything outside the circle)
        masked_gray = cv2.bitwise_and(gray_curr, mask)
        # -----------------------------------------
        
        # 1. DOME OBSTRUCTION CHECK (Safety First)
        laplacian = cv2.Laplacian(gray_curr, cv2.CV_64F)
        variance = laplacian[mask == 255].var() if np.any(mask) else 0
        is_obscured = (variance < 25.0)
        
        # 2. TIME-BASED FOLDER SELECTION
        hour = datetime.now().hour
        if 6 <= hour < 17: folder = "day"
        elif 17 <= hour < 20: folder = "evening"
        else: folder = "night"
        ref_folder = f"/home/pi/allsky_guard/ref/{folder}/"
        
        # 3. TEMPLATE MATCHING
        best_match = "UNCERTAIN"
        highest_score = -1.0
        masked_gray_blurred = cv2.GaussianBlur(masked_gray, (5, 5), 0)
        
        if os.path.exists(ref_folder):
            for ref_file in os.listdir(ref_folder):
                if not ref_file.endswith(".jpg"): continue
                ref_img = cv2.imread(os.path.join(ref_folder, ref_file), cv2.IMREAD_GRAYSCALE)
                
                if ref_img is not None:
                    ref_img = cv2.resize(ref_img, (masked_gray_blurred.shape[1], masked_gray_blurred.shape[0]))
                    ref_img_masked = cv2.bitwise_and(ref_img, mask)
                    
                    score = cv2.matchTemplate(masked_gray_blurred, ref_img_masked, cv2.TM_CCOEFF_NORMED)[0][0]
                    if score > highest_score:
                        highest_score = score
                        best_match = ref_file.replace(".jpg", "").replace("_", " ")

        # 4. CONSOLIDATED STATUS
        if is_obscured:
            self.ai_sky_status = "OBSCURED"
            status, color = "AI: DOME OBSCURED", "#922B21"
        else:
            self.ai_sky_status = best_match.upper()
            color = "#1E8449" if "CLEAR" in self.ai_sky_status else "#D4AC0D"
            status = f"AI: {self.ai_sky_status}"

        self.btn_ai.config(text=f"{status}\n({folder.upper()} | Var: {variance:.1f})", bg=color)
        
        if self.btn_dew and "AUTO" in self.btn_dew.cget("text"):
            with open(self.path_dew_cmd, "w") as f:
                f.write("ON" if is_obscured else "OFF")

        # 5. MANUAL CLICK DEBUG IMAGE
        if manual_click:
            debug_img = current_img.copy()
            
            # Visual feedback: Draw the FOV boundary
            cv2.circle(debug_img, center, radius, (0, 255, 255), 2)
            
            # Darken everything outside the mask for the user preview
            mask_3c = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
            darkened = cv2.addWeighted(debug_img, 0.3, np.zeros_like(debug_img), 0.7, 0)
            debug_img = np.where(mask_3c == 255, debug_img, darkened)

            txt_color = (0, 255, 0) if color == "#1E8449" else (0, 165, 255)
            if is_obscured: txt_color = (0, 0, 255)

            cv2.putText(debug_img, f"STATUS: {self.ai_sky_status}", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.5, txt_color, 3)
            cv2.putText(debug_img, f"MATCH: {best_match} ({highest_score:.2f})", (30, 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            cv2.putText(debug_img, f"VARIANCE: {variance:.1f}", (30, 170), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            cv2.putText(debug_img, f"MASK OFFSETS: X:{offset_x} Y:{offset_y}", (30, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            
            debug_path = "/tmp/motion_debug.jpg"
            cv2.imwrite(debug_path, debug_img)
            self.popout(debug_path)

    def manual_open(self):
        with open(self.path_roof_cmd, "w") as f: f.write("OPEN")
        messagebox.showinfo("ROOF", "Manual OPEN command sent.")

    def manual_close(self):
        with open(self.path_roof_cmd, "w") as f: f.write("CLOSE")
        messagebox.showinfo("ROOF", "Manual CLOSE command sent.")

    def trigger_fingerbot(self):
        try:
            subprocess.Popen(["python3", "/home/pi/allsky_guard/seestar_push.py"])
            self.power_btn.config(bg="red", text="⚡ SENDING...")
            self.root.after(2000, lambda: self.power_btn.config(bg="#900", text="⚡ SEESTAR"))
        except: messagebox.showerror("ERROR", "Could not run seestar_push.py")

    def open_seestar_alp(self):
        # Drop topmost so the browser isn't trapped behind the fullscreen HUD
        self.root.attributes("-topmost", False)
        target_url = "http://localhost:5432/"
        try:
            # Try to launch chromium in a clean app window
            subprocess.Popen(["chromium-browser", f"--app={target_url}"])
        except Exception:
            # Fallback to default browser
            webbrowser.open(target_url)

    def run_health_check(self):
        report = []
        if os.path.exists(self.path_sensors):
            mtime = os.path.getmtime(self.path_sensors)
            report.append("✅ SENSORS: Active" if (datetime.now().timestamp() - mtime) < 30 else "❌ SENSORS: Stale")
        try:
            bt_check = subprocess.check_output(["bluetoothctl", "devices"], text=True)
            report.append("✅ BLUETOOTH: Bot paired" if "E1:6A:83:06:38:48" in bt_check else "⚠️ BLUETOOTH: Bot missing")
        except: report.append("❌ BLUETOOTH: Error")
        messagebox.showinfo("SYSTEM HEALTH REPORT", "\n".join(report))

    def get_connection_type(self):
        try:
            ips = subprocess.check_output("hostname -I", shell=True).decode().split()
            for ip in ips:
                if ip.startswith("100."): return "REMOTE (VPN)", "orange"
            return "LOCAL (WiFi)", "lightgreen"
        except: return "UNKNOWN", "gray"

    def create_placeholder(self, text, w, h):
        if w <= 0 or h <= 0: w, h = 100, 100
        img = Image.new('RGB', (w, h), color=(15, 15, 15))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, w-1, h-1], outline="red", width=3)
        draw.text((w//2, h//2), text, fill="white", anchor="mm", align="center")
        return ImageTk.PhotoImage(img)

    def load_scale(self, path, w, h, label):
        if w <= 0 or h <= 0: w, h = 100, 100
        if not os.path.exists(path) or os.path.getsize(path) < 100:
            return self.create_placeholder(f"SET {label} ID\nIN DOSSIER", w, h)
        try:
            with Image.open(path) as raw:
                img = raw.convert("RGB")
                img.thumbnail((w, h), Image.Resampling.LANCZOS)
                return ImageTk.PhotoImage(img)
        except: return self.create_placeholder(f"ERROR LOADING\n{label}", w, h)

    def check_cleaning_reminder(self):
        if os.path.exists(self.path_hours):
            try:
                with open(self.path_hours, "r") as f:
                    hrs = float(f.read().strip())
                    if hrs >= 1000.0: messagebox.showwarning("MAINTENANCE", f"Alert: {hrs:.1f} Hours. Clean dome.")
            except: pass

    def check_alpaca_status(self):
        if not self.seestar_ip or self.seestar_ip == "0.0.0.0": return False
        try:
            with socket.create_connection((self.seestar_ip, 32323), timeout=0.5): return True
        except: return False

    def show_weather_history(self):
        if not os.path.exists(self.path_sensors_log):
            messagebox.showerror("ERROR", "No sensor log file found.")
            return
        pop = tk.Toplevel(self.root)
        pop.attributes("-fullscreen", True, "-topmost", True)
        pop.config(bg='black')
        times, temps, hums, winds, press, sky_diff = [], [], [], [], [], []
        cutoff = datetime.now() - timedelta(hours=24)
        try:
            with open(self.path_sensors_log, "r") as f:
                for line in f:
                    parts = line.split('|')
                    if len(parts) < 5: continue
                    log_t = datetime.strptime(parts[0].strip(), '%Y-%m-%d %H:%M:%S')
                    if log_t >= cutoff:
                        times.append(log_t)
                        temps.append(float(parts[1].split(':')[1]))
                        hums.append(float(parts[2].split(':')[1]))
                        winds.append(float(parts[3].split(':')[1]))
                        press.append(float(parts[4].split(':')[1]))
                        if len(parts) > 5: sky_diff.append(float(parts[5].split(':')[1]))
        except Exception as e: print(f"Log Parse Error: {e}")
        fig, axs = plt.subplots(5, 1, figsize=(10, 12), dpi=100, sharex=True)
        fig.set_facecolor('black')
        sets = [(temps, "TEMP (F)", "#EC7063"), (hums, "HUM (%)", "#5499C7"), (winds, "WIND (MPH)", "#F4D03F"), (press, "BARO (IN)", "#58D68D"), (sky_diff, "MOTION Δ", "#AAB7B8")]
        for i, (data, label, color) in enumerate(sets):
            if data: axs[i].plot(times, data, color=color, linewidth=1.5)
            axs[i].set_ylabel(label, color='white', fontsize=8)
            axs[i].set_facecolor('#0a0a0a')
            axs[i].tick_params(colors='white', labelsize=7)
            axs[i].xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
            axs[i].xaxis.set_major_locator(mdates.HourLocator(interval=2))
            axs[i].grid(color='#333', linestyle='--')
            for s in axs[i].spines.values(): s.set_color('#444')
        plt.xticks(rotation=45)
        tk.Button(pop, text="CLOSE", command=pop.destroy, bg="#500", fg="white", font=("Arial", 10, "bold")).pack(side="bottom", pady=10)
        canvas = FigureCanvasTkAgg(fig, master=pop)
        canvas.draw(); canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def fetch_online_wind_dir(self):
        coords = self.get_radar_coords()
        try:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={coords['lat']}&longitude={coords['lon']}&current_weather=true"
            data = requests.get(url, timeout=5).json()
            degrees = data['current_weather']['winddirection']
            dirs = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
            cardinal = dirs[round(degrees / (360. / len(dirs))) % len(dirs)]
            self.right_panel.nametowidget(self.val_dir).config(text=f"{cardinal} ({degrees}°)")
        except Exception as e:
            print(f"Weather API Error: {e}")
            self.right_panel.nametowidget(self.val_dir).config(text="API ERROR")
        self.root.after(900000, self.fetch_online_wind_dir)

    # --- NEW: Wind Direction Utility ---
    def get_wind_direction(self, degrees):
        """Converts numerical degrees into 8-sector cardinal directions."""
        deg = float(degrees) % 360
        sectors = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        # Shift by 22.5 to ensure N is centered at 0/360
        index = int(((deg + 22.5) % 360) / 45)
        return sectors[index]

    def update_hud(self, wind_data):
        # ... logic to get degree from your sensor ...
        direction_label = self.get_wind_direction(wind_data['degrees'])
        
        # Update the UI display
        self.lbl_wind.config(text=f"WIND: {direction_label}")

    def fetch_radar_auto(self):
        """Silently runs get_radar.py in the background every 10 minutes."""
        try:
            subprocess.Popen(["python3", self.path_sync_script])
        except Exception as e:
            print(f"Radar sync error: {e}")
            
        # 600000 ms = 10 minutes. Adjust if you want it faster or slower.
        self.root.after(600000, self.fetch_radar_auto)

    def open_dossier(self):
        d_win = tk.Toplevel(self.root)
        d_win.geometry(f"{int(self.sw * 0.45)}x{int(self.sh * 0.85)}")
        d_win.config(bg="#050505"); d_win.attributes("-topmost", True)
        d_win.grid_rowconfigure(2, weight=1); d_win.grid_columnconfigure(0, weight=1)
        tk.Label(d_win, text="SYSTEM DOSSIER", bg="#050505", fg="#FFCC00", font=("Arial", 18, "bold")).grid(row=0, column=0, pady=10)
        entry_frame = tk.Frame(d_win, bg="#050505")
        entry_frame.grid(row=1, column=0, sticky="ew", padx=20)
        def create_entry(label_text, path, color="cyan"):
            f = tk.Frame(entry_frame, bg="#111")
            f.pack(fill="x", pady=2)
            tk.Label(f, text=label_text, bg="#111", fg="white", width=15, anchor="w").pack(side="left")
            e = tk.Entry(f, bg="black", fg=color, insertbackground="white")
            e.pack(side="left", padx=10, fill="x", expand=True)
            if os.path.exists(path):
                with open(path, "r") as file: e.insert(0, file.read().strip())
            return e
        rad_entry = create_entry("Radar Station:", self.path_radar_id, "orange")
        csk_entry = create_entry("ClearSky ID:", self.path_csk_id, "#00FFCC")
        ip_entry  = create_entry("Seestar IP:", self.path_seestar_ip, "#FF33FF")
        bt_entry  = create_entry("Fingerbot MAC:", self.path_fingerbot_mac, "#FFCC00")
        mail_entry = create_entry("Alert Email:", self.path_email, "lightgreen")
        txt = scrolledtext.ScrolledText(d_win, bg="black", fg="#00FFCC", font=("Courier", 14), insertbackground="white")
        txt.grid(row=2, column=0, sticky="nsew", padx=20, pady=5)
        if os.path.exists(self.path_notes):
            with open(self.path_notes, "r") as f: txt.insert('1.0', f.read())
        def save_all():
            with open(self.path_radar_id, "w") as f: f.write(rad_entry.get().upper().strip())
            with open(self.path_csk_id, "w") as f: f.write(csk_entry.get().strip())
            with open(self.path_seestar_ip, "w") as f: f.write(ip_entry.get().strip())
            with open(self.path_fingerbot_mac, "w") as f: f.write(bt_entry.get().strip())
            with open(self.path_email, "w") as f: f.write(mail_entry.get().strip())
            with open(self.path_notes, 'w') as f: f.write(txt.get('1.0', 'end'))
            with open(self.path_thresh, 'w') as f: f.write(str(motion_slider.get()))
            self.seestar_ip = ip_entry.get().strip()
            self.email_receiver = mail_entry.get().strip()
            self.cloud_motion_threshold = motion_slider.get()
            d_win.destroy()
        def reset_hrs():
            if messagebox.askyesno("RESET", "Reset Timer to 0?"):
                with open(self.path_hours, "w") as f: f.write("0.0")
            
        btn_f = tk.Frame(d_win, bg="#050505")
        btn_f.grid(row=3, column=0, sticky="ew", pady=(10, 20))
        tk.Button(btn_f, text="♻ RESET", bg="#D4AC0D", command=reset_hrs).pack(side="left", padx=10)
        tk.Button(btn_f, text="🔄 SYNC RADAR", bg="#4B0082", fg="white", command=lambda: subprocess.Popen(["python3", self.path_sync_script])).pack(side="left", padx=5)
        tk.Button(btn_f, text="🤖 TEST BOT", bg="orange", command=self.trigger_fingerbot).pack(side="left", padx=5)
        
        tk.Label(btn_f, text="MOTION %:", bg="#050505", fg="white", font=("Arial", 8)).pack(side="left", padx=(10, 2))
        motion_slider = tk.Scale(btn_f, from_=1.0, to=30.0, resolution=0.5, orient='horizontal', bg='#050505', fg='white', troughcolor='#333', length=100, highlightthickness=0, font=("Arial", 7))
        motion_slider.set(self.cloud_motion_threshold)
        motion_slider.pack(side="left", padx=5)
        tk.Button(btn_f, text="💾 SAVE", bg="#1E8449", fg="white", command=save_all).pack(side="right", padx=20)

    # --- Integrated Loop ---
    def update_loop(self):
        now = datetime.now()
        # Dusk Snapshot Trigger
        if now.hour == 18 and now.minute == 0 and self.dusk_sent_today != now.date():
            sensor_report = f"AI Matrix: {self.ai_sky_status}"
            self.send_email_notification("Dusk Sensor Snapshot", 
                f"Observatory status at 18:00:\n\n{sensor_report}")
            self.dusk_sent_today = now.date()
            
        self.left_workspace.update()
        w_half = int(self.left_workspace.winfo_width() / 2) - 10
        h_main = int(self.left_workspace.winfo_height() * 0.5) - 10
        w_full = int(self.left_workspace.winfo_width()) - 15
        h_lower = int(self.left_workspace.winfo_height() * 0.35) - 10
        
        self.img_all = self.load_scale(self.path_allsky, w_half, h_main, "AllSky")
        self.all_canvas.itemconfig(self.all_img_id, image=self.img_all)
        self.img_rad = self.load_scale(self.path_radar, w_half, h_main, "Radar")
        self.rad_canvas.itemconfig(self.rad_img_id, image=self.img_rad)
        self.img_clk = self.load_scale(self.path_clock, w_full, h_lower, "ClearSky")
        self.clk_canvas.itemconfig(self.clk_img_id, image=self.img_clk)
        
        if os.path.exists(self.path_allsky):
            ts = os.path.getmtime(self.path_allsky)
            if ts != self.last_allsky_ts:
                self.last_allsky_ts = ts
                self.run_ai_clear_check()
                
        net_stat, net_col = self.get_connection_type()
        self.net_lbl.config(text=f"NET: {net_stat}", fg=net_col)
        alpaca_on = self.check_alpaca_status()
        self.right_panel.nametowidget(self.val_alpaca).config(text="ONLINE" if alpaca_on else "OFFLINE", fg="#00FF00" if alpaca_on else "#FF3333")
        
        if os.path.exists(self.path_hours):
            try:
                with open(self.path_hours, "r") as f:
                    num_hrs = float(f.read().strip())
                    if num_hrs >= 1000.0 and not self.maintenance_alerted:
                        messagebox.showwarning("MAINTENANCE", f"Alert: {num_hrs:.1f} Hours reached. Please clean the dome.")
                        self.maintenance_alerted = True
                    hrs_col = "red" if num_hrs >= 1000.0 else "#FFCC00"
                    self.val_hrs.config(text=f"{num_hrs:.1f} HRS", fg=hrs_col)
            except: pass
            
        if os.path.exists(self.path_sensors):
            try:
                amb_t, hum_val, wind_val, raw_p = None, None, None, None
                sensor_report = ""
                with open(self.path_sensors, "r") as f:
                    for line in f:
                        u_line = line.upper().strip(); val = line.split(":", 1)[1].strip() if ":" in u_line else ""
                        sensor_report += f"{line.strip()}\n"
                        if "AMB TEMP" in u_line:
                            self.right_panel.nametowidget(self.val_amb).config(text=val)
                            try: amb_t = float(''.join(c for c in val if c in '0123456789.-'))
                            except: pass
                        elif "HUMIDITY" in u_line:
                            try:
                                clean_val = val.split('%')[0].strip()
                                hum_val = float(''.join(c for c in clean_val if c in '0123456789.-'))
                                self.right_panel.nametowidget(self.val_hum).config(text=f"{hum_val}%")
                            except: pass
                        elif "WIND SPD" in u_line:
                            try:
                                wind_val = float(''.join(c for c in val if c in '0123456789.-'))
                                self.right_panel.nametowidget(self.val_wind).config(text=f"{wind_val} mph")
                            except: pass
                        elif "HEATER" in u_line:
                            self.right_panel.nametowidget(self.val_heat).config(text=val)
                        elif "RAIN" in u_line or "PRECIP" in u_line:
                            self.is_wet = "WET" in val.upper()
                            self.right_panel.nametowidget(self.val_rain).config(text="WET" if self.is_wet else "DRY", fg="red" if self.is_wet else "cyan")
                        elif "PRESSURE" in u_line:
                            try:
                                raw_p = float(''.join(c for c in val if c in '0123456789.-'))
                                self.right_panel.nametowidget(self.val_pres).config(text=f"{raw_p * 0.02953:.2f} in")
                            except: pass
                
                current_time_ts = datetime.now().timestamp()
                if (current_time_ts - self.last_log_time) >= 900: 
                    if all(v is not None for v in [amb_t, hum_val, wind_val, raw_p]):
                        self.log_sensor_data(amb_t, hum_val, wind_val, raw_p * 0.02953, 0.0)
                        self.last_log_time = current_time_ts
                
                dew_f = 0
                if amb_t and hum_val:
                    T = (amb_t - 32) * 5/9
                    gamma = (math.log(hum_val/100) + ((17.27 * T) / (237.3 + T)))
                    dew_f = ((237.3 * gamma) / (17.27 - gamma) * 9/5) + 32
                    self.right_panel.nametowidget(self.val_dew).config(text=f"{dew_f:.1f} F")
                
                extreme_dew = (amb_t - dew_f) < 3 if (amb_t and dew_f) else False
                ai_safe = (self.ai_sky_status in ["CLEAR", "INITIALIZING"])
                
                if not self.is_wet and not self.is_obscured and (not wind_val or wind_val < 15) and not extreme_dew and ai_safe:
                    roof_text, roof_color = "SAFE TO OPEN", "lightgreen"
                else:
                    reasons = []
                    if self.is_wet: reasons.append("RAIN")
                    if self.is_obscured: reasons.append("OBSCURED")
                    if wind_val and wind_val >= 15: reasons.append("WIND")
                    if extreme_dew: reasons.append("DEW")
                    if not ai_safe: reasons.append("CLOUDY")
                    roof_text, roof_color = (f"UNSAFE: {', '.join(reasons)}" if reasons else "UNSAFE"), "red"
                self.right_panel.nametowidget(self.val_dome).config(text=roof_text, fg=roof_color)
                
                if self.is_wet or self.is_obscured or (wind_val and wind_val > 20) or (self.ai_sky_status == "CLOUDY"):
                    with open(self.path_roof_cmd, "w") as f: f.write("CLOSE")
                    if self.last_roof_safety_state == "SAFE TO OPEN" and not self.emergency_sent:
                        reason = "RAIN/OBSCURED" if (self.is_wet or self.is_obscured) else ("INCOMING CLOUD FRONT" if self.ai_sky_status == "CLOUDY" else f"HIGH WIND ({wind_val} mph)")
                        self.send_email_notification("EMERGENCY ROOF CLOSE", f"Roof forced CLOSED: {reason}.\n\n{sensor_report}")
                        self.emergency_sent = True
                else: self.emergency_sent = False
                self.last_roof_safety_state = roof_text
            except: pass
            
        self.root.after(1000, self.update_loop)

    def create_ui_elements(self):
        menu_frame = tk.Frame(self.root, bg="#0a0a0a", bd=2, relief="groove")
        menu_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        for col in range(9): menu_frame.grid_columnconfigure(col, weight=1)
        menu_frame.grid_rowconfigure(0, weight=1)
        
        exit_min_frame = tk.Frame(menu_frame, bg="#0a0a0a")
        exit_min_frame.grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        tk.Button(exit_min_frame, text="_", command=self.minimize_hud, bg="#333", fg="white", font=("Arial", 9, "bold"), width=3).pack(side="left", padx=1)
        tk.Button(exit_min_frame, text="X", command=self.shutdown, bg="#500", fg="white", font=("Arial", 9, "bold"), width=3).pack(side="left", padx=1)
        
        self.btn_dew = tk.Button(menu_frame, text="DEW HTR: AUTO", command=self.toggle_dew, bg="#333", fg="white", font=("Arial", 9, "bold"))
        self.btn_dew.grid(row=0, column=1, padx=4, pady=4, sticky="ew")

        tk.Button(menu_frame, text="WEATHER HIST", command=self.show_weather_history, bg="#003366", fg="white", font=("Arial", 9, "bold")).grid(row=0, column=2, padx=4, pady=4, sticky="ew")
        tk.Button(menu_frame, text="DOSSIER / MAINT", command=self.open_dossier, bg="#222", fg="white", font=("Arial", 9, "bold")).grid(row=0, column=3, padx=4, pady=4, sticky="ew")
        self.power_btn = tk.Button(menu_frame, text="⚡ SEESTAR", command=self.trigger_fingerbot, bg="#900", fg="white", font=("Arial", 9, "bold"))
        self.power_btn.grid(row=0, column=4, padx=4, pady=4, sticky="ew")
        
        self.btn_control = tk.Button(menu_frame, text="🔭 SEESTAR ALP", bg="#FFD700", fg="black", font=("Arial", 9, "bold"), command=self.open_seestar_alp)
        self.btn_control.grid(row=0, column=5, padx=4, pady=4, sticky="ew")
        
        self.btn_health = tk.Button(menu_frame, text="🩺 HEALTH CHK", bg="#5D6D7E", fg="white", font=("Arial", 9, "bold"), command=self.run_health_check)
        self.btn_health.grid(row=0, column=6, padx=4, pady=4, sticky="ew")
        self.net_lbl = tk.Label(menu_frame, text="NET: CHECKING...", font=("Arial", 9, "bold"), bg="#0a0a0a", fg="cyan")
        self.net_lbl.grid(row=0, column=7, padx=4, pady=4, sticky="w")
        
        self.left_workspace = tk.Frame(self.root, bg="black")
        self.left_workspace.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.left_workspace.grid_rowconfigure(0, weight=1)
        self.left_workspace.grid_rowconfigure(1, weight=6)
        self.left_workspace.grid_rowconfigure(2, weight=4)
        self.left_workspace.grid_columnconfigure(0, weight=1)
        self.left_workspace.grid_columnconfigure(1, weight=1)
        
        roof_btn_frame = tk.Frame(self.left_workspace, bg="black")
        roof_btn_frame.grid(row=0, column=0, columnspan=2, pady=5, sticky="ew")
        roof_btn_frame.grid_columnconfigure((0,1,2), weight=1)
        
        self.btn_open = tk.Button(roof_btn_frame, text="OPEN ROOF", bg="#1E8449", fg="white", font=("Arial", 9, "bold"), command=self.manual_open)
        self.btn_open.grid(row=0, column=0, padx=10, sticky="ew")
        self.btn_ai = tk.Button(roof_btn_frame, text="AI MOVEMENT CHECK", bg="#6C3483", fg="white", font=("Arial", 9, "bold"), command=lambda: self.run_ai_clear_check(manual_click=True))
        self.btn_ai.grid(row=0, column=1, padx=10, sticky="ew")
        self.btn_close = tk.Button(roof_btn_frame, text="CLOSE ROOF", bg="#922B21", fg="white", font=("Arial", 9, "bold"), command=self.manual_close)
        self.btn_close.grid(row=0, column=2, padx=10, sticky="ew")
        
        self.all_canvas = tk.Canvas(self.left_workspace, bg="#050505", highlightthickness=1, highlightbackground="#222")
        self.all_canvas.grid(row=1, column=0, padx=4, pady=4, sticky="nsew")
        self.all_img_id = self.all_canvas.create_image(0, 0, anchor='nw')
        self.all_canvas.tag_bind(self.all_img_id, "<Button-1>", lambda e: self.popout(self.path_allsky))
        
        self.rad_canvas = tk.Canvas(self.left_workspace, bg="#050505", highlightthickness=1, highlightbackground="#222")
        self.rad_canvas.grid(row=1, column=1, padx=4, pady=4, sticky="nsew")
        self.rad_img_id = self.rad_canvas.create_image(0, 0, anchor='nw')
        self.rad_canvas.tag_bind(self.rad_img_id, "<Button-1>", lambda e: self.popout(self.path_radar))
        
        self.clk_canvas = tk.Canvas(self.left_workspace, bg="#050505", highlightthickness=1, highlightbackground="#222")
        self.clk_canvas.grid(row=2, column=0, columnspan=2, padx=4, pady=4, sticky="nsew")
        self.clk_img_id = self.clk_canvas.create_image(0, 0, anchor='nw')
        self.clk_canvas.tag_bind(self.clk_img_id, "<Button-1>", lambda e: self.popout(self.path_clock))
        
        self.right_panel = tk.Frame(self.root, bg="#050505", bd=3, relief="ridge", highlightthickness=1, highlightbackground="#00FFCC")
        self.right_panel.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)
        for r in range(12): self.right_panel.grid_rowconfigure(r, weight=1)
        self.right_panel.grid_columnconfigure(0, weight=1)
        self.right_panel.grid_columnconfigure(1, weight=3)
        self.right_panel.grid_columnconfigure(2, weight=3)
        
        tk.Label(self.right_panel, text="TELEMETRY", bg="#050505", fg="#00FFCC", font=("Arial", 12, "bold")).grid(row=0, column=0, columnspan=3, pady=5)
        
        self.val_amb = self.build_telemetry_row("🌡️", "AMB TEMP:", "#EC7063", 1)
        self.val_hum = self.build_telemetry_row("💧", "HUMIDITY:", "#5499C7", 2)
        self.val_dew = self.build_telemetry_row("✨", "DEW POINT:", "#A569BD", 3)
        self.val_heat = self.build_telemetry_row("🔥", "DEW HEAT:", "#FF5733", 4)
        self.val_pres = self.build_telemetry_row("⏲️", "PRESSURE:", "#58D68D", 5)
        self.val_wind = self.build_telemetry_row("💨", "WIND SPD:", "#F4D03F", 6)
        self.val_dir  = self.build_telemetry_row("🧭", "WIND DIR:", "#3498DB", 7)
        self.val_rain = self.build_telemetry_row("☔", "RAIN DET:", "#AF7AC5", 8)
        self.val_dome = self.build_telemetry_row("🏠", "ROOF STAT:", "#EB984E", 9)
        self.val_alpaca = self.build_telemetry_row("🔭", "ALPACA LINK:", "#00FF00", 10)
        
        timer_frame = tk.Frame(self.right_panel, bg="#050505")
        timer_frame.grid(row=11, column=0, columnspan=3, sticky="nsew", padx=5)
        timer_frame.grid_columnconfigure(1, weight=1)
        self.sync_canvas = tk.Canvas(timer_frame, width=16, height=16, bg="#050505", highlightthickness=0)
        self.sync_canvas.pack(side="left", padx=5)
        self.sync_light = self.sync_canvas.create_oval(2, 2, 14, 14, fill="gray", outline="white")
        tk.Label(timer_frame, text="OP HOURS:", bg="#050505", fg="white", font=("Arial", 10, "bold")).pack(side="left")
        self.val_hrs = tk.Label(timer_frame, text="--", bg="#050505", fg="cyan", font=("Courier", 12, "bold"))
        self.val_hrs.pack(side="right", padx=10)

        self.preview_frame = tk.Frame(self.root, bg="black")
        self.preview_frame.grid(row=2, column=1, sticky="nsew", padx=5, pady=5)

    def build_telemetry_row(self, icon, label, color, row_idx):
        tk.Label(self.right_panel, text=icon, bg="#050505", fg=color, font=("Arial", 14), anchor="w").grid(row=row_idx, column=0, padx=5, sticky="w")
        tk.Label(self.right_panel, text=label, bg="#050505", fg="white", font=("Arial", 10, "bold"), anchor="w").grid(row=row_idx, column=1, sticky="w")
        lbl_val = tk.Label(self.right_panel, text="--", bg="#050505", fg="cyan", font=("Courier", 12, "bold"), anchor="e")
        lbl_val.grid(row=row_idx, column=2, padx=10, sticky="e")
        return lbl_val

    def popout(self, path):
        if not os.path.exists(path): return
        pop = tk.Toplevel(self.root)
        pop.attributes("-fullscreen", True, "-topmost", True)
        pop.config(bg='black')
        img = Image.open(path)
        if "latest.jpg" in path.lower(): img.thumbnail((int(self.sw * 0.95), int(self.sh * 0.95)), Image.Resampling.LANCZOS)
        elif "radar" in path.lower() or "motion_debug" in path.lower():
            new_h = int(self.sh * 0.88); ratio = new_h / float(img.size[1]);
            new_w = int(float(img.size[0]) * ratio)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        else: img.thumbnail((int(self.sw * 0.8), int(self.sh * 0.8)), Image.Resampling.LANCZOS)
        self.p_img = ImageTk.PhotoImage(img)
        tk.Button(pop, image=self.p_img, bg='black', bd=0, activebackground='black', command=pop.destroy).pack(expand=True)

if __name__ == "__main__":
    root = tk.Tk()
    app = SumnerHUD(root)
    root.mainloop()