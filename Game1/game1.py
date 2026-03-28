#make a simple game where blocks are falling down the screen and the player has to catch them with a basket
import socket
import struct
import time
import threading
import random
import copy
import psutil
import os
import json

# --- Configuration ---
_CFG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Matrix", "matrix_sim_config.json")

def _load_config():
    defaults = {
        "device_ip": "255.255.255.255",
        "send_port": 7271,
        "recv_port": 7270,
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
UDP_SEND_PORT = CONFIG.get("send_port", 7271)
UDP_LISTEN_PORT = CONFIG.get("recv_port", 7270)

# --- Matrix Constants ---
NUM_CHANNELS = 8
LEDS_PER_CHANNEL = 64
FRAME_DATA_LENGTH = NUM_CHANNELS * LEDS_PER_CHANNEL * 3

# Board Area
BOARD_WIDTH = 16
BOARD_HEIGHT = 32

# --- Colors (R, G, B) ---
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)

class FallingBlocksGame:
    def __init__(self):
        self.board = [[BLACK for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]
        self.players = []
        
        # Audio
        self.sound = SoundManager()
        
        self.running = True
        self.state = 'LOBBY' # LOBBY, STARTUP, PLAYING, GAMEOVER
        self.startup_step = 0
        self.startup_timer = time.time()
        
        self.base_fall_speed = 1.0 
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
        
        
        # Input State for Visualization & Logic
        self.button_states = [False] * 64
        self.prev_button_states = [False] * 64
        # Key: (player_id, action_str) -> Value: next_trigger_time
        self.input_timers = {} 

    def tick(self):
        if self.game_over:
            return
        self.frame_count += 1

        # Handle input
        self.process_inputs()

        # Spawn new blocks
        if random.randint(1, max(10, 30 - self.score // 5)) == 1:  # Spawn faster as score increases
            x = random.randint(0, BOARD_WIDTH - 1)
            self.blocks.append([x, 0])

        # Move blocks down
        if self.frame_count % self.speed == 0:
            for block in self.blocks[:]:
                block[1] += 1
                if block[1] >= BOARD_HEIGHT:
                    self.blocks.remove(block)
                    self.missed += 1
                    if self.missed >= 10:
                        self.game_over = True
                elif block[1] == BOARD_HEIGHT - 1 and self.basket_x <= block[0] < self.basket_x + self.basket_width:
                    self.blocks.remove(block)
                    self.score += 1
                    if self.score % 10 == 0 and self.speed > 1:
                        self.speed -= 1  # Increase speed every 10 points

    def process_inputs(self):
        # Simple: use left and right buttons for player 0
        left_pressed = self.button_states[31]  # LED 31 is left for player 0
        right_pressed = self.button_states[29]  # LED 29 is right for player 0

        if self.game_over:
            # Any button press to restart
            if any(self.button_states) and not any(self.prev_button_states):
                self.reset_game()
        else:
            if left_pressed and not self.prev_button_states[31] and self.basket_x > 0:
                self.basket_x -= 1
            if right_pressed and not self.prev_button_states[29] and self.basket_x + self.basket_width < BOARD_WIDTH:
                self.basket_x += 1

        self.prev_button_states = self.button_states[:]

    def reset_game(self):
        self.board = [[BLACK for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]
        self.basket_x = BOARD_WIDTH // 2 - 2
        self.blocks = []
        self.score = 0
        self.missed = 0
        self.speed = 1
        self.frame_count = 0
        self.game_over = False

    def render(self):
        buffer = bytearray(FRAME_DATA_LENGTH)

        # Clear board
        self.board = [[BLACK for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]

        if self.game_over:
            # Game over screen: flash red
            color = RED if (self.frame_count // 10) % 2 == 0 else BLACK
            for y in range(BOARD_HEIGHT):
                for x in range(BOARD_WIDTH):
                    self.board[y][x] = color
        else:
            # Draw basket
            for i in range(self.basket_width):
                if 0 <= self.basket_x + i < BOARD_WIDTH:
                    self.board[BOARD_HEIGHT - 1][self.basket_x + i] = WHITE

            # Draw blocks
            for x, y in self.blocks:
                if 0 <= y < BOARD_HEIGHT and 0 <= x < BOARD_WIDTH:
                    self.board[y][x] = RED

            # Draw score (top row: green for score)
            for i in range(min(self.score, BOARD_WIDTH)):
                self.board[0][i] = GREEN

            # Draw missed (second row: red for missed)
            for i in range(min(self.missed, BOARD_WIDTH)):
                self.board[1][i] = RED

        # Convert board to buffer
        for y in range(BOARD_HEIGHT):
            for x in range(BOARD_WIDTH):
                self.set_led(buffer, x, y, self.board[y][x])

        return buffer

    def set_led(self, buffer, x, y, color):
        if x < 0 or x >= 16: return
        channel = y // 4
        if channel >= 8: return
        row_in_channel = y % 4
        if row_in_channel % 2 == 0: led_index = row_in_channel * 16 + x
        else: led_index = row_in_channel * 16 + (15 - x)
        block_size = NUM_CHANNELS * 3
        offset = led_index * block_size + channel
        if offset + NUM_CHANNELS*2 < len(buffer):
            buffer[offset] = color[1] # GREEN (Swap for hardware)
            buffer[offset + NUM_CHANNELS] = color[0] # RED (Swap for hardware)
            buffer[offset + NUM_CHANNELS*2] = color[2]

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
        start_packet.append(0x0E) # Force Checksum
        start_packet.append(0x00) 
        try: 
            self.sock_send.sendto(start_packet, (target_ip, port))
            self.sock_send.sendto(start_packet, ("127.0.0.1", port))
        except: pass

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
        except: pass
        
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
            except: pass
            
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
        except: pass

    def recv_loop(self):
        while self.running:
            try:
                data, _ = self.sock_recv.recvfrom(2048)
                if len(data) >= 1373 and data[0] == 0x88:
                    offset = 2 + (7 * 171) + 1 
                    ch8_data = data[offset : offset + 170]
                    for led_idx, val in enumerate(ch8_data):
                        if led_idx >= 64: break
                        is_pressed = (val == 0xCC)
                        
                        # Sync state to game active list
                        # Logic now handled in Game.tick() -> process_inputs()
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
    game = FallingBlocksGame()
    network = NetworkManager(game)

    # Start threads
    threading.Thread(target=network.send_loop, daemon=True).start()
    threading.Thread(target=network.recv_loop, daemon=True).start()

    # Game loop
    while game.running:
        game.tick()
        time.sleep(0.1)  # Update every 100ms