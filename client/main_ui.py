"""
Sapora LAN Collaboration Suite - Main PyQt6 GUI
Modern Zoom-like interface integrating video, audio, chat, file transfer, and screen sharing.
(Modified: thread-safe signals for cross-thread UI updates)
"""

import sys
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QLineEdit, QTextEdit, QStackedWidget,
    QFileDialog, QMessageBox, QScrollArea, QFrame, QDialog,
    QDialogButtonBox, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize, QObject
from PyQt6.QtGui import QPixmap, QImage, QFont, QIcon
import cv2
import numpy as np

# Import client modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from client.video_client import VideoClient
from client.audio_client import AudioClient
from client.chat_client import ChatClient
from client.file_client import FileTransferClient
from client.screen_share_client import ScreenShareClient
from shared.constants import DEFAULT_SERVER_IP, VIDEO_PORT, CONTROL_PORT


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
    """Initial screen for entering server IP and username"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Join Sapora Meeting")
        self.setFixedSize(400, 250)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
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
        return self.ip_input.text().strip(), self.username_input.text().strip()


# ============================================================================
# MAIN APPLICATION WINDOW
# ============================================================================

class SaporaMainWindow(QMainWindow):
    """Main application window with Zoom-like interface"""
    
    # Thread-safe signals for updating UI from other threads
    chat_message_signal = pyqtSignal(str, str)   # sender, message
    user_list_signal = pyqtSignal(object)        # list of users
    frame_signal = pyqtSignal(object)            # (source_ip, frame) or frame
    file_status_signal = pyqtSignal(str)         # file status messages
    status_signal = pyqtSignal(str)              # generic status updates
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sapora - Video Conference")
        self.setMinimumSize(1200, 700)
        
        # Connection details
        self.server_ip = None
        self.username = None
        
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
        
        # Frame storage for display
        self.current_frame = None
        
        # Connect signals to slots (must be done before clients may emit)
        self.chat_message_signal.connect(self._on_chat_message_signal)
        self.user_list_signal.connect(self._on_user_list_signal)
        self.frame_signal.connect(self._on_frame_signal)
        self.file_status_signal.connect(self._on_file_status_signal)
        self.status_signal.connect(self._on_status_signal)
        
        # Show login dialog first
        self.show_login()
        
    def show_login(self):
        """Display login dialog and initialize on success"""
        dialog = LoginDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.server_ip, self.username = dialog.get_credentials()
            
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
            username=self.username
        )
        # chat_client will call these callbacks from its network thread; signals queue to GUI thread
        self.chat_client.set_callbacks(
            user_list_cb=self.user_list_signal.emit,
            message_cb=self.chat_message_signal.emit
        )
        
        # File Transfer Client: use file_status_signal for status updates
        self.file_client = FileTransferClient(
            server_ip=self.server_ip,
            status_callback=self.file_status_signal.emit
        )
        
        # Screen Share Client
        # Provide a status callback via status_signal
        try:
            self.screen_client = ScreenShareClient(
                server_ip=self.server_ip,
                mode="presenter",
                status_callback=self.status_signal.emit
            )
        except TypeError:
            # If ScreenShareClient doesn't accept status_callback, instantiate without it,
            # but we'll still call start in a thread and catch exceptions.
            self.screen_client = ScreenShareClient(
                server_ip=self.server_ip,
                mode="presenter"
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
        
        # Content area (video + chat)
        content_layout = QHBoxLayout()
        content_layout.setSpacing(0)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        # Video area
        self.video_widget = self.create_video_area()
        content_layout.addWidget(self.video_widget, stretch=3)
        
        # Chat panel (initially hidden)
        self.chat_panel = self.create_chat_panel()
        self.chat_panel.setVisible(False)
        content_layout.addWidget(self.chat_panel, stretch=1)
        
        main_layout.addLayout(content_layout)
        
        # Control bar
        main_layout.addWidget(self.create_control_bar())
        
        # Timer for updating video display
        self.display_timer = QTimer()
        self.display_timer.timeout.connect(self.update_video_display)
        self.display_timer.start(33)  # ~30 FPS
    
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
        self.meeting_label = QLabel(f"📹 Sapora Meeting")
        self.meeting_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(self.meeting_label)
        
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
        """Creates the central video display area"""
        widget = QFrame()
        widget.setObjectName("videoArea")
        
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Main video label
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setMinimumSize(640, 480)
        self.video_label.setScaledContents(False)
        self.video_label.setStyleSheet("background-color: #1a1a1a; border-radius: 10px;")
        self.video_label.setText("📹\n\nNo Video Feed\n\nClick 'Start Video' to begin")
        
        layout.addWidget(self.video_label)
        
        return widget
    
    def create_chat_panel(self):
        """Creates the chat side panel"""
        panel = QFrame()
        panel.setObjectName("chatPanel")
        panel.setMinimumWidth(300)
        panel.setMaximumWidth(400)
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Header
        header = QLabel("💬 Chat")
        header.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(header)
        
        # Message display
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setObjectName("chatDisplay")
        layout.addWidget(self.chat_display)
        
        # Input area
        input_layout = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Type a message...")
        self.chat_input.returnPressed.connect(self.send_chat_message)
        
        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self.send_chat_message)
        
        input_layout.addWidget(self.chat_input)
        input_layout.addWidget(send_btn)
        layout.addLayout(input_layout)
        
        # Participants list
        participants_header = QLabel("👥 Participants")
        participants_header.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(participants_header)
        
        self.participants_display = QTextEdit()
        self.participants_display.setReadOnly(True)
        self.participants_display.setMaximumHeight(100)
        self.participants_display.setObjectName("participantsList")
        layout.addWidget(self.participants_display)
        
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
            self.status_label.setText("● Connected")
            self.status_label.setStyleSheet("color: #4CAF50;")
            self.show_notification("Connected to server!")
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
            
            self.video_enabled = False
            self.video_btn.setText("🎥 Start Video")
            self.video_btn.setChecked(False)
            self.video_label.setText("📹\n\nVideo Stopped")
    
    def on_video_status(self, message):
        """Callback for video status updates (passed to video_client.start_streaming)"""
        # The video client will call this from its thread; route via signal to ensure UI-safe actions
        self.status_signal.emit(message)
    
    def _on_frame_signal(self, payload):
        """Slot invoked in GUI thread when a frame arrives via signal"""
        # payload could be either: frame OR (source_ip, frame)
        try:
            if isinstance(payload, tuple) and len(payload) >= 2:
                _, frame = payload[0], payload[1]
            else:
                frame = payload
            if isinstance(frame, np.ndarray):
                self.current_frame = frame
        except Exception:
            pass
    
    def update_video_display(self):
        """Update the video label with the latest frame"""
        # Show local camera feed if available
        frame = None
        if self.video_enabled:
            # video_client may store last_frame attribute
            try:
                if hasattr(self.video_client, "last_frame") and self.video_client.last_frame is not None:
                    frame = self.video_client.last_frame
            except Exception:
                pass
        
        # Otherwise show received frame
        if frame is None and self.current_frame is not None:
            frame = self.current_frame
        
        if frame is None:
            return
        
        try:
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_frame.shape
            bytes_per_line = ch * w
            
            # Create QImage and scale to fit
            qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_image)
            
            # Scale to fit label while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                self.video_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            self.video_label.setPixmap(scaled_pixmap)
        except Exception:
            # If conversion fails, ignore (frame format might be unexpected)
            pass
    
    # ========================================================================
    # AUDIO HANDLING
    # ========================================================================
    
    def toggle_audio(self):
        """Start/stop audio streaming"""
        if not self.audio_enabled:
            # Start audio
            success = self.audio_client.start_streaming(self.on_audio_status)
            if success:
                self.audio_enabled = True
                self.audio_btn.setText("🎙 Mute")
                self.audio_btn.setChecked(True)
                
                # Start receiver thread
                self.audio_thread = AudioStreamThread(self.audio_client)
                self.audio_thread.status_update.connect(self.show_notification)
                self.audio_thread.start()
        else:
            # Stop audio
            try:
                self.audio_client.stop_streaming()
            except Exception:
                pass
            if self.audio_thread:
                self.audio_thread.stop()
                self.audio_thread.wait(2000)
            
            self.audio_enabled = False
            self.audio_btn.setText("🎙 Start Audio")
            self.audio_btn.setChecked(False)
    
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
        """Send a chat message"""
        text = self.chat_input.text().strip()
        if text:
            try:
                self.chat_client.send_message(text)
            except Exception as e:
                self.show_notification(f"Chat send failed: {e}")
            self.chat_input.clear()
    
    # ---- Signal slots (these run in GUI thread) ----
    def _on_chat_message_signal(self, sender, message):
        """Thread-safe slot for appending chat messages to UI"""
        try:
            formatted = f"<b>{sender}:</b> {message}"
            self.chat_display.append(formatted)
        except Exception:
            pass
    
    def _on_user_list_signal(self, users):
        """Thread-safe slot for updating participants list"""
        try:
            user_text = "\n".join(f"• {user}" for user in users)
            self.participants_display.setText(user_text)
        except Exception:
            pass
    
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
        
        self.file_thread = FileTransferThread(self.file_client, "upload", file_path)
        self.file_thread.status_update.connect(self.file_status_signal.emit)
        self.file_thread.transfer_complete.connect(self.on_file_transfer_complete)
        self.file_thread.start()
        self.show_notification(f"📤 Uploading {Path(file_path).name}...")
    
    def on_file_transfer_complete(self, success):
        """Callback when file transfer completes"""
        if success:
            self.show_notification("✅ File transfer successful!")
        else:
            self.show_notification("❌ File transfer failed")
    
    def _on_file_status_signal(self, message):
        """Update UI from file client status callbacks"""
        self.show_notification(message)
    
    # ========================================================================
    # SCREEN SHARE HANDLING
    # ========================================================================
    
    def toggle_screen_share(self):
        """Start/stop screen sharing"""
        reply = QMessageBox.question(
            self,
            "Screen Share",
            "Start sharing your screen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Start screen sharing in a separate thread to prevent blocking
            def _start_sharing():
                try:
                    # ScreenShareClient may raise if pyscreeze/pillow missing; catch and emit
                    self.screen_client.start()
                except Exception as e:
                    self.status_signal.emit(f"Screen share error: {e}")
            
            t = QThread()
            # Run the blocking start in a Python thread (not a QThread) because ScreenShareClient likely uses blocking sockets/loops
            import threading
            threading.Thread(target=_start_sharing, daemon=True).start()
            self.show_notification("🖥 Screen sharing started")
    
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
                try:
                    self.video_thread.stop()
                    self.video_thread.wait(2000)
                except Exception:
                    pass
        
        # Stop audio
        if self.audio_enabled:
            try:
                self.audio_client.stop_streaming()
            except Exception:
                pass
            if self.audio_thread:
                try:
                    self.audio_thread.stop()
                    self.audio_thread.wait(2000)
                except Exception:
                    pass
        
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
    app = QApplication(sys.argv)
    app.setApplicationName("Sapora Video Conference")
    
    window = SaporaMainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
