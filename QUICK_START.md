# Sapora LAN Collaboration Suite - Quick Start Guide

## 🚀 Getting Started

### Prerequisites
Ensure all dependencies are installed:
```bash
pip install -r requirements.txt
```

Required packages:
- PyQt5 >= 5.15.9
- opencv-python >= 4.9.0.80
- numpy >= 1.26.0
- pyaudio >= 0.2.14
- mss >= 9.0.1

---

## 📡 Starting the Server

### Option 1: Basic Server Start
```bash
python server/server_main.py
```

### What You'll See:
```
======================================================================
🌐 SAPORA LAN COLLABORATION SERVER - STARTING ALL SERVICES
======================================================================
⏰ Server started at: 2025-01-27 10:00:00

✓ Control/Chat        → Port  5000 [RUNNING]
✓ File Transfer       → Port  5002 [RUNNING]
✓ Screen Share        → Port  5003 [RUNNING]
✓ UDP Video           → Port  6000 [RUNNING]
✓ UDP Audio           → Port  6001 [RUNNING]

======================================================================
🚀 ALL SERVICES ACTIVE
======================================================================
📊 Active clients: 0 | Monitoring connections...
Press Ctrl+C to stop the server
```

**Server Ports:**
- **TCP 5000**: Control & Chat
- **TCP 5002**: File Transfer
- **TCP 5003**: Screen Sharing
- **UDP 6000**: Video Streaming
- **UDP 6001**: Audio Streaming

---

## 💻 Starting the Client

### Option 1: Launch with GUI Dialog
```bash
python client/launcher.py
```
- Shows modern splash screen
- Prompts for server IP
- Auto-detects local network

### Option 2: Connect to Localhost
```bash
python client/launcher.py --localhost
```

### Option 3: Connect to Specific Server
```bash
python client/launcher.py --server 192.168.1.100
```

### Option 4: Skip Splash Screen
```bash
python client/launcher.py --localhost --no-splash
```

---

## 🎯 Basic Workflow

### 1. Start Server (Machine A)
```bash
cd C:\Users\SUSHANTH\OneDrive\Desktop\CN_PROJECT\sapora\Sapora
python server/server_main.py
```

### 2. Start First Client (Machine A or B)
```bash
python client/launcher.py --server 192.168.1.100
```
- Enter your username when prompted
- Client connects to server
- You'll see "✓ Connected to Control Server as YourName"

### 3. Start Second Client (Machine B or C)
```bash
python client/launcher.py --server 192.168.1.100
```
- Enter a different username
- Both clients will see each other in the user list

### 4. Use Features

**Chat:**
- Type message in chat input box
- Press Enter or click ➤ button
- All connected clients receive the message

**File Transfer:**
- Click "📎 Send File" button
- Select file to upload
- File appears in server's `sapora_files/` directory
- Other clients can download from server

**Video Streaming:**
- Click 📹 Camera button to start/stop video
- Your webcam feed is sent to server
- Server broadcasts to all other clients
- Video appears in participant tiles

**Audio Streaming:**
- Click 🎤 Microphone button to start/stop audio
- Your microphone audio is sent to server
- Server mixes and broadcasts to all clients

**Screen Sharing:**
- Click 🖥️ Share Screen button
- Your screen is captured and streamed
- Other clients see your screen in real-time

---

## 🔧 Troubleshooting

### Issue: "Cannot connect to server"
**Solution:**
1. Verify server is running: `netstat -an | findstr "5000"`
2. Check firewall allows connections on ports 5000-5003, 6000-6001
3. Verify IP address is correct
4. Try localhost first: `--localhost`

### Issue: "Webcam not found"
**Solution:**
1. Check camera is not used by another application
2. Verify OpenCV can access camera:
   ```python
   import cv2
   cap = cv2.VideoCapture(0)
   print(cap.isOpened())  # Should be True
   ```
3. Try closing Teams/Zoom/Skype if running

### Issue: "No audio detected"
**Solution:**
1. Check microphone permissions in Windows Settings
2. Verify PyAudio can access microphone:
   ```python
   import pyaudio
   p = pyaudio.PyAudio()
   print(p.get_default_input_device_info())
   ```
3. Select correct audio device in Windows Sound Settings

### Issue: "Module not found" errors
**Solution:**
```bash
# Reinstall all dependencies
pip install --upgrade -r requirements.txt

# Or install individually:
pip install PyQt5 opencv-python numpy pyaudio mss
```

### Issue: "Server shows 'Unknown' username"
**Solution:**
- This is normal for 1-2 seconds during connection
- Username updates after TCP registration completes
- If it stays "Unknown", check client console for errors

---

## 📊 Monitoring

### Server Status
Server automatically reports:
- Connected clients every 5 seconds
- Registration events
- File transfer progress
- Disconnections

### Client Status
Client shows in chat panel:
- "✓ Connected to Control Server as [Username]"
- "✓ Streaming video..."
- "📤 Uploading [filename]..."
- "✗ Failed to..." for errors

---

## 🛑 Stopping Services

### Stop Server
- Press `Ctrl+C` in server terminal
- Server gracefully disconnects all clients
- All sockets are closed cleanly

