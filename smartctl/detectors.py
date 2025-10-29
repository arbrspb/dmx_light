import time
from dataclasses import dataclass
from typing import Optional
import numpy as np

@dataclass
class LevelConfig:
    ema_alpha: float
    dynamic_threshold: bool
    on_multiplier: float
    off_multiplier: float
    min_on_threshold: float
    min_off_threshold: float
    on_threshold: float
    off_threshold: float
    startup_grace_seconds: float
    min_on_seconds: float
    min_off_seconds: float
    silence_hold_seconds: float
    calibration_seconds: float

@dataclass
class LevelState:
    smooth: float = 0.0
    baseline: Optional[float] = None
    last_on_ts: float = 0.0
    last_off_ts: float = 0.0
    above_since: Optional[float] = None
    below_since: Optional[float] = None
    started_at: float = 0.0

class LevelDetector:
    def __init__(self, cfg: LevelConfig):
        self.cfg = cfg
        self.state = LevelState(started_at=time.time())

    def calibrate_step(self, samples: np.ndarray):
        # усредняем RMS на этапе калибровки
        rms = float(np.sqrt(np.mean(samples * samples)) + 1e-12)
        if self.state.baseline is None:
            self.state.baseline = rms
        else:
            # простая EMA для базовой линии
            self.state.baseline = 0.9 * self.state.baseline + 0.1 * rms

    def thresholds(self):
        if self.cfg.dynamic_threshold and self.state.baseline is not None:
            on_th = max(self.cfg.min_on_threshold, self.state.baseline * self.cfg.on_multiplier)
            off_th = max(self.cfg.min_off_threshold, self.state.baseline * self.cfg.off_multiplier)
            return on_th, off_th
        return self.cfg.on_threshold, self.cfg.off_threshold

    def update(self, samples: np.ndarray):
        # обновляем EMA уровня
        rms = float(np.sqrt(np.mean(samples * samples)) + 1e-12)
        self.state.smooth = self.cfg.ema_alpha * rms + (1.0 - self.cfg.ema_alpha) * self.state.smooth

        on_th, off_th = self.thresholds()
        now = time.time()

        # учёт выше/ниже порогов с “hold”
        if self.state.smooth > on_th:
            if self.state.above_since is None:
                self.state.above_since = now
            self.state.below_since = None
        elif self.state.smooth < off_th:
            if self.state.below_since is None:
                self.state.below_since = now
            self.state.above_since = None

        return {
            "rms": rms,
            "smooth": self.state.smooth,
            "on_th": on_th,
            "off_th": off_th,
            "now": now,
        }