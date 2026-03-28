"""
mutate_midi.py
--------------
Processes a MIDI file and brings all notes into the allowed range C3–G5.

  - Notes ABOVE G5  (MIDI > 79)  → shifted down by octaves into A4–G5  (69–79)
  - Notes BELOW C3  (MIDI < 48)  → shifted up   by octaves into C3–C4  (48–60)
  - Notes already in C3–G5 are left unchanged.

Usage:
    python mutate_midi.py <input.mid> [output.mid]

If output is omitted the result is saved as <input>_mutated.mid.

MIDI note reference (C4 = 60):
    C3=48  C4=60  A4=69  G5=79
"""

import sys
import os
import subprocess
import importlib.util


# ── auto-install mido if missing ─────────────────────────────────────────────
def _ensure(pkg, pip_name=None):
    if importlib.util.find_spec(pkg) is None:
        pip_name = pip_name or pkg
        print(f"[SETUP] installing {pip_name}…")
        subprocess.run(
            [sys.executable, "-m", "pip", "install",
             "--disable-pip-version-check", "--quiet", pip_name],
            check=True,
        )

_ensure("mido")

import mido  # noqa: E402 – imported after possible install

# ── constants ────────────────────────────────────────────────────────────────
C3   = 48   # lower bound of valid range
G5   = 79   # upper bound of valid range

# target ranges for out-of-bounds notes
LOW_MIN,  LOW_MAX  = 48, 60   # C3–C4
HIGH_MIN, HIGH_MAX = 69, 79   # A4–G5


# ── mutation logic ───────────────────────────────────────────────────────────
def _shift_into_range(note: int, lo: int, hi: int) -> int:
    """Shift *note* by ±12 semitones (octaves) until it falls in [lo, hi].
    If that is impossible (range < 12 wide), clamp to the nearest boundary."""
    if lo <= note <= hi:
        return note
    while note < lo:
        note += 12
    while note > hi:
        note -= 12
    # after shifting, re-check and clamp if the range is narrower than an octave
    return max(lo, min(hi, note))


def mutate_note(note: int) -> int:
    """Return the mutated note number."""
    if note < C3:
        return _shift_into_range(note, LOW_MIN,  LOW_MAX)
    if note > G5:
        return _shift_into_range(note, HIGH_MIN, HIGH_MAX)
    return note          # already in valid range


# ── MIDI processing ──────────────────────────────────────────────────────────
def process(input_path: str, output_path: str) -> None:
    mid = mido.MidiFile(input_path)
    changed = 0
    total   = 0

    for track in mid.tracks:
        for msg in track:
            if msg.type in ("note_on", "note_off"):
                total += 1
                new_note = mutate_note(msg.note)
                if new_note != msg.note:
                    changed += 1
                msg.note = new_note

    mid.save(output_path)
    print(f"Done. {changed}/{total} notes mutated.")
    print(f"Saved → {output_path}")


# ── entry point ──────────────────────────────────────────────────────────────
def _default_output(input_path: str) -> str:
    base, ext = os.path.splitext(input_path)
    return f"{base}_mutated{ext}"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    inp = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) >= 3 else _default_output(inp)

    if not os.path.isfile(inp):
        print(f"Error: file not found: {inp}")
        sys.exit(1)

    process(inp, out)
