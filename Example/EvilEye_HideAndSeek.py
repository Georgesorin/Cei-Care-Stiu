"""
Evil Eye – Hide & Seek Game

Game flow (one round):
  1. GREEN  (10 s)  – 2 random walls each show 1 green button. Press both for +1 each.
                      Miss a button when time runs out → -1 each.
  2. RED    ( 3 s)  – One wall goes fully red (the Evil Eye). Hide! Any button press
                      on that wall → -1 (caught).
  3. HIDDEN ( 5 s)  – Lights off. Stay hidden.
  4. FLASH  ( 1 s)  – All LEDs white, then restart.

Run with the Simulator open:
  python EvilEye_HideAndSeek.py
"""

import json
import os
import queue
import random
import socket
import threading
import time
import tkinter as tk

# ── Game timing (seconds) ────────────────────────────────────────────────────
GREEN_DURATION  = 5.0   # time to find and press the green buttons
RED_DURATION    =  3.0   # time to hide from the evil eye
HIDDEN_DURATION =  5.0   # stay hidden
FLASH_DURATION  =  1.0   # end-of-round flash

# ── Port / IP overrides ───────────────────────────────────────────────────────
# Set to None to auto-detect from eye_ctrl_config.json; set a number to override.
# Simulator default:  Port IN (light commands) = 9999,  Port OUT (button events) = 9998
# Real hardware:      Port IN (light commands) = 9998,  Port OUT (button events) = 9999
DEVICE_IP   = None   # e.g. "192.168.1.7" or "255.255.255.255"
SEND_PORT   = None   # port the Simulator/device listens on  (matches Simulator "Port IN")
RECV_PORT   = None   # port we listen on for button events   (matches Simulator "Port OUT")
IFACE_INDEX = 1      # auto-select this interface index for discovery (None = ask at startup)

# ── Config loading ────────────────────────────────────────────────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_CFG_PATH = os.path.join(_THIS_DIR, "..", "EvilEye", "eye_ctrl_config.json")

def _load_config():
    # eye_ctrl_config.json naming (from hardware perspective):
    #   "udp_port"       = port where hardware SENDS button events  → we LISTEN here
    #   "receiver_port"  = port where hardware RECEIVES light data  → we SEND here
    defaults = {"device_ip": "169.254.182.11", "udp_port": 4626,
                "receiver_port": 7800, "polling_rate_ms": 100}
    try:
        with open(_CFG_PATH, encoding="utf-8") as f:
            defaults.update(json.load(f))
    except Exception:
        pass
    if DEVICE_IP is not None:
        defaults["device_ip"] = DEVICE_IP
    return defaults

# ── Protocol constants ────────────────────────────────────────────────────────
NUM_CHANNELS     = 4
LEDS_PER_CHANNEL = 11   # 0 = Eye, 1-10 = Buttons
FRAME_DATA_LEN   = NUM_CHANNELS * LEDS_PER_CHANNEL * 3   # 132 bytes

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

# ── Protocol helpers ──────────────────────────────────────────────────────────
def _checksum(data):
    idx = sum(data) & 0xFF
    return PASSWORD_ARRAY[idx]

def _build_command(data_id, msg_loc, payload, seq):
    internal = bytes([
        0x02, 0x00, 0x00,
        (data_id >> 8) & 0xFF, data_id & 0xFF,
        (msg_loc >> 8) & 0xFF, msg_loc & 0xFF,
        (len(payload) >> 8) & 0xFF, len(payload) & 0xFF,
    ]) + payload
    hdr = bytes([0x75, random.randint(0, 127), random.randint(0, 127),
                 (len(internal) >> 8) & 0xFF, len(internal) & 0xFF])
    pkt = bytearray(hdr + internal)
    pkt[10] = (seq >> 8) & 0xFF
    pkt[11] = seq & 0xFF
    pkt.append(_checksum(pkt))
    return bytes(pkt)

