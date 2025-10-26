# client/client_main.py

# ... (rest of the file)
import sys
import os
import argparse

# Add parent path to import shared modules
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Import the class directly from the file path
from client.main_ui import SaporaGUI 

# ... (rest of the file)
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPalette, QColor

def setup_arg_parser():
    """Sets up the command line argument parser."""
    parser = argparse.ArgumentParser(description='Sapora LAN Collaboration Client')
    parser.add_argument('--server', type=str, default=DEFAULT_SERVER_IP,
                        help='The IP address of the Sapora Unified Server (e.g., 192.168.1.10)')
    return parser

# client/client_main.py (Modified)

# ... (lines 1-27 remain the same) ...

def main():
    """Main function to run the client application."""
    parser = setup_arg_parser()
    args = parser.parse_args()
    
    # --- START OF MODIFICATION ---
    try:
        app = QApplication(sys.argv)
        
        # --- Apply Theme (Fusion with Blue/Light Accents) ---
        # ... (lines 34-45 remain the same) ...
        
        # Create and show the main window
        window = SaporaGUI(server_ip=args.server)
        window.show()
        
        sys.exit(app.exec_())
    except Exception as e:
        print("------------------------------------------")
        print("SAPORA CLIENT CRASH: UNHANDLED EXCEPTION")
        print(f"Error Type: {type(e).__name__}")
        print(f"Details: {e}")
        import traceback
        traceback.print_exc(file=sys.stdout)
        print("------------------------------------------")
        sys.exit(1)
    # --- END OF MODIFICATION ---

if __name__ == '__main__':
    main()