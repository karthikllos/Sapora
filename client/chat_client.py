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
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(CONNECTION_TIMEOUT)
            self.sock.connect((self.server_ip, self.server_port))
            
            # 1. Send initial registration payload (JSON)
            reg_payload = json.dumps({'username': self.username})
            reg_packet = pack_message(CMD_REGISTER, reg_payload.encode('utf-8'))
            self.sock.sendall(reg_packet)
            
            self.running = True
            threading.Thread(target=self._listen_loop, daemon=True).start()
            return True
            
        except Exception as e:
            print(f"ChatClient Connection Error: {e}")
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
        while self.running:
            try:
                raw_message = read_tcp_message(self.sock)
                
                if raw_message is None:
                    # Server closed connection or read failed
                    break
                
                version, msg_type, _, _, payload = unpack_message(raw_message)
                
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
                continue
            except Exception as e:
                if self.running:
                    print(f"ChatClient Listen Error: {e}")
                break
        
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