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
        
        # File notification callback
        self.file_callback = None

    def set_callbacks(self, user_list_cb, message_cb):
        """Sets callbacks for user list and message updates."""
        self.user_list_callback = user_list_cb
        self.message_callback = message_cb
    
    def set_file_callback(self, file_cb):
        """Set callback for file availability notifications"""
        self.file_callback = file_cb

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

    def send_message(self, text, target: str = 'all'):
        """Sends a chat message; supports target ('all' or username')."""
        if not self.running or not self.sock:
            return False

        try:
            try:
                payload_obj = {
                    'sender': self.username,
                    'target': target or 'all',
                    'text': text,
                    'meeting_id': getattr(self, 'meeting_id', None)
                }
                payload = json.dumps(payload_obj).encode('utf-8')
            except Exception:
                payload = f"{self.username}: {text}".encode('utf-8')
            packet = pack_message(MSG_CHAT, payload)
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
                    # Try file notify compatibility
                    try:
                        from shared.protocol import FILE_NOTIFY_AVAILABLE
                        if msg_type == FILE_NOTIFY_AVAILABLE:
                            self._handle_file_notify(payload)
                            continue
                    except Exception:
                        pass
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
            raw = payload.decode('utf-8', errors='ignore')
            try:
                obj = json.loads(raw)
                # Filter by target if present
                target = (obj.get('target') or 'all') if isinstance(obj, dict) else 'all'
                if target.lower() != 'all' and target != self.username:
                    return
                if obj.get('type') == 'file_announce':
                    # Deliver file announce to intended recipients only
                    if self.file_callback:
                        self.file_callback(obj)
                    return
                sender = obj.get('sender', 'SYSTEM')
                text = obj.get('text', raw)
                # Annotate private messages
                if target.lower() != 'all':
                    text = f"(to {target}) {text}"
            except Exception:
                msg = raw
                sender, text = (msg.split(':', 1) + [""])[:2] if ':' in msg else ("SYSTEM", msg)
            if self.message_callback:
                self.message_callback(sender.strip(), text.strip())
        except Exception as e:
            print(f"[ChatClient] Chat Decode Error: {e}")
    
    def _handle_file_notify(self, payload):
        try:
            raw = payload.decode('utf-8', errors='ignore')
            obj = json.loads(raw)
            # Filter by target on file notify, if present
            target = obj.get('target') or 'all'
            if target.lower() != 'all' and target != self.username:
                return
            if self.file_callback:
                self.file_callback(obj)
        except Exception as e:
            print(f"[ChatClient] File notify decode error: {e}")
    
    def send_file_announce(self, filename, target: str = 'all'):
        try:
            obj = {
                'type': 'file_announce',
                'filename': filename,
                'sender': self.username,
                'target': target or 'all',
                'meeting_id': getattr(self, 'meeting_id', None)
            }
            payload = json.dumps(obj).encode('utf-8')
            packet = pack_message(MSG_CHAT, payload)
            with self.send_lock:
                self.sock.sendall(packet)
            return True
        except Exception as e:
            print(f"[ChatClient] File announce send error: {e}")
            return False

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
