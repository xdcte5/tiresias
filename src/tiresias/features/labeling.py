"""SNI-based ground-truth labeling.

During data collection the capture agent sees the TLS SNI in the ClientHello (visible
even though the session is encrypted). We map the SNI domain to one of the target
classes to auto-generate labels — then **exclude SNI from the feature set** so it
can't leak the label into the model (see ``features.extract``).

The map is intentionally small and explicit: extend it as you collect more services.
Matching is by domain suffix, longest-suffix-wins.
"""

from __future__ import annotations

# Ordered longest-suffix-wins is achieved by sorting at lookup time; author freely.
SNI_LABEL_RULES: dict[str, str] = {
    # video streaming
    "youtube.com": "video_streaming",
    "googlevideo.com": "video_streaming",
    "ytimg.com": "video_streaming",
    "nflxvideo.net": "video_streaming",
    "netflix.com": "video_streaming",
    "ttvnw.net": "video_streaming",  # twitch video
    "twitch.tv": "video_streaming",
    # video conferencing
    "zoom.us": "video_conferencing",
    "zoom.com": "video_conferencing",
    "meet.google.com": "video_conferencing",
    "teams.microsoft.com": "video_conferencing",
    "teams.live.com": "video_conferencing",
    "webex.com": "video_conferencing",
    # web browsing (generic)
    "wikipedia.org": "web_browsing",
    "github.com": "web_browsing",
    "stackoverflow.com": "web_browsing",
    "reddit.com": "web_browsing",
    "nytimes.com": "web_browsing",
    # file transfer / downloads
    "drive.google.com": "file_transfer",
    "dropbox.com": "file_transfer",
    "dropboxusercontent.com": "file_transfer",
    "backblazeb2.com": "file_transfer",
    "amazonaws.com": "file_transfer",  # S3-style bulk transfer
    # gaming
    "steamserver.net": "gaming",
    "steamcontent.com": "gaming",
    "riotgames.com": "gaming",
    "epicgames.com": "gaming",
    "playstation.net": "gaming",
    # music streaming
    "spotify.com": "music_streaming",
    "scdn.co": "music_streaming",  # spotify CDN
    "pandora.com": "music_streaming",
    "soundcloud.com": "music_streaming",
    # vpn / tunneled
    "nordvpn.com": "vpn",
    "expressvpn.com": "vpn",
    "protonvpn.com": "vpn",
    "wireguard.com": "vpn",
    # dns / background chatter
    "dns.google": "dns_background",
    "cloudflare-dns.com": "dns_background",
    "one.one.one.one": "dns_background",
}

UNKNOWN_LABEL = "unknown"


def label_for_sni(sni: str | None) -> str:
    """Return the class label for an SNI, or ``UNKNOWN_LABEL`` if unmatched/None."""
    if not sni:
        return UNKNOWN_LABEL
    host = sni.lower().strip(".")
    # Longest suffix wins so "meet.google.com" beats a hypothetical "google.com".
    best: tuple[int, str] | None = None
    for suffix, label in SNI_LABEL_RULES.items():
        if host == suffix or host.endswith("." + suffix):
            if best is None or len(suffix) > best[0]:
                best = (len(suffix), label)
    return best[1] if best else UNKNOWN_LABEL
