"""
Sapora LAN Collaboration Suite - UDP Audio Server (optimized)
Receives audio streams, mixes them, and broadcasts the mixed audio back.
Improvements:
 - bounded jitter buffers per client
 - precise mix interval loop
 - skip mixing when no sources available
 - safe send (ignore transient send errors)
 - periodic cleanup of stale clients
"""
import threading
import socket
import time
from collections import deque

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared.constants import UDP_STREAM_BUFFER, AUDIO_PORT, SOCKET_TIMEOUT, AUDIO_CHUNK
from shared.protocol import STREAM_AUDIO, CMD_REGISTER
from server.utils import unpack_message, pack_message, mix_audio_chunks

# How long to consider a client "active" since last packet (seconds)
CLIENT_TIMEOUT = 5.0

class UDPAudioServer(threading.Thread):
    """Handles incoming and outgoing UDP audio streams with mixing."""
    
    def __init__(self, manager):
        super().__init__(daemon=True)
        self.manager = manager
        self.sock = None
        
        # audio_buffers maps (ip,port) -> deque([audio_bytes, ...])
        # maxlen keeps buffer bounded. 10 * 20ms = 200ms
        self.audio_buffers = {}
        self.buffers_lock = threading.Lock()
        
        # Track last seen timestamp for clients for cleanup
        self.last_seen = {}
        self.last_seen_lock = threading.Lock()
        
        self.mix_interval = 0.02  # 20ms mix cycle
        self.running = False
        
        self.mixer_thread = threading.Thread(target=self._audio_mixer, daemon=True)

    def run(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, UDP_STREAM_BUFFER)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, UDP_STREAM_BUFFER)
            self.sock.bind(('0.0.0.0', AUDIO_PORT))
            self.sock.settimeout(SOCKET_TIMEOUT)
            
            print(f"UDPAudioServer: Listening on UDP port {AUDIO_PORT}")
            self.running = True
            self.mixer_thread.start()
            
            while self.running and getattr(self.manager, "running", True):
                try:
                    data, sender_addr = self.sock.recvfrom(UDP_STREAM_BUFFER)
                except socket.timeout:
                    # periodic cleanup of stale clients
                    self._cleanup_stale_clients()
                    continue
                except Exception as e:
                    if self.running:
                        print(f"UDPAudioServer: Receive error: {e}")
                    continue
                
                # Treat sender_addr as tuple (ip, port)
                self.manager.register_stream('audio', sender_addr)
                self._handle_incoming_chunk(data, sender_addr)
                        
        except Exception as e:
            print(f"UDPAudioServer: Fatal error: {e}")
        finally:
            self.stop()
            
    def _handle_incoming_chunk(self, data, sender_addr):
        """Extracts audio payload and buffers it for mixing."""
        try:
            version, msg_type, payload_length, seq_num, audio_data = unpack_message(data)
        except ValueError:
            # Malformed packet
            return
        
        if msg_type != STREAM_AUDIO:
            # Could be CMD_REGISTER, but registration handled elsewhere
            return

        key = tuple(sender_addr)
        now = time.time()
        with self.buffers_lock:
            if key not in self.audio_buffers:
                # maxlen bounds stored latency
                self.audio_buffers[key] = deque(maxlen=10) 
            self.audio_buffers[key].append(audio_data)
        with self.last_seen_lock:
            self.last_seen[key] = now

    def _audio_mixer(self):
        """Mixes and broadcasts audio chunks periodically."""
        print("UDPAudioServer: Mixer thread started.")
        next_tick = time.time()
        while self.running and getattr(self.manager, "running", True):
            next_tick += self.mix_interval
            # Collect one chunk per active source (if available)
            chunks_to_mix = []
            with self.buffers_lock:
                for key, buffer in list(self.audio_buffers.items()):
                    if buffer:
                        # pop left oldest chunk for lowest latency
                        chunk = buffer.popleft()
                        chunks_to_mix.append((key, chunk))
            # If no chunks available, just sleep until next cycle
            if not chunks_to_mix:
                # cleanup stale clients periodically
                self._cleanup_stale_clients()
                now = time.time()
                sleep_time = max(0, next_tick - now)
                time.sleep(sleep_time)
                continue

            # Targets are registered audio listeners (IP,port)
            targets = self.manager.get_audio_listeners()

            # Broadcast a mixed chunk tailored for each target (exclude their own audio)
            for target in list(targets):
                # target may be stored in manager as (ip,port) or similar; ensure tuple
                target_key = tuple(target)
                # Gather sources excluding the target IP:port
                sources_for_mix = [chunk for (addr, chunk) in chunks_to_mix if tuple(addr) != target_key]
                if not sources_for_mix:
                    # Nothing to mix for this target (only self audio) — optionally send silence or skip
                    continue

                try:
                    mixed_audio = mix_audio_chunks(sources_for_mix)
                except Exception as e:
                    # If mixing fails, skip this target
                    print(f"UDPAudioServer: mix error for {target}: {e}")
                    continue

                if not mixed_audio:
                    continue

                packet = pack_message(STREAM_AUDIO, mixed_audio)
                try:
                    self.sock.sendto(packet, target)
                except Exception:
                    # transient network errors: ignore and continue
                    pass

            # cleanup stale clients and throttle loop properly
            self._cleanup_stale_clients()
            now = time.time()
            sleep_time = max(0, next_tick - now)
            time.sleep(sleep_time)

    def _cleanup_stale_clients(self):
        """Remove clients that haven't been seen for CLIENT_TIMEOUT seconds."""
        cutoff = time.time() - CLIENT_TIMEOUT
        removed = []
        with self.last_seen_lock:
            for key, ts in list(self.last_seen.items()):
                if ts < cutoff:
                    removed.append(key)
                    del self.last_seen[key]
        if removed:
            with self.buffers_lock:
                for key in removed:
                    if key in self.audio_buffers:
                        del self.audio_buffers[key]
            # Also inform manager that these clients are gone (optional)
            for key in removed:
                try:
                    self.manager.unregister_stream('audio', key)
                except Exception:
                    pass

    def stop(self):
        self.running = False
        try:
            if self.sock:
                self.sock.close()
        except:
            pass
        print("UDPAudioServer: Server stopped.")
