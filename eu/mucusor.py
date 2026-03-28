import socket
import struct
import time
import threading
import random
import copy
import psutil
import os

import json

try:
    import pygame

    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

# import SoundGenerator

# --- Configuration ---
_CFG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tetris_config.json")


def _load_config():
    defaults = {
        "device_ip": "255.255.255.255",
        "send_port": 7270,
        "recv_port": 7271,
        "bind_ip": "0.0.0.0"
    }
    try:
        if os.path.exists(_CFG_FILE):
            with open(_CFG_FILE, encoding="utf-8") as f:
                return {**defaults, **json.load(f)}
    except:
        pass
    return defaults


CONFIG = _load_config()

# --- Networking Constants ---
UDP_SEND_IP = CONFIG.get("device_ip", "255.255.255.255")
UDP_SEND_PORT = CONFIG.get("send_port", 7271)
UDP_LISTEN_PORT = CONFIG.get("recv_port", 7270)

# --- Matrix Constants ---
NUM_CHANNELS = 8
LEDS_PER_CHANNEL = 64
FRAME_DATA_LENGTH = NUM_CHANNELS * LEDS_PER_CHANNEL * 3

# Board Area: Channels 0-6 (Rows 0-27)
BOARD_WIDTH = 16
BOARD_HEIGHT = 28

# Input Area: Channel 7 (Rows 28-31)
INPUT_CHANNEL = 7

