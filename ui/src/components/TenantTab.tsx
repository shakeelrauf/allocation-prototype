import { type FormEvent, useState } from "react";
import { fetchJson } from "../api/client";
import { useData } from "../context/DataContext";

const WEIGHT_KEYS = [
  "no_show",
  "free_space",
  "offence",
  "carpool",
  "decay_per_week",
  "reward_cap_total",
  "reward_cap_window_days",
] as const;

const DEFAULT_WEIGHTS: Record<(typeof WEIGHT_KEYS)[number], number> = {
  no_show: 3,
  free_space: 1,
  offence: 5,
  carpool: 5,
  decay_per_week: 2,
  reward_cap_total: 20,
  reward_cap_window_days: 28,
};

export function TenantTab() {
  const { API, groups } = useData();
  const [groupId, setGroupId] = useState("");
  const [weights, setWeights] = useState(DEFAULT_WEIGHTS);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);

  async function loadCurrent() {
    const gid = groupId.trim();
    if (!gid) {
      window.alert("Select a group.");
      return;
    }
    try {
      const r = await fetchJson<{ weights: Record<string, number> }>(
        `${API}/admin/tenant-config/${encodeURIComponent(gid)}`,
      );
      const w = r.weights || {};
      setWeights((prev) => {
        const next = { ...prev };
        for (const k of WEIGHT_KEYS) {
          if (w[k] !== undefined) next[k] = Number(w[k]);
        }
        return next;
      });
      setMsg({ text: "Loaded weights for " + gid, ok: true });
    } catch (e) {
      setMsg({ text: String(e instanceof Error ? e.message : e), ok: false });
    }
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    const gid = groupId.trim();
    const body = { group_id: gid, weights: { ...weights } };
    try {
      const r = await fetchJson(`${API}/admin/tenant-config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setMsg({ text: JSON.stringify(r, null, 2), ok: true });
    } catch (err) {
      setMsg({ text: String(err instanceof Error ? err.message : err), ok: false });
    }
  }

  return (
    <div className="grid-inner">
        <article className="card wide">
          <h2>Tenant weights (per group_id)</h2>
          <p className="muted small">Overrides default penalties/rewards/decay for users in that group.</p>
          <form className="tenant-form" onSubmit={save}>
            <label>
              Group
              <select required value={groupId} onChange={(e) => setGroupId(e.target.value)}>
                <option value="">— Select —</option>
                {groups.map((g) => (
                  <option key={g.group_id} value={g.group_id}>
                    {g.group_id}
                  </option>
                ))}
              </select>
            </label>
            <div className="weights-grid">
              {WEIGHT_KEYS.map((k) => (
                <label key={k}>
                  {k}
                  <input
                    name={k}
                    type="number"
                    step={k === "reward_cap_window_days" ? 1 : 0.5}
                    value={weights[k]}
                    onChange={(e) =>
                      setWeights((w) => ({ ...w, [k]: Number(e.target.value) }))
                    }
                  />
                </label>
              ))}
            </div>
            <div className="row-inline mt">
              <button type="button" className="secondary" onClick={() => void loadCurrent()}>
                Load current
              </button>
              <button type="submit">Save tenant config</button>
            </div>
          </form>
          {msg && <div className={`callout mt ${msg.ok ? "ok" : "err"}`}>{msg.text}</div>}
        </article>
      </div>
  );
}
