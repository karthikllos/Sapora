# Sapora LAN Collaboration Suite

Sapora is an all-in-one, cross-platform collaboration application designed to facilitate Zoom-like video conferencing, chat, and file sharing over a local area network (LAN). It operates entirely offline, making it ideal for closed network environments.

## 🔧 Technology Stack

- **Server:** Python (Threaded Sockets, TCP/UDP)
- **Client GUI:** Python + PyQt5 (Minimal Light Theme)
- **Video:** OpenCV (for capture/processing) + UDP (for streaming)
- **Audio:** PyAudio (for capture/mixing) + UDP (for streaming)
- **Screen Share:** `mss` (for capture) + TCP (for reliable streaming)

## 🚀 Setup & Installation

### 1. Requirements

You must have **Python 3.8+** installed. Additionally, you will need system libraries for OpenCV and PyAudio.

| OS | Dependency Notes |
|---|---|
| **Windows** | Ensure you have the Microsoft Visual C++ Redistributable. PyAudio usually installs via `pip`. |
| **Linux (Ubuntu/Debian)**| `sudo apt install python3-dev portaudio19-dev` |
| **macOS** | `brew install portaudio` |

### 2. Python Dependencies

Install the required Python packages using the provided `requirements.txt`:

```bash
pip install -r requirements.txt