from unittest.mock import MagicMock

from transcribe.config import NETWORK_DEFAULTS
from transcribe.net import crypto, protocol
from transcribe.net.host import Host

PSK = b"\x05" * 32
KEY = crypto.derive_key(PSK)
WRONG_KEY = crypto.derive_key(b"\x06" * 32)

CLIENT_A = ("10.211.55.3", 40001)
CLIENT_B = ("10.211.55.4", 40002)


class FakeTransport:
    def __init__(self):
        self.sent = []

    def sendto(self, data, addr):
        self.sent.append((data, addr))


class FakeClock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def make_network(**overrides):
    network = dict(NETWORK_DEFAULTS)
    network["mode"] = "host"
    network.update(overrides)
    return network


def make_host(clock=None, transport=None, **overrides):
    clock = clock or FakeClock()
    transport = transport or FakeTransport()
    on_start = MagicMock()
    on_stop = MagicMock()
    host = Host(
        make_network(**overrides),
        PSK,
        transport,
        clock=clock,
        on_start=on_start,
        on_stop=on_stop,
    )
    return host, transport, clock, on_start, on_stop


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


def register(host, clock, addr, label):
    body = protocol.new_body(clock(), client=label)
    host.handle_datagram(seal_datagram(protocol.TYPE_REGISTER, body), addr)


def send_start(host, clock, addr, label, session):
    body = protocol.new_body(clock(), client=label, session=session)
    datagram = seal_datagram(protocol.TYPE_START, body)
    host.handle_datagram(datagram, addr)
    return body, datagram


def send_stop(host, clock, addr, label, session):
    body = protocol.new_body(clock(), client=label, session=session)
    datagram = seal_datagram(protocol.TYPE_STOP, body)
    host.handle_datagram(datagram, addr)
    return body, datagram


class TestRegistry:
    def test_register_adds_subscriber(self):
        host, transport, clock, _, _ = make_host()
        register(host, clock, CLIENT_A, "vm")
        host.publish_state("idle")
        states = sent_of_type(transport, protocol.TYPE_STATE, CLIENT_A)
        assert len(states) == 1
        assert states[0][0]["state"] == "idle"

    def test_unregister_removes_subscriber(self):
        host, transport, clock, _, _ = make_host()
        register(host, clock, CLIENT_A, "vm")
        body = protocol.new_body(clock(), client="vm")
        host.handle_datagram(
            seal_datagram(protocol.TYPE_UNREGISTER, body), CLIENT_A
        )
        host.publish_state("idle")
        assert sent_of_type(transport, protocol.TYPE_STATE, CLIENT_A) == []

    def test_ttl_prunes_silent_subscriber(self):
        host, transport, clock, _, _ = make_host(subscriber_ttl=30)
        register(host, clock, CLIENT_A, "vm")
        clock.advance(31)
        host.tick()
        host.publish_state("idle")
        assert sent_of_type(transport, protocol.TYPE_STATE, CLIENT_A) == []

    def test_renew_keeps_subscriber_alive(self):
        host, transport, clock, _, _ = make_host(subscriber_ttl=30)
        register(host, clock, CLIENT_A, "vm")
        clock.advance(20)
        body = protocol.new_body(clock(), client="vm")
        host.handle_datagram(
            seal_datagram(protocol.TYPE_RENEW, body), CLIENT_A
        )
        clock.advance(20)
        host.tick()
        host.publish_state("idle")
        assert len(sent_of_type(transport, protocol.TYPE_STATE)) == 1


