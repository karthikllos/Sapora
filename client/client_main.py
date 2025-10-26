import sys
import os
import argparse
import traceback
from pathlib import Path

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtCore import Qt

# Define a default IP for convenience
DEFAULT_SERVER_IP = "127.0.0.1"

# Add parent path to import shared modules
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Import the main GUI class
# NOTE: Ensure the SaporaGUI class in client/main_ui.py is correctly defined.
try:
    from client.main_ui import SaporaGUI 
except ImportError:
    print("FATAL ERROR: Could not import SaporaGUI. Check client/main_ui.py and its dependencies.")
    sys.exit(1)


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
    
    # --- Robust Error Handling Starts Here ---
    try:
        app = QApplication(sys.argv)
        
        # --- Apply Theme (Fusion with Light/Blue Accents) ---
        app.setStyle('Fusion')

        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(240, 240, 240)) 
        palette.setColor(QPalette.WindowText, QColor(50, 50, 50))
        palette.setColor(QPalette.Base, QColor(255, 255, 255))
        palette.setColor(QPalette.AlternateBase, QColor(230, 230, 230))
        palette.setColor(QPalette.ToolTipBase, Qt.white)
        palette.setColor(QPalette.ToolTipText, Qt.black)
        palette.setColor(QPalette.Text, QColor(50, 50, 50))
        palette.setColor(QPalette.Button, QColor(240, 240, 240))
        palette.setColor(QPalette.ButtonText, QColor(50, 50, 50))
        
        # Highlight/Accent Color (Sapora Blue)
        ACCENT_COLOR = QColor(26, 115, 232) 
        palette.setColor(QPalette.Highlight, ACCENT_COLOR)
        palette.setColor(QPalette.HighlightedText, Qt.white)
        
        app.setPalette(palette)
        
        # Create and show the main window
        print(f"Starting Sapora Client...")
        print(f"Connecting to server: {args.server}")
        window = SaporaGUI(server_ip=args.server)
        window.show()
        
        # Start the application event loop
        sys.exit(app.exec_())
        
    except Exception as e:
        print("------------------------------------------")
        print("SAPORA CLIENT CRASH: UNHANDLED EXCEPTION")
        print(f"Error Type: {type(e).__name__}")
        print(f"Details: {e}")
        # Print full stack trace to the console
        traceback.print_exc(file=sys.stdout)
        print("------------------------------------------")
        # Exit with error code 1 indicating failure
        sys.exit(1)


if __name__ == '__main__':
    main()
