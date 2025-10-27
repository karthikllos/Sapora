"""
Sapora LAN Collaboration Suite - Chat Client
Handles TCP control, registration, user list updates, and chat messages.
"""
import threading
import socket
import time
import json
import sys
import os

# Add parent path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.constants import CONTROL_PORT, BUFFER_SIZE, CONNECTION_TIMEOUT
from shared.protocol import CMD_REGISTER, CMD_HEARTBEAT, CMD_USER_LIST, MSG_CHAT, CMD_DISCONNECT
from client.utils import pack_message, unpack_message, read_tcp_message

class ChatClient:
    """Handles TCP-based control and chat communication."""

    def __init__(self, server_ip, server_port, username):
        self.server_ip = server_ip
        self.server_port = server_port
        self.username = username
        
        self.running = False
        self.sock = None
        
        self.user_list_callback = None
        self.message_callback = None

    def set_callbacks(self, user_list_cb, message_cb):
        """Sets thread-safe callbacks for UI updates."""
        self.user_list_callback = user_list_cb
        self.message_callback = message_cb

    def connect(self):
        """Establishes TCP connection and registers with the server."""
        try:
            print(f"[DEBUG ChatClient] Creating socket...")
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            print(f"[DEBUG ChatClient] Setting timeout to {CONNECTION_TIMEOUT}...")
            self.sock.settimeout(CONNECTION_TIMEOUT)
            print(f"[DEBUG ChatClient] Attempting to connect to {self.server_ip}:{self.server_port}...")
            self.sock.connect((self.server_ip, self.server_port))
            print(f"[DEBUG ChatClient] TCP connection established!")
            
            # 1. Send initial registration payload (JSON)
            print(f"[DEBUG ChatClient] Preparing registration packet for username: {self.username}")
            reg_payload = json.dumps({'username': self.username})
            print(f"[DEBUG ChatClient] Registration payload: {reg_payload}")
            reg_packet = pack_message(CMD_REGISTER, reg_payload.encode('utf-8'))
            print(f"[DEBUG ChatClient] Registration packet size: {len(reg_packet)} bytes")
            print(f"[DEBUG ChatClient] Sending registration packet...")
            self.sock.sendall(reg_packet)
            print(f"[DEBUG ChatClient] Registration packet sent successfully!")
            
            self.running = True
            print(f"[DEBUG ChatClient] Starting listen thread...")
            threading.Thread(target=self._listen_loop, daemon=True).start()
            print(f"[DEBUG ChatClient] Listen thread started, returning True")
            return True
            
        except Exception as e:
            print(f"[DEBUG ChatClient] EXCEPTION in connect(): {type(e).__name__}: {e}")
            print(f"ChatClient Connection Error: {e}")
            import traceback
            traceback.print_exc()
            self.disconnect()
            return False

    def disconnect(self):
        """Sends disconnect signal and closes the connection."""
        self.running = False
        if self.sock:
            try:
                # Send disconnect command
                disconnect_packet = pack_message(CMD_DISCONNECT)
                self.sock.sendall(disconnect_packet)
                self.sock.close()
            except:
                pass
            self.sock = None

    def send_message(self, text):
        """Sends a formatted chat message."""
        if not self.running or not self.sock:
            return False
            
        try:
            # Format: "Username: Message Text"
            formatted_message = f"{self.username}: {text}"
            message_packet = pack_message(MSG_CHAT, formatted_message.encode('utf-8'))
            self.sock.sendall(message_packet)
            return True
        except Exception as e:
            print(f"ChatClient Send Error: {e}")
            self.disconnect()
            return False

    def _listen_loop(self):
        """Continuously listens for incoming control/chat messages."""
        print(f"[DEBUG ChatClient] _listen_loop STARTED")
        while self.running:
            try:
                print(f"[DEBUG ChatClient] Waiting for message...")
                raw_message = read_tcp_message(self.sock)
                print(f"[DEBUG ChatClient] read_tcp_message returned: {raw_message is not None}")
                
                if raw_message is None:
                    # Server closed connection or read failed
                    print(f"[DEBUG ChatClient] raw_message is None, breaking listen loop")
                    break
                
                print(f"[DEBUG ChatClient] Unpacking message of length {len(raw_message)}...")
                version, msg_type, _, _, payload = unpack_message(raw_message)
                print(f"[DEBUG ChatClient] Message unpacked: type={msg_type}, payload_len={len(payload)}")
                
                if msg_type == MSG_CHAT:
                    self._handle_chat_message(payload)
                elif msg_type == CMD_USER_LIST:
                    self._handle_user_list(payload)
                elif msg_type == CMD_HEARTBEAT:
                    # Heartbeat received, keep connection alive
                    pass
                elif msg_type == CMD_DISCONNECT:
                    # Server initiated disconnect
                    break
                else:
                    print(f"ChatClient: Unknown message type {msg_type}")

            except socket.timeout:
                print(f"[DEBUG ChatClient] Socket timeout in listen loop, continuing...")
                continue
            except Exception as e:
                print(f"[DEBUG ChatClient] EXCEPTION in listen loop: {type(e).__name__}: {e}")
                if self.running:
                    print(f"ChatClient Listen Error: {e}")
                    import traceback
                    traceback.print_exc()
                break
        
        print(f"[DEBUG ChatClient] Listen loop ended, calling disconnect()")
        self.disconnect()

    def _handle_chat_message(self, payload):
        """Calls the UI callback for received chat messages."""
        message_text = payload.decode('utf-8')
        
        # Extract sender's username
        if ":" in message_text:
            sender, text = message_text.split(":", 1)
        else:
            sender = "SYSTEM"
            text = message_text
            
        if self.message_callback:
            self.message_callback(sender.strip(), message_text.strip())

    def _handle_user_list(self, payload):
        """Calls the UI callback with the updated user list."""
        try:
            user_list_json = payload.decode('utf-8')
            user_list = json.loads(user_list_json)
            if self.user_list_callback:
                self.user_list_callback(user_list)
        except Exception as e:
            print(f"ChatClient User List Error: {e}")