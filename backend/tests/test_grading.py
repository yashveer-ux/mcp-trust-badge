"""Regression guard: every labeled server in the corpus must grade to its
expected tier. Locks the agreed grading criteria (Stage 1, deterministic)."""
import pytest

from tests.grading_corpus import CORPUS, grade


@pytest.mark.parametrize("name,expected,note,tools", CORPUS, ids=[c[0] for c in CORPUS])
def test_corpus_tier(name, expected, note, tools):
    _score, tier, _flags = grade(tools)
    assert tier == expected, f"{name}: expected {expected}, got {tier} ({note})"


def test_high_impact_flag_fires():
    # the new criterion: destructive/financial verbs raise a high-impact flag
    _n, _e, _note, tools = next(c for c in CORPUS if c[0] == "payments")
    _s, _t, flags = grade(tools)
    assert any(f.label == "high-impact" for f in flags)


@pytest.mark.parametrize("name,desc,expected", [
    ("delete_temp_file", "delete a temporary file", False),
    ("drop_connection", "drop the network connection", False),
    ("clear_cache", "delete cached entries", False),
    ("delete_database", "permanently delete a database", True),
    ("drop_table", "drop a table", True),
    ("charge_card", "charge a saved card token", True),
    ("revoke_access", "revoke a user's access grant", True),
])
def test_high_impact_precision(name, desc, expected):
    """Destructive verbs need a high-value object; financial verbs fire alone."""
    from app.core.manifest_schema import Tool, ToolManifest
    flags, _ = __import__("app.checks.rules", fromlist=["run_rules"]).run_rules(
        ToolManifest(server_name="x", tools=[Tool(name=name, description=desc)]))
    assert any(f.label == "high-impact" for f in flags) is expected


def test_flags_are_deduped():
    """Repeated same-label findings collapse to one flag per label."""
    _n, _e, _note, tools = next(c for c in CORPUS if c[0] == "filesystem")
    _s, _t, flags = grade(tools)
    labels = [f.label for f in flags]
    assert labels.count("broad-fs") == 1
