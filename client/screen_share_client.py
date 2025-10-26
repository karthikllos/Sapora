"""
Sapora LAN Collaboration Suite - Screen Share Client
Handles screen capture (Presenter) and sending (TCP).
"""
import threading
import socket
import time
import struct
from io import BytesIO
from PIL import Image
import mss
import sys
import os

# Add parent path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.constants import (
    SCREEN_SHARE_PORT, CONNECTION_TIMEOUT, VIDEO_FPS, VIDEO_QUALITY,
    BUFFER_SIZE
)
from shared.protocol import SCREEN_FRAME
from client.utils import pack_message

class ScreenShareClient:
    """Handles Screen Share as Presenter (Sender) via TCP."""

    def __init__(self, server_ip, server_port, status_callback, fps=VIDEO_FPS, quality=VIDEO_QUALITY):
        self.server_ip = server_ip
        self.server_port = server_port
        self.status_callback = status_callback
        self.fps = fps
        self.quality = quality
        
        self.running = False
        self.send_sock = None
        self.presenter_thread = None

    # --- Presenter (Sender) Logic ---

    def start_streaming(self):
        """Connects to server and starts the screen capture/send loop."""
        if self.running:
            return True
            
        try:
            self.send_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.send_sock.settimeout(CONNECTION_TIMEOUT)
            self.send_sock.connect((self.server_ip, self.server_port))
            
            self.running = True
            self.presenter_thread = threading.Thread(target=self._send_loop, daemon=True)
            self.presenter_thread.start()
            return True

        except Exception as e:
            self.status_callback(f"❌ Screen share connection error: {str(e)}")
            self.stop_streaming()
            return False

    def _send_loop(self):
        """Continuously captures, compresses, and sends screen frames via TCP."""
        frame_interval = 1.0 / self.fps
        
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1] # Primary monitor
                
                while self.running:
                    start_time = time.time()
                    
                    # 1. Capture screen
                    screenshot = sct.grab(monitor)
                    img = Image.frombytes('RGB', screenshot.size, screenshot.rgb)
                    
                    # 2. Compress to JPEG
                    buffer = BytesIO()
                    img.save(buffer, format='JPEG', quality=self.quality, optimize=True)
                    jpeg_bytes = buffer.getvalue()
                    
                    # 3. Pack and send (TCP)
                    packet = pack_message(SCREEN_FRAME, jpeg_bytes)
                    
                    # Send packet size (4 bytes)
                    size_bytes = struct.pack('!I', len(packet))
                    self.send_sock.sendall(size_bytes)
                    
                    # Send packet data
                    self.send_sock.sendall(packet)
                    
                    # 4. Control frame rate
                    elapsed = time.time() - start_time
                    sleep_time = max(0, frame_interval - elapsed)
                    time.sleep(sleep_time)

        except Exception as e:
            if self.running:
                self.status_callback(f"❌ Screen share streaming error: {str(e)}")
        finally:
            self.stop_streaming()

    # --- Cleanup ---

    def stop_streaming(self):
        """Cleans up resources and stops threads."""
        self.running = False
        if self.send_sock:
            try:
                self.send_sock.close()
            except:
                pass
            self.send_sock = None