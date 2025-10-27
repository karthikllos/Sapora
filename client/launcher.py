"""
Sapora LAN Collaboration Suite - Modern Client Launcher
Production-ready launcher with splash screen, dependency checks,
and safe internal import recovery for all modules.
"""

import sys
import os
import time
import traceback
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QSplashScreen, QMessageBox, QWidget, QDialog, 
    QVBoxLayout, QLabel, QProgressBar, QPushButton, QLineEdit, QHBoxLayout
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont, QLinearGradient

# ---------------------------------------------------------------------
# 🔧 Ensure project root is in path (so shared/, client/, server/ can import)
# ---------------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ---------------------------------------------------------------------
# 🎬 Modern Splash Screen
# ---------------------------------------------------------------------
class ModernSplashScreen(QSplashScreen):
    """Modern animated splash screen"""
    def __init__(self):
        pixmap = QPixmap(600, 400)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        gradient = QLinearGradient(0, 0, 600, 400)
        gradient.setColorAt(0, QColor("#1a73e8"))
        gradient.setColorAt(1, QColor("#174ea6"))
        painter.fillRect(0, 0, 600, 400, gradient)

        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Segoe UI", 72, QFont.Bold))
        painter.drawText(pixmap.rect().adjusted(0, -80, 0, 0), Qt.AlignCenter, "🎥")

        painter.setFont(QFont("Segoe UI", 32, QFont.Bold))
        painter.drawText(pixmap.rect().adjusted(0, 40, 0, 0), Qt.AlignCenter, "Sapora")

        painter.setFont(QFont("Segoe UI", 14, QFont.Normal))
        painter.drawText(pixmap.rect().adjusted(0, 100, 0, 0), Qt.AlignCenter, "Professional Collaboration Suite")

        painter.setFont(QFont("Segoe UI", 10, QFont.Normal))
        painter.drawText(pixmap.rect().adjusted(0, 0, -20, -20), Qt.AlignBottom | Qt.AlignRight, "v2.0")
        painter.end()

        super().__init__(pixmap, Qt.WindowStaysOnTopHint)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)

    def showMessage(self, message, alignment=Qt.AlignBottom | Qt.AlignCenter, color=QColor("#ffffff")):
        super().showMessage(message, alignment, color)
        QApplication.processEvents()


# ---------------------------------------------------------------------
# ⚙️ Background Initialization Worker
# ---------------------------------------------------------------------
class InitializationWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, server_ip):
        super().__init__()
        self.server_ip = server_ip

    def run(self):
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

            for p, msg in steps:
                self.progress.emit(p, msg)
                time.sleep(0.3)
                if p == 20:
                    self._check_dependencies()

            self.finished.emit(True, "")

        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            print("InitializationWorker Exception:\n", traceback.format_exc())
            self.finished.emit(False, err)

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
            raise ImportError(f"Missing required modules: {', '.join(missing)}")


# ---------------------------------------------------------------------
# 🧱 Dialogs (Error + Config)
# ---------------------------------------------------------------------
class ErrorDialog(QDialog):
    def __init__(self, title, message, details=""):
        super().__init__()
        self.setWindowTitle(title)
        self.setFixedSize(500, 350)
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        self.setLayout(layout)

        icon = QLabel("⚠️")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 48px;")
        layout.addWidget(icon)

        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet("font-size: 18px; font-weight: 600; color: #202124;")
        layout.addWidget(title_lbl)

        msg_lbl = QLabel(message)
        msg_lbl.setAlignment(Qt.AlignCenter)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet("font-size: 14px; color: #5f6368;")
        layout.addWidget(msg_lbl)

        if details:
            det_lbl = QLabel(details[:600] + ("..." if len(details) > 600 else ""))
            det_lbl.setWordWrap(True)
            det_lbl.setStyleSheet(
                "font-size: 11px; color: #9aa0a6; background:#f8f9fa; padding:10px; border-radius:6px;"
            )
            layout.addWidget(det_lbl)

        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        ok_btn.setStyleSheet(
            "QPushButton {background:#1a73e8; color:white; border:none; border-radius:6px; padding:12px;}"
            "QPushButton:hover {background:#1557b0;}"
        )
        layout.addWidget(ok_btn)


class ConfigDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.server_ip = "127.0.0.1"
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Sapora - Connect to Server")
        self.setFixedSize(450, 380)
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout()
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        self.setLayout(layout)

        title = QLabel("Connect to Sapora Server")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:20px; font-weight:600; color:#202124;")
        layout.addWidget(title)

        lbl = QLabel("Server IP Address:")
        lbl.setStyleSheet("font-size:13px; color:#5f6368;")
        layout.addWidget(lbl)

        self.ip_input = QLineEdit(self.server_ip)
        self.ip_input.setPlaceholderText("e.g., 192.168.1.100")
        self.ip_input.setStyleSheet(
            "QLineEdit {border:2px solid #dadce0; border-radius:8px; padding:12px; font-size:14px;}"
            "QLineEdit:focus {border:2px solid #1a73e8;}"
        )
        layout.addWidget(self.ip_input)

        quick = QHBoxLayout()
        for label, val in [("Localhost", "127.0.0.1"), ("Auto-detect", None)]:
            btn = QPushButton(label)
            btn.setStyleSheet("background:#f1f3f4; border:none; border-radius:6px; padding:8px 16px;")
            if val:
                btn.clicked.connect(lambda _, v=val: self.ip_input.setText(v))
            else:
                btn.clicked.connect(self.auto_detect)
            quick.addWidget(btn)
        layout.addLayout(quick)
        layout.addStretch()

        connect = QPushButton("Connect")
        connect.setStyleSheet(
            "QPushButton {background:#1a73e8; color:white; border:none; border-radius:8px; padding:14px; font-weight:600;}"
            "QPushButton:hover {background:#1557b0;}"
        )
        connect.clicked.connect(self.accept)
        layout.addWidget(connect)

    def auto_detect(self):
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            self.ip_input.setText(ip)
        except Exception:
            self.ip_input.setText("127.0.0.1")

    def accept(self):
        self.server_ip = self.ip_input.text().strip()
        super().accept()

    def get_server_ip(self):
        return self.server_ip


# ---------------------------------------------------------------------
# 🚀 Main Launcher Class
# ---------------------------------------------------------------------
class SaporaLauncher:
    def __init__(self, server_ip):
        self.server_ip = server_ip
        self.app = None
        self.splash = None
        self.main_window = None

    def launch(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("Sapora")
        self.app.setApplicationVersion("2.0")
        self.app.setOrganizationName("Sapora Collaboration")
        self.app.setStyle("Fusion")

        self.splash = ModernSplashScreen()
        self.splash.show()
        self.splash.showMessage("Initializing...")

        self.init_worker = InitializationWorker(self.server_ip)
        self.init_worker.progress.connect(self.on_progress)
        self.init_worker.finished.connect(self.on_finish)
        self.init_worker.start()

        return self.app.exec_()

    def on_progress(self, p, msg):
        self.splash.showMessage(f"{msg} ({p}%)")

    def on_finish(self, success, err):
        if not success:
            self.splash.close()
            self.show_error("Initialization Failed", "Dependency check failed.", err)
            sys.exit(1)
            return
        try:
            from client.main_ui import SaporaGUI
            self.main_window = SaporaGUI(server_ip=self.server_ip)
            self.splash.finish(self.main_window)
            self.main_window.show()
        except Exception as e:
            self.splash.close()
            self.show_error(
                "Startup Error",
                "Failed to load main application window (Check Internal Imports)",
                f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}",
            )
            sys.exit(1)

    def show_error(self, title, msg, details=""):
        dlg = ErrorDialog(title, msg, details)
        dlg.exec_()


# ---------------------------------------------------------------------
# 🏁 Main Entrypoint
# ---------------------------------------------------------------------
def main():
    import argparse

    parser = argparse.ArgumentParser(description="Sapora LAN Collaboration Client")
    parser.add_argument("--server", type=str, help="Server IP (e.g. 192.168.1.100)")
    parser.add_argument("--localhost", action="store_true", help="Use localhost")
    args = parser.parse_args()

    if args.localhost:
        server_ip = "127.0.0.1"
    elif args.server:
        server_ip = args.server
    else:
        temp = QApplication(sys.argv)
        dlg = ConfigDialog()
        dlg.exec_()
        server_ip = dlg.get_server_ip()
        temp.quit()

    print(f"🚀 Launching Sapora Client\n📡 Server: {server_ip}\n⏰ {time.strftime('%Y-%m-%d %H:%M:%S')}\n{'-'*50}")

    try:
        launcher = SaporaLauncher(server_ip)
        exit_code = launcher.launch()
        print(f"{'-'*50}\n✓ Application closed normally")
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        sys.exit(1)


if __name__ == "__main__":
    main()
