from unittest.mock import MagicMock, patch

from transcribe.wayland_hotkey import WaylandHotkeyListener


def _make_ecodes_mock():
    """Create a mock ecodes module with real key constants."""
    ecodes = MagicMock()
    ecodes.KEY_LEFTCTRL = 29
    ecodes.KEY_RIGHTCTRL = 97
    ecodes.KEY_LEFTSHIFT = 42
    ecodes.KEY_RIGHTSHIFT = 54
    ecodes.KEY_LEFTALT = 56
    ecodes.KEY_RIGHTALT = 100
    ecodes.KEY_LEFTMETA = 125
    ecodes.KEY_RIGHTMETA = 126
    ecodes.KEY_SEMICOLON = 39
    ecodes.KEY_A = 30
    ecodes.KEY_Z = 44
    ecodes.EV_KEY = 1
    ecodes.ecodes = {
        "KEY_LEFTCTRL": 29,
        "KEY_RIGHTCTRL": 97,
        "KEY_LEFTSHIFT": 42,
        "KEY_RIGHTSHIFT": 54,
        "KEY_LEFTALT": 56,
        "KEY_RIGHTALT": 100,
        "KEY_LEFTMETA": 125,
        "KEY_RIGHTMETA": 126,
        "KEY_SEMICOLON": 39,
        "KEY_A": 30,
        "KEY_Z": 44,
        "EV_KEY": 1,
    }
    return ecodes


class TestWaylandHotkeyListener:
    @patch("transcribe.wayland_hotkey.ecodes", _make_ecodes_mock())
    def test_hotkey_fires_callback(self):
        callback = MagicMock()
        listener = WaylandHotkeyListener(
            callback, modifiers={"ctrl", "shift"}, key=";"
        )

        # Simulate key events: press ctrl, press shift, press ;
        events = [
            MagicMock(type=1, code=29, value=1),  # ctrl down
            MagicMock(type=1, code=42, value=1),  # shift down
            MagicMock(type=1, code=39, value=1),  # ; down
        ]
        for e in events:
            e.type = 1  # EV_KEY

        listener._handle_event(events[0])
        listener._handle_event(events[1])
        listener._handle_event(events[2])

        callback.assert_called_once()

    @patch("transcribe.wayland_hotkey.ecodes", _make_ecodes_mock())
    def test_incomplete_modifiers_ignored(self):
        callback = MagicMock()
        listener = WaylandHotkeyListener(
            callback, modifiers={"ctrl", "shift"}, key=";"
        )

        # Only ctrl + ;, missing shift
        events = [
            MagicMock(type=1, code=29, value=1),  # ctrl down
            MagicMock(type=1, code=39, value=1),  # ; down
        ]

        for e in events:
            listener._handle_event(e)

        callback.assert_not_called()

    @patch("transcribe.wayland_hotkey.ecodes", _make_ecodes_mock())
    def test_debounce_prevents_rapid_fire(self):
        callback = MagicMock()
        listener = WaylandHotkeyListener(
            callback, modifiers={"ctrl", "shift"}, key=";"
        )

        def press_combo():
            listener._handle_event(MagicMock(type=1, code=29, value=1))  # ctrl
            listener._handle_event(
                MagicMock(type=1, code=42, value=1)
            )  # shift
            listener._handle_event(MagicMock(type=1, code=39, value=1))  # ;

        press_combo()
        press_combo()  # Immediate repeat should be debounced

        assert callback.call_count == 1

    @patch("transcribe.wayland_hotkey.ecodes", _make_ecodes_mock())
    def test_modifier_release_clears_state(self):
        callback = MagicMock()
        listener = WaylandHotkeyListener(
            callback, modifiers={"ctrl", "shift"}, key=";"
        )

        # Press ctrl+shift+;
        listener._handle_event(MagicMock(type=1, code=29, value=1))
        listener._handle_event(MagicMock(type=1, code=42, value=1))
        listener._handle_event(MagicMock(type=1, code=39, value=1))
        assert callback.call_count == 1

        # Release all keys
        listener._handle_event(MagicMock(type=1, code=29, value=0))
        listener._handle_event(MagicMock(type=1, code=42, value=0))
        listener._handle_event(MagicMock(type=1, code=39, value=0))

        # Wait past debounce window
        listener._last_press = 0.0

        # Press again
        listener._handle_event(MagicMock(type=1, code=29, value=1))
        listener._handle_event(MagicMock(type=1, code=42, value=1))
        listener._handle_event(MagicMock(type=1, code=39, value=1))
        assert callback.call_count == 2

    @patch("transcribe.wayland_hotkey.ecodes", _make_ecodes_mock())
    def test_stop_is_safe_when_not_started(self):
        callback = MagicMock()
        listener = WaylandHotkeyListener(callback, modifiers={"ctrl"}, key="a")
        # Should not raise
        listener.stop()

    @patch("transcribe.wayland_hotkey.ecodes", _make_ecodes_mock())
    def test_right_modifier_works(self):
        callback = MagicMock()
        listener = WaylandHotkeyListener(callback, modifiers={"ctrl"}, key=";")

        # Use right ctrl instead of left
        listener._handle_event(MagicMock(type=1, code=97, value=1))  # rctrl
        listener._handle_event(MagicMock(type=1, code=39, value=1))  # ;

        callback.assert_called_once()
