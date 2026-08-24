from unittest.mock import MagicMock, patch

from transcribe.clipboard_content import ClipboardContent
from transcribe.wayland_clipboard import WaylandClipboard


class TestWaylandClipboard:
    def _make_clipboard(self):
        return WaylandClipboard(use_xclip=False)

    @patch("transcribe.wayland_clipboard.subprocess")
    def test_get_clipboard_returns_clipboard_content(self, mock_sub):
        def run_side_effect(cmd, **kwargs):
            result = MagicMock(returncode=0)
            if "--list-types" in cmd:
                result.stdout = b"text/plain\nUTF8_STRING\n"
            else:
                result.stdout = b"existing text"
            return result

        mock_sub.run.side_effect = run_side_effect
        cb = self._make_clipboard()
        result = cb._get_clipboard()
        assert isinstance(result, ClipboardContent)
        assert result.data == b"existing text"
        assert result.mime_type == "UTF8_STRING"

    @patch("transcribe.wayland_clipboard.subprocess")
    def test_get_clipboard_returns_none_on_failure(self, mock_sub):
        mock_sub.run.return_value.returncode = 1
        mock_sub.run.return_value.stdout = b""
        cb = self._make_clipboard()
        assert cb._get_clipboard() is None

    @patch("transcribe.wayland_clipboard.subprocess")
    def test_set_clipboard_calls_wl_copy(self, mock_sub):
        cb = self._make_clipboard()
        cb._set_clipboard("hello")
        mock_sub.run.assert_called_once_with(
            ["wl-copy", "hello"],
            check=True,
        )

    @patch("transcribe.wayland_clipboard.time")
    @patch("transcribe.wayland_clipboard.subprocess")
    def test_paste_text_saves_restores_text_clipboard(
        self, mock_sub, mock_time
    ):
        def run_side_effect(cmd, **kwargs):
            result = MagicMock(returncode=0)
            if "--list-types" in cmd:
                result.stdout = b"UTF8_STRING\ntext/plain\n"
            elif cmd[0] == "wl-paste" and "-t" in cmd:
                result.stdout = b"old"
            else:
                result.stdout = b""
            return result

        mock_sub.run.side_effect = run_side_effect
        cb = self._make_clipboard()
        cb.paste_text("new text")

        calls = mock_sub.run.call_args_list
        # Last call: wl-copy restore with --type
        last = calls[-1]
        assert last[0][0] == ["wl-copy", "--type", "UTF8_STRING"]
        assert last[1]["input"] == b"old"

    @patch("transcribe.wayland_clipboard.time")
    @patch("transcribe.wayland_clipboard.subprocess")
    def test_paste_text_saves_restores_image_clipboard(
        self, mock_sub, mock_time
    ):
        image_data = b"\x89PNG\r\n\x1a\nfake"

        def run_side_effect(cmd, **kwargs):
            result = MagicMock(returncode=0)
            if "--list-types" in cmd:
                result.stdout = b"image/png\ntext/plain\n"
            elif cmd[0] == "wl-paste" and "-t" in cmd:
                result.stdout = image_data
            else:
                result.stdout = b""
            return result

        mock_sub.run.side_effect = run_side_effect
        cb = self._make_clipboard()
        cb.paste_text("transcription")

        calls = mock_sub.run.call_args_list
        last = calls[-1]
        assert last[0][0] == ["wl-copy", "--type", "image/png"]
        assert last[1]["input"] == image_data

    @patch("transcribe.wayland_clipboard.time")
    @patch("transcribe.wayland_clipboard.subprocess")
    def test_paste_text_no_restore_when_clipboard_empty(
        self, mock_sub, mock_time
    ):
        mock_sub.run.return_value.returncode = 1
        mock_sub.run.return_value.stdout = b""
        cb = self._make_clipboard()
        cb.paste_text("text")

        # Should not call wl-copy to restore
        wl_copy_calls = [
            c for c in mock_sub.run.call_args_list if c[0][0][0] == "wl-copy"
        ]
        # Only one wl-copy call (setting new text), no restore
        assert len(wl_copy_calls) == 1

    @patch("transcribe.wayland_clipboard.time")
    @patch("transcribe.wayland_clipboard.subprocess")
    def test_paste_chord_uses_human_speed_key_delay(self, mock_sub, mock_time):
        # Sub-millisecond synthetic chords can be double-processed by
        # some Wayland apps; the Ctrl+V injection must space its key
        # events at human typing speed.
        mock_sub.run.return_value.returncode = 1
        mock_sub.run.return_value.stdout = b""
        cb = self._make_clipboard()
        cb.paste_text("text")
        chords = [
            c[0][0]
            for c in mock_sub.run.call_args_list
            if c[0][0][0] == "ydotool" and "47:1" in c[0][0]
        ]
        assert len(chords) == 1
        cmd = chords[0]
        assert "-d" in cmd
        delay_ms = int(cmd[cmd.index("-d") + 1])
        assert delay_ms >= 40

    @patch("transcribe.wayland_clipboard.time")
    @patch("transcribe.wayland_clipboard.subprocess")
    def test_focus_settles_before_chord(self, mock_sub, mock_time):
        # wl-copy/wl-paste pop focus-stealing transient surfaces on
        # compositors without data-control; the chord must not be
        # injected until focus has returned to the target app.
        mock_sub.run.return_value.returncode = 1
        mock_sub.run.return_value.stdout = b""
        cb = self._make_clipboard()
        cb.paste_text("text")
        first_sleep = mock_time.sleep.call_args_list[0][0][0]
        assert first_sleep >= 0.3

    @patch("transcribe.wayland_clipboard.time")
    @patch("transcribe.wayland_clipboard.subprocess")
    def test_safety_release_after_chord(self, mock_sub, mock_time):
        # If focus churn makes the app believe V is still held, its
        # key repeat pastes forever. A release-only injection after
        # the chord guarantees every app sees V and Ctrl go up.
        mock_sub.run.return_value.returncode = 1
        mock_sub.run.return_value.stdout = b""
        cb = self._make_clipboard()
        cb.paste_text("text")
        ydotool_calls = [
            c[0][0]
            for c in mock_sub.run.call_args_list
            if c[0][0][0] == "ydotool"
        ]
        chord_idx = next(
            i for i, cmd in enumerate(ydotool_calls) if "47:1" in cmd
        )
        after_chord = ydotool_calls[chord_idx + 1 :]
        assert any(
            "47:0" in cmd and "29:0" in cmd and "47:1" not in cmd
            for cmd in after_chord
        )

    @patch("transcribe.wayland_clipboard.time")
    @patch("transcribe.wayland_clipboard.subprocess")
    def test_restore_waits_for_paste_completion(self, mock_sub, mock_time):
        def run_side_effect(cmd, **kwargs):
            result = MagicMock(returncode=0)
            if "--list-types" in cmd:
                result.stdout = b"UTF8_STRING\n"
            elif cmd[0] == "wl-paste":
                result.stdout = b"old"
            else:
                result.stdout = b""
            return result

        mock_sub.run.side_effect = run_side_effect
        cb = self._make_clipboard()
        cb.paste_text("text")
        # The sleep immediately before the restoring wl-copy must be
        # generous: restoring pops another transient surface, which
        # must not overlap the app's paste handling.
        last_sleep = mock_time.sleep.call_args_list[-1][0][0]
        assert last_sleep >= 0.5


