"""ClientHello detection off a raw TCP payload."""

from tiresias.capture.tls_detect import extract_client_hello
from tiresias.synth.tls_bytes import client_hello


def test_detects_real_client_hello():
    ch = client_hello("www.youtube.com")
    got = extract_client_hello(ch)
    assert got is not None
    assert got[0] == 0x16 and got[5] == 0x01


def test_detects_within_larger_buffer():
    ch = client_hello("zoom.us")
    # ClientHello followed by trailing bytes (e.g. TCP coalescing) still detected.
    got = extract_client_hello(ch + b"trailing-garbage")
    assert got is not None
    # We only keep the record we recognise, not the trailing bytes.
    assert len(got) <= len(ch) + 0  # end clamped to record length


def test_rejects_non_tls():
    assert extract_client_hello(b"GET / HTTP/1.1\r\n") is None
    assert extract_client_hello(b"") is None
    assert extract_client_hello(b"\x16\x03") is None  # too short


def test_rejects_server_hello():
    # 0x16 handshake but handshake type 0x02 (server_hello), not client_hello.
    payload = b"\x16\x03\x03\x00\x10\x02" + b"\x00" * 14
    assert extract_client_hello(payload) is None
