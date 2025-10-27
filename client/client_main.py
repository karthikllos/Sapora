"""
Sapora LAN Collaboration Suite - Unified Client Backend
Starts all client modules and exposes WebSocket/IPC API for Electron to control.
Handles: audio, video, chat, file transfer, and screen share.
"""

import sys
import os
import signal
import threading
import time
import json

# Add parent path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from client.audio_client import AudioClient
from client.video_client import VideoClient
from client.chat_client import ChatClient
from client.file_client import FileTransferClient
from client.screen_share_client import ScreenShareClient

# Flask-SocketIO for WebSocket API to Electron
try:
    from flask import Flask
    from flask_socketio import SocketIO, emit
    from flask_cors import CORS
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    print("⚠️  Warning: flask-socketio not installed. WebSocket API disabled.")


class SaporaClient:
    """Unified client backend managing all client modules"""
    
    def __init__(self, server_ip, username, websocket_port=5556):
        self.server_ip = server_ip
        self.username = username
        self.websocket_port = websocket_port
        self.running = False
        
        # Client modules
        self.audio_client = None
        self.video_client = None
        self.chat_client = None
        self.file_client = None
        self.screen_share_client = None
        
        # State tracking
        self.state = {
            'audio_streaming': False,
            'audio_receiving': False,
            'video_streaming': False,
            'video_receiving': False,
            'chat_connected': False,
            'screen_sharing': False,
            'screen_viewing': False,
            'muted': False,
            'video_off': False
        }
        
        # WebSocket server for Electron
        self.flask_app = None
        self.socketio = None
        self.websocket_thread = None
        
        # Video frames buffer for Electron
        self.video_frames = {}  # {source_ip: latest_frame}
        self.video_frames_lock = threading.Lock()
        
        # Chat messages buffer
        self.chat_messages = []
        self.chat_lock = threading.Lock()
        
        # Signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        print("\n🛑 Shutdown signal received...")
        self.stop()
        sys.exit(0)
    
    def start(self):
        """Initialize all client modules and start WebSocket API"""
        print("="*60)
        print(f"🚀 Starting Sapora Client: {self.username}")
        print(f"📡 Server: {self.server_ip}")
        print("="*60)
        
        self.running = True
        
        # Initialize client modules (don't start streaming yet)
        print("\n📦 Initializing client modules...")
        
        # 1. Audio Client
        self.audio_client = AudioClient(self.server_ip, self.username)
        print("   ✓ Audio client ready")
        
        # 2. Video Client
        self.video_client = VideoClient(
            self.server_ip,
            6000,  # VIDEO_PORT
            self.username,
            self._video_frame_callback
        )
        print("   ✓ Video client ready")
        
        # 3. Chat Client
        self.chat_client = ChatClient(self.server_ip, 5000, self.username)
        self.chat_client.set_callbacks(
            self._user_list_callback,
            self._chat_message_callback
        )
        if self.chat_client.connect():
            self.state['chat_connected'] = True
            print("   ✓ Chat client connected")
        
        # 4. File Transfer Client
        self.file_client = FileTransferClient(
            self.server_ip,
            status_callback=self._file_status_callback
        )
        print("   ✓ File transfer client ready")
        
        # 5. Screen Share Client
        self.screen_share_client = ScreenShareClient(self.server_ip, mode="viewer")
        print("   ✓ Screen share client ready")
        
        # Start WebSocket API server
        if WEBSOCKET_AVAILABLE:
            print("\n🌐 Starting WebSocket API server...")
            self._start_websocket_api()
        
        print("\n" + "="*60)
        print("✅ Sapora Client ready!")
        print("="*60)
        print(f"   • WebSocket API: Port {self.websocket_port}")
        print("\n💡 Waiting for Electron frontend to connect...\n")
        
        # Keep main thread alive
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def _start_websocket_api(self):
        """Start Flask-SocketIO WebSocket API for Electron"""
        self.flask_app = Flask(__name__)
        self.flask_app.config['SECRET_KEY'] = 'sapora-client-key'
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
            print(f"🔌 Electron frontend connected")
            emit('client_ready', {
                'username': self.username,
                'server_ip': self.server_ip,
                'state': self.state
            })
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            print(f"🔌 Electron frontend disconnected")
        
        @self.socketio.on('start_audio')
        def handle_start_audio():
            """Start audio streaming"""
            if not self.state['audio_streaming']:
                success = self.audio_client.start_streaming(self._status_callback)
                if success:
                    self.state['audio_streaming'] = True
                    self.audio_client.start_receiving()
                    self.state['audio_receiving'] = True
                emit('audio_status', {'streaming': self.state['audio_streaming']})
        
        @self.socketio.on('stop_audio')
        def handle_stop_audio():
            """Stop audio streaming"""
            if self.state['audio_streaming']:
                self.audio_client.stop_streaming()
                self.state['audio_streaming'] = False
                self.state['audio_receiving'] = False
                emit('audio_status', {'streaming': False})
        
        @self.socketio.on('toggle_mute')
        def handle_toggle_mute():
            """Toggle microphone mute"""
            self.state['muted'] = not self.state['muted']
            # Note: Would need to add mute functionality to audio_client
            emit('mute_status', {'muted': self.state['muted']})
        
        @self.socketio.on('start_video')
        def handle_start_video():
            """Start video streaming"""
            if not self.state['video_streaming']:
                success = self.video_client.start_streaming(self._status_callback)
                if success:
                    self.state['video_streaming'] = True
                    self.video_client.start_receiving()
                    self.state['video_receiving'] = True
                emit('video_status', {'streaming': self.state['video_streaming']})
        
        @self.socketio.on('stop_video')
        def handle_stop_video():
            """Stop video streaming"""
            if self.state['video_streaming']:
                self.video_client.stop_streaming()
                self.state['video_streaming'] = False
                self.state['video_receiving'] = False
                emit('video_status', {'streaming': False})
        
        @self.socketio.on('send_chat')
        def handle_send_chat(data):
            """Send chat message"""
            message = data.get('message', '')
            if self.chat_client and message:
                self.chat_client.send_message(message)
        
        @self.socketio.on('upload_file')
        def handle_upload_file(data):
            """Upload file to server"""
            file_path = data.get('file_path', '')
            if file_path and self.file_client:
                threading.Thread(
                    target=self.file_client.upload_file,
                    args=(file_path,),
                    daemon=True
                ).start()
        
        @self.socketio.on('download_file')
        def handle_download_file(data):
            """Download file from server"""
            filename = data.get('filename', '')
            save_path = data.get('save_path', './downloads')
            if filename and self.file_client:
                threading.Thread(
                    target=self.file_client.download_file,
                    args=(filename, save_path),
                    daemon=True
                ).start()
        
        @self.socketio.on('start_screen_share')
        def handle_start_screen_share():
            """Start screen sharing as presenter"""
            if not self.state['screen_sharing']:
                self.screen_share_client.mode = "presenter"
                threading.Thread(target=self.screen_share_client.start, daemon=True).start()
                self.state['screen_sharing'] = True
                emit('screen_share_status', {'sharing': True})
        
        @self.socketio.on('stop_screen_share')
        def handle_stop_screen_share():
            """Stop screen sharing"""
            if self.state['screen_sharing']:
                self.screen_share_client.running = False
                self.state['screen_sharing'] = False
                emit('screen_share_status', {'sharing': False})
        
        @self.socketio.on('view_screen_share')
        def handle_view_screen_share():
            """Start viewing screen share"""
            if not self.state['screen_viewing']:
                self.screen_share_client.mode = "viewer"
                threading.Thread(target=self.screen_share_client.start, daemon=True).start()
                self.state['screen_viewing'] = True
                emit('screen_view_status', {'viewing': True})
        
        @self.socketio.on('get_state')
        def handle_get_state():
            """Get current client state"""
            emit('state_update', self.state)
        
        # Run Flask-SocketIO in separate thread
        def run_socketio():
            self.socketio.run(
                self.flask_app,
                host='127.0.0.1',
                port=self.websocket_port,
                debug=False,
                use_reloader=False,
                log_output=False
            )
        
        self.websocket_thread = threading.Thread(target=run_socketio, daemon=True)
        self.websocket_thread.start()
        time.sleep(0.5)
    
    # Callback functions
    def _status_callback(self, message):
        """Status callback for audio/video"""
        print(f"📊 {message}")
        if self.socketio:
            self.socketio.emit('status_message', {'message': message})
    
    def _file_status_callback(self, message):
        """File transfer status callback"""
        print(f"📁 {message}")
        if self.socketio:
            self.socketio.emit('file_status', {'message': message})
    
    def _video_frame_callback(self, source_ip, frame):
        """Callback when video frame received"""
        with self.video_frames_lock:
            self.video_frames[source_ip] = frame
        
        # Notify Electron (frame data would be sent separately via binary protocol)
        if self.socketio:
            self.socketio.emit('video_frame_received', {
                'source_ip': source_ip,
                'timestamp': time.time()
            })
    
    def _chat_message_callback(self, sender, message):
        """Callback when chat message received"""
        with self.chat_lock:
            msg_obj = {
                'sender': sender,
                'message': message,
                'timestamp': time.time()
            }
            self.chat_messages.append(msg_obj)
        
        print(f"💬 {sender}: {message}")
        if self.socketio:
            self.socketio.emit('chat_message', msg_obj)
    
    def _user_list_callback(self, user_list):
        """Callback when user list updated"""
        print(f"👥 User list updated: {len(user_list)} users")
        if self.socketio:
            self.socketio.emit('user_list_update', {'users': user_list})
    
    def stop(self):
        """Stop all client modules"""
        if not self.running:
            return
        
        print("\n🛑 Stopping Sapora Client...")
        self.running = False
        
        # Stop all modules
        if self.audio_client:
            print("   • Stopping audio client...")
            self.audio_client.stop_streaming()
        
        if self.video_client:
            print("   • Stopping video client...")
            self.video_client.stop_streaming()
        
        if self.chat_client:
            print("   • Disconnecting chat client...")
            self.chat_client.disconnect()
        
        if self.screen_share_client and self.screen_share_client.running:
            print("   • Stopping screen share client...")
            self.screen_share_client.running = False
        
        # Stop WebSocket server
        if self.socketio:
            print("   • Stopping WebSocket API...")
            try:
                self.socketio.stop()
            except:
                pass
        
        print("\n✅ Sapora Client stopped cleanly.\n")
    
    def get_state(self):
        """Get current client state"""
        return self.state.copy()


def main():
    """Entry point for client"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Sapora Client - LAN Collaboration Suite')
    parser.add_argument(
        'server_ip',
        help='Server IP address'
    )
    parser.add_argument(
        '--username',
        default=f'User-{os.getpid()}',
        help='Your username (default: User-<PID>)'
    )
    parser.add_argument(
        '--websocket-port',
        type=int,
        default=5556,
        help='WebSocket API port for Electron (default: 5556)'
    )
    args = parser.parse_args()
    
    # Create and start client
    client = SaporaClient(args.server_ip, args.username, args.websocket_port)
    
    try:
        client.start()
    except Exception as e:
        print(f"\n❌ Client error: {e}")
        client.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
