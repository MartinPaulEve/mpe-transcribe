"""Wire protocol framing, bodies, and chunking. Pure — no I/O."""

import base64
import binascii
import json
import uuid

MAGIC = b"MPET"
VERSION = 0x01
HEADER_LEN = 6  # MAGIC(4) + VERSION(1) + TYPE(1)
NONCE_LEN = 12

TYPE_REGISTER = 0x01
TYPE_RENEW = 0x02
TYPE_UNREGISTER = 0x03
TYPE_START = 0x04
TYPE_STOP = 0x05
TYPE_STATE = 0x06
TYPE_TEXT = 0x07
TYPE_ACK = 0x08
TYPE_AUDIO = 0x09  # reserved for future client-side audio

_KNOWN_TYPES = frozenset(range(TYPE_REGISTER, TYPE_AUDIO + 1))

# Conservative allowance for header, nonce, AEAD tag, JSON envelope
# and base64 expansion when sizing raw chunk bytes.
_ENVELOPE_ALLOWANCE = 250


class ProtocolError(Exception):
    """Raised on malformed frames, bodies, or chunk sets."""


def header(msg_type: int) -> bytes:
    """6-byte frame header MAGIC|VERSION|TYPE — also the AEAD AAD."""
    return MAGIC + bytes([VERSION, msg_type])


def encode_frame(msg_type: int, nonce: bytes, ciphertext: bytes) -> bytes:
    """header(msg_type) + nonce + ciphertext. Validates nonce length."""
    if len(nonce) != NONCE_LEN:
        raise ProtocolError(
            f"nonce must be {NONCE_LEN} bytes, got {len(nonce)}"
        )
    return header(msg_type) + nonce + ciphertext


def decode_frame(data: bytes) -> tuple[int, bytes, bytes]:
    """Return (msg_type, nonce, ciphertext).

    Raise ProtocolError on: too short, bad MAGIC, unknown VERSION,
    unknown TYPE (not in 0x01..0x09).
    """
    if len(data) < HEADER_LEN + NONCE_LEN:
        raise ProtocolError("frame too short")
    if data[:4] != MAGIC:
        raise ProtocolError("bad magic")
    if data[4] != VERSION:
        raise ProtocolError(f"unknown version {data[4]:#04x}")
    msg_type = data[5]
    if msg_type not in _KNOWN_TYPES:
        raise ProtocolError(f"unknown message type {msg_type:#04x}")
    nonce = data[HEADER_LEN : HEADER_LEN + NONCE_LEN]
    ciphertext = data[HEADER_LEN + NONCE_LEN :]
    return msg_type, nonce, ciphertext


def encode_body(body: dict) -> bytes:
    """Compact JSON (separators=(",", ":")) UTF-8 bytes."""
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def decode_body(data: bytes) -> dict:
    """Parse JSON; raise ProtocolError if invalid JSON or not a dict."""
    try:
        body = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"invalid body: {exc}") from exc
    if not isinstance(body, dict):
        raise ProtocolError("body is not a JSON object")
    return body


def new_body(ts: float, **fields) -> dict:
    """Body dict with a random uuid4 hex 'id', 'ts'=ts, plus fields."""
    body = {"id": uuid.uuid4().hex, "ts": ts}
    body.update(fields)
    return body


def split_message(
    text: str,
    session: str,
    msg_id: str,
    ts: float,
    max_datagram_bytes: int = 1200,
) -> list[dict]:
    """Split text's UTF-8 bytes into TEXT chunk bodies."""
    raw = text.encode("utf-8")
    budget = max_datagram_bytes - _ENVELOPE_ALLOWANCE
    raw_per_chunk = max(1, (budget * 3) // 4)
    chunks = [
        raw[i : i + raw_per_chunk] for i in range(0, len(raw), raw_per_chunk)
    ] or [b""]
    n = len(chunks)
    return [
        new_body(
            ts,
            session=session,
            msg=msg_id,
            i=i,
            n=n,
            data=base64.b64encode(chunk).decode("ascii"),
        )
        for i, chunk in enumerate(chunks)
    ]


def _decode_chunk_data(body: dict) -> bytes:
    try:
        return base64.b64decode(body["data"], validate=True)
    except (binascii.Error, KeyError, TypeError, ValueError) as exc:
        raise ProtocolError(f"bad chunk data: {exc}") from exc


def join_message(bodies: list[dict]) -> str:
    """Reassemble chunk bodies into the original text."""
    if not bodies:
        raise ProtocolError("no chunks to join")
    try:
        ordered = sorted(bodies, key=lambda b: b["i"])
        counts = {b["n"] for b in bodies}
        indices = [b["i"] for b in ordered]
    except (KeyError, TypeError) as exc:
        raise ProtocolError(f"malformed chunk: {exc}") from exc
    if len(counts) != 1:
        raise ProtocolError("inconsistent chunk count")
    n = counts.pop()
    if n != len(bodies) or indices != list(range(n)):
        raise ProtocolError("missing or duplicate chunks")
    data = b"".join(_decode_chunk_data(b) for b in ordered)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProtocolError(f"invalid UTF-8 in message: {exc}") from exc


class Reassembler:
    """Per-(session, msg) chunk buffer with expiry. Pure; caller
    passes `now`."""

    def __init__(
        self,
        timeout: float = 10.0,
        max_message_bytes: int = 65536,
    ):
        self._timeout = timeout
        self._max_message_bytes = max_message_bytes
        # key -> {"first": float, "n": int, "chunks": {i: bytes}}
        self._buffers: dict[tuple, dict] = {}

    def add(self, body: dict, now: float) -> str | None:
        """Insert a TEXT body chunk; return full text when complete."""
        try:
            key = (body["session"], body["msg"])
            index = body["i"]
            n = body["n"]
        except (KeyError, TypeError) as exc:
            raise ProtocolError(f"malformed chunk: {exc}") from exc
        data = _decode_chunk_data(body)

        buffer = self._buffers.get(key)
        if buffer is None:
            buffer = {"first": now, "n": n, "chunks": {}}
            self._buffers[key] = buffer
        if index in buffer["chunks"]:
            return None
        total = sum(len(c) for c in buffer["chunks"].values()) + len(data)
        if total > self._max_message_bytes:
            del self._buffers[key]
            return None
        buffer["chunks"][index] = data
        if len(buffer["chunks"]) < buffer["n"]:
            return None
        del self._buffers[key]
        raw = b"".join(buffer["chunks"][i] for i in sorted(buffer["chunks"]))
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError(f"invalid UTF-8 in message: {exc}") from exc

    def expire(self, now: float) -> None:
        """Forget buffers whose first chunk arrived > timeout ago."""
        stale = [
            key
            for key, buffer in self._buffers.items()
            if now - buffer["first"] > self._timeout
        ]
        for key in stale:
            del self._buffers[key]
