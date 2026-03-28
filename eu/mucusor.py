import socket
import struct
import time
import threading
import random
import copy
import psutil
import os
from collections import deque

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
        "send_port": 7272,
        "recv_port": 7273,
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
        self.directionX = random.choice([-1, 1])
        self.directionY = random.choice([-1, 1])
        self.score = 0
        self.input_cooldown = 0
        self.next_shape_key = random.choice(list(SHAPES.keys()))
        self.respawn_time = 0  # when to respawn (0 = not waiting)

    def spawn_piece(self):
        shape_key = self.next_shape_key
        self.next_shape_key = random.choice(list(SHAPES.keys()))
        # Use safe spawn
        if hasattr(self, 'game') and hasattr(self.game, '_find_safe_spawn'):
            spawn_x, spawn_y = self.game._find_safe_spawn()
        else:
            spawn_x = random.randint(0, BOARD_WIDTH - 1)
            spawn_y = random.randint(0, BOARD_HEIGHT - 1)
        self.piece = PresidentialVehicle(shape_key, self.color, spawn_x, spawn_y)

class PresidentGame:
    def apply_color_scheme(self):
        scheme = self.color_schemes[(self.round_number-1) % len(self.color_schemes)]
        self.obstacle_color = scheme['obstacle']
        # Optionally update other colors if needed

    def __init__(self):
        self.board = [[BLACK for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]
        self.players = []

        self.running = True
        self.state = 'LOBBY'  # LOBBY, STARTUP, PLAYING, GAMEOVER
        self.startup_step = 0
        self.startup_timer = time.time()

        self.base_fall_speed = 0.6
        self.current_fall_speed = self.base_fall_speed
        self.min_fall_speed = 0.1
        self.last_tick = time.time()
        self.game_start_time = time.time()

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
        self.obstacle_maps = [
            # Map 1: scattered blocks (full grid, less aggressive)
            [(random.randint(0, 15), random.randint(0, 31)) for _ in range(8)],
            # Map 2: diagonal line (full grid)
            [(i, i) for i in range(min(BOARD_WIDTH, BOARD_HEIGHT))],
            # Map 3: border
            [(x, 0) for x in range(BOARD_WIDTH)] + [(x, BOARD_HEIGHT-1) for x in range(BOARD_WIDTH)] + [(0, y) for y in range(BOARD_HEIGHT)] + [(BOARD_WIDTH-1, y) for y in range(BOARD_HEIGHT)],
            # Map 4: random blocks (full grid, less aggressive)
            [(random.randint(0, 15), random.randint(0, 31)) for _ in range(10)]
        ]
        self.obstacle_color = (64, 64, 64)  # dark gray
        self.current_obstacle_map = []

        # Motion trail for smooth visuals
        self.trail = [[0.0 for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]
        self.trail_color = [[BLACK for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]
        self.trail_decay = 0.7  # multiplier per render frame (lower = faster fade)

        # Sequential spawn
        self.spawn_interval = 3.0  # seconds between each new cube
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
        self.big_cube_speed = 1.0  # seconds per move
        self.big_cube_last_move = time.time()
        self.big_cube_direction = random.choice([(0,1),(0,-1),(1,0),(-1,0)])
        self.big_cube_turn_interval = random.uniform(2,5)
        self.big_cube_last_turn = time.time()

        self.round_duration_minutes = 1  # default, will be set at start
        self.round_start_time = None
        self.round_number = 1
        self.color_schemes = [
            {'bg': (0,0,0), 'obstacle': (64,64,64), 'bullet': (255,215,0), 'car': (255,255,255)},
            {'bg': (10,10,30), 'obstacle': (0,128,255), 'bullet': (255,140,0), 'car': (255,255,255)},
            {'bg': (30,10,10), 'obstacle': (128,0,64), 'bullet': (0,255,255), 'car': (255,255,255)},
            {'bg': (0,30,10), 'obstacle': (0,255,128), 'bullet': (255,0,255), 'car': (255,255,255)},
        ]

    def setup_players(self, count):
        self.players = []
        if count < 1: count = 1
        # if count > 4: count = 4

        # All bullets are gold
        bullet_color = GOLD
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
            self.reset_board()
            # Choose random obstacle map
            self.current_obstacle_map = random.choice(self.obstacle_maps)
            for x, y in self.current_obstacle_map:
                # + shape: center and 4 arms
                plus_pixels = [(0,0), (0,-1), (0,1), (-1,0), (1,0)]
                for dx, dy in plus_pixels:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < BOARD_WIDTH and 0 <= ny < BOARD_HEIGHT:
                        self.board[ny][nx] = self.obstacle_color
            # Spawn big car in safe spot
            bx, by = self._find_safe_spawn()
            self.big_cube = {'x': bx, 'y': by, 'color': WHITE}
            # self.sound.start_bgm()
            self.state = 'COUNTDOWN'
            self.countdown_start_time = time.time()
            self.countdown_seconds = 3
            self.flashing_lines = []

    def restart_round(self):
        with self.lock:
            count = len(self.players)
            self.start_game(count)

    def spawn_all(self):
        for p in self.players:
            p.spawn_piece()

    def _spawn_next(self):
        if self.next_spawn_index < len(self.players):
            self.players[self.next_spawn_index].spawn_piece()
            p = self.players[self.next_spawn_index]
            if self.big_cube:
                dx = self.big_cube['x'] - p.piece.x
                dy = self.big_cube['y'] - p.piece.y
                p.directionX = 1 if dx >= 0 else -1
                p.directionY = 1 if dy >= 0 else -1
            self.next_spawn_index += 1

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
                for p in self.players:
                    if p.piece and p.piece.active:
                        for bx, by in p.piece.get_absolute_blocks():
                            if bx == x:
                                p.piece.active = False
                                p.piece = None
                                p.respawn_time = time.time() + self.respawn_delay
                                p.score += 1
                                print(f"Player {p.id} cube hit at column {x}! Score: {p.score}")
                                break
                        if p.piece is None:
                            break  # Already deleted, stop checking

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

    def _can_place_big_cube(self, center_x, center_y):
        obstacle_cells = self._obstacle_cells()
        for cell_x, cell_y in self._big_cube_cells(center_x, center_y):
            if cell_x < 0 or cell_x >= BOARD_WIDTH or cell_y < 0 or cell_y >= BOARD_HEIGHT:
                return False
            if (cell_x, cell_y) in obstacle_cells:
                return False
        return True

    def is_collision(self, piece, player=None, dx=0, dy=0, absolute_blocks=None):
        blocks = absolute_blocks if absolute_blocks else piece.get_absolute_blocks()
        for bx, by in blocks:
            nx, ny = bx + dx, by + dy
            # Wall collision
            if nx < 0 or nx >= BOARD_WIDTH or ny >= BOARD_HEIGHT or ny < 0:
                return True

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
                return

            if self.state == 'COUNTDOWN':
                now = time.time()
                elapsed = int(now - self.countdown_start_time)
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
                    self.state = 'PLAYING'
                    self.game_start_time = time.time()
                    self.last_tick = time.time()
                    self.next_spawn_index = 0
                    self.last_spawn_time = time.time()
                    self._spawn_next()
                return

            # --- PLAYING STATE ---
            # Round timer logic must be here!
            if self.round_start_time is not None and self.round_duration_minutes > 0:
                elapsed = time.time() - self.round_start_time
                if elapsed >= self.round_duration_minutes * 60:
                    self.round_number += 1
                    self.round_start_time = time.time()
                    self.apply_color_scheme()
                    print(f"--- ROUND {self.round_number} ---")

            # Sequential spawning
            if self.next_spawn_index < len(self.players):
                now_spawn = time.time()
                if now_spawn - self.last_spawn_time >= self.spawn_interval:
                    self._spawn_next()
                    self.last_spawn_time = now_spawn

            # Check for respawns
            now_respawn = time.time()
            for p in self.players:
                if p.respawn_time > 0 and now_respawn >= p.respawn_time:
                    p.respawn_time = 0
                    p.spawn_piece()
                    if self.big_cube:
                        dx = self.big_cube['x'] - p.piece.x
                        dy = self.big_cube['y'] - p.piece.y
                        p.directionX = 1 if dx >= 0 else -1
                        p.directionY = 1 if dy >= 0 else -1
                    print(f"Player {p.id} cube respawned!")

            # Check for clicks on active cubes via button inputs (channel 7)
            self.process_inputs()

            # Handle queued immediate board hits from recv loop
            self.process_board_touch_queue()

            # Big cube movement
            now = time.time()
            if now - self.big_cube_last_move >= self.big_cube_speed:
                dx, dy = self.big_cube_direction
                nx = self.big_cube['x'] + dx
                ny = self.big_cube['y'] + dy
                if not self._can_place_big_cube(nx, ny):
                    # Pick a new random direction (not current)
                    possible_dirs = [(0,1), (0,-1), (1,0), (-1,0)]
                    if self.big_cube_direction in possible_dirs:
                        possible_dirs.remove(self.big_cube_direction)
                    random.shuffle(possible_dirs)
                    for next_dx, next_dy in possible_dirs:
                        if self._can_place_big_cube(self.big_cube['x'] + next_dx, self.big_cube['y'] + next_dy):
                            self.big_cube_direction = (next_dx, next_dy)
                            break
                else:
                    self.big_cube['x'] = nx
                    self.big_cube['y'] = ny
                self.big_cube_last_move = now
            if now - self.big_cube_last_turn >= self.big_cube_turn_interval:
                directions = [(0,1),(0,-1),(1,0),(-1,0)]
                if self.big_cube_direction in directions:
                    directions.remove(self.big_cube_direction)
                self.big_cube_direction = random.choice(directions)
                self.big_cube_turn_interval = random.uniform(2,5)
                self.big_cube_last_turn = now

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
                            # --- Y axis movement ---
                            dy = p.directionY
                            collision_with_big = any(self.big_cube and (bx, by + dy) == (self.big_cube['x'], self.big_cube['y']) for bx, by in p.piece.get_absolute_blocks())
                            if not collision_with_big and not self.is_collision(p.piece, player=p, dy=dy):
                                p.piece.y += dy
                            else:
                                if collision_with_big:
                                    p.piece.active = False
                                    p.piece = None
                                    p.respawn_time = time.time() + self.respawn_delay
                                    p.score = max(0, p.score - 1)
                                    print(f"Player {p.id} hit big cube! Lost 1 point. Score: {p.score}")
                                else:
                                    # Reverse Y direction and try again
                                    p.directionY = -p.directionY
                                    dy = p.directionY
                                    if not self.is_collision(p.piece, player=p, dy=dy):
                                        p.piece.y += dy

                            if not p.piece or not p.piece.active:
                                continue

                            # --- X axis movement ---
                            dx = p.directionX
                            collision_with_big = any(self.big_cube and (bx + dx, by) == (self.big_cube['x'], self.big_cube['y']) for bx, by in p.piece.get_absolute_blocks())
                            if not collision_with_big and not self.is_collision(p.piece, player=p, dx=dx):
                                p.piece.x += dx
                            else:
                                if collision_with_big:
                                    p.piece.active = False
                                    p.piece = None
                                    p.respawn_time = time.time() + self.respawn_delay
                                    p.score = max(0, p.score - 1)
                                    print(f"Player {p.id} hit big cube! Lost 1 point. Score: {p.score}")
                                else:
                                    # Reverse X direction and try again
                                    p.directionX = -p.directionX
                                    dx = p.directionX
                                    if not self.is_collision(p.piece, player=p, dx=dx):
                                        p.piece.x += dx
                
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
                p.piece.active = False
                p.piece = None
                p.respawn_time = time.time() + self.respawn_delay
                p.score += 1
                print(f"Player {p.id} cube hit at ({x},{y})! Score: {p.score}")
                return True

        return False

    def process_board_touch_queue(self):
        while self.board_touch_queue:
            x, y = self.board_touch_queue.popleft()
            self.handle_board_click(x, y)

    def draw_glyph(self, buffer, key, ox, oy, color):
        if key not in FONT: return
        for dx, dy in FONT[key]:
            self.set_led(buffer, ox + dx, oy + dy, color)

    def render(self):
        buffer = bytearray(FRAME_DATA_LENGTH)

        # Use current color scheme
        scheme = self.color_schemes[(self.round_number-1) % len(self.color_schemes)]
        bg_color = scheme['bg']
        obstacle_color = scheme['obstacle']
        bullet_color = scheme['bullet']
        car_color = scheme['car']

        if self.state == 'LOBBY':
            # No white bar at the bottom
            return buffer

        if self.state == 'COUNTDOWN':
            now = time.time()
            elapsed = int(now - self.countdown_start_time)
            remaining = self.countdown_seconds - elapsed
            if remaining > 0:
                self.draw_glyph(buffer, remaining, 6, 10, WHITE)
            return buffer

        if self.state == 'TRANSITION':
            now = time.time()
            elapsed = now - self.transition_start_time
            total_tiles = BOARD_WIDTH * BOARD_HEIGHT
            unravel_duration = self.transition_duration
            fill_duration = unravel_duration / 2
            unfill_duration = unravel_duration / 2
            if elapsed < fill_duration:
                # Fill phase (top-down on physical panel)
                progress = min(1.0, elapsed / fill_duration)
                tiles_to_fill = int(progress * total_tiles)
                count = 0
                for y in range(BOARD_HEIGHT - 1, -1, -1):
                    for x in range(BOARD_WIDTH):
                        if count < tiles_to_fill:
                            self.set_led(buffer, x, y, WHITE)
                            count += 1
            elif elapsed < unravel_duration:
                # Unfill phase (top-down on physical panel)
                progress = min(1.0, (elapsed - fill_duration) / unfill_duration)
                tiles_to_unfill = int(progress * total_tiles)
                count = 0
                for y in range(BOARD_HEIGHT - 1, -1, -1):
                    for x in range(BOARD_WIDTH):
                        if count < total_tiles - tiles_to_unfill:
                            self.set_led(buffer, x, y, WHITE)
                            count += 1
            return buffer

        if self.state == 'GAMEOVER':
            flash_on = (self.winner_flash_count % 2 == 0)
            winner_color = self.winner_player.color if self.winner_player else RED
            text_color = winner_color if flash_on else BLACK

            if self.winner_flash_count >= 10: text_color = winner_color

            self.draw_glyph(buffer, 'W', 1, 10, text_color)
            self.draw_glyph(buffer, 'I', 7, 10, text_color)
            self.draw_glyph(buffer, 'N', 11, 10, text_color)

            # for p in self.players:
            #     self.draw_player_controls(buffer, p, p.id * 4)
            return buffer

        if self.state == 'PLAYING':
            with self.lock:
                # Draw background
                for y in range(BOARD_HEIGHT):
                    for x in range(BOARD_WIDTH):
                        self.set_led(buffer, x, y, bg_color)
                # Draw input area (rows 28-31) with bg_color
                for y in range(28, 32):
                    for x in range(BOARD_WIDTH):
                        self.set_led(buffer, x, y, bg_color)
                # Draw obstacles
                for x, y in self.current_obstacle_map:
                    plus_pixels = [(0,0), (0,-1), (0,1), (-1,0), (1,0)]
                    for dx, dy in plus_pixels:
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < BOARD_WIDTH and 0 <= ny < BOARD_HEIGHT:
                            self.set_led(buffer, nx, ny, obstacle_color)
                # Draw big car
                if self.big_cube:
                    for cx, cy in self._big_cube_cells():
                        if 0 <= cx < BOARD_WIDTH and 0 <= cy < BOARD_HEIGHT:
                            self.set_led(buffer, cx, cy, car_color)
                    window_x = self.big_cube['x']
                    window_y = self.big_cube['y'] - 1
                    if 0 <= window_x < BOARD_WIDTH and 0 <= window_y < BOARD_HEIGHT:
                        self.set_led(buffer, window_x, window_y, BLUE)
                # Draw player bullets
                for p in self.players:
                    if p.piece and p.piece.active:
                        for bx, by in p.piece.get_absolute_blocks():
                            if 0 <= bx < BOARD_WIDTH and 0 <= by < BOARD_HEIGHT:
                                self.set_led(buffer, bx, by, bullet_color)
                # Draw player pieces
                for p in self.players:
                    if p.piece and p.piece.active:
                        for bx, by in p.piece.get_absolute_blocks():
                            if 0 <= by < BOARD_HEIGHT and 0 <= bx < BOARD_WIDTH:
                                self.set_led(buffer, bx, by, p.piece.color)

                # Draw obstacles (already on board)

                # Draw big car (protected object)
                if self.big_cube:
                    car_color = self.big_cube['color']
                    for cx, cy in self._big_cube_cells():
                        if 0 <= cx < BOARD_WIDTH and 0 <= cy < BOARD_HEIGHT:
                            self.set_led(buffer, cx, cy, car_color)
                    window_x = self.big_cube['x']
                    window_y = self.big_cube['y'] - 1
                    if 0 <= window_x < BOARD_WIDTH and 0 <= window_y < BOARD_HEIGHT:
                        self.set_led(buffer, window_x, window_y, BLUE)
                    # Optionally, add wheels (darker color)
                    wheel_color = (32,32,32)
                    for wx in [-1,1]:
                        for wy in [1]:
                            cx = self.big_cube['x'] + wx
                            cy = self.big_cube['y'] + wy
                            if 0 <= cx < BOARD_WIDTH and 0 <= cy < BOARD_HEIGHT:
                                self.set_led(buffer, cx, cy, wheel_color)

                # Decay trail for next frame
                for y in range(BOARD_HEIGHT):
                    for x in range(BOARD_WIDTH):
                        self.trail[y][x] *= self.trail_decay

            # for x in range(16): self.set_led(buffer, x, 28, WHITE)
            # for p in self.players:
            #     self.draw_player_controls(buffer, p, p.id * 4)

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

    def _find_safe_spawn(self):
        # Find a random (x, y) not in terrain
        attempts = 0
        while attempts < 100:
            x = random.randint(0, BOARD_WIDTH-1)
            y = random.randint(0, BOARD_HEIGHT-1)
            # Check if (x, y) is not in any obstacle
            is_safe = True
            for ox, oy in self.current_obstacle_map:
                for dx, dy in [(0,0), (0,-1), (0,1), (-1,0), (1,0)]:
                    if x == ox + dx and y == oy + dy:
                        is_safe = False
                        break
                if not is_safe:
                    break
            if is_safe:
                return x, y
            attempts += 1
        # fallback: just return (0,0)
        return 0, 0


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
                parts = cmd.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    num_players = int(parts[1])
                    # Prompt for round duration
                    while True:
                        try:
                            mins = int(input("Enter round duration in minutes: "))
                            if mins > 0: break
                        except Exception:
                            pass
                    game.round_duration_minutes = mins
                    game.round_start_time = time.time()
                    game.round_number = 1
                    game.start_game(num_players)
                else:
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