from transcribe.config import NETWORK_DEFAULTS
from transcribe.net import crypto, protocol
from transcribe.net.client import Client, sanitize_text

PSK = b"test-psk"
KEY = crypto.derive_key(PSK)
WRONG_KEY = crypto.derive_key(b"a-different-psk")
SERVER = ("127.0.0.1", 47800)
LABEL = "testclient"


class FakeTransport:
    def __init__(self):
        self.sent = []

    def sendto(self, data, addr):
        self.sent.append((data, addr))


class FakeClock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def make_network(**overrides):
    network = dict(NETWORK_DEFAULTS)
    network["client_label"] = LABEL
    network.update(overrides)
    return network


def make_client(on_state=None, on_text=None, **overrides):
    transport = FakeTransport()
    clock = FakeClock()
    client = Client(
        make_network(**overrides),
        PSK,
        transport,
        clock=clock,
        on_state=on_state,
        on_text=on_text,
    )
    return client, transport, clock


def decode_sent(data):
    msg_type, nonce, ciphertext = protocol.decode_frame(data)
    plaintext = crypto.open_sealed(
        KEY, protocol.header(msg_type), nonce, ciphertext
    )
    return msg_type, protocol.decode_body(plaintext)


def sent_of_type(transport, msg_type):
    bodies = []
    for data, _addr in transport.sent:
        got_type, body = decode_sent(data)
        if got_type == msg_type:
            bodies.append(body)
    return bodies


def host_datagram(msg_type, body, key=KEY):
    plaintext = protocol.encode_body(body)
    nonce, ciphertext = crypto.seal(key, protocol.header(msg_type), plaintext)
    return protocol.encode_frame(msg_type, nonce, ciphertext)


def text_datagrams(text, now, session="sess", msg="msg1", **kwargs):
    bodies = protocol.split_message(text, session, msg, now, **kwargs)
    return bodies, [host_datagram(protocol.TYPE_TEXT, body) for body in bodies]


class TestSanitizeText:
    def test_c0_controls_stripped(self):
        assert sanitize_text("a\x07b\x1bc") == "abc"

    def test_newline_and_tab_kept(self):
        assert sanitize_text("a\nb\tc") == "a\nb\tc"

    def test_carriage_return_stripped(self):
        assert sanitize_text("a\rb") == "ab"

    def test_del_stripped(self):
        assert sanitize_text("a\x7fb") == "ab"

    def test_c1_range_stripped(self):
        assert sanitize_text("a\x80b\x9fc\x85d") == "abcd"

    def test_unicode_kept(self):
        assert sanitize_text("héllo — 世界 🌍") == "héllo — 世界 🌍"

    def test_empty_string(self):
        assert sanitize_text("") == ""

    def test_mixed(self):
        assert sanitize_text("a\x07b\x1bc\nd\te") == "abc\nd\te"


class TestStart:
    def test_sends_register_to_server_address(self):
        client, transport, clock = make_client()
        client.start()
        assert len(transport.sent) == 1
        data, addr = transport.sent[0]
        assert addr == SERVER
        msg_type, body = decode_sent(data)
        assert msg_type == protocol.TYPE_REGISTER
        assert body["client"] == LABEL

    def test_register_body_has_id_and_ts(self):
        client, transport, clock = make_client()
        client.start()
        _msg_type, body = decode_sent(transport.sent[0][0])
        assert isinstance(body["id"], str)
        assert body["ts"] == clock.now

    def test_empty_label_falls_back_to_client(self):
        client, transport, clock = make_client(client_label="")
        client.start()
        _msg_type, body = decode_sent(transport.sent[0][0])
        assert body["client"] == "client"


class TestRenew:
    def test_tick_before_interval_sends_nothing(self):
        client, transport, clock = make_client()
        client.start()
        transport.sent.clear()
        clock.advance(5)
        client.tick()
        assert transport.sent == []

    def test_tick_after_interval_sends_renew(self):
        client, transport, clock = make_client()
        client.start()
        transport.sent.clear()
        clock.advance(10.5)
        client.tick()
        renews = sent_of_type(transport, protocol.TYPE_RENEW)
        assert len(renews) == 1
        assert renews[0]["client"] == LABEL

    def test_renew_repeats_each_interval(self):
        client, transport, clock = make_client()
        client.start()
        transport.sent.clear()
        clock.advance(10.5)
        client.tick()
        client.tick()
        clock.advance(10.5)
        client.tick()
        renews = sent_of_type(transport, protocol.TYPE_RENEW)
        assert len(renews) == 2

    def test_no_renew_before_start(self):
        client, transport, clock = make_client()
        clock.advance(100)
        client.tick()
        assert sent_of_type(transport, protocol.TYPE_RENEW) == []


