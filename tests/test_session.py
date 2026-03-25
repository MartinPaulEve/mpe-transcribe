from unittest.mock import patch

from transcribe.session import detect_session


class TestDetectSession:
    @patch.dict("os.environ", {"XDG_SESSION_TYPE": "wayland"}, clear=False)
    def test_xdg_session_type_wayland(self):
        assert detect_session() == "wayland"

    @patch.dict("os.environ", {"XDG_SESSION_TYPE": "x11"}, clear=False)
    def test_xdg_session_type_x11(self):
        assert detect_session() == "x11"

    @patch.dict(
        "os.environ",
        {"XDG_SESSION_TYPE": "", "WAYLAND_DISPLAY": "wayland-0"},
        clear=False,
    )
    def test_wayland_display_fallback(self):
        assert detect_session() == "wayland"

    @patch.dict(
        "os.environ",
        {"XDG_SESSION_TYPE": "", "WAYLAND_DISPLAY": ""},
        clear=False,
    )
    def test_defaults_to_x11(self):
        assert detect_session() == "x11"

    @patch.dict(
        "os.environ",
        {},
        clear=True,
    )
    def test_no_env_vars_defaults_to_x11(self):
        assert detect_session() == "x11"

    @patch("transcribe.session.platform.system", return_value="Darwin")
    def test_macos_detected_on_darwin(self, mock_system):
        assert detect_session() == "macos"

    @patch("transcribe.session.platform.system", return_value="Linux")
    @patch.dict("os.environ", {"XDG_SESSION_TYPE": "x11"}, clear=False)
    def test_linux_not_detected_as_macos(self, mock_system):
        assert detect_session() == "x11"

    @patch("transcribe.session.platform.system", return_value="Darwin")
    @patch.dict("os.environ", {"XDG_SESSION_TYPE": "x11"}, clear=False)
    def test_macos_takes_priority_over_x11(self, mock_system):
        """macOS detection should take priority over XDG env vars."""
        assert detect_session() == "macos"

    @patch("transcribe.session.platform.system", return_value="Windows")
    def test_windows_detected(self, mock_system):
        assert detect_session() == "windows"

    @patch("transcribe.session.platform.system", return_value="Windows")
    @patch.dict("os.environ", {"XDG_SESSION_TYPE": "x11"}, clear=False)
    def test_windows_takes_priority_over_x11_env(self, mock_system):
        """Windows detection should take priority over XDG env vars."""
        assert detect_session() == "windows"
