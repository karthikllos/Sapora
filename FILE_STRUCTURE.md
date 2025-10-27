# Sapora LAN Collaboration Suite - File Structure

## 📁 Project Organization

```
Sapora/
├── server/                          # Server-side components
│   ├── server_main.py              # Main server entry point (START HERE)
│   ├── connection_manager.py       # Manages all client connections
│   ├── tcp_handler.py              # Handles TCP control/chat connections
│   ├── file_server.py              # File upload/download handler
│   ├── udp_video_server.py         # UDP video broadcast server
│   ├── udp_audio_server.py         # UDP audio mixing server
│   ├── screen_share_server.py      # Screen sharing TCP server
│   └── utils.py                    # Server utility functions
│
├── client/                          # Client-side components
│   ├── launcher.py                 # 🚀 CLIENT ENTRY POINT (USE THIS)
│   ├── main_ui.py                  # Main GUI window (SaporaGUI class)
│   ├── chat_client.py              # TCP control & chat client
│   ├── file_client.py              # File transfer client
│   ├── video_client.py             # UDP video streaming client
│   ├── audio_client.py             # UDP audio streaming client
│   ├── screen_share_client.py      # Screen sharing client
│   └── utils.py                    # Client utility functions
│
├── shared/                          # Shared modules (used by both)
│   ├── constants.py                # Configuration constants (ports, buffers, etc.)
│   ├── protocol.py                 # Message type definitions
│   └── helpers.py                  # Protocol serialization functions
│
├── test_udp_video_sender.py        # Standalone UDP video sender test
├── test_udp_video_receiver.py      # Standalone UDP video receiver test
├── test_udp_video_receiver_optimized.py  # Optimized receiver with threading
├── test_udp_video_server.py        # Standalone UDP video server test
│
├── requirements.txt                 # Python dependencies
├── QUICK_START.md                  # User guide (HOW TO RUN)
├── COMPATIBILITY_REPORT.md         # Technical QA analysis
├── CHANGES_SUMMARY.md              # Recent changes documentation
└── FILE_STRUCTURE.md               # This file
```

---

## 🎯 Entry Points

### Server
```bash
python server/server_main.py
```
- Starts all services (Control, File, Video, Audio, Screen)
- Listens on ports 5000, 5002, 5003, 6000, 6001

### Client (RECOMMENDED)
```bash
python client/launcher.py
```
- Modern launcher with splash screen
- Configuration dialog for server IP
- Command-line arguments supported
- Best user experience

### Client (Alternative - Direct)
If you want to skip the launcher for debugging:
```python
from client.main_ui import SaporaGUI
from PyQt5.QtWidgets import QApplication
app = QApplication([])
window = SaporaGUI(server_ip="127.0.0.1")
window.show()
app.exec_()
```

---

## 📝 File Purposes

### Server Files

| File | Purpose | Lines | Complexity |
|------|---------|-------|------------|
| `server_main.py` | Orchestrates all services, handles startup/shutdown | ~150 | Low |
| `connection_manager.py` | Tracks all clients, manages heartbeats | ~200 | Medium |
| `tcp_handler.py` | Handles individual TCP connections (chat/control) | ~155 | Medium |
| `file_server.py` | Manages file uploads/downloads with checksums | ~250 | High |
| `udp_video_server.py` | Receives and broadcasts UDP video frames | ~90 | Low |
| `udp_audio_server.py` | Receives, mixes, broadcasts audio | ~120 | Medium |
| `screen_share_server.py` | Handles screen sharing streams | ~150 | Medium |
| `utils.py` | Protocol helpers (imports from shared/helpers.py) | ~160 | Low |

### Client Files

| File | Purpose | Lines | Complexity |
|------|---------|-------|------------|
| `launcher.py` | 🚀 **Primary entry point**, splash screen, config | ~530 | Medium |
| `main_ui.py` | Main GUI window, all UI components | ~800+ | High |
| `chat_client.py` | TCP control connection, chat messaging | ~147 | Medium |
| `file_client.py` | File upload/download with progress | ~250 | Medium |
| `video_client.py` | Webcam capture, UDP video send/receive | ~180 | Medium |
| `audio_client.py` | Microphone capture, UDP audio send/receive | ~150 | Medium |
| `screen_share_client.py` | Screen capture and streaming | ~180 | Medium |
| `utils.py` | Client utilities (imports from shared/helpers.py) | ~130 | Low |

