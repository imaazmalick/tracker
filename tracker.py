import time
import requests
import json
import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox
from pynput import mouse, keyboard
import subprocess
import ctypes
import pyautogui
import base64
import io
import sqlite3

# --- PLATFORM SPECIFIC IMPORTS ---
if sys.platform == "win32":
    import winreg as reg

# ================= CONFIGURATION =================
if sys.platform == "win32":
    # Windows: C:\Users\<User>\AppData\Roaming\SoftexHRM
    BASE_DIR = os.path.join(os.environ["APPDATA"], "SoftexHRM")
else:
    # Linux: /home/<user>/.config/softex_hrm
    BASE_DIR = os.path.join(os.path.expanduser("~"), ".config", "softex_hrm")

if not os.path.exists(BASE_DIR):
    os.makedirs(BASE_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(BASE_DIR, "sys_config.dat")
DB_FILE = os.path.join(BASE_DIR, "sys_logs.db")
SERVER_URL = "https://hrm.softexsolution.com"

# Tamper Detection
TAMPER_FLAG = False
if os.path.exists(CONFIG_FILE) and not os.path.exists(DB_FILE):
    TAMPER_FLAG = True

# Global State
employee_data = None
is_tracking = False
mouse_events = 0
key_events = 0

# ================= AUTO-STARTUP LOGIC =================
def add_to_startup():
    """Adds the script to startup (Registry for Windows, Autostart for Linux)."""
    if sys.platform == "win32":
        try:
            if getattr(sys, "frozen", False):
                file_path = sys.executable
            else:
                file_path = os.path.abspath(__file__)

            key = reg.HKEY_CURRENT_USER
            key_value = r"Software\Microsoft\Windows\CurrentVersion\Run"
            open_key = reg.OpenKey(key, key_value, 0, reg.KEY_ALL_ACCESS)
            reg.SetValueEx(open_key, "SoftexHRM", 0, reg.REG_SZ, file_path)
            reg.CloseKey(open_key)
        except Exception as e:
            print(f"Windows Startup Failed: {e}")

    elif sys.platform.startswith("linux"):
        try:
            if getattr(sys, "frozen", False):
                exe_path = sys.executable
            else:
                exe_path = f"{sys.executable} {os.path.abspath(__file__)}"

            autostart_dir = os.path.join(
                os.path.expanduser("~"), ".config", "autostart"
            )
            if not os.path.exists(autostart_dir):
                os.makedirs(autostart_dir)

            desktop_file = os.path.join(autostart_dir, "softex_hrm.desktop")
            content = f"""[Desktop Entry]
Type=Application
Exec={exe_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=Softex HRM Agent
Comment=Employee Activity Tracker
"""
            with open(desktop_file, "w") as f:
                f.write(content)

            os.chmod(desktop_file, 0o755)
        except Exception as e:
            print(f"Linux Startup Failed: {e}")

# ================= DATABASE ENGINE =================
def init_db():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            """CREATE TABLE IF NOT EXISTS activity_logs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      window_title TEXT,
                      is_coding INTEGER,
                      activity_score INTEGER,
                      timestamp REAL,
                      screenshot TEXT,
                      is_tamper_alert INTEGER DEFAULT 0)"""
        )

        if TAMPER_FLAG:
            c.execute(
                "INSERT INTO activity_logs "
                "(window_title, is_coding, activity_score, timestamp, is_tamper_alert) "
                "VALUES (?, ?, ?, ?, ?)",
                ("SYSTEM_SECURITY_EVENT: LOGS_DELETED", 0, 0, time.time(), 1),
            )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Init Error: {e}")

def save_log_local(window, is_coding, score, screenshot=None):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            "INSERT INTO activity_logs "
            "(window_title, is_coding, activity_score, timestamp, screenshot, is_tamper_alert) "
            "VALUES (?, ?, ?, ?, ?, 0)",
            (window, 1 if is_coding else 0, score, time.time(), screenshot),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Local Save Error: {e}")

def get_unsent_logs():
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM activity_logs")
        rows = c.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"Get logs error: {e}")
        return []

def clear_logs(log_ids):
    if not log_ids:
        return
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.executemany(
            "DELETE FROM activity_logs WHERE id = ?",
            [(i,) for i in log_ids],
        )
        print("Rows deleted from local DB:", c.rowcount)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Clear Log Error: {e}")

# ================= CONFIG MANAGERS =================
def save_config(data):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print("Save config error:", e)

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print("Load config error:", e)
            return None
    return None

# ================= OS UTILITIES =================
def get_active_window_title():
    current_os = sys.platform
    try:
        if current_os == "win32":
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            return buff.value if buff.value else "Unknown"
        elif current_os.startswith("linux"):
            result = subprocess.check_output(
                ["xdotool", "getactivewindow", "getwindowname"]
            )
            return result.decode("utf-8").strip()
        return "Unknown"
    except Exception:
        return "Unknown"

