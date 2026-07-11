/* MCP Trust — frontend logic. No build step, no deps. */
const API_BASE = "http://localhost:8000"; // change here to point elsewhere

/* ---------- tiny helpers ---------- */
const $ = (sel, root = document) => root.querySelector(sel);
const el = (id) => document.getElementById(id);

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const TIERS = new Set(["S", "A", "B", "C", "D", "E", "F", "U"]);
const tierClass = (t) => "tier-" + (TIERS.has(t) ? t : "U");

/* Hard-override legibility. Each cap label has a ceiling (mirror of backend tier.py);
   the backend floors the score to match, so we just name the flag behind a capped tier. */
const CAP_TIERS = { "lethal-trifecta": "C", "arbitrary-exec": "D", "secret-solicitation": "D" };
const _ORD = { S: 0, A: 1, B: 2, C: 3, D: 4, F: 5, U: 6 };
function capReason(s) {
  const present = (s.flags || []).filter((f) => f.severity === "hard" && CAP_TIERS[f.label]);
  if (!present.length) return null;
  // strictest = lowest ceiling tier
  const strictest = present.reduce((a, f) => (_ORD[CAP_TIERS[f.label]] > _ORD[CAP_TIERS[a.label]] ? f : a));
  if (s.tier !== CAP_TIERS[strictest.label]) return null; // cap didn't set this tier
  return strictest.label;
}

/* fetch wrapper: returns parsed JSON, or throws {code,message} */
async function api(path, opts) {
  let res;
  try {
    res = await fetch(API_BASE + path, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
  } catch (e) {
    throw { code: "unreachable", message: "Backend not running" };
  }
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    const err = data && data.error ? data.error : {};
    throw { code: err.code || res.status, message: err.message || res.statusText || "Request failed" };
  }
  return data;
}

/* ---------- tier chip + score fragments ---------- */
function chip(tier, cls) {
  const t = TIERS.has(tier) ? tier : "U";
  return `<span class="chip ${tierClass(t)} ${cls || ""}">${esc(t)}</span>`;
}

/* ---------- TRUST FACTS label (signature element) ---------- */
function renderFacts(s) {
  const m = s.metadata || {};
  const flags = Array.isArray(s.flags) ? s.flags : [];
  const tools = Array.isArray(s.tools) ? s.tools : [];

  const flagsHTML = flags.length
    ? flags.map((f) => `
        <div class="flag">
          <span class="flag-dot sev-${esc(f.severity)}" aria-hidden="true"></span>
          <span class="flag-body">
            <span class="flag-label">${esc(f.label)}</span>
            <span class="flag-exp">${esc(f.explanation)}</span>
          </span>
        </div>`).join("")
    : `<p class="flag-none">No flags raised.</p>`;

  const toolsHTML = tools.length
    ? tools.map((t) => `
        <div class="tool">
          <div class="tool-name">${esc(t.name)}</div>
          ${t.description ? `<div class="tool-desc">${esc(t.description)}</div>` : ""}
          ${t.risk_note ? `<div class="tool-risk">${esc(t.risk_note)}</div>` : ""}
        </div>`).join("")
    : `<p class="flag-none">No tools reported.</p>`;

  const scoreNum = (typeof s.score === "number") ? s.score : "—";
  const cap = capReason(s);
  const capHTML = cap ? `
    <div class="cap-note" role="note">
      <b>Capped at ${esc(s.tier)} by <code>${esc(cap)}</code>.</b> This capability pattern
      holds the grade at ${esc(s.tier)} no matter how few other flags the server has —
      the score is floored to match.
    </div>` : "";

  return `
  <div class="facts">
    <div class="facts-title">TRUST FACTS</div>
    <div class="rule thick"></div>
    <div class="facts-server"><span class="k">Server</span>${esc(s.server_name || "unknown")}</div>
    <div class="rule med"></div>

    <div class="facts-score">
      ${chip(s.tier, "")}
      <div class="amount">
        <span class="tierword">Trust score</span>
        <span class="num">${esc(scoreNum)}</span><span class="den"> / 100</span>
      </div>
    </div>
    ${capHTML}

    <div class="rule thick"></div>
    <div class="facts-section-h">Flags</div>
    ${flagsHTML}

    <div class="rule med"></div>
    <div class="facts-section-h">Tools</div>
    ${toolsHTML}

    <div class="rule thick"></div>
    <div class="facts-meta">
      <div class="mrow"><span>Tools</span><b>${esc(m.tool_count ?? tools.length)}</b></div>
      <div class="mrow"><span>Auth</span><b>${esc(m.auth_type || "—")}</b></div>
      <div class="mrow"><span>Transport</span><b>${esc(m.transport || "—")}</b></div>
      <div class="mrow"><span>Scanned</span><b>${esc(m.scanned_at || "—")}</b></div>
    </div>
  </div>`;
}

