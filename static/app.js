const API = "/api";

const EVENT_TYPES = [
  "booking.created",
  "booking.cancelled",
  "booking.completed",
  "gate.entry_detected",
  "offence.reported",
  "carpool.detected",
  "unused_booking",
  "free_space_used",
  "weekly_decay",
];

const state = {
  users: [],
  groups: [],
  health: null,
  recentEvents: [],
};

let dashChartScores = null;
let dashChartTiers = null;
let dashChartEventTypes = null;

const TIER_CHART_COLORS = {
  Platinum: "rgba(149, 213, 178, 0.88)",
  Gold: "rgba(233, 196, 106, 0.9)",
  Silver: "rgba(154, 163, 181, 0.88)",
  Bronze: "rgba(205, 127, 50, 0.88)",
  Restricted: "rgba(231, 111, 81, 0.85)",
};

function $(sel, root = document) {
  return root.querySelector(sel);
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function fetchJson(url, opts) {
  const res = await fetch(url, opts);
  const text = await res.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!res.ok) {
    let msg = text;
    if (typeof body === "object" && body && body.detail !== undefined) {
      msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    }
    throw new Error(msg || res.statusText);
  }
  return body;
}

function showCallout(el, text, ok) {
  el.hidden = false;
  el.textContent = text;
  el.className = "callout mt " + (ok ? "ok" : "err");
}

function fillEventTypes() {
  const sel = $("#event-type");
  sel.innerHTML = "";
  EVENT_TYPES.forEach((t) => {
    const o = document.createElement("option");
    o.value = t;
    o.textContent = t;
    sel.appendChild(o);
  });
}

async function loadHealth() {
  const pill = document.getElementById("health-pill");
  const badges = document.getElementById("feature-badges");
  try {
    const h = await fetchJson(`${API}/health`);
    state.health = h;
    if (pill) {
      pill.textContent = `${h.status} · ${h.store}`;
      pill.style.background = "#1f3b2d";
    }
    if (badges) {
      badges.innerHTML = "";
      const f = h.features || {};
      const llmLabel = `LLM (${f.llm_backend || "off"})`;
      const entries = [
        ["SQLite / store", h.store === "SqliteStore"],
        ["Groups registry", f.groups_registry],
        ["Score history", f.score_history],
        ["Tenant weights", f.tenant_weights],
        ["Shadow mode", f.shadow_mode],
        [llmLabel, f.llm_explain_env],
      ];
      for (const [label, on] of entries) {
        const span = document.createElement("span");
        span.className = "badge " + (on ? "on" : "off");
        span.textContent = `${label}: ${on ? "yes" : "no"}`;
        badges.appendChild(span);
      }
    }
  } catch {
    if (pill) {
      pill.textContent = "offline";
      pill.style.background = "#4a2323";
    }
    if (badges) badges.innerHTML = "";
  }
}

async function loadGroups() {
  try {
    const data = await fetchJson(`${API}/groups`);
    state.groups = data.groups || [];
  } catch {
    state.groups = [];
  }
  const sg = document.getElementById("stat-groups");
  if (sg) sg.textContent = String(state.groups.length);
  renderGroupSelects();
}

function renderGroupSelects() {
  const ids = ["form-user-group", "tenant-group-select"];
  const prev = {};
  for (const id of ids) {
    const el = document.getElementById(id);
    if (el) prev[id] = el.value;
  }
  const groups = state.groups;
  for (const id of ids) {
    const sel = document.getElementById(id);
    if (!sel) continue;
    sel.innerHTML = "";
    const ph = document.createElement("option");
    ph.value = "";
    ph.textContent = groups.length ? "— Select group —" : "No groups — use New group on Dashboard";
    ph.disabled = !groups.length;
    sel.appendChild(ph);
    for (const g of groups) {
      const o = document.createElement("option");
      o.value = g.group_id;
      o.dataset.priority = String(g.group_priority);
      o.textContent = `${g.group_id} (allocation prio ${g.group_priority})`;
      sel.appendChild(o);
    }
    if (prev[id] && [...sel.options].some((opt) => opt.value === prev[id])) {
      sel.value = prev[id];
    }
  }
  syncUserGroupPriorityFromSelect();
}