class TestStartStop:
    def test_start_from_idle_records_and_broadcasts(self):
        host, transport, clock, on_start, _ = make_host()
        register(host, clock, CLIENT_A, "vm")
        body, _ = send_start(host, clock, CLIENT_A, "vm", "sess1")
        assert host.state == "recording"
        assert host.session == "sess1"
        assert host.initiator == "vm"
        on_start.assert_called_once()
        states = sent_of_type(transport, protocol.TYPE_STATE, CLIENT_A)
        assert states[-1][0]["state"] == "recording"
        acks = sent_of_type(transport, protocol.TYPE_ACK, CLIENT_A)
        assert acks[0][0]["ref"] == body["id"]

    def test_duplicate_start_datagram_is_idempotent(self):
        host, transport, clock, on_start, _ = make_host()
        register(host, clock, CLIENT_A, "vm")
        body, datagram = send_start(host, clock, CLIENT_A, "vm", "sess1")
        host.handle_datagram(datagram, CLIENT_A)
        assert on_start.call_count == 1
        acks = sent_of_type(transport, protocol.TYPE_ACK, CLIENT_A)
        assert len(acks) == 2
        assert all(a[0]["ref"] == body["id"] for a in acks)

    def test_retried_start_same_session_reacked_not_restarted(self):
        host, transport, clock, on_start, _ = make_host()
        register(host, clock, CLIENT_A, "vm")
        send_start(host, clock, CLIENT_A, "vm", "sess1")
        body2, _ = send_start(host, clock, CLIENT_A, "vm", "sess1")
        assert on_start.call_count == 1
        acks = sent_of_type(transport, protocol.TYPE_ACK, CLIENT_A)
        assert acks[-1][0]["ref"] == body2["id"]

    def test_start_while_busy_rejected_with_state_sync(self):
        host, transport, clock, on_start, _ = make_host()
        register(host, clock, CLIENT_A, "vm")
        register(host, clock, CLIENT_B, "other")
        send_start(host, clock, CLIENT_A, "vm", "sess1")
        transport.sent.clear()
        body2, _ = send_start(host, clock, CLIENT_B, "other", "sess2")
        assert host.session == "sess1"
        assert on_start.call_count == 1
        # no ACK for the rejected START
        assert sent_of_type(transport, protocol.TYPE_ACK, CLIENT_B) == []
        # but the newcomer is synced with the current state
        states = sent_of_type(transport, protocol.TYPE_STATE, CLIENT_B)
        assert states[-1][0]["state"] == "recording"
        assert states[-1][0]["session"] == "sess1"

    def test_stop_active_session_transcribes(self):
        host, transport, clock, _, on_stop = make_host()
        register(host, clock, CLIENT_A, "vm")
        send_start(host, clock, CLIENT_A, "vm", "sess1")
        body, _ = send_stop(host, clock, CLIENT_A, "vm", "sess1")
        assert host.state == "transcribing"
        on_stop.assert_called_once()
        states = sent_of_type(transport, protocol.TYPE_STATE, CLIENT_A)
        assert states[-1][0]["state"] == "transcribing"
        acks = sent_of_type(transport, protocol.TYPE_ACK, CLIENT_A)
        assert acks[-1][0]["ref"] == body["id"]

    def test_stop_stale_session_acked_but_ignored(self):
        host, transport, clock, _, on_stop = make_host()
        register(host, clock, CLIENT_A, "vm")
        send_start(host, clock, CLIENT_A, "vm", "sess1")
        body, _ = send_stop(host, clock, CLIENT_A, "vm", "old-sess")
        assert host.state == "recording"
        on_stop.assert_not_called()
        acks = sent_of_type(transport, protocol.TYPE_ACK, CLIENT_A)
        assert acks[-1][0]["ref"] == body["id"]

    def test_stop_when_idle_is_ignored(self):
        host, _, clock, _, on_stop = make_host()
        register(host, clock, CLIENT_A, "vm")
        send_stop(host, clock, CLIENT_A, "vm", "sess1")
        assert host.state == "idle"
        on_stop.assert_not_called()

    def test_lost_stop_auto_stops_after_max_record_seconds(self):
        host, transport, clock, _, on_stop = make_host(max_record_seconds=60)
        register(host, clock, CLIENT_A, "vm")
        send_start(host, clock, CLIENT_A, "vm", "sess1")
        clock.advance(59)
        host.tick()
        on_stop.assert_not_called()
        clock.advance(2)
        host.tick()
        on_stop.assert_called_once()
        assert host.state == "transcribing"

    def test_finish_session_returns_to_idle(self):
        host, transport, clock, _, _ = make_host()
        register(host, clock, CLIENT_A, "vm")
        send_start(host, clock, CLIENT_A, "vm", "sess1")
        send_stop(host, clock, CLIENT_A, "vm", "sess1")
        host.finish_session()
        assert host.state == "idle"
        assert host.session is None
        states = sent_of_type(transport, protocol.TYPE_STATE, CLIENT_A)
        assert states[-1][0]["state"] == "idle"

    def test_allowed_clients_blocks_unlisted_label(self):
        host, transport, clock, on_start, _ = make_host(allowed_clients=["vm"])
        register(host, clock, CLIENT_B, "intruder")
        send_start(host, clock, CLIENT_B, "intruder", "sess1")
        assert host.state == "idle"
        on_start.assert_not_called()
        assert sent_of_type(transport, protocol.TYPE_ACK, CLIENT_B) == []


