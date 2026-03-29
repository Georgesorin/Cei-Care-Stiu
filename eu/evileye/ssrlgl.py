import socket
import threading
import random
import time
import ctypes
import os
import winsound
import io
import wave
import audioop
import tkinter as tk
from tkinter import ttk

# --- Protocol/Simulator Settings ---
NUM_CHANNELS = 4
LEDS_PER_CHANNEL = 11
EYE_LED_INDEX = 10
SIMULATOR_IP = '127.0.0.1'
# SEND_PORT = 4626  # To simulator (light commands)
# RECV_PORT = 7800  # From simulator (button events)
SEND_PORT = 7273
RECV_PORT = 7272
FRAME_DATA_LEN = LEDS_PER_CHANNEL * NUM_CHANNELS * 3
TRIGGER_PACKET_LEN = 687

# Real hardware ports (used when a device is discovered on the LAN)
DEVICE_IP = '169.254.182.11'       # Known device IP (link-local)
DEVICE_SEND_PORT = 4626            # Send light commands to device
DEVICE_RECV_PORT = 7800            # Receive button events from device
DISCOVERY_TIMEOUT_SEC = 3  # How long to wait for a hardware response

# Playable buttons based on your wall layout (all non-eye LEDs).
WALL_PATH = [idx for idx in range(LEDS_PER_CHANNEL) if idx != EYE_LED_INDEX]

# Timings (milliseconds)
SHOW_ON_MS = 700
SHOW_OFF_MS = 250
INPUT_GREEN_MS = 3400
INPUT_RED_MS = 1400
INPUT_TIMEOUT_MS = 20000
LED_REFRESH_MS = 220
EYE_PENALTY_SECONDS = 1.0
MAX_EYE_STRIKES = 4
AUTO_NEXT_ROUND_MS = 5000
RED_PENALTY_RESTART_MS = 2000
DETECTION_COOLDOWN_MS = 180
MOTION_COOLDOWN_MS = 900
RED_LIGHT_GRACE_MS = 350
RED_MOVE_COOLDOWN_MS = 1400
MAX_ROUND1_REGRESSIONS = 5
MOTION_CONFIRM_PACKETS = 1
MOTION_ACTIVE_GAP_MS = 180

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


def build_frame_data(led_states):
	frame = bytearray(FRAME_DATA_LEN)
	for (ch, led), (r, g, b) in led_states.items():
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
		sock.sendto(pkt, (DEVICE_IP, DEVICE_SEND_PORT))
		print(f"[Discovery] Sent unicast to {DEVICE_IP}:{DEVICE_SEND_PORT}")
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
	print("[Discovery] No hardware found — falling back to known device IP.")
	return DEVICE_IP, DEVICE_SEND_PORT, DEVICE_RECV_PORT


def get_monitor_rects():
	"""Return monitor rectangles [(left, top, right, bottom), ...] on Windows."""
	class RECT(ctypes.Structure):
		_fields_ = [
			("left", ctypes.c_long),
			("top", ctypes.c_long),
			("right", ctypes.c_long),
			("bottom", ctypes.c_long),
		]

	monitor_rects = []

	MONITORENUMPROC = ctypes.WINFUNCTYPE(
		ctypes.c_int,
		ctypes.c_ulong,
		ctypes.c_ulong,
		ctypes.POINTER(RECT),
		ctypes.c_double,
	)

	def _callback(hmonitor, hdc, lprect, lparam):
		r = lprect.contents
		monitor_rects.append((int(r.left), int(r.top), int(r.right), int(r.bottom)))
		return 1

	try:
		ctypes.windll.user32.EnumDisplayMonitors(0, 0, MONITORENUMPROC(_callback), 0)
	except Exception:
		return []

	return monitor_rects


