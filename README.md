# 🎥 Sapora - LAN Video Conferencing Suite

**Modern Electron + Python Hybrid Application for Real-Time Collaboration**

Sapora is a powerful LAN-based video conferencing solution that combines a sleek Electron/React frontend with a robust Python networking backend. Think Zoom, but designed for secure local area networks.

---

## ✨ Features

### Core Capabilities
- **🎤 Audio Conferencing**: Real-time audio streaming with automatic mixing
- **📹 Video Conferencing**: Multi-user video streams with dynamic grid layout
- **💬 Chat**: Built-in text messaging system
- **📁 File Transfer**: Upload/download files during meetings
- **🖥️ Screen Sharing**: Share your screen with participants
- **👥 User Management**: Real-time participant list

### Technical Highlights
- **Hybrid Architecture**: Python backend + Electron frontend
- **WebSocket Communication**: Socket.IO for real-time events
- **UDP/TCP Protocols**: UDP for A/V streaming, TCP for control/files
- **Cross-Platform**: Works on Windows, macOS, and Linux
- **Zoom-Like UI**: Modern, intuitive interface

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Electron Frontend                         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  React UI (Zoom-like)                                 │   │
│  │  - Video Grid                                         │   │
│  │  - Chat Panel                                         │   │
│  │  - Control Bar                                        │   │
│  └──────────────────────────────────────────────────────┘   │
│                         │                                     │
│                         │ WebSocket (Socket.IO)               │
│                         ↓                                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Python Client Backend (client_main.py)              │   │
│  │  - Audio Client                                      │   │
│  │  - Video Client                                      │   │
│  │  - Chat Client                                       │   │
│  │  - File Client                                       │   │
│  │  - Screen Share Client                               │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ UDP/TCP Sockets
                         ↓
┌─────────────────────────────────────────────────────────────┐
│                    Python Server Backend                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Server Orchestrator (server_main.py)                │   │
│  │  - Connection Manager                                │   │
│  │  - UDP Audio Server (Port 6001)                      │   │
│  │  - UDP Video Server (Port 6000)                      │   │
│  │  - TCP Control Server (Port 5000)                    │   │
│  │  - File Transfer Server (Port 5002)                  │   │
│  │  - Screen Share Server (Port 5003)                   │   │
│  │  - WebSocket Gateway (Port 5555)                     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Getting Started

### Prerequisites

**Python 3.10+** (Python 3.11+ recommended)
```bash
python --version
```

**Node.js 18+** (Latest LTS recommended)
```bash
node --version
npm --version
```

**System Dependencies**:
- **Windows**: Visual Studio Build Tools (for PyAudio)
- **macOS**: PortAudio (`brew install portaudio`)
- **Linux**: PortAudio dev package (`sudo apt-get install portaudio19-dev`)

---

### Installation

#### 1. Clone the Repository
```bash
git clone <your-repo-url>
cd Sapora
```

#### 2. Install Python Dependencies
```bash
pip install -r requirements.txt
```

**Note**: If PyAudio fails to install:
- **Windows**: Download pre-built wheel from [here](https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio)
- **macOS**: `brew install portaudio && pip install pyaudio`
- **Linux**: `sudo apt-get install portaudio19-dev python3-pyaudio`

#### 3. Install Node.js Dependencies
```bash
cd sapora_electron
npm install
```

---

## 🎬 Running the Application

### Step 1: Start the Server
Open a terminal and run:
```bash
cd server
python server_main.py
```

You should see:
```
============================================================
🚀 Starting Sapora Server - LAN Collaboration Suite
============================================================

📡 Starting TCP Control Server...
🎤 Starting UDP Audio Server...
📹 Starting UDP Video Server...
📁 Starting File Transfer Server...
🖥️  Starting Screen Share Server...
🌐 Starting WebSocket Gateway for Electron...

============================================================
✅ All Sapora Server services started successfully!
============================================================
```

**Note**: The server will run on `0.0.0.0` to accept connections from any machine on the LAN. Find your LAN IP:
- **Windows**: `ipconfig` → Look for "IPv4 Address"
- **macOS/Linux**: `ifconfig` or `ip addr` → Look for your local IP (192.168.x.x or 10.x.x.x)

### Step 2: Launch the Electron App
Open a new terminal:
```bash
cd sapora_electron
npm start
```

### Step 3: Join the Meeting
1. The Sapora login screen will appear
2. Enter the **Server IP** (use `127.0.0.1` for local testing, or your LAN IP for other machines)
3. Enter your **Name**
4. Click **"Join Meeting"**

### Step 4: Invite Others
Share your server's LAN IP with other participants. They can:
- Run the Electron app on their machines
- Enter your server IP
- Join the same meeting room

---

## 🎮 Usage Guide

### Meeting Controls

#### Bottom Control Bar (Zoom-like)
- **🎤 Microphone**: Click to toggle mute/unmute
- **📹 Video**: Click to start/stop video
- **💬 Chat**: Click to open/close chat panel
- **📞 End Call**: Leave the meeting

### Chat Panel
- Opens on the right side
- Real-time messaging with all participants
- Auto-scrolls to newest messages

### Video Grid
- Automatically adjusts based on number of participants:
  - 1-2 users: Single column
  - 3-4 users: 2x2 grid
  - 5+ users: 3-column grid
- Displays user avatars when video is off
- Shows mute/unmute status

---

## 🔧 Configuration

