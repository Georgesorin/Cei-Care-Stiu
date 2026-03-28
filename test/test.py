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

# --- Game Winner ---
WINNER_P = None  # Will be set when game ends

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
    except: pass
    return defaults

CONFIG = _load_config()

# --- Networking Constants ---
UDP_SEND_IP = CONFIG.get("device_ip", "255.255.255.255")
UDP_SEND_PORT = CONFIG.get("send_port", 7270)
UDP_LISTEN_PORT = CONFIG.get("recv_port", 7271)

# --- Matrix Constants ---
NUM_CHANNELS = 8
LEDS_PER_CHANNEL = 64
FRAME_DATA_LENGTH = NUM_CHANNELS * LEDS_PER_CHANNEL * 3
MATRIX_TOUCH_CHANNELS = 8
MATRIX_TOUCH_PER_CHANNEL = 64
MATRIX_TOUCH_COUNT = MATRIX_TOUCH_CHANNELS * MATRIX_TOUCH_PER_CHANNEL

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
    1: [(1,0), (1,1), (1,2), (1,3), (1,4)], # Center vertical
    2: [(0,0), (1,0), (2,0), (2,1), (1,2), (0,2), (0,3), (0,4), (1,4), (2,4)],
    3: [(0,0), (1,0), (2,0), (2,1), (1,2), (2,2), (2,3), (0,4), (1,4), (2,4)],
    4: [(0,0), (0,1), (0,2), (1,2), (2,2), (2,0), (2,1), (2,3), (2,4)],
    5: [(0,0), (1,0), (2,0), (0,1), (0,2), (1,2), (2,2), (2,3), (0,4), (1,4), (2,4)],
    'W': [(0,0),(0,1),(0,2),(0,3),(0,4), (4,0),(4,1),(4,2),(4,3),(4,4), (1,3),(2,2),(3,3)], # Wide W
    'I': [(0,0),(1,0),(2,0), (1,1),(1,2),(1,3), (0,4),(1,4),(2,4)],
    'N': [(0,0),(0,1),(0,2),(0,3),(0,4), (3,0),(3,1),(3,2),(3,3),(3,4), (1,1),(2,2)] # Compact N
}

# Input Configuration
INPUT_REPEAT_RATE = 0.25  # Seconds per move when holding
INPUT_INITIAL_DELAY = 0.5 # Initial delay before repeat starts

def calculate_checksum(data):
    acc = sum(data)
    idx = acc & 0xFF
    return PASSWORD_ARRAY[idx] if idx < len(PASSWORD_ARRAY) else 0

class Player:
    """Player class for tracking score and input control"""
    def __init__(self):
        self.points = 0
        self.player_scores = {}
        self.player_combos = {}
        self.player_max_combos = {}
        self.player_misses = {}
        self.control_rows = [1, 2, 3, 4, 5]  # Control pad rows for groups 0-4
        self.control_column = 1  # Control pads are at column 1
        self.last_scored_states = {}  # Track which flashes we've already scored

    def get_multiplier(self, combo):
        """Beat Saber-style combo multiplier curve: 1x, 2x, 4x, 8x."""
        if combo >= 14:
            return 8
        if combo >= 6:
            return 4
        if combo >= 2:
            return 2
        return 1

    def register_hit(self, player_id, base_points=1):
        """Register a successful hit, update combo and score with multiplier."""
        combo = self.player_combos.get(player_id, 0) + 1
        self.player_combos[player_id] = combo

        max_combo = self.player_max_combos.get(player_id, 0)
        if combo > max_combo:
            self.player_max_combos[player_id] = combo

        multiplier = self.get_multiplier(combo)
        gained = base_points * multiplier

        self.points += gained
        self.player_scores[player_id] = self.player_scores.get(player_id, 0) + gained

        return gained, multiplier, combo

    def register_miss(self, player_id):
        """Register a miss and break combo."""
        previous_combo = self.player_combos.get(player_id, 0)
        self.player_combos[player_id] = 0
        self.player_misses[player_id] = self.player_misses.get(player_id, 0) + 1
        return previous_combo

    def get_led_index(self, x, y):
        """Convert (x, y) board position to LED index for button checking"""
        # This maps board coordinates to button state index
        channel = y // 4
        row_in_channel = y % 4

        if row_in_channel % 2 == 0:
            led_index = row_in_channel * 16 + x
        else:
            led_index = row_in_channel * 16 + (15 - x)

        # Return full matrix touch index (0..511), not just per-channel 0..63.
        return channel * 64 + led_index

    def check_hit(self, group_index, x, y, button_states):
        """
        Check if player hits the raindrop at position (x, y) for given group.
        Returns True if hit and points were awarded.
        """
        # Only group 0 (left side) controls
        if group_index != 0:
            return False

        # Check if this position has a button and if it's pressed
        if x == self.control_column and y in self.control_rows:
            state_key = (group_index, y)
            
            # Get the LED index for this button
            led_index = self.get_led_index(x, y)
            
            # Check if button is pressed and we haven't already scored for this flash
            if led_index < len(button_states) and button_states[led_index]:
                if state_key not in self.last_scored_states:
                    self.points += 1
                    self.last_scored_states[state_key] = True
                    print("Hit! Points: ", self.points)
                    return True
        
        return False

    def reset_hit_for_state(self, group_index, y):
        """Reset hit tracking for a specific group/row combination"""
        state_key = (group_index, y)
        if state_key in self.last_scored_states:
            del self.last_scored_states[state_key]