### Stop Client
- Click X button on window
- Or press `Ctrl+C` in terminal
- Client sends disconnect signal to server
- Webcam/microphone released automatically

---

## 🧪 Testing

### Test 1: Local Loopback
```bash
# Terminal 1: Start server
python server/server_main.py

# Terminal 2: Start client 1
python client/launcher.py --localhost
# Enter username: Alice

# Terminal 3: Start client 2
python client/launcher.py --localhost
# Enter username: Bob

# Verify:
# - Both clients appear in each other's user list
# - Chat messages work between Alice and Bob
# - File transfers complete successfully
```

### Test 2: LAN Network
```bash
# Machine 1 (Server):
python server/server_main.py
# Note the server's IP: 192.168.1.100

# Machine 2 (Client):
python client/launcher.py --server 192.168.1.100

# Verify:
# - Client connects successfully
# - Video/audio streams work across network
# - File transfers work across network
```

---

## 🎨 Features Overview

| Feature | Status | Shortcut | Port |
|---------|--------|----------|------|
| Text Chat | ✅ Working | Enter | TCP 5000 |
| User List | ✅ Working | Auto | TCP 5000 |
| File Upload | ✅ Working | 📎 Button | TCP 5002 |
| File Download | ✅ Working | Download | TCP 5002 |
| Video Streaming | ✅ Working | 📹 Button | UDP 6000 |
| Audio Streaming | ✅ Working | 🎤 Button | UDP 6001 |
| Screen Sharing | ✅ Working | 🖥️ Button | TCP 5003 |
| Heartbeat | ✅ Working | Auto (3s) | TCP 5000 |

---

## 📝 Configuration

### Change Server Ports
Edit `shared/constants.py`:
```python
CONTROL_PORT = 5000       # Control & Chat
FILE_TRANSFER_PORT = 5002 # File Transfer
SCREEN_SHARE_PORT = 5003  # Screen Sharing
VIDEO_PORT = 6000         # UDP Video
AUDIO_PORT = 6001         # UDP Audio
```

### Change Video Settings
Edit `shared/constants.py`:
```python
VIDEO_WIDTH = 640
VIDEO_HEIGHT = 480
VIDEO_FPS = 15
VIDEO_QUALITY = 55  # JPEG quality 0-100
```

### Change Audio Settings
Edit `shared/constants.py`:
```python
AUDIO_RATE = 44100      # Sample rate
AUDIO_CHANNELS = 1      # Mono
AUDIO_CHUNK = 1024      # Buffer size
```

---

## 🔐 Security Notes

**⚠️ Important:**
- Sapora is designed for **trusted LAN environments only**
- No encryption is implemented (data sent in plaintext)
- No authentication beyond username
- Not suitable for internet/WAN deployment
- Use on private networks only

**For Production:**
Consider adding:
- TLS/SSL encryption for TCP
- DTLS for UDP streams
- User authentication (passwords/tokens)
- Rate limiting
- Input validation on server

---

## 📚 Architecture

```
Client                    Server                   Client
  |                          |                        |
  |---[REGISTER username]--->|                        |
  |<--[USER_LIST all users]--|                        |
  |                          |<--[REGISTER username]--|
  |<--[USER_LIST updated]----|---[USER_LIST]-------->|
  |                          |                        |
  |---[MSG_CHAT "Hello"]---->|                        |
  |                          |---[MSG_CHAT]---------->|
  |                          |                        |
  |---[FILE_UPLOAD data]---->|                        |
  |<--[FILE_ACK_SUCCESS]-----|                        |
  |                          |                        |
  |---[STREAM_VIDEO frame]-->|                        |
  |                          |---[STREAM_VIDEO]------>|
  |<--[STREAM_VIDEO frame]---|<--[STREAM_VIDEO]------|
```

---

## ✅ Success Indicators

**Server Running Successfully:**
```
✓ Control/Chat        → Port  5000 [RUNNING]
✓ File Transfer       → Port  5002 [RUNNING]
✓ Screen Share        → Port  5003 [RUNNING]
✓ UDP Video           → Port  6000 [RUNNING]
✓ UDP Audio           → Port  6001 [RUNNING]
🚀 ALL SERVICES ACTIVE
```

**Client Connected Successfully:**
```
[SaporaGUI] Successfully connected as YourName
✓ Connected to Control Server as YourName.
[SaporaGUI] All clients initialized successfully
```

**Successful File Transfer:**
```
📤 Uploading document.pdf (2.3 MB)...
✅ Upload successful: document.pdf
```

---

## 🆘 Support

**Common Issues:**
1. Port already in use → Change ports in `shared/constants.py`
2. Firewall blocking → Allow Python through Windows Firewall
3. Import errors → Reinstall dependencies: `pip install -r requirements.txt`
4. Camera/mic issues → Check Windows permissions

**Debug Mode:**
- Check console output for detailed logs
- Server shows all client connections/disconnections
- Client shows connection status and errors

---

## 🎓 Next Steps

1. **Test locally** with `--localhost`
2. **Test on LAN** with actual IP addresses
3. **Test multiple clients** (3-5 clients)
4. **Test file transfers** (upload/download)
5. **Test video/audio** (check FPS and quality)

**Enjoy collaborating with Sapora! 🎉**
