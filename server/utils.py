"""
Sapora LAN Collaboration Suite - Server Utilities
Includes helpers for message serialization (protocol) and connection management.
"""
import struct
import json
import time
import sys
import os

# Add parent directory to path to import constants/protocol
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.constants import (
    HEADER_SIZE, PROTOCOL_VERSION, MAX_MESSAGE_SIZE, AUDIO_CHUNK, AUDIO_FORMAT_PCM
)
from shared.protocol import MESSAGE_TYPES, CMD_USER_LIST


# --- Protocol Serialization Helpers ---

def pack_message(msg_type, payload=b""):
    """Packs a message with the Sapora header (12 bytes)."""
    if not isinstance(payload, bytes):
        payload = str(payload).encode('utf-8')
    
    payload_length = len(payload)
    
    # Check max size (simplified to allow buffer_size limits for streaming data)
    if payload_length > MAX_MESSAGE_SIZE:
        # For a full implementation, large payloads like file chunks would be handled
        # via chunking logic *before* calling this.
        if msg_type not in (STREAM_VIDEO, STREAM_AUDIO):
             raise ValueError(f"Payload size {payload_length} exceeds maximum {MAX_MESSAGE_SIZE}")

    sequence_number = 0 # Simple implementation uses static 0
    reserved = 0
    
    # Format: !BBIHH = network byte order, unsigned char, unsigned char, unsigned int, unsigned int, unsigned short
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
    
    # Validate payload length only if we have the full message
    if len(payload) < payload_length:
        raise ValueError(f"Incomplete payload: expected {payload_length}, got {len(payload)}")

    # Truncate payload to expected length if more data was received in one go (TCP stream)
    payload = payload[:payload_length]

    if version != PROTOCOL_VERSION:
        raise ValueError(f"Protocol version mismatch: expected {PROTOCOL_VERSION}, got {version}")
    
    return version, msg_type, payload_length, sequence_number, payload

def read_tcp_message(sock):
    """Reads a complete message packet from a TCP socket."""
    # 1. Read header (fixed size)
    header = sock.recv(HEADER_SIZE)
    if not header:
        return None
    
    # 2. Parse payload length
    try:
        # Payload length is at byte index 2, is a 4-byte unsigned integer (I)
        payload_length = struct.unpack('!I', header[2:6])[0]
    except struct.error:
        # Corrupted header
        return None

    # 3. Read payload (variable size)
    payload = b''
    while len(payload) < payload_length:
        chunk = sock.recv(min(payload_length - len(payload), BUFFER_SIZE))
        if not chunk:
            return None # Connection closed while reading payload
        payload += chunk
        
    return header + payload

# --- Connection Management Helper ---

def broadcast_user_list(manager):
    """Packs and sends the current user list to all connected TCP clients."""
    user_list = manager.get_user_list()
    # Serialize the list of dicts to JSON payload
    user_list_json = json.dumps(user_list)
    
    user_list_packet = pack_message(CMD_USER_LIST, user_list_json.encode('utf-8'))
    
    # Send to all connected clients on the control/chat ports
    disconnected = []
    
    # Broadcast to control clients (where chat handler will also listen)
    for addr, client_info in list(manager.control_clients.items()):
        try:
            client_info['socket'].sendall(user_list_packet)
        except Exception:
            disconnected.append(client_info['socket'])
    
    # Clean up disconnected clients in the main manager thread
    for sock in disconnected:
        manager.remove_client(sock)
        
# --- Audio Mixing Helpers ---

def mix_audio_chunks(chunks):
    """Mixes a list of raw PCM audio chunks (np.int16, Mono) by averaging."""
    if not chunks:
        return None
        
    try:
        # Convert all chunks to numpy arrays (int16)
        arrays = []
        for chunk in chunks:
            # Need to ensure the chunk is the correct size before conversion
            bytes_per_chunk = AUDIO_CHUNK * AUDIO_CHANNELS * AUDIO_FORMAT_PCM // 8
            if len(chunk) != bytes_per_chunk:
                # Pad to expected chunk size if necessary (or simply skip)
                continue 

            arr = np.frombuffer(chunk, dtype=np.int16)
            arrays.append(arr)
        
        if not arrays:
            return None

        # Determine max length and pad (critical for UDP chunk synchronization)
        max_len = max(len(arr) for arr in arrays)
        padded = []
        for arr in arrays:
            if len(arr) < max_len:
                padded_arr = np.pad(arr, (0, max_len - len(arr)), mode='constant')
                padded.append(padded_arr)
            else:
                padded.append(arr)
        
        # Mix: Average all audio streams, then convert back to int16
        # np.mean converts to float by default, so we cast back to int16
        mixed = np.mean(padded, axis=0).astype(np.int16)
        
        return mixed.tobytes()
        
    except Exception as e:
        # print(f"Audio Mix Error: {e}") # Log on server side
        return None