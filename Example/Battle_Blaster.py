import socket
import struct
import time
import threading
import random
import copy
import psutil
import os
import math
import array as _array

import json
import tkinter as tk
from tkinter import font as tkfont

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
        "send_port": 4626,
        "recv_port": 7800,
        "bind_ip": "0.0.0.0",
        "bgm_path": "_sfx/bgm.wav"
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

# --- Background Music ---
BGM_FILENAME = "Lady Gaga - Judas (Lyrics) - bemu (128k).wav"
BGM_VOLUME   = 0.7   # 0.0 = silent, 1.0 = full volume

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
    'E': [(0,0),(1,0),(2,0),(0,1),(0,2),(1,2),(0,3),(0,4),(1,4),(2,4)],
    'D': [(0,0),(1,0),(0,1),(2,1),(0,2),(2,2),(0,3),(2,3),(0,4),(1,4)],
}

# --- Battle Blaster Game Constants ---
GAME_DURATION           = 120     # 2 minutes in seconds
FIRE_COOLDOWN           = 0.7     # seconds lockout per column after firing
PROJECTILE_TICK_INTERVAL = 0.075  # seconds between projectile steps (doubled speed)
POWERUP_SPAWN_INTERVAL  = 4.0     # seconds between spawns
POWERUP_LIFETIME        = 30.0    # seconds power-up stays on board
POWERUP_EFFECT_DURATION = 15.0    # seconds collected effect lasts
MAX_POWERUPS_ON_BOARD   = 3
POWERUP_SPAWN_ROW_MIN   = 2       # keep clear of first/last 2 rows
POWERUP_SPAWN_ROW_MAX   = 29


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
PTYPE_SPEED   = 1   # Yellow  — 2× projectile speed for 15s
PTYPE_DOUBLE  = 3   # Magenta — fire 2 projectiles (col±1) for 15s
PTYPE_ULTIMATE = 4  # Red 1×1 — unblockable 3-point shot

VIOLET   = (148, 0, 211)
DARK_RED = (139, 0,   0)

PTYPE_COLORS = {
    PTYPE_SPEED:    YELLOW,
    PTYPE_DOUBLE:   MAGENTA,
    PTYPE_ULTIMATE: RED,
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

    # ------------------------------------------------------------------ #
    #  Pure-Python audio synthesis helpers                                #
    # ------------------------------------------------------------------ #
    _SR = 44100   # sample rate

    def _build_sound(self, freqs_amps, duration,
                     env_attack=0.008, env_decay=3.0,
                     reverb=None, echo=None,
                     distort=False, master=0.72):
        """
        Synthesise a stereo 16-bit pygame.mixer.Sound.

        freqs_amps : list of (hz, amplitude)   – summed sine waves
        duration   : seconds
        env_attack : attack time in seconds
        env_decay  : exponential decay rate  (higher = faster fade)
        reverb     : list of (delay_sec, gain) pairs
        echo       : (delay_sec, gain) single echo tap
        distort    : apply soft-clip distortion (power chord grit)
        master     : final volume scalar 0..1
        """
        SR  = self._SR
        N   = int(SR * duration)
        sig = [0.0] * N

        # Mix sine waves
        for freq, amp in freqs_amps:
            for i in range(N):
                t   = i / SR
                env = (1.0 - math.exp(-t / max(env_attack, 1e-6))) * math.exp(-env_decay * t)
                sig[i] += amp * env * math.sin(2.0 * math.pi * freq * t)

        # Soft-clip distortion (tanh approximation)
        if distort:
            drive = 2.5
            for i in range(N):
                x = sig[i] * drive
                # fast tanh via rational approx
                if   x >  1.0: sig[i] =  1.0
                elif x < -1.0: sig[i] = -1.0
                else:          sig[i] = x * (27.0 + x*x) / (27.0 + 9.0*x*x)

        # Reverb (comb: multiple delay taps)
        if reverb:
            wet = [0.0] * N
            for delay_sec, gain in reverb:
                d = int(SR * delay_sec)
                for i in range(d, N):
                    wet[i] += sig[i - d] * gain
            for i in range(N):
                sig[i] += wet[i]

        # Echo (single distinct repeat)
        if echo:
            delay_sec, gain = echo
            d = int(SR * delay_sec)
            for i in range(d, N):
                sig[i] += sig[i - d] * gain

        # Normalise → 16-bit stereo interleaved
        peak = max(abs(s) for s in sig) or 1.0
        scale = master * 32767.0 / peak
        buf = _array.array('h', [0] * (N * 2))
        for i in range(N):
            v = int(sig[i] * scale)
            v = max(-32768, min(32767, v))
            buf[i * 2]     = v
            buf[i * 2 + 1] = v
        return pygame.mixer.Sound(buffer=buf)

    def _synth_hit(self):
        """Low, bassy impact + heavy reverb — projectile vs projectile."""
        return self._build_sound(
            freqs_amps=[(90, 0.9), (55, 0.7), (140, 0.4), (180, 0.2)],
            duration=0.9,
            env_attack=0.003, env_decay=5.5,
            reverb=[(0.018, 0.55), (0.035, 0.38), (0.065, 0.22), (0.11, 0.12)],
            master=0.80,
        )

    def _synth_powerup(self):
        """Lower-register chime + warm reverb — collect a regular power-up."""
        return self._build_sound(
            freqs_amps=[(130, 0.8), (195, 0.5), (260, 0.3)],
            duration=0.8,
            env_attack=0.010, env_decay=4.0,
            reverb=[(0.022, 0.50), (0.048, 0.28), (0.090, 0.14)],
            master=0.70,
        )

    def _synth_score(self):
        """Deep resonant thud + reverb tail — a point scored."""
        return self._build_sound(
            freqs_amps=[(75, 0.9), (112, 0.5), (50, 0.6)],
            duration=1.0,
            env_attack=0.005, env_decay=4.5,
            reverb=[(0.025, 0.55), (0.055, 0.32), (0.100, 0.18)],
            master=0.78,
        )

    def _synth_launch(self):
        """Deep sub-bass cannon thump — projectile fires."""
        return self._build_sound(
            freqs_amps=[(42, 0.9), (28, 0.8), (68, 0.5), (95, 0.3)],
            duration=0.55,
            env_attack=0.004, env_decay=7.0,
            reverb=[(0.016, 0.45), (0.034, 0.25), (0.060, 0.12)],
            master=0.82,
        )

    def _synth_ultimate_hit(self):
        """Massive deep explosion + heavy reverb + long echo — sphere/slash impact."""
        return self._build_sound(
            freqs_amps=[(38, 0.9), (55, 0.75), (27, 0.8), (80, 0.5), (110, 0.35), (160, 0.25)],
            duration=2.0,
            env_attack=0.003, env_decay=1.6,
            reverb=[(0.020, 0.65), (0.045, 0.48), (0.090, 0.32), (0.160, 0.20), (0.250, 0.12)],
            echo=(0.280, 0.55),
            distort=True,
            master=0.85,
        )

    def _synth_ultimate(self):
        """Power chord (E2 + B2 + E3) with distortion, reverb & echo — ultimate fires."""
        # E2=82 Hz, B2=123 Hz, E3=164 Hz, add sub-octave at 41 Hz
        return self._build_sound(
            freqs_amps=[(82, 0.7), (123, 0.65), (164, 0.55), (41, 0.45), (246, 0.30)],
            duration=1.4,
            env_attack=0.006, env_decay=1.8,
            reverb=[(0.018, 0.60), (0.040, 0.42), (0.080, 0.26), (0.130, 0.15)],
            echo=(0.170, 0.52),
            distort=True,
            master=0.75,
        )

    # ------------------------------------------------------------------ #

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
            'drop':     '_sfx/drop.wav',
            'gameover': '_sfx/gameover.wav',
        }
        for name, path in sfx_files.items():
            if os.path.exists(path):
                try:
                    self.sounds[name] = pygame.mixer.Sound(path)
                except:
                    print(f"Failed to load {path}")

        # Synthesised sounds — generated fresh at startup
        try:
            print("Synthesising SFX...")
            self.sounds['move']         = self._synth_launch()
            self.sounds['hit']          = self._synth_hit()
            self.sounds['powerup']      = self._synth_powerup()
            self.sounds['score']        = self._synth_score()
            self.sounds['ultimate_sfx'] = self._synth_ultimate()
            self.sounds['ultimate_hit'] = self._synth_ultimate_hit()
            print("SFX synthesis complete.")
        except Exception as e:
            print(f"SFX synthesis failed: {e}")

        _sfx_dir  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_sfx")
        BGM_PATH  = os.path.join(_sfx_dir, BGM_FILENAME)
        if os.path.exists(BGM_PATH):
            try:
                pygame.mixer.music.load(BGM_PATH)
                pygame.mixer.music.set_volume(BGM_VOLUME)
                print(f"BGM loaded OK: {BGM_PATH}")
            except Exception as e:
                print(f"Failed to load BGM as WAV ({e}), trying as MP3...")
                try:
                    mp3_path = BGM_PATH.replace(".wav", ".mp3")
                    # Try loading the .wav path directly via pygame (it handles mp3 too)
                    pygame.mixer.music.load(BGM_PATH)
                    pygame.mixer.music.set_volume(BGM_VOLUME)
                    print("BGM loaded OK as MP3")
                except Exception as e2:
                    print(f"BGM load failed entirely: {e2}")
        else:
            print(f"BGM file not found: {BGM_PATH}")

    def play(self, name):
        if not self.enabled: return
        if name in self.sounds:
            try: self.sounds[name].play()
            except: pass

    def start_bgm(self):
        if not self.enabled: return
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.play(-1)
            print("BGM playback started.")
        except Exception as e:
            print(f"BGM play failed: {e}")

    def stop_bgm(self):
        if not self.enabled: return
        try: pygame.mixer.music.stop()
        except: pass


