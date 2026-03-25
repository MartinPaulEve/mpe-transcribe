from unittest.mock import MagicMock, patch

from transcribe.factory import (
    create_clipboard,
    create_hotkey_listener,
    create_notifier,
    create_transcriber,
)


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

    @patch("transcribe.factory.detect_session", return_value="macos")
    def test_create_hotkey_listener_macos(self, mock_detect):
        from transcribe.macos_hotkey import MacOSHotkeyListener

        cb = MagicMock()
        listener = create_hotkey_listener(cb, {"super"}, "a")
        assert isinstance(listener, MacOSHotkeyListener)

    @patch.dict("os.environ", {"TRANSCRIBE_LAUNCHER": "1"})
    @patch("transcribe.factory.detect_session", return_value="macos")
    def test_create_hotkey_listener_macos_launcher(self, mock_detect):
        from transcribe.signal_hotkey import SignalHotkeyListener

        cb = MagicMock()
        listener = create_hotkey_listener(cb, {"super"}, "'")
        assert isinstance(listener, SignalHotkeyListener)

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

    @patch("transcribe.factory.detect_session", return_value="macos")
    def test_create_clipboard_macos(self, mock_detect):
        from transcribe.macos_clipboard import MacOSClipboard

        cb = create_clipboard()
        assert isinstance(cb, MacOSClipboard)

    @patch("transcribe.factory.detect_session", return_value="x11")
    def test_create_transcriber_linux(self, mock_detect):
        from transcribe.transcriber import Transcriber

        t = create_transcriber("nvidia/parakeet-tdt-0.6b-v3")
        assert isinstance(t, Transcriber)

    @patch("transcribe.factory.detect_session", return_value="macos")
    def test_create_transcriber_macos(self, mock_detect):
        from transcribe.macos_transcriber import MacOSTranscriber

        t = create_transcriber("mlx-community/whisper-large-v3-turbo")
        assert isinstance(t, MacOSTranscriber)

    @patch("transcribe.factory.detect_session", return_value="x11")
    def test_create_notifier_linux(self, mock_detect):
        from transcribe.notifier import AppNotifier

        n = create_notifier()
        assert isinstance(n, AppNotifier)

    @patch("transcribe.factory.detect_session", return_value="macos")
    def test_create_notifier_macos(self, mock_detect):
        from transcribe.macos_notifier import MacOSNotifier

        n = create_notifier()
        assert isinstance(n, MacOSNotifier)

    @patch("transcribe.factory.detect_session", return_value="windows")
    def test_create_hotkey_listener_windows(self, mock_detect):
        from transcribe.windows_hotkey import WindowsHotkeyListener

        cb = MagicMock()
        listener = create_hotkey_listener(cb, {"ctrl"}, "a")
        assert isinstance(listener, WindowsHotkeyListener)

    @patch("transcribe.factory.detect_session", return_value="windows")
    def test_create_clipboard_windows(self, mock_detect):
        from transcribe.windows_clipboard import WindowsClipboard

        cb = create_clipboard()
        assert isinstance(cb, WindowsClipboard)

    @patch("transcribe.factory.detect_session", return_value="windows")
    def test_create_transcriber_windows(self, mock_detect):
        from transcribe.windows_transcriber import WindowsTranscriber

        t = create_transcriber("nvidia/parakeet-tdt-0.6b-v3")
        assert isinstance(t, WindowsTranscriber)

    @patch("transcribe.factory.detect_session", return_value="windows")
    def test_create_notifier_windows(self, mock_detect):
        from transcribe.windows_notifier import WindowsNotifier

        n = create_notifier()
        assert isinstance(n, WindowsNotifier)
