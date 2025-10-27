#!/usr/bin/env python3
"""
optimized_sender.py

- Threaded capture -> encode -> send pipeline
- Low JPEG quality (configurable)
- Per-stage small queues with latest-frame-first eviction
- Lightweight pacing with minimal drift
"""
import os
import sys
import time
import socket
import threading
import queue
import cv2

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.constants import VIDEO_PORT, VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS, UDP_STREAM_BUFFER
from shared.protocol import STREAM_VIDEO, CMD_REGISTER
from client.utils import pack_message
# optional helper: if encode helper exists, prefer it
try:
    from client.utils import encode_frame_to_jpeg
except Exception:
    def encode_frame_to_jpeg(frame, quality=55):
        # returns bytes
        _, enc = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        return enc.tobytes()

class VideoSenderOptimized:
    def __init__(self, server_ip='127.0.0.1', target_fps=20, jpeg_quality=55):
        self.server_ip = server_ip
        self.server_port = VIDEO_PORT

        self.cap = None
        self.sock = None

        # small queues for fast drop-latest behavior
        self.capture_queue = queue.Queue(maxsize=2)  # raw frames
        self.encode_queue = queue.Queue(maxsize=3)   # jpeg bytes

        self.running = False
        self.target_fps = target_fps
        self.jpeg_quality = jpeg_quality

        # stats
        self.frames_sent = 0

    def start(self):
        print("=" * 60)
        print("OPTIMIZED SENDER STARTING")
        print("=" * 60)

        # open camera
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            print("✗ ERROR: Cannot open webcam")
            return

        # set requested params (best-effort)
        try:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, VIDEO_WIDTH)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, VIDEO_HEIGHT)
            self.cap.set(cv2.CAP_PROP_FPS, VIDEO_FPS)
        except Exception:
            pass

        # socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, UDP_STREAM_BUFFER * 4)
        except Exception:
            pass

        # register
        reg_packet = pack_message(CMD_REGISTER, b"VIDEO")
        for _ in range(3):
            try:
                self.sock.sendto(reg_packet, (self.server_ip, self.server_port))
            except Exception:
                pass
            time.sleep(0.02)

        self.running = True

        # threads
        t_capture = threading.Thread(target=self._capture_loop, name='capture', daemon=True)
        t_encode = threading.Thread(target=self._encode_loop, name='encode', daemon=True)
        t_send = threading.Thread(target=self._send_loop, name='send', daemon=True)

        t_capture.start()
        t_encode.start()
        t_send.start()

        try:
            while self.running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("Interrupted by user")
        finally:
            self.stop()

    def _capture_loop(self):
        print("[CAPTURE] capture thread started")
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            # latest-first policy
            try:
                self.capture_queue.put_nowait(frame)
            except queue.Full:
                try:
                    _ = self.capture_queue.get_nowait()  # drop oldest
                except Exception:
                    pass
                try:
                    self.capture_queue.put_nowait(frame)
                except Exception:
                    pass
        print("[CAPTURE] capture thread ended")

    def _encode_loop(self):
        print("[ENCODE] encode thread started")
        encode_param_quality = int(self.jpeg_quality)
        while self.running:
            try:
                frame = self.capture_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                jpeg_bytes = encode_frame_to_jpeg(frame, quality=encode_param_quality)
            except Exception:
                continue

            try:
                self.encode_queue.put_nowait(jpeg_bytes)
            except queue.Full:
                # drop oldest and insert new
                try:
                    _ = self.encode_queue.get_nowait()
                except Exception:
                    pass
                try:
                    self.encode_queue.put_nowait(jpeg_bytes)
                except Exception:
                    pass
        print("[ENCODE] encode thread ended")

    def _send_loop(self):
        print("[SEND] send thread started")
        frame_interval = 1.0 / max(1, self.target_fps)
        while self.running:
            start = time.time()
            try:
                jpeg_bytes = self.encode_queue.get(timeout=0.1)
            except queue.Empty:
                time.sleep(0.001)
                continue

            packet = pack_message(STREAM_VIDEO, jpeg_bytes)
            try:
                self.sock.sendto(packet, (self.server_ip, self.server_port))
                self.frames_sent += 1
            except BlockingIOError:
                # kernel buffer full: backoff briefly
                time.sleep(0.005)
            except Exception:
                # ignore other send errors (UDP)
                pass

            elapsed = time.time() - start
            to_sleep = frame_interval - elapsed
            if to_sleep > 0:
                time.sleep(min(to_sleep, 0.02))

        print("[SEND] send thread ended")

    def stop(self):
        if not self.running:
            return
        print("\n[STOP] Shutting down sender")
        self.running = False
        try:
            if self.cap:
                self.cap.release()
        except Exception:
            pass
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass
        cv2.destroyAllWindows()
        print(f"Frames sent: {self.frames_sent}")
        print("Sender stopped")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Optimized UDP Video Sender')
    parser.add_argument('--server', type=str, default='127.0.0.1', help='Server IP')
    parser.add_argument('--fps', type=int, default=20, help='Target FPS')
    parser.add_argument('--quality', type=int, default=55, help='JPEG quality (1-100)')
    args = parser.parse_args()

    s = VideoSenderOptimized(server_ip=args.server, target_fps=args.fps, jpeg_quality=args.quality)
    s.start()