# ---------------------------------------------------------------------------
# Game Data Classes
# ---------------------------------------------------------------------------

class Projectile:
    TRAIL_LENGTH = 4

    def __init__(self, x, y, team_id, unblockable=False, points=1, shape='normal'):
        self.x = x
        self.y = y
        self.team_id     = team_id      # 'A' or 'B'
        self.active      = True
        self.trail       = []           # list of (x, y) — oldest first
        self.unblockable = unblockable
        self.points      = points
        self.shape       = shape        # 'normal' | 'sphere' | 'slash'
        self.created_at  = time.time()


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
        self.effect_double_until = None

    def led_idx_for_col(self, col):
        """Return global button_states index for this team's button row at column col."""
        return global_btn_idx(self.input_y, col)

    def reset(self):
        self.score               = 0
        self.effect_speed_until  = None
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

        # Timers
        self.last_proj_tick     = {'A': 0.0, 'B': 0.0}
        self.last_powerup_spawn = 0.0
        self.last_fire_time     = {}
        self.startup_step       = 0
        self.startup_timer      = time.time()
        self.game_over_timer    = 0.0
        self.game_start_time    = 0.0
        self.winner             = None   # 'A', 'B', or 'TIE'
        self.last_console_print = 0.0   # for throttled time-remaining prints

        self.sound.start_bgm()

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
            now = time.time()
            self.last_proj_tick     = {'A': now, 'B': now}
            self.last_powerup_spawn = now
            self.last_fire_time     = {}
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
                sa = self.teams['A'].score
                sb = self.teams['B'].score
                if sa > sb:
                    self.winner = 'A'
                    print(f"TIME'S UP! Team A wins {sa}-{sb}!")
                elif sb > sa:
                    self.winner = 'B'
                    print(f"TIME'S UP! Team B wins {sb}-{sa}!")
                else:
                    self.winner = 'TIE'
                    print(f"TIME'S UP! It's a tie {sa}-{sb}!")
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
            self.explosions = [e for e in self.explosions
                               if now - e['start'] < (1.2 if e.get('ultimate') else 0.55 if e.get('big') else 0.45)]
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
        # 3s spread + 2s END text = 5s total, then exit
        if now - self.game_over_timer >= 5.0:
            print("Game over — exiting.")
            os._exit(0)

    # -----------------------------------------------------------------------
    # Input processing — double-press state machine
    # -----------------------------------------------------------------------

    def process_inputs(self):
        now = time.time()
        for team_id in ('A', 'B'):
            team = self.teams[team_id]
            for col in range(BOARD_WIDTH):
                led_idx     = team.led_idx_for_col(col)
                is_pressed  = self.button_states[led_idx]
                was_pressed = self.prev_button_states[led_idx]
                if is_pressed and not was_pressed:
                    if now - self.last_fire_time.get(team_id, 0) >= FIRE_COOLDOWN:
                        self.fire_projectile(team_id, col)
                        self.last_fire_time[team_id] = now

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

                # Cross-collision check
                next_y = proj.y + team.direction
                if proj.unblockable:
                    # Ultimate wipes every enemy on the entire destination row
                    for opp in self.projectiles:
                        if opp.active and opp.team_id != team_id and opp.y == next_y:
                            opp.active = False
                            self.sound.play('hit')
                else:
                    # Normal projectile: only check same column
                    for opp in self.projectiles:
                        if not opp.active or opp.team_id == team_id \
                                or opp.x != proj.x or opp.y != next_y:
                            continue
                        if opp.unblockable:
                            # Enemy ultimate destroys us, keeps going
                            proj.active = False
                            self.sound.play('hit')
                        else:
                            # Mutual destruction
                            proj.active = False
                            opp.active = False
                            mid_y = (proj.y + opp.y) // 2
                            self.explosions.append({
                                'x': proj.x - 1, 'y': mid_y - 1,
                                'color': VIOLET,
                                'start': time.time(),
                                'big': True,
                            })
                            self.sound.play('hit')
                        break
                if not proj.active:
                    continue

                proj.trail.append((proj.x, proj.y))
                if len(proj.trail) > Projectile.TRAIL_LENGTH:
                    proj.trail.pop(0)
                proj.y += team.direction

                # Check power-up collection — ULTIMATE is 1×1, others are 2×2
                for pu in self.power_ups:
                    size = 0 if pu.ptype == PTYPE_ULTIMATE else 1
                    if pu.active and pu.x <= proj.x <= pu.x + size and pu.y <= proj.y <= pu.y + size:
                        self._apply_powerup(team_id, pu.ptype)
                        self.explosions.append({
                            'x': pu.x, 'y': pu.y,
                            'color': PTYPE_COLORS[pu.ptype],
                            'start': time.time()
                        })
                        pu.active = False
                        if pu.ptype == PTYPE_ULTIMATE:
                            self.sound.play('ultimate_sfx')
                        else:
                            self.sound.play('powerup')
                        break

                # Did projectile reach the enemy base or exit the board?
                # Team A shoots down → scores when proj.y >= TEAM_B_BASE_ROW (31)
                # Team B shoots up  → scores when proj.y <= TEAM_A_BASE_ROW (0)
                if team_id == 'A' and proj.y >= TEAM_B_BASE_ROW:
                    proj.active = False
                    self.teams['A'].score += proj.points
                    self.ripples.append({'x': proj.x, 'y': TEAM_B_BASE_ROW, 'color': RED, 'start': time.time()})
                    if proj.points >= 3:
                        self.explosions.append({'x': proj.x, 'y': TEAM_B_BASE_ROW,
                                                'color': DARK_RED, 'start': time.time(), 'ultimate': True})
                        self.sound.play('ultimate_hit')
                    print(f"SCORE — Team A: {self.teams['A'].score}  Team B: {self.teams['B'].score}")
                    self.sound.play('score')
                elif team_id == 'B' and proj.y <= TEAM_A_BASE_ROW:
                    proj.active = False
                    self.teams['B'].score += proj.points
                    self.ripples.append({'x': proj.x, 'y': TEAM_A_BASE_ROW, 'color': BLUE, 'start': time.time()})
                    if proj.points >= 3:
                        self.explosions.append({'x': proj.x, 'y': TEAM_A_BASE_ROW,
                                                'color': VIOLET, 'start': time.time(), 'ultimate': True})
                        self.sound.play('ultimate_hit')
                    print(f"SCORE — Team A: {self.teams['A'].score}  Team B: {self.teams['B'].score}")
                    self.sound.play('score')
                elif proj.y < 0 or proj.y >= BOARD_HEIGHT:
                    proj.active = False

        # Remove inactive projectiles
        self.projectiles = [p for p in self.projectiles if p.active]

    # -----------------------------------------------------------------------
    # Collision detection
    # -----------------------------------------------------------------------

    def handle_collisions(self):
        # Ultimate projectiles destroy every enemy on the same row
        for proj in self.projectiles:
            if not proj.active or not proj.unblockable:
                continue
            for opp in self.projectiles:
                if opp.active and opp.team_id != proj.team_id \
                        and opp.y == proj.y and not opp.unblockable:
                    opp.active = False

        # Normal same-cell collisions (column-matched)
        pos_a = {}
        pos_b = {}
        for proj in self.projectiles:
            if not proj.active or proj.unblockable:
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
                ultimate_locked = (
                    any(pu.active and pu.ptype == PTYPE_ULTIMATE for pu in self.power_ups) or
                    any(p.active  and p.unblockable               for p  in self.projectiles)
                )
                choices = [PTYPE_SPEED, PTYPE_DOUBLE] if ultimate_locked else \
                          [PTYPE_SPEED, PTYPE_DOUBLE, PTYPE_ULTIMATE, PTYPE_ULTIMATE]
                ptype = random.choice(choices)
                self.power_ups.append(PowerUp(x, y, ptype))
                names = {PTYPE_SPEED: 'SPEED',
                         PTYPE_DOUBLE: 'DOUBLE', PTYPE_ULTIMATE: 'ULTIMATE'}
                print(f"Power-up spawned: {names[ptype]} at ({x},{y})")
                break

    def _apply_powerup(self, team_id, ptype):
        now    = time.time()
        team   = self.teams[team_id]
        expiry = now + POWERUP_EFFECT_DURATION
        if ptype == PTYPE_SPEED:
            team.effect_speed_until  = expiry
            print(f"Team {team_id} got SPEED boost!")
        elif ptype == PTYPE_DOUBLE:
            team.effect_double_until = expiry
            print(f"Team {team_id} got DOUBLE SHOT!")
        elif ptype == PTYPE_ULTIMATE:
            # Fire one unblockable 3-point projectile immediately from the centre
            cx = BOARD_WIDTH // 2
            if team_id == 'B':
                shape = 'sphere'
                p = Projectile(cx, LAUNCHER_ROW_B, 'B', unblockable=True, points=3, shape='sphere')
            else:
                p = Projectile(cx, LAUNCHER_ROW_A, 'A', unblockable=True, points=3, shape='parabola')
            self.projectiles.append(p)
            print(f"Team {team_id} fired ULTIMATE!")

    def _expire_effects(self):
        now = time.time()
        for team in self.teams.values():
            if team.effect_speed_until  and now > team.effect_speed_until:
                team.effect_speed_until  = None
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
            if team.effect_double_until and now < team.effect_double_until:
                self.set_led(buffer, 1, indicator_y, MAGENTA)

    def _render_input_bar_highlight(self, buffer, now):
        """Draw the dim launcher bar for each team."""
        for x in range(BOARD_WIDTH):
            self.set_led(buffer, x, LAUNCHER_ROW_A, DIM_RED)
            self.set_led(buffer, x, LAUNCHER_ROW_B, DIM_BLUE)

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

            # Compute total elapsed since startup began
            if step < 5:
                total_elapsed = step * 0.2 + (now - self.startup_timer)
            else:
                total_elapsed = 1.0 + (step - 5) * 1.0 + (now - self.startup_timer)

            # ── Step 9 (1 second left): return board to normal ──
            if step >= 9:
                for x in range(BOARD_WIDTH):
                    self.set_led(buffer, x, TEAM_A_BASE_ROW, RED)
                    self.set_led(buffer, x, TEAM_B_BASE_ROW, BLUE)
                    self.set_led(buffer, x, LAUNCHER_ROW_A, DIM_RED)
                    self.set_led(buffer, x, LAUNCHER_ROW_B, DIM_BLUE)
                self.draw_glyph(buffer, 1, 6, 13, WHITE)
                return buffer

            # ── Full-board anime animation ──
            MID    = BOARD_HEIGHT // 2          # row 16
            speed  = total_elapsed * 14         # scroll speed

            # Background energy waves — red top half, blue bottom half
            for y in range(BOARD_HEIGHT):
                for x in range(BOARD_WIDTH):
                    if y < MID:
                        band = int(y * 2 + speed) % 12
                        fac  = max(0.12, 1.0 - abs(band - 6) / 6.0)
                        # column shimmer
                        cfac = max(0.4, 1.0 - ((x + int(speed * 0.5)) % 5) * 0.12)
                        self.set_led(buffer, x, y, (int(210 * fac * cfac), 0, 0))
                    else:
                        band = int((BOARD_HEIGHT - 1 - y) * 2 + speed) % 12
                        fac  = max(0.12, 1.0 - abs(band - 6) / 6.0)
                        cfac = max(0.4, 1.0 - ((x + int(speed * 0.5)) % 5) * 0.12)
                        self.set_led(buffer, x, y, (0, 0, int(210 * fac * cfac)))

            # Vertical energy beams erupting from each base
            for x in range(BOARD_WIDTH):
                # Red beams from row 0 downward
                phase_r = int(x * 3 + speed * 0.8) % 9
                if phase_r < 4:
                    beam_len = 5 + phase_r * 2
                    for y in range(min(beam_len, MID)):
                        fac = max(0.0, 1.0 - y / max(1, beam_len))
                        self.set_led(buffer, x, y,
                                     (int(255 * fac), int(60 * fac), 0))
                # Blue beams from row 31 upward
                phase_b = int(x * 5 + speed * 1.1) % 9
                if phase_b < 4:
                    beam_len = 5 + phase_b * 2
                    for y in range(BOARD_HEIGHT - 1,
                                   max(BOARD_HEIGHT - 1 - beam_len, MID - 1), -1):
                        fac = max(0.0, 1.0 - (BOARD_HEIGHT - 1 - y) / max(1, beam_len))
                        self.set_led(buffer, x, y,
                                     (0, int(60 * fac), int(255 * fac)))

            # Center clash band (rows MID-3 to MID+2)
            clash_phase = int(total_elapsed * 6) % 3
            for x in range(BOARD_WIDTH):
                for y in range(MID - 3, MID + 3):
                    dist = abs(y - MID)
                    fac  = max(0.0, 1.0 - dist * 0.28)
                    if clash_phase == 0:        # red-to-blue gradient
                        rf = (MID - y + 3) / 6.0
                        bf = (y - MID + 3) / 6.0
                        self.set_led(buffer, x, y,
                                     (int(255 * rf * fac), 0, int(255 * bf * fac)))
                    elif clash_phase == 1:      # white flash
                        self.set_led(buffer, x, y,
                                     (int(255 * fac), int(255 * fac), int(255 * fac)))
                    else:                       # purple surge
                        self.set_led(buffer, x, y,
                                     (int(180 * fac), 0, int(220 * fac)))

            # Horizontal shockwave lines sweeping from centre outward
            wave_y_r = MID - 1 - int(total_elapsed * 6) % MID   # red line sweeps up
            wave_y_b = MID     + int(total_elapsed * 6) % MID   # blue line sweeps down
            for x in range(BOARD_WIDTH):
                self.set_led(buffer, x, max(0, wave_y_r), WHITE)
                self.set_led(buffer, x, min(BOARD_HEIGHT-1, wave_y_b), WHITE)

            # Base rows always bright
            for x in range(BOARD_WIDTH):
                self.set_led(buffer, x, TEAM_A_BASE_ROW, RED)
                self.set_led(buffer, x, TEAM_B_BASE_ROW, BLUE)

            # Countdown number (steps 5-8 → digits 5,4,3,2)
            if 5 <= step <= 8:
                num = 5 - (step - 5)
                step_prog = now - self.startup_timer
                text_c = WHITE if step_prog < 0.12 else (200, 200, 200)
                self.draw_glyph(buffer, num, 6, 13, text_c)

            return buffer

        # ---------- GAMEOVER ----------
        if self.state == 'GAMEOVER':
            elapsed_go = now - self.game_over_timer

            # Determine winner color(s)
            if self.winner == 'A':
                win_color = RED
                spread_from_top = True   # A is at top (row 0), spreads downward
            elif self.winner == 'B':
                win_color = BLUE
                spread_from_top = False  # B is at bottom (row 31), spreads upward
            else:
                win_color = WHITE        # TIE — white flood from both ends
                spread_from_top = True

            # --- Phase 1: color flood (0 – 3 s) ---
            SPREAD_DURATION = 3.0
            spread_t = min(elapsed_go / SPREAD_DURATION, 1.0)
            rows_filled = int(spread_t * BOARD_HEIGHT)

            if self.winner == 'TIE':
                # Both sides flood toward the middle
                half = rows_filled // 2 + 1
                for x in range(BOARD_WIDTH):
                    for row in range(min(half, BOARD_HEIGHT // 2)):
                        self.set_led(buffer, x, row, RED)
                    for row in range(BOARD_HEIGHT - 1, max(BOARD_HEIGHT - half - 1, BOARD_HEIGHT // 2 - 1), -1):
                        self.set_led(buffer, x, row, BLUE)
            elif spread_from_top:
                # Flood from row 0 downward
                for x in range(BOARD_WIDTH):
                    for row in range(min(rows_filled + 1, BOARD_HEIGHT)):
                        # Slight brightness gradient — leading edge brighter
                        depth = (rows_filled - row)
                        factor = max(0.4, 1.0 - depth * 0.04)
                        c = tuple(int(ch * factor) for ch in win_color)
                        self.set_led(buffer, x, row, c)
            else:
                # Flood from row 31 upward
                for x in range(BOARD_WIDTH):
                    for row in range(BOARD_HEIGHT - 1, max(BOARD_HEIGHT - rows_filled - 2, -1), -1):
                        depth = (row - (BOARD_HEIGHT - rows_filled - 1))
                        factor = max(0.4, 1.0 - depth * 0.04)
                        c = tuple(int(ch * factor) for ch in win_color)
                        self.set_led(buffer, x, row, c)

            # --- Phase 2: "END" text appears after spread completes (>= 3 s) ---
            if elapsed_go >= SPREAD_DURATION:
                flash_on   = int((elapsed_go - SPREAD_DURATION) * 2) % 2 == 0
                text_color = WHITE if flash_on else (50, 50, 50)
                self.draw_glyph(buffer, 'E',  2, 14, text_color)
                self.draw_glyph(buffer, 'N',  6, 14, text_color)
                self.draw_glyph(buffer, 'D', 10, 14, text_color)

            return buffer

        # ---------- PLAYING ----------
        if self.state == 'PLAYING':
            with self.lock:
                # 1. Team base rows (solid color)
                for x in range(BOARD_WIDTH):
                    self.set_led(buffer, x, TEAM_A_BASE_ROW, RED)
                    self.set_led(buffer, x, TEAM_B_BASE_ROW, BLUE)

                # 2. Draw power-ups in neutral zone (ULTIMATE=1×1, others=2×2)
                for pu in self.power_ups:
                    if not pu.active:
                        continue
                    remaining = POWERUP_LIFETIME - (now - pu.created_time)
                    if remaining < 5.0 and int(now * 4) % 2 == 0:
                        continue  # blink off near expiry
                    color = PTYPE_COLORS[pu.ptype]
                    if pu.ptype == PTYPE_ULTIMATE:
                        self.set_led(buffer, pu.x, pu.y, color)
                    else:
                        for dx in range(2):
                            for dy in range(2):
                                self.set_led(buffer, pu.x + dx, pu.y + dy, color)

                # 2b. Draw explosion animations
                for exp in self.explosions:
                    elapsed  = now - exp['start']
                    cx, cy   = exp['x'], exp['y']
                    big      = exp.get('big', False)
                    ultimate = exp.get('ultimate', False)
                    ec       = exp['color']

                    if ultimate:
                        # ── ULTIMATE IMPACT ── massive 5-frame anime shockwave
                        GOLD = (255, 220, 0)
                        DIM_EC = tuple(c // 3 for c in ec)
                        if elapsed < 0.08:
                            # F1: full-board white flash
                            for x in range(BOARD_WIDTH):
                                for y in range(BOARD_HEIGHT):
                                    self.set_led(buffer, x, y, WHITE)
                        elif elapsed < 0.22:
                            # F2: 10×10 white core + gold ring
                            for dx in range(-5, 6):
                                for dy in range(-5, 6):
                                    dist = abs(dx) + abs(dy)
                                    if dist <= 3:
                                        self.set_led(buffer, cx+dx, cy+dy, WHITE)
                                    elif dist <= 7:
                                        self.set_led(buffer, cx+dx, cy+dy, GOLD)
                                    elif dist <= 9:
                                        self.set_led(buffer, cx+dx, cy+dy, ec)
                        elif elapsed < 0.42:
                            # F3: expanding shockwave ring (thin bright ring at growing radius)
                            radius = int((elapsed - 0.22) / 0.20 * 7) + 4
                            for dx in range(-radius-1, radius+2):
                                for dy in range(-radius-1, radius+2):
                                    dist = abs(dx) + abs(dy)
                                    if radius - 1 <= dist <= radius + 1:
                                        fac = 1.0 - abs(dist - radius) * 0.5
                                        c = tuple(int(ch * fac) for ch in ec)
                                        self.set_led(buffer, cx+dx, cy+dy, c)
                            # Cross beams
                            for d in range(-6, 7):
                                self.set_led(buffer, cx+d, cy,   GOLD)
                                self.set_led(buffer, cx,   cy+d, GOLD)
                        elif elapsed < 0.75:
                            # F4: scattered sparks + large cross
                            fac = max(0.0, 1.0 - (elapsed - 0.42) / 0.33)
                            spark_c = tuple(int(ch * fac) for ch in ec)
                            gold_c  = tuple(int(ch * fac) for ch in GOLD)
                            for d in range(-7, 8):
                                self.set_led(buffer, cx+d, cy,   gold_c)
                                self.set_led(buffer, cx,   cy+d, gold_c)
                            # diagonal sparks
                            for d in range(-5, 6):
                                self.set_led(buffer, cx+d, cy+d, spark_c)
                                self.set_led(buffer, cx+d, cy-d, spark_c)
                        else:
                            # F5: dim embers fade out
                            fac = max(0.0, 1.0 - (elapsed - 0.75) / 0.45)
                            ember = tuple(int(ch * fac * 0.4) for ch in ec)
                            for d in range(-8, 9):
                                self.set_led(buffer, cx+d, cy,   ember)
                                self.set_led(buffer, cx,   cy+d, ember)
                            for d in range(-6, 7):
                                self.set_led(buffer, cx+d, cy+d, ember)
                                self.set_led(buffer, cx+d, cy-d, ember)

                    elif big:
                        # ── ANIME CLASH EXPLOSION ── purple shockwave
                        PB = (220, 0, 255)   # bright
                        PM = (148, 0, 211)   # mid
                        PD = ( 60, 0,  80)   # dim
                        if elapsed < 0.07:
                            # F1: pure white full-board flash
                            for x in range(BOARD_WIDTH):
                                for y in range(max(0,cy-5), min(BOARD_HEIGHT,cy+6)):
                                    self.set_led(buffer, x, y, WHITE)
                        elif elapsed < 0.17:
                            # F2: white core + bright purple diamond ring
                            for dx in range(-6, 7):
                                for dy in range(-6, 7):
                                    dist = abs(dx) + abs(dy)
                                    if dist <= 2:   self.set_led(buffer, cx+dx, cy+dy, WHITE)
                                    elif dist <= 5: self.set_led(buffer, cx+dx, cy+dy, PB)
                                    elif dist <= 8: self.set_led(buffer, cx+dx, cy+dy, PM)
                        elif elapsed < 0.30:
                            # F3: 8-directional energy beams
                            fac = 1.0 - (elapsed - 0.17) / 0.13
                            for d in range(1, 8):
                                bc = tuple(int(c * fac * max(0.2, 1.0 - d*0.12)) for c in PB)
                                self.set_led(buffer, cx+d,  cy,   bc)
                                self.set_led(buffer, cx-d,  cy,   bc)
                                self.set_led(buffer, cx,    cy+d, bc)
                                self.set_led(buffer, cx,    cy-d, bc)
                                self.set_led(buffer, cx+d,  cy+d, tuple(c//2 for c in bc))
                                self.set_led(buffer, cx-d,  cy+d, tuple(c//2 for c in bc))
                                self.set_led(buffer, cx+d,  cy-d, tuple(c//2 for c in bc))
                                self.set_led(buffer, cx-d,  cy-d, tuple(c//2 for c in bc))
                        else:
                            # F4: fading purple ember cross + diagonals
                            fac = max(0.0, 1.0 - (elapsed - 0.30) / 0.25)
                            for d in range(-7, 8):
                                self.set_led(buffer, cx+d, cy,   tuple(int(c*fac) for c in PD))
                                self.set_led(buffer, cx,   cy+d, tuple(int(c*fac) for c in PD))
                            for d in range(-5, 6):
                                self.set_led(buffer, cx+d, cy+d, tuple(int(c*fac*0.5) for c in PM))
                                self.set_led(buffer, cx+d, cy-d, tuple(int(c*fac*0.5) for c in PM))
                    else:
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
                    if proj.shape == 'sphere':
                        # ══ DRAGON BALL ENERGY SPHERE ══
                        pulse   = int(now * 16) % 2           # 8 Hz white flash
                        t_rot_a = int(now * 8)  % 8           # inner ring  (CW)
                        t_rot_b = int(now * 5)  % 8           # outer ring  (CCW)
                        px, py  = proj.x, proj.y

                        # --- Full-column energy wake: entire column behind, 14 rows ---
                        for wy in range(py + 1, min(py + 14, BOARD_HEIGHT)):
                            fac = max(0.0, 1.0 - (wy - py) * 0.075)
                            wc = tuple(int(c * fac * 0.8) for c in VIOLET)
                            for wx in range(px - 2, px + 3):
                                cf = max(0.0, 1.0 - abs(wx - px) * 0.3)
                                self.set_led(buffer, wx, wy, tuple(int(c * cf) for c in wc))

                        # --- Horizontal speed flare at sphere row (full width) ---
                        SPEED_FLARE = (40, 0, 60)
                        for x in range(BOARD_WIDTH):
                            fac = max(0.2, 1.0 - abs(x - px) * 0.08)
                            fc = tuple(int(c * fac) for c in SPEED_FLARE)
                            self.set_led(buffer, x, py, fc)
                            self.set_led(buffer, x, py - 1, tuple(c // 2 for c in fc))
                            self.set_led(buffer, x, py + 1, tuple(c // 2 for c in fc))

                        # --- Ghost trail: full-sized ghost orbs ---
                        for i, (tx, ty) in enumerate(proj.trail):
                            factor = (i + 1) / (Projectile.TRAIL_LENGTH + 1)
                            for ddx in range(-4, 5):
                                for ddy in range(-4, 5):
                                    dist = abs(ddx) + abs(ddy)
                                    if dist > 8: continue
                                    fac = factor * max(0.0, 1.0 - dist * 0.1) * 0.55
                                    tc = tuple(int(c * fac) for c in VIOLET)
                                    self.set_led(buffer, tx + ddx, ty + ddy, tc)

                        # --- Concentric aura rings (large diamond) ---
                        for ddx in range(-7, 8):
                            for ddy in range(-7, 8):
                                dist = abs(ddx) + abs(ddy)
                                if   dist <= 2:  c = WHITE
                                elif dist <= 4:  c = VIOLET
                                elif dist <= 6:  c = (140, 0, 200)
                                elif dist <= 8:  c = (80,  0, 120)
                                elif dist <= 10: c = (40,  0,  60)
                                elif dist <= 12: c = (15,  0,  25)
                                else: continue
                                self.set_led(buffer, px + ddx, py + ddy, c)

                        # --- Inner 8 spokes at radius 4 (rotate CW) ---
                        spokes_i = [(0,-4),(3,-3),(4,0),(3,3),(0,4),(-3,3),(-4,0),(-3,-3)]
                        for si in range(8):
                            sx, sy = spokes_i[(si + t_rot_a) % 8]
                            bright = 1.0 if si % 2 == 0 else 0.5
                            sc = tuple(int(c * bright) for c in (240, 100, 255))
                            self.set_led(buffer, px + sx, py + sy, sc)

                        # --- Outer 8 spokes at radius 6 (rotate CCW) ---
                        spokes_o = [(0,-6),(4,-4),(6,0),(4,4),(0,6),(-4,4),(-6,0),(-4,-4)]
                        for si in range(8):
                            sx, sy = spokes_o[(si - t_rot_b) % 8]
                            bright = 1.0 if si % 2 == 0 else 0.3
                            sc = tuple(int(c * bright) for c in (200, 50, 255))
                            self.set_led(buffer, px + sx, py + sy, sc)

                        # --- Blazing white core cross ---
                        core_c = WHITE if pulse else (240, 180, 255)
                        for d in range(-2, 3):
                            self.set_led(buffer, px + d, py,     core_c)
                            self.set_led(buffer, px,     py + d, core_c)
                        self.set_led(buffer, px, py, WHITE)

                    elif proj.shape == 'slash':
                        # ══ DEMON SLAYER SWORD SLASH ══
                        flicker = int(now * 20) % 3           # 6.7 Hz 3-frame
                        pulse   = int(now * 30) % 2           # fast tip flash
                        px, py  = proj.x, proj.y

                        # --- FULL-BOARD horizontal impact lines (5 rows each side) ---
                        impact_rows = [(-1,1.0),(-2,0.75),(-3,0.45),(-4,0.22),(-5,0.08),
                                       ( 1,1.0),( 2,0.75),( 3,0.45),( 4,0.22),( 5,0.08)]
                        for row_off, alpha in impact_rows:
                            ic = (int(180 * alpha), 0, 0)
                            for x in range(BOARD_WIDTH):
                                self.set_led(buffer, x, py + row_off, ic)

                        # --- Full-height vertical ki column (entire board height above) ---
                        for ky in range(py - 1, -1, -1):
                            fac = max(0.0, 1.0 - (py - ky) * 0.065)
                            kc  = tuple(int(c * fac * 0.85) for c in DARK_RED)
                            for kx in range(px - 3, px + 4):
                                cf = max(0.0, 1.0 - abs(kx - px) * 0.28)
                                self.set_led(buffer, kx, ky, tuple(int(c * cf) for c in kc))

                        # --- Ghost afterimages (large 9-cell diagonal) ---
                        for i, (tx, ty) in enumerate(proj.trail):
                            factor = (i + 1) / (Projectile.TRAIL_LENGTH + 1)
                            tc = tuple(int(c * factor * 0.5) for c in DARK_RED)
                            for d in range(-4, 5):
                                self.set_led(buffer, tx + d, ty + d, tc)

                        # --- 5 parallel diagonal lines for a thick blade ---
                        # Offsets perpendicular to '\': shift x while keeping y same
                        blade_layers = [
                            (-2, (50,  0, 0)),   # far edge
                            (-1, (100, 0, 0)),   # inner edge
                            ( 0, DARK_RED),      # centre
                            ( 1, (100, 0, 0)),   # inner edge
                            ( 2, (50,  0, 0)),   # far edge
                        ]
                        for x_off, bc in blade_layers:
                            for d in range(-5, 6):
                                self.set_led(buffer, px + d + x_off, py + d, bc)

                        # --- White/yellow/orange flickering hot core ---
                        if flicker == 0:   core_c = WHITE
                        elif flicker == 1: core_c = (255, 230, 0)
                        else:              core_c = (255, 100, 0)
                        for d in range(-3, 4):
                            self.set_led(buffer, px + d, py + d, core_c)

                        # --- Starburst at the leading tip ---
                        tip_c = WHITE if pulse else (255, 240, 100)
                        for ddx in range(-1, 2):
                            for ddy in range(-1, 2):
                                self.set_led(buffer, px + 5 + ddx, py + 5 + ddy, tip_c)
                        self.set_led(buffer, px + 5, py + 5, WHITE)
                        # Cross flare on tip
                        for d in range(1, 4):
                            fac = 1.0 - d * 0.3
                            fc = tuple(int(c * fac) for c in (255, 200, 0))
                            self.set_led(buffer, px + 5 + d, py + 5, fc)
                            self.set_led(buffer, px + 5, py + 5 + d, fc)
                            self.set_led(buffer, px + 5 - d, py + 5, fc)
                            self.set_led(buffer, px + 5, py + 5 - d, fc)
                    elif proj.shape == 'parabola':
                        # ══ SHOCKWAVE PARABOLA — red energy wave ══
                        flicker = int(now * 20) % 3
                        pulse   = int(now * 30) % 2
                        px, py  = proj.x, proj.y
                        team    = self.teams[proj.team_id]
                        COEFF   = 7   # lower = wider/shallower parabola

                        # Pre-compute curve y for every board column
                        curve = {}
                        for x in range(BOARD_WIDTH):
                            curve[x] = py - round((x - px) ** 2 / COEFF)

                        # --- Dark red glow BELOW the parabola (energy wake behind the curve) ---
                        for x in range(BOARD_WIDTH):
                            cy_curve = curve[x]
                            for gy in range(cy_curve + 1, min(BOARD_HEIGHT, cy_curve + 9)):
                                fac = max(0.0, 1.0 - (gy - cy_curve) * 0.14)
                                gc  = (int(120 * fac), 0, 0)
                                self.set_led(buffer, x, gy, gc)

                        # --- Full-width impact lines at the parabola spine rows ---
                        for row_off, alpha in [(-1,0.8),(-2,0.5),(-3,0.25),(-4,0.1),
                                               ( 1,0.8),( 2,0.5),( 3,0.25),( 4,0.1)]:
                            ic = (int(160 * alpha), 0, 0)
                            for x in range(BOARD_WIDTH):
                                self.set_led(buffer, x, py + row_off, ic)

                        # --- Ghost trail: fading parabola afterimages ---
                        for i, (tx, ty) in enumerate(proj.trail):
                            factor = (i + 1) / (Projectile.TRAIL_LENGTH + 1) * 0.45
                            for x in range(BOARD_WIDTH):
                                gy = ty - round((x - tx) ** 2 / COEFF)
                                tc = (int(139 * factor), 0, 0)
                                self.set_led(buffer, x, gy, tc)

                        # --- Parabola curve: dark red outer, then hot core, glow pixels ---
                        for x in range(BOARD_WIDTH):
                            cy_c = curve[x]
                            # Glow halo ±2 around curve
                            for off, fac in [(-2,0.3),(-1,0.65),(0,1.0),(1,0.65),(2,0.3)]:
                                self.set_led(buffer, x, cy_c + off, (int(139 * fac), 0, 0))
                            # Hot core on curve
                            if flicker == 0:   hot = WHITE
                            elif flicker == 1: hot = (255, 200, 0)
                            else:              hot = (255, 80,  0)
                            self.set_led(buffer, x, cy_c, hot)

                        # --- Blazing starburst at the center leading tip (px, py) ---
                        tip_c = WHITE if pulse else (255, 230, 80)
                        for ddx in range(-2, 3):
                            for ddy in range(-2, 3):
                                if abs(ddx) + abs(ddy) <= 2:
                                    self.set_led(buffer, px + ddx, py + ddy, tip_c)
                        for d in range(1, 5):
                            fc = tuple(int(c * (1.0 - d*0.22)) for c in (255, 180, 0))
                            self.set_led(buffer, px + d, py,     fc)
                            self.set_led(buffer, px - d, py,     fc)
                            self.set_led(buffer, px,     py - d, fc)
                            self.set_led(buffer, px,     py + d, fc)

                    else:
                        # ══ ENERGY BEAM ══
                        color  = self.teams[proj.team_id].color
                        team   = self.teams[proj.team_id]
                        direct = team.direction   # +1 down, -1 up
                        px, py = proj.x, proj.y
                        pulse  = int(now * 20) % 2

                        # Active power-up aura colours
                        has_speed  = team.effect_speed_until  and now < team.effect_speed_until
                        has_double = team.effect_double_until and now < team.effect_double_until

                        # --- Beam body: solid bright streak 6 cells behind the head ---
                        for step in range(1, 7):
                            by   = py - step * direct      # trail goes opposite to travel direction
                            fac  = max(0.0, 1.0 - step * 0.16)
                            core = tuple(int(c * fac) for c in color)
                            # White-bright core at center
                            bright_core = tuple(min(255, int(c + (255 - c) * fac * 0.6)) for c in color)
                            self.set_led(buffer, px, by, bright_core)
                            # Dim side pixels (beam width)
                            side = tuple(int(c * fac * 0.35) for c in color)
                            self.set_led(buffer, px - 1, by, side)
                            self.set_led(buffer, px + 1, by, side)

                        # --- SPEED aura: yellow sparks streaking behind ---
                        if has_speed:
                            YSPARK = (255, 220, 0)
                            for step in range(1, 9):
                                sy   = py - step * direct
                                fac  = max(0.0, 1.0 - step * 0.12)
                                yc   = tuple(int(c * fac * 0.8) for c in YSPARK)
                                self.set_led(buffer, px, sy, yc)
                                if step % 2 == 0:
                                    self.set_led(buffer, px - 1, sy, tuple(c // 2 for c in yc))
                                    self.set_led(buffer, px + 1, sy, tuple(c // 2 for c in yc))

                        # --- DOUBLE aura: twin magenta flanking beams ---
                        if has_double:
                            MAG = (255, 0, 255)
                            for step in range(0, 5):
                                dy  = py - step * direct
                                fac = max(0.0, 1.0 - step * 0.22)
                                mc  = tuple(int(c * fac * 0.7) for c in MAG)
                                self.set_led(buffer, px - 2, dy, mc)
                                self.set_led(buffer, px + 2, dy, mc)

                        # --- Horizontal plasma flare at head ---
                        flare_c = tuple(min(255, int(c * 1.3)) for c in color)
                        self.set_led(buffer, px - 1, py, tuple(c // 2 for c in color))
                        self.set_led(buffer, px + 1, py, tuple(c // 2 for c in color))

                        # --- Bright white-hot head pixel ---
                        head_c = WHITE if pulse else tuple(min(255, c + 80) for c in color)
                        self.set_led(buffer, px, py, head_c)

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

                # 5. Anime power-up auras on launcher bars
                for tid, team in self.teams.items():
                    bar_y = LAUNCHER_ROW_A if tid == 'A' else LAUNCHER_ROW_B
                    t_anim = int(now * 10) % BOARD_WIDTH   # sweeping position

                    if team.effect_speed_until and now < team.effect_speed_until:
                        # SPEED — yellow lightning sweep across the bar
                        for x in range(BOARD_WIDTH):
                            dist = abs(x - t_anim)
                            fac  = max(0.0, 1.0 - dist * 0.25)
                            self.set_led(buffer, x, bar_y, (int(255*fac), int(220*fac), 0))
                            # spark above/below
                            if dist < 2:
                                self.set_led(buffer, x, bar_y - team.direction,
                                             (int(180*fac), int(150*fac), 0))

                    if team.effect_double_until and now < team.effect_double_until:
                        # DOUBLE — magenta twin-pulse ripple from centre outward
                        t_wave = (now * 6) % 1.0
                        for x in range(BOARD_WIDTH):
                            cx_dist = abs(x - BOARD_WIDTH // 2) / (BOARD_WIDTH / 2)
                            wave    = max(0.0, 1.0 - abs(cx_dist - t_wave) * 4)
                            self.set_led(buffer, x, bar_y, (int(255*wave), 0, int(255*wave)))


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
    # DPI awareness on Windows so monitor coordinates are correct
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    try:
        import screeninfo
        SCREENINFO_OK = True
    except ImportError:
        SCREENINFO_OK = False

    game = BattleGame()
    net  = NetworkManager(game)
    net.start_bg()

    gt = threading.Thread(target=game_thread_func, args=(game,))
    gt.daemon = True
    gt.start()

    # ── Shared style constants ────────────────────────────────────────────────
    BG        = "#0a0a0a"
    BG_CARD   = "#141414"
    RED_HEX   = "#ff2222"
    BLUE_HEX  = "#2266ff"
    WHITE_HEX = "#ffffff"
    DIM_HEX   = "#555555"
    BTN_BG    = "#1e1e1e"
    BTN_HO    = "#2e2e2e"

    STATE_COLORS = {
        'LOBBY':    DIM_HEX,
        'STARTUP':  "#ffcc00",
        'PLAYING':  "#44ff88",
        'GAMEOVER': "#ff4444",
    }

    # ── Helper: build control window on a given tk parent/toplevel ────────────
    def build_control(win):
        win.title("Battle Blaster — Control")
        win.configure(bg=BG)
        win.resizable(False, False)

        tk.Label(win, text="⚡ BATTLE BLASTER", bg=BG,
                 fg=WHITE_HEX, font=("Consolas", 18, "bold")).pack(pady=(18, 4))

        sv = tk.StringVar(value="● LOBBY")
        sl = tk.Label(win, textvariable=sv, bg=BG,
                      fg=DIM_HEX, font=("Consolas", 11))
        sl.pack(pady=(0, 16))

        def make_btn(text, cmd, fg=WHITE_HEX):
            btn = tk.Button(win, text=text, command=cmd,
                            bg=BTN_BG, fg=fg, activebackground=BTN_HO,
                            activeforeground=fg, relief="flat",
                            font=("Consolas", 13, "bold"),
                            width=20, pady=8, cursor="hand2")
            btn.pack(pady=5, padx=30)
            btn.bind("<Enter>", lambda e: btn.configure(bg=BTN_HO))
            btn.bind("<Leave>", lambda e: btn.configure(bg=BTN_BG))

        make_btn("▶  START GAME",    lambda: game.start_game(),    fg="#44ff88")
        make_btn("↺  RESTART ROUND", lambda: game.restart_round(), fg="#ffcc00")
        make_btn("✕  QUIT",          lambda: os._exit(0),           fg="#ff4444")
        tk.Label(win, text="", bg=BG).pack(pady=6)

        return sv, sl   # so refresh() can update them

    # ── Helper: build scoreboard window on a given tk parent/toplevel ─────────
    def build_scoreboard(win):
        win.title("Battle Blaster — Scoreboard")
        win.configure(bg=BG)
        win.resizable(True, True)

        tk.Label(win, text="SCOREBOARD", bg=BG,
                 fg=DIM_HEX, font=("Consolas", 11, "bold")).pack(pady=(16, 8))

        fa = tk.Frame(win, bg=BG_CARD)
        fa.pack(fill="x", padx=24, pady=6)
        tk.Label(fa, text="  TEAM A  ", bg=BG_CARD,
                 fg=RED_HEX, font=("Consolas", 13, "bold")).pack(side="left", padx=10, pady=10)
        sa_var = tk.StringVar(value="0")
        tk.Label(fa, textvariable=sa_var, bg=BG_CARD,
                 fg=RED_HEX, font=("Consolas", 36, "bold"), width=4).pack(side="right", padx=10)

        fb = tk.Frame(win, bg=BG_CARD)
        fb.pack(fill="x", padx=24, pady=6)
        tk.Label(fb, text="  TEAM B  ", bg=BG_CARD,
                 fg=BLUE_HEX, font=("Consolas", 13, "bold")).pack(side="left", padx=10, pady=10)
        sb_var = tk.StringVar(value="0")
        tk.Label(fb, textvariable=sb_var, bg=BG_CARD,
                 fg=BLUE_HEX, font=("Consolas", 36, "bold"), width=4).pack(side="right", padx=10)

        tk.Label(win, text="TIME REMAINING", bg=BG,
                 fg=DIM_HEX, font=("Consolas", 10)).pack(pady=(14, 2))
        t_var = tk.StringVar(value="--:--")
        t_lbl = tk.Label(win, textvariable=t_var, bg=BG,
                         fg=WHITE_HEX, font=("Consolas", 48, "bold"))
        t_lbl.pack(pady=(0, 18))

        return sa_var, sb_var, t_var, t_lbl

    # ── Monitor picker dialog ─────────────────────────────────────────────────
    def launch_ui_after_pick(monitors):
        """
        Show a small dialog so the user picks which monitor gets
        the Control panel and which gets the Scoreboard.
        Called with a list of screeninfo Monitor objects (may be empty).
        """
        picker = tk.Tk()
        picker.title("Battle Blaster — Monitor Setup")
        picker.configure(bg=BG)
        picker.resizable(False, False)

        tk.Label(picker, text="⚡ MONITOR SETUP", bg=BG,
                 fg=WHITE_HEX, font=("Consolas", 14, "bold")).pack(pady=(16, 4))

        # Show detected monitors and let user label them
        monitor_entries = []
        if monitors:
            tk.Label(picker, text="Label each monitor (e.g. 1, 2, A, B …)",
                     bg=BG, fg=DIM_HEX, font=("Consolas", 9)).pack(pady=(0, 6))
            for i, m in enumerate(monitors):
                name = getattr(m, 'name', f'Monitor {i}')
                row  = tk.Frame(picker, bg=BG)
                row.pack(fill="x", padx=20, pady=2)
                tk.Label(row, text=f"{name}  ({m.width}×{m.height})",
                         bg=BG, fg=WHITE_HEX,
                         font=("Consolas", 9), width=28, anchor="w").pack(side="left")
                e = tk.Entry(row, width=6, bg=BTN_BG, fg=WHITE_HEX,
                             insertbackground=WHITE_HEX, relief="flat",
                             font=("Consolas", 10))
                e.pack(side="left", padx=6)
                monitor_entries.append((m, e))
        else:
            tk.Label(picker,
                     text="screeninfo not available.\nWindows will open on the primary monitor.",
                     bg=BG, fg=DIM_HEX, font=("Consolas", 9)).pack(pady=6, padx=20)

        sep = tk.Frame(picker, bg=DIM_HEX, height=1)
        sep.pack(fill="x", padx=16, pady=10)

        tk.Label(picker, text="Control panel → monitor label:",
                 bg=BG, fg=WHITE_HEX, font=("Consolas", 10)).pack(anchor="w", padx=20)
        ctrl_entry = tk.Entry(picker, width=8, bg=BTN_BG, fg=WHITE_HEX,
                              insertbackground=WHITE_HEX, relief="flat",
                              font=("Consolas", 11))
        ctrl_entry.pack(anchor="w", padx=20, pady=(2, 8))

        tk.Label(picker, text="Scoreboard → monitor label:",
                 bg=BG, fg=WHITE_HEX, font=("Consolas", 10)).pack(anchor="w", padx=20)
        board_entry = tk.Entry(picker, width=8, bg=BTN_BG, fg=WHITE_HEX,
                               insertbackground=WHITE_HEX, relief="flat",
                               font=("Consolas", 11))
        board_entry.pack(anchor="w", padx=20, pady=(2, 12))

        def find_monitor(label):
            label = label.strip()
            if not label:
                return None
            for m, e in monitor_entries:
                if e.get().strip() == label:
                    return m
            return None

        def on_start():
            ctrl_mon  = find_monitor(ctrl_entry.get())
            board_mon = find_monitor(board_entry.get())
            picker.destroy()
            open_main_windows(ctrl_mon, board_mon)

        tk.Button(picker, text="▶  LAUNCH", command=on_start,
                  bg="#1a3a1a", fg="#44ff88", activebackground="#2a5a2a",
                  activeforeground="#44ff88", relief="flat",
                  font=("Consolas", 12, "bold"), pady=8, cursor="hand2").pack(
                      fill="x", padx=20, pady=(0, 16))

        picker.mainloop()

    # ── Actually open the two windows ─────────────────────────────────────────
    def open_main_windows(ctrl_mon, board_mon):
        root = tk.Tk()

        # Place control window
        if ctrl_mon:
            root.geometry(f"+{ctrl_mon.x}+{ctrl_mon.y}")

        state_var, state_lbl = build_control(root)

        # Place scoreboard window
        board = tk.Toplevel(root)
        if board_mon:
            board.geometry(
                f"{board_mon.width}x{board_mon.height}+{board_mon.x}+{board_mon.y}")
            board.overrideredirect(True)   # fullscreen borderless on chosen monitor
            board.bind("<Escape>", lambda e: board.destroy())
        else:
            root.update_idletasks()
            cx = root.winfo_x() + root.winfo_width() + 12
            cy = root.winfo_y()
            board.geometry(f"+{cx}+{cy}")

        sa_var, sb_var, t_var, t_lbl = build_scoreboard(board)

        def refresh():
            st = game.state
            state_var.set(f"● {st}")
            state_lbl.configure(fg=STATE_COLORS.get(st, DIM_HEX))

            sa_var.set(str(game.teams['A'].score))
            sb_var.set(str(game.teams['B'].score))

            if st == 'PLAYING':
                elapsed   = time.time() - game.game_start_time
                remaining = max(0.0, GAME_DURATION - elapsed)
                mins = int(remaining) // 60
                secs = int(remaining) % 60
                t_var.set(f"{mins:02d}:{secs:02d}")
                t_lbl.configure(fg="#ff4444" if remaining < 30 else WHITE_HEX)
            elif st == 'GAMEOVER':
                t_var.set("00:00")
                t_lbl.configure(fg="#ff4444")
            else:
                t_var.set("--:--")
                t_lbl.configure(fg=DIM_HEX)

            root.after(200, refresh)

        refresh()
        root.mainloop()

    # ── Entry: detect monitors then show picker ────────────────────────────────
    monitors = []
    if SCREENINFO_OK:
        try:
            monitors = screeninfo.get_monitors()
        except Exception:
            monitors = []

    launch_ui_after_pick(monitors)
