"""
Sapora LAN Collaboration Suite - Screen Share Server
Receives one screen stream (presenter) and broadcasts to all connected viewers (TCP).
"""
import threading
import socket
import time
import struct

# Import constants/protocol/utils
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.constants import SCREEN_SHARE_PORT, BUFFER_SIZE, SOCKET_TIMEOUT
from shared.protocol import SCREEN_FRAME
from server.utils import unpack_message

class ScreenShareServer(threading.Thread):
    """Manages the single active screen share stream and broadcasts it to viewers."""

    def __init__(self, manager):
        super().__init__(daemon=True)
        self.manager = manager
        self.server_socket = None
        self.presenter_socket = None
        self.presenter_addr = None
        self.viewers = {} # {socket: address}
        self.viewers_lock = threading.Lock()

    def run(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', SCREEN_SHARE_PORT))
            self.server_socket.listen(10)
            self.server_socket.settimeout(SOCKET_TIMEOUT)
            
            print(f"ScreenShareServer: Listening on TCP port {SCREEN_SHARE_PORT}")
            
            while self.manager.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    # Hand off client connection to a new handler thread
                    threading.Thread(
                        target=self._handle_new_client, 
                        args=(client_socket, address), 
                        daemon=True
                    ).start()
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.manager.running:
                        print(f"ScreenShareServer: Error accepting connection: {e}")
                        
        except Exception as e:
            print(f"ScreenShareServer: Fatal error: {e}")
        finally:
            self.stop()

    def _handle_new_client(self, client_socket, address):
        """Determines if the client is a presenter or a viewer."""
        try:
            client_socket.settimeout(SOCKET_TIMEOUT * 3) # Longer timeout for initial detection
            
            # Try to receive frame size (4 bytes)
            size_data = self._recv_exact(client_socket, 4)
            
            if size_data and size_data != b'\x00\x00\x00\x00':
                # This is a presenter sending a frame. Reject if one is already active.
                if self.presenter_socket:
                    print(f"ScreenShareServer: Presenter rejected. Already active.")
                    client_socket.close()
                    return
                    
                self._handle_presenter(client_socket, address, size_data)
            else:
                # This is a viewer, register and start passive viewing.
                self._handle_viewer(client_socket, address)

        except socket.timeout:
            # No data received, assume viewer (passive connection)
            self._handle_viewer(client_socket, address)
        except Exception as e:
            print(f"ScreenShareServer: Error handling client {address[0]}: {e}")
            client_socket.close()

    def _handle_presenter(self, client_socket, address, first_size_data):
        """Handles the active presenter connection."""
        self.presenter_socket = client_socket
        self.presenter_addr = address
        print(f"ScreenShareServer: Presenter connected: {address[0]}")

        # Send the first frame's size data immediately
        full_frame_data = first_size_data 
        frame_size = struct.unpack('!I', first_size_data)[0]

        try:
            # Receive the rest of the first frame
            frame_data = self._recv_exact(client_socket, frame_size)
            if not frame_data:
                raise ConnectionError("Incomplete first frame.")
            full_frame_data += frame_data
            
            # Broadcast first frame
            self._broadcast_frame(full_frame_data, client_socket)

            while self.manager.running:
                # Receive size for next frame
                size_data = self._recv_exact(client_socket, 4)
                if not size_data:
                    break
                
                frame_size = struct.unpack('!I', size_data)[0]
                frame_data = self._recv_exact(client_socket, frame_size)
                if not frame_data:
                    break
                
                # Broadcast new frame (size_data + frame_data)
                self._broadcast_frame(size_data + frame_data, client_socket)
                
        except Exception as e:
            print(f"ScreenShareServer: Presenter {address[0]} error: {e}")
        finally:
            self.presenter_socket = None
            self.presenter_addr = None
            client_socket.close()
            self._cleanup_viewer(client_socket)
            print(f"ScreenShareServer: Presenter disconnected: {address[0]}")

    def _handle_viewer(self, client_socket, address):
        """Handles a passive viewer connection."""
        with self.viewers_lock:
            self.viewers[client_socket] = address
        print(f"ScreenShareServer: Viewer connected: {address[0]}")

        # Keep connection alive simply by waiting
        try:
            while self.manager.running:
                # Use a small recv to detect disconnect, but primarily wait
                if client_socket.recv(BUFFER_SIZE) == b'':
                    break # Client closed connection
                time.sleep(1) 
        except Exception:
            pass
        finally:
            self._cleanup_viewer(client_socket)
            print(f"ScreenShareServer: Viewer disconnected: {address[0]}")

    def _broadcast_frame(self, frame_data, sender_socket):
        """Sends the raw frame data to all viewers."""
        disconnected = []
        with self.viewers_lock:
            for viewer_socket in list(self.viewers.keys()):
                if viewer_socket == sender_socket:
                    continue # Should not happen for viewers, but safe to check

                try:
                    viewer_socket.sendall(frame_data)
                except Exception:
                    disconnected.append(viewer_socket)
            
            for sock in disconnected:
                del self.viewers[sock]

    def _recv_exact(self, sock, num_bytes):
        """Receives exactly num_bytes from a TCP socket."""
        data = b''
        while len(data) < num_bytes:
            chunk = sock.recv(min(num_bytes - len(data), BUFFER_SIZE))
            if not chunk:
                return None
            data += chunk
        return data

    def _cleanup_viewer(self, client_socket):
        """Removes a socket from the viewer list and closes it."""
        with self.viewers_lock:
            if client_socket in self.viewers:
                del self.viewers[client_socket]
        try:
            client_socket.close()
        except:
            pass

    def stop(self):
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        with self.viewers_lock:
            for sock in list(self.viewers.keys()):
                self._cleanup_viewer(sock)
        if self.presenter_socket:
            try:
                self.presenter_socket.close()
            except:
                pass
        print("ScreenShareServer: Server stopped.")