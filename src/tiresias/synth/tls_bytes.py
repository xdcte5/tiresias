"""Build syntactically valid TLS ClientHello record bytes.

Used to (a) exercise ClientHello detection/parsing deterministically in tests and
(b) stamp realistic handshakes onto synthetic flows so the SNI/JA3 feature path runs
end-to-end without real captures. The encoder is spec-faithful enough that the JA3
computed from its output matches an independently hand-computed JA3.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Common real cipher suites / extensions / curves for plausible-looking hellos.
DEFAULT_CIPHERS = [0x1301, 0x1302, 0x1303, 0xC02B, 0xC02F, 0xC02C, 0xC030]
DEFAULT_EXTENSIONS = [0x0000, 0x0017, 0xFF01, 0x000A, 0x000B, 0x0023, 0x0010, 0x000D, 0x002B]
DEFAULT_CURVES = [0x001D, 0x0017, 0x0018]  # x25519, secp256r1, secp384r1
DEFAULT_POINT_FORMATS = [0x00]


def _u8(n: int) -> bytes:
    return bytes([n & 0xFF])


def _u16(n: int) -> bytes:
    return bytes([(n >> 8) & 0xFF, n & 0xFF])


def _u24(n: int) -> bytes:
    return bytes([(n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF])


def _vec8(payload: bytes) -> bytes:
    return _u8(len(payload)) + payload


def _vec16(payload: bytes) -> bytes:
    return _u16(len(payload)) + payload


@dataclass
class ClientHelloSpec:
    """Everything that determines the SNI and JA3 of a synthetic ClientHello."""

    sni: str | None
    version: int = 0x0303  # TLS 1.2 legacy version in the handshake
    ciphers: list[int] = field(default_factory=lambda: list(DEFAULT_CIPHERS))
    extensions: list[int] = field(default_factory=lambda: list(DEFAULT_EXTENSIONS))
    curves: list[int] = field(default_factory=lambda: list(DEFAULT_CURVES))
    point_formats: list[int] = field(default_factory=lambda: list(DEFAULT_POINT_FORMATS))


def _extension_body(ext_type: int, spec: ClientHelloSpec) -> bytes:
    """Return the extension *data* (without the type/length header) for ext_type."""
    if ext_type == 0x0000 and spec.sni is not None:  # server_name
        host = spec.sni.encode("ascii")
        entry = _u8(0x00) + _vec16(host)  # name_type host_name(0) + hostname
        return _vec16(entry)  # server_name_list
    if ext_type == 0x000A:  # supported_groups (elliptic curves)
        groups = b"".join(_u16(c) for c in spec.curves)
        return _vec16(groups)
    if ext_type == 0x000B:  # ec_point_formats
        fmts = b"".join(_u8(f) for f in spec.point_formats)
        return _vec8(fmts)
    # Other extensions present but empty-bodied — enough for JA3 (only the type list
    # matters there).
    return b""


def build_client_hello(spec: ClientHelloSpec) -> bytes:
    """Return the full TLS record bytes (record header + handshake) for the spec."""
    body = b""
    body += _u16(spec.version)
    body += b"\x00" * 32  # random (zeroed; irrelevant to SNI/JA3)
    body += _vec8(b"")  # session_id (empty)
    body += _vec16(b"".join(_u16(c) for c in spec.ciphers))  # cipher suites
    body += _vec8(b"\x00")  # compression methods: null only

    ext_blob = b""
    for ext_type in spec.extensions:
        data = _extension_body(ext_type, spec)
        ext_blob += _u16(ext_type) + _vec16(data)
    body += _vec16(ext_blob)  # extensions block

    handshake = _u8(0x01) + _u24(len(body)) + body  # client_hello
    record = _u8(0x16) + _u16(0x0301) + _vec16(handshake)  # handshake record
    return record


def client_hello(sni: str | None, **kwargs) -> bytes:
    """Convenience wrapper: ``client_hello("www.youtube.com")``."""
    return build_client_hello(ClientHelloSpec(sni=sni, **kwargs))
