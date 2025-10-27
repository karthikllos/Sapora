"""
Sapora LAN Collaboration Suite - Global Constants
Defines ports, buffer sizes, and configuration values.
"""
import os

# --- Server Configuration ---
# Default IP is 127.0.0.1 for local testing, can be set to 0.0.0.0 on server
# or a specific LAN IP for the client.
DEFAULT_SERVER_IP = "127.0.0.1" 
STORAGE_DIR = "sapora_files"

# --- Service Ports ---
# TCP ports (Reliable connections: Control, Chat, File Transfer, Screen Share)
CONTROL_PORT = 5000       # TCP for initial handshake, user list, and keepalive
CHAT_PORT = 5001          # TCP for chat messages
FILE_TRANSFER_PORT = 5002 # TCP for file upload/download
SCREEN_SHARE_PORT = 5003  # TCP for screen sharing (presenter stream)

# UDP ports (Low-latency streaming: Video, Audio)
VIDEO_PORT = 6000         # UDP for video streaming
AUDIO_PORT = 6001         # UDP for audio streaming

# --- Protocol & Buffer Sizes (in bytes) ---
PROTOCOL_VERSION = 1
HEADER_SIZE = 10             # Fixed header size for message packets (BBIHH struct)
BUFFER_SIZE = 65536          # Default socket buffer size (64 KB)
UDP_STREAM_BUFFER = 65536    # 64 KB for UDP sockets
MAX_MESSAGE_SIZE = 1048576   # 1 MB maximum for non-file payloads <--- ADDED THIS LINE

# File Transfer Limits
FILE_CHUNK_SIZE = 32768      # 32 KB chunk size for TCP file transfer
MAX_FILE_SIZE = 104857600    # 100 MB maximum file size

# --- Streaming Settings ---
# Video (Simplified to JPEG/H.264 compatible settings for robust socket implementation)
VIDEO_WIDTH = 640
VIDEO_HEIGHT = 480
VIDEO_FPS = 15
VIDEO_QUALITY = 55           # JPEG compression quality (0-100) - Reduced for faster encode/decode
VIDEO_STREAM_FORMAT = 'BGR'  # OpenCV default

# Audio (Simplified to raw PCM for robust socket implementation)
AUDIO_RATE = 44100      # Sample rate in Hz
AUDIO_CHANNELS = 1      # Mono (Simplifies mixing)
AUDIO_CHUNK = 1024      # Frames per buffer (common PyAudio chunk size)
AUDIO_FORMAT_PCM = 2    # pyaudio.paInt16 (2 bytes per sample)

# --- Timeouts and Retries ---
CONNECTION_TIMEOUT = 5.0
SOCKET_TIMEOUT = 1.0
HEARTBEAT_INTERVAL = 3.0
CLIENT_IDLE_TIMEOUT=15.0