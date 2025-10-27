"""
Standalone UDP Video Receiver Test
Tests receiving and displaying video from UDP server.
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

from shared.constants import VIDEO_PORT, UDP_STREAM_BUFFER, CONNECTION_TIMEOUT
from shared.protocol import STREAM_VIDEO, CMD_REGISTER
from client.utils import pack_message, unpack_message, decode_jpeg_to_frame

class VideoReceiver:
    """Receives and displays video from UDP server."""
    
    def __init__(self, server_ip='127.0.0.1'):
        self.server_ip = server_ip
        self.server_port = VIDEO_PORT
        self.sock = None
        self.running = True
        
    def start(self):
        """Start receiving and displaying."""
        try:
            print("=" * 70)
            print("UDP VIDEO RECEIVER TEST - STARTED")
            print("=" * 70)
            print(f"Server: {self.server_ip}:{self.server_port}")
            
            # Initialize socket
            print("\nInitializing UDP socket...")
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Increase buffer size to prevent packet loss
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, UDP_STREAM_BUFFER * 4)
            self.sock.settimeout(1.0)  # Shorter timeout for more responsive frame display
            
            # Bind to any available port
            self.sock.bind(('', 0))
            local_port = self.sock.getsockname()[1]
            print(f"✓ UDP socket created")
            print(f"  Local port: {local_port}")
            
            # Register with server
            print(f"\nRegistering with server...")
            reg_packet = pack_message(CMD_REGISTER, b"VIDEO")
            for i in range(3):
                self.sock.sendto(reg_packet, (self.server_ip, self.server_port))
                time.sleep(0.1)
            print(f"✓ Registration packets sent")
            
            print("\n" + "=" * 70)
            print("RECEIVING VIDEO")
            print("=" * 70)
            print("Waiting for video frames...")
            print("Press 'q' in the video window or Ctrl+C to stop\n")
            
            frame_count = 0
            display_count = 0
            start_time = time.time()
            last_report = time.time()
            last_frame_time = time.time()
            display_interval = 1.0 / 30  # Display at 30 FPS max
            last_display_time = time.time()
            
            while self.running:
                try:
                    # Receive data
                    data, sender_addr = self.sock.recvfrom(UDP_STREAM_BUFFER)
                    
                    # Parse message
                    try:
                        version, msg_type, payload_length, seq_num, payload = unpack_message(data)
                        
                        if msg_type == STREAM_VIDEO:
                            frame_count += 1
                            last_frame_time = time.time()
                            
                            # Throttle display updates to prevent overwhelming CV2
                            now = time.time()
                            if now - last_display_time < display_interval:
                                continue  # Skip displaying this frame
                            
                            # Decode JPEG to frame
                            frame = decode_jpeg_to_frame(payload)
                            if frame is not None:
                                # Display frame
                                cv2.imshow('Video Receiver - Press Q to quit', frame)
                                display_count += 1
                                last_display_time = now
                                
                                key = cv2.waitKey(1) & 0xFF
                                if key == ord('q'):
                                    print("\nQuit key pressed")
                                    break
                                # Check if window was closed (X button)
                                try:
                                    if cv2.getWindowProperty('Video Receiver - Press Q to quit', cv2.WND_PROP_VISIBLE) < 1:
                                        print("\nWindow closed")
                                        break
                                except:
                                    print("\nWindow closed")
                                    break
                            else:
                                print("✗ Failed to decode frame")
                                
                    except ValueError as e:
                        print(f"✗ Malformed packet: {e}")
                        
                except socket.timeout:
                    # Check if we haven't received frames in a while
                    if time.time() - last_frame_time > 5.0 and frame_count > 0:
                        print("⚠ No frames received for 5 seconds")
                        last_frame_time = time.time()
                    continue
                    
                # Report stats every 2 seconds
                now = time.time()
                if now - last_report >= 2.0:
                    elapsed = now - start_time
                    recv_fps = frame_count / elapsed if elapsed > 0 else 0
                    display_fps = display_count / elapsed if elapsed > 0 else 0
                    print(f"📹 Received: {frame_count} ({recv_fps:.1f} FPS) | Displayed: {display_count} ({display_fps:.1f} FPS) | From: {sender_addr[0]}")
                    last_report = now
                    
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
        
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
                
        cv2.destroyAllWindows()
        
        print("\n" + "=" * 70)
        print("UDP VIDEO RECEIVER - STOPPED")
        print("=" * 70)

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='UDP Video Receiver Test')
    parser.add_argument('--server', type=str, default='127.0.0.1',
                        help='Server IP address (default: 127.0.0.1)')
    args = parser.parse_args()
    
    receiver = VideoReceiver(server_ip=args.server)
    receiver.start()
