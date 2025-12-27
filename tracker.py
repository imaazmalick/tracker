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

# ================= CONFIGURATION =================
SERVER_URL = "https://hrm.softexsolution.com"
# Save files in User's Home Directory (Safe for Windows/Linux)
CONFIG_FILE = os.path.join(os.path.expanduser("~"), "hrm_config.json")
DB_FILE = os.path.join(os.path.expanduser("~"), "hrm_logs.db")
# =================================================

# Global Variables
employee_data = None
is_tracking = False
mouse_events = 0
key_events = 0

# --- DATABASE ENGINE (Offline Storage) ---
def init_db():
    """Create local database table if it doesn't exist."""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS activity_logs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      window_title TEXT,
                      is_coding INTEGER,
                      activity_score INTEGER,
                      timestamp REAL,
                      screenshot TEXT)''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Init Error: {e}")

def save_log_local(window, is_coding, score, screenshot=None):
    """Save a single log entry to local disk immediately."""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO activity_logs (window_title, is_coding, activity_score, timestamp, screenshot) VALUES (?, ?, ?, ?, ?)",
                  (window, 1 if is_coding else 0, score, time.time(), screenshot))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Local Save Error: {e}")

def get_unsent_logs():
    """Fetch all logs that haven't been uploaded yet."""
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM activity_logs")
        rows = c.fetchall()
        conn.close()
        return rows
    except:
        return []

def clear_logs(log_ids):
    """Delete specific logs after successful upload."""
    if not log_ids: return
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        # Securely delete only the IDs that were uploaded
        query = f"DELETE FROM activity_logs WHERE id IN ({','.join(map(str, log_ids))})"
        c.execute(query)
        conn.commit()
        conn.close()
        print(f"Cleared {len(log_ids)} records from local disk.")
    except Exception as e:
        print(f"Clear Log Error: {e}")

# --- CONFIG HELPERS ---
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

# --- ROBUST WINDOW TITLE DETECTION ---
def get_active_window_title():
    current_os = sys.platform
    try:
        # 1. WINDOWS LOGIC (Native API for Tab Names)
        if current_os == "win32":
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value
            return title if title else "Unknown"

        # 2. LINUX LOGIC (Native xdotool)
        elif current_os.startswith("linux"):
            try:
                result = subprocess.check_output(["xdotool", "getactivewindow", "getwindowname"])
                title = result.decode("utf-8").strip()
                return title if title else "Unknown"
            except:
                return "Unknown"
        
        # 3. MACOS LOGIC
        elif current_os == "darwin":
            from AppKit import NSWorkspace
            return NSWorkspace.sharedWorkspace().activeApplication()['NSApplicationName']

    except Exception:
        return "Unknown"
    return "Unknown"

# --- SCREENSHOT CAPTURE ---
def take_screenshot_base64():
    try:
        screenshot = pyautogui.screenshot()
        img_buffer = io.BytesIO()
        # Compress to JPEG Quality 40 (Small size, fast upload)
        screenshot.save(img_buffer, format='JPEG', quality=40)
        img_str = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
        return f"data:image/jpeg;base64,{img_str}"
    except Exception as e:
        print(f"Screenshot Error: {e}")
        return None

# --- UI: LOGIN WINDOW ---
def show_login():
    root = tk.Tk()
    root.title("HRM Tracker Setup")
    root.geometry("350x250")
    
    # Center Window
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width / 2) - (350 / 2)
    y = (screen_height / 2) - (250 / 2)
    root.geometry(f'350x250+{int(x)}+{int(y)}')
    
    tk.Label(root, text="HRM Employee Login", font=("Arial", 14, "bold")).pack(pady=15)
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
            messagebox.showwarning("Error", "Fill all fields")
            return
        try:
            res = requests.post(f"{SERVER_URL}/api/tracker/login", json={"email": email, "password": password})
            if res.status_code == 200:
                data = res.json()
                save_config(data)
                messagebox.showinfo("Success", f"Welcome {data.get('name')}!")
                root.destroy() 
            else:
                messagebox.showerror("Error", "Login Failed")
        except Exception as e:
            messagebox.showerror("Connection Error", str(e))

    tk.Button(root, text="Connect", command=perform_login, bg="#007bff", fg="white", width=15).pack(pady=20)
    root.mainloop()