function syncUserGroupPriorityFromSelect() {
  const sel = $("#form-user-group");
  const hid = $("#form-user-group-priority");
  const meta = $("#form-user-group-meta");
  if (!sel || !hid || !meta) return;
  const opt = sel.selectedOptions[0];
  if (!opt || !opt.value) {
    hid.value = "100";
    meta.textContent = "";
    return;
  }
  const p = opt.dataset.priority || "100";
  hid.value = p;
  meta.textContent = `Registered group allocation priority: ${p} (included in save request).`;
}

function renderEventUserSelect() {
  const sel = $("#event-user-id");
  if (!sel) return;
  const prev = sel.value;
  sel.innerHTML = "";
  const ph = document.createElement("option");
  ph.value = "";
  ph.textContent = state.users.length ? "— Select user —" : "No users yet";
  ph.disabled = !state.users.length;
  sel.appendChild(ph);
  for (const u of state.users) {
    const o = document.createElement("option");
    o.value = u.user_id;
    o.textContent = `${u.user_id} · ${u.group_id}`;
    sel.appendChild(o);
  }
  if (prev && [...sel.options].some((o) => o.value === prev)) sel.value = prev;
  else if (state.users[0]) sel.value = state.users[0].user_id;
}

async function loadUsers() {
  const data = await fetchJson(`${API}/users`);
  state.users = data.users || [];
  const su = document.getElementById("stat-users");
  if (su) su.textContent = String(state.users.length);
  renderDashUsers();
  renderAllocPicks();
  renderIntelFocus();
  renderEventUserSelect();
  updateDashboardCharts();
}

function renderDashUsers() {
  const tbl = document.getElementById("tbl-users");
  const scoresCb = document.getElementById("dash-users-scores");
  if (!tbl || !scoresCb) return;
  const hideScore = !scoresCb.checked;
  tbl.classList.toggle("hide-score", hideScore);
  const tbody = tbl.querySelector("tbody");
  tbody.innerHTML = "";
  for (const u of state.users) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(u.user_id)}</td>
      <td>${escapeHtml(u.group_id)}</td>
      <td>${u.group_priority} / ${u.user_priority}</td>
      <td class="col-sc">${Number(u.score).toFixed(2)}</td>
      <td class="col-ti"><span class="badge ${tierBadgeClass(u.tier)}">${escapeHtml(u.tier)}</span></td>
      <td>
        <button type="button" class="linkish" data-action="score" data-user="${escapeHtml(u.user_id)}">Score detail</button>
      </td>`;
    tbody.appendChild(tr);
  }
  tbody.querySelectorAll('button[data-action="score"]').forEach((btn) => {
    btn.addEventListener("click", () => openScoreModal(btn.dataset.user));
  });
}

function tierBadgeClass(tier) {
  const t = String(tier).toLowerCase();
  if (t === "platinum") return "on";
  if (t === "restricted") return "off";
  return "";
}

function renderAllocPicks() {
  const box = document.getElementById("alloc-picks");
  if (!box) return;
  box.innerHTML = "";
  for (const u of state.users) {
    const lab = document.createElement("label");
    lab.innerHTML = `<input type="checkbox" value="${escapeHtml(u.user_id)}" checked /> ${escapeHtml(u.user_id)}`;
    box.appendChild(lab);
  }
}

function renderIntelFocus() {
  const sel = document.getElementById("intel-focus");
  if (!sel) return;
  const prev = sel.value;
  sel.innerHTML = "";
  const ph = document.createElement("option");
  ph.value = "";
  ph.textContent = state.users.length ? "Select user…" : "No users — register first";
  sel.appendChild(ph);
  for (const u of state.users) {
    const o = document.createElement("option");
    o.value = u.user_id;
    o.textContent = `${u.user_id} (${u.tier})`;
    sel.appendChild(o);
  }
  if (prev && [...sel.options].some((o) => o.value === prev)) sel.value = prev;
  else if (state.users[0]) sel.value = state.users[0].user_id;
}

function getAllocSelectedIds() {
  const box = document.getElementById("alloc-picks");
  if (!box) return [];
  return [...box.querySelectorAll('input[type="checkbox"]:checked')].map((cb) => cb.value);
}

function poolQueryParam() {
  const sel = getAllocSelectedIds();
  const ids = sel.length ? sel : state.users.map((u) => u.user_id);
  return ids.join(",");
}

async function loadEvents() {
  const limEl = document.getElementById("events-limit");
  const lim = limEl
    ? Math.max(5, Math.min(200, Number(limEl.value) || 40))
    : 40;
  const data = await fetchJson(`${API}/events/recent?limit=${lim}`);
  state.recentEvents = data.events || [];
  const se = document.getElementById("stat-events");
  if (se) se.textContent = String(state.recentEvents.length);
  const tbl = document.getElementById("tbl-events");
  const tbody = tbl ? tbl.querySelector("tbody") : null;
  if (tbody) {
    tbody.innerHTML = "";
    for (const ev of state.recentEvents) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
      <td>${escapeHtml(ev.timestamp || "")}</td>
      <td>${escapeHtml(ev.event_type)}</td>
      <td>${escapeHtml(ev.user_id)}</td>
      <td><code>${escapeHtml(JSON.stringify(ev.payload || {}))}</code></td>`;
      tbody.appendChild(tr);
    }
  }
  updateDashboardCharts();
}

