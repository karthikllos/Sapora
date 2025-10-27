"""
Sapora LAN Collaboration Suite - Control Server (Optimized)
Handles TCP control, registration, heartbeats, chat, and disconnects.
"""

import threading
import socket
import json
import sys
import os

# Add parent path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.constants import CONTROL_PORT, SOCKET_TIMEOUT
from shared.protocol import CMD_REGISTER, CMD_HEARTBEAT, CMD_DISCONNECT, MSG_CHAT
from server.utils import read_tcp_message, unpack_message, pack_message, get_message_type_name


class TCPHandler(threading.Thread):
    """Handles one TCP client connection."""

    def __init__(self, manager, client_socket, address):
        super().__init__(daemon=True)
        self.manager = manager
        self.sock = client_socket
        self.address = address
        self.ip, self.port = address
        self.username = "Unknown"
        self.running = True

        self.sock.settimeout(SOCKET_TIMEOUT)
        self.manager.add_client(self.sock, self.address)

    def run(self):
        print(f"[TCPHandler] Started for {self.ip}:{self.port}")

        try:
            while self.manager.running and self.running:
                raw = read_tcp_message(self.sock)
                if not raw:
                    break

                version, msg_type, _, _, payload = unpack_message(raw)
                self.manager.update_client_status(self.sock)

                if msg_type == CMD_REGISTER:
                    self._handle_register(payload)
                elif msg_type == MSG_CHAT:
                    self._handle_chat(payload)
                elif msg_type == CMD_HEARTBEAT:
                    continue  # heartbeat, ignore
                elif msg_type == CMD_DISCONNECT:
                    print(f"[TCPHandler] {self.username} requested disconnect.")
                    break
                else:
                    print(f"[TCPHandler] Unknown message type: {get_message_type_name(msg_type)}")

        except socket.timeout:
            pass
        except ConnectionResetError:
            print(f"[TCPHandler] Client {self.username} disconnected abruptly.")
        except Exception as e:
            print(f"[TCPHandler] Error from {self.username}: {e}")
        finally:
            self._cleanup()

    def _handle_register(self, payload):
        """Registers client username."""
        try:
            data = json.loads(payload.decode('utf-8'))
            self.username = data.get('username', f"User-{self.port}")
            self.manager.update_client_status(self.sock, username=self.username)
            print(f"[TCPHandler] Registered: {self.username} ({self.ip})")
        except Exception as e:
            print(f"[TCPHandler] Registration Error: {e}")

    def _handle_chat(self, payload):
        """Broadcasts chat message to all clients."""
        try:
            msg = payload.decode('utf-8', errors='ignore')
            print(f"[Chat] {self.username}: {msg}")
            chat_packet = pack_message(MSG_CHAT, payload)

            disconnected = []
            with self.manager.control_clients_lock:
                for client_sock in list(self.manager.control_clients.keys()):
                    if client_sock != self.sock:
                        try:
                            client_sock.sendall(chat_packet)
                        except Exception:
                            disconnected.append(client_sock)

            # Cleanup disconnected clients
            for sock in disconnected:
                self.manager.remove_client(sock)

        except Exception as e:
            print(f"[TCPHandler] Chat Broadcast Error: {e}")

    def _cleanup(self):
        """Removes client from manager and closes socket."""
        if not self.running:
            return
        self.running = False
        self.manager.remove_client(self.sock)
        try:
            self.sock.close()
        except:
            pass
        print(f"[TCPHandler] Disconnected {self.username}.")


class ControlServer(threading.Thread):
    """Main TCP Control Server."""

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

            print(f"[ControlServer] Listening on TCP port {CONTROL_PORT}")

            while self.manager.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    handler = TCPHandler(self.manager, client_socket, address)
                    handler.start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.manager.running:
                        print(f"[ControlServer] Accept Error: {e}")

        except Exception as e:
            print(f"[ControlServer] Fatal Error: {e}")
        finally:
            self.stop()

    def stop(self):
        """Stops the control server."""
        try:
            if self.server_socket:
                self.server_socket.close()
        except:
            pass
        print("[ControlServer] Stopped cleanly.")
