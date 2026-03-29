import socket
import threading
import random
import time
import math
import os
import ctypes
import pygame
from collections import deque
import tkinter as tk
from tkinter import ttk

# --- Protocol/Simulator Settings ---
NUM_CHANNELS = 4
LEDS_PER_CHANNEL = 11
SIMULATOR_IP = '127.0.0.1'
SEND_PORT = 7277  # To simulator (light commands)
RECV_PORT = 7278  # From simulator (button events)
USE_REAL_ROOM = 1  # 0 = force simulator, 1 = allow real room discovery
DEBUG_INPUT = 1  # 1 = print input/trigger debug logs
FRAME_DATA_LEN = LEDS_PER_CHANNEL * NUM_CHANNELS * 3
TRIGGER_PACKET_LEN = 687

# Real hardware can have different channel/LED wiring than simulator.
# These defaults reflect current in-room measurements.
REAL_ROOM_COLOR_ORDER = "RGB"
REAL_ROOM_SWAP_RB = 1      # Real room shows red as blue without this correction.
REAL_ROOM_LED_SHIFT = 1    # Real room LEDs appear one index left; shift output +1.
OUTPUT_COLOR_ORDER = "RGB"
OUTPUT_SWAP_RB = False
OUTPUT_LED_SHIFT = 0

# Real hardware ports (used when a device is discovered on the LAN)
DEVICE_SEND_PORT = 4626    # Send light commands to device
DEVICE_RECV_PORT = 7800    # Receive button events from device
DISCOVERY_TIMEOUT_SEC = 3  # How long to wait for a hardware response

# Playable buttons based on your wall layout.
WALL_PATH = list(range(1, 11))

# Timings (milliseconds)
SHOW_ON_MS = 700
SHOW_OFF_MS = 250
INPUT_GREEN_MS = 2300
INPUT_RED_MS = 1400
INPUT_TIMEOUT_MS = 20000
LED_REFRESH_MS = 80
EYE_PENALTY_SECONDS = 2.5
RED_PENALTY_RESTART_MS = 2000
STATE_PLAYING = "playing"
STATE_IDLE = "idle"
IDLE_MAX_BRIGHTNESS = 0.20
IDLE_FADE_MS = 1000
EYE_LED_INDEX = 0
EYE_SCAN_MIN_MS = 2000
EYE_SCAN_MAX_MS = 4000
EYE_SCAN_GAP_MIN_MS = 10000
EYE_SCAN_GAP_MAX_MS = 15000
EYE_SCAN_GRACE_MS = 500
PRE_SCAN_WARN_MS = 1000
PRE_SCAN_BLINK_INTERVAL_MS = 180
PRE_SCAN_RED_LEVEL = 128
ROOM_BLINK_DURATION_MS = 2000
ROOM_BLINK_INTERVAL_MS = 250
ANIM_STEP_MS = 320
GREEN_HIDE_BEFORE_WARNING_MS = 400
SPIN_COOLDOWN_MIN_SEC = 1
SPIN_COOLDOWN_MAX_SEC = 2
HOLD_TARGET_COLOR = (0, 0, 255)
HOLD_SOURCE_LED = 10
HOLD_ADJACENT_LED = 1
ANIM_COLORS = (
	(0, 255, 0),
	(0, 255, 255),
	(255, 255, 0),
	(255, 0, 255),
)

# Combo scoring: checked highest-to-lowest, first match wins.
SCORE_JACKPOT    = 50   # all 5 positions same color
SCORE_4_IN_A_ROW = 10   # any 4 consecutive positions same color
SCORE_3_IN_A_ROW = 3    # any 3 consecutive or {1,3,5} positions same color
_COMBOS_4 = [(0, 1, 2, 3), (1, 2, 3, 4), (0, 1, 3, 4)]
_COMBOS_3 = [(0, 1, 2), (1, 2, 3), (2, 3, 4), (0, 2, 4)]

# Playing flow summary:
# 1) When entering PLAYING, buttons 3/8 are green for a random 5-8s window.
# 2) Pressing 3 or 8 starts lane animations (1-5 or 6-10) with random colors.
# 3) After a random delay, the eye system runs: warning blink -> eye open -> 0.5s grace.
# 4) If IR eye input (LED 0) triggers during active scan, room blinks red for 2s.
# 5) When scan ends, green trigger window is reset and the cycle continues.

PASSWORD_ARRAY = [
	35, 63, 187, 69, 107, 178, 92, 76, 39, 69, 205, 37, 223, 255, 165, 231,
	16, 220, 99, 61, 25, 203, 203, 155, 107, 30, 92, 144, 218, 194, 226, 88,
	196, 190, 67, 195, 159, 185, 209, 24, 163, 65, 25, 172, 126, 63, 224, 61,
	160, 80, 125, 91, 239, 144, 25, 141, 183, 204, 171, 188, 255, 162, 104, 225,
	186, 91, 232, 3, 100, 208, 49, 211, 37, 192, 20, 99, 27, 92, 147, 152,
	86, 177, 53, 153, 94, 177, 200, 33, 175, 195, 15, 228, 247, 18, 244, 150,
	165, 229, 212, 96, 84, 200, 168, 191, 38, 112, 171, 116, 121, 186, 147, 203,
	30, 118, 115, 159, 238, 139, 60, 57, 235, 213, 159, 198, 160, 50, 97, 201,
	253, 242, 240, 77, 102, 12, 183, 235, 243, 247, 75, 90, 13, 236, 56, 133,
	150, 128, 138, 190, 140, 13, 213, 18, 7, 117, 255, 45, 69, 214, 179, 50,
	28, 66, 123, 239, 190, 73, 142, 218, 253, 5, 212, 174, 152, 75, 226, 226,
	172, 78, 35, 93, 250, 238, 19, 32, 247, 223, 89, 123, 86, 138, 150, 146,
	214, 192, 93, 152, 156, 211, 67, 51, 195, 165, 66, 10, 10, 31, 1, 198,
	234, 135, 34, 128, 208, 200, 213, 169, 238, 74, 221, 208, 104, 170, 166, 36,
	76, 177, 196, 3, 141, 167, 127, 56, 177, 203, 45, 107, 46, 82, 217, 139,
	168, 45, 198, 6, 43, 11, 57, 88, 182, 84, 189, 29, 35, 143, 138, 171,
]


