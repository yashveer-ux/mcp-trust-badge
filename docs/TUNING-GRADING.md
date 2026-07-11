# Tuning the Grading Engine — A How-To Guide

This is the guide to changing how MCP Trust Badge grades servers, by yourself.
Everything here is deterministic Stage-1 logic (no API key needed), which is where
the grading *criteria* live.

---

## 1. The mental model

Grading is three steps. Learn these and everything else follows.

```
1. run_rules(manifest)  ->  a list of Flag objects, each with a `weight`
2. score = 100 - (sum of all flag weights)         # clamped to 0..100
3. tier  = the letter bucket the score falls into  # S/A/B/C/D/F
   ...unless a "hard-cap" flag is present -> tier pulled down to at most D
   ...unless the scan didn't complete   -> tier = U ("no data")
```

So there are only **three levers**:

| Lever | What it controls | Where |
|---|---|---|
| **Flags & weights** | what counts as risky, and how many points it costs | `app/checks/rules.py` |
| **Tier thresholds** | which score becomes which letter | `app/checks/tier.py` |
| **Hard-cap labels** | which flags cap the tier regardless of score | `app/checks/tier.py` |

A higher weight = a bigger deduction = a worse grade.

---

## 2. The two files you edit

### `app/checks/rules.py` — the checks

At the top are **keyword sets** (lowercased substrings) and **constants**:

```python
_EXEC      = ("exec", "shell", "command", "spawn", "subprocess")
_BROAD_FS  = ("path", "cwd", "directory", "filesystem")
_SECRETS   = ("token", "apikey", "api key", "password", "secret", "credential")
BROAD_FS_CAP = 32   # max total broad-fs deduction, however many file tools
```

`run_rules()` builds a lowercased "blob" per tool (`name + description + input schema`,
with underscores turned into spaces) and checks each blob against those sets. Matches
become `Flag(severity, label, weight, explanation)`.

Two shapes of check:
- **Per-tool** (exec, broad-fs, secrets): checked on each tool, then emitted as **one
  aggregated flag per label** whose weight scales with how many tools matched.
- **Cross-tool** (lethal-trifecta, high-impact): reasons over the whole tool list at once.

### `app/checks/tier.py` — the scoring

```python
_THRESHOLDS   = [(95,"S"), (85,"A"), (70,"B"), (50,"C"), (30,"D"), (0,"F")]
HARD_CAP_LABELS = {"lethal-trifecta", "arbitrary-exec"}
```

`compute_tier(flags)` sums the weights, buckets the score, then applies the cap.

---

## 3. Recipes

### 3a. Change how much a check costs (a weight)

Say `secrets` feels too harsh. Find it in `run_rules`:

```python
if secret_tools:
    flags.append(Flag(severity="caution", label="secrets", weight=10 * len(secret_tools), ...))
```

Change `10` to `6`. Done. Re-run the corpus (section 4) to see the effect.

### 3b. Add a keyword to an existing check

A server exposes a `run_query_unsafe` tool you want caught as exec. Add the keyword:

```python
_EXEC = ("exec", "shell", "command", "spawn", "subprocess", "unsafe")
```

Keywords are **substring** matches on the blob. Underscores in tool names are
already turned into spaces, so `"api key"` matches a tool named `api_key`.

### 3c. Cap or plateau a stacking penalty

This is what we did for `broad-fs`. A per-tool weight that stacks linearly tanks
servers with many similar tools. Cap the aggregate:

```python
BROAD_FS_CAP = 32                       # constant at top of file
...
fs_weight = min(8 * len(fs_tools), BROAD_FS_CAP)
flags.append(Flag(..., weight=fs_weight, ...))
```

Now 3 file tools cost 24 (B), but 8 file tools plateau at 32 (C) instead of 64 (D).
Want a filesystem server to land B instead of C? Lower the cap to 24.

### 3d. Add a whole new check

Example: flag servers that can send outbound email (spam/exfil surface).

