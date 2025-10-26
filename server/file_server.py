"""
Sapora LAN Collaboration Suite - File Server
Handles reliable TCP-based file upload and download requests.
"""
import threading
import socket
import os
import struct
import hashlib
from pathlib import Path
import sys 

# --- CRITICAL FIX: Add project root to path for shared/ imports ---
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
from shared.helpers import unpack_file_metadata, pack_file_metadata # This import will now succeed

# ... (rest of file_server.py remains the same)

class FileTransferServer(threading.Thread):
    """Main server component for handling file transfers."""
    
    def __init__(self, manager):
        super().__init__(daemon=True)
        self.manager = manager
        self.server_socket = None
        self.storage_dir = Path(STORAGE_DIR)
        self.storage_dir.mkdir(exist_ok=True)
        
    def run(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', FILE_TRANSFER_PORT))
            self.server_socket.listen(5)
            self.server_socket.settimeout(SOCKET_TIMEOUT)
            
            print(f"FileTransferServer: Listening on TCP port {FILE_TRANSFER_PORT}. Storage: {self.storage_dir.absolute()}")
            
            while self.manager.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    
                    handler = FileHandler(self.manager, client_socket, address)
                    handler.start()
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.manager.running:
                        print(f"FileTransferServer: Error accepting connection: {e}")
                        
        except Exception as e:
            print(f"FileTransferServer: Fatal error: {e}")
        finally:
            self.stop()
            
    def stop(self):
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        print("FileTransferServer: Server stopped.")

class FileHandler(threading.Thread):
    """Handles a single file transfer client connection."""
    
    def __init__(self, manager, client_socket, address):
        super().__init__(daemon=True)
        self.manager = manager
        self.sock = client_socket
        self.address = address
        self.ip = address[0]
        self.storage_dir = Path(STORAGE_DIR)
        
        self.sock.settimeout(SOCKET_TIMEOUT * 10) 
        
    def run(self):
        print(f"FileHandler: Started for {self.ip}")
        try:
            raw_message = read_tcp_message(self.sock)
            if raw_message is None:
                return
            
            version, msg_type, payload_length, seq_num, payload = unpack_message(raw_message)

            if msg_type == FILE_REQUEST_UPLOAD:
                self._handle_upload_request(payload)
            elif msg_type == FILE_REQUEST_DOWNLOAD:
                self._handle_download_request(payload)
            else:
                print(f"FileHandler: Unknown request type {msg_type} from {self.ip}")

        except Exception as e:
            print(f"FileHandler: Connection error for {self.ip}: {e}")
        finally:
            try:
                self.sock.close()
            except:
                pass
            print(f"FileHandler: Connection closed for {self.ip}")

    def _handle_upload_request(self, payload):
        """Processes an upload initiation request."""
        print(f"FileHandler: Upload requested from {self.ip}")
        
        try:
            metadata = unpack_file_metadata(payload)
            filename = metadata['filename']
            filesize = metadata['filesize']
            checksum = metadata.get('checksum')
        except Exception:
            print("FileHandler: Invalid metadata format.")
            self.sock.sendall(pack_message(FILE_ACK_FAILURE, b"Invalid metadata"))
            return

        if filesize > MAX_FILE_SIZE:
            print(f"FileHandler: Rejected upload: {filename} too large.")
            self.sock.sendall(pack_message(FILE_ACK_FAILURE, b"File too large"))
            return

        file_path = self.storage_dir / filename
        bytes_received = 0
        try:
            with open(file_path, 'wb') as f:
                while bytes_received < filesize:
                    raw_chunk = read_tcp_message(self.sock)
                    if raw_chunk is None:
                        raise ConnectionAbortedError("Connection lost during file data transfer.")
                    
                    _, chunk_type, _, _, chunk_payload = unpack_message(raw_chunk)

                    if chunk_type != FILE_CHUNK:
                        raise ValueError(f"Unexpected message type ({chunk_type}) received in file stream.")
                        
                    f.write(chunk_payload)
                    bytes_received += len(chunk_payload)
            
            if bytes_received != filesize:
                 raise IOError("Received file size mismatch.")

            if checksum:
                actual_checksum = self._calculate_md5(file_path)
                if actual_checksum != checksum:
                    os.remove(file_path)
                    print(f"FileHandler: Checksum mismatch for {filename}. Deleted file.")
                    self.sock.sendall(pack_message(FILE_ACK_FAILURE, b"Checksum mismatch"))
                    return

            print(f"FileHandler: Successfully uploaded {filename} ({bytes_received} bytes).")
            self.sock.sendall(pack_message(FILE_ACK_SUCCESS, b"Upload successful"))

        except Exception as e:
            print(f"FileHandler: Upload failed for {filename}: {e}")
            if file_path.exists():
                os.remove(file_path)
            self.sock.sendall(pack_message(FILE_ACK_FAILURE, str(e).encode('utf-8')))

    def _handle_download_request(self, payload):
        """Processes a download request."""
        try:
            filename = payload.decode('utf-8')
            file_path = self.storage_dir / filename
        except Exception:
            print("FileHandler: Invalid download request payload.")
            return

        print(f"FileHandler: Download requested for {filename} by {self.ip}")
        
        if not file_path.exists() or not file_path.is_file():
            print(f"FileHandler: File not found: {filename}")
            self.sock.sendall(pack_message(FILE_ACK_FAILURE, b"File not found"))
            return

        filesize = file_path.stat().st_size
        checksum = self._calculate_md5(file_path)

        try:
            metadata = pack_file_metadata(filename, filesize, checksum)
            self.sock.sendall(pack_message(FILE_METADATA, metadata))

            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(FILE_CHUNK_SIZE)
                    if not chunk:
                        break
                    
                    self.sock.sendall(pack_message(FILE_CHUNK, chunk))
            
            print(f"FileHandler: Successfully sent {filename} ({filesize} bytes).")
            
        except Exception as e:
            print(f"FileHandler: Download failed for {filename}: {e}")

    def _calculate_md5(self, file_path):
        """Calculates MD5 checksum of a file."""
        md5_hash = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(FILE_CHUNK_SIZE), b''):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()