def calc_checksum_send(data):
	idx = sum(data) & 0xFF
	return PASSWORD_ARRAY[idx] if idx < len(PASSWORD_ARRAY) else 0


def build_command_packet(data_id, msg_loc, payload, seq):
	rand1 = random.randint(0, 127)
	rand2 = random.randint(0, 127)

	internal = bytes([
		0x02,
		0x00,
		0x00,
		(data_id >> 8) & 0xFF,
		data_id & 0xFF,
		(msg_loc >> 8) & 0xFF,
		msg_loc & 0xFF,
		(len(payload) >> 8) & 0xFF,
		len(payload) & 0xFF,
	]) + payload

	hdr = bytes([
		0x75,
		rand1,
		rand2,
		(len(internal) >> 8) & 0xFF,
		len(internal) & 0xFF,
	])

	pkt = bytearray(hdr + internal)
	pkt[10] = (seq >> 8) & 0xFF
	pkt[11] = seq & 0xFF
	pkt.append(calc_checksum_send(pkt))
	return bytes(pkt)


def build_start_packet(seq):
	pkt = bytearray([
		0x75,
		random.randint(0, 127), random.randint(0, 127),
		0x00, 0x08,
		0x02, 0x00, 0x00,
		0x33, 0x44,
		(seq >> 8) & 0xFF, seq & 0xFF,
		0x00, 0x00,
	])
	pkt.append(calc_checksum_send(pkt))
	return bytes(pkt)


def build_end_packet(seq):
	pkt = bytearray([
		0x75,
		random.randint(0, 127), random.randint(0, 127),
		0x00, 0x08,
		0x02, 0x00, 0x00,
		0x55, 0x66,
		(seq >> 8) & 0xFF, seq & 0xFF,
		0x00, 0x00,
	])
	pkt.append(calc_checksum_send(pkt))
	return bytes(pkt)


def build_fff0_packet(seq):
	payload = bytearray()
	for _ in range(NUM_CHANNELS):
		payload += bytes([(LEDS_PER_CHANNEL >> 8) & 0xFF, LEDS_PER_CHANNEL & 0xFF])
	return build_command_packet(0x8877, 0xFFF0, bytes(payload), seq)


def map_output_color(r, g, b):
	if OUTPUT_COLOR_ORDER == "GRB":
		return g, r, b
	if OUTPUT_COLOR_ORDER == "RBG":
		return r, b, g
	if OUTPUT_COLOR_ORDER == "BRG":
		return b, r, g
	if OUTPUT_COLOR_ORDER == "BGR":
		return b, g, r
	if OUTPUT_COLOR_ORDER == "GBR":
		return g, b, r
	out_r, out_g, out_b = r, g, b
	if OUTPUT_SWAP_RB:
		out_r, out_b = out_b, out_r
	return out_r, out_g, out_b


def map_output_led_index(led):
	out_led = led
	if OUTPUT_LED_SHIFT:
		out_led = (led + OUTPUT_LED_SHIFT) % LEDS_PER_CHANNEL
	return out_led


def build_frame_data(led_states):
	frame = bytearray(FRAME_DATA_LEN)
	for (ch, led), (r, g, b) in led_states.items():
		r, g, b = map_output_color(r, g, b)
		led = map_output_led_index(led)
		ch_idx = ch - 1
		if 0 <= ch_idx < NUM_CHANNELS and 0 <= led < LEDS_PER_CHANNEL:
			frame[led * 12 + ch_idx] = g
			frame[led * 12 + 4 + ch_idx] = r
			frame[led * 12 + 8 + ch_idx] = b
	return bytes(frame)

# --- Hardware Discovery ---
def build_discovery_packet():
	"""Build the 0x67 broadcast discovery packet."""
	rand1 = random.randint(0, 127)
	rand2 = random.randint(0, 127)
	payload = bytes([
		0x0A, 0x02, 0x4B, 0x58, 0x2D, 0x48, 0x43, 0x30, 0x34, 0x03,
		0x00, 0x00, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x14,
	])
	pkt = bytearray([0x67, rand1, rand2, len(payload)] + list(payload))
	idx = sum(pkt) & 0xFF
	pkt.append(PASSWORD_ARRAY[idx] if idx < len(PASSWORD_ARRAY) else 0)
	return bytes(pkt), rand1, rand2