```python
# 1. add a keyword set near the others
_EMAIL_SEND = ("send email", "send mail", "smtp")

# 2. inside run_rules, after the existing cross-tool checks:
email_tools = [n for n, b in blobs.items() if _hits(b, _EMAIL_SEND)]
if email_tools:
    flags.append(Flag(severity="caution", label="email-egress", weight=12,
                      explanation=f"can send outbound email ({', '.join(email_tools)})"))
```

That's it — the new flag flows through scoring automatically because scoring only
reads `flag.weight`. If you want it to also render nicely on the label, the frontend
already shows any flag with a severity dot.

### 3e. Change the tier boundaries

Think a 70 should be a C, not a B? Edit the thresholds in `tier.py`:

```python
_THRESHOLDS = [(95,"S"), (88,"A"), (75,"B"), (55,"C"), (30,"D"), (0,"F")]
```

Order matters: highest threshold first. Keep them descending.

### 3f. Change what caps the tier (the override)

Right now `lethal-trifecta` and `arbitrary-exec` cap a server at D no matter its score.
To make, say, `high-impact` also a cap:

```python
HARD_CAP_LABELS = {"lethal-trifecta", "arbitrary-exec", "high-impact"}
```

To make arbitrary exec cap at **F** instead of D, you'd change the cap logic in
`compute_tier` — currently it pulls down to `"D"`; a second, stricter set could pull
certain labels to `"F"`.

---

## 4. The tuning loop (do this every time)

There is a **labeled corpus** of 17 realistic servers with the tier each *should* get.
After any change, run it — it prints exactly what moved:

```bash
cd backend
.venv/bin/python -m tests.grading_corpus
```

You get a table (expected vs got vs score vs flags) and an accuracy line. If a server
now grades wrong, you decide: was the **rule** wrong, or was my **expectation** wrong?

- Rule wrong  -> adjust the weight/keyword/threshold.
- Expectation wrong (you changed the policy on purpose) -> update the `expected` tier
  in `tests/grading_corpus.py` so it reflects the new policy.

Then run the guard suite (this is what fails CI if grading drifts):

```bash
.venv/bin/python -m pytest tests/ -q
```

### Locking a new decision

When you're happy with a change, **add a corpus entry** so it can't silently regress.
In `tests/grading_corpus.py`, append to `CORPUS`:

```python
("my-server", "C", "why this tier", [
    T("some_tool", "what it does", param="string")]),
```

`tests/test_grading.py` automatically tests every corpus entry — no extra wiring.

---

## 5. Quick reference — the current criteria

| Flag | Trigger | Weight | Caps tier? |
|---|---|---|---|
| `arbitrary-exec` | exec/shell/command/subprocess in a tool | 40 × tools | yes → D |
| `lethal-trifecta` | reads-untrusted + net-egress + sensitive across the toolset | 5 | yes → D |
| `high-impact` | financial verb, or destructive verb + high-value object | 30 | no |
| `broad-fs` | path/cwd/directory params | 8 × tools, capped 32 | no |
| `secrets` | token/apikey/password/secret/credential | 10 × tools | no |
| `rwx-ratio` | (informational read/write/exec counts) | 0 | no |

Tiers: S 95–100 · A 85–94 · B 70–84 · C 50–69 · D 30–49 · F 0–29 · U = incomplete scan.

Philosophy (agreed): **only flag known-bad.** A powerful-but-benign server (fetch,
slack, browser) keeps a high grade; the grade drops only for the flags above.

---

## 6. Where NOT to tune here

Stage 2 (`app/checks/llm_analysis.py`) is the *semantic* pass — it catches coercive or
injection-style language a keyword can't. It needs `ANTHROPIC_API_KEY` and is
non-deterministic, so it isn't part of this corpus. Tune its **system prompt** (the
few-shot examples) if the LLM over/under-flags, and its `_WEIGHTS` map for how much its
findings cost. Same three-lever model applies.
