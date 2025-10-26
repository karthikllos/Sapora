"""
Sapora LAN Collaboration Suite - File Transfer Client
Handles reliable TCP file upload and download operations.
"""
import socket
import os
import struct
import hashlib
import time
from pathlib import Path
import sys

# Add parent path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.constants import (
    FILE_TRANSFER_PORT, FILE_CHUNK_SIZE, MAX_FILE_SIZE, CONNECTION_TIMEOUT,
    DEFAULT_SERVER_IP
)
from shared.protocol import (
    FILE_REQUEST_UPLOAD, FILE_REQUEST_DOWNLOAD, FILE_METADATA, FILE_CHUNK,
    FILE_ACK_SUCCESS, FILE_ACK_FAILURE
)
from client.utils import pack_message, unpack_message, read_tcp_message, format_size
from shared.helpers import pack_file_metadata, unpack_file_metadata # Using unpacked helpers directly

class FileTransferClient:
    """Handles file upload and download operations."""

    def __init__(self, server_ip, server_port, status_callback):
        self.server_ip = server_ip
        self.server_port = server_port
        self.status_callback = status_callback
        self.sock = None

    def _connect(self):
        """Establishes a temporary TCP connection for the transfer."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(CONNECTION_TIMEOUT)
            self.sock.connect((self.server_ip, self.server_port))
            return True
        except Exception as e:
            self.status_callback(f"❌ File connection error: {str(e)}")
            return False
        
    def _disconnect(self):
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        self.sock = None

    def _calculate_md5(self, file_path):
        """Calculates MD5 checksum of file."""
        md5_hash = hashlib.md5()
        # Use a safe chunk size for reading
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(FILE_CHUNK_SIZE), b''):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()

    def upload_file(self, file_path):
        """Uploads a file to the server."""
        if not self._connect(): return False
        
        file_path = Path(file_path)
        if not file_path.exists() or file_path.stat().st_size == 0:
            self.status_callback(f"❌ File not found or empty: {file_path.name}")
            self._disconnect()
            return False

        file_size = file_path.stat().st_size
        if file_size > MAX_FILE_SIZE:
             self.status_callback(f"❌ File too large: {format_size(file_size)}")
             self._disconnect()
             return False

        checksum = self._calculate_md5(file_path)
        filename = file_path.name

        try:
            # 1. Send Metadata Request
            metadata_payload = pack_file_metadata(filename, file_size, checksum)
            request_packet = pack_message(FILE_REQUEST_UPLOAD, metadata_payload)
            self.sock.sendall(request_packet)
            
            self.status_callback(f"📤 Uploading {filename} ({format_size(file_size)})...")

            # 2. Send File Chunks
            with open(file_path, 'rb') as f:
                bytes_sent = 0
                while bytes_sent < file_size:
                    chunk = f.read(FILE_CHUNK_SIZE)
                    if not chunk: break
                    
                    self.sock.sendall(pack_message(FILE_CHUNK, chunk))
                    bytes_sent += len(chunk)
            
            # 3. Wait for Acknowledgment
            ack_raw = read_tcp_message(self.sock)
            if ack_raw is None:
                self.status_callback(f"❌ Upload failed: No response from server.")
                return False

            _, ack_type, _, _, ack_payload = unpack_message(ack_raw)

            if ack_type == FILE_ACK_SUCCESS:
                self.status_callback(f"✅ Upload successful: {filename}")
                return True
            else:
                reason = ack_payload.decode('utf-8')
                self.status_callback(f"❌ Upload failed: {reason}")
                return False

        except Exception as e:
            self.status_callback(f"❌ Upload error: {str(e)}")
            return False
        finally:
            self._disconnect()

    def download_file(self, file_name, save_path):
        """Downloads a file from the server."""
        if not self._connect(): return False

        output_file = Path(save_path) / file_name
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # 1. Send Download Request
            request_packet = pack_message(FILE_REQUEST_DOWNLOAD, file_name.encode('utf-8'))
            self.sock.sendall(request_packet)
            
            # 2. Receive Metadata
            metadata_raw = read_tcp_message(self.sock)
            if metadata_raw is None:
                self.status_callback(f"❌ Download failed: No metadata received.")
                return False

            _, msg_type, _, _, metadata_payload = unpack_message(metadata_raw)
            
            if msg_type == FILE_ACK_FAILURE:
                self.status_callback(f"❌ Download failed: {metadata_payload.decode('utf-8')}")
                return False
            if msg_type != FILE_METADATA:
                self.status_callback("❌ Download failed: Unexpected server response.")
                return False

            metadata = unpack_file_metadata(metadata_payload)
            filesize = metadata['filesize']
            checksum = metadata.get('checksum')
            
            self.status_callback(f"📥 Downloading {file_name} ({format_size(filesize)})...")

            # 3. Receive File Chunks
            bytes_received = 0
            with open(output_file, 'wb') as f:
                while bytes_received < filesize:
                    chunk_raw = read_tcp_message(self.sock)
                    if chunk_raw is None:
                         raise ConnectionAbortedError("Connection lost during download.")
                    
                    _, chunk_type, _, _, chunk_payload = unpack_message(chunk_raw)
                    
                    if chunk_type != FILE_CHUNK:
                        raise ValueError("Unexpected message received in file stream.")

                    f.write(chunk_payload)
                    bytes_received += len(chunk_payload)

            if bytes_received != filesize:
                 raise IOError("Incomplete download received.")

            # 4. Verification
            if checksum:
                actual_checksum = self._calculate_md5(output_file)
                if actual_checksum != checksum:
                    self.status_callback(f"❌ Checksum mismatch for {file_name}. File may be corrupted.")
                    os.remove(output_file)
                    return False
            
            self.status_callback(f"✅ Download complete: {output_file.name}")
            return True

        except Exception as e:
            self.status_callback(f"❌ Download error: {str(e)}")
            return False
        finally:
            self._disconnect()