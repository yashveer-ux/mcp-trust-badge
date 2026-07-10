"""Stage 1 deterministic checks (§8.2). Keyword heuristics, no rule engine.

# ponytail: keyword matching is the known ceiling. Upgrade path: LLM stage
# (llm_analysis.py) for semantics + real JSON-Schema walk instead of str dump.
"""
from __future__ import annotations

from app.core.manifest_schema import Flag, Tool, ToolManifest, ToolNote

# Cap keyword sets (lowercased substring match).
_EXEC = ("exec", "shell", "command", "spawn", "subprocess")
_BROAD_FS = ("path", "cwd", "directory", "filesystem")
_SECRETS = ("token", "apikey", "api_key", "password", "secret", "credential")
_READS_UNTRUSTED = ("fetch", "read", "scrape", "browse", "http get", "email", "file read")
_NET_EGRESS = ("http", "post", "send", "upload", "webhook", "request")
_SENSITIVE = ("secret", "private", "db", "credential", "keychain", "env")


def _blob(t: Tool) -> str:
    """name + description + stringified input schema, lowercased."""
    return f"{t.name} {t.description} {t.input_schema}".lower()


def _hits(blob: str, kws: tuple[str, ...]) -> bool:
    return any(k in blob for k in kws)


def _verb(blob: str) -> str:
    if _hits(blob, _EXEC):
        return "exec"
    if _hits(blob, ("write", "create", "update", "delete", "post", "send", "upload")):
        return "write"
    return "read"


def run_rules(manifest: ToolManifest) -> tuple[list[Flag], list[ToolNote]]:
    flags: list[Flag] = []
    notes: list[ToolNote] = []
    blobs = {t.name: _blob(t) for t in manifest.tools}

    # cross-tool cap presence (lethal trifecta needs the whole toolset).
    reads = [n for n, b in blobs.items() if _hits(b, _READS_UNTRUSTED)]
    egress = [n for n, b in blobs.items() if _hits(b, _NET_EGRESS)]
    sensitive = [n for n, b in blobs.items() if _hits(b, _SENSITIVE)]

    verbs = {"read": 0, "write": 0, "exec": 0}
    for t in manifest.tools:
        b = blobs[t.name]
        contributed: list[str] = []

        if _hits(b, _EXEC):
            flags.append(Flag(severity="hard", label="arbitrary-exec", weight=40,
                              explanation=f"'{t.name}' can execute arbitrary commands"))
            contributed.append("arbitrary-exec")
        elif _hits(b, _BROAD_FS):
            flags.append(Flag(severity="caution", label="broad-fs", weight=8,
                              explanation=f"'{t.name}' takes broad filesystem paths"))
            contributed.append("broad-fs")

        if _hits(b, _SECRETS):
            flags.append(Flag(severity="caution", label="secrets", weight=10,
                              explanation=f"'{t.name}' handles credentials/secrets"))
            contributed.append("secrets")

        verbs[_verb(b)] += 1
        notes.append(ToolNote(name=t.name, description=t.description,
                              risk_note=", ".join(contributed)))

    # lethal trifecta: all three caps present somewhere across the toolset.
    if reads and egress and sensitive:
        flags.append(Flag(
            severity="hard", label="lethal-trifecta", weight=5,
            explanation=(f"reads untrusted ({', '.join(reads)}); "
                         f"network egress ({', '.join(egress)}); "
                         f"sensitive data ({', '.join(sensitive)})")))

    flags.append(Flag(severity="info", label="rwx-ratio", weight=0,
                      explanation=f"{verbs['read']} read / {verbs['write']} write / {verbs['exec']} exec"))
    return flags, notes


if __name__ == "__main__":
    m = ToolManifest(server_name="t", tools=[
        Tool(name="run_shell", description="execute a shell command",
             input_schema={"cmd": "string"}),
        Tool(name="fetch_url", description="fetch a web page via http request",
             input_schema={"url": "string"}),
        Tool(name="read_secret", description="read a private credential from env",
             input_schema={"key": "string"}),
    ])
    flags, notes = run_rules(m)
    labels = {f.label for f in flags}
    assert "arbitrary-exec" in labels
    assert "secrets" in labels
    assert "lethal-trifecta" in labels  # fetch(reads) + fetch(http egress) + secret(sensitive)
    assert any(f.label == "rwx-ratio" for f in flags)
    assert len(notes) == 3
    print("rules self-check OK")
