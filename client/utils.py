"""
Sapora LAN Collaboration Suite - Client Utilities
Includes helper functions for protocol, audio, and video processing.
"""
import struct
import sys
import os
import numpy as np
import cv2

# Add parent directory to path to import constants/protocol
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.constants import (
    HEADER_SIZE, PROTOCOL_VERSION, AUDIO_CHUNK, AUDIO_FORMAT_PCM, 
    VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_QUALITY
)
from shared.helpers import pack_message, unpack_message

# --- Protocol Serialization Helpers (Mirroring Server) ---

# --- Video Helpers ---

def encode_frame_to_jpeg(frame, quality=VIDEO_QUALITY):
    """Compresses an OpenCV frame (numpy array) to JPEG bytes."""
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    # Use 1 for JPEG quality
    result, encoded_frame = cv2.imencode('.jpg', frame, encode_param)
    
    if not result:
        raise Exception("Failed to encode frame to JPEG")
    
    return encoded_frame.tobytes()

def decode_jpeg_to_frame(jpeg_bytes):
    """Decompresses JPEG bytes to an OpenCV frame (numpy array)."""
    nparr = np.frombuffer(jpeg_bytes, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    return frame

# --- General Helpers ---

def format_size(size_bytes):
    """Formats byte size to human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"

def _recv_exact(sock, num_bytes):
    """Receives exactly num_bytes from a TCP socket."""
    data = b''
    while len(data) < num_bytes:
        chunk = sock.recv(min(num_bytes - len(data), 4096)) # Use a safe internal buffer size
        if not chunk:
            return None
        data += chunk
    return data

def read_tcp_message(sock):
    """Reads a complete message packet from a TCP socket."""
    # 1. Read header (fixed size)
    print(f"[DEBUG read_tcp_message] Reading {HEADER_SIZE} byte header...")
    header = _recv_exact(sock, HEADER_SIZE)
    if header is None:
        print(f"[DEBUG read_tcp_message] Header read failed (None)")
        return None
    print(f"[DEBUG read_tcp_message] Header received: {len(header)} bytes")
    
    # 2. Parse payload length
    try:
        payload_length = struct.unpack('!I', header[2:6])[0]
        print(f"[DEBUG read_tcp_message] Payload length: {payload_length}")
    except struct.error as e:
        print(f"[DEBUG read_tcp_message] Failed to parse payload length: {e}")
        return None

    # 3. Read payload (variable size)
    print(f"[DEBUG read_tcp_message] Reading {payload_length} byte payload...")
    payload = _recv_exact(sock, payload_length)
    if payload is None:
        print(f"[DEBUG read_tcp_message] Payload read failed (None)")
        return None
    print(f"[DEBUG read_tcp_message] Payload received: {len(payload)} bytes")
    print(f"[DEBUG read_tcp_message] Returning complete message: {len(header) + len(payload)} bytes")
        
    return header + payload
