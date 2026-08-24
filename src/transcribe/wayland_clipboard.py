import os
import shutil
import subprocess
import time

from transcribe.clipboard_content import ClipboardContent, pick_best_target

# ydotool key codes (Linux input event codes)
_KEY_LEFTCTRL = 29
_KEY_LEFTSHIFT = 42
_KEY_LEFTMETA = 125
_KEY_LEFTALT = 56
_KEY_V = 47

PASTE_METHODS = ("ctrl+v", "type")


class WaylandClipboard:
    """Paste on Wayland sessions.

    Clipboard access prefers xclip through the XWayland bridge: X11
    selections need no keyboard focus, whereas wl-copy/wl-paste on
    compositors without the data-control protocol (GNOME) must pop a
    transient surface that steals focus — and focus churn around the
    injected Ctrl+V can corrupt app key-repeat state into pasting
    again. Mutter mirrors the X11 and Wayland clipboards, so xclip
    reaches Wayland apps too.

    paste_method="type" skips the clipboard and chord entirely and
    types the text via ydotool — the escape hatch for environments
    where any synthetic Ctrl+V misbehaves.
    """

    def __init__(
        self,
        use_xclip: bool | None = None,
        paste_method: str = "ctrl+v",
    ):
        if paste_method not in PASTE_METHODS:
            raise ValueError(
                f"invalid paste_method: {paste_method!r} "
                f"(expected one of {', '.join(PASTE_METHODS)})"
            )
        if use_xclip is None:
            use_xclip = bool(
                shutil.which("xclip") and os.environ.get("DISPLAY")
            )
        self._use_xclip = use_xclip
        self._paste_method = paste_method

    # -- clipboard backends -------------------------------------------

    def _get_clipboard(self) -> ClipboardContent | None:
        if self._use_xclip:
            list_cmd = [
                "xclip",
                "-selection",
                "clipboard",
                "-o",
                "-t",
                "TARGETS",
            ]
        else:
            list_cmd = ["wl-paste", "--list-types"]
        result = subprocess.run(list_cmd, capture_output=True, text=False)
        if result.returncode != 0:
            return None
        targets = result.stdout.decode(errors="replace").splitlines()
        mime = pick_best_target(targets)
        if mime is None:
            return None
        if self._use_xclip:
            read_cmd = ["xclip", "-selection", "clipboard", "-o", "-t", mime]
        else:
            read_cmd = ["wl-paste", "-t", mime, "--no-newline"]
        result = subprocess.run(read_cmd, capture_output=True, text=False)
        if result.returncode != 0:
            return None
        return ClipboardContent(data=result.stdout, mime_type=mime)

    def _set_clipboard(self, text: str):
        if self._use_xclip:
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text,
                text=True,
                check=True,
            )
        else:
            subprocess.run(["wl-copy", text], check=True)

    def _restore_clipboard(self, content: ClipboardContent):
        if self._use_xclip:
            cmd = [
                "xclip",
                "-selection",
                "clipboard",
                "-t",
                content.mime_type,
            ]
        else:
            cmd = ["wl-copy", "--type", content.mime_type]
        subprocess.run(cmd, input=content.data, text=False, check=True)

    # -- key injection ------------------------------------------------

    def _release_ghost_modifiers(self):
        # Modifiers still held from the hotkey would corrupt the
        # injected input (Ctrl+V becomes Ctrl+Shift+V; typed text
        # becomes shortcuts).
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

    def _type_text(self, text: str):
        self._release_ghost_modifiers()
        time.sleep(0.05)
        # stdin keeps arbitrary text out of argv and disables
        # ydotool's escape processing.
        subprocess.run(
            ["ydotool", "type", "-d", "5", "-H", "5", "-f", "-"],
            input=text,
            text=True,
            check=True,
        )

    def paste_text(self, text: str):
        if self._paste_method == "type":
            self._type_text(text)
            return
        previous = self._get_clipboard()
        self._set_clipboard(text)
        # Let any clipboard-tool transient surface settle before key
        # events are sent (wl-clipboard fallback steals focus; xclip
        # does not, but the wait is harmless).
        time.sleep(0.35)
        self._release_ghost_modifiers()
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
        # Let the app finish reading the clipboard before restoring.
        time.sleep(0.5)
        if previous is not None:
            self._restore_clipboard(previous)
