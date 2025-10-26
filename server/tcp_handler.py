"""
Sapora LAN Collaboration Suite - Base TCP Handler
Handles all TCP control messages (Register, Heartbeat, Chat, Disconnect).
"""
import threading
import socket
import json
import time

# Import constants/protocol/utils
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.constants import BUFFER_SIZE, SOCKET_TIMEOUT
from shared.protocol import CMD_REGISTER, CMD_HEARTBEAT, CMD_DISCONNECT, MSG_CHAT
from server.utils import read_tcp_message, unpack_message, pack_message, get_message_type_name

class TCPHandler(threading.Thread):
    """Handles a single TCP client connection for control and chat."""
    
    def __init__(self, manager, client_socket, address):
        super().__init__(daemon=True)
        self.manager = manager
        self.sock = client_socket
        self.address = address
        self.ip = address[0]
        self.port = address[1]
        self.username = "Unknown"
        self.running = True
        
        self.sock.settimeout(SOCKET_TIMEOUT)
        self.manager.add_client(self.sock, self.address)
        
    def run(self):
        """Main loop to receive and process messages."""
        print(f"TCPHandler: Started for {self.ip}:{self.port}")

        try:
            while self.manager.running and self.running:
                raw_message = read_tcp_message(self.sock)
                
                if raw_message is None:
                    # Connection closed or error reading header/payload
                    break
                
                try:
                    version, msg_type, payload_length, seq_num, payload = unpack_message(raw_message)
                    
                    self.manager.update_client_status(self.sock)
                    
                    if msg_type == CMD_REGISTER:
                        self._handle_register(payload)
                    elif msg_type == MSG_CHAT:
                        self._handle_chat(payload)
                    elif msg_type == CMD_DISCONNECT:
                        self.running = False
                        print(f"TCPHandler: Received DISCONNECT from {self.username}.")
                        break
                    elif msg_type == CMD_HEARTBEAT:
                        # Heartbeat received, manager updated last_seen, nothing more to do
                        pass
                    else:
                        print(f"TCPHandler: Unknown message type {get_message_type_name(msg_type)} from {self.username}")
                        
                except ValueError as e:
                    # Protocol error (e.g., malformed packet)
                    print(f"TCPHandler: Protocol error from {self.ip}: {e}")
                    break
                except Exception as e:
                    # General error
                    print(f"TCPHandler: Error processing message from {self.username}: {e}")
                    break
                    
        except socket.timeout:
             # Regular timeout, continue loop
             pass
        except Exception as e:
            if self.running:
                print(f"TCPHandler: Connection error for {self.username} ({self.ip}): {e}")
        finally:
            self._cleanup()

    def _handle_register(self, payload):
        """Processes the initial registration payload."""
        try:
            data = json.loads(payload.decode('utf-8'))
            new_username = data.get('username', f"User-{self.port}")
            self.username = new_username
            self.manager.update_client_status(self.sock, username=new_username)
            print(f"TCPHandler: Registered {new_username} from {self.ip}")
        except Exception as e:
            print(f"TCPHandler: Failed to process registration payload: {e}")

    def _handle_chat(self, payload):
        """Broadcasts a received chat message to all other connected control clients."""
        try:
            message_text = payload.decode('utf-8')
            # Assuming message already contains username prefix (e.g., "User: Hello")
            print(f"Chat: [{self.username}] {message_text}")
            
            chat_packet = pack_message(MSG_CHAT, payload)
            
            # Broadcast to all other control clients
            disconnected = []
            with self.manager.control_clients_lock:
                for client_sock, info in self.manager.control_clients.items():
                    if client_sock != self.sock: # Don't echo back to sender
                        try:
                            client_sock.sendall(chat_packet)
                        except Exception:
                            disconnected.append(client_sock)
            
            # Clean up disconnected clients
            for sock in disconnected:
                self.manager.remove_client(sock)
                
        except Exception as e:
            print(f"TCPHandler: Error handling chat message: {e}")

    def _cleanup(self):
        """Removes client from manager on disconnect."""
        if self.running:
            self.running = False
            self.manager.remove_client(self.sock)
            print(f"TCPHandler: Cleaned up client {self.username}.")


class ControlServer(threading.Thread):
    """Main Control/Chat Server using TCP."""
    
    def __init__(self, manager):
        super().__init__(daemon=True)
        self.manager = manager
        self.server_socket = None
        
    def run(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', CONTROL_PORT))
            self.server_socket.listen(10)
            self.server_socket.settimeout(SOCKET_TIMEOUT)
            
            print(f"ControlServer: Listening on TCP port {CONTROL_PORT}")
            
            while self.manager.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    # Hand off client connection to a new TCPHandler thread
                    handler = TCPHandler(self.manager, client_socket, address)
                    handler.start()
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.manager.running:
                        print(f"ControlServer: Error accepting connection: {e}")
                        
        except Exception as e:
            print(f"ControlServer: Fatal error: {e}")
        finally:
            self.stop()
            
    def stop(self):
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        print("ControlServer: Server stopped.")