/* ---------- marketplace card (mini label) ---------- */
function renderCard(s) {
  const flags = Array.isArray(s.flags) ? s.flags : [];
  const hard = flags.filter((f) => f.severity === "hard").length;
  const caution = flags.filter((f) => f.severity === "caution").length;
  const toolCount = (s.metadata && s.metadata.tool_count) ?? (s.tools ? s.tools.length : 0);
  const id = s.scan_id || "";
  return `
    <a class="card" role="listitem" href="#/server/${encodeURIComponent(id)}" aria-label="${esc(s.server_name)} — tier ${esc(s.tier)}, score ${esc(s.score)}">
      <div class="card-top">
        <div class="card-name">${esc(s.server_name)}</div>
        ${chip(s.tier, "")}
      </div>
      <div class="card-score">
        <span class="num">${esc(typeof s.score === "number" ? s.score : "—")}</span>
        <span class="den">/ 100</span>
        ${capReason(s) ? `<span class="capped-tag" title="Capped by ${esc(capReason(s))}">▼ capped at ${esc(s.tier)}</span>` : ""}
      </div>
      <div class="card-flags">
        <span><b>${esc(toolCount)}</b> tools</span>
        <span><b>${esc(caution)}</b> caution</span>
        <span><b>${esc(hard)}</b> hard</span>
        <button class="card-del" data-id="${esc(id)}" title="Remove from marketplace" aria-label="Remove ${esc(s.server_name)}">✕</button>
      </div>
    </a>`;
}

/* ---------- marketplace screen ---------- */
async function loadMarketplace() {
  const grid = el("mkt-grid");
  const status = el("mkt-status");
  grid.innerHTML = "";
  status.textContent = "Loading…";
  try {
    const data = await api("/marketplace");
    const servers = (data && data.servers) || [];
    status.textContent = servers.length ? `${servers.length} servers graded` : "";
    if (!servers.length) {
      grid.innerHTML = `<div class="empty"><h2>No servers yet</h2><p>Submit one to see its Trust Facts label.</p></div>`;
      return;
    }
    grid.innerHTML = servers.map(renderCard).join("");
    wireDelete(grid, status);
  } catch (e) {
    status.textContent = "";
    grid.innerHTML = backendDown(e);
  }
}

/* per-card remove: two-step inline confirm (no native dialog) */
function wireDelete(grid, status) {
  grid.querySelectorAll(".card-del").forEach((btn) => {
    btn.addEventListener("click", async (ev) => {
      ev.preventDefault();
      ev.stopPropagation(); // don't navigate into the card's detail link
      if (btn.dataset.armed !== "1") {
        btn.dataset.armed = "1";
        btn.textContent = "remove?";
        btn.classList.add("armed");
        setTimeout(() => {
          if (btn.isConnected) { btn.dataset.armed = "0"; btn.textContent = "✕"; btn.classList.remove("armed"); }
        }, 3000);
        return;
      }
      try { await api("/marketplace/" + encodeURIComponent(btn.dataset.id), { method: "DELETE" }); }
      catch (e) { btn.textContent = "failed"; return; }
      const card = btn.closest(".card");
      if (card) card.remove();
      const n = grid.querySelectorAll(".card").length;
      if (status) status.textContent = n ? `${n} servers graded` : "";
      if (!n) grid.innerHTML = `<div class="empty"><h2>No servers yet</h2><p>Submit one to see its Trust Facts label.</p></div>`;
    });
  });
}

function backendDown(e) {
  if (e && e.code === "unreachable") {
    return `<div class="empty">
      <h2>Backend not running</h2>
      <p>Start it, then reload: <code>uvicorn app.main:app</code></p>
    </div>`;
  }
  return `<div class="err"><h2>Could not load</h2><p>${esc(e.message)}</p><code>${esc(e.code)}</code></div>`;
}