# --- ACTIVITY LISTENERS ---
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

# --- MAIN AGENT LOOP ---
def main_loop():
    global is_tracking, mouse_events, key_events, employee_data
    
    init_db() # Create DB if new
    print(f"--- Agent Active: {employee_data.get('name')} ---")
    start_listeners()

    # Sync Timer
    last_upload_time = time.time()
    UPLOAD_INTERVAL = 300 # 5 Minutes (Sync Interval)

    while True:
        try:
            emp_id = employee_data['employeeId']
            
            # 1. POLL STATUS (Every 5 seconds)
            command = "STOP"
            should_take_ss = False
            
            try:
                res = requests.get(f"{SERVER_URL}/api/tracker/status?employeeId={emp_id}", timeout=5)
                if res.status_code == 200:
                    data = res.json()
                    command = data.get('command', 'STOP')
                    should_take_ss = data.get('ss', False)
            except:
                # Offline Mode: Keep previous state or assume STOP depending on preference
                pass 

            if command == "START":
                is_tracking = True
                
                # A. CAPTURE
                win_title = get_active_window_title()
                is_coding = False
                if win_title:
                    lower = win_title.lower()
                    if "visual studio code" in lower or "code" in lower or ".py" in lower:
                        is_coding = True

                total_activity = mouse_events + key_events

                # B. SCREENSHOT (If requested)
                ss_data = None
                if should_take_ss:
                    print(">>> Capturing Screenshot...")
                    ss_data = take_screenshot_base64()

                # C. SAVE TO LOCAL DB (Instant backup)
                save_log_local(win_title, is_coding, total_activity, ss_data)
                print(f"Local Save: {win_title[:25]}... | Act: {total_activity} | SS: {'Yes' if ss_data else 'No'}")

                # Reset Counters
                mouse_events = 0
                key_events = 0

                # D. SYNC TO SERVER (Batch Upload)
                if time.time() - last_upload_time > UPLOAD_INTERVAL:
                    print(">>> Attempting Sync...")
                    unsent_rows = get_unsent_logs()
                    
                    if unsent_rows:
                        # Prepare Batch Payload
                        payload_logs = []
                        ids_to_clean = []
                        
                        for row in unsent_rows:
                            payload_logs.append({
                                "windowTitle": row['window_title'],
                                "isCoding": bool(row['is_coding']),
                                "activityScore": row['activity_score'],
                                "ss": row['screenshot'] 
                            })
                            ids_to_clean.append(row['id'])

                        # Upload
                        try:
                            res = requests.post(f"{SERVER_URL}/api/tracker/update", 
                                              json={"employeeId": emp_id, "logs": payload_logs}, 
                                              timeout=60)
                            
                            if res.status_code in [200, 201]:
                                print("✅ Sync Successful")
                                clear_logs(ids_to_clean) # Delete local copies
                                last_upload_time = time.time()
                            else:
                                print(f"❌ Server rejected data: {res.status_code}")
                        except Exception as e:
                            print(f"⚠️ Sync Failed (Offline?): {e}")
                    else:
                        print("Nothing to sync.")
                        last_upload_time = time.time()

            else:
                is_tracking = False

            time.sleep(5) # Tick every 5 seconds

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Critical Loop Error: {e}")
            time.sleep(5)

# --- ENTRY POINT ---
if __name__ == "__main__":
    employee_data = load_config()
    if not employee_data:
        show_login()
        employee_data = load_config()
    
    if employee_data:
        main_loop()
