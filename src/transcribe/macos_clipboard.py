import os
import subprocess
import time


def _post_cmd_v():
    """Request a Cmd+V keystroke.

    When running under the launcher (TRANSCRIBE_PASTE_FD is set), we
    write a byte to the pipe — the launcher's run loop picks it up and
    posts CGEventPost(Cmd+V) from the .app process which has the GUI
    session context.

    When running standalone (e.g. during development), fall back to
    osascript.
    """
    paste_fd = os.environ.get("TRANSCRIBE_PASTE_FD")
    if paste_fd:
        os.write(int(paste_fd), b"\x01")
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
