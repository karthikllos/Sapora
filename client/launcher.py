"""
Sapora LAN Collaboration Suite - Modern Client Launcher
Production-ready launcher with splash screen and error handling
"""
import sys
import os
import time
import traceback
from pathlib import Path

# NOTE: QDialog is imported here to fix the AttributeError on ErrorDialog/ConfigDialog
from PyQt5.QtWidgets import (
    QApplication, QSplashScreen, QMessageBox, QWidget, QDialog, 
    QVBoxLayout, QLabel, QProgressBar, QPushButton, QLineEdit, QHBoxLayout
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont, QLinearGradient

# Add parent directory to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class ModernSplashScreen(QSplashScreen):
    """Modern animated splash screen"""
    
    def __init__(self):
        # Create gradient background
        pixmap = QPixmap(600, 400)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Gradient background
        gradient = QLinearGradient(0, 0, 600, 400)
        gradient.setColorAt(0, QColor("#1a73e8"))
        gradient.setColorAt(1, QColor("#174ea6"))
        
        painter.fillRect(0, 0, 600, 400, gradient)
        
        # Logo/Icon
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Segoe UI", 72, QFont.Bold))
        painter.drawText(pixmap.rect().adjusted(0, -80, 0, 0), Qt.AlignCenter, "🎥")
        
        # Title
        painter.setFont(QFont("Segoe UI", 32, QFont.Bold))
        painter.drawText(pixmap.rect().adjusted(0, 40, 0, 0), Qt.AlignCenter, "Sapora")
        
        # Subtitle
        painter.setFont(QFont("Segoe UI", 14, QFont.Normal))
        painter.drawText(pixmap.rect().adjusted(0, 100, 0, 0), Qt.AlignCenter, "Professional Collaboration Suite")
        
        # Version
        painter.setFont(QFont("Segoe UI", 10, QFont.Normal))
        painter.drawText(pixmap.rect().adjusted(0, 0, -20, -20), Qt.AlignBottom | Qt.AlignRight, "v2.0")
        
        painter.end()
        
        super().__init__(pixmap, Qt.WindowStaysOnTopHint)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        
    def showMessage(self, message, alignment=Qt.AlignBottom | Qt.AlignCenter, color=QColor("#ffffff")):
        """Show status message on splash screen"""
        super().showMessage(message, alignment, color)
        QApplication.processEvents()


class InitializationWorker(QThread):
    """Worker thread for application initialization"""
    
    progress = pyqtSignal(int, str)  # progress, message
    finished = pyqtSignal(bool, str)  # success, error_message
    
    def __init__(self, server_ip):
        super().__init__()
        self.server_ip = server_ip
        
    def run(self):
        """Initialize application components"""
        try:
            steps = [
                (10, "Loading configuration..."),
                (20, "Checking dependencies..."),
                (40, "Initializing video system..."),
                (60, "Initializing audio system..."),
                (80, "Setting up network..."),
                (90, "Loading user interface..."),
                (100, "Ready!")
            ]
            
            for progress, message in steps:
                self.progress.emit(progress, message)
                time.sleep(0.3)  # Simulate loading time
                
                # Actual checks
                if progress == 20:
                    self._check_dependencies()
                # We skip actual hardware checks here as cv2 and pyaudio might not be available 
                # in all environments, and the main app should handle graceful failure.
            
            self.finished.emit(True, "")
            
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            # We explicitly print the traceback here in the thread for debugging
            print(f"InitializationWorker Exception: {traceback.format_exc()}")
            self.finished.emit(False, error_msg)
    
    def _check_dependencies(self):
        """Check if all required modules are available"""
        # Checks only standard/common dependencies listed in requirements.txt
        required = ['cv2', 'numpy', 'pyaudio', 'PyQt5', 'mss', 'pyautogui', 'ffmpeg']
        missing = []
        
        for module in required:
            try:
                __import__(module)
            except ImportError:
                missing.append(module)
        
        if missing:
            # Note: Raising an ImportError here will trigger the failure path
            raise ImportError(f"Missing required modules: {', '.join(missing)}")
    
    # Removed _check_video and _check_audio as they are handled in the main app


# FIX 1: Inherit from QDialog instead of QWidget to allow exec_()
class ErrorDialog(QDialog):
    """Modern error dialog"""
    
    def __init__(self, title, message, details=""):
        super().__init__()
        self.setWindowTitle(title)
        self.setFixedSize(500, 350)
        # Use Qt.Dialog window flag for modality
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        self.setLayout(layout)
        
        # Icon
        icon_label = QLabel("⚠️")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("font-size: 48px;")
        layout.addWidget(icon_label)
        
        # Title
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            font-size: 18px;
            font-weight: 600;
            color: #202124;
        """)
        layout.addWidget(title_label)
        
        # Message
        msg_label = QLabel(message)
        msg_label.setAlignment(Qt.AlignCenter)
        msg_label.setWordWrap(True)
        msg_label.setStyleSheet("""
            font-size: 14px;
            color: #5f6368;
            line-height: 1.5;
        """)
        layout.addWidget(msg_label)
        
        # Details (if provided)
        if details:
            # Limit details display to prevent dialog from being excessively tall
            details_text = details[:500] + ('...' if len(details) > 500 else '')
            details_label = QLabel(details_text)
            details_label.setAlignment(Qt.AlignLeft)
            details_label.setWordWrap(True)
            details_label.setStyleSheet("""
                font-size: 11px;
                color: #9aa0a6;
                background-color: #f8f9fa;
                padding: 10px;
                border-radius: 6px;
                font-family: 'Consolas', 'Monaco', monospace;
            """)
            layout.addWidget(details_label)
        
        layout.addStretch()
        
        # OK button
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a73e8;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #1557b0;
            }
        """)
        # Connect OK button to QDialog's accept method
        ok_btn.clicked.connect(self.accept)
        layout.addWidget(ok_btn)
        
        self.setStyleSheet("""
            QDialog { /* Apply to QDialog base */
                background-color: white;
                font-family: 'Segoe UI', sans-serif;
            }
        """)


