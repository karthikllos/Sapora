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

    def __init__(self, server_ip, username=None):
        self.server_ip = server_ip
        self.server_port = AUDIO_PORT
        self.username = username or "user"
        
        self.running = False
        self.audio = None
        self.stream_out = None
        self.stream_in = None
        
        self.send_sock = None
        self.recv_sock = None
        
        self.send_thread = None
        self.recv_thread = None

    # --- Sender Logic (Microphone) ---

    def start_streaming(self, status_callback=None):
        """Starts microphone capture and transmission loop."""
        if self.running:
            return True
        try:
            self.audio = pyaudio.PyAudio()
            
            # Input stream (microphone)
            self.stream_in = self.audio.open(
                format=AUDIO_FORMAT,
                channels=AUDIO_CHANNELS,
                rate=AUDIO_RATE,
                input=True,
                frames_per_buffer=AUDIO_CHUNK
            )
            
            # Sender socket
            self.send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, UDP_STREAM_BUFFER)
            self.send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            self.running = True
            self.send_thread = threading.Thread(target=self._send_loop, daemon=True)
            self.send_thread.start()
            if status_callback:
                status_callback("🎤 Streaming audio...")
            return True
        except Exception as e:
            if status_callback:
                status_callback(f"❌ Audio stream error: {str(e)}")
            self.stop_streaming()
            return False

    def _send_loop(self):
        """Continuously reads audio chunks and sends to server."""
        # compute ideal sleep per chunk based on sample params:
        chunk_duration = float(AUDIO_CHUNK) / float(AUDIO_RATE)  # seconds
        try:
            while self.running:
                loop_start = time.time()
                try:
                    audio_data = self.stream_in.read(AUDIO_CHUNK, exception_on_overflow=False)
                except IOError:
                    # Overflows happen under load; skip this chunk
                    audio_data = None
                except Exception as e:
                    print(f"AudioClient Send read error: {e}")
                    audio_data = None

                if audio_data:
                    packet = pack_message(STREAM_AUDIO, audio_data)
                    try:
                        self.send_sock.sendto(packet, (self.server_ip, self.server_port))
                    except Exception:
                        # Ignore transient send errors
                        pass

                # Throttle to maintain consistent capture->send cadence
                elapsed = time.time() - loop_start
                sleep_time = max(0, chunk_duration - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)

        finally:
            # Ensure resources cleaned when send loop exits
            self.stop_streaming()

    # --- Receiver Logic (Playback) ---
    
    def start_receiving(self):
        """Initializes playback stream and starts receiver thread."""
        try:
            if not self.audio:
                self.audio = pyaudio.PyAudio()

            # Output stream
            self.stream_out = self.audio.open(
                format=AUDIO_FORMAT,
                channels=AUDIO_CHANNELS,
                rate=AUDIO_RATE,
                output=True,
                frames_per_buffer=AUDIO_CHUNK
            )
            
            self.recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, UDP_STREAM_BUFFER)
            self.recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # bind to ephemeral port so server can send to us
            self.recv_sock.bind(('', 0))
            self.recv_sock.settimeout(CONNECTION_TIMEOUT)
            
            self.running = True
            self._register_receiver()
            self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            self.recv_thread.start()
        except Exception as e:
            print(f"AudioClient Recv Setup Error: {e}")
            self.stop_streaming()

    def _register_receiver(self):
        """Sends registration packet to the server's audio port."""
        register_packet = pack_message(CMD_REGISTER, b"AUDIO")
        for _ in range(3):
            try:
                self.recv_sock.sendto(register_packet, (self.server_ip, self.server_port))
            except Exception as e:
                print(f"AudioClient Registration Error: {e}")
            time.sleep(0.05)

    def _recv_loop(self):
        """Continuously receives mixed audio and plays it back."""
        while self.running:
            try:
                data, addr = self.recv_sock.recvfrom(UDP_STREAM_BUFFER)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
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
                        self.stream_out.write(payload)
                except Exception as e:
                    # ignore bursts/underruns
                    # print(f"AudioClient Playback error: {e}")
                    pass

    # --- Cleanup ---

    def stop_streaming(self):
        """Cleans up all audio resources and closes sockets."""
        self.running = False
        
        # Close send socket
        if self.send_sock:
            try:
                self.send_sock.close()
            except:
                pass
            self.send_sock = None

        # Close recv socket
        if self.recv_sock:
            try:
                self.recv_sock.close()
            except:
                pass
            self.recv_sock = None

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
