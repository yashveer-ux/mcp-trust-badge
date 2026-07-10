"""Tier logic only: override rule, U state, bucket boundaries. No net/LLM."""
from app.checks.tier import bucket, compute_tier
from app.core.manifest_schema import Flag


def _f(label, weight, sev="caution"):
    return Flag(severity=sev, label=label, explanation="", weight=weight)


def test_clean_manifest_is_S():
    assert compute_tier([]) == (100, "S")


def test_bucket_boundaries():
    assert bucket(95) == "S" and bucket(94) == "A"
    assert bucket(85) == "A" and bucket(84) == "B"
    assert bucket(70) == "B" and bucket(69) == "C"
    assert bucket(50) == "C" and bucket(49) == "D"
    assert bucket(30) == "D" and bucket(29) == "F"
    assert bucket(150) == "S" and bucket(-5) == "F"  # clamped


def test_hard_cap_pulls_down_to_D():
    # score 95 would be S, but the cap label forces D.
    assert compute_tier([_f("lethal-trifecta", 5, "hard")]) == (95, "D")


def test_hard_cap_never_upgrades():
    # already F stays F; cap only pulls down.
    assert compute_tier([_f("arbitrary-exec", 80, "hard")]) == (20, "F")


def test_incomplete_scan_is_U():
    assert compute_tier([_f("secrets", 10)], scan_complete=False) == (0, "U")


def test_llm_weights_subtract():
    assert compute_tier([_f("secrets", 5)], [20, 10]) == (65, "C")
