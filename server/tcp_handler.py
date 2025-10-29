"""
Sapora LAN Collaboration Suite - Control Server (FIXED - Chat Delivery)
Handles TCP control, registration, heartbeats, chat, and disconnects.
CRITICAL FIX: Case-insensitive username matching for reliable message delivery
"""

import threading
import socket
import json
import sys
import os
import time

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
                try:
                    raw = read_tcp_message(self.sock)
                except socket.timeout:
                    # No data this interval; keep connection alive
                    continue
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
                    # CRITICAL FIX: Store username in original case but create lowercase map
                    room['participants'][self.username] = self.sock
                    self.server.client_rooms[self.sock] = self.meeting_id
                # notify room members
                broadcast_room_user_list(self.server, self.meeting_id)
        except Exception as e:
            print(f"[TCPHandler] Registration Error: {e}")

    def _handle_chat(self, payload):
        """
        CRITICAL FIX: Broadcasts/unicasts chat message with case-insensitive username matching.
        This ensures messages reach intended recipients regardless of case differences.
        """
        try:
            raw = payload.decode('utf-8', errors='ignore')
            target_username = None
            
            # Log in debug mode only
            if os.environ.get('SAPORA_DEBUG'):
                print(f"[TCPHandler] Chat from {self.username} ({self.ip}): {raw[:100]}")
            
            try:
                obj = json.loads(raw)
                # Normalize fields
                if 'sender' not in obj or not obj.get('sender'):
                    obj['sender'] = self.username
                if 'meeting_id' not in obj or not obj.get('meeting_id'):
                    obj['meeting_id'] = self.meeting_id
                
                target_username = obj.get('target', 'all')
                obj['timestamp'] = time.time()
                
                chat_packet = pack_message(MSG_CHAT, json.dumps(obj).encode('utf-8'))
            except json.JSONDecodeError:
                # Legacy mode: relay as-is to room
                chat_packet = pack_message(MSG_CHAT, payload)
                target_username = 'all'

            if not self.server:
                # Fallback if no server reference
                with self.manager.control_clients_lock:
                    targets = [s for s in self.manager.control_clients.keys() if s != self.sock]
                self._send_to_targets(targets, chat_packet, target_username)
                return

            with self.server.rooms_lock:
                room = self.server.rooms.get(self.meeting_id)
                if not room:
                    # Send error back to sender
                    error_msg = {
                        'sender': 'SYSTEM',
                        'target': self.username,
                        'text': f'Room "{self.meeting_id}" not found',
                        'timestamp': time.time(),
                        'meeting_id': self.meeting_id,
                        'type': 'error'
                    }
                    error_packet = pack_message(MSG_CHAT, json.dumps(error_msg).encode('utf-8'))
                    try:
                        self.sock.sendall(error_packet)
                    except:
                        pass
                    return
                
                participants = room.get('participants', {})

                # CRITICAL FIX: Case-insensitive username matching
                targets = []
                delivery_status = "unknown"
                
                if target_username and target_username.lower() not in ['all', 'everyone']:
                    # Unicast message - CASE INSENSITIVE LOOKUP
                    target_lower = str(target_username).strip().lower()
                    
                    # Create case-insensitive lookup map
                    participants_ci = {str(name).strip().lower(): (name, sock) 
                                      for name, sock in participants.items()}
                    
                    if target_lower in participants_ci:
                        original_name, target_sock = participants_ci[target_lower]
                        targets = [target_sock]
                        delivery_status = f"private to {original_name}"
                        
                        print(f"[TCPHandler] ✅ Unicast match: '{target_username}' -> '{original_name}' (socket: {target_sock.getpeername()})")
                    else:
                        # Target not found - send error back to sender
                        available_users = ', '.join(participants.keys())
                        error_msg = {
                            'sender': 'SYSTEM',
                            'target': self.username,
                            'text': f'User "{target_username}" not found. Available: {available_users}',
                            'timestamp': time.time(),
                            'meeting_id': self.meeting_id,
                            'type': 'error'
                        }
                        error_packet = pack_message(MSG_CHAT, json.dumps(error_msg).encode('utf-8'))
                        try:
                            self.sock.sendall(error_packet)
                        except:
                            pass
                        print(f"[TCPHandler] ❌ User not found: '{target_username}' in [{available_users}]")
                        return
                else:
                    # Broadcast to all EXCEPT sender
                    targets = [s for s in room['clients'] if s and s != self.sock]
                    delivery_status = f"broadcast to {len(targets)} recipients"
                    print(f"[TCPHandler] 📢 Broadcasting to {len(targets)} clients")

            # Send the actual message to targets
            self._send_to_targets(targets, chat_packet, delivery_status)
            
        except Exception as e:
            print(f"[TCPHandler] Chat Broadcast Error: {e}")
            if os.environ.get('SAPORA_DEBUG'):
                import traceback
                traceback.print_exc()

    def _send_to_targets(self, targets, chat_packet, delivery_status):
        """Helper to send message to targets and send delivery confirmation"""
        sent_count = 0
        failed_count = 0
        failed_sockets = []
        
        for client_sock in list(targets):
            try:
                if client_sock:
                    client_sock.sendall(chat_packet)
                    sent_count += 1
                    if os.environ.get('SAPORA_DEBUG'):
                        print(f"[TCPHandler] ✅ Sent to {client_sock.getpeername()}")
            except Exception as e:
                failed_count += 1
                failed_sockets.append(client_sock)
                if os.environ.get('SAPORA_DEBUG'):
                    print(f"[TCPHandler] ❌ Failed to send to socket: {e}")
        
        # Remove failed sockets
        for sock in failed_sockets:
            self.manager.remove_client(sock)
        
        # Send delivery confirmation to sender
        if sent_count > 0 or failed_count == 0:
            confirm_msg = {
                'sender': 'SYSTEM',
                'target': self.username,
                'text': f'✅ Message delivered: {delivery_status} (sent: {sent_count}, failed: {failed_count})',
                'timestamp': time.time(),
                'meeting_id': self.meeting_id,
                'type': 'delivery_confirm'
            }
        else:
            confirm_msg = {
                'sender': 'SYSTEM',
                'target': self.username,
                'text': f'❌ Message delivery failed: {delivery_status} (sent: {sent_count}, failed: {failed_count})',
                'timestamp': time.time(),
                'meeting_id': self.meeting_id,
                'type': 'error'
            }
        
        confirm_packet = pack_message(MSG_CHAT, json.dumps(confirm_msg).encode('utf-8'))
        try:
            self.sock.sendall(confirm_packet)
        except:
            pass
        
        print(f"[TCPHandler] 📊 Delivery stats: {sent_count} sent, {failed_count} failed - {delivery_status}")

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