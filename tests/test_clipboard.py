from unittest.mock import MagicMock, patch

from transcribe.clipboard import Clipboard


def _mock_subprocess(stdout="old clipboard"):
    """Return a mock subprocess where xclip -o returns stdout."""
    mock_sub = MagicMock()

    def run_side_effect(cmd, **kwargs):
        result = MagicMock(returncode=0)
        if "-o" in cmd:
            result.stdout = stdout
        return result

    mock_sub.run.side_effect = run_side_effect
    return mock_sub


class TestClipboard:
    def test_saves_and_restores_clipboard(self):
        with patch("transcribe.clipboard.subprocess") as mock_sub:
            mock_sub.run = _mock_subprocess("previous text").run
            cb = Clipboard()
            cb.paste_text("new text")
            calls = mock_sub.run.call_args_list
            # First call: read old clipboard
            assert calls[0][0][0] == ["xclip", "-selection", "clipboard", "-o"]
            # Last call: restore old clipboard
            last = calls[-1]
            assert last[0][0] == ["xclip", "-selection", "clipboard"]
            assert last[1]["input"] == "previous text"

    def test_sets_clipboard_with_text(self):
        with patch("transcribe.clipboard.subprocess") as mock_sub:
            mock_sub.run = _mock_subprocess().run
            cb = Clipboard()
            cb.paste_text("hello world")
            # Second call: set clipboard to new text
            set_call = mock_sub.run.call_args_list[1]
            assert set_call[1]["input"] == "hello world"

    def test_keyup_then_ctrl_v(self):
        with patch("transcribe.clipboard.subprocess") as mock_sub:
            mock_sub.run = _mock_subprocess().run
            cb = Clipboard()
            cb.paste_text("text")
            calls = mock_sub.run.call_args_list
            # calls: [read, set, keyup, ctrl+v, restore]
            assert calls[2][0][0] == [
                "xdotool",
                "keyup",
                "ctrl",
                "shift",
                "super",
                "alt",
            ]
            assert calls[3][0][0] == ["xdotool", "key", "ctrl+v"]

    def test_unicode_text(self):
        with patch("transcribe.clipboard.subprocess") as mock_sub:
            mock_sub.run = _mock_subprocess().run
            cb = Clipboard()
            cb.paste_text("caf\u00e9 \U0001f600")
            set_call = mock_sub.run.call_args_list[1]
            assert set_call[1]["input"] == "caf\u00e9 \U0001f600"

    def test_empty_previous_clipboard_skips_restore(self):
        """When clipboard was empty (xclip -o fails), don't restore."""
        with patch("transcribe.clipboard.subprocess") as mock_sub:

            def run_side_effect(cmd, **kwargs):
                result = MagicMock()
                if "-o" in cmd:
                    result.returncode = 1
                    result.stdout = ""
                else:
                    result.returncode = 0
                return result

            mock_sub.run.side_effect = run_side_effect
            cb = Clipboard()
            cb.paste_text("text")
            calls = mock_sub.run.call_args_list
            # Should be 4 calls: read, set, keyup, ctrl+v (no restore)
            assert len(calls) == 4