def take_screenshot_base64():
    try:
        screenshot = pyautogui.screenshot()
        img_buffer = io.BytesIO()
        screenshot.save(img_buffer, format="JPEG", quality=30)
        img_str = base64.b64encode(img_buffer.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{img_str}"
    except Exception as e:
        print("Screenshot error:", e)
        return None

# ================= UI & MAIN LOOP =================
def show_login():
    root = tk.Tk()
    root.title("Softex HRM Agent")

    w, h = 350, 250
    ws, hs = root.winfo_screenwidth(), root.winfo_screenheight()
    x, y = (ws / 2) - (w / 2), (hs / 2) - (h / 2)
    root.geometry(f"{w}x{h}+{int(x)}+{int(y)}")

    tk.Label(
        root,
        text="Softex HRM Configuration",
        font=("Segoe UI", 12, "bold"),
    ).pack(pady=20)
    frame = tk.Frame(root)
    frame.pack(pady=5)

    tk.Label(frame, text="Email:").grid(row=0, column=0, sticky="e")
    entry_email = tk.Entry(frame)
    entry_email.grid(row=0, column=1, padx=5)

    tk.Label(frame, text="Password:").grid(row=1, column=0, sticky="e", pady=5)
    entry_pass = tk.Entry(frame, show="*")
    entry_pass.grid(row=1, column=1, padx=5, pady=5)

    def perform_login():
        email = entry_email.get()
        password = entry_pass.get()
        if not email or not password:
            messagebox.showwarning("Input", "Please fill all fields")
            return
        try:
            res = requests.post(
                f"{SERVER_URL}/api/tracker/login",
                json={"email": email, "password": password},
                timeout=10,
            )
            if res.status_code == 200:
                data = res.json()
                save_config(data)
                messagebox.showinfo("Success", "Agent Configured Successfully.")
                root.destroy()
            else:
                messagebox.showerror("Error", "Invalid Credentials")
        except Exception as e:
            messagebox.showerror("Network Error", str(e))

    tk.Button(
        root,
        text="Authenticate Device",
        command=perform_login,
        bg="#28a745",
        fg="white",
    ).pack(pady=20)
    root.mainloop()

def start_listeners():
    def on_move(x, y):
        global mouse_events
        if is_tracking:
            mouse_events += 1

    def on_press(key):
        global key_events
        if is_tracking:
            key_events += 1

    try:
        ml = mouse.Listener(on_move=on_move)
        kl = keyboard.Listener(on_press=on_press)
        ml.start()
        kl.start()
        print("Listeners started:", ml.is_alive(), kl.is_alive())
    except Exception as e:
        print("Listener start error:", e)

def main_loop():
    global is_tracking, mouse_events, key_events
    init_db()
    start_listeners()

    last_upload = time.time()
    UPLOAD_INTERVAL = 300  # 5 min

    while True:
        try:
            emp_id = employee_data["employeeId"]
            command = "STOP"
            should_ss = False

            # STATUS CHECK
            try:
                res = requests.get(
                    f"{SERVER_URL}/api/tracker/status?employeeId={emp_id}",
                    timeout=5,
                )
                print("STATUS RESPONSE:", res.status_code, res.text)
                if res.status_code == 200:
                    data = res.json()
                    command = data.get("command", "STOP")
                    should_ss = data.get("ss", False)
            except Exception as e:
                print("Status check error:", e)

            if command == "START":
                is_tracking = True
                win = get_active_window_title()
                is_code = any(
                    x in win.lower()
                    for x in ["code", "visual studio", ".py", ".js", ".ts"]
                )
                ss_data = take_screenshot_base64() if should_ss else None
                total_acts = mouse_events + key_events
                print("Activity:", total_acts, "Window:", win)
                save_log_local(win, is_code, total_acts, ss_data)
                mouse_events = 0
                key_events = 0

                # UPLOAD
                if time.time() - last_upload > UPLOAD_INTERVAL:
                    logs = get_unsent_logs()
                    print("Unsent logs count:", len(logs))
                    if logs:
                        payload = []
                        ids = []
                        for row in logs:
                            payload.append(
                                {
                                    "windowTitle": row["window_title"],
                                    "isCoding": bool(row["is_coding"]),
                                    "activityScore": row["activity_score"],
                                    "ss": row["screenshot"],
                                    "tamperAlert": bool(row["is_tamper_alert"]),
                                    "createdAt": row["timestamp"],  # seconds
                                }
                            )
                            ids.append(row["id"])
                        try:
                            r = requests.post(
                                f"{SERVER_URL}/api/tracker/update",
                                json={"employeeId": emp_id, "logs": payload},
                                timeout=60,
                            )
                            print("UPLOAD STATUS:", r.status_code, r.text)
                            if r.status_code in (200, 201):
                                clear_logs(ids)
                                last_upload = time.time()
                            else:
                                print("Upload failed; logs kept locally")
                        except Exception as e:
                            print("Upload error:", e)
            else:
                is_tracking = False

            time.sleep(5)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print("Main loop error:", e)
            time.sleep(10)

if __name__ == "__main__":
    add_to_startup()
    employee_data = load_config()
    if not employee_data:
        show_login()
        employee_data = load_config()
    if employee_data:
        main_loop()
