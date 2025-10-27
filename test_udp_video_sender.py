"""
Standalone UDP Video Sender Test
Tests webcam capture and sending to UDP server.
"""
import sys
import os
import socket
import time
import cv2

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.constants import VIDEO_PORT, VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS
from shared.protocol import STREAM_VIDEO, CMD_REGISTER
from client.utils import pack_message, encode_frame_to_jpeg

class VideoSender:
    """Captures webcam and sends to UDP server."""
    
    def __init__(self, server_ip='127.0.0.1'):
        self.server_ip = server_ip
        self.server_port = VIDEO_PORT
        self.sock = None
        self.cap = None
        self.running = True
        
    def start(self):
        """Start capturing and sending."""
        try:
            print("=" * 70)
            print("UDP VIDEO SENDER TEST - STARTED")
            print("=" * 70)
            print(f"Target server: {self.server_ip}:{self.server_port}")
            
            # Initialize camera
            print("\nInitializing webcam...")
            self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)  # Windows optimized
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(0)  # Fallback
                if not self.cap.isOpened():
                    print("✗ ERROR: Cannot open webcam!")
                    print("  Make sure no other application is using the camera.")
                    return
            
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, VIDEO_WIDTH)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, VIDEO_HEIGHT)
            self.cap.set(cv2.CAP_PROP_FPS, VIDEO_FPS)
            
            actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = int(self.cap.get(cv2.CAP_PROP_FPS))
            
            print(f"✓ Webcam opened")
            print(f"  Resolution: {actual_width}x{actual_height}")
            print(f"  Target FPS: {VIDEO_FPS}")
            
            # Initialize socket
            print("\nInitializing UDP socket...")
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            print(f"✓ UDP socket created")
            
            # Send registration
            print(f"\nRegistering with server...")
            reg_packet = pack_message(CMD_REGISTER, b"VIDEO")
            for i in range(3):
                self.sock.sendto(reg_packet, (self.server_ip, self.server_port))
                time.sleep(0.1)
            print(f"✓ Registration packets sent")
            
            print("\n" + "=" * 70)
            print("STREAMING VIDEO")
            print("=" * 70)
            print("Press 'q' in the preview window or Ctrl+C to stop\n")
            
            frame_interval = 1.0 / VIDEO_FPS
            frame_count = 0
            start_time = time.time()
            last_report = time.time()
            
            while self.running:
                loop_start = time.time()
                
                # Capture frame
                ret, frame = self.cap.read()
                if not ret:
                    print("✗ Failed to read frame from camera")
                    time.sleep(0.1)
                    continue
                
                # Encode to JPEG
                try:
                    jpeg_bytes = encode_frame_to_jpeg(frame)
                    jpeg_size_kb = len(jpeg_bytes) / 1024
                except Exception as e:
                    print(f"✗ Encoding error: {e}")
                    continue
                
                # Pack and send
                packet = pack_message(STREAM_VIDEO, jpeg_bytes)
                try:
                    self.sock.sendto(packet, (self.server_ip, self.server_port))
                    frame_count += 1
                except Exception as e:
                    print(f"✗ Send error: {e}")
                
                # Show local preview
                cv2.imshow('Video Sender - Press Q to quit', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    print("\nQuit key pressed")
                    break
                
                # Report stats every 2 seconds
                now = time.time()
                if now - last_report >= 2.0:
                    elapsed = now - start_time
                    fps = frame_count / elapsed if elapsed > 0 else 0
                    print(f"📹 Frames sent: {frame_count} | FPS: {fps:.1f} | Size: {jpeg_size_kb:.1f} KB")
                    last_report = now
                
                # Control frame rate
                elapsed = time.time() - loop_start
                sleep_time = max(0, frame_interval - elapsed)
                time.sleep(sleep_time)
                
        except KeyboardInterrupt:
            print("\n\nShutting down...")
        except Exception as e:
            print(f"\n✗ Fatal error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.stop()
            
    def stop(self):
        """Cleanup resources."""
        self.running = False
        
        if self.cap:
            try:
                self.cap.release()
            except:
                pass
                
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
                
        cv2.destroyAllWindows()
        
        print("\n" + "=" * 70)
        print("UDP VIDEO SENDER - STOPPED")
        print("=" * 70)

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='UDP Video Sender Test')
    parser.add_argument('--server', type=str, default='127.0.0.1',
                        help='Server IP address (default: 127.0.0.1)')
    args = parser.parse_args()
    
    sender = VideoSender(server_ip=args.server)
    sender.start()
