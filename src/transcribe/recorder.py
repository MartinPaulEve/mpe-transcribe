import logging
import threading

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)


class AudioRecorder:
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self._recording = False
        self._frames: list[np.ndarray] = []
        self._stream = None
        self._lock = threading.Lock()

    @property
    def is_recording(self) -> bool:
        return self._recording

    def _callback(self, indata, frames, time_info, status):
        if status:
            logger.warning("PortAudio status: %s", status)
        self._frames.append(indata.copy())

    def start(self):
        with self._lock:
            if self._recording:
                raise RuntimeError("already recording")
            self._frames = []
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                callback=self._callback,
            )
            self._stream.start()
            self._recording = True

    def stop(self) -> np.ndarray:
        with self._lock:
            if not self._recording:
                raise RuntimeError("not recording")
            self._stream.stop()
            self._stream.close()
            self._recording = False
            if not self._frames:
                return np.array([], dtype=np.float32)
            audio = np.concatenate(self._frames, axis=0)
            return audio.flatten()
