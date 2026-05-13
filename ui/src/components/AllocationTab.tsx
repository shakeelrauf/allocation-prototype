import { useState } from "react";
import { fetchJson } from "../api/client";
import { useData } from "../context/DataContext";

export function AllocationTab() {
  const {
    API,
    health,
    users,
    allocChecked,
    setAllocChecked,
    getPoolUserIds,
    allocationRuns,
    loadAllocationRuns,
  } = useData();
  const [seed, setSeed] = useState(42);
  const [capacity, setCapacity] = useState(2);
  const [rankRows, setRankRows] = useState<
    { rank: number; user_id: string; behavior_score?: number; tier?: string; explain: string }[]
  >([]);
  const [rankErr, setRankErr] = useState("");
  const [allocHtml, setAllocHtml] = useState<{ ok: boolean; html: string } | null>(null);

  const idsParam = () => getPoolUserIds().join(",");

  async function runRank() {
    const ids = idsParam();
    setRankErr("");
    setRankRows([]);
    if (!ids) {
      setRankErr("No users in pool.");
      return;
    }
    try {
      const rank = await fetchJson<{
        ranking: {
          rank: number;
          user_id: string;
          behavior_score?: number;
          tier?: string;
          explain: string;
        }[];
      }>(
        `${API}/allocation/rank?user_ids=${encodeURIComponent(ids)}&seed=${seed}&include_scores=1`,
      );
      setRankRows(rank.ranking || []);
    } catch (e) {
      setRankErr(String(e instanceof Error ? e.message : e));
    }
  }

  async function runAllocate() {
    const ids = idsParam();
    const cap = Math.max(1, capacity || 1);
    if (!ids) {
      setAllocHtml({ ok: false, html: "No users in pool." });
      return;
    }
    try {
      const alloc = await fetchJson<{
        allocation_id?: number;
        winners: {
          rank: number;
          user_id: string;
          behavior_score: number;
          tier: string;
        }[];
      }>(
        `${API}/allocation/allocate?user_ids=${encodeURIComponent(ids)}&capacity=${cap}&seed=${seed}`,
      );
      const lines = (alloc.winners || []).map(
        (w) =>
          `#${w.rank} ${w.user_id} · score ${Number(w.behavior_score).toFixed(2)} (${w.tier})`,
      );
      const saved =
        alloc.allocation_id != null
          ? `<br><span class="muted small">Saved as allocation run #${alloc.allocation_id} · GET /api/allocations · GET /api/allocation/runs/${alloc.allocation_id}</span>`
          : "";
      setAllocHtml({
        ok: true,
        html:
          `<strong>${alloc.winners.length} winner(s) / capacity ${cap}</strong>${saved}<br>` +
          lines.join("<br>"),
      });
      await loadAllocationRuns();
    } catch (e) {
      setAllocHtml({ ok: false, html: String(e instanceof Error ? e.message : e) });
    }
  }

  function toggleAll(on: boolean) {
    setAllocChecked((prev) => {
      const next = { ...prev };
      for (const u of users) next[u.user_id] = on;
      return next;
    });
  }

  return (
    <div className="grid-inner">
        <article className="card wide">
          <h2>Pool &amp; seed</h2>
          {health?.sqlite_path ? (
            <p className="muted small mono">
              SQLite file (survives browser refresh): {health.sqlite_path}
            </p>
          ) : health && health.store !== "SqliteStore" ? (
            <p className="muted small">
              Backend store is <strong>{health.store}</strong> — allocations are not written to a local DB file.
              Run <code className="mono">python run_local.py</code> for SQLite persistence.
            </p>
          ) : null}
          <p className="muted small">
            Choose who competes for spaces. Lower group priority value = higher preferred group.
          </p>
          <div className="pick-grid">
            {users.map((u) => (
              <label key={u.user_id}>
                <input
                  type="checkbox"
                  checked={allocChecked[u.user_id] !== false}
                  onChange={(e) =>
                    setAllocChecked((p) => ({ ...p, [u.user_id]: e.target.checked }))
                  }
                />{" "}
                {u.user_id}
              </label>
            ))}
          </div>
          <div className="row-inline mt">
            <button type="button" className="secondary sm" onClick={() => toggleAll(true)}>
              Select all
            </button>
            <button type="button" className="secondary sm" onClick={() => toggleAll(false)}>
              Clear
            </button>
            <label className="inline">
              Seed
              <input className="w-short" type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} />
            </label>
          </div>
        </article>

        <article className="card">
          <h2>Full ranking</h2>
          <button type="button" onClick={() => void runRank()}>
            Compute ranking
          </button>
          <div className="table-wrap mt">
            <table id="tbl-rank">
              <thead>
                <tr>
                  <th>#</th>
                  <th>User</th>
                  <th>Score</th>
                  <th>Tier</th>
                  <th>Explain</th>
                </tr>
              </thead>
              <tbody>
                {rankErr ? (
                  <tr>
                    <td colSpan={5}>{rankErr}</td>
                  </tr>
                ) : (
                  rankRows.map((r) => (
                    <tr key={r.rank + r.user_id}>
                      <td>{r.rank}</td>
                      <td>{r.user_id}</td>
                      <td>{r.behavior_score != null ? Number(r.behavior_score).toFixed(2) : ""}</td>
                      <td>{r.tier ?? ""}</td>
                      <td>{r.explain}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </article>

        <article className="card">
          <h2>Allocate capacity</h2>
          <label className="stack">
            Spaces available
            <input
              type="number"
              min={1}
              max={99}
              value={capacity}
              onChange={(e) => setCapacity(Number(e.target.value))}
            />
          </label>
          <button type="button" className="mt" onClick={() => void runAllocate()}>
            Run allocation
          </button>
          {allocHtml && (
            <div
              className={`callout mt ${allocHtml.ok ? "ok" : "err"}`}
              dangerouslySetInnerHTML={{ __html: allocHtml.html }}
            />
          )}
        </article>

        <article className="card wide">
          <div className="row-inline" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
            <h2>Saved allocation runs</h2>
            <button type="button" className="secondary sm" onClick={() => void loadAllocationRuns()}>
              Refresh list
            </button>
          </div>
          <p className="muted small">
            Loaded from the API after each page load. Run allocation above to append a new saved row.
          </p>
          <div className="table-wrap mt">
            <table>
              <thead>
                <tr>
                  <th>Run</th>
                  <th>When (UTC)</th>
                  <th>Seed</th>
                  <th>Cap</th>
                  <th>Winners</th>
                </tr>
              </thead>
              <tbody>
                {allocationRuns.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="muted">
                      No saved runs yet — use “Run allocation” or check that the API uses SqliteStore.
                    </td>
                  </tr>
                ) : (
                  allocationRuns.map((r) => (
                    <tr key={r.id}>
                      <td className="mono">#{r.id}</td>
                      <td className="mono small">{r.created_at}</td>
                      <td>{r.seed ?? "—"}</td>
                      <td>{r.capacity}</td>
                      <td>
                        {(r.winners || [])
                          .map((w) => `#${w.rank} ${w.user_id}`)
                          .join(", ") || "—"}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </article>
      </div>
  );
}
