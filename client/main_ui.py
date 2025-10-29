"""
Sapora LAN Collaboration Suite - Main PyQt6 GUI
Modern Zoom-like interface integrating video, audio, chat, file transfer, and screen sharing.
(Modified: thread-safe signals for cross-thread UI updates + Multi-tile video grid)
"""

import sys
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QLineEdit, QTextEdit, QStackedWidget,
    QFileDialog, QMessageBox, QScrollArea, QFrame, QDialog,
    QDialogButtonBox, QSizePolicy, QGridLayout
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize, QObject
from PyQt6.QtGui import QPixmap, QImage, QFont, QIcon
import cv2
import numpy as np
import json
import subprocess
from datetime import datetime
from typing import Optional, Dict
import math

# Import client modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from client.video_client import VideoClient
from client.audio_client import AudioClient
from client.chat_client import ChatClient
from client.file_client import FileTransferClient
from client.screen_share_client import ScreenShareClient
from shared.constants import DEFAULT_SERVER_IP, VIDEO_PORT, CONTROL_PORT
from shared.lan_discovery import start_client_discovery


# ============================================================================
# WORKER THREADS FOR NON-BLOCKING OPERATIONS
# ============================================================================

class VideoStreamThread(QThread):
    """Thread for handling video streaming operations"""
    # Note: frames are emitted by the VideoClient's callback which now emits a signal.
    status_update = pyqtSignal(str)
    
    def __init__(self, video_client):
        super().__init__()
        self.video_client = video_client
        self._running = False
    
    def run(self):
        self._running = True
        try:
            # VideoClient.start_receiving should invoke the frame callback in its own thread
            self.video_client.start_receiving()
        except Exception as e:
            self.status_update.emit(f"VideoThread error: {e}")
    
    def stop(self):
        self._running = False
        try:
            self.video_client.stop_streaming()
        except Exception:
            pass


class AudioStreamThread(QThread):
    """Thread for handling audio streaming operations"""
    status_update = pyqtSignal(str)
    
    def __init__(self, audio_client):
        super().__init__()
        self.audio_client = audio_client
        self._running = False
    
    def run(self):
        self._running = True
        try:
            # AudioClient manages its own send/receive threads; call start_receiving to begin playback thread
            self.audio_client.start_receiving()
        except Exception as e:
            self.status_update.emit(f"AudioThread error: {e}")
    
    def stop(self):
        self._running = False
        try:
            self.audio_client.stop_streaming()
        except Exception:
            pass


class FileTransferThread(QThread):
    """Thread for file upload/download operations"""
    status_update = pyqtSignal(str)
    transfer_complete = pyqtSignal(bool)
    
    def __init__(self, file_client, operation, file_path, save_path=None):
        super().__init__()
        self.file_client = file_client
        self.operation = operation
        self.file_path = file_path
        self.save_path = save_path
    
    def run(self):
        try:
            if self.operation == "upload":
                success = self.file_client.upload_file(self.file_path)
                self.transfer_complete.emit(bool(success))
            elif self.operation == "download":
                success = self.file_client.download_file(self.file_path, self.save_path)
                self.transfer_complete.emit(bool(success))
            else:
                self.transfer_complete.emit(False)
        except Exception as e:
            self.status_update.emit(f"File thread error: {e}")
            self.transfer_complete.emit(False)


# ============================================================================
# LOGIN/JOIN SCREEN
# ============================================================================

