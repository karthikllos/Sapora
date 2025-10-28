# Quick Testing Guide - Sapora Fixed Version

## Setup Instructions

### On Server Computer (Your Computer):
1. Open a terminal/command prompt
2. Navigate to the Sapora directory
3. Activate the virtual environment:
   ```bash
   env\Scripts\activate
   ```
4. Start the server:
   ```bash
   python server/server_main.py
   ```
5. Wait for the message: "✅ All Sapora Server services started successfully!"

### On Client Computers (Your Computer + Friend's Computer):

#### Your Computer (also running server):
1. Open a **second** terminal/command prompt
2. Navigate to the Sapora directory
3. Activate the virtual environment:
   ```bash
   env\Scripts\activate
   ```
4. Start the client:
   ```bash
   python client/main_ui.py
   ```
5. In the connection dialog:
   - Server IP: `127.0.0.1` (localhost)
   - Username: Your name
   - Meeting ID: `test-room`
   - Click "Connect"

#### Friend's Computer:
1. Open terminal/command prompt
2. Navigate to the Sapora directory
3. Activate the virtual environment
4. Start the client:
   ```bash
   python client/main_ui.py
   ```
5. In the connection dialog:
   - Server IP: `<YOUR_LOCAL_IP>` (e.g., 192.168.1.100)
   - Username: Friend's name
   - Meeting ID: `test-room` (must match!)
   - Click "Connect"

**To find YOUR_LOCAL_IP:**
- Windows: `ipconfig` (look for IPv4 Address)
- Mac/Linux: `ifconfig` or `ip addr`

---

## Test Checklist

### ✅ Test 1: Chat Messages
1. Type a message in the chat box on Computer A
2. Press Send
3. **Expected:** Message appears on Computer B
4. Type a message on Computer B
5. **Expected:** Message appears on Computer A

**Status:** _________

---

### ✅ Test 2: File Sharing
1. On Computer A: Click "Send File" button
2. Select a small file (< 10MB)
3. Upload the file
4. **Expected:** 
   - Computer A shows "✅ Uploaded [filename] successfully"
   - Computer B receives notification about available file
   - Computer B can click to download the file

**Status:** _________

---

### ✅ Test 3: Audio Streaming
1. On both computers: Click "Start Audio" button
2. Speak into microphone on Computer A
3. **Expected:** Computer B hears the audio (with slight delay)
4. Speak into microphone on Computer B
5. **Expected:** Computer A hears the audio
6. **Note:** You should NOT hear your own voice (echo cancellation)

**Status:** _________

---

### ✅ Test 4: Video Streaming
1. On both computers: Click "Start Video" button
2. **Expected on Computer A:** 
   - Your own video appears in the "My Video" panel
   - Friend's video appears in the main remote video area
3. **Expected on Computer B:**
   - Your own video appears in the "My Video" panel
   - Computer A's video appears in the main remote video area
4. Wave your hand in front of the camera
5. **Expected:** Other person sees the movement (with slight delay)

**Status:** _________

---

## Troubleshooting

### "Connection refused" or "Cannot connect"
- Ensure the server is running first
- Check firewall settings (Windows Firewall may block Python)
- Verify the IP address is correct
- Make sure both computers are on the same network

### "Chat messages not appearing"
- Verify both clients are in the same Meeting ID (case-sensitive)
- Check the server terminal for error messages
- Try reconnecting both clients

### "No audio" or "Audio crackling"
- Check microphone permissions
- Try closing other applications using the microphone
- Verify PyAudio is installed: `pip install pyaudio`
- On Windows, you may need to install PyAudio from a wheel file

### "Video not showing"
- Check camera permissions
- Close other applications using the camera (Zoom, Teams, etc.)
- Verify OpenCV is installed: `pip install opencv-python`
- Try unplugging/replugging USB cameras

### "File upload fails"
- Check file size (max 100MB)
- Ensure `sapora_files/` folder exists and is writable
- Check disk space

---

## Performance Tips

1. **For better video quality:** Reduce number of participants or close other bandwidth-heavy apps
2. **For better audio:** Use headphones to prevent echo
3. **For faster file transfers:** Use wired ethernet instead of WiFi if possible
4. **Network requirements:** At least 1-2 Mbps upload/download for smooth operation

---

## Expected Behavior Summary

| Feature | Working? | Notes |
|---------|----------|-------|
| Chat to all users | ✅ | Messages relay instantly |
| Private chat | ✅ | Select user from dropdown |
| File upload | ✅ | Max 100MB |
| File download notification | ✅ | Auto-appears for recipients |
| Audio streaming | ✅ | ~100-200ms latency |
| Audio mixing | ✅ | Hears others but not self |
| Video streaming | ✅ | ~200-500ms latency |
| Video display | ✅ | Shows remote participant |
| Room isolation | ✅ | Only users in same meeting ID |

---

## Success Criteria

All four issues should now be resolved:
- ✅ Chat messages reach all clients in the same room
- ✅ File sharing announcements propagate to other clients
- ✅ Audio streaming works bidirectionally
- ✅ Video frames are visible to remote participants

If any test fails, check the server terminal output for error messages and include them when asking for help.

