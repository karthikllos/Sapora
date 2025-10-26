"""
Helper functions for message serialization and deserialization
Uses struct for efficient binary packing/unpacking
"""
import struct
from shared.constants import HEADER_SIZE, PROTOCOL_VERSION, MAX_MESSAGE_SIZE

def pack_message(msg_type, payload=b""):
    """Packs a message with header and payload"""
    if not isinstance(payload, bytes):
        payload = str(payload).encode('utf-8')
    
    payload_length = len(payload)
    
    if payload_length > MAX_MESSAGE_SIZE:
        raise ValueError(f"Payload size {payload_length} exceeds maximum {MAX_MESSAGE_SIZE}")
    
    sequence_number = 0
    reserved = 0
    
    # Format: !BBIHH = Version(1), MsgType(1), PayloadLen(4), SeqNum(4), Reserved(2)
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
    """Unpack a message into header components and payload"""
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
    
    if len(payload) != payload_length:
        raise ValueError(
            f"Payload length mismatch: expected {payload_length}, got {len(payload)}"
        )
    
    if version != PROTOCOL_VERSION:
        raise ValueError(
            f"Protocol version mismatch: expected {PROTOCOL_VERSION}, got {version}"
        )
    
    return version, msg_type, payload_length, sequence_number, payload


# --- File Metadata Helpers (The ones causing the error) ---

def pack_file_metadata(filename, filesize, checksum=""):
    """Packs file metadata for file transfer"""
    filename_bytes = filename.encode('utf-8')
    checksum_bytes = checksum.encode('utf-8')
    
    # Format: filename_length(I) + filename + filesize(Q) + checksum_length(I) + checksum
    metadata = struct.pack('!I', len(filename_bytes))
    metadata += filename_bytes
    metadata += struct.pack('!Q', filesize)
    metadata += struct.pack('!I', len(checksum_bytes))
    metadata += checksum_bytes
    
    return metadata


def unpack_file_metadata(data):
    """Unpacks file metadata"""
    offset = 0
    
    # Unpack filename
    filename_length = struct.unpack('!I', data[offset:offset+4])[0]
    offset += 4
    filename = data[offset:offset+filename_length].decode('utf-8')
    offset += filename_length
    
    # Unpack filesize (Q is 8 bytes for large file support)
    filesize = struct.unpack('!Q', data[offset:offset+8])[0]
    offset += 8
    
    # Unpack checksum
    checksum_length = struct.unpack('!I', data[offset:offset+4])[0]
    offset += 4
    checksum = data[offset:offset+checksum_length].decode('utf-8')
    
    return {
        'filename': filename,
        'filesize': filesize,
        'checksum': checksum
    }