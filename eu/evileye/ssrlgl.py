import socket
import threading
import random
import time
import tkinter as tk
from tkinter import ttk

# --- Protocol/Simulator Settings ---
NUM_CHANNELS = 4
LEDS_PER_CHANNEL = 11
SIMULATOR_IP = '127.0.0.1'
SEND_PORT = 4626  # To simulator (light commands)
RECV_PORT = 7800  # From simulator (button events)
FRAME_DATA_LEN = LEDS_PER_CHANNEL * NUM_CHANNELS * 3
TRIGGER_PACKET_LEN = 687

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
LED_REFRESH_MS = 220
EYE_PENALTY_SECONDS = 2.5
MAX_EYE_STRIKES = 2
AUTO_NEXT_ROUND_MS = 10000
RED_PENALTY_RESTART_MS = 2000

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

		self.comm = EvilEyeComm(self.on_button_event, device_ip, send_port, recv_port)
		self._device_label = f"{device_ip}:{send_port}"
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

		self._last_led_states = {}
		self._flash_leds = {}

		self._show_job = None
		self._light_job = None
		self._timeout_job = None
		self._refresh_job = None
		self._next_round_job = None

		self._build_ui()
		self._schedule_led_refresh()
		self.protocol("WM_DELETE_WINDOW", self.on_close)

	def _build_ui(self):
		top = tk.Frame(self, bg="#1f1f1f")
		top.pack(fill=tk.X)

		ttk.Button(top, text="Start Round", command=self.start_round).pack(side=tk.LEFT, padx=10, pady=10)
		ttk.Button(top, text="Reset", command=self.reset_game).pack(side=tk.LEFT, padx=6, pady=10)
		tk.Label(top, textvariable=self.round_var, bg="#1f1f1f", fg="#d8d8d8").pack(side=tk.LEFT, padx=14)
		tk.Label(top, textvariable=self.phase_var).pack(side=tk.LEFT, padx=14)
		tk.Label(top, textvariable=self.status_var).pack(side=tk.LEFT, padx=14)
		tk.Label(top, text=f"Device: {self._device_label}", bg="#1f1f1f", fg="#888").pack(side=tk.RIGHT, padx=10)

		self.log_text = tk.Text(self, height=20, state="disabled", bg="#111", fg="#00ff8c")
		self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

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
			self.status_var.set(f"Green light: enter sequence | Motion strikes: {self.eye_strikes}/{MAX_EYE_STRIKES}")
			delay = self._get_input_green_ms()
		else:
			self.status_var.set(f"Red light: freeze | Motion strikes: {self.eye_strikes}/{MAX_EYE_STRIKES}")
			delay = self._get_input_red_ms()

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
				self._flash((ch, 0), (255, 165, 0), 1.5)
			self._render_leds()
			self._next_round_job = self.after(3000, self._use_grace_retry)
			return
		self._cancel_round_jobs()
		self.phase = "ROUND_OVER"
		self.phase_var.set("Phase: Round Over")
		self.status_var.set(f"Failed: {reason}")
		self.log(f"Round failed: {reason}")
		for ch in range(1, NUM_CHANNELS + 1):
			self._flash((ch, 0), (255, 0, 0), 0.8)
		self._render_leds()

	def _round_success(self):
		self._cancel_round_jobs()
		self.phase = "ROUND_OVER"
		self.phase_var.set("Phase: Round Over")
		self.status_var.set("Success! Next round starts in 10s")
		self.log("Round complete.")
		for ch in range(1, NUM_CHANNELS + 1):
			self._flash((ch, 0), (0, 255, 80), 1.0)
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
			if self.round1_regression_count >= 3:
				self._trigger_game_over()
				return
		self.phase = "ROUND_OVER"
		self.phase_var.set("Phase: Penalty")
		self.round_var.set(f"Round: {len(self.sequence)}")
		self.status_var.set(f"Moved on RED (W{channel} B{led}) -> back to round {len(self.sequence)}")
		self.log(f"Red-light penalty at W{channel} B{led}. Regressed to round {len(self.sequence)}.")
		for ch in range(1, NUM_CHANNELS + 1):
			self._flash((ch, 0), (255, 0, 0), 0.9)
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
			self._flash((ch, 0), (255, 0, 0), 10.0)
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
		"""Green-light window shrinks from 2300ms → 1100ms over 10 rounds."""
		return max(1100, INPUT_GREEN_MS - (len(self.sequence) - 1) * 120)

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
			leds[(ch, 0)] = eye_rgb

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
		self._flash((channel, 0), (255, 80, 80), 0.7)
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

		if led == 0:
			self._apply_motion_penalty(channel)
			return

		if not self.green_light:
			self._apply_red_move_penalty(channel, led)
			return

		if led not in WALL_PATH:
			self._round_failed(f"Invalid button {led}")
			return

		expected = self.sequence[self.input_index]
		if (channel, led) != expected:
			self._flash((channel, led), (255, 0, 0), 0.6)
			self._render_leds()
			self._round_failed(f"Wrong button. Expected W{expected[0]} B{expected[1]}")
			return

		self._flash((channel, led), (0, 255, 120), 0.5)
		self.log(f"Correct: W{channel} B{led}")
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

		rising = pressed - self.prev_pressed
		self.prev_pressed = pressed

		for ch, led in sorted(rising):
			self._handle_rising_press(ch, led)

	def on_close(self):
		self._cancel_jobs()
		self.comm.close()
		self.destroy()

if __name__ == "__main__":
	print("[Discovery] Scanning LAN for Evil Eye hardware...")
	device_ip, send_port, recv_port = run_discovery()
	print(f"[Discovery] Connecting to {device_ip}:{send_port} (recv:{recv_port})")
	EvilEyeGame(device_ip, send_port, recv_port).mainloop()
