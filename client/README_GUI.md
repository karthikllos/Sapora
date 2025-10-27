# Sapora Video Conference - PyQt6 GUI

Modern Zoom-like desktop interface for the Sapora LAN video conferencing application.

---

## 📋 Prerequisites

Before running the GUI, ensure you have the following Python packages installed:

```bash
pip install PyQt6 opencv-python numpy pyaudio pyautogui
```

### Package Breakdown:
- **PyQt6** - GUI framework
- **opencv-python** (cv2) - Video capture and processing
- **numpy** - Array operations for video frames
- **pyaudio** - Audio capture and playback
- **pyautogui** - Screen capture for screen sharing

---

## 🚀 How to Launch

### 1. Start the Server

First, start the server on the host machine (or locally for testing):

```bash
cd C:\Users\SUSHANTH\OneDrive\Desktop\CN_PROJECT\sapora\Sapora
python server/server_main.py
```

The server will start and listen on all configured ports (video, audio, chat, file transfer, screen share).

### 2. Start the Client GUI

On the same or different machine(s), launch the PyQt6 client:

```bash
cd C:\Users\SUSHANTH\OneDrive\Desktop\CN_PROJECT\sapora\Sapora
python client/main_ui.py
```

### 3. Join the Meeting

A login dialog will appear:

1. **Enter Server IP**: 
   - For local testing: `127.0.0.1`
   - For LAN: Enter the server's local IP (e.g., `192.168.1.100`)
   
2. **Enter Your Name**: Type your username

3. Click **"Join Meeting"**

---

## 🎮 Using the Interface

### Main Controls (Bottom Bar)

#### 🎥 Start Video
- Click to start your webcam feed
- Your video will be sent to the server and broadcast to other clients
- Click again (button changes to "Stop Video") to turn off camera

#### 🎙 Start Audio
- Click to enable microphone and speaker
- Your audio is mixed on the server with other participants
- Click again (button changes to "Mute") to mute your mic

#### 💬 Chat
- Toggle the chat side panel
- Type messages and press Enter or click "Send"
- See the list of connected participants below the chat

#### 📁 Share File
- Opens a file picker dialog
- Select any file to upload to the server
- Progress updates shown in status bar
- Maximum file size: 100 MB

#### 🖥 Share Screen
- Starts broadcasting your screen to other participants
- Confirmation dialog appears before starting
- Runs in background thread

#### 🔚 Leave
- Disconnects from the meeting
- Cleans up all resources (camera, mic, sockets)
- Closes the application

---

## 🎨 UI Features

### Dark Theme
- Modern Zoom-inspired dark color scheme
- Rounded buttons with hover effects
- Smooth transitions and professional styling

### Video Display
- Central video area shows:
  - Your own camera feed when video is enabled
  - Remote participant video feeds when receiving
- Automatically scales to fit the window

### Chat Panel
- Collapsible right-side panel
- Real-time message display with sender names
- Participant list showing all connected users

### Status Indicators
- Top bar shows:
  - Meeting name
  - Your username
  - Connection status (colored dot indicator)
  - Real-time notifications

---

## 🔧 Testing

### Single Machine Test (Localhost)

1. Open 3 terminal windows
2. Terminal 1: Start server
   ```bash
   python server/server_main.py
   ```
3. Terminal 2: Start Client 1
   ```bash
   python client/main_ui.py
   ```
   - Enter `127.0.0.1` and username "Alice"
4. Terminal 3: Start Client 2
   ```bash
   python client/main_ui.py
   ```
   - Enter `127.0.0.1` and username "Bob"

Both clients should see each other in the participant list.

### LAN Test (Multiple Machines)

1. **Server Machine**:
   - Find your local IP: `ipconfig` (Windows) or `ifconfig` (Linux/Mac)
   - Start server: `python server/server_main.py`
   
2. **Client Machines**:
   - Enter server's IP address in login dialog
   - Each user provides unique username
   - All clients connect to the same meeting

---

## 🐛 Troubleshooting

### Camera Not Working
- **Error**: "Camera unavailable. Try closing other video apps."
- **Solution**: Close any apps using the webcam (Zoom, Teams, browser tabs, etc.)
- **Windows Specific**: Check camera privacy settings

### Audio Issues
- **No Sound**: Check system volume and ensure correct audio device selected
- **Echo**: Lower speaker volume or use headphones
- **PyAudio Errors**: Reinstall with `pip install --upgrade pyaudio`

### Connection Failed
- Verify server is running
- Check firewall settings (ports 5000-5003, 6000-6001)
- Ensure correct server IP address
- Try pinging the server: `ping <server_ip>`

### Import Errors
```bash
# If PyQt6 not found:
pip install PyQt6

# If cv2 not found:
pip install opencv-python

# If pyaudio not found:
pip install pyaudio
```

---

## 📁 Project Structure

```
client/
├── main_ui.py          ← Main GUI application (start here!)
├── style.qss           ← Dark theme stylesheet
├── video_client.py     ← Video streaming logic
├── audio_client.py     ← Audio streaming logic
├── chat_client.py      ← Chat & user management
├── file_client.py      ← File transfer operations
├── screen_share_client.py ← Screen sharing
└── utils.py            ← Helper functions
```

---

## 🎯 Key Features Implemented

✅ **Complete GUI Integration** - All networking modules connected to PyQt6 interface  
✅ **Non-Blocking Operations** - QThread workers for video, audio, and file transfers  
✅ **Modern Dark Theme** - Professional Zoom-like styling with hover effects  
✅ **Real-Time Video** - Live webcam feed display with automatic scaling  
✅ **Audio Streaming** - Microphone capture and mixed playback  
✅ **Text Chat** - Real-time messaging with participant list  
✅ **File Sharing** - Upload/download with progress tracking  
✅ **Screen Sharing** - Desktop broadcast capability  
✅ **Clean Disconnection** - Proper resource cleanup on exit  

---

## 🔮 Optional Enhancements (Future)

- Add animated status icons (QMovie)
- Implement toast notifications for events
- Create gallery view for multiple participants
- Add settings dialog for camera/mic selection
- Implement recording functionality
- Add virtual backgrounds
- Create custom icons set

---

## 📞 Support

For issues or questions:
1. Check the troubleshooting section above
2. Review server console logs for errors
3. Verify all dependencies are installed
4. Ensure network connectivity between clients and server

---

## 🎉 Enjoy Your Sapora Meeting!

Launch the app, invite your team, and experience seamless LAN video conferencing! 🚀
