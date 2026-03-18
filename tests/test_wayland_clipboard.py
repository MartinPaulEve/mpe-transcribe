from unittest.mock import MagicMock, call, patch

from transcribe.clipboard_content import ClipboardContent
from transcribe.wayland_clipboard import WaylandClipboard


class TestWaylandClipboard:
    def _make_clipboard(self):
        return WaylandClipboard()

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
    def test_restore_delay_is_200ms(self, mock_sub, mock_time):
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
        sleep_calls = mock_time.sleep.call_args_list
        # Second sleep (before restore) should be 0.2
        assert sleep_calls[1] == call(0.2)
