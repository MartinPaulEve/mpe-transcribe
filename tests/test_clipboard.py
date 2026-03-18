from unittest.mock import MagicMock, call, patch

from transcribe.clipboard import Clipboard
from transcribe.clipboard_content import ClipboardContent


def _mock_subprocess_text(stdout="old clipboard"):
    """Return a mock subprocess where xclip -o returns text content."""
    mock_sub = MagicMock()

    def run_side_effect(cmd, **kwargs):
        result = MagicMock(returncode=0)
        if "-o" in cmd and "TARGETS" in cmd:
            # xclip -o -t TARGETS
            result.stdout = b"UTF8_STRING\ntext/plain\n"
        elif "-o" in cmd:
            # xclip -o -t <type> (binary mode)
            result.stdout = (
                stdout.encode() if isinstance(stdout, str) else stdout
            )
        return result

    mock_sub.run.side_effect = run_side_effect
    return mock_sub


def _mock_subprocess_image():
    """Return a mock subprocess where clipboard holds a PNG image."""
    mock_sub = MagicMock()
    image_data = b"\x89PNG\r\n\x1a\nfake image data"

    def run_side_effect(cmd, **kwargs):
        result = MagicMock(returncode=0)
        if "-o" in cmd and "TARGETS" in cmd:
            result.stdout = b"image/png\ntext/plain\n"
        elif "-o" in cmd:
            result.stdout = image_data
        return result

    mock_sub.run.side_effect = run_side_effect
    return mock_sub


class TestClipboard:
    def test_saves_and_restores_text_clipboard(self):
        with patch("transcribe.clipboard.subprocess") as mock_sub:
            mock_sub.run = _mock_subprocess_text("previous text").run
            cb = Clipboard()
            cb.paste_text("new text")
            calls = mock_sub.run.call_args_list
            # First call: read TARGETS
            assert "TARGETS" in calls[0][0][0]
            # Last call: restore old clipboard via _restore_clipboard
            last = calls[-1]
            assert last[0][0] == [
                "xclip",
                "-selection",
                "clipboard",
                "-t",
                "UTF8_STRING",
            ]
            assert last[1]["input"] == b"previous text"

    def test_saves_and_restores_image_clipboard(self):
        with patch("transcribe.clipboard.subprocess") as mock_sub:
            mock_sub.run = _mock_subprocess_image().run
            cb = Clipboard()
            cb.paste_text("transcription")
            calls = mock_sub.run.call_args_list
            # Last call: restore image
            last = calls[-1]
            assert last[0][0] == [
                "xclip",
                "-selection",
                "clipboard",
                "-t",
                "image/png",
            ]
            assert last[1]["input"] == b"\x89PNG\r\n\x1a\nfake image data"

    def test_sets_clipboard_with_text(self):
        with patch("transcribe.clipboard.subprocess") as mock_sub:
            mock_sub.run = _mock_subprocess_text().run
            cb = Clipboard()
            cb.paste_text("hello world")
            # _set_clipboard call (after TARGETS read and content read)
            set_calls = [
                c
                for c in mock_sub.run.call_args_list
                if c[0][0] == ["xclip", "-selection", "clipboard"]
                and c[1].get("input") == "hello world"
            ]
            assert len(set_calls) == 1

    def test_keyup_then_ctrl_v(self):
        with patch("transcribe.clipboard.subprocess") as mock_sub:
            mock_sub.run = _mock_subprocess_text().run
            cb = Clipboard()
            cb.paste_text("text")
            calls = mock_sub.run.call_args_list
            # Find keyup and ctrl+v calls
            keyup_call = [
                c for c in calls if "xdotool" in c[0][0] and "keyup" in c[0][0]
            ]
            ctrlv_call = [
                c
                for c in calls
                if "xdotool" in c[0][0] and "ctrl+v" in c[0][0]
            ]
            assert len(keyup_call) == 1
            assert len(ctrlv_call) == 1

    def test_unicode_text(self):
        with patch("transcribe.clipboard.subprocess") as mock_sub:
            mock_sub.run = _mock_subprocess_text().run
            cb = Clipboard()
            cb.paste_text("caf\u00e9 \U0001f600")
            set_calls = [
                c
                for c in mock_sub.run.call_args_list
                if c[0][0] == ["xclip", "-selection", "clipboard"]
                and c[1].get("input") == "caf\u00e9 \U0001f600"
            ]
            assert len(set_calls) == 1

    def test_empty_previous_clipboard_skips_restore(self):
        """When clipboard was empty (xclip TARGETS fails), don't restore."""
        with patch("transcribe.clipboard.subprocess") as mock_sub:

            def run_side_effect(cmd, **kwargs):
                result = MagicMock()
                if "TARGETS" in cmd:
                    result.returncode = 1
                    result.stdout = b""
                else:
                    result.returncode = 0
                return result

            mock_sub.run.side_effect = run_side_effect
            cb = Clipboard()
            cb.paste_text("text")
            # No restore call (xclip -t <mime>)
            restore_calls = [
                c
                for c in mock_sub.run.call_args_list
                if len(c[0][0]) > 3
                and c[0][0][0] == "xclip"
                and "-t" in c[0][0]
                and "TARGETS" not in c[0][0]
            ]
            assert len(restore_calls) == 0

    def test_restore_delay_is_200ms(self):
        """Verify the delay before restore is 0.2s, not 0.05s."""
        with (
            patch("transcribe.clipboard.subprocess") as mock_sub,
            patch("transcribe.clipboard.time") as mock_time,
        ):
            mock_sub.run = _mock_subprocess_text().run
            cb = Clipboard()
            cb.paste_text("text")
            sleep_calls = mock_time.sleep.call_args_list
            # Second sleep (before restore) should be 0.2
            assert sleep_calls[1] == call(0.2)

    def test_get_clipboard_returns_clipboard_content(self):
        with patch("transcribe.clipboard.subprocess") as mock_sub:
            mock_sub.run = _mock_subprocess_text("hello").run
            cb = Clipboard()
            result = cb._get_clipboard()
            assert isinstance(result, ClipboardContent)
            assert result.data == b"hello"
            assert result.mime_type == "UTF8_STRING"