# FIX 1: Inherit from QDialog instead of QWidget to allow exec_()
class ConfigDialog(QDialog):
    """Configuration dialog for server connection"""
    
    def __init__(self):
        super().__init__()
        self.server_ip = "127.0.0.1"
        self.init_ui()
        
    def init_ui(self):
        """Initialize configuration UI"""
        self.setWindowTitle("Sapora - Connect to Server")
        self.setFixedSize(450, 380)
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        self.setLayout(layout)
        
        # Title
        title = QLabel("Connect to Sapora Server")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 20px;
            font-weight: 600;
            color: #202124;
            margin-bottom: 10px;
        """)
        layout.addWidget(title)
        
        # Server IP input
        ip_label = QLabel("Server IP Address:")
        ip_label.setStyleSheet("font-size: 13px; color: #5f6368;")
        layout.addWidget(ip_label)
        
        self.ip_input = QLineEdit()
        self.ip_input.setText(self.server_ip)
        self.ip_input.setPlaceholderText("e.g., 192.168.1.100")
        self.ip_input.setStyleSheet("""
            QLineEdit {
                background-color: white;
                border: 2px solid #dadce0;
                border-radius: 8px;
                padding: 12px 16px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #1a73e8;
            }
        """)
        layout.addWidget(self.ip_input)
        
        # Quick connect buttons
        quick_label = QLabel("Quick Connect:")
        quick_label.setStyleSheet("font-size: 13px; color: #5f6368; margin-top: 10px;")
        layout.addWidget(quick_label)
        
        quick_layout = QHBoxLayout()
        quick_layout.setSpacing(10)
        
        localhost_btn = QPushButton("Localhost")
        localhost_btn.setStyleSheet(self.get_quick_btn_style())
        localhost_btn.clicked.connect(lambda: self.ip_input.setText("127.0.0.1"))
        quick_layout.addWidget(localhost_btn)
        
        lan_btn = QPushButton("Auto-detect")
        lan_btn.setStyleSheet(self.get_quick_btn_style())
        lan_btn.clicked.connect(self.auto_detect_server)
        quick_layout.addWidget(lan_btn)
        
        layout.addLayout(quick_layout)
        
        layout.addStretch()
        
        # Connect button
        connect_btn = QPushButton("Connect")
        connect_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a73e8;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 14px 24px;
                font-size: 15px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1557b0;
            }
        """)
        # Connect button to QDialog's accept method
        connect_btn.clicked.connect(self.accept) 
        layout.addWidget(connect_btn)
        
        self.setStyleSheet("""
            QDialog { /* Apply to QDialog base */
                background-color: white;
                font-family: 'Segoe UI', sans-serif;
            }
        """)
    
    def get_quick_btn_style(self):
        return """
            QPushButton {
                background-color: #f1f3f4;
                color: #202124;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e8eaed;
            }
        """
    
    def auto_detect_server(self):
        """Auto-detect server on LAN"""
        import socket
        try:
            # Simple attempt to get local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            self.ip_input.setText(local_ip)
        except Exception:
            # Fallback for systems without external connection
            self.ip_input.setText("127.0.0.1")
    
    def accept(self):
        """Accept and save configuration"""
        self.server_ip = self.ip_input.text().strip()
        super().accept() # Use QDialog's built-in accept/close
    
    def get_server_ip(self):
        """Get configured server IP"""
        return self.server_ip


