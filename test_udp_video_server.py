#!/usr/bin/env python3
"""
optimized_server.py

- Selector-based non-blocking UDP listener
- Per-client outgoing queues with dedicated sender threads
- Keeps newest packets when client queue is full (drop oldest)
"""
import os
import sys
import socket
import selectors
import threading
import queue
import time

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.constants import VIDEO_PORT, UDP_STREAM_BUFFER, SOCKET_TIMEOUT
from shared.protocol import STREAM_VIDEO, CMD_REGISTER
from server.utils import unpack_message

class UltraLowLatencyServer:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, UDP_STREAM_BUFFER * 4)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, UDP_STREAM_BUFFER * 4)
        except Exception:
            pass
        self.sock.setblocking(False)
        self.sock.bind(('0.0.0.0', VIDEO_PORT))

        self.selector = selectors.DefaultSelector()
        self.selector.register(self.sock, selectors.EVENT_READ)

        # client -> queue
        self.client_queues = {}
        self.clients = set()
        self.lock = threading.Lock()
        self.running = True

    def start(self):
        print("=" * 60)
        print(f"ULTRA LOW LATENCY SERVER LISTENING ON UDP {VIDEO_PORT}")
        print("=" * 60)
        try:
            while self.running:
                events = self.selector.select(timeout=0.01)
                for key, mask in events:
                    try:
                        data, addr = key.fileobj.recvfrom(UDP_STREAM_BUFFER)
                    except BlockingIOError:
                        continue
                    except Exception:
                        continue

                    # unpack
                    try:
                        _, msg_type, _, _, payload = unpack_message(data)
                    except Exception:
                        continue

                    if msg_type == CMD_REGISTER:
                        self._register_client(addr)
                    elif msg_type == STREAM_VIDEO:
                        self._enqueue_broadcast(data, addr)

        except KeyboardInterrupt:
            print("Server interrupted by user")
        finally:
            self.stop()

    def _register_client(self, addr):
        with self.lock:
            if addr not in self.clients:
                self.clients.add(addr)
                q = queue.Queue(maxsize=8)
                self.client_queues[addr] = q
                t = threading.Thread(target=self._client_sender, args=(addr,), daemon=True)
                t.start()
                print(f"Client registered: {addr} (total {len(self.clients)})")

    def _enqueue_broadcast(self, data, sender_addr):
        with self.lock:
            # broadcast to copies of clients set to avoid runtime change
            for client in list(self.clients):
                if client == sender_addr:
                    continue
                q = self.client_queues.get(client)
                if q is None:
                    continue
                if q.full():
                    try:
                        _ = q.get_nowait()  # drop oldest
                    except Exception:
                        pass
                try:
                    q.put_nowait(data)
                except Exception:
                    pass

    def _client_sender(self, addr):
        q = self.client_queues.get(addr)
        if q is None:
            return
        while self.running:
            try:
                data = q.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                self.sock.sendto(data, addr)
            except BlockingIOError:
                # kernel full: small backoff
                time.sleep(0.005)
            except Exception as e:
                # on unrecoverable error unregister client
                print(f"Send error to {addr}: {e}")
                with self.lock:
                    try:
                        self.clients.remove(addr)
                        del self.client_queues[addr]
                    except Exception:
                        pass
                return

    def stop(self):
        if not self.running:
            return
        print("\n[STOP] Server shutting down")
        self.running = False
        try:
            self.selector.unregister(self.sock)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass
        print("Server stopped")

if __name__ == '__main__':
    s = UltraLowLatencyServer()
    s.start()
