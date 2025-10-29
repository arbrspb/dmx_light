import logging
from dataclasses import dataclass
from typing import Literal, Optional, Dict, Any
from smartctl.midi_io import MidiSender

player_logger = logging.getLogger("player")

TriggerMode = Literal["same_note", "separate_notes", "cc_gate"]

@dataclass
class SceneTriggerConfig:
    mode: TriggerMode
    channel: int
    velocity: int
    # same_note
    note: Optional[int] = None
    # separate_notes
    note_on: Optional[int] = None
    note_off: Optional[int] = None
    # cc_gate
    cc: Optional[int] = None

class SceneController:
    def __init__(self, midi: MidiSender, cfg: SceneTriggerConfig):
        self.midi = midi
        self.cfg = cfg
        self._is_on = False

    def turn_on(self):
        if self._is_on:
            return
        if self.cfg.mode == "same_note":
            assert self.cfg.note is not None, "Config note required for same_note mode"
            self.midi.note_on(self.cfg.note, self.cfg.velocity, self.cfg.channel)
            player_logger.info("[SCENE] ON same_note (note=%s ch=%s)", self.cfg.note, self.cfg.channel)

        elif self.cfg.mode == "separate_notes":
            assert self.cfg.note_on is not None, "Config note_on required for separate_notes mode"
            # В FS повесьте эту ноту на “Запуск”
            self.midi.note_on(self.cfg.note_on, self.cfg.velocity, self.cfg.channel)
            player_logger.info("[SCENE] ON separate_notes (note_on=%s ch=%s)", self.cfg.note_on, self.cfg.channel)

        elif self.cfg.mode == "cc_gate":
            # CC 127 = включить
            assert self.cfg.cc is not None, "Config cc required for cc_gate mode"
            self.midi.cc(self.cfg.cc, 127, self.cfg.channel)
            player_logger.info("[SCENE] ON cc_gate (cc=%s val=127 ch=%s)", self.cfg.cc, self.cfg.channel)

        self._is_on = True

    def turn_off(self):
        if not self._is_on:
            return
        if self.cfg.mode == "same_note":
            assert self.cfg.note is not None, "Config note required for same_note mode"
            self.midi.note_off(self.cfg.note, self.cfg.channel)
            player_logger.info("[SCENE] OFF same_note (note=%s ch=%s)", self.cfg.note, self.cfg.channel)

        elif self.cfg.mode == "separate_notes":
            assert self.cfg.note_off is not None, "Config note_off required for separate_notes mode"
            # В FS повесьте эту ноту на “Остановка”
            self.midi.note_on(self.cfg.note_off, self.cfg.velocity, self.cfg.channel)
            player_logger.info("[SCENE] OFF separate_notes (note_off=%s ch=%s)", self.cfg.note_off, self.cfg.channel)

        elif self.cfg.mode == "cc_gate":
            # CC 0 = выключить
            assert self.cfg.cc is not None, "Config cc required for cc_gate mode"
            self.midi.cc(self.cfg.cc, 0, self.cfg.channel)
            player_logger.info("[SCENE] OFF cc_gate (cc=%s val=0 ch=%s)", self.cfg.cc, self.cfg.channel)

        self._is_on = False