import base64

import pytest

from transcribe.net.crypto import (
    HKDF_INFO,
    KEY_LEN,
    NONCE_LEN,
    CryptoError,
    ReplayGuard,
    decode_key,
    derive_key,
    encode_key,
    generate_key,
    open_sealed,
    seal,
)


class TestConstants:
    def test_key_len(self):
        assert KEY_LEN == 32

    def test_nonce_len(self):
        assert NONCE_LEN == 12

    def test_hkdf_info(self):
        assert HKDF_INFO == b"mpet-v1"


class TestGenerateKey:
    def test_returns_32_bytes(self):
        key = generate_key()
        assert isinstance(key, bytes)
        assert len(key) == 32

    def test_two_calls_differ(self):
        assert generate_key() != generate_key()


class TestEncodeDecodeKey:
    def test_round_trip(self):
        key = b"\x01" * 32
        encoded = encode_key(key)
        assert isinstance(encoded, str)
        assert decode_key(encoded) == key

    def test_round_trip_random_key(self):
        key = generate_key()
        assert decode_key(encode_key(key)) == key

    def test_encode_rejects_short_key(self):
        with pytest.raises(CryptoError):
            encode_key(b"\x01" * 31)

    def test_encode_rejects_long_key(self):
        with pytest.raises(CryptoError):
            encode_key(b"\x01" * 33)

    def test_encode_rejects_empty(self):
        with pytest.raises(CryptoError):
            encode_key(b"")

    def test_decode_rejects_bad_base64(self):
        with pytest.raises(CryptoError):
            decode_key("not!!valid@@base64%%")

    def test_decode_rejects_wrong_decoded_length(self):
        short = base64.b64encode(b"\x01" * 16).decode("ascii")
        with pytest.raises(CryptoError):
            decode_key(short)

    def test_decode_accepts_surrounding_whitespace(self):
        key = b"\x02" * 32
        encoded = "  " + encode_key(key) + "\n"
        assert decode_key(encoded) == key


class TestDeriveKey:
    def test_deterministic(self):
        psk = b"\x03" * 32
        assert derive_key(psk) == derive_key(psk)

    def test_differs_for_different_psk(self):
        assert derive_key(b"\x03" * 32) != derive_key(b"\x04" * 32)

    def test_differs_from_raw_psk(self):
        psk = b"\x05" * 32
        assert derive_key(psk) != psk

    def test_returns_32_bytes(self):
        derived = derive_key(b"any length psk")
        assert isinstance(derived, bytes)
        assert len(derived) == 32


