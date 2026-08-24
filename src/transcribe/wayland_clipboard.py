import subprocess
import time

from transcribe.clipboard_content import ClipboardContent, pick_best_target

# ydotool key codes (Linux input event codes)
_KEY_LEFTCTRL = 29
_KEY_LEFTSHIFT = 42
_KEY_LEFTMETA = 125
_KEY_LEFTALT = 56
_KEY_V = 47


class WaylandClipboard:
    def _get_clipboard(self) -> ClipboardContent | None:
        result = subprocess.run(
            ["wl-paste", "--list-types"],
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
            ["wl-paste", "-t", mime, "--no-newline"],
            capture_output=True,
            text=False,
        )
        if result.returncode != 0:
            return None
        return ClipboardContent(data=result.stdout, mime_type=mime)

    def _set_clipboard(self, text: str):
        subprocess.run(
            ["wl-copy", text],
            check=True,
        )

    def _restore_clipboard(self, content: ClipboardContent):
        subprocess.run(
            ["wl-copy", "--type", content.mime_type],
            input=content.data,
            text=False,
            check=True,
        )

    def paste_text(self, text: str):
        # On compositors without the data-control protocol (GNOME),
        # every wl-copy/wl-paste below pops a transient surface that
        # briefly steals keyboard focus. If that churn overlaps the
        # injected chord, the target app can miss the V release and
        # its client-side key repeat pastes again (or forever). The
        # sequence therefore isolates the chord from all clipboard
        # operations and always re-releases the keys afterwards.
        previous = self._get_clipboard()
        self._set_clipboard(text)
        # Let focus return to the target app after the wl-copy
        # transient before any key event is sent.
        time.sleep(0.35)
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
        # Simulate Ctrl+V at human typing speed: sub-millisecond
        # synthetic chords can be double-processed by some apps.
        subprocess.run(
            [
                "ydotool",
                "key",
                "-d",
                "40",
                f"{_KEY_LEFTCTRL}:1",
                f"{_KEY_V}:1",
                f"{_KEY_V}:0",
                f"{_KEY_LEFTCTRL}:0",
            ],
            check=True,
        )
        time.sleep(0.15)
        # Safety release: guarantee every surface sees V and Ctrl go
        # up, cancelling any phantom-held key before repeat starts.
        subprocess.run(
            [
                "ydotool",
                "key",
                f"{_KEY_V}:0",
                f"{_KEY_LEFTCTRL}:0",
            ],
            check=False,
        )
        # Let the app finish reading the clipboard before the restore
        # pops another focus-stealing transient.
        time.sleep(0.5)
        if previous is not None:
            self._restore_clipboard(previous)