### Shared Files

| File | Purpose | Lines | Complexity |
|------|---------|-------|------------|
| `constants.py` | All configuration values (ports, buffers, FPS, etc.) | ~52 | Low |
| `protocol.py` | Message type constants (0x01-0x41) | ~62 | Low |
| `helpers.py` | pack_message/unpack_message, file metadata | ~103 | Medium |

---

## 🔄 Data Flow

### Client Connection Flow
```
launcher.py
    └─> Creates QApplication
    └─> Shows splash screen
    └─> Imports main_ui.SaporaGUI
    └─> Creates SaporaGUI(server_ip)
        └─> Initializes all client modules:
            ├─> chat_client.py (TCP control)
            ├─> file_client.py (TCP file transfer)
            ├─> video_client.py (UDP video)
            ├─> audio_client.py (UDP audio)
            └─> screen_share_client.py (TCP screen)
```

### Server Startup Flow
```
server_main.py
    └─> Creates UnifiedServer
    └─> Creates ConnectionManager
    └─> Starts all services:
        ├─> ControlServer (tcp_handler.py) on port 5000
        ├─> FileTransferServer (file_server.py) on port 5002
        ├─> ScreenShareServer (screen_share_server.py) on port 5003
        ├─> UDPVideoServer (udp_video_server.py) on port 6000
        └─> UDPAudioServer (udp_audio_server.py) on port 6001
```

---

## 🗑️ Removed Files

### client_main.py (DELETED - Redundant)
**Reason:** Superseded by `launcher.py`

**What it did:**
- Basic command-line argument parsing (`--server`)
- Simple theme application
- Direct SaporaGUI instantiation
- Basic error handling

**Why launcher.py is better:**
- ✅ Modern splash screen with loading animation
- ✅ GUI configuration dialog
- ✅ Auto-detect LAN server
- ✅ Better error messages
- ✅ More command-line options (`--localhost`, `--no-splash`)
- ✅ Professional UX

**Migration:** If you were using `client_main.py`, just use `launcher.py` instead:

**Old way:**
```bash
python client/client_main.py --server 192.168.1.100
```

**New way (identical functionality):**
```bash
python client/launcher.py --server 192.168.1.100
```

---

## 🧩 Module Dependencies

### Server Dependencies
```
server_main.py
    ├─> connection_manager.py
    ├─> tcp_handler.py
    │   └─> utils.py → shared/helpers.py
    ├─> file_server.py
    │   └─> utils.py → shared/helpers.py
    ├─> udp_video_server.py
    ├─> udp_audio_server.py
    └─> screen_share_server.py
```

### Client Dependencies
```
launcher.py
    └─> main_ui.py (SaporaGUI)
        ├─> chat_client.py
        │   └─> utils.py → shared/helpers.py
        ├─> file_client.py
        │   └─> utils.py → shared/helpers.py
        ├─> video_client.py
        │   └─> utils.py → shared/helpers.py
        ├─> audio_client.py
        │   └─> utils.py → shared/helpers.py
        └─> screen_share_client.py
            └─> utils.py → shared/helpers.py
```

### Shared Module (No Dependencies)
```
shared/
    ├─> constants.py (standalone)
    ├─> protocol.py (standalone)
    └─> helpers.py (imports constants.py only)
```

---

## 🎨 UI Component Structure

### Main Window (main_ui.py)
```
SaporaGUI (QMainWindow)
    ├─> Left Panel: Video Grid
    │   └─> VideoTile (QFrame) for each participant
    │       ├─> Video label (QLabel)
    │       └─> Name overlay
    │
    ├─> Bottom: Control Bar
    │   ├─> Meeting timer
    │   ├─> Participant count
    │   ├─> 🎤 Mic button
    │   ├─> 📹 Camera button
    │   ├─> 🖥️ Screen share button
    │   ├─> 💬 Chat toggle
    │   └─> Leave button
    │
    └─> Right Panel: Chat
        ├─> Chat header
        ├─> Message scroll area
        │   └─> ChatMessageWidget for each message
        └─> Input area
            ├─> Text input
            ├─> Send button
            └─> 📎 File button
```