def _build_start(seq):
    pkt = bytearray([0x75, random.randint(0, 127), random.randint(0, 127),
                     0x00, 0x08, 0x02, 0x00, 0x00, 0x33, 0x44,
                     (seq >> 8) & 0xFF, seq & 0xFF, 0x00, 0x00])
    pkt.append(_checksum(pkt))
    return bytes(pkt)

def _build_end(seq):
    pkt = bytearray([0x75, random.randint(0, 127), random.randint(0, 127),
                     0x00, 0x08, 0x02, 0x00, 0x00, 0x55, 0x66,
                     (seq >> 8) & 0xFF, seq & 0xFF, 0x00, 0x00])
    pkt.append(_checksum(pkt))
    return bytes(pkt)

def _build_fff0(seq):
    payload = bytearray()
    for _ in range(NUM_CHANNELS):
        payload += bytes([(LEDS_PER_CHANNEL >> 8) & 0xFF, LEDS_PER_CHANNEL & 0xFF])
    return _build_command(0x8877, 0xFFF0, bytes(payload), seq)

def _build_frame(led_states):
    frame = bytearray(FRAME_DATA_LEN)
    for (ch, led), (r, g, b) in led_states.items():
        ci = ch - 1
        if 0 <= ci < NUM_CHANNELS and 0 <= led < LEDS_PER_CHANNEL:
            frame[led * 12 + ci]     = g
            frame[led * 12 + 4 + ci] = r
            frame[led * 12 + 8 + ci] = b
    return bytes(frame)

# ── Light service ─────────────────────────────────────────────────────────────
class LightService:
    """Minimal sender + receiver — no tkinter dependency."""

    def __init__(self, device_ip, send_port, recv_port, poll_ms=100):
        self._ip        = device_ip
        self._sport     = send_port
        self._rport     = recv_port
        self._poll_ms   = poll_ms
        self._seq       = 0
        self._states    = {}
        self._lock      = threading.Lock()
        self._send_q    = queue.Queue(maxsize=4)
        self._running   = True
        self._prev_btn  = {}

        self.on_button_state = None  # fn(ch, led, is_trig, is_disc)

        threading.Thread(target=self._sender_loop, daemon=True).start()
        threading.Thread(target=self._poll_loop,   daemon=True).start()
        threading.Thread(target=self._recv_loop,   daemon=True).start()

    def _next_seq(self):
        with self._lock:
            self._seq = (self._seq + 1) & 0xFFFF
            return self._seq

    def _send_sequence(self, frame_data):
        seq = self._next_seq()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            targets = [(self._ip, self._sport)]
            if self._ip not in ("127.0.0.1", "0.0.0.0"):
                targets.append(("127.0.0.1", self._sport))
            packets = [
                _build_start(seq),
                _build_fff0(seq),
                _build_command(0x8877, 0x0000, frame_data, seq),
                _build_end(seq),
            ]
            for pkt in packets:
                for ep in targets:
                    sock.sendto(pkt, ep)
                time.sleep(0.008)
            sock.close()
        except Exception:
            pass

    def _sender_loop(self):
        while self._running:
            try:
                item = self._send_q.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                break
            self._send_sequence(item)

    def _enqueue(self):
        with self._lock:
            states = dict(self._states)
        try:
            self._send_q.put_nowait(_build_frame(states))
        except queue.Full:
            pass

    def _poll_loop(self):
        while self._running:
            self._enqueue()
            time.sleep(self._poll_ms / 1000.0)

    def _recv_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(0.5)
        try:
            sock.bind(("0.0.0.0", self._rport))
        except Exception:
            return
        while self._running:
            try:
                data, _ = sock.recvfrom(1024)
            except socket.timeout:
                continue
            except Exception:
                break
            if len(data) != 687 or data[0] != 0x88:
                continue
            if sum(data[:-1]) & 0xFF != data[-1]:
                continue
            for ch in range(1, NUM_CHANNELS + 1):
                base = 2 + (ch - 1) * 171
                for idx in range(LEDS_PER_CHANNEL):
                    val     = data[base + 1 + idx]
                    is_trig = val == 0xCC
                    is_disc = val == 0x10
                    prev    = self._prev_btn.get((ch, idx))
                    new     = (is_trig, is_disc)
                    if prev != new:
                        self._prev_btn[(ch, idx)] = new
                        if self.on_button_state:
                            self.on_button_state(ch, idx, is_trig, is_disc)
        sock.close()

    # ── Public LED API ────────────────────────────────────────────────────────
    def set_led(self, ch, led, r, g, b):
        with self._lock:
            self._states[(ch, led)] = (r, g, b)
        self._enqueue()

    def set_all(self, r, g, b):
        with self._lock:
            for c in range(1, NUM_CHANNELS + 1):
                for l in range(LEDS_PER_CHANNEL):
                    self._states[(c, l)] = (r, g, b)
        self._enqueue()

    def all_off(self):
        self.set_all(0, 0, 0)

    def stop(self):
        self._running = False
        try:
            self._send_q.put_nowait(None)
        except queue.Full:
            pass