class SaporaLauncher:
    """Main application launcher with initialization and error handling"""
    
    def __init__(self, server_ip):
        self.server_ip = server_ip
        self.app = None
        self.splash = None
        self.main_window = None
        
    def launch(self):
        """Launch application with splash screen and initialization"""
        # Create QApplication
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("Sapora")
        self.app.setApplicationVersion("2.0")
        self.app.setOrganizationName("Sapora Collaboration")
        
        # Set application style
        self.app.setStyle('Fusion')
        
        # Show splash screen
        self.splash = ModernSplashScreen()
        self.splash.show()
        self.splash.showMessage("Initializing...", Qt.AlignBottom | Qt.AlignCenter)
        
        # Initialize in background
        self.init_worker = InitializationWorker(self.server_ip)
        self.init_worker.progress.connect(self.on_init_progress)
        self.init_worker.finished.connect(self.on_init_finished)
        self.init_worker.start()
        
        return self.app.exec_()
    
    def on_init_progress(self, progress, message):
        """Update splash screen with initialization progress"""
        self.splash.showMessage(f"{message} ({progress}%)", Qt.AlignBottom | Qt.AlignCenter)
    
    def on_init_finished(self, success, error_message):
        """Handle initialization completion"""
        # Ensure splash screen is closed immediately if an error occurred during loading
        if not success:
            self.splash.close()
            self.show_error(
                "Initialization Failed",
                "The application could not start properly (Dependency Check Failed).",
                error_message
            )
            sys.exit(1)
            return
            
        # Import main window (after all checks pass)
        try:
            # The actual GUI is imported here. If there is an internal ImportError
            # in main_ui.py (like the one originally reported for ScreenShareClient),
            # it will be caught by the outer 'except Exception as e' block below.
            from client.main_ui import SaporaGUI
            
            # Create main window
            self.main_window = SaporaGUI(server_ip=self.server_ip)
            
            # Close splash and show main window
            self.splash.finish(self.main_window)
            self.main_window.show()
            
        except Exception as e:
            # FIX: This catches the ImportError from within main_ui.py
            self.splash.close()
            self.show_error(
                "Startup Error",
                "Failed to load main application window (Check Internal Imports)",
                f"{type(e).__name__}: {str(e)}\n\n{traceback.format_exc()}"
            )
            sys.exit(1)
    
    def show_error(self, title, message, details=""):
        """Show error dialog"""
        # FIX 1: error_dialog is now a QDialog and has exec_()
        error_dialog = ErrorDialog(title, message, details)
        error_dialog.exec_() # Blocking call


def main():
    """Main entry point with command line arguments"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Sapora LAN Collaboration Client',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python launcher.py                           # Show connection dialog
  python launcher.py --server 192.168.1.100    # Connect to specific server
  python launcher.py --localhost               # Connect to localhost
        """
    )
    
    parser.add_argument(
        '--server',
        type=str,
        default=None,
        help='Server IP address (e.g., 192.168.1.100)'
    )
    
    parser.add_argument(
        '--localhost',
        action='store_true',
        help='Connect to localhost (127.0.0.1)'
    )
    
    parser.add_argument(
        '--no-splash',
        action='store_true',
        help='Skip splash screen'
    )
    
    args = parser.parse_args()
    
    # Determine server IP
    server_ip = None
    
    if args.localhost:
        server_ip = "127.0.0.1"
    elif args.server:
        server_ip = args.server
    else:
        # Show configuration dialog
        temp_app = QApplication(sys.argv)
        temp_app.setStyle('Fusion')
        
        # FIX 1: ConfigDialog is now a QDialog and has exec_()
        config_dialog = ConfigDialog()
        # show() followed by exec_() for modal dialog
        config_dialog.show()
        config_dialog.exec_() 
        
        server_ip = config_dialog.get_server_ip()
        temp_app.quit()
    
    # Launch application
    print(f"🚀 Launching Sapora Client...")
    print(f"📡 Connecting to server: {server_ip}")
    print(f"⏰ Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 50)
    
    try:
        launcher = SaporaLauncher(server_ip)
        exit_code = launcher.launch()
        
        print("-" * 50)
        print(f"✓ Application closed normally")
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(0)
        
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {type(e).__name__}")
        print(f"   {str(e)}")
        print("\n" + traceback.format_exc())
        sys.exit(1)


if __name__ == '__main__':
    main()
