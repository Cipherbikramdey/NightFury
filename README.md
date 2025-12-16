# NightFury
# Contributors

## 👥 Team - SHADOWNET

- **Rohit Nandi** – @rohit-nandi  
- **Chiranjit Ghosh** – @cyberchiranjit  
- **Bikram Dey** – @cipherbikramdey
- **Pritam Das** – @pritamdas

NightFury C2 Server

NightFury is a Python-based Command & Control (C2) server designed for educational, research, and defensive cybersecurity testing.
It demonstrates how remote administration, session management, and controlled client interactions work in a lab-only environment.

⚠️ Disclaimer:
This project is strictly for educational purposes, ethical hacking practice, and authorized environments only.
Do NOT deploy or use this tool on systems you do not own or have explicit permission to test.

✨ Features
🔗 Connection & Session Management

Multi-client support with unique client IDs

Displays IP, port, platform, and hostname

Clean attach / detach client sessions

Graceful shutdown & connection cleanup


📂 File Transfer

Upload files (supports custom & nested paths)

Download files from client

Base64 encoding for safe binary transfer

Automatic directory creation

Robust permission & path validation

🖥️ Remote Capabilities

📸 Screenshot capture (PNG, timestamped)

📷 Webcam image capture

🎤 Audio recording (5–60 seconds, WAV)

⌨️ Keylogger start / stop with log retrieval

🧹 Security & Stability

Strong error handling (no freezes)

Path sanitization

Safe failure recovery

Organized downloads per client

💣 Self-Destruct

selfdestruct / delete command

Client deletes its own script and exits cleanly



⚙️ Requirements

Install dependencies using:

pip install -r requirements.txt

colorama

pyfiglet

Pillow

opencv-python

pynput

sounddevice

numpy


🚀 Usage
1️⃣ Start the Server
python3 server.py


You’ll see the NightFury ASCII banner and the main operator prompt:

C2>

2️⃣ Operator Commands
Command	Description
list	List all connected clients
select <id>	Interact with a client
broadcast <cmd>	Send command to all clients
quit / stop	Shutdown server
help	Show help menu
3️⃣ Client Session Commands
Command	Function
upload <local> [remote]	Upload file to client
download <remote>	Download file
screenshot	Capture screen
webcam	Capture webcam image
audio [seconds]	Record audio
keylogger_start [file]	Start keylogger
keylogger_stop	Stop keylogger
selfdestruct / delete	Remove client

📌 Examples
Upload
C2(1)> upload test.txt remote/path/file.txt

Download
C2(1)> download secret.txt

Screenshot
C2(1)> screenshot

Audio Recording
C2(1)> audio 10

Keylogger
C2(1)> keylogger_start mylog.txt
C2(1)> keylogger_stop


📥 Saved Files Location

All client data is stored under:

downloads/<client_ip>_<port>/


Files are timestamped, organized, and collision-safe.

🔐 Security Design

Base64 encoded transfers

Path traversal protection

Permission checks

Clean client exit handling

No sensitive system leakage

Detailed updates & improvements are documented in update.txt 



