import subprocess
import time


class Clipboard:
    def _get_clipboard(self) -> str | None:
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-o"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout
        return None

    def _set_clipboard(self, text: str):
        subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=text,
            text=True,
            check=True,
        )

    def paste_text(self, text: str):
        previous = self._get_clipboard()
        self._set_clipboard(text)
        # Release any ghost modifiers from the hotkey, then paste.
        subprocess.run(
            ["xdotool", "keyup", "ctrl", "shift", "super", "alt"],
            check=False,
        )
        time.sleep(0.05)
        subprocess.run(
            ["xdotool", "key", "ctrl+v"],
            check=True,
        )
        # Restore the previous clipboard contents.
        time.sleep(0.05)
        if previous is not None:
            self._set_clipboard(previous)
