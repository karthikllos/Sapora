"""
Sapora LAN Collaboration Suite - Server Utilities (FIXED)
Includes helpers for message serialization (protocol) and connection management.
"""
import struct
import json
import time
import sys
import os
import numpy as np 
import socket

# --- CRITICAL FIX: Add project root to path for shared/ imports ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.constants import (
    HEADER_SIZE, PROTOCOL_VERSION, MAX_MESSAGE_SIZE, AUDIO_CHUNK, AUDIO_FORMAT_PCM,
    AUDIO_CHANNELS, BUFFER_SIZE
)
from shared.protocol import MESSAGE_TYPES, CMD_USER_LIST

from shared.helpers import pack_message, unpack_message

# --- Protocol Serialization Helpers ---

def _recv_exact(sock, num_bytes):
    """Receive exactly num_bytes from a TCP socket or return None on failure.
    NOTE: Timeouts are propagated so callers can decide to continue rather than treat as disconnect.
    """
    data = b''
    try:
        while len(data) < num_bytes:
            chunk = sock.recv(min(num_bytes - len(data), BUFFER_SIZE))
            if not chunk:
                return None
            data += chunk
        return data
    except socket.timeout:
        # Propagate timeout so TCP handlers can continue their loops instead of disconnecting clients
        raise
    except Exception:
        return None

def read_tcp_message(sock):
    """Reads a complete message packet from a TCP socket."""
    # 1) Read full header
    header = _recv_exact(sock, HEADER_SIZE)
    if header is None:
        return None

    # 2) Parse payload length
    try:
        payload_length = struct.unpack('!I', header[2:6])[0]
    except struct.error:
        return None

    # 3) Read full payload
    payload = _recv_exact(sock, payload_length) if payload_length > 0 else b''
    if payload is None:
        return None

    return header + payload

# --- Debug/Logging Helpers ---

def get_message_type_name(msg_type):
    """Return human-readable name for a protocol message type."""
    try:
        return MESSAGE_TYPES.get(msg_type, f"UNKNOWN({msg_type})")
    except Exception:
        return str(msg_type)

# --- Connection Management Helper (FIXED) ---

def broadcast_user_list(manager):
    """Packs and sends the current user list to all connected TCP clients."""
    user_list = manager.get_user_list()
    user_list_json = json.dumps(user_list)
    
    user_list_packet = pack_message(CMD_USER_LIST, user_list_json.encode('utf-8'))
    
    disconnected = []
    
    # FIX: Iterate over control_clients correctly
    with manager.control_clients_lock:
        for client_socket, client_info in list(manager.control_clients.items()):
            try:
                client_socket.sendall(user_list_packet)
                if os.environ.get('SAPORA_DEBUG'):
                    print(f"[broadcast_user_list] Sent to {client_info.get('username', 'Unknown')}")
            except Exception as e:
                if os.environ.get('SAPORA_DEBUG'):
                    print(f"[broadcast_user_list] Failed to send to {client_info.get('username', 'Unknown')}: {e}")
                disconnected.append(client_socket)
    
    # Remove disconnected clients
    for sock in disconnected:
        manager.remove_client(sock)

def broadcast_room_user_list(server, room_id: str):
    """Broadcast detailed user list to all participants in a room."""
    try:
        with server.rooms_lock:
            room = server.rooms.get(room_id)
            if not room:
                return
            participants = room.get('participants') or {}
            
            # Get detailed user info for this room
            user_list = []
            for username, sock in participants.items():
                if sock in server.manager.control_clients:
                    client_info = server.manager.control_clients[sock]
                    user_list.append({
                        'username': username,
                        'ip': client_info['addr'][0],
                        'last_seen': client_info['last_seen'],
                        'last_seen_formatted': server.manager._format_last_seen(client_info['last_seen']),
                        'room': room_id
                    })
            
            payload = json.dumps(user_list).encode('utf-8')
            packet = pack_message(CMD_USER_LIST, payload)
            sockets = list(participants.values())
            
        # Send to all participants in the room
        for sock in sockets:
            try:
                sock.sendall(packet)
            except Exception:
                pass
    except Exception as e:
        if os.environ.get('SAPORA_DEBUG'):
            print(f"[broadcast_room_user_list] Error: {e}")

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
        if os.environ.get('SAPORA_DEBUG'):
            print(f"[mix_audio_chunks] Error: {e}")
        return None