class TestTextDelivery:
    def _start_stop(self, host, clock, addr=CLIENT_A, label="vm"):
        send_start(host, clock, addr, label, "sess1")
        send_stop(host, clock, addr, label, "sess1")

    def test_text_goes_to_initiator_only_by_default(self):
        host, transport, clock, _, _ = make_host()
        register(host, clock, CLIENT_A, "vm")
        register(host, clock, CLIENT_B, "other")
        self._start_stop(host, clock)
        transport.sent.clear()
        host.publish_text("hello world")
        texts_a = sent_of_type(transport, protocol.TYPE_TEXT, CLIENT_A)
        texts_b = sent_of_type(transport, protocol.TYPE_TEXT, CLIENT_B)
        assert len(texts_a) == 1
        assert texts_b == []
        assert protocol.join_message([texts_a[0][0]]) == "hello world"

    def test_text_broadcast_when_deliver_to_all(self):
        host, transport, clock, _, _ = make_host(deliver_to="all")
        register(host, clock, CLIENT_A, "vm")
        register(host, clock, CLIENT_B, "other")
        self._start_stop(host, clock)
        transport.sent.clear()
        host.publish_text("hi")
        assert len(sent_of_type(transport, protocol.TYPE_TEXT, CLIENT_A)) == 1
        assert len(sent_of_type(transport, protocol.TYPE_TEXT, CLIENT_B)) == 1

    def test_text_retransmits_until_ack(self):
        host, transport, clock, _, _ = make_host()
        register(host, clock, CLIENT_A, "vm")
        self._start_stop(host, clock)
        transport.sent.clear()
        host.publish_text("hello")
        assert len(sent_of_type(transport, protocol.TYPE_TEXT, CLIENT_A)) == 1
        clock.advance(1)
        host.tick()
        texts = sent_of_type(transport, protocol.TYPE_TEXT, CLIENT_A)
        assert len(texts) == 2
        # ACK halts retransmission
        chunk_id = texts[0][0]["id"]
        ack = protocol.new_body(clock(), ref=chunk_id)
        host.handle_datagram(seal_datagram(protocol.TYPE_ACK, ack), CLIENT_A)
        clock.advance(60)
        host.tick()
        assert len(sent_of_type(transport, protocol.TYPE_TEXT, CLIENT_A)) == 2

    def test_text_retransmission_gives_up_eventually(self):
        host, transport, clock, _, _ = make_host(max_retries=2)
        register(host, clock, CLIENT_A, "vm")
        self._start_stop(host, clock)
        transport.sent.clear()
        host.publish_text("hello")
        for _ in range(10):
            clock.advance(10)
            host.tick()
        texts = sent_of_type(transport, protocol.TYPE_TEXT, CLIENT_A)
        # initial send + at most max_retries resends
        assert len(texts) == 3

    def test_multichunk_text_reassembles(self):
        host, transport, clock, _, _ = make_host(max_datagram_bytes=300)
        register(host, clock, CLIENT_A, "vm")
        self._start_stop(host, clock)
        transport.sent.clear()
        text = "héllo wörld ✓ " * 30
        host.publish_text(text)
        texts = sent_of_type(transport, protocol.TYPE_TEXT, CLIENT_A)
        assert len(texts) > 1
        assert protocol.join_message([t[0] for t in texts]) == text


