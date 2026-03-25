import time
from unittest.mock import MagicMock, patch

from transcribe.windows_hotkey import WindowsHotkeyListener


class TestWindowsHotkeyListener:
    def test_start_creates_daemon_thread(self):
        callback = MagicMock()
        listener = WindowsHotkeyListener(
            callback, modifiers={"ctrl", "shift"}, key=";"
        )
        with patch.object(listener, "_run"):
            listener.start()
            assert listener._thread is not None
            assert listener._thread.daemon is True
            listener._running = False

    def test_stop_without_start_is_safe(self):
        listener = WindowsHotkeyListener(MagicMock())
        listener.stop()

    def test_stop_sets_running_false(self):
        callback = MagicMock()
        listener = WindowsHotkeyListener(callback, modifiers={"ctrl"}, key="a")
        listener._running = True
        listener._thread = MagicMock()
        listener.stop()
        assert listener._running is False

    def test_default_modifiers_and_key(self):
        listener = WindowsHotkeyListener(MagicMock())
        assert listener._modifiers == {"ctrl", "shift"}
        assert listener._key == ";"

    def test_callback_fires_on_hotkey(self):
        callback = MagicMock()
        listener = WindowsHotkeyListener(
            callback, modifiers={"ctrl", "shift"}, key=";"
        )
        listener._on_hotkey()
        time.sleep(0.05)
        callback.assert_called_once()

    def test_rapid_presses_debounced(self):
        callback = MagicMock()
        listener = WindowsHotkeyListener(callback, modifiers={"ctrl"}, key="a")
        listener._on_hotkey()
        listener._on_hotkey()
        listener._on_hotkey()
        time.sleep(0.05)
        callback.assert_called_once()

    def test_press_after_debounce_window_fires(self):
        callback = MagicMock()
        listener = WindowsHotkeyListener(callback, modifiers={"ctrl"}, key="a")
        listener._on_hotkey()
        time.sleep(0.05)
        assert callback.call_count == 1
        listener._last_press = time.monotonic() - 0.5
        listener._on_hotkey()
        time.sleep(0.05)
        assert callback.call_count == 2

    def test_builds_pynput_hotkey_combination(self):
        listener = WindowsHotkeyListener(
            MagicMock(), modifiers={"ctrl", "shift"}, key=";"
        )
        combo = listener._build_hotkey_string()
        assert "<ctrl>" in combo
        assert "<shift>" in combo

    def test_modifier_mapping(self):
        listener = WindowsHotkeyListener(
            MagicMock(),
            modifiers={"ctrl", "alt", "super", "shift"},
            key="a",
        )
        combo = listener._build_hotkey_string()
        assert "<ctrl>" in combo
        assert "<alt>" in combo
        assert "<shift>" in combo
        assert "<cmd>" in combo