class TestGame:
    def __init__(self):
        self.board = [[BLACK for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]

        self.running = True
        self.state = 'LOBBY' # LOBBY, STARTUP, PLAYING, GAMEOVER
        self.startup_step = 0
        self.startup_timer = time.time()
        self.lobby_timer = time.time()  # Timer for LOBBY zone display

        self.lock = threading.RLock()
        
        # Initialize player and controls
        self.player = Player()
        self.button_states = [False] * MATRIX_TOUCH_COUNT  # Track touch states across full 16x32 matrix
        self.prev_button_states = [False] * MATRIX_TOUCH_COUNT  # Edge detection: tap = False -> True
        # 10-player mapping: each player owns a row-band and has 5 lane buttons.
        self.player_button_map = {}

    def _build_player_button_map(self, row_groups_left, row_groups_right, left_edge, right_edge):
        """Build 10-player button map from row-group bands.

        Player ownership model:
        - P1: left, first element of each lane tuple
        - P2: right, first element of each lane tuple
        - P3: left, second element ... and so on.
        """
        player_map = {}
        lanes_per_side = len(row_groups_left)
        bands = len(row_groups_left[0]) if row_groups_left else 0

        for band_index in range(bands):
            left_player_id = (band_index * 2) + 1
            right_player_id = left_player_id + 1

            left_buttons = []
            right_buttons = []

            for lane_index in range(lanes_per_side):
                left_row = row_groups_left[lane_index][band_index]
                right_row = row_groups_right[lane_index][band_index]

                left_buttons.append(self.player.get_led_index(left_edge, left_row))
                right_buttons.append(self.player.get_led_index(right_edge, right_row))

            player_map[left_player_id] = left_buttons
            player_map[right_player_id] = right_buttons

        self.player_button_map = player_map

    def button_index_to_xy(self, button_index):
        """Convert button index (0..511) back to (x, y) board coordinates."""
        channel = button_index // 64
        led_index = button_index % 64
        row_in_channel = led_index // 16
        y = channel * 4 + row_in_channel
        
        if row_in_channel % 2 == 0:
            x = led_index % 16
        else:
            x = 15 - (led_index % 16)
        
        return x, y
        self.board = [[BLACK for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]

    def set_led(self, buffer, x, y, color):
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

        if offset + NUM_CHANNELS * 2 < len(buffer):
            buffer[offset] = color[1]  # GREEN (Swap for hardware)
            buffer[offset + NUM_CHANNELS] = color[0]  # RED (Swap for hardware)
            buffer[offset + NUM_CHANNELS*2] = color[2]

    def start_game(self):
        with self.lock:
            self.reset_board()
            self.state = 'STARTUP'
            self.startup_step = 0

    def render(self):
        # Create a blank frame buffer
        frame_buffer = bytearray(FRAME_DATA_LENGTH)

        if not hasattr(self, 'time_counter'):
            self.time_counter = 0

        # Fade existing pixels
        for y in range(BOARD_HEIGHT):
            for x in range(BOARD_WIDTH):
                # Get current color from board (for fading effect)
                current_color = self.board[y][x]
                r_fade = max(0, current_color[0] - 25) if current_color[0] > 0 else 0
                g_fade = max(0, current_color[1] - 25) if current_color[1] > 0 else 0
                b_fade = max(0, current_color[2] - 25) if current_color[2] > 0 else 0
                faded_color = (r_fade, g_fade, b_fade)
                self.set_led(frame_buffer, x, y, faded_color)
                self.board[y][x] = faded_color  # Update board with faded color

        # ===========================================
        # LOBBY STATE: Flash player zones
        # ===========================================
        if self.state == 'LOBBY':
            # Create a flashing pattern (on/off every 0.5 seconds)
            flash_cycle = int((time.time() - self.lobby_timer) * 2) % 2
            
            # Ensure player_button_map is built (copy from render logic)
            LEFT_EDGE = 1
            RIGHT_EDGE = BOARD_WIDTH - 2
            ROW_GROUPS_LEFT = [
                (1, 7, 13, 19, 25),   # Group 0
                (2, 8, 14, 20, 26),   # Group 1
                (3, 9, 15, 21, 27),   # Group 2
                (4, 10, 16, 22, 28),  # Group 3
                (5, 11, 17, 23, 29)   # Group 4
            ]
            ROW_GROUPS_RIGHT = [
                (1, 7, 13, 19, 25),
                (2, 8, 14, 20, 26),
                (3, 9, 15, 21, 27),
                (4, 10, 16, 22, 28),
                (5, 11, 17, 23, 29)
            ]
            
            if not self.player_button_map:
                self._build_player_button_map(ROW_GROUPS_LEFT, ROW_GROUPS_RIGHT, LEFT_EDGE, RIGHT_EDGE)
            
            # Player colors (10 players)
            PLAYER_COLORS = [
                RED, BLUE, GREEN, CYAN, MAGENTA,
                YELLOW, ORANGE, WHITE, RED, BLUE
            ]
            
            # Flash each player's zones when flash_cycle is 1
            if flash_cycle == 1:
                for player_id in range(1, 11):
                    if player_id in self.player_button_map:
                        player_buttons = self.player_button_map[player_id]
                        color = PLAYER_COLORS[player_id - 1]
                        
                        for button_idx in player_buttons:
                            x, y = self.button_index_to_xy(button_idx)
                            if 0 <= x < BOARD_WIDTH and 0 <= y < BOARD_HEIGHT:
                                self.set_led(frame_buffer, x, y, color)
                                self.board[y][x] = color
            
            # Step 3: Update animation timing
            self.time_counter += 1
            self.prev_button_states = self.button_states.copy()
            return frame_buffer

        # ===========================================
        # MATRIX BORDER AND CENTER COLUMN
        # ===========================================
        # Draw white border around perimeter and vertical center column

        # Draw white border around the entire matrix perimeter
        for x in range(BOARD_WIDTH):
            # Top border (row 0)
            self.set_led(frame_buffer, x, 0, WHITE)
            self.board[0][x] = WHITE
            # Bottom border (last row)
            self.set_led(frame_buffer, x, BOARD_HEIGHT - 1, WHITE)
            self.board[BOARD_HEIGHT - 1][x] = WHITE

        for y in range(BOARD_HEIGHT):
            # Left border (column 0)
            self.set_led(frame_buffer, 0, y, WHITE)
            self.board[y][0] = WHITE
            # Right border (last column)
            self.set_led(frame_buffer, BOARD_WIDTH - 1, y, WHITE)
            self.board[y][BOARD_WIDTH - 1] = WHITE

        # Draw white vertical center columns (middle of 16 columns = columns 7 & 8)
        CENTER_COLUMN = BOARD_WIDTH // 2  # Column 8
        CENTER_COLUMN_LEFT = CENTER_COLUMN - 1  # Column 7

        for y in range(BOARD_HEIGHT):
            self.set_led(frame_buffer, CENTER_COLUMN, y, WHITE)
            self.board[y][CENTER_COLUMN] = WHITE

            self.set_led(frame_buffer, CENTER_COLUMN_LEFT, y, WHITE)
            self.board[y][CENTER_COLUMN_LEFT] = WHITE

        # Draw horizontal lines at rows 6n (0,6,12) - uses every sixth row
        for y in range(0, BOARD_HEIGHT, 6):
            for x in range(BOARD_WIDTH):
                # Keep border and center line as white too
                self.set_led(frame_buffer, x, y, WHITE)
                self.board[y][x] = WHITE

        # ===========================================
        # HORIZONTAL MATRIX RAIN FROM CENTER AREA
        # ===========================================
        # 5 row pairs, drops spawn from center column area, move left together

        # Define the target position and row groups
        LEFT_EDGE = 1  # Stop at left edge (column 0)
        RIGHT_EDGE = BOARD_WIDTH - 2  # Stop before right border (column 14)

        # Left-moving groups (original)
        ROW_GROUPS_LEFT = [
            (1, 7, 13, 19, 25),   # Group 0 (Top)
            (2, 8, 14, 20, 26),   # Group 1 (Upper-Middle)
            (3, 9, 15, 21, 27),   # Group 2 (Upper-Middle)
            (4, 10, 16, 22, 28),  # Group 3 (Middle)
            (5, 11, 17, 23, 29)   # Group 4 (Bottom)
        ]

        # Right-moving groups (mirrored)
        ROW_GROUPS_RIGHT = [
            (1, 7, 13, 19, 25),   # Group 5 (Top, moving right)
            (2, 8, 14, 20, 26),   # Group 6 (Upper-Middle, moving right)
            (3, 9, 15, 21, 27),   # Group 7 (Upper-Middle, moving right)
            (4, 10, 16, 22, 28),  # Group 8 (Middle, moving right)
            (5, 11, 17, 23, 29)   # Group 9 (Bottom, moving right)
        ]

        # All groups combined
        ROW_GROUPS = ROW_GROUPS_LEFT + ROW_GROUPS_RIGHT

        if not self.player_button_map:
            self._build_player_button_map(ROW_GROUPS_LEFT, ROW_GROUPS_RIGHT, LEFT_EDGE, RIGHT_EDGE)

        # Colors for each group (shared across all rows in that group)
        GROUP_COLORS = [MAGENTA, CYAN, GREEN, RED, YELLOW] * 2  # Repeat for both sides

        # ===========================================
        # INITIALIZE DROP STATES (FIRST TIME ONLY)
        # ===========================================

        if not hasattr(self, 'group_states'):
            self.group_states = {}         # States: 'waiting', 'moving', 'flashing'
            self.group_positions = {}      # X positions for each group
            self.group_flash_timers = {}   # Flash duration timers
            self.group_speed_counters = {} # Speed control counters
            self.group_directions = {}     # Direction: -1 for left, +1 for right
            self.group_hit_players = {}    # Track which players hit during current flash window

            self.global_spawn_timer = 0

            for group_index in range(len(ROW_GROUPS)):
                self.group_states[group_index] = 'waiting'
                # Left groups (0-4) start right of center, right groups (5-9) start left of center
                if group_index < 5:
                    self.group_positions[group_index] = CENTER_COLUMN + 1
                    self.group_directions[group_index] = -1  # Move left
                else:
                    self.group_positions[group_index] = CENTER_COLUMN - 1
                    self.group_directions[group_index] = 1   # Move right

                self.group_flash_timers[group_index] = 0
                self.group_speed_counters[group_index] = 0


        # ===========================================
        # RANDOM PAIRED GROUP SPAWNING SYSTEM
        # ===========================================
        # Left and right groups spawn together in pairs

        self.global_spawn_timer += 1

        if self.global_spawn_timer >= random.randint(10, 20):
            # Find pairs where both left and right groups are waiting
            available_pairs = []
            for pair_index in range(5):
                left_idx = pair_index
                right_idx = pair_index + 5
                if self.group_states[left_idx] == 'waiting' and self.group_states[right_idx] == 'waiting':
                    available_pairs.append((left_idx, right_idx))

            if available_pairs:
                left_group, right_group = random.choice(available_pairs)
                
                # Spawn both groups
                self.group_states[left_group] = 'moving'
                self.group_positions[left_group] = CENTER_COLUMN - 1
                
                self.group_states[right_group] = 'moving'
                self.group_positions[right_group] = CENTER_COLUMN + 1

            self.global_spawn_timer = 0

        # ===========================================
        # PROCESS EACH GROUP'S DROP STATE
        # ===========================================

        for group_index, group_rows in enumerate(ROW_GROUPS):
            group_color = GROUP_COLORS[group_index]
            state = self.group_states[group_index]
            direction = self.group_directions[group_index]

            if state == 'moving':
                # Check if reached edge (different edge for left vs right movement)
                if direction == -1:  # Moving left
                    if self.group_positions[group_index] > LEFT_EDGE:
                        self.group_speed_counters[group_index] += 1
                        if self.group_speed_counters[group_index] >= 2:
                            self.group_positions[group_index] -= 1
                            self.group_speed_counters[group_index] = 0
                    else:
                        self.group_states[group_index] = 'flashing'
                        self.group_flash_timers[group_index] = 0
                        self.group_hit_players[group_index] = set()
                else:  # Moving right
                    if self.group_positions[group_index] < RIGHT_EDGE:
                        self.group_speed_counters[group_index] += 1
                        if self.group_speed_counters[group_index] >= 2:
                            self.group_positions[group_index] += 1
                            self.group_speed_counters[group_index] = 0
                    else:
                        self.group_states[group_index] = 'flashing'
                        self.group_flash_timers[group_index] = 0
                        self.group_hit_players[group_index] = set()

            elif state == 'flashing':
                self.group_flash_timers[group_index] += 1
                
                # 10-player hit detection:
                # Players are grouped by row-band and side (left/right).
                lane_index = group_index % 5
                is_left_side_group = group_index < 5

                for band_index in range(5):
                    player_id = (band_index * 2) + (1 if is_left_side_group else 2)
                    player_buttons = self.player_button_map.get(player_id, [])

                    if lane_index >= len(player_buttons):
                        continue

                    lane_button = player_buttons[lane_index]
                    is_pressed = lane_button < len(self.button_states) and self.button_states[lane_button]
                    was_pressed = lane_button < len(self.prev_button_states) and self.prev_button_states[lane_button]

                    # Score only on a tap edge while the note is in the hit window.
                    if is_pressed and not was_pressed and player_id not in self.group_hit_players.get(group_index, set()):
                        gained, multiplier, combo = self.player.register_hit(player_id)
                        self.group_hit_players.setdefault(group_index, set()).add(player_id)
                        print(
                            f"P{player_id} HIT lane {lane_index} | "
                            f"+{gained} (x{multiplier}) | "
                            f"Combo: {combo} | "
                            f"P{player_id} Score: {self.player.player_scores[player_id]}"
                        )

                if self.group_flash_timers[group_index] >= 3:
                    # Any player on this side who did not hit this note gets a miss.
                    hit_players = self.group_hit_players.get(group_index, set())
                    for band_index in range(5):
                        player_id = (band_index * 2) + (1 if is_left_side_group else 2)
                        if player_id not in hit_players:
                            broken_combo = self.player.register_miss(player_id)
                            if broken_combo > 0:
                                print(
                                    f"P{player_id} MISS lane {lane_index} | "
                                    f"Combo Broken: {broken_combo}"
                                )

                    self.group_hit_players[group_index] = set()
                    self.group_states[group_index] = 'waiting'

            # ===========================================
            # DRAW THE GROUP BASED ON CURRENT STATE
            # ===========================================

            drop_x = self.group_positions[group_index]
            if 0 <= drop_x < BOARD_WIDTH:
                for row in group_rows:
                    if state == 'moving':
                        self.set_led(frame_buffer, drop_x, row, group_color)
                        self.board[row][drop_x] = group_color
                    elif state == 'flashing':
                        self.set_led(frame_buffer, drop_x, row, WHITE)
                        self.board[row][drop_x] = WHITE

        # Step 3: Update animation timing
        self.time_counter += 1
        self.prev_button_states = self.button_states.copy()

        # Return the completed frame buffer
        return frame_buffer


    def tick(self):
        with self.lock:
            if self.state == 'LOBBY':
                # Display player zones for 7 seconds, then transition to STARTUP
                now = time.time()
                if now - self.lobby_timer >= 7:
                    print("Entering STARTUP phase...")
                    self.state = 'STARTUP'
                    self.startup_timer = now
                    self.startup_step = 0
                return

            if self.state == 'STARTUP':
                now = time.time()
                delay = 0.2 if self.startup_step < 5 else 1.0
                if now - self.startup_timer > delay:
                    self.startup_step += 1
                    self.startup_timer = now
                    if self.startup_step >= 10:
                        print("FIGHT! Game Starting...")
                        self.state = 'PLAYING'
                        self.game_start_time = time.time()
                        self.spawn_all()
                return

            if self.state == 'PLAYING':
                # Check if 3 minutes (180 seconds) have elapsed
                now = time.time()
                elapsed_time = now - self.game_start_time
                
                if elapsed_time >= 180:
                    # Game over - calculate winner
                    global WINNER_P
                    if self.player.player_scores:
                        WINNER_P = max(self.player.player_scores, key=self.player.player_scores.get)
                        winner_score = self.player.player_scores[WINNER_P]
                        print(f"\n=== TIME'S UP ===")
                        print(f"Winner: P{WINNER_P} with {winner_score} points!")
                        print(f"Final Scores: {self.player.player_scores}\n")
                    else:
                        WINNER_P = None
                        print("\n=== TIME'S UP ===")
                        print("No scores recorded.\n")
                    
                    self.state = 'GAMEOVER'
                    self.game_over_timer = now
                    self.winner_flash_count = 0
                return

            if self.state == 'GAMEOVER':
                now = time.time()
                if now - self.game_over_timer > 0.5:
                    self.game_over_timer = now
                    self.winner_flash_count += 1
                return

class NetworkManager:
    def __init__(self, game):
        self.game = game
        self.sock_send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_send.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock_recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.running = True
        self.sequence_number = 0
        self.prev_button_states = [False] * MATRIX_TOUCH_COUNT

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
        if self.sequence_number == 0:
            self.sequence_number = 1

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
        fff0_packet.append(0x1E) # Force Checksum
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

            chunk = frame_data[i:i+chunk_size]
            
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
            time.sleep(0.005) # Slight delay

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
                data, addr = self.sock_recv.recvfrom(2048)

                # Simulator packets contain per-channel touch bytes in 171-byte blocks.
                # Parse all channels so taps from upper and lower matrix are both visible.
                if len(data) >= 1264 and data[0] == 0x88:
                    new_states = [False] * MATRIX_TOUCH_COUNT

                    for channel in range(MATRIX_TOUCH_CHANNELS):
                        base = 2 + (channel * 171) + 1
                        for led in range(MATRIX_TOUCH_PER_CHANNEL):
                            source_idx = base + led
                            if source_idx < len(data):
                                dst_idx = channel * MATRIX_TOUCH_PER_CHANNEL + led
                                new_states[dst_idx] = (data[source_idx] == 0xCC)

                    self.game.button_states = new_states

                    self.prev_button_states = self.game.button_states.copy()

            except Exception as e:
                print(f"[RECV ERROR] {e}")

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
    game = TestGame()
    net = NetworkManager(game)
    net.start_bg()

    gt = threading.Thread(target=game_thread_func, args=(game,))
    gt.daemon = True
    gt.start()

    print("Game is running. Press Ctrl+C to exit.")
    print("Commands: exit")
          
    try:
        while game.running:
            cmd = input("> ").strip().lower()
            if cmd == "exit":
                game.running = False
    except KeyboardInterrupt:
        game.running = False

    net.running = False
    print("Exiting...")