/* ---------- embeddable badge ---------- */
function renderEmbed(s) {
  const id = s.scan_id || "";
  const badge = `${API_BASE}/badge/${encodeURIComponent(id)}.svg`;
  const page = `${location.origin}${location.pathname}#/server/${encodeURIComponent(id)}`;
  const md = `[![MCP Trust](${badge})](${page})`;
  const html = `<a href="${page}"><img src="${badge}" alt="MCP Trust: tier ${s.tier}"></a>`;
  return `
    <section class="embed" aria-label="Embed badge">
      <h3>Embed this badge</h3>
      <p class="embed-hint">Drop it in a README or on your site — it always shows this server's current grade.</p>
      <img class="embed-preview" src="${esc(badge)}" alt="Trust badge preview" width="132" height="20">
      <div class="embed-field">
        <span class="embed-label">Markdown</span>
        <code id="snip-md">${esc(md)}</code>
        <button class="copy" data-copy="snip-md">Copy</button>
      </div>
      <div class="embed-field">
        <span class="embed-label">HTML</span>
        <code id="snip-html">${esc(html)}</code>
        <button class="copy" data-copy="snip-html">Copy</button>
      </div>
    </section>`;
}

function wireCopy(root) {
  root.querySelectorAll("[data-copy]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const text = el(btn.dataset.copy).textContent;
      try { await navigator.clipboard.writeText(text); btn.textContent = "Copied"; }
      catch { btn.textContent = "Copy failed"; }
      setTimeout(() => { btn.textContent = "Copy"; }, 1500);
    });
  });
}

/* ---------- detail screen ---------- */
async function loadDetail(id) {
  const body = el("detail-body");
  body.innerHTML = `<p class="status">Loading…</p>`;
  try {
    const s = await fetchServer(id);
    body.innerHTML = renderFacts(s) + renderEmbed(s) +
      `<div class="detail-actions"><button class="go" id="rescan">Re-scan</button></div>`;
    wireCopy(body);
    $("#rescan").addEventListener("click", async (ev) => {
      ev.target.disabled = true;
      ev.target.textContent = "Re-scanning…";
      await loadDetail(id); // lazy: refetch current grade (seeded servers no-op)
    });
  } catch (e) {
    body.innerHTML = backendDown(e);
  }
}

/* try marketplace record first, fall back to scan record */
async function fetchServer(id) {
  try { return await api("/marketplace/" + encodeURIComponent(id)); }
  catch (e) {
    if (e.code === "unreachable") throw e;
    return await api("/scan/" + encodeURIComponent(id));
  }
}

/* ---------- submit + scan polling ---------- */
const STEPS = [
  { key: "connecting", label: "Connecting" },
  { key: "analyzing", label: "Analyzing" },
  { key: "done", label: "Done" },
];
function statusToStepIndex(status) {
  if (status === "pending") return 0;
  if (status === "scanning") return 1;
  return 2; // done / error
}
function renderProgress(status) {
  const box = el("scan-progress");
  box.hidden = false;
  const idx = statusToStepIndex(status);
  const pct = [8, 55, 100][idx];
  const steps = STEPS.map((st, i) => {
    const cls = i < idx ? "done" : i === idx ? "active" : "";
    return `<span class="step ${cls}">${st.label}</span>` +
      (i < STEPS.length - 1 ? `<span class="step-arrow">→</span>` : "");
  }).join("");
  box.innerHTML = `<div class="steps">${steps}</div><div class="bar"><span style="width:${pct}%"></span></div>`;
}