function destroyDashChart(ch) {
  if (ch && typeof ch.destroy === "function") ch.destroy();
  return null;
}

function setChartSection(which, hasChart) {
  const wrap = document.getElementById(`wrap-chart-${which}`);
  const fb = document.getElementById(`fallback-chart-${which}`);
  if (wrap) wrap.hidden = !hasChart;
  if (fb) fb.hidden = hasChart;
}

function updateDashboardCharts() {
  const miss = document.getElementById("charts-lib-missing");
  if (typeof Chart === "undefined") {
    if (miss) miss.hidden = false;
    return;
  }
  if (miss) miss.hidden = true;

  const scoresCanvas = document.getElementById("chart-scores");
  const tiersCanvas = document.getElementById("chart-tiers");
  const eventsCanvas = document.getElementById("chart-event-types");
  if (!scoresCanvas || !tiersCanvas || !eventsCanvas) return;

  dashChartScores = destroyDashChart(dashChartScores);
  dashChartTiers = destroyDashChart(dashChartTiers);
  dashChartEventTypes = destroyDashChart(dashChartEventTypes);

  const usersSorted = [...state.users].sort((a, b) => Number(b.score) - Number(a.score));
  const hasUsers = usersSorted.length > 0;

  setChartSection("scores", hasUsers);
  if (hasUsers) {
    dashChartScores = new Chart(scoresCanvas, {
      type: "bar",
      data: {
        labels: usersSorted.map((u) => u.user_id),
        datasets: [
          {
            label: "Score",
            data: usersSorted.map((u) => Number(u.score)),
            backgroundColor: "rgba(77, 124, 248, 0.5)",
            borderColor: "rgba(119, 156, 250, 0.95)",
            borderWidth: 1,
            borderRadius: 4,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            grid: { color: "rgba(37, 42, 54, 0.95)" },
            ticks: { color: "#9aa3b5" },
            border: { color: "#353d52" },
            title: {
              display: true,
              text: "Behaviour score",
              color: "#9aa3b5",
              font: { size: 11 },
            },
          },
          y: {
            grid: { display: false },
            ticks: { color: "#c7cfdf" },
            border: { display: false },
          },
        },
      },
    });
  }

  setChartSection("tiers", hasUsers);
  if (hasUsers) {
    const tierCounts = {};
    for (const u of state.users) {
      const t = u.tier || "Silver";
      tierCounts[t] = (tierCounts[t] || 0) + 1;
    }
    const tierLabels = Object.keys(tierCounts).sort();
    dashChartTiers = new Chart(tiersCanvas, {
      type: "doughnut",
      data: {
        labels: tierLabels,
        datasets: [
          {
            data: tierLabels.map((l) => tierCounts[l]),
            backgroundColor: tierLabels.map(
              (l) => TIER_CHART_COLORS[l] || "rgba(100, 116, 139, 0.75)",
            ),
            borderColor: "#171b24",
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
            labels: { color: "#c7cfdf", boxWidth: 12, padding: 12 },
          },
        },
      },
    });
  }

  const evCounts = {};
  for (const ev of state.recentEvents || []) {
    const t = ev.event_type || "?";
    evCounts[t] = (evCounts[t] || 0) + 1;
  }
  const evLabels = Object.keys(evCounts).sort((a, b) => evCounts[b] - evCounts[a]);
  const hasEv = evLabels.length > 0;
  setChartSection("events", hasEv);
  if (hasEv) {
    dashChartEventTypes = new Chart(eventsCanvas, {
      type: "bar",
      data: {
        labels: evLabels,
        datasets: [
          {
            label: "Count",
            data: evLabels.map((l) => evCounts[l]),
            backgroundColor: "rgba(61, 168, 126, 0.45)",
            borderColor: "rgba(94, 196, 154, 0.95)",
            borderWidth: 1,
            borderRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: "#9aa3b5", maxRotation: 40, minRotation: 40 },
            border: { color: "#353d52" },
          },
          y: {
            grid: { color: "rgba(37, 42, 54, 0.95)" },
            ticks: { color: "#9aa3b5" },
            border: { color: "#353d52" },
            title: {
              display: true,
              text: "Count",
              color: "#9aa3b5",
              font: { size: 11 },
            },
          },
        },
      },
    });
  }
}

