"""
Sapora LAN Collaboration Suite - Chat Client (FIXED)
Handles TCP control, registration, user list updates, and chat messages.
"""

import threading
import socket
import json
import sys
import os
import time

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
        self.file_callback = None

        # Lock for thread-safe send
        self.send_lock = threading.Lock()

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
            
            print(f"[ChatClient] Connected and registered as '{self.username}' in room '{self.meeting_id}'")

            self.running = True
            threading.Thread(target=self._listen_loop, daemon=True).start()
            return True

        except Exception as e:
            print(f"[ChatClient] Connection Error: {e}")
            self.disconnect()
            return False

    def _attempt_reconnect(self, attempts: int = 3, backoff: float = 1.5):
        """Try to reconnect and re-register with exponential backoff."""
        for i in range(attempts):
            try:
                time.sleep(backoff ** i)
                print(f"[ChatClient] Reconnecting... attempt {i+1}/{attempts}")
                if self.connect():
                    print("[ChatClient] Reconnected")
                    return True
            except Exception:
                pass
        print("[ChatClient] Reconnect failed")
        return False

    def send_message(self, text, target: str = 'all'):
        """Sends a chat message with proper JSON structure."""
        if not self.running or not self.sock:
            print(f"[ChatClient] Cannot send: not connected")
            return False

        try:
            # Create properly structured JSON payload
            payload_obj = {
                'sender': self.username,
                'target': target if target else 'all',
                'text': text,
                'meeting_id': self.meeting_id,
                'timestamp': time.time()
            }
            
            payload = json.dumps(payload_obj).encode('utf-8')
            packet = pack_message(MSG_CHAT, payload)
            
            with self.send_lock:
                self.sock.sendall(packet)
            
            if os.environ.get('SAPORA_DEBUG'):
                print(f"[ChatClient] Sent message to '{target}': {text[:50]}...")
            return True

        except Exception as e:
            print(f"[ChatClient] Send Error: {e}")
            self.disconnect()
            return False

    def send_file_announce(self, filename, target: str = 'all'):
        """Announces file availability to target users."""
        try:
            obj = {
                'type': 'file_announce',
                'filename': filename,
                'sender': self.username,
                'target': target if target else 'all',
                'meeting_id': self.meeting_id,
                'timestamp': time.time()
            }
            payload = json.dumps(obj).encode('utf-8')
            packet = pack_message(MSG_CHAT, payload)
            
            with self.send_lock:
                self.sock.sendall(packet)
            
            print(f"[ChatClient] Announced file '{filename}' to {target}")
            return True
        except Exception as e:
            print(f"[ChatClient] File announce error: {e}")
            return False

    def _listen_loop(self):
        """Continuously listens for incoming messages."""
        while self.running:
            try:
                raw = read_tcp_message(self.sock)
                if not raw:
                    print("[ChatClient] Connection closed by server")
                    if not self._attempt_reconnect():
                        break

                version, msg_type, _, _, payload = unpack_message(raw)

                if msg_type == MSG_CHAT:
                    self._handle_chat(payload)
                elif msg_type == CMD_USER_LIST:
                    self._handle_user_list(payload)
                elif msg_type == CMD_HEARTBEAT:
                    continue
                elif msg_type == CMD_DISCONNECT:
                    print("[ChatClient] Server requested disconnect")
                    break
                else:
                    # Try file notify
                    try:
                        from shared.protocol import FILE_NOTIFY_AVAILABLE
                        if msg_type == FILE_NOTIFY_AVAILABLE:
                            self._handle_file_notify(payload)
                            continue
                    except Exception:
                        pass

            except (ConnectionResetError, OSError) as e:
                if os.environ.get('SAPORA_DEBUG'):
                    print(f"[ChatClient] Connection error: {e}")
                break
            except Exception as e:
                if os.environ.get('SAPORA_DEBUG'):
                    print(f"[ChatClient] Listen Error: {e}")
                continue

        self.disconnect()

    def _handle_chat(self, payload):
        """Handles an incoming chat message with enhanced filtering."""
        try:
            raw = payload.decode('utf-8', errors='ignore')
            
            try:
                obj = json.loads(raw)
                sender = obj.get('sender', 'SYSTEM')
                text = obj.get('text', '')
                target = obj.get('target', 'all')
                msg_type = obj.get('type', '')
                
                # Handle file announcements separately
                if msg_type == 'file_announce':
                    if target.lower() == 'all' or target == self.username:
                        if self.file_callback:
                            self.file_callback(obj)
                    return
                
                # Skip delivery confirmations (internal messages)
                if msg_type == 'delivery_confirm':
                    return
                
                # Filter messages: only show if we're the target or it's broadcast
                if target.lower() not in ['all', 'everyone']:
                    if target != self.username and sender != self.username:
                        # This is a private message for someone else
                        if os.environ.get('SAPORA_DEBUG'):
                            print(f"[ChatClient] Filtered message from {sender} to {target}")
                        return
                
                # Add annotation for private messages
                if target.lower() not in ['all', 'everyone']:
                    if sender == self.username:
                        text = f"(to {target}) {text}"
                    else:
                        text = f"(private) {text}"
                
                if self.message_callback:
                    self.message_callback(sender.strip(), text.strip())
                    
            except json.JSONDecodeError:
                # Fallback for legacy messages
                if ':' in raw:
                    sender, text = raw.split(':', 1)
                else:
                    sender = "SYSTEM"
                    text = raw
                
                if self.message_callback:
                    self.message_callback(sender.strip(), text.strip())
                    
        except Exception as e:
            if os.environ.get('SAPORA_DEBUG'):
                print(f"[ChatClient] Chat decode error: {e}")
    
    def _handle_file_notify(self, payload):
        """Handles file availability notifications."""
        try:
            raw = payload.decode('utf-8', errors='ignore')
            obj = json.loads(raw)
            target = obj.get('target', 'all')
            
            # Filter by target
            if target.lower() not in ['all', 'everyone'] and target != self.username:
                return
            
            if self.file_callback:
                self.file_callback(obj)
        except Exception as e:
            print(f"[ChatClient] File notify decode error: {e}")

    def _handle_user_list(self, payload):
        """Handles updated user list from the server."""
        try:
            user_list = json.loads(payload.decode('utf-8'))
            if os.environ.get('SAPORA_DEBUG'):
                print(f"[ChatClient] Received user list: {len(user_list)} users")
            
            if self.user_list_callback:
                self.user_list_callback(user_list)
        except Exception as e:
            print(f"[ChatClient] User list decode error: {e}")

    def disconnect(self):
        """Cleanly disconnects from server."""
        if not self.sock:
            return
        
        self.running = False
        try:
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
            print("[ChatClient] Disconnected")