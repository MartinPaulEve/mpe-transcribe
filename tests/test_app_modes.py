import base64
import os
import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from tests.test_notifier import RecordingNotifier
from transcribe.app import ClientApp, HostApp, main
from transcribe.config import NETWORK_DEFAULTS, ConfigError
from transcribe.net import crypto, protocol
from transcribe.notifier import FilteredNotifier

PSK = b"\x07" * 32
PSK_B64 = base64.b64encode(PSK).decode()
KEY = crypto.derive_key(PSK)

CLIENT_ADDR = ("10.211.55.3", 40001)


class FakeTransport:
    def __init__(self):
        self.sent = []

    def sendto(self, data, addr):
        self.sent.append((data, addr))

    def recvfrom(self, bufsize=4096):
        return None

    def close(self):
        pass


def make_config(mode, **net_overrides):
    network = dict(NETWORK_DEFAULTS)
    network["mode"] = mode
    network.update(net_overrides)
    return {
        "model": "test-model",
        "hotkey": "ctrl+shift+;",
        "replacements": {},
        "custom_terms": [],
        "custom_terms_threshold": 0.8,
        "network": network,
    }


def seal_datagram(msg_type, body, key=KEY):
    plaintext = protocol.encode_body(body)
    nonce, ct = crypto.seal(key, protocol.header(msg_type), plaintext)
    return protocol.encode_frame(msg_type, nonce, ct)


def open_datagram(data, key=KEY):
    msg_type, nonce, ct = protocol.decode_frame(data)
    plaintext = crypto.open_sealed(key, protocol.header(msg_type), nonce, ct)
    return msg_type, protocol.decode_body(plaintext)


def sent_of_type(transport, msg_type, addr=None):
    out = []
    for data, dest in transport.sent:
        if addr is not None and dest != addr:
            continue
        decoded_type, body = open_datagram(data)
        if decoded_type == msg_type:
            out.append((body, dest))
    return out


def make_host_app(config=None, notifier=None, **net_overrides):
    config = config or make_config("host", **net_overrides)
    transport = FakeTransport()
    mock_trans = MagicMock()
    mock_notif = notifier if notifier is not None else MagicMock()
    mock_cb = MagicMock()
    mock_hk = MagicMock()
    with (
        patch("transcribe.recorder.AudioRecorder") as mock_rec_cls,
        patch("transcribe.app.create_transcriber", return_value=mock_trans),
        patch(
            "transcribe.app.create_hotkey_listener", return_value=mock_hk
        ) as mock_hk_factory,
        patch("transcribe.app.create_notifier", return_value=mock_notif),
        patch("transcribe.app.create_clipboard", return_value=mock_cb),
        patch.dict(os.environ, {"TRANSCRIBE_PSK": PSK_B64}),
    ):
        app = HostApp(config=config, transport=transport)
    return (
        app,
        transport,
        mock_rec_cls.return_value,
        mock_trans,
        mock_notif,
        mock_cb,
        mock_hk_factory,
    )


def make_client_app(config=None, notifier=None, **net_overrides):
    config = config or make_config("client", **net_overrides)
    transport = FakeTransport()
    mock_notif = notifier if notifier is not None else MagicMock()
    mock_cb = MagicMock()
    mock_hk = MagicMock()
    with (
        patch("transcribe.app.create_transcriber") as mock_trans_factory,
        patch(
            "transcribe.app.create_hotkey_listener", return_value=mock_hk
        ) as mock_hk_factory,
        patch("transcribe.app.create_notifier", return_value=mock_notif),
        patch("transcribe.app.create_clipboard", return_value=mock_cb),
        patch.dict(os.environ, {"TRANSCRIBE_PSK": PSK_B64}),
    ):
        app = ClientApp(config=config, transport=transport)
    return (
        app,
        transport,
        mock_notif,
        mock_cb,
        mock_hk_factory,
        mock_trans_factory,
    )


