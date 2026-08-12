"""UDP host: subscriber registry, session control, reliable TEXT.

The Host owns the authoritative session state machine. It receives
REGISTER/RENEW/UNREGISTER heartbeats and START/STOP commands from
clients, drives the recorder via the ``on_start``/``on_stop``
callbacks, and publishes STATE and TEXT datagrams back.

All I/O goes through an injected transport (``sendto(data, addr)``)
and an injected clock, so the logic is fully testable without a
socket.
"""

import logging
import time
import uuid

from transcribe.net import crypto, protocol

logger = logging.getLogger(__name__)

# Cap on how many subscribers the registry will hold.
MAX_SUBSCRIBERS = 32

# Minimum seconds between accepted STARTs (mic-thrash rate limit).
START_RATE_LIMIT = 1.0


class Host:
    """Authoritative session host bound to a fake-able transport."""

    def __init__(
        self,
        network: dict,
        psk: bytes,
        transport,
        clock=time.time,
        on_start=None,
        on_stop=None,
    ):
        self._network = network
        self._key = crypto.derive_key(psk)
        self._transport = transport
        self._clock = clock
        self._on_start = on_start
        self._on_stop = on_stop
        self._guard = crypto.ReplayGuard(network["clock_skew"])
        self._backoff = network["retry_backoff_ms"] / 1000.0
        # addr -> {"label": str, "last_seen": float}
        self._subscribers: dict = {}
        # (addr, body id) -> {"data", "addr", "tries", "next_at"}
        self._pending: dict = {}
        # body ids we have ACKed, for re-ACKing duplicates
        self._acked: dict[str, float] = {}
        self._state = "idle"
        self._session: str | None = None
        self._initiator_label: str | None = None
        self._initiator_addr = None
        self._started_at: float | None = None
        self._last_start: float | None = None

    @property
    def state(self) -> str:
        return self._state

    @property
    def session(self) -> str | None:
        return self._session

    @property
    def initiator(self) -> str | None:
        return self._initiator_label

    @property
    def initiator_addr(self):
        """The initiating client's address, or None for a local
        (host-hotkey) session."""
        return self._initiator_addr

    def local_start(self) -> bool:
        """Start a session from the host's own hotkey."""
        now = self._clock()
        if self._state != "idle":
            return False
        if (
            self._last_start is not None
            and now - self._last_start < START_RATE_LIMIT
        ):
            return False
        self._last_start = now
        self._session = uuid.uuid4().hex
        self._initiator_label = "host"
        self._initiator_addr = None
        self._started_at = now
        self._state = "recording"
        if not self._run_on_start():
            return False
        self.publish_state()
        logger.info("Session %s started locally", self._session)
        return True

    def local_stop(self) -> bool:
        """Stop the active recording from the host's own hotkey."""
        if self._state != "recording":
            return False
        self._begin_transcribing()
        return True

    def _run_on_start(self) -> bool:
        """Invoke on_start; on failure abort the session cleanly."""
        try:
            if self._on_start is not None:
                self._on_start()
        except Exception:
            logger.exception("Recording failed to start")
            self._state = "error"
            self.publish_state()
            self.finish_session()
            return False
        return True

    # -- sending ------------------------------------------------------

    def _send(self, msg_type: int, body: dict, addr) -> bytes:
        plaintext = protocol.encode_body(body)
        nonce, ct = crypto.seal(
            self._key, protocol.header(msg_type), plaintext
        )
        datagram = protocol.encode_frame(msg_type, nonce, ct)
        self._transport.sendto(datagram, addr)
        return datagram

    def _send_reliable(self, msg_type: int, body: dict, addr) -> None:
        datagram = self._send(msg_type, body, addr)
        if not self._network["ack"]:
            return
        self._pending[(addr, body["id"])] = {
            "data": datagram,
            "addr": addr,
            "tries": 0,
            "next_at": self._clock() + self._backoff,
        }

    def _ack(self, ref: str, addr) -> None:
        body = protocol.new_body(self._clock(), ref=ref)
        self._send(protocol.TYPE_ACK, body, addr)
        self._acked[ref] = self._clock()

    def publish_state(self, state: str | None = None) -> None:
        """Broadcast the session state to all subscribers."""
        state = state or self._state
        now = self._clock()
        for addr in list(self._subscribers):
            body = protocol.new_body(
                now,
                state=state,
                session=self._session,
                initiator=self._initiator_label,
            )
            self._send(protocol.TYPE_STATE, body, addr)

    def publish_text(self, text: str) -> None:
        """Chunk and reliably send a transcription per deliver_to."""
        now = self._clock()
        if self._network["deliver_to"] == "all":
            targets = set(self._subscribers)
            if self._initiator_addr is not None:
                targets.add(self._initiator_addr)
        else:
            if self._initiator_addr is None:
                # local (host-hotkey) session: nothing to network
                logger.debug("Local session; text stays on the host")
                return
            targets = {self._initiator_addr}
        bodies = protocol.split_message(
            text,
            self._session or "",
            uuid.uuid4().hex,
            now,
            self._network["max_datagram_bytes"],
        )
        for addr in targets:
            for body in bodies:
                self._send_reliable(protocol.TYPE_TEXT, body, addr)

    def finish_session(self) -> None:
        """Return to idle and broadcast the terminal STATE."""
        self._state = "idle"
        self.publish_state()
        self._session = None
        self._initiator_label = None
        self._initiator_addr = None
        self._started_at = None

    # -- receiving ----------------------------------------------------

    def handle_datagram(self, data: bytes, addr) -> None:
        """Verify, replay-check, and dispatch one datagram."""
        try:
            msg_type, nonce, ct = protocol.decode_frame(data)
            plaintext = crypto.open_sealed(
                self._key, protocol.header(msg_type), nonce, ct
            )
            body = protocol.decode_body(plaintext)
        except (protocol.ProtocolError, crypto.CryptoError):
            return
        body_id = body.get("id")
        ts = body.get("ts")
        if not isinstance(body_id, str) or not isinstance(ts, (int, float)):
            return
        now = self._clock()
        if msg_type == protocol.TYPE_ACK:
            ref = body.get("ref")
            self._pending.pop((addr, ref), None)
            return
        verdict = self._guard.check(body_id, ts, now)
        if verdict == "stale":
            return
        if verdict == "duplicate":
            # Re-ACK duplicates of messages we already accepted so a
            # lost ACK cannot wedge the sender, but never re-process.
            if body_id in self._acked:
                self._ack(body_id, addr)
            return
        if msg_type in (protocol.TYPE_REGISTER, protocol.TYPE_RENEW):
            self._touch_subscriber(addr, body.get("client"), now)
        elif msg_type == protocol.TYPE_UNREGISTER:
            self._subscribers.pop(addr, None)
        elif msg_type == protocol.TYPE_START:
            self._handle_start(body, addr, now)
        elif msg_type == protocol.TYPE_STOP:
            self._handle_stop(body, addr, now)
        # TYPE_AUDIO is reserved; TYPE_STATE/TEXT are host-outbound.

    def _touch_subscriber(self, addr, label, now: float) -> None:
        if addr not in self._subscribers:
            if len(self._subscribers) >= MAX_SUBSCRIBERS:
                logger.warning("Subscriber registry full; ignoring %s", addr)
                return
            self._subscribers[addr] = {}
        self._subscribers[addr] = {
            "label": label or "",
            "last_seen": now,
        }

    def _allowed(self, label) -> bool:
        allowed = self._network.get("allowed_clients")
        if allowed is None:
            return True
        return label in allowed

    def _handle_start(self, body: dict, addr, now: float) -> None:
        label = body.get("client")
        session = body.get("session")
        if not isinstance(session, str) or not session:
            return
        if not self._allowed(label):
            logger.warning("Rejected START from disallowed %r", label)
            return
        self._touch_subscriber(addr, label, now)
        if self._state == "idle":
            if (
                self._last_start is not None
                and now - self._last_start < START_RATE_LIMIT
            ):
                logger.warning("START rate-limited from %r", label)
                return
            self._last_start = now
            self._session = session
            self._initiator_label = label or ""
            self._initiator_addr = addr
            self._started_at = now
            self._state = "recording"
            self._ack(body["id"], addr)
            if not self._run_on_start():
                return
            self.publish_state()
            logger.info("Session %s started by %r", session, label)
        elif self._state == "recording" and session == self._session:
            # duplicate/retried START for the live session: idempotent
            self._ack(body["id"], addr)
        else:
            # busy with another session: reject silently, sync sender
            body_out = protocol.new_body(
                now,
                state=self._state,
                session=self._session,
                initiator=self._initiator_label,
            )
            self._send(protocol.TYPE_STATE, body_out, addr)

    def _handle_stop(self, body: dict, addr, now: float) -> None:
        label = body.get("client")
        if not self._allowed(label):
            return
        self._touch_subscriber(addr, label, now)
        self._ack(body["id"], addr)
        session = body.get("session")
        if self._state == "recording" and session == self._session:
            self._begin_transcribing()
        # any other STOP is stale: ACKed (idempotent) but ignored

    def _begin_transcribing(self) -> None:
        self._state = "transcribing"
        self.publish_state()
        logger.info("Session %s stopping; transcribing", self._session)
        if self._on_stop is not None:
            self._on_stop()

    # -- periodic work ------------------------------------------------

    def tick(self) -> None:
        """Prune subscribers, retransmit, enforce max_record_seconds."""
        now = self._clock()
        ttl = self._network["subscriber_ttl"]
        for addr in list(self._subscribers):
            if now - self._subscribers[addr]["last_seen"] > ttl:
                del self._subscribers[addr]
        if (
            self._state == "recording"
            and self._started_at is not None
            and now - self._started_at >= self._network["max_record_seconds"]
        ):
            logger.warning(
                "Auto-stopping session %s after max_record_seconds",
                self._session,
            )
            self._begin_transcribing()
        for key in list(self._pending):
            entry = self._pending.get(key)
            if entry is None or now < entry["next_at"]:
                continue
            if entry["tries"] >= self._network["max_retries"]:
                logger.warning("Giving up on unACKed datagram to %s", key[0])
                del self._pending[key]
                continue
            self._transport.sendto(entry["data"], entry["addr"])
            entry["tries"] += 1
            entry["next_at"] = now + self._backoff * (2 ** entry["tries"])
        cutoff = now - 2 * self._network["clock_skew"]
        self._acked = {
            ref: at for ref, at in self._acked.items() if at >= cutoff
        }
