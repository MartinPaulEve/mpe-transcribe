import subprocess
import time


class MacOSClipboard:
    def _get_clipboard(self) -> str | None:
        result = subprocess.run(
            ["pbpaste"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        return result.stdout

    def _set_clipboard(self, text: str):
        subprocess.run(
            ["pbcopy"],
            input=text,
            text=True,
            check=True,
        )

    def paste_text(self, text: str):
        previous = self._get_clipboard()
        self._set_clipboard(text)
        time.sleep(0.05)
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to '
                'keystroke "v" using command down',
            ],
            check=True,
        )
        time.sleep(0.2)
        if previous is not None:
            self._set_clipboard(previous)
