import queue
import threading
from typing import Optional, Callable
import numpy as np
import sounddevice as sd
import logging

audio_logger = logging.getLogger("audio_diag")

class AudioStream:
    def __init__(self, samplerate: int, blocksize: int, channels: int, device_index: Optional[int] = None):
        self.sr = samplerate
        self.bs = blocksize
        self.ch = channels
        self.dev = device_index
        self.q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=32)
        self._stream: Optional[sd.InputStream] = None

    def _callback(self, indata, frames, time_info, status):
        if status:
            audio_logger.debug("Sounddevice status: %s", status)
        if indata is None or len(indata) == 0:
            return
        data = np.mean(indata, axis=1).astype(np.float32) if indata.ndim > 1 else indata.astype(np.float32)
        try:
            self.q.put_nowait(data.copy())
        except queue.Full:
            pass

    def start(self):
        self._stream = sd.InputStream(
            channels=self.ch,
            samplerate=self.sr,
            blocksize=self.bs,
            device=self.dev,
            callback=self._callback
        )
        self._stream.start()
        audio_logger.info("[Audio] listening...")

    def read_block(self, timeout: float = 0.5) -> Optional[np.ndarray]:
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self):
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass