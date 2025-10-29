import time
import logging
from logging_config import setup_audio_diag_logger, setup_player_logger
setup_audio_diag_logger()
setup_player_logger()
audio_logger = logging.getLogger("audio_diag")
player_logger = logging.getLogger("player")

from smartctl import config as cfgmod
from smartctl.audio_input import AudioStream
from smartctl.midi_io import MidiSender
from smartctl.detectors import LevelConfig, LevelDetector
from smartctl.state_machine import FSMConfig, OnOffFSM
from smartctl.controller import SceneController, SceneTriggerConfig

def _build_trigger_cfg(m: dict) -> SceneTriggerConfig:
    mode = m.get("trigger_mode", "same_note")
    ch = m.get("channel", 1)
    vel = m.get("velocity", 127)

    if mode == "same_note":
        note = m.get("note")
        if note is None:
            raise ValueError("Config error: trigger_mode=same_note, but midi.note is missing. Example: midi.note: 60")
        player_logger.info("[CFG] trigger_mode=same_note note=%s ch=%s vel=%s", note, ch, vel)
        return SceneTriggerConfig(mode="same_note", channel=ch, velocity=vel, note=note)

    if mode == "separate_notes":
        notes = m.get("notes") or {}
        note_on = notes.get("on")
        note_off = notes.get("off")
        if note_on is None or note_off is None:
            raise ValueError("Config error: trigger_mode=separate_notes requires midi.notes.on and midi.notes.off. "
                             "Example:\n  midi:\n    trigger_mode: separate_notes\n    notes:\n      on: 60\n      off: 61")
        player_logger.info("[CFG] trigger_mode=separate_notes on=%s off=%s ch=%s vel=%s", note_on, note_off, ch, vel)
        return SceneTriggerConfig(mode="separate_notes", channel=ch, velocity=vel, note_on=note_on, note_off=note_off)

    if mode == "cc_gate":
        cc = m.get("cc")
        if cc is None:
            raise ValueError("Config error: trigger_mode=cc_gate requires midi.cc (controller number).")
        player_logger.info("[CFG] trigger_mode=cc_gate cc=%s ch=%s", cc, ch)
        return SceneTriggerConfig(mode="cc_gate", channel=ch, velocity=vel, cc=cc)

    raise ValueError(f"Unknown trigger_mode: {mode}")

def main():
    cfg = cfgmod.load("config.yaml")

    # Audio
    a = cfg["audio"]
    audio = AudioStream(
        samplerate=a["samplerate"],
        blocksize=a["blocksize"],
        channels=a["channels"],
        device_index=a.get("device_index"),
    )

    # MIDI
    m = cfg["midi"]
    midi = MidiSender(port_substr=m["output_port_name_contains"])
    trig_cfg = _build_trigger_cfg(m)
    scene = SceneController(midi, trig_cfg)

    # Detector + FSM
    l = cfg["logic"]
    level_cfg = LevelConfig(
        ema_alpha=a["ema_alpha"],
        dynamic_threshold=l["dynamic_threshold"],
        on_multiplier=l.get("on_multiplier", 2.5),
        off_multiplier=l.get("off_multiplier", 1.6),
        min_on_threshold=l.get("min_on_threshold", 0.00006),
        min_off_threshold=l.get("min_off_threshold", 0.00004),
        on_threshold=l.get("on_threshold", 0.00005),
        off_threshold=l.get("off_threshold", 0.00003),
        startup_grace_seconds=l["startup_grace_seconds"],
        min_on_seconds=l["min_on_seconds"],
        min_off_seconds=l["min_off_seconds"],
        silence_hold_seconds=l["silence_hold_seconds"],
        calibration_seconds=a["calibration_seconds"],
    )
    det = LevelDetector(level_cfg)
    fsm = OnOffFSM(FSMConfig(
        startup_grace_seconds=l["startup_grace_seconds"],
        min_on_seconds=l["min_on_seconds"],
        min_off_seconds=l["min_off_seconds"],
        silence_hold_seconds=l["silence_hold_seconds"],
        calibration_seconds=a["calibration_seconds"],
    ))

    audio_logger.info("[Audio] starting input stream")
    audio.start()
    try:
        # Калибровка тишины
        t0 = time.time()
        while (time.time() - t0) < a["calibration_seconds"]:
            blk = audio.read_block(timeout=0.2)
            if blk is not None:
                det.calibrate_step(blk)
        audio_logger.info("[Calib] baseline=%.6f", det.state.baseline or -1.0)

        # Основной цикл
        while True:
            blk = audio.read_block(timeout=0.5)
            if blk is None:
                continue
            info = det.update(blk)
            if audio_logger.isEnabledFor(logging.DEBUG):
                audio_logger.debug("lvl=%.5f on=%.5f off=%.5f", info["smooth"], info["on_th"], info["off_th"])
            fsm.step(det.state, info, on_event=scene.turn_on, off_event=scene.turn_off)

    except KeyboardInterrupt:
        audio_logger.info("[Audio] stopped by user")
    finally:
        scene.turn_off()
        audio.stop()
        midi.close()
        player_logger.info("[MIDI] closed")

if __name__ == "__main__":
    main()