"""UDP client: trigger, register/renew, verify + reassemble + paste.

Pure logic behind an injected transport (sendto(data, addr)) and
clock; no sockets here."""

import time
import uuid

from transcribe.net import crypto, protocol

REASSEMBLY_TIMEOUT = 10.0

_KEPT_CONTROLS = frozenset("\n\t")


def sanitize_text(text: str) -> str:
    """Strip C0/C1 control characters except \\n and \\t.
    (DEL 0x7f and 0x80-0x9f are C1-ish — strip those too.)"""
    return "".join(
        char
        for char in text
        if char in _KEPT_CONTROLS
        or not (ord(char) < 0x20 or 0x7F <= ord(char) <= 0x9F)
    )


class Client:
    def __init__(
        self,
        network: dict,
        psk: bytes,
        transport,
        clock=time.time,
        on_state=None,
        on_text=None,
    ):
        """network is a NETWORK_DEFAULTS-shaped dict. Derive the AEAD
        key with crypto.derive_key(psk). Server address is
        (network["server_host"], network["server_port"]). Client
        label is network["client_label"] or "client"."""
        self._network = network
        self._key = crypto.derive_key(psk)
        self._transport = transport
        self._clock = clock
        self._on_state = on_state
        self._on_text = on_text
        self._server = (network["server_host"], network["server_port"])
        self._label = network["client_label"] or "client"
        self._view: str | None = None
        self._own_session: str | None = None
        self._host_session: str | None = None
        self._renew_at: float | None = None
        # body id -> {"data", "next_at", "interval", "resends"}
        self._pending: dict[str, dict] = {}
        self._guard = crypto.ReplayGuard(network["clock_skew"])
        self._reassembler = protocol.Reassembler(
            timeout=REASSEMBLY_TIMEOUT,
            max_message_bytes=network["max_message_bytes"],
        )
        self._delivered: dict[str, float] = {}

    @property
    def view(self) -> str | None:
        """Last-known host session state from STATE messages, or None
        if never heard."""
        return self._view

    def start(self) -> None:
        """Send REGISTER (fire-and-forget) and schedule the first
        RENEW for now + renew_interval."""
        now = self._clock()
        self._send(
            protocol.TYPE_REGISTER, protocol.new_body(now, client=self._label)
        )
        self._renew_at = now + self._network["renew_interval"]

    def stop(self) -> None:
        """Send UNREGISTER (fire-and-forget)."""
        self._send(
            protocol.TYPE_UNREGISTER,
            protocol.new_body(self._clock(), client=self._label),
        )

    def trigger(self) -> None:
        """Hotkey press. Explicit commands, never a toggle:
        - view None or "idle"  -> send reliable START with a fresh
          uuid4-hex session id (remember it).
        - view "recording"     -> send reliable STOP naming the
          active session.
        - view "transcribing" or "error" -> do nothing."""
        now = self._clock()
        if self._view is None or self._view == "idle":
            session = uuid.uuid4().hex
            self._own_session = session
            self._send_reliable(
                protocol.TYPE_START,
                protocol.new_body(now, client=self._label, session=session),
                now,
            )
        elif self._view == "recording":
            session = self._host_session or self._own_session
            self._send_reliable(
                protocol.TYPE_STOP,
                protocol.new_body(now, client=self._label, session=session),
                now,
            )

    def tick(self) -> None:
        """Renew when due, retransmit unACKed reliable sends with
        exponential backoff, expire stale reassembly buffers, and
        purge old delivered-message ids."""
        now = self._clock()
        if self._renew_at is not None and now >= self._renew_at:
            self._send(
                protocol.TYPE_RENEW, protocol.new_body(now, client=self._label)
            )
            self._renew_at = now + self._network["renew_interval"]
        for body_id, entry in list(self._pending.items()):
            if now < entry["next_at"]:
                continue
            if entry["resends"] >= self._network["max_retries"]:
                del self._pending[body_id]
                continue
            self._transport.sendto(entry["data"], self._server)
            entry["resends"] += 1
            entry["interval"] *= 2
            entry["next_at"] = now + entry["interval"]
        self._reassembler.expire(now)
        cutoff = now - 2 * self._network["clock_skew"]
        self._delivered = {
            msg_id: seen_at
            for msg_id, seen_at in self._delivered.items()
            if seen_at >= cutoff
        }

    def handle_datagram(self, data: bytes, addr) -> None:
        """Decode frame -> AEAD open -> decode body -> dispatch. Any
        failure is a silent drop; never an error reply."""
        try:
            msg_type, nonce, ciphertext = protocol.decode_frame(data)
            plaintext = crypto.open_sealed(
                self._key, protocol.header(msg_type), nonce, ciphertext
            )
            body = protocol.decode_body(plaintext)
        except (protocol.ProtocolError, crypto.CryptoError):
            return
        body_id = body.get("id")
        ts = body.get("ts")
        if not isinstance(body_id, str) or not self._is_number(ts):
            return
        if msg_type == protocol.TYPE_ACK:
            self._handle_ack(body)
        elif msg_type == protocol.TYPE_STATE:
            self._handle_state(body, body_id, ts)
        elif msg_type == protocol.TYPE_TEXT:
            self._handle_text(body, body_id, ts)
        # Other types arriving at a client are dropped.

    @staticmethod
    def _is_number(value) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def _send(self, msg_type: int, body: dict) -> bytes:
        plaintext = protocol.encode_body(body)
        nonce, ciphertext = crypto.seal(
            self._key, protocol.header(msg_type), plaintext
        )
        data = protocol.encode_frame(msg_type, nonce, ciphertext)
        self._transport.sendto(data, self._server)
        return data

    def _send_reliable(self, msg_type: int, body: dict, now: float) -> None:
        data = self._send(msg_type, body)
        if not self._network["ack"]:
            return
        interval = self._network["retry_backoff_ms"] / 1000
        self._pending[body["id"]] = {
            "data": data,
            "next_at": now + interval,
            "interval": interval,
            "resends": 0,
        }

    def _handle_ack(self, body: dict) -> None:
        ref = body.get("ref")
        try:
            self._pending.pop(ref, None)
        except TypeError:
            pass

    def _handle_state(self, body: dict, body_id: str, ts: float) -> None:
        now = self._clock()
        if self._guard.check(body_id, ts, now) != "ok":
            return
        self._view = body.get("state")
        self._host_session = body.get("session")
        if self._on_state is not None:
            self._on_state(body)

    def _handle_text(self, body: dict, body_id: str, ts: float) -> None:
        now = self._clock()
        status = self._guard.check(body_id, ts, now)
        if status == "stale":
            return
        if self._network["ack"]:
            self._send(protocol.TYPE_ACK, protocol.new_body(now, ref=body_id))
        if status == "duplicate":
            return
        try:
            text = self._reassembler.add(body, now)
        except protocol.ProtocolError:
            return
        if text is None:
            return
        msg_id = body.get("msg")
        if msg_id in self._delivered:
            return
        self._delivered[msg_id] = now
        if self._on_text is not None:
            self._on_text(sanitize_text(text))