# --- UDP Communication ---
class EvilEyeComm:
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
		threading.Thread(target=self._recv_loop, daemon=True).start()

	def send_led_frame(self, led_states):
		frame = build_frame_data(led_states)
		ep = (self.device_ip, self.send_port)
		self.seq = (self.seq + 1) & 0xFFFF
		self.send_sock.sendto(build_start_packet(self.seq), ep)
		time.sleep(0.008)
		self.send_sock.sendto(build_fff0_packet(self.seq), ep)
		time.sleep(0.008)
		self.send_sock.sendto(build_command_packet(0x8877, 0x0000, frame, self.seq), ep)
		time.sleep(0.008)
		self.send_sock.sendto(build_end_packet(self.seq), ep)

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

# --- Game Logic ---
class EvilEyeGame(tk.Tk):
	def __init__(self, device_ip, send_port, recv_port):
		super().__init__()
		self.title("Evil Eye - Memory x Red Light / Green Light")
		self.geometry("860x520")

		self._device_ip = device_ip
		self._send_port = send_port
		self._recv_port = recv_port
		self._is_simulator = (device_ip == SIMULATOR_IP)
		self.comm = EvilEyeComm(self.on_button_event, device_ip, send_port, recv_port)
		self._device_label_var = tk.StringVar(value=f"Device: {device_ip}:{send_port}")
		self.status_var = tk.StringVar(value="Press Start Round")
		self.round_var = tk.StringVar(value="Round: 0")
		self.phase_var = tk.StringVar(value="Phase: Idle")

		self.sequence = []
		self.input_index = 0
		self.phase = "IDLE"
		self.prev_pressed = set()
		self.current_show_node = None
		self.green_light = True
		self.input_deadline_ts = 0.0
		self.eye_strikes = 0
		self.round1_grace_available = True
		self.round1_regression_count = 0
		self._last_press_ts = 0.0
		self._last_motion_ts = 0.0
		self._last_light_toggle_ts = 0.0
		self._last_red_penalty_ts = 0.0
		self.red_warning_used = False
		self._motion_seen_count = {}
		self._motion_last_seen_ts = {}
		self._motion_reported_active = set()

		self._last_led_states = {}
		self._flash_leds = {}

		self._show_job = None
		self._light_job = None
		self._timeout_job = None
		self._refresh_job = None
		self._next_round_job = None
		self._tv_window = None
		self._tv_text_var = tk.StringVar(value="Welcome. Press Start Round.")
		self._sound_gain = 0.8
		self._sound_paths = self._resolve_sound_paths()
		self._sound_buffers = self._build_quieter_sound_buffers()

		self._build_ui()
		self._build_tv_ui()
		self._position_tv_window()
		self._update_tv_text()
		self.status_var.trace_add("write", lambda *_args: self._update_tv_text())
		self.phase_var.trace_add("write", lambda *_args: self._update_tv_text())
		self.round_var.trace_add("write", lambda *_args: self._update_tv_text())
		self._schedule_led_refresh()
		self.protocol("WM_DELETE_WINDOW", self.on_close)

	def _resolve_sound_paths(self):
		base_dir = os.path.dirname(os.path.abspath(__file__))
		parent_dir = os.path.dirname(base_dir)
		start_candidates = [
			os.path.join(base_dir, "start.wav"),
			os.path.join(parent_dir, "start.wav"),
		]
		end_candidates = [
			os.path.join(base_dir, "end.wav"),
			os.path.join(parent_dir, "end.wav"),
		]
		beep_candidates = [
			os.path.join(base_dir, "beep.wav"),
			os.path.join(parent_dir, "beep.wav"),
		]

		start_path = next((p for p in start_candidates if os.path.exists(p)), None)
		end_path = next((p for p in end_candidates if os.path.exists(p)), None)
		beep_path = next((p for p in beep_candidates if os.path.exists(p)), None)
		return {"start": start_path, "end": end_path, "beep": beep_path}

	def _attenuate_wav_bytes(self, wav_path, gain):
		"""Return a quieter WAV byte stream. Falls back to original file bytes if needed."""
		try:
			with wave.open(wav_path, "rb") as src:
				params = src.getparams()
				raw = src.readframes(src.getnframes())
				sample_width = src.getsampwidth()

			quiet_raw = audioop.mul(raw, sample_width, gain)

			buf = io.BytesIO()
			with wave.open(buf, "wb") as dst:
				dst.setparams(params)
				dst.writeframes(quiet_raw)
			return buf.getvalue()
		except Exception:
			try:
				with open(wav_path, "rb") as f:
					return f.read()
			except Exception:
				return None

	def _build_quieter_sound_buffers(self):
		buffers = {}
		for cue_name, path in self._sound_paths.items():
			if cue_name == "beep":
				continue
			if not path:
				buffers[cue_name] = None
				continue
			buffers[cue_name] = self._attenuate_wav_bytes(path, self._sound_gain)
		return buffers

	def _pitch_factor_for_round(self):
		"""Increase beep pitch as rounds increase, with a safe upper cap."""
		return min(1.9, 1.0 + max(0, len(self.sequence) - 1) * 0.07)

	def _build_pitched_beep_bytes(self, pitch_factor):
		path = self._sound_paths.get("beep")
		if not path:
			return None
		try:
			with wave.open(path, "rb") as src:
				params = src.getparams()
				raw = src.readframes(src.getnframes())
				new_rate = int(max(8000, min(192000, params.framerate * pitch_factor)))

			buf = io.BytesIO()
			with wave.open(buf, "wb") as dst:
				dst.setnchannels(params.nchannels)
				dst.setsampwidth(params.sampwidth)
				dst.setframerate(new_rate)
				dst.writeframes(raw)
			return buf.getvalue()
		except Exception:
			return None

	def _play_beep_for_round(self):
		path = self._sound_paths.get("beep")
		if not path:
			return

		if not hasattr(self, "_beep_cache"):
			self._beep_cache = {}

		factor = self._pitch_factor_for_round()
		cache_key = int(factor * 100)
		wav_bytes = self._beep_cache.get(cache_key)
		if wav_bytes is None:
			wav_bytes = self._build_pitched_beep_bytes(factor)
			self._beep_cache[cache_key] = wav_bytes

		if wav_bytes:
			try:
				winsound.PlaySound(wav_bytes, winsound.SND_MEMORY | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
				return
			except Exception:
				pass

		try:
			winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
		except Exception:
			pass

	def _play_cue(self, cue_name):
		wav_bytes = self._sound_buffers.get(cue_name)
		path = self._sound_paths.get(cue_name)

		if wav_bytes:
			try:
				winsound.PlaySound(wav_bytes, winsound.SND_MEMORY | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
				return
			except Exception:
				pass

		if path:
			try:
				winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
			except Exception:
				pass

	def _build_ui(self):
		top = tk.Frame(self, bg="#1f1f1f")
		top.pack(fill=tk.X)

		ttk.Button(top, text="Start Round", command=self.start_round).pack(side=tk.LEFT, padx=10, pady=10)
		ttk.Button(top, text="Reset", command=self.reset_game).pack(side=tk.LEFT, padx=6, pady=10)
		tk.Label(top, textvariable=self.round_var, bg="#1f1f1f", fg="#d8d8d8").pack(side=tk.LEFT, padx=14)
		tk.Label(top, textvariable=self.phase_var).pack(side=tk.LEFT, padx=14)
		tk.Label(top, textvariable=self.status_var).pack(side=tk.LEFT, padx=14)
		tk.Label(top, textvariable=self._device_label_var, bg="#1f1f1f", fg="#888").pack(side=tk.RIGHT, padx=10)
		self._mode_btn = ttk.Button(top, text=self._mode_btn_text(), command=self._switch_connection)
		self._mode_btn.pack(side=tk.RIGHT, padx=6, pady=10)

		self.log_text = tk.Text(self, height=20, state="disabled", bg="#111", fg="#00ff8c")
		self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

	def _build_tv_ui(self):
		self._tv_window = tk.Toplevel(self)
		self._tv_window.title("Evil Eye - Room Display")
		self._tv_window.configure(bg="#050505")

		header = tk.Label(
			self._tv_window,
			text="EVIL EYE",
			bg="#050505",
			fg="#00ff8c",
			font=("Segoe UI", 34, "bold"),
		)
		header.pack(pady=(24, 8))

		self._tv_label = tk.Label(
			self._tv_window,
			textvariable=self._tv_text_var,
			bg="#050505",
			fg="#f0f0f0",
			font=("Segoe UI", 28, "bold"),
			justify="center",
			wraplength=1400,
		)
		self._tv_label.pack(expand=True, fill=tk.BOTH, padx=40, pady=20)

	def _position_tv_window(self):
		if not self._tv_window:
			return

		# Default behavior: leave it as a normal window if second monitor is unavailable.
		try:
			monitors = get_monitor_rects()
			if len(monitors) >= 2:
				left, top, right, bottom = monitors[1]
				width = max(1, right - left)
				height = max(1, bottom - top)
				self._tv_window.geometry(f"{width}x{height}+{left}+{top}")
				self._tv_window.state("zoomed")
		except Exception:
			pass

	def _update_tv_text(self):
		phase = self.phase
		round_no = len(self.sequence)

		if phase == "IDLE":
			msg = "Press START ROUND"
		elif phase == "SHOW":
			msg = "Watch carefully\nMemorize the sequence"
		elif phase == "INPUT":
			if self.green_light:
				msg = "GREEN LIGHT\nRepeat the sequence now"
			else:
				msg = "RED LIGHT\nFreeze - no movement"
		elif phase == "GAME_OVER":
			msg = "GAME OVER\nAsk staff to reset"
		else:
			msg = self.status_var.get()

		line2 = f"Round {round_no}"
		line3 = f"Strikes: {self.eye_strikes}/{MAX_EYE_STRIKES}"
		self._tv_text_var.set(f"{msg}\n\n{line2}\n{line3}")

	def _btn_label(self, led):
		return led + 1

	def _mode_btn_text(self):
		return "Switch to Live" if self._is_simulator else "Switch to Simulator"

	def _switch_connection(self):
		if self._is_simulator:
			self._mode_btn.configure(text="Connecting...", state="disabled")
			threading.Thread(target=self._connect_live, daemon=True).start()
		else:
			self._apply_connection(SIMULATOR_IP, SEND_PORT, RECV_PORT, is_simulator=True)

	def _connect_live(self):
		device_ip, send_port, recv_port = run_discovery()
		self.after(0, lambda: self._apply_connection(device_ip, send_port, recv_port, is_simulator=(device_ip == SIMULATOR_IP)))

	def _apply_connection(self, device_ip, send_port, recv_port, is_simulator):
		self.comm.close()
		time.sleep(0.1)  # Allow old recv thread to exit
		self._device_ip = device_ip
		self._send_port = send_port
		self._recv_port = recv_port
		self._is_simulator = is_simulator
		self.comm = EvilEyeComm(self.on_button_event, device_ip, send_port, recv_port)
		self._device_label_var.set(f"Device: {device_ip}:{send_port}")
		self._mode_btn.configure(text=self._mode_btn_text(), state="normal")
		mode = "simulator" if is_simulator else "live"
		self.log(f"Switched to {mode}: {device_ip}:{send_port}")

	def log(self, msg):
		self.log_text.configure(state="normal")
		self.log_text.insert(tk.END, msg + "\n")
		self.log_text.see(tk.END)
		self.log_text.configure(state="disabled")

	def reset_game(self):
		self._cancel_jobs()
		self.sequence = []
		self.input_index = 0
		self.phase = "IDLE"
		self.current_show_node = None
		self.green_light = True
		self.input_deadline_ts = 0.0
		self.eye_strikes = 0
		self.round1_grace_available = True
		self.round1_regression_count = 0
		self._last_press_ts = 0.0
		self._last_motion_ts = 0.0
		self._last_light_toggle_ts = 0.0
		self._last_red_penalty_ts = 0.0
		self.red_warning_used = False
		self._motion_seen_count.clear()
		self._motion_last_seen_ts.clear()
		self._motion_reported_active.clear()
		self.prev_pressed.clear()
		self._flash_leds.clear()
		self.round_var.set("Round: 0")
		self.phase_var.set("Phase: Idle")
		self.status_var.set("Press Start Round")
		self.log("Game reset.")
		self._render_leds()

	def start_round(self):
		if self.phase not in ("IDLE", "ROUND_OVER"):
			return
		self._start_stage(add_step=True)

	def _start_stage(self, add_step):
		if self.phase not in ("IDLE", "ROUND_OVER"):
			return

		self._cancel_jobs()
		if add_step or not self.sequence:
			next_node = (random.randint(1, NUM_CHANNELS), random.choice(WALL_PATH))
			self.sequence.append(next_node)
		self.input_index = 0
		self.current_show_node = None
		self.phase = "SHOW"
		self.phase_var.set("Phase: Show Sequence")
		self.round_var.set(f"Round: {len(self.sequence)}")
		self.status_var.set("Memorize the sequence")
		self.log(f"Round {len(self.sequence)} started. Sequence length: {len(self.sequence)}")
		self._render_leds()
		self._start_show_sequence(0, False)

	def _start_show_sequence(self, idx, is_on):
		if self.phase != "SHOW":
			return

		if idx >= len(self.sequence):
			self.current_show_node = None
			self._start_input_phase()
			return

		node = self.sequence[idx]
		self.current_show_node = node if is_on else None

		# Distractor: flash a random wrong LED briefly during the off-gap (rounds 3+)
		if not is_on and len(self.sequence) >= 3:
			wrong_chs = [c for c in range(1, NUM_CHANNELS + 1) if c != (node[0] if idx > 0 else 0)]
			wrong_leds = [l for l in WALL_PATH if l != node[1]]
			if wrong_chs and wrong_leds:
				decoy = (random.choice(wrong_chs), random.choice(wrong_leds))
				self._flash(decoy, (255, 100, 0), SHOW_OFF_MS / 1000.0 * 0.7)

		self._render_leds()

		delay = self._get_show_on_ms() if is_on else SHOW_OFF_MS
		next_idx = idx + 1 if is_on else idx
		next_on = not is_on
		self._show_job = self.after(delay, lambda: self._start_show_sequence(next_idx, next_on))

	def _start_input_phase(self):
		self.phase = "INPUT"
		self.input_index = 0
		self.green_light = True
		self.input_deadline_ts = time.time() + (self._get_input_timeout_ms() / 1000.0)
		self.eye_strikes = 0
		self._last_light_toggle_ts = time.time()
		self.red_warning_used = False
		self.phase_var.set("Phase: Input")
		self.status_var.set("Green light: enter sequence | Motion strikes: 0")
		self.log("Input phase started.")
		self._render_leds()
		self._schedule_light_toggle()
		self._schedule_timeout_check()

	def _schedule_light_toggle(self):
		if self.phase != "INPUT":
			return

		self.green_light = not self.green_light
		if self.green_light:
			self._play_cue("end")
			self.status_var.set(f"Green light: enter sequence | Motion strikes: {self.eye_strikes}/{MAX_EYE_STRIKES}")
			delay = self._get_input_green_ms()
		else:
			self._play_cue("start")
			self.status_var.set(f"Red light: freeze | Motion strikes: {self.eye_strikes}/{MAX_EYE_STRIKES}")
			delay = self._get_input_red_ms()
		self._last_light_toggle_ts = time.time()

		self._render_leds()
		self._light_job = self.after(delay, self._schedule_light_toggle)

	def _schedule_timeout_check(self):
		if self.phase != "INPUT":
			return
		if time.time() > self.input_deadline_ts:
			self._round_failed("Time out")
			return
		self._timeout_job = self.after(200, self._schedule_timeout_check)

	def _round_failed(self, reason):
		if len(self.sequence) == 1 and self.round1_grace_available:
			self.round1_grace_available = False
			self._cancel_round_jobs()
			self.phase = "ROUND_OVER"
			self.phase_var.set("Phase: Extra Chance!")
			self.status_var.set("First fail on round 1 — extra chance! Retrying in 3s...")
			self.log(f"Grace on round 1: {reason}. Retrying...")
			for ch in range(1, NUM_CHANNELS + 1):
				self._flash((ch, EYE_LED_INDEX), (255, 165, 0), 1.5)
			self._render_leds()
			self._next_round_job = self.after(3000, self._use_grace_retry)
			return
		self._cancel_round_jobs()
		self.phase = "ROUND_OVER"
		self.phase_var.set("Phase: Round Over")
		self.status_var.set(f"Failed: {reason}")
		self.log(f"Round failed: {reason}")
		for ch in range(1, NUM_CHANNELS + 1):
			self._flash((ch, EYE_LED_INDEX), (255, 0, 0), 0.8)
		self._render_leds()

	def _round_success(self):
		self._cancel_round_jobs()
		self.phase = "ROUND_OVER"
		self.phase_var.set("Phase: Round Over")
		self.status_var.set("Success! Next round starts in 5s")
		self.log("Round complete.")
		for ch in range(1, NUM_CHANNELS + 1):
			self._flash((ch, EYE_LED_INDEX), (0, 255, 80), 1.0)
		self._render_leds()
		self._next_round_job = self.after(AUTO_NEXT_ROUND_MS, self._start_next_round_if_ready)

	def _start_next_round_if_ready(self):
		self._next_round_job = None
		if self.phase == "ROUND_OVER":
			self.start_round()

	def _apply_red_move_penalty(self, channel, led):
		self._cancel_round_jobs()
		regressing_to_round1 = len(self.sequence) > 1 and len(self.sequence) - 1 == 1
		if len(self.sequence) > 1:
			self.sequence.pop()
		if regressing_to_round1:
			self.round1_regression_count += 1
			if self.round1_regression_count >= MAX_ROUND1_REGRESSIONS:
				self._trigger_game_over()
				return
		self.phase = "ROUND_OVER"
		self.phase_var.set("Phase: Penalty")
		self.round_var.set(f"Round: {len(self.sequence)}")
		self.status_var.set(f"Moved on RED (W{channel} B{self._btn_label(led)}) -> back to round {len(self.sequence)}")
		self.log(f"Red-light penalty at W{channel} B{self._btn_label(led)}. Regressed to round {len(self.sequence)}.")
		for ch in range(1, NUM_CHANNELS + 1):
			self._flash((ch, EYE_LED_INDEX), (255, 0, 0), 0.9)
		self._render_leds()
		self._next_round_job = self.after(RED_PENALTY_RESTART_MS, self._restart_after_red_penalty)

	def _restart_after_red_penalty(self):
		self._next_round_job = None
		if self.phase == "ROUND_OVER" and self.sequence:
			self._start_stage(add_step=False)

	def _use_grace_retry(self):
		self._next_round_job = None
		if self.phase == "ROUND_OVER":
			self.log("Retrying round 1 (grace).")
			self._start_stage(add_step=False)

	def _trigger_game_over(self):
		self._cancel_round_jobs()
		if self._next_round_job is not None:
			self.after_cancel(self._next_round_job)
			self._next_round_job = None
		self.phase = "GAME_OVER"
		self.phase_var.set("Phase: GAME OVER")
		self.status_var.set("GAME OVER — Press Reset to play again")
		self.log("GAME OVER! Returned to round 1 too many times.")
		for ch in range(1, NUM_CHANNELS + 1):
			self._flash((ch, EYE_LED_INDEX), (255, 0, 0), 10.0)
		self._render_leds()

	def _cancel_round_jobs(self):
		if self._show_job is not None:
			self.after_cancel(self._show_job)
			self._show_job = None
		if self._light_job is not None:
			self.after_cancel(self._light_job)
			self._light_job = None
		if self._timeout_job is not None:
			self.after_cancel(self._timeout_job)
			self._timeout_job = None

	def _cancel_jobs(self):
		self._cancel_round_jobs()
		if self._refresh_job is not None:
			self.after_cancel(self._refresh_job)
			self._refresh_job = None
		if self._next_round_job is not None:
			self.after_cancel(self._next_round_job)
			self._next_round_job = None

	# --- Difficulty scaling ---
	def _get_show_on_ms(self):
		"""Show time per node shrinks from 700ms → 300ms over 10 rounds."""
		return max(300, SHOW_ON_MS - (len(self.sequence) - 1) * 40)

	def _get_input_green_ms(self):
		"""Green-light window shrinks from 3400ms → 1800ms over rounds."""
		return max(1800, INPUT_GREEN_MS - (len(self.sequence) - 1) * 85)

	def _get_input_red_ms(self):
		"""Red-light freeze grows from 1400ms → 2400ms over 10 rounds."""
		return min(2400, INPUT_RED_MS + (len(self.sequence) - 1) * 100)

	def _get_input_timeout_ms(self):
		"""Total input budget shrinks from 20s → 10s over 10 rounds."""
		return max(10000, INPUT_TIMEOUT_MS - (len(self.sequence) - 1) * 1000)

	def _flash(self, node, color, sec):
		self._flash_leds[node] = (color, time.time() + sec)

	def _eye_color(self):
		if self.phase == "SHOW":
			return (255, 180, 0)
		if self.phase == "INPUT":
			return (0, 255, 0) if self.green_light else (255, 0, 0)
		if self.phase == "ROUND_OVER":
			return (120, 120, 120)
		if self.phase == "GAME_OVER":
			return (255, 0, 0)
		return (0, 0, 120)

	def _render_leds(self):
		now = time.time()
		for key, (_, until_ts) in list(self._flash_leds.items()):
			if now >= until_ts:
				del self._flash_leds[key]

		leds = {}
		eye_rgb = self._eye_color()
		for ch in range(1, NUM_CHANNELS + 1):
			leds[(ch, EYE_LED_INDEX)] = eye_rgb

		if self.phase == "SHOW" and self.current_show_node:
			leds[self.current_show_node] = (0, 210, 255)

		for node, (color, _until_ts) in self._flash_leds.items():
			leds[node] = color

		self._last_led_states = leds
		self.comm.send_led_frame(self._last_led_states)

	def _schedule_led_refresh(self):
		if self._last_led_states:
			self.comm.send_led_frame(self._last_led_states)
		self._refresh_job = self.after(LED_REFRESH_MS, self._schedule_led_refresh)

	def _apply_motion_penalty(self, channel):
		self.eye_strikes += 1
		self.input_deadline_ts = max(time.time() + 1.0, self.input_deadline_ts - EYE_PENALTY_SECONDS)
		self._flash((channel, EYE_LED_INDEX), (255, 80, 80), 0.7)
		remaining = max(0.0, self.input_deadline_ts - time.time())
		self.log(
			f"Motion detected on eye W{channel}. Penalty {self.eye_strikes}/{MAX_EYE_STRIKES}, "
			f"-{EYE_PENALTY_SECONDS:.1f}s (remaining {remaining:.1f}s)"
		)
		if self.eye_strikes >= MAX_EYE_STRIKES:
			self._render_leds()
			self._round_failed("Too many motion penalties")
			return

		light_text = "Green light: enter sequence" if self.green_light else "Red light: freeze"
		self.status_var.set(f"{light_text} | Motion strikes: {self.eye_strikes}/{MAX_EYE_STRIKES}")
		self._render_leds()

	def _handle_rising_press(self, channel, led):
		if self.phase != "INPUT":
			return

		now = time.time()
		if (now - self._last_press_ts) < (DETECTION_COOLDOWN_MS / 1000.0):
			return

		if led == EYE_LED_INDEX:
			if (now - self._last_motion_ts) < (MOTION_COOLDOWN_MS / 1000.0):
				return
			self._last_motion_ts = now
			self._last_press_ts = now
			self._apply_motion_penalty(channel)
			return

		self._play_beep_for_round()

		if not self.green_light:
			if (now - self._last_light_toggle_ts) < (RED_LIGHT_GRACE_MS / 1000.0):
				self.log(f"Ignored W{channel} B{self._btn_label(led)} during red-light grace window")
				return
			if not self.red_warning_used:
				self.red_warning_used = True
				self._last_press_ts = now
				self._flash((channel, led), (255, 0, 0), 0.6)
				self.status_var.set(
					f"Warning: moved on RED once (next red move penalizes) | Motion strikes: {self.eye_strikes}/{MAX_EYE_STRIKES}"
				)
				self.log(f"Warning only: RED movement at W{channel} B{self._btn_label(led)}")
				self._render_leds()
				return
			if (now - self._last_red_penalty_ts) < (RED_MOVE_COOLDOWN_MS / 1000.0):
				self.log(f"Ignored repeated RED movement at W{channel} B{self._btn_label(led)} (cooldown)")
				return
			self._last_red_penalty_ts = now
			self._last_press_ts = now
			self._apply_red_move_penalty(channel, led)
			return

		if led not in WALL_PATH:
			self._round_failed(f"Invalid button {led}")
			return

		expected = self.sequence[self.input_index]
		if (channel, led) != expected:
			self._last_press_ts = now
			self._flash((channel, led), (255, 0, 0), 0.6)
			self._render_leds()
			self._round_failed(
				f"Wrong button. Expected W{expected[0]} B{self._btn_label(expected[1])}"
			)
			return

		self._last_press_ts = now
		self._flash((channel, led), (0, 255, 120), 0.5)
		self.log(f"Correct: W{channel} B{self._btn_label(led)}")
		self.input_index += 1

		if self.input_index >= len(self.sequence):
			self._round_success()
		else:
			remaining = len(self.sequence) - self.input_index
			self.status_var.set(
				f"Green light: {remaining} step(s) left | Motion strikes: {self.eye_strikes}/{MAX_EYE_STRIKES}"
			)
		self._render_leds()

	def on_button_event(self, data, addr):
		if len(data) != TRIGGER_PACKET_LEN:
			return
		if data[0] != 0x88:
			return
		if (sum(data[:-1]) & 0xFF) != data[-1]:
			return

		pressed = set()
		for ch in range(1, NUM_CHANNELS + 1):
			base = 2 + (ch - 1) * 171
			for idx in range(LEDS_PER_CHANNEL):
				if data[base + 1 + idx] == 0xCC:
					pressed.add((ch, idx))

		now = time.time()

		# Motion (eye LED index): packet-based trigger with active-state gating.
		for ch in range(1, NUM_CHANNELS + 1):
			node = (ch, EYE_LED_INDEX)
			if node in pressed:
				self._motion_last_seen_ts[ch] = now
				self._motion_seen_count[ch] = self._motion_seen_count.get(ch, 0) + 1
				if ch not in self._motion_reported_active and self._motion_seen_count[ch] >= MOTION_CONFIRM_PACKETS:
					self._motion_reported_active.add(ch)
					self._handle_rising_press(ch, EYE_LED_INDEX)
			else:
				last_seen = self._motion_last_seen_ts.get(ch, 0.0)
				if (now - last_seen) >= (MOTION_ACTIVE_GAP_MS / 1000.0):
					self._motion_seen_count.pop(ch, None)
					self._motion_last_seen_ts.pop(ch, None)
					self._motion_reported_active.discard(ch)

		# Regular wall buttons still use rising-edge detection.
		rising = {(ch, led) for (ch, led) in (pressed - self.prev_pressed) if led != 0}
		self.prev_pressed = pressed

		for ch, led in sorted(rising):
			self._handle_rising_press(ch, led)

	def on_close(self):
		self._cancel_jobs()
		self.comm.close()
		if self._tv_window is not None:
			try:
				self._tv_window.destroy()
			except Exception:
				pass
		self.destroy()

if __name__ == "__main__":
	print("[Discovery] Scanning LAN for Evil Eye hardware...")
	device_ip, send_port, recv_port = run_discovery()
	print(f"[Discovery] Connecting to {device_ip}:{send_port} (recv:{recv_port})")
	EvilEyeGame(device_ip, send_port, recv_port).mainloop()
