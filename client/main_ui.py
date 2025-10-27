"""
Sapora LAN Collaboration Suite - Main PyQt5 GUI Window (COMPLETE FIXED VERSION)
Integrates all client modules and manages the user interface.
"""
import sys
import os
import threading
import time
from datetime import datetime
from pathlib import Path
import math

# Qt imports
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QInputDialog,
    QFileDialog, QMessageBox, QScrollArea, QFrame, QSplitter,
    QGridLayout, QSizePolicy, QAction, QMenu
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer, QCoreApplication
from PyQt5.QtGui import QFont, QPalette, QColor, QPixmap, QImage

# Add parent directory to path to import shared modules
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Import required libraries BEFORE client imports
try:
    import cv2
except ImportError as e:
    print(f"ERROR: OpenCV not installed. Run: pip install opencv-python")
    sys.exit(1)

try:
    import numpy as np
except ImportError as e:
    print(f"ERROR: NumPy not installed. Run: pip install numpy")
    sys.exit(1)

try:
    import pyaudio
except ImportError as e:
    print(f"ERROR: PyAudio not installed. Run: pip install pyaudio")
    sys.exit(1)

# Import constants FIRST
from shared.constants import (
    DEFAULT_SERVER_IP, CONTROL_PORT, VIDEO_PORT, AUDIO_PORT, 
    FILE_TRANSFER_PORT, SCREEN_SHARE_PORT, VIDEO_WIDTH, VIDEO_HEIGHT
)

# THEN import client modules
from client.chat_client import ChatClient
from client.video_client import VideoClient
from client.audio_client import AudioClient
from client.screen_share_client import ScreenShareServer
from client.file_client import FileTransferClient
from client.utils import read_tcp_message 


# --- Custom Widgets ---

class ChatMessageWidget(QWidget):
    """Individual chat message bubble widget."""
    def __init__(self, username, message, timestamp, is_self=False, is_file=False):
        super().__init__()
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 5, 10, 5)
        self.setLayout(layout)
        
        # Header (Username and Time)
        header = QHBoxLayout()
        username_label = QLabel(username)
        username_label.setObjectName("ChatMessageUsername")
        header.addWidget(username_label)
        
        time_label = QLabel(timestamp)
        time_label.setObjectName("ChatMessageTime")
        header.addWidget(time_label)
        header.addStretch()
        layout.addLayout(header)
        
        # Message Content
        if is_file:
            msg_text = f"📎 {message}"
            style = "color: #1f1f1f; background-color: #e0e0e0; padding: 8px; border-radius: 5px; font-weight: bold;"
        else:
            msg_text = message
            style = "color: #1f1f1f; font-size: 13px;"
            
        msg_label = QLabel(msg_text)
        msg_label.setStyleSheet(style)
        msg_label.setWordWrap(True)
        layout.addWidget(msg_label)

class VideoTile(QFrame):
    """Individual video tile for participant display."""
    def __init__(self, username, is_self=False):
        super().__init__()
        self.username = username
        self.is_self = is_self
        self.setObjectName("VideoTile")
        self.setMinimumSize(240, 180)
        self.setMaximumSize(640, 480)
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        self.setLayout(layout)
        
        # Video placeholder
        self.video_label = QLabel(username[0].upper())
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet(f"""
            color: #ffffff;
            font-size: 40px;
            background-color: #3c4043;
            border-radius: 8px;
            min-height: {VIDEO_HEIGHT - 10}px;
        """)
        self.video_label.setScaledContents(False)
        layout.addWidget(self.video_label, 1)
        
        # Name overlay at bottom
        name_label = QLabel(f"{username} (You)" if is_self else username)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("""
            background-color: rgba(0, 0, 0, 0.7);
            color: #ffffff;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
        """)
        layout.addWidget(name_label)
        
class GUISignals(QObject):
    """Thread-safe signals for GUI updates."""
    status_message = pyqtSignal(str)
    user_list_updated = pyqtSignal(list)
    chat_message_received = pyqtSignal(str, str, bool) # sender, message, is_file
    video_frame_ready = pyqtSignal(str, object) # username/ip, frame(numpy array)
    audio_active = pyqtSignal(str, bool) # username/ip, active
    
