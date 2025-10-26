"""
Sapora LAN Collaboration Suite - Unified Server Main Entry Point
Manages all services: Control, Chat, Video, Audio, File Transfer, Screen Sharing.
"""
import sys
import os
import time
import signal
import threading
from datetime import datetime

# --- CRITICAL FIX: Add project root to path for shared/ imports ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
# -----------------------------------------------------------------

# Import constants/protocol/services
from shared.constants import (
    CONTROL_PORT, CHAT_PORT, VIDEO_PORT, AUDIO_PORT, 
    FILE_TRANSFER_PORT, SCREEN_SHARE_PORT
)
from server.connection_manager import ConnectionManager
from server.tcp_handler import ControlServer 
from server.udp_video_server import UDPVideoServer
from server.udp_audio_server import UDPAudioServer
from server.file_server import FileTransferServer
from server.screen_share_server import ScreenShareServer

class UnifiedServer:
    """Manages and runs all collaboration server services."""
    
    def __init__(self):
        self.manager = ConnectionManager()
        self.services = []
        self.running = False
        
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def start_all(self):
        """Starts all server services."""
        print("\n" + "=" * 70)
        print("🌐 SAPORA LAN COLLABORATION SERVER - STARTING ALL SERVICES")
        print("=" * 70)
        print(f"⏰ Server started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        self.running = True
        
        service_configs = [
            ('Control/Chat', ControlServer, CONTROL_PORT),
            ('File Transfer', FileTransferServer, FILE_TRANSFER_PORT),
            ('Screen Share', ScreenShareServer, SCREEN_SHARE_PORT),
            ('UDP Video', UDPVideoServer, VIDEO_PORT),
            ('UDP Audio', UDPAudioServer, AUDIO_PORT)
        ]
        
        for name, service_class, port in service_configs:
            try:
                service_instance = service_class(self.manager) 
                self.services.append(service_instance)
                
                service_instance.start()
                print(f"✓ {name:20s} → Port {port:5d} [RUNNING]")
                time.sleep(0.2)
            except Exception as e:
                print(f"✗ {name:20s} → Port {port:5d} [FAILED: {e}]")
        
        print("\n" + "=" * 70)
        print("🚀 ALL SERVICES ACTIVE")
        print("=" * 70)
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nReceived keyboard interrupt.")
        finally:
            self.stop_all()

    def stop_all(self):
        """Stops all server services gracefully."""
        if not self.running:
            return
        
        print("\n\n" + "=" * 70)
        print("🛑 SHUTTING DOWN ALL SERVICES")
        print("=" * 70)
        
        self.running = False
        self.manager.stop() 
        
        for service in self.services:
            name = service.__class__.__name__
            try:
                print(f"⏳ Stopping {name}...")
                service.stop()
                print(f"✓ {name} stopped")
            except Exception as e:
                print(f"⚠️  Error stopping {name}: {e}")
        
        print("\n" + "=" * 70)
        print("✓ SHUTDOWN COMPLETE")
        print("=" * 70)
        print(f"⏰ Server stopped at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    def _signal_handler(self, signum, frame):
        """Handles shutdown signals."""
        print(f"\n\n⚠️ Received signal {signum}")
        self.stop_all()
        os._exit(0) 

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Sapora LAN Collaboration Server')
    parser.add_argument('--service', choices=['all'], default='all', help='Service to start (default: all)')
    args = parser.parse_args()
    
    if args.service == 'all':
        server = UnifiedServer()
        server.start_all()

if __name__ == '__main__':
    main()