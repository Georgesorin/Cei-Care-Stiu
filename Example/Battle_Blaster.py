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

#import SoundGenerator

# --- Configuration ---
_CFG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tetris_config.json")

def _load_config():
    defaults = {
        "device_ip": "255.255.255.255",
        "send_port": 9999,
        "recv_port": 9998,
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
UDP_SEND_IP   = CONFIG.get("device_ip", "255.255.255.255")
UDP_SEND_PORT = CONFIG.get("send_port", 4626)
UDP_LISTEN_PORT = CONFIG.get("recv_port", 7800)

# --- Matrix Constants ---
NUM_CHANNELS    = 8
LEDS_PER_CHANNEL = 64
FRAME_DATA_LENGTH = NUM_CHANNELS * LEDS_PER_CHANNEL * 3

BOARD_WIDTH  = 16
BOARD_HEIGHT = 32
INPUT_CHANNEL = 7

# --- Colors (R, G, B) ---
BLACK   = (0,   0,   0)
WHITE   = (255, 255, 255)
RED     = (255, 0,   0)
YELLOW  = (255, 255, 0)
GREEN   = (0,   255, 0)
BLUE    = (0,   0,   255)
CYAN    = (0,   255, 255)
MAGENTA = (255, 0,   255)
ORANGE  = (255, 165, 0)
DIM_RED   = (60,  0,   0)
DIM_BLUE  = (0,   0,   60)

# --- Password for Checksum ---
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

# --- Font Data (3x5 pixels, (dx, dy) offsets) ---
FONT = {
    # Original digits
    1: [(1,0), (1,1), (1,2), (1,3), (1,4)],
    2: [(0,0),(1,0),(2,0),(2,1),(1,2),(0,2),(0,3),(0,4),(1,4),(2,4)],
    3: [(0,0),(1,0),(2,0),(2,1),(1,2),(2,2),(2,3),(0,4),(1,4),(2,4)],
    4: [(0,0),(0,1),(0,2),(1,2),(2,2),(2,0),(2,1),(2,3),(2,4)],
    5: [(0,0),(1,0),(2,0),(0,1),(0,2),(1,2),(2,2),(2,3),(0,4),(1,4),(2,4)],
    # New digits
    0: [(0,0),(1,0),(2,0),(0,1),(2,1),(0,2),(2,2),(0,3),(2,3),(0,4),(1,4),(2,4)],
    6: [(0,0),(1,0),(2,0),(0,1),(0,2),(1,2),(2,2),(0,3),(2,3),(0,4),(1,4),(2,4)],
    7: [(0,0),(1,0),(2,0),(2,1),(2,2),(2,3),(2,4)],
    8: [(0,0),(1,0),(2,0),(0,1),(2,1),(0,2),(1,2),(2,2),(0,3),(2,3),(0,4),(1,4),(2,4)],
    9: [(0,0),(1,0),(2,0),(0,1),(2,1),(0,2),(1,2),(2,2),(2,3),(0,4),(1,4),(2,4)],
    # Original letters
    'W': [(0,0),(0,1),(0,2),(0,3),(0,4),(4,0),(4,1),(4,2),(4,3),(4,4),(1,3),(2,2),(3,3)],
    'I': [(0,0),(1,0),(2,0),(1,1),(1,2),(1,3),(0,4),(1,4),(2,4)],
    'N': [(0,0),(0,1),(0,2),(0,3),(0,4),(3,0),(3,1),(3,2),(3,3),(3,4),(1,1),(2,2)],
    # New letters
    'A': [(1,0),(0,1),(2,1),(0,2),(1,2),(2,2),(0,3),(2,3),(0,4),(2,4)],
    'B': [(0,0),(1,0),(0,1),(2,1),(0,2),(1,2),(0,3),(2,3),(0,4),(1,4)],
    'V': [(0,0),(2,0),(0,1),(2,1),(0,2),(2,2),(1,3),(1,4)],
    'S': [(0,0),(1,0),(2,0),(0,1),(0,2),(1,2),(2,2),(2,3),(0,4),(1,4),(2,4)],
}

# --- Battle Blaster Game Constants ---
GAME_DURATION           = 300     # 5 minutes in seconds
PROJECTILE_TICK_INTERVAL = 0.15   # seconds between projectile steps
POWERUP_SPAWN_INTERVAL  = 10.0    # seconds between spawns
POWERUP_LIFETIME        = 30.0    # seconds power-up stays on board
POWERUP_EFFECT_DURATION = 15.0    # seconds collected effect lasts
MAX_POWERUPS_ON_BOARD   = 3
POWERUP_SPAWN_ROW_MIN   = 2       # keep clear of first/last 2 rows
POWERUP_SPAWN_ROW_MAX   = 29

DOUBLE_PRESS_WINDOW  = 1.0   # max seconds between first and second press
DOUBLE_PRESS_TIMEOUT = 1.5   # first press expires after this

# Team A is at the TOP (row 0), shoots downward (+1)
# Team B is at the BOTTOM (row 31), shoots upward (-1)
TEAM_A_BASE_ROW     = 0
TEAM_B_BASE_ROW     = 31
LAUNCHER_ROW_A      = 1     # Team A's button bar (just below their base, toward middle)
LAUNCHER_ROW_B      = 30    # Team B's button bar (just above their base, toward middle)
NEUTRAL_ROW_MIN     = 2
NEUTRAL_ROW_MAX     = 29

# Physical button rows (by board y-coordinate)
TEAM_A_INPUT_ROW = 1    # y=1  — channel 0, row_in_ch 1 (odd/reversed)
TEAM_B_INPUT_ROW = 30   # y=30 — channel 7, row_in_ch 2 (even/direct)

# button_states is indexed globally: channel*64 + local_led_idx (512 total)
BUTTON_STATES_SIZE = NUM_CHANNELS * LEDS_PER_CHANNEL   # 512

def global_btn_idx(y, col):
    """Return the global button_states index for board position (y, col)."""
    channel      = y // 4
    row_in_ch    = y % 4
    if row_in_ch % 2 == 0:          # even row: left→right
        local_idx = row_in_ch * 16 + col
    else:                            # odd row: right→left (snake)
        local_idx = row_in_ch * 16 + (15 - col)
    return channel * 64 + local_idx

# Power-up types
PTYPE_SPEED  = 1   # Yellow  — 2× projectile speed for 15s
PTYPE_RAPID  = 2   # Green   — single tap fires for 15s
PTYPE_DOUBLE = 3   # Magenta — fire 2 projectiles (col±1) for 15s

PTYPE_COLORS = {
    PTYPE_SPEED:  YELLOW,
    PTYPE_RAPID:  GREEN,
    PTYPE_DOUBLE: MAGENTA,
}


def calculate_checksum(data):
    acc = sum(data)
    idx = acc & 0xFF
    return PASSWORD_ARRAY[idx] if idx < len(PASSWORD_ARRAY) else 0


# ---------------------------------------------------------------------------
# Sound Manager (unchanged from Tetris_Game.py)
# ---------------------------------------------------------------------------

class SoundManager:
    def __init__(self):
        self.enabled = False
        try:
            if PYGAME_AVAILABLE:
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
                self.enabled = True
                self.sounds = {}
                self._load_sounds()
            else:
                print("Pygame module not found. Audio disabled.")
        except Exception as e:
            print(f"Audio init failed: {e}")
            self.enabled = False

    def _load_sounds(self):
        if not os.path.exists("_sfx/bgm.wav"):
            try:
                import SoundGenerator
                print("Generating SFX...")
                SoundGenerator.generate_all()
            except ImportError:
                print("SoundGenerator not available, skipping SFX generation.")

        sfx_files = {
            'move':     '_sfx/move.wav',
            'rotate':   '_sfx/rotate.wav',
            'drop':     '_sfx/drop.wav',
            'line':     '_sfx/line.wav',
            'gameover': '_sfx/gameover.wav',
        }
        for name, path in sfx_files.items():
            if os.path.exists(path):
                try:
                    self.sounds[name] = pygame.mixer.Sound(path)
                except:
                    print(f"Failed to load {path}")

        if os.path.exists("_sfx/bgm.wav"):
            try:
                pygame.mixer.music.load("_sfx/bgm.wav")
                pygame.mixer.music.set_volume(0.5)
            except:
                print("Failed to load BGM")

    def play(self, name):
        if not self.enabled: return
        if name in self.sounds:
            try: self.sounds[name].play()
            except: pass

    def start_bgm(self):
        if not self.enabled: return
        try:
            if not pygame.mixer.music.get_busy():
                pygame.mixer.music.play(-1)
        except: pass

    def stop_bgm(self):
        if not self.enabled: return
        try: pygame.mixer.music.stop()
        except: pass


# ---------------------------------------------------------------------------
# Game Data Classes
# ---------------------------------------------------------------------------

class Projectile:
    TRAIL_LENGTH = 4

    def __init__(self, x, y, team_id):
        self.x = x
        self.y = y
        self.team_id = team_id   # 'A' or 'B'
        self.active = True
        self.trail = []   # list of (x, y) — oldest first


class PowerUp:
    def __init__(self, x, y, ptype):
        self.x = x
        self.y = y
        self.ptype = ptype
        self.created_time = time.time()
        self.active = True


class TeamData:
    def __init__(self, team_id, color, base_row, direction, input_y):
        self.team_id = team_id
        self.color = color
        self.base_row = base_row
        self.direction = direction   # +1 (down) for A, -1 (up) for B
        self.input_y   = input_y    # board y-row where this team's buttons live
        self.score               = 0
        self.effect_speed_until  = None
        self.effect_rapid_until  = None
        self.effect_double_until = None

    def led_idx_for_col(self, col):
        """Return global button_states index for this team's button row at column col."""
        return global_btn_idx(self.input_y, col)

    def reset(self):
        self.score               = 0
        self.effect_speed_until  = None
        self.effect_rapid_until  = None
        self.effect_double_until = None


# ---------------------------------------------------------------------------
# Main Game Engine
# ---------------------------------------------------------------------------

class BattleGame:
    def __init__(self):
        self.sound = SoundManager()
        self.lock  = threading.RLock()
        self.running = True
        self.state = 'STARTUP'   # LOBBY | STARTUP | PLAYING | GAMEOVER

        # Hardware input state (written by NetworkManager.recv_loop)
        # Indexed as channel*64 + local_led_idx  (512 total)
        self.button_states      = [False] * BUTTON_STATES_SIZE
        self.prev_button_states = [False] * BUTTON_STATES_SIZE

        # Game objects
        self.projectiles = []
        self.power_ups   = []
        self.explosions  = []    # {'x','y','color','start'}
        self.ripples     = []    # {'x','y','color','start'}

        # Team A (RED)  — top,    shoots DOWN (+1), buttons at y=1
        # Team B (BLUE) — bottom, shoots UP   (-1), buttons at y=30
        self.teams = {
            'A': TeamData('A', RED,  TEAM_A_BASE_ROW, +1, TEAM_A_INPUT_ROW),
            'B': TeamData('B', BLUE, TEAM_B_BASE_ROW, -1, TEAM_B_INPUT_ROW),
        }

        # Double-press state per (team_id, col):
        # {'state': 'idle'|'first'|'released', 'first_press_time': float}
        self.col_press_states = {}

        # Timers
        self.last_proj_tick     = {'A': 0.0, 'B': 0.0}
        self.last_powerup_spawn = 0.0
        self.startup_step       = 0
        self.startup_timer      = time.time()
        self.game_over_timer    = 0.0
        self.game_start_time    = 0.0
        self.last_console_print = 0.0   # for throttled time-remaining prints

    # -----------------------------------------------------------------------
    # Game lifecycle
    # -----------------------------------------------------------------------

    def start_game(self):
        with self.lock:
            for team in self.teams.values():
                team.reset()
            self.projectiles = []
            self.power_ups   = []
            self.explosions  = []
            self.ripples     = []
            self.col_press_states = {}
            now = time.time()
            self.last_proj_tick     = {'A': now, 'B': now}
            self.last_powerup_spawn = now
            self.game_start_time    = 0.0   # set when PLAYING actually begins
            self.last_console_print = 0.0
            self.sound.start_bgm()
            self.state         = 'STARTUP'
            self.startup_step  = 0
            self.startup_timer = now

    def restart_round(self):
        self.start_game()

    # -----------------------------------------------------------------------
    # Main tick
    # -----------------------------------------------------------------------

    def tick(self):
        with self.lock:
            if self.state == 'LOBBY':
                self._lobby_check_start()
                return

            if self.state == 'STARTUP':
                self._tick_startup()
                return

            if self.state == 'GAMEOVER':
                self._tick_gameover()
                return

            # --- PLAYING ---
            now = time.time()
            elapsed = now - self.game_start_time

            # 5-minute time limit
            if elapsed >= GAME_DURATION:
                print("TIME'S UP! Game over.")
                self.state           = 'GAMEOVER'
                self.game_over_timer = now
                self.sound.play('gameover')
                self.sound.stop_bgm()
                return

            # Console countdown every 30 seconds
            if now - self.last_console_print >= 30.0:
                remaining = int(GAME_DURATION - elapsed)
                print(f"Time remaining: {remaining // 60}m {remaining % 60}s")
                self.last_console_print = now

            self.process_inputs()
            self._expire_effects()
            self.move_projectiles()
            self.handle_collisions()
            self.spawn_power_up()
            # Expire old power-ups by lifetime
            self.power_ups = [
                pu for pu in self.power_ups
                if pu.active and (now - pu.created_time) < POWERUP_LIFETIME
            ]
            # Expire finished explosions and ripples
            self.explosions = [e for e in self.explosions if now - e['start'] < 0.45]
            self.ripples    = [r for r in self.ripples    if now - r['start'] < 0.60]

    def _lobby_check_start(self):
        for i in range(BUTTON_STATES_SIZE):
            if self.button_states[i] and not self.prev_button_states[i]:
                # Update prev before starting so we don't double-trigger
                for j in range(BUTTON_STATES_SIZE):
                    self.prev_button_states[j] = self.button_states[j]
                self.start_game()
                return
        for i in range(BUTTON_STATES_SIZE):
            self.prev_button_states[i] = self.button_states[i]

    def _tick_startup(self):
        now = time.time()
        delay = 0.2 if self.startup_step < 5 else 1.0
        if now - self.startup_timer > delay:
            self.startup_step += 1
            self.startup_timer = now
            if self.startup_step >= 10:
                print("FIGHT! Game Starting — 5 minutes on the clock!")
                self.state = 'PLAYING'
                now2 = time.time()
                self.last_proj_tick     = {'A': now2, 'B': now2}
                self.last_powerup_spawn = now2
                self.game_start_time    = now2
                self.last_console_print = now2

    def _tick_gameover(self):
        now = time.time()
        # Blink "TIME" on the board every 0.5s
        if now - self.game_over_timer > 0.5:
            self.game_over_timer = now

        # Allow restart via any button press after 3 seconds of GAMEOVER
        if now - self.game_over_timer > 3.0:
            for i in range(BUTTON_STATES_SIZE):
                if self.button_states[i] and not self.prev_button_states[i]:
                    for j in range(BUTTON_STATES_SIZE):
                        self.prev_button_states[j] = self.button_states[j]
                    self.restart_round()
                    return
        for i in range(BUTTON_STATES_SIZE):
            self.prev_button_states[i] = self.button_states[i]

    # -----------------------------------------------------------------------
    # Input processing — double-press state machine
    # -----------------------------------------------------------------------

    def process_inputs(self):
        now = time.time()

        for team_id in ('A', 'B'):
            team = self.teams[team_id]
            for col in range(BOARD_WIDTH):
                led_idx = team.led_idx_for_col(col)
                is_pressed  = self.button_states[led_idx]
                was_pressed = self.prev_button_states[led_idx]
                fresh_press = is_pressed and not was_pressed

                key = (team_id, col)
                ps = self.col_press_states.get(key, {'state': 'idle', 'first_press_time': 0.0})

                if ps['state'] == 'idle':
                    if fresh_press:
                        rapid_on = team.effect_rapid_until and now < team.effect_rapid_until
                        if rapid_on:
                            self.fire_projectile(team_id, col)
                            # stay idle — next press also fires immediately
                        else:
                            ps = {'state': 'first', 'first_press_time': now}

                elif ps['state'] == 'first':
                    # Timeout check
                    if now - ps['first_press_time'] > DOUBLE_PRESS_TIMEOUT:
                        ps = {'state': 'idle', 'first_press_time': 0.0}
                    # Released transition
                    elif not is_pressed and was_pressed:
                        ps['state'] = 'released'

                elif ps['state'] == 'released':
                    # Timeout check
                    if now - ps['first_press_time'] > DOUBLE_PRESS_TIMEOUT:
                        ps = {'state': 'idle', 'first_press_time': 0.0}
                    elif fresh_press:
                        if now - ps['first_press_time'] <= DOUBLE_PRESS_WINDOW:
                            self.fire_projectile(team_id, col)
                        ps = {'state': 'idle', 'first_press_time': 0.0}

                self.col_press_states[key] = ps

        # Update prev states after all evaluations
        for i in range(BUTTON_STATES_SIZE):
            self.prev_button_states[i] = self.button_states[i]

    def fire_projectile(self, team_id, col):
        team = self.teams[team_id]
        now  = time.time()

        # Projectile starts AT the launcher bar so it visually "comes out of" the pressed cube.
        # Team A (top, row 0) bar at row 1 — projectile starts at row 1, moves DOWN (+1)
        # Team B (bottom, row 31) bar at row 30 — projectile starts at row 30, moves UP (-1)
        if team_id == 'A':
            start_y = LAUNCHER_ROW_A        # row 1
        else:
            start_y = LAUNCHER_ROW_B        # row 30

        double_on = team.effect_double_until and now < team.effect_double_until

        if double_on:
            for dx in (-1, +1):
                nx = col + dx
                if 0 <= nx < BOARD_WIDTH:
                    self.projectiles.append(Projectile(nx, start_y, team_id))
        else:
            self.projectiles.append(Projectile(col, start_y, team_id))

        self.sound.play('move')

    # -----------------------------------------------------------------------
    # Projectile movement
    # -----------------------------------------------------------------------

    def move_projectiles(self):
        now = time.time()

        for team_id in ('A', 'B'):
            team = self.teams[team_id]

            # Halve interval if SPEED active
            interval = PROJECTILE_TICK_INTERVAL
            if team.effect_speed_until and now < team.effect_speed_until:
                interval = PROJECTILE_TICK_INTERVAL / 2.0

            if now - self.last_proj_tick[team_id] < interval:
                continue
            self.last_proj_tick[team_id] = now

            for proj in self.projectiles:
                if not proj.active or proj.team_id != team_id:
                    continue

                # Cross-collision: check if the destination cell holds an opposing projectile
                next_y = proj.y + team.direction
                for opp in self.projectiles:
                    if opp.active and opp.team_id != team_id and opp.x == proj.x and opp.y == next_y:
                        proj.active = False
                        opp.active = False
                        break
                if not proj.active:
                    continue

                proj.trail.append((proj.x, proj.y))
                if len(proj.trail) > Projectile.TRAIL_LENGTH:
                    proj.trail.pop(0)
                proj.y += team.direction

                # Check power-up collection — projectile overlaps any cell of the 2×2 block
                for pu in self.power_ups:
                    if pu.active and pu.x <= proj.x <= pu.x + 1 and pu.y <= proj.y <= pu.y + 1:
                        self._apply_powerup(team_id, pu.ptype)
                        self.explosions.append({
                            'x': pu.x, 'y': pu.y,
                            'color': PTYPE_COLORS[pu.ptype],
                            'start': time.time()
                        })
                        pu.active = False
                        self.sound.play('rotate')
                        break

                # Did projectile reach the enemy base or exit the board?
                # Team A shoots down → scores when proj.y >= TEAM_B_BASE_ROW (31)
                # Team B shoots up  → scores when proj.y <= TEAM_A_BASE_ROW (0)
                if team_id == 'A' and proj.y >= TEAM_B_BASE_ROW:
                    proj.active = False
                    self.teams['A'].score += 1
                    self.ripples.append({'x': proj.x, 'y': TEAM_B_BASE_ROW, 'color': RED,  'start': time.time()})
                    print(f"SCORE — Team A: {self.teams['A'].score}  Team B: {self.teams['B'].score}")
                    self.sound.play('line')
                elif team_id == 'B' and proj.y <= TEAM_A_BASE_ROW:
                    proj.active = False
                    self.teams['B'].score += 1
                    self.ripples.append({'x': proj.x, 'y': TEAM_A_BASE_ROW, 'color': BLUE, 'start': time.time()})
                    print(f"SCORE — Team A: {self.teams['A'].score}  Team B: {self.teams['B'].score}")
                    self.sound.play('line')
                elif proj.y < 0 or proj.y >= BOARD_HEIGHT:
                    proj.active = False

        # Remove inactive projectiles
        self.projectiles = [p for p in self.projectiles if p.active]

    # -----------------------------------------------------------------------
    # Collision detection
    # -----------------------------------------------------------------------

    def handle_collisions(self):
        pos_a = {}
        pos_b = {}
        for proj in self.projectiles:
            if not proj.active:
                continue
            key = (proj.x, proj.y)
            if proj.team_id == 'A':
                pos_a[key] = proj
            else:
                pos_b[key] = proj

        for key in pos_a:
            if key in pos_b:
                pos_a[key].active = False
                pos_b[key].active = False

        self.projectiles = [p for p in self.projectiles if p.active]

    # -----------------------------------------------------------------------
    # Power-up management
    # -----------------------------------------------------------------------

    def spawn_power_up(self):
        now = time.time()
        if now - self.last_powerup_spawn < POWERUP_SPAWN_INTERVAL:
            return
        self.last_powerup_spawn = now

        # Expire dead power-ups first
        self.power_ups = [
            pu for pu in self.power_ups
            if pu.active and (now - pu.created_time) < POWERUP_LIFETIME
        ]

        if len(self.power_ups) >= MAX_POWERUPS_ON_BOARD:
            return

        occupied = set()
        for pu in self.power_ups:
            for dx in range(2):
                for dy in range(2):
                    occupied.add((pu.x + dx, pu.y + dy))
        for _ in range(20):
            x = random.randint(0, BOARD_WIDTH - 2)          # leave room for x+1
            y = random.randint(POWERUP_SPAWN_ROW_MIN, POWERUP_SPAWN_ROW_MAX - 1)  # leave room for y+1
            if (x, y) not in occupied and (x+1, y) not in occupied and \
               (x, y+1) not in occupied and (x+1, y+1) not in occupied:
                ptype = random.choice([PTYPE_SPEED, PTYPE_RAPID, PTYPE_DOUBLE])
                self.power_ups.append(PowerUp(x, y, ptype))
                names = {PTYPE_SPEED: 'SPEED', PTYPE_RAPID: 'RAPID', PTYPE_DOUBLE: 'DOUBLE'}
                print(f"Power-up spawned: {names[ptype]} at ({x},{y})")
                break

    def _apply_powerup(self, team_id, ptype):
        now    = time.time()
        team   = self.teams[team_id]
        expiry = now + POWERUP_EFFECT_DURATION
        if ptype == PTYPE_SPEED:
            team.effect_speed_until  = expiry
            print(f"Team {team_id} got SPEED boost!")
        elif ptype == PTYPE_RAPID:
            team.effect_rapid_until  = expiry
            print(f"Team {team_id} got RAPID FIRE!")
        elif ptype == PTYPE_DOUBLE:
            team.effect_double_until = expiry
            print(f"Team {team_id} got DOUBLE SHOT!")

    def _expire_effects(self):
        now = time.time()
        for team in self.teams.values():
            if team.effect_speed_until  and now > team.effect_speed_until:
                team.effect_speed_until  = None
            if team.effect_rapid_until  and now > team.effect_rapid_until:
                team.effect_rapid_until  = None
            if team.effect_double_until and now > team.effect_double_until:
                team.effect_double_until = None

    # -----------------------------------------------------------------------
    # Rendering helpers
    # -----------------------------------------------------------------------

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
            buffer[offset]                  = color[1]  # GREEN (hardware swap)
            buffer[offset + NUM_CHANNELS]   = color[0]  # RED
            buffer[offset + NUM_CHANNELS*2] = color[2]  # BLUE

    def draw_glyph(self, buffer, key, ox, oy, color):
        if key not in FONT: return
        for dx, dy in FONT[key]:
            self.set_led(buffer, ox + dx, oy + dy, color)

    def _render_effect_indicators(self, buffer, now):
        """Draw colored dots on the launcher bar to show active power-up effects."""
        for team_id in ('A', 'B'):
            team = self.teams[team_id]
            indicator_y = LAUNCHER_ROW_A if team_id == 'A' else LAUNCHER_ROW_B
            if team.effect_speed_until  and now < team.effect_speed_until:
                self.set_led(buffer, 0, indicator_y, YELLOW)
            if team.effect_rapid_until  and now < team.effect_rapid_until:
                self.set_led(buffer, 1, indicator_y, GREEN)
            if team.effect_double_until and now < team.effect_double_until:
                self.set_led(buffer, 2, indicator_y, MAGENTA)

    def _render_input_bar_highlight(self, buffer, now):
        """Show first-press highlights in each team's launcher bar row."""
        for team_id in ('A', 'B'):
            launcher_y   = LAUNCHER_ROW_A if team_id == 'A' else LAUNCHER_ROW_B
            dim_color    = DIM_RED  if team_id == 'A' else DIM_BLUE
            bright_color = RED      if team_id == 'A' else BLUE

            for col in range(BOARD_WIDTH):
                key = (team_id, col)
                ps  = self.col_press_states.get(key, {'state': 'idle'})
                color = bright_color if ps['state'] in ('first', 'released') else dim_color
                self.set_led(buffer, col, launcher_y, color)

    # -----------------------------------------------------------------------
    # Render
    # -----------------------------------------------------------------------

    def render(self):
        buffer = bytearray(FRAME_DATA_LENGTH)
        now = time.time()

        # ---------- LOBBY ----------
        if self.state == 'LOBBY':
            # Pulsing separator at mid-board
            if int(now * 2) % 2 == 0:
                for x in range(BOARD_WIDTH):
                    self.set_led(buffer, x, 15, WHITE)
                    self.set_led(buffer, x, 16, WHITE)
            # Team base rows
            for x in range(BOARD_WIDTH):
                self.set_led(buffer, x, TEAM_A_BASE_ROW, DIM_RED)
                self.set_led(buffer, x, TEAM_B_BASE_ROW, DIM_BLUE)
            # Team labels in the neutral zone
            self.draw_glyph(buffer, 'A', 6,  3, RED)
            self.draw_glyph(buffer, 'B', 6, 24, BLUE)
            # Pulsing "press to start" on launcher bars
            if int(now * 3) % 2 == 0:
                for x in range(BOARD_WIDTH):
                    self.set_led(buffer, x, LAUNCHER_ROW_A, DIM_RED)
                    self.set_led(buffer, x, LAUNCHER_ROW_B, DIM_BLUE)
            return buffer

        # ---------- STARTUP ----------
        if self.state == 'STARTUP':
            step = self.startup_step
            # Base rows always visible
            for x in range(BOARD_WIDTH):
                self.set_led(buffer, x, TEAM_A_BASE_ROW, RED)
                self.set_led(buffer, x, TEAM_B_BASE_ROW, BLUE)
            # Launcher bars dim
            for x in range(BOARD_WIDTH):
                self.set_led(buffer, x, LAUNCHER_ROW_A, DIM_RED)
                self.set_led(buffer, x, LAUNCHER_ROW_B, DIM_BLUE)
            # Countdown digits centred in neutral zone (steps 5-9: 5,4,3,2,1)
            if 5 <= step <= 9:
                num = 5 - (step - 5)
                self.draw_glyph(buffer, num, 6, 13, WHITE)
            return buffer

        # ---------- GAMEOVER ----------
        if self.state == 'GAMEOVER':
            # Flash "TIME" — alternate between white and dim grey
            flash_on   = int((now - self.game_over_timer) * 2) % 2 == 0
            text_color = WHITE if flash_on else (40, 40, 40)

            # "TIME" spelled across the board centre
            # T-I-M-E each 3 wide + 1 gap = 15 columns, starting at x=0
            # Draw as individual letters using FONT glyphs
            # We'll use I, N glyph pieces to approximate — or use raw pixels
            # Simple: draw the word TIME as coloured rows
            # Use available FONT glyphs: reuse digit shapes for letters
            # Row 12-16 for text area
            self.draw_glyph(buffer, 'I',  0, 13, text_color)   # T (approximate with I)
            self.draw_glyph(buffer, 'I',  4, 13, text_color)
            self.draw_glyph(buffer, 'I',  8, 13, text_color)
            self.draw_glyph(buffer, 'N', 12, 13, text_color)

            # Base rows dim
            for x in range(BOARD_WIDTH):
                self.set_led(buffer, x, TEAM_A_BASE_ROW, DIM_RED)
                self.set_led(buffer, x, TEAM_B_BASE_ROW, DIM_BLUE)
            return buffer

        # ---------- PLAYING ----------
        if self.state == 'PLAYING':
            with self.lock:
                # 1. Team base rows (solid color)
                for x in range(BOARD_WIDTH):
                    self.set_led(buffer, x, TEAM_A_BASE_ROW, RED)
                    self.set_led(buffer, x, TEAM_B_BASE_ROW, BLUE)

                # 2. Draw power-ups in neutral zone (2×2 blocks)
                for pu in self.power_ups:
                    if not pu.active:
                        continue
                    remaining = POWERUP_LIFETIME - (now - pu.created_time)
                    if remaining < 5.0 and int(now * 4) % 2 == 0:
                        continue  # blink off near expiry
                    color = PTYPE_COLORS[pu.ptype]
                    for dx in range(2):
                        for dy in range(2):
                            self.set_led(buffer, pu.x + dx, pu.y + dy, color)

                # 2b. Draw explosion animations
                for exp in self.explosions:
                    elapsed = now - exp['start']
                    cx, cy  = exp['x'], exp['y']
                    if elapsed < 0.15:
                        # Frame 1: 2×2 white flash
                        for dx in range(2):
                            for dy in range(2):
                                self.set_led(buffer, cx + dx, cy + dy, WHITE)
                    elif elapsed < 0.30:
                        # Frame 2: 4×4 ring in power-up color
                        for dx in range(-1, 3):
                            for dy in range(-1, 3):
                                self.set_led(buffer, cx + dx, cy + dy, exp['color'])
                    else:
                        # Frame 3: 6×6 dim fade-out
                        dim = tuple(c // 4 for c in exp['color'])
                        for dx in range(-2, 4):
                            for dy in range(-2, 4):
                                self.set_led(buffer, cx + dx, cy + dy, dim)

                # 3. Draw projectile trails then projectiles
                for proj in self.projectiles:
                    if not proj.active:
                        continue
                    color = self.teams[proj.team_id].color
                    # Trail: oldest = dimmest, newest = brightest
                    for i, (tx, ty) in enumerate(proj.trail):
                        factor = (i + 1) / (Projectile.TRAIL_LENGTH + 1)
                        tc = tuple(int(c * factor * 0.6) for c in color)
                        self.set_led(buffer, tx, ty, tc)
                    self.set_led(buffer, proj.x, proj.y, color)

                # 3b. Draw score ripples (expand horizontally along the base row)
                for rip in self.ripples:
                    elapsed = now - rip['start']
                    radius  = int(elapsed / 0.06)   # grows 1 cell every 60ms
                    cx, cy  = rip['x'], rip['y']
                    brightness = max(0.0, 1.0 - elapsed / 0.60)
                    rc = tuple(int(c * brightness) for c in rip['color'])
                    for dx in range(-radius, radius + 1):
                        self.set_led(buffer, cx + dx, cy, rc)

                # 4. Launcher bar highlights (first-press pending state)
                self._render_input_bar_highlight(buffer, now)

                # 5. Active power-up effect indicators on launcher bars


            return buffer

        return buffer


# ---------------------------------------------------------------------------
# Network Manager (unchanged from Tetris_Game.py)
# ---------------------------------------------------------------------------

class NetworkManager:
    def __init__(self, game):
        self.game = game
        self.sock_send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_send.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock_recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.running = True
        self.sequence_number = 0
        self.prev_button_states = [False] * BUTTON_STATES_SIZE

        bind_ip = CONFIG.get("bind_ip", "0.0.0.0")
        if bind_ip != "0.0.0.0":
            try:
                self.sock_send.bind((bind_ip, 0))
            except Exception as e:
                print(f"Warning: Could not bind send socket to {bind_ip}: {e}")

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
        self.sequence_number = (self.sequence_number + 1) & 0xFFFF
        if self.sequence_number == 0: self.sequence_number = 1

        target_ip = UDP_SEND_IP
        port      = UDP_SEND_PORT

        # 1. Start Packet
        rand1 = random.randint(0, 127)
        rand2 = random.randint(0, 127)
        start_packet = bytearray([
            0x75, rand1, rand2, 0x00, 0x08,
            0x02, 0x00, 0x00, 0x33, 0x44,
            (self.sequence_number >> 8) & 0xFF,
            self.sequence_number & 0xFF,
            0x00, 0x00, 0x00
        ])
        start_packet.append(0x0E)
        start_packet.append(0x00)
        try:
            self.sock_send.sendto(start_packet, (target_ip, port))
            self.sock_send.sendto(start_packet, ("127.0.0.1", port))
        except: pass

        # 2. FFF0 Packet
        rand1 = random.randint(0, 127)
        rand2 = random.randint(0, 127)
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
        fff0_packet.append(0x1E)
        fff0_packet.append(0x00)
        try:
            self.sock_send.sendto(fff0_packet, (target_ip, port))
            self.sock_send.sendto(fff0_packet, ("127.0.0.1", port))
        except: pass

        # 3. Data Packets
        chunk_size       = 984
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
            ]) + chunk
            payload_len = len(internal_data) - 1
            packet = bytearray([
                0x75, rand1, rand2,
                (payload_len >> 8) & 0xFF, (payload_len & 0xFF)
            ]) + internal_data
            packet.append(0x1E if len(chunk) == 984 else 0x36)
            packet.append(0x00)
            try:
                self.sock_send.sendto(packet, (target_ip, port))
                self.sock_send.sendto(packet, ("127.0.0.1", port))
            except: pass
            data_packet_index += 1
            time.sleep(0.005)

        # 4. End Packet
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
        except: pass

    def recv_loop(self):
        while self.running:
            try:
                data, _ = self.sock_recv.recvfrom(2048)
                if len(data) >= 1373 and data[0] == 0x88:
                    for ch in range(NUM_CHANNELS):
                        ch_offset = 2 + ch * 171 + 1
                        ch_data   = data[ch_offset: ch_offset + 170]
                        base      = ch * 64
                        for local_idx, val in enumerate(ch_data):
                            if local_idx >= 64: break
                            self.game.button_states[base + local_idx] = (val == 0xCC)
            except Exception:
                pass

    def start_bg(self):
        t1 = threading.Thread(target=self.send_loop)
        t2 = threading.Thread(target=self.recv_loop)
        t1.daemon = True
        t2.daemon = True
        t1.start()
        t2.start()


# ---------------------------------------------------------------------------
# Game thread
# ---------------------------------------------------------------------------

def game_thread_func(game):
    while game.running:
        game.tick()
        time.sleep(0.01)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    game = BattleGame()
    net  = NetworkManager(game)
    net.start_bg()

    gt = threading.Thread(target=game_thread_func, args=(game,))
    gt.daemon = True
    gt.start()

    print("Battle Blaster Server Running.")
    print("Commands: 'start', 'restart', 'quit'")
    print("Or press any button on the hardware to start from LOBBY.")

    try:
        while game.running:
            cmd = input("> ").strip().lower()
            if cmd in ('quit', 'exit'):
                game.running = False
            elif cmd == 'start':
                game.start_game()
                print("Game started.")
            elif cmd == 'restart':
                game.restart_round()
                print("Round restarted.")
            else:
                print("Unknown command. Use: start | restart | quit")
    except KeyboardInterrupt:
        game.running = False

    net.running = False
    print("Exiting...")
