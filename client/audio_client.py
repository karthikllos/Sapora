"""
Sapora LAN Collaboration Suite - Audio Client (optimized)
Handles microphone capture (sender) and playback (receiver).
Improvements:
 - robust PyAudio handling
 - controlled send timing to match chunk duration
 - non-blocking/timeout recv loop for low latency playback
 - safer resource cleanup
"""
import threading
import socket
import time
import pyaudio
import numpy as np
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared.constants import (
    AUDIO_PORT, UDP_STREAM_BUFFER, AUDIO_RATE, AUDIO_CHANNELS, AUDIO_CHUNK,
    CONNECTION_TIMEOUT
)
from shared.protocol import STREAM_AUDIO, CMD_REGISTER
from client.utils import pack_message, unpack_message

AUDIO_FORMAT = pyaudio.paInt16

class AudioClient:
    """Handles all audio I/O: sender, receiver, and PyAudio management."""

    def _init_(self, server_ip, username=None):
        self.server_ip = server_ip
        self.server_port = AUDIO_PORT
        self.username = username or "user"
        
        # Lifecycle flags
        self.running = False          # Any audio activity
        self.sending = False          # Mic capture -> send active
        self.playing = False          # Playback active
        
        self.audio = None
        self.stream_out = None
        self.stream_in = None
        
        # FIX: Use single socket for both send and receive
        self.sock = None
        
        self.send_thread = None
        self.recv_thread = None
        
        # Mic mute state (True = sending audio, False = muted)
        self.mic_enabled = True

    # --- Sender Logic (Microphone) ---

    def start_streaming(self, status_callback=None):
        """Starts microphone capture and transmission loop (idempotent)."""
        try:
            # Already sending?
            if self.send_thread and self.send_thread.is_alive():
                return True
            if not self.audio:
                self.audio = pyaudio.PyAudio()
            
            # Input stream (microphone)
            if not self.stream_in:
                self.stream_in = self.audio.open(
                    format=AUDIO_FORMAT,
                    channels=AUDIO_CHANNELS,
                    rate=AUDIO_RATE,
                    input=True,
                    frames_per_buffer=AUDIO_CHUNK
                )
            
            # FIX: Single socket for both send and receive
            # Bind to ephemeral port so we can receive on same socket
            if not self.sock:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, UDP_STREAM_BUFFER)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, UDP_STREAM_BUFFER)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.sock.bind(('', 0))  # Bind to ephemeral port
                self.sock.settimeout(CONNECTION_TIMEOUT)

            self.running = True
            self.sending = True
            self.send_thread = threading.Thread(target=self._send_loop, daemon=True)
            self.send_thread.start()
            if status_callback:
                status_callback("🎤 Streaming audio...")
            return True
        except Exception as e:
            if status_callback:
                status_callback(f"❌ Audio stream error: {str(e)}")
            self.sending = False
            return False

    def _send_loop(self):
        """Continuously reads audio chunks and sends to server."""
        # compute ideal sleep per chunk based on sample params:
        chunk_duration = float(AUDIO_CHUNK) / float(AUDIO_RATE)  # seconds
        try:
            while self.sending:
                loop_start = time.time()
                try:
                    audio_data = self.stream_in.read(AUDIO_CHUNK, exception_on_overflow=False)
                except IOError:
                    # Overflows happen under load; skip this chunk
                    audio_data = None
                except Exception as e:
                    print(f"AudioClient Send read error: {e}")
                    audio_data = None

                # If mic is enabled and we have data, send it; otherwise drop it (mute)
                if audio_data and self.mic_enabled:
                    packet = pack_message(STREAM_AUDIO, audio_data)
                    try:
                        # FIX: Use single socket
                        self.sock.sendto(packet, (self.server_ip, self.server_port))
                    except Exception:
                        # Ignore transient send errors
                        pass

                # Throttle to maintain consistent capture->send cadence
                elapsed = time.time() - loop_start
                sleep_time = max(0, chunk_duration - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)

        finally:
            # Ensure sender cleaned when loop exits (keep playback/socket alive)
            try:
                if self.stream_in:
                    self.stream_in.stop_stream()
                    self.stream_in.close()
            except:
                pass
            self.stream_in = None
            self.sending = False
            if not self.playing:
                self.running = False

    # --- Receiver Logic (Playback) ---
    
    def start_receiving(self):
        """Initializes playback stream and starts receiver thread (idempotent)."""
        try:
            if self.recv_thread and self.recv_thread.is_alive():
                return
            if not self.audio:
                self.audio = pyaudio.PyAudio()

            # Output stream
            if not self.stream_out:
                self.stream_out = self.audio.open(
                    format=AUDIO_FORMAT,
                    channels=AUDIO_CHANNELS,
                    rate=AUDIO_RATE,
                    output=True,
                    frames_per_buffer=AUDIO_CHUNK
                )
            
            # FIX: Use single socket (create if not already created by start_streaming)
            if not self.sock:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, UDP_STREAM_BUFFER)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, UDP_STREAM_BUFFER)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                # bind to ephemeral port so server can send to us
                self.sock.bind(('', 0))
                self.sock.settimeout(CONNECTION_TIMEOUT)
            
            self.running = True
            self.playing = True
            self._register_receiver()
            self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            self.recv_thread.start()
        except Exception as e:
            print(f"AudioClient Recv Setup Error: {e}")

    def _register_receiver(self):
        """Sends registration packet to the server's audio port with username and room info."""
        try:
            import json
            reg_data = {
                'username': self.username,
                'stream_type': 'audio',
                'room': 'default'  # Could be made configurable
            }
            register_packet = pack_message(CMD_REGISTER, json.dumps(reg_data).encode('utf-8'))
            
            for _ in range(3):
                try:
                    # Use single socket - this ensures server knows our receive address
                    self.sock.sendto(register_packet, (self.server_ip, self.server_port))
                except Exception as e:
                    if os.environ.get('SAPORA_DEBUG'):
                        print(f"AudioClient Registration Error: {e}")
                time.sleep(0.05)
        except Exception as e:
            if os.environ.get('SAPORA_DEBUG'):
                print(f"AudioClient Registration Setup Error: {e}")

    def _recv_loop(self):
        """Continuously receives mixed audio and plays it back (with UDP keepalive)."""
        last_keepalive = 0.0
        import json
        while self.playing:
            # periodic keepalive so server retains our listener mapping
            now = time.time()
            if now - last_keepalive > 5.0:
                try:
                    reg = {'username': self.username, 'stream_type': 'audio', 'room': 'default'}
                    self.sock.sendto(pack_message(CMD_REGISTER, json.dumps(reg).encode('utf-8')), (self.server_ip, self.server_port))
                except Exception:
                    pass
                last_keepalive = now
            try:
                # FIX: Use single socket
                data, addr = self.sock.recvfrom(UDP_STREAM_BUFFER)
            except socket.timeout:
                continue
            except Exception as e:
                if self.playing:
                    print(f"AudioClient Recv Error (socket): {e}")
                break

            try:
                version, msg_type, _, _, payload = unpack_message(data)
            except ValueError:
                continue

            if msg_type == STREAM_AUDIO:
                try:
                    # Play mixed audio chunk (non-blocking write)
                    if self.stream_out:
                        # Simple echo mitigation: attenuate playback when mic is active
                        if self.mic_enabled:
                            try:
                                samples = np.frombuffer(payload, dtype=np.int16)
                                atten = (samples * 0.7).astype(np.int16)
                                self.stream_out.write(atten.tobytes())
                            except Exception:
                                self.stream_out.write(payload)
                        else:
                            self.stream_out.write(payload)
                except Exception as e:
                    # ignore bursts/underruns
                    # print(f"AudioClient Playback error: {e}")
                    pass

    # --- Cleanup ---

    def set_mic_enabled(self, enabled: bool):
        """Enable/disable microphone sending without stopping playback"""
        self.mic_enabled = bool(enabled)

    def stop_streaming(self):
        """Cleans up all audio resources and closes sockets (stop both sending and playing)."""
        self.running = False
        self.sending = False
        self.playing = False
        
        # Close socket (single socket for both send and receive)
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None

        # Close streams
        if self.stream_in:
            try:
                self.stream_in.stop_stream()
                self.stream_in.close()
            except:
                pass
            self.stream_in = None

        if self.stream_out:
            try:
                self.stream_out.stop_stream()
                self.stream_out.close()
            except:
                pass
            self.stream_out = None

        if self.audio:
            try:
                self.audio.terminate()
            except:
                pass
            self.audio = None

        print("AudioClient: stopped.")