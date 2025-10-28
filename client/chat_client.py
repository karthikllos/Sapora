"""
Sapora LAN Collaboration Suite - Chat Client (Optimized)
Handles TCP control, registration, user list updates, and chat messages.
"""

import threading
import socket
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

    def __init__(self, server_ip, server_port, username, meeting_id: str = 'default'):
        self.server_ip = server_ip
        self.server_port = server_port
        self.username = username
        self.meeting_id = meeting_id

        self.running = False
        self.sock = None

        # UI callbacks
        self.user_list_callback = None
        self.message_callback = None

        # Lock for thread-safe send
        self.send_lock = threading.Lock()

    def set_callbacks(self, user_list_cb, message_cb):
        """Sets callbacks for user list and message updates."""
        self.user_list_callback = user_list_cb
        self.message_callback = message_cb

    def connect(self):
        """Establishes TCP connection and registers with the server."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(CONNECTION_TIMEOUT)
            self.sock.connect((self.server_ip, self.server_port))

            # Register username + meeting_id
            reg_payload = json.dumps({'username': self.username, 'meeting_id': self.meeting_id})
            reg_packet = pack_message(CMD_REGISTER, reg_payload.encode('utf-8'))
            self.sock.sendall(reg_packet)

            self.running = True
            threading.Thread(target=self._listen_loop, daemon=True).start()
            return True

        except Exception as e:
            print(f"[ChatClient] Connection Error: {e}")
            self.disconnect()
            return False

    def send_message(self, text):
        """Sends a formatted chat message."""
        if not self.running or not self.sock:
            return False

        try:
            formatted = f"{self.username}: {text}"
            packet = pack_message(MSG_CHAT, formatted.encode('utf-8'))
            with self.send_lock:
                self.sock.sendall(packet)
            return True

        except Exception as e:
            print(f"[ChatClient] Send Error: {e}")
            self.disconnect()
            return False

    def _listen_loop(self):
        """Continuously listens for incoming messages."""
        while self.running:
            try:
                raw = read_tcp_message(self.sock)
                if not raw:
                    break

                version, msg_type, _, _, payload = unpack_message(raw)

                if msg_type == MSG_CHAT:
                    self._handle_chat(payload)
                elif msg_type == CMD_USER_LIST:
                    self._handle_user_list(payload)
                elif msg_type == CMD_HEARTBEAT:
                    continue  # keep-alive
                elif msg_type == CMD_DISCONNECT:
                    print("[ChatClient] Server requested disconnect.")
                    break
                else:
                    print(f"[ChatClient] Unknown message type: {msg_type}")

            except (ConnectionResetError, OSError):
                break
            except Exception as e:
                print(f"[ChatClient] Listen Error: {e}")
                continue

        self.disconnect()

    def _handle_chat(self, payload):
        """Handles an incoming chat message."""
        try:
            msg = payload.decode('utf-8', errors='ignore')
            sender, text = (msg.split(':', 1) + [""])[:2] if ':' in msg else ("SYSTEM", msg)
            if self.message_callback:
                self.message_callback(sender.strip(), text.strip())
        except Exception as e:
            print(f"[ChatClient] Chat Decode Error: {e}")

    def _handle_user_list(self, payload):
        """Handles updated user list from the server."""
        try:
            user_list = json.loads(payload.decode('utf-8'))
            if self.user_list_callback:
                self.user_list_callback(user_list)
        except Exception as e:
            print(f"[ChatClient] User List Decode Error: {e}")

    def disconnect(self):
        """Cleanly disconnects from server."""
        if not self.sock:
            return
        try:
            self.running = False
            packet = pack_message(CMD_DISCONNECT)
            with self.send_lock:
                self.sock.sendall(packet)
        except:
            pass
        finally:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None
            print("[ChatClient] Disconnected cleanly.")
