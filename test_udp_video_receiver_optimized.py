#!/usr/bin/env python3
"""
optimized_receiver.py

- Non-blocking UDP socket
- Reception thread -> decode thread -> display thread
- Small queues, latest-frame-first behavior
- Works with your existing shared.* and client.utils when available;
  falls back to OpenCV decode if needed.
"""
import os
import sys
import socket
import time
import threading
import queue
import cv2

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.constants import VIDEO_PORT, UDP_STREAM_BUFFER
from shared.protocol import STREAM_VIDEO, CMD_REGISTER
from client.utils import pack_message, unpack_message
# optional helper; fall back if not present
try:
    from client.utils import decode_jpeg_to_frame
except Exception:
    def decode_jpeg_to_frame(payload_bytes):
        import numpy as np
        arr = np.frombuffer(payload_bytes, dtype='uint8')
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return frame

class VideoReceiverOptimized:
    def __init__(self, server_ip='127.0.0.1', target_fps=20):
        self.server_ip = server_ip
        self.server_port = VIDEO_PORT
        self.target_fps = target_fps

        self.sock = None
        self.running = False

        # Pipelines
        self.recv_queue = queue.Queue(maxsize=4)    # raw payload bytes
        self.decode_queue = queue.Queue(maxsize=3)  # decoded frames ready to display

        # Stats
        self.packets_received = 0
        self.frames_decoded = 0
        self.frames_displayed = 0
        self.frames_dropped = 0

        # Threads
        self.threads = []

    def start(self):
        print("=" * 60)
        print("OPTIMIZED RECEIVER STARTING")
        print("=" * 60)

        # socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # enlarge kernel recv buffer to reduce OS drops
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, UDP_STREAM_BUFFER * 8)
        except Exception:
            pass
        self.sock.setblocking(False)
        # bind to ephemeral port (client mode)
        self.sock.bind(('', 0))
        local_port = self.sock.getsockname()[1]
        print(f"Listening (ephemeral) on local port {local_port}")

        # register with server (brief blocking)
        reg = pack_message(CMD_REGISTER, b"VIDEO")
        try:
            self.sock.setblocking(True)
            for _ in range(3):
                try:
                    self.sock.sendto(reg, (self.server_ip, self.server_port))
                except Exception:
                    pass
                time.sleep(0.02)
        finally:
            self.sock.setblocking(False)

        self.running = True

        # threads
        t_recv = threading.Thread(target=self._reception_loop, name='recv', daemon=True)
        t_dec = threading.Thread(target=self._decoder_loop, name='decoder', daemon=True)
        t_disp = threading.Thread(target=self._display_loop, name='display', daemon=True)

        self.threads = [t_recv, t_dec, t_disp]
        for t in self.threads:
            t.start()

        try:
            while self.running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("Interrupted by user")
        finally:
            self.stop()

    def _reception_loop(self):
        print("[RECV] reception thread started")
        last_recv = time.time()
        while self.running:
            try:
                data, addr = self.sock.recvfrom(UDP_STREAM_BUFFER)
                self.packets_received += 1
                last_recv = time.time()

                # unpack and quick validate
                try:
                    _, msg_type, _, _, payload = unpack_message(data)
                except Exception:
                    # malformed, skip
                    continue

                if msg_type != STREAM_VIDEO:
                    continue

                # push latest-first: if queue full, drop oldest to insert newest
                try:
                    self.recv_queue.put_nowait(payload)
                except queue.Full:
                    try:
                        _ = self.recv_queue.get_nowait()  # drop oldest
                    except Exception:
                        pass
                    try:
                        self.recv_queue.put_nowait(payload)
                        self.frames_dropped += 1
                    except Exception:
                        self.frames_dropped += 1

            except BlockingIOError:
                # nothing to read
                time.sleep(0.002)
                # detect prolonged silence optionally
                if time.time() - last_recv > 10.0:
                    last_recv = time.time()
            except Exception as e:
                # log first few errors and continue
                print(f"[RECV] error: {type(e).__name__}: {e}")
                time.sleep(0.01)
        print("[RECV] reception thread ended")

    def _decoder_loop(self):
        print("[DECODER] decoder thread started")
        while self.running:
            try:
                payload = self.recv_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                frame = decode_jpeg_to_frame(payload)
            except Exception:
                frame = None

            if frame is None:
                self.frames_dropped += 1
                continue

            # put into decode_queue; if full drop oldest decoded
            try:
                self.decode_queue.put_nowait(frame)
                self.frames_decoded += 1
            except queue.Full:
                try:
                    _ = self.decode_queue.get_nowait()
                except Exception:
                    pass
                try:
                    self.decode_queue.put_nowait(frame)
                    self.frames_dropped += 1
                except Exception:
                    self.frames_dropped += 1
        print("[DECODER] decoder thread ended")

    def _display_loop(self):
        print("[DISPLAY] display thread started")
        window = "Optimized Video Receiver - Press Q to quit"
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        frame_interval = 1.0 / max(1, self.target_fps)

        while self.running:
            loop_start = time.time()
            try:
                frame = self.decode_queue.get(timeout=0.05)
            except queue.Empty:
                # keep window responsive
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    self.running = False
                    break
                time.sleep(0.001)
                continue

            if frame is not None:
                self.frames_displayed += 1
                cv2.imshow(window, frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    self.running = False
                    break

                # handle window close
                try:
                    if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                        self.running = False
                        break
                except Exception:
                    self.running = False
                    break

            elapsed = time.time() - loop_start
            to_sleep = frame_interval - elapsed
            if to_sleep > 0:
                # clamp small sleeps to prevent drift
                time.sleep(min(to_sleep, 0.02))

        print("[DISPLAY] display thread ended")

    def stop(self):
        if not self.running:
            return
        print("\n[STOP] Shutting down receiver")
        self.running = False

        for t in self.threads:
            try:
                if t.is_alive():
                    t.join(timeout=1.0)
            except Exception:
                pass

        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass

        cv2.destroyAllWindows()

        print("=" * 40)
        print("FINAL STATS")
        print(f"Packets received : {self.packets_received}")
        print(f"Frames decoded   : {self.frames_decoded}")
        print(f"Frames displayed : {self.frames_displayed}")
        print(f"Frames dropped   : {self.frames_dropped}")
        print("=" * 40)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Optimized UDP Video Receiver')
    parser.add_argument('--server', type=str, default='127.0.0.1', help='Server IP')
    parser.add_argument('--fps', type=int, default=20, help='Target FPS')
    args = parser.parse_args()
    r = VideoReceiverOptimized(server_ip=args.server, target_fps=args.fps)
    r.start()
