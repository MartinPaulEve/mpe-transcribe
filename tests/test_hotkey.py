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

    def test_rapid_keypresses_debounced(self):
        """Auto-repeat KeyPress events are ignored."""
        # Simulate 3 rapid KeyPress events (as X11 auto-repeat would generate)
        events = [MagicMock(type=2) for _ in range(3)]
        mock_display, _ = _make_mock_display(events)

        callback = MagicMock()
        listener = HotkeyListener(callback, modifiers={"ctrl"}, key="a")

        import threading
        import time

        def run():
            with patch(
                "transcribe.hotkey.xdisplay.Display", return_value=mock_display
            ):
                listener._run()

        listener._running = True
        t = threading.Thread(target=run)
        t.start()
        time.sleep(0.1)
        listener._running = False
        t.join(timeout=1)

        # Only the first keypress should fire; the rest are debounced
        callback.assert_called_once()

    def test_keypress_after_debounce_window_fires(self):
        """A KeyPress after the debounce window should fire the callback."""
        import threading
        import time

        callback = MagicMock()
        listener = HotkeyListener(callback, modifiers={"ctrl"}, key="a")

        # We'll manually drive the debounce logic by simulating events
        # with a delay between them that exceeds the debounce window
        event1 = MagicMock(type=2)
        event2 = MagicMock(type=2)
        call_count = 0

        def next_event():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return event1
            elif call_count == 2:
                # Wait longer than debounce window before returning 2nd event
                time.sleep(0.4)
                return event2
            else:
                threading.Event().wait(0.01)
                return MagicMock(type=999)

        mock_display = MagicMock()
        mock_display.screen.return_value.root = MagicMock()
        mock_display.keysym_to_keycode.return_value = 47
        mock_display.next_event.side_effect = next_event

        def run():
            with patch(
                "transcribe.hotkey.xdisplay.Display", return_value=mock_display
            ):
                listener._run()

        listener._running = True
        t = threading.Thread(target=run)
        t.start()
        time.sleep(0.6)
        listener._running = False
        t.join(timeout=1)

        # Both keypresses should fire (separated by > debounce window)
        assert callback.call_count == 2
