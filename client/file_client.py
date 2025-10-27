"""
Sapora LAN Collaboration Suite - File Transfer Client (optimized)
Handles reliable TCP file upload and download operations.
"""

import socket
import os
import hashlib
from pathlib import Path
import sys
import time

# Add parent path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.constants import (
    FILE_TRANSFER_PORT, FILE_CHUNK_SIZE, MAX_FILE_SIZE, CONNECTION_TIMEOUT,
)
from shared.protocol import (
    FILE_REQUEST_UPLOAD, FILE_REQUEST_DOWNLOAD, FILE_METADATA, FILE_CHUNK,
    FILE_ACK_SUCCESS, FILE_ACK_FAILURE
)
from client.utils import pack_message, unpack_message, read_tcp_message, format_size
from shared.helpers import pack_file_metadata, unpack_file_metadata


class FileTransferClient:
    """Handles file upload and download operations."""

    def __init__(self, server_ip, server_port=FILE_TRANSFER_PORT, status_callback=None):
        self.server_ip = server_ip
        self.server_port = server_port
        self.status_callback = status_callback or (lambda msg: None)
        self.sock = None

    def _connect(self):
        """Establishes a temporary TCP connection for the transfer."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(CONNECTION_TIMEOUT)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.connect((self.server_ip, self.server_port))
            return True
        except Exception as e:
            self.status_callback(f"❌ File connection error: {e}")
            self._disconnect()
            return False

    def _disconnect(self):
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        self.sock = None

    def _calculate_md5(self, file_path: Path):
        """Calculates MD5 checksum of file."""
        md5_hash = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(FILE_CHUNK_SIZE), b''):
                    md5_hash.update(chunk)
            return md5_hash.hexdigest()
        except Exception:
            return None

    def upload_file(self, file_path_str):
        """Uploads a file to the server. Returns True/False."""
        file_path = Path(file_path_str)
        if not file_path.exists() or file_path.stat().st_size == 0:
            self.status_callback(f"❌ File not found or empty: {file_path.name}")
            return False

        file_size = file_path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            self.status_callback(f"❌ File too large: {format_size(file_size)}")
            return False

        if not self._connect():
            return False

        checksum = self._calculate_md5(file_path) or ""
        filename = file_path.name

        try:
            # send upload request with metadata
            metadata_payload = pack_file_metadata(filename, file_size, checksum)
            request_packet = pack_message(FILE_REQUEST_UPLOAD, metadata_payload)
            self.sock.sendall(request_packet)
            self.status_callback(f"📤 Uploading {filename} ({format_size(file_size)})...")

            bytes_sent = 0
            last_report = time.time()
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(FILE_CHUNK_SIZE)
                    if not chunk:
                        break
                    try:
                        self.sock.sendall(pack_message(FILE_CHUNK, chunk))
                    except Exception as e:
                        self.status_callback(f"❌ Send error: {e}")
                        raise

                    bytes_sent += len(chunk)

                    # occasional progress update (every 1s)
                    if time.time() - last_report >= 1.0:
                        self.status_callback(f"📤 Sent {format_size(bytes_sent)} / {format_size(file_size)}")
                        last_report = time.time()

            # wait for ack
            ack_raw = read_tcp_message(self.sock)
            if ack_raw is None:
                self.status_callback("❌ Upload failed: No response from server.")
                return False

            _, ack_type, _, _, ack_payload = unpack_message(ack_raw)
            if ack_type == FILE_ACK_SUCCESS:
                self.status_callback(f"✅ Upload successful: {filename}")
                return True
            else:
                reason = ack_payload.decode('utf-8', errors='ignore')
                self.status_callback(f"❌ Upload failed: {reason}")
                return False

        except Exception as e:
            self.status_callback(f"❌ Upload error: {e}")
            return False
        finally:
            self._disconnect()

    def download_file(self, file_name, save_path):
        """Downloads a file from the server. Returns True/False."""
        try:
            output_dir = Path(save_path)
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.status_callback(f"❌ Invalid save path: {e}")
            return False

        if not self._connect():
            return False

        try:
            # request download
            request_packet = pack_message(FILE_REQUEST_DOWNLOAD, file_name.encode('utf-8'))
            self.sock.sendall(request_packet)

            # read metadata
            metadata_raw = read_tcp_message(self.sock)
            if metadata_raw is None:
                self.status_callback("❌ Download failed: No metadata received.")
                return False

            _, msg_type, _, _, metadata_payload = unpack_message(metadata_raw)

            if msg_type == FILE_ACK_FAILURE:
                self.status_callback(f"❌ Download failed: {metadata_payload.decode('utf-8', errors='ignore')}")
                return False
            if msg_type != FILE_METADATA:
                self.status_callback("❌ Download failed: Unexpected server response.")
                return False

            metadata = unpack_file_metadata(metadata_payload)
            filesize = int(metadata.get('filesize', 0))
            checksum = metadata.get('checksum')

            if filesize <= 0:
                self.status_callback("❌ Download failed: Invalid filesize.")
                return False

            self.status_callback(f"📥 Downloading {file_name} ({format_size(filesize)})...")

            output_file = output_dir / file_name
            bytes_received = 0
            last_report = time.time()
            with open(output_file, 'wb') as f:
                while bytes_received < filesize:
                    chunk_raw = read_tcp_message(self.sock)
                    if chunk_raw is None:
                        raise ConnectionAbortedError("Connection lost during download.")

                    _, chunk_type, _, _, chunk_payload = unpack_message(chunk_raw)
                    if chunk_type != FILE_CHUNK:
                        raise ValueError("Unexpected message received during download.")

                    f.write(chunk_payload)
                    bytes_received += len(chunk_payload)

                    # occasional progress update
                    if time.time() - last_report >= 1.0:
                        self.status_callback(f"📥 Received {format_size(bytes_received)} / {format_size(filesize)}")
                        last_report = time.time()

            if bytes_received != filesize:
                raise IOError("Incomplete download received.")

            # verify checksum
            if checksum:
                actual_checksum = self._calculate_md5(output_file) or ""
                if actual_checksum != checksum:
                    try:
                        output_file.unlink()
                    except Exception:
                        pass
                    self.status_callback("❌ Checksum mismatch: file may be corrupted.")
                    return False

            self.status_callback(f"✅ Download complete: {output_file.name}")
            return True

        except Exception as e:
            self.status_callback(f"❌ Download error: {e}")
            return False
        finally:
            self._disconnect()
