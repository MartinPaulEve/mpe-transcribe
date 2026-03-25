import subprocess

import numpy as np
import sounddevice as sd


class WindowsNotifier:
    def notify(self, title: str, body: str):
        try:
            ps_script = (
                "[Windows.UI.Notifications"
                ".ToastNotificationManager,"
                " Windows.UI.Notifications,"
                " ContentType = WindowsRuntime] | Out-Null; "
                "$template = [Windows.UI.Notifications"
                ".ToastNotificationManager]::GetTemplateContent("
                "[Windows.UI.Notifications.ToastTemplateType]"
                "::ToastText02); "
                "$textNodes = "
                "$template.GetElementsByTagName('text'); "
                "$textNodes.Item(0).AppendChild("
                f"$template.CreateTextNode('{title}')); "
                "$textNodes.Item(1).AppendChild("
                f"$template.CreateTextNode('{body}')); "
                "$toast = [Windows.UI.Notifications"
                ".ToastNotification]::new($template); "
                "[Windows.UI.Notifications"
                ".ToastNotificationManager]"
                "::CreateToastNotifier('Transcribe')"
                ".Show($toast)"
            )
            subprocess.run(
                ["powershell", "-Command", ps_script],
                check=False,
                capture_output=True,
            )
        except Exception:
            pass

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
