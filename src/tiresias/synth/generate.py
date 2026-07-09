"""Synthetic labeled traffic generator.

Produces :class:`FlowRecord` objects whose *shape* (packet sizes, timing, direction
balance, burstiness) is characteristic of each target class, with a class-appropriate
TLS ClientHello (distinct SNI and JA3 per class) stamped on TLS flows.

This exists so the entire downstream pipeline — features, model training, streaming
inference, dashboard — can run and be tested end-to-end **before** any real capture.
Real captures then replace this generator to produce the headline evaluation numbers.
The class profiles are deliberately overlapping in the ways the spec predicts (e.g.
gaming vs video-conferencing both small+frequent) so the model faces a realistic,
non-trivial problem rather than a separable toy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..flows.key import FlowKey
from ..flows.record import BACKWARD, FORWARD, FlowRecord
from .tls_bytes import ClientHelloSpec, build_client_hello

CLIENT_IP = "10.0.0.5"


@dataclass
class ClassProfile:
    label: str
    protocol: str
    n_packets: tuple[int, int]  # inclusive range
    fwd_size: tuple[float, float]  # (mean, std) bytes
    bwd_size: tuple[float, float]
    iat: tuple[float, float]  # (mean, std) seconds
    download_ratio: float  # P(a given packet is backward/download)
    burst: bool  # inject periodic idle gaps (streaming-style)
    tls: bool
    sni_pool: list[str] = field(default_factory=list)
    # A class-specific cipher list => a class-specific JA3 (simulating distinct apps).
    ciphers: list[int] = field(default_factory=list)


PROFILES: list[ClassProfile] = [
    ClassProfile("video_streaming", "TCP", (60, 100), (90, 30), (1350, 120), (0.020, 0.05),
                 download_ratio=0.82, burst=True, tls=True,
                 sni_pool=["r1---sn-video.googlevideo.com", "www.youtube.com"],
                 ciphers=[0x1301, 0x1302, 0x1303, 0xC02B, 0xC02F]),
    ClassProfile("video_conferencing", "TCP", (60, 100), (350, 150), (450, 180), (0.028, 0.010),
                 download_ratio=0.52, burst=False, tls=True,
                 sni_pool=["us01.zoom.us", "meet.google.com"],
                 ciphers=[0x1301, 0x1302, 0xC02B, 0xC02C, 0xCCA9]),
    ClassProfile("web_browsing", "TCP", (12, 45), (250, 200), (900, 450), (0.20, 0.30),
                 download_ratio=0.66, burst=True, tls=True,
                 sni_pool=["en.wikipedia.org", "github.com", "www.reddit.com"],
                 ciphers=[0x1301, 0x1302, 0x1303, 0xC02F, 0xC030, 0xCCA8]),
    ClassProfile("file_transfer", "TCP", (80, 100), (80, 20), (1460, 40), (0.004, 0.002),
                 download_ratio=0.90, burst=False, tls=True,
                 sni_pool=["dl.dropboxusercontent.com", "s3.amazonaws.com"],
                 ciphers=[0x1301, 0x1302, 0x1303, 0xC02B, 0xC02F, 0xC030]),
    ClassProfile("gaming", "UDP", (60, 100), (110, 40), (160, 60), (0.016, 0.008),
                 download_ratio=0.50, burst=False, tls=False,
                 sni_pool=[], ciphers=[]),
    ClassProfile("music_streaming", "TCP", (25, 60), (110, 40), (900, 300), (0.10, 0.12),
                 download_ratio=0.78, burst=True, tls=True,
                 sni_pool=["audio-fa.scdn.co", "api.spotify.com"],
                 ciphers=[0x1301, 0x1302, 0xC02B, 0xC02F]),
    ClassProfile("vpn", "UDP", (70, 100), (900, 400), (950, 400), (0.010, 0.008),
                 download_ratio=0.55, burst=False, tls=False,
                 sni_pool=[], ciphers=[]),
    ClassProfile("dns_background", "UDP", (4, 12), (70, 20), (120, 40), (0.9, 1.2),
                 download_ratio=0.50, burst=False, tls=False,
                 sni_pool=[], ciphers=[]),
]

PROFILE_BY_LABEL = {p.label: p for p in PROFILES}


def _clamp_size(x: float) -> int:
    return int(min(1500.0, max(40.0, x)))


def generate_flow(
    profile: ClassProfile,
    rng: np.random.Generator,
    start_ts: float,
    server_ip: str,
) -> FlowRecord:
    """Generate one FlowRecord matching ``profile``."""
    n = int(rng.integers(profile.n_packets[0], profile.n_packets[1] + 1))
    client_port = int(rng.integers(1024, 65535))
    server_port = 443 if profile.protocol == "TCP" else int(rng.choice([443, 53, 3478, 51820]))

    key, _ = FlowKey.normalize(CLIENT_IP, client_port, server_ip, server_port, profile.protocol)
    flow = FlowRecord(key=key, initiator=(CLIENT_IP, client_port), start_ts=start_ts, last_ts=start_ts)

    if profile.tls and profile.sni_pool:
        sni = str(rng.choice(profile.sni_pool))
        flow.client_hello = build_client_hello(ClientHelloSpec(sni=sni, ciphers=list(profile.ciphers)))

    t = start_ts
    for i in range(n):
        is_download = rng.random() < profile.download_ratio
        direction = BACKWARD if is_download else FORWARD
        mean, std = profile.bwd_size if is_download else profile.fwd_size
        size = _clamp_size(rng.normal(mean, std))

        # Advance time; bursty classes occasionally insert a longer idle gap.
        iat_mean, iat_std = profile.iat
        gap = max(0.0, rng.normal(iat_mean, iat_std))
        if profile.burst and i > 0 and rng.random() < 0.08:
            gap += rng.uniform(0.3, 1.2)
        t += gap
        flow.sizes.append(size * direction)
        flow.timestamps.append(t)
        flow.directions.append(direction)
    flow.last_ts = t
    return flow


def generate_dataset(
    sessions_per_class: int = 20,
    flows_per_session: tuple[int, int] = (3, 8),
    seed: int = 7,
) -> list[tuple[FlowRecord, str, str]]:
    """Generate ``(flow, label, session_id)`` triples.

    A *session* is a contiguous run of same-class flows sharing a ``session_id`` —
    this mirrors "run app X for a few minutes" and is what the session-based train/
    test split (Sprint 3) groups on, so flows from one session never straddle the
    split.
    """
    master = np.random.default_rng(seed)
    out: list[tuple[FlowRecord, str, str]] = []
    for profile in PROFILES:
        for s in range(sessions_per_class):
            session_id = f"{profile.label}__s{s:03d}"
            # Per-session RNG so a session is a coherent, reproducible unit.
            rng = np.random.default_rng(master.integers(0, 2**32))
            server_ip = f"93.{int(rng.integers(0,256))}.{int(rng.integers(0,256))}.{int(rng.integers(1,255))}"
            n_flows = int(rng.integers(flows_per_session[0], flows_per_session[1] + 1))
            base_ts = float(rng.uniform(1_600_000_000, 1_700_000_000))
            t = base_ts
            for _ in range(n_flows):
                flow = generate_flow(profile, rng, start_ts=t, server_ip=server_ip)
                out.append((flow, profile.label, session_id))
                t = flow.last_ts + float(rng.uniform(0.5, 5.0))
    return out
