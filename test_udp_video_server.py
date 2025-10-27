"""
Standalone UDP Video Server Test
Tests video broadcast functionality without full server infrastructure.
"""
import sys
import os
import socket
import time

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.constants import VIDEO_PORT, UDP_STREAM_BUFFER, SOCKET_TIMEOUT
from shared.protocol import STREAM_VIDEO, CMD_REGISTER
from server.utils import unpack_message

class SimpleVideoServer:
    """Simplified video server for testing."""
    
    def __init__(self):
        self.sock = None
        self.running = True
        self.clients = {}  # {ip: (ip, port)}
        
    def start(self):
        """Start the UDP video server."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, UDP_STREAM_BUFFER)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, UDP_STREAM_BUFFER)
            self.sock.bind(('0.0.0.0', VIDEO_PORT))
            self.sock.settimeout(SOCKET_TIMEOUT)
            
            print("=" * 70)
            print("UDP VIDEO SERVER TEST - STARTED")
            print("=" * 70)
            print(f"Listening on UDP port {VIDEO_PORT}")
            print(f"Waiting for video clients to connect...")
            print("Press Ctrl+C to stop\n")
            
            frame_count = 0
            last_report = time.time()
            
            while self.running:
                try:
                    data, sender_addr = self.sock.recvfrom(UDP_STREAM_BUFFER)
                    
                    # Parse message
                    try:
                        version, msg_type, payload_length, seq_num, payload = unpack_message(data)
                        
                        if msg_type == CMD_REGISTER:
                            # Client registering for video
                            self.clients[sender_addr[0]] = sender_addr
                            print(f"✓ Client registered: {sender_addr[0]}:{sender_addr[1]}")
                            print(f"  Total clients: {len(self.clients)}")
                            
                        elif msg_type == STREAM_VIDEO:
                            # Video frame received
                            frame_count += 1
                            
                            # Register sender if not already registered
                            if sender_addr[0] not in self.clients:
                                self.clients[sender_addr[0]] = sender_addr
                            
                            # Broadcast to all other clients
                            broadcast_count = 0
                            for client_ip, client_addr in self.clients.items():
                                if client_addr != sender_addr:
                                    try:
                                        self.sock.sendto(data, client_addr)
                                        broadcast_count += 1
                                    except Exception as e:
                                        print(f"✗ Broadcast error to {client_addr}: {e}")
                            
                            # Report stats every 2 seconds
                            if time.time() - last_report >= 2.0:
                                print(f"📹 Frames: {frame_count} | Clients: {len(self.clients)} | Last broadcast: {broadcast_count} recipients")
                                last_report = time.time()
                                
                    except ValueError as e:
                        print(f"✗ Malformed packet from {sender_addr}: {e}")
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"✗ Error: {e}")
                        
        except KeyboardInterrupt:
            print("\n\nShutting down...")
        except Exception as e:
            print(f"✗ Fatal error: {e}")
        finally:
            self.stop()
            
    def stop(self):
        """Stop the server."""
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        print("\n" + "=" * 70)
        print("UDP VIDEO SERVER - STOPPED")
        print("=" * 70)

if __name__ == '__main__':
    server = SimpleVideoServer()
    server.start()
