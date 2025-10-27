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
    CONNECTION_TIMEOUT, SOCKET_TIMEOUT
)
from shared.protocol import CMD_HEARTBEAT, CMD_USER_LIST, CMD_DISCONNECT
from server.utils import broadcast_user_list, pack_message

class ConnectionManager:
    """
    Central repository for tracking all client connections and state.
    """
    def __init__(self):
        self.running = True
        
        # TCP Control/Chat Clients: {socket: {'addr': (ip, port), 'username': str, 'last_seen': float, 'id': str}}
        self.control_clients = {}
        self.control_clients_lock = threading.Lock()
        
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
                'socket': client_socket
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

    def update_client_status(self, client_socket, username=None):
        """Updates client's last seen time and optionally username."""
        with self.control_clients_lock:
            if client_socket in self.control_clients:
                self.control_clients[client_socket]['last_seen'] = time.time()
                if username and self.control_clients[client_socket]['username'] == "Unknown":
                     self.control_clients[client_socket]['username'] = username
                     # If username was just set, re-broadcast the list
                     threading.Thread(target=lambda: broadcast_user_list(self), daemon=True).start()
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
        """Returns a list of connected user information."""
        with self.control_clients_lock:
            return [
                {'username': info['username'], 'ip': info['addr'][0], 'last_seen': info['last_seen']}
                for info in self.control_clients.values()
            ]

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

    def get_video_listeners(self):
        """Returns a list of addresses registered to receive video streams."""
        listeners = []
        with self.stream_clients_lock:
            for ip_addr, info in self.stream_clients.items():
                if info['video']:
                    listeners.append(info['video'])
        return listeners

    def get_audio_listeners(self):
        """Returns a list of addresses registered to receive audio streams."""
        listeners = []
        with self.stream_clients_lock:
            for ip_addr, info in self.stream_clients.items():
                if info['audio']:
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
                        sock.send(heartbeat_packet) # Send heartbeat
                        
                        # Check for stale connection based on last_seen
                        if time.time() - info['last_seen'] > CONNECTION_TIMEOUT:
                            print(f"Manager: Timeout detected for {info['username']} ({info['addr'][0]}).")
                            to_remove.append(sock)

                    except Exception:
                        to_remove.append(sock)
            
            # Remove stale connections OUTSIDE the lock to avoid deadlock
            for sock in to_remove:
                self.remove_client(sock)
        
        print("Manager: Heartbeat thread stopped.")

    def stop(self):
        """Shuts down the connection manager and all associated threads/sockets."""
        self.running = False
        with self.control_clients_lock:
            for sock in list(self.control_clients.keys()):
                try:
                    sock.send(pack_message(CMD_DISCONNECT))
                    sock.close()
                except:
                    pass
            self.control_clients.clear()
        print("Manager: All client connections closed.")