# ── Phase constants ───────────────────────────────────────────────────────────
STATE_GREEN  = "GREEN"
STATE_RED    = "RED"
STATE_HIDDEN = "HIDDEN"
STATE_FLASH  = "FLASH"
STATE_IDLE   = "IDLE"


# ── Game logic ────────────────────────────────────────────────────────────────
class HideAndSeekGame:

    def __init__(self, service: LightService):
        self.service = service

        self.score         = 0
        self.state         = STATE_IDLE
        self.state_end_at  = 0.0
        self.status_msg    = "Starting…"
        self.red_wall      = None

        self._green_buttons    = {}
        self._pressed_in_green = set()
        self._lock             = threading.Lock()
        self._running          = True

        self.service.on_button_state = self._on_button_state

    def _on_button_state(self, ch, led, is_trig, is_disc):
        if not is_trig:
            return
        with self._lock:
            if self.state == STATE_GREEN:
                if ch in self._green_buttons and self._green_buttons[ch] == led:
                    if (ch, led) not in self._pressed_in_green:
                        self._pressed_in_green.add((ch, led))
                        self.score += 1
                        self.service.set_led(ch, led, 0, 0, 0)
            elif self.state == STATE_RED:
                if ch == self.red_wall:
                    self.score -= 1

    def run(self):
        while self._running:
            self._run_round()

    def stop(self):
        self._running = False

    def _run_round(self):
        # Phase 1 – GREEN
        walls = random.sample([1, 2, 3, 4], 2)
        green_buttons = {w: random.randint(1, 10) for w in walls}

        with self._lock:
            self._green_buttons    = dict(green_buttons)
            self._pressed_in_green = set()

        self.service.all_off()
        for ch, led in green_buttons.items():
            self.service.set_led(ch, led, 0, 255, 0)

        with self._lock:
            self.state        = STATE_GREEN
            self.state_end_at = time.time() + GREEN_DURATION
            self.status_msg   = f"Find the green buttons! Wall {walls[0]} & Wall {walls[1]}"

        time.sleep(GREEN_DURATION)

        with self._lock:
            for ch, led in green_buttons.items():
                if (ch, led) not in self._pressed_in_green:
                    self.score -= 1

        # Phase 2 – RED
        red_wall = random.choice([1, 2, 3, 4])
        with self._lock:
            self.red_wall = red_wall

        self.service.all_off()
        for led in range(LEDS_PER_CHANNEL):
            self.service.set_led(red_wall, led, 255, 0, 0)

        with self._lock:
            self.state        = STATE_RED
            self.state_end_at = time.time() + RED_DURATION
            self.status_msg   = f"HIDE! The Eye is on Wall {red_wall}!"

        time.sleep(RED_DURATION)

        # Phase 3 – HIDDEN
        self.service.all_off()
        with self._lock:
            self.state        = STATE_HIDDEN
            self.state_end_at = time.time() + HIDDEN_DURATION
            self.status_msg   = "Stay hidden…"

        time.sleep(HIDDEN_DURATION)

        # Phase 4 – FLASH
        if self.score > 0:
            flash_color = (0, 255, 0)    # green – positive score
        elif self.score < 0:
            flash_color = (255, 0, 0)    # red   – negative score
        else:
            flash_color = (255, 255, 255) # white – zero

        with self._lock:
            self.state        = STATE_FLASH
            self.state_end_at = time.time() + FLASH_DURATION
            self.status_msg   = "Next round incoming!"

        self.service.set_all(*flash_color)
        time.sleep(FLASH_DURATION)
        self.service.all_off()
        time.sleep(0.2)


