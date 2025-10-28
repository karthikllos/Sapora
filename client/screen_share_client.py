"""
Screen Share Client
Acts as either:
  🎬 Presenter - captures screen and sends frames to server
  👁️ Viewer - receives frames and displays them in real-time

Uses TCP for reliable frame transfer.
"""

import socket
import sys
import os
import struct
import cv2
import numpy as np
import pyautogui
import threading
import time

# --- CRITICAL FIX: Add project root for shared imports ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
# ---------------------------------------------------------

from shared.constants import SCREEN_SHARE_PORT, BUFFER_SIZE
from shared.protocol import SCREEN_SHARE  # keep same constant
# No need for unpack_message here — not used

class ScreenShareClient:
    def __init__(self, server_ip, mode="viewer", frame_callback=None, local_preview_callback=None, status_callback=None):
        self.server_ip = server_ip
        self.mode = mode.lower()
        self.socket = None
        self.running = False
        # Optional callbacks
        self.frame_callback = frame_callback              # for viewer frames
        self.local_preview_callback = local_preview_callback  # for presenter local preview
        self.status_callback = status_callback or (lambda msg: None)

    def connect(self):
        """Connect to the screen share server (non-fatal if fails; allows local preview)."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.server_ip, SCREEN_SHARE_PORT))
            self.status_callback(f"✅ ScreenShare connected {self.server_ip}:{SCREEN_SHARE_PORT}")
            return True
        except Exception as e:
            # Keep running for local preview, but note we won't send frames
            self.socket = None
            self.status_callback(f"⚠️ ScreenShare connect failed (preview only): {e}")
            return False

    def start(self):
        """Start as presenter or viewer"""
        self.connect()  # Try to connect, but continue even if it fails for local preview
        
        self.running = True

        if self.mode == "presenter":
            self.status_callback("🎬 Presenter Mode: sharing your screen...")
            self._start_presenter()
        else:
            self.status_callback("👁️ Viewer Mode: watching screen share...")
            self._start_viewer()

    def _start_presenter(self):
        """Capture and send screen frames to the server"""
        try:
            while self.running:
                # Capture screen using pyautogui
                screenshot = pyautogui.screenshot()
                frame = np.array(screenshot)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # Resize for efficiency
                frame = cv2.resize(frame, (960, 540))

                # Local preview callback before encoding
                try:
                    if self.local_preview_callback:
                        self.local_preview_callback(frame)
                except Exception:
                    pass

                # Encode as JPEG
                ret, encoded_frame = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if not ret:
                    continue

                frame_data = encoded_frame.tobytes()
                frame_size = len(frame_data)

                # Send size + data if connected; otherwise skip (local preview only)
                if self.socket:
                    self.socket.sendall(struct.pack('!I', frame_size) + frame_data)

                # Control frame rate
                time.sleep(0.1)

        except Exception as e:
            self.status_callback(f"⚠️ Presenter error: {e}")
        finally:
            try:
                self.socket.close()
            except Exception:
                pass
            self.status_callback("🛑 Presenter stopped")

    def _start_viewer(self):
        """Receive and display frames from the server"""
        try:
            while self.running:
                # Read 4-byte size header
                size_data = self._recv_exact(4)
                if not size_data:
                    break
                frame_size = struct.unpack('!I', size_data)[0]

                # Read frame data
                frame_data = self._recv_exact(frame_size)
                if not frame_data:
                    break

                # Decode JPEG to image
                np_frame = np.frombuffer(frame_data, dtype=np.uint8)
                frame = cv2.imdecode(np_frame, cv2.IMREAD_COLOR)
                if frame is None:
                    continue

                # If a callback exists, pass frame (in BGR) to it; else fallback to cv2 window
                if self.frame_callback:
                    try:
                        self.frame_callback(frame)
                    except Exception:
                        pass
                else:
                    cv2.imshow("🖥️ Screen Share - Viewer", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

        except Exception as e:
            self.status_callback(f"⚠️ Viewer error: {e}")
        finally:
            try:
                self.socket.close()
            except Exception:
                pass
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass
            self.status_callback("🛑 Viewer disconnected")

    def stop(self):
        """Stop running and close socket"""
        self.running = False
        try:
            if self.socket:
                self.socket.close()
        except Exception:
            pass

    def _recv_exact(self, num_bytes):
        """Receive exactly num_bytes"""
        data = b''
        while len(data) < num_bytes:
            try:
                chunk = self.socket.recv(min(num_bytes - len(data), BUFFER_SIZE))
                if not chunk:
                    return None
                data += chunk
            except Exception:
                return None
        return data


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage:")
        print("  Presenter: python3 screen_share_client.py <server_ip> presenter")
        print("  Viewer:    python3 screen_share_client.py <server_ip> viewer")
        sys.exit(1)

    server_ip = sys.argv[1]
    mode = sys.argv[2]

    client = ScreenShareClient(server_ip, mode)
    client.start()
