"""
Sapora LAN Collaboration Suite - File Server (optimized)
Handles reliable TCP-based file upload and download requests.
"""

import threading
import socket
import os
import hashlib
from pathlib import Path
import sys
import time

# --- Ensure project root on path for shared imports ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
# -----------------------------------------------------------------

from shared.constants import (
    FILE_TRANSFER_PORT, FILE_CHUNK_SIZE,
    MAX_FILE_SIZE, BUFFER_SIZE, SOCKET_TIMEOUT,
    STORAGE_DIR
)
from shared.protocol import (
    FILE_REQUEST_UPLOAD, FILE_REQUEST_DOWNLOAD, FILE_METADATA, FILE_CHUNK,
    FILE_ACK_SUCCESS, FILE_ACK_FAILURE
)
from server.utils import read_tcp_message, unpack_message, pack_message
from shared.helpers import unpack_file_metadata, pack_file_metadata


class FileTransferServer(threading.Thread):
    """Main server component for handling file transfers."""

    def __init__(self, manager):
        super().__init__(daemon=True)
        self.manager = manager
        self.server_socket = None
        self.storage_dir = Path(STORAGE_DIR)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.running = False

    def run(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', FILE_TRANSFER_PORT))
            self.server_socket.listen(5)
            self.server_socket.settimeout(SOCKET_TIMEOUT)

            self.running = True
            print(f"[FileTransferServer] Listening on TCP port {FILE_TRANSFER_PORT}. Storage: {self.storage_dir.resolve()}")

            while self.running and getattr(self.manager, "running", True):
                try:
                    client_socket, address = self.server_socket.accept()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"[FileTransferServer] Accept error: {e}")
                    continue

                # Hand off to handler thread
                handler = FileHandler(self.manager, client_socket, address, self.storage_dir)
                handler.start()

        except Exception as e:
            print(f"[FileTransferServer] Fatal error: {e}")
        finally:
            self.stop()

    def stop(self):
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        print("[FileTransferServer] Server stopped.")


