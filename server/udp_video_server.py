"""
Sapora LAN Collaboration Suite - UDP Video Server
Receives video streams and broadcasts them to all registered video listeners.
"""
import threading
import socket
import time
import os

# Import constants/protocol/utils
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.constants import UDP_STREAM_BUFFER, VIDEO_PORT, SOCKET_TIMEOUT
from shared.protocol import STREAM_VIDEO, CMD_REGISTER
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
                    version, msg_type, payload_length, seq_num, payload = unpack_message(data)
                    if msg_type == STREAM_VIDEO:
                        # Broadcast the raw packet (header + payload) to all listeners
                        self._broadcast_frame(data, sender_addr)
                    elif msg_type == CMD_REGISTER:
                        # Handle registration with username/room info
                        try:
                            import json
                            reg_data = json.loads(payload.decode('utf-8'))
                            username = reg_data.get('username', 'Unknown')
                            room = reg_data.get('room', 'default')
                            # Update manager with username mapping
                            self.manager.update_client_status_by_ip(sender_addr[0], username=username, room=room)
                        except Exception:
                            pass
                except ValueError:
                    # Ignore malformed packets
                    continue
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
        """Sends the frame to all clients registered for video listening in the same room."""
        try:
            sender_ip = sender_addr[0]
            room = self.manager.get_room_by_ip(sender_ip)
            listeners = self.manager.get_video_listeners(room=room)
            
            # Only broadcast if we have listeners
            if not listeners:
                return
                
            # Send to all listeners except sender
            sent_count = 0
            failed_count = 0
            
            for listener_addr in listeners:
                # Do not send back to the sender
                if listener_addr == sender_addr:
                    continue
                    
                try:
                    self.sock.sendto(frame_data, listener_addr)
                    sent_count += 1
                except Exception as e:
                    failed_count += 1
                    # Remove stale listener
                    self.manager.unregister_stream('video', listener_addr)
            
            # Log stats only in debug mode
            if os.environ.get('SAPORA_DEBUG') and sent_count > 0:
                print(f"[UDPVideoServer] Broadcast: {sent_count} sent, {failed_count} failed to room '{room}'")
                
        except Exception as e:
            if os.environ.get('SAPORA_DEBUG'):
                print(f"[UDPVideoServer] Broadcast error: {e}") 
                
    def stop(self):
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        print("UDPVideoServer: Server stopped.")