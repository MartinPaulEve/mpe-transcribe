import time
from unittest.mock import MagicMock, patch

from transcribe.macos_hotkey import MacOSHotkeyListener


class TestMacOSHotkeyListener:
    def test_start_creates_daemon_thread(self):
        callback = MagicMock()
        listener = MacOSHotkeyListener(
            callback, modifiers={"super", "shift"}, key=";"
        )
        with patch.object(listener, "_run"):
            listener.start()
            assert listener._thread is not None
            assert listener._thread.daemon is True
            listener._running = False

    def test_stop_without_start_is_safe(self):
        listener = MacOSHotkeyListener(MagicMock())
        listener.stop()

    def test_stop_sets_running_false(self):
        callback = MagicMock()
        listener = MacOSHotkeyListener(
            callback, modifiers={"super"}, key="a"
        )
        listener._running = True
        listener._thread = MagicMock()
        listener.stop()
        assert listener._running is False

    def test_default_modifiers_and_key(self):
        listener = MacOSHotkeyListener(MagicMock())
        assert listener._modifiers == {"ctrl", "shift"}
        assert listener._key == ";"

    def test_callback_fires_on_hotkey(self):
        callback = MagicMock()
        listener = MacOSHotkeyListener(
            callback, modifiers={"super", "shift"}, key=";"
        )

        # Simulate the listener calling _on_hotkey
        listener._on_hotkey()
        time.sleep(0.05)
        callback.assert_called_once()

    def test_rapid_presses_debounced(self):
        callback = MagicMock()
        listener = MacOSHotkeyListener(
            callback, modifiers={"super"}, key="a"
        )

        listener._on_hotkey()
        listener._on_hotkey()
        listener._on_hotkey()
        time.sleep(0.05)
        # Only first should fire due to debounce
        callback.assert_called_once()

    def test_press_after_debounce_window_fires(self):
        callback = MagicMock()
        listener = MacOSHotkeyListener(
            callback, modifiers={"super"}, key="a"
        )

        listener._on_hotkey()
        time.sleep(0.05)
        assert callback.call_count == 1

        # Wait past debounce window
        listener._last_press = time.monotonic() - 0.5
        listener._on_hotkey()
        time.sleep(0.05)
        assert callback.call_count == 2

    def test_builds_pynput_hotkey_combination(self):
        listener = MacOSHotkeyListener(
            MagicMock(), modifiers={"super", "shift"}, key=";"
        )
        combo = listener._build_hotkey_string()
        # Should contain pynput-style modifier tokens
        assert "<cmd>" in combo or "<super>" in combo
        assert "<shift>" in combo

    def test_modifier_mapping(self):
        listener = MacOSHotkeyListener(
            MagicMock(), modifiers={"ctrl", "alt", "super", "shift"}, key="a"
        )
        combo = listener._build_hotkey_string()
        assert "<ctrl>" in combo
        assert "<alt>" in combo
        assert "<shift>" in combo
