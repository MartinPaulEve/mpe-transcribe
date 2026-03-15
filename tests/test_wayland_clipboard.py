from unittest.mock import call, patch

from transcribe.wayland_clipboard import WaylandClipboard


class TestWaylandClipboard:
    def _make_clipboard(self):
        return WaylandClipboard()

    @patch("transcribe.wayland_clipboard.subprocess")
    def test_get_clipboard_returns_stdout(self, mock_sub):
        mock_sub.run.return_value.returncode = 0
        mock_sub.run.return_value.stdout = "existing text"
        cb = self._make_clipboard()
        result = cb._get_clipboard()
        assert result == "existing text"
        mock_sub.run.assert_called_once_with(
            ["wl-paste", "--no-newline"],
            capture_output=True,
            text=True,
        )

    @patch("transcribe.wayland_clipboard.subprocess")
    def test_get_clipboard_returns_none_on_failure(self, mock_sub):
        mock_sub.run.return_value.returncode = 1
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
    def test_paste_text_saves_restores_clipboard(self, mock_sub, mock_time):
        mock_sub.run.return_value.returncode = 0
        mock_sub.run.return_value.stdout = "old"
        cb = self._make_clipboard()
        cb.paste_text("new text")

        calls = mock_sub.run.call_args_list
        # 1: wl-paste (get old)
        assert calls[0] == call(
            ["wl-paste", "--no-newline"],
            capture_output=True,
            text=True,
        )
        # 2: wl-copy (set new)
        assert calls[1] == call(["wl-copy", "new text"], check=True)
        # 3: ydotool release modifiers + paste
        assert calls[2] == call(
            [
                "ydotool",
                "key",
                "29:0",  # release ctrl
                "42:0",  # release shift
                "125:0",  # release super
                "56:0",  # release alt
            ],
            check=False,
        )
        # 4: ydotool ctrl+v
        assert calls[3] == call(
            ["ydotool", "key", "29:1", "47:1", "47:0", "29:0"],
            check=True,
        )
        # 5: wl-copy (restore old)
        assert calls[4] == call(["wl-copy", "old"], check=True)

    @patch("transcribe.wayland_clipboard.time")
    @patch("transcribe.wayland_clipboard.subprocess")
    def test_paste_text_no_restore_when_clipboard_empty(
        self, mock_sub, mock_time
    ):
        mock_sub.run.return_value.returncode = 1
        cb = self._make_clipboard()
        cb.paste_text("text")

        # Should not call wl-copy to restore
        wl_copy_calls = [
            c for c in mock_sub.run.call_args_list if c[0][0][0] == "wl-copy"
        ]
        # Only one wl-copy call (setting new text), no restore
        assert len(wl_copy_calls) == 1
