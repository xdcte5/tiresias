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

# TLS client stacks reflect the *browser/library*, not the application class — a
# Chrome tab streaming video and a Chrome tab browsing share a JA3. Each TLS flow
# draws a stack independent of its class, so TLS handshake shape is a realistic weak
# signal rather than a class giveaway. (This is also why JA3 is only a partial leak,
# not a perfect one — see the ablation in the eval report.)
BROWSER_STACKS: list[list[int]] = [
    [0x1301, 0x1302, 0x1303, 0xC02B, 0xC02F, 0xC02C, 0xC030, 0xCCA9, 0xCCA8],  # chrome-ish
    [0x1301, 0x1303, 0x1302, 0xC02C, 0xC030, 0xC02B, 0xC02F],  # firefox-ish
    [0x1301, 0x1302, 0x1303, 0xC02B, 0xC02F],  # safari/native-ish
]


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


# Profiles deliberately OVERLAP in the ways the spec predicts, so the model faces a
# realistic (~85-92%), non-trivial problem rather than perfectly separable toy classes:
#   * gaming vs video_conferencing — both small, frequent, near-symmetric.
#   * web_browsing vs music_streaming — both medium, bursty, download-leaning.
#   * vpn — tunneled, so its shape overlaps large-packet classes (file/video).
# Per-session "style" jitter (see generate_dataset) adds cross-session variance on top,
# which is what makes the session-based split genuinely harder than a flow-random one.
PROFILES: list[ClassProfile] = [
    ClassProfile("video_streaming", "TCP", (55, 100), (110, 60), (1200, 320), (0.022, 0.05),
                 download_ratio=0.80, burst=True, tls=True,
                 sni_pool=["r1---sn-video.googlevideo.com", "www.youtube.com"],
                 ciphers=[0x1301, 0x1302, 0x1303, 0xC02B, 0xC02F]),
    ClassProfile("video_conferencing", "TCP", (45, 95), (260, 150), (360, 200), (0.030, 0.015),
                 download_ratio=0.54, burst=False, tls=True,
                 sni_pool=["us01.zoom.us", "meet.google.com"],
                 ciphers=[0x1301, 0x1302, 0xC02B, 0xC02C, 0xCCA9]),
    ClassProfile("web_browsing", "TCP", (12, 55), (300, 260), (760, 430), (0.18, 0.28),
                 download_ratio=0.68, burst=True, tls=True,
                 sni_pool=["en.wikipedia.org", "github.com", "www.reddit.com"],
                 ciphers=[0x1301, 0x1302, 0x1303, 0xC02F, 0xC030, 0xCCA8]),
    ClassProfile("file_transfer", "TCP", (70, 100), (110, 70), (1380, 180), (0.006, 0.004),
                 download_ratio=0.88, burst=False, tls=True,
                 sni_pool=["dl.dropboxusercontent.com", "s3.amazonaws.com"],
                 ciphers=[0x1301, 0x1302, 0x1303, 0xC02B, 0xC02F, 0xC030]),
    ClassProfile("gaming", "UDP", (55, 100), (150, 80), (240, 130), (0.018, 0.012),
                 download_ratio=0.52, burst=False, tls=False,
                 sni_pool=[], ciphers=[]),
    ClassProfile("music_streaming", "TCP", (22, 65), (170, 110), (780, 360), (0.09, 0.13),
                 download_ratio=0.74, burst=True, tls=True,
                 sni_pool=["audio-fa.scdn.co", "api.spotify.com"],
                 ciphers=[0x1301, 0x1302, 0xC02B, 0xC02F]),
    ClassProfile("vpn", "UDP", (60, 100), (760, 470), (860, 470), (0.014, 0.012),
                 download_ratio=0.58, burst=False, tls=False,
                 sni_pool=[], ciphers=[]),
    ClassProfile("dns_background", "UDP", (4, 14), (75, 30), (150, 70), (0.7, 1.1),
                 download_ratio=0.50, burst=False, tls=False,
                 sni_pool=[], ciphers=[]),
]

PROFILE_BY_LABEL = {p.label: p for p in PROFILES}


def _clamp_size(x: float) -> int:
    return int(min(1500.0, max(40.0, x)))


@dataclass
class SessionStyle:
    """Per-session multiplicative jitter, shared by all flows in a session.

    This adds cross-session variance (different device/network/app-version "style"),
    so test sessions differ systematically from train sessions — the reason a
    session-based split is harder, and more honest, than a flow-random one.
    """

    size_scale: float = 1.0
    iat_scale: float = 1.0
    download_ratio: float = 0.5


def generate_flow(
    profile: ClassProfile,
    rng: np.random.Generator,
    start_ts: float,
    server_ip: str,
    style: SessionStyle | None = None,
) -> FlowRecord:
    """Generate one FlowRecord matching ``profile`` under a session ``style``."""
    style = style or SessionStyle(download_ratio=profile.download_ratio)
    n = int(rng.integers(profile.n_packets[0], profile.n_packets[1] + 1))
    client_port = int(rng.integers(1024, 65535))
    server_port = 443 if profile.protocol == "TCP" else int(rng.choice([443, 53, 3478, 51820]))

    key, _ = FlowKey.normalize(CLIENT_IP, client_port, server_ip, server_port, profile.protocol)
    flow = FlowRecord(key=key, initiator=(CLIENT_IP, client_port), start_ts=start_ts, last_ts=start_ts)

    if profile.tls and profile.sni_pool:
        sni = str(rng.choice(profile.sni_pool))
        # Stack chosen by browser, independent of class -> weak, non-diagnostic signal.
        stack = BROWSER_STACKS[int(rng.integers(0, len(BROWSER_STACKS)))]
        flow.client_hello = build_client_hello(ClientHelloSpec(sni=sni, ciphers=list(stack)))

    t = start_ts
    for i in range(n):
        is_download = rng.random() < style.download_ratio
        direction = BACKWARD if is_download else FORWARD
        mean, std = profile.bwd_size if is_download else profile.fwd_size
        # ~28% of packets are "contamination": generic sizes shared across all classes
        # (embedded content, keepalives, control), blurring the class boundaries.
        if rng.random() < 0.28:
            size = _clamp_size(rng.normal(500, 380))
        else:
            size = _clamp_size(rng.normal(mean, std) * style.size_scale)

        # Advance time; bursty classes occasionally insert a longer idle gap.
        iat_mean, iat_std = profile.iat
        gap = max(0.0, rng.normal(iat_mean, iat_std) * style.iat_scale)
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
            # A session has a consistent "style": device/network/app-version character.
            style = SessionStyle(
                size_scale=float(rng.lognormal(0.0, 0.20)),
                iat_scale=float(rng.lognormal(0.0, 0.28)),
                download_ratio=float(np.clip(rng.normal(profile.download_ratio, 0.07), 0.05, 0.97)),
            )
            n_flows = int(rng.integers(flows_per_session[0], flows_per_session[1] + 1))
            base_ts = float(rng.uniform(1_600_000_000, 1_700_000_000))
            t = base_ts
            for _ in range(n_flows):
                flow = generate_flow(profile, rng, start_ts=t, server_ip=server_ip, style=style)
                out.append((flow, profile.label, session_id))
                t = flow.last_ts + float(rng.uniform(0.5, 5.0))
    return out
