import sys
from unittest.mock import MagicMock, patch

from transcribe.macos_permissions import (
    _is_interactive,
    _show_alert_dialog,
    _warn_missing_permission,
    get_microphone_status,
    is_accessibility_trusted,
    request_accessibility,
    request_microphone_access,
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


class TestRequestAccessibility:
    def test_returns_true_when_library_not_found(self):
        with patch(
            "transcribe.macos_permissions.ctypes"
        ) as mock_ctypes:
            mock_ctypes.util.find_library.return_value = None
            assert request_accessibility() is True

    def test_falls_back_to_is_trusted_on_error(self):
        with (
            patch(
                "transcribe.macos_permissions.ctypes"
            ) as mock_ctypes,
            patch(
                "transcribe.macos_permissions.is_accessibility_trusted",
                return_value=True,
            ) as mock_trusted,
        ):
            mock_ctypes.util.find_library.return_value = "/fake/path"
            mock_ctypes.cdll.LoadLibrary.side_effect = OSError("fail")
            assert request_accessibility() is True
            mock_trusted.assert_called_once()

    def test_returns_false_when_not_trusted(self):
        mock_lib = MagicMock()
        mock_lib.AXIsProcessTrustedWithOptions.return_value = False
        mock_cf = MagicMock()
        mock_cf.CFDictionaryCreate.return_value = MagicMock()

        def fake_find_library(name):
            return f"/fake/{name}"

        def fake_load_library(path):
            if "CoreFoundation" in path:
                return mock_cf
            return mock_lib

        with patch(
            "transcribe.macos_permissions.ctypes"
        ) as mock_ctypes:
            mock_ctypes.util.find_library = fake_find_library
            mock_ctypes.cdll.LoadLibrary = fake_load_library
            mock_ctypes.c_void_p = MagicMock()
            mock_ctypes.c_bool = bool
            mock_ctypes.c_long = int
            mock_ctypes.c_char_p = bytes
            mock_ctypes.POINTER = MagicMock()
            mock_ctypes.CFUNCTYPE = MagicMock()
            assert request_accessibility() is False


class TestGetMicrophoneStatus:
    def test_returns_unknown_when_objc_not_found(self):
        with patch(
            "transcribe.macos_permissions.ctypes"
        ) as mock_ctypes:
            mock_ctypes.util.find_library.return_value = None
            assert get_microphone_status() == "unknown"

    def test_returns_unknown_on_load_error(self):
        with patch(
            "transcribe.macos_permissions.ctypes"
        ) as mock_ctypes:
            mock_ctypes.util.find_library.return_value = "/fake"
            mock_ctypes.cdll.LoadLibrary.side_effect = OSError("fail")
            assert get_microphone_status() == "unknown"

    def test_returns_valid_status_string(self):
        # On non-macOS, this returns "unknown" since the ObjC
        # runtime isn't available. Verify it doesn't crash and
        # returns one of the expected values.
        status = get_microphone_status()
        assert status in {
            "authorized",
            "denied",
            "restricted",
            "not_determined",
            "unknown",
        }


class TestRequestMicrophoneAccess:
    def test_returns_true_when_granted(self):
        mock_sd = sys.modules["sounddevice"]
        mock_sd.reset_mock()
        with patch(
            "transcribe.macos_permissions.get_microphone_status",
            return_value="authorized",
        ):
            assert request_microphone_access() is True
        mock_sd.InputStream.assert_called_once()

    def test_returns_false_when_denied(self):
        mock_sd = sys.modules["sounddevice"]
        mock_sd.reset_mock()
        with patch(
            "transcribe.macos_permissions.get_microphone_status",
            return_value="denied",
        ):
            assert request_microphone_access() is False

    def test_returns_false_on_stream_error(self):
        mock_sd = sys.modules["sounddevice"]
        mock_sd.reset_mock()
        mock_sd.InputStream.side_effect = Exception("no mic")
        assert request_microphone_access() is False
        mock_sd.InputStream.side_effect = None  # reset


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
            _show_alert_dialog("Title", "Body", "x-apple:test")
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
            _show_alert_dialog("Title", "Body", "x-apple:test-url")
            assert mock_sub.run.call_count == 2
            open_cmd = mock_sub.run.call_args_list[1][0][0]
            assert open_cmd[0] == "open"
            assert open_cmd[1] == "x-apple:test-url"

    def test_does_not_raise_on_failure(self):
        with patch(
            "transcribe.macos_permissions.subprocess"
        ) as mock_sub:
            mock_sub.run.side_effect = Exception("fail")
            _show_alert_dialog("Title", "Body", "x-apple:test")


class TestWarnMissingPermission:
    def test_terminal_mode_sends_notification(self):
        with (
            patch(
                "transcribe.macos_permissions._is_interactive",
                return_value=True,
            ),
            patch(
                "transcribe.macos_permissions.subprocess"
            ) as mock_sub,
        ):
            _warn_missing_permission("Test", "Fix it.", "x-apple:url")
            mock_sub.run.assert_called_once()
            cmd = mock_sub.run.call_args[0][0]
            assert "display notification" in cmd[2]
            assert "Test" in cmd[2]

    def test_service_mode_shows_alert_dialog(self):
        with (
            patch(
                "transcribe.macos_permissions._is_interactive",
                return_value=False,
            ),
            patch(
                "transcribe.macos_permissions._show_alert_dialog",
            ) as mock_alert,
        ):
            _warn_missing_permission("Test", "Fix it.", "x-apple:url")
            mock_alert.assert_called_once()
            assert "Test" in mock_alert.call_args[0][0]


class TestWarnIfNotTrusted:
    def test_no_warnings_when_all_granted(self):
        with (
            patch(
                "transcribe.macos_permissions.request_accessibility",
                return_value=True,
            ),
            patch(
                "transcribe.macos_permissions.get_microphone_status",
                return_value="authorized",
            ),
            patch(
                "transcribe.macos_permissions._warn_missing_permission",
            ) as mock_warn,
        ):
            warn_if_not_trusted()
            mock_warn.assert_not_called()

    def test_warns_when_accessibility_missing(self):
        with (
            patch(
                "transcribe.macos_permissions.request_accessibility",
                return_value=False,
            ),
            patch(
                "transcribe.macos_permissions.get_microphone_status",
                return_value="authorized",
            ),
            patch(
                "transcribe.macos_permissions._warn_missing_permission",
            ) as mock_warn,
        ):
            warn_if_not_trusted()
            mock_warn.assert_called_once()
            assert mock_warn.call_args[0][0] == "Accessibility"

    def test_warns_when_microphone_denied(self):
        with (
            patch(
                "transcribe.macos_permissions.request_accessibility",
                return_value=True,
            ),
            patch(
                "transcribe.macos_permissions.get_microphone_status",
                return_value="denied",
            ),
            patch(
                "transcribe.macos_permissions._warn_missing_permission",
            ) as mock_warn,
        ):
            warn_if_not_trusted()
            mock_warn.assert_called_once()
            assert mock_warn.call_args[0][0] == "Microphone"

    def test_requests_mic_when_not_determined_and_interactive(self):
        with (
            patch(
                "transcribe.macos_permissions.request_accessibility",
                return_value=True,
            ),
            patch(
                "transcribe.macos_permissions.get_microphone_status",
                return_value="not_determined",
            ),
            patch(
                "transcribe.macos_permissions._is_interactive",
                return_value=True,
            ),
            patch(
                "transcribe.macos_permissions.request_microphone_access",
                return_value=True,
            ) as mock_req,
            patch(
                "transcribe.macos_permissions._warn_missing_permission",
            ) as mock_warn,
        ):
            warn_if_not_trusted()
            mock_req.assert_called_once()
            mock_warn.assert_not_called()

    def test_warns_when_mic_request_denied_interactively(self):
        with (
            patch(
                "transcribe.macos_permissions.request_accessibility",
                return_value=True,
            ),
            patch(
                "transcribe.macos_permissions.get_microphone_status",
                return_value="not_determined",
            ),
            patch(
                "transcribe.macos_permissions._is_interactive",
                return_value=True,
            ),
            patch(
                "transcribe.macos_permissions.request_microphone_access",
                return_value=False,
            ),
            patch(
                "transcribe.macos_permissions._warn_missing_permission",
            ) as mock_warn,
        ):
            warn_if_not_trusted()
            mock_warn.assert_called_once()
            assert mock_warn.call_args[0][0] == "Microphone"

    def test_warns_when_not_determined_and_not_interactive(self):
        with (
            patch(
                "transcribe.macos_permissions.request_accessibility",
                return_value=True,
            ),
            patch(
                "transcribe.macos_permissions.get_microphone_status",
                return_value="not_determined",
            ),
            patch(
                "transcribe.macos_permissions._is_interactive",
                return_value=False,
            ),
            patch(
                "transcribe.macos_permissions._warn_missing_permission",
            ) as mock_warn,
        ):
            warn_if_not_trusted()
            mock_warn.assert_called_once()
            assert mock_warn.call_args[0][0] == "Microphone"

    def test_skips_mic_check_when_unknown(self):
        with (
            patch(
                "transcribe.macos_permissions.request_accessibility",
                return_value=True,
            ),
            patch(
                "transcribe.macos_permissions.get_microphone_status",
                return_value="unknown",
            ),
            patch(
                "transcribe.macos_permissions._warn_missing_permission",
            ) as mock_warn,
        ):
            warn_if_not_trusted()
            mock_warn.assert_not_called()
