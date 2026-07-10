"""Shared contract entrypoint: run both stages, score, return the result tuple."""
from __future__ import annotations

import logging

from app.checks.llm_analysis import analyze_semantics
from app.checks.rules import run_rules
from app.checks.tier import compute_tier
from app.core.manifest_schema import Flag, Tier, ToolManifest, ToolNote

log = logging.getLogger(__name__)


def analyze(manifest: ToolManifest,
            scan_complete: bool = True) -> tuple[int, Tier, list[Flag], list[ToolNote]]:
    rule_flags, notes = run_rules(manifest)
    llm_flags = analyze_semantics(manifest)
    all_flags = rule_flags + llm_flags

    # llm flags already carry their weights, so pass them via `flags` (counts weight
    # AND lets llm hard-cap labels trigger); no separate llm weights -> no double count.
    score, tier = compute_tier(all_flags, scan_complete=scan_complete)
    log.info("scan '%s': tier=%s score=%d flags=%s",
             manifest.server_name, tier, score, [f.label for f in all_flags])
    return score, tier, all_flags, notes
