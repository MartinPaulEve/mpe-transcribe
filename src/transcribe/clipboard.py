import subprocess
import time

from transcribe.clipboard_content import ClipboardContent, pick_best_target


class Clipboard:
    def _get_clipboard(self) -> ClipboardContent | None:
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-o", "-t", "TARGETS"],
            capture_output=True,
            text=False,
        )
        if result.returncode != 0:
            return None
        targets = result.stdout.decode(errors="replace").splitlines()
        mime = pick_best_target(targets)
        if mime is None:
            return None
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-o", "-t", mime],
            capture_output=True,
            text=False,
        )
        if result.returncode != 0:
            return None
        return ClipboardContent(data=result.stdout, mime_type=mime)

    def _set_clipboard(self, text: str):
        subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=text,
            text=True,
            check=True,
        )

    def _restore_clipboard(self, content: ClipboardContent):
        subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", content.mime_type],
            input=content.data,
            text=False,
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
        # Wait for X11 to fully process the keyup events before
        # simulating Ctrl+V.  50 ms was not always enough — the
        # physical hotkey modifiers could still be in-flight,
        # causing only "v" to appear.
        time.sleep(0.15)
        # Use explicit keydown/keyup instead of "key ctrl+v" so
        # the Ctrl state is unambiguous and not subject to X11
        # modifier-map races.
        subprocess.run(
            [
                "xdotool",
                "keydown",
                "ctrl",
                "key",
                "v",
                "keyup",
                "ctrl",
            ],
            check=True,
        )
        # Restore the previous clipboard contents.
        time.sleep(0.2)
        if previous is not None:
            self._restore_clipboard(previous)
