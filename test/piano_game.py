import socket
import struct
import time
import threading
import random
import copy
import psutil
import os
import sys
import subprocess
import importlib.util
import math
import wave
from pathlib import Path
from math import gcd

import json

def _ensure_packages_installed():
    """Auto-install numpy, scipy, and pygame if missing."""
    packages = {
        "numpy": "numpy",
        "scipy": "scipy",
        "pygame": "pygame",
    }
    for import_name, pip_name in packages.items():
        if importlib.util.find_spec(import_name) is None:
            print(f"[SETUP] {pip_name} missing. Auto-installing...", flush=True)
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install",
                     "--disable-pip-version-check", "--no-input", "--quiet", pip_name],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode == 0:
                    print(f"[SETUP] {pip_name} installed.", flush=True)
                else:
                    print(f"[SETUP] {pip_name} install failed (code {result.returncode})", flush=True)
            except Exception as e:
                print(f"[SETUP] {pip_name} install exception: {e}", flush=True)

_ensure_packages_installed()

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    from scipy.io import wavfile
    from scipy.signal import resample_poly
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

def _ensure_mido_installed():
    """Fast one-time check/install for mido on startup."""
    if importlib.util.find_spec("mido") is not None:
        return True

    print(f"[MIDI] mido missing for python={sys.executable}. Auto-installing...", flush=True)
    install_cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--quiet",
        "mido",
    ]

    try:
        result = subprocess.run(install_cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0 and importlib.util.find_spec("mido") is not None:
            print("[MIDI] Auto-install complete", flush=True)
            return True

        print(f"[MIDI] Auto-install failed (code {result.returncode})", flush=True)
        if result.stderr:
            print(f"[MIDI] pip stderr: {result.stderr[-250:]}", flush=True)
    except Exception as e:
        print(f"[MIDI] Auto-install exception: {e}", flush=True)

    return False

MIDO_AVAILABLE = _ensure_mido_installed()
try:
    import winsound
    WINSOUND_AVAILABLE = True
except ImportError:
    WINSOUND_AVAILABLE = False

# Import note mutation helper from mutate_midi (octave-shifts out-of-range notes)
try:
    _mutate_midi_dir = os.path.dirname(os.path.abspath(__file__))
    if _mutate_midi_dir not in sys.path:
        sys.path.insert(0, _mutate_midi_dir)
    from mutate_midi import mutate_note as _mutate_midi_note
except Exception:
    # Fallback: same octave-shift logic inline
    def _mutate_midi_note(note: int) -> int:
        PIANO_LOW, PIANO_HIGH = 48, 79
        while note < PIANO_LOW:
            note += 12
        while note > PIANO_HIGH:
            note -= 12
        return max(PIANO_LOW, min(PIANO_HIGH, note))

# --- Sample-based Piano (uses real piano samples) ---
SEMITONE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_TO_SHARP = {
    "Db": "C#", "Eb": "D#", "Fb": "E", "Gb": "F#",
    "Ab": "G#", "Bb": "A#", "Cb": "B",
}

def note_to_midi(name: str) -> int:
    """Convert note name (e.g., 'C4', 'C#4') to MIDI number"""
    name = name.strip()
    for flat, sharp in FLAT_TO_SHARP.items():
        if name.startswith(flat):
            name = sharp + name[len(flat):]
            break
    if len(name) >= 3 and name[1] == "#":
        letter, octave = name[:2], int(name[2:])
    else:
        letter, octave = name[0], int(name[1:])
    return (octave + 1) * 12 + SEMITONE_NAMES.index(letter)

def midi_to_note(midi: int) -> str:
    """Convert MIDI number to note name"""
    octave = midi // 12 - 1
    semitone = midi % 12
    return f"{SEMITONE_NAMES[semitone]}{octave}"

class SampleBank:
    """
    Loads .wav files named like C4.wav, C#4.wav, Db4.wav …
    Pitch-shifts via resampling for notes that have no exact sample.
    """
    TARGET_SR = 44100

    def __init__(self, sample_dir: str):
        self.sample_dir = Path(sample_dir)
        self._raw = {}
        self._cache = {}
        self._load_all()

    def _load_all(self):
        if not self.sample_dir.exists():
            raise FileNotFoundError(f"Sample directory not found: {self.sample_dir}")

        loaded = 0
        for wav_path in sorted(self.sample_dir.glob("*.wav")):
            stem = wav_path.stem
            try:
                midi = note_to_midi(stem)
            except (ValueError, KeyError, IndexError):
                continue
            try:
                sr, data = wavfile.read(str(wav_path))
            except Exception as e:
                print(f"  [SAMPLE] Could not read {wav_path.name}: {e}")
                continue

            # Normalise to float32 mono
            if data.dtype == np.int16:
                data = data.astype(np.float32) / 32768.0
            elif data.dtype == np.int32:
                data = data.astype(np.float32) / 2_147_483_648.0
            elif data.dtype != np.float32:
                data = data.astype(np.float32)
            if data.ndim == 2:
                data = data.mean(axis=1)

            # Resample to TARGET_SR if needed
            if sr != self.TARGET_SR:
                if HAS_SCIPY:
                    g = gcd(self.TARGET_SR, sr)
                    data = resample_poly(data, self.TARGET_SR // g, sr // g).astype(np.float32)
                else:
                    ratio = self.TARGET_SR / sr
                    new_len = int(len(data) * ratio)
                    idx = np.clip((np.arange(new_len) / ratio).astype(int), 0, len(data) - 1)
                    data = data[idx]

            self._raw[midi] = data.astype(np.float32)
            loaded += 1

        if loaded == 0:
            raise RuntimeError(f"No usable .wav files in '{self.sample_dir}'")
        print(f"[SAMPLE] Loaded {loaded} samples from '{self.sample_dir}'")

    def _pitch_shift(self, data: np.ndarray, semitones: float) -> np.ndarray:
        """Pitch-shift audio data by semitones"""
        if semitones == 0:
            return data
        ratio = 2 ** (semitones / 12)
        if HAS_SCIPY:
            num = round(ratio * 1000)
            den = 1000
            g = gcd(num, den)
            shifted = resample_poly(data, den // g, num // g).astype(np.float32)
        else:
            new_len = int(len(data) / ratio)
            idx = np.clip((np.arange(new_len) * ratio).astype(int), 0, len(data) - 1)
            shifted = data[idx].astype(np.float32)
        return shifted

    def get(self, midi: int, velocity: float = 0.85) -> np.ndarray:
        """Get sample for MIDI note, pitch-shifted from nearest available sample"""
        if midi not in self._cache:
            nearest = min(self._raw.keys(), key=lambda m: abs(m - midi))
            semitones = midi - nearest
            self._cache[midi] = self._pitch_shift(self._raw[nearest], semitones)
        return (self._cache[midi] * velocity).astype(np.float32)

# --- Configuration ---
_CFG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tetris_config.json")

def _load_config():
    defaults = {
        "device_ip": "255.255.255.255",
        "send_port": 7274,
        "recv_port": 7275,
        "bind_ip": "0.0.0.0"
    }
    try:
        if os.path.exists(_CFG_FILE):
            with open(_CFG_FILE, encoding="utf-8") as f:
                return {**defaults, **json.load(f)}
    except: pass
    return defaults

CONFIG = _load_config()

SCORE_WINDOW_PROCESS = None

# --- Networking Constants ---
UDP_SEND_IP = CONFIG.get("device_ip", "255.255.255.255")
UDP_SEND_PORT = CONFIG.get("send_port", 7274)
UDP_LISTEN_PORT = CONFIG.get("recv_port", 7275)

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
DIM_DARK_BLUE = (6, 14, 38)
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

class PianoController:
    """Manages piano note mapping and sound generation for button presses"""
    def __init__(self):
        self.note_frequencies = self._generate_note_frequencies()
        self.button_to_note = self._map_buttons_to_notes()
        self.prev_button_states = {}
        self.sound_threads = []
        self._button_to_note_index = {}
        self._button_side_map = {}
        self.enable_left = True
        self.enable_right = True
        self.active_hold_channels = {}
        self.active_hold_started_at = {}
        self.sustain_sound_cache = {}
        
        # Try to load real piano samples
        self.sample_bank = None
        try:
            piano_sample_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")
            if os.path.exists(piano_sample_dir) and NUMPY_AVAILABLE and HAS_SCIPY:
                self.sample_bank = SampleBank(piano_sample_dir)
            else:
                pass
        except Exception as e:
            print(f"Failed to load sample bank: {e}", flush=True)
            self.sample_bank = None
        
        # Build piano keyboard mapping on both sides.
        self._build_piano_column_mapping()
        
        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.init()
                pygame.mixer.set_num_channels(64)
                self.mixer_available = True
            except Exception as e:
                self.mixer_available = False
                print(f"Pygame mixer init failed: {e}", flush=True)
        else:
            self.mixer_available = False

    def _build_piano_column_mapping(self):
        """
        Build mapping for vertical piano keyboard columns on both sides.
        Border columns (0-1 left, 14-15 right) are visual only.
        Playable columns: 2 left, 13 right (single column each side)
        Note progression: bottom row = lowest note, top row = highest note
        """
        self._button_to_note_index = {}
        self._button_side_map = {}

        left_columns_x = [2] if self.enable_left else []
        right_columns_x = [BOARD_WIDTH - 3] if self.enable_right else []
        note_count = min(len(self.note_frequencies), BOARD_HEIGHT)

        for note_idx in range(note_count):
            # y goes from bottom to top, so pitch rises as y decreases.
            y = (BOARD_HEIGHT - 1) - note_idx

            for x in left_columns_x:
                left_button_idx = self._get_led_index(x, y)
                self._button_to_note_index[left_button_idx] = note_idx
                self._button_side_map[left_button_idx] = "left"

            for x in right_columns_x:
                right_button_idx = self._get_led_index(x, y)
                self._button_to_note_index[right_button_idx] = note_idx
                self._button_side_map[right_button_idx] = "right"

    def configure_active_sides(self, enable_left=True, enable_right=True):
        """Enable piano input columns by side and rebuild touch mapping."""
        if not enable_left and not enable_right:
            enable_left = True
            enable_right = True

        self.enable_left = enable_left
        self.enable_right = enable_right

        # Stop sustained notes when remapping sides.
        for held_button in list(self.active_hold_channels.keys()):
            self._stop_held_note(held_button)

        self._build_piano_column_mapping()

        

    def _get_led_index(self, x, y):
        """Convert (x, y) board position to LED/button index (same logic as Player.get_led_index)"""
        channel = y // 4
        row_in_channel = y % 4

        if row_in_channel % 2 == 0:
            led_index = row_in_channel * 16 + x
        else:
            led_index = row_in_channel * 16 + (15 - x)

        return channel * 64 + led_index

    def _generate_note_frequencies(self):
        """
        Generate 50 note frequencies starting from C3.
        Uses equal temperament tuning: each semitone = frequency * 2^(1/12)
        C3 = 130.81 Hz, goes up chromatically for 50 notes
        """
        notes = []
        c3_freq = 130.81  # C3 frequency in Hz
        semitone_ratio = 2.0 ** (1.0 / 12.0)  # Ratio between semitones
        
        for i in range(50):
            freq = c3_freq * (semitone_ratio ** i)
            notes.append(freq)
        
        return notes

    def _map_buttons_to_notes(self):
        """
        Create mapping from button indices to note indices.
        Buttons are mapped in order: player 1-10, lane 1-5 each = 50 buttons total
        """
        mapping = {}
        
        # Button indices are organized from top to bottom in the row groups
        # We'll map them sequentially to our 50 notes
        button_index = 0
        
        # For each row band (5 bands = 10 players)
        # Band 0: Players 1-2, Band 1: Players 3-4, etc.
        # Each band has 5 lanes (left and right variants)
        
        for band in range(5):
            for lane in range(5):
                # Left player buttons (P1, P3, P5, P7, P9)
                left_button = band * 10 + lane
                mapping[left_button] = button_index
                button_index += 1
                
                # Right player buttons (P2, P4, P6, P8, P10)
                right_button = band * 10 + 5 + lane
                mapping[right_button] = button_index
                button_index += 1
        
        return mapping

    def _generate_piano_tone(self, freq, duration, vol=0.45, sample_rate=44100):
        """Generate a soft piano-like tone with mellow harmonics and smoothing."""
        n_samples = int(sample_rate * duration)
        data = bytearray()

        # Softer, less percussive envelope.
        attack = 0.014
        decay = 0.18
        sustain_level = 0.32
        release = min(0.30, duration * 0.55)
        release_start = max(attack + decay, duration - release)

        # One-pole low-pass filter state for warmth.
        lp_prev = 0.0
        # Lower cutoff removes synthetic brightness.
        cutoff_hz = 1750.0
        alpha = (2.0 * math.pi * cutoff_hz) / (sample_rate + (2.0 * math.pi * cutoff_hz))

        # Tiny slow phase drift to reduce static synth feel.
        drift_rate = 0.22

        for i in range(n_samples):
            t = i / sample_rate
            drift = 1.0 + (0.0012 * math.sin(2.0 * math.pi * drift_rate * t))
            base_freq = freq * drift

            # Mellow harmonic stack (fewer bright partials).
            fundamental = math.sin(2.0 * math.pi * base_freq * t)
            harmonic_2 = 0.30 * math.sin(2.0 * math.pi * (base_freq * 2.0) * t)
            harmonic_3 = 0.10 * math.sin(2.0 * math.pi * (base_freq * 3.0) * t)
            harmonic_4 = 0.04 * math.sin(2.0 * math.pi * (base_freq * 4.0) * t)

            # Subtle, soft key noise instead of sharp hammer click.
            key_noise = 0.0
            if t < 0.012:
                key_noise = random.uniform(-1.0, 1.0) * (1.0 - (t / 0.012)) * 0.012

            tone = fundamental + harmonic_2 + harmonic_3 + harmonic_4 + key_noise

            # ADSR envelope.
            if t < attack:
                env = t / attack
            elif t < attack + decay:
                decay_t = (t - attack) / decay
                env = 1.0 - (1.0 - sustain_level) * decay_t
            elif t < release_start:
                env = sustain_level
            else:
                rel_t = (t - release_start) / max(release, 1e-6)
                env = max(0.0, sustain_level * (1.0 - rel_t))

            # Natural body decay.
            env *= math.exp(-1.9 * t / max(duration, 1e-6))

            dry = tone * env * vol
            # Low-pass filter for soft timbre.
            lp_prev += alpha * (dry - lp_prev)
            sample = max(-1.0, min(1.0, lp_prev))

            scaled = int((sample + 1.0) * 127.5)
            data.append(max(0, min(255, scaled)))

        return data

    def _generate_piano_sustain_tone(self, freq, duration=0.42, vol=0.20, sample_rate=44100):
        """Generate a soft, loopable sustain body for held notes."""
        n_samples = int(sample_rate * duration)
        data = bytearray()
        fade_samples = min(1024, max(128, n_samples // 20))

        lp_prev = 0.0
        cutoff_hz = 1400.0
        alpha = (2.0 * math.pi * cutoff_hz) / (sample_rate + (2.0 * math.pi * cutoff_hz))

        for i in range(n_samples):
            t = i / sample_rate

            # Even softer sustain spectrum.
            fundamental = math.sin(2.0 * math.pi * freq * t)
            harmonic_2 = 0.22 * math.sin(2.0 * math.pi * (freq * 2.0) * t)
            harmonic_3 = 0.07 * math.sin(2.0 * math.pi * (freq * 3.0) * t)
            tone = (fundamental + harmonic_2 + harmonic_3) * vol

            # Fade-in/out on loop edges to avoid clicks.
            edge = 1.0
            if i < fade_samples:
                edge = i / float(fade_samples)
            elif i >= n_samples - fade_samples:
                edge = (n_samples - i - 1) / float(fade_samples)

            dry = tone * edge
            lp_prev += alpha * (dry - lp_prev)
            sample = max(-1.0, min(1.0, lp_prev))

            scaled = int((sample + 1.0) * 127.5)
            data.append(max(0, min(255, scaled)))

        return data

    def _get_sustain_sound(self, note_idx, freq):
        """Get or create a cached sustain sound object for a note."""
        if note_idx not in self.sustain_sound_cache:
            sustain_data = self._generate_piano_sustain_tone(freq)
            self.sustain_sound_cache[note_idx] = pygame.mixer.Sound(buffer=bytes(sustain_data))
        return self.sustain_sound_cache[note_idx]

    def _start_held_note(self, button_idx, note_idx, freq):
        """Start a held note: play sample with looping sustain until release."""
        if self.sample_bank is not None and self.mixer_available:
            try:
                # Get MIDI note number (C3 = 48, +note_idx semitones)
                midi_note = 48 + note_idx
                
                # Get audio sample from bank and loop it
                audio_data = self.sample_bank.get(midi_note, velocity=0.80)
                
                if len(audio_data) > 0:
                    # Create sound and play once (samples have natural decay, no looping)
                    sound = pygame.mixer.Sound(buffer=bytes((audio_data * 32767).astype(np.int16)))
                    sustain_channel = pygame.mixer.find_channel(True)
                    if sustain_channel is None:
                        raise RuntimeError("No available mixer channel for sustain")
                    
                    sustain_channel.set_volume(0.70)
                    sustain_channel.play(sound)
                    self.active_hold_channels[button_idx] = sustain_channel
                    self.active_hold_started_at[button_idx] = time.time()
                else:
                    raise RuntimeError("Empty audio data from sample bank")
            except Exception as e:
                print(f"Sample playback failed: {e}, using synthetic fallback", flush=True)
                self._start_held_note_synthetic(button_idx, note_idx, freq)
        else:
            # No sample bank, use synthetic tone
            self._start_held_note_synthetic(button_idx, note_idx, freq)

    def _start_held_note_synthetic(self, button_idx, note_idx, freq):
        """Start a held note using synthetic generation (fallback)."""
        if self.mixer_available:
            try:
                # Short attack to keep piano feel at note onset.
                attack_data = self._generate_piano_tone(freq, duration=0.24, vol=0.50)
                attack_sound = pygame.mixer.Sound(buffer=bytes(attack_data))
                attack_channel = pygame.mixer.find_channel(True)
                if attack_channel is not None:
                    attack_channel.set_volume(0.85)
                    attack_channel.play(attack_sound)
                else:
                    attack_sound.play()

                sustain_sound = self._get_sustain_sound(note_idx, freq)
                sustain_channel = pygame.mixer.find_channel(True)
                if sustain_channel is None:
                    raise RuntimeError("No available mixer channel for sustain")

                sustain_channel.set_volume(0.55)
                sustain_channel.play(sustain_sound, loops=-1, fade_ms=25)
                self.active_hold_channels[button_idx] = sustain_channel
                self.active_hold_started_at[button_idx] = time.time()
            except Exception as e:
                print(f"Synthetic hold note start failed: {e}", flush=True)
                self.play_note(freq, duration=0.70)
        else:
            self.play_note(freq, duration=0.70)

    def _stop_held_note(self, button_idx):
        """Stop a held note when the button is released."""
        channel = self.active_hold_channels.pop(button_idx, None)
        self.active_hold_started_at.pop(button_idx, None)
        if channel is not None:
            try:
                channel.fadeout(120)
            except Exception:
                pass

    def _release_other_holds_on_same_side(self, keep_button_idx):
        """Release older held notes on the same side to avoid stuck notes during fast swipes."""
        side = self._button_side_map.get(keep_button_idx)
        if side is None:
            return

        to_release = []
        for held_button_idx in self.active_hold_channels.keys():
            if held_button_idx == keep_button_idx:
                continue
            if self._button_side_map.get(held_button_idx) == side:
                to_release.append(held_button_idx)

        for button_idx in to_release:
            self._stop_held_note(button_idx)

    def play_note(self, frequency, duration=0.3):
        """
        Play a piano note with given frequency.
        Spawns in background thread to avoid blocking.
        """
        duration = max(duration, 0.52)
        
        def _play():
            try:
                audio_data = self._generate_piano_tone(frequency, duration, vol=0.50)
                
                if self.mixer_available and len(audio_data) > 0:
                    # Use pygame mixer
                    try:
                        # Create a pygame sound from the raw audio data
                        sound = pygame.mixer.Sound(buffer=bytes(audio_data))
                        channel = pygame.mixer.find_channel(True)
                        if channel is not None:
                            channel.set_volume(0.90)
                            channel.play(sound)
                        else:
                            sound.play()
                    except Exception as mixer_err:
                        self._play_audio_wave(audio_data)
                else:
                    # Fallback: save and play using wave
                    self._play_audio_wave(audio_data)
            except Exception as e:
                print(f"Error playing note: {e}")
        
        thread = threading.Thread(target=_play, daemon=True)
        thread.start()
        self.sound_threads = [t for t in self.sound_threads if t.is_alive()]  # Clean up dead threads

    def _play_audio_wave(self, audio_data):
        """Play audio data directly using wave module"""
        try:
            import tempfile
            # Use Windows temp directory
            temp_dir = tempfile.gettempdir()
            temp_file = os.path.join(temp_dir, "piano_note.wav")
            
            with wave.open(temp_file, 'w') as f:
                f.setnchannels(1)
                f.setsampwidth(1)  # 8-bit audio
                f.setframerate(44100)
                f.writeframes(bytes(audio_data))
            
            # Try to play using available method
            if os.name == 'nt':  # Windows
                if WINSOUND_AVAILABLE:
                    winsound.PlaySound(temp_file, winsound.SND_FILENAME | winsound.SND_ASYNC)
                else:
                    # Last-resort fallback when winsound is unavailable
                    os.startfile(temp_file)
            else:  # Linux/Mac
                os.system(f"aplay '{temp_file}'")
        except Exception as e:
            print(f"Wave playback failed: {e}")

    def handle_button_press(self, button_states, player_button_map=None):
        """
        Detect button transitions and keep notes held while a button stays pressed.
        """
        pressed_started = 0
        released_count = 0

        # First, check if any unmapped button (empty area) is pressed.
        # If so, stop all active holds immediately (user moved away from keyboard).
        for button_idx in range(len(button_states)):
            if button_idx not in self._button_to_note_index:
                is_pressed = button_states[button_idx]
                was_pressed = self.prev_button_states.get(button_idx, False)
                if is_pressed and not was_pressed and self.active_hold_channels:
                    for held_button in list(self.active_hold_channels.keys()):
                        self._stop_held_note(held_button)

        for button_idx, note_idx in self._button_to_note_index.items():
            is_pressed = button_states[button_idx] if button_idx < len(button_states) else False
            was_pressed = self.prev_button_states.get(button_idx, False)

            if is_pressed and not was_pressed:
                if note_idx < len(self.note_frequencies):
                    # Keep opposite-side holds alive; only release older holds
                    # on the same side to avoid accidental cut-offs on side switch.
                    self._release_other_holds_on_same_side(button_idx)
                    
                    freq = self.note_frequencies[note_idx]
                    self._start_held_note(button_idx, note_idx, freq)
                    pressed_started += 1

            elif (not is_pressed) and was_pressed:
                self._stop_held_note(button_idx)
                released_count += 1

        # State-mismatch safeguard: if button is NOT pressed but still has an active hold, stop it immediately.
        for button_idx in list(self.active_hold_started_at.keys()):
            is_pressed = button_states[button_idx] if button_idx < len(button_states) else False
            if not is_pressed and button_idx in self.active_hold_started_at:
                self._stop_held_note(button_idx)

        # Update previous state snapshot.
        self.prev_button_states = {i: button_states[i] for i in range(len(button_states))}

    def _get_note_name(self, semitone_offset):
        """Convert semitone offset from C3 to note name"""
        note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        note_in_octave = semitone_offset % 12
        octave = 3 + (semitone_offset // 12)
        return f"{note_names[note_in_octave]}{octave}"


class MidiSongPlayer:
    """
    Visual-only MIDI guide.
    Phase 1: notes fade in while stationary at center.
    Phase 2: notes move toward the right piano column.
    """
    # Visual-only mode: notes stay in the middle and fade in before play time.
    MIDDLE_COL_LEFT = 7
    MIDDLE_COL_RIGHT = 8
    TARGET_COL_LEFT = 2
    TARGET_COL_RIGHT = 13
    MOVE_SPEED = 1
    MOVE_STEP_FRAMES = 2  # Move every N render frames to slow travel
    LINGER_SECONDS = 0.20 # Keep note visible briefly at piano roll
    HARD_TEMPO_SCALE = 2.0     # 2x time => half BPM
    LEAD_TICKS = 13  # ~0.65s at 20 FPS (render loop is 50 ms)
    MAX_SPAWNS_PER_FRAME = 6  # Queue budget to avoid bursty visual updates

    SHARP_POSITIONS = {1, 3, 6, 8, 10}
    # Right-side colors (going right)
    COLOR_NATURAL_RIGHT = (0, 200, 220)    # cyan
    COLOR_SHARP_RIGHT   = (255, 130, 0)    # orange
    # Left-side colors (going left)
    COLOR_NATURAL_LEFT  = (180, 0, 255)    # purple
    COLOR_SHARP_LEFT    = (0, 230, 80)     # green
    DIRECTION_INTERVAL  = 7.0   # seconds between direction changes

    def __init__(self, midi_path, piano_controller, difficulty='medium'):
        self.piano = piano_controller
        self.midi_path = midi_path
        self.difficulty = difficulty  # 'easy', 'medium', 'hard'
        self.tempo_scale = self.HARD_TEMPO_SCALE if difficulty == 'hard' else 1.0
        self.enable_left = True
        self.enable_right = True
        self.single_target_side = None
        self.all_notes = []      # immutable source notes for replay
        self.flying_notes = []   # active on-screen note blocks
        self.pending_notes = []  # notes waiting to be spawned, sorted by spawn_time
        self.spawn_queue = []    # due notes waiting to be released under frame budget
        self.song_started = False
        self.start_time = None
        self.finished = False
        self._current_elapsed = 0.0
        self._update_counter = 0
        self._load_midi(midi_path)
        self._reset_song_state()

    def _reset_song_state(self):
        """Reset runtime song state so the same MIDI can be played again."""
        self.pending_notes = [dict(n) for n in self.all_notes]
        self.spawn_queue = []
        self.flying_notes = []
        self.finished = False
        self.song_started = False
        self._current_elapsed = 0.0
        self._update_counter = 0
        self._going_right = True          # current travel direction
        self._next_interval_at = self.DIRECTION_INTERVAL  # elapsed time of next change

    def configure_active_sides(self, enable_left=True, enable_right=True):
        """Restrict note targets to active piano side when only one side has players."""
        if not enable_left and not enable_right:
            enable_left = True
            enable_right = True

        self.enable_left = enable_left
        self.enable_right = enable_right
        if enable_left and not enable_right:
            self.single_target_side = 'left'
        elif enable_right and not enable_left:
            self.single_target_side = 'right'
        else:
            self.single_target_side = None

    def _load_midi(self, path):
        try:
            import mido
        except ImportError:
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "mido"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode != 0:
                    return

                import mido
            except Exception as e:
                print(f"MIDI auto-install failed: {e}", flush=True)
                return

        mid = mido.MidiFile(path)
        lead_time = self.LEAD_TICKS * 0.05  # 13 frames * 50ms per frame = 0.65s

        events = []
        abs_time = 0.0
        active_notes = {}
        for msg in mid:               # mido yields messages with time in seconds
            abs_time += msg.time

            if msg.type == 'note_on' and msg.velocity > 0:
                active_notes.setdefault(msg.note, []).append(abs_time)
            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                starts = active_notes.get(msg.note)
                if starts:
                    start_time = starts.pop(0)
                    hold_seconds = max(0.0, abs_time - start_time)
                    events.append((start_time, msg.note, hold_seconds))

        # Fallback for notes that never got an explicit note_off.
        for midi_note, starts in active_notes.items():
            for start_time in starts:
                events.append((start_time, midi_note, 0.25))

        parsed_notes = []
        note_index = 0  # For hard mode: alternate sides per note
        for play_time, midi_note, hold_seconds in events:
            scaled_play_time = play_time * self.tempo_scale
            # Shift out-of-range notes into piano range (C3–G5, MIDI 48–79) by octave
            midi_note = _mutate_midi_note(midi_note)
            note_idx = midi_note - 48  # guaranteed in [0, BOARD_HEIGHT-1]
            row = (BOARD_HEIGHT - 1) - note_idx
            note_dict = {
                'spawn_time': max(0.0, scaled_play_time - lead_time),
                'play_time':  scaled_play_time,
                'note_idx':   note_idx,
                'row':        row,
                'hold_seconds': max(0.0, hold_seconds * self.tempo_scale),
            }
            # For hard mode, force alternating sides
            if self.difficulty == 'hard':
                note_dict['forced_side'] = 'left' if note_index % 2 == 0 else 'right'
                note_index += 1
            parsed_notes.append(note_dict)

        parsed_notes.sort(key=lambda n: n['spawn_time'])
        self.all_notes = parsed_notes

    def start(self):
        # Safety: if note cache is empty for any reason, retry loading now.
        if not self.all_notes:
            try:
                file_exists = os.path.exists(self.midi_path)
                if file_exists:
                    self._load_midi(self.midi_path)
            except Exception as e:
                print(f"MIDI reload error: {e}", flush=True)

        self._reset_song_state()
        # Subtract START_DELAY so elapsed is negative for the first second,
        # meaning no notes will spawn until 1s after the piano roll appears.
        self.start_time = time.time() + 1.0
        self.song_started = True

    def update(self):
        """Call once per frame to advance note positions."""
        if not self.song_started or self.finished:
            return

        self._update_counter += 1
        elapsed = time.time() - self.start_time
        queued_this_frame = 0
        spawned_this_frame = 0

        # Move due notes into queue first.
        while self.pending_notes and self.pending_notes[0]['spawn_time'] <= elapsed:
            self.spawn_queue.append(self.pending_notes.pop(0))
            queued_this_frame += 1

        # Toggle direction only in two-sided mode.
        if self.single_target_side is None and elapsed >= self._next_interval_at:
            self._going_right = not self._going_right
            self._next_interval_at += self.DIRECTION_INTERVAL

        # Release only a limited number from queue each frame.
        budget = self.MAX_SPAWNS_PER_FRAME
        while budget > 0 and self.spawn_queue:
            n = self.spawn_queue.pop(0)
            spawned_this_frame += 1
            budget -= 1
            # In one-sided mode, always travel toward the active piano side from the opposite end.
            if self.single_target_side == 'left':
                going_right = False
            elif self.single_target_side == 'right':
                going_right = True
            else:
                # Use forced_side if present (hard mode), otherwise current direction.
                going_right = n.get('forced_side', 'right' if self._going_right else 'left') == 'right'
            # Pick side, direction, and color set
            if going_right:
                spawn_x   = self.MIDDLE_COL_RIGHT if self.single_target_side is None else self.TARGET_COL_LEFT
                target_x  = self.TARGET_COL_RIGHT
                dx        = self.MOVE_SPEED
                color_natural = self.COLOR_NATURAL_RIGHT
                color_sharp   = self.COLOR_SHARP_RIGHT
            else:
                spawn_x   = self.MIDDLE_COL_LEFT if self.single_target_side is None else self.TARGET_COL_RIGHT
                target_x  = self.TARGET_COL_LEFT
                dx        = -self.MOVE_SPEED
                color_natural = self.COLOR_NATURAL_LEFT
                color_sharp   = self.COLOR_SHARP_LEFT
            is_sharp = (n['note_idx'] % 12) in self.SHARP_POSITIONS
            note_color = color_sharp if is_sharp else color_natural
            # Mirror row vertically for left-going notes
            row = n['row'] if going_right else (BOARD_HEIGHT - 1 - n['note_idx'])
            self.flying_notes.append({
                'row': row, 'x': spawn_x,
                'spawn_x': spawn_x,
                'color': note_color,
                'note_idx': n['note_idx'],
                'hold_seconds': n.get('hold_seconds', 0.0),
                'spawn_time': n['spawn_time'], 'play_time': n['play_time'],
                'phase': 'fade', 'target_x': target_x, 'dx': dx,
            })

        self._current_elapsed = elapsed

        # Fade phase at center -> move phase toward piano roll.
        for n in self.flying_notes:
            if n['phase'] == 'fade':
                if elapsed >= n['play_time']:
                    n['phase'] = 'move'
            elif n['phase'] == 'move':
                # Slower motion: only step every MOVE_STEP_FRAMES frames.
                if (self._update_counter % self.MOVE_STEP_FRAMES) == 0:
                    n['x'] += n['dx']

        # Convert reached move notes into linger notes.
        for n in self.flying_notes:
            if n['phase'] == 'move':
                if n['dx'] < 0 and n['x'] <= n['target_x']:
                    n['x'] = n['target_x']
                    n['phase'] = 'linger'
                    max_hold_cells = 1 + min(6, int(max(0.0, n.get('hold_seconds', 0.0)) * 4.0))
                    n['linger_start_counter'] = self._update_counter
                    n['linger_steps'] = max_hold_cells
                elif n['dx'] > 0 and n['x'] >= n['target_x']:
                    n['x'] = n['target_x']
                    n['phase'] = 'linger'
                    max_hold_cells = 1 + min(6, int(max(0.0, n.get('hold_seconds', 0.0)) * 4.0))
                    n['linger_start_counter'] = self._update_counter
                    n['linger_steps'] = max_hold_cells

        # Remove notes only after linger expires.
        kept = []
        for n in self.flying_notes:
            if n['phase'] == 'linger':
                linger_start = n.get('linger_start_counter', self._update_counter)
                linger_steps = n.get('linger_steps', 1)
                steps_elapsed = max(0, (self._update_counter - linger_start) // self.MOVE_STEP_FRAMES)
                if steps_elapsed >= linger_steps:
                    continue
            kept.append(n)
        self.flying_notes = kept

        # Mark as finished when nothing is left
        if not self.pending_notes and not self.spawn_queue and not self.flying_notes:
            self.finished = True

    def check_piano_hit(self, side: str, note_idx: int) -> bool:
        """
        Returns True if there is a linger-phase note at the given side's piano
        column matching note_idx. Marks it as scored so it only awards points
        once, but keeps the note visible for its natural retract/linger effect.
        """
        target_x = self.TARGET_COL_RIGHT if side == 'right' else self.TARGET_COL_LEFT
        for n in self.flying_notes:
            if n['phase'] == 'linger' and n['x'] == target_x and n['note_idx'] == note_idx:
                if n.get('scored', False):
                    return False
                n['scored'] = True
                return True
        return False

    def get_flying_notes(self):
        """Return two-phase guide notes: fade at center, then move outward."""
        result = []
        for n in self.flying_notes:
            if n['phase'] == 'fade':
                total = max(0.001, n['play_time'] - n['spawn_time'])
                t = (self._current_elapsed - n['spawn_time']) / total
                t = max(0.0, min(1.0, t))
                # brightness goes from 0.15 at spawn to 1.0 at play time
                brightness = max(0.15, t)
            else:
                brightness = 1.0
            r = int(n['color'][0] * brightness)
            g = int(n['color'][1] * brightness)
            b = int(n['color'][2] * brightness)
            result.append({**n, 'color': (r, g, b)})
        return result

    def _predict_side_for_spawn_time(self, spawn_time):
        """Predict side for future note preview in two-sided mode."""
        if self.single_target_side is not None:
            return self.single_target_side

        # Start from current direction and count interval toggles until spawn_time.
        right = self._going_right
        if spawn_time >= self._next_interval_at:
            toggles = int((spawn_time - self._next_interval_at) / self.DIRECTION_INTERVAL) + 1
            if toggles % 2 == 1:
                right = not right

        return 'right' if right else 'left'

    def get_next_hit_guides(self, limit=None, preview_window_seconds=10.0):
        """Return upcoming hit guides with time-based opacity info."""
        candidates = []

        # Active on-screen notes are always authoritative.
        for n in self.flying_notes:
            side = 'right' if n.get('target_x') == self.TARGET_COL_RIGHT else 'left'
            candidates.append((n.get('play_time', 0.0), side, n['note_idx']))

        # Notes already due this frame but not yet released.
        for n in self.spawn_queue:
            side = n.get('forced_side')
            if side is None:
                side = self.single_target_side or ('right' if self._going_right else 'left')
            candidates.append((n.get('play_time', 0.0), side, n['note_idx']))

        # Upcoming notes from pending queue.
        for n in self.pending_notes:
            side = n.get('forced_side')
            if side is None:
                side = self._predict_side_for_spawn_time(n['spawn_time'])
            candidates.append((n.get('play_time', 0.0), side, n['note_idx']))

        if not candidates:
            return []

        candidates.sort(key=lambda x: x[0])

        guides = []
        seen = set()
        now = self._current_elapsed
        for play_time, side, note_idx in candidates:
            key = (side, note_idx)
            if key in seen:
                continue
            seen.add(key)

            seconds_away = max(0.0, play_time - now)
            if seconds_away > preview_window_seconds:
                continue

            # Stronger log-based fade-in: stay very transparent until very close
            # to hit, and reach max visibility at ~0.1s before hit.
            log_ratio = math.log1p(seconds_away) / math.log1p(preview_window_seconds)
            raw_visibility = (1.0 - log_ratio) ** 4
            anchor_seconds = 0.1
            anchor_ratio = math.log1p(anchor_seconds) / math.log1p(preview_window_seconds)
            anchor_raw = max(1e-6, (1.0 - anchor_ratio) ** 4)
            # Cap at 60% opacity (40% transparency) even right before hit.
            visibility = min(0.6, raw_visibility / anchor_raw)

            guides.append({
                'side': side,
                'note_idx': note_idx,
                'seconds_away': seconds_away,
                'visibility': max(0.0, min(1.0, visibility)),
            })

            if limit is not None and len(guides) >= limit:
                break

        return guides


class Player:
    """Player class for tracking score and input control"""
    def __init__(self):
        self.points = 0
        self.player_scores = {}
        self.side_scores = {'left': 0, 'right': 0}  # piano-guide hit scores per side
        self.control_rows = [1, 2, 3, 4, 5]  # Control pad rows for groups 0-4
        self.control_column = 1  # Control pads are at column 1
        self.last_scored_states = {}  # Track which flashes we've already scored

    def add_point(self, player_id):
        """Increment total score and per-player score."""
        self.points += 1
        self.player_scores[player_id] = self.player_scores.get(player_id, 0) + 1

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

class PianoGame:
    SONG_BY_DIFFICULTY = {
        'easy': 'Sweden - Minecraft',
        'medium': 'Viva La Vida - Coldplay',
        'hard': 'Moonlight Sonata - Beethoven',
    }

    def __init__(self):
        self.board = [[BLACK for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]

        self.running = True
        self.state = 'PRELOBBY' # PRELOBBY, LOBBY, SIDE_SELECT, COUNTDOWN, PLAYING, GAMEOVER
        self.startup_step = 0
        self.startup_timer = time.time()
        self.countdown_start_time = None
        self.winner_side = None  # 'left' or 'right'
        self.game_over_start_time = None
        self.GAMEOVER_DURATION = 5.0
        self.countdown_sound_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "countdown.wav")
        self.airhorn_sound_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "airhorn.wav")
        self.applause_sound_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "applause.wav")
        self.applause_fallback_sound_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "applause_1.wav")
        self.COUNTDOWN_STEP = 1.5
        self.COUNTDOWN_DURATION = self.COUNTDOWN_STEP * 3

        self.lock = threading.RLock()
        
        # Initialize player and controls
        self.player = Player()
        self.button_states = [False] * MATRIX_TOUCH_COUNT  # Track touch states across full 16x32 matrix
        self.prev_button_states = [False] * MATRIX_TOUCH_COUNT  # Edge detection: tap = False -> True
        # 10-player mapping: each player owns a row-band and has 5 lane buttons.
        self.player_button_map = {}
        
        # Initialize piano controller for button-to-note mapping
        self.piano = PianoController()
        self.midi_player = None

        # Lobby voting state
        self.lobby_start_time = time.time()
        self.LOBBY_DURATION = 12.0  # seconds
        # Zone row boundaries (board is 32 rows tall)
        # easy: rows 0-9, medium: rows 10-20, hard: rows 21-31
        self.LOBBY_ZONES = [
            ('easy',   0,  9,  (0, 220, 60)),
            ('medium', 10, 20, (220, 200, 0)),
            ('hard',   21, 31, (220, 30, 0)),
        ]

        # Side-select state
        self.side_select_start_time = None
        self.SIDE_SELECT_DURATION = 4.0  # seconds (2s longer)
        self.active_piano_sides = {'left': True, 'right': True}
        self.PRELOBBY_START_RECT = (6, 16, 9, 19)  # x0, y0, x1, y1
        self.selected_difficulty = None
        self.scoreboard_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "team_scores.json")
        self._publish_scores()

    def _publish_scores(self):
        left = self.player.side_scores.get('left', 0)
        right = self.player.side_scores.get('right', 0)
        payload = {
            'left': left,
            'right': right,
            'total': self.player.points,
            'state': self.state,
            'winner': self.winner_side,
            'difficulty': self.selected_difficulty,
            'song': self.SONG_BY_DIFFICULTY.get(self.selected_difficulty),
            'updated_at': time.time(),
        }
        tmp_file = self.scoreboard_file + ".tmp"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp_file, self.scoreboard_file)
        except Exception as e:
            print(f"Score publish failed: {e}", flush=True)

    def set_led(self, buffer, x, y, color):
        if x < 0 or x >= BOARD_WIDTH:
            return
        if y < 0 or y >= BOARD_HEIGHT:
            return

        channel = y // 4
        if channel >= NUM_CHANNELS:
            return

        row_in_channel = y % 4
        if row_in_channel % 2 == 0:
            led_index = row_in_channel * 16 + x
        else:
            led_index = row_in_channel * 16 + (15 - x)

        block_size = NUM_CHANNELS * 3
        offset = led_index * block_size + channel
        if offset + NUM_CHANNELS * 2 < len(buffer):
            buffer[offset] = color[1]
            buffer[offset + NUM_CHANNELS] = color[0]
            buffer[offset + NUM_CHANNELS * 2] = color[2]

    def reset_board(self):
        self.board = [[BLACK for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]
        self.player_button_map = {}

    def _build_player_button_map(self, row_groups_left, row_groups_right, left_edge, right_edge):
        player_map = {}

        for group_index, rows in enumerate(row_groups_left):
            buttons = []
            for y in rows:
                if 0 <= y < BOARD_HEIGHT:
                    buttons.append(self.player.get_led_index(left_edge, y))
            player_map[group_index] = buttons

        base_index = len(row_groups_left)
        for local_index, rows in enumerate(row_groups_right):
            buttons = []
            for y in rows:
                if 0 <= y < BOARD_HEIGHT:
                    buttons.append(self.player.get_led_index(right_edge, y))
            player_map[base_index + local_index] = buttons

        self.player_button_map = player_map

    def _render_countdown(self, frame_buffer):
        """3-2-1 countdown: renders large pixel-art digits centred on the board."""
        if self.countdown_start_time is None:
            self.countdown_start_time = time.time()

        # 3-wide x 5-tall bitmaps for each digit
        GLYPHS = {
            3: [
                [1,1,1],
                [0,0,1],
                [1,1,1],
                [0,0,1],
                [1,1,1],
            ],
            2: [
                [1,1,1],
                [0,0,1],
                [1,1,1],
                [1,0,0],
                [1,1,1],
            ],
            1: [
                [0,1,0],
                [1,1,0],
                [0,1,0],
                [0,1,0],
                [1,1,1],
            ],
        }
        SCALE = 4  # each glyph pixel -> 4x4 LEDs => 12 wide x 20 tall on board

        elapsed    = time.time() - self.countdown_start_time
        digit      = max(1, 3 - int(elapsed / self.COUNTDOWN_STEP))
        frac       = (elapsed % self.COUNTDOWN_STEP) / self.COUNTDOWN_STEP
        colors     = {3: (0, 220, 60), 2: (220, 200, 0), 1: (220, 30, 0)}
        base_color = colors[digit]
        # Brief flash at the start of each digit transition
        brightness = 1.5 if frac < 0.08 else 1.0
        draw_color = tuple(min(255, int(c * brightness)) for c in base_color)
        dim        = tuple(int(c * 0.10) for c in base_color)

        glyph  = GLYPHS[digit]
        gh     = len(glyph) * SCALE       # 20
        gw     = len(glyph[0]) * SCALE    # 12
        off_y  = (BOARD_HEIGHT - gh) // 2
        off_x  = (BOARD_WIDTH  - gw) // 2

        # Background
        for y in range(BOARD_HEIGHT):
            for x in range(BOARD_WIDTH):
                self.set_led(frame_buffer, x, y, dim)

        # Draw glyph
        for gy, row in enumerate(glyph):
            for gx, bit in enumerate(row):
                if bit:
                    for dy in range(SCALE):
                        for dx in range(SCALE):
                            px = off_x + gx * SCALE + dx
                            py = off_y + gy * SCALE + dy
                            if 0 <= px < BOARD_WIDTH and 0 <= py < BOARD_HEIGHT:
                                self.set_led(frame_buffer, px, py, draw_color)

    def _play_countdown_sound(self):
        if not os.path.exists(self.countdown_sound_path):
            print(f"Countdown sound missing: {self.countdown_sound_path}", flush=True)
            return

        try:
            if PYGAME_AVAILABLE and pygame.mixer.get_init():
                sound = pygame.mixer.Sound(self.countdown_sound_path)
                channel = pygame.mixer.find_channel(True)
                if channel is not None:
                    channel.play(sound)
                    return
                sound.play()
                return
        except Exception as e:
            print(f"Countdown sound pygame failed: {e}", flush=True)

        try:
            if WINSOUND_AVAILABLE:
                winsound.PlaySound(self.countdown_sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                return
        except Exception as e:
            print(f"Countdown sound winsound failed: {e}", flush=True)

        try:
            if os.name == 'nt':
                os.startfile(self.countdown_sound_path)
        except Exception as e:
            print(f"Countdown sound fallback failed: {e}", flush=True)

    def _resolve_applause_path(self):
        if os.path.exists(self.applause_sound_path):
            return self.applause_sound_path
        if os.path.exists(self.applause_fallback_sound_path):
            return self.applause_fallback_sound_path
        return None

    def _play_round_end_sounds(self):
        airhorn_path = self.airhorn_sound_path if os.path.exists(self.airhorn_sound_path) else None
        applause_path = self._resolve_applause_path()

        if not airhorn_path:
            print(f"Airhorn sound missing: {self.airhorn_sound_path}", flush=True)
        if not applause_path:
            print(
                f"Applause sound missing: {self.applause_sound_path} (or {self.applause_fallback_sound_path})",
                flush=True,
            )
        if not airhorn_path and not applause_path:
            return

        try:
            if PYGAME_AVAILABLE and pygame.mixer.get_init():
                if airhorn_path:
                    ch = pygame.mixer.find_channel(True)
                    if ch is not None:
                        ch.play(pygame.mixer.Sound(airhorn_path))
                    else:
                        pygame.mixer.Sound(airhorn_path).play()
                if applause_path:
                    ch = pygame.mixer.find_channel(True)
                    if ch is not None:
                        ch.play(pygame.mixer.Sound(applause_path))
                    else:
                        pygame.mixer.Sound(applause_path).play()
                return
        except Exception as e:
            print(f"Round-end sound pygame failed: {e}", flush=True)

        # Non-pygame fallback: launch both files so they can overlap.
        try:
            if os.name == 'nt':
                if airhorn_path:
                    os.startfile(airhorn_path)
                if applause_path:
                    os.startfile(applause_path)
                return
        except Exception as e:
            print(f"Round-end sound fallback failed: {e}", flush=True)

        # Last fallback if startfile path is unavailable.
        try:
            if WINSOUND_AVAILABLE:
                if airhorn_path:
                    winsound.PlaySound(airhorn_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                if applause_path:
                    winsound.PlaySound(applause_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception as e:
            print(f"Round-end sound winsound failed: {e}", flush=True)

    def _render_side_select(self, frame_buffer):
        """Show left half purple, right half cyan with a 5s countdown bar."""
        elapsed    = time.time() - self.side_select_start_time
        remaining  = max(0.0, self.SIDE_SELECT_DURATION - elapsed)
        frac       = remaining / self.SIDE_SELECT_DURATION
        pulse      = 0.55 + 0.45 * math.sin(self.time_counter * 0.18)

        LEFT_COLOR  = (int(180 * pulse), 0, int(255 * pulse))   # purple
        RIGHT_COLOR = (0, int(200 * pulse), int(220 * pulse))   # cyan
        MID         = BOARD_WIDTH // 2  # col 8 is the split

        for y in range(BOARD_HEIGHT):
            for x in range(BOARD_WIDTH):
                color = LEFT_COLOR if x < MID else RIGHT_COLOR
                self.set_led(frame_buffer, x, y, color)

        # White divider at centre
        for y in range(BOARD_HEIGHT):
            self.set_led(frame_buffer, MID - 1, y, WHITE)
            self.set_led(frame_buffer, MID,     y, WHITE)

        # Countdown bar at top row
        for x in range(BOARD_WIDTH):
            color = WHITE if x < int(frac * BOARD_WIDTH) else BLACK
            self.set_led(frame_buffer, x, 0, color)

    def _button_index_to_xy(self, button_idx):
        """Convert matrix touch index (0..511) back to board coordinates."""
        channel = button_idx // 64
        led_index = button_idx % 64
        row_in_channel = led_index // 16
        pos_in_row = led_index % 16
        x = pos_in_row if (row_in_channel % 2 == 0) else (15 - pos_in_row)
        y = channel * 4 + row_in_channel
        return x, y

    def _count_side_select_presses(self):
        """Count currently held touches on left and right half of the board."""
        left = 0
        right = 0
        mid = BOARD_WIDTH // 2
        for idx, pressed in enumerate(self.button_states):
            if not pressed:
                continue
            x, y = self._button_index_to_xy(idx)
            if not (0 <= y < BOARD_HEIGHT):
                continue
            if x < mid:
                left += 1
            else:
                right += 1
        return left, right

    def _is_prelobby_start_pressed(self):
        """Return True if any pressed touch is inside the central START area."""
        x0, y0, x1, y1 = self.PRELOBBY_START_RECT
        for idx, pressed in enumerate(self.button_states):
            if not pressed:
                continue
            x, y = self._button_index_to_xy(idx)
            if x0 <= x <= x1 and y0 <= y <= y1:
                return True
        return False

    def _render_prelobby(self, frame_buffer):
        """Render PRELOBBY with central START gate and blue ground fade animation."""
        # Dark sky background.
        for y in range(BOARD_HEIGHT):
            for x in range(BOARD_WIDTH):
                self.set_led(frame_buffer, x, y, (2, 6, 20))

        # Blue fade animation on the ground.
        ground_pulse = 0.25 + 0.75 * (0.5 + 0.5 * math.sin(self.time_counter * 0.14))
        ground_color = (
            int(8 * ground_pulse),
            int(34 * ground_pulse),
            int(165 * ground_pulse),
        )
        for y in range(BOARD_HEIGHT - 6, BOARD_HEIGHT):
            for x in range(BOARD_WIDTH):
                self.set_led(frame_buffer, x, y, ground_color)

        # START word (3x5 letters, no spacing => width 15, centered).
        glyphs = {
            'S': [
                [1, 1, 1],
                [1, 0, 0],
                [1, 1, 1],
                [0, 0, 1],
                [1, 1, 1],
            ],
            'T': [
                [1, 1, 1],
                [0, 1, 0],
                [0, 1, 0],
                [0, 1, 0],
                [0, 1, 0],
            ],
            'A': [
                [1, 1, 1],
                [1, 0, 1],
                [1, 1, 1],
                [1, 0, 1],
                [1, 0, 1],
            ],
            'R': [
                [1, 1, 1],
                [1, 0, 1],
                [1, 1, 1],
                [1, 1, 0],
                [1, 0, 1],
            ],
        }
        start_text = "START"
        text_width = len(start_text) * 3
        start_x = max(0, (BOARD_WIDTH - text_width) // 2)
        start_y = 8
        for i, ch in enumerate(start_text):
            glyph = glyphs[ch]
            gx0 = start_x + i * 3
            for gy, row in enumerate(glyph):
                for gx, bit in enumerate(row):
                    if bit:
                        self.set_led(frame_buffer, gx0 + gx, start_y + gy, WHITE)

        # Central START touch area (button-like panel).
        x0, y0, x1, y1 = self.PRELOBBY_START_RECT
        button_pulse = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(self.time_counter * 0.20))
        fill = (0, int(100 * button_pulse), int(220 * button_pulse))
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                border = (x == x0 or x == x1 or y == y0 or y == y1)
                self.set_led(frame_buffer, x, y, WHITE if border else fill)








    # ------------------------------------------------------------------ lobby
    def _lobby_zone(self, button_idx):
        """Return the difficulty zone name for a button index, or None."""
        channel      = button_idx // 64
        row_in_chan  = (button_idx % 64) // 16
        y = channel * 4 + row_in_chan
        for name, lo, hi, _ in self.LOBBY_ZONES:
            if lo <= y <= hi:
                return name
        return None

    def _load_midi_by_difficulty(self, difficulty):
        """Load the MIDI file matching the chosen difficulty."""
        self.selected_difficulty = difficulty
        game_dir  = os.path.dirname(os.path.abspath(__file__))
        midi_path = os.path.join(game_dir, f"{difficulty}.mid")
        if not os.path.exists(midi_path):
            # Fallback: first .mid found
            mid_files = sorted(f for f in os.listdir(game_dir) if f.lower().endswith('.mid'))
            if not mid_files:
                print("No MIDI file found!", flush=True)
                return
            midi_path = os.path.join(game_dir, mid_files[0])
        try:
            self.midi_player = MidiSongPlayer(midi_path, self.piano, difficulty=difficulty)
            self._publish_scores()
            print(f"Lobby: loaded {os.path.basename(midi_path)} ({difficulty})", flush=True)
        except Exception as e:
            print(f"Failed to load MIDI: {e}", flush=True)

    def _render_lobby(self, frame_buffer):
        """Draw the 3 difficulty zones with live press indicators."""
        pulse = 0.55 + 0.45 * math.sin(self.time_counter * 0.18)
        elapsed        = time.time() - self.lobby_start_time
        remaining      = max(0.0, self.LOBBY_DURATION - elapsed)
        countdown_frac = remaining / self.LOBBY_DURATION

        # Count currently held buttons per zone (live)
        live_counts = {'easy': 0, 'medium': 0, 'hard': 0}
        for btn_idx, state in enumerate(self.button_states):
            if state:
                zone = self._lobby_zone(btn_idx)
                if zone:
                    live_counts[zone] += 1

        for name, lo, hi, base_color in self.LOBBY_ZONES:
            votes = live_counts[name]
            for y in range(lo, hi + 1):
                for x in range(BOARD_WIDTH):
                    br = 0.20 + 0.25 * pulse
                    if x < votes:
                        br = 0.85
                    color = (int(base_color[0] * br),
                             int(base_color[1] * br),
                             int(base_color[2] * br))
                    self.set_led(frame_buffer, x, y, color)

        # Countdown bar at top row
        for x in range(BOARD_WIDTH):
            if x < int(countdown_frac * BOARD_WIDTH):
                self.set_led(frame_buffer, x, 0, WHITE)
            else:
                self.set_led(frame_buffer, x, 0, BLACK)

    def _render_gameover(self, frame_buffer):
        """Fill the whole field with the winner color and tint the ground rows."""
        team_colors = {
            'left': (180, 0, 255),
            'right': (0, 200, 220),
        }
        base_color = team_colors.get(self.winner_side, (100, 100, 100))
        pulse = 0.75 + 0.25 * math.sin(self.time_counter * 0.10)

        sky_color = tuple(int(channel * (0.55 * pulse)) for channel in base_color)
        ground_color = tuple(min(255, int(channel * (1.00 * pulse))) for channel in base_color)
        text_color = WHITE if sum(base_color) < 420 else BLACK

        for y in range(BOARD_HEIGHT):
            color = ground_color if y >= BOARD_HEIGHT - 6 else sky_color
            for x in range(BOARD_WIDTH):
                self.set_led(frame_buffer, x, y, color)

        glyphs = {
            'W': [
                [1, 0, 0, 0, 1],
                [1, 0, 0, 0, 1],
                [1, 0, 1, 0, 1],
                [1, 1, 0, 1, 1],
                [1, 0, 0, 0, 1],
            ],
            'I': [
                [1, 1, 1],
                [0, 1, 0],
                [0, 1, 0],
                [0, 1, 0],
                [1, 1, 1],
            ],
            'N': [
                [1, 0, 0, 1],
                [1, 1, 0, 1],
                [1, 0, 1, 1],
                [1, 0, 0, 1],
                [1, 0, 0, 1],
            ],
        }

        word = 'WIN'
        spacing = 1
        glyph_height = 5
        total_width = sum(len(glyphs[ch][0]) for ch in word) + spacing * (len(word) - 1)
        start_x = max(0, (BOARD_WIDTH - total_width) // 2)
        start_y = max(1, (BOARD_HEIGHT - 6 - glyph_height) // 2)
        cursor_x = start_x

        for ch in word:
            glyph = glyphs[ch]
            for gy, row in enumerate(glyph):
                for gx, bit in enumerate(row):
                    if bit:
                        self.set_led(frame_buffer, cursor_x + gx, start_y + gy, text_color)
            cursor_x += len(glyph[0]) + spacing

    def start_game(self):
        with self.lock:
            self.reset_board()
            self.player.points = 0
            self.player.side_scores = {'left': 0, 'right': 0}
            self.winner_side = None
            self.state = 'COUNTDOWN'
            self._publish_scores()
            self.countdown_start_time = time.time()
            self._play_countdown_sound()
            print("3... 2... 1...", flush=True)

    def render(self):
        # Create a blank frame buffer
        frame_buffer = bytearray(FRAME_DATA_LENGTH)

        if not hasattr(self, 'time_counter'):
            self.time_counter = 0

        if self.state == 'PRELOBBY':
            self._render_prelobby(frame_buffer)
            self.time_counter += 1
            self.prev_button_states = self.button_states.copy()
            return frame_buffer

        if self.state == 'LOBBY':
            self._render_lobby(frame_buffer)
            self.time_counter += 1
            self.prev_button_states = self.button_states.copy()
            return frame_buffer

        if self.state == 'SIDE_SELECT':
            self._render_side_select(frame_buffer)
            self.time_counter += 1
            self.prev_button_states = self.button_states.copy()
            return frame_buffer

        if self.state == 'COUNTDOWN':
            self._render_countdown(frame_buffer)
            self.time_counter += 1
            self.prev_button_states = self.button_states.copy()
            return frame_buffer

        if self.state == 'GAMEOVER':
            self._render_gameover(frame_buffer)
            self.time_counter += 1
            self.prev_button_states = self.button_states.copy()
            return frame_buffer

        # Fill background with dim dark blue.
        for y in range(BOARD_HEIGHT):
            for x in range(BOARD_WIDTH):
                self.set_led(frame_buffer, x, y, DIM_DARK_BLUE)
                self.board[y][x] = DIM_DARK_BLUE

        # ===========================================
        # MIDI FLYING NOTES
        # ===========================================
        if self.midi_player:
            for note in self.midi_player.get_flying_notes():
                x, y = note['x'], note['row']
                if 0 <= x < BOARD_WIDTH and 0 <= y < BOARD_HEIGHT:
                    hold_seconds = note.get('hold_seconds', 0.0)
                    # Hold notes are drawn as horizontal bars (tail length by hold duration).
                    max_hold_cells = 1 + min(6, int(max(0.0, hold_seconds) * 4.0))

                    # Keep constant length while travelling; once at piano roll,
                    # retract one block per movement step from the tail.
                    if note.get('phase') == 'linger':
                        linger_start = note.get('linger_start_counter', self.midi_player._update_counter)
                        steps_elapsed = max(
                            0,
                            (self.midi_player._update_counter - linger_start) // self.midi_player.MOVE_STEP_FRAMES,
                        )
                        hold_cells = max(0, max_hold_cells - steps_elapsed)
                    else:
                        hold_cells = max_hold_cells

                    if hold_cells <= 0:
                        continue

                    moving_right = note.get('dx', 1) > 0
                    for i in range(hold_cells):
                        px = x - i if moving_right else x + i
                        if 0 <= px < BOARD_WIDTH:
                            self.set_led(frame_buffer, px, y, note['color'])

        # ===========================================
        # MATRIX BORDER AND CENTER COLUMN
        # ===========================================
        # Draw white border around perimeter and vertical center column

        # Left/right borders (2 columns wide each side) are steady piano keys.
        sharp_note_positions = {1, 3, 6, 8, 10}
        for y in range(BOARD_HEIGHT):
            note_idx = (BOARD_HEIGHT - 1) - y
            note_pos = note_idx % 12
            base_key_color = (70, 70, 70) if note_pos in sharp_note_positions else WHITE
            key_color = base_key_color
            left_border_color = key_color if self.active_piano_sides.get('left', True) else DIM_DARK_BLUE
            right_border_color = key_color if self.active_piano_sides.get('right', True) else DIM_DARK_BLUE

            # Left border (columns 0 and 1)
            self.set_led(frame_buffer, 0, y, left_border_color)
            self.board[y][0] = left_border_color
            self.set_led(frame_buffer, 1, y, left_border_color)
            self.board[y][1] = left_border_color

            # Right border (last two columns)
            self.set_led(frame_buffer, BOARD_WIDTH - 2, y, right_border_color)
            self.board[y][BOARD_WIDTH - 2] = right_border_color
            self.set_led(frame_buffer, BOARD_WIDTH - 1, y, right_border_color)
            self.board[y][BOARD_WIDTH - 1] = right_border_color

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

        # Advance MIDI song animation (runs at render rate ~20fps, correct speed)
        if self.midi_player and self.state == 'PLAYING':
            self.midi_player.update()

        # Show upcoming hit tiles with logarithmic fade-in based on time-to-hit.
        if self.midi_player and self.state == 'PLAYING':
            guides = self.midi_player.get_next_hit_guides(limit=None, preview_window_seconds=10.0)
            for g in guides:
                side = g['side']
                note_idx = g['note_idx']
                if side == 'left' and not self.active_piano_sides.get('left', True):
                    continue
                if side == 'right' and not self.active_piano_sides.get('right', True):
                    continue

                x = 2 if side == 'left' else (BOARD_WIDTH - 3)
                y = (BOARD_HEIGHT - 1) - note_idx
                if 0 <= y < BOARD_HEIGHT:
                    visibility = g.get('visibility', 0.0)
                    if visibility <= 0.0:
                        continue

                    bg = DIM_DARK_BLUE
                    guide_color = (
                        int(bg[0] + (YELLOW[0] - bg[0]) * visibility),
                        int(bg[1] + (YELLOW[1] - bg[1]) * visibility),
                        int(bg[2] + (YELLOW[2] - bg[2]) * visibility),
                    )
                    self.set_led(frame_buffer, x, y, guide_color)
                    self.board[y][x] = guide_color

        # Step 3: Update animation timing
        self.time_counter += 1
        self.prev_button_states = self.button_states.copy()

        # Return the completed frame buffer
        return frame_buffer


    def tick(self):
        with self.lock:
            if self.state == 'PRELOBBY':
                if self._is_prelobby_start_pressed():
                    self.state = 'LOBBY'
                    self.lobby_start_time = time.time()
                    self._publish_scores()
                    print("PRELOBBY -> LOBBY (START pressed)", flush=True)
                return

            if self.state == 'LOBBY':
                # Check if timer has expired — snapshot current button state
                elapsed = time.time() - self.lobby_start_time
                if elapsed >= self.LOBBY_DURATION:
                    votes = {'easy': 0, 'medium': 0, 'hard': 0}
                    for btn_idx, state in enumerate(self.button_states):
                        if state:
                            zone = self._lobby_zone(btn_idx)
                            if zone:
                                votes[zone] += 1
                    # Pick difficulty with most votes; tie-break: easy > medium > hard
                    winner = max(votes, key=lambda k: (votes[k], -['easy','medium','hard'].index(k)))
                    print(f"Lobby result: {votes} → {winner}", flush=True)
                    self._load_midi_by_difficulty(winner)
                    self.state = 'SIDE_SELECT'
                    self.side_select_start_time = time.time()
                    print("Choose your side! (4 seconds)", flush=True)
                return

            if self.state == 'SIDE_SELECT':
                elapsed = time.time() - self.side_select_start_time
                if elapsed >= self.SIDE_SELECT_DURATION:
                    left_count, right_count = self._count_side_select_presses()
                    if left_count > 0 and right_count == 0:
                        self.active_piano_sides = {'left': True, 'right': False}
                    elif right_count > 0 and left_count == 0:
                        self.active_piano_sides = {'left': False, 'right': True}
                    else:
                        self.active_piano_sides = {'left': True, 'right': True}

                    self.piano.configure_active_sides(
                        enable_left=self.active_piano_sides['left'],
                        enable_right=self.active_piano_sides['right'],
                    )
                    if self.midi_player:
                        self.midi_player.configure_active_sides(
                            enable_left=self.active_piano_sides['left'],
                            enable_right=self.active_piano_sides['right'],
                        )

                    print(
                        f"Side select: left={left_count}, right={right_count} -> active {self.active_piano_sides}",
                        flush=True,
                    )
                    self.start_game()
                return

            if self.state == 'COUNTDOWN':
                if self.countdown_start_time is None:
                    self.countdown_start_time = time.time()
                elapsed = time.time() - self.countdown_start_time
                if elapsed >= self.COUNTDOWN_DURATION:
                    print("FIGHT! Game Starting...", flush=True)
                    self.state = 'PLAYING'
                    self.game_start_time = time.time()
                    if self.midi_player:
                        self.midi_player.start()
                return

            if self.state == 'PLAYING':
                # Handle piano note generation from button presses
                try:
                    self.piano.handle_button_press(self.button_states, self.player_button_map)
                except Exception as e:
                    print(f"Tick error in piano.handle_button_press: {e}")
                    import traceback
                    traceback.print_exc()

                # Score points when a player presses a lit (linger) note on their side
                if self.midi_player:
                    prev = self.prev_button_states
                    curr = self.button_states
                    for btn_idx, note_idx in self.piano._button_to_note_index.items():
                        if btn_idx < len(curr) and curr[btn_idx] and not (btn_idx < len(prev) and prev[btn_idx]):
                            side = self.piano._button_side_map.get(btn_idx)
                            if side and self.midi_player.check_piano_hit(side, note_idx):
                                self.player.side_scores[side] = self.player.side_scores.get(side, 0) + 1
                                self.player.points += 1
                                left  = self.player.side_scores.get('left', 0)
                                right = self.player.side_scores.get('right', 0)
                                self._publish_scores()
                                print(f"SCORE! {side.upper()} side hit note {note_idx} | Left: {left}  Right: {right}  Total: {self.player.points}")

                    # Check if song finished
                    if self.midi_player and self.midi_player.finished:
                        left_score = self.player.side_scores.get('left', 0)
                        right_score = self.player.side_scores.get('right', 0)
                        self.winner_side = 'left' if left_score > right_score else 'right'
                        self.state = 'GAMEOVER'
                        self.game_over_start_time = time.time()
                        self._publish_scores()
                        self._play_round_end_sounds()
                        print(f"GAME OVER! Winner: {self.winner_side.upper()} side ({left_score} vs {right_score})", flush=True)
                    return

            if self.state == 'GAMEOVER':
                if self.game_over_start_time is None:
                    self.game_over_start_time = time.time()
                elif time.time() - self.game_over_start_time >= self.GAMEOVER_DURATION:
                    print("Closing program after winner screen.", flush=True)
                    self.running = False
                    close_score_window()
                    os._exit(0)
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

                    with self.game.lock:
                        self.game.button_states = new_states
                        self.prev_button_states = self.game.button_states.copy()

            except Exception as e:
                print(f"Receive error: {e}")

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


def launch_score_window():
    """Launch separate team score window process."""
    global SCORE_WINDOW_PROCESS

    if SCORE_WINDOW_PROCESS is not None and SCORE_WINDOW_PROCESS.poll() is None:
        return

    game_dir = os.path.dirname(os.path.abspath(__file__))
    score_window_path = os.path.join(game_dir, "score_window.py")
    if not os.path.exists(score_window_path):
        print(f"Score window script missing: {score_window_path}", flush=True)
        return

    try:
        kwargs = {
            "cwd": game_dir,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True

        SCORE_WINDOW_PROCESS = subprocess.Popen([sys.executable, score_window_path], **kwargs)
        print("Score window launched.", flush=True)
    except Exception as e:
        print(f"Failed to launch score window: {e}", flush=True)


def close_score_window():
    """Close score window process if it is running."""
    global SCORE_WINDOW_PROCESS

    proc = SCORE_WINDOW_PROCESS
    SCORE_WINDOW_PROCESS = None
    if proc is None:
        return

    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1.5)
            except Exception:
                proc.kill()
    except Exception as e:
        print(f"Failed to close score window: {e}", flush=True)

if __name__ == "__main__":
    launch_score_window()
    game = PianoGame()
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
    finally:
        net.running = False
        close_score_window()
        print("Exiting...")