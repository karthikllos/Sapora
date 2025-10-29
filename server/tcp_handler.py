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
from server.utils import read_tcp_message, unpack_message, pack_message, get_message_type_name, broadcast_room_user_list


class TCPHandler(threading.Thread):
    """Handles one TCP client connection."""

    def __init__(self, manager, client_socket, address, server=None):
        super().__init__(daemon=True)
        self.manager = manager
        self.server = server  # Reference to SaporaServer for room logic
        self.sock = client_socket
        self.address = address
        self.ip, self.port = address
        self.username = "Unknown"
        self.meeting_id = "default"
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
        """Registers client username and joins room if provided."""
        try:
            data = json.loads(payload.decode('utf-8'))
            self.username = data.get('username', f"User-{self.port}")
            self.meeting_id = data.get('meeting_id', 'default')
            # Update manager state with username and room for UDP room-based routing
            self.manager.update_client_status(self.sock, username=self.username)
            try:
                # Ensure room is set so get_room_by_ip works for UDP servers
                if hasattr(self.manager, 'set_client_room'):
                    self.manager.set_client_room(self.sock, self.meeting_id)
                else:
                    self.manager.update_client_status(self.sock, room=self.meeting_id)
            except Exception:
                pass
            print(f"[TCPHandler] Registered: {self.username} ({self.ip}) in room '{self.meeting_id}'")
            
            # Join room in server rooms map
            if self.server:
                with self.server.rooms_lock:
                    room = self.server.rooms.setdefault(self.meeting_id, {'clients': [], 'participants': {}, 'metadata': {}})
                    if self.sock not in room['clients']:
                        room['clients'].append(self.sock)
                    room['participants'][self.username] = self.sock
                    self.server.client_rooms[self.sock] = self.meeting_id
                # notify room members
                broadcast_room_user_list(self.server, self.meeting_id)
        except Exception as e:
            print(f"[TCPHandler] Registration Error: {e}")

    def _handle_chat(self, payload):
        """Broadcasts/unicasts chat message within the same room based on target."""
        try:
            raw = payload.decode('utf-8', errors='ignore')
            target_username = None
            
            print(f"[TCPHandler] Received chat from {self.username}: {raw[:100]}")
            
            try:
                obj = json.loads(raw)
                # Normalize fields and preserve JSON payload on the wire
                if 'sender' not in obj or not obj.get('sender'):
                    obj['sender'] = self.username
                if 'meeting_id' not in obj or not obj.get('meeting_id'):
                    obj['meeting_id'] = self.meeting_id
                
                target_username = obj.get('target', 'all')
                print(f"[TCPHandler] Parsed target: '{target_username}'")
                
                chat_packet = pack_message(MSG_CHAT, json.dumps(obj).encode('utf-8'))
            except json.JSONDecodeError:
                # Legacy mode: relay as-is to room
                print(f"[TCPHandler] Non-JSON message, broadcasting to all in room")
                chat_packet = pack_message(MSG_CHAT, payload)
                target_username = 'all'

            if self.server:
                with self.server.rooms_lock:
                    room = self.server.rooms.get(self.meeting_id)
                    if not room:
                        print(f"[ROOM: {self.meeting_id}] Room not found, skipping chat broadcast")
                        return
                    
                    participants = room.get('participants', {})
                    print(f"[ROOM: {self.meeting_id}] Room participants: {list(participants.keys())}")

                    # Determine targets
                    if target_username and target_username.lower() not in ['all', 'everyone']:
                        target_sock = participants.get(target_username)
                        if target_sock:
                            targets = [target_sock]
                            print(f"[ROOM: {self.meeting_id}] Private message to {target_username}")
                        else:
                            print(f"[ROOM: {self.meeting_id}] Target user '{target_username}' not found in room")
                            targets = []
                    else:
                        # Broadcast to all EXCEPT sender
                        targets = [s for s in room['clients'] if s and s != self.sock]
                        print(f"[ROOM: {self.meeting_id}] Broadcasting to {len(targets)} recipients (excluding sender)")
            else:
                # Fallback if no server reference
                with self.manager.control_clients_lock:
                    targets = [s for s in self.manager.control_clients.keys() if s != self.sock]
                    print(f"[TCPHandler] Broadcasting to {len(targets)} recipients (no room support)")

            # Send to targets
            sent_count = 0
            failed_count = 0
            for client_sock in list(targets):
                try:
                    if client_sock:
                        client_sock.sendall(chat_packet)
                        sent_count += 1
                except Exception as e:
                    print(f"[TCPHandler] Failed to send to client: {e}")
                    failed_count += 1
                    self.manager.remove_client(client_sock)
            
            print(f"[TCPHandler] Message delivery: {sent_count} sent, {failed_count} failed")
            
        except Exception as e:
            print(f"[TCPHandler] Chat Broadcast Error: {e}")
            import traceback
            traceback.print_exc()

    def _cleanup(self):
        """Removes client from manager and closes socket; leaves room."""
        if not self.running:
            return
        self.running = False
        self.manager.remove_client(self.sock)

        # Remove from room
        if self.server:
            with self.server.rooms_lock:
                room_id = self.server.client_rooms.pop(self.sock, None)
                if room_id and room_id in self.server.rooms:
                    room = self.server.rooms[room_id]
                    if self.sock in room['clients']:
                        room['clients'].remove(self.sock)
                    # remove from participants mapping
                    try:
                        for uname, s in list(room.get('participants', {}).items()):
                            if s == self.sock:
                                del room['participants'][uname]
                                break
                    except Exception:
                        pass
                    # broadcast updated list
                    broadcast_room_user_list(self.server, room_id)
                    # delete empty room
                    if not room['clients']:
                        del self.server.rooms[room_id]
                        print(f"[Rooms] Removed empty room '{room_id}'")

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
                    handler = TCPHandler(self.manager, client_socket, address, server=self.manager.server_ref if hasattr(self.manager, 'server_ref') else None)
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
