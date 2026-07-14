import time
import requests
import json
import os
import shutil
import base64
import io
import platform
import subprocess
import datetime
import threading
import tkinter as tk
from tkinter import messagebox
from pynput import mouse, keyboard

# Screenshots and active-window detection are optional — if a package or system
# tool is missing on this machine, the tracker keeps logging plain activity
# instead of crashing. A crash here at import time is fatal: this app is built
# with --noconsole, so an uncaught import error kills the process before the
# login window ever appears, with no error message shown to the user.
try:
    import pyautogui
    SCREENSHOT_AVAILABLE = True
except Exception:
    SCREENSHOT_AVAILABLE = False

# ================= CONFIGURATION =================
# YOUR PRODUCTION URL
SERVER_URL = "https://synkrox.com"

# Everything lives in a predictable, well-known folder instead of "wherever the
# app's current working directory happened to be" (which varies depending on
# whether it was launched from a .desktop file, a terminal, or a file manager).
# This also gives the debug log a fixed, discoverable location — critical since
# the app is built with --noconsole, so nothing printed to stdout is ever seen.
APP_DIR = os.path.join(os.path.expanduser("~"), ".hrm_tracker")
os.makedirs(APP_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(APP_DIR, "hrm_config.json")
LOG_FILE = os.path.join(APP_DIR, "tracker_debug.log")
# =================================================

# Global Variables
employee_data = None
is_tracking = False
mouse_events = 0
key_events = 0

# --- Helper: Debug Logging ---
# print() is invisible on a --noconsole build. This writes every important
# event and failure reason to a log file the user/admin can actually open, so
# "Unknown" / a score of 0 / a missing screenshot is diagnosable instead of a
# silent black box.
def log_debug(message):
    line = f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {message}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

# --- Helper: Save/Load Config ---
def save_config(data):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        log_debug(f"Error saving config: {e}")

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            return None
    return None

# --- Startup Diagnostics ---
def log_environment_diagnostics():
    """
    Logs everything needed to diagnose why window-title detection, activity
    scoring, or screenshots aren't working, without requiring console access.
    """
    log_debug(f"=== Tracker starting | Python {platform.python_version()} | {platform.platform()} ===")

    if platform.system() == "Linux":
        session_type = os.environ.get("XDG_SESSION_TYPE", "unknown")
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "unknown")
        log_debug(f"Session type: {session_type} | Desktop: {desktop}")

        if session_type == "wayland":
            log_debug(
                "WARNING: Running under Wayland. xdotool (window titles), pynput's "
                "global input hooks (activity score), and pyautogui/scrot "
                "(screenshots) are all X11-only technologies and typically do NOT "
                "work under Wayland — this is a Wayland security restriction, not "
                "a bug in this app. For accurate tracking, log out and choose an "
                "'Xorg' / 'X11' session at the login screen (on GNOME/GDM this is "
                "usually a gear icon on the login screen next to your username)."
            )

        if shutil.which("xdotool") is None:
            log_debug("WARNING: xdotool not found on PATH. Window titles will always show 'Unknown'. Install with: sudo dnf install xdotool  (or apt-get install xdotool)")
        else:
            log_debug("xdotool found on PATH.")

        if shutil.which("scrot") is None:
            log_debug("WARNING: scrot not found on PATH. Screenshot capture will likely fail. Install with: sudo dnf install scrot  (or apt-get install scrot)")
        else:
            log_debug("scrot found on PATH.")

    log_debug(f"SCREENSHOT_AVAILABLE (pyautogui imported successfully): {SCREENSHOT_AVAILABLE}")

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
            log_debug(f"Connecting to: {url}")

            res = requests.post(url, json={
                "email": email, "password": password
            })

            if res.status_code == 200:
                data = res.json()
                save_config(data)
                log_debug(f"Login successful for {data.get('name', 'Employee')} (employeeId={data.get('employeeId')})")
                messagebox.showinfo("Success", f"Welcome {data.get('name', 'Employee')}!\nTracker is now ready.")
                root.destroy()
            else:
                try:
                    err_msg = res.json().get('error', 'Login Failed')
                except:
                    err_msg = "Login Failed"
                log_debug(f"Login failed: HTTP {res.status_code} — {err_msg}")
                messagebox.showerror("Error", err_msg)
        except Exception as e:
            log_debug(f"Login connection error: {e}")
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

    # Start listeners safely. On Linux these open an X11 connection under the
    # hood (pynput.mouse._xorg / pynput.keyboard._xorg) — under Wayland this
    # either raises here or silently never fires, which is why activity score
    # can get stuck at 0 with no visible error on a --noconsole build.
    try:
        m_listener = mouse.Listener(on_move=on_move)
        k_listener = keyboard.Listener(on_press=on_press)
        m_listener.start()
        k_listener.start()
        log_debug("Input listeners (mouse + keyboard) started successfully.")
    except Exception as e:
        log_debug(f"ERROR starting input listeners — activity score will stay 0: {e}")