# ── UI ────────────────────────────────────────────────────────────────────────
class GameUI:
    PHASE_COLORS = {
        STATE_GREEN:  "#00cc44",
        STATE_RED:    "#ff3333",
        STATE_HIDDEN: "#888888",
        STATE_FLASH:  "#ffffff",  # overridden dynamically in _tick
        STATE_IDLE:   "#555555",
    }
    PHASE_LABELS = {
        STATE_GREEN:  "FIND THE BUTTONS",
        STATE_RED:    "HIDE FROM THE EYE",
        STATE_HIDDEN: "STAY HIDDEN",
        STATE_FLASH:  "ROUND OVER",
        STATE_IDLE:   "STARTING…",
    }

    def __init__(self, game: HideAndSeekGame):
        self.game = game
        self.root = tk.Tk()
        self.root.title("Evil Eye – Hide & Seek")
        self.root.configure(bg="#111111")
        self.root.resizable(False, False)

        self._phase_label = tk.Label(
            self.root, text="STARTING…",
            font=("Consolas", 28, "bold"),
            bg="#111111", fg="#555555", width=22, anchor="center",
        )
        self._phase_label.grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 4))

        self._timer_label = tk.Label(
            self.root, text="",
            font=("Consolas", 16),
            bg="#111111", fg="#aaaaaa",
        )
        self._timer_label.grid(row=1, column=0, columnspan=2, pady=(0, 6))

        self._status_label = tk.Label(
            self.root, text="",
            font=("Consolas", 11),
            bg="#111111", fg="#888888", wraplength=700,
        )
        self._status_label.grid(row=2, column=0, columnspan=2, padx=20, pady=(0, 8))

        tk.Label(self.root, text="SCORE", font=("Consolas", 10, "bold"),
                 bg="#111111", fg="#555555").grid(
            row=3, column=0, padx=(40, 4), pady=(0, 20), sticky="e")

        self._score_label = tk.Label(
            self.root, text="0",
            font=("Consolas", 32, "bold"),
            bg="#111111", fg="#00ff88",
        )
        self._score_label.grid(row=3, column=1, padx=(4, 40), pady=(0, 20), sticky="w")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._tick()

    def _tick(self):
        state = self.game.state
        if state == STATE_FLASH:
            flash_fg = "#00ff00" if self.game.score > 0 else "#ff3333" if self.game.score < 0 else "#ffffff"
        else:
            flash_fg = self.PHASE_COLORS[STATE_FLASH]
        colors = {**self.PHASE_COLORS, STATE_FLASH: flash_fg}
        self._phase_label.config(
            text=self.PHASE_LABELS.get(state, state),
            fg=colors.get(state, "#555555"),
        )
        self._status_label.config(text=self.game.status_msg)
        self._score_label.config(text=str(self.game.score))
        remaining = max(0.0, self.game.state_end_at - time.time())
        self._timer_label.config(text=f"{remaining:.1f}s" if remaining > 0 else "")
        self.root.after(100, self._tick)

    def _on_close(self):
        self.game.stop()
        self.game.service.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ── Discovery ─────────────────────────────────────────────────────────────────
