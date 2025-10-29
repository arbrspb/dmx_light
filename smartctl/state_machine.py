from dataclasses import dataclass
from typing import Optional, Callable, Literal
import time

StateName = Literal["OFF", "ON"]

@dataclass
class FSMConfig:
    startup_grace_seconds: float
    min_on_seconds: float
    min_off_seconds: float
    silence_hold_seconds: float
    calibration_seconds: float

class OnOffFSM:
    def __init__(self, cfg: FSMConfig):
        self.cfg = cfg
        self.state: StateName = "OFF"
        self.since: float = time.time()

    def _can_switch(self, min_hold_s: float) -> bool:
        return (time.time() - self.since) >= min_hold_s

    def step(self, level_state, level_info, on_event: Callable[[], None], off_event: Callable[[], None]):
        now = level_info["now"]
        started_at = level_state.started_at

        # фаза калибровки и стартовая задержка
        if (now - started_at) < (self.cfg.calibration_seconds + self.cfg.startup_grace_seconds):
            return  # ничего не делаем

        # активная зона (выше on_th) — включаем, если выдержали min_off и есть активность
        if level_state.above_since is not None:
            if (now - level_state.above_since) >= 0.05:  # короткий антидребезг
                if self.state == "OFF" and self._can_switch(self.cfg.min_off_seconds):
                    self.state = "ON"
                    self.since = now
                    on_event()
            return

        # “тишина” (ниже off_th) — выключаем, если держится достаточно
        if level_state.below_since is not None:
            if (now - level_state.below_since) >= self.cfg.silence_hold_seconds:
                if self.state == "ON" and self._can_switch(self.cfg.min_on_seconds):
                    self.state = "OFF"
                    self.since = now
                    off_event()
            return