class TestHostSecurity:
    def test_malformed_datagram_changes_nothing(self):
        host, transport, clock, on_start, _ = make_host()
        host.handle_datagram(b"garbage", CLIENT_A)
        host.handle_datagram(b"", CLIENT_A)
        assert host.state == "idle"
        on_start.assert_not_called()
        assert transport.sent == []

    def test_wrong_key_start_is_dropped_silently(self):
        host, transport, clock, on_start, _ = make_host()
        body = protocol.new_body(clock(), client="vm", session="s")
        datagram = seal_datagram(protocol.TYPE_START, body, key=WRONG_KEY)
        host.handle_datagram(datagram, CLIENT_A)
        assert host.state == "idle"
        on_start.assert_not_called()
        assert transport.sent == []

    def test_replayed_start_never_retriggers_mic(self):
        host, transport, clock, on_start, _ = make_host()
        register(host, clock, CLIENT_A, "vm")
        body, datagram = send_start(host, clock, CLIENT_A, "vm", "sess1")
        send_stop(host, clock, CLIENT_A, "vm", "sess1")
        host.finish_session()
        assert host.state == "idle"
        # fast replay: dedup cache catches it
        host.handle_datagram(datagram, CLIENT_A)
        assert host.state == "idle"
        assert on_start.call_count == 1
        # late replay: freshness catches it
        clock.advance(120)
        host.tick()
        host.handle_datagram(datagram, CLIENT_A)
        assert host.state == "idle"
        assert on_start.call_count == 1

    def test_stale_timestamp_start_is_dropped(self):
        host, _, clock, on_start, _ = make_host()
        body = protocol.new_body(clock() - 300, client="vm", session="sess1")
        host.handle_datagram(
            seal_datagram(protocol.TYPE_START, body), CLIENT_A
        )
        assert host.state == "idle"
        on_start.assert_not_called()

    def test_tampered_datagram_is_dropped(self):
        host, _, clock, on_start, _ = make_host()
        body = protocol.new_body(clock(), client="vm", session="sess1")
        datagram = bytearray(seal_datagram(protocol.TYPE_START, body))
        datagram[-1] ^= 0xFF
        host.handle_datagram(bytes(datagram), CLIENT_A)
        assert host.state == "idle"
        on_start.assert_not_called()

    def test_body_missing_id_or_ts_is_dropped(self):
        host, _, clock, on_start, _ = make_host()
        datagram = seal_datagram(
            protocol.TYPE_START, {"client": "vm", "session": "s"}
        )
        host.handle_datagram(datagram, CLIENT_A)
        assert host.state == "idle"
        on_start.assert_not_called()


class TestPublishState:
    def test_publish_state_reaches_all_subscribers(self):
        host, transport, clock, _, _ = make_host()
        register(host, clock, CLIENT_A, "vm")
        register(host, clock, CLIENT_B, "other")
        transport.sent.clear()
        host.publish_state("idle")
        assert len(sent_of_type(transport, protocol.TYPE_STATE, CLIENT_A)) == 1
        assert len(sent_of_type(transport, protocol.TYPE_STATE, CLIENT_B)) == 1

    def test_state_body_carries_session_and_initiator(self):
        host, transport, clock, _, _ = make_host()
        register(host, clock, CLIENT_A, "vm")
        send_start(host, clock, CLIENT_A, "vm", "sess1")
        states = sent_of_type(transport, protocol.TYPE_STATE, CLIENT_A)
        body = states[-1][0]
        assert body["session"] == "sess1"
        assert body["initiator"] == "vm"

    def test_start_rate_limit_ignores_rapid_restart(self):
        host, transport, clock, on_start, _ = make_host()
        register(host, clock, CLIENT_A, "vm")
        send_start(host, clock, CLIENT_A, "vm", "sess1")
        send_stop(host, clock, CLIENT_A, "vm", "sess1")
        host.finish_session()
        # immediate new START within the rate limit window is dropped
        send_start(host, clock, CLIENT_A, "vm", "sess2")
        assert on_start.call_count == 1
        assert host.state == "idle"
        clock.advance(2)
        send_start(host, clock, CLIENT_A, "vm", "sess3")
        assert on_start.call_count == 2
        assert host.state == "recording"


class TestHostStub:
    def test_host_constructible(self):
        host, _, _, _, _ = make_host()
        assert host.state == "idle"