def run_discovery():
	"""
	Broadcasts a discovery packet on the LAN.
	Returns (device_ip, send_port, recv_port).
	Falls back to the simulator (127.0.0.1) if no real hardware responds.
	"""
	if USE_REAL_ROOM == 0:
		print("[Discovery] Real room disabled. Using simulator.")
		return SIMULATOR_IP, SEND_PORT, RECV_PORT

	pkt, rand1, rand2 = build_discovery_packet()
	sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, True)
	sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
	sock.settimeout(0.5)

	try:
		sock.bind(('', DEVICE_RECV_PORT))
	except OSError:
		sock.close()
		print("[Discovery] Could not bind recv port — using simulator fallback.")
		return SIMULATOR_IP, SEND_PORT, RECV_PORT

	try:
		sock.sendto(pkt, ('255.255.255.255', DEVICE_SEND_PORT))
		print(f"[Discovery] Sent broadcast to 255.255.255.255:{DEVICE_SEND_PORT}")
	except OSError as e:
		sock.close()
		print(f"[Discovery] Broadcast failed: {e} — using simulator fallback.")
		return SIMULATOR_IP, SEND_PORT, RECV_PORT

	found_ip = None
	deadline = time.time() + DISCOVERY_TIMEOUT_SEC
	while time.time() < deadline:
		try:
			data, addr = sock.recvfrom(256)
			if len(data) >= 30 and data[0] == 0x68 and data[1] == rand1 and data[2] == rand2:
				found_ip = addr[0]
				model = data[6:13].rstrip(b'\x00').decode('ascii', errors='replace')
				print(f"[Discovery] Found device '{model}' at {found_ip}")
				break
		except socket.timeout:
			continue
		except OSError:
			break

	sock.close()

	if found_ip:
		return found_ip, DEVICE_SEND_PORT, DEVICE_RECV_PORT
	print("[Discovery] No hardware found — using simulator fallback.")
	return SIMULATOR_IP, SEND_PORT, RECV_PORT


# --- UDP Communication ---
class GamblerFugitiveGameCommunicator:
	def __init__(self, recv_callback, device_ip, send_port, recv_port):
		self.device_ip = device_ip
		self.send_port = send_port
		self.send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		self.recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		self.recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self.recv_sock.bind(("", recv_port))
		self.recv_callback = recv_callback
		self.running = True
		self.seq = 0
		self._last_frame = bytes(FRAME_DATA_LEN)
		self._frame_lock = threading.Lock()
		threading.Thread(target=self._recv_loop, daemon=True).start()
		threading.Thread(target=self._send_loop, daemon=True).start()

	def send_led_frame(self, frame):
		with self._frame_lock:
			self._last_frame = frame

	def _send_loop(self):
		ep = (self.device_ip, self.send_port)
		while self.running:
			with self._frame_lock:
				frame = self._last_frame
			try:
				self.seq = (self.seq + 1) & 0xFFFF
				self.send_sock.sendto(build_start_packet(self.seq), ep)
				time.sleep(0.008)
				self.send_sock.sendto(build_fff0_packet(self.seq), ep)
				time.sleep(0.008)
				self.send_sock.sendto(build_command_packet(0x8877, 0x0000, frame, self.seq), ep)
				time.sleep(0.008)
				self.send_sock.sendto(build_end_packet(self.seq), ep)
			except OSError:
				if not self.running:
					break
			except Exception:
				pass
			time.sleep(LED_REFRESH_MS / 1000.0)

	def _recv_loop(self):
		while self.running:
			try:
				data, addr = self.recv_sock.recvfrom(1024)
				self.recv_callback(data, addr)
			except Exception:
				pass

	def close(self):
		self.running = False
		self.recv_sock.close()
		self.send_sock.close()
		
