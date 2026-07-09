"""Minimal TLS ClientHello *detection* (not parsing).

Sprint 1 only needs to recognise and stash the raw ClientHello record bytes off a
TCP payload. Parsing those bytes into SNI / JA3 / cipher shape happens in
``tiresias.features.tls`` (Sprint 2). Kept pure (no scapy) so it is trivially
unit-testable.
"""

from __future__ import annotations

# TLS record content type 22 = handshake; handshake type 1 = client_hello.
_TLS_HANDSHAKE = 0x16
_CLIENT_HELLO = 0x01
_MAX_RECORD = 16384  # TLS record payload cap; guards against absurd lengths.


def extract_client_hello(payload: bytes) -> bytes | None:
    """Return the TLS record bytes if ``payload`` begins a ClientHello, else None.

    Structure checked:
        byte 0      content type == 0x16 (handshake)
        bytes 1..2  legacy record version (0x03 0x0X)
        bytes 3..4  record length
        byte 5      handshake type == 0x01 (client_hello)
    """
    if len(payload) < 6:
        return None
    if payload[0] != _TLS_HANDSHAKE:
        return None
    if payload[1] != 0x03:  # all TLS/SSL3 record versions start 0x03
        return None
    record_len = (payload[3] << 8) | payload[4]
    if record_len <= 0 or record_len > _MAX_RECORD:
        return None
    if payload[5] != _CLIENT_HELLO:
        return None
    # Keep only the handshake record we have on hand (may be a single segment).
    end = min(len(payload), 5 + record_len)
    return bytes(payload[:end])