class TestWaylandClipboardXclip:
    """X11-bridge clipboard: xclip through XWayland needs no focus,
    so no transient surfaces disturb the injected chord."""

    def _make_clipboard(self):
        return WaylandClipboard(use_xclip=True)

    @patch("transcribe.wayland_clipboard.subprocess")
    def test_set_clipboard_uses_xclip(self, mock_sub):
        cb = self._make_clipboard()
        cb._set_clipboard("hello")
        mock_sub.run.assert_called_once_with(
            ["xclip", "-selection", "clipboard"],
            input="hello",
            text=True,
            check=True,
        )

    @patch("transcribe.wayland_clipboard.subprocess")
    def test_get_clipboard_uses_xclip(self, mock_sub):
        def run_side_effect(cmd, **kwargs):
            result = MagicMock(returncode=0)
            if "TARGETS" in cmd:
                result.stdout = b"text/plain\nUTF8_STRING\n"
            else:
                result.stdout = b"existing text"
            return result

        mock_sub.run.side_effect = run_side_effect
        cb = self._make_clipboard()
        result = cb._get_clipboard()
        assert isinstance(result, ClipboardContent)
        assert result.data == b"existing text"
        assert result.mime_type == "UTF8_STRING"
        for c in mock_sub.run.call_args_list:
            assert c[0][0][0] == "xclip"

    @patch("transcribe.wayland_clipboard.time")
    @patch("transcribe.wayland_clipboard.subprocess")
    def test_paste_text_never_calls_wl_clipboard(self, mock_sub, mock_time):
        def run_side_effect(cmd, **kwargs):
            result = MagicMock(returncode=0)
            if "TARGETS" in cmd:
                result.stdout = b"UTF8_STRING\n"
            elif cmd[0] == "xclip" and "-o" in cmd:
                result.stdout = b"old"
            else:
                result.stdout = b""
            return result

        mock_sub.run.side_effect = run_side_effect
        cb = self._make_clipboard()
        cb.paste_text("new text")
        commands = [c[0][0][0] for c in mock_sub.run.call_args_list]
        assert "wl-copy" not in commands
        assert "wl-paste" not in commands
        assert "xclip" in commands
        assert "ydotool" in commands

    @patch("transcribe.wayland_clipboard.time")
    @patch("transcribe.wayland_clipboard.subprocess")
    def test_paste_text_restores_via_xclip(self, mock_sub, mock_time):
        def run_side_effect(cmd, **kwargs):
            result = MagicMock(returncode=0)
            if "TARGETS" in cmd:
                result.stdout = b"UTF8_STRING\n"
            elif cmd[0] == "xclip" and "-o" in cmd:
                result.stdout = b"old"
            else:
                result.stdout = b""
            return result

        mock_sub.run.side_effect = run_side_effect
        cb = self._make_clipboard()
        cb.paste_text("new text")
        last = mock_sub.run.call_args_list[-1]
        assert last[0][0] == [
            "xclip",
            "-selection",
            "clipboard",
            "-t",
            "UTF8_STRING",
        ]
        assert last[1]["input"] == b"old"

    @patch.dict("os.environ", {"DISPLAY": ":0"})
    @patch("transcribe.wayland_clipboard.shutil.which")
    def test_autodetects_xclip_when_display_present(self, mock_which):
        mock_which.return_value = "/usr/bin/xclip"
        cb = WaylandClipboard()
        assert cb._use_xclip is True

    @patch.dict("os.environ", {"DISPLAY": ":0"})
    @patch("transcribe.wayland_clipboard.shutil.which")
    def test_falls_back_to_wl_clipboard_without_xclip(self, mock_which):
        mock_which.return_value = None
        cb = WaylandClipboard()
        assert cb._use_xclip is False

    @patch.dict("os.environ", {}, clear=True)
    @patch("transcribe.wayland_clipboard.shutil.which")
    def test_falls_back_to_wl_clipboard_without_display(self, mock_which):
        mock_which.return_value = "/usr/bin/xclip"
        cb = WaylandClipboard()
        assert cb._use_xclip is False


