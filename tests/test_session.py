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
