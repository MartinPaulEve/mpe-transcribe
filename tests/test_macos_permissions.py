from unittest.mock import MagicMock, patch

from transcribe.macos_permissions import (
    _is_interactive,
    _show_alert_dialog,
    is_accessibility_trusted,
    warn_if_not_trusted,
)


class TestIsAccessibilityTrusted:
    def test_returns_true_when_trusted(self):
        mock_lib = MagicMock()
        mock_lib.AXIsProcessTrusted.return_value = True
        with patch(
            "transcribe.macos_permissions.ctypes"
        ) as mock_ctypes:
            mock_ctypes.util.find_library.return_value = "/fake/path"
            mock_ctypes.cdll.LoadLibrary.return_value = mock_lib
            mock_ctypes.c_bool = bool
            assert is_accessibility_trusted() is True

    def test_returns_false_when_not_trusted(self):
        mock_lib = MagicMock()
        mock_lib.AXIsProcessTrusted.return_value = False
        with patch(
            "transcribe.macos_permissions.ctypes"
        ) as mock_ctypes:
            mock_ctypes.util.find_library.return_value = "/fake/path"
            mock_ctypes.cdll.LoadLibrary.return_value = mock_lib
            mock_ctypes.c_bool = bool
            assert is_accessibility_trusted() is False

    def test_returns_true_when_library_not_found(self):
        with patch(
            "transcribe.macos_permissions.ctypes"
        ) as mock_ctypes:
            mock_ctypes.util.find_library.return_value = None
            assert is_accessibility_trusted() is True

    def test_returns_true_on_load_error(self):
        with patch(
            "transcribe.macos_permissions.ctypes"
        ) as mock_ctypes:
            mock_ctypes.util.find_library.return_value = "/fake/path"
            mock_ctypes.cdll.LoadLibrary.side_effect = OSError("fail")
            assert is_accessibility_trusted() is True


class TestIsInteractive:
    def test_returns_true_when_tty(self):
        with patch(
            "transcribe.macos_permissions.sys"
        ) as mock_sys:
            mock_sys.stdin.isatty.return_value = True
            assert _is_interactive() is True

    def test_returns_false_when_not_tty(self):
        with patch(
            "transcribe.macos_permissions.sys"
        ) as mock_sys:
            mock_sys.stdin.isatty.return_value = False
            assert _is_interactive() is False


class TestShowAlertDialog:
    def test_shows_osascript_dialog(self):
        with patch(
            "transcribe.macos_permissions.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(stdout="OK")
            _show_alert_dialog("Title", "Body")
            mock_sub.run.assert_called_once()
            cmd = mock_sub.run.call_args[0][0]
            assert cmd[0] == "osascript"
            assert "as critical" in cmd[2]

    def test_opens_system_settings_when_chosen(self):
        with patch(
            "transcribe.macos_permissions.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(
                stdout="button returned:Open System Settings"
            )
            _show_alert_dialog("Title", "Body")
            assert mock_sub.run.call_count == 2
            open_cmd = mock_sub.run.call_args_list[1][0][0]
            assert open_cmd[0] == "open"
            assert "Accessibility" in open_cmd[1]

    def test_does_not_raise_on_failure(self):
        with patch(
            "transcribe.macos_permissions.subprocess"
        ) as mock_sub:
            mock_sub.run.side_effect = Exception("fail")
            # Should not raise
            _show_alert_dialog("Title", "Body")


class TestWarnIfNotTrusted:
    def test_no_warning_when_trusted(self):
        with (
            patch(
                "transcribe.macos_permissions.is_accessibility_trusted",
                return_value=True,
            ),
            patch(
                "transcribe.macos_permissions.subprocess"
            ) as mock_sub,
        ):
            warn_if_not_trusted()
            mock_sub.run.assert_not_called()

    def test_terminal_mode_sends_notification(self):
        with (
            patch(
                "transcribe.macos_permissions.is_accessibility_trusted",
                return_value=False,
            ),
            patch(
                "transcribe.macos_permissions._is_interactive",
                return_value=True,
            ),
            patch(
                "transcribe.macos_permissions.subprocess"
            ) as mock_sub,
        ):
            warn_if_not_trusted()
            mock_sub.run.assert_called_once()
            cmd = mock_sub.run.call_args[0][0]
            assert "display notification" in cmd[2]

    def test_service_mode_shows_alert_dialog(self):
        with (
            patch(
                "transcribe.macos_permissions.is_accessibility_trusted",
                return_value=False,
            ),
            patch(
                "transcribe.macos_permissions._is_interactive",
                return_value=False,
            ),
            patch(
                "transcribe.macos_permissions._show_alert_dialog",
            ) as mock_alert,
        ):
            warn_if_not_trusted()
            mock_alert.assert_called_once()
            title = mock_alert.call_args[0][0]
            assert "Permission" in title
