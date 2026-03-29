import socket
import struct
import time
import threading
import random
import copy
import math
import psutil
import os
from collections import deque

import json

try:
    import tkinter as tk
    from tkinter import messagebox

    TK_AVAILABLE = True
except Exception:
    TK_AVAILABLE = False

try:
    import pygame

    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

# --- Configuration ---
_CFG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tetris_config.json")


def _load_config():
    defaults = {
        "device_ip": "255.255.255.255",
        "send_port": 7272,
        "recv_port": 7273,
        "bind_ip": "0.0.0.0"
    }
    try:
        if os.path.exists(_CFG_FILE):
            with open(_CFG_FILE, encoding="utf-8") as f:
                return {**defaults, **json.load(f)}
    except Exception:
        pass
    return defaults


def _save_config(config_data):
    try:
        with open(_CFG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
        return True
    except Exception as exc:
        print(f"Config save failed: {exc}")
        return False


CONFIG = _load_config()

# --- Networking Constants ---
UDP_SEND_IP = CONFIG.get("device_ip", "255.255.255.255")
UDP_SEND_PORT = CONFIG.get("send_port", 7273)
UDP_LISTEN_PORT = CONFIG.get("recv_port", 7272)

# --- Matrix Constants ---
NUM_CHANNELS = 8
LEDS_PER_CHANNEL = 64
FRAME_DATA_LENGTH = NUM_CHANNELS * LEDS_PER_CHANNEL * 3

# Board Area: Channels 0-6 (Rows 0-27)
BOARD_WIDTH = 16
BOARD_HEIGHT = 32

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
GOLD = (255, 215, 0)
PURPLE_BULLET = (170, 80, 255)

BULLET_NORMAL_COLOR = RED
BULLET_RARE_COLOR = PURPLE_BULLET
BULLET_RARE_CHANCE_PER_ROUND = 0.10
BULLET_RARE_CLICK_HITS = 2

BOMB_MIN_ROUND = 3
BOMB_CLICK_HITS = 3
BOMB_CAR_DAMAGE = 2
BOMB_START_COUNT = 1
BOMB_ROUND_GROWTH = 1

# Lobby difficulty buttons and presets
LOBBY_BUTTONS = {
    'E': {
        'label': 'E',
        'x_range': (5, 11),
        'y_range': (4, 8),
        'bg': lambda p: (0, int(140 * p), int(55 * p)),
        'border': lambda p: (0, int(70 * p), int(25 * p)),
        'text': (180, 255, 200),
        'difficulty': 'EASY',
    },
    'N': {
        'label': 'N',
        'x_range': (5, 11),
        'y_range': (13, 18),
        'bg': lambda p: (0, int(60 * p), int(200 * p)),
        'border': lambda p: (0, int(30 * p), int(100 * p)),
        'text': (180, 215, 255),
        'difficulty': 'NORMAL',
    },
    'H': {
        'label': 'H',
        'x_range': (5, 11),
        'y_range': (23, 27),
        'bg': lambda p: (int(185 * p), int(20 * p), 0),
        'border': lambda p: (int(92 * p), int(10 * p), 0),
        'text': (255, 160, 90),
        'difficulty': 'HARD',
    },
}

DIFFICULTY_PRESETS = {
    'EASY': {'num_players': 3, 'mins': 1, 'rounds': 3, 'fall_speed': 0.55},
    'NORMAL': {'num_players': 5, 'mins': 2, 'rounds': 5, 'fall_speed': 0.40},
    'HARD': {'num_players': 8, 'mins': 3, 'rounds': 7, 'fall_speed': 0.26},
}

# Tetris Shapes
SHAPES = {
    'O': [(0, 0)],  # Damage cubes are 1x1
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
    'A': [(1, 0), (0, 1), (2, 1), (0, 2), (1, 2), (2, 2), (0, 3), (2, 3), (0, 4), (2, 4)],
    'E': [(0, 0), (1, 0), (2, 0), (0, 1), (0, 2), (1, 2), (2, 2), (0, 3), (0, 4), (1, 4), (2, 4)],
    'G': [(0, 0), (1, 0), (2, 0), (0, 1), (0, 2), (2, 2), (0, 3), (2, 3), (0, 4), (1, 4), (2, 4)],
    'M': [(0, 0), (2, 0), (0, 1), (1, 1), (2, 1), (0, 2), (2, 2), (0, 3), (2, 3), (0, 4), (2, 4)],
    'O': [(0, 0), (1, 0), (2, 0), (0, 1), (2, 1), (0, 2), (2, 2), (0, 3), (2, 3), (0, 4), (1, 4), (2, 4)],
    'R': [(0, 0), (1, 0), (2, 0), (0, 1), (2, 1), (0, 2), (1, 2), (0, 3), (2, 3), (0, 4), (2, 4)],
    'V': [(0, 0), (2, 0), (0, 1), (2, 1), (0, 2), (2, 2), (0, 3), (2, 3), (1, 4)],
    'W': [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (4, 0), (4, 1), (4, 2), (4, 3), (4, 4), (1, 3), (2, 2), (3, 3)],
    # Wide W
    'I': [(0, 0), (1, 0), (2, 0), (1, 1), (1, 2), (1, 3), (0, 4), (1, 4), (2, 4)],
    'N': [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (3, 0), (3, 1), (3, 2), (3, 3), (3, 4), (1, 1), (2, 2)],  # Compact N
    'H': [(0, 0), (2, 0), (0, 1), (2, 1), (0, 2), (1, 2), (2, 2), (0, 3), (2, 3), (0, 4), (2, 4)],  # H
}

# Input Configuration
INPUT_REPEAT_RATE = 0.25  # Seconds per move when holding
INPUT_INITIAL_DELAY = 0.5  # Initial delay before repeat starts


def calculate_checksum(data):
    acc = sum(data)
    idx = acc & 0xFF
    return PASSWORD_ARRAY[idx] if idx < len(PASSWORD_ARRAY) else 0

def generate_spread_obstacles(count, min_distance=4):
    """Generate random obstacles with minimum spacing to prevent clumping"""
    obstacles = []
    attempts = 0
    max_attempts = count * 50  # Prevent infinite loops
    
    while len(obstacles) < count and attempts < max_attempts:
        x = random.randint(0, BOARD_WIDTH - 1)
        y = random.randint(0, BOARD_HEIGHT - 1)
        
        # Check if this position is far enough from all existing obstacles
        is_valid = True
        for ox, oy in obstacles:
            distance = abs(x - ox) + abs(y - oy)  # Manhattan distance
            if distance < min_distance:
                is_valid = False
                break
        
        if is_valid:
            obstacles.append((x, y))
        
        attempts += 1
    
    return obstacles

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
    global_points_default = 8
    global_points = 8

    @classmethod
    def reset_global_points(cls, points=None):
        cls.global_points = cls.global_points_default if points is None else points

    @classmethod
    def apply_hit(cls):
        cls.global_points = max(0, cls.global_points - 1)
        return cls.global_points

    def __init__(self, shape_key, color, x, y, click_hits_required=1):
        self.shape_key = shape_key
        self.blocks = copy.deepcopy(SHAPES[shape_key])
        self.color = color
        self.x = x
        self.y = y
        self.active = True
        self.click_hits_required = max(1, int(click_hits_required))
        self.click_hits_remaining = self.click_hits_required

    def get_absolute_blocks(self):
        return [(self.x + bx, self.y + by) for bx, by in self.blocks]

class Player:
    def __init__(self, id, color, start_col_min, start_col_max):
        self.id = id
        self.color = color
        self.col_min = start_col_min
        self.col_max = start_col_max
        self.piece = None
        self.directionX = random.choice([-1, 1])
        self.directionY = random.choice([-1, 1])
        self.input_cooldown = 0
        self.next_shape_key = random.choice(list(SHAPES.keys()))
        self.respawn_time = 0  # when to respawn (0 = not waiting)
        self.hits_taken = 0
        self.last_progress_time = time.time()

    def spawn_piece(self):
        shape_key = self.next_shape_key
        self.next_shape_key = random.choice(list(SHAPES.keys()))
        # Use safe spawn
        if hasattr(self, 'game') and hasattr(self.game, '_find_safe_spawn'):
            spawn_x, spawn_y = self.game._find_safe_spawn(include_dynamic=True, prefer_cop_edges=True)
        else:
            spawn_x = random.randint(0, BOARD_WIDTH - 1)
            spawn_y = random.randint(0, BOARD_HEIGHT - 1)
        round_number = 1
        if hasattr(self, 'game') and hasattr(self.game, 'round_number'):
            round_number = max(1, int(self.game.round_number))
        rare_chance = min(1.0, max(0.0, (round_number - 1) * BULLET_RARE_CHANCE_PER_ROUND))
        is_rare = random.random() < rare_chance
        piece_color = BULLET_RARE_COLOR if is_rare else self.color
        required_clicks = BULLET_RARE_CLICK_HITS if is_rare else 1
        self.piece = PresidentialVehicle(
            shape_key,
            piece_color,
            spawn_x,
            spawn_y,
            click_hits_required=required_clicks,
        )
        self.last_progress_time = time.time()


class SoundManager:
    def __init__(self, base_dir):
        self.enabled = False
        self.hit_sound = None
        self.ambient_sound = None
        self.ambient_channel = None
        self.deflect_sound = None
        self.attack_sound = None
        self.bomb_deflect_sound = None

        if not PYGAME_AVAILABLE:
            return

        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=256)

            candidates = [
                os.path.join(base_dir, "hit.wav"),
                os.path.join(base_dir, "_sfx", "hit.wav"),
                os.path.join(os.path.dirname(base_dir), "_sfx", "hit.wav"),
                os.path.join(os.getcwd(), "hit.wav"),
                os.path.join(os.getcwd(), "_sfx", "hit.wav"),
            ]

            hit_path = next((path for path in candidates if os.path.exists(path)), None)
            if not hit_path:
                print("Audio note: hit.wav not found; hit sound disabled.")
            else:
                self.hit_sound = pygame.mixer.Sound(hit_path)
                self.hit_sound.set_volume(0.35)

            ambient_candidates = [
                os.path.join(base_dir, "main_ambient.wav"),
                os.path.join(base_dir, "_sfx", "main_ambient.wav"),
                os.path.join(os.path.dirname(base_dir), "_sfx", "main_ambient.wav"),
                os.path.join(os.getcwd(), "main_ambient.wav"),
                os.path.join(os.getcwd(), "_sfx", "main_ambient.wav"),
                os.path.join(base_dir, "main_ambient.mp3"),
                os.path.join(base_dir, "_sfx", "main_ambient.mp3"),
                os.path.join(os.getcwd(), "main_ambient.mp3"),
                os.path.join(os.getcwd(), "_sfx", "main_ambient.mp3"),
            ]
            ambient_path = next((p for p in ambient_candidates if os.path.exists(p)), None)
            if not ambient_path:
                print("Audio note: main_ambient not found; lobby ambient disabled.")
            else:
                self.ambient_sound = pygame.mixer.Sound(ambient_path)

            def _load_sfx(name):
                exts = [".wav", ".mp3"]
                dirs = [base_dir, os.path.join(base_dir, "_sfx"),
                        os.path.join(os.path.dirname(base_dir), "_sfx"), os.getcwd(),
                        os.path.join(os.getcwd(), "_sfx")]
                for d in dirs:
                    for ext in exts:
                        p = os.path.join(d, name + ext)
                        if os.path.exists(p):
                            return p
                return None

            self.countdown_sound = None
            ct_path = _load_sfx("countdown_tick")
            if ct_path:
                self.countdown_sound = pygame.mixer.Sound(ct_path)
                self.countdown_sound.set_volume(0.35)
            else:
                print("Audio note: countdown_tick not found; countdown sound disabled.")

            self.spawn_sound = None
            sp_path = _load_sfx("spawn")
            if sp_path:
                self.spawn_sound = pygame.mixer.Sound(sp_path)
                self.spawn_sound.set_volume(0.3)
            else:
                print("Audio note: spawn not found; spawn sound disabled.")

            self.win_sound = None
            win_path = _load_sfx("win")
            if win_path:
                self.win_sound = pygame.mixer.Sound(win_path)
                self.win_sound.set_volume(0.3)
            else:
                print("Audio note: win not found; win sound disabled.")

            self.loss_sound = None
            loss_path = _load_sfx("loss")
            if loss_path:
                self.loss_sound = pygame.mixer.Sound(loss_path)
                self.loss_sound.set_volume(0.3)
            else:
                print("Audio note: loss not found; loss sound disabled.")

            self.deflect_sound = None
            deflect_path = _load_sfx("deflect")
            if deflect_path:
                self.deflect_sound = pygame.mixer.Sound(deflect_path)
                self.deflect_sound.set_volume(0.25)  # Slightly quieter as it can be frequent
            else:
                print("Audio note: deflect not found; deflect sound disabled.")

            self.attack_sound = None
            attack_path = _load_sfx("attack")
            if attack_path:
                self.attack_sound = pygame.mixer.Sound(attack_path)
                self.attack_sound.set_volume(0.25)
            else:
                print("Audio note: attack not found; attack sound disabled.")

            self.bomb_deflect_sound = None
            bomb_deflect_path = _load_sfx("bomb_deflect")
            if bomb_deflect_path:
                self.bomb_deflect_sound = pygame.mixer.Sound(bomb_deflect_path)
                self.bomb_deflect_sound.set_volume(0.28)
            else:
                print("Audio note: bomb_deflect not found; bomb deflect sound disabled.")

            self.enabled = True
        except Exception as exc:
            print(f"Audio init failed: {exc}")
            self.enabled = False

    def play_ambient(self):
        if not self.enabled or not self.ambient_sound:
            return
        try:
            if self.ambient_channel and self.ambient_channel.get_busy():
                return  # already playing
            self.ambient_sound.set_volume(0.30)
            self.ambient_channel = self.ambient_sound.play(loops=-1)
        except Exception:
            pass

    def stop_ambient(self):
        if not self.enabled or not self.ambient_sound:
            return
        try:
            if self.ambient_channel:
                self.ambient_channel.stop()
            else:
                self.ambient_sound.stop()
        except Exception:
            pass

    def play_countdown_tick(self):
        if not self.enabled or not self.countdown_sound:
            return
        try:
            self.countdown_sound.play()
        except Exception:
            pass

    def play_spawn(self):
        if not self.enabled or not self.spawn_sound:
            return
        try:
            self.spawn_sound.play()
        except Exception:
            pass

    def play_hit(self):
        if not self.enabled or not self.hit_sound:
            return
        try:
            self.hit_sound.play()
        except Exception:
            pass

    def play_win(self):
        if not self.enabled or not self.win_sound:
            return
        try:
            self.win_sound.play()
        except Exception:
            pass

    def play_loss(self):
        if not self.enabled or not self.loss_sound:
            return
        try:
            self.loss_sound.play()
        except Exception:
            pass

    def play_deflect(self):
        if not self.enabled or not self.deflect_sound:
            return
        try:
            self.deflect_sound.play()
        except Exception:
            pass

    def play_attack(self):
        if not self.enabled or not self.attack_sound:
            return
        try:
            self.attack_sound.play()
        except Exception:
            pass

    def play_bomb_deflect(self):
        if not self.enabled or not self.bomb_deflect_sound:
            return
        try:
            self.bomb_deflect_sound.play()
        except Exception:
            pass

