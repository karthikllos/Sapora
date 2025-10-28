"""
Sapora LAN Collaboration Suite - Video Client
Handles webcam capture, encoding, sending (UDP), and receiving/decoding (UDP).
"""
import threading
import socket
import time
import cv2
import numpy as np
import sys
import os

# Add parent path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.constants import (
    VIDEO_PORT, UDP_STREAM_BUFFER, VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS,
    CONNECTION_TIMEOUT
)
from shared.protocol import STREAM_VIDEO, CMD_REGISTER
from client.utils import pack_message, unpack_message, encode_frame_to_jpeg, decode_jpeg_to_frame

class VideoClient:
    """Handles all video I/O, combining sender and receiver logic."""

    def __init__(self, server_ip, server_port, username, frame_callback):
        self.server_ip = server_ip
        self.server_port = server_port
        self.username = username
        self.frame_callback = frame_callback
        
        self.running = False
        self.cap = None
        self.sock = None  # Single socket for both send and receive
        
        self.last_frame = None # Frame captured by self for local display

    # --- Sender Logic ---

    def start_streaming(self, status_callback):
        """Starts webcam capture and transmission thread."""
        if self.running:
            return True
            
        try:
            # 1. Initialize camera
            self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) # Use DSHOW for Windows low latency
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(0) # Fallback
                if not self.cap.isOpened():
                    status_callback("❌ Camera unavailable. Try closing other video apps.")
                    return False
            
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, VIDEO_WIDTH)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, VIDEO_HEIGHT)
            self.cap.set(cv2.CAP_PROP_FPS, VIDEO_FPS)
            
            # 2. Initialize socket (single for both send and receive)
            if not self.sock:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, UDP_STREAM_BUFFER)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, UDP_STREAM_BUFFER)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                # Bind to ephemeral port for receiving
                self.sock.bind(('', 0))
                self.sock.settimeout(CONNECTION_TIMEOUT)
            
            self.running = True
            threading.Thread(target=self._send_loop, daemon=True).start()
            status_callback("📹 Streaming video...")
            return True
            
        except Exception as e:
            status_callback(f"❌ Video stream error: {str(e)}")
            self.stop_streaming()
            return False

    def _send_loop(self):
        """Continuously captures, encodes, and sends frames."""
        frame_interval = 1.0 / VIDEO_FPS
        
        try:
            while self.running:
                start_time = time.time()
                
                ret, frame = self.cap.read()
                if not ret:
                    continue

                self.last_frame = frame.copy() # Store for local display

                # Encode frame to JPEG
                jpeg_bytes = encode_frame_to_jpeg(frame)
                
                # Pack and send using single socket
                packet = pack_message(STREAM_VIDEO, jpeg_bytes)
                self.sock.sendto(packet, (self.server_ip, self.server_port))
                
                # Control frame rate
                elapsed = time.time() - start_time
                sleep_time = max(0, frame_interval - elapsed)
                time.sleep(sleep_time)

        except Exception as e:
            if self.running:
                print(f"VideoClient Send Error: {e}")
        finally:
            self.stop_streaming()

    # --- Receiver Logic ---
    
    def start_receiving(self):
        """Starts the receiver thread and registers with the server."""
        # Create socket if not already created by start_streaming
        if not self.sock:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, UDP_STREAM_BUFFER)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, UDP_STREAM_BUFFER)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Bind to ephemeral port to receive broadcasts
            self.sock.bind(('', 0))
            self.sock.settimeout(CONNECTION_TIMEOUT)
        
        self.running = True
        self._register_receiver()
        
        threading.Thread(target=self._recv_loop, daemon=True).start()

    def _register_receiver(self):
        """Sends registration packet to the server."""
        # Payload can be simple REGISTRATION command to tell server client is ready for video
        register_packet = pack_message(CMD_REGISTER, b"VIDEO") 
        for _ in range(3): # Send a few times for reliability
            try:
                self.sock.sendto(register_packet, (self.server_ip, self.server_port))
                time.sleep(0.1)
            except Exception as e:
                print(f"VideoClient Registration Error: {e}")

    def _recv_loop(self):
        """Continuously receives and processes video frames."""
        while self.running:
            try:
                data, addr = self.sock.recvfrom(UDP_STREAM_BUFFER)
                
                # Unpack and decode
                version, msg_type, _, _, payload = unpack_message(data)
                
                if msg_type == STREAM_VIDEO:
                    frame = decode_jpeg_to_frame(payload)
                    if frame is not None:
                        # Use the source IP for identification (Server's UDP IP)
                        source_ip = addr[0] 
                        self.frame_callback(source_ip, frame) 
                        
            except socket.timeout:
                continue
            except ValueError:
                # Malformed packet, ignore
                continue
            except Exception as e:
                if self.running:
                    print(f"VideoClient Recv Error: {e}")
        
    # --- Cleanup ---

    def stop_streaming(self):
        """Cleans up resources and stops threads."""
        self.running = False
        
        if self.cap:
            try:
                self.cap.release()
            except:
                pass
            self.cap = None
            
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None