# --- Main Window ---

class SaporaGUI(QMainWindow):
    """Main application window for the Sapora collaboration client."""
    
    def __init__(self, server_ip):
        super().__init__()
        
        print(f"[SaporaGUI] Initializing with server: {server_ip}")
        
        QCoreApplication.setApplicationName("Sapora Client")
        self.setWindowTitle("Sapora LAN Collaboration Suite")
        self.setGeometry(50, 50, 1200, 800)
        
        self.server_ip = server_ip
        self.username = "User"
        
        # Client instances
        self.video_client = None
        self.audio_client = None
        self.chat_client = None
        self.screen_client = None 
        self.file_client = None
        
        # State
        self.video_active = False
        self.audio_active = False
        self.screen_active = False
        self.chat_visible = True
        
        # Data
        self.user_tiles = {} # {username: VideoTile}
        self.video_frames = {} # {username/ip: frame}
        
        # Signals
        self.gui_signals = GUISignals()
        self.gui_signals.status_message.connect(self.add_system_message)
        self.gui_signals.user_list_updated.connect(self.update_user_tiles)
        self.gui_signals.chat_message_received.connect(self.display_received_message)
        self.gui_signals.video_frame_ready.connect(self.update_video_frame)
        self.gui_signals.audio_active.connect(self.update_audio_status)
        
        print("[SaporaGUI] Setting up connection info...")
        self.setup_connection_info()
        
        print("[SaporaGUI] Initializing UI...")
        self.init_ui()
        
        # Timers
        self.video_update_timer = QTimer()
        self.video_update_timer.timeout.connect(self.process_video_updates)
        self.video_update_timer.start(1000 // 30) # ~30 FPS UI update rate
        
        self.meeting_start_time = datetime.now()
        self.ui_update_timer = QTimer()
        self.ui_update_timer.timeout.connect(self.update_ui_stats)
        self.ui_update_timer.start(1000)
        
        print("[SaporaGUI] Scheduling connection...")
        # Delayed connection
        QTimer.singleShot(500, self.connect_to_control)
        
        print("[SaporaGUI] Initialization complete")

    def setup_connection_info(self):
        """Prompts user for username and sets client IPs."""
        username, ok = QInputDialog.getText(
            self, "Join Sapora", "Enter your display name:",
            QLineEdit.Normal, os.environ.get('USERNAME', 'Guest')
        )
        if ok and username.strip():
            self.username = username.strip()
        else:
            self.username = "Guest-" + str(os.getpid())
        
        print(f"[SaporaGUI] Username set to: {self.username}")

    def init_ui(self):
        """Initializes the main user interface layout."""
        # Load Stylesheet
        qss_path = os.path.join(os.path.dirname(__file__), 'style.qss')
        if os.path.exists(qss_path):
             with open(qss_path, "r") as f:
                self.setStyleSheet(f.read())
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        central_widget.setLayout(main_layout)
        
        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter)
        
        # --- Left Side: Video & Controls ---
        video_container = QWidget()
        video_layout = QVBoxLayout()
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_container.setLayout(video_layout)
        
        # Video Grid Area
        self.tiles_container = QWidget()
        self.tiles_grid = QGridLayout()
        self.tiles_grid.setSpacing(10)
        self.tiles_grid.setContentsMargins(10, 10, 10, 10)
        self.tiles_container.setLayout(self.tiles_grid)
        
        # Wrap tiles container in a scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.tiles_container)
        video_layout.addWidget(scroll_area, 1)

        # Create self tile initially
        self.tile_self = VideoTile(self.username, is_self=True)
        self.user_tiles[self.username] = self.tile_self
        self._reorganize_grid_layout()
        
        # Control Bar
        control_bar = self._create_control_bar()
        video_layout.addWidget(control_bar)
        
        # --- Right Side: Chat Panel ---
        self.chat_panel = self._create_chat_panel()
        
        self.splitter.addWidget(video_container)
        self.splitter.addWidget(self.chat_panel)
        self.splitter.setSizes([900, 300]) # Initial split sizes

    def _create_control_bar(self):
        """Creates the bottom control bar."""
        control_bar = QWidget()
        control_bar.setStyleSheet("background-color: #e0e0e0; min-height: 60px;")
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(20, 10, 20, 10)
        control_bar.setLayout(control_layout)
        
        # Left Info Section
        self.meeting_time = QLabel("00:00")
        self.meeting_time.setStyleSheet("font-weight: bold; color: #1a73e8;")
        self.participant_count = QLabel("👥 1")
        self.participant_count.setStyleSheet("color: #606060;")
        
        info_layout = QHBoxLayout()
        info_layout.addWidget(self.meeting_time)
        info_layout.addWidget(QLabel("|"))
        info_layout.addWidget(self.participant_count)
        control_layout.addLayout(info_layout)
        control_layout.addStretch()

        # Center Controls
        center_controls = QHBoxLayout()
        center_controls.setSpacing(10)
        
        self.btn_mic = self._create_control_button("🎤", "Toggle Microphone", self.toggle_audio)
        self.btn_camera = self._create_control_button("📹", "Toggle Camera", self.toggle_video)
        self.btn_share = self._create_control_button("🖥️", "Share Screen", self.toggle_screen_share, object_name="btn_share")
        
        center_controls.addWidget(self.btn_mic)
        center_controls.addWidget(self.btn_camera)
        center_controls.addWidget(self.btn_share)
        
        control_layout.addLayout(center_controls)
        control_layout.addStretch()
        
        # Right Utility Controls
        utility_controls = QHBoxLayout()
        utility_controls.setSpacing(10)
        
        self.btn_chat_toggle = self._create_control_button("💬", "Toggle Chat", self.toggle_chat_panel)
        self.btn_chat_toggle.setCheckable(True)
        self.btn_chat_toggle.setChecked(True)
        
        self.btn_leave = QPushButton("Leave")
        self.btn_leave.setObjectName("btn_leave")
        self.btn_leave.clicked.connect(self.leave_meeting)
        
        utility_controls.addWidget(self.btn_chat_toggle)
        utility_controls.addWidget(self.btn_leave)

        control_layout.addLayout(utility_controls)
        return control_bar

    def _create_control_button(self, text, tooltip, callback, object_name=None):
        """Helper to create control buttons."""
        btn = QPushButton(text)
        if object_name:
            btn.setObjectName(object_name)
        btn.setCheckable(True)
        btn.setToolTip(tooltip)
        btn.clicked.connect(callback)
        return btn
    
    def _create_chat_panel(self):
        """Creates the chat panel widget."""
        chat_panel = QWidget()
        chat_panel.setObjectName("ChatPanel")
        chat_panel.setMinimumWidth(300)
        chat_layout = QVBoxLayout()
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_panel.setLayout(chat_layout)
        
        # Header
        chat_header = QWidget()
        chat_header.setStyleSheet("background-color: #e8e8e8; border-bottom: 1px solid #d0d0d0;")
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(15, 10, 15, 10)
        chat_header.setLayout(header_layout)
        
        chat_title = QLabel("💬 Chat & Files")
        chat_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        header_layout.addWidget(chat_title)
        header_layout.addStretch()
        chat_layout.addWidget(chat_header)

        # Messages Area
        self.chat_messages_scroll = QScrollArea()
        self.chat_messages_scroll.setWidgetResizable(True)
        self.chat_messages_scroll.setStyleSheet("border: none; background-color: #ffffff;")
        
        messages_container = QWidget()
        self.messages_layout = QVBoxLayout()
        self.messages_layout.setAlignment(Qt.AlignTop)
        messages_container.setLayout(self.messages_layout)
        self.chat_messages_scroll.setWidget(messages_container)
        chat_layout.addWidget(self.chat_messages_scroll, 1)

        # Input Area
        input_container = QWidget()
        input_container.setStyleSheet("background-color: #e8e8e8; border-top: 1px solid #d0d0d0;")
        input_layout = QVBoxLayout()
        input_layout.setContentsMargins(10, 10, 10, 10)
        input_container.setLayout(input_layout)
        
        # Chat Input
        input_row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Send a message...")
        self.chat_input.returnPressed.connect(self.send_chat_message)
        input_row.addWidget(self.chat_input)
        
        btn_send = QPushButton("➤")
        btn_send.clicked.connect(self.send_chat_message)
        btn_send.setFixedSize(36, 36)
        btn_send.setStyleSheet("background-color: #1a73e8; color: white; border-radius: 18px; padding: 0;")
        input_row.addWidget(btn_send)
        input_layout.addLayout(input_row)

        # File Button
        btn_attach = QPushButton("📎 Send File")
        btn_attach.clicked.connect(self.open_file_transfer_menu)
        btn_attach.setStyleSheet("background-color: #1a73e8; color: white; font-weight: bold;")
        input_layout.addWidget(btn_attach)
        
        chat_layout.addWidget(input_container)
        return chat_panel

    # --- Connection & Setup ---

    def connect_to_control(self):
        """Initializes all TCP and UDP clients."""
        
        print(f"[DEBUG] connect_to_control() STARTED")
        print(f"[SaporaGUI] Attempting to connect to {self.server_ip}:{CONTROL_PORT}...")
        
        # 1. Chat/Control Client (TCP) - CRITICAL
        try:
            print(f"[DEBUG] Creating ChatClient...")
            self.chat_client = ChatClient(self.server_ip, CONTROL_PORT, self.username)
            print(f"[DEBUG] ChatClient object created successfully")
            
            print("[SaporaGUI] ChatClient created, attempting connection...")
            print(f"[DEBUG] Calling chat_client.connect()...")
            
            connection_result = self.chat_client.connect()
            print(f"[DEBUG] chat_client.connect() returned: {connection_result}")
            
            if connection_result:
                print(f"[DEBUG] Connection successful, setting callbacks...")
                self.chat_client.set_callbacks(
                    self.gui_signals.user_list_updated.emit,
                    lambda sender, msg: self.gui_signals.chat_message_received.emit(sender, msg, False)
                )
                print(f"[DEBUG] Callbacks set, adding system message...")
                self.add_system_message(f"✓ Connected to Control Server as {self.username}.")
                print(f"[SaporaGUI] Successfully connected as {self.username}")
                print(f"[DEBUG] Connection setup complete")
            else:
                print(f"[DEBUG] Connection FAILED - connection_result was False")
                error_msg = (
                    f"❌ Cannot connect to server at {self.server_ip}:{CONTROL_PORT}\n\n"
                    "Possible reasons:\n"
                    "• Server is not running\n"
                    "• Wrong IP address\n"
                    "• Firewall blocking connection\n\n"
                    "Please start the server first:\n"
                    "  python server/server_main.py\n\n"
                    "Then restart the client."
                )
                self.add_system_message(error_msg)
                
                print(f"[SaporaGUI] Connection failed - showing error dialog")
                print(f"[DEBUG] About to show QMessageBox.critical")
                
                # Show error dialog
                QMessageBox.critical(
                    self,
                    "Connection Failed",
                    f"Cannot connect to server at {self.server_ip}:{CONTROL_PORT}\n\n"
                    "Please make sure the server is running:\n"
                    "  python server/server_main.py"
                )
                print(f"[DEBUG] QMessageBox closed, scheduling window close")
                QTimer.singleShot(100, self.close)
                print(f"[DEBUG] Returning from connect_to_control after failure")
                return
        except Exception as e:
            print(f"[DEBUG] EXCEPTION caught in connect_to_control: {type(e).__name__}: {e}")
            error_msg = (
                f"❌ Connection error: {str(e)}\n\n"
                f"Server: {self.server_ip}:{CONTROL_PORT}\n\n"
                "Make sure the server is running:\n"
                "  python server/server_main.py"
            )
            self.add_system_message(error_msg)
            
            print(f"[SaporaGUI] Exception during connection: {e}")
            import traceback
            print(f"[DEBUG] Full traceback:")
            traceback.print_exc()
            
            print(f"[DEBUG] About to show exception QMessageBox")
            QMessageBox.critical(
                self,
                "Connection Error",
                f"Error connecting to server:\n{str(e)}\n\n"
                "Please start the server first."
            )
            print(f"[DEBUG] Exception QMessageBox closed, scheduling window close")
            QTimer.singleShot(100, self.close)
            print(f"[DEBUG] Returning from connect_to_control after exception")
            return

        # 2. Video Client (UDP)
        try:
            print("[SaporaGUI] Initializing VideoClient...")
            self.video_client = VideoClient(self.server_ip, VIDEO_PORT, self.username, self.gui_signals.video_frame_ready.emit)
            threading.Thread(target=self.video_client.start_receiving, daemon=True).start()
        except Exception as e:
            self.add_system_message(f"✗ Failed to initialize Video Client: {str(e)}")
            self.video_client = None
            
        # 3. Audio Client (UDP)
        try:
            print("[SaporaGUI] Initializing AudioClient...")
            self.audio_client = AudioClient(self.server_ip, AUDIO_PORT, self.username)
            threading.Thread(target=self.audio_client.start_receiving, daemon=True).start()
        except Exception as e:
            self.add_system_message(f"✗ Failed to initialize Audio Client: {str(e)}")
            self.audio_client = None
            
        # 4. File Client (TCP)
        try:
            print("[SaporaGUI] Initializing FileTransferClient...")
            self.file_client = FileTransferClient(self.server_ip, FILE_TRANSFER_PORT, self.gui_signals.status_message.emit)
        except Exception as e:
            self.add_system_message(f"✗ Failed to initialize File Client: {str(e)}")
            self.file_client = None
            
        # 5. Screen Share Client (TCP)
        try:
            print("[SaporaGUI] Initializing ScreenShareServer...")
            self.screen_client = ScreenShareServer(self.server_ip, SCREEN_SHARE_PORT, self.gui_signals.status_message.emit)
        except Exception as e:
            self.add_system_message(f"✗ Failed to initialize Screen Share Client: {str(e)}")
            self.screen_client = None
        
        print("[DEBUG] connect_to_control() COMPLETED SUCCESSFULLY")
        print("[SaporaGUI] All clients initialized")

    # --- UI Updates & Layout ---

    def _reorganize_grid_layout(self):
        """Dynamically adjusts the video grid based on the number of participants."""
        for i in reversed(range(self.tiles_grid.count())): 
            widget = self.tiles_grid.itemAt(i).widget()
            if widget is not None:
                widget.setParent(None)
        
        all_users = list(self.user_tiles.keys())
        total_participants = len(all_users)

        cols = 1
        if total_participants > 1:
            cols = min(math.ceil(math.sqrt(total_participants)), 4)
        rows = math.ceil(total_participants / cols)

        for idx, username in enumerate(all_users):
            row = idx // cols
            col = idx % cols
            tile = self.user_tiles[username]
            self.tiles_grid.addWidget(tile, row, col, 1, 1)

    def update_user_tiles(self, user_list_raw):
        """Updates video tiles based on connected users."""
        user_list = [u['username'] for u in user_list_raw]

        for username in user_list:
            if username not in self.user_tiles:
                new_tile = VideoTile(username, is_self=(username == self.username))
                self.user_tiles[username] = new_tile
        
        to_remove = []
        for username in self.user_tiles.keys():
            if username != self.username and username not in user_list:
                to_remove.append(username)
        
        for username in to_remove:
            tile = self.user_tiles.pop(username)
            tile.deleteLater()
            self.video_frames.pop(username, None)

        self._reorganize_grid_layout()
        self.participant_count.setText(f"👥 {len(self.user_tiles)}")

    def update_video_frame(self, source_ip, frame):
        """Receives and caches a video frame for display."""
        try:
            if self.chat_client and hasattr(self.chat_client, 'manager'):
                username = self.chat_client.manager.get_client_username_by_ip(source_ip)
                self.video_frames[username] = frame
            else:
                self.video_frames[source_ip] = frame
        except AttributeError:
            self.video_frames[source_ip] = frame

    def process_video_updates(self):
        """Processes and displays all cached video frames."""
        if self.video_client and self.video_client.last_frame is not None:
            self.video_frames[self.username] = self.video_client.last_frame

        for username, tile in self.user_tiles.items():
            if username in self.video_frames:
                frame = self.video_frames[username]
                if frame is None: continue

                try:
                    target_w = tile.width() if tile.width() > 1 else VIDEO_WIDTH 
                    target_h = tile.height() if tile.height() > 1 else VIDEO_HEIGHT
                    
                    frame_resized = cv2.resize(frame, (target_w, target_h))
                    frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
                    h, w, ch = frame_rgb.shape
                    bytes_per_line = ch * w
                    
                    qt_image = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
                    pixmap = QPixmap.fromImage(qt_image)
                    
                    tile.video_label.setPixmap(pixmap)
                    tile.video_label.setStyleSheet(f"background-color: #000000; border-radius: 8px; min-height: {target_h - 10}px;")
                except Exception:
                    tile.video_label.setText(username[0].upper())
                    tile.video_label.setStyleSheet("color: #ffffff; font-size: 40px; background-color: #3c4043; border-radius: 8px;")
            elif username != self.username:
                tile.video_label.setText(username[0].upper())
                tile.video_label.setStyleSheet("color: #ffffff; font-size: 40px; background-color: #3c4043; border-radius: 8px;")

    def update_audio_status(self, source_ip, is_active):
        """Updates the microphone icon on a user's tile."""
        pass

    def update_ui_stats(self):
        """Updates time elapsed and other general stats."""
        elapsed = datetime.now() - self.meeting_start_time
        minutes = int(elapsed.total_seconds() // 60)
        seconds = int(elapsed.total_seconds() % 60)
        self.meeting_time.setText(f"{minutes:02d}:{seconds:02d}")

    # --- Chat & File Handling ---

    def add_system_message(self, message):
        """Adds a system message to the chat panel."""
        self.display_received_message("SYSTEM", message, False, is_system=True)
    
    def display_received_message(self, username, message, is_file, is_system=False):
        """Displays a message in the chat panel."""
        timestamp = datetime.now().strftime("%I:%M %p")
        
        if is_system:
             msg_widget = ChatMessageWidget("SYSTEM", message, timestamp, is_self=True, is_file=False)
             msg_widget.setStyleSheet("QWidget {background-color: #f7f7f7;} QLabel {color: #a0a0a0; font-style: italic;}")
        else:
             msg_widget = ChatMessageWidget(username, message, timestamp, is_self=(username == self.username), is_file=is_file)

        self.messages_layout.addWidget(msg_widget)
        self.chat_messages_scroll.verticalScrollBar().setValue(
            self.chat_messages_scroll.verticalScrollBar().maximum()
        )

    def send_chat_message(self):
        """Sends user input as a chat message."""
        message = self.chat_input.text().strip()
        if not message:
            return
        
        if self.chat_client:
            success = self.chat_client.send_message(message)
            if success:
                self.display_received_message(self.username, message, False) 
            else:
                self.add_system_message("✗ Failed to send message. Check control connection.")
        
        self.chat_input.clear()
    
    def open_file_transfer_menu(self):
        """Opens a context menu for file transfer options."""
        menu = QMenu(self)
        
        action_upload = QAction("📤 Upload File", self)
        action_upload.triggered.connect(self._prompt_upload)
        menu.addAction(action_upload)
        
        action_download = QAction("📥 Download File", self)
        action_download.triggered.connect(self._prompt_download)
        menu.addAction(action_download)
        
        btn_attach = self.sender()
        menu.exec_(btn_attach.mapToGlobal(btn_attach.rect().bottomLeft()))

    def _prompt_upload(self):
        """Prompts user to select a file for upload."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File to Upload", "", "All Files (*.*)")
        if not file_path:
            return
        
        filename = Path(file_path).name
        self.add_system_message(f"⏳ Uploading {filename}...")
        
        def upload_thread():
            success = self.file_client.upload_file(file_path)
            if success:
                self.gui_signals.chat_message_received.emit(self.username, filename, True)
        
        threading.Thread(target=upload_thread, daemon=True).start()

    def _prompt_download(self):
        """Prompts user for filename to download."""
        filename, ok = QInputDialog.getText(self, "Download File", "Enter filename (e.g., document.pdf):")
        if not ok or not filename.strip():
            return
        
        save_dir = QFileDialog.getExistingDirectory(self, "Save to Directory")
        if not save_dir:
            return
            
        self.add_system_message(f"⏳ Downloading {filename} to {Path(save_dir).name}...")

        def download_thread():
            self.file_client.download_file(filename, save_dir)
            
        threading.Thread(target=download_thread, daemon=True).start()

    # --- Feature Toggles ---

    def toggle_video(self):
        """Toggles video streaming (Webcam)."""
        if not self.video_active:
            if self.video_client and self.video_client.start_streaming(self.gui_signals.status_message.emit):
                self.video_active = True
                self.add_system_message("📹 Camera ON.")
            else:
                self.btn_camera.setChecked(False)
        else:
            if self.video_client:
                self.video_client.stop_streaming()
            self.video_active = False
            self.video_frames.pop(self.username, None)
            self.btn_camera.setChecked(False)
            self.add_system_message("📹 Camera OFF.")

    def toggle_audio(self):
        """Toggles audio streaming (Microphone)."""
        if not self.audio_active:
            if self.audio_client and self.audio_client.start_streaming(self.gui_signals.status_message.emit):
                self.audio_active = True
                self.add_system_message("🎤 Microphone ON.")
            else:
                self.btn_mic.setChecked(False)
        else:
            if self.audio_client:
                self.audio_client.stop_streaming()
            self.audio_active = False
            self.btn_mic.setChecked(False)
            self.add_system_message("🎤 Microphone OFF.")

    def toggle_screen_share(self):
        """Toggles screen sharing."""
        if not self.screen_active:
            if self.screen_client and hasattr(self.screen_client, 'start') and self.screen_client.start(): 
                self.screen_active = True
                self.add_system_message("🖥️ Sharing Screen.")
            else:
                self.btn_share.setChecked(False)
        else:
            if self.screen_client and hasattr(self.screen_client, 'stop'):
                self.screen_client.stop()
            self.screen_active = False
            self.btn_share.setChecked(False)
            self.add_system_message("🖥️ Screen Share Stopped.")
            
    def toggle_chat_panel(self):
        """Toggles chat panel visibility."""
        self.chat_visible = not self.chat_visible
        self.chat_panel.setVisible(self.chat_visible)
        self.btn_chat_toggle.setChecked(self.chat_visible)

    # --- Cleanup ---

    def leave_meeting(self):
        """Initiates graceful disconnect and closes the application."""
        reply = QMessageBox.question(
            self, "Leave Meeting",
            "Are you sure you want to leave the meeting?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.cleanup()
            self.close()

    def cleanup(self):
        """Cleans up all client resources."""
        print("[SaporaGUI] Cleaning up...")
        
        self.video_update_timer.stop()
        self.ui_update_timer.stop()

        if self.video_client: 
            self.video_client.stop_streaming()
        if self.audio_client: 
            self.audio_client.stop_streaming()
        if self.screen_client and hasattr(self.screen_client, 'stop'): 
            self.screen_client.stop()
        if self.chat_client: 
            self.chat_client.disconnect()

        self.add_system_message("Disconnected.")
        print("[SaporaGUI] Cleanup complete.")
        
    def closeEvent(self, event):
        """Handles window close event."""
        print("[SaporaGUI] Close event triggered")
        self.cleanup()
        event.accept()