class PresidentGame:
    def apply_color_scheme(self):
        next_scheme = self.color_schemes[(self.round_number-1) % len(self.color_schemes)]
        self.prev_color_scheme = self.current_color_scheme
        self.current_color_scheme = next_scheme
        self.color_transition_active = True
        self.color_transition_start = time.time()
        self.obstacle_color = next_scheme['obstacle']

    def __init__(self):
        self.sound = SoundManager(os.path.dirname(os.path.abspath(__file__)))
        self.board = [[BLACK for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]
        self.players = []

        self.running = True
        self.state = 'LOBBY'  # LOBBY, PREFIGHT_FLICKER, COUNTDOWN, TRANSITION, PREPLAY_FLICKER, PLAYING, PREWIN_FLICKER, GAMEOVER, WIN
        self.startup_step = 0
        self.startup_timer = time.time()
        self.lobby_anim_start = time.time()
        self.prefight_flicker_start = 0.0
        self.prefight_flicker_interval = 0.05
        self.prefight_flicker_toggles = 4  # 2 visible flickers (on/off pairs)
        self.preplay_flicker_start = 0.0
        self.preplay_flicker_interval = 0.05
        self.preplay_flicker_toggles = 4  # 2 visible flickers (on/off pairs)
        self.prewin_flicker_start = 0.0
        self.prewin_flicker_interval = 0.05
        self.prewin_flicker_toggles = 4  # 2 visible flickers (on/off pairs)

        self.base_fall_speed = 0.4
        self.current_fall_speed = self.base_fall_speed
        self.min_fall_speed = 0.1
        self.last_tick = time.time()
        self.game_start_time = time.time()
        self.player_stuck_timeout = 2.0

        self.lock = threading.RLock()

        # Flashing/Clearing State
        self.flashing_lines = []
        self.flash_start_time = 0
        self.flash_duration = 0.5
        self.scoring_player = None

        self.winner_player = None
        self.winner_flash_count = 0
        self.game_over_timer = 0

        # --- Obstacle maps (positions for tree-like obstacles, full grid) ---
        candidate_maps = [
            # Center zig-zag gates.
            [(7, 10), (8, 12), (7, 14), (8, 16), (7, 18), (8, 20), (7, 22)],
            # Inner box clusters.
            [(5, 11), (10, 11), (5, 16), (10, 16), (5, 21), (10, 21), (7, 14), (8, 18)],
            # Middle diamonds.
            [(7, 11), (6, 14), (8, 14), (5, 17), (9, 17), (6, 20), (8, 20), (7, 23)],
            # Offset center pillars.
            [(6, 10), (9, 12), (6, 15), (9, 17), (6, 20), (9, 22)],
            # Procedural playable candidates (middle zone only).
            self._generate_middle_obstacles(6, min_distance=5),
            self._generate_middle_obstacles(7, min_distance=5),
            self._generate_middle_obstacles(8, min_distance=5),
        ]
        self.obstacle_maps = self._build_playable_maps(candidate_maps, desired_count=10)
        self.obstacle_color = (64, 64, 64)  # dark gray
        self.current_obstacle_map = []
        self.cop_spawn_points = self._build_cop_spawn_points()
        self.bombs = []
        self.cop_move_interval = 10.0
        self.last_cop_move_time = time.time()

        # Motion trail for smooth visuals
        self.trail = [[0.0 for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]
        self.trail_color = [[BLACK for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]
        self.trail_decay = 0.74  # multiplier per render frame (lower = faster, stronger fade)

        # Sequential spawn
        self.spawn_interval = 1.5  # seconds between each new cube
        self.next_spawn_index = 0
        self.last_spawn_time = 0

        # Board touch detection (all channels, 28 rows x 16 cols)
        self.board_pressed = [[False for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]
        self.prev_board_pressed = [[False for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]
        self.respawn_delay = 5.0  # seconds before a clicked cube respawns
        self.board_touch_queue = deque()  # event queue for new press events

        # Input State for Visualization & Logic
        self.button_states = [False] * 64
        self.prev_button_states = [False] * 64
        # Key: (player_id, action_str) -> Value: next_trigger_time
        self.input_timers = {}

        # Big cube
        self.big_cube = None
        self.big_cube_speed = 0.6  # seconds per move
        self.big_cube_last_move = time.time()
        self.big_cube_direction = random.choice([(0,1),(0,-1),(1,0),(-1,0)])
        self.big_cube_last_turn = time.time()
        self.big_cube_last_progress = time.time()
        self.big_cube_stuck_timeout = 5.0
        self.big_cube_recovering = False
        self.big_cube_recover_forward = (1, 0)
        self.big_cube_recover_side_dx = -1

        self.round_duration_minutes = 1  # default, will be set at start
        self.total_rounds_to_survive = 1
        self.round_start_time = None
        self.round_number = 1
        self.starting_points = 8
        self.color_schemes = [
            {'bg': (0,0,0), 'obstacle': (64,64,64), 'bullet': (255,215,0), 'car': (255,255,255)},
            {'bg': (10,10,30), 'obstacle': (0,128,255), 'bullet': (255,140,0), 'car': (255,255,255)},
            {'bg': (30,10,10), 'obstacle': (128,0,64), 'bullet': (0,255,255), 'car': (255,255,255)},
            {'bg': (0,30,10), 'obstacle': (0,255,128), 'bullet': (255,0,255), 'car': (255,255,255)},
        ]
        self.current_color_scheme = self.color_schemes[0]
        self.prev_color_scheme = self.current_color_scheme
        self.color_transition_active = False
        self.color_transition_start = 0.0
        self.color_transition_duration = 1.2

        # Start ambient music for the lobby.
        self.sound.play_ambient()

    def _blend_color(self, color_a, color_b, t):
        t = max(0.0, min(1.0, t))
        return (
            int(color_a[0] + (color_b[0] - color_a[0]) * t),
            int(color_a[1] + (color_b[1] - color_a[1]) * t),
            int(color_a[2] + (color_b[2] - color_a[2]) * t),
        )

    def _get_active_color_scheme(self):
        if not self.color_transition_active:
            return self.current_color_scheme

        elapsed = time.time() - self.color_transition_start
        progress = elapsed / self.color_transition_duration if self.color_transition_duration > 0 else 1.0

        if progress >= 1.0:
            self.color_transition_active = False
            return self.current_color_scheme

        return {
            'bg': self._blend_color(self.prev_color_scheme['bg'], self.current_color_scheme['bg'], progress),
            'obstacle': self._blend_color(self.prev_color_scheme['obstacle'], self.current_color_scheme['obstacle'], progress),
            'bullet': self._blend_color(self.prev_color_scheme['bullet'], self.current_color_scheme['bullet'], progress),
            'car': self._blend_color(self.prev_color_scheme['car'], self.current_color_scheme['car'], progress),
        }

    def _handle_player_hit(self, p, reason):
        if PresidentialVehicle.global_points <= 0:
            return

        p.hits_taken += 1
        points_left = PresidentialVehicle.apply_hit()
        self.sound.play_hit()
        if p.piece:
            p.piece.active = False

        if points_left <= 0:
            p.respawn_time = 0
            print(f"Global car health depleted by {reason}!")
            self._check_game_over()
        else:
            p.respawn_time = time.time() + self.respawn_delay
            print(f"Bullet {p.id} hit by {reason}! Global points left: {points_left}")

    def _destroy_player_piece(self, p, reason):
        if p.piece:
            p.piece.active = False
        p.respawn_time = time.time() + self.respawn_delay
        print(f"Bullet {p.id} destroyed by {reason}.")

        self.sound.play_deflect()

    def _apply_global_damage(self, amount, reason):
        if PresidentialVehicle.global_points <= 0:
            return

        amount = max(1, int(amount))
        points_left = PresidentialVehicle.global_points
        for _ in range(amount):
            points_left = PresidentialVehicle.apply_hit()
            if points_left <= 0:
                break

        self.sound.play_hit()
        if points_left <= 0:
            print(f"Global car health depleted by {reason}!")
            self._check_game_over()
        else:
            print(f"Global car took {amount} damage from {reason}. Points left: {points_left}")

    def _apply_click_damage(self, p, reason):
        if not (p.piece and p.piece.active):
            return False

        if getattr(p.piece, 'click_hits_remaining', 1) > 1:
            p.piece.click_hits_remaining -= 1
            self.sound.play_attack()
            print(
                f"Bullet {p.id} damaged by {reason}. "
                f"{p.piece.click_hits_remaining} click left."
            )
            return False

        self._destroy_player_piece(p, reason)
        return True

    def _check_game_over(self):
        if PresidentialVehicle.global_points <= 0:
            self.state = 'GAMEOVER'
            self.game_over_timer = time.time()
            self.winner_player = None
            self.sound.play_loss()

    def _bomb_cell_next_to_officer(self, sx, sy):
        left, right, top, bottom = self._edge_loop_bounds()
        min_x = left - 1
        max_x = right + 1
        min_y = top
        max_y = bottom + 1

        if sx <= 0:
            return min_x, max(min_y, min(max_y, sy))
        if sx >= BOARD_WIDTH - 1:
            return max_x, max(min_y, min(max_y, sy))
        if sy <= 0:
            return max(min_x, min(max_x, sx)), top
        if sy >= BOARD_HEIGHT - 1:
            return max(min_x, min(max_x, sx)), bottom + 1
        return None, None

    def _spawn_bombs_for_round(self):
        self.bombs = []
        if self.round_number < BOMB_MIN_ROUND:
            return

        obstacle_cells = self._obstacle_cells()
        candidates = []
        occupied = set()
        for sx, sy in self.cop_spawn_points:
            bx, by = self._bomb_cell_next_to_officer(sx, sy)
            if bx is None:
                continue
            if (bx, by) in occupied:
                continue
            if not (0 <= bx < BOARD_WIDTH and 0 <= by < BOARD_HEIGHT):
                continue
            if (bx, by) in obstacle_cells:
                continue

            occupied.add((bx, by))
            candidates.append((bx, by))

        if not candidates:
            return

        # Ramp bomb pressure by round: round 3 starts light and increases each round.
        rounds_since_bombs = self.round_number - BOMB_MIN_ROUND
        target_bombs = BOMB_START_COUNT + (rounds_since_bombs * BOMB_ROUND_GROWTH)
        target_bombs = max(1, min(len(candidates), target_bombs))

        random.shuffle(candidates)
        for bx, by in candidates[:target_bombs]:
            self.bombs.append({
                'x': bx,
                'y': by,
                'hits_remaining': BOMB_CLICK_HITS,
            })

    def _apply_bomb_click_damage(self, bomb, reason):
        bomb['hits_remaining'] -= 1
        if bomb['hits_remaining'] > 0:
            self.sound.play_attack()
            print(
                f"Bomb at ({bomb['x']},{bomb['y']}) damaged by {reason}. "
                f"{bomb['hits_remaining']} steps left."
            )
            return False

        self.sound.play_bomb_deflect()
        print(f"Bomb at ({bomb['x']},{bomb['y']}) destroyed by {reason}.")
        self.bombs = [b for b in self.bombs if b is not bomb]
        return True

    def _check_big_cube_bomb_collision(self):
        if not self.big_cube or not self.bombs:
            return

        big_cells = set(self._big_cube_cells())
        exploded = []
        for bomb in self.bombs:
            if (bomb['x'], bomb['y']) in big_cells:
                exploded.append(bomb)

        if not exploded:
            return

        for bomb in exploded:
            print(f"Bomb at ({bomb['x']},{bomb['y']}) exploded on the car.")
            self._apply_global_damage(BOMB_CAR_DAMAGE, f"bomb ({bomb['x']},{bomb['y']})")

        self.bombs = [b for b in self.bombs if b not in exploded]

    def _determine_winner_by_hits(self):
        if not self.players:
            return None

        min_hits = min(p.hits_taken for p in self.players)
        winners = [p for p in self.players if p.hits_taken == min_hits]
        return winners[0] if len(winners) == 1 else None

    def _finish_match_by_time(self):
        if self.round_number >= self.total_rounds_to_survive:
            self.state = 'PREWIN_FLICKER'
            self.prewin_flicker_start = time.time()
            self.winner_player = None
            self.sound.play_win()
            print(f"Victory! Car survived all {self.total_rounds_to_survive} rounds.")
            return

        self.round_number += 1
        print(f"Round survived. Starting round {self.round_number}/{self.total_rounds_to_survive}.")
        self._start_round()

    def _populate_obstacles(self):
        self.current_obstacle_map = random.choice(self.obstacle_maps)
        for x, y in self.current_obstacle_map:
            # + shape: center and 4 arms
            plus_pixels = [(0, 0), (0, -1), (0, 1), (-1, 0), (1, 0)]
            for dx, dy in plus_pixels:
                nx, ny = x + dx, y + dy
                if 0 <= nx < BOARD_WIDTH and 0 <= ny < BOARD_HEIGHT:
                    self.board[ny][nx] = self.obstacle_color

    def _is_middle_zone(self, x, y):
        return 4 <= x <= 11 and 8 <= y <= 23

    def _edge_loop_bounds(self):
        # Keep the car loop one ring inward so edge props remain decorative.
        return 2, BOARD_WIDTH - 3, 2, BOARD_HEIGHT - 4

    def _is_edge_lane_center(self, center_x, center_y):
        left, right, top, bottom = self._edge_loop_bounds()
        return center_x in (left, right) or center_y in (top, bottom)

    def _edge_loop_corner_points(self):
        left, right, top, bottom = self._edge_loop_bounds()
        return {
            (left, top),
            (right, top),
            (left, bottom),
            (right, bottom),
        }

    def _edge_loop_direction_for_position(self, center_x, center_y):
        left, right, top, bottom = self._edge_loop_bounds()

        if center_y == top and center_x < right:
            return (1, 0)
        if center_x == right and center_y < bottom:
            return (0, 1)
        if center_y == bottom and center_x > left:
            return (-1, 0)
        if center_x == left and center_y > top:
            return (0, -1)

        return (1, 0)

    def _edge_loop_next_direction(self, center_x, center_y, current_direction):
        left, right, top, bottom = self._edge_loop_bounds()
        clockwise_corners = {
            (left, top): (1, 0),
            (right, top): (0, 1),
            (right, bottom): (-1, 0),
            (left, bottom): (0, -1),
        }

        if (center_x, center_y) in clockwise_corners:
            return clockwise_corners[(center_x, center_y)]

        # Keep moving straight between corners.
        expected = self._edge_loop_direction_for_position(center_x, center_y)
        if current_direction == expected:
            return current_direction
        return expected

    def _bank_positions(self):
        return [
            (0, 0),
            (BOARD_WIDTH - 1, 0),
            (0, BOARD_HEIGHT - 3),
            (BOARD_WIDTH - 1, BOARD_HEIGHT - 3),
            (0, (BOARD_HEIGHT // 2) - 1),
            (BOARD_WIDTH - 1, (BOARD_HEIGHT // 2) - 1),
        ]

    def _bank_wall_cells(self, ox, oy):
        return [
            (ox, oy + dy)
            for dy in range(3)
            if 0 <= ox < BOARD_WIDTH and 0 <= (oy + dy) < BOARD_HEIGHT
        ]

    def _bank_anchor_point(self, ox, oy):
        return ox, min(BOARD_HEIGHT - 1, oy + 1)

    def _build_cop_spawn_points(self):
        # Build small random police spawn markers on literal edges near each bank.
        points = set()
        candidates = self._cop_edge_candidates()

        for bx, by in self._bank_positions():
            ax, ay = self._bank_anchor_point(bx, by)
            local_candidates = [(ex, ey) for ex, ey in candidates if abs(ex - ax) + abs(ey - ay) <= 4]
            random.shuffle(local_candidates)
            for point in local_candidates[:2]:
                points.add(point)

        # Fallback if random filtering was too strict.
        if len(points) < 6:
            for point in candidates:
                points.add(point)
                if len(points) >= 8:
                    break

        return list(points)

    def _cop_edge_candidates(self):
        points = set()
        edge_cells = {
            (x, 0) for x in range(BOARD_WIDTH)
        } | {
            (x, BOARD_HEIGHT - 1) for x in range(BOARD_WIDTH)
        } | {
            (0, y) for y in range(BOARD_HEIGHT)
        } | {
            (BOARD_WIDTH - 1, y) for y in range(BOARD_HEIGHT)
        }

        for bx, by in self._bank_positions():
            ax, ay = self._bank_anchor_point(bx, by)
            bank_cells = set(self._bank_wall_cells(bx, by))
            for ex, ey in edge_cells:
                if (ex, ey) in bank_cells:
                    continue
                if abs(ex - ax) + abs(ey - ay) <= 4:
                    points.add((ex, ey))

        if not points:
            points.update({(0, 6), (0, 24), (BOARD_WIDTH - 1, 6), (BOARD_WIDTH - 1, 24)})

        return list(points)

    def _move_one_cop_spawn(self):
        if not self.cop_spawn_points:
            return

        candidates = [pt for pt in self._cop_edge_candidates() if pt not in self.cop_spawn_points]
        if not candidates:
            return

        move_idx = random.randrange(len(self.cop_spawn_points))
        self.cop_spawn_points[move_idx] = random.choice(candidates)

    def _edge_prop_cells(self):
        # Decorative-only visuals on map edges (no gameplay collision/hitbox).
        cells = set(self.cop_spawn_points)
        for bx, by in self._bank_positions():
            cells.update(self._bank_wall_cells(bx, by))
        return cells

    def _recovery_side_direction(self):
        mid_x = (BOARD_WIDTH - 1) / 2.0
        return -1 if self.big_cube['x'] <= mid_x else 1

    def _generate_middle_obstacles(self, count, min_distance=4):
        obstacles = []
        attempts = 0
        max_attempts = count * 80

        while len(obstacles) < count and attempts < max_attempts:
            x = random.randint(4, 11)
            y = random.randint(8, 23)

            is_valid = True
            for ox, oy in obstacles:
                distance = abs(x - ox) + abs(y - oy)
                if distance < min_distance:
                    is_valid = False
                    break

            if is_valid:
                obstacles.append((x, y))

            attempts += 1

        return obstacles

    def _expand_obstacle_cells(self, obstacle_centers):
        cells = set()
        for x, y in obstacle_centers:
            for dx, dy in [(0, 0), (0, -1), (0, 1), (-1, 0), (1, 0)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < BOARD_WIDTH and 0 <= ny < BOARD_HEIGHT:
                    cells.add((nx, ny))
        return cells

    def _is_playable_map(self, obstacle_centers):
        if any(not self._is_middle_zone(x, y) for x, y in obstacle_centers):
            return False

        obstacle_cells = self._expand_obstacle_cells(obstacle_centers)
        all_cells = {(x, y) for y in range(BOARD_HEIGHT) for x in range(BOARD_WIDTH)}
        free_cells = all_cells - obstacle_cells

        # Keep maps open enough for both the big car and bullets.
        if len(free_cells) < int(BOARD_WIDTH * BOARD_HEIGHT * 0.45):
            return False

        if not free_cells:
            return False

        # Every free cell should connect to the same navigable region.
        start = next(iter(free_cells))
        queue = deque([start])
        seen = {start}
        while queue:
            cx, cy = queue.popleft()
            for nx, ny in [(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)]:
                if (nx, ny) in free_cells and (nx, ny) not in seen:
                    seen.add((nx, ny))
                    queue.append((nx, ny))

        if len(seen) != len(free_cells):
            return False

        # Avoid isolated pockets where bullets can dead-end visually.
        for cell_x, cell_y in free_cells:
            neighbors = 0
            for nx, ny in [(cell_x + 1, cell_y), (cell_x - 1, cell_y), (cell_x, cell_y + 1), (cell_x, cell_y - 1)]:
                if (nx, ny) in free_cells:
                    neighbors += 1
            if neighbors == 0:
                return False

        # Validate that big-car center positions form one connected region too.
        big_positions = set()
        for center_y in range(BOARD_HEIGHT - 1):
            for center_x in range(1, BOARD_WIDTH - 1):
                can_place = True
                for cell_x, cell_y in self._big_cube_cells(center_x, center_y):
                    if (cell_x, cell_y) in obstacle_cells:
                        can_place = False
                        break
                if can_place and self._is_edge_lane_center(center_x, center_y):
                    big_positions.add((center_x, center_y))

        if len(big_positions) < 24:
            return False

        start_big = next(iter(big_positions))
        queue = deque([start_big])
        seen_big = {start_big}
        while queue:
            cx, cy = queue.popleft()
            for nx, ny in [(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)]:
                if (nx, ny) in big_positions and (nx, ny) not in seen_big:
                    seen_big.add((nx, ny))
                    queue.append((nx, ny))

        return len(seen_big) == len(big_positions)

    def _build_playable_maps(self, candidate_maps, desired_count=10):
        playable = []
        seen_signatures = set()

        for cmap in candidate_maps:
            signature = tuple(sorted(cmap))
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            if self._is_playable_map(cmap):
                playable.append(cmap)

        attempts = 0
        while len(playable) < desired_count and attempts < 200:
            attempts += 1
            generated = self._generate_middle_obstacles(random.randint(6, 9), min_distance=5)
            signature = tuple(sorted(generated))
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            if self._is_playable_map(generated):
                playable.append(generated)

        if not playable:
            # Guaranteed fallback map.
            playable.append([(6, 12), (9, 12), (7, 16), (8, 20)])

        return playable

    def _would_hit_big_cube(self, blocks, dx=0, dy=0):
        if not self.big_cube:
            return False
        big_cube_cells = set(self._big_cube_cells())
        return any((bx + dx, by + dy) in big_cube_cells for bx, by in blocks)

    def _attempt_unstick_player(self, p):
        if not (p.piece and p.piece.active):
            return False

        for _ in range(6):
            new_dx = random.choice([-1, 1])
            new_dy = random.choice([-1, 1])
            moved = False

            blocks_now = p.piece.get_absolute_blocks()
            if not self._would_hit_big_cube(blocks_now, dy=new_dy) and not self.is_collision(p.piece, dy=new_dy):
                p.piece.y += new_dy
                moved = True

            blocks_now = p.piece.get_absolute_blocks()
            if not self._would_hit_big_cube(blocks_now, dx=new_dx) and not self.is_collision(p.piece, dx=new_dx):
                p.piece.x += new_dx
                moved = True

            p.directionX = new_dx
            p.directionY = new_dy

            if moved:
                p.last_progress_time = time.time()
                return True

        # Teleport fallback avoids visual infinite loops in narrow corridors.
        spawn_x, spawn_y = self._find_safe_spawn(include_dynamic=True)
        p.piece.x = spawn_x
        p.piece.y = spawn_y
        p.directionX = random.choice([-1, 1])
        p.directionY = random.choice([-1, 1])
        p.last_progress_time = time.time()
        return True

    def _start_round(self):
        self.reset_board()
        PresidentialVehicle.reset_global_points(self.starting_points)

        self.apply_color_scheme()
        self._populate_obstacles()
        self.cop_spawn_points = self._build_cop_spawn_points()
        self._spawn_bombs_for_round()
        self.last_cop_move_time = time.time()

        # Reset visuals and player pieces for the next timed round.
        self.trail = [[0.0 for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]
        self.trail_color = [[BLACK for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]
        for p in self.players:
            p.piece = None
            p.respawn_time = 0

        # Spawn big car on edge lane.
        bx, by = self._find_safe_edge_spawn()
        self.big_cube = {'x': bx, 'y': by, 'color': WHITE}
        self.big_cube_last_progress = time.time()
        self.big_cube_direction = self._edge_loop_direction_for_position(bx, by)
        self.big_cube_last_move = time.time()
        self.big_cube_last_turn = time.time()
        self.big_cube_recovering = False
        self.big_cube_recover_forward = self.big_cube_direction
        self.big_cube_recover_side_dx = self._recovery_side_direction()

        self.round_start_time = time.time()
        self.state = 'PREFIGHT_FLICKER'
        self.prefight_flicker_start = time.time()
        self.countdown_start_time = 0
        self.last_countdown_value = -1
        self.flashing_lines = []
        self.sound.play_ambient()

    def setup_players(self, count):
        self.players = []
        if count < 1: count = 1

        # Default bullet type is red. Rare bullets override their color on spawn.
        bullet_color = BULLET_NORMAL_COLOR
        width = 16 // count
        for i in range(count):
            start = i * width
            end = start + width - 1
            if i == count - 1: end = 15

            p = Player(i, bullet_color, start, end)
            p.game = self  # Give player access to game for safe spawn
            self.players.append(p)

    def start_game(self, num_players):
        with self.lock:
            self.setup_players(num_players)
            self.current_color_scheme = self.color_schemes[(self.round_number - 1) % len(self.color_schemes)]
            self.prev_color_scheme = self.current_color_scheme
            self.color_transition_active = False
            self.countdown_seconds = 3
            self._start_round()

    def restart_round(self):
        with self.lock:
            count = len(self.players)
            self.start_game(count)

    def spawn_all(self):
        for p in self.players:
            p.spawn_piece()

    def _spawn_next(self):
        while self.next_spawn_index < len(self.players):
            p = self.players[self.next_spawn_index]
            self.next_spawn_index += 1

            if PresidentialVehicle.global_points <= 0:
                continue

            p.spawn_piece()
            self.sound.play_spawn()
            if self.big_cube:
                dx = self.big_cube['x'] - p.piece.x
                dy = self.big_cube['y'] - p.piece.y
                p.directionX = 1 if dx >= 0 else -1
                p.directionY = 1 if dy >= 0 else -1
            p.last_progress_time = time.time()
            break

    def process_inputs(self):
        """Check button presses (channel 7) and delete cubes at the pressed column."""
        for i in range(64):
            is_pressed = self.button_states[i]
            was_pressed = self.prev_button_states[i]

            if is_pressed and not was_pressed:  # Fresh press only
                # Map button LED index to column X (same serpentine mapping as set_led)
                row_in_channel = i // 16
                col_raw = i % 16
                x = col_raw if (row_in_channel % 2 == 0) else (15 - col_raw)

                # Find and delete any cube at this column
                hit_registered = False
                for bomb in list(self.bombs):
                    if bomb['x'] == x:
                        self._apply_bomb_click_damage(bomb, f"column {x}")
                        hit_registered = True
                        break

                if hit_registered:
                    self.prev_button_states[i] = is_pressed
                    continue

                for p in self.players:
                    if p.piece and p.piece.active:
                        for bx, by in p.piece.get_absolute_blocks():
                            if bx == x:
                                self._apply_click_damage(p, f"column {x}")
                                hit_registered = True
                                break
                        if hit_registered:
                            break  # Already handled one hit, stop checking

            self.prev_button_states[i] = is_pressed

    def update_speed(self):
        elapsed = time.time() - self.game_start_time
        # Reduce fall time by 0.05s every 10 seconds (0.6 -> 0.1 over ~100s)
        reduction = (elapsed // 10) * 0.05
        self.current_fall_speed = max(self.min_fall_speed, self.base_fall_speed - reduction)

    def _obstacle_cells(self):
        cells = set()
        for ox, oy in self.current_obstacle_map:
            for dx, dy in [(0, 0), (0, -1), (0, 1), (-1, 0), (1, 0)]:
                nx, ny = ox + dx, oy + dy
                if 0 <= nx < BOARD_WIDTH and 0 <= ny < BOARD_HEIGHT:
                    cells.add((nx, ny))
        return cells

    def _big_cube_cells(self, center_x=None, center_y=None):
        if center_x is None or center_y is None:
            if not self.big_cube:
                return []
            center_x = self.big_cube['x']
            center_y = self.big_cube['y']
        return [
            (center_x - 1, center_y),
            (center_x, center_y),
            (center_x + 1, center_y),
            (center_x - 1, center_y + 1),
            (center_x, center_y + 1),
            (center_x + 1, center_y + 1),
        ]

    def _can_place_big_cube(self, center_x, center_y, enforce_edge_lane=True):
        if enforce_edge_lane and not self._is_edge_lane_center(center_x, center_y):
            return False

        obstacle_cells = self._obstacle_cells()
        edge_props = self._edge_prop_cells()
        for cell_x, cell_y in self._big_cube_cells(center_x, center_y):
            # Prevent big cube from entering reserved rows 0-1 (health bar and timer)
            if cell_x < 0 or cell_x >= BOARD_WIDTH or cell_y < 2 or cell_y >= BOARD_HEIGHT:
                return False
            if (cell_x, cell_y) in edge_props:
                # Cops/banks are decorative only, never blocking.
                continue
            if (cell_x, cell_y) in obstacle_cells:
                return False
        return True

    def is_collision(self, piece, player=None, dx=0, dy=0, absolute_blocks=None):
        blocks = absolute_blocks if absolute_blocks else piece.get_absolute_blocks()
        edge_props = self._edge_prop_cells()
        for bx, by in blocks:
            nx, ny = bx + dx, by + dy
            # Wall collision (including reserved rows 0-1 for health bar and timer)
            if nx < 0 or nx >= BOARD_WIDTH or ny >= BOARD_HEIGHT or ny < 2:
                return True

            # Decorative edge props (banks/cops) should never collide.
            if (nx, ny) in edge_props:
                continue

            # Locked Board collision
            if self.board[ny][nx] != BLACK:
                return True

            # Other Active Pieces Collision
            for other in self.players:
                if other.piece and other.piece.active and other.piece != piece:
                    for obx, oby in other.piece.get_absolute_blocks():
                        if nx == obx and ny == oby:
                            return True
            # Big car collision
            if self.big_cube:
                for cx, cy in self._big_cube_cells():
                    if nx == cx and ny == cy:
                        return True
        return False

    def tick(self):
        with self.lock:
            if self.state == 'LOBBY':
                while self.board_touch_queue:
                    x, y = self.board_touch_queue.popleft()
                    self._lobby_handle_click(x, y)
                    if self.state != 'LOBBY':
                        break  # game was just started
                return

            if self.state == 'GAMEOVER':
                return

            if self.state == 'WIN':
                return

            if self.state == 'PREWIN_FLICKER':
                elapsed = time.time() - self.prewin_flicker_start
                flicker_total = self.prewin_flicker_interval * self.prewin_flicker_toggles
                if elapsed >= flicker_total:
                    self.state = 'WIN'
                    self.game_over_timer = time.time()
                return

            if self.state == 'PREFIGHT_FLICKER':
                elapsed = time.time() - self.prefight_flicker_start
                flicker_total = self.prefight_flicker_interval * self.prefight_flicker_toggles
                if elapsed >= flicker_total:
                    self.state = 'COUNTDOWN'
                    self.countdown_start_time = time.time()
                    self.last_countdown_value = self.countdown_seconds
                    self.sound.play_countdown_tick()
                return

            if self.state == 'COUNTDOWN':
                now = time.time()
                elapsed = int(now - self.countdown_start_time)
                remaining = self.countdown_seconds - elapsed
                if remaining != self.last_countdown_value and remaining > 0:
                    self.last_countdown_value = remaining
                    self.sound.play_countdown_tick()
                if elapsed >= self.countdown_seconds:
                    print("FIGHT! Transition effect...")
                    self.state = 'TRANSITION'
                    self.transition_start_time = time.time()
                    self.transition_duration = 1.5
                return

            if self.state == 'TRANSITION':
                now = time.time()
                elapsed = now - self.transition_start_time
                # Add a small pause after the animation before PLAYING
                total_transition = self.transition_duration + 0.7
                if elapsed >= total_transition:
                    self.state = 'PREPLAY_FLICKER'
                    self.preplay_flicker_start = time.time()
                return

            if self.state == 'PREPLAY_FLICKER':
                elapsed = time.time() - self.preplay_flicker_start
                flicker_total = self.preplay_flicker_interval * self.preplay_flicker_toggles
                if elapsed >= flicker_total:
                    self.state = 'PLAYING'
                    self.game_start_time = time.time()
                    self.last_tick = time.time()
                    self.next_spawn_index = 0
                    self.last_spawn_time = time.time()
                    self._spawn_next()
                return

            # --- PLAYING STATE ---
            now = time.time()
            if now - self.last_cop_move_time >= self.cop_move_interval:
                self._move_one_cop_spawn()
                self.last_cop_move_time = now

            # Round timer logic must be here!
            if self.round_start_time is not None and self.round_duration_minutes > 0:
                elapsed = time.time() - self.round_start_time
                if elapsed >= self.round_duration_minutes * 60:
                    self._finish_match_by_time()
                    return

            # Sequential spawning
            if self.next_spawn_index < len(self.players):
                now_spawn = time.time()
                if now_spawn - self.last_spawn_time >= self.spawn_interval:
                    self._spawn_next()
                    self.last_spawn_time = now_spawn

            # Check for respawns
            now_respawn = time.time()
            for p in self.players:
                if PresidentialVehicle.global_points > 0 and p.respawn_time > 0 and now_respawn >= p.respawn_time:
                    p.respawn_time = 0
                    p.spawn_piece()
                    self.sound.play_spawn()
                    if self.big_cube:
                        dx = self.big_cube['x'] - p.piece.x
                        dy = self.big_cube['y'] - p.piece.y
                        p.directionX = 1 if dx >= 0 else -1
                        p.directionY = 1 if dy >= 0 else -1
                    p.last_progress_time = time.time()
                    print(f"Bullet {p.id} respawned!")

            # Check for clicks on active cubes via button inputs (channel 7)
            self.process_inputs()

            # Handle queued immediate board hits from recv loop
            self.process_board_touch_queue()

            # Bombs are static hazards on the car path from round 3 onward.
            self._check_big_cube_bomb_collision()

            # Big cube movement
            now = time.time()
            if now - self.big_cube_last_move >= self.big_cube_speed:
                moved = False
                if self.big_cube_recovering:
                    fdx, fdy = self.big_cube_recover_forward
                    self.big_cube_direction = (fdx, fdy)
                    fx = self.big_cube['x'] + fdx
                    fy = self.big_cube['y'] + fdy

                    if self._can_place_big_cube(fx, fy):
                        # Forward opened again: return to normal perimeter loop.
                        self.big_cube['x'] = fx
                        self.big_cube['y'] = fy
                        moved = True
                        self.big_cube_recovering = False
                    else:
                        lx = self.big_cube['x'] + self.big_cube_recover_side_dx
                        ly = self.big_cube['y']
                        if self._can_place_big_cube(lx, ly, enforce_edge_lane=False):
                            self.big_cube['x'] = lx
                            self.big_cube['y'] = ly
                            moved = True
                else:
                    dx, dy = self._edge_loop_next_direction(
                        self.big_cube['x'],
                        self.big_cube['y'],
                        self.big_cube_direction,
                    )
                    self.big_cube_direction = (dx, dy)
                    nx = self.big_cube['x'] + dx
                    ny = self.big_cube['y'] + dy
                    if self._can_place_big_cube(nx, ny):
                        self.big_cube['x'] = nx
                        self.big_cube['y'] = ny
                        moved = True
                    else:
                        # Enter recovery mode: strafe by map side until forward opens again.
                        self.big_cube_recovering = True
                        self.big_cube_recover_forward = (dx, dy)
                        self.big_cube_recover_side_dx = self._recovery_side_direction()
                        lx = self.big_cube['x'] + self.big_cube_recover_side_dx
                        ly = self.big_cube['y']
                        if self._can_place_big_cube(lx, ly, enforce_edge_lane=False):
                            self.big_cube['x'] = lx
                            self.big_cube['y'] = ly
                            moved = True
                            self.big_cube_direction = (dx, dy)

                if moved:
                    self.big_cube_last_progress = now
                elif now - self.big_cube_last_progress >= self.big_cube_stuck_timeout:
                    # If the car is blocked for too long, respawn it to a safe location.
                    old_pos = (self.big_cube['x'], self.big_cube['y'])
                    new_pos = old_pos
                    for _ in range(10):
                        candidate = self._find_safe_edge_spawn()
                        if candidate != old_pos:
                            new_pos = candidate
                            break
                    self.big_cube['x'], self.big_cube['y'] = new_pos
                    self.big_cube_direction = self._edge_loop_direction_for_position(
                        self.big_cube['x'], self.big_cube['y']
                    )
                    self.big_cube_recovering = False
                    self.big_cube_recover_forward = self.big_cube_direction
                    self.big_cube_recover_side_dx = self._recovery_side_direction()
                    self.big_cube_last_progress = now
                    self.big_cube_last_turn = now

                self.big_cube_last_move = now

            if self.flashing_lines:
                if time.time() - self.flash_start_time > self.flash_duration:
                    self.process_cleared_lines()
                return

            self.update_speed()
            now = time.time()
            elapsed = now - self.last_tick
            
            # Cap maximum frames per tick to prevent burst-after-lag behavior
            # but allow graceful catch-up over time
            if elapsed >= self.current_fall_speed:
                frames_owed = int(elapsed / self.current_fall_speed)
                frames_to_execute = min(frames_owed, 3)  # Execute max 3 frames per tick
                
                for _ in range(frames_to_execute):
                    for p in self.players:
                        if p.piece and p.piece.active:
                            piece_moved = False
                            # --- Y axis movement ---
                            dy = p.directionY
                            collision_with_big = self._would_hit_big_cube(p.piece.get_absolute_blocks(), dy=dy)
                            if not collision_with_big and not self.is_collision(p.piece, player=p, dy=dy):
                                p.piece.y += dy
                                piece_moved = True
                            else:
                                if collision_with_big:
                                    self._handle_player_hit(p, "big cube")
                                else:
                                    # Reverse Y direction and try again
                                    p.directionY = -p.directionY
                                    dy = p.directionY
                                    if not self.is_collision(p.piece, player=p, dy=dy):
                                        p.piece.y += dy
                                        piece_moved = True

                            if not p.piece or not p.piece.active:
                                continue

                            # --- X axis movement ---
                            dx = p.directionX
                            collision_with_big = self._would_hit_big_cube(p.piece.get_absolute_blocks(), dx=dx)
                            if not collision_with_big and not self.is_collision(p.piece, player=p, dx=dx):
                                p.piece.x += dx
                                piece_moved = True
                            else:
                                if collision_with_big:
                                    self._handle_player_hit(p, "big cube")
                                else:
                                    # Reverse X direction and try again
                                    p.directionX = -p.directionX
                                    dx = p.directionX
                                    if not self.is_collision(p.piece, player=p, dx=dx):
                                        p.piece.x += dx
                                        piece_moved = True

                            if p.piece and p.piece.active:
                                if piece_moved:
                                    p.last_progress_time = time.time()
                                elif time.time() - p.last_progress_time >= self.player_stuck_timeout:
                                    self._attempt_unstick_player(p)
                            
                            # Update trail for this piece
                            if p.piece and p.piece.active:
                                for bx, by in p.piece.get_absolute_blocks():
                                    if 0 <= bx < BOARD_WIDTH and 0 <= by < BOARD_HEIGHT:
                                        self.trail[by][bx] = 1.0
                                        self.trail_color[by][bx] = p.piece.color
                
                self.last_tick += frames_to_execute * self.current_fall_speed

    def reset_board(self):
        self.board = [[BLACK for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]

    def handle_board_click(self, x, y):
        # Immediate hit detection for board touches.
        # Allow a small hit window to reduce timing/prediction reliance.
        for p in self.players:
            if not (p.piece and p.piece.active):
                continue

            piece_blocks = p.piece.get_absolute_blocks()
            # Primary hit: exact cell
            if (x, y) in piece_blocks:
                hit = True
            else:
                # Secondary hit: current velocity prediction and adjacent cells
                predicted = (p.piece.x + p.directionX, p.piece.y + p.directionY)
                hit = (x, y) == predicted
                if not hit:
                    for bx, by in piece_blocks:
                        if abs(bx - x) <= 1 and abs(by - y) <= 1:
                            hit = True
                            break

            if hit:
                self._apply_click_damage(p, f"touch ({x},{y})")
                return True

        for bomb in list(self.bombs):
            if bomb['x'] == x and bomb['y'] == y:
                self._apply_bomb_click_damage(bomb, f"touch ({x},{y})")
                return True

        return False

    def _lobby_handle_click(self, x, y):
        """Handle a board tap in LOBBY to select difficulty and start game."""
        for btn_key, btn_def in LOBBY_BUTTONS.items():
            x_min, x_max = btn_def['x_range']
            y_min, y_max = btn_def['y_range']
            if x_min <= x <= x_max and y_min <= y <= y_max:
                difficulty_key = btn_def['difficulty']
                diff = DIFFICULTY_PRESETS[difficulty_key]
                print(f"[Lobby] {btn_key} button selected: {difficulty_key}")
                self.round_duration_minutes = diff['mins']
                self.round_number = 1
                self.total_rounds_to_survive = diff['rounds']
                self.base_fall_speed = diff['fall_speed']
                self.current_fall_speed = self.base_fall_speed
                self.start_game(diff['num_players'])
                return

    def process_board_touch_queue(self):
        while self.board_touch_queue:
            x, y = self.board_touch_queue.popleft()
            self.handle_board_click(x, y)

    def draw_glyph(self, buffer, key, ox, oy, color):
        if key not in FONT: return
        for dx, dy in FONT[key]:
            self.set_led(buffer, ox + dx, oy + dy, color)

    def draw_word(self, buffer, text, ox, oy, color, spacing=1):
        cursor_x = ox
        for ch in text:
            glyph = FONT.get(ch)
            if glyph:
                self.draw_glyph(buffer, ch, cursor_x, oy, color)
                max_x = max(dx for dx, _ in glyph)
                glyph_width = max_x + 1
                cursor_x += glyph_width + spacing
            else:
                cursor_x += 3 + spacing

    def _text_points(self, text, spacing=1, space_width=2):
        points = []
        cursor_x = 0
        for ch in text:
            if ch == ' ':
                cursor_x += space_width
                continue

            glyph = FONT.get(ch)
            if not glyph:
                cursor_x += 3 + spacing
                continue

            for dx, dy in glyph:
                points.append((cursor_x + dx, dy))

            max_x = max(dx for dx, _ in glyph)
            glyph_width = max_x + 1
            cursor_x += glyph_width + spacing

        width = max((x for x, _ in points), default=-1) + 1
        height = max((y for _, y in points), default=-1) + 1
        return points, width, height

    def draw_text_rotated_right(self, buffer, text, ox, oy, color, spacing=1, space_width=2):
        points, _, height = self._text_points(text, spacing=spacing, space_width=space_width)
        # 90-degree clockwise rotation: (x, y) -> (height - 1 - y, x)
        for x, y in points:
            rx = height - 1 - y
            ry = x
            self.set_led(buffer, ox + rx, oy + ry, color)

    def _draw_bank_sprite(self, buffer, ox, oy, pulse=1.0):
        pulse = max(0.0, min(1.0, pulse))

        # Minimal bank marker: 1-block-thick beige wall segment on the edge.
        wall = (
            int(168 + 30 * pulse),
            int(150 + 24 * pulse),
            int(102 + 16 * pulse),
        )

        for wx, wy in self._bank_wall_cells(ox, oy):
            self.set_led(buffer, wx, wy, wall)

    def render(self):
        buffer = bytearray(FRAME_DATA_LENGTH)

        # Use current color scheme
        scheme = self._get_active_color_scheme()
        obstacle_color = scheme['obstacle']
        bullet_color = BULLET_NORMAL_COLOR

        if self.state == 'LOBBY':
            # Animated lobby backdrop: layered waves + moving scanline + sparkles.
            t = time.time() - self.lobby_anim_start
            scan_y = int((t * 8.0) % BOARD_HEIGHT)

            deep_blue = (6, 18, 56)
            electric_cyan = (0, 210, 255)
            warm_orange = (255, 110, 20)

            for y in range(BOARD_HEIGHT):
                for x in range(BOARD_WIDTH):
                    wave_a = 0.5 + 0.5 * math.sin((x * 0.55 + y * 0.35) - t * 2.8)
                    wave_b = 0.5 + 0.5 * math.sin((x * 0.22 - y * 0.62) + t * 2.1)
                    blend = 0.68 * wave_a + 0.32 * wave_b
                    blend = max(0.0, min(1.0, blend))

                    # Base mix from deep blue to cyan.
                    r = int(deep_blue[0] + (electric_cyan[0] - deep_blue[0]) * blend)
                    g = int(deep_blue[1] + (electric_cyan[1] - deep_blue[1]) * blend)
                    b = int(deep_blue[2] + (electric_cyan[2] - deep_blue[2]) * blend)

                    # Add warm accents on wave peaks for a neon look.
                    accent = max(0.0, wave_a - 0.72) / 0.28
                    if accent > 0:
                        r = min(255, int(r + warm_orange[0] * 0.38 * accent))
                        g = min(255, int(g + warm_orange[1] * 0.24 * accent))
                        b = min(255, int(b + warm_orange[2] * 0.10 * accent))

                    # Moving scanline pulse.
                    dist = abs(y - scan_y)
                    if dist <= 1:
                        boost = 0.45 if dist == 0 else 0.22
                        r = min(255, int(r * (1.0 + boost)))
                        g = min(255, int(g * (1.0 + boost)))
                        b = min(255, int(b * (1.0 + boost)))

                    # Sparse sparkle points for additional motion detail.
                    sparkle = ((x * 17 + y * 29 + int(t * 14)) % 47 == 0)
                    if sparkle:
                        r = min(255, r + 50)
                        g = min(255, g + 50)
                        b = min(255, b + 50)

                    self.set_led(buffer, x, y, (r, g, b))

            # --- Render lobby difficulty buttons ---
            pulse = 0.72 + 0.28 * math.sin(t * 3.5)
            for btn_key, btn_def in LOBBY_BUTTONS.items():
                x_min, x_max = btn_def['x_range']
                y_min, y_max = btn_def['y_range']
                bg_color = btn_def['bg'](pulse)
                border_color = btn_def['border'](pulse)
                text_color = btn_def['text']
                
                # Fill button area
                for bx in range(x_min, x_max + 1):
                    for by in range(y_min, y_max + 1):
                        self.set_led(buffer, bx, by, bg_color)
                
                # Draw border (1-pixel frame)
                for bx in range(x_min, x_max + 1):
                    self.set_led(buffer, bx, y_min, border_color)
                    self.set_led(buffer, bx, y_max, border_color)
                for by in range(y_min, y_max + 1):
                    self.set_led(buffer, x_min, by, border_color)
                    self.set_led(buffer, x_max, by, border_color)
                
                # Draw centered rotated letter
                letter_x = x_min + 1
                letter_y = y_min + 1
                self.draw_text_rotated_right(buffer, btn_key, letter_x, letter_y, text_color)

            return buffer

        if self.state == 'COUNTDOWN':
            now = time.time()
            elapsed = int(now - self.countdown_start_time)
            remaining = self.countdown_seconds - elapsed
            if remaining > 0:
                glyph = FONT.get(remaining, [])
                if glyph:
                    min_x = min(dx for dx, _ in glyph)
                    max_x = max(dx for dx, _ in glyph)
                    min_y = min(dy for _, dy in glyph)
                    max_y = max(dy for _, dy in glyph)
                    glyph_width = max_x - min_x + 1
                    glyph_height = max_y - min_y + 1
                    origin_x = (BOARD_WIDTH - glyph_width) // 2 - min_x
                    origin_y = (BOARD_HEIGHT - glyph_height) // 2 - min_y
                    self.draw_glyph(buffer, remaining, origin_x, origin_y, WHITE)
            return buffer

        if self.state == 'PREFIGHT_FLICKER':
            elapsed = time.time() - self.prefight_flicker_start
            step = int(elapsed / self.prefight_flicker_interval)
            flicker_on = (step % 2 == 0)
            flicker_color = WHITE if flicker_on else BLACK
            for y in range(BOARD_HEIGHT):
                for x in range(BOARD_WIDTH):
                    self.set_led(buffer, x, y, flicker_color)
            return buffer

        if self.state == 'PREPLAY_FLICKER':
            elapsed = time.time() - self.preplay_flicker_start
            step = int(elapsed / self.preplay_flicker_interval)
            flicker_on = (step % 2 == 0)
            flicker_color = WHITE if flicker_on else BLACK
            for y in range(BOARD_HEIGHT):
                for x in range(BOARD_WIDTH):
                    self.set_led(buffer, x, y, flicker_color)
            return buffer

        if self.state == 'PREWIN_FLICKER':
            elapsed = time.time() - self.prewin_flicker_start
            step = int(elapsed / self.prewin_flicker_interval)
            flicker_on = (step % 2 == 0)
            flicker_color = WHITE if flicker_on else BLACK
            for y in range(BOARD_HEIGHT):
                for x in range(BOARD_WIDTH):
                    self.set_led(buffer, x, y, flicker_color)
            return buffer

        if self.state == 'TRANSITION':
            now = time.time()
            elapsed = now - self.transition_start_time
            duration = max(0.001, self.transition_duration)
            progress = max(0.0, min(1.0, elapsed / duration))

            # Cinematic 3-phase transition:
            # 1) side energy converges to center,
            # 2) diagonal neon wipe,
            # 3) short flash decay.
            if progress < 0.4:
                phase = progress / 0.4
                center_x = (BOARD_WIDTH - 1) / 2.0
                edge_band = int(((1.0 - phase) * (BOARD_WIDTH / 2.0)) + 0.5)

                for y in range(BOARD_HEIGHT):
                    for x in range(BOARD_WIDTH):
                        dist_center = abs(x - center_x)
                        if dist_center >= edge_band:
                            lane = 0.5 + 0.5 * math.sin((y * 0.65) - phase * 9.0)
                            glow = 0.55 + 0.45 * lane
                            r = int(20 + 130 * glow)
                            g = int(90 + 130 * glow)
                            b = int(180 + 75 * glow)
                            self.set_led(buffer, x, y, (r, g, b))
                        else:
                            # Dim center tunnel before impact.
                            dim = int(12 + 22 * (1.0 - phase))
                            self.set_led(buffer, x, y, (dim, dim, dim))

            elif progress < 0.85:
                phase = (progress - 0.4) / 0.45
                diag_limit = int(phase * (BOARD_WIDTH + BOARD_HEIGHT - 2))
                scan_y = int((phase * 1.2) * (BOARD_HEIGHT - 1))

                for y in range(BOARD_HEIGHT):
                    for x in range(BOARD_WIDTH):
                        if (x + y) <= diag_limit:
                            mix = (x + y) / float(BOARD_WIDTH + BOARD_HEIGHT - 2)
                            # Magenta -> cyan gradient with bright scanline.
                            r = int(255 * (1.0 - mix) + 20 * mix)
                            g = int(30 * (1.0 - mix) + 220 * mix)
                            b = int(255 * (1.0 - mix) + 240 * mix)

                            if abs(y - scan_y) <= 1:
                                r = min(255, int(r * 1.18))
                                g = min(255, int(g * 1.18))
                                b = min(255, int(b * 1.18))
                            self.set_led(buffer, x, y, (r, g, b))
                        else:
                            # Deep space-like background behind wipe.
                            self.set_led(buffer, x, y, (6, 8, 20))

            else:
                phase = (progress - 0.85) / 0.15
                decay = max(0.0, 1.0 - phase)
                # Flash decays from white to black right before gameplay.
                v = int(255 * decay)
                for y in range(BOARD_HEIGHT):
                    for x in range(BOARD_WIDTH):
                        self.set_led(buffer, x, y, (v, v, v))

            return buffer

        if self.state == 'GAMEOVER':
            elapsed = time.time() - self.game_over_timer

            flash_count = 3
            flash_interval = 0.2
            flash_total = flash_count * 2 * flash_interval

            if elapsed < flash_total:
                blink_on = (int(elapsed / flash_interval) % 2 == 0)
                flash_color = RED if blink_on else BLACK
                for y in range(BOARD_HEIGHT):
                    for x in range(BOARD_WIDTH):
                        self.set_led(buffer, x, y, flash_color)
            else:
                # Slide rotated GAME OVER top-to-bottom while staying horizontally centered.
                slide_elapsed = elapsed - flash_total
                message = "GAME OVER"
                repetitions = 2
                repetition_gap = 10

                _, source_w, source_h = self._text_points(message, spacing=1, space_width=2)
                # After right rotation: width'=source_h, height'=source_w
                rot_w = source_h
                rot_h = source_w

                text_rot_w = rot_w
                text_rot_h = repetitions * rot_h + (repetitions - 1) * repetition_gap

                start_y = -text_rot_h
                end_y = BOARD_HEIGHT
                slide_duration = 2.8
                t = min(1.0, slide_elapsed / slide_duration)
                y_pos = int(start_y + (end_y - start_y) * t)
                x_centered = (BOARD_WIDTH - text_rot_w) // 2

                for i in range(repetitions):
                    rep_y = y_pos + i * (rot_h + repetition_gap)
                    self.draw_text_rotated_right(buffer, message, x_centered, rep_y, RED, spacing=1, space_width=2)

            return buffer

        if self.state == 'WIN':
            elapsed = time.time() - self.game_over_timer

            # Celebratory shimmer background.
            for y in range(BOARD_HEIGHT):
                for x in range(BOARD_WIDTH):
                    wave_a = 0.5 + 0.5 * math.sin((x * 0.46 + y * 0.21) + elapsed * 2.2)
                    wave_b = 0.5 + 0.5 * math.sin((x * 0.18 - y * 0.41) - elapsed * 1.5)
                    mix = 0.6 * wave_a + 0.4 * wave_b

                    r = int(6 + 30 * mix)
                    g = int(28 + 190 * mix)
                    b = int(16 + 120 * mix)

                    sparkle = ((x * 13 + y * 19 + int(elapsed * 18)) % 31 == 0)
                    if sparkle:
                        r = min(255, r + 45)
                        g = min(255, g + 55)
                        b = min(255, b + 35)

                    self.set_led(buffer, x, y, (r, g, b))

            # Pulsing WIN text in the center, rotated 90 degrees clockwise.
            text = "WIN"
            points, _, source_h = self._text_points(text, spacing=1, space_width=2)
            _, source_w, _ = self._text_points(text, spacing=1, space_width=2)
            rot_w = source_h
            rot_h = source_w
            ox = (BOARD_WIDTH - rot_w) // 2
            oy = (BOARD_HEIGHT - rot_h) // 2

            pulse = 0.5 + 0.5 * math.sin(elapsed * 5.0)
            win_color = (
                int(120 + 110 * pulse),
                int(255),
                int(140 + 90 * pulse)
            )

            self.draw_text_rotated_right(buffer, text, ox, oy, win_color, spacing=1, space_width=2)

            # Subtle white glow around text.
            glow_alpha = 0.05 + 0.07 * (0.5 + 0.5 * math.sin(elapsed * 4.2))
            for px, py in points:
                rx = source_h - 1 - py
                ry = px
                for gx, gy in [(rx - 1, ry), (rx + 1, ry), (rx, ry - 1), (rx, ry + 1)]:
                    self.add_led(buffer, ox + gx, oy + gy, WHITE, glow_alpha)

            return buffer

        if self.state == 'PLAYING':
            with self.lock:
                t = time.time()

                # Animated background with subtle grid shimmer.
                for y in range(BOARD_HEIGHT):
                    for x in range(BOARD_WIDTH):
                        wave_a = 0.5 + 0.5 * math.sin((x * 0.34 + y * 0.11) + t * 1.35)
                        wave_b = 0.5 + 0.5 * math.sin((y * 0.48 - x * 0.17) - t * 0.95)
                        mix = 0.62 * wave_a + 0.38 * wave_b

                        r = int(4 + 18 * mix)
                        g = int(8 + 30 * mix)
                        b = int(18 + 52 * mix)

                        if (x + y) % 4 == 0:
                            r = min(255, r + 5)
                            g = min(255, g + 6)
                            b = min(255, b + 7)

                        self.set_led(buffer, x, y, (r, g, b))

                # Draw obstacles with pulse.
                for ox, oy in self.current_obstacle_map:
                    pulse = 0.62 + 0.38 * (0.5 + 0.5 * math.sin(t * 3.7 + ox * 0.31 + oy * 0.23))
                    oc = (
                        min(255, int(obstacle_color[0] * pulse)),
                        min(255, int(obstacle_color[1] * pulse)),
                        min(255, int(obstacle_color[2] * pulse))
                    )
                    plus_pixels = [(0,0), (0,-1), (0,1), (-1,0), (1,0)]
                    for dx, dy in plus_pixels:
                        nx, ny = ox + dx, oy + dy
                        if 0 <= nx < BOARD_WIDTH and 0 <= ny < BOARD_HEIGHT:
                            self.set_led(buffer, nx, ny, oc)

                # Cops-and-robbers story props: banks near the edges (inside the perimeter lane).
                bank_positions = self._bank_positions()
                for i, (bx, by) in enumerate(bank_positions):
                    bank_pulse = 0.6 + 0.4 * (0.5 + 0.5 * math.sin(t * 2.1 + i * 0.9))
                    self._draw_bank_sprite(buffer, bx, by, pulse=bank_pulse)

                # Police spawn markers: blue edge dots around the banks.
                for i, (sx, sy) in enumerate(self.cop_spawn_points):
                    pulse = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(t * 3.3 + i * 0.7))
                    cop_blue = (
                        int(20 + 30 * pulse),
                        int(70 + 90 * pulse),
                        int(170 + 80 * pulse),
                    )
                    self.set_led(buffer, sx, sy, cop_blue)

                # Static bombs on the car path (from round 3 onward).
                for bomb in self.bombs:
                    bx, by = bomb['x'], bomb['y']
                    hp = bomb.get('hits_remaining', 1)
                    if hp >= 3:
                        core = (140, 60, 255)
                    elif hp == 2:
                        core = (170, 90, 255)
                    else:
                        core = (205, 135, 255)

                    self.set_led(buffer, bx, by, core)
                    for gx, gy in [(bx - 1, by), (bx + 1, by), (bx, by - 1), (bx, by + 1)]:
                        if 0 <= gx < BOARD_WIDTH and 0 <= gy < BOARD_HEIGHT:
                            glow = (int(core[0] * 0.22), int(core[1] * 0.22), int(core[2] * 0.22))
                            self.set_led(buffer, gx, gy, glow)

                # Draw trail behind pieces.
                for y in range(BOARD_HEIGHT):
                    for x in range(BOARD_WIDTH):
                        if self.trail[y][x] > 0.02:
                            trail_intensity = self.trail[y][x]
                            trail_scale = 0.10 + 0.50 * trail_intensity
                            base_trail_color = self.trail_color[y][x] if self.trail_color[y][x] != BLACK else bullet_color
                            trail_color = (
                                int(base_trail_color[0] * trail_scale),
                                int(base_trail_color[1] * trail_scale),
                                int(base_trail_color[2] * trail_scale)
                            )
                            self.set_led(buffer, x, y, trail_color)

                # Draw player bullets with a soft glow.
                for p in self.players:
                    if p.piece and p.piece.active:
                        for bx, by in p.piece.get_absolute_blocks():
                            core_color = p.piece.color
                            for gx, gy in [(bx-1, by), (bx+1, by), (bx, by-1), (bx, by+1)]:
                                if 0 <= gx < BOARD_WIDTH and 0 <= gy < BOARD_HEIGHT:
                                    glow = (
                                        int(core_color[0] * 0.24),
                                        int(core_color[1] * 0.24),
                                        int(core_color[2] * 0.24)
                                    )
                                    self.set_led(buffer, gx, gy, glow)
                            if 0 <= bx < BOARD_WIDTH and 0 <= by < BOARD_HEIGHT:
                                self.set_led(buffer, bx, by, core_color)

                # Draw player pieces core.
                for p in self.players:
                    if p.piece and p.piece.active:
                        for bx, by in p.piece.get_absolute_blocks():
                            if 0 <= by < BOARD_HEIGHT and 0 <= bx < BOARD_WIDTH:
                                self.set_led(buffer, bx, by, p.piece.color)

                # Draw big car with highlights.
                if self.big_cube:
                    cx = self.big_cube['x']
                    cy = self.big_cube['y']

                    # Keep sprite rotation based on movement direction.
                    dir_x, dir_y = self.big_cube_direction
                    if dir_x == 0 and dir_y == 0:
                        dir_x, dir_y = 0, -1
                    side_x, side_y = dir_y, -dir_x

                    body_white = (238, 238, 245)
                    windshield_blue = (40, 160, 255)
                    headlight = (255, 230, 120)
                    wheel = (35, 35, 35)

                    # Front row: two headlights and windshield (along movement direction).
                    for px, py, color in [
                        (cx + dir_x + side_x, cy + dir_y + side_y, headlight),
                        (cx + dir_x, cy + dir_y, windshield_blue),
                        (cx + dir_x - side_x, cy + dir_y - side_y, headlight),
                    ]:
                        if 0 <= px < BOARD_WIDTH and 0 <= py < BOARD_HEIGHT:
                            self.set_led(buffer, px, py, color)

                    # Middle row: white body.
                    for px, py in [
                        (cx + side_x, cy + side_y),
                        (cx, cy),
                        (cx - side_x, cy - side_y),
                    ]:
                        if 0 <= px < BOARD_WIDTH and 0 <= py < BOARD_HEIGHT:
                            self.set_led(buffer, px, py, body_white)

                    # Rear row: two wheels and center body block.
                    for px, py, color in [
                        (cx - dir_x + side_x, cy - dir_y + side_y, wheel),
                        (cx - dir_x, cy - dir_y, body_white),
                        (cx - dir_x - side_x, cy - dir_y - side_y, wheel),
                    ]:
                        if 0 <= px < BOARD_WIDTH and 0 <= py < BOARD_HEIGHT:
                            self.set_led(buffer, px, py, color)

                # HUD: health bar on row 0, timer bar on row 1.
                if PresidentialVehicle.global_points_default > 0:
                    hp_ratio = PresidentialVehicle.global_points / float(PresidentialVehicle.global_points_default)
                else:
                    hp_ratio = 0.0
                hp_fill = int(hp_ratio * BOARD_WIDTH)
                for x in range(BOARD_WIDTH):
                    if x < hp_fill:
                        if hp_ratio > 0.6:
                            c = (40, 220, 60)
                        elif hp_ratio > 0.3:
                            c = (240, 170, 20)
                        else:
                            c = (230, 40, 40)
                    else:
                        c = (20, 12, 12)
                    self.set_led(buffer, x, 0, c)

                if self.round_start_time is not None and self.round_duration_minutes > 0:
                    total = self.round_duration_minutes * 60
                    left = max(0.0, total - (time.time() - self.round_start_time))
                    timer_ratio = left / total if total > 0 else 0.0
                    timer_fill = int(timer_ratio * BOARD_WIDTH)
                    for x in range(BOARD_WIDTH):
                        c = (30, 140, 255) if x < timer_fill else (8, 14, 24)
                        self.set_led(buffer, x, 1, c)

                # Full-grid translucent overlay animation on top of gameplay.
                overlay_base = (18, 70, 110)
                for y in range(BOARD_HEIGHT):
                    for x in range(BOARD_WIDTH):
                        wave = 0.5 + 0.5 * math.sin((x * 0.29 + y * 0.17) + t * 1.9)
                        alpha = 0.02 + 0.08 * wave
                        self.add_led(buffer, x, y, overlay_base, alpha)

                # Decay trail for next frame.
                for y in range(BOARD_HEIGHT):
                    for x in range(BOARD_WIDTH):
                        self.trail[y][x] *= self.trail_decay
                        if self.trail[y][x] < 0.02:
                            self.trail_color[y][x] = BLACK

            return buffer

    def set_led(self, buffer, x, y, color):
        if x < 0 or x >= 16: return
        channel = y // 4
        if channel >= 8: return
        row_in_channel = y % 4
        if row_in_channel % 2 == 0:
            led_index = row_in_channel * 16 + x
        else:
            led_index = row_in_channel * 16 + (15 - x)
        block_size = NUM_CHANNELS * 3
        offset = led_index * block_size + channel
        if offset + NUM_CHANNELS * 2 < len(buffer):
            buffer[offset] = color[1]  # GREEN (Swap for hardware)
            buffer[offset + NUM_CHANNELS] = color[0]  # RED (Swap for hardware)
            buffer[offset + NUM_CHANNELS * 2] = color[2]

    def add_led(self, buffer, x, y, color, alpha=1.0):
        if x < 0 or x >= 16:
            return
        channel = y // 4
        if channel >= 8:
            return

        row_in_channel = y % 4
        if row_in_channel % 2 == 0:
            led_index = row_in_channel * 16 + x
        else:
            led_index = row_in_channel * 16 + (15 - x)

        block_size = NUM_CHANNELS * 3
        offset = led_index * block_size + channel
        if offset + NUM_CHANNELS * 2 >= len(buffer):
            return

        a = max(0.0, min(1.0, alpha))
        add_r = int(color[0] * a)
        add_g = int(color[1] * a)
        add_b = int(color[2] * a)

        # Stored order in buffer is G, R, B for this hardware mapping.
        buffer[offset] = min(255, buffer[offset] + add_g)
        buffer[offset + NUM_CHANNELS] = min(255, buffer[offset + NUM_CHANNELS] + add_r)
        buffer[offset + NUM_CHANNELS * 2] = min(255, buffer[offset + NUM_CHANNELS * 2] + add_b)

    def _find_safe_spawn(self, include_dynamic=False, prefer_cop_edges=False):
        # Find a random (x, y) not in terrain
        if prefer_cop_edges and self.cop_spawn_points:
            shuffled_spawns = list(self.cop_spawn_points)
            random.shuffle(shuffled_spawns)
            for x, y in shuffled_spawns:
                is_safe = True
                for ox, oy in self.current_obstacle_map:
                    for dx, dy in [(0,0), (0,-1), (0,1), (-1,0), (1,0)]:
                        if x == ox + dx and y == oy + dy:
                            is_safe = False
                            break
                    if not is_safe:
                        break

                if is_safe and include_dynamic:
                    if self.big_cube and (x, y) in set(self._big_cube_cells()):
                        is_safe = False

                    if is_safe:
                        for player in self.players:
                            if player.piece and player.piece.active and (x, y) in set(player.piece.get_absolute_blocks()):
                                is_safe = False
                                break

                if is_safe:
                    return x, y

        attempts = 0
        while attempts < 100:
            x = random.randint(0, BOARD_WIDTH-1)
            y = random.randint(2, BOARD_HEIGHT-1)  # Avoid reserved rows 0-1
            # Check if (x, y) is not in any obstacle
            is_safe = True
            for ox, oy in self.current_obstacle_map:
                for dx, dy in [(0,0), (0,-1), (0,1), (-1,0), (1,0)]:
                    if x == ox + dx and y == oy + dy:
                        is_safe = False
                        break
                if not is_safe:
                    break
            if is_safe and include_dynamic:
                if self.big_cube and (x, y) in set(self._big_cube_cells()):
                    is_safe = False

                if is_safe:
                    for player in self.players:
                        if player.piece and player.piece.active and (x, y) in set(player.piece.get_absolute_blocks()):
                            is_safe = False
                            break
            if is_safe:
                return x, y
            attempts += 1
        # fallback: return safe position avoiding rows 0-1
        return 0, 2

    def _find_safe_edge_spawn(self):
        corners = list(self._edge_loop_corner_points())
        random.shuffle(corners)
        for x, y in corners:
            if self._can_place_big_cube(x, y):
                return x, y

        left, right, top, bottom = self._edge_loop_bounds()

        attempts = 0
        while attempts < 150:
            x = random.randint(left, right)
            y = random.randint(top, bottom)

            if not self._is_edge_lane_center(x, y):
                attempts += 1
                continue

            if not self._can_place_big_cube(x, y):
                attempts += 1
                continue

            blocked_by_player = False
            big_cells = set(self._big_cube_cells(x, y))
            for player in self.players:
                if not (player.piece and player.piece.active):
                    continue
                if any(cell in big_cells for cell in player.piece.get_absolute_blocks()):
                    blocked_by_player = True
                    break

            if not blocked_by_player:
                return x, y

            attempts += 1

        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                if self._is_edge_lane_center(x, y) and self._can_place_big_cube(x, y):
                    return x, y

        # Fallback: spawn at a safe position avoiding reserved rows 0-1
        return 1, 2


class NetworkManager:
    def __init__(self, game):
        self.game = game
        self.sock_send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_send.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock_recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_lock = threading.Lock()
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

    def update_ports(self, send_port, recv_port):
        global UDP_SEND_PORT, UDP_LISTEN_PORT

        send_port = int(send_port)
        recv_port = int(recv_port)
        if not (1 <= send_port <= 65535 and 1 <= recv_port <= 65535):
            raise ValueError("Ports must be in range 1-65535")

        # Build and bind replacement receive socket first so we never drop into an invalid state.
        new_recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        new_recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        new_recv_sock.bind(("0.0.0.0", recv_port))

        with self.sock_lock:
            old_recv_sock = self.sock_recv
            self.sock_recv = new_recv_sock

        try:
            old_recv_sock.close()
        except Exception:
            pass

        UDP_SEND_PORT = send_port
        UDP_LISTEN_PORT = recv_port

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
        except OSError:
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
        except OSError:
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
            except OSError:
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
        except OSError:
            pass

    def recv_loop(self):
        while self.running:
            try:
                with self.sock_lock:
                    recv_sock = self.sock_recv
                data, _ = recv_sock.recvfrom(2048)
                if len(data) >= 1373 and data[0] == 0x88:
                    # Read board touch data from channels 0-6 (rows 0-27)
                    for channel in range(7):
                        ch_offset = 2 + (channel * 171) + 1
                        ch_data = data[ch_offset: ch_offset + 170]
                        for led_idx in range(min(64, len(ch_data))):
                            is_pressed = (ch_data[led_idx] == 0xCC)
                            # Convert led_idx to board (x, y) using same mapping as set_led
                            row_in_channel = led_idx // 16
                            col_raw = led_idx % 16
                            if row_in_channel % 2 == 0:
                                x = col_raw
                            else:
                                x = 15 - col_raw
                            y = channel * 4 + row_in_channel
                            if 0 <= x < BOARD_WIDTH and 0 <= y < BOARD_HEIGHT:
                                # apply hits immediately on fresh board press for minimal lag
                                if is_pressed and not self.game.board_pressed[y][x]:
                                    with self.game.lock:
                                        self.game.board_touch_queue.append((x, y))
                                self.game.board_pressed[y][x] = is_pressed

                    # Read input area (channel 7) for button states
                    offset = 2 + (7 * 171) + 1
                    ch8_data = data[offset: offset + 170]
                    for led_idx, val in enumerate(ch8_data):
                        if led_idx >= 64: break
                        is_pressed = (val == 0xCC)
                        self.game.button_states[led_idx] = is_pressed

            except OSError:
                # Socket can be briefly interrupted while ports are being reconfigured.
                time.sleep(0.05)
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


class GameControlUI:
    def __init__(self, game, net):
        self.game = game
        self.net = net

        self.ui_bg = "#10151d"
        self.ui_panel = "#18212b"
        self.ui_panel_alt = "#1f2b38"
        self.ui_fg = "#e7eef7"
        self.ui_muted = "#9fb2c7"
        self.ui_accent = "#26c6da"

        self.root = tk.Tk()
        self.root.title("Protect the car Control")
        self.root.geometry("500x360")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.quit_game)
        self.root.configure(bg=self.ui_bg)

        self.players_var = tk.StringVar(value="5")
        self.minutes_var = tk.StringVar(value="2")
        self.rounds_var = tk.StringVar(value="5")
        self.fall_speed_var = tk.StringVar(value="0.40")
        self.status_var = tk.StringVar(value="Ready")
        self.settings_window = None
        self.send_port_var = tk.StringVar(value=str(UDP_SEND_PORT))
        self.recv_port_var = tk.StringVar(value=str(UDP_LISTEN_PORT))

        self._build_controls()
        self._build_stats_window()
        self._schedule_stats_update()

    def _build_controls(self):
        title = tk.Label(
            self.root,
            text="Protect the car Mission Control",
            bg=self.ui_bg,
            fg=self.ui_fg,
            font=("Segoe UI", 14, "bold"),
            anchor="w",
        )
        title.pack(fill="x", padx=12, pady=(10, 4))

        preset_frame = tk.LabelFrame(
            self.root,
            text="Difficulty",
            padx=8,
            pady=8,
            bg=self.ui_panel,
            fg=self.ui_fg,
            font=("Segoe UI", 9, "bold"),
            bd=1,
            relief="ridge",
        )
        preset_frame.pack(fill="x", padx=10, pady=(10, 6))

        tk.Button(
            preset_frame,
            text="Easy",
            width=10,
            command=lambda: self.start_preset("EASY"),
            bg="#1f8f5f",
            fg="white",
            activebackground="#28a86f",
            activeforeground="white",
            relief="flat",
        ).pack(side="left", padx=5)
        tk.Button(
            preset_frame,
            text="Normal",
            width=10,
            command=lambda: self.start_preset("NORMAL"),
            bg="#1976d2",
            fg="white",
            activebackground="#2488eb",
            activeforeground="white",
            relief="flat",
        ).pack(side="left", padx=5)
        tk.Button(
            preset_frame,
            text="Hard",
            width=10,
            command=lambda: self.start_preset("HARD"),
            bg="#b14a28",
            fg="white",
            activebackground="#c45a34",
            activeforeground="white",
            relief="flat",
        ).pack(side="left", padx=5)

        custom_frame = tk.LabelFrame(
            self.root,
            text="Custom Start",
            padx=8,
            pady=8,
            bg=self.ui_panel,
            fg=self.ui_fg,
            font=("Segoe UI", 9, "bold"),
            bd=1,
            relief="ridge",
        )
        custom_frame.pack(fill="x", padx=10, pady=6)

        label_opts = {"bg": self.ui_panel, "fg": self.ui_fg, "font": ("Segoe UI", 9, "bold")}
        entry_opts = {
            "width": 8,
            "bg": self.ui_panel_alt,
            "fg": self.ui_fg,
            "insertbackground": self.ui_fg,
            "relief": "flat",
            "highlightthickness": 1,
            "highlightbackground": "#2e3f51",
            "highlightcolor": self.ui_accent,
        }
        arrow_opts = {
            "width": 3,
            "bg": "#2b3d50",
            "fg": self.ui_fg,
            "activebackground": "#365169",
            "activeforeground": self.ui_fg,
            "relief": "flat",
        }

        tk.Label(custom_frame, text="Bullets:", **label_opts).grid(row=0, column=0, sticky="w")
        tk.Entry(custom_frame, textvariable=self.players_var, **entry_opts).grid(row=0, column=1, padx=6, pady=3, sticky="w")
        tk.Button(custom_frame, text="<", command=lambda: self._adjust_int_var(self.players_var, -1, 1), **arrow_opts).grid(row=0, column=2, padx=2)
        tk.Button(custom_frame, text=">", command=lambda: self._adjust_int_var(self.players_var, 1, 1), **arrow_opts).grid(row=0, column=3, padx=2)

        tk.Label(custom_frame, text="Minutes:", **label_opts).grid(row=1, column=0, sticky="w")
        tk.Entry(custom_frame, textvariable=self.minutes_var, **entry_opts).grid(row=1, column=1, padx=6, pady=3, sticky="w")
        tk.Button(custom_frame, text="<", command=lambda: self._adjust_int_var(self.minutes_var, -1, 1), **arrow_opts).grid(row=1, column=2, padx=2)
        tk.Button(custom_frame, text=">", command=lambda: self._adjust_int_var(self.minutes_var, 1, 1), **arrow_opts).grid(row=1, column=3, padx=2)

        tk.Label(custom_frame, text="Rounds:", **label_opts).grid(row=2, column=0, sticky="w")
        tk.Entry(custom_frame, textvariable=self.rounds_var, **entry_opts).grid(row=2, column=1, padx=6, pady=3, sticky="w")
        tk.Button(custom_frame, text="<", command=lambda: self._adjust_int_var(self.rounds_var, -1, 1), **arrow_opts).grid(row=2, column=2, padx=2)
        tk.Button(custom_frame, text=">", command=lambda: self._adjust_int_var(self.rounds_var, 1, 1), **arrow_opts).grid(row=2, column=3, padx=2)

        tk.Label(custom_frame, text="Fall speed:", **label_opts).grid(row=3, column=0, sticky="w")
        tk.Entry(custom_frame, textvariable=self.fall_speed_var, **entry_opts).grid(row=3, column=1, padx=6, pady=3, sticky="w")
        tk.Button(
            custom_frame,
            text="<",
            command=lambda: self._adjust_float_var(self.fall_speed_var, -0.05, 0.05, 2.0),
            **arrow_opts,
        ).grid(row=3, column=2, padx=2)
        tk.Button(
            custom_frame,
            text=">",
            command=lambda: self._adjust_float_var(self.fall_speed_var, 0.05, 0.05, 2.0),
            **arrow_opts,
        ).grid(row=3, column=3, padx=2)

        tk.Button(custom_frame, text="Start (Custom)", width=18, command=self.start_custom).grid(
            row=0, column=4, rowspan=2, padx=12, pady=2, sticky="n"
        )
        tk.Button(custom_frame, text="Restart", width=18, command=self.restart_round).grid(
            row=2, column=4, padx=12, pady=2, sticky="n"
        )
        tk.Button(custom_frame, text="Quit", width=18, command=self.quit_game).grid(
            row=3, column=4, padx=12, pady=2, sticky="n"
        )

        status_frame = tk.LabelFrame(
            self.root,
            text="Status",
            padx=8,
            pady=8,
            bg=self.ui_panel,
            fg=self.ui_fg,
            font=("Segoe UI", 9, "bold"),
            bd=1,
            relief="ridge",
        )
        status_frame.pack(fill="x", padx=10, pady=6)
        tk.Label(
            status_frame,
            textvariable=self.status_var,
            anchor="w",
            justify="left",
            bg=self.ui_panel,
            fg=self.ui_accent,
            font=("Segoe UI", 9, "bold"),
        ).pack(fill="x")

        hint = "Presets auto-start. Custom uses Bullets/Minutes/Rounds/Fall speed."
        tk.Label(self.root, text=hint, fg=self.ui_muted, bg=self.ui_bg).pack(fill="x", padx=12, pady=(4, 8))

        tk.Button(
            self.root,
            text="Settings",
            width=8,
            command=self._open_settings_window,
            bg="#2b3d50",
            fg=self.ui_fg,
            activebackground="#365169",
            activeforeground=self.ui_fg,
            relief="flat",
        ).place(relx=1.0, y=8, x=-8, anchor="ne")

    def _open_settings_window(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            self.settings_window.focus_force()
            return

        self.send_port_var.set(str(UDP_SEND_PORT))
        self.recv_port_var.set(str(UDP_LISTEN_PORT))

        win = tk.Toplevel(self.root)
        self.settings_window = win
        win.title("Network Settings")
        win.geometry("330x180")
        win.resizable(False, False)
        win.configure(bg=self.ui_bg)
        win.transient(self.root)

        frame = tk.LabelFrame(
            win,
            text="Ports",
            padx=10,
            pady=10,
            bg=self.ui_panel,
            fg=self.ui_fg,
            font=("Segoe UI", 9, "bold"),
            bd=1,
            relief="ridge",
        )
        frame.pack(fill="both", expand=True, padx=12, pady=10)

        label_opts = {"bg": self.ui_panel, "fg": self.ui_fg, "font": ("Segoe UI", 9, "bold")}
        entry_opts = {
            "width": 12,
            "bg": self.ui_panel_alt,
            "fg": self.ui_fg,
            "insertbackground": self.ui_fg,
            "relief": "flat",
            "highlightthickness": 1,
            "highlightbackground": "#2e3f51",
            "highlightcolor": self.ui_accent,
        }

        tk.Label(frame, text="Send Port:", **label_opts).grid(row=0, column=0, sticky="w", pady=4)
        tk.Entry(frame, textvariable=self.send_port_var, **entry_opts).grid(row=0, column=1, sticky="w", pady=4, padx=(8, 0))

        tk.Label(frame, text="Receive Port:", **label_opts).grid(row=1, column=0, sticky="w", pady=4)
        tk.Entry(frame, textvariable=self.recv_port_var, **entry_opts).grid(row=1, column=1, sticky="w", pady=4, padx=(8, 0))

        btn_row = tk.Frame(frame, bg=self.ui_panel)
        btn_row.grid(row=2, column=0, columnspan=2, sticky="e", pady=(10, 2))
        tk.Button(btn_row, text="Cancel", width=10, command=win.destroy).pack(side="right", padx=(6, 0))
        tk.Button(btn_row, text="Save", width=10, command=self._save_network_settings).pack(side="right")

    def _save_network_settings(self):
        try:
            send_port = int(self.send_port_var.get().strip())
            recv_port = int(self.recv_port_var.get().strip())
            if not (1 <= send_port <= 65535 and 1 <= recv_port <= 65535):
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid ports", "Use integers in range 1-65535.")
            return

        try:
            self.net.update_ports(send_port, recv_port)
        except Exception as exc:
            messagebox.showerror("Port update failed", f"Could not apply ports: {exc}")
            return

        CONFIG["send_port"] = send_port
        CONFIG["recv_port"] = recv_port
        _save_config(CONFIG)

        self.status_var.set(f"Ports updated: send={send_port}, recv={recv_port}")
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.destroy()

    def _adjust_int_var(self, var, delta, min_value=1, max_value=99):
        try:
            current = int(var.get().strip())
        except Exception:
            current = min_value
        next_value = max(min_value, min(max_value, current + delta))
        var.set(str(next_value))

    def _adjust_float_var(self, var, delta, min_value=0.05, max_value=2.0):
        try:
            current = float(var.get().strip())
        except Exception:
            current = min_value
        next_value = max(min_value, min(max_value, current + delta))
        var.set(f"{next_value:.2f}")

    def _build_stats_window(self):
        self.stats_window = tk.Toplevel(self.root)
        self.stats_window.title("Protect the car Live Stats")
        self.stats_window.geometry("960x640")
        self.stats_window.minsize(900, 600)
        self.stats_window.resizable(True, True)
        self.stats_window.protocol("WM_DELETE_WINDOW", self.stats_window.withdraw)
        self.stats_window.configure(bg=self.ui_bg)

        header = tk.Frame(self.stats_window, bg=self.ui_bg)
        header.pack(fill="x", padx=14, pady=(14, 6))
        tk.Label(
            header,
            text="Live Match Telemetry",
            bg=self.ui_bg,
            fg=self.ui_fg,
            font=("Segoe UI", 28, "bold"),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Real-time state, resources and pacing",
            bg=self.ui_bg,
            fg=self.ui_muted,
            font=("Segoe UI", 16),
            anchor="w",
        ).pack(anchor="w")

        grid = tk.Frame(self.stats_window, bg=self.ui_bg)
        grid.pack(fill="both", expand=True, padx=12, pady=(4, 12))

        self.stats_value_vars = {}
        self.stats_value_labels = {}
        card_defs = [
            ("state", "STATE", "#5cc8ff"),
            ("round", "ROUND", "#ffd166"),
            ("hp", "HP", "#7bd389"),
            ("time_left", "TIME LEFT", "#ff9f6e"),
            ("players", "BULLETS", "#b392f0"),
            ("bombs", "BOMBS", "#f28482"),
            ("speed", "FALL SPEED", "#8ecae6"),
            ("spawner", "SPAWNER", "#9ad47b"),
        ]

        for idx, (key, title, accent) in enumerate(card_defs):
            row = idx // 2
            col = idx % 2
            card = tk.Frame(grid, bg=self.ui_panel, bd=1, relief="ridge")
            card.grid(row=row, column=col, sticky="nsew", padx=7, pady=7)
            grid.grid_columnconfigure(col, weight=1)
            grid.grid_rowconfigure(row, weight=1)

            top = tk.Frame(card, bg=self.ui_panel)
            top.pack(fill="x", padx=14, pady=(10, 6))
            tk.Label(top, text=title, bg=self.ui_panel, fg=self.ui_muted, font=("Segoe UI", 14, "bold")).pack(side="left")
            tk.Label(top, text="●", bg=self.ui_panel, fg=accent, font=("Segoe UI", 16, "bold")).pack(side="right")

            value_var = tk.StringVar(value="--")
            self.stats_value_vars[key] = value_var
            value_lbl = tk.Label(
                card,
                textvariable=value_var,
                bg=self.ui_panel,
                fg=self.ui_fg,
                font=("Segoe UI", 26, "bold"),
                anchor="w",
                justify="left",
                wraplength=420,
            )
            value_lbl.pack(fill="both", expand=True, padx=14, pady=(4, 16))
            self.stats_value_labels[key] = value_lbl

        self._move_stats_to_second_screen_if_available()

    def _get_windows_monitors(self):
        if os.name != "nt":
            return []

        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", wintypes.LONG),
                    ("top", wintypes.LONG),
                    ("right", wintypes.LONG),
                    ("bottom", wintypes.LONG),
                ]

            class MONITORINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("rcMonitor", RECT),
                    ("rcWork", RECT),
                    ("dwFlags", wintypes.DWORD),
                ]

            monitors = []
            MONITORINFOF_PRIMARY = 1

            MonitorEnumProc = ctypes.WINFUNCTYPE(
                wintypes.BOOL,
                wintypes.HMONITOR,
                wintypes.HDC,
                ctypes.POINTER(RECT),
                wintypes.LPARAM,
            )

            def _callback(h_monitor, _hdc, _lprc, _lparam):
                info = MONITORINFO()
                info.cbSize = ctypes.sizeof(MONITORINFO)
                if user32.GetMonitorInfoW(h_monitor, ctypes.byref(info)):
                    monitors.append({
                        "left": int(info.rcMonitor.left),
                        "top": int(info.rcMonitor.top),
                        "right": int(info.rcMonitor.right),
                        "bottom": int(info.rcMonitor.bottom),
                        "is_primary": bool(info.dwFlags & MONITORINFOF_PRIMARY),
                    })
                return True

            user32.EnumDisplayMonitors(0, 0, MonitorEnumProc(_callback), 0)
            return monitors
        except Exception:
            return []

    def _move_stats_to_second_screen_if_available(self):
        monitors = self._get_windows_monitors()
        self.stats_window.update_idletasks()

        if len(monitors) >= 2:
            target = next((m for m in monitors if not m.get("is_primary")), monitors[1])
        elif monitors:
            target = monitors[0]
        else:
            # Fallback when monitor enumeration fails: use current fullscreen behavior.
            self.stats_window.attributes("-fullscreen", True)
            return

        target_width = max(1, target["right"] - target["left"])
        target_height = max(1, target["bottom"] - target["top"])
        x = target["left"]
        y = target["top"]

        # First move/size to the target monitor, then request fullscreen.
        # On Windows this keeps fullscreen scoped to the selected monitor.
        self.stats_window.attributes("-fullscreen", False)
        self.stats_window.geometry(f"{target_width}x{target_height}+{x}+{y}")
        self.stats_window.update_idletasks()
        self.stats_window.attributes("-fullscreen", True)

    def _set_custom_fields_from_preset(self, preset):
        self.players_var.set(str(preset["num_players"]))
        self.minutes_var.set(str(preset["mins"]))
        self.rounds_var.set(str(preset["rounds"]))
        self.fall_speed_var.set(f"{preset['fall_speed']:.2f}")

    def _apply_start(self, num_players, minutes, rounds, fall_speed):
        num_players = max(1, int(num_players))
        minutes = max(1, int(minutes))
        rounds = max(1, int(rounds))
        fall_speed = max(0.05, float(fall_speed))

        with self.game.lock:
            self.game.round_duration_minutes = minutes
            self.game.round_number = 1
            self.game.total_rounds_to_survive = rounds
            self.game.base_fall_speed = fall_speed
            self.game.current_fall_speed = fall_speed

        self.game.start_game(num_players)

    def start_preset(self, key):
        preset = DIFFICULTY_PRESETS[key]
        self._set_custom_fields_from_preset(preset)
        self._apply_start(preset["num_players"], preset["mins"], preset["rounds"], preset["fall_speed"])
        self.status_var.set(f"Started preset: {key}")

    def start_custom(self):
        try:
            num_players = int(self.players_var.get().strip())
            minutes = int(self.minutes_var.get().strip())
            rounds = int(self.rounds_var.get().strip())
            fall_speed = float(self.fall_speed_var.get().strip())
            self._apply_start(num_players, minutes, rounds, fall_speed)
            self.status_var.set(
                f"Started custom: bullets={max(1, num_players)}, mins={max(1, minutes)}, rounds={max(1, rounds)}, speed={max(0.05, fall_speed):.2f}"
            )
        except ValueError:
            messagebox.showerror("Invalid values", "Use numeric values: bullets, minutes, rounds, fall speed.")

    def restart_round(self):
        self.game.restart_round()
        self.status_var.set("Round restarted")

    def _schedule_stats_update(self):
        self._update_stats()
        if self.game.running:
            self.root.after(200, self._schedule_stats_update)

    def _update_stats(self):
        with self.game.lock:
            state = self.game.state
            round_no = self.game.round_number
            round_total = self.game.total_rounds_to_survive
            hp = PresidentialVehicle.global_points
            hp_max = PresidentialVehicle.global_points_default

            total_players = len(self.game.players)
            active_players = sum(1 for p in self.game.players if p.piece and p.piece.active)
            waiting_players = sum(1 for p in self.game.players if p.respawn_time > 0)
            bombs = len(self.game.bombs)
            speed = self.game.current_fall_speed
            spawner = f"{self.game.next_spawn_index}/{len(self.game.players)}"

            time_left_text = "--"
            if self.game.round_start_time is not None and self.game.round_duration_minutes > 0:
                total_sec = self.game.round_duration_minutes * 60
                left = max(0, int(total_sec - (time.time() - self.game.round_start_time)))
                mm = left // 60
                ss = left % 60
                time_left_text = f"{mm:02d}:{ss:02d}"

        self.stats_value_vars["state"].set(state)
        self.stats_value_vars["round"].set(f"{round_no}/{round_total}")
        self.stats_value_vars["hp"].set(f"{hp}/{hp_max}")
        self.stats_value_vars["players"].set(f"{total_players} total, {active_players} active, {waiting_players} waiting")
        self.stats_value_vars["bombs"].set(str(bombs))
        self.stats_value_vars["speed"].set(f"{speed:.2f}")
        self.stats_value_vars["time_left"].set(time_left_text)
        self.stats_value_vars["spawner"].set(spawner)

        hp_ratio = (hp / hp_max) if hp_max else 0.0
        hp_color = "#ff6961" if hp_ratio <= 0.30 else ("#ffd166" if hp_ratio <= 0.60 else "#7bd389")
        self.stats_value_labels["hp"].configure(fg=hp_color)

        state_colors = {
            "LOBBY": "#5cc8ff",
            "COUNTDOWN": "#ffd166",
            "PLAYING": "#7bd389",
            "PREWIN_FLICKER": "#ffcf6e",
            "WIN": "#7bed9f",
            "GAMEOVER": "#ff6b6b",
        }
        self.stats_value_labels["state"].configure(fg=state_colors.get(state, self.ui_fg))

    def quit_game(self):
        self.game.running = False
        self.net.running = False
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    game = PresidentGame()
    net = NetworkManager(game)
    net.start_bg()

    gt = threading.Thread(target=game_thread_func, args=(game,))
    gt.daemon = True
    gt.start()

    if TK_AVAILABLE:
        print("Launching desktop UI...")
        ui = GameControlUI(game, net)
        ui.run()
    else:
        print("Tkinter not available. Falling back to console controls.")
        print("Commands: 'start <num_bullets> <mins_playtime> <rounds_to_survive>', 'restart', 'quit'")

        try:
            while game.running:
                cmd = input("> ").strip().lower()
                if cmd == 'quit' or cmd == 'exit':
                    game.running = False
                    break
                elif cmd.startswith('start'):
                    parts = cmd.split()
                    if len(parts) >= 4 and parts[1].isdigit() and parts[2].isdigit() and parts[3].isdigit():
                        num_players = int(parts[1])
                        mins_playtime = int(parts[2])
                        rounds_to_survive = max(1, int(parts[3]))

                        game.round_duration_minutes = mins_playtime
                        game.round_number = 1
                        game.total_rounds_to_survive = rounds_to_survive
                        game.start_game(num_players)
                    else:
                        print("Usage: start <num_bullets> <mins_playtime> <rounds_to_survive>")
                elif cmd == 'restart':
                    game.restart_round()
                    print("Restarted round.")
                else:
                    print("Unknown command.")
        except KeyboardInterrupt:
            game.running = False

    net.running = False
    print("Exiting...")