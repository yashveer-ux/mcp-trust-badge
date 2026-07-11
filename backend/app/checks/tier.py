"""Pure scoring/bucket/override logic (§8.3, §10). No I/O, no deps."""
from __future__ import annotations

from app.core.manifest_schema import Flag, Tier

# score >= threshold -> letter. Ordered high to low.
_THRESHOLDS: list[tuple[int, Tier]] = [(95, "S"), (85, "A"), (70, "B"),
                                       (50, "C"), (30, "D"), (0, "F")]

# Labels that cap the tier at "D" no matter the score.
HARD_CAP_LABELS = {"lethal-trifecta", "arbitrary-exec", "secret-solicitation"}

_ORDER: list[Tier] = ["S", "A", "B", "C", "D", "F"]  # best -> worst, "U" is off-scale

# Top of the D band (C starts at 50). When a cap fires we floor the score to here
# so the number matches the capped letter instead of showing e.g. 85 next to a D.
_CAP_SCORE_CEIL = 49


def bucket(score: int) -> Tier:
    score = max(0, min(100, score))
    for thresh, letter in _THRESHOLDS:
        if score >= thresh:
            return letter
    return "F"  # unreachable (0 threshold), keeps type checker happy


def compute_tier(flags: list[Flag], llm_severity_weights: list[int] | None = None,
                 scan_complete: bool = True) -> tuple[int, Tier]:
    if not scan_complete:
        return (0, "U")
    score = 100 - sum(f.weight for f in flags) - sum(llm_severity_weights or [])
    score = max(0, min(100, score))
    tier = bucket(score)
    # Hard cap: pull DOWN to "D" only, never upgrade (F stays F). When the cap
    # actually lowers the tier, also floor the score into the D band so the number
    # and the letter agree (no more "85 / D").
    if any(f.label in HARD_CAP_LABELS for f in flags):
        if _ORDER.index(tier) < _ORDER.index("D"):
            tier = "D"
            score = min(score, _CAP_SCORE_CEIL)
    return (score, tier)


if __name__ == "__main__":
    def _f(label, weight, sev="caution"):
        return Flag(severity=sev, label=label, explanation="", weight=weight)

    assert compute_tier([]) == (100, "S")
    assert compute_tier([_f("secrets", 10), _f("broad-fs", 8)]) == (82, "B")
    assert compute_tier([_f("lethal-trifecta", 5, "hard")]) == (49, "D")  # score floored to D band
    assert compute_tier([_f("arbitrary-exec", 80, "hard")]) == (20, "F")
    assert compute_tier([], scan_complete=False)[1] == "U"
    assert compute_tier([_f("secrets", 5)], [20, 10]) == (65, "C")
    print("tier self-check OK")
