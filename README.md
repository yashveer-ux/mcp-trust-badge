# MCP Trust Badge

**A trust-grading system for [Model Context Protocol](https://modelcontextprotocol.io) servers — a "nutrition label" for the tools you let an AI use.**

Point it at any MCP server and it returns an **S–F letter tier**, a **0–100 trust score**, and a **Trust Facts** panel (FDA-nutrition-label styling) explaining exactly what pulled the grade down.

> **Read-only by construction.** It only ever inspects a server's *declared* capabilities (`initialize` + `tools/list`). There is no code path that executes a scanned server's tools — a trust scanner must never run what it's grading.

---

## Why

MCP lets an AI assistant call external tools. But a tool's manifest can hide real danger: arbitrary shell execution, credential exfiltration, phishing prompts, or the "lethal trifecta" (reads untrusted content **+** touches sensitive data **+** can reach the network). Today you trust a server by vibes. This grades it before you connect.

## What it does

Submit a server three ways:

| Method | Input | How |
|---|---|---|
| **Live URL** | a running server's URL | real Streamable-HTTP handshake, SSRF-guarded |
| **Manifest** | pasted `tools/list` JSON | graded inline |
| **GitHub repo** | a repo URL | reads `server.json`, or README → LLM extraction |

It also **exposes itself as an MCP server**, so an assistant can grade a server before trusting it — `grade_manifest` and `grade_server_url` tools over stdio or HTTP.

## The grading model

`score = 100 − Σ(flag weights)`, then **per-label caps** pull the tier down. Philosophy: **only flag known-bad** — a powerful-but-benign server (fetch, slack, browser) keeps a high grade.

| Flag | Trigger | Caps at |
|---|---|---|
| `arbitrary-exec` | exec / shell / spawn / subprocess | **D** |
| `secret-solicitation` | phishing ("paste your seed phrase") | **D** |
| `lethal-trifecta` | untrusted-read **+** net-egress **+** sensitive-data | **C** |
| `high-impact` | financial verb, or destructive verb + high-value object | — |
| `broad-fs` / `scoped-fs` | arbitrary vs repo-bounded filesystem paths | — |
| `credential-exposure` | returns a specific secret to the caller | — |

Tiers: **S** 95–100 · **A** 85–94 · **B** 70–84 · **C** 50–69 · **D** 30–49 · **F** 0–29 · **U** = incomplete scan. Full rationale in [`docs/TUNING-GRADING.md`](docs/TUNING-GRADING.md).

## Security posture

Grading untrusted input is itself an attack surface. This project treats it like one:

- **SSRF guard** — every fetched URL is resolved and blocked if it hits private / loopback / link-local / reserved / cloud-metadata addresses; redirects disabled.
- **Read-only MCP client** — no `tools/call` method exists.
- **Bounded** — byte caps + hard timeouts on every fetch; capped manifest size; capped concurrent scans.
- **No injection** — parameterized SQL, output-escaped frontend (no XSS), no committed secrets.

## Run it

```bash
# One-time setup (Python 3.9+)
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# API on :8000 (seeds the marketplace on startup)
.venv/bin/uvicorn app.main:app

# UI: in another shell, then open http://localhost:5500
cd frontend && python3 -m http.server 5500

# The grader as an MCP server (stdio), from backend/
.venv/bin/python -m app.mcp_server
# ...or over HTTP once the API is up: POST http://localhost:8000/mcp

# Tests, from backend/
.venv/bin/python -m pytest tests/ -q   # 37 passing
```

The MCP handshake is hand-rolled raw JSON-RPC (no SDK dependency). Client setup (Claude Desktop) is in [`docs/MCP-SERVER.md`](docs/MCP-SERVER.md).

### Configuration

Optional. Set as env vars or in a gitignored `backend/.env` (`KEY=VALUE` lines; real env vars win).

| Variable | Default | Effect |
|---|---|---|
| `ANTHROPIC_API_KEY` | unset | enables Stage-2 Claude analysis and README → manifest extraction; without it those steps are stubbed |
| `ANTHROPIC_MODEL` | `claude-sonnet-5` | model for Stage-2 analysis |
| `TRUST_DB_PATH` | `backend/scans.db` | where scans are stored |

The frontend talks to `http://localhost:8000`; change `API_BASE` at the top of `frontend/app.js` to point elsewhere.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/scan/manifest` | grade pasted `tools/list` JSON |
| `POST` | `/scan/url` | grade a live server URL |
| `POST` | `/scan/repo` | grade a GitHub repo |
| `GET` | `/scan/{scan_id}` | fetch a scan result |
| `GET` | `/marketplace` | list graded servers |
| `GET` / `DELETE` | `/marketplace/{server_id}` | get / remove one server |
| `GET` | `/badge/{server_id}.svg` | embeddable badge |
| `GET` / `POST` | `/mcp` | MCP Streamable-HTTP endpoint (POST is the protocol; GET returns info) |
| `GET` | `/health` | liveness |

## Repo layout

```
backend/app/
  api/         FastAPI routes (scan, marketplace, badge, mcp)
  checks/      grading: rules.py, tier.py, llm_analysis.py, pipeline.py
  core/        manifest schema, read-only MCP client, SSRF guard, SQLite store
  ingestion/   live URL, GitHub repo, registry seed, known servers
  mcp_server.py  the grader exposed as an MCP server
backend/tests/ grading corpus + tier tests
frontend/      vanilla JS UI (index.html, app.js, styles.css)
docs/          MCP-SERVER.md, TUNING-GRADING.md
MCP-Trust-Badge-Technical-Report.docx
```

## Try these live servers

| URL | Grade |
|---|---|
| `https://mcp.deepwiki.com/mcp` | S |
| `https://docs.mcp.cloudflare.com/mcp` | S |
| `https://huggingface.co/mcp` | B |
| `https://mcp.context7.com/mcp` | B |

## Stack

FastAPI · vanilla-JS frontend (no build) · stdlib `sqlite3` · `httpx` · optional Claude for Stage-2 semantic analysis (graceful stub without a key).

## Embed a badge

Every graded server gets a shields-style SVG:

```markdown
[![MCP Trust](http://localhost:8000/badge/<server_id>.svg)](http://localhost:8000)
```