### Server Ports
Defined in `shared/constants.py`:
```python
CONTROL_PORT = 5000       # TCP: Chat, registration, heartbeat
CHAT_PORT = 5001          # TCP: Chat messages (handled by CONTROL_PORT)
FILE_TRANSFER_PORT = 5002 # TCP: File uploads/downloads
SCREEN_SHARE_PORT = 5003  # TCP: Screen sharing
VIDEO_PORT = 6000         # UDP: Video streaming
AUDIO_PORT = 6001         # UDP: Audio streaming
WEBSOCKET_PORT = 5555     # WebSocket: Electron gateway (server)
CLIENT_WS_PORT = 5556     # WebSocket: Client API (client)
```

### Video Settings
```python
VIDEO_WIDTH = 640
VIDEO_HEIGHT = 480
VIDEO_FPS = 15
VIDEO_QUALITY = 55  # JPEG compression (0-100)
```

### Audio Settings
```python
AUDIO_RATE = 44100      # Sample rate (Hz)
AUDIO_CHANNELS = 1      # Mono
AUDIO_CHUNK = 1024      # Frames per buffer
```

---

## 📂 Project Structure

```
Sapora/
├── server/
│   ├── server_main.py           # 🎯 Unified server orchestrator
│   ├── connection_manager.py    # Client state management
│   ├── tcp_handler.py            # TCP control server
│   ├── udp_audio_server.py       # Audio mixing & broadcast
│   ├── udp_video_server.py       # Video relay
│   ├── file_server.py            # File transfer handler
│   ├── screen_share_server.py    # Screen share relay
│   └── utils.py                  # Server utilities
│
├── client/
│   ├── client_main.py            # 🎯 Unified client backend
│   ├── audio_client.py           # Audio capture/playback
│   ├── video_client.py           # Video capture/display
│   ├── chat_client.py            # Chat communication
│   ├── file_client.py            # File upload/download
│   ├── screen_share_client.py    # Screen capture/view
│   └── utils.py                  # Client utilities
│
├── shared/
│   ├── constants.py              # Global configuration
│   ├── protocol.py               # Message type definitions
│   └── helpers.py                # Serialization helpers
│
├── sapora_electron/              # 🎯 Electron Frontend
│   ├── main.js                   # Electron main process
│   ├── preload.js                # Secure IPC bridge
│   ├── package.json              # Node dependencies
│   └── renderer/
│       ├── index.html            # Main HTML
│       └── app.js                # React application (Zoom-like UI)
│
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

---

## 🐛 Troubleshooting

### "Failed to start Python backend"
- **Check Python path**: Ensure `python` or `python3` is in your PATH
- **Check dependencies**: Run `pip install -r requirements.txt` again
- **Check server IP**: Verify the server is running and accessible

### "Connection timeout" or "Cannot connect"
- **Firewall**: Allow Python through your firewall
- **Network**: Ensure server and client are on the same LAN
- **Port conflicts**: Check if ports 5000-6001 are available

### PyAudio installation fails
- **Windows**: Download wheel from [here](https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio)
- **macOS**: `brew install portaudio`
- **Linux**: `sudo apt-get install portaudio19-dev`

### No audio/video
- **Permissions**: Grant camera/microphone permissions
- **Device busy**: Close other apps using camera/mic
- **Check logs**: Look at terminal output for errors

### Electron app doesn't start
- **Node version**: Ensure Node.js 18+ is installed
- **Dependencies**: Run `npm install` in `sapora_electron/`
- **Clear cache**: Delete `node_modules/` and reinstall

---

## 🔒 Security Notes

⚠️ **LAN Use Only**: Sapora is designed for trusted local networks.
- No built-in encryption (assumes secure LAN environment)
- No authentication/authorization by default
- Not recommended for public internet use without additional security layers

For production/internet use, consider adding:
- SSL/TLS encryption
- User authentication
- End-to-end encryption for media streams

---

## 🛠️ Development

### Running in Development Mode
```bash
# Server with auto-reload
cd server
python server_main.py

# Electron with DevTools
cd sapora_electron
npm run dev
```

### Code Style
- **Python**: Follow PEP 8, use `black` for formatting
- **JavaScript**: Use ESLint + Prettier

### Testing
```bash
# Python tests
pytest tests/

# Node tests
cd sapora_electron
npm test
```

---

## 🌟 Features Roadmap

### Upcoming Features
- [ ] End-to-end encryption
- [ ] Recording functionality
- [ ] Virtual backgrounds
- [ ] Breakout rooms
- [ ] Waiting room
- [ ] Meeting passwords
- [ ] Reaction emojis
- [ ] Whiteboard collaboration
- [ ] Mobile app support

---

## 📝 License

MIT License - See LICENSE file for details

---

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

---

## 💬 Support

For issues, questions, or feature requests:
- Open an issue on GitHub
- Check existing documentation
- Review troubleshooting guide

---

## 🎓 Credits

Built with:
- **Python** - Backend networking & media processing
- **Electron** - Cross-platform desktop framework
- **React** - UI library
- **Socket.IO** - Real-time WebSocket communication
- **OpenCV** - Video processing
- **PyAudio** - Audio processing

---

## 📊 Performance Tips

### For Better Performance:
1. **Use wired connections** instead of Wi-Fi when possible
2. **Close unnecessary applications** to free up system resources
3. **Adjust video quality** in `shared/constants.py` if needed
4. **Limit participants** to 8-10 for smooth performance on typical hardware

### System Requirements:
- **CPU**: Dual-core 2.0 GHz+ (Quad-core recommended)
- **RAM**: 4 GB minimum (8 GB recommended)
- **Network**: 100 Mbps LAN recommended
- **Webcam**: Any USB webcam or built-in camera
- **Microphone**: Any USB/built-in microphone

---

**Made with ❤️ for secure, private LAN collaboration**
