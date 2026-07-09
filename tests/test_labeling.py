"""SNI -> class label mapping."""

from tiresias.features.labeling import UNKNOWN_LABEL, label_for_sni


def test_direct_and_subdomain_matches():
    assert label_for_sni("www.youtube.com") == "video_streaming"
    assert label_for_sni("r3---sn-abc.googlevideo.com") == "video_streaming"
    assert label_for_sni("us01web.zoom.us") == "video_conferencing"
    assert label_for_sni("audio-fa.scdn.co") == "music_streaming"


def test_case_and_trailing_dot():
    assert label_for_sni("WWW.YouTube.CoM.") == "video_streaming"


def test_unknown_and_none():
    assert label_for_sni(None) == UNKNOWN_LABEL
    assert label_for_sni("") == UNKNOWN_LABEL
    assert label_for_sni("example.invalid") == UNKNOWN_LABEL


def test_longest_suffix_wins():
    # meet.google.com is conferencing even though a shorter google-ish rule could exist.
    assert label_for_sni("meet.google.com") == "video_conferencing"