_window_detection_failure_logged = False

# --- WINDOW TITLE: Active window detection (no extra pip package required) ---
def get_active_window_title():
    """
    Returns the title of the foreground window, or "Unknown" if it can't be
    determined. Deliberately avoids PyGetWindow: its Linux backend needs
    ewmh/python-xlib, which this app's build never installs, and importing it
    unguarded is what used to crash the tracker before the login window could
    even appear. Windows uses the built-in ctypes/Win32 API (no dependency);
    Linux shells out to xdotool, which the .deb/.rpm packages already depend on.
    """
    global _window_detection_failure_logged
    try:
        system = platform.system()
        if system == "Windows":
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buffer = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
            return buffer.value.strip() or "Unknown"
        elif system == "Linux":
            result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True,
                timeout=2,
            )
            title = result.stdout.decode("utf-8", errors="ignore").strip()
            if result.returncode != 0 and not _window_detection_failure_logged:
                stderr = result.stderr.decode("utf-8", errors="ignore").strip()
                log_debug(
                    f"xdotool failed (exit {result.returncode}): {stderr or '(no stderr)'} "
                    "— if this says 'cannot find display' or similar, this is almost "
                    "certainly a Wayland session; see the Wayland warning above. This "
                    "message only logs once to avoid flooding the log every 5 seconds."
                )
                _window_detection_failure_logged = True
            return title or "Unknown"
    except FileNotFoundError:
        if not _window_detection_failure_logged:
            log_debug("xdotool executable not found — cannot detect window titles on Linux without it.")
            _window_detection_failure_logged = True
    except Exception as e:
        if not _window_detection_failure_logged:
            log_debug(f"Window title detection failed: {e}")
            _window_detection_failure_logged = True
    return "Unknown"

# --- SCREENSHOT: Capture + Encode ---
def capture_screenshot():
    """Grabs the screen and returns a compact base64 data URI, or None on failure."""
    if not SCREENSHOT_AVAILABLE:
        log_debug("Screenshot requested but pyautogui is not available — see startup diagnostics above.")
        return None
    try:
        img = pyautogui.screenshot()
        # Keep the upload small and fast: cap width at 1280px and re-encode as JPEG.
        max_width = 1280
        if img.width > max_width:
            ratio = max_width / float(img.width)
            img = img.resize((max_width, int(img.height * ratio)))
        img = img.convert("RGB")

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=55)
        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
        log_debug(f"Screenshot captured successfully ({len(encoded)} base64 chars).")
        return f"data:image/jpeg;base64,{encoded}"
    except Exception as e:
        log_debug(f"Screenshot capture failed: {e}")
        return None

# --- MAIN: Background Loop ---
def main_loop():
    global is_tracking, mouse_events, key_events, employee_data

    emp_name = employee_data.get('name', 'Unknown')
    log_debug(f"--- Agent Active for: {emp_name} ---")
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
                log_debug("Server unreachable. Waiting...")
            except Exception as e:
                log_debug(f"Polling error: {e}")

            # 2. Handle Logic
            if command == "START":
                if not is_tracking:
                    log_debug(">>> Check-in detected. TRACKING STARTED.")
                is_tracking = True

                # Get Active Window (Robust way)
                win_title = get_active_window_title()

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

                payload = {
                    "employeeId": emp_id,
                    "logs": [log_entry],
                }

                try:
                    # Screenshot uploads are bigger than plain activity pings, so
                    # give this request more headroom than the 5s status poll.
                    requests.post(f"{SERVER_URL}/api/tracker/update", json=payload, timeout=15)
                    log_debug(f"Logged: {win_title[:30]}... | Activity: {total_activity}")
                except Exception as e:
                    log_debug(f"Failed to send log update (Network glitch): {e}")

                # Reset Counters
                mouse_events = 0
                key_events = 0

            else:
                if is_tracking:
                    log_debug("<<< Check-out detected. IDLE MODE.")
                is_tracking = False

            # Sleep for 5 seconds (5 seconds)
            time.sleep(5)

        except Exception as e:
            log_debug(f"Critical Loop Error: {e}")
            # If error occurs, retry after 5 minute instead of immediately
            time.sleep(5)

# --- ENTRY POINT ---
if __name__ == "__main__":
    log_environment_diagnostics()

    # 1. Try to load config
    employee_data = load_config()

    # 2. If no config, Force Login UI
    if not employee_data:
        show_login()
        # Reload after login closes
        employee_data = load_config()

    # 3. If still no data (user closed window), exit
    if not employee_data:
        log_debug("No user configuration found. Exiting.")
        exit()

    # 4. Start Tracker
    try:
        main_loop()
    except KeyboardInterrupt:
        log_debug("Agent Stopped.")
