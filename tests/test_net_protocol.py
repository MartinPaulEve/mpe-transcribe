import base64

import pytest

from transcribe.net.protocol import (
    HEADER_LEN,
    MAGIC,
    NONCE_LEN,
    TYPE_ACK,
    TYPE_AUDIO,
    TYPE_REGISTER,
    TYPE_RENEW,
    TYPE_START,
    TYPE_STATE,
    TYPE_STOP,
    TYPE_TEXT,
    TYPE_UNREGISTER,
    VERSION,
    ProtocolError,
    Reassembler,
    decode_body,
    decode_frame,
    encode_body,
    encode_frame,
    header,
    join_message,
    new_body,
    split_message,
)

ALL_TYPES = [
    TYPE_REGISTER,
    TYPE_RENEW,
    TYPE_UNREGISTER,
    TYPE_START,
    TYPE_STOP,
    TYPE_STATE,
    TYPE_TEXT,
    TYPE_ACK,
    TYPE_AUDIO,
]

NONCE = bytes(range(NONCE_LEN))


class TestHeader:
    def test_is_magic_version_type(self):
        assert header(TYPE_TEXT) == MAGIC + bytes([VERSION, TYPE_TEXT])

    def test_has_header_len_bytes(self):
        assert len(header(TYPE_ACK)) == HEADER_LEN

    def test_is_prefix_of_encoded_frame(self):
        frame = encode_frame(TYPE_STATE, NONCE, b"cipher")
        assert frame[:HEADER_LEN] == header(TYPE_STATE)


class TestFrameRoundTrip:
    @pytest.mark.parametrize("msg_type", ALL_TYPES)
    def test_round_trip_every_type(self, msg_type):
        frame = encode_frame(msg_type, NONCE, b"\x00\x01payload")
        assert decode_frame(frame) == (msg_type, NONCE, b"\x00\x01payload")

    def test_round_trip_empty_ciphertext(self):
        frame = encode_frame(TYPE_STOP, NONCE, b"")
        assert decode_frame(frame) == (TYPE_STOP, NONCE, b"")

    def test_encode_rejects_short_nonce(self):
        with pytest.raises(ProtocolError):
            encode_frame(TYPE_TEXT, b"\x00" * (NONCE_LEN - 1), b"x")

    def test_encode_rejects_long_nonce(self):
        with pytest.raises(ProtocolError):
            encode_frame(TYPE_TEXT, b"\x00" * (NONCE_LEN + 1), b"x")


class TestDecodeFrameErrors:
    def test_rejects_bad_magic(self):
        frame = encode_frame(TYPE_TEXT, NONCE, b"x")
        bad = b"XXXX" + frame[4:]
        with pytest.raises(ProtocolError):
            decode_frame(bad)

    def test_rejects_unknown_version(self):
        frame = encode_frame(TYPE_TEXT, NONCE, b"x")
        bad = frame[:4] + bytes([0x7F]) + frame[5:]
        with pytest.raises(ProtocolError):
            decode_frame(bad)

    def test_rejects_truncated_data(self):
        frame = encode_frame(TYPE_TEXT, NONCE, b"x")
        with pytest.raises(ProtocolError):
            decode_frame(frame[:10])

    def test_rejects_empty_data(self):
        with pytest.raises(ProtocolError):
            decode_frame(b"")

    def test_rejects_unknown_type_zero(self):
        frame = encode_frame(TYPE_TEXT, NONCE, b"x")
        bad = frame[:5] + bytes([0x00]) + frame[6:]
        with pytest.raises(ProtocolError):
            decode_frame(bad)

    def test_rejects_unknown_type_above_range(self):
        frame = encode_frame(TYPE_TEXT, NONCE, b"x")
        bad = frame[:5] + bytes([0x0A]) + frame[6:]
        with pytest.raises(ProtocolError):
            decode_frame(bad)