class FileHandler(threading.Thread):
    """Handles a single file transfer client connection."""

    def __init__(self, manager, client_socket, address, storage_dir: Path):
        super().__init__(daemon=True)
        self.manager = manager
        self.sock = client_socket
        self.address = address
        self.ip = address[0]
        self.port = address[1]
        self.storage_dir = storage_dir
        self.sock.settimeout(60)  # Default timeout until metadata received

    def run(self):
        print(f"[FileHandler] Started for {self.ip}:{self.port}")
        try:
            raw_message = read_tcp_message(self.sock)
            if raw_message is None:
                print(f"[FileHandler] No initial request from {self.ip}.")
                return

            _, msg_type, _, _, payload = unpack_message(raw_message)

            if msg_type == FILE_REQUEST_UPLOAD:
                self._handle_upload_request(payload)
            elif msg_type == FILE_REQUEST_DOWNLOAD:
                self._handle_download_request(payload)
            else:
                print(f"[FileHandler] Unknown request type {msg_type} from {self.ip}")

        except Exception as e:
            print(f"[FileHandler] Connection error for {self.ip}: {e}")
        finally:
            try:
                self.sock.close()
            except:
                pass
            print(f"[FileHandler] Connection closed for {self.ip}:{self.port}")

    def _handle_upload_request(self, payload):
        """Processes an upload initiation request with target routing."""
        if os.environ.get('SAPORA_DEBUG'):
            print(f"[FileHandler] Upload requested from {self.ip}:{self.port}")
        
        filename = None
        file_path = None
        target_users = []  # List of users to notify about file availability

        try:
            metadata = unpack_file_metadata(payload)
            filename = metadata.get('filename')
            filesize = int(metadata.get('filesize', 0))
            checksum = metadata.get('checksum')
            
            # Extract target information if present
            target_info = metadata.get('target', 'all')
            if target_info and target_info != 'all':
                target_users = [target_info]
            else:
                target_users = ['all']  # Broadcast to all
                
        except Exception as e:
            if os.environ.get('SAPORA_DEBUG'):
                print(f"[FileHandler] Invalid metadata from {self.ip}: {e}")
            self._safe_send(pack_message(FILE_ACK_FAILURE, b"Invalid metadata"))
            return

        if not filename or filesize <= 0:
            self._safe_send(pack_message(FILE_ACK_FAILURE, b"Invalid filename or filesize"))
            return

        if filesize > MAX_FILE_SIZE:
            if os.environ.get('SAPORA_DEBUG'):
                print(f"[FileHandler] Rejected upload: {filename} too large ({filesize} bytes).")
            self._safe_send(pack_message(FILE_ACK_FAILURE, b"File too large"))
            return

        # Adjust timeout dynamically based on file size
        transfer_timeout = max(30, filesize / 1048576 * 2)
        self.sock.settimeout(transfer_timeout)

        file_path = (self.storage_dir / filename).resolve()

        # Prevent directory traversal
        try:
            if not str(file_path).startswith(str(self.storage_dir.resolve())):
                raise ValueError("Invalid filename (path traversal)")
        except Exception as e:
            if os.environ.get('SAPORA_DEBUG'):
                print(f"[FileHandler] Filename validation error: {e}")
            self._safe_send(pack_message(FILE_ACK_FAILURE, b"Invalid filename"))
            return

        bytes_received = 0
        try:
            with open(file_path, 'wb') as f:
                while bytes_received < filesize:
                    chunk_raw = read_tcp_message(self.sock)
                    if chunk_raw is None:
                        raise ConnectionAbortedError("Connection lost during file transfer")

                    _, chunk_type, _, _, chunk_payload = unpack_message(chunk_raw)

                    if chunk_type != FILE_CHUNK:
                        raise ValueError(f"Unexpected message type ({chunk_type}) during upload")

                    f.write(chunk_payload)
                    bytes_received += len(chunk_payload)

            if bytes_received != filesize:
                raise IOError(f"Received size mismatch (got {bytes_received}, expected {filesize})")

            # Validate checksum if provided
            if checksum:
                actual_checksum = self._calculate_md5(file_path)
                if actual_checksum != checksum:
                    try:
                        file_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    if os.environ.get('SAPORA_DEBUG'):
                        print(f"[FileHandler] Checksum mismatch for {filename}. Deleted file.")
                    self._safe_send(pack_message(FILE_ACK_FAILURE, b"Checksum mismatch"))
                    return

            if os.environ.get('SAPORA_DEBUG'):
                print(f"[FileHandler] Successfully uploaded {filename} ({bytes_received} bytes).")
            self._safe_send(pack_message(FILE_ACK_SUCCESS, b"Upload successful"))
            
            # Notify target users about file availability
            self._notify_file_availability(filename, filesize, target_users)

        except Exception as e:
            if os.environ.get('SAPORA_DEBUG'):
                print(f"[FileHandler] Upload failed for {filename}: {e}")
            try:
                if file_path and file_path.exists():
                    file_path.unlink()
            except Exception:
                pass
            try:
                self._safe_send(pack_message(FILE_ACK_FAILURE, str(e).encode('utf-8')))
            except Exception:
                pass
    
    def _notify_file_availability(self, filename, filesize, target_users):
        """Notify target users about file availability."""
        try:
            # Get sender info from manager
            sender_username = self.manager.get_client_username_by_ip(self.ip)
            
            # Create file notification
            notification = {
                'type': 'file_announce',
                'filename': filename,
                'sender': sender_username,
                'size': filesize,
                'target': target_users[0] if len(target_users) == 1 else 'all',
                'timestamp': time.time()
            }
            
            # Send notification via chat system if available
            if hasattr(self.manager, 'server_ref') and self.manager.server_ref:
                self._broadcast_file_notification(notification)
                
        except Exception as e:
            if os.environ.get('SAPORA_DEBUG'):
                print(f"[FileHandler] File notification error: {e}")
    
    def _broadcast_file_notification(self, notification):
        """Broadcast file notification to target users."""
        try:
            import json
            from shared.protocol import MSG_CHAT
            from server.utils import pack_message
            
            target = notification.get('target', 'all')
            server = self.manager.server_ref

            # Determine sender's room reliably via ConnectionManager
            sender_room = self.manager.get_room_by_ip(self.ip)
            if not sender_room:
                return

            with server.rooms_lock:
                room = server.rooms.get(sender_room)
                if not room:
                    return

                participants = room.get('participants', {})

                # Determine targets
                if str(target).strip().lower() in ['all', 'everyone', '']:
                    targets = list(participants.values())
                else:
                    # Case-insensitive username lookup
                    target_lower = str(target).strip().lower()
                    participants_ci = {str(name).strip().lower(): sock for name, sock in participants.items()}
                    target_sock = participants_ci.get(target_lower)
                    targets = [target_sock] if target_sock else []

                # Exclude sender from targets to avoid self-popup
                try:
                    sndr = notification.get('sender')
                    if sndr and sndr in participants:
                        sender_sock = participants.get(sndr)
                        targets = [s for s in targets if s and s != sender_sock]
                except Exception:
                    pass

                # Send notification to targets
                notification_json = json.dumps(notification)
                packet = pack_message(MSG_CHAT, notification_json.encode('utf-8'))

                for sock in targets:
                    try:
                        if sock:
                            sock.sendall(packet)
                    except Exception:
                        pass
                        
        except Exception as e:
            if os.environ.get('SAPORA_DEBUG'):
                print(f"[FileHandler] Broadcast notification error: {e}")

    def _handle_download_request(self, payload):
        """Processes a download request."""
        try:
            filename = payload.decode('utf-8')
        except Exception:
            print("[FileHandler] Invalid download request payload.")
            self._safe_send(pack_message(FILE_ACK_FAILURE, b"Invalid request"))
            return

        print(f"[FileHandler] Download requested for '{filename}' by {self.ip}:{self.port}")

        file_path = (self.storage_dir / filename).resolve()

        # Validate file path (prevent traversal)
        try:
            if not str(file_path).startswith(str(self.storage_dir.resolve())):
                raise ValueError("Invalid filename (path traversal)")
        except Exception as e:
            print(f"[FileHandler] Filename validation error: {e}")
            self._safe_send(pack_message(FILE_ACK_FAILURE, b"Invalid filename"))
            return

        if not file_path.exists() or not file_path.is_file():
            print(f"[FileHandler] File not found: {filename}")
            self._safe_send(pack_message(FILE_ACK_FAILURE, b"File not found"))
            return

        filesize = file_path.stat().st_size
        checksum = self._calculate_md5(file_path)

        try:
            metadata = pack_file_metadata(filename, filesize, checksum)
            self._safe_send(pack_message(FILE_METADATA, metadata))

            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(FILE_CHUNK_SIZE)
                    if not chunk:
                        break
                    self._safe_send(pack_message(FILE_CHUNK, chunk))

            print(f"[FileHandler] Successfully sent {filename} ({filesize} bytes).")
        except Exception as e:
            print(f"[FileHandler] Download failed for {filename}: {e}")

    def _calculate_md5(self, file_path: Path):
        """Calculates MD5 checksum of a file."""
        md5_hash = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(FILE_CHUNK_SIZE), b''):
                    md5_hash.update(chunk)
            return md5_hash.hexdigest()
        except Exception:
            return None

    def _safe_send(self, data_bytes: bytes):
        """Send safely (ignore transient send errors)."""
        try:
            self.sock.sendall(data_bytes)
        except Exception:
            pass