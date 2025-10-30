#!/usr/bin/env python3
"""
Simple CLI client for the Paid Hangman Server with MAC Authentication.
Usage:
    python3 client.py [host] [port]
Commands:
    /pay <mac-address>  - Pay ₹100 for 1 hour using MAC address
    /name <yourname>    - Set your display name
    /guess <letter>     - Guess a letter
    /status             - Show game status
    /time               - Show remaining time
    /quit               - Exit game
"""

import socket
import threading
import sys
import json
import os
import re

class ClientApp:
    def __init__(self, host="127.0.0.1", port=5000):
        self.host = host
        self.port = port
        self.sock = None

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.connect((self.host, self.port))
            print(f"🔗 Connected to {self.host}:{self.port}")
        except Exception as e:
            print(f"❌ Could not connect: {e}")
            return
        threading.Thread(target=self.receive_loop, daemon=True).start()
        self.input_loop()

    def display_hangman(self, stage):
        """Display hangman ASCII art based on incorrect guesses"""
        stages = [
            # Stage 0
            """
   +---+
   |   |
       |
       |
       |
       |
=========
""",
            # Stage 1
            """
   +---+
   |   |
   O   |
       |
       |
       |
=========
""",
            # Stage 2
            """
   +---+
   |   |
   O   |
   |   |
       |
       |
=========
""",
            # Stage 3
            """
   +---+
   |   |
   O   |
  /|   |
       |
       |
=========
""",
            # Stage 4
            """
   +---+
   |   |
   O   |
  /|\\  |
       |
       |
=========
""",
            # Stage 5
            """
   +---+
   |   |
   O   |
  /|\\  |
  /    |
       |
=========
""",
            # Stage 6
            """
   +---+
   |   |
   O   |
  /|\\  |
  / \\  |
       |
=========
"""
        ]
        return stages[min(stage, 6)]

    def parse_game_state(self, json_str):
        """Parse and display game state in a user-friendly format"""
        try:
            state = json.loads(json_str)
            
            print("\n" + "="*60)
            print("🎮 HANGMAN GAME STATE")
            print("="*60)
            
            # Display word with guessed letters
            word = state.get("word", "")
            guessed = set(state.get("guessed", []))
            display = " ".join([c.upper() if c in guessed else "_" for c in word])
            print(f"📝 Word: {display}")
            
            # Display hint
            hint = state.get("hint", "")
            print(f"💡 Hint: {hint}")
            
            # Display hangman
            hangman_stage = state.get("hangman_stage", 0)
            print(f"🎯 Hangman Stage: {hangman_stage}/6")
            print(self.display_hangman(hangman_stage))
            
            # Display guessed letters
            if guessed:
                print(f"🔤 Guessed letters: {', '.join(sorted(guessed)).upper()}")
            
            # Display players
            players = state.get("players", [])
            current_player = state.get("current_player", "")
            
            print("\n👥 Players:")
            for player in players:
                name = player.get("name", "Unknown")
                incorrect = player.get("incorrect", 0)
                max_attempts = player.get("max_attempts", 6)
                remaining = max_attempts - incorrect
                status = "🎯" if name == current_player else "⏳"
                print(f"  {status} {name}: {remaining}/{max_attempts} attempts left")
            
            if current_player:
                print(f"\n🎲 Current turn: {current_player}")
            
            print("="*60 + "\n")
            
        except json.JSONDecodeError:
            print(f"❌ Could not parse game state: {json_str}")

    def get_mac_address_suggestions(self):
        """Get MAC address suggestions from system"""
        suggestions = []
        try:
            # Try to get MAC addresses from system
            import uuid
            mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff) 
                           for elements in range(0,2*6,2)][::-1])
            suggestions.append(mac)
        except:
            pass
        
        # Add some example formats
        suggestions.extend([
            "00:11:22:33:44:55",
            "AA-BB-CC-DD-EE-FF", 
            "112233445566"
        ])
        
        return suggestions

    def validate_mac_format(self, mac):
        """Validate MAC address format"""
        mac_pattern = re.compile(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$|^[0-9A-Fa-f]{12}$')
        return bool(mac_pattern.match(mac))

    def receive_loop(self):
        """Background loop to receive and display messages from server"""
        try:
            while True:
                data = self.sock.recv(4096)
                if not data:
                    print("🔌 Disconnected from server.")
                    break

                for line in data.decode().splitlines():
                    if line.startswith("GAME_STATE:"):
                        json_str = line[len("GAME_STATE:"):]
                        self.parse_game_state(json_str)
                    else:
                        print(line)
        except Exception as e:
            print(f"⚠️ Connection error: {e}")
        finally:
            try:
                self.sock.close()
            except:
                pass

    def input_loop(self):
        """Loop for user input commands"""
        try:
            while True:
                cmd = input("> ").strip()
                if not cmd:
                    continue

                # If user typed "/pay" without MAC, suggest some
                if cmd.startswith("/pay") and len(cmd.split()) == 1:
                    print("⚠️ Please provide your MAC address.")
                    print("💡 Suggestions:")
                    for s in self.get_mac_address_suggestions():
                        print(f"   /pay {s}")
                    continue

                # Validate MAC if /pay command
                if cmd.startswith("/pay "):
                    parts = cmd.split(maxsplit=1)
                    if len(parts) == 2:
                        mac = parts[1].strip()
                        if not self.validate_mac_format(mac):
                            print("❌ Invalid MAC format. Use formats like:")
                            print("   00:11:22:33:44:55   or   AA-BB-CC-DD-EE-FF   or   001122334455")
                            continue

                # Send command
                try:
                    self.sock.sendall((cmd + "\n").encode())
                except:
                    print("🔌 Connection closed.")
                    break

                if cmd.lower() == "/quit":
                    break

        except KeyboardInterrupt:
            print("\n👋 Exiting client...")
            try:
                self.sock.sendall(b"/quit\n")
            except:
                pass
            try:
                self.sock.close()
            except:
                pass
            sys.exit(0)


if __name__ == "__main__":
    host = "127.0.0.1"
    port = 5000

    if len(sys.argv) >= 2:
        host = sys.argv[1]
    if len(sys.argv) >= 3:
        port = int(sys.argv[2])

    app = ClientApp(host, port)
    app.connect()