# --- Colors (R, G, B) ---
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
YELLOW = (255, 255, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
CYAN = (0, 255, 255)
MAGENTA = (255, 0, 255)
ORANGE = (255, 165, 0)

# Tetris Shapes
SHAPES = {
    'I': [(-1, 0), (0, 0), (1, 0), (2, 0)],
    'O': [(0, 0), (1, 0), (0, 1), (1, 1)],
    'T': [(-1, 0), (0, 0), (1, 0), (0, 1)],
    'S': [(0, 0), (1, 0), (-1, 1), (0, 1)],
    'Z': [(-1, 0), (0, 0), (0, 1), (1, 1)],
    'J': [(-1, 0), (0, 0), (1, 0), (1, 1)],
    'L': [(-1, 0), (0, 0), (1, 0), (-1, 1)]
}

SHAPE_COLORS = {
    'I': CYAN, 'O': YELLOW, 'T': MAGENTA, 'S': GREEN,
    'Z': RED, 'J': BLUE, 'L': ORANGE
}

# --- Password for Checksum (Optional, code now uses forced checksums in NetworkManager) ---
PASSWORD_ARRAY = [
    35, 63, 187, 69, 107, 178, 92, 76, 39, 69, 205, 37, 223, 255, 165, 231, 16, 220, 99, 61, 25, 203, 203,
    155, 107, 30, 92, 144, 218, 194, 226, 88, 196, 190, 67, 195, 159, 185, 209, 24, 163, 65, 25, 172, 126,
    63, 224, 61, 160, 80, 125, 91, 239, 144, 25, 141, 183, 204, 171, 188, 255, 162, 104, 225, 186, 91, 232,
    3, 100, 208, 49, 211, 37, 192, 20, 99, 27, 92, 147, 152, 86, 177, 53, 153, 94, 177, 200, 33, 175, 195,
    15, 228, 247, 18, 244, 150, 165, 229, 212, 96, 84, 200, 168, 191, 38, 112, 171, 116, 121, 186, 147, 203,
    30, 118, 115, 159, 238, 139, 60, 57, 235, 213, 159, 198, 160, 50, 97, 201, 242, 240, 77, 102, 12,
    183, 235, 243, 247, 75, 90, 13, 236, 56, 133, 150, 128, 138, 190, 140, 13, 213, 18, 7, 117, 255, 45, 69,
    214, 179, 50, 28, 66, 123, 239, 190, 73, 142, 218, 253, 5, 212, 174, 152, 75, 226, 226, 172, 78, 35, 93,
    250, 238, 19, 32, 247, 233, 89, 123, 86, 138, 150, 146, 214, 192, 93, 152, 156, 211, 67, 51, 195, 165,
    66, 10, 10, 31, 1, 198, 234, 135, 34, 128, 208, 200, 213, 169, 238, 74, 221, 208, 104, 170, 166, 36, 76,
    177, 196, 3, 141, 167, 127, 56, 177, 203, 45, 107, 46, 82, 217, 139, 168, 45, 198, 6, 43, 11, 57, 88,
    182, 84, 189, 29, 35, 143, 138, 171
]

# --- Font Data (3x5 or similar) ---
FONT = {
    1: [(1, 0), (1, 1), (1, 2), (1, 3), (1, 4)],  # Center vertical
    2: [(0, 0), (1, 0), (2, 0), (2, 1), (1, 2), (0, 2), (0, 3), (0, 4), (1, 4), (2, 4)],
    3: [(0, 0), (1, 0), (2, 0), (2, 1), (1, 2), (2, 2), (2, 3), (0, 4), (1, 4), (2, 4)],
    4: [(0, 0), (0, 1), (0, 2), (1, 2), (2, 2), (2, 0), (2, 1), (2, 3), (2, 4)],
    5: [(0, 0), (1, 0), (2, 0), (0, 1), (0, 2), (1, 2), (2, 2), (2, 3), (0, 4), (1, 4), (2, 4)],
    6: [(0, 0), (1, 0), (2, 0), (0, 1), (0, 2), (0, 3), (1, 2), (2, 2), (2, 3), (0, 4), (1, 4), (2, 4)],
    7: [(0, 0), (1, 0), (2, 0), (2, 1), (1, 2), (1, 3), (1, 4)],
    'W': [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (4, 0), (4, 1), (4, 2), (4, 3), (4, 4), (1, 3), (2, 2), (3, 3)],
    # Wide W
    'I': [(0, 0), (1, 0), (2, 0), (1, 1), (1, 2), (1, 3), (0, 4), (1, 4), (2, 4)],
    'N': [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (3, 0), (3, 1), (3, 2), (3, 3), (3, 4), (1, 1), (2, 2)]  # Compact N
}

# Input Configuration
INPUT_REPEAT_RATE = 0.25  # Seconds per move when holding
INPUT_INITIAL_DELAY = 0.5  # Initial delay before repeat starts


def calculate_checksum(data):
    acc = sum(data)
    idx = acc & 0xFF
    return PASSWORD_ARRAY[idx] if idx < len(PASSWORD_ARRAY) else 0

class Asteroid:
    def __init__(self, shape_key, color, x, y):
        self.shape_key = shape_key
        self.blocks = copy.deepcopy(SHAPES[shape_key])
        self.color = color
        self.x = x
        self.y = y
        self.active = True

    def get_absolute_blocks(self):
        return [(self.x + bx, self.y + by) for bx, by in self.blocks]

class PresidentialVehicle:
    def __init__(self, shape_key, color, x, y):
        self.shape_key = shape_key
        self.blocks = copy.deepcopy(SHAPES[shape_key])
        self.color = color
        self.x = x
        self.y = y
        self.active = True

    def get_absolute_blocks(self):
        return [(self.x + bx, self.y + by) for bx, by in self.blocks]

class Player:
    def __init__(self, id, color, start_col_min, start_col_max):
        self.id = id
        self.color = color
        self.col_min = start_col_min
        self.col_max = start_col_max
        self.piece = None
        self.score = 0
        self.input_cooldown = 0
        self.next_shape_key = random.choice(list(SHAPES.keys()))

    def spawn_piece(self):
        shape_key = self.next_shape_key
        self.next_shape_key = random.choice(list(SHAPES.keys()))
        spawn_x = (self.col_min + self.col_max) // 2
        self.piece = PresidentialVehicle(shape_key, self.color, spawn_x, 0)

class PresidentGame:
    def __init__(self):
        self.board = [[BLACK for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]
        self.players = []

        self.running = True
        self.state = 'LOBBY'  # LOBBY, STARTUP, PLAYING, GAMEOVER
        self.startup_step = 0
        self.startup_timer = time.time()

        self.base_fall_speed = 1.0
        self.current_fall_speed = self.base_fall_speed
        self.min_fall_speed = 0.1
        self.last_tick = time.time()
        self.game_start_time = time.time()

        # Flashing/Clearing State
        self.flashing_lines = []
        self.flash_start_time = 0
        self.flash_duration = 0.5
        self.scoring_player = None

        self.winner_player = None
        self.winner_flash_count = 0
        self.game_over_timer = 0

        # Input State for Visualization & Logic
        self.button_states = [False] * 64
        self.prev_button_states = [False] * 64
        # Key: (player_id, action_str) -> Value: next_trigger_time
        self.input_timers = {}


class NetworkManager:
    def __init__(self, game):
        self.game = game
        self.sock_send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_send.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock_recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.running = True
        self.sequence_number = 0
        self.prev_button_states = [False] * 64

        # Auto-Bind Logic: If no bind_ip specified, we stay on 0.0.0.0 (default)
        bind_ip = CONFIG.get("bind_ip", "0.0.0.0")

        # We try to bind if a specific IP was requested, but fallback gracefully
        if bind_ip != "0.0.0.0":
            try:
                self.sock_send.bind((bind_ip, 0))
            except Exception as e:
                print(f"Warning: Could not bind send socket to {bind_ip} (Routing via default): {e}")

        try:
            self.sock_recv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock_recv.bind(("0.0.0.0", UDP_LISTEN_PORT))
        except Exception as e:
            print(f"Critical Error: Could not bind receive socket to port {UDP_LISTEN_PORT}: {e}")
            self.running = False

    def send_loop(self):
        while self.running:
            frame = self.game.render()
            self.send_packet(frame)
            time.sleep(0.05)

    def send_packet(self, frame_data):
        # Protocol v11 Implementation
        self.sequence_number = (self.sequence_number + 1) & 0xFFFF
        if self.sequence_number == 0: self.sequence_number = 1

        target_ip = UDP_SEND_IP
        port = UDP_SEND_PORT

        # --- 1. Start Packet ---
        rand1 = random.randint(0, 127)
        rand2 = random.randint(0, 127)
        start_packet = bytearray([
            0x75, rand1, rand2, 0x00, 0x08,
            0x02, 0x00, 0x00, 0x33, 0x44,
            (self.sequence_number >> 8) & 0xFF,
            self.sequence_number & 0xFF,
            0x00, 0x00, 0x00
        ])
        start_packet.append(0x0E)  # Force Checksum
        start_packet.append(0x00)
        try:
            self.sock_send.sendto(start_packet, (target_ip, port))
            self.sock_send.sendto(start_packet, ("127.0.0.1", port))
        except:
            pass

        # --- 2. FFF0 Packet ---
        rand1 = random.randint(0, 127)
        rand2 = random.randint(0, 127)

        # Payload size fixed for 8 channels * 64 LEDs
        fff0_payload = bytearray()
        for _ in range(NUM_CHANNELS):
            fff0_payload += bytes([(LEDS_PER_CHANNEL >> 8) & 0xFF, LEDS_PER_CHANNEL & 0xFF])

        fff0_internal = bytearray([
            0x02, 0x00, 0x00,
            0x88, 0x77,
            0xFF, 0xF0,
            (len(fff0_payload) >> 8) & 0xFF, (len(fff0_payload) & 0xFF)
        ]) + fff0_payload

        fff0_len = len(fff0_internal) - 1

        fff0_packet = bytearray([
            0x75, rand1, rand2,
            (fff0_len >> 8) & 0xFF, (fff0_len & 0xFF)
        ]) + fff0_internal
        fff0_packet.append(0x1E)  # Force Checksum
        fff0_packet.append(0x00)

        try:
            self.sock_send.sendto(fff0_packet, (target_ip, port))
            self.sock_send.sendto(fff0_packet, ("127.0.0.1", port))
        except:
            pass

        # --- 3. Data Packets ---
        chunk_size = 984
        data_packet_index = 1

        for i in range(0, len(frame_data), chunk_size):
            rand1 = random.randint(0, 127)
            rand2 = random.randint(0, 127)

            chunk = frame_data[i:i + chunk_size]

            internal_data = bytearray([
                0x02, 0x00, 0x00,
                (0x8877 >> 8) & 0xFF, (0x8877 & 0xFF),
                (data_packet_index >> 8) & 0xFF, (data_packet_index & 0xFF),
                (len(chunk) >> 8) & 0xFF, (len(chunk) & 0xFF)
            ])
            internal_data += chunk

            payload_len = len(internal_data) - 1

            packet = bytearray([
                0x75, rand1, rand2,
                (payload_len >> 8) & 0xFF, (payload_len & 0xFF)
            ]) + internal_data

            if len(chunk) == 984:
                packet.append(0x1E)
            else:
                packet.append(0x36)

            packet.append(0x00)

            try:
                self.sock_send.sendto(packet, (target_ip, port))
                self.sock_send.sendto(packet, ("127.0.0.1", port))
            except:
                pass

            data_packet_index += 1
            time.sleep(0.005)  # Slight delay

        # --- 4. End Packet ---
        rand1 = random.randint(0, 127)
        rand2 = random.randint(0, 127)
        end_packet = bytearray([
            0x75, rand1, rand2, 0x00, 0x08,
            0x02, 0x00, 0x00, 0x55, 0x66,
            (self.sequence_number >> 8) & 0xFF,
            self.sequence_number & 0xFF,
            0x00, 0x00, 0x00
        ])
        end_packet.append(0x0E)
        end_packet.append(0x00)
        try:
            self.sock_send.sendto(end_packet, (target_ip, port))
            self.sock_send.sendto(end_packet, ("127.0.0.1", port))
        except:
            pass

    def recv_loop(self):
        while self.running:
            try:
                data, _ = self.sock_recv.recvfrom(2048)
                if len(data) >= 1373 and data[0] == 0x88:
                    offset = 2 + (7 * 171) + 1
                    ch8_data = data[offset: offset + 170]
                    for led_idx, val in enumerate(ch8_data):
                        if led_idx >= 64: break
                        is_pressed = (val == 0xCC)

                        # Sync state to game active list
                        # Logic now handled in Game.tick() -> process_inputs()
                        self.game.button_states[led_idx] = is_pressed

            except Exception:
                pass

    def start_bg(self):
        t1 = threading.Thread(target=self.send_loop)
        t2 = threading.Thread(target=self.recv_loop)
        t1.daemon = True
        t2.daemon = True
        t1.start()
        t2.start()


def game_thread_func(game):
    while game.running:
        game.tick()
        time.sleep(0.01)

if __name__ == "__main__":
    game = PresidentGame()
    net = NetworkManager(game)
    net.start_bg()

    gt = threading.Thread(target=game_thread_func, args=(game,))
    gt.daemon = True
    gt.start()

    print("jocu lu mucusor Console Server Running.")
    print("Commands: 'start <num_players>', 'restart', 'quit'")

    try:
        while game.running:
            cmd = input("> ").strip().lower()
            if cmd == 'quit' or cmd == 'exit':
                game.running = False
                break
            elif cmd.startswith('start'):
                try:
                    num = int(cmd.split()[1])
                    game.start_game(num)
                    print(f"Started game with {num} players.")
                except:
                    print("Usage: start <num_players>")
            elif cmd == 'restart':
                game.restart_round()
                print("Restarted round.")
            else:
                print("Unknown command.")
    except KeyboardInterrupt:
        game.running = False

    net.running = False
    print("Exiting...")