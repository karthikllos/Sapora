"""
Sapora LAN Collaboration Suite - Audio Client
Handles microphone capture, mixing (implicitly via server), and playback (UDP).
"""
import threading
import socket
import time
import pyaudio
import sys
import os

# Add parent path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.constants import (
    AUDIO_PORT, UDP_STREAM_BUFFER, AUDIO_RATE, AUDIO_CHANNELS, AUDIO_CHUNK, 
    CONNECTION_TIMEOUT
)
from shared.protocol import STREAM_AUDIO, CMD_REGISTER
from client.utils import pack_message, unpack_message

# PyAudio setup (uses constants for format)
AUDIO_FORMAT = pyaudio.paInt16

class AudioClient:
    """Handles all audio I/O: sender, receiver, and PyAudio management."""

    def __init__(self, server_ip, server_port, username):
        self.server_ip = server_ip
        self.server_port = server_port
        self.username = username
        
        self.running = False
        self.audio = None
        self.stream_out = None
        self.stream_in = None
        
        self.send_sock = None
        self.recv_sock = None
        
        # Threads
        self.send_thread = None
        self.recv_thread = None

    # --- Sender Logic (Microphone) ---

    def start_streaming(self, status_callback):
        """Starts microphone capture and transmission loop."""
        if self.running:
            return True
            
        try:
            self.audio = pyaudio.PyAudio()
            
            # Open input stream
            self.stream_in = self.audio.open(
                format=AUDIO_FORMAT,
                channels=AUDIO_CHANNELS,
                rate=AUDIO_RATE,
                input=True,
                frames_per_buffer=AUDIO_CHUNK
            )
            
            self.send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            self.running = True
            self.send_thread = threading.Thread(target=self._send_loop, daemon=True)
            self.send_thread.start()
            status_callback("🎤 Streaming audio...")
            return True
            
        except Exception as e:
            status_callback(f"❌ Audio stream error: {str(e)}")
            self.stop_streaming()
            return False

    def _send_loop(self):
        """Continuously reads audio chunks and sends to server."""
        while self.running:
            try:
                # 1. Read audio data
                audio_data = self.stream_in.read(AUDIO_CHUNK, exception_on_overflow=False)
                
                # 2. Pack and send (audio chunks are sent continuously)
                packet = pack_message(STREAM_AUDIO, audio_data)
                self.send_sock.sendto(packet, (self.server_ip, self.server_port))
                
            except IOError as e:
                # Ignore overflow/underrun errors
                pass
            except Exception as e:
                if self.running:
                    print(f"AudioClient Send Error: {e}")
                break
        
        self.stop_streaming()

    # --- Receiver Logic (Playback) ---
    
    def start_receiving(self):
        """Initializes playback stream and starts receiver thread."""
        try:
            if not self.audio:
                self.audio = pyaudio.PyAudio()

            # Open output stream
            self.stream_out = self.audio.open(
                format=AUDIO_FORMAT,
                channels=AUDIO_CHANNELS,
                rate=AUDIO_RATE,
                output=True,
                frames_per_buffer=AUDIO_CHUNK
            )
            
            self.recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, UDP_STREAM_BUFFER)
            self.recv_sock.settimeout(CONNECTION_TIMEOUT)
            self.recv_sock.bind(('', 0)) # Bind to any port for receiving mixed stream

            self.running = True
            self._register_receiver()
            
            self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            self.recv_thread.start()
            
        except Exception as e:
            if self.running:
                 print(f"AudioClient Recv Setup Error: {e}")

    def _register_receiver(self):
        """Sends registration packet to the server's audio port."""
        # Use simple AUDIO payload to notify server this IP:Port is a listener
        register_packet = pack_message(CMD_REGISTER, b"AUDIO") 
        
        for _ in range(3):
            try:
                self.recv_sock.sendto(register_packet, (self.server_ip, self.server_port))
                time.sleep(0.1)
            except Exception as e:
                print(f"AudioClient Registration Error: {e}")

    def _recv_loop(self):
        """Continuously receives mixed audio and plays it back."""
        while self.running:
            try:
                data, addr = self.recv_sock.recvfrom(UDP_STREAM_BUFFER)
                
                version, msg_type, _, _, payload = unpack_message(data)
                
                if msg_type == STREAM_AUDIO:
                    self.stream_out.write(payload) # Play mixed audio chunk

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"AudioClient Recv Error: {e}")

    # --- Cleanup ---

    def stop_streaming(self):
        """Cleans up all audio resources and closes sockets."""
        self.running = False
        
        if self.stream_in:
            try:
                self.stream_in.stop_stream()
                self.stream_in.close()
            except Exception:
                pass
            self.stream_in = None
            
        if self.stream_out:
            try:
                self.stream_out.stop_stream()
                self.stream_out.close()
            except Exception:
                pass
            self.stream_out = None
            
        if self.audio:
            try:
                self.audio.terminate()
            except Exception:
                pass
            self.audio = None

        if self.send_sock:
            try:
                self.send_sock.close()
            except:
                pass
            self.send_sock = None
            
        if self.recv_sock:
             try:
                 self.recv_sock.close()
             except:
                 pass
             self.recv_sock = None