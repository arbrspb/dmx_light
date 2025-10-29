import time
import argparse
import threading
import logging
import numpy as np
import sounddevice as sd
import rtmidi
import librosa

# Логирование — используем ваш конфиг
from logging_config import (
    is_log_type_enabled,
    setup_audio_diag_logger,
    setup_player_logger
)

# Настройка логгеров
setup_audio_diag_logger()
setup_player_logger()
audio_diag_logger = logging.getLogger("audio_diag")
player_logger = logging.getLogger("player")

# ====== Настройки по умолчанию ======
DEFAULT_NOTE = 60
DEFAULT_CHANNEL = 1
DEFAULT_VELOCITY = 127
DEFAULT_PORT = None
SAMPLE_RATE = 44100
FRAMES_PER_BUFFER = 1024

ALPHA = 0.35
ON_THRESHOLD = 1e-05
OFF_THRESHOLD = 4e-06
MIN_ON_TIME = 0.12
# ===================================


class RealtimeAudioMidi:
    def __init__(self, port_name=None, note=DEFAULT_NOTE, channel=DEFAULT_CHANNEL,
                 velocity=DEFAULT_VELOCITY, sr=SAMPLE_RATE, block=FRAMES_PER_BUFFER,
                 on_th=ON_THRESHOLD, off_th=OFF_THRESHOLD, alpha=ALPHA, min_on=MIN_ON_TIME):
        self.note = int(note)
        self.channel = int(channel)
        self.velocity = int(velocity)
        self.sr = sr
        self.block = block
        self.on_th = float(on_th)
        self.off_th = float(off_th)
        self.alpha = float(alpha)
        self.min_on = float(min_on)

        # Попытка использовать стандартный интерфейс python-rtmidi; fallback на RtMidiOut если нужно
        try:
            self.midi_out = rtmidi.MidiOut()
        except Exception:
            # Некоторые сборки/вёртки называют класс RtMidiOut
            self.midi_out = rtmidi.RtMidiOut()

        # Получаем список портов — поддерживаем несколько API-форматов
        ports = []
        if hasattr(self.midi_out, "get_ports"):
            try:
                ports = self.midi_out.get_ports() or []
            except Exception:
                ports = []
        elif hasattr(self.midi_out, "getPortCount") and hasattr(self.midi_out, "getPortName"):
            try:
                ports = [self.midi_out.getPortName(i) for i in range(self.midi_out.getPortCount())]
            except Exception:
                ports = []
        else:
            # Попытка посмотреть атрибуты объектa на всякий случай
            audio_diag_logger.debug("MIDI object methods at init: %s", dir(self.midi_out))

        if not ports:
            audio_diag_logger.error("No MIDI output ports found. Запустите loopMIDI или подключите виртуальный MIDI.")
            raise RuntimeError("No MIDI output ports found.")

        # Выбираем нужный порт (по подстроке имени) или первый доступный
        idx = 0
        if port_name:
            for i, p in enumerate(ports):
                if p and (port_name.lower() in p.lower()):
                    idx = i
                    break

        # Открываем порт, поддерживая разные имена методов
        try:
            if hasattr(self.midi_out, "open_port"):
                self.midi_out.open_port(idx)
            elif hasattr(self.midi_out, "openPort"):
                self.midi_out.openPort(idx)
            else:
                raise RuntimeError("No known open port method on MidiOut object")
            audio_diag_logger.info(f"[MIDI] opened port: {ports[idx]}")
            self.port_name = ports[idx]
        except Exception as e:
            audio_diag_logger.error(f"[MIDI] Failed to open port #{idx}: {e}", exc_info=True)
            raise

        # состояние
        self.smooth = 0.0
        self.is_on = False
        self.last_change = time.time()
        self.lock = threading.Lock()

        # буфер для onset detection через librosa
        self.audio_buffer = np.zeros(self.block * 4, dtype=np.float32)
        audio_diag_logger.debug(f"RealtimeAudioMidi initialized: note={self.note}, channel={self.channel}, midi_out_type={type(self.midi_out)}")

    def _send_midi_bytes(self, msg_bytes):
        """
        Robust send: tries several APIs depending on installed rtmidi wrapper:
         - send_message (python-rtmidi typical)
         - sendMessage(list)
         - sendMessage(MidiMessage) if rtmidi.MidiMessage exists
         - sendMessage(bytes)
         - fallback to mido (if installed)
        If all fail, logs object type and dir for debugging.
        """
        try:
            # 1) preferred modern wrapper name
            if hasattr(self.midi_out, "send_message"):
                try:
                    self.midi_out.send_message(msg_bytes)
                    player_logger.debug(f"[MIDI OUT] Sent (send_message) {msg_bytes}")
                    return
                except Exception as e:
                    player_logger.debug("send_message failed: %s", e, exc_info=True)

            # 2) older wrapper name sendMessage
            if hasattr(self.midi_out, "sendMessage"):
                try:
                    # first try to send plain list
                    self.midi_out.sendMessage(msg_bytes)
                    player_logger.debug(f"[MIDI OUT] Sent (sendMessage:list) {msg_bytes}")
                    return
                except Exception as e1:
                    player_logger.debug("sendMessage(list) failed: %s", e1, exc_info=True)
                    # try to build MidiMessage object if available in rtmidi module
                    try:
                        MidiMessageCls = getattr(rtmidi, "MidiMessage", None)
                        if MidiMessageCls is not None:
                            try:
                                msgobj = MidiMessageCls(msg_bytes)
                                self.midi_out.sendMessage(msgobj)
                                player_logger.debug(f"[MIDI OUT] Sent (sendMessage:MidiMessage) {msg_bytes}")
                                return
                            except Exception as e2:
                                player_logger.debug("sendMessage(MidiMessage) failed: %s", e2, exc_info=True)
                    except Exception:
                        player_logger.debug("No MidiMessage constructor available in rtmidi", exc_info=True)

                    # try bytes
                    try:
                        self.midi_out.sendMessage(bytes(msg_bytes))
                        player_logger.debug(f"[MIDI OUT] Sent (sendMessage:bytes) {msg_bytes}")
                        return
                    except Exception as e3:
                        player_logger.debug("sendMessage(bytes) failed: %s", e3, exc_info=True)

            # 3) fallback with mido (optional dependency)
            try:
                import mido
                try:
                    # open a temporary mido output using RtMidi backend
                    with mido.open_output(self.port_name) as out:
                        msg = mido.Message.from_bytes(bytes(msg_bytes))
                        out.send(msg)
                        player_logger.debug(f"[MIDI OUT] Sent via mido fallback: {msg_bytes}")
                        return
                except Exception as e_mido:
                    player_logger.debug("mido fallback send failed: %s", e_mido, exc_info=True)
            except Exception:
                # mido not installed or failed to import — ignore silently here
                player_logger.debug("mido not available for fallback")

            # If we reach here — nothing worked: log diagnostics
            player_logger.error(
                "Unable to send MIDI message %s. midi_out type=%s, methods=%s",
                msg_bytes, type(self.midi_out), dir(self.midi_out)
            )
        except Exception as e:
            player_logger.error("Unexpected error while sending MIDI message %s: %s", msg_bytes, e, exc_info=True)

    def _send_note_on(self):
        status = 0x90 | ((self.channel - 1) & 0x0f)
        msg = [status, self.note & 0x7f, self.velocity & 0x7f]
        self._send_midi_bytes(msg)

    def _send_note_off(self):
        status = 0x80 | ((self.channel - 1) & 0x0f)
        msg = [status, self.note & 0x7f, 0]
        self._send_midi_bytes(msg)

    def _close_midi_port(self):
        """Безопасное закрытие порта, поддерживающее разные имена методов."""
        try:
            if hasattr(self.midi_out, "close_port"):
                self.midi_out.close_port()
            elif hasattr(self.midi_out, "closePort"):
                self.midi_out.closePort()
            elif hasattr(self.midi_out, "close"):
                self.midi_out.close()
            else:
                audio_diag_logger.debug("No known MIDI close method on object: %s", dir(self.midi_out))
        except Exception as e:
            audio_diag_logger.error(f"Error while closing MIDI port: {e}", exc_info=True)

    def detect_onset_librosa(self, audio_chunk):
        """Обнаружение атак через librosa.onset_strength"""
        try:
            onset_env = librosa.onset.onset_strength(y=audio_chunk, sr=self.sr)
            return np.max(onset_env) > 0.5
        except Exception as e:
            audio_diag_logger.debug("Librosa onset error: %s", e)
            return False

    def process_block(self, indata, frames, time_info, status):
        if indata is None or len(indata) == 0:
            return
        data = np.mean(indata, axis=1) if indata.ndim > 1 else indata
        data = data.astype(np.float32)

        rms = np.sqrt(np.mean(np.square(data)))
        with self.lock:
            self.smooth = self.alpha * rms + (1.0 - self.alpha) * self.smooth
            now = time.time()

            self.audio_buffer = np.roll(self.audio_buffer, -len(data))
            self.audio_buffer[-len(data):] = data

            if self.detect_onset_librosa(self.audio_buffer):
                audio_diag_logger.debug("Onset detected")

            if not self.is_on:
                if self.smooth > self.on_th:
                    self.is_on = True
                    self.last_change = now
                    self._send_note_on()
            else:
                if (self.smooth < self.off_th) and ((now - self.last_change) >= self.min_on):
                    self.is_on = False
                    self.last_change = now
                    self._send_note_off()

    def run(self):
        audio_diag_logger.info("[Audio] starting input stream")
        try:
            with sd.InputStream(channels=1, samplerate=self.sr, blocksize=self.block,
                                callback=self.process_block):
                audio_diag_logger.info("[Audio] listening... Ctrl-C to stop.")
                while True:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            audio_diag_logger.info("[Audio] stopped by user")
        except Exception as e:
            audio_diag_logger.error(f"[Audio] stream error: {e}", exc_info=True)
        finally:
            if self.is_on:
                self._send_note_off()
            # Закрываем порт безопасно
            self._close_midi_port()
            audio_diag_logger.info("[MIDI] closed")


# === Точка входа ===
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=str, default=DEFAULT_PORT, help="MIDI port name (substring)")
    parser.add_argument("--note", type=int, default=DEFAULT_NOTE)
    parser.add_argument("--channel", type=int, default=DEFAULT_CHANNEL)
    parser.add_argument("--velocity", type=int, default=DEFAULT_VELOCITY)
    parser.add_argument("--on", type=float, default=ON_THRESHOLD)
    parser.add_argument("--off", type=float, default=OFF_THRESHOLD)
    parser.add_argument("--alpha", type=float, default=ALPHA)
    parser.add_argument("--hold", type=float, default=MIN_ON_TIME)
    args = parser.parse_args()

    ram = RealtimeAudioMidi(
        port_name=args.port,
        note=args.note,
        channel=args.channel,
        velocity=args.velocity,
        on_th=args.on,
        off_th=args.off,
        alpha=args.alpha,
        min_on=args.hold
    )
    ram.run()


if __name__ == "__main__":
    main()