import json
import os
import tkinter as tk
import tkinter.font as tkfont
import ctypes
from tkinter import ttk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCORE_FILE = os.path.join(BASE_DIR, "team_scores.json")


def _get_monitor_rects():
    """Return monitor rectangles as [(left, top, right, bottom), ...]."""
    if os.name != "nt":
        return []

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", ctypes.c_ulong),
        ]

    user32 = ctypes.windll.user32
    monitors = []

    monitor_enum_proc = ctypes.WINFUNCTYPE(
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(RECT),
        ctypes.c_long,
    )

    def _callback(h_monitor, _hdc, _lprc, _lparam):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(h_monitor, ctypes.byref(info)):
            r = info.rcMonitor
            monitors.append((int(r.left), int(r.top), int(r.right), int(r.bottom)))
        return 1

    user32.EnumDisplayMonitors(0, 0, monitor_enum_proc(_callback), 0)
    monitors.sort(key=lambda rect: (rect[0], rect[1]))
    return monitors


def _place_fullscreen(window, rect):
    left, top, right, bottom = rect
    width = max(100, right - left)
    height = max(100, bottom - top)
    window.overrideredirect(True)
    window.geometry(f"{width}x{height}+{left}+{top}")
    window.configure(bg="#10131a")
    window.lift()


class ScoreWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("Team Score")
        self.root.configure(bg="#10131a")
        self.style_prefix = f"W{str(id(self))}"

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(f"{self.style_prefix}.Root.TFrame", background="#10131a")

        self.font_title = tkfont.Font(family="Segoe UI", size=20, weight="bold")
        self.font_song = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        self.font_team = tkfont.Font(family="Segoe UI", size=16, weight="bold")
        self.font_score = tkfont.Font(family="Consolas", size=42, weight="bold")
        self.font_small = tkfont.Font(family="Segoe UI", size=10)

        style.configure(f"{self.style_prefix}.Big.TLabel", background="#10131a", foreground="#f2f5ff", font=self.font_title)
        style.configure(f"{self.style_prefix}.Song.TLabel", background="#10131a", foreground="#ffd166", font=self.font_song)
        style.configure(f"{self.style_prefix}.TeamLeft.TLabel", background="#10131a", foreground="#c070ff", font=self.font_team)
        style.configure(f"{self.style_prefix}.TeamRight.TLabel", background="#10131a", foreground="#00c8dc", font=self.font_team)
        style.configure(f"{self.style_prefix}.ScoreLeft.TLabel", background="#10131a", foreground="#e2b4ff", font=self.font_score)
        style.configure(f"{self.style_prefix}.ScoreRight.TLabel", background="#10131a", foreground="#9cefff", font=self.font_score)
        style.configure(f"{self.style_prefix}.Small.TLabel", background="#10131a", foreground="#a8b0c2", font=self.font_small)

        container = ttk.Frame(root, style=f"{self.style_prefix}.Root.TFrame", padding=18)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text="SCOR ECHIPE", style=f"{self.style_prefix}.Big.TLabel").pack(pady=(0, 14))
        self.song_lbl = ttk.Label(container, text="Melodie: -", style=f"{self.style_prefix}.Song.TLabel")
        self.song_lbl.pack(pady=(0, 10))

        scoreboard = ttk.Frame(container, style=f"{self.style_prefix}.Root.TFrame")
        scoreboard.pack(fill="x")
        scoreboard.columnconfigure(0, weight=1)
        scoreboard.columnconfigure(1, weight=1)

        left_frame = ttk.Frame(scoreboard, style=f"{self.style_prefix}.Root.TFrame")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ttk.Label(left_frame, text="LEFT", style=f"{self.style_prefix}.TeamLeft.TLabel").pack()
        self.left_score_lbl = ttk.Label(left_frame, text="0", style=f"{self.style_prefix}.ScoreLeft.TLabel")
        self.left_score_lbl.pack()

        right_frame = ttk.Frame(scoreboard, style=f"{self.style_prefix}.Root.TFrame")
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ttk.Label(right_frame, text="RIGHT", style=f"{self.style_prefix}.TeamRight.TLabel").pack()
        self.right_score_lbl = ttk.Label(right_frame, text="0", style=f"{self.style_prefix}.ScoreRight.TLabel")
        self.right_score_lbl.pack()

        self.winner_lbl = ttk.Label(container, text="Winner: -", style=f"{self.style_prefix}.Small.TLabel")
        self.winner_lbl.pack(pady=(14, 0))
        self.state_lbl = ttk.Label(container, text="State: PRELOBBY", style=f"{self.style_prefix}.Small.TLabel")
        self.state_lbl.pack(pady=(6, 0))

        self._last_payload = None
        self.root.update_idletasks()
        self._refresh_fonts()
        self.root.bind("<Configure>", self._on_resize)
        self._poll_scores()

    def _on_resize(self, event):
        if event.widget is self.root:
            self._refresh_fonts()

    def _refresh_fonts(self):
        w = max(420, self.root.winfo_width())
        h = max(240, self.root.winfo_height())
        scale = min(w / 460.0, h / 260.0)

        self.font_title.configure(size=max(16, int(20 * scale)))
        self.font_song.configure(size=max(9, int(11 * scale)))
        self.font_team.configure(size=max(12, int(16 * scale)))
        self.font_score.configure(size=max(26, int(42 * scale)))
        self.font_small.configure(size=max(9, int(10 * scale)))

    def _read_payload(self):
        if not os.path.exists(SCORE_FILE):
            return None
        try:
            with open(SCORE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception:
            return None

    def _poll_scores(self):
        payload = self._read_payload()

        if payload is None:
            self.song_lbl.configure(text="Melodie: waiting for game...")
        else:
            if payload != self._last_payload:
                left = int(payload.get("left", 0))
                right = int(payload.get("right", 0))
                winner = payload.get("winner")
                song = payload.get("song") or "-"
                state = payload.get("state") or "-"

                self.left_score_lbl.configure(text=str(left))
                self.right_score_lbl.configure(text=str(right))
                self.song_lbl.configure(text=f"Melodie: {song}")
                self.winner_lbl.configure(text=f"Winner: {winner if winner else '-'}")
                self.state_lbl.configure(text=f"State: {state}")
                self._last_payload = payload

        self.root.after(120, self._poll_scores)


def main():
    root = tk.Tk()
    monitors = _get_monitor_rects()

    # Need two mirrored windows: monitor 1 and monitor 2.
    # Fallback: if only one monitor, show both windows on primary monitor.
    if not monitors:
        w = root.winfo_screenwidth()
        h = root.winfo_screenheight()
        monitors = [(0, 0, w, h)]

    rect_1 = monitors[0]
    rect_2 = monitors[1] if len(monitors) > 1 else monitors[0]

    _place_fullscreen(root, rect_1)
    ScoreWindow(root)

    second = tk.Toplevel(root)
    _place_fullscreen(second, rect_2)
    ScoreWindow(second)

    # Quick manual exit shortcut for operator.
    root.bind("<Escape>", lambda _e: root.destroy())
    second.bind("<Escape>", lambda _e: root.destroy())

    root.mainloop()


if __name__ == "__main__":
    main()
