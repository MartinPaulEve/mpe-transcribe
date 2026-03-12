from unittest.mock import MagicMock, patch

from transcribe.hotkey import MODIFIER_MASKS, HotkeyListener


def _make_mock_display(events):
    """Create a mock Display that yields events then stops the listener."""
    mock_display = MagicMock()
    mock_root = MagicMock()
    mock_display.screen.return_value.root = mock_root
    mock_display.keysym_to_keycode.return_value = 47
    event_iter = iter(events)

    def next_event():
        try:
            return next(event_iter)
        except StopIteration:
            # Block forever (stop() will unblock via _running = False)
            import threading

            threading.Event().wait(0.01)
            return MagicMock(type=999)

    mock_display.next_event.side_effect = next_event
    return mock_display, mock_root


class TestHotkeyListener:
    def test_start_creates_daemon_thread(self):
        callback = MagicMock()
        listener = HotkeyListener(
            callback, modifiers={"ctrl", "shift"}, key=";"
        )
        with patch.object(listener, "_run"):
            listener.start()
            assert listener._thread is not None
            assert listener._thread.daemon is True
            listener._running = False

    def test_stop_without_start_is_safe(self):
        listener = HotkeyListener(MagicMock())
        listener.stop()

    def test_grabs_key_on_root_window(self):
        keypress_event = MagicMock(type=2)
        mock_display, mock_root = _make_mock_display([keypress_event])

        callback = MagicMock()
        listener = HotkeyListener(
            callback, modifiers={"ctrl", "shift"}, key=";"
        )

        def run_and_stop():
            with patch(
                "transcribe.hotkey.xdisplay.Display", return_value=mock_display
            ):
                listener._run()

        with patch(
            "transcribe.hotkey.xdisplay.Display", return_value=mock_display
        ):
            listener._running = True
            # Run in thread so we can stop it
            import threading

            t = threading.Thread(target=run_and_stop)
            t.start()
            import time

            time.sleep(0.05)
            listener._running = False
            t.join(timeout=1)

        # 4 grabs (one per lock mask combo)
        assert mock_root.grab_key.call_count == 4
        # Callback fired for the KeyPress event
        callback.assert_called_once()

    def test_callback_fires_on_keypress(self):
        keypress = MagicMock(type=2)
        mock_display, _ = _make_mock_display([keypress])

        callback = MagicMock()
        listener = HotkeyListener(callback, modifiers={"ctrl"}, key="a")

        import threading

        def run():
            with patch(
                "transcribe.hotkey.xdisplay.Display", return_value=mock_display
            ):
                listener._run()

        listener._running = True
        t = threading.Thread(target=run)
        t.start()
        import time

        time.sleep(0.05)
        listener._running = False
        t.join(timeout=1)

        callback.assert_called_once()

    def test_modifier_mask_combines_correctly(self):
        # ctrl=4, alt=8 -> combined=12
        assert MODIFIER_MASKS["ctrl"] | MODIFIER_MASKS["alt"] == 12
        assert MODIFIER_MASKS["ctrl"] | MODIFIER_MASKS["shift"] == 5
        assert MODIFIER_MASKS["super"] == 64

    def test_non_keypress_events_ignored(self):
        other_event = MagicMock(type=999)
        mock_display, _ = _make_mock_display([other_event])

        callback = MagicMock()
        listener = HotkeyListener(callback, modifiers={"ctrl"}, key="a")

        import threading

        def run():
            with patch(
                "transcribe.hotkey.xdisplay.Display", return_value=mock_display
            ):
                listener._run()

        listener._running = True
        t = threading.Thread(target=run)
        t.start()
        import time

        time.sleep(0.05)
        listener._running = False
        t.join(timeout=1)

        callback.assert_not_called()