class TestStop:
    def test_sends_unregister(self):
        client, transport, clock = make_client()
        client.stop()
        assert len(transport.sent) == 1
        data, addr = transport.sent[0]
        assert addr == SERVER
        msg_type, body = decode_sent(data)
        assert msg_type == protocol.TYPE_UNREGISTER
        assert body["client"] == LABEL


class TestTrigger:
    def test_unknown_state_sends_start(self):
        client, transport, clock = make_client()
        client.trigger()
        starts = sent_of_type(transport, protocol.TYPE_START)
        assert len(starts) == 1
        assert starts[0]["client"] == LABEL
        assert isinstance(starts[0]["session"], str)
        assert len(starts[0]["session"]) == 32

    def test_idle_state_sends_start(self):
        client, transport, clock = make_client()
        state = protocol.new_body(clock.now, state="idle")
        client.handle_datagram(
            host_datagram(protocol.TYPE_STATE, state), SERVER
        )
        client.trigger()
        assert len(sent_of_type(transport, protocol.TYPE_START)) == 1

    def test_recording_sends_stop_with_host_session(self):
        client, transport, clock = make_client()
        state = protocol.new_body(
            clock.now, state="recording", session="hostsess"
        )
        client.handle_datagram(
            host_datagram(protocol.TYPE_STATE, state), SERVER
        )
        client.trigger()
        stops = sent_of_type(transport, protocol.TYPE_STOP)
        assert len(stops) == 1
        assert stops[0]["session"] == "hostsess"
        assert stops[0]["client"] == LABEL

    def test_recording_without_session_uses_started_session(self):
        client, transport, clock = make_client()
        client.trigger()
        starts = sent_of_type(transport, protocol.TYPE_START)
        session = starts[0]["session"]
        state = protocol.new_body(clock.now, state="recording")
        client.handle_datagram(
            host_datagram(protocol.TYPE_STATE, state), SERVER
        )
        client.trigger()
        stops = sent_of_type(transport, protocol.TYPE_STOP)
        assert len(stops) == 1
        assert stops[0]["session"] == session

    def test_transcribing_sends_nothing(self):
        client, transport, clock = make_client()
        state = protocol.new_body(clock.now, state="transcribing")
        client.handle_datagram(
            host_datagram(protocol.TYPE_STATE, state), SERVER
        )
        transport.sent.clear()
        client.trigger()
        assert transport.sent == []

    def test_error_sends_nothing(self):
        client, transport, clock = make_client()
        state = protocol.new_body(clock.now, state="error")
        client.handle_datagram(
            host_datagram(protocol.TYPE_STATE, state), SERVER
        )
        transport.sent.clear()
        client.trigger()
        assert transport.sent == []


class TestState:
    def test_view_none_before_any_state(self):
        client, transport, clock = make_client()
        assert client.view is None

    def test_state_updates_view_and_calls_on_state(self):
        seen = []
        client, transport, clock = make_client(on_state=seen.append)
        body = protocol.new_body(clock.now, state="recording")
        client.handle_datagram(
            host_datagram(protocol.TYPE_STATE, body), SERVER
        )
        assert client.view == "recording"
        assert seen == [body]

    def test_state_without_callback_still_updates_view(self):
        client, transport, clock = make_client()
        body = protocol.new_body(clock.now, state="idle")
        client.handle_datagram(
            host_datagram(protocol.TYPE_STATE, body), SERVER
        )
        assert client.view == "idle"

    def test_duplicate_state_calls_on_state_once(self):
        seen = []
        client, transport, clock = make_client(on_state=seen.append)
        body = protocol.new_body(clock.now, state="recording")
        datagram = host_datagram(protocol.TYPE_STATE, body)
        client.handle_datagram(datagram, SERVER)
        client.handle_datagram(datagram, SERVER)
        assert len(seen) == 1

    def test_stale_state_dropped(self):
        seen = []
        client, transport, clock = make_client(on_state=seen.append)
        body = protocol.new_body(clock.now - 1000, state="recording")
        client.handle_datagram(
            host_datagram(protocol.TYPE_STATE, body), SERVER
        )
        assert seen == []
        assert client.view is None

    def test_state_with_wrong_key_dropped(self):
        seen = []
        client, transport, clock = make_client(on_state=seen.append)
        body = protocol.new_body(clock.now, state="recording")
        client.handle_datagram(
            host_datagram(protocol.TYPE_STATE, body, key=WRONG_KEY), SERVER
        )
        assert seen == []
        assert client.view is None

    def test_state_missing_id_dropped(self):
        seen = []
        client, transport, clock = make_client(on_state=seen.append)
        body = {"ts": clock.now, "state": "recording"}
        client.handle_datagram(
            host_datagram(protocol.TYPE_STATE, body), SERVER
        )
        assert seen == []
        assert client.view is None

    def test_state_missing_ts_dropped(self):
        seen = []
        client, transport, clock = make_client(on_state=seen.append)
        body = {"id": "abc123", "state": "recording"}
        client.handle_datagram(
            host_datagram(protocol.TYPE_STATE, body), SERVER
        )
        assert seen == []

    def test_state_with_non_numeric_ts_dropped(self):
        seen = []
        client, transport, clock = make_client(on_state=seen.append)
        body = {"id": "abc123", "ts": "soon", "state": "recording"}
        client.handle_datagram(
            host_datagram(protocol.TYPE_STATE, body), SERVER
        )
        assert seen == []