async function reloadAllData() {
  await loadHealth();
  await loadGroups();
  await loadUsers();
  await loadEvents();
}

/** Reload tables/stats only (used after saves and on boot). */
async function refreshAll() {
  const btn = document.getElementById("btn-refresh-global");
  const prevLabel = btn ? btn.textContent : "";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Refreshing…";
  }
  try {
    await reloadAllData();
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = prevLabel || "Reset all data";
    }
  }
}

/** Header control: wipe backend store, then reload (destructive). */
async function resetAllDataAndReload() {
  if (
    !confirm(
      "Delete ALL local data (users, groups, events, scores, tenant config)? This cannot be undone.",
    )
  ) {
    return;
  }
  const btn = document.getElementById("btn-refresh-global");
  const prevLabel = btn ? btn.textContent : "";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Clearing…";
  }
  try {
    await fetchJson(`${API}/admin/reset`, { method: "POST" });
    if (btn) btn.textContent = "Refreshing…";
    await reloadAllData();
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = prevLabel || "Reset all data";
    }
  }
}

/* Tabs */
function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => {
    const on = t.dataset.tab === name;
    t.classList.toggle("active", on);
    t.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll(".panel").forEach((p) => {
    const on = p.dataset.panel === name;
    p.classList.toggle("active", on);
    p.hidden = !on;
  });
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

/* Dashboard */
document.getElementById("dash-users-scores")?.addEventListener("change", renderDashUsers);
document.getElementById("btn-dash-reload-users")?.addEventListener("click", () => refreshAll().catch(errAlert));
document.getElementById("btn-events-reload")?.addEventListener("click", () => loadEvents().catch(errAlert));
document.getElementById("btn-refresh-global")?.addEventListener("click", () =>
  resetAllDataAndReload().catch(errAlert),
);

function setFormBackdropOpen(el, open) {
  if (!el) return;
  if (open) {
    el.hidden = false;
    el.removeAttribute("hidden");
    el.setAttribute("aria-hidden", "false");
  } else {
    el.hidden = true;
    el.setAttribute("hidden", "");
    el.setAttribute("aria-hidden", "true");
  }
}

function closeGroupModal() {
  setFormBackdropOpen(document.getElementById("modal-group-backdrop"), false);
}

function closeUserModal() {
  setFormBackdropOpen(document.getElementById("modal-user-backdrop"), false);
}

function openGroupModal() {
  closeUserModal();
  const bd = document.getElementById("modal-group-backdrop");
  const out = document.getElementById("group-result");
  if (out) out.hidden = true;
  setFormBackdropOpen(bd, true);
  document.querySelector("#form-group [name=group_id]")?.focus();
}

function openUserModal() {
  closeGroupModal();
  const bd = document.getElementById("modal-user-backdrop");
  const out = document.getElementById("user-result");
  if (out) out.hidden = true;
  setFormBackdropOpen(bd, true);
  syncUserGroupPriorityFromSelect();
  document.querySelector("#form-user [name=user_id]")?.focus();
}

document.getElementById("btn-open-modal-group")?.addEventListener("click", () => openGroupModal());
document.getElementById("btn-open-modal-user")?.addEventListener("click", () => openUserModal());

document.getElementById("modal-group-close")?.addEventListener("click", (e) => {
  e.preventDefault();
  closeGroupModal();
});
document.getElementById("modal-user-close")?.addEventListener("click", (e) => {
  e.preventDefault();
  closeUserModal();
});

document.getElementById("modal-group-backdrop")?.addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeGroupModal();
});
document.getElementById("modal-user-backdrop")?.addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeUserModal();
});