class TestBody:
    def test_round_trip(self):
        body = {"id": "abc", "ts": 12.5, "n": 3}
        assert decode_body(encode_body(body)) == body

    def test_round_trip_unicode(self):
        body = {"data": "héllo 漢字 🎉"}
        assert decode_body(encode_body(body)) == body

    def test_encode_is_compact_json(self):
        raw = encode_body({"a": 1, "b": 2})
        assert raw == b'{"a":1,"b":2}'

    def test_decode_rejects_invalid_json(self):
        with pytest.raises(ProtocolError):
            decode_body(b"{not json")

    def test_decode_rejects_non_dict_json(self):
        with pytest.raises(ProtocolError):
            decode_body(b"[1,2,3]")

    def test_decode_rejects_scalar_json(self):
        with pytest.raises(ProtocolError):
            decode_body(b'"hello"')


class TestNewBody:
    def test_sets_given_ts(self):
        body = new_body(42.25)
        assert body["ts"] == 42.25

    def test_includes_extra_fields(self):
        body = new_body(1.0, session="s1", state="recording")
        assert body["session"] == "s1"
        assert body["state"] == "recording"

    def test_ids_are_unique(self):
        ids = {new_body(0.0)["id"] for _ in range(50)}
        assert len(ids) == 50

    def test_id_is_uuid4_hex(self):
        body = new_body(0.0)
        assert isinstance(body["id"], str)
        assert len(body["id"]) == 32
        int(body["id"], 16)


class TestSplitJoinRoundTrip:
    def test_single_chunk_ascii(self):
        bodies = split_message("hello world", "sess", "msg1", 5.0)
        assert len(bodies) == 1
        assert join_message(bodies) == "hello world"

    def test_multi_chunk_long_text(self):
        text = "the quick brown fox jumps over the lazy dog " * 10
        bodies = split_message(
            text, "sess", "msg1", 5.0, max_datagram_bytes=300
        )
        assert len(bodies) > 1
        assert join_message(bodies) == text

    def test_unicode_across_chunk_boundaries(self):
        text = "héllo wörld 漢字テスト🎉 ünïcödé " * 20
        bodies = split_message(
            text, "sess", "msg1", 5.0, max_datagram_bytes=300
        )
        assert len(bodies) > 1
        assert join_message(bodies) == text

    def test_empty_string_produces_one_chunk(self):
        bodies = split_message("", "sess", "msg1", 5.0)
        assert len(bodies) == 1
        assert bodies[0]["data"] == ""
        assert join_message(bodies) == ""

    def test_join_out_of_order_input(self):
        text = "abcdefghij" * 50
        bodies = split_message(
            text, "sess", "msg1", 5.0, max_datagram_bytes=300
        )
        assert join_message(list(reversed(bodies))) == text


class TestSplitChunkFields:
    def _chunks(self):
        text = "payload data " * 40
        return split_message(
            text, "sess-1", "msg-1", 7.5, max_datagram_bytes=300
        )

    def test_shared_msg_session_n(self):
        bodies = self._chunks()
        n = len(bodies)
        for body in bodies:
            assert body["session"] == "sess-1"
            assert body["msg"] == "msg-1"
            assert body["n"] == n
            assert body["ts"] == 7.5

    def test_indices_are_correct_and_ordered(self):
        bodies = self._chunks()
        assert [b["i"] for b in bodies] == list(range(len(bodies)))

    def test_each_chunk_has_distinct_id(self):
        bodies = self._chunks()
        ids = {b["id"] for b in bodies}
        assert len(ids) == len(bodies)

    def test_data_is_valid_base64(self):
        for body in self._chunks():
            base64.b64decode(body["data"], validate=True)

    @pytest.mark.parametrize("max_dg", [300, 600, 1200])
    def test_encoded_bodies_fit_datagram_budget(self, max_dg):
        text = "x" * 5000
        session = "a" * 32
        msg_id = "b" * 32
        bodies = split_message(
            text, session, msg_id, 1723456789.123, max_datagram_bytes=max_dg
        )
        for body in bodies:
            assert len(encode_body(body)) <= max_dg - 34