class TestText:
    def test_single_chunk_delivers_text_once(self):
        texts = []
        client, transport, clock = make_client(on_text=texts.append)
        _bodies, datagrams = text_datagrams("hello world", clock.now)
        assert len(datagrams) == 1
        client.handle_datagram(datagrams[0], SERVER)
        assert texts == ["hello world"]

    def test_single_chunk_is_acked(self):
        client, transport, clock = make_client(on_text=lambda t: None)
        bodies, datagrams = text_datagrams("hello", clock.now)
        client.handle_datagram(datagrams[0], SERVER)
        acks = sent_of_type(transport, protocol.TYPE_ACK)
        assert len(acks) == 1
        assert acks[0]["ref"] == bodies[0]["id"]
        assert transport.sent[0][1] == SERVER

    def test_no_ack_when_ack_disabled(self):
        texts = []
        client, transport, clock = make_client(on_text=texts.append, ack=False)
        _bodies, datagrams = text_datagrams("hello", clock.now)
        client.handle_datagram(datagrams[0], SERVER)
        assert texts == ["hello"]
        assert sent_of_type(transport, protocol.TYPE_ACK) == []

    def test_multi_chunk_out_of_order_reassembles(self):
        texts = []
        client, transport, clock = make_client(on_text=texts.append)
        original = "Ünïcode — 世界 🌍 grüße " * 12
        bodies, datagrams = text_datagrams(
            original, clock.now, max_datagram_bytes=300
        )
        assert len(datagrams) > 1
        for datagram in reversed(datagrams):
            client.handle_datagram(datagram, SERVER)
        assert texts == [original]

    def test_replayed_chunk_not_redelivered_but_reacked(self):
        texts = []
        client, transport, clock = make_client(on_text=texts.append)
        bodies, datagrams = text_datagrams("hello", clock.now)
        client.handle_datagram(datagrams[0], SERVER)
        client.handle_datagram(datagrams[0], SERVER)
        assert texts == ["hello"]
        acks = sent_of_type(transport, protocol.TYPE_ACK)
        assert len(acks) == 2
        assert acks[0]["ref"] == bodies[0]["id"]
        assert acks[1]["ref"] == bodies[0]["id"]

    def test_same_msg_id_with_fresh_chunks_delivered_once(self):
        texts = []
        client, transport, clock = make_client(on_text=texts.append)
        _bodies, datagrams = text_datagrams("hello", clock.now, msg="m1")
        client.handle_datagram(datagrams[0], SERVER)
        _bodies2, datagrams2 = text_datagrams("hello", clock.now, msg="m1")
        client.handle_datagram(datagrams2[0], SERVER)
        assert texts == ["hello"]

    def test_wrong_key_text_dropped(self):
        texts = []
        client, transport, clock = make_client(on_text=texts.append)
        bodies = protocol.split_message("secret", "sess", "m1", clock.now)
        datagram = host_datagram(protocol.TYPE_TEXT, bodies[0], key=WRONG_KEY)
        client.handle_datagram(datagram, SERVER)
        assert texts == []
        assert transport.sent == []

    def test_tampered_text_dropped(self):
        texts = []
        client, transport, clock = make_client(on_text=texts.append)
        _bodies, datagrams = text_datagrams("hello", clock.now)
        tampered = bytearray(datagrams[0])
        tampered[-1] ^= 0x01
        client.handle_datagram(bytes(tampered), SERVER)
        assert texts == []
        assert transport.sent == []

    def test_stale_text_dropped(self):
        texts = []
        client, transport, clock = make_client(on_text=texts.append)
        _bodies, datagrams = text_datagrams("hello", clock.now - 1000)
        client.handle_datagram(datagrams[0], SERVER)
        assert texts == []
        assert transport.sent == []

    def test_garbage_datagram_no_exception(self):
        client, transport, clock = make_client(on_text=lambda t: None)
        client.handle_datagram(b"junk", SERVER)
        client.handle_datagram(b"", SERVER)
        client.handle_datagram(b"MPET\x01\x07" + b"\x00" * 20, SERVER)
        assert transport.sent == []

    def test_control_characters_stripped_on_delivery(self):
        texts = []
        client, transport, clock = make_client(on_text=texts.append)
        _bodies, datagrams = text_datagrams("a\x07b\x1bc\nd\te", clock.now)
        client.handle_datagram(datagrams[0], SERVER)
        assert texts == ["abc\nd\te"]

    def test_expired_partial_then_fresh_resend_delivers_once(self):
        texts = []
        client, transport, clock = make_client(on_text=texts.append)
        original = "Ünïcode — 世界 🌍 grüße " * 12
        _bodies, datagrams = text_datagrams(
            original, clock.now, max_datagram_bytes=300
        )
        client.handle_datagram(datagrams[0], SERVER)
        clock.advance(20)
        client.tick()
        _bodies2, datagrams2 = text_datagrams(
            original, clock.now, max_datagram_bytes=300
        )
        for datagram in datagrams2:
            client.handle_datagram(datagram, SERVER)
        assert texts == [original]

    def test_register_type_arriving_at_client_dropped(self):
        seen = []
        texts = []
        client, transport, clock = make_client(
            on_state=seen.append, on_text=texts.append
        )
        body = protocol.new_body(clock.now, client="other")
        client.handle_datagram(
            host_datagram(protocol.TYPE_REGISTER, body), SERVER
        )
        assert seen == []
        assert texts == []
        assert transport.sent == []


