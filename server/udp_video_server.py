"""
Sapora LAN Collaboration Suite - UDP Video Server
Receives video streams and broadcasts them to all registered video listeners.
"""
import threading
import socket
import time

# Import constants/protocol/utils
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.constants import UDP_STREAM_BUFFER, VIDEO_PORT, SOCKET_TIMEOUT
from shared.protocol import STREAM_VIDEO
from server.utils import unpack_message, get_message_type_name

class UDPVideoServer(threading.Thread):
    """Handles incoming and outgoing UDP video streams."""
    
    def __init__(self, manager):
        super().__init__(daemon=True)
        self.manager = manager
        self.sock = None
        
    def run(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, UDP_STREAM_BUFFER)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, UDP_STREAM_BUFFER)
            self.sock.bind(('0.0.0.0', VIDEO_PORT))
            self.sock.settimeout(SOCKET_TIMEOUT)
            
            print(f"UDPVideoServer: Listening on UDP port {VIDEO_PORT}")
            
            while self.manager.running:
                try:
                    # Receive video frame
                    data, sender_addr = self.sock.recvfrom(UDP_STREAM_BUFFER)
                    
                    # Update client registration (sender is also a potential receiver)
                    self.manager.register_stream('video', sender_addr)

                    # Quick protocol check
                    try:
                        version, msg_type, payload_length, seq_num, payload = unpack_message(data)
                        if msg_type != STREAM_VIDEO:
                             continue # Ignore non-video packets
                    except ValueError:
                         continue # Ignore malformed packets

                    # Broadcast the raw packet (header + payload) to all listeners
                    self._broadcast_frame(data, sender_addr)
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.manager.running:
                        print(f"UDPVideoServer: Error: {e}")
                        
        except Exception as e:
            print(f"UDPVideoServer: Fatal error: {e}")
        finally:
            self.stop()

    def _broadcast_frame(self, frame_data, sender_addr):
        """Sends the frame to all clients registered for video listening."""
        listeners = self.manager.get_video_listeners()
        
        for listener_addr in listeners:
            # Do not send back to the sender
            if listener_addr == sender_addr:
                continue
                
            try:
                self.sock.sendto(frame_data, listener_addr)
            except Exception:
                # In a real app, track dropped packets or remove stale listener here.
                pass 
                
    def stop(self):
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        print("UDPVideoServer: Server stopped.")