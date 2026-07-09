"""Parse a TLS ClientHello record into features: SNI, JA3, and structural shape.

Pure byte parsing — no scapy. Mirrors the encoder in ``synth.tls_bytes`` and is
robust to malformed / truncated input (returns ``None``/empty rather than raising).

JA3 (github.com/salesforce/ja3) fingerprints the *client* TLS stack:
``md5("Version,Ciphers,Extensions,Curves,PointFormats")`` with decimal values,
"-"-joined, and GREASE values removed. It is a well-known technique in the traffic-
fingerprinting literature; we compute it but keep it out of the default training
feature set (see notes in ``features.extract``), because in a self-generated dataset
a single app == a single JA3 can leak the label.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

# The 16 GREASE values (RFC 8701) excluded from JA3.
_GREASE = frozenset(
    (0x0A0A, 0x1A1A, 0x2A2A, 0x3A3A, 0x4A4A, 0x5A5A, 0x6A6A, 0x7A7A,
     0x8A8A, 0x9A9A, 0xAAAA, 0xBABA, 0xCACA, 0xDADA, 0xEAEA, 0xFAFA)
)

_EXT_SERVER_NAME = 0x0000
_EXT_SUPPORTED_GROUPS = 0x000A
_EXT_EC_POINT_FORMATS = 0x000B


@dataclass(frozen=True)
class TLSInfo:
    sni: str | None
    version: int
    ciphers: tuple[int, ...]
    extensions: tuple[int, ...]
    curves: tuple[int, ...]
    point_formats: tuple[int, ...]
    ja3: str
    ja3_hash: str

    @property
    def n_ciphers(self) -> int:
        return len(self.ciphers)

    @property
    def n_extensions(self) -> int:
        return len(self.extensions)

    @property
    def n_curves(self) -> int:
        return len(self.curves)


class _Cursor:
    """Bounds-checked forward reader over a byte buffer."""

    def __init__(self, buf: bytes) -> None:
        self.buf = buf
        self.i = 0

    def remaining(self) -> int:
        return len(self.buf) - self.i

    def u8(self) -> int:
        if self.remaining() < 1:
            raise ValueError("eof")
        v = self.buf[self.i]
        self.i += 1
        return v

    def u16(self) -> int:
        if self.remaining() < 2:
            raise ValueError("eof")
        v = (self.buf[self.i] << 8) | self.buf[self.i + 1]
        self.i += 2
        return v

    def u24(self) -> int:
        if self.remaining() < 3:
            raise ValueError("eof")
        b = self.buf
        v = (b[self.i] << 16) | (b[self.i + 1] << 8) | b[self.i + 2]
        self.i += 3
        return v

    def take(self, n: int) -> bytes:
        if self.remaining() < n:
            raise ValueError("eof")
        v = self.buf[self.i : self.i + n]
        self.i += n
        return v


def _ja3(version: int, ciphers, extensions, curves, point_formats) -> tuple[str, str]:
    def dash(vals):
        return "-".join(str(v) for v in vals if v not in _GREASE)

    ja3 = ",".join(
        [
            str(version),
            dash(ciphers),
            dash(extensions),
            dash(curves),
            "-".join(str(v) for v in point_formats),
        ]
    )
    return ja3, hashlib.md5(ja3.encode()).hexdigest()


def parse_client_hello(record: bytes | None) -> TLSInfo | None:
    """Parse a TLS ClientHello *record* (starting with 0x16). None if not parseable."""
    if not record or len(record) < 9 or record[0] != 0x16:
        return None
    try:
        # Skip record header (5) + handshake type(1) + handshake length(3).
        cur = _Cursor(record)
        cur.take(5)  # record header
        if cur.u8() != 0x01:  # handshake type client_hello
            return None
        cur.u24()  # handshake length (not trusted; we bound-check as we go)

        version = cur.u16()
        cur.take(32)  # random
        sid_len = cur.u8()
        cur.take(sid_len)  # session id

        cs_len = cur.u16()
        cs_bytes = cur.take(cs_len)
        ciphers = tuple(
            (cs_bytes[i] << 8) | cs_bytes[i + 1] for i in range(0, len(cs_bytes) - 1, 2)
        )

        comp_len = cur.u8()
        cur.take(comp_len)  # compression methods

        extensions: list[int] = []
        curves: tuple[int, ...] = ()
        point_formats: tuple[int, ...] = ()
        sni: str | None = None

        if cur.remaining() >= 2:
            ext_total = cur.u16()
            ext_buf = cur.take(min(ext_total, cur.remaining()))
            ecur = _Cursor(ext_buf)
            while ecur.remaining() >= 4:
                etype = ecur.u16()
                elen = ecur.u16()
                edata = ecur.take(min(elen, ecur.remaining()))
                extensions.append(etype)
                if etype == _EXT_SERVER_NAME:
                    sni = _parse_sni(edata)
                elif etype == _EXT_SUPPORTED_GROUPS:
                    curves = _parse_u16_vec16(edata)
                elif etype == _EXT_EC_POINT_FORMATS:
                    point_formats = _parse_u8_vec8(edata)

        ja3, ja3_hash = _ja3(version, ciphers, extensions, curves, point_formats)
        return TLSInfo(
            sni=sni,
            version=version,
            ciphers=ciphers,
            extensions=tuple(extensions),
            curves=curves,
            point_formats=point_formats,
            ja3=ja3,
            ja3_hash=ja3_hash,
        )
    except (ValueError, IndexError):
        return None


def _parse_sni(data: bytes) -> str | None:
    try:
        cur = _Cursor(data)
        list_len = cur.u16()
        sub = _Cursor(cur.take(list_len))
        while sub.remaining() >= 3:
            name_type = sub.u8()
            name = sub.take(sub.u16())
            if name_type == 0x00:  # host_name
                return name.decode("ascii", errors="ignore")
    except (ValueError, IndexError):
        return None
    return None


def _parse_u16_vec16(data: bytes) -> tuple[int, ...]:
    try:
        cur = _Cursor(data)
        body = cur.take(cur.u16())
        return tuple((body[i] << 8) | body[i + 1] for i in range(0, len(body) - 1, 2))
    except (ValueError, IndexError):
        return ()


def _parse_u8_vec8(data: bytes) -> tuple[int, ...]:
    try:
        cur = _Cursor(data)
        body = cur.take(cur.u8())
        return tuple(body)
    except (ValueError, IndexError):
        return ()
