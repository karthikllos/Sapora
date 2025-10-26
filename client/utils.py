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

# --- Protocol Serialization Helpers (Mirroring Server) ---

def pack_message(msg_type, payload=b""):
    """Packs a message with the Sapora header (12 bytes)."""
    if not isinstance(payload, bytes):
        payload = str(payload).encode('utf-8')
    
    payload_length = len(payload)
    sequence_number = 0
    reserved = 0
    
    header = struct.pack(
        '!BBIHH',
        PROTOCOL_VERSION,
        msg_type,
        payload_length,
        sequence_number,
        reserved
    )
    
    return header + payload

def unpack_message(data):
    """Unpacks a message into header components and payload."""
    if len(data) < HEADER_SIZE:
        raise ValueError(f"Data too short: {len(data)} bytes (minimum {HEADER_SIZE})")
    
    header = data[:HEADER_SIZE]
    payload = data[HEADER_SIZE:]
    
    version, msg_type, payload_length, sequence_number, reserved = struct.unpack(
        '!BBIHH',
        header
    )
    
    # Client should only attempt to unpack a full message, but handle slight over-read in TCP stream
    if len(payload) < payload_length:
        raise ValueError(f"Incomplete payload: expected {payload_length}, got {len(payload)}")

    payload = payload[:payload_length]

    if version != PROTOCOL_VERSION:
        raise ValueError(f"Protocol version mismatch: expected {PROTOCOL_VERSION}, got {version}")
    
    return version, msg_type, payload_length, sequence_number, payload

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
    header = _recv_exact(sock, HEADER_SIZE)
    if header is None:
        return None
    
    # 2. Parse payload length
    try:
        payload_length = struct.unpack('!I', header[2:6])[0]
    except struct.error:
        return None

    # 3. Read payload (variable size)
    payload = _recv_exact(sock, payload_length)
    if payload is None:
        return None
        
    return header + payload