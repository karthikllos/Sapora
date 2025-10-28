"""
Sapora LAN Collaboration Suite - Unified Server Orchestrator
Starts and manages all server modules (audio, video, chat, file, screen share) in parallel.
Includes WebSocket gateway for Electron frontend communication.
"""

import sys
import os
import signal
import threading
import time
import json

# Add parent path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from server.connection_manager import ConnectionManager
from server.tcp_handler import ControlServer
from server.udp_audio_server import UDPAudioServer
from server.udp_video_server import UDPVideoServer
from server.file_server import FileTransferServer
from server.screen_share_server import ScreenShareServer
from shared.lan_discovery import start_server_discovery

# Flask-SocketIO for WebSocket gateway to Electron
try:
    from flask import Flask
    from flask_socketio import SocketIO, emit
    from flask_cors import CORS
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    print("⚠️  Warning: flask-socketio not installed. WebSocket gateway disabled.")
    print("   Install with: pip install flask flask-socketio flask-cors python-socketio")


class SaporaServer:
    """Main server orchestrator managing all services"""
    
    def __init__(self, enable_websocket=True):
        self.manager = ConnectionManager()
        self.manager.server_ref = self  # Allow TCPHandler to access room methods
        self.services = {}
        self.running = False
        
        # Multi-room support
        self.rooms = {}  # meeting_id: {'clients': [sockets], 'metadata': {}}
        self.client_rooms = {}  # client_socket: meeting_id
        self.rooms_lock = threading.Lock()
        
        # WebSocket gateway (optional)
        self.websocket_enabled = enable_websocket and WEBSOCKET_AVAILABLE
        self.flask_app = None
        self.socketio = None
        self.websocket_thread = None
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle Ctrl+C and termination signals"""
        print("\n🛑 Shutdown signal received...")
        self.stop()
        sys.exit(0)
    
    def start(self):
        """Start all server services"""
        print("="*60)
        print("🚀 Starting Sapora Server - LAN Collaboration Suite")
        print("="*60)
        
        self.running = True
        
        # 1. Start TCP Control Server (Chat, Registration, Heartbeat)
        print("\n📡 Starting TCP Control Server...")
        control_server = ControlServer(self.manager)
        control_server.start()
        self.services['control'] = control_server
        time.sleep(0.2)
        
        # 2. Start UDP Audio Server
        print("🎤 Starting UDP Audio Server...")
        audio_server = UDPAudioServer(self.manager)
        audio_server.start()
        self.services['audio'] = audio_server
        time.sleep(0.2)
        
        # 3. Start UDP Video Server
        print("📹 Starting UDP Video Server...")
        video_server = UDPVideoServer(self.manager)
        video_server.start()
        self.services['video'] = video_server
        time.sleep(0.2)
        
        # 4. Start File Transfer Server
        print("📁 Starting File Transfer Server...")
        file_server = FileTransferServer(self.manager)
        file_server.start()
        self.services['file'] = file_server
        time.sleep(0.2)
        
        # 5. Start Screen Share Server
        print("🖥️  Starting Screen Share Server...")
        screen_server = ScreenShareServer()
        screen_thread = threading.Thread(target=screen_server.start, daemon=True)
        screen_thread.start()
        self.services['screen'] = screen_server
        time.sleep(0.2)
        
        # 6. Start LAN discovery broadcaster
        try:
            self.discovery = start_server_discovery("Sapora Host", 5000)
        except Exception as e:
            print(f"⚠️  Discovery start failed: {e}")
        
        # 7. Start WebSocket Gateway for Electron (if enabled)
        if self.websocket_enabled:
            print("🌐 Starting WebSocket Gateway for Electron...")
            self._start_websocket_gateway()
        
        print("\n" + "="*60)
        print("✅ All Sapora Server services started successfully!")
        print("="*60)
        print("\n📊 Service Status:")
        print(f"   • TCP Control: Port 5000")
        print(f"   • Chat: Port 5001")
        print(f"   • File Transfer: Port 5002")
        print(f"   • Screen Share: Port 5003")
        print(f"   • UDP Video: Port 6000")
        print(f"   • UDP Audio: Port 6001")
        if self.websocket_enabled:
            print(f"   • WebSocket Gateway: Port 5555")
        print("\n💡 Press Ctrl+C to stop all services.\n")
        
        # Keep main thread alive
        try:
            while self.running:
                time.sleep(1)
                self._monitor_services()
        except KeyboardInterrupt:
            self.stop()
    
    def _start_websocket_gateway(self):
        """Start Flask-SocketIO WebSocket gateway for Electron communication"""
        if not WEBSOCKET_AVAILABLE:
            return
        
        self.flask_app = Flask(__name__)
        self.flask_app.config['SECRET_KEY'] = 'sapora-secret-key'
        CORS(self.flask_app)
        
        self.socketio = SocketIO(
            self.flask_app,
            cors_allowed_origins="*",
            async_mode='threading',
            logger=False,
            engineio_logger=False
        )
        
        # WebSocket event handlers
        @self.socketio.on('connect')
        def handle_connect():
            print(f"🔌 Electron client connected via WebSocket")
            emit('server_status', {'status': 'connected', 'services': list(self.services.keys())})
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            print(f"🔌 Electron client disconnected")
        
        @self.socketio.on('get_user_list')
        def handle_get_user_list():
            """Send current user list to Electron"""
            user_list = self.manager.get_user_list()
            emit('user_list_update', {'users': user_list})
        
        @self.socketio.on('get_stats')
        def handle_get_stats():
            """Send server statistics to Electron"""
            stats = {
                'control_clients': len(self.manager.control_clients),
                'stream_clients': len(self.manager.stream_clients),
                'screen_share': self.services.get('screen').get_stats() if 'screen' in self.services else {}
            }
            emit('stats_update', stats)
        
        @self.socketio.on('broadcast_event')
        def handle_broadcast(data):
            """Broadcast custom events to all Electron clients"""
            event_type = data.get('type')
            payload = data.get('payload', {})
            self.socketio.emit(event_type, payload, broadcast=True)
        
        # Run Flask-SocketIO in separate thread
        def run_socketio():
            self.socketio.run(
                self.flask_app,
                host='0.0.0.0',
                port=5555,
                debug=False,
                use_reloader=False,
                log_output=False
            )
        
        self.websocket_thread = threading.Thread(target=run_socketio, daemon=True)
        self.websocket_thread.start()
        time.sleep(0.5)
    
    def _monitor_services(self):
        """Monitor service health (optional enhancement)"""
        # Future: Add health checks, restart failed services, etc.
        pass
    
    def stop(self):
        """Stop all services gracefully"""
        if not self.running:
            return
        
        print("\n🛑 Stopping Sapora Server...")
        self.running = False
        
        # Stop connection manager (triggers all TCP handlers to exit)
        print("   • Stopping Connection Manager...")
        self.manager.stop()
        
        # Stop individual services
        for name, service in self.services.items():
            try:
                print(f"   • Stopping {name.capitalize()} Server...")
                if hasattr(service, 'stop'):
                    service.stop()
                elif hasattr(service, 'running'):
                    service.running = False
            except Exception as e:
                print(f"   ⚠️  Error stopping {name}: {e}")
        
        # Stop WebSocket gateway
        if self.socketio:
            print("   • Stopping WebSocket Gateway...")
            try:
                self.socketio.stop()
            except:
                pass
        
        # Stop LAN discovery
        if hasattr(self, 'discovery') and self.discovery:
            print("   • Stopping LAN Discovery...")
            try:
                self.discovery.stop()
            except:
                pass
        
        print("\n✅ Sapora Server stopped cleanly.\n")
    
    def get_status(self):
        """Get current server status (for monitoring/debugging)"""
        return {
            'running': self.running,
            'services': {
                name: {
                    'running': getattr(service, 'running', False) if hasattr(service, 'running') else True
                }
                for name, service in self.services.items()
            },
            'connections': {
                'control_clients': len(self.manager.control_clients),
                'stream_clients': len(self.manager.stream_clients)
            }
        }


def main():
    """Entry point for server"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Sapora Server - LAN Collaboration Suite')
    parser.add_argument(
        '--no-websocket',
        action='store_true',
        help='Disable WebSocket gateway for Electron'
    )
    args = parser.parse_args()
    
    # Create and start server
    server = SaporaServer(enable_websocket=not args.no_websocket)
    
    try:
        server.start()
    except Exception as e:
        print(f"\n❌ Server error: {e}")
        server.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
