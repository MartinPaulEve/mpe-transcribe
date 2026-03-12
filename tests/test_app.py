import time
from unittest.mock import patch

import numpy as np

from transcribe.app import AppState, TranscribeApp


class TestApp:
    TEST_CONFIG = {
        "model": "nvidia/parakeet-tdt-0.6b-v3",
        "hotkey": "ctrl+shift+;",
    }

    def _make_app(self):
        with (
            patch("transcribe.app.AudioRecorder") as mock_rec_cls,
            patch("transcribe.app.Transcriber") as mock_trans_cls,
            patch("transcribe.app.HotkeyListener") as mock_hk_cls,
            patch("transcribe.app.AppNotifier") as mock_notif_cls,
            patch("transcribe.app.Clipboard") as mock_cb_cls,
        ):
            app = TranscribeApp(config=self.TEST_CONFIG)
            return (
                app,
                mock_rec_cls.return_value,
                mock_trans_cls.return_value,
                mock_hk_cls.return_value,
                mock_notif_cls.return_value,
                mock_cb_cls.return_value,
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

    def test_shutdown_stops_hotkey(self):
        app, _, _, mock_hk, _, _ = self._make_app()
        app.shutdown()
        mock_hk.stop.assert_called_once()
