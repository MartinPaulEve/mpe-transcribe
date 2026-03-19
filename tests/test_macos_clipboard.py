from unittest.mock import MagicMock, call, patch

from transcribe.macos_clipboard import MacOSClipboard


class TestMacOSClipboard:
    def test_sets_clipboard_via_pbcopy(self):
        with (
            patch("transcribe.macos_clipboard.subprocess") as mock_sub,
            patch("transcribe.macos_clipboard._post_cmd_v"),
        ):
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout="old text"
            )
            cb = MacOSClipboard()
            cb.paste_text("hello world")
            # Find pbcopy calls that set "hello world"
            pbcopy_calls = [
                c
                for c in mock_sub.run.call_args_list
                if c[0][0][0] == "pbcopy"
                and c[1].get("input") == "hello world"
            ]
            assert len(pbcopy_calls) == 1

    def test_reads_clipboard_via_pbpaste(self):
        with patch("transcribe.macos_clipboard.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout="existing text"
            )
            cb = MacOSClipboard()
            result = cb._get_clipboard()
            pbpaste_calls = [
                c
                for c in mock_sub.run.call_args_list
                if c[0][0] == ["pbpaste"]
            ]
            assert len(pbpaste_calls) == 1
            assert result == "existing text"

    def test_simulates_cmd_v_via_cgevent(self):
        with (
            patch("transcribe.macos_clipboard.subprocess") as mock_sub,
            patch("transcribe.macos_clipboard._post_cmd_v") as mock_cmd_v,
        ):
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="old")
            cb = MacOSClipboard()
            cb.paste_text("text")
            mock_cmd_v.assert_called_once()

    def test_saves_and_restores_clipboard(self):
        with (
            patch("transcribe.macos_clipboard.subprocess") as mock_sub,
            patch("transcribe.macos_clipboard._post_cmd_v"),
        ):
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout="previous"
            )
            cb = MacOSClipboard()
            cb.paste_text("new text")
            calls = mock_sub.run.call_args_list
            # Last call should be restoring the clipboard via pbcopy
            last_pbcopy = [c for c in calls if c[0][0][0] == "pbcopy"]
            # Should have 2 pbcopy calls: set new text, restore old text
            assert len(last_pbcopy) == 2

    def test_empty_clipboard_skips_restore(self):
        with (
            patch("transcribe.macos_clipboard.subprocess") as mock_sub,
            patch("transcribe.macos_clipboard._post_cmd_v"),
        ):
            # pbpaste returns empty
            mock_sub.run.return_value = MagicMock(returncode=1, stdout="")
            cb = MacOSClipboard()
            cb.paste_text("text")
            pbcopy_calls = [
                c
                for c in mock_sub.run.call_args_list
                if c[0][0][0] == "pbcopy"
            ]
            # Only 1 pbcopy call (setting new text), no restore
            assert len(pbcopy_calls) == 1

    def test_unicode_text(self):
        with (
            patch("transcribe.macos_clipboard.subprocess") as mock_sub,
            patch("transcribe.macos_clipboard._post_cmd_v"),
        ):
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="old")
            cb = MacOSClipboard()
            cb.paste_text("caf\u00e9 \U0001f600")
            pbcopy_calls = [
                c
                for c in mock_sub.run.call_args_list
                if c[0][0][0] == "pbcopy"
                and c[1].get("input") == "caf\u00e9 \U0001f600"
            ]
            assert len(pbcopy_calls) == 1

    def test_restore_delay(self):
        with (
            patch("transcribe.macos_clipboard.subprocess") as mock_sub,
            patch("transcribe.macos_clipboard._post_cmd_v"),
            patch("transcribe.macos_clipboard.time") as mock_time,
        ):
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="old")
            cb = MacOSClipboard()
            cb.paste_text("text")
            sleep_calls = mock_time.sleep.call_args_list
            # Should have a delay before restore
            assert call(0.2) in sleep_calls