class TestSealOpen:
    def setup_method(self):
        self.key = b"\x07" * 32
        self.aad = b"header-bytes"
        self.plaintext = b"hello, secure world"

    def test_round_trip_auto_nonce(self):
        nonce, ciphertext = seal(self.key, self.aad, self.plaintext)
        assert (
            open_sealed(self.key, self.aad, nonce, ciphertext)
            == self.plaintext
        )

    def test_round_trip_explicit_nonce(self):
        nonce_in = b"\x0a" * 12
        nonce, ciphertext = seal(
            self.key, self.aad, self.plaintext, nonce=nonce_in
        )
        assert nonce == nonce_in
        assert (
            open_sealed(self.key, self.aad, nonce, ciphertext)
            == self.plaintext
        )

    def test_auto_nonce_is_12_bytes(self):
        nonce, _ = seal(self.key, self.aad, self.plaintext)
        assert isinstance(nonce, bytes)
        assert len(nonce) == 12

    def test_auto_nonce_unique_across_calls(self):
        nonces = {
            seal(self.key, self.aad, self.plaintext)[0] for _ in range(20)
        }
        assert len(nonces) == 20

    def test_empty_plaintext_round_trip(self):
        nonce, ciphertext = seal(self.key, self.aad, b"")
        assert open_sealed(self.key, self.aad, nonce, ciphertext) == b""

    def test_seal_rejects_bad_key_length(self):
        with pytest.raises(CryptoError):
            seal(b"\x07" * 16, self.aad, self.plaintext)

    def test_seal_rejects_bad_nonce_length(self):
        with pytest.raises(CryptoError):
            seal(self.key, self.aad, self.plaintext, nonce=b"\x0a" * 8)

    def test_open_rejects_wrong_key(self):
        nonce, ciphertext = seal(self.key, self.aad, self.plaintext)
        with pytest.raises(CryptoError):
            open_sealed(b"\x08" * 32, self.aad, nonce, ciphertext)

    def test_open_rejects_flipped_ciphertext_byte(self):
        nonce, ciphertext = seal(self.key, self.aad, self.plaintext)
        tampered = bytes([ciphertext[0] ^ 0x01]) + ciphertext[1:]
        with pytest.raises(CryptoError):
            open_sealed(self.key, self.aad, nonce, tampered)

    def test_open_rejects_flipped_tag_byte(self):
        nonce, ciphertext = seal(self.key, self.aad, self.plaintext)
        tampered = ciphertext[:-1] + bytes([ciphertext[-1] ^ 0x01])
        with pytest.raises(CryptoError):
            open_sealed(self.key, self.aad, nonce, tampered)

    def test_open_rejects_different_aad(self):
        nonce, ciphertext = seal(self.key, self.aad, self.plaintext)
        with pytest.raises(CryptoError):
            open_sealed(self.key, b"other-aad", nonce, ciphertext)

    def test_open_rejects_truncated_ciphertext(self):
        nonce, ciphertext = seal(self.key, self.aad, self.plaintext)
        with pytest.raises(CryptoError):
            open_sealed(self.key, self.aad, nonce, ciphertext[:-1])

    def test_open_rejects_wrong_nonce(self):
        nonce, ciphertext = seal(
            self.key, self.aad, self.plaintext, nonce=b"\x0b" * 12
        )
        with pytest.raises(CryptoError):
            open_sealed(self.key, self.aad, b"\x0c" * 12, ciphertext)

    def test_open_rejects_bad_key_length(self):
        nonce, ciphertext = seal(self.key, self.aad, self.plaintext)
        with pytest.raises(CryptoError):
            open_sealed(b"\x07" * 16, self.aad, nonce, ciphertext)

    def test_open_rejects_bad_nonce_length(self):
        nonce, ciphertext = seal(self.key, self.aad, self.plaintext)
        with pytest.raises(CryptoError):
            open_sealed(self.key, self.aad, b"\x0a" * 8, ciphertext)

    def test_different_key_never_opens(self):
        key_a = derive_key(b"psk-a")
        key_b = derive_key(b"psk-b")
        nonce, ciphertext = seal(key_a, self.aad, self.plaintext)
        with pytest.raises(CryptoError):
            open_sealed(key_b, self.aad, nonce, ciphertext)


class TestReplayGuard:
    def test_fresh_id_ok(self):
        guard = ReplayGuard(clock_skew=30.0)
        assert guard.check("id-1", 100.0, 100.0) == "ok"

    def test_same_id_duplicate(self):
        guard = ReplayGuard(clock_skew=30.0)
        guard.check("id-1", 100.0, 100.0)
        assert guard.check("id-1", 100.0, 100.0) == "duplicate"

    def test_same_id_fresh_ts_still_duplicate(self):
        guard = ReplayGuard(clock_skew=30.0)
        guard.check("id-1", 100.0, 100.0)
        assert guard.check("id-1", 105.0, 105.0) == "duplicate"

    def test_distinct_ids_both_ok(self):
        guard = ReplayGuard(clock_skew=30.0)
        assert guard.check("id-1", 100.0, 100.0) == "ok"
        assert guard.check("id-2", 100.0, 100.0) == "ok"

    def test_too_old_is_stale(self):
        guard = ReplayGuard(clock_skew=30.0)
        assert guard.check("id-1", 100.0, 140.0) == "stale"

    def test_too_far_in_future_is_stale(self):
        guard = ReplayGuard(clock_skew=30.0)
        assert guard.check("id-1", 140.0, 100.0) == "stale"

    def test_boundary_within_skew_past_accepted(self):
        guard = ReplayGuard(clock_skew=30.0)
        assert guard.check("id-1", 70.0, 100.0) == "ok"

    def test_boundary_within_skew_future_accepted(self):
        guard = ReplayGuard(clock_skew=30.0)
        assert guard.check("id-1", 130.0, 100.0) == "ok"

    def test_seen_id_forgotten_after_expiry(self):
        guard = ReplayGuard(clock_skew=30.0)
        assert guard.check("id-1", 100.0, 100.0) == "ok"
        # Advance well beyond 2 * clock_skew; a fresh ts with the
        # same id proves the old record expired.
        assert guard.check("id-1", 300.0, 300.0) == "ok"

    def test_stale_does_not_record_id(self):
        guard = ReplayGuard(clock_skew=30.0)
        assert guard.check("id-1", 10.0, 100.0) == "stale"
        assert guard.check("id-1", 100.0, 100.0) == "ok"

    def test_default_clock_skew(self):
        guard = ReplayGuard()
        assert guard.check("id-1", 71.0, 100.0) == "ok"
        assert guard.check("id-2", 69.0, 100.0) == "stale"
