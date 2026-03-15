from unittest.mock import MagicMock, patch

from transcribe.factory import create_clipboard, create_hotkey_listener


class TestFactory:
    @patch("transcribe.factory.detect_session", return_value="x11")
    def test_create_hotkey_listener_x11(self, mock_detect):
        from transcribe.hotkey import HotkeyListener

        cb = MagicMock()
        listener = create_hotkey_listener(cb, {"ctrl"}, "a")
        assert isinstance(listener, HotkeyListener)

    @patch("transcribe.factory.detect_session", return_value="wayland")
    def test_create_hotkey_listener_wayland(self, mock_detect):
        from transcribe.wayland_hotkey import WaylandHotkeyListener

        cb = MagicMock()
        listener = create_hotkey_listener(cb, {"ctrl"}, "a")
        assert isinstance(listener, WaylandHotkeyListener)

    @patch("transcribe.factory.detect_session", return_value="x11")
    def test_create_clipboard_x11(self, mock_detect):
        from transcribe.clipboard import Clipboard

        cb = create_clipboard()
        assert isinstance(cb, Clipboard)

    @patch("transcribe.factory.detect_session", return_value="wayland")
    def test_create_clipboard_wayland(self, mock_detect):
        from transcribe.wayland_clipboard import WaylandClipboard

        cb = create_clipboard()
        assert isinstance(cb, WaylandClipboard)
