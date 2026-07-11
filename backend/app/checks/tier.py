"""Pure scoring/bucket/override logic (§8.3, §10). No I/O, no deps."""
from __future__ import annotations

from app.core.manifest_schema import Flag, Tier

# score >= threshold -> letter. Ordered high to low.
_THRESHOLDS: list[tuple[int, Tier]] = [(95, "S"), (85, "A"), (70, "B"),
                                       (50, "C"), (30, "D"), (0, "F")]

# Labels that cap the tier, each to its own ceiling. lethal-trifecta is a *potential*
# exfil pattern (caution) so it caps at C; unsandboxed exec and phishing are more
# directly dangerous so they cap at D.
CAP_TIERS = {"lethal-trifecta": "C", "arbitrary-exec": "D", "secret-solicitation": "D"}
HARD_CAP_LABELS = set(CAP_TIERS)  # kept for callers that just need the label set

_ORDER: list[Tier] = ["S", "A", "B", "C", "D", "F"]  # best -> worst, "U" is off-scale

# Top of each cap tier's band (score that still buckets to it), so the number matches
# the capped letter instead of showing e.g. 85 next to a C.
_CAP_SCORE_CEIL = {"C": 69, "D": 49}


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
    # Hard caps pull DOWN to each label's ceiling (never upgrade). With several cap
    # labels the strictest (lowest) ceiling wins. When a cap lowers the tier, floor
    # the score into that band so the number and letter agree (no more "85 / D").
    ceilings = [CAP_TIERS[f.label] for f in flags if f.label in CAP_TIERS]
    if ceilings:
        strictest = max(ceilings, key=_ORDER.index)  # lowest tier = highest order index
        if _ORDER.index(tier) < _ORDER.index(strictest):
            tier = strictest
            score = min(score, _CAP_SCORE_CEIL[strictest])
    return (score, tier)


if __name__ == "__main__":
    def _f(label, weight, sev="caution"):
        return Flag(severity=sev, label=label, explanation="", weight=weight)

    assert compute_tier([]) == (100, "S")
    assert compute_tier([_f("secrets", 10), _f("broad-fs", 8)]) == (82, "B")
    assert compute_tier([_f("lethal-trifecta", 5, "hard")]) == (69, "C")  # trifecta caps at C
    assert compute_tier([_f("arbitrary-exec", 5, "hard")]) == (49, "D")  # exec caps at D
    assert compute_tier([_f("arbitrary-exec", 80, "hard")]) == (20, "F")
    assert compute_tier([], scan_complete=False)[1] == "U"
    assert compute_tier([_f("secrets", 5)], [20, 10]) == (65, "C")
    print("tier self-check OK")
