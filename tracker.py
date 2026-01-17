import time
import requests
import json
import os
import sys
import tkinter as tk
from tkinter import messagebox
from pynput import mouse, keyboard
import subprocess
import ctypes
import pyautogui
import base64
import io

if sys.platform == "win32":
    import winreg as reg

# ================= CONFIGURATION =================
if sys.platform == "win32":
    BASE_DIR = os.path.join(os.environ["APPDATA"], "SoftexHRM")
else:
    BASE_DIR = os.path.join(os.path.expanduser("~"), ".config", "softex_hrm")

if not os.path.exists(BASE_DIR):
    os.makedirs(BASE_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(BASE_DIR, "sys_config.dat")
SERVER_URL = "https://hrm.softexsolution.com"

# Global State
employee_data = None
is_tracking = False
mouse_events = 0
key_events = 0

# ================= AUTO-STARTUP LOGIC =================
def add_to_startup():
    if sys.platform == "win32":
        try:
            if getattr(sys, "frozen", False):
                file_path = sys.executable
            else:
                file_path = os.path.abspath(__file__)

            key = winreg.HKEY_CURRENT_USER
            key_value = r"Software\Microsoft\Windows\CurrentVersion\Run"
            open_key = winreg.OpenKey(key, key_value, 0, winreg.KEY_ALL_ACCESS)
            winreg.SetValueEx(open_key, "SoftexHRM", 0, winreg.REG_SZ, file_path)
            winreg.CloseKey(open_key)
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

# ================= UI =================
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

# ================= INPUT LISTENERS =================
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

# ================= MAIN LOOP =================
def main_loop():
    global is_tracking, mouse_events, key_events
    start_listeners()

    while True:
        try:
            emp_id = employee_data["employeeId"]
            command = "STOP"
            should_ss = False

            # 1. STATUS CHECK
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

                # 2. SEND DIRECTLY TO BACKEND (single log)
                log = {
                    "windowTitle": win,
                    "isCoding": bool(is_code),
                    "activityScore": int(total_acts),
                    "ss": ss_data,
                    "tamperAlert": False,
                    "createdAt": time.time(),  # seconds
                }
                try:
                    r = requests.post(
                        f"{SERVER_URL}/api/tracker/update",
                        json={"employeeId": emp_id, "logs": [log]},
                        timeout=30,
                    )
                    print("UPLOAD STATUS:", r.status_code, r.text)
                except Exception as e:
                    print("Upload error:", e)

                # reset counters for next 5-second window
                mouse_events = 0
                key_events = 0
            else:
                is_tracking = False

            # keep running as long as machine is on
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
