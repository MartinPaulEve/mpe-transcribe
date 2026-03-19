import os
import signal
import subprocess
import time


def _post_cmd_v():
    """Ask the native launcher to simulate Cmd+V via CGEventPost.

    When running under the launcher (TRANSCRIBE_LAUNCHER=1), we send
    SIGUSR2 to the parent process — the .app binary that has the GUI
    session context needed for CGEventPost to reach the focused app.

    When running standalone (e.g. during development), fall back to
    osascript.
    """
    if os.environ.get("TRANSCRIBE_LAUNCHER"):
        os.kill(os.getppid(), signal.SIGUSR2)
    else:
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to '
                'keystroke "v" using command down',
            ],
            check=True,
        )


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
        _post_cmd_v()
        time.sleep(0.2)
        if previous is not None:
            self._set_clipboard(previous)
