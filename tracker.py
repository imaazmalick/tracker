import time
import requests
import json
import os
import base64
import io
import threading
import tkinter as tk
from tkinter import messagebox
from pynput import mouse, keyboard
import pygetwindow as gw

# Screenshot capture is optional — if Pillow (or its screen-grab backend) isn't
# available on this machine, the tracker keeps logging activity without screenshots
# instead of crashing.
try:
    from PIL import ImageGrab
    SCREENSHOT_AVAILABLE = True
except ImportError:
    SCREENSHOT_AVAILABLE = False

# ================= CONFIGURATION =================
# YOUR PRODUCTION URL
SERVER_URL = "https://synkrox.com"
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

# --- UI: Login Window ---
def show_login():
    root = tk.Tk()
    root.title("HRM Tracker Setup")
    root.geometry("350x250")
    
    # Center the window on screen
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
            print(f"Connecting to: {url}")
            
            res = requests.post(url, json={
                "email": email, "password": password
            })
            
            if res.status_code == 200:
                data = res.json()
                save_config(data)
                messagebox.showinfo("Success", f"Welcome {data.get('name', 'Employee')}!\nTracker is now ready.")
                root.destroy() 
            else:
                try:
                    err_msg = res.json().get('error', 'Login Failed')
                except:
                    err_msg = "Login Failed"
                messagebox.showerror("Error", err_msg)
        except Exception as e:
            messagebox.showerror("Connection Error", f"Could not connect to server.\nCheck your internet.\n\nError: {e}")

    btn = tk.Button(root, text="Connect & Start", command=perform_login, bg="#007bff", fg="white", width=20, height=2)
    btn.pack(pady=20)
    
    root.mainloop()

# --- TRACKING: Input Listeners ---
def start_listeners():
    def on_move(x, y):
        global mouse_events
        if is_tracking: mouse_events += 1

    def on_press(key):
        global key_events
        if is_tracking: key_events += 1

    # Start listeners safely
    try:
        m_listener = mouse.Listener(on_move=on_move)
        k_listener = keyboard.Listener(on_press=on_press)
        m_listener.start()
        k_listener.start()
    except Exception as e:
        print(f"Error starting input listeners: {e}")

# --- SCREENSHOT: Capture + Encode ---
def capture_screenshot():
    """Grabs the screen and returns a compact base64 data URI, or None on failure."""
    if not SCREENSHOT_AVAILABLE:
        return None
    try:
        img = ImageGrab.grab()
        # Keep the upload small and fast: cap width at 1280px and re-encode as JPEG.
        max_width = 1280
        if img.width > max_width:
            ratio = max_width / float(img.width)
            img = img.resize((max_width, int(img.height * ratio)))
        img = img.convert("RGB")

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=55)
        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{encoded}"
    except Exception as e:
        print(f"Screenshot capture failed: {e}")
        return None

# --- MAIN: Background Loop ---
def main_loop():
    global is_tracking, mouse_events, key_events, employee_data

    emp_name = employee_data.get('name', 'Unknown')
    print(f"--- Agent Active for: {emp_name} ---")
    start_listeners()

    while True:
        try:
            emp_id = employee_data['employeeId']

            # 1. Check Status (Polling)
            command = "STOP"
            should_screenshot = False
            try:
                # Poll the API
                res = requests.get(f"{SERVER_URL}/api/tracker/status?employeeId={emp_id}", timeout=5)
                if res.status_code == 200:
                    status_data = res.json()
                    command = status_data.get('command', 'STOP')
                    should_screenshot = bool(status_data.get('ss', False))
            except requests.exceptions.ConnectionError:
                print("Server unreachable. Waiting...")
            except Exception as e:
                print(f"Polling error: {e}")

            # 2. Handle Logic
            if command == "START":
                if not is_tracking:
                    print(">>> Check-in detected. TRACKING STARTED.")
                is_tracking = True

                # Get Active Window (Robust way)
                win_title = "Unknown"
                try:
                    active_window = gw.getActiveWindow()
                    if active_window and active_window.title:
                        win_title = active_window.title.strip()
                except:
                    pass

                # Check for VS Code or other IDEs
                is_coding = False
                if win_title:
                    lower_title = win_title.lower()
                    if "visual studio code" in lower_title or "code" in lower_title or ".py" in lower_title or ".js" in lower_title:
                        is_coding = True

                total_activity = mouse_events + key_events

                # Build one log entry. The server expects a batch of entries under
                # "logs" even when we only have one per poll cycle — sending the old
                # flat shape here means the server silently drops every update.
                log_entry = {
                    "windowTitle": win_title,
                    "isCoding": is_coding,
                    "activityScore": total_activity,
                    "createdAt": time.time(),
                }

                if should_screenshot:
                    screenshot = capture_screenshot()
                    if screenshot:
                        log_entry["ss"] = screenshot
                        print("Screenshot captured for this cycle.")

                payload = {
                    "employeeId": emp_id,
                    "logs": [log_entry],
                }

                try:
                    # Screenshot uploads are bigger than plain activity pings, so
                    # give this request more headroom than the 5s status poll.
                    requests.post(f"{SERVER_URL}/api/tracker/update", json=payload, timeout=15)
                    print(f"Logged: {win_title[:30]}... | Activity: {total_activity}")
                except:
                    print("Failed to send log update (Network glitch)")

                # Reset Counters
                mouse_events = 0
                key_events = 0

            else:
                if is_tracking:
                    print("<<< Check-out detected. IDLE MODE.")
                is_tracking = False

            # Sleep for 5 seconds (5 seconds)
            time.sleep(5)

        except Exception as e:
            print(f"Critical Loop Error: {e}")
            # If error occurs, retry after 5 minute instead of immediately
            time.sleep(5)

# --- ENTRY POINT ---
if __name__ == "__main__":
    # 1. Try to load config
    employee_data = load_config()

    # 2. If no config, Force Login UI
    if not employee_data:
        show_login()
        # Reload after login closes
        employee_data = load_config()

    # 3. If still no data (user closed window), exit
    if not employee_data:
        print("No user configuration found. Exiting.")
        exit()

    # 4. Start Tracker
    try:
        main_loop()
    except KeyboardInterrupt:
        print("Agent Stopped.")
