"""Tiresias — encrypted-traffic application classifier.

Classifies network flows by the application/service that generated them
(video streaming, video conferencing, web, gaming, ...) using only flow-level
metadata — packet sizes, timing, and TLS handshake fields — without inspecting
payloads.

The blind seer Tiresias perceived truth without sight; this classifier infers
application identity without seeing (decrypting) payloads.
"""

__version__ = "0.1.0"

CLASS_NAMES = (
    "video_streaming",
    "video_conferencing",
    "web_browsing",
    "file_transfer",
    "gaming",
    "music_streaming",
    "vpn",
    "dns_background",
)
"""The classification target classes (spec: 6-10 well-separated classes)."""