class TestWaylandClipboardTypeMethod:
    """paste_method='type': text is typed directly, no clipboard and
    no Ctrl+V, so keystroke-replay bugs cannot double the paste."""

    @patch("transcribe.wayland_clipboard.time")
    @patch("transcribe.wayland_clipboard.subprocess")
    def test_types_text_via_ydotool_stdin(self, mock_sub, mock_time):
        cb = WaylandClipboard(use_xclip=False, paste_method="type")
        cb.paste_text("hello world")
        type_calls = [
            c
            for c in mock_sub.run.call_args_list
            if c[0][0][0] == "ydotool" and c[0][0][1] == "type"
        ]
        assert len(type_calls) == 1
        cmd = type_calls[0][0][0]
        assert cmd[-2:] == ["-f", "-"]
        assert type_calls[0][1]["input"] == "hello world"

    @patch("transcribe.wayland_clipboard.time")
    @patch("transcribe.wayland_clipboard.subprocess")
    def test_type_method_touches_no_clipboard(self, mock_sub, mock_time):
        cb = WaylandClipboard(use_xclip=False, paste_method="type")
        cb.paste_text("hello")
        commands = [c[0][0][0] for c in mock_sub.run.call_args_list]
        assert "wl-copy" not in commands
        assert "wl-paste" not in commands
        assert "xclip" not in commands

    @patch("transcribe.wayland_clipboard.time")
    @patch("transcribe.wayland_clipboard.subprocess")
    def test_type_method_releases_ghost_modifiers_first(
        self, mock_sub, mock_time
    ):
        # Held hotkey modifiers would turn typed characters into
        # shortcuts; they must be released before typing starts.
        cb = WaylandClipboard(use_xclip=False, paste_method="type")
        cb.paste_text("hi")
        calls = [c[0][0] for c in mock_sub.run.call_args_list]
        release_idx = next(i for i, cmd in enumerate(calls) if "29:0" in cmd)
        type_idx = next(i for i, cmd in enumerate(calls) if cmd[1] == "type")
        assert release_idx < type_idx

    def test_invalid_method_rejected(self):
        try:
            WaylandClipboard(use_xclip=False, paste_method="telepathy")
            raised = False
        except ValueError:
            raised = True
        assert raised
