"""ClientHello parsing: SNI extraction and JA3 correctness (encoder <-> parser)."""

import hashlib

from tiresias.features.tls import parse_client_hello
from tiresias.synth.tls_bytes import ClientHelloSpec, build_client_hello


def test_sni_roundtrip():
    rec = build_client_hello(ClientHelloSpec(sni="www.youtube.com"))
    info = parse_client_hello(rec)
    assert info is not None
    assert info.sni == "www.youtube.com"


def test_ja3_exact_value():
    # A fully-specified hello -> a known JA3 string, independent of the parser's md5.
    spec = ClientHelloSpec(
        sni="zoom.us",
        version=0x0303,
        ciphers=[0x1301, 0xC02F],
        extensions=[0x0000, 0x000A, 0x000B],
        curves=[0x001D, 0x0017],
        point_formats=[0x00],
    )
    info = parse_client_hello(build_client_hello(spec))
    assert info is not None
    expected_ja3 = "771,4865-49199,0-10-11,29-23,0"
    assert info.ja3 == expected_ja3
    assert info.ja3_hash == hashlib.md5(expected_ja3.encode()).hexdigest()


def test_ja3_excludes_grease():
    spec = ClientHelloSpec(
        sni=None,
        ciphers=[0x0A0A, 0x1301],  # first is GREASE
        extensions=[0x1A1A, 0x000A],  # first is GREASE
        curves=[0x001D],
        point_formats=[0x00],
    )
    info = parse_client_hello(build_client_hello(spec))
    assert info is not None
    # GREASE values dropped from cipher and extension lists in JA3.
    assert info.ja3.split(",")[1] == "4865"
    assert "6682" not in info.ja3  # 0x1a1a decimal, must be absent


def test_counts_and_no_sni():
    spec = ClientHelloSpec(sni=None, ciphers=[0x1301, 0x1302, 0x1303])
    info = parse_client_hello(build_client_hello(spec))
    assert info is not None
    assert info.sni is None
    assert info.n_ciphers == 3


def test_malformed_returns_none():
    assert parse_client_hello(None) is None
    assert parse_client_hello(b"") is None
    assert parse_client_hello(b"\x16\x03\x01\x00\x05notreal") is None
    assert parse_client_hello(b"not tls at all") is None
