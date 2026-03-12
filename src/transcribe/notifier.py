import subprocess

import numpy as np
import sounddevice as sd


class AppNotifier:
    def notify(self, title: str, body: str):
        subprocess.run(["notify-send", title, body], check=False)

    def ding(self):
        duration = 0.15
        sample_rate = 44100
        t = np.linspace(
            0, duration, int(sample_rate * duration), endpoint=False
        )
        tone = np.sin(2 * np.pi * 880 * t).astype(np.float32)
        sd.play(tone, samplerate=sample_rate)

    def notify_and_ding(self, title: str, body: str):
        self.notify(title, body)
        self.ding()
