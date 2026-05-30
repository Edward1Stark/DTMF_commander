"""
dtmf_engine.py — Core DTMF decoding engine, COM sender, rule matcher.
No UI code lives here. Import this from your UI module.
"""

import threading
import queue
import json
import os
import time
import numpy as np

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

import DTMF2

# ── Config ─────────────────────────────────────────────────────────────────────

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".dtmf_commander_config.json")

RATE  = 44100
# CHUNK = 0.25 s of audio — small enough to feel responsive, large enough for
# reliable FFT-based DTMF detection (DTMF tones are typically ≥ 70 ms).
CHUNK_SAMPLES = int(RATE * 0.25)


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"rules": [], "audio_device_index": None}


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[WARN] Could not save config: {e}")


# ── Audio device listing ────────────────────────────────────────────────────────

def list_audio_devices():
    if not SOUNDDEVICE_AVAILABLE:
        return []
    devices = []
    for i, info in enumerate(sd.query_devices()):
        if info["max_input_channels"] > 0:
            devices.append((i, info["name"]))
    return devices


def list_com_ports():
    if not SERIAL_AVAILABLE:
        return []
    return [p.device for p in serial.tools.list_ports.comports()]


# ── COM port sender ─────────────────────────────────────────────────────────────

def send_to_com(port, command, baud=9600):
    if not SERIAL_AVAILABLE:
        return False, "pyserial not installed"
    try:
        with serial.Serial(port, baud, timeout=1) as ser:
            ser.write((command + "\r\n").encode("utf-8"))
        return True, None
    except Exception as e:
        return False, str(e)


# ── Rule matcher ────────────────────────────────────────────────────────────────

class RuleMatcher:
    """
    Rolling-buffer DTMF password matcher.
    Call .feed(digit_str) after each detection; it returns triggered rules.
    """

    def __init__(self, rules):
        self.rules   = rules
        self.buffer  = ""
        self.max_len = max((len(r.get("password", "")) for r in rules), default=0) if rules else 0

    def feed(self, digits: str):
        self.buffer += digits
        if self.max_len:
            self.buffer = self.buffer[-(self.max_len * 2):]
        triggered = []
        for rule in self.rules:
            pw = rule.get("password", "")
            if pw and self.buffer.endswith(pw):
                triggered.append(rule)
        return triggered

    def reset(self):
        self.buffer = ""


# ── DTMF Listener thread ────────────────────────────────────────────────────────

class DTMFListener(threading.Thread):
    """
    Reads audio from the chosen input device in fixed-size chunks.
    Deduplication: a digit is only emitted once per "tone event" — i.e. we
    suppress consecutive identical results until there is silence (empty result)
    between them.

    result_queue receives tuples:
        ("digit",  str)      — one or more newly detected unique digits
        ("status", str)      — "listening" | "stopped"
        ("error",  str)      — error message
    """

    def __init__(self, device_index, result_queue, stop_event):
        super().__init__(daemon=True)
        self.device_index = device_index
        self.result_queue = result_queue
        self.stop_event   = stop_event

    def run(self):
        if not SOUNDDEVICE_AVAILABLE:
            self.result_queue.put(("error", "sounddevice is not installed.\nRun:  pip install sounddevice"))
            return

        try:
            with sd.InputStream(
                samplerate=RATE,
                channels=1,
                dtype="int16",
                blocksize=CHUNK_SAMPLES,
                device=self.device_index,
            ) as stream:
                self.result_queue.put(("status", "listening"))

                last_result = ""   # last non-empty result — for dedup

                while not self.stop_event.is_set():
                    data, _ = stream.read(CHUNK_SAMPLES)
                    data = np.asarray(data, dtype=np.int16).flatten()
                    result = DTMF2.DTMF(data, RATE)

                    if not result:
                        # Silence window — reset dedup so the same key can fire again
                        # after a genuine new press
                        last_result = ""
                        continue

                    # Only emit if this chunk's result is different from the last
                    # non-empty chunk — this suppresses the same tone being reported
                    # across consecutive overlapping windows.
                    if result != last_result:
                        self.result_queue.put(("digit", result))
                        last_result = result

        except Exception as e:
            self.result_queue.put(("error", str(e)))
        finally:
            self.result_queue.put(("status", "stopped"))