class LoginDialog(QDialog):
    """Initial screen for entering server IP, meeting ID and username with LAN discovery"""
    
    def __init__(self, parent=None, defaults: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Join Sapora Meeting")
        self.setFixedSize(460, 420)
        self.discovery = None
        self.defaults = defaults or {}
        self.setup_ui()
        self._apply_defaults()
        self._start_discovery()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(12)
        
        # Title
        title = QLabel("🎥 Sapora Video Conference")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Server IP input
        ip_label = QLabel("Server IP Address:")
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("e.g., 192.168.1.100")
        self.ip_input.setText(DEFAULT_SERVER_IP)
        layout.addWidget(ip_label)
        layout.addWidget(self.ip_input)
        
        # Discovered servers list
        from PyQt6.QtWidgets import QListWidget
        self.discovery_list = QListWidget()
        self.discovery_list.setMaximumHeight(100)
        self.discovery_list.itemClicked.connect(self._apply_discovered_server)
        layout.addWidget(QLabel("Discovered Servers:"))
        layout.addWidget(self.discovery_list)
        
        # Meeting ID input
        meeting_label = QLabel("Meeting ID:")
        self.meeting_input = QLineEdit()
        self.meeting_input.setPlaceholderText("e.g., team123 (default if blank)")
        layout.addWidget(meeting_label)
        layout.addWidget(self.meeting_input)
        
        # Username input
        user_label = QLabel("Your Name:")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter your name")
        layout.addWidget(user_label)
        layout.addWidget(self.username_input)
        
        # Join button
        self.join_button = QPushButton("Join Meeting")
        self.join_button.setDefault(True)
        self.join_button.clicked.connect(self.accept)
        layout.addWidget(self.join_button)
        
        self.setLayout(layout)
    
    def get_credentials(self):
        return (
            self.ip_input.text().strip(),
            self.username_input.text().strip(),
            (self.meeting_input.text().strip() or 'default')
        )
    
    def _apply_defaults(self):
        try:
            if 'server_ip' in self.defaults:
                self.ip_input.setText(self.defaults['server_ip'])
            if 'meeting_id' in self.defaults and hasattr(self, 'meeting_input'):
                self.meeting_input.setText(self.defaults['meeting_id'])
            if 'username' in self.defaults:
                self.username_input.setText(self.defaults['username'])
        except Exception:
            pass
    
    def _start_discovery(self):
        try:
            self.discovery = start_client_discovery(callback=self._on_discovered_server)
        except Exception as e:
            print(f"[Login] Discovery disabled: {e}")
    
    def _on_discovered_server(self, info: dict):
        try:
            from PyQt6.QtWidgets import QListWidgetItem
            item = QListWidgetItem(f"{info['name']} — {info['ip']}:{info['port']}")
            item.setData(Qt.ItemDataRole.UserRole, info)
            self.discovery_list.addItem(item)
        except Exception:
            pass
    
    def _apply_discovered_server(self, item):
        info = item.data(Qt.ItemDataRole.UserRole)
        if info:
            self.ip_input.setText(info.get('ip', DEFAULT_SERVER_IP))


# ============================================================================
# MAIN APPLICATION WINDOW
# ============================================================================

class SchedulerDialog(QDialog):
    """Simple meeting scheduler dialog"""
    def __init__(self, parent=None, storage_path: Optional[Path] = None):
        super().__init__(parent)
        self.setWindowTitle("Meeting Scheduler")
        self.resize(520, 420)
        self.storage_path = storage_path or (Path(__file__).parent / 'meetings.json')
        from PyQt6.QtWidgets import QListWidget
        self.list = QListWidget()
        self.meeting_id = QLineEdit()
        self.title = QLineEdit()
        self.time = QLineEdit()
        self._build_ui()
        self._load()
    
    def _build_ui(self):
        from PyQt6.QtWidgets import QFormLayout, QDialogButtonBox
        layout = QVBoxLayout(self)
        layout.addWidget(self.list)
        form = QFormLayout()
        form.addRow("Meeting ID", self.meeting_id)
        form.addRow("Title", self.title)
        form.addRow("Time (YYYY-MM-DDTHH:MM)", self.time)
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Discard)
        btns.accepted.connect(self._save_entry)
        btns.rejected.connect(self._delete_selected)
        layout.addWidget(btns)
        self.list.itemSelectionChanged.connect(self._on_select)
    
    def _load(self):
        self.list.clear()
        try:
            data = json.loads(self.storage_path.read_text(encoding='utf-8'))
        except Exception:
            data = []
        for entry in data:
            from PyQt6.QtWidgets import QListWidgetItem
            item = QListWidgetItem(f"{entry.get('meeting_id')} — {entry.get('title')} — {entry.get('time')}")
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.list.addItem(item)
    
    def _persist(self, entries):
        try:
            self.storage_path.write_text(json.dumps(entries, indent=2), encoding='utf-8')
        except Exception as e:
            print(f"[Scheduler] Save error: {e}")
    
    def _entries(self):
        items = []
        for i in range(self.list.count()):
            items.append(self.list.item(i).data(Qt.ItemDataRole.UserRole))
        return items
    
    def _save_entry(self):
        entry = {
            'meeting_id': self.meeting_id.text().strip(),
            'title': self.title.text().strip(),
            'time': self.time.text().strip()
        }
        if not entry['meeting_id'] or not entry['time']:
            QMessageBox.warning(self, "Invalid", "Meeting ID and Time are required")
            return
        # replace or add
        entries = [e for e in self._entries() if e['meeting_id'] != entry['meeting_id']]
        entries.append(entry)
        # rebuild list
        self.list.clear()
        for e in entries:
            from PyQt6.QtWidgets import QListWidgetItem
            item = QListWidgetItem(f"{e.get('meeting_id')} — {e.get('title')} — {e.get('time')}")
            item.setData(Qt.ItemDataRole.UserRole, e)
            self.list.addItem(item)
        self._persist(entries)
    
    def _delete_selected(self):
        row = self.list.currentRow()
        if row >= 0:
            self.list.takeItem(row)
            self._persist(self._entries())
    
    def _on_select(self):
        item = self.list.currentItem()
        if not item:
            return
        e = item.data(Qt.ItemDataRole.UserRole)
        self.meeting_id.setText(e.get('meeting_id',''))
        self.title.setText(e.get('title',''))
        self.time.setText(e.get('time',''))


# ============================================================================
# VIDEO TILE WIDGET FOR MULTI-PARTICIPANT GRID
# ============================================================================

class VideoTileWidget(QWidget):
    """Individual video tile showing a participant's video feed and username"""
    
    def __init__(self, username="Unknown", is_local=False, parent=None):
        super().__init__(parent)
        self.username = username
        self.is_local = is_local
        self.last_frame = None
        
        # Setup UI
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # Video display label
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setMinimumSize(160, 120)
        self.video_label.setScaledContents(False)
        self.video_label.setStyleSheet("""
            background-color: #1a1a1a; 
            border: 2px solid #333;
            border-radius: 8px;
        """)
        self.video_label.setText("📹\n\nNo Video")
        layout.addWidget(self.video_label)
        
        # Username label
        self.username_label = QLabel(username)
        self.username_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.username_label.setStyleSheet("""
            background-color: rgba(0, 0, 0, 180);
            color: white;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
        """)
        if is_local:
            self.username_label.setText(f"{username} (You)")
            self.video_label.setStyleSheet("""
                background-color: #1a1a1a; 
                border: 2px solid #4CAF50;
                border-radius: 8px;
            """)
        layout.addWidget(self.username_label)
        
        self.setMinimumSize(180, 160)
    
    def update_frame(self, frame):
        """Update the video frame displayed in this tile"""
        if frame is None:
            return
        
        try:
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_frame.shape
            bytes_per_line = ch * w
            
            # Create QImage
            qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_image)
            
            # Scale to fit label while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                self.video_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            self.video_label.setPixmap(scaled_pixmap)
            self.last_frame = frame
        except Exception as e:
            pass
    
    def update_username(self, username):
        """Update the displayed username"""
        self.username = username
        display_name = f"{username} (You)" if self.is_local else username
        self.username_label.setText(display_name)
    
    def clear_video(self):
        """Clear the video display"""
        self.video_label.clear()
        self.video_label.setText("📹\n\nNo Video")
        self.last_frame = None


