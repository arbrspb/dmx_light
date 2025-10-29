import os
import yaml

_DEFAULT = {
    "audio": {
        "device_index": None,
        "samplerate": 44100,
        "blocksize": 1024,
        "channels": 1,
        "calibration_seconds": 1.0,
        "ema_alpha": 0.3,
    },
    "logic": {
        "dynamic_threshold": True,
        "on_multiplier": 4.0,
        "off_multiplier": 2.0,
        "min_on_threshold": 0.005,
        "min_off_threshold": 0.003,

        "on_threshold": 0.02,
        "off_threshold": 0.01,

        "startup_grace_seconds": 0.5,
        "min_on_seconds": 0.20,
        "min_off_seconds": 0.40,
        "silence_hold_seconds": 0.30,
    },
    "midi": {
        "output_port_name_contains": "loopMIDI",
        "channel": 1,
        "note": 60,
        "velocity": 127,
    }
}

def load(path: str = "config.yaml") -> dict:
    cfg = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    # глубокое объединение
    def merge(a, b):
        for k, v in b.items():
            if isinstance(v, dict):
                a[k] = merge(a.get(k, {}) if isinstance(a.get(k), dict) else {}, v)
            else:
                a.setdefault(k, v)
        return a
    return merge(cfg, _DEFAULT)