calc_sum = _checksum   # alias used by the discovery helpers below

def get_local_interfaces():
    """Return list of (iface_name, ip, broadcast) for all active IPv4 interfaces."""
    try:
        import psutil
        results = []
        for iface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET and addr.address not in ("127.0.0.1",):
                    bcast = addr.broadcast or "255.255.255.255"
                    results.append((iface, addr.address, bcast))
        return results
    except Exception:
        return []

def build_discovery_packet():
    rand1, rand2 = random.randint(0, 127), random.randint(0, 127)
    payload = bytearray([0x0A, 0x02, *b"KX-HC04", 0x03, 0x00, 0x00, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x14])
    pkt = bytearray([0x67, rand1, rand2, len(payload)]) + payload
    pkt.append(calc_sum(pkt))
    return pkt, rand1, rand2

def run_discovery_flow():
    interfaces = get_local_interfaces()
    if not interfaces:
        print("No active network interfaces found.")
        return None
    print("\n--- Network Selection ---")
    for i, (iface, ip, bcast) in enumerate(interfaces):
        print(f"[{i}] {iface} - {ip}")
    if IFACE_INDEX is not None:
        try:
            sel = interfaces[IFACE_INDEX]
            print(f"Auto-selected [{IFACE_INDEX}]")
        except IndexError:
            sel = interfaces[0]
            print(f"IFACE_INDEX {IFACE_INDEX} out of range, defaulting to [0].")
    else:
        try:
            choice = int(input("\nSelect interface number: "))
            sel = interfaces[choice]
        except Exception:
            sel = interfaces[0]
            print("Invalid choice, defaulting to [0].")
    print(f"Using {sel[0]} ({sel[1]})")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try: sock.bind((sel[1], 7800))
    except: pass

    pkt, r1, r2 = build_discovery_packet()
    try: sock.sendto(pkt, (sel[2], 4626))
    except: return None

    print("Listening for devices...")
    sock.settimeout(0.5)
    end_time = time.time() + 3
    devices = []
    while time.time() < end_time:
        try:
            data, addr = sock.recvfrom(1024)
            if len(data) >= 30 and data[0] == 0x68 and data[1] == r1 and data[2] == r2:
                if addr[0] not in [d['ip'] for d in devices]:
                    model = data[6:13].decode(errors='ignore').strip('\x00')
                    devices.append({'ip': addr[0], 'model': model})
                    print(f"Found {model} at {addr[0]}")
        except socket.timeout: continue
        except: pass
    sock.close()
    if devices:
        print(f"Targeting {devices[0]['ip']}\n")
        return devices[0]['ip']
    print("No devices found, using default config.\n")
    return None


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    cfg = _load_config()
    # Run discovery unless DEVICE_IP is already set at the top of the file
    if DEVICE_IP is None:
        discovered = run_discovery_flow()
        if discovered:
            cfg["device_ip"] = discovered
    # receiver_port = where hardware/Simulator RECEIVES light  → we SEND there
    # udp_port      = where hardware/Simulator SENDS buttons   → we LISTEN there
    send_port = SEND_PORT if SEND_PORT is not None else cfg["receiver_port"]
    recv_port = RECV_PORT if RECV_PORT is not None else cfg["udp_port"]
    print(f"[config] device={cfg['device_ip']}  send->{send_port}  recv<-{recv_port}")
    service = LightService(
        device_ip = cfg["device_ip"],
        send_port = send_port,
        recv_port = recv_port,
        poll_ms   = cfg.get("polling_rate_ms", 100),
    )
    game = HideAndSeekGame(service)
    threading.Thread(target=game.run, daemon=True).start()

    ui = GameUI(game)
    ui.run()
