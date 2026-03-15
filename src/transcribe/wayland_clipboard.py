import subprocess
import time

# ydotool key codes (Linux input event codes)
_KEY_LEFTCTRL = 29
_KEY_LEFTSHIFT = 42
_KEY_LEFTMETA = 125
_KEY_LEFTALT = 56
_KEY_V = 47


class WaylandClipboard:
    def _get_clipboard(self) -> str | None:
        result = subprocess.run(
            ["wl-paste", "--no-newline"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout
        return None

    def _set_clipboard(self, text: str):
        subprocess.run(
            ["wl-copy", text],
            check=True,
        )

    def paste_text(self, text: str):
        previous = self._get_clipboard()
        self._set_clipboard(text)
        # Release any ghost modifiers from the hotkey
        subprocess.run(
            [
                "ydotool",
                "key",
                f"{_KEY_LEFTCTRL}:0",
                f"{_KEY_LEFTSHIFT}:0",
                f"{_KEY_LEFTMETA}:0",
                f"{_KEY_LEFTALT}:0",
            ],
            check=False,
        )
        time.sleep(0.05)
        # Simulate Ctrl+V
        subprocess.run(
            [
                "ydotool",
                "key",
                f"{_KEY_LEFTCTRL}:1",
                f"{_KEY_V}:1",
                f"{_KEY_V}:0",
                f"{_KEY_LEFTCTRL}:0",
            ],
            check=True,
        )
        time.sleep(0.05)
        if previous is not None:
            self._set_clipboard(previous)
