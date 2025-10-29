import logging
from typing import List, Optional

player_logger = logging.getLogger("player")

class MidiSender:
    def __init__(self, port_substr: Optional[str] = None):
        try:
            import rtmidi  # type: ignore
        except Exception as e:
            raise RuntimeError("python-rtmidi is required. Install: pip install python-rtmidi") from e

        self._rtmidi = rtmidi
        try:
            self._out = rtmidi.MidiOut()
        except Exception:
            self._out = rtmidi.RtMidiOut()

        ports: List[str] = []
        if hasattr(self._out, "get_ports"):
            try:
                ports = self._out.get_ports() or []
            except Exception:
                ports = []
        elif hasattr(self._out, "getPortCount") and hasattr(self._out, "getPortName"):
            try:
                ports = [self._out.getPortName(i) for i in range(self._out.getPortCount())]
            except Exception:
                ports = []
        if not ports:
            raise RuntimeError("No MIDI outputs. Create a virtual port (loopMIDI).")

        idx = 0
        if port_substr:
            for i, p in enumerate(ports):
                if p and port_substr.lower() in p.lower():
                    idx = i
                    break

        if hasattr(self._out, "open_port"):
            self._out.open_port(idx)
        elif hasattr(self._out, "openPort"):
            self._out.openPort(idx)
        else:
            raise RuntimeError("MidiOut object has no open_port/openPort")

        self.port_name = ports[idx]
        player_logger.info(f"[MIDI] opened port: {self.port_name}")

    def close(self):
        try:
            if hasattr(self._out, "close_port"):
                self._out.close_port()
            elif hasattr(self._out, "closePort"):
                self._out.closePort()
            elif hasattr(self._out, "close"):
                self._out.close()
        except Exception as e:
            player_logger.debug("MIDI close error: %s", e)

    def _send_bytes(self, msg_bytes):
        try:
            if hasattr(self._out, "send_message"):
                self._out.send_message(msg_bytes)
                player_logger.debug(f"[MIDI OUT] Sent (send_message) {msg_bytes}")
                return
            if hasattr(self._out, "sendMessage"):
                try:
                    self._out.sendMessage(msg_bytes)
                    player_logger.debug(f"[MIDI OUT] Sent (sendMessage:list) {msg_bytes}")
                    return
                except Exception:
                    try:
                        MidiMessageCls = getattr(self._rtmidi, "MidiMessage", None)
                        if MidiMessageCls is not None:
                            obj = MidiMessageCls(msg_bytes)
                            self._out.sendMessage(obj)
                            player_logger.debug(f"[MIDI OUT] Sent (sendMessage:MidiMessage) {msg_bytes}")
                            return
                    except Exception:
                        pass
                    self._out.sendMessage(bytes(msg_bytes))
                    player_logger.debug(f"[MIDI OUT] Sent (sendMessage:bytes) {msg_bytes}")
                    return
        except Exception as e:
            try:
                import mido  # type: ignore
                with mido.open_output(self.port_name) as out:
                    msg = mido.Message.from_bytes(bytes(msg_bytes))
                    out.send(msg)
                    player_logger.debug(f"[MIDI OUT] Sent via mido fallback: {msg_bytes}")
                    return
            except Exception as e2:
                player_logger.error("Unable to send MIDI msg %s; rtmidi err: %s; mido err: %s",
                                    msg_bytes, e, e2, exc_info=True)
                raise

    def note_on(self, note: int, velocity: int = 127, channel: int = 1):
        status = 0x90 | ((channel - 1) & 0x0F)
        self._send_bytes([status, note & 0x7F, velocity & 0x7F])

    def note_off(self, note: int, channel: int = 1):
        status = 0x80 | ((channel - 1) & 0x0F)
        self._send_bytes([status, note & 0x7F, 0])

    def cc(self, cc_num: int, value: int, channel: int = 1):
        status = 0xB0 | ((channel - 1) & 0x0F)
        self._send_bytes([status, cc_num & 0x7F, value & 0x7F])