$("#btn-submit-group").addEventListener("click", async () => {
  const fd = new FormData($("#form-group"));
  const out = $("#group-result");
  try {
    await fetchJson(`${API}/admin/groups`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        group_id: fd.get("group_id").trim(),
        group_priority: Number(fd.get("group_priority")),
      }),
    });
    showCallout(out, "Group saved to registry.", true);
    $("#form-group").reset();
    $("#form-group [name=group_priority]").value = "1";
    await refreshAll();
  } catch (err) {
    showCallout(out, String(err.message || err), false);
  }
});

$("#form-user-group").addEventListener("change", syncUserGroupPriorityFromSelect);

$("#btn-submit-user").addEventListener("click", async () => {
  const fd = new FormData($("#form-user"));
  const out = $("#user-result");
  const gid = (fd.get("group_id") || "").trim();
  if (!gid) {
    showCallout(out, "Select a group (create one with New group first).", false);
    return;
  }
  syncUserGroupPriorityFromSelect();
  try {
    await fetchJson(`${API}/admin/users`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify([
        {
          user_id: fd.get("user_id").trim(),
          group_id: gid,
          group_priority: Number(fd.get("group_priority")),
          user_priority: Number(fd.get("user_priority")),
        },
      ]),
    });
    showCallout(out, "User saved.", true);
    $("#form-user").reset();
    $("#form-user [name=user_priority]").value = "10";
    $("#form-user-group-priority").value = "100";
    $("#form-user-group-meta").textContent = "";
    await refreshAll();
  } catch (err) {
    showCallout(out, String(err.message || err), false);
  }
});

function errAlert(err) {
  console.error(err);
  alert(String(err.message || err));
}

/* Modal */
function closeModal() {
  const bd = $("#modal-backdrop");
  _scoreModalToken++;
  bd.hidden = true;
  bd.setAttribute("hidden", "");
  bd.setAttribute("aria-hidden", "true");
}

$("#modal-close").addEventListener("click", (e) => {
  e.preventDefault();
  e.stopPropagation();
  closeModal();
});

$("#modal-backdrop").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeModal();
});

document.querySelectorAll(".modal-backdrop .modal").forEach((modalEl) => {
  modalEl.addEventListener("click", (e) => e.stopPropagation());
});

let _scoreModalToken = 0;

async function openScoreModal(userId) {
  const bd = $("#modal-backdrop");
  const body = $("#modal-body");
  const pathEl = $("#modal-rest-path");
  const token = ++_scoreModalToken;
  $("#modal-title").textContent = `Behaviour · ${userId}`;
  pathEl.textContent = `${API}/users/${userId}/behavior-score · /users/${userId}/behavior-score`;
  body.innerHTML = "<p class='muted'>Loading…</p>";
  bd.hidden = false;
  bd.removeAttribute("hidden");
  bd.setAttribute("aria-hidden", "false");
  try {
    const j = await fetchJson(`${API}/users/${encodeURIComponent(userId)}/behavior-score`);
    if (token !== _scoreModalToken || bd.hidden) return;
    body.innerHTML = `
      <dl>
        <dt>Score</dt><dd>${Number(j.score).toFixed(2)}</dd>
        <dt>Tier</dt><dd>${escapeHtml(j.tier)}</dd>
        <dt>Group</dt><dd>${escapeHtml(j.group_id)}</dd>
        <dt>Reward rolling (28d)</dt><dd>${Number(j.reward_total_rolling).toFixed(2)}</dd>
        <dt>Last penalty</dt><dd>${escapeHtml(j.last_penalty_at || "—")}</dd>
        <dt>Updated</dt><dd>${escapeHtml(j.updated_at)}</dd>
      </dl>`;
  } catch (err) {
    if (token !== _scoreModalToken || bd.hidden) return;
    body.innerHTML = `<p class="muted">${escapeHtml(String(err.message || err))}</p>`;
  }
}

