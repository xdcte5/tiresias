"""Sprint 0 smoke tests: package imports and config are sane."""

from tiresias import CLASS_NAMES, __version__
from tiresias.config import CONFIG, Config


def test_version_present():
    assert isinstance(__version__, str)
    assert __version__.count(".") >= 1


def test_class_names_reasonable():
    # Spec: 6-10 well-separated classes, unique.
    assert 6 <= len(CLASS_NAMES) <= 10
    assert len(set(CLASS_NAMES)) == len(CLASS_NAMES)


def test_config_defaults_sane():
    assert CONFIG.flow.packet_cap > CONFIG.flow.min_packets
    assert CONFIG.flow.idle_timeout_s > 0
    assert CONFIG.features.sequence_len > 0
    # Leakage guard defaults ON (SNI excluded from features).
    assert CONFIG.features.allow_sni_features is False


def test_config_describe_roundtrip():
    d = Config().describe()
    assert set(d) == {"flow", "features", "capture", "inference"}
    assert d["flow"]["packet_cap"] == 100
