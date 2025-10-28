"""
Sapora LAN Discovery Module
Server broadcasts discovery packets; clients listen for available servers.
"""

import socket
import json
import threading
import time
try:
    import netifaces
except Exception:
    netifaces = None  # optional dependency
from typing import List, Dict, Callable

DISCOVERY_PORT = 5001
BROADCAST_INTERVAL = 5  # seconds
SERVER_TTL = 15  # server timeout after no broadcasts


class LANDiscoveryServer:
    """Server-side LAN discovery broadcaster"""
    
    def __init__(self, server_name: str, server_port: int):
        self.server_name = server_name
        self.server_port = server_port
        self.running = False
        self.broadcast_thread = None
        
    def start(self):
        """Start broadcasting discovery packets"""
        if self.running:
            return
            
        self.running = True
        self.broadcast_thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self.broadcast_thread.start()
        print(f"[Discovery] Broadcasting as '{self.server_name}' on port {DISCOVERY_PORT}")
        
    def stop(self):
        """Stop broadcasting"""
        self.running = False
        if self.broadcast_thread:
            self.broadcast_thread.join(timeout=1)
            
    def _broadcast_loop(self):
        """Continuously broadcast server info"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            while self.running:
                # Get local IP address
                local_ip = self._get_local_ip()
                
                discovery_packet = {
                    "type": "sapora_discovery",
                    "server_name": self.server_name,
                    "ip": local_ip,
                    "port": self.server_port,
                    "timestamp": time.time()
                }
                
                try:
                    message = json.dumps(discovery_packet).encode('utf-8')
                    sock.sendto(message, ('<broadcast>', DISCOVERY_PORT))
                except Exception as e:
                    print(f"[Discovery] Broadcast error: {e}")
                
                time.sleep(BROADCAST_INTERVAL)
        
        except Exception as e:
            print(f"[Discovery] Server error: {e}")
        finally:
            sock.close()
            
    def _get_local_ip(self) -> str:
        """Get the machine's local IP address"""
        try:
            if netifaces is not None:
                # Try to get the main network interface
                interfaces = netifaces.interfaces()
                for interface in interfaces:
                    addrs = netifaces.ifaddresses(interface)
                    if netifaces.AF_INET in addrs:
                        for addr in addrs[netifaces.AF_INET]:
                            ip = addr['addr']
                            # Skip loopback and other special addresses
                            if not ip.startswith('127.') and not ip.startswith('169.254.'):
                                return ip
        except Exception:
            pass
            
        # Fallback method
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(('8.8.8.8', 80))
                return s.getsockname()[0]
        except:
            return '127.0.0.1'


class LANDiscoveryClient:
    """Client-side LAN discovery listener"""
    
    def __init__(self, callback: Callable[[Dict], None] = None):
        self.callback = callback
        self.running = False
        self.listen_thread = None
        self.discovered_servers = {}  # ip: server_info
        self.servers_lock = threading.Lock()
        
    def start(self):
        """Start listening for server broadcasts"""
        if self.running:
            return
            
        self.running = True
        self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listen_thread.start()
        
        # Start cleanup thread for expired servers
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()
        
        print(f"[Discovery] Listening for servers on port {DISCOVERY_PORT}")
        
    def stop(self):
        """Stop listening"""
        self.running = False
        if self.listen_thread:
            self.listen_thread.join(timeout=1)
            
    def get_servers(self) -> List[Dict]:
        """Get list of discovered servers"""
        with self.servers_lock:
            return list(self.discovered_servers.values())
            
    def _listen_loop(self):
        """Listen for server broadcast packets"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            sock.bind(('', DISCOVERY_PORT))
            sock.settimeout(1.0)  # Non-blocking with timeout
            
            while self.running:
                try:
                    data, addr = sock.recvfrom(1024)
                    packet = json.loads(data.decode('utf-8'))
                    
                    if packet.get('type') == 'sapora_discovery':
                        server_ip = packet.get('ip', addr[0])
                        
                        server_info = {
                            'name': packet.get('server_name', 'Unknown Server'),
                            'ip': server_ip,
                            'port': packet.get('port', 5000),
                            'last_seen': time.time(),
                            'source_addr': addr[0]
                        }
                        
                        with self.servers_lock:
                            was_new = server_ip not in self.discovered_servers
                            self.discovered_servers[server_ip] = server_info
                            
                        if was_new and self.callback:
                            self.callback(server_info)
                            
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"[Discovery] Listen error: {e}")
                        
        except Exception as e:
            print(f"[Discovery] Client error: {e}")
        finally:
            sock.close()
            
    def _cleanup_loop(self):
        """Remove expired servers"""
        while self.running:
            time.sleep(5)
            current_time = time.time()
            
            with self.servers_lock:
                expired = [
                    ip for ip, info in self.discovered_servers.items()
                    if current_time - info['last_seen'] > SERVER_TTL
                ]
                
                for ip in expired:
                    del self.discovered_servers[ip]
                    print(f"[Discovery] Server {ip} expired")


# Utility functions for PyQt integration
def start_server_discovery(server_name: str = "Sapora Host", server_port: int = 5000) -> LANDiscoveryServer:
    """Start server discovery broadcasting"""
    server = LANDiscoveryServer(server_name, server_port)
    server.start()
    return server


def start_client_discovery(callback: Callable[[Dict], None] = None) -> LANDiscoveryClient:
    """Start client discovery listening"""
    client = LANDiscoveryClient(callback)
    client.start()
    return client