# game here
class GamblerFugitiveGame:
	def __init__(self, device_ip, send_port, recv_port):
		# Networking/transport.
		self.communicator = GamblerFugitiveGameCommunicator(self.handle_packet, device_ip, send_port, recv_port)

		# UI.
		self.root = tk.Tk()
		self.root.title("Gambler Fugitive Game")
		self.root.configure(bg="#09131b")
		self._configure_fullscreen_window()

		self.ui_card = tk.Frame(self.root, bg="#102332", bd=0, highlightthickness=2, highlightbackground="#1e4257")
		self.ui_card.pack(fill="both", expand=True, padx=40, pady=32)

		self.title_label = tk.Label(
			self.ui_card,
			text="Gambler Fugitive",
			font=("Bahnschrift", 44, "bold"),
			fg="#f4f7fb",
			bg="#102332",
		)
		self.title_label.pack(anchor="w", padx=40, pady=(34, 8))

		self.subtitle_label = tk.Label(
			self.ui_card,
			text="Co-op slot rush with eye scans, shared score, and recovery holds",
			font=("Segoe UI", 18),
			fg="#9dc3d8",
			bg="#102332",
		)
		self.subtitle_label.pack(anchor="w", padx=40, pady=(0, 28))

		self.score_panel = tk.Frame(self.ui_card, bg="#0b1a26", bd=0, highlightthickness=1, highlightbackground="#21475d")
		self.score_panel.pack(fill="x", padx=40, pady=(0, 22))
		self.score_caption = tk.Label(
			self.score_panel,
			text="TEAM SCORE",
			font=("Segoe UI", 15, "bold"),
			fg="#6cbad8",
			bg="#0b1a26",
		)
		self.score_caption.pack(anchor="w", padx=26, pady=(20, 6))
		self.score_label = tk.Label(
			self.score_panel,
			text="0",
			font=("Bahnschrift", 62, "bold"),
			fg="#ffd166",
			bg="#0b1a26",
		)
		self.score_label.pack(anchor="w", padx=26, pady=(0, 20))

		self.status_label = tk.Label(
			self.ui_card,
			text="Welcome to the Gambler Fugitive Game!",
			font=("Segoe UI Semibold", 22),
			fg="#f4f7fb",
			bg="#102332",
			justify="left",
			anchor="w",
		)
		self.status_label.pack(fill="x", padx=40, pady=(0, 12))

		self.hint_label = tk.Label(
			self.ui_card,
			text="Start from the button below. The game runs full-screen across the room display.",
			font=("Segoe UI", 15),
			fg="#88a9bb",
			bg="#102332",
			anchor="w",
		)
		self.hint_label.pack(fill="x", padx=40, pady=(0, 28))

		self.controls_frame = tk.Frame(self.ui_card, bg="#102332")
		self.controls_frame.pack(fill="x", padx=40, pady=(0, 32))
		self.start_button = tk.Button(
			self.controls_frame,
			text="Start Game",
			command=lambda: self.set_state(STATE_PLAYING),
			font=("Segoe UI Semibold", 22),
			fg="#041018",
			bg="#43d9a3",
			activeforeground="#041018",
			activebackground="#62efba",
			relief="flat",
			bd=0,
			padx=40,
			pady=18,
			cursor="hand2",
		)
		self.start_button.pack(side="left")
		self.idle_button = tk.Button(
			self.controls_frame,
			text="Return To Idle",
			command=lambda: self.set_state(STATE_IDLE),
			font=("Segoe UI", 18),
			fg="#d9e8f0",
			bg="#183647",
			activeforeground="#ffffff",
			activebackground="#21475d",
			relief="flat",
			bd=0,
			padx=34,
			pady=18,
			cursor="hand2",
		)
		self.idle_button.pack(side="left", padx=(18, 0))

		self._BG_MUSIC_WAV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bg_music.wav")
		self._audio_ready = False
		self._sound_cache = {}
		self._init_audio()
		# Shared runtime state.
		self.led_states = {}
		self._closed = False
		self._pressed_snapshot = set()

		# Scheduled Tk jobs.
		self._refresh_job = None
		self._eye_scan_start_job = None
		self._eye_scan_open_job = None
		self._eye_scan_stop_job = None

		# State machine fields.
		self._idle_anim_start = time.monotonic()
		self.state = STATE_IDLE
		self.active_scan_wall = None
		self.pending_scan_wall = None
		self.pre_scan_until_ts = 0.0
		self.scan_movement_detected = False
		self.scan_detection_enabled_ts = 0.0
		self.room_blink_until_ts = 0.0
		self.caught_hold_targets = set()

		# Shared team score.
		self.score = 0

		# Animation/trigger state.
		self.button_animations = {}
		self._anim_seq = 0
		self._anim_press_latch = set()
		self._lane_cooldown_until = {}

		# Thread-safe input queue (recv thread -> Tk thread).
		self._pending_pressed_queue = deque()
		self._input_queue_lock = threading.Lock()

		# Trigger availability timer.
		self.green_visible_from_ts = 0.0
		self.green_visible_until_ts = 0.0
		self.next_eye_warning_ts = 0.0
		self.root.protocol("WM_DELETE_WINDOW", self.on_close)
		self._play_idle_music()
		self._apply_state_defaults()
		self.update_leds()
		self._schedule_led_refresh()
		self.set_status("State: IDLE")
		self._refresh_control_state()

	def handle_packet(self, data, addr):
		if self.state != STATE_PLAYING:
			return
		if len(data) != TRIGGER_PACKET_LEN or data[0] != 0x88:
			return
		if (sum(data[:-1]) & 0xFF) != data[-1]:
			return

		pressed = set()
		for ch in range(1, NUM_CHANNELS + 1):
			base = 2 + (ch - 1) * 171
			for idx in range(LEDS_PER_CHANNEL):
				if data[base + 1 + idx] == 0xCC:
					pressed.add((ch, idx))

		# Queue input for main-thread processing; do not call Tk APIs from recv thread.
		with self._input_queue_lock:
			self._pending_pressed_queue.append(pressed)

	def _drain_input_updates(self):
		"""Run queued button snapshots on Tk thread to keep state updates thread-safe."""
		with self._input_queue_lock:
			if not self._pending_pressed_queue:
				return
			queued = list(self._pending_pressed_queue)
			self._pending_pressed_queue.clear()

		for pressed in queued:
			if self.state != STATE_PLAYING:
				continue

			rising = pressed - self._pressed_snapshot
			if DEBUG_INPUT and (pressed or rising):
				print(f"[Input] pressed={sorted(pressed)} rising={sorted(rising)}")

			now = time.monotonic()
			self._maybe_start_press_animations(pressed, now)

			# Ignore duplicate packets carrying identical state.
			if pressed == self._pressed_snapshot:
				continue

			self._pressed_snapshot = pressed
			if (
				self.active_scan_wall is not None
				and now >= self.scan_detection_enabled_ts
				and (self.active_scan_wall, EYE_LED_INDEX) in rising
			):
				if DEBUG_INPUT:
					print(f"[Eye] Infrared movement detected on wall {self.active_scan_wall} (rising eye index {EYE_LED_INDEX})")
				self.scan_movement_detected = True
				self.room_blink_until_ts = now + (ROOM_BLINK_DURATION_MS / 1000.0)
				self.set_status(f"State: PLAYING | Infrared movement on wall {self.active_scan_wall}")

			self._apply_pressed_leds(self._pressed_snapshot)

	def set_state(self, state):
		"""Switch between IDLE and PLAYING and reset the flow-dependent state."""
		if state not in (STATE_PLAYING, STATE_IDLE):
			return
		if self.state == state:
			return

		self.state = state
		self._pressed_snapshot = set()
		self._cancel_eye_scan_jobs()
		self.active_scan_wall = None
		self.pending_scan_wall = None
		self.pre_scan_until_ts = 0.0
		self.scan_movement_detected = False
		self.scan_detection_enabled_ts = 0.0
		self.room_blink_until_ts = 0.0
		self.caught_hold_targets.clear()
		self.button_animations.clear()
		self._anim_press_latch.clear()
		self._lane_cooldown_until.clear()
		self.green_visible_from_ts = 0.0
		self.green_visible_until_ts = 0.0
		self.next_eye_warning_ts = 0.0
		if self.state == STATE_IDLE:
			self._idle_anim_start = time.monotonic()
			self._play_idle_music()
		self._apply_state_defaults()
		if self.state == STATE_PLAYING:
			self.set_status("State: PLAYING")
			self._schedule_next_eye_scan()
		else:
			self.set_status("State: IDLE")
		self._refresh_control_state()
		self.update_leds()

	def _apply_state_defaults(self):
		if self.state == STATE_PLAYING:
			self._clear_leds()
			self._apply_playing_baseline()
		elif self.state == STATE_IDLE:
			self._render_idle_frame(time.monotonic())

	def _apply_pressed_leds(self, pressed):
		if self.state != STATE_PLAYING:
			return
		now = time.monotonic()
		self._update_caught_hold(now, pressed)
		if self._is_room_blink_active(now):
			self._render_room_blink(now)
			self.update_leds()
			return
		if self._is_pre_scan_warning_active(now):
			self._render_pre_scan_warning(now)
			self.update_leds()
			return
		if self.active_scan_wall is None:
			self._update_button_animations(now)
		self._clear_leds()
		self._apply_playing_baseline()
		if self.active_scan_wall is not None:
			for led in range(LEDS_PER_CHANNEL):
				self.led_states[(self.active_scan_wall, led)] = (255, 0, 0)
			self.led_states[(self.active_scan_wall, EYE_LED_INDEX)] = (255, 255, 0)
		else:
			self._render_button_animations()
		if self._is_caught_hold_active():
			self._render_caught_hold_targets()
		self.update_leds()

	def mainloop(self):
		try:
			while not self._closed:
				self.root.update_idletasks()
				self.root.update()
				time.sleep(0.01)
		except tk.TclError:
			# Window was closed/destroyed while updating.
			pass
		except KeyboardInterrupt:
			print("[Game] Keyboard interrupt received. Closing gracefully.")
		finally:
			self.on_close()

	def on_close(self):
		if self._closed:
			return
		self._closed = True
		self._shutdown_audio()
		self._cancel_eye_scan_jobs()
		if self._refresh_job is not None:
			try:
				self.root.after_cancel(self._refresh_job)
			except Exception:
				pass
			self._refresh_job = None
		try:
			self.communicator.close()
		except Exception:
			pass
		try:
			self.root.destroy()
		except Exception:
			pass

	def _init_audio(self):
		try:
			if not pygame.mixer.get_init():
				pygame.mixer.init()
			self._audio_ready = True
		except Exception:
			self._audio_ready = False

	def _play_idle_music(self):
		try:
			if not self._audio_ready:
				return
			if not pygame.mixer.music.get_busy():
				pygame.mixer.music.load(self._BG_MUSIC_WAV)
				pygame.mixer.music.play(-1)
		except Exception:
			pass

	def _stop_sound(self):
		try:
			if self._audio_ready:
				pygame.mixer.stop()
		except Exception:
			pass

	def _shutdown_audio(self):
		try:
			if self._audio_ready:
				pygame.mixer.music.stop()
				pygame.mixer.stop()
				pygame.mixer.quit()
		except Exception:
			pass
	def update_leds(self):
		frame = build_frame_data(self.led_states)
		self.communicator.send_led_frame(frame)

	def _schedule_led_refresh(self):
		if self._closed:
			return
		try:
			# Process any queued input snapshots on the main thread.
			self._drain_input_updates()
			now = time.monotonic()
			# Render priority:
			# IDLE animation > room red blink > eye pre-warning > normal PLAYING render.
			if self.state == STATE_IDLE:
				self._render_idle_frame(now)
			elif self.state == STATE_PLAYING and self._is_room_blink_active(now):
				self._render_room_blink(now)
			elif self.state == STATE_PLAYING and self._is_pre_scan_warning_active(now):
				self._render_pre_scan_warning(now)
			elif self.state == STATE_PLAYING:
				self._apply_pressed_leds(self._pressed_snapshot)
				self._refresh_job = self.root.after(LED_REFRESH_MS, self._schedule_led_refresh)
				return
			self.update_leds()
		except KeyboardInterrupt:
			self.on_close()
			return
		except Exception:
			pass
		self._refresh_job = self.root.after(LED_REFRESH_MS, self._schedule_led_refresh)

	def set_status(self, text):
		self.status_label.config(text=text)

	def _configure_fullscreen_window(self):
		try:
			user32 = ctypes.windll.user32
			x = user32.GetSystemMetrics(76)
			y = user32.GetSystemMetrics(77)
			width = user32.GetSystemMetrics(78)
			height = user32.GetSystemMetrics(79)
			self.root.geometry(f"{width}x{height}{x:+d}{y:+d}")
			self.root.state("normal")
			self.root.attributes("-topmost", False)
		except Exception:
			self.root.state("zoomed")

	def _refresh_control_state(self):
		if self.state == STATE_PLAYING:
			self.start_button.config(text="Game Running", state="disabled", bg="#24596b", fg="#88a9bb", cursor="arrow")
			self.idle_button.config(state="normal", cursor="hand2")
		else:
			self.start_button.config(text="Start Game", state="normal", bg="#43d9a3", fg="#041018", cursor="hand2")
			self.idle_button.config(state="disabled", cursor="arrow")

	def _update_score_label(self):
		self.score_label.config(text=str(self.score))

	def _clear_leds(self):
		self.led_states.clear()
		for ch in range(1, NUM_CHANNELS + 1):
			for led in range(LEDS_PER_CHANNEL):
				self.led_states[(ch, led)] = (0, 0, 0)

	def _apply_playing_baseline(self, now=None):
		if now is None:
			now = time.monotonic()
		blocked_walls = set()
		if self._is_caught_hold_active():
			blocked_walls = self._get_caught_hold_walls()
			if not self._is_caught_hold_satisfied(self._pressed_snapshot):
				return
		# Green trigger buttons respawn after a short delay, then hide just before eye warning.
		if now < self.green_visible_from_ts or now >= self.green_visible_until_ts:
			return
		for ch in range(1, NUM_CHANNELS + 1):
			if ch in blocked_walls:
				continue
			# Keep green hidden while pressed or while that lane animation is still active.
			left_blocked = (
				(ch, "left") in self._anim_press_latch
				or self._has_active_lane_animation(ch, "left")
				or now < self._lane_cooldown_until.get((ch, "left"), 0.0)
			)
			right_blocked = (
				(ch, "right") in self._anim_press_latch
				or self._has_active_lane_animation(ch, "right")
				or now < self._lane_cooldown_until.get((ch, "right"), 0.0)
			)
			if not left_blocked and 0 <= 3 < LEDS_PER_CHANNEL:
				self.led_states[(ch, 3)] = (0, 255, 0)
			if not right_blocked and 0 <= 8 < LEDS_PER_CHANNEL:
				self.led_states[(ch, 8)] = (0, 255, 0)

	def _has_active_lane_animation(self, channel, lane):
		for _anim_id, anim in self.button_animations.items():
			if anim.get("channel") == channel and anim.get("lane") == lane:
				return True
		return False

	def _get_adjacent_wall(self, channel):
		return channel + 1 if channel < NUM_CHANNELS else 1

	def _is_caught_hold_active(self):
		return bool(self.caught_hold_targets)

	def _get_caught_hold_walls(self):
		return {channel for channel, _led in self.caught_hold_targets}

	def _is_caught_hold_satisfied(self, pressed):
		return self.caught_hold_targets.issubset(pressed)

	def _render_caught_hold_targets(self):
		for target in self.caught_hold_targets:
			self.led_states[target] = HOLD_TARGET_COLOR

	def _start_caught_hold(self, wall):
		adjacent_wall = self._get_adjacent_wall(wall)
		self.caught_hold_targets = {
			(wall, HOLD_SOURCE_LED),
			(adjacent_wall, HOLD_ADJACENT_LED),
		}
		self.set_status(
			f"State: PLAYING | Hold blue buttons on walls {wall} and {adjacent_wall} until the next eye opens"
		)

	def _clear_caught_hold(self):
		self.caught_hold_targets.clear()

	def _update_caught_hold(self, now, pressed):
		if not self._is_caught_hold_active():
			return
		return

	def _is_eye_animation_active(self, now):
		return (
			self._is_room_blink_active(now)
			or self._is_pre_scan_warning_active(now)
			or self.active_scan_wall is not None
		)

	def _is_room_blink_active(self, now):
		return now < self.room_blink_until_ts

	def _render_room_blink(self, now):
		blink_phase = int((now * 1000.0) / ROOM_BLINK_INTERVAL_MS) % 2
		self.led_states.clear()
		for ch in range(1, NUM_CHANNELS + 1):
			for led in range(LEDS_PER_CHANNEL):
				self.led_states[(ch, led)] = (255, 0, 0) if blink_phase == 0 else (0, 0, 0)

	def _is_pre_scan_warning_active(self, now):
		return self.pending_scan_wall is not None and now < self.pre_scan_until_ts

	def _render_pre_scan_warning(self, now):
		blink_phase = int((now * 1000.0) / PRE_SCAN_BLINK_INTERVAL_MS) % 2
		self._clear_leds()
		if self.pending_scan_wall is None:
			return
		for led in range(LEDS_PER_CHANNEL):
			self.led_states[(self.pending_scan_wall, led)] = (PRE_SCAN_RED_LEVEL, 0, 0) if blink_phase == 0 else (0, 0, 0)

	_SLOTS_WAV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "slots.wav")
	_SMALL_WIN_WAV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "small_win.wav")
	_JACKPOT_WAV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jackpot.wav")

	def _play_sound(self, path):
		try:
			if not self._audio_ready:
				return
			sound = self._sound_cache.get(path)
			if sound is None:
				sound = pygame.mixer.Sound(path)
				self._sound_cache[path] = sound
			sound.play()
		except Exception:
			pass

	def _play_win_sound(self, points):
		if points == SCORE_JACKPOT:
			self._play_sound(self._JACKPOT_WAV)
		elif points in (SCORE_3_IN_A_ROW, SCORE_4_IN_A_ROW):
			self._play_sound(self._SMALL_WIN_WAV)

	def _check_spin_score(self, final_colors):
		"""Return points for a completed 5-reel spin. Checks combos highest-first."""
		c = final_colors
		if len(c) < 5:
			return 0
		# Jackpot: all 5 the same.
		if c[0] == c[1] == c[2] == c[3] == c[4]:
			return SCORE_JACKPOT
		# 4 in a row.
		for i0, i1, i2, i3 in _COMBOS_4:
			if c[i0] == c[i1] == c[i2] == c[i3]:
				return SCORE_4_IN_A_ROW
		# 3 in a row (consecutive or 1-3-5 pattern).
		for i0, i1, i2 in _COMBOS_3:
			if c[i0] == c[i1] == c[i2]:
				return SCORE_3_IN_A_ROW
		return 0

	def _start_button_animation(self, channel, lane, order):
		if self.state != STATE_PLAYING:
			return
		# Play slots sound asynchronously (non-blocking).
		self._play_sound(self._SLOTS_WAV)
		# Final colors are locked progressively from left to right.
		final_colors = [random.choice(ANIM_COLORS) for _ in order]
		self._anim_seq += 1
		anim_id = (channel, lane, self._anim_seq)
		if DEBUG_INPUT:
			print(f"[Anim] START id={anim_id} wall={channel} lane={lane} order={order} final_colors={final_colors}")
		self.button_animations[anim_id] = {
			"channel": channel,
			"lane": lane,
			"order": order,
			"final_colors": final_colors,
			"step": 0,
			"last_step_ts": time.monotonic(),
		}

	def _update_button_animations(self, now):
		to_remove = []
		for anim_key, anim in self.button_animations.items():
			if (now - anim["last_step_ts"]) * 1000.0 >= ANIM_STEP_MS:
				anim["step"] += 1
				anim["last_step_ts"] = now
				if anim["step"] >= len(anim["order"]):
					to_remove.append(anim_key)
		for anim_key in to_remove:
			anim = self.button_animations.pop(anim_key, None)
			if anim is not None:
				# Score this spin and update the shared team score.
				pts = self._check_spin_score(anim["final_colors"])
				if pts > 0:
					self.score += pts
					self._update_score_label()
					self._play_win_sound(pts)
					print(f"[Score] +{pts} pts (wall={anim['channel']} lane={anim['lane']}) → total {self.score}")
				elif DEBUG_INPUT:
					print(f"[Score] no combo (wall={anim['channel']} lane={anim['lane']}) → total {self.score}")
				lane_key = (anim["channel"], anim["lane"])
				self._lane_cooldown_until[lane_key] = now + random.uniform(SPIN_COOLDOWN_MIN_SEC, SPIN_COOLDOWN_MAX_SEC)

	def _render_button_animations(self):
		for _anim_id, anim in self.button_animations.items():
			channel = anim["channel"]
			step = anim["step"]
			last_idx = max(-1, min(step, len(anim["order"]) - 1))
			for i, led in enumerate(anim["order"]):
				# LEDs to the left are locked; LEDs to the right keep flickering randomly.
				if i <= last_idx:
					color = anim["final_colors"][i]
				else:
					color = random.choice(ANIM_COLORS)
				led = anim["order"][i]
				if 0 <= led < LEDS_PER_CHANNEL:
					self.led_states[(channel, led)] = color

	def _maybe_start_press_animations(self, pressed, now):
		"""Start lane animations from trigger buttons, respecting state gates and latches."""
		blocked_walls = set()
		if self._is_caught_hold_active():
			blocked_walls = self._get_caught_hold_walls()
			if not self._is_caught_hold_satisfied(pressed):
				self._anim_press_latch.clear()
				return
		# Trigger buttons can only be used while green is visible.
		if now >= self.green_visible_until_ts:
			for ch in range(1, NUM_CHANNELS + 1):
				self._anim_press_latch.discard((ch, "left"))
				self._anim_press_latch.discard((ch, "right"))
			return

		# 3/8 presses are ignored while any eye warning/scan/blink is active.
		if self._is_eye_animation_active(now):
			for ch in range(1, NUM_CHANNELS + 1):
				left_pressed = ((ch, 3) in pressed) or ((ch, 2) in pressed)
				right_pressed = ((ch, 8) in pressed) or ((ch, 7) in pressed)
				left_key = (ch, "left")
				right_key = (ch, "right")
				if left_pressed:
					self._anim_press_latch.add(left_key)
				else:
					self._anim_press_latch.discard(left_key)
				if right_pressed:
					self._anim_press_latch.add(right_key)
				else:
					self._anim_press_latch.discard(right_key)
			return

		for ch in range(1, NUM_CHANNELS + 1):
			if ch in blocked_walls:
				self._anim_press_latch.discard((ch, "left"))
				self._anim_press_latch.discard((ch, "right"))
				continue
			left_pressed = ((ch, 3) in pressed) or ((ch, 2) in pressed)
			right_pressed = ((ch, 8) in pressed) or ((ch, 7) in pressed)

			left_key = (ch, "left")
			right_key = (ch, "right")

			# Release latch when lane buttons are no longer pressed.
			if not left_pressed:
				self._anim_press_latch.discard(left_key)
			if not right_pressed:
				self._anim_press_latch.discard(right_key)

			# Trigger once per press; do not restart while lane is held.
			if left_pressed and left_key not in self._anim_press_latch:
				if DEBUG_INPUT:
					print(f"[Anim] TRIGGER wall={ch} lane=left (1-5)")
				self._anim_press_latch.add(left_key)
				if now >= self._lane_cooldown_until.get(left_key, 0.0):
					self._start_button_animation(ch, "left", [1, 2, 3, 4, 5])
				elif DEBUG_INPUT:
					print(f"[Anim] SKIP wall={ch} lane=left cooldown")

			if right_pressed and right_key not in self._anim_press_latch:
				if DEBUG_INPUT:
					print(f"[Anim] TRIGGER wall={ch} lane=right (6-10)")
				self._anim_press_latch.add(right_key)
				if now >= self._lane_cooldown_until.get(right_key, 0.0):
					self._start_button_animation(ch, "right", [6, 7, 8, 9, 10])
				elif DEBUG_INPUT:
					print(f"[Anim] SKIP wall={ch} lane=right cooldown")

	def _cancel_eye_scan_jobs(self):
		if self._eye_scan_start_job is not None:
			try:
				self.root.after_cancel(self._eye_scan_start_job)
			except Exception:
				pass
			self._eye_scan_start_job = None
		if self._eye_scan_open_job is not None:
			try:
				self.root.after_cancel(self._eye_scan_open_job)
			except Exception:
				pass
			self._eye_scan_open_job = None
		if self._eye_scan_stop_job is not None:
			try:
				self.root.after_cancel(self._eye_scan_stop_job)
			except Exception:
				pass
			self._eye_scan_stop_job = None

	def _schedule_next_eye_scan(self):
		if self._closed or self.state != STATE_PLAYING:
			return
		delay_ms = random.randint(EYE_SCAN_GAP_MIN_MS, EYE_SCAN_GAP_MAX_MS)
		now = time.monotonic()
		self.next_eye_warning_ts = now + (delay_ms / 1000.0)
		self._reset_green_window(self.next_eye_warning_ts, now)
		self._eye_scan_start_job = self.root.after(delay_ms, self._start_eye_warning)

	def _start_eye_warning(self):
		"""Start pre-scan warning blink before opening the selected eye wall."""
		self._eye_scan_start_job = None
		if self._closed or self.state != STATE_PLAYING:
			return

		# Do not interrupt active lane animations; wait until they finish.
		if self.button_animations:
			if DEBUG_INPUT:
				print("[Eye] Warning delayed: waiting for active button animations to finish")
			self._eye_scan_start_job = self.root.after(200, self._start_eye_warning)
			return

		self.green_visible_until_ts = min(self.green_visible_until_ts, time.monotonic())
		self.pending_scan_wall = random.randint(1, NUM_CHANNELS)
		self.pre_scan_until_ts = time.monotonic() + (PRE_SCAN_WARN_MS / 1000.0)
		self.set_status(f"State: PLAYING | Eye warning on wall {self.pending_scan_wall}")
		self._apply_pressed_leds(self._pressed_snapshot)
		self._eye_scan_open_job = self.root.after(PRE_SCAN_WARN_MS, self._start_eye_scan)

	def _start_eye_scan(self):
		"""Open eye on selected wall and enable IR detection after grace period."""
		self._eye_scan_open_job = None
		if self._closed or self.state != STATE_PLAYING:
			return

		if self._is_caught_hold_active():
			self._clear_caught_hold()
			self.set_status("State: PLAYING")

		self.active_scan_wall = self.pending_scan_wall if self.pending_scan_wall is not None else random.randint(1, NUM_CHANNELS)
		self.pending_scan_wall = None
		self.pre_scan_until_ts = 0.0
		self.scan_movement_detected = False
		self.scan_detection_enabled_ts = time.monotonic() + (EYE_SCAN_GRACE_MS / 1000.0)
		self.set_status(f"State: PLAYING | Eye open on wall {self.active_scan_wall} (grace 0.5s)")
		self._apply_pressed_leds(self._pressed_snapshot)

		duration_ms = random.randint(EYE_SCAN_MIN_MS, EYE_SCAN_MAX_MS)
		self._eye_scan_stop_job = self.root.after(duration_ms, self._stop_eye_scan)

	def _stop_eye_scan(self):
		"""Finish current eye scan, report result, reopen trigger window, and schedule next scan."""
		self._eye_scan_stop_job = None
		if self.state != STATE_PLAYING:
			return

		closed_wall = self.active_scan_wall
		movement_detected = self.scan_movement_detected
		self.active_scan_wall = None
		self.scan_movement_detected = False
		self.scan_detection_enabled_ts = 0.0
		if movement_detected and closed_wall is not None:
			self.set_status(f"State: PLAYING | Movement caught on wall {closed_wall}")
			self._start_caught_hold(closed_wall)
		else:
			self.set_status("State: PLAYING")
		self._apply_pressed_leds(self._pressed_snapshot)
		self._schedule_next_eye_scan()

	def _reset_green_window(self, next_warning_ts=None, now=None):
		"""Show green triggers immediately and hide them shortly before eye warning."""
		if now is None:
			now = time.monotonic()
		if next_warning_ts is None:
			next_warning_ts = self.next_eye_warning_ts
		hide_ts = next_warning_ts - (GREEN_HIDE_BEFORE_WARNING_MS / 1000.0)
		if hide_ts <= now:
			hide_ts = now + 0.1
		self.green_visible_from_ts = now
		self.green_visible_until_ts = hide_ts

	def _render_idle_frame(self, now):
		# Crossfade odd/even wall LEDs between 50% and 0% each second, then reverse.
		elapsed_ms = (now - self._idle_anim_start) * 1000.0
		phase = elapsed_ms / IDLE_FADE_MS
		mix = 0.5 * (1.0 + math.cos(math.pi * phase))
		odd_level = 0.50 * mix
		even_level = 0.50 * (1.0 - mix)

		self.led_states.clear()
		for ch in range(1, NUM_CHANNELS + 1):
			for led in range(LEDS_PER_CHANNEL):
				if led == EYE_LED_INDEX:
					red = int(255 * (1.0 - mix))
					self.led_states[(ch, led)] = (red, 255, 0)
					continue
				one_based = led + 1
				level = odd_level if (one_based % 2 == 1) else even_level
				g = int(255 * level)
				self.led_states[(ch, led)] = (0, g, 0)


