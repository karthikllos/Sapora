"""
Sapora LAN Collaboration Suite - UDP Audio Server
Receives audio streams, mixes them, and broadcasts the mixed audio back.
"""
import threading
import socket
import time
from collections import deque

# Import constants/protocol/utils
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.constants import UDP_STREAM_BUFFER, AUDIO_PORT, SOCKET_TIMEOUT, AUDIO_CHUNK
from shared.protocol import STREAM_AUDIO
from server.utils import unpack_message, pack_message, mix_audio_chunks

class UDPAudioServer(threading.Thread):
    """Handles incoming and outgoing UDP audio streams with mixing."""
    
    def __init__(self, manager):
        super().__init__(daemon=True)
        self.manager = manager
        self.sock = None
        self.audio_buffers = {} # {addr: deque of audio chunks}
        self.buffers_lock = threading.Lock()
        self.mix_interval = 0.02 # 20ms mix cycle
        
        self.mixer_thread = threading.Thread(target=self._audio_mixer, daemon=True)

    def run(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, UDP_STREAM_BUFFER)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, UDP_STREAM_BUFFER)
            self.sock.bind(('0.0.0.0', AUDIO_PORT))
            self.sock.settimeout(SOCKET_TIMEOUT)
            
            print(f"UDPAudioServer: Listening on UDP port {AUDIO_PORT}")
            self.mixer_thread.start()
            
            while self.manager.running:
                try:
                    # Receive audio packet
                    data, sender_addr = self.sock.recvfrom(UDP_STREAM_BUFFER)
                    
                    # Update client registration (sender is also a potential receiver)
                    self.manager.register_stream('audio', sender_addr)

                    # Extract audio data and buffer it
                    self._handle_incoming_chunk(data, sender_addr)
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.manager.running:
                        print(f"UDPAudioServer: Error: {e}")
                        
        except Exception as e:
            print(f"UDPAudioServer: Fatal error: {e}")
        finally:
            self.stop()
            
    def _handle_incoming_chunk(self, data, sender_addr):
        """Extracts audio payload and buffers it for mixing."""
        try:
            version, msg_type, payload_length, seq_num, audio_data = unpack_message(data)
            
            if msg_type != STREAM_AUDIO:
                return

            with self.buffers_lock:
                if sender_addr not in self.audio_buffers:
                    # Maxlen ensures buffer does not grow indefinitely 
                    # (10 chunks * 20ms/chunk = 200ms buffer)
                    self.audio_buffers[sender_addr] = deque(maxlen=10) 
                
                self.audio_buffers[sender_addr].append(audio_data)

        except ValueError:
            # Malformed packet
            pass 
        
    def _audio_mixer(self):
        """Mixes and broadcasts audio chunks periodically."""
        print("UDPAudioServer: Mixer thread started.")
        while self.manager.running:
            time.sleep(self.mix_interval)
            
            # --- 1. Collect Chunks ---
            chunks_to_mix = []
            clients_to_send = []
            
            with self.buffers_lock:
                for addr, buffer in list(self.audio_buffers.items()):
                    if buffer:
                        # Grab the oldest chunk from the buffer
                        chunk = buffer.popleft() 
                        chunks_to_mix.append((addr, chunk))
                        clients_to_send.append(addr)
                    
            if len(chunks_to_mix) < 1:
                continue

            # --- 2. Mix and Broadcast ---
            
            # Use the registered listeners as targets
            targets = self.manager.get_audio_listeners()

            for target_addr in targets:
                # Mix audio from all sources *except* the target client's own IP
                # (Mixing only happens if there's at least one other source)
                sources_for_mix = [(addr, chunk) for addr, chunk in chunks_to_mix if addr != target_addr]
                
                mixed_audio = mix_audio_chunks([chunk for _, chunk in sources_for_mix])
                
                if mixed_audio:
                    # Pack mixed audio
                    packet = pack_message(STREAM_AUDIO, mixed_audio)
                    try:
                        self.sock.sendto(packet, target_addr)
                    except Exception:
                        pass # Ignore send errors

    def stop(self):
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        self.manager.running = False
        print("UDPAudioServer: Server stopped.")