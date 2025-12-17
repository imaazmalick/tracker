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

# ================= CONFIGURATION =================
SERVER_URL = "https://hrm.softexsolution.com"
CONFIG_FILE = "hrm_config.json"
# =================================================

# Global Variables
employee_data = None
is_tracking = False
mouse_events = 0
key_events = 0

# --- Helper: Save/Load Config ---
def save_config(data):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Error saving config: {e}")

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            return None
    return None

# --- Helper: Get Active Window (Cross-Platform) ---
def get_active_window_title():
    current_os = sys.platform
    try:
        # 1. WINDOWS LOGIC
        if current_os == "win32":
            import pygetwindow as gw
            window = gw.getActiveWindow()
            if window:
                return window.title
            return "Unknown"

        # 2. LINUX LOGIC (Requires xdotool)
        elif current_os.startswith("linux"):
            try:
                # Use xdotool to get the active window name
                result = subprocess.check_output(["xdotool", "getwindowfocus", "getwindowname"])
                return result.decode("utf-8").strip()
            except subprocess.CalledProcessError:
                return "Unknown (Wayland/Error)"
            except FileNotFoundError:
                return "Error: xdotool not installed"
        
        # 3. MACOS LOGIC (Optional)
        elif current_os == "darwin":
            from AppKit import NSWorkspace
            return NSWorkspace.sharedWorkspace().activeApplication()['NSApplicationName']

    except Exception as e:
        print(f"Window detection error: {e}")
        return "Unknown"
    
    return "Unknown"

# --- UI: Login Window ---
def show_login():
    root = tk.Tk()
    root.title("HRM Tracker Setup")
    root.geometry("350x250")
    
    lbl_status = tk.Label(root, text="HRM Employee Login", font=("Arial", 14, "bold"))
    lbl_status.pack(pady=15)

    frame = tk.Frame(root)
    frame.pack(pady=5)

    tk.Label(frame, text="Email:").grid(row=0, column=0, padx=5, sticky="e")
    entry_email = tk.Entry(frame, width=25)
    entry_email.grid(row=0, column=1, padx=5)

    tk.Label(frame, text="Password:").grid(row=1, column=0, padx=5, sticky="e", pady=5)
    entry_pass = tk.Entry(frame, show="*", width=25)
    entry_pass.grid(row=1, column=1, padx=5, pady=5)

    def perform_login():
        email = entry_email.get()
        password = entry_pass.get()
        
        if not email or not password:
            messagebox.showwarning("Input Error", "Please fill in all fields")
            return

        try:
            res = requests.post(f"{SERVER_URL}/api/tracker/login", json={
                "email": email, "password": password
            })
            
            if res.status_code == 200:
                data = res.json()
                save_config(data)
                messagebox.showinfo("Success", f"Welcome {data.get('name')}!")
                root.destroy() 
            else:
                messagebox.showerror("Error", "Login Failed")
        except Exception as e:
            messagebox.showerror("Connection Error", str(e))

    tk.Button(root, text="Connect", command=perform_login, bg="#007bff", fg="white").pack(pady=20)
    root.mainloop()

# --- TRACKING: Input Listeners ---
def start_listeners():
    def on_move(x, y):
        global mouse_events
        if is_tracking: mouse_events += 1

    def on_press(key):
        global key_events
        if is_tracking: key_events += 1

    try:
        mouse.Listener(on_move=on_move).start()
        keyboard.Listener(on_press=on_press).start()
    except Exception as e:
        print(f"Listener Error: {e}")

# --- MAIN LOOP ---
def main_loop():
    global is_tracking, mouse_events, key_events, employee_data
    print(f"--- Agent Active: {employee_data.get('name')} ---")
    start_listeners()

    while True:
        try:
            emp_id = employee_data['employeeId']

            # Check Status
            command = "STOP"
            try:
                res = requests.get(f"{SERVER_URL}/api/tracker/status?employeeId={emp_id}", timeout=5)
                if res.status_code == 200:
                    command = res.json().get('command', 'STOP')
            except:
                pass

            if command == "START":
                is_tracking = True
                
                # Get Window Title (Using the cross-platform function)
                win_title = get_active_window_title()

                is_coding = False
                if win_title:
                    lower = win_title.lower()
                    if "visual studio code" in lower or "code" in lower or ".py" in lower:
                        is_coding = True

                total_activity = mouse_events + key_events

                payload = {
                    "employeeId": emp_id,
                    "windowTitle": win_title,
                    "isCoding": is_coding,
                    "activityScore": total_activity
                }
                
                try:
                    requests.post(f"{SERVER_URL}/api/tracker/update", json=payload, timeout=3)
                    print(f"Logged: {win_title} | Score: {total_activity}")
                except:
                    pass

                mouse_events = 0
                key_events = 0
            else:
                is_tracking = False

            time.sleep(5)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    employee_data = load_config()
    if not employee_data:
        show_login()
        employee_data = load_config()
    
    if employee_data:
        main_loop()