if __name__ == "__main__":
	game = None
	try:
		print("[Discovery] Scanning LAN for Evil Eye hardware...")
		device_ip, send_port, recv_port = run_discovery()
		is_real_target = (send_port == DEVICE_SEND_PORT and recv_port == DEVICE_RECV_PORT)
		OUTPUT_SWAP_RB = bool(is_real_target and REAL_ROOM_SWAP_RB)
		OUTPUT_LED_SHIFT = REAL_ROOM_LED_SHIFT if is_real_target else 0
		OUTPUT_COLOR_ORDER = REAL_ROOM_COLOR_ORDER if is_real_target else "RGB"
		if is_real_target:
			print(
				f"[Compat] Real-room mapping active: order={OUTPUT_COLOR_ORDER}, "
				f"swap_rb={OUTPUT_SWAP_RB}, led_shift={OUTPUT_LED_SHIFT}"
			)
		else:
			print(
				f"[Compat] Simulator/default mapping active: order={OUTPUT_COLOR_ORDER}, "
				f"swap_rb={OUTPUT_SWAP_RB}, led_shift={OUTPUT_LED_SHIFT}"
			)
		print(f"[Discovery] Connecting to {device_ip}:{send_port} (recv:{recv_port})")
		game = GamblerFugitiveGame(device_ip, send_port, recv_port)
		game.mainloop()
	except KeyboardInterrupt:
		print("\n[Main] Ctrl+C received. Exiting cleanly.")
	finally:
		if game is not None:
			game.on_close()