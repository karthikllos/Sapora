"""
Sapora LAN Collaboration Suite - Server Utilities
Includes helpers for message serialization (protocol) and connection management.
"""
import struct
import json
import time
import sys
import os
import numpy as np 
import socket # Added socket import for robust read_tcp_message

# --- CRITICAL FIX: Add project root to path for shared/ imports ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
# -----------------------------------------------------------------

from shared.constants import (
    HEADER_SIZE, PROTOCOL_VERSION, MAX_MESSAGE_SIZE, AUDIO_CHUNK, AUDIO_FORMAT_PCM,
    AUDIO_CHANNELS, BUFFER_SIZE # Added BUFFER_SIZE for read_tcp_message
)
from shared.protocol import MESSAGE_TYPES, CMD_USER_LIST, get_message_type_name


# --- Protocol Serialization Helpers ---

def pack_message(msg_type, payload=b""):
    """Packs a message with the Sapora header (12 bytes)."""
    if not isinstance(payload, bytes):
        payload = str(payload).encode('utf-8')
    
    payload_length = len(payload)
    
    if payload_length > MAX_MESSAGE_SIZE:
        if msg_type not in (0x40, 0x41):
             raise ValueError(f"Payload size {payload_length} exceeds maximum {MAX_MESSAGE_SIZE}")

    sequence_number = 0 
    reserved = 0
    
    header = struct.pack(
        '!BBIHH',
        PROTOCOL_VERSION,    # 1 byte (B)
        msg_type,            # 1 byte (B)
        payload_length,      # 4 bytes (I)
        sequence_number,     # 4 bytes (I)
        reserved             # 2 bytes (H)
    )
    
    return header + payload

def unpack_message(data):
    """Unpacks a message into header components and payload."""
    if len(data) < HEADER_SIZE:
        raise ValueError(f"Data too short: {len(data)} bytes (minimum {HEADER_SIZE})")
    
    header = data[:HEADER_SIZE]
    payload = data[HEADER_SIZE:]
    
    try:
        version, msg_type, payload_length, sequence_number, reserved = struct.unpack(
            '!BBIHH',
            header
        )
    except struct.error as e:
        raise ValueError(f"Failed to unpack header: {e}")
    
    if len(payload) < payload_length:
        raise ValueError(f"Incomplete payload: expected {payload_length}, got {len(payload)}")

    payload = payload[:payload_length]

    if version != PROTOCOL_VERSION:
        raise ValueError(f"Protocol version mismatch: expected {PROTOCOL_VERSION}, got {version}")
    
    return version, msg_type, payload_length, sequence_number, payload

def read_tcp_message(sock):
    """Reads a complete message packet from a TCP socket."""
    # 1. Read header (fixed size)
    try:
        header = sock.recv(HEADER_SIZE)
        if not header or len(header) < HEADER_SIZE:
            return None
    except socket.timeout:
        return None
    except Exception:
        return None
    
    # 2. Parse payload length
    try:
        payload_length = struct.unpack('!I', header[2:6])[0]
    except struct.error:
        return None

    # 3. Read payload (variable size)
    payload = b''
    while len(payload) < payload_length:
        chunk = sock.recv(min(payload_length - len(payload), BUFFER_SIZE))
        if not chunk:
            return None 
        payload += chunk
        
    return header + payload

# --- Connection Management Helper ---

def broadcast_user_list(manager):
    """Packs and sends the current user list to all connected TCP clients."""
    user_list = manager.get_user_list()
    user_list_json = json.dumps(user_list)
    
    user_list_packet = pack_message(CMD_USER_LIST, user_list_json.encode('utf-8'))
    
    disconnected = []
    
    for addr, client_info in list(manager.control_clients.items()):
        try:
            client_info['socket'].sendall(user_list_packet)
        except Exception:
            disconnected.append(client_info['socket'])
    
    for sock in disconnected:
        manager.remove_client(sock)
        
# --- Audio Mixing Helpers ---

def mix_audio_chunks(chunks):
    """Mixes a list of raw PCM audio chunks (np.int16, Mono) by averaging."""
    if not chunks:
        return None
        
    try:
        arrays = []
        for chunk in chunks:
            bytes_per_chunk = AUDIO_CHUNK * AUDIO_CHANNELS * AUDIO_FORMAT_PCM
            if len(chunk) != bytes_per_chunk:
                continue 

            arr = np.frombuffer(chunk, dtype=np.int16)
            arrays.append(arr)
        
        if not arrays:
            return None

        max_len = max(len(arr) for arr in arrays)
        padded = []
        for arr in arrays:
            if len(arr) < max_len:
                padded_arr = np.pad(arr, (0, max_len - len(arr)), mode='constant')
                padded.append(padded_arr)
            else:
                padded.append(arr)
        
        mixed = np.mean(padded, axis=0).astype(np.int16)
        
        return mixed.tobytes()
        
    except Exception as e:
        return None