---

## 🔧 Configuration Files

### constants.py
**Categories:**
- Server Configuration (IPs, storage directory)
- Service Ports (TCP 5000-5003, UDP 6000-6001)
- Protocol & Buffer Sizes (10-byte header, 64KB buffers)
- File Transfer Limits (32KB chunks, 100MB max)
- Streaming Settings (Video: 640x480@15fps, Audio: 44.1kHz mono)
- Timeouts and Retries (5s connection, 1s socket, 3s heartbeat, 15s idle)

### protocol.py
**Message Categories:**
- Control & Handshake: 0x01-0x06
- Chat: 0x10
- File Transfer: 0x20-0x25
- Screen Share: 0x30-0x32
- Streaming (UDP): 0x40-0x41

---

## 📦 External Dependencies

### Required Packages (requirements.txt)
```
PyQt5>=5.15.9              # GUI framework
opencv-python>=4.9.0.80    # Video capture/processing
numpy>=1.26.0              # Array operations
pyaudio>=0.2.14            # Audio capture
mss>=9.0.1                 # Screen capture
ffmpeg-python>=0.2.0       # Video encoding (future)
tqdm>=4.66.1               # Progress bars
```

### Standard Library Usage
- `socket` - All network communication
- `threading` - Concurrent connections
- `struct` - Binary protocol packing
- `json` - Metadata serialization
- `hashlib` - File checksums (MD5)
- `pathlib` - File path operations
- `time`, `datetime` - Timestamps
- `signal` - Graceful shutdown

---

## 🧪 Test Files

### UDP Video Tests (Standalone)
These can run independently without the full server/client:

1. **test_udp_video_server.py**
   - Minimal UDP server for testing
   - Receives frames, broadcasts to clients
   - No connection manager needed

2. **test_udp_video_sender.py**
   - Captures webcam
   - Sends JPEG frames via UDP
   - Shows local preview

3. **test_udp_video_receiver.py**
   - Receives UDP video frames
   - Decodes and displays
   - Basic version

4. **test_udp_video_receiver_optimized.py**
   - Threaded architecture
   - Non-blocking sockets
   - Queue-based frame handling
   - 15-20 FPS smooth playback

**Usage:**
```bash
# Terminal 1
python test_udp_video_server.py

# Terminal 2
python test_udp_video_sender.py

# Terminal 3
python test_udp_video_receiver_optimized.py
```

---

## 📊 Code Statistics

### Total Lines of Code (Approximate)
- **Server:** ~1,200 lines
- **Client:** ~2,500 lines (including main_ui.py)
- **Shared:** ~220 lines
- **Tests:** ~800 lines
- **Total:** ~4,720 lines

### File Count
- **Server modules:** 8 files
- **Client modules:** 8 files
- **Shared modules:** 3 files
- **Test files:** 4 files
- **Documentation:** 4 files
- **Total:** 27 files

---

## 🎓 Best Practices Used

1. **Separation of Concerns**
   - Server/Client/Shared clearly separated
   - Each module has single responsibility

2. **Import Management**
   - All modules add project root to sys.path
   - Centralized protocol/constants in shared/

3. **Error Handling**
   - Try/except blocks on all network operations
   - Graceful degradation for missing hardware

4. **Thread Safety**
   - All threads use daemon=True
   - Locks on shared data structures
   - Clean shutdown handlers

5. **User Experience**
   - Professional splash screen
   - Clear error messages
   - Progress indicators
   - Status feedback

---

## 🚀 Quick Reference

### Start Server
```bash
python server/server_main.py
```

### Start Client (Production)
```bash
python client/launcher.py --server 192.168.1.100
```

### Start Client (Local Testing)
```bash
python client/launcher.py --localhost
```

### Start Client (Skip Splash)
```bash
python client/launcher.py --localhost --no-splash
```

---

**Last Updated:** 2025-01-27  
**Version:** 2.0  
**Status:** Production Ready ✅