def wait_for(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


def send_start(app, session="sess1", label="vm"):
    body = protocol.new_body(time.time(), client=label, session=session)
    app.host.handle_datagram(
        seal_datagram(protocol.TYPE_START, body), CLIENT_ADDR
    )
    return body


def send_stop(app, session="sess1", label="vm"):
    body = protocol.new_body(time.time(), client=label, session=session)
    app.host.handle_datagram(
        seal_datagram(protocol.TYPE_STOP, body), CLIENT_ADDR
    )
    return body


@patch("transcribe.app.check_default_input_device", return_value=(True, ""))
class TestHostApp:
    def test_network_start_begins_recording(self, mock_check):
        app, transport, mock_rec, _, mock_notif, _, _ = make_host_app()
        send_start(app)
        assert app.host.state == "recording"
        mock_rec.start.assert_called_once()
        mock_notif.notify_and_ding.assert_called()

    def test_network_stop_transcribes_and_sends_text(self, mock_check):
        app, transport, mock_rec, mock_trans, _, _, _ = make_host_app()
        mock_rec.stop.return_value = np.ones(16000, dtype=np.float32)
        mock_trans.transcribe.return_value = "hello world"
        send_start(app)
        send_stop(app)
        time.sleep(0.2)
        texts = sent_of_type(transport, protocol.TYPE_TEXT, CLIENT_ADDR)
        assert len(texts) == 1
        assert protocol.join_message([texts[0][0]]) == "hello world"
        assert app.host.state == "idle"

    def test_silent_audio_finishes_session_without_text(self, mock_check):
        app, transport, mock_rec, mock_trans, _, _, _ = make_host_app()
        mock_rec.stop.return_value = np.zeros(16000, dtype=np.float32)
        send_start(app)
        send_stop(app)
        time.sleep(0.2)
        assert sent_of_type(transport, protocol.TYPE_TEXT) == []
        mock_trans.transcribe.assert_not_called()
        assert app.host.state == "idle"

    def test_transcription_error_recovers_to_idle(self, mock_check):
        app, transport, mock_rec, mock_trans, _, _, _ = make_host_app()
        mock_rec.stop.return_value = np.ones(16000, dtype=np.float32)
        mock_trans.transcribe.side_effect = RuntimeError("boom")
        send_start(app)
        send_stop(app)
        time.sleep(0.2)
        assert sent_of_type(transport, protocol.TYPE_TEXT) == []
        assert app.host.state == "idle"

    def test_also_paste_locally_pastes_on_host(self, mock_check):
        app, transport, mock_rec, mock_trans, _, mock_cb, _ = make_host_app(
            also_paste_locally=True
        )
        mock_rec.stop.return_value = np.ones(16000, dtype=np.float32)
        mock_trans.transcribe.return_value = "hi there"
        send_start(app)
        send_stop(app)
        time.sleep(0.2)
        mock_cb.paste_text.assert_called_once_with("hi there")

    def test_no_local_paste_by_default(self, mock_check):
        app, transport, mock_rec, mock_trans, _, mock_cb, _ = make_host_app()
        mock_rec.stop.return_value = np.ones(16000, dtype=np.float32)
        mock_trans.transcribe.return_value = "hi there"
        send_start(app)
        send_stop(app)
        time.sleep(0.2)
        mock_cb.paste_text.assert_not_called()

    def test_corrections_applied_to_networked_text(self, mock_check):
        config = make_config("host")
        config["replacements"] = {"comet": "commit"}
        app, transport, mock_rec, mock_trans, _, _, _ = make_host_app(
            config=config
        )
        mock_rec.stop.return_value = np.ones(16000, dtype=np.float32)
        mock_trans.transcribe.return_value = "push the comet"
        send_start(app)
        send_stop(app)
        time.sleep(0.2)
        texts = sent_of_type(transport, protocol.TYPE_TEXT, CLIENT_ADDR)
        assert protocol.join_message([texts[0][0]]) == "push the commit"

    def test_no_hotkey_listener_by_default(self, mock_check):
        app, _, _, _, _, _, mock_hk_factory = make_host_app()
        mock_hk_factory.assert_not_called()

    def test_host_hotkey_drives_local_session(self, mock_check):
        app, transport, mock_rec, mock_trans, _, mock_cb, hk_factory = (
            make_host_app(host_hotkey=True)
        )
        hk_factory.assert_called_once()
        toggle = hk_factory.call_args[0][0]
        mock_rec.stop.return_value = np.ones(16000, dtype=np.float32)
        mock_trans.transcribe.return_value = "local words"
        toggle()
        assert app.host.state == "recording"
        mock_rec.start.assert_called_once()
        toggle()
        time.sleep(0.2)
        # local session pastes locally, sends nothing over the wire
        mock_cb.paste_text.assert_called_once_with("local words")
        assert sent_of_type(transport, protocol.TYPE_TEXT) == []
        assert app.host.state == "idle"

    def test_host_event_flags_silence_session_notifications(self, mock_check):
        inner = RecordingNotifier()
        notifier = FilteredNotifier(
            inner,
            events={
                "recording": False,
                "stopped": False,
                "pasted": False,
            },
        )
        app, transport, mock_rec, mock_trans, _, _, _ = make_host_app(
            notifier=notifier
        )
        mock_rec.stop.return_value = np.ones(16000, dtype=np.float32)
        mock_trans.transcribe.return_value = "hello world"
        send_start(app)
        send_stop(app)
        time.sleep(0.2)
        # text still reaches the client; only notifications are off
        texts = sent_of_type(transport, protocol.TYPE_TEXT, CLIENT_ADDR)
        assert len(texts) == 1
        assert inner.notifications == []
        assert inner.dings == 0

    def test_network_stop_returns_before_recorder_finishes(self, mock_check):
        app, transport, mock_rec, mock_trans, _, _, _ = make_host_app()
        release = threading.Event()

        def slow_stop():
            release.wait(timeout=5)
            return np.ones(16000, dtype=np.float32)

        mock_rec.stop.side_effect = slow_stop
        mock_trans.transcribe.return_value = "hello"
        send_start(app)
        started = time.monotonic()
        send_stop(app)
        elapsed = time.monotonic() - started
        release.set()
        assert elapsed < 1.0
        assert wait_for(lambda: app.host.state == "idle")
        texts = sent_of_type(transport, protocol.TYPE_TEXT, CLIENT_ADDR)
        assert len(texts) == 1
        assert protocol.join_message([texts[0][0]]) == "hello"

    def test_recorder_stop_failure_recovers_to_idle(self, mock_check):
        app, transport, mock_rec, mock_trans, _, _, _ = make_host_app()
        mock_rec.stop.side_effect = RuntimeError("coreaudio wedged")
        send_start(app)
        send_stop(app)  # must not raise
        assert wait_for(lambda: app.host.state == "idle")
        assert sent_of_type(transport, protocol.TYPE_TEXT) == []
        error_states = [
            body
            for body, _ in sent_of_type(transport, protocol.TYPE_STATE)
            if body["state"] == "error"
        ]
        assert error_states

    def test_text_for_expired_session_is_discarded(self, mock_check):
        app, transport, mock_rec, mock_trans, _, _, _ = make_host_app(
            deliver_to="all"
        )
        mock_rec.stop.return_value = np.ones(16000, dtype=np.float32)
        release = threading.Event()

        def slow_transcribe(audio, rate):
            release.wait(timeout=5)
            return "stale words"

        mock_trans.transcribe.side_effect = slow_transcribe
        send_start(app)
        send_stop(app)
        assert wait_for(lambda: app.host.state == "transcribing")
        # the watchdog gives up on the session while it transcribes
        with app._lock:
            app.host.publish_state("error")
            app.host.finish_session()
        release.set()
        time.sleep(0.3)
        assert sent_of_type(transport, protocol.TYPE_TEXT) == []
        assert app.host.state == "idle"

    def test_host_mode_without_key_refuses_to_start(self, mock_check):
        config = make_config("host")
        env = {k: v for k, v in os.environ.items() if k != "TRANSCRIBE_PSK"}
        with (
            patch("transcribe.recorder.AudioRecorder"),
            patch("transcribe.app.create_transcriber"),
            patch("transcribe.app.create_notifier"),
            patch("transcribe.app.create_clipboard"),
            patch.dict(os.environ, env, clear=True),
            pytest.raises(ConfigError),
        ):
            HostApp(config=config, transport=FakeTransport())


class TestClientApp:
    def test_client_never_builds_transcriber(self):
        _, _, _, _, _, mock_trans_factory = make_client_app()
        mock_trans_factory.assert_not_called()

    def test_hotkey_trigger_sends_start(self):
        app, transport, _, _, hk_factory, _ = make_client_app()
        trigger = hk_factory.call_args[0][0]
        trigger()
        starts = sent_of_type(transport, protocol.TYPE_START)
        assert len(starts) == 1
        assert starts[0][1] == (
            NETWORK_DEFAULTS["server_host"],
            NETWORK_DEFAULTS["server_port"],
        )

    def test_state_recording_notifies_with_ding(self):
        app, _, mock_notif, _, _, _ = make_client_app()
        body = protocol.new_body(time.time(), state="recording")
        app.client.handle_datagram(
            seal_datagram(protocol.TYPE_STATE, body), CLIENT_ADDR
        )
        mock_notif.notify_and_ding.assert_called_once()
        assert "Recording" in mock_notif.notify_and_ding.call_args[0][1]

    def test_text_pastes_and_notifies(self):
        app, _, mock_notif, mock_cb, _, _ = make_client_app()
        bodies = protocol.split_message(
            "dictated text", "sess1", "msg1", time.time()
        )
        for body in bodies:
            app.client.handle_datagram(
                seal_datagram(protocol.TYPE_TEXT, body), CLIENT_ADDR
            )
        mock_cb.paste_text.assert_called_once_with("dictated text")
        mock_notif.notify.assert_called_with(
            "Transcribe", "Pasted!", event="pasted"
        )

    def test_client_event_flags_silence_state_notifications(self):
        inner = RecordingNotifier()
        notifier = FilteredNotifier(
            inner,
            events={"recording": False, "stopped": False, "error": False},
        )
        app, _, _, _, _, _ = make_client_app(notifier=notifier)
        for state in ("recording", "transcribing", "error"):
            body = protocol.new_body(time.time(), state=state)
            app.client.handle_datagram(
                seal_datagram(protocol.TYPE_STATE, body), CLIENT_ADDR
            )
        assert inner.notifications == []
        assert inner.dings == 0

    def test_client_pasted_event_off_still_pastes(self):
        inner = RecordingNotifier()
        notifier = FilteredNotifier(inner, events={"pasted": False})
        app, _, _, mock_cb, _, _ = make_client_app(notifier=notifier)
        bodies = protocol.split_message(
            "dictated text", "sess1", "msg1", time.time()
        )
        for body in bodies:
            app.client.handle_datagram(
                seal_datagram(protocol.TYPE_TEXT, body), CLIENT_ADDR
            )
        mock_cb.paste_text.assert_called_once_with("dictated text")
        assert inner.notifications == []
        assert inner.dings == 0

    def test_client_mode_without_key_refuses_to_start(self):
        config = make_config("client")
        env = {k: v for k, v in os.environ.items() if k != "TRANSCRIBE_PSK"}
        with (
            patch("transcribe.app.create_hotkey_listener"),
            patch("transcribe.app.create_notifier"),
            patch("transcribe.app.create_clipboard"),
            patch.dict(os.environ, env, clear=True),
            pytest.raises(ConfigError),
        ):
            ClientApp(config=config, transport=FakeTransport())


class TestMainDispatch:
    def _run_main(self, mode, argv=None):
        config = make_config(mode)
        with (
            patch("transcribe.app.load_config", return_value=config),
            patch("transcribe.app.TranscribeApp") as standalone_cls,
            patch("transcribe.app.HostApp") as host_cls,
            patch("transcribe.app.ClientApp") as client_cls,
        ):
            main(argv or [])
        return standalone_cls, host_cls, client_cls

    def test_standalone_is_default(self):
        standalone_cls, host_cls, client_cls = self._run_main("standalone")
        standalone_cls.assert_called_once()
        standalone_cls.return_value.run.assert_called_once()
        host_cls.assert_not_called()
        client_cls.assert_not_called()

    def test_host_mode_dispatches_to_host_app(self):
        standalone_cls, host_cls, client_cls = self._run_main("host")
        host_cls.assert_called_once()
        host_cls.return_value.run.assert_called_once()
        standalone_cls.assert_not_called()

    def test_client_mode_dispatches_to_client_app(self):
        standalone_cls, host_cls, client_cls = self._run_main("client")
        client_cls.assert_called_once()
        client_cls.return_value.run.assert_called_once()
        standalone_cls.assert_not_called()


class TestCli:
    def test_keygen_prints_fresh_base64_key(self, capsys):
        with patch("transcribe.app.load_config") as mock_load:
            main(["keygen"])
            mock_load.assert_not_called()
        printed = capsys.readouterr().out.strip()
        assert len(base64.b64decode(printed, validate=True)) == 32

    def test_keygen_keys_are_unique(self, capsys):
        main(["keygen"])
        first = capsys.readouterr().out.strip()
        main(["keygen"])
        second = capsys.readouterr().out.strip()
        assert first != second

    def test_client_flag_overrides_config_mode(self):
        config = make_config("standalone")
        with (
            patch("transcribe.app.load_config", return_value=config),
            patch("transcribe.app.TranscribeApp") as standalone_cls,
            patch("transcribe.app.ClientApp") as client_cls,
        ):
            main(["--client"])
        client_cls.assert_called_once()
        standalone_cls.assert_not_called()

    def test_standalone_flag_overrides_config_mode(self):
        config = make_config("client")
        with (
            patch("transcribe.app.load_config", return_value=config),
            patch("transcribe.app.TranscribeApp") as standalone_cls,
            patch("transcribe.app.ClientApp") as client_cls,
        ):
            main(["--standalone"])
        standalone_cls.assert_called_once()
        client_cls.assert_not_called()

    def test_host_flag_overrides_config_mode(self):
        config = make_config("standalone")
        with (
            patch("transcribe.app.load_config", return_value=config),
            patch("transcribe.app.TranscribeApp") as standalone_cls,
            patch("transcribe.app.HostApp") as host_cls,
        ):
            main(["--host"])
        host_cls.assert_called_once()
        standalone_cls.assert_not_called()

    def test_server_flags_override_network_config(self):
        config = make_config("client")
        with (
            patch("transcribe.app.load_config", return_value=config),
            patch("transcribe.app.ClientApp") as client_cls,
        ):
            main(
                [
                    "--server-host",
                    "192.168.1.9",
                    "--server-port",
                    "48123",
                ]
            )
        passed = client_cls.call_args[0][0]
        assert passed["network"]["server_host"] == "192.168.1.9"
        assert passed["network"]["server_port"] == 48123