class TestJoinMessageErrors:
    def _chunks(self):
        text = "0123456789" * 60
        return split_message(text, "sess", "msg1", 5.0, max_datagram_bytes=300)

    def test_missing_chunk(self):
        bodies = self._chunks()
        assert len(bodies) >= 3
        del bodies[1]
        with pytest.raises(ProtocolError):
            join_message(bodies)

    def test_duplicate_chunk_index(self):
        bodies = self._chunks()
        bodies[-1] = dict(bodies[0])
        with pytest.raises(ProtocolError):
            join_message(bodies)

    def test_inconsistent_n(self):
        bodies = self._chunks()
        bodies[1] = dict(bodies[1], n=bodies[1]["n"] + 1)
        with pytest.raises(ProtocolError):
            join_message(bodies)

    def test_wrong_count_for_n(self):
        bodies = self._chunks()
        with pytest.raises(ProtocolError):
            join_message(bodies[:-1])

    def test_bad_base64(self):
        bodies = self._chunks()
        bodies[0] = dict(bodies[0], data="!!!not base64!!!")
        with pytest.raises(ProtocolError):
            join_message(bodies)

    def test_empty_list(self):
        with pytest.raises(ProtocolError):
            join_message([])


class TestReassembler:
    def _chunks(self, text="reassemble me please " * 30, msg="m1"):
        return split_message(text, "sess", msg, 0.0, max_datagram_bytes=300)

    def test_in_order_completes(self):
        text = "reassemble me please " * 30
        bodies = self._chunks(text)
        r = Reassembler()
        results = [r.add(b, now=0.0) for b in bodies]
        assert results[:-1] == [None] * (len(bodies) - 1)
        assert results[-1] == text

    def test_out_of_order_completes(self):
        text = "reassemble me please " * 30
        bodies = self._chunks(text)
        r = Reassembler()
        shuffled = bodies[1:] + bodies[:1]
        results = [r.add(b, now=0.0) for b in shuffled]
        assert results[-1] == text
        assert results[:-1] == [None] * (len(bodies) - 1)

    def test_single_chunk_message_completes_immediately(self):
        bodies = split_message("short", "sess", "m1", 0.0)
        r = Reassembler()
        assert r.add(bodies[0], now=0.0) == "short"

    def test_incomplete_returns_none(self):
        bodies = self._chunks()
        r = Reassembler()
        assert r.add(bodies[0], now=0.0) is None

    def test_duplicate_chunks_ignored(self):
        text = "reassemble me please " * 30
        bodies = self._chunks(text)
        r = Reassembler()
        assert r.add(bodies[0], now=0.0) is None
        assert r.add(bodies[0], now=0.0) is None
        results = [r.add(b, now=0.0) for b in bodies[1:]]
        assert results[-1] == text

    def test_expire_drops_stale_partial(self):
        bodies = self._chunks()
        r = Reassembler(timeout=10.0)
        for body in bodies[:-1]:
            assert r.add(body, now=0.0) is None
        r.expire(now=20.0)
        assert r.add(bodies[-1], now=20.0) is None

    def test_expire_keeps_fresh_partial(self):
        text = "reassemble me please " * 30
        bodies = self._chunks(text)
        r = Reassembler(timeout=10.0)
        for body in bodies[:-1]:
            assert r.add(body, now=0.0) is None
        r.expire(now=5.0)
        assert r.add(bodies[-1], now=5.0) == text

    def test_messages_tracked_independently(self):
        text_a = "message aaaa " * 30
        text_b = "message bbbb " * 30
        bodies_a = self._chunks(text_a, msg="ma")
        bodies_b = self._chunks(text_b, msg="mb")
        r = Reassembler()
        for a, b in zip(bodies_a[:-1], bodies_b[:-1]):
            assert r.add(a, now=0.0) is None
            assert r.add(b, now=0.0) is None
        assert r.add(bodies_a[-1], now=0.0) == text_a
        assert r.add(bodies_b[-1], now=0.0) == text_b

    def test_oversize_message_dropped(self):
        text = "reassemble me please " * 30
        bodies = self._chunks(text)
        assert len(bodies) > 1
        r = Reassembler(max_message_bytes=40)
        results = [r.add(b, now=0.0) for b in bodies]
        assert results == [None] * len(bodies)

    def test_oversize_single_chunk_dropped(self):
        bodies = split_message("x" * 100, "sess", "m1", 0.0)
        r = Reassembler(max_message_bytes=50)
        assert r.add(bodies[0], now=0.0) is None
