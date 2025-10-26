"""
Sapora LAN Collaboration Suite - Client Main Entry Point
Parses arguments and runs the PyQt5 GUI application.
"""
import sys
import os
import argparse

# Add parent path to import shared modules
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.constants import DEFAULT_SERVER_IP
from client.main_ui import SaporaGUI
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPalette, QColor

def setup_arg_parser():
    """Sets up the command line argument parser."""
    parser = argparse.ArgumentParser(description='Sapora LAN Collaboration Client')
    parser.add_argument('--server', type=str, default=DEFAULT_SERVER_IP,
                        help='The IP address of the Sapora Unified Server (e.g., 192.168.1.10)')
    return parser

def main():
    """Main function to run the client application."""
    parser = setup_arg_parser()
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    
    # --- Apply Theme (Fusion with Blue/Light Accents) ---
    app.setStyle('Fusion')
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(240, 240, 240))
    palette.setColor(QPalette.WindowText, QColor(31, 31, 31))
    palette.setColor(QPalette.Base, QColor(255, 255, 255))
    palette.setColor(QPalette.Text, QColor(31, 31, 31))
    palette.setColor(QPalette.Button, QColor(224, 224, 224))
    palette.setColor(QPalette.ButtonText, QColor(31, 31, 31))
    # Blue Accent Color
    blue_accent = QColor(26, 115, 232) 
    palette.setColor(QPalette.Highlight, blue_accent)
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)
    # ----------------------------------------------------
    
    # Create and show the main window
    window = SaporaGUI(server_ip=args.server)
    window.show()
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()