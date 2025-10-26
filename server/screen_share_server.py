"""
Screen Share Server
Receives screen streams from presenters and broadcasts to viewers
Uses TCP for reliable screen frame delivery
"""

import socket
import threading
import sys
import os
import time
import struct

# --- CRITICAL FIX: Add project root to path for shared/ imports ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
# -----------------------------------------------------------------

from shared.constants import SCREEN_SHARE_PORT, BUFFER_SIZE
from shared.protocol import SCREEN_SHARE
from shared.helpers import unpack_message


class ScreenShareServer:
    """Multi-user screen sharing server"""
    
    def __init__(self, port=SCREEN_SHARE_PORT):
        self.port = port
        self.server_socket = None
        self.running = False
        
        # Track presenters and viewers
        self.presenters = {}  # {socket: address}
        self.viewers = {}     # {socket: address}
        self.lock = threading.Lock()
        
        # Statistics
        self.stats = {
            'frames_relayed': 0,
            'bytes_relayed': 0,
            'total_connections': 0
        }
    
    def start(self):
        """Start the screen share server"""
        try:
            # Create TCP socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.port))
            self.server_socket.listen(10)
            self.server_socket.settimeout(1.0)
            
            self.running = True
            
            print(f"🖥️  Screen Share Server listening on TCP port {self.port}")
            
            # Accept connections
            while self.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    
                    self.stats['total_connections'] += 1
                    
                    print(f"✓ Screen share connection from {address[0]}:{address[1]}")
                    
                    # Handle in new thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, address),
                        daemon=True
                    )
                    client_thread.start()
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"⚠️  Error accepting connection: {e}")
                        
        except Exception as e:
            print(f"❌ Screen share server error: {e}")
        finally:
            self.stop()
    
    def _handle_client(self, client_socket, address):
        """Handle screen share client (presenter or viewer)"""
        is_presenter = False
        
        try:
            client_socket.settimeout(1.0)
            
            # Wait for first frame to determine if presenter or viewer
            
            try:
                # Try to receive frame size (4 bytes)
                size_data = self._recv_with_timeout(client_socket, 4, timeout=3.0)
                
                if size_data:
                    # This is a presenter sending frames
                    is_presenter = True
                    with self.lock:
                        self.presenters[client_socket] = address
                    
                    print(f"🎬 Presenter connected: {address[0]}:{address[1]}")
                    self._handle_presenter(client_socket, address, size_data)
                else:
                    # This is a viewer waiting for frames
                    with self.lock:
                        self.viewers[client_socket] = address
                    
                    print(f"👁️  Viewer connected: {address[0]}:{address[1]}")
                    self._handle_viewer(client_socket, address)
                    
            except socket.timeout:
                # No data received, assume viewer
                with self.lock:
                    self.viewers[client_socket] = address
                
                print(f"👁️  Viewer connected: {address[0]}:{address[1]}")
                self._handle_viewer(client_socket, address)
                
        except Exception as e:
            print(f"⚠️  Error handling client {address[0]}: {e}")
        finally:
            # Remove from tracking
            with self.lock:
                if client_socket in self.presenters:
                    del self.presenters[client_socket]
                    print(f"🎬 Presenter disconnected: {address[0]}:{address[1]}")
                if client_socket in self.viewers:
                    del self.viewers[client_socket]
                    print(f"👁️  Viewer disconnected: {address[0]}:{address[1]}")
            
            client_socket.close()
    
    def _handle_presenter(self, client_socket, address, first_size_data):
        """Handle presenter sending screen frames"""
        try:
            # Process first frame
            frame_size = struct.unpack('!I', first_size_data)[0]
            frame_data = self._recv_exact(client_socket, frame_size)
            
            if frame_data:
                self._broadcast_frame(first_size_data + frame_data, client_socket)
            
            # Receive and broadcast subsequent frames
            while self.running:
                # Receive frame size
                size_data = self._recv_exact(client_socket, 4)
                if not size_data:
                    break
                
                frame_size = struct.unpack('!I', size_data)[0]
                
                # Validate size
                if frame_size > 10 * 1024 * 1024:  # Max 10MB
                    print(f"⚠️  Frame too large: {frame_size}")
                    break
                
                # Receive frame data
                frame_data = self._recv_exact(client_socket, frame_size)
                if not frame_data:
                    break
                
                # Broadcast to all viewers
                self._broadcast_frame(size_data + frame_data, client_socket)
                
                # Update stats
                self.stats['frames_relayed'] += 1
                self.stats['bytes_relayed'] += len(frame_data)
                
                # Log stats periodically
                if self.stats['frames_relayed'] % 100 == 0:
                    self._log_stats()
                    
        except Exception as e:
            print(f"⚠️  Presenter error: {e}")
    
    def _handle_viewer(self, client_socket, address):
        """Handle viewer waiting for frames"""
        # Viewers are passive - they just receive frames from broadcast
        # Keep connection alive
        try:
            while self.running:
                time.sleep(1)
                # Check if socket is still connected
                try:
                    client_socket.send(b'')
                except:
                    break
        except Exception as e:
            pass
    
    def _broadcast_frame(self, frame_data, sender_socket):
        """Broadcast frame to all viewers"""
        with self.lock:
            disconnected = []
            
            for viewer_socket in list(self.viewers.keys()):
                if viewer_socket == sender_socket:
                    continue
                
                try:
                    viewer_socket.sendall(frame_data)
                except Exception as e:
                    disconnected.append(viewer_socket)
            
            # Remove disconnected viewers
            for socket in disconnected:
                if socket in self.viewers:
                    addr = self.viewers[socket]
                    del self.viewers[socket]
                    print(f"👁️  Viewer disconnected (broadcast failed): {addr[0]}")
    
    def _recv_exact(self, sock, num_bytes):
        """Receive exactly num_bytes"""
        data = b''
        while len(data) < num_bytes:
            chunk = sock.recv(min(num_bytes - len(data), BUFFER_SIZE))
            if not chunk:
                return None
            data += chunk
        return data
    
    def _recv_with_timeout(self, sock, num_bytes, timeout=1.0):
        """Receive with timeout"""
        sock.settimeout(timeout)
        try:
            return self._recv_exact(sock, num_bytes)
        except socket.timeout:
            return None
    
    def _log_stats(self):
        """Log server statistics"""
        with self.lock:
            presenters = len(self.presenters)
            viewers = len(self.viewers)
        
        mbytes = self.stats['bytes_relayed'] / (1024 * 1024)
        print(f"📊 Screen: {self.stats['frames_relayed']} frames | "
              f"{mbytes:.2f} MB | "
              f"{presenters} presenters | {viewers} viewers")
    
    def stop(self):
        """Stop the server"""
        self.running = False
        
        # Close all connections
        with self.lock:
            for socket in list(self.presenters.keys()):
                try:
                    socket.close()
                except:
                    pass
            for socket in list(self.viewers.keys()):
                try:
                    socket.close()
                except:
                    pass
            self.presenters.clear()
            self.viewers.clear()
        
        if self.server_socket:
            self.server_socket.close()
        
        print("🛑 Screen share server stopped")
    
    def get_stats(self):
        """Get server statistics"""
        with self.lock:
            return {
                'frames_relayed': self.stats['frames_relayed'],
                'bytes_relayed': self.stats['bytes_relayed'],
                'presenters': len(self.presenters),
                'viewers': len(self.viewers),
                'total_connections': self.stats['total_connections']
            }


if __name__ == '__main__':
    server = ScreenShareServer()
    try:
        server.start()
    except KeyboardInterrupt:
        print("\n")
        server.stop()