async function pollScan(id) {
  const result = el("submit-result");
  for (let i = 0; i < 60; i++) {
    let s;
    try { s = await api("/scan/" + encodeURIComponent(id)); }
    catch (e) { el("scan-progress").hidden = true; result.innerHTML = backendDown(e); return; }

    if (s.status === "error") {
      el("scan-progress").hidden = true;
      const err = s.error || {};
      result.innerHTML = `<div class="err"><h2>Scan failed</h2><p>${esc(err.message || "Unknown error")}</p><code>${esc(err.code || "error")}</code></div>`;
      return;
    }
    renderProgress(s.status);
    if (s.status === "done") {
      el("scan-progress").hidden = true;
      result.innerHTML = renderFacts(s) +
        `<div class="detail-actions"><a class="go" href="#/server/${encodeURIComponent(s.scan_id)}">Open permalink</a></div>`;
      return;
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  el("scan-progress").hidden = true;
  result.innerHTML = `<div class="err"><h2>Timed out</h2><p>The scan did not finish. Try again.</p></div>`;
}

function buildPayload(endpoint, form) {
  if (endpoint === "url") return { url: form.url.value.trim() };
  if (endpoint === "repo") return { repo_url: form.repo_url.value.trim() };
  // manifest: parse tools JSON here so we can fail cleanly before POST
  let tools;
  try { tools = JSON.parse(form.tools.value); }
  catch { throw { code: "invalid_json", message: "Tools field is not valid JSON." }; }
  if (!Array.isArray(tools)) throw { code: "invalid_json", message: "Tools must be a JSON array." };
  return { server_name: form.server_name.value.trim(), tools };
}

function wireSubmit() {
  // tab switching
  document.querySelectorAll('[role="tab"]').forEach((tab) => {
    tab.addEventListener("click", () => selectTab(tab.dataset.tab));
    tab.addEventListener("keydown", (e) => {
      const tabs = [...document.querySelectorAll('[role="tab"]')];
      const i = tabs.indexOf(tab);
      if (e.key === "ArrowRight") { e.preventDefault(); tabs[(i + 1) % tabs.length].focus(); selectTab(tabs[(i + 1) % tabs.length].dataset.tab); }
      if (e.key === "ArrowLeft") { e.preventDefault(); tabs[(i - 1 + tabs.length) % tabs.length].focus(); selectTab(tabs[(i - 1 + tabs.length) % tabs.length].dataset.tab); }
    });
  });

  document.querySelectorAll(".panel").forEach((form) => {
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const endpoint = form.dataset.endpoint;
      const btn = $(".go", form);
      const result = el("submit-result");
      result.innerHTML = "";
      let payload;
      try { payload = buildPayload(endpoint, form); }
      catch (e) { result.innerHTML = `<div class="err"><h2>Check your input</h2><p>${esc(e.message)}</p></div>`; return; }

      btn.disabled = true;
      renderProgress("pending");
      try {
        const s = await api("/scan/" + endpoint, { method: "POST", body: JSON.stringify(payload) });
        if (s.status === "done") { // already finished
          el("scan-progress").hidden = true;
          result.innerHTML = renderFacts(s) +
            `<div class="detail-actions"><a class="go" href="#/server/${encodeURIComponent(s.scan_id)}">Open permalink</a></div>`;
        } else {
          await pollScan(s.scan_id);
        }
      } catch (e) {
        el("scan-progress").hidden = true;
        result.innerHTML = backendDown(e);
      } finally {
        btn.disabled = false;
      }
    });
  });
}

function selectTab(name) {
  document.querySelectorAll('[role="tab"]').forEach((t) => {
    const on = t.dataset.tab === name;
    t.setAttribute("aria-selected", on ? "true" : "false");
    t.tabIndex = on ? 0 : -1;
  });
  document.querySelectorAll(".panel").forEach((p) => {
    p.hidden = p.dataset.endpoint !== name;
  });
}

/* ---------- router ---------- */
const SCREENS = ["marketplace", "submit", "detail"];
function show(screen) {
  SCREENS.forEach((s) => { el(s).hidden = s !== screen; });
  document.querySelectorAll("[data-nav]").forEach((a) => {
    a.setAttribute("aria-current", a.dataset.nav === screen ? "page" : "false");
  });
  el("view").focus();
}

function route() {
  const hash = location.hash.replace(/^#\/?/, "");
  if (hash.startsWith("server/")) {
    show("detail");
    loadDetail(decodeURIComponent(hash.slice("server/".length)));
  } else if (hash === "submit") {
    show("submit");
    el("submit-result").innerHTML = "";
    el("scan-progress").hidden = true;
  } else {
    show("marketplace");
    loadMarketplace();
  }
}

/* ---------- health indicator ---------- */
async function checkHealth() {
  try {
    await api("/health");
    el("health").textContent = "backend: online";
  } catch {
    el("health").textContent = "backend: offline";
  }
}

/* ---------- boot ---------- */
window.addEventListener("hashchange", route);
wireSubmit();
route();
checkHealth();
