"""AEAD sealing and replay protection for the wire protocol.

Pure — no I/O, no clock reads (callers pass `now`).
"""

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

KEY_LEN = 32
NONCE_LEN = 12
HKDF_INFO = b"mpet-v1"


class CryptoError(Exception):
    """Raised on any cryptographic failure."""


def generate_key() -> bytes:
    """32 random bytes (os.urandom)."""
    return os.urandom(KEY_LEN)


def encode_key(key: bytes) -> str:
    """Standard base64 str of a 32-byte key.

    CryptoError on wrong length.
    """
    if len(key) != KEY_LEN:
        raise CryptoError(f"key must be {KEY_LEN} bytes, got {len(key)}")
    return base64.b64encode(key).decode("ascii")


def decode_key(data: str) -> bytes:
    """Base64-decode; CryptoError if invalid base64 or not exactly
    32 bytes after decoding. Accepts surrounding whitespace.
    """
    try:
        key = base64.b64decode(data.strip(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CryptoError("invalid base64 key") from exc
    if len(key) != KEY_LEN:
        raise CryptoError(
            f"decoded key must be {KEY_LEN} bytes, got {len(key)}"
        )
    return key


def derive_key(psk: bytes) -> bytes:
    """HKDF-SHA256(psk, salt=None, info=HKDF_INFO, length=32) so the
    raw PSK is never used directly as the AEAD key.
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_LEN,
        salt=None,
        info=HKDF_INFO,
    )
    return hkdf.derive(psk)


def seal(
    key: bytes,
    aad: bytes,
    plaintext: bytes,
    nonce: bytes | None = None,
) -> tuple[bytes, bytes]:
    """ChaCha20-Poly1305 encrypt.

    Fresh 12-byte os.urandom nonce when nonce is None. Returns
    (nonce, ciphertext). CryptoError on bad key/nonce length.
    """
    if len(key) != KEY_LEN:
        raise CryptoError(f"key must be {KEY_LEN} bytes, got {len(key)}")
    if nonce is None:
        nonce = os.urandom(NONCE_LEN)
    elif len(nonce) != NONCE_LEN:
        raise CryptoError(f"nonce must be {NONCE_LEN} bytes, got {len(nonce)}")
    cipher = ChaCha20Poly1305(key)
    ciphertext = cipher.encrypt(nonce, plaintext, aad)
    return nonce, ciphertext


def open_sealed(
    key: bytes,
    aad: bytes,
    nonce: bytes,
    ciphertext: bytes,
) -> bytes:
    """Decrypt+verify; raise CryptoError on ANY failure (wrong key,
    tampered ciphertext, tampered aad, bad lengths).
    """
    if len(key) != KEY_LEN:
        raise CryptoError(f"key must be {KEY_LEN} bytes, got {len(key)}")
    if len(nonce) != NONCE_LEN:
        raise CryptoError(f"nonce must be {NONCE_LEN} bytes, got {len(nonce)}")
    try:
        cipher = ChaCha20Poly1305(key)
        return cipher.decrypt(nonce, ciphertext, aad)
    except (InvalidTag, ValueError) as exc:
        raise CryptoError("decryption failed") from exc


class ReplayGuard:
    """Freshness + dedup for message bodies.

    check(body_id, ts, now) returns one of:
      "ok"        — fresh and unseen; the id is recorded
      "duplicate" — id already seen (caller may re-ACK, must not
                    re-process)
      "stale"     — |ts - now| > clock_skew; dropped, NOT recorded
    Seen ids expire after 2 * clock_skew (lazy purge inside check is
    fine).
    """

    def __init__(self, clock_skew: float = 30.0):
        self._clock_skew = clock_skew
        self._seen: dict[str, float] = {}

    def check(self, body_id: str, ts: float, now: float) -> str:
        cutoff = now - 2 * self._clock_skew
        self._seen = {
            seen_id: seen_at
            for seen_id, seen_at in self._seen.items()
            if seen_at >= cutoff
        }
        if abs(ts - now) > self._clock_skew:
            return "stale"
        if body_id in self._seen:
            return "duplicate"
        self._seen[body_id] = now
        return "ok"
