from unittest.mock import call, patch

from transcribe.windows_clipboard import WindowsClipboard


class TestWindowsClipboard:
    def test_sets_clipboard_text(self):
        cb = WindowsClipboard()
        with (
            patch.object(cb, "_get_clipboard", return_value="old text"),
            patch.object(cb, "_set_clipboard") as mock_set,
            patch.object(cb, "_simulate_ctrl_v"),
            patch("transcribe.windows_clipboard.time"),
        ):
            cb.paste_text("hello world")
            # Should be called twice: once with new text, once to restore
            assert any(
                c == call("hello world") for c in mock_set.call_args_list
            )

    def test_reads_clipboard_text(self):
        cb = WindowsClipboard()
        with patch.object(cb, "_get_clipboard", return_value="existing text"):
            result = cb._get_clipboard()
            assert result == "existing text"

    def test_simulates_ctrl_v(self):
        cb = WindowsClipboard()
        with (
            patch.object(cb, "_get_clipboard", return_value="old"),
            patch.object(cb, "_set_clipboard"),
            patch.object(cb, "_simulate_ctrl_v") as mock_ctrl_v,
            patch("transcribe.windows_clipboard.time"),
        ):
            cb.paste_text("text")
            mock_ctrl_v.assert_called_once()

    def test_saves_and_restores_clipboard(self):
        cb = WindowsClipboard()
        with (
            patch.object(cb, "_get_clipboard", return_value="previous"),
            patch.object(cb, "_set_clipboard") as mock_set,
            patch.object(cb, "_simulate_ctrl_v"),
            patch("transcribe.windows_clipboard.time"),
        ):
            cb.paste_text("new text")
            assert mock_set.call_count == 2
            mock_set.assert_any_call("new text")
            mock_set.assert_any_call("previous")

    def test_empty_clipboard_skips_restore(self):
        cb = WindowsClipboard()
        with (
            patch.object(cb, "_get_clipboard", return_value=None),
            patch.object(cb, "_set_clipboard") as mock_set,
            patch.object(cb, "_simulate_ctrl_v"),
            patch("transcribe.windows_clipboard.time"),
        ):
            cb.paste_text("text")
            assert mock_set.call_count == 1
            mock_set.assert_called_once_with("text")

    def test_unicode_text(self):
        cb = WindowsClipboard()
        with (
            patch.object(cb, "_get_clipboard", return_value="old"),
            patch.object(cb, "_set_clipboard") as mock_set,
            patch.object(cb, "_simulate_ctrl_v"),
            patch("transcribe.windows_clipboard.time"),
        ):
            cb.paste_text("café 😀")
            mock_set.assert_any_call("café 😀")

    def test_restore_delay(self):
        cb = WindowsClipboard()
        with (
            patch.object(cb, "_get_clipboard", return_value="old"),
            patch.object(cb, "_set_clipboard"),
            patch.object(cb, "_simulate_ctrl_v"),
            patch("transcribe.windows_clipboard.time") as mock_time,
        ):
            cb.paste_text("text")
            assert call(0.2) in mock_time.sleep.call_args_list