class SaporaMainWindow(QMainWindow):
    """Main application window with Zoom-like interface"""
    
    # Thread-safe signals for updating UI from other threads
    chat_message_signal = pyqtSignal(str, str)   # sender, message
    user_list_signal = pyqtSignal(object)        # list of users
    frame_signal = pyqtSignal(object)            # (source_ip, frame) or frame
    screen_frame_signal = pyqtSignal(object)     # screen share frame (BGR)
    local_screen_signal = pyqtSignal(object)     # local presenter preview frame (BGR)
    file_status_signal = pyqtSignal(str)         # file status messages
    status_signal = pyqtSignal(str)              # generic status updates
    
    def __init__(self, prefill: Optional[dict] = None):
        super().__init__()
        self.setWindowTitle("Sapora - Video Conference")
        self.prefill = prefill or {}
        self.setMinimumSize(1200, 700)
        
        # Connection details
        self.server_ip = None
        self.username = None
        self.meeting_id = 'default'
        
        # Client instances
        self.video_client = None
        self.audio_client = None
        self.chat_client = None
        self.file_client = None
        self.screen_client = None
        
        # Worker threads
        self.video_thread = None
        self.audio_thread = None
        self.file_thread = None
        
        # UI state
        self.video_enabled = False
        self.audio_enabled = False
        self.chat_visible = False
        
        # Multi-tile video grid state
        self.video_tiles: Dict[str, VideoTileWidget] = {}  # key: source_id (IP or 'local')
        self.video_grid_layout = None
        self.video_grid_container = None
        self.ip_to_username: Dict[str, str] = {}  # Map IP addresses to usernames
        self.user_list_data = []  # Store user list for IP mapping
        
        # Frame storage for display
        self.current_frame = None
        
        # Connect signals to slots (must be done before clients may emit)
        self.chat_message_signal.connect(self._on_chat_message_signal)
        self.user_list_signal.connect(self._on_user_list_signal)
        self.frame_signal.connect(self._on_frame_signal)
        self.screen_frame_signal.connect(self._on_screen_frame_signal)
        self.local_screen_signal.connect(self._on_screen_frame_signal)
        self.file_status_signal.connect(self._on_file_status_signal)
        self.status_signal.connect(self._on_status_signal)
        
        # Show login dialog first
        self.show_login()
        
    def show_login(self):
        """Display login dialog and initialize on success"""
        dialog = LoginDialog(self, defaults=self.prefill)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.server_ip, self.username, self.meeting_id = dialog.get_credentials()
            
            if not self.server_ip or not self.username:
                QMessageBox.warning(self, "Invalid Input", "Please enter both server IP and username.")
                self.close()
                return
            
            self.initialize_clients()
            self.setup_ui()
            self.connect_to_server()
        else:
            self.close()
    
    def initialize_clients(self):
        """Initialize all client modules and pass thread-safe callbacks"""
        # Video Client: pass a frame callback that emits a signal
        # We don't assume exact signature, so wrap in a safe function:
        def video_frame_callback(*args):
            """
            Accepts either (frame,) or (source_ip, frame). Normalize and emit via frame_signal.
            """
            try:
                if len(args) == 1:
                    self.frame_signal.emit(args[0])
                elif len(args) >= 2:
                    # (source_ip, frame)
                    self.frame_signal.emit((args[0], args[1]))
                else:
                    # unknown form
                    pass
            except Exception:
                pass
        
        self.video_client = VideoClient(
            server_ip=self.server_ip,
            server_port=VIDEO_PORT,
            username=self.username,
            frame_callback=video_frame_callback
        )
        
        # Audio Client: file/audio status callbacks will emit signals
        self.audio_client = AudioClient(
            server_ip=self.server_ip,
            username=self.username
        )
        
        # Chat Client: give callbacks that emit signals (thread-safe)
        self.chat_client = ChatClient(
            server_ip=self.server_ip,
            server_port=CONTROL_PORT,
            username=self.username,
            meeting_id=self.meeting_id
        )
        # chat_client will call these callbacks from its network thread; signals queue to GUI thread
        self.chat_client.set_callbacks(
            user_list_cb=self.user_list_signal.emit,
            message_cb=self.chat_message_signal.emit
        )
        try:
            self.chat_client.set_file_callback(self._on_file_announce)
        except Exception:
            pass
        
        # File Transfer Client: use file_status_signal for status updates
        self.file_client = FileTransferClient(
            server_ip=self.server_ip,
            status_callback=self.file_status_signal.emit
        )
        
        # Screen Share: presenter (local preview) and viewer (remote)
        self.screen_presenter = ScreenShareClient(
            server_ip=self.server_ip,
            mode="presenter",
            local_preview_callback=self.local_screen_signal.emit,
            status_callback=self.status_signal.emit
        )
        self.screen_viewer = ScreenShareClient(
            server_ip=self.server_ip,
            mode="viewer",
            frame_callback=self.screen_frame_signal.emit,
            status_callback=self.status_signal.emit
        )
    
    def setup_ui(self):
        """Build the main interface"""
        # Load stylesheet
        self.load_stylesheet()
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Top bar
        main_layout.addWidget(self.create_top_bar())
        
        # Content area (video + screen share + chat)
        content_layout = QHBoxLayout()
        content_layout.setSpacing(0)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        # Video area
        self.video_widget = self.create_video_area()
        content_layout.addWidget(self.video_widget, stretch=3)
        
        # Screen share area
        self.screen_widget = self.create_screen_area()
        content_layout.addWidget(self.screen_widget, stretch=3)
        
        # Chat panel (initially hidden)
        self.chat_panel = self.create_chat_panel()
        self.chat_panel.setVisible(False)
        content_layout.addWidget(self.chat_panel, stretch=2)
        
        main_layout.addLayout(content_layout)
        
        # Control bar
        main_layout.addWidget(self.create_control_bar())
        
        # Timer for updating video display
        self.display_timer = QTimer()
        self.display_timer.timeout.connect(self.update_video_display)
        self.display_timer.start(33)  # ~30 FPS
        
        # Scheduler timer (checks every 30s)
        self.scheduler_timer = QTimer()
        self.scheduler_timer.timeout.connect(self._check_scheduled_meetings)
        self.scheduler_timer.start(30000)
    
    def load_stylesheet(self):
        """Load style.qss if available"""
        qss_path = Path(__file__).parent / "style.qss"
        if qss_path.exists():
            with open(qss_path, 'r', encoding='utf-8') as f:
                self.setStyleSheet(f.read())
    
    def create_top_bar(self):
        """Creates the top status bar"""
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setFixedHeight(50)
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(15, 5, 15, 5)
        
        # Meeting info
        self.meeting_label = QLabel(f"📹 Sapora Meeting — {self.meeting_id}")
        self.meeting_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(self.meeting_label)
        
        # Scheduler button
        sched_btn = QPushButton("🗓 Scheduler")
        sched_btn.clicked.connect(self._open_scheduler)
        layout.addWidget(sched_btn)
        
        layout.addStretch()
        
        # Username display
        self.user_label = QLabel(f"👤 {self.username}")
        self.user_label.setFont(QFont("Arial", 10))
        layout.addWidget(self.user_label)
        
        # Connection status
        self.status_label = QLabel("● Connecting...")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)
        
        return bar
    
    def create_video_area(self):
        """Creates the central video display area with multi-tile grid"""
        widget = QFrame()
        widget.setObjectName("videoArea")
        
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Container for grid layout with scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("background-color: #1a1a1a; border: none;")
        
        # Grid container widget
        self.video_grid_container = QWidget()
        self.video_grid_layout = QGridLayout(self.video_grid_container)
        self.video_grid_layout.setSpacing(10)
        self.video_grid_layout.setContentsMargins(10, 10, 10, 10)
        
        # Add placeholder message
        placeholder = QLabel("📹\n\nNo Video Feed\n\nClick 'Start Video' to begin")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("color: #888; font-size: 16px;")
        placeholder.setMinimumSize(640, 480)
        self.video_grid_layout.addWidget(placeholder, 0, 0)
        
        scroll.setWidget(self.video_grid_container)
        layout.addWidget(scroll)
        
        return widget
    
    def reorganize_video_grid(self):
        """Reorganize video tiles in optimal grid layout"""
        # Clear existing layout
        while self.video_grid_layout.count():
            item = self.video_grid_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        
        tiles = list(self.video_tiles.values())
        if not tiles:
            # Show placeholder
            placeholder = QLabel("📹\n\nNo Video Feed\n\nClick 'Start Video' to begin")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("color: #888; font-size: 16px;")
            placeholder.setMinimumSize(640, 480)
            self.video_grid_layout.addWidget(placeholder, 0, 0)
            return
        
        # Calculate optimal grid dimensions
        num_tiles = len(tiles)
        cols = math.ceil(math.sqrt(num_tiles))
        rows = math.ceil(num_tiles / cols)
        
        # Add tiles to grid
        for i, tile in enumerate(tiles):
            row = i // cols
            col = i % cols
            self.video_grid_layout.addWidget(tile, row, col)
    
    def add_or_update_video_tile(self, source_id, frame, username=None):
        """Add or update a video tile for a specific source"""
        if source_id not in self.video_tiles:
            # Create new tile
            is_local = (source_id == 'local')
            display_name = username or (self.username if is_local else source_id)
            tile = VideoTileWidget(username=display_name, is_local=is_local)
            self.video_tiles[source_id] = tile
            self.reorganize_video_grid()
        
        # Update frame
        tile = self.video_tiles[source_id]
        tile.update_frame(frame)
        
        # Update username if provided and changed
        if username and tile.username != username:
            tile.update_username(username)
    
    def remove_video_tile(self, source_id):
        """Remove a video tile"""
        if source_id in self.video_tiles:
            tile = self.video_tiles.pop(source_id)
            tile.setParent(None)
            tile.deleteLater()
            self.reorganize_video_grid()
    
    def update_ip_to_username_mapping(self):
        """Update the IP to username mapping from user list"""
        self.ip_to_username.clear()
        for user in self.user_list_data:
            if isinstance(user, dict):
                ip = user.get('ip')
                username = user.get('username')
                if ip and username:
                    self.ip_to_username[ip] = username
    
    def get_username_for_ip(self, ip_address):
        """Get username for a given IP address"""
        return self.ip_to_username.get(ip_address, ip_address)
    
    def create_screen_area(self):
        """Creates the screen share display area"""
        widget = QFrame()
        widget.setObjectName("screenArea")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        
        title = QLabel("🖥 Screen Share")
        title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        layout.addWidget(title)
        
        self.screen_label = QLabel()
        self.screen_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen_label.setMinimumSize(480, 270)
        self.screen_label.setStyleSheet("background-color: #121212; border-radius: 10px;")
        self.screen_label.setText("🖥\n\nNo Screen Share\n\nWaiting for presenter...")
        layout.addWidget(self.screen_label)
        
        return widget
    
    def create_chat_panel(self):
        """Creates the chat side panel with enhanced features"""
        panel = QFrame()
        panel.setObjectName("chatPanel")
        panel.setMinimumWidth(320)
        panel.setMaximumWidth(420)
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # Header with connection status
        header_layout = QHBoxLayout()
        header = QLabel("💬 Chat")
        header.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        header_layout.addWidget(header)
        header_layout.addStretch()
        
        # Online indicator
        self.chat_status_indicator = QLabel("● Online")
        self.chat_status_indicator.setStyleSheet("color: #4CAF50; font-size: 10px; font-weight: bold;")
        header_layout.addWidget(self.chat_status_indicator)
        layout.addLayout(header_layout)
        
        # Participants list (moved to top for better visibility)
        participants_header = QLabel("👥 Participants")
        participants_header.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(participants_header)
        
        self.participants_display = QTextEdit()
        self.participants_display.setReadOnly(True)
        self.participants_display.setMaximumHeight(120)
        self.participants_display.setObjectName("participantsList")
        self.participants_display.setStyleSheet("""
            QTextEdit {
                background-color: #2a2a2a;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 8px;
                color: #fff;
                font-size: 11px;
            }
        """)
        layout.addWidget(self.participants_display)
        
        # Message display
        chat_header = QLabel("Messages")
        chat_header.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(chat_header)
        
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setObjectName("chatDisplay")
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 8px;
                color: #fff;
            }
        """)
        layout.addWidget(self.chat_display)
        
        # Recipient selector (more prominent)
        from PyQt6.QtWidgets import QComboBox
        recipient_layout = QHBoxLayout()
        recipient_label = QLabel("Send to:")
        recipient_label.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        self.chat_target = QComboBox()
        self.chat_target.addItem("📢 Everyone")
        self.chat_target.setMinimumWidth(150)
        self.chat_target.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 5px;
                color: #fff;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #fff;
                margin-right: 5px;
            }
        """)
        recipient_layout.addWidget(recipient_label)
        recipient_layout.addWidget(self.chat_target, 1)
        layout.addLayout(recipient_layout)
        
        # Input area with improved styling
        input_layout = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Type your message here...")
        self.chat_input.returnPressed.connect(self.send_chat_message)
        self.chat_input.setStyleSheet("""
            QLineEdit {
                background-color: #2a2a2a;
                border: 2px solid #555;
                border-radius: 5px;
                padding: 8px;
                color: #fff;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 2px solid #4CAF50;
            }
        """)
        
        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self.send_chat_message)
        send_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        
        input_layout.addWidget(self.chat_input, 1)
        input_layout.addWidget(send_btn)
        layout.addLayout(input_layout)
        
        return panel
    
    def create_control_bar(self):
        """Creates the bottom control bar with action buttons"""
        bar = QFrame()
        bar.setObjectName("controlBar")
        bar.setFixedHeight(80)
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(15)
        
        layout.addStretch()
        
        # Video toggle button
        self.video_btn = QPushButton("🎥 Start Video")
        self.video_btn.setObjectName("videoButton")
        self.video_btn.setCheckable(True)
        self.video_btn.clicked.connect(self.toggle_video)
        layout.addWidget(self.video_btn)
        
        # Audio toggle button
        self.audio_btn = QPushButton("🎙 Start Audio")
        self.audio_btn.setObjectName("audioButton")
        self.audio_btn.setCheckable(True)
        self.audio_btn.clicked.connect(self.toggle_audio)
        layout.addWidget(self.audio_btn)
        
        # Chat toggle button
        self.chat_btn = QPushButton("💬 Chat")
        self.chat_btn.setObjectName("chatButton")
        self.chat_btn.clicked.connect(self.toggle_chat)
        layout.addWidget(self.chat_btn)
        
        # File transfer button
        self.file_btn = QPushButton("📁 Share File")
        self.file_btn.setObjectName("fileButton")
        self.file_btn.clicked.connect(self.open_file_dialog)
        layout.addWidget(self.file_btn)
        
        # Screen share button
        self.screen_btn = QPushButton("🖥 Share Screen")
        self.screen_btn.setObjectName("screenButton")
        self.screen_btn.clicked.connect(self.toggle_screen_share)
        layout.addWidget(self.screen_btn)
        
        layout.addStretch()
        
        # Leave button
        self.leave_btn = QPushButton("🔚 Leave")
        self.leave_btn.setObjectName("leaveButton")
        self.leave_btn.clicked.connect(self.leave_meeting)
        layout.addWidget(self.leave_btn)
        
        return bar
    
    # ========================================================================
    # CONNECTION & INITIALIZATION
    # ========================================================================
    
    def connect_to_server(self):
        """Establish connection to the server"""
        # Connect chat client (TCP control)
        if self.chat_client.connect():
            # Start screen viewer in background to receive remote shares
            import threading
            threading.Thread(target=self.screen_viewer.start, daemon=True).start()
            self.status_label.setText("● Connected")
            self.status_label.setStyleSheet("color: #4CAF50;")
            self.show_notification("Connected to server!")
            
            # Display welcome message in chat
            welcome_msg = f"""
            <div style='margin: 10px 0; padding: 12px; background-color: #1a1a1a; border-radius: 8px; border: 2px solid #4CAF50; text-align: center;'>
                <span style='color: #4CAF50; font-size: 14px; font-weight: bold;'>🎉 Welcome to Sapora! 🎉</span><br/>
                <span style='color: #aaa; font-size: 11px;'>Connected as <b style='color: #4CAF50;'>{self.username}</b></span><br/>
                <span style='color: #aaa; font-size: 11px;'>Room: <b style='color: #2196F3;'>{self.meeting_id}</b></span><br/>
                <span style='color: #888; font-size: 10px; font-style: italic;'>Use the dropdown above to send private messages</span>
            </div>
            """
            self.chat_display.append(welcome_msg)
        else:
            self.status_label.setText("● Connection Failed")
            self.status_label.setStyleSheet("color: #f44336;")
            QMessageBox.critical(self, "Connection Error", 
                                "Failed to connect to server. Please check the IP and try again.")
    
    # ========================================================================
    # VIDEO HANDLING
    # ========================================================================
    
    def toggle_video(self):
        """Start/stop video streaming"""
        if not self.video_enabled:
            # Start video
            success = self.video_client.start_streaming(self.on_video_status)
            if success:
                self.video_enabled = True
                self.video_btn.setText("🎥 Stop Video")
                self.video_btn.setChecked(True)
                
                # Start receiver thread
                self.video_thread = VideoStreamThread(self.video_client)
                self.video_thread.status_update.connect(self.show_notification)
                self.video_thread.start()
        else:
            # Stop video
            try:
                self.video_client.stop_streaming()
            except Exception:
                pass
            if self.video_thread:
                self.video_thread.stop()
                self.video_thread.wait(2000)
            
            # Remove local video tile
            self.remove_video_tile('local')
            
            self.video_enabled = False
            self.video_btn.setText("🎥 Start Video")
            self.video_btn.setChecked(False)
    
    def on_video_status(self, message):
        """Callback for video status updates (passed to video_client.start_streaming)"""
        # The video client will call this from its thread; route via signal to ensure UI-safe actions
        self.status_signal.emit(message)
    
    def _on_frame_signal(self, payload):
        """Slot invoked in GUI thread when a frame arrives via signal"""
        # payload could be either: frame OR (source_ip, frame)
        try:
            source_ip = None
            frame = None
            
            if isinstance(payload, tuple) and len(payload) >= 2:
                source_ip, frame = payload[0], payload[1]
            else:
                frame = payload
            
            if isinstance(frame, np.ndarray):
                # Update the remote video tile
                if source_ip:
                    username = self.get_username_for_ip(source_ip)
                    self.add_or_update_video_tile(source_ip, frame, username)
                else:
                    # Old style frame without source IP, treat as generic remote
                    self.add_or_update_video_tile('remote', frame, 'Remote')
        except Exception as e:
            pass
    
    def update_video_display(self):
        """Update the local video tile with camera feed"""
        # Update local camera feed tile if video is enabled
        if self.video_enabled and self.video_client:
            try:
                if hasattr(self.video_client, "last_frame") and self.video_client.last_frame is not None:
                    frame = self.video_client.last_frame
                    self.add_or_update_video_tile('local', frame, self.username)
            except Exception:
                pass
    
    # ========================================================================
    # AUDIO HANDLING
    # ========================================================================
    
    def toggle_audio(self):
        """Start/stop audio or mute/unmute mic without tearing down playback"""
        try:
            # If audio hasn't started yet, start mic + receiver
            if not self.audio_enabled:
                success = self.audio_client.start_streaming(self.on_audio_status)
                if success:
                    # Start playback receiver thread once
                    self.audio_thread = AudioStreamThread(self.audio_client)
                    self.audio_thread.status_update.connect(self.show_notification)
                    self.audio_thread.start()
                    self.audio_enabled = True
                    self.mic_muted = False
                    self.audio_btn.setText("🎙 Mute")
                    self.audio_btn.setChecked(True)
                return

            # Audio is running; toggle mic mute state instead of stopping everything
            if not hasattr(self, 'mic_muted'):
                self.mic_muted = False
            self.mic_muted = not self.mic_muted
            self.audio_client.set_mic_enabled(not self.mic_muted)
            self.audio_btn.setText("🎙 Unmute" if self.mic_muted else "🎙 Mute")
            self.audio_btn.setChecked(not self.mic_muted)
        except Exception as e:
            self.show_notification(f"Audio toggle error: {e}")
    
    def on_audio_status(self, message):
        """Callback for audio status updates"""
        self.status_signal.emit(message)
    
    # ========================================================================
    # CHAT HANDLING
    # ========================================================================
    
    def toggle_chat(self):
        """Toggle chat panel visibility"""
        self.chat_visible = not self.chat_visible
        self.chat_panel.setVisible(self.chat_visible)
    
    def send_chat_message(self):
        """Send a chat message with enhanced formatting and error handling"""
        text = self.chat_input.text().strip()
        if not text:
            return
        
        # Clear input immediately for better UX
        self.chat_input.clear()
        
        sent = False
        target = 'all'
        target_display = 'Everyone'
        
        try:
            # Get target from dropdown and clean it
            if hasattr(self, 'chat_target') and self.chat_target.currentIndex() >= 0:
                val = self.chat_target.currentText().strip()
                # Remove emoji prefixes
                val_clean = val.replace('📢', '').replace('👤', '').strip()
                
                if val_clean and val_clean.lower() not in ['all', 'everyone']:
                    target = val_clean
                    target_display = val_clean
            
            print(f"[UI] Sending message to '{target}': {text}")
            
            # Send message via chat client
            if self.chat_client and self.chat_client.running:
                sent = self.chat_client.send_message(text, target=target)
                print(f"[UI] Message sent result: {sent}")
            else:
                print(f"[UI] Chat client not ready: running={getattr(self.chat_client, 'running', None)}")
            
            # Local echo with enhanced formatting
            timestamp = datetime.now().strftime("%H:%M")
            
            if sent:
                if target.lower() == 'all':
                    # Public message
                    formatted_msg = f"""
                    <div style='margin: 5px 0; padding: 8px; background-color: #2a2a2a; border-radius: 5px; border-left: 3px solid #4CAF50;'>
                        <span style='color: #888; font-size: 10px;'>{timestamp}</span>
                        <span style='color: #4CAF50; font-weight: bold;'> You </span>
                        <span style='color: #aaa;'>→ Everyone</span><br/>
                        <span style='color: #fff;'>{text}</span>
                    </div>
                    """
                else:
                    # Private message
                    formatted_msg = f"""
                    <div style='margin: 5px 0; padding: 8px; background-color: #2a2a2a; border-radius: 5px; border-left: 3px solid #FF9800;'>
                        <span style='color: #888; font-size: 10px;'>{timestamp}</span>
                        <span style='color: #4CAF50; font-weight: bold;'> You </span>
                        <span style='color: #FF9800;'>→ {target_display} (private)</span><br/>
                        <span style='color: #fff;'>{text}</span>
                    </div>
                    """
                
                self.chat_display.append(formatted_msg)
            else:
                # Show error message
                error_msg = f"""
                <div style='margin: 5px 0; padding: 8px; background-color: #2a2a2a; border-radius: 5px; border-left: 3px solid #f44336;'>
                    <span style='color: #888; font-size: 10px;'>{timestamp}</span>
                    <span style='color: #f44336; font-weight: bold;'> ERROR </span><br/>
                    <span style='color: #fff;'>Failed to send: {text}</span><br/>
                    <span style='color: #888; font-size: 10px; font-style: italic;'>Check your connection</span>
                </div>
                """
                self.chat_display.append(error_msg)
                self.show_notification("❌ Failed to send message - check connection")
            
            # Auto-scroll to bottom
            cursor = self.chat_display.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.chat_display.setTextCursor(cursor)
            
        except Exception as e:
            error_msg = f"""
            <div style='margin: 5px 0; padding: 8px; background-color: #2a2a2a; border-radius: 5px; border-left: 3px solid #f44336;'>
                <span style='color: #f44336; font-weight: bold;'> ERROR </span><br/>
                <span style='color: #fff;'>Exception: {str(e)}</span>
            </div>
            """
            self.chat_display.append(error_msg)
            self.show_notification(f"❌ Chat error: {e}")
            print(f"[UI] Chat exception: {e}")
            import traceback
            traceback.print_exc()
        traceback.print_exc()
    
    # ---- Signal slots (these run in GUI thread) ----
    def _on_chat_message_signal(self, sender, message):
        """Thread-safe slot for appending incoming chat messages with enhanced formatting"""
        try:
            timestamp = datetime.now().strftime("%H:%M")
            
            # Check if it's a private message
            is_private = '(to ' in message or message.startswith('(private)')
            
            # Check if it's a system message
            is_system = sender in ['SYSTEM', 'System', 'SERVER']
            
            if is_system:
                # System message (gold border)
                formatted_msg = f"""
                <div style='margin: 5px 0; padding: 8px; background-color: #2a2a2a; border-radius: 5px; border-left: 3px solid #FFC107;'>
                    <span style='color: #888; font-size: 10px;'>{timestamp}</span>
                    <span style='color: #FFC107; font-weight: bold;'> {sender} </span><br/>
                    <span style='color: #fff; font-style: italic;'>{message}</span>
                </div>
                """
            elif is_private:
                # Private message (orange border)
                formatted_msg = f"""
                <div style='margin: 5px 0; padding: 8px; background-color: #2a2a2a; border-radius: 5px; border-left: 3px solid #FF9800;'>
                    <span style='color: #888; font-size: 10px;'>{timestamp}</span>
                    <span style='color: #2196F3; font-weight: bold;'> {sender} </span>
                    <span style='color: #FF9800;'>(private)</span><br/>
                    <span style='color: #fff;'>{message}</span>
                </div>
                """
            else:
                # Public message (blue border)
                formatted_msg = f"""
                <div style='margin: 5px 0; padding: 8px; background-color: #2a2a2a; border-radius: 5px; border-left: 3px solid #2196F3;'>
                    <span style='color: #888; font-size: 10px;'>{timestamp}</span>
                    <span style='color: #2196F3; font-weight: bold;'> {sender} </span><br/>
                    <span style='color: #fff;'>{message}</span>
                </div>
                """
            
            self.chat_display.append(formatted_msg)
            
            # Auto-scroll to bottom
            cursor = self.chat_display.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.chat_display.setTextCursor(cursor)
            
        except Exception as e:
            # Fallback to simple display
            try:
                self.chat_display.append(f"<b>{sender}:</b> {message}")
            except:
                pass
    
    def _on_user_list_signal(self, users):
        """Thread-safe slot for updating participants list with enhanced formatting"""
        try:
            # Store user list for IP mapping
            self.user_list_data = users
            self.update_ip_to_username_mapping()
            
            # users may be a list of dicts or usernames; normalize to usernames
            usernames = []
            for u in users:
                if isinstance(u, dict):
                    usernames.append(u.get('username') or u.get('name') or str(u))
                else:
                    usernames.append(str(u))
            
            # Update chat target dropdown with enhanced styling
            current = self.chat_target.currentText() if hasattr(self, 'chat_target') else '📢 Everyone'
            if hasattr(self, 'chat_target'):
                self.chat_target.blockSignals(True)
                self.chat_target.clear()
                
                # Add "Everyone" option with emoji
                self.chat_target.addItem("📢 Everyone")
                
                # Add individual participants with emoji (excluding self)
                for name in sorted(usernames):
                    if name and name != (self.username or ""):
                        self.chat_target.addItem(f"👤 {name}")
                
                # Restore previous selection if possible
                # Clean up current selection for matching
                current_clean = current.replace('📢', '').replace('👤', '').strip()
                found_idx = -1
                for i in range(self.chat_target.count()):
                    item_text = self.chat_target.itemText(i)
                    item_clean = item_text.replace('📢', '').replace('👤', '').strip()
                    if item_clean.lower() == current_clean.lower():
                        found_idx = i
                        break
                
                self.chat_target.setCurrentIndex(found_idx if found_idx >= 0 else 0)
                self.chat_target.blockSignals(False)
            
            # Update participants display with online status and count
            participant_count = len(usernames)
            participants_html = f"<div style='color: #4CAF50; font-weight: bold; margin-bottom: 5px;'>● {participant_count} Online</div>"
            
            for name in sorted(usernames):
                is_you = (name == self.username)
                if is_you:
                    participants_html += f"<div style='color: #4CAF50; margin: 3px 0;'>● {name} <b>(You)</b></div>"
                else:
                    participants_html += f"<div style='color: #2196F3; margin: 3px 0;'>● {name}</div>"
            
            self.participants_display.setHtml(participants_html)
            
            # Update online status indicator
            if hasattr(self, 'chat_status_indicator'):
                if participant_count > 1:
                    self.chat_status_indicator.setText(f"● {participant_count} online")
                    self.chat_status_indicator.setStyleSheet("color: #4CAF50; font-size: 10px; font-weight: bold;")
                else:
                    self.chat_status_indicator.setText("● Waiting...")
                    self.chat_status_indicator.setStyleSheet("color: #FFC107; font-size: 10px; font-weight: bold;")
            
            # Update usernames in existing video tiles
            for source_id, tile in self.video_tiles.items():
                if source_id != 'local' and source_id in self.ip_to_username:
                    tile.update_username(self.ip_to_username[source_id])
                    
        except Exception as e:
            print(f"Error updating user list: {e}")
    
    # Legacy - kept for API compatibility (used by earlier code)
    def on_chat_message(self, sender, message):
        self._on_chat_message_signal(sender, message)
    
    def on_user_list_update(self, users):
        self._on_user_list_signal(users)
    
    # ========================================================================
    # FILE TRANSFER HANDLING
    # ========================================================================
    
    def open_file_dialog(self):
        """Open file dialog for sharing"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select File to Share",
            "",
            "All Files (*.*)"
        )
        
        if file_path:
            self.upload_file(file_path)
    
    def upload_file(self, file_path):
        """Upload a file to the server (threaded)"""
        # Ensure any previous thread cleaned up
        if self.file_thread and self.file_thread.isRunning():
            self.show_notification("File transfer already in progress.")
            return
        
        # Track current filename for user feedback
        try:
            self._current_upload_name = Path(file_path).name
        except Exception:
            self._current_upload_name = None
        
        self.file_thread = FileTransferThread(self.file_client, "upload", file_path)
        self.file_thread.status_update.connect(self.file_status_signal.emit)
        self.file_thread.transfer_complete.connect(self.on_file_transfer_complete)
        self.file_thread.start()
        self.show_notification(f"📤 Uploading {self._current_upload_name or file_path}...")
    
    def on_file_transfer_complete(self, success):
        """Callback when file transfer completes"""
        fname = getattr(self, '_current_upload_name', None)
        if success:
            self.show_notification("✅ File transfer successful!")
            try:
                self.chat_display.append(f"<i style='color:#4CAF50;'>✅ Uploaded {fname or ''} successfully</i>")
            except Exception:
                pass
            # Announce file to target (or All)
            try:
                target = 'all'
                if hasattr(self, 'chat_target') and self.chat_target.currentIndex() >= 0:
                    val = self.chat_target.currentText().strip()
                    if val and val.lower() != 'all':
                        target = val
                # Send announce (routed via chat); receivers auto-download
                if hasattr(self, 'chat_client') and self.chat_client:
                    self.chat_client.send_file_announce(fname or '', target=target)
            except Exception:
                pass
        else:
            self.show_notification("❌ File transfer failed")
            try:
                self.chat_display.append(f"<i style='color:#f44336;'>❌ Upload failed for {fname or ''}</i>")
            except Exception:
                pass
        # clear current filename
        self._current_upload_name = None
    
    def _on_file_status_signal(self, message):
        """Update UI from file client status callbacks"""
        self.show_notification(message)
    
    def _on_file_announce(self, obj):
        try:
            fname = obj.get('filename')
            sender = obj.get('sender', 'someone')
            size = obj.get('size')
            self.chat_display.append(f"<i>📥 {sender} shared {fname} ({size or ''} bytes)</i>")
            # Auto-download to downloads folder
            downloads = (Path(__file__).parent / 'downloads')
            downloads.mkdir(parents=True, exist_ok=True)
            self.file_thread = FileTransferThread(self.file_client, 'download', fname, save_path=str(downloads))
            self.file_thread.status_update.connect(self.file_status_signal.emit)
            def _after(ok):
                try:
                    self.chat_display.append(
                        f"<i style='color:{'#4CAF50' if ok else '#f44336'};'>{'✅ Downloaded' if ok else '❌ Download failed'} {fname}</i>")
                except Exception:
                    pass
                # Send private ack back to sender when known
                if ok and sender and hasattr(self, 'chat_client') and self.chat_client:
                    try:
                        self.chat_client.send_message(f"Downloaded {fname}", target=sender)
                    except Exception:
                        pass
            self.file_thread.transfer_complete.connect(_after)
            self.file_thread.start()
        except Exception as e:
            self.show_notification(f"File announce error: {e}")
    
    # ========================================================================
    # SCREEN SHARE HANDLING
    # ========================================================================
    
    def _on_screen_frame_signal(self, frame_bgr):
        try:
            if isinstance(frame_bgr, tuple) and len(frame_bgr) >= 2:
                frame_bgr = frame_bgr[1]
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_per_line = ch * w
            qt_image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_image)
            scaled = pixmap.scaled(
                self.screen_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.screen_label.setPixmap(scaled)
        except Exception:
            pass
    
    def toggle_screen_share(self):
        """Start/stop screen sharing"""
        # Toggle presenter start/stop
        if not getattr(self, '_presenting', False):
            reply = QMessageBox.question(
                self,
                "Screen Share",
                "Start sharing your screen?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            import threading
            threading.Thread(target=self.screen_presenter.start, daemon=True).start()
            self._presenting = True
            self.show_notification("🖥 Screen sharing started")
            self.screen_btn.setText("🛑 Stop Share")
        else:
            try:
                self.screen_presenter.stop()
            except Exception:
                pass
            self._presenting = False
            self.show_notification("🛑 Screen sharing stopped")
            self.screen_btn.setText("🖥 Share Screen")
    
    # ========================================================================
    # UI HELPERS
    # ========================================================================
    
    def show_notification(self, message):
        """Display a notification message"""
        # Route through the status_signal to centralize notifications
        print(f"[NOTIFICATION] {message}")
        try:
            current_text = self.status_label.text()
            self.status_label.setText(str(message))
            QTimer.singleShot(3000, lambda: self.status_label.setText(current_text))
        except Exception:
            pass
    
    def _on_status_signal(self, text):
        """Slot for handling status_signal emissions (GUI thread)"""
        self.show_notification(text)
    
    def _open_scheduler(self):
        try:
            dlg = SchedulerDialog(self, storage_path=Path(__file__).parent / 'meetings.json')
            dlg.exec()
        except Exception as e:
            print(f"Scheduler open error: {e}")
    
    def _check_scheduled_meetings(self):
        """Checks meetings.json and auto-launches due meetings."""
        try:
            storage = Path(__file__).parent / 'meetings.json'
            if not storage.exists():
                return
            data = json.loads(storage.read_text(encoding='utf-8'))
            now = datetime.now()
            for e in data:
                try:
                    t = datetime.fromisoformat(e.get('time'))
                    if 0 <= (t - now).total_seconds() <= 30:
                        # Launch a new client for this meeting
                        subprocess.Popen([sys.executable, str(Path(__file__).parent / 'main_ui.py'), '--meeting', e.get('meeting_id')])
                except Exception:
                    continue
        except Exception as e:
            print(f"Scheduler check error: {e}")
    
    def leave_meeting(self):
        """Leave the meeting and clean up"""
        reply = QMessageBox.question(
            self,
            "Leave Meeting",
            "Are you sure you want to leave?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.cleanup()
            self.close()
    
    def cleanup(self):
        """Clean up all resources before closing"""
        # Stop video
        if self.video_enabled:
            try:
                self.video_client.stop_streaming()
            except Exception:
                pass
            if self.video_thread:
                self.video_thread.stop()
                self.video_thread.wait(2000)
        
        # Stop screen share
        try:
            if getattr(self, '_presenting', False):
                self.screen_presenter.stop()
        except Exception:
            pass
        try:
            if hasattr(self, 'screen_viewer') and self.screen_viewer:
                self.screen_viewer.stop()
        except Exception:
            pass

        # Stop audio (full shutdown)
        if self.audio_enabled or getattr(self, 'mic_muted', False):
            try:
                self.audio_client.stop_streaming()
            except Exception:
                pass
            if self.audio_thread:
                self.audio_thread.stop()
                self.audio_thread.wait(2000)
        
        # Disconnect chat
        if self.chat_client:
            try:
                self.chat_client.disconnect()
            except Exception:
                pass
    
    def closeEvent(self, event):
        """Handle window close event"""
        self.cleanup()
        event.accept()


# ============================================================================
# APPLICATION ENTRY POINT
# ============================================================================

def main():
    # Parse optional --meeting MEETING_ID
    meeting_cli = None
    try:
        if '--meeting' in sys.argv:
            idx = sys.argv.index('--meeting')
            if idx + 1 < len(sys.argv):
                meeting_cli = sys.argv[idx + 1]
    except Exception:
        meeting_cli = None

    app = QApplication(sys.argv)
    app.setApplicationName("Sapora Video Conference")
    
    prefill = {}
    if meeting_cli:
        prefill['meeting_id'] = meeting_cli
    window = SaporaMainWindow(prefill=prefill)
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