/* Events tab */
document.querySelectorAll(".preset-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    $("#event-payload").value = btn.dataset.payload === "{}" ? "" : btn.dataset.payload;
  });
});

$("#btn-submit-event").addEventListener("click", async () => {
  const fd = new FormData($("#form-event"));
  let payload = {};
  const raw = fd.get("payload").trim();
  if (raw) payload = JSON.parse(raw);
  const out = $("#event-result");
  try {
    const res = await fetchJson(`${API}/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_type: fd.get("event_type"),
        user_id: fd.get("user_id").trim(),
        payload,
      }),
    });
    showCallout(out, JSON.stringify(res, null, 2), true);
  } catch (err) {
    showCallout(out, String(err.message || err), false);
  }
  await refreshAll();
});

$("#btn-bulk-sample").addEventListener("click", () => {
  const lines = [
    { event_type: "booking.created", user_id: "alice", payload: {} },
    { event_type: "carpool.detected", user_id: "alice", payload: {} },
    { event_type: "unused_booking", user_id: "bob", payload: {} },
    { event_type: "weekly_decay", user_id: "bob", payload: { weeks: 2 } },
    { event_type: "offence.reported", user_id: "carol", payload: {} },
  ];
  $("#bulk-ndjson").value = lines.map((x) => JSON.stringify(x)).join("\n");
});

$("#btn-bulk-run").addEventListener("click", async () => {
  const raw = $("#bulk-ndjson").value.trim();
  const status = $("#bulk-status");
  const pre = $("#bulk-result");
  if (!raw) {
    status.textContent = "Paste NDJSON first.";
    return;
  }
  let events;
  try {
    events = raw
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .map((line) => JSON.parse(line));
  } catch (e) {
    status.textContent = "Invalid JSON: " + e.message;
    return;
  }
  status.textContent = `Sending ${events.length} events…`;
  try {
    const res = await fetchJson(`${API}/events/bulk`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events }),
    });
    status.textContent = `Done · ${res.count} processed`;
    pre.hidden = false;
    pre.textContent = JSON.stringify(res, null, 2);
    await refreshAll();
  } catch (err) {
    status.textContent = "Error";
    pre.hidden = false;
    pre.textContent = String(err.message || err);
  }
});

/* Allocation */
$("#btn-pick-all").addEventListener("click", () => {
  $("#alloc-picks").querySelectorAll('input[type="checkbox"]').forEach((cb) => {
    cb.checked = true;
  });
});
$("#btn-pick-none").addEventListener("click", () => {
  $("#alloc-picks").querySelectorAll('input[type="checkbox"]').forEach((cb) => {
    cb.checked = false;
  });
});

function allocSeed() {
  const v = Number($("#alloc-seed").value);
  return Number.isFinite(v) ? v : 42;
}

$("#btn-run-rank").addEventListener("click", async () => {
  const ids = poolQueryParam();
  const tbody = $("#tbl-rank tbody");
  tbody.innerHTML = "";
  if (!ids) {
    tbody.innerHTML = `<tr><td colspan="5">No users in pool.</td></tr>`;
    return;
  }
  try {
    const rank = await fetchJson(
      `${API}/allocation/rank?user_ids=${encodeURIComponent(ids)}&seed=${allocSeed()}&include_scores=1`
    );
    for (const r of rank.ranking || []) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${r.rank}</td>
        <td>${escapeHtml(r.user_id)}</td>
        <td>${Number(r.behavior_score).toFixed(2)}</td>
        <td>${escapeHtml(r.tier)}</td>
        <td>${escapeHtml(r.explain)}</td>`;
      tbody.appendChild(tr);
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5">${escapeHtml(String(err.message || err))}</td></tr>`;
  }
});

$("#btn-run-allocate").addEventListener("click", async () => {
  const ids = poolQueryParam();
  const cap = Math.max(1, Number($("#alloc-capacity").value) || 1);
  const box = $("#alloc-winners");
  if (!ids) {
    box.hidden = false;
    showCallout(box, "No users in pool.", false);
    return;
  }
  try {
    const alloc = await fetchJson(
      `${API}/allocation/allocate?user_ids=${encodeURIComponent(ids)}&capacity=${cap}&seed=${allocSeed()}`
    );
    const lines = (alloc.winners || []).map(
      (w) => `#${w.rank} ${w.user_id} · score ${Number(w.behavior_score).toFixed(2)} (${w.tier})`
    );
    box.hidden = false;
    box.className = "callout mt ok";
    box.innerHTML =
      `<strong>${alloc.winners.length} winner(s) / capacity ${cap}</strong><br>` + lines.join("<br>");
  } catch (err) {
    box.hidden = false;
    showCallout(box, String(err.message || err), false);
  }
});

/* Intel */
function intelSeed() {
  const v = Number($("#intel-seed").value);
  return Number.isFinite(v) ? v : 42;
}

function intelFocus() {
  return $("#intel-focus").value.trim();
}

$("#btn-intel-explain").addEventListener("click", async () => {
  const focus = intelFocus();
  const ids = poolQueryParam();
  const box = $("#box-explain");
  if (!focus || !ids) return alert("Pick focus user and ensure pool has users.");
  try {
    const ex = await fetchJson(
      `${API}/allocation/explain?user_ids=${encodeURIComponent(ids)}&focus=${encodeURIComponent(focus)}&seed=${intelSeed()}`
    );
    if (ex.error) return alert(ex.error);
    box.hidden = false;
    $("#intel-narrative").textContent = ex.narrative || "";
    const tbody = $("#tbl-above tbody");
    tbody.innerHTML = "";
    for (const r of ex.users_above || []) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${r.rank}</td><td>${escapeHtml(r.user_id)}</td><td>${escapeHtml(r.explain)}</td>`;
      tbody.appendChild(tr);
    }
  } catch (err) {
    alert(String(err.message || err));
  }
});

$("#btn-intel-shadow").addEventListener("click", async () => {
  const ids = poolQueryParam();
  if (!ids) return alert("No users in pool.");
  let sh;
  try {
    sh = await fetchJson(
      `${API}/allocation/shadow?user_ids=${encodeURIComponent(ids)}&seed=${intelSeed()}`
    );
  } catch (err) {
    return alert(String(err.message || err));
  }
  $("#box-shadow").hidden = false;
  const tn = $("#tbl-newton tbody");
  const tl = $("#tbl-legacy tbody");
  tn.innerHTML = "";
  tl.innerHTML = "";
  for (const r of sh.newton || []) {
    tn.innerHTML += `<tr><td>${r.rank}</td><td>${escapeHtml(r.user_id)}</td></tr>`;
  }
  for (const r of sh.legacy_mock || []) {
    tl.innerHTML += `<tr><td>${r.rank}</td><td>${escapeHtml(r.user_id)}</td></tr>`;
  }
  const tb = $("#tbl-diff tbody");
  tb.innerHTML = "";
  for (const d of sh.diff || []) {
    const delta = d.delta_newton_minus_legacy;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(d.user_id)}</td>
      <td>${d.newton_rank ?? "—"}</td>
      <td>${d.legacy_rank ?? "—"}</td>
      <td>${delta === null || delta === undefined ? "—" : delta}</td>`;
    tb.appendChild(tr);
  }
});

$("#btn-intel-history").addEventListener("click", async () => {
  const focus = intelFocus();
  if (!focus) return alert("Select focus user.");
  let data;
  try {
    data = await fetchJson(`${API}/users/${encodeURIComponent(focus)}/score-history?limit=40`);
  } catch (err) {
    return alert(String(err.message || err));
  }
  $("#box-history").hidden = false;
  const tbody = $("#tbl-history tbody");
  tbody.innerHTML = "";
  const snaps = data.snapshots || [];
  if (data.note && !snaps.length) {
    tbody.innerHTML = `<tr><td colspan="6">${escapeHtml(data.note)}</td></tr>`;
    return;
  }
  for (const s of snaps) {
    tbody.innerHTML += `<tr>
      <td>${escapeHtml(s.created_at || "")}</td>
      <td>${escapeHtml(s.event_type)}</td>
      <td>${Number(s.score).toFixed(2)}</td>
      <td>${escapeHtml(s.tier)}</td>
      <td>${s.applied ? "yes" : "no"}</td>
      <td>${escapeHtml(s.detail)}</td>
    </tr>`;
  }
});

$("#btn-intel-insights").addEventListener("click", async () => {
  const focus = intelFocus();
  if (!focus) return alert("Select focus user.");
  let data;
  try {
    data = await fetchJson(`${API}/users/${encodeURIComponent(focus)}/insights`);
  } catch (err) {
    return alert(String(err.message || err));
  }
  $("#box-insights").hidden = false;
  const root = $("#insights-body");
  root.innerHTML = "";
  const blocks = [
    ["Population anomaly (z-score)", data.anomaly],
    ["No-show risk (heuristic)", data.no_show],
    ["Ensemble flag", data.ensemble],
  ];
  for (const [title, obj] of blocks) {
    const div = document.createElement("div");
    div.className = "insight-card";
    div.innerHTML = `<h4>${escapeHtml(title)}</h4><pre>${escapeHtml(JSON.stringify(obj, null, 2))}</pre>`;
    root.appendChild(div);
  }
});

$("#btn-llm").addEventListener("click", async () => {
  const ids = poolQueryParam();
  if (!ids) return alert("No users.");
  const ctx = $("#llm-context").value.trim();
  const box = $("#llm-out");
  box.hidden = false;
  box.textContent = "…";
  try {
    const res = await fetchJson(`${API}/allocation/explain-llm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_ids: ids, seed: intelSeed(), context: ctx }),
    });
    const text = res.text || JSON.stringify(res, null, 2);
    box.innerHTML =
      `<div class="muted small" style="margin-bottom:0.5rem">mode: ${escapeHtml(res.mode || "?")}</div>` +
      `<div>${escapeHtml(text).replaceAll("\n", "<br>")}</div>`;
    if (res.hint)
      box.innerHTML += `<div class="muted small mt">${escapeHtml(res.hint)}</div>`;
  } catch (err) {
    box.innerHTML = `<div class="callout err">${escapeHtml(String(err.message || err))}</div>`;
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const scoreBd = document.getElementById("modal-backdrop");
  const userBd = document.getElementById("modal-user-backdrop");
  const groupBd = document.getElementById("modal-group-backdrop");
  if (scoreBd && !scoreBd.hidden) closeModal();
  else if (userBd && !userBd.hidden) closeUserModal();
  else if (groupBd && !groupBd.hidden) closeGroupModal();
});

/* Tenant admin */
$("#btn-tenant-load").addEventListener("click", async () => {
  const gid = ($("#tenant-group-select").value || "").trim();
  if (!gid) return alert("Select a group.");
  const out = $("#tenant-result");
  try {
    const r = await fetchJson(`${API}/admin/tenant-config/${encodeURIComponent(gid)}`);
    const w = r.weights || {};
    for (const k of Object.keys(w)) {
      const inp = $("#form-tenant").querySelector(`[name="${k}"]`);
      if (inp) inp.value = w[k];
    }
    showCallout(out, "Loaded weights for " + gid, true);
  } catch (err) {
    showCallout(out, String(err.message || err), false);
  }
});

$("#btn-submit-tenant").addEventListener("click", async () => {
  const fd = new FormData($("#form-tenant"));
  const group_id = fd.get("group_id").trim();
  const weights = {
    no_show: Number(fd.get("no_show")),
    free_space: Number(fd.get("free_space")),
    offence: Number(fd.get("offence")),
    carpool: Number(fd.get("carpool")),
    decay_per_week: Number(fd.get("decay_per_week")),
    reward_cap_total: Number(fd.get("reward_cap_total")),
    reward_cap_window_days: Number(fd.get("reward_cap_window_days")),
  };
  const out = $("#tenant-result");
  try {
    const r = await fetchJson(`${API}/admin/tenant-config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ group_id, weights }),
    });
    showCallout(out, JSON.stringify(r, null, 2), true);
  } catch (err) {
    showCallout(out, String(err.message || err), false);
  }
});

/* Boot */
fillEventTypes();
switchTab("dash");
refreshAll().catch(console.error);
