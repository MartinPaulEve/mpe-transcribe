import time
from unittest.mock import MagicMock, patch

import numpy as np

from transcribe.app import AppState, TranscribeApp


class TestApp:
    TEST_CONFIG = {
        "model": "nvidia/parakeet-tdt-0.6b-v3",
        "hotkey": "ctrl+shift+;",
    }

    def _make_app(self):
        mock_hk = MagicMock()
        mock_cb = MagicMock()
        mock_trans = MagicMock()
        mock_notif = MagicMock()
        with (
            patch("transcribe.app.AudioRecorder") as mock_rec_cls,
            patch(
                "transcribe.app.create_transcriber",
                return_value=mock_trans,
            ),
            patch(
                "transcribe.app.create_hotkey_listener",
                return_value=mock_hk,
            ),
            patch(
                "transcribe.app.create_notifier",
                return_value=mock_notif,
            ),
            patch(
                "transcribe.app.create_clipboard",
                return_value=mock_cb,
            ),
        ):
            app = TranscribeApp(config=self.TEST_CONFIG)
            return (
                app,
                mock_rec_cls.return_value,
                mock_trans,
                mock_hk,
                mock_notif,
                mock_cb,
            )

    def test_initial_state_is_idle(self):
        app, *_ = self._make_app()
        assert app.state == AppState.IDLE

    def test_toggle_from_idle_starts_recording(self):
        app, mock_rec, _, _, mock_notif, _ = self._make_app()
        app.toggle()
        assert app.state == AppState.RECORDING
        mock_rec.start.assert_called_once()
        mock_notif.notify_and_ding.assert_called_once()

    def test_toggle_from_recording_starts_transcription(self):
        app, mock_rec, mock_trans, _, _, _ = self._make_app()
        mock_rec.stop.return_value = np.ones(16000, dtype=np.float32)
        mock_trans.transcribe.return_value = "hello"

        app.toggle()  # IDLE -> RECORDING
        app.toggle()  # RECORDING -> TRANSCRIBING

        mock_rec.stop.assert_called_once()
        time.sleep(0.1)
        mock_trans.transcribe.assert_called_once()

    def test_toggle_during_transcribing_is_ignored(self):
        app, mock_rec, _, _, _, _ = self._make_app()
        app._state = AppState.TRANSCRIBING
        app.toggle()
        assert app.state == AppState.TRANSCRIBING
        mock_rec.start.assert_not_called()

    def test_transcription_pastes_result(self):
        app, mock_rec, mock_trans, _, _, mock_cb = self._make_app()
        mock_rec.stop.return_value = np.ones(16000, dtype=np.float32)
        mock_trans.transcribe.return_value = "transcribed text"

        app.toggle()
        app.toggle()

        time.sleep(0.1)
        mock_cb.paste_text.assert_called_once_with("transcribed text")
        assert app.state == AppState.IDLE

    def test_empty_transcription_skips_paste(self):
        app, mock_rec, mock_trans, _, _, mock_cb = self._make_app()
        mock_rec.stop.return_value = np.ones(16000, dtype=np.float32)
        mock_trans.transcribe.return_value = ""

        app.toggle()
        app.toggle()

        time.sleep(0.1)
        mock_cb.paste_text.assert_not_called()

    def test_transcription_error_returns_to_idle(self):
        app, mock_rec, mock_trans, _, _, mock_cb = self._make_app()
        mock_rec.stop.return_value = np.ones(16000, dtype=np.float32)
        mock_trans.transcribe.side_effect = RuntimeError("model error")

        app.toggle()
        app.toggle()

        time.sleep(0.1)
        assert app.state == AppState.IDLE
        mock_cb.paste_text.assert_not_called()

    def test_empty_audio_returns_to_idle(self):
        app, mock_rec, mock_trans, _, mock_notif, _ = self._make_app()
        mock_rec.stop.return_value = np.array([], dtype=np.float32)

        app.toggle()  # IDLE -> RECORDING
        app.toggle()  # RECORDING -> IDLE (too short)

        assert app.state == AppState.IDLE
        mock_trans.transcribe.assert_not_called()
        mock_notif.notify.assert_called_once_with(
            "Transcribe", "Recording too short"
        )

    def test_silent_audio_returns_to_idle(self):
        app, mock_rec, mock_trans, _, mock_notif, _ = self._make_app()
        # All zeros — simulates mic returning silence (no permission)
        mock_rec.stop.return_value = np.zeros(16000, dtype=np.float32)

        app.toggle()  # IDLE -> RECORDING
        app.toggle()  # RECORDING -> IDLE (silent)

        assert app.state == AppState.IDLE
        mock_trans.transcribe.assert_not_called()
        mock_notif.notify.assert_called_once_with(
            "Transcribe",
            "No audio detected — check mic permissions",
        )

    def test_recording_error_returns_to_idle(self):
        app, mock_rec, _, _, mock_notif, _ = self._make_app()
        mock_rec.start.side_effect = RuntimeError("PortAudio error")

        app.toggle()

        assert app.state == AppState.IDLE
        mock_notif.notify.assert_called_once_with(
            "Transcribe", "Mic error — see logs"
        )

    def test_run_notifies_when_ready(self):
        app, _, mock_trans, mock_hk, mock_notif, _ = self._make_app()

        # Set stop event immediately so run() returns
        app._stop_event.set()
        with patch("transcribe.app.signal"):
            app.run()

        mock_trans.load_model.assert_called_once()
        mock_notif.notify_and_ding.assert_called_once_with(
            "Transcribe", "Ready"
        )

    def test_shutdown_stops_hotkey(self):
        app, _, _, mock_hk, _, _ = self._make_app()
        app.shutdown()
        mock_hk.stop.assert_called_once()

    def test_shutdown_stops_active_recording(self):
        app, mock_rec, _, mock_hk, _, _ = self._make_app()
        mock_rec.stop.return_value = np.array([], dtype=np.float32)
        app._state = AppState.RECORDING
        app.shutdown()
        mock_rec.stop.assert_called_once()
        assert app.state == AppState.IDLE
        mock_hk.stop.assert_called_once()

    @patch(
        "transcribe.app.check_default_input_device",
        return_value=(False, "USB audio device is in error state"),
    )
    def test_device_error_prevents_recording(self, mock_check):
        app, mock_rec, _, _, mock_notif, _ = self._make_app()
        app.toggle()
        assert app.state == AppState.IDLE
        mock_rec.start.assert_not_called()
        mock_notif.notify.assert_called_once()
        assert "error" in mock_notif.notify.call_args[0][1].lower()

    @patch(
        "transcribe.app.check_default_input_device",
        return_value=(True, ""),
    )
    def test_device_ok_allows_recording(self, mock_check):
        app, mock_rec, _, _, _, _ = self._make_app()
        app.toggle()
        assert app.state == AppState.RECORDING
        mock_rec.start.assert_called_once()
