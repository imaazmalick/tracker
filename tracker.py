import time
import requests
import json
import os
import threading
import tkinter as tk
from tkinter import messagebox
from pynput import mouse, keyboard
import pygetwindow as gw

# ================= CONFIGURATION =================
SERVER_URL = "https://hrm.softexsolution.com"
CONFIG_FILE = "hrm_config.json"
# =================================================

# Global Variables
employee_data = None
is_tracking = False
mouse_events = 0
key_events = 0
activity_buffer = []  # <--- NEW: Buffer to store history

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

# --- UI: Login Window ---
def show_login():
    root = tk.Tk()
    root.title("HRM Tracker Setup")
    root.geometry("350x250")
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width / 2) - (350 / 2)
    y = (screen_height / 2) - (250 / 2)
    root.geometry(f'350x250+{int(x)}+{int(y)}')
    
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
            url = f"{SERVER_URL}/api/tracker/login"
            res = requests.post(url, json={"email": email, "password": password})
            if res.status_code == 200:
                data = res.json()
                save_config(data)
                messagebox.showinfo("Success", f"Welcome {data.get('name', 'Employee')}!")
                root.destroy() 
            else:
                messagebox.showerror("Error", "Login Failed")
        except Exception as e:
            messagebox.showerror("Connection Error", str(e))

    tk.Button(root, text="Connect & Start", command=perform_login, bg="#007bff", fg="white", width=20, height=2).pack(pady=20)
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
        print(f"Error starting input listeners: {e}")

# --- MAIN: Background Loop ---
def main_loop():
    global is_tracking, mouse_events, key_events, employee_data, activity_buffer
    
    emp_name = employee_data.get('name', 'Unknown')
    print(f"--- Agent Active for: {emp_name} ---")
    start_listeners()

    while True:
        try:
            emp_id = employee_data['employeeId']

            # 1. Check Status (Fast Check)
            command = "STOP"
            try:
                res = requests.get(f"{SERVER_URL}/api/tracker/status?employeeId={emp_id}", timeout=5)
                if res.status_code == 200:
                    command = res.json().get('command', 'STOP')
            except:
                pass # Ignore polling errors

            if command == "START":
                is_tracking = True
                
                # --- A. CAPTURE SNAPSHOT ---
                win_title = "Unknown"
                try:
                    active_window = gw.getActiveWindow()
                    if active_window and active_window.title:
                        win_title = active_window.title.strip()
                except:
                    pass

                is_coding = False
                if win_title:
                    lower = win_title.lower()
                    if "visual studio code" in lower or "code" in lower or ".py" in lower:
                        is_coding = True

                # --- B. STORE IN BUFFER (RAM) ---
                # We do NOT send to server yet. We just save it locally.
                activity_buffer.append({
                    "windowTitle": win_title,
                    "isCoding": is_coding,
                    # Optional: You can send a timestamp here if needed
                })
                
                print(f"Recorded: {win_title[:20]}... (Buffer: {len(activity_buffer)}/60)")

                # --- C. CHECK IF 5 MINUTES PASSED ---
                # 60 samples * 5 seconds = 300 seconds (5 Minutes)
                if len(activity_buffer) >= 60:
                    
                    print(f">>> Uploading {len(activity_buffer)} records...")
                    
                    payload = {
                        "employeeId": emp_id,
                        "logs": activity_buffer,          # Send the FULL list
                        "totalMouseEvents": mouse_events, # Total clicks in 5 mins
                        "totalKeyEvents": key_events      # Total typing in 5 mins
                    }
                    
                    try:
                        requests.post(f"{SERVER_URL}/api/tracker/update", json=payload, timeout=10)
                        print("✅ Upload Successful")
                        
                        # Clear memory for next 5 minutes
                        activity_buffer = [] 
                        mouse_events = 0
                        key_events = 0
                        
                    except Exception as e:
                        print(f"❌ Upload Failed: {e}")
                        # Ideally, you keep the buffer and try again later, 
                        # but for simplicity, we clear it or keep appending.
            
            else:
                is_tracking = False
                activity_buffer = [] # Clear buffer if user checked out

            # Sleep 5 seconds (Fast Sampling)
            time.sleep(5)

        except Exception as e:
            print(f"Critical Loop Error: {e}")
            time.sleep(5)

# --- ENTRY POINT ---
if __name__ == "__main__":
    employee_data = load_config()
    if not employee_data:
        show_login()
        employee_data = load_config()
    if not employee_data:
        exit()
    try:
        main_loop()
    except KeyboardInterrupt:
        print("Agent Stopped.")