class TestRetransmission:
    def _start_id_and_bytes(self, transport):
        data, _addr = transport.sent[0]
        _msg_type, body = decode_sent(data)
        return body["id"], data

    def test_trigger_sends_start_once(self):
        client, transport, clock = make_client()
        client.trigger()
        assert len(sent_of_type(transport, protocol.TYPE_START)) == 1

    def test_tick_before_backoff_does_not_resend(self):
        client, transport, clock = make_client()
        client.trigger()
        client.tick()
        clock.advance(0.05)
        client.tick()
        assert len(sent_of_type(transport, protocol.TYPE_START)) == 1

    def test_tick_after_backoff_resends_same_bytes(self):
        client, transport, clock = make_client()
        client.trigger()
        _start_id, first = self._start_id_and_bytes(transport)
        clock.advance(0.2)
        client.tick()
        assert len(transport.sent) == 2
        assert transport.sent[1][0] == first
        assert transport.sent[1][1] == SERVER

    def test_backoff_doubles_between_resends(self):
        client, transport, clock = make_client()
        client.trigger()
        clock.advance(0.2)
        client.tick()
        clock.advance(0.2)
        client.tick()
        assert len(sent_of_type(transport, protocol.TYPE_START)) == 2
        clock.advance(0.2)
        client.tick()
        assert len(sent_of_type(transport, protocol.TYPE_START)) == 3

    def test_ack_stops_retransmission(self):
        client, transport, clock = make_client()
        client.trigger()
        start_id, _first = self._start_id_and_bytes(transport)
        clock.advance(0.2)
        client.tick()
        ack = protocol.new_body(clock.now, ref=start_id)
        client.handle_datagram(host_datagram(protocol.TYPE_ACK, ack), SERVER)
        for _ in range(10):
            clock.advance(5)
            client.tick()
        assert len(sent_of_type(transport, protocol.TYPE_START)) == 2

    def test_gives_up_after_max_retries_resends(self):
        client, transport, clock = make_client()
        client.trigger()
        for _ in range(20):
            clock.advance(5)
            client.tick()
        starts = sent_of_type(transport, protocol.TYPE_START)
        assert len(starts) == 1 + 4

    def test_no_retransmission_when_ack_disabled(self):
        client, transport, clock = make_client(ack=False)
        client.trigger()
        for _ in range(10):
            clock.advance(5)
            client.tick()
        assert len(sent_of_type(transport, protocol.TYPE_START)) == 1

    def test_ack_for_unknown_ref_is_harmless(self):
        client, transport, clock = make_client()
        ack = protocol.new_body(clock.now, ref="nonexistent")
        client.handle_datagram(host_datagram(protocol.TYPE_ACK, ack), SERVER)
        assert transport.sent == []
