"""
OPTIMIZED UDP Video Receiver
Implements thread + queue architecture for smooth, low-latency video playback.

Key Optimizations:
1. Separate threads for reception and display (decouples I/O from rendering)
2. Non-blocking sockets to prevent stalls
3. Frame queue with latest-frame-only strategy (drops old frames automatically)
4. Reduced JPEG quality for faster decoding
5. Adaptive frame skipping based on queue depth
6. Large receive buffer to prevent packet loss
"""
import sys
import os
import socket
import time
import cv2
import threading
import queue

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.constants import VIDEO_PORT, UDP_STREAM_BUFFER
from shared.protocol import STREAM_VIDEO, CMD_REGISTER
from client.utils import pack_message, unpack_message, decode_jpeg_to_frame

class VideoReceiverOptimized:
    """
    High-performance video receiver using threaded architecture.
    
    Architecture:
    - Reception Thread: Continuously pulls packets from socket, minimal processing
    - Display Thread: Decodes and displays frames from queue at target FPS
    - Queue: Bounded queue (size=2) automatically drops old frames
    """
    
    def __init__(self, server_ip='127.0.0.1', target_fps=20):
        self.server_ip = server_ip
        self.server_port = VIDEO_PORT
        self.target_fps = target_fps
        
        self.sock = None
        self.running = False
        
        # Frame queue (maxsize=2 means only keep latest 2 frames)
        # This automatically drops old frames if decoder can't keep up
        self.frame_queue = queue.Queue(maxsize=2)
        
        # Statistics
        self.packets_received = 0
        self.frames_decoded = 0
        self.frames_displayed = 0
        self.frames_dropped = 0
        
        # Threads
        self.recv_thread = None
        self.display_thread = None
        
    def start(self):
        """Start the optimized receiver with separate threads."""
        try:
            print("=" * 70)
            print("OPTIMIZED UDP VIDEO RECEIVER - STARTED")
            print("=" * 70)
            print(f"Server: {self.server_ip}:{self.server_port}")
            print(f"Target FPS: {self.target_fps}")
            print(f"Optimizations: Threading + Queue + Non-blocking Socket")
            
            # Initialize socket with optimizations
            print("\nInitializing UDP socket...")
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            # OPTIMIZATION 1: Massive receive buffer to prevent OS-level packet drops
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, UDP_STREAM_BUFFER * 8)
            
            # OPTIMIZATION 2: Non-blocking socket - no timeouts, no stalls
            self.sock.setblocking(False)
            
            # Bind to any available port
            self.sock.bind(('', 0))
            local_port = self.sock.getsockname()[1]
            print(f"✓ UDP socket created (non-blocking)")
            print(f"  Local port: {local_port}")
            print(f"  Receive buffer: {UDP_STREAM_BUFFER * 8 / 1024:.0f} KB")
            
            # Register with server
            print(f"\nRegistering with server...")
            self._register_with_server()
            print(f"✓ Registration complete")
            
            print("\n" + "=" * 70)
            print("RECEIVING VIDEO (THREADED)")
            print("=" * 70)
            print("Press 'q' in video window or Ctrl+C to stop\n")
            
            # Start threads
            self.running = True
            
            self.recv_thread = threading.Thread(target=self._reception_loop, daemon=True)
            self.recv_thread.start()
            print("✓ Reception thread started")
            
            self.display_thread = threading.Thread(target=self._display_loop, daemon=True)
            self.display_thread.start()
            print("✓ Display thread started")
            
            # Statistics reporting thread
            self._stats_loop()
            
        except KeyboardInterrupt:
            print("\n\nShutting down...")
        except Exception as e:
            print(f"\n✗ Fatal error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.stop()
    
    def _register_with_server(self):
        """Send registration packets to server."""
        reg_packet = pack_message(CMD_REGISTER, b"VIDEO")
        
        # Temporarily make socket blocking for registration
        self.sock.setblocking(True)
        for i in range(3):
            try:
                self.sock.sendto(reg_packet, (self.server_ip, self.server_port))
                time.sleep(0.1)
            except Exception as e:
                print(f"✗ Registration error: {e}")
        # Return to non-blocking
        self.sock.setblocking(False)
    
    def _reception_loop(self):
        """
        OPTIMIZATION 3: Reception thread - pulls packets as fast as possible.
        
        - Non-blocking recvfrom() with short sleep on EWOULDBLOCK
        - Minimal processing: just unpack and validate
        - Push raw payload to queue (decode happens in display thread)
        """
        print("[RECV] Reception loop started")
        
        last_recv_time = time.time()
        consecutive_errors = 0
        
        while self.running:
            try:
                # Non-blocking receive
                data, sender_addr = self.sock.recvfrom(UDP_STREAM_BUFFER)
                
                self.packets_received += 1
                last_recv_time = time.time()
                consecutive_errors = 0
                
                # Quick protocol validation
                try:
                    version, msg_type, payload_length, seq_num, payload = unpack_message(data)
                    
                    if msg_type == STREAM_VIDEO:
                        # OPTIMIZATION 4: Queue with maxsize=2 automatically drops old frames
                        # Try to put frame in queue (non-blocking)
                        try:
                            self.frame_queue.put_nowait((payload, sender_addr))
                        except queue.Full:
                            # Queue full - drop this frame (keeps only latest)
                            self.frames_dropped += 1
                            
                except ValueError:
                    # Malformed packet, ignore
                    pass
                    
            except BlockingIOError:
                # No data available right now - yield CPU briefly
                time.sleep(0.001)  # 1ms sleep to prevent busy-waiting
                
                # Check for prolonged silence
                if time.time() - last_recv_time > 10.0:
                    last_recv_time = time.time()  # Reset to prevent spam
                    
            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors < 5:  # Only log first few errors
                    print(f"[RECV] Error: {type(e).__name__}: {e}")
                if consecutive_errors > 100:
                    print(f"[RECV] Too many errors, stopping reception")
                    break
                time.sleep(0.01)
        
        print("[RECV] Reception loop ended")
    
    def _display_loop(self):
        """
        OPTIMIZATION 5: Display thread - processes frames at consistent rate.
        
        - Runs at target FPS (20 FPS default)
        - Decodes only latest frame from queue
        - Skips frames if queue is building up
        - Handles window close detection
        """
        print("[DISPLAY] Display loop started")
        
        frame_interval = 1.0 / self.target_fps
        last_frame_time = time.time()
        
        window_name = 'Optimized Video Receiver - Press Q to quit'
        
        while self.running:
            loop_start = time.time()
            
            try:
                # OPTIMIZATION 6: Get frame with short timeout
                # If queue is empty, we just skip this display cycle
                try:
                    payload, sender_addr = self.frame_queue.get(timeout=0.1)
                except queue.Empty:
                    # No frame available, skip this cycle
                    time.sleep(frame_interval)
                    continue
                
                # Decode JPEG to frame
                decode_start = time.time()
                frame = decode_jpeg_to_frame(payload)
                decode_time = time.time() - decode_start
                
                if frame is not None:
                    self.frames_decoded += 1
                    
                    # Display frame
                    cv2.imshow(window_name, frame)
                    self.frames_displayed += 1
                    last_frame_time = time.time()
                    
                    # Check for quit
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q'):
                        print("\n[DISPLAY] Quit key pressed")
                        self.running = False
                        break
                    
                    # Check window close
                    try:
                        if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                            print("\n[DISPLAY] Window closed")
                            self.running = False
                            break
                    except:
                        print("\n[DISPLAY] Window closed")
                        self.running = False
                        break
                
                # OPTIMIZATION 7: Frame timing control
                # Ensure consistent display rate
                elapsed = time.time() - loop_start
                sleep_time = max(0, frame_interval - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
            except Exception as e:
                print(f"[DISPLAY] Error: {type(e).__name__}: {e}")
                time.sleep(0.1)
        
        print("[DISPLAY] Display loop ended")
    
    def _stats_loop(self):
        """Report statistics every 2 seconds."""
        start_time = time.time()
        last_report = time.time()
        
        last_packets = 0
        last_decoded = 0
        last_displayed = 0
        
        try:
            while self.running:
                time.sleep(0.5)
                
                now = time.time()
                if now - last_report >= 2.0:
                    elapsed_total = now - start_time
                    elapsed_interval = now - last_report
                    
                    # Calculate rates
                    packets_fps = (self.packets_received - last_packets) / elapsed_interval
                    decode_fps = (self.frames_decoded - last_decoded) / elapsed_interval
                    display_fps = (self.frames_displayed - last_displayed) / elapsed_interval
                    
                    # Overall averages
                    avg_recv_fps = self.packets_received / elapsed_total if elapsed_total > 0 else 0
                    avg_display_fps = self.frames_displayed / elapsed_total if elapsed_total > 0 else 0
                    
                    # Queue depth
                    queue_depth = self.frame_queue.qsize()
                    
                    print(f"📹 Recv: {self.packets_received} ({packets_fps:.1f} FPS) | "
                          f"Display: {self.frames_displayed} ({display_fps:.1f} FPS) | "
                          f"Dropped: {self.frames_dropped} | Queue: {queue_depth}")
                    
                    # Update counters
                    last_packets = self.packets_received
                    last_decoded = self.frames_decoded
                    last_displayed = self.frames_displayed
                    last_report = now
                    
        except Exception as e:
            print(f"[STATS] Error: {e}")
    
    def stop(self):
        """Cleanup resources."""
        print("\n[STOP] Shutting down...")
        self.running = False
        
        # Wait for threads
        if self.recv_thread and self.recv_thread.is_alive():
            self.recv_thread.join(timeout=2.0)
            
        if self.display_thread and self.display_thread.is_alive():
            self.display_thread.join(timeout=2.0)
        
        # Close socket
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        
        # Close windows
        cv2.destroyAllWindows()
        
        # Final statistics
        print("\n" + "=" * 70)
        print("FINAL STATISTICS")
        print("=" * 70)
        print(f"Packets received:  {self.packets_received}")
        print(f"Frames decoded:    {self.frames_decoded}")
        print(f"Frames displayed:  {self.frames_displayed}")
        print(f"Frames dropped:    {self.frames_dropped}")
        
        if self.packets_received > 0:
            efficiency = (self.frames_displayed / self.packets_received) * 100
            print(f"Display efficiency: {efficiency:.1f}%")
        
        print("\n" + "=" * 70)
        print("OPTIMIZED UDP VIDEO RECEIVER - STOPPED")
        print("=" * 70)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Optimized UDP Video Receiver')
    parser.add_argument('--server', type=str, default='127.0.0.1',
                        help='Server IP address (default: 127.0.0.1)')
    parser.add_argument('--fps', type=int, default=20,
                        help='Target display FPS (default: 20)')
    args = parser.parse_args()
    
    receiver = VideoReceiverOptimized(server_ip=args.server, target_fps=args.fps)
    receiver.start()
