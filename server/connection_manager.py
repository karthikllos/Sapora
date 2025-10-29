"""
Sapora LAN Collaboration Suite - Connection Manager (FIXED)
Maintains state for all connected clients (TCP and UDP) and manages synchronization.
"""
import threading
import socket
import time
from datetime import datetime
# Import constants/protocol
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.constants import (
    HEARTBEAT_INTERVAL, VIDEO_PORT, AUDIO_PORT, CONTROL_PORT, 
    CONNECTION_TIMEOUT, SOCKET_TIMEOUT,CLIENT_IDLE_TIMEOUT
)
from shared.protocol import CMD_HEARTBEAT, CMD_USER_LIST, CMD_DISCONNECT
from server.utils import broadcast_user_list, pack_message

class ConnectionManager:
    """
    Central repository for tracking all client connections and state.
    """
    def __init__(self):
        self.running = True
        
        # TCP Control/Chat Clients: {socket: {'addr': (ip, port), 'username': str, 'last_seen': float, 'id': str, 'room': str}}
        self.control_clients = {}
        self.control_clients_lock = threading.Lock()
        
        # Back-reference to server for room management (set externally)
        self.server_ref = None
        
        # UDP Streaming Clients: {ip_str: {'video': (ip, port) | None, 'audio': (ip, port) | None, 'last_seen': float}}
        self.stream_clients = {}
        self.stream_clients_lock = threading.Lock()
        
        # Heartbeat Thread
        self.heartbeat_thread = threading.Thread(target=self._run_heartbeat, daemon=True)
        self.heartbeat_thread.start()

    # --- Client Management (TCP/Control) ---

    def add_client(self, client_socket, address, username="Unknown"):
        """Adds a new TCP client connection."""
        with self.control_clients_lock:
            client_id = f"{address[0]}:{address[1]}_{time.time()}"
            self.control_clients[client_socket] = {
                'addr': address,
                'username': username,
                'last_seen': time.time(),
                'id': client_id,
                'socket': client_socket,
                'room': 'default'
            }
            print(f"Manager: Client added: {username} from {address[0]}. Total: {len(self.control_clients)}")
            
        # Broadcast updated list
        broadcast_user_list(self)

    def remove_client(self, client_socket):
        """Removes a disconnected TCP client."""
        username = "Unknown"
        address = ("0.0.0.0", 0)
        
        with self.control_clients_lock:
            if client_socket in self.control_clients:
                client_info = self.control_clients.pop(client_socket)
                username = client_info['username']
                address = client_info['addr']
                
                try:
                    client_socket.close()
                except:
                    pass
                
                print(f"Manager: Client removed: {username} from {address[0]}. Total: {len(self.control_clients)}")
        
        # Also remove corresponding UDP streams if found
        with self.stream_clients_lock:
            if address[0] in self.stream_clients:
                 del self.stream_clients[address[0]]
        
        # Broadcast updated list
        if username != "Unknown":
            broadcast_user_list(self)
        
        return username, address

    def update_client_status(self, client_socket, username=None, room=None):
        """Updates client's last seen time and optionally username and room."""
        with self.control_clients_lock:
            if client_socket in self.control_clients:
                self.control_clients[client_socket]['last_seen'] = time.time()
                if username and self.control_clients[client_socket]['username'] == "Unknown":
                     self.control_clients[client_socket]['username'] = username
                     threading.Thread(target=lambda: broadcast_user_list(self), daemon=True).start()
                if room:
                     self.control_clients[client_socket]['room'] = room
                return True
            return False

    def update_client_status_by_ip(self, ip_address, username=None, room=None):
        """Updates client's status by IP address (for UDP registrations)."""
        with self.control_clients_lock:
            for sock, info in self.control_clients.items():
                if info['addr'][0] == ip_address:
                    info['last_seen'] = time.time()
                    if username and info['username'] == "Unknown":
                        info['username'] = username
                    if room:
                        info['room'] = room
                    return True
        return False

    def get_client_by_socket(self, client_socket):
        """Retrieves client info by socket."""
        with self.control_clients_lock:
            return self.control_clients.get(client_socket)
        
    def get_client_username_by_ip(self, ip_address):
        """Retrieves username by IP address."""
        with self.control_clients_lock:
            for info in self.control_clients.values():
                if info['addr'][0] == ip_address and info['username'] != "Unknown":
                    return info['username']
            return ip_address # Default to IP if no username is found

    def get_user_list(self):
        """Returns a list of connected user information with formatted last_seen."""
        with self.control_clients_lock:
            return [
                {
                    'username': info['username'], 
                    'ip': info['addr'][0], 
                    'last_seen': info['last_seen'],
                    'last_seen_formatted': self._format_last_seen(info['last_seen']),
                    'room': info.get('room', 'default')
                }
                for info in self.control_clients.values()
            ]
    
    def _format_last_seen(self, timestamp):
        """Format timestamp as human-readable string."""
        try:
            import datetime
            now = time.time()
            diff = now - timestamp
            
            if diff < 60:  # Less than 1 minute
                return f"{int(diff)}s ago"
            elif diff < 3600:  # Less than 1 hour
                return f"{int(diff/60)}m ago"
            elif diff < 86400:  # Less than 1 day
                return f"{int(diff/3600)}h ago"
            else:
                # More than 1 day, show date
                dt = datetime.datetime.fromtimestamp(timestamp)
                return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return "Unknown"

    # --- Client Management (UDP/Streaming) ---

    def register_stream(self, stream_type, address):
        """Registers a client's UDP stream address."""
        ip_addr = address[0]
        port = address[1]
        
        with self.stream_clients_lock:
            if ip_addr not in self.stream_clients:
                self.stream_clients[ip_addr] = {
                    'video': None, 
                    'audio': None, 
                    'last_seen': time.time()
                }
            
            # The client sends the stream from a dynamic UDP port, 
            # but it is *receiving* streams back on the same (ip, port) combo.
            if stream_type == 'video':
                 self.stream_clients[ip_addr]['video'] = address
            elif stream_type == 'audio':
                 self.stream_clients[ip_addr]['audio'] = address
            
            self.stream_clients[ip_addr]['last_seen'] = time.time()

    def get_video_listeners(self, room: str = None):
        """Returns a list of addresses registered to receive video streams, optionally filtered by room."""
        listeners = []
        with self.stream_clients_lock:
            for ip_addr, info in self.stream_clients.items():
                if info['video']:
                    if room is None or self._ip_in_room(ip_addr, room):
                        listeners.append(info['video'])
        return listeners

    def get_audio_listeners(self, room: str = None):
        """Returns a list of addresses registered to receive audio streams, optionally filtered by room."""
        listeners = []
        with self.stream_clients_lock:
            for ip_addr, info in self.stream_clients.items():
                if info['audio']:
                    if room is None or self._ip_in_room(ip_addr, room):
                        listeners.append(info['audio'])
        return listeners

    # --- Server Maintenance ---

    def _run_heartbeat(self):
        """Sends heartbeats to all TCP clients to keep connections alive and checks for stale connections."""
        while self.running:
            time.sleep(HEARTBEAT_INTERVAL)
            
            with self.control_clients_lock:
                to_remove = []
                heartbeat_packet = pack_message(CMD_HEARTBEAT)

                for sock, info in list(self.control_clients.items()):
                    try:
                        sock.send(heartbeat_packet)  # Send heartbeat
                        # Consider heartbeat send success as client activity
                        info['last_seen'] = time.time()
                    except Exception:
                        # Heartbeat failed, mark for removal
                        to_remove.append(sock)
            
            # Remove stale connections OUTSIDE the lock to avoid deadlock
            for sock in to_remove:
                self.remove_client(sock)
            
            # Also clean up stale UDP streams
            self._cleanup_stale_streams()
        
        print("Manager: Heartbeat thread stopped.")
    
    def _cleanup_stale_streams(self):
        """Remove stale UDP stream registrations."""
        current_time = time.time()
        stale_threshold = CLIENT_IDLE_TIMEOUT
        
        with self.stream_clients_lock:
            to_remove = []
            for ip_addr, info in self.stream_clients.items():
                if current_time - info['last_seen'] > stale_threshold:
                    to_remove.append(ip_addr)
            
            for ip_addr in to_remove:
                del self.stream_clients[ip_addr]
                if os.environ.get('SAPORA_DEBUG'):
                    print(f"[Manager] Removed stale stream: {ip_addr}")

    def _ip_in_room(self, ip_addr: str, room: str) -> bool:
        """Check if a given IP belongs to a client in the specified room."""
        with self.control_clients_lock:
            for info in self.control_clients.values():
                if info['addr'][0] == ip_addr and info.get('room', 'default') == room:
                    return True
        return False

    def get_room_by_ip(self, ip_addr: str) -> str:
        with self.control_clients_lock:
            for info in self.control_clients.values():
                if info['addr'][0] == ip_addr:
                    return info.get('room', 'default')
        return 'default'

    def set_client_room(self, client_socket, room: str):
        with self.control_clients_lock:
            if client_socket in self.control_clients:
                self.control_clients[client_socket]['room'] = room
                threading.Thread(target=lambda: broadcast_user_list(self), daemon=True).start()

    def unregister_stream(self, stream_type: str, key):
        """Optional: remove a specific UDP stream mapping for an IP."""
        ip = key[0] if isinstance(key, (tuple, list)) else (key if isinstance(key, str) else None)
        if not ip:
            return
        with self.stream_clients_lock:
            if ip in self.stream_clients:
                if stream_type == 'audio':
                    self.stream_clients[ip]['audio'] = None
                elif stream_type == 'video':
                    self.stream_clients[ip]['video'] = None
                self.stream_clients[ip]['last_seen'] = time.time()

    def stop(self):
        """Shuts down the connection manager and all associated threads/sockets."""
        # Signal heartbeat loop to exit
        self.running = False
        # Join heartbeat briefly (it's a daemon, but we try to exit cleanly)
        try:
            if self.heartbeat_thread and self.heartbeat_thread.is_alive():
                self.heartbeat_thread.join(timeout=2.0)
        except Exception:
            pass

        # Disconnect all TCP clients
        with self.control_clients_lock:
            for sock in list(self.control_clients.keys()):
                try:
                    sock.send(pack_message(CMD_DISCONNECT))
                    sock.close()
                except Exception:
                    pass
            self.control_clients.clear()
        print("Manager: All client connections closed.")