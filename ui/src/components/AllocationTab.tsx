import { useState } from "react";
import { API, fetchJson } from "../api/client";
import { useData } from "../context/DataContext";
import { AllocationResultFlow, AllocationSetupFlow } from "./AllocationFlowVisual";
import { UserLabel } from "../utils/userDisplay";

type AllocRow = {
  rank: number;
  user_id: string;
  user_name?: string;
  got_parking?: boolean;
  parking_slot?: number | null;
  behavior_score?: number;
  tier?: string;
  summary?: string;
};

type AllocateResponse = {
  allocation_id?: number;
  capacity: number;
  pool_size: number;
  seed?: number | null;
  how_it_works?: string;
  assigned: AllocRow[];
  waiting: AllocRow[];
  waiting_total: number;
};

export function AllocationTab() {
  const { users, allocChecked, setAllocChecked, getPoolUserIds, allocationRuns, loadAllocationRuns, formatUser } =
    useData();
  const [seed, setSeed] = useState(42);
  const [capacity, setCapacity] = useState(2);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [result, setResult] = useState<AllocateResponse | null>(null);
  const [showPoolPicker, setShowPoolPicker] = useState(false);

  const poolIds = getPoolUserIds();
  const poolCount = poolIds.length;

  function toggleAll(on: boolean) {
    setAllocChecked((prev) => {
      const next = { ...prev };
      for (const u of users) next[u.user_id] = on;
      return next;
    });
  }

  async function runAllocation() {
    if (!poolCount) {
      setErr("Import users first (Dashboard → CSV), or select who competes below.");
      setResult(null);
      return;
    }
    const cap = Math.max(1, capacity || 1);
    setBusy(true);
    setErr("");
    setResult(null);
    try {
      const alloc = await fetchJson<AllocateResponse>(
        `${API}/allocation/allocate?user_ids=${encodeURIComponent(poolIds.join(","))}&capacity=${cap}&seed=${seed}&wait_limit=0`,
      );
      setResult(alloc);
      await loadAllocationRuns();
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid-inner">
      <article className="card wide allocation-hero">
        <h2>Who gets parking today?</h2>
        <p className="muted small">
          Each <strong>parking booking</strong> is one physical space. Newton lines everyone up,
          then the first in line get Space #1, #2, and so on.
        </p>
        <AllocationSetupFlow poolCount={poolCount} capacity={capacity} busy={busy} />
      </article>

      <article className="card wide">
        <div className="row-inline wrap">
          <label className="inline stack-tight">
            <span className="muted small">Parking spaces available</span>
            <input
              className="w-short"
              type="number"
              min={1}
              max={99}
              value={capacity}
              onChange={(e) => setCapacity(Number(e.target.value) || 1)}
            />
          </label>
          <label className="inline stack-tight">
            <span className="muted small">Seed (same seed = same order)</span>
            <input
              className="w-short"
              type="number"
              value={seed}
              onChange={(e) => setSeed(Number(e.target.value))}
            />
          </label>
          <button type="button" onClick={() => void runAllocation()} disabled={busy || !poolCount}>
            {busy ? "Assigning…" : "Assign parking spaces"}
          </button>
        </div>

        <p className="muted small mt">
          {poolCount} drivers in pool
          {poolCount !== users.length ? ` (${users.length} total in system)` : ""}.
          <button
            type="button"
            className="linkish ml"
            onClick={() => setShowPoolPicker((v) => !v)}
          >
            {showPoolPicker ? "Hide list" : "Change who competes"}
          </button>
        </p>

        {showPoolPicker ? (
          <div className="pick-grid mt">
            {users.map((u) => (
              <label key={u.user_id}>
                <input
                  type="checkbox"
                  checked={allocChecked[u.user_id] !== false}
                  onChange={(e) =>
                    setAllocChecked((p) => ({ ...p, [u.user_id]: e.target.checked }))
                  }
                />{" "}
                <UserLabel userId={u.user_id} userName={u.user_name} />
              </label>
            ))}
            <div className="row-inline mt">
              <button type="button" className="secondary sm" onClick={() => toggleAll(true)}>
                Everyone
              </button>
              <button type="button" className="secondary sm" onClick={() => toggleAll(false)}>
                Clear
              </button>
            </div>
          </div>
        ) : null}

        {err ? <p className="callout err mt">{err}</p> : null}
      </article>

      {result ? (
        <>
          <article className="card wide">
            <AllocationResultFlow result={result} />
          </article>

          <article className="card wide allocation-outcome assigned">
            <div className="allocation-outcome-header">
              <h2>
                Got parking ({result.assigned.length} of {result.capacity} space
                {result.capacity === 1 ? "" : "s"})
              </h2>
              <span className="allocation-outcome-pointer win">
                Top {result.capacity} in the ranked list → these bookings
              </span>
            </div>
            {result.assigned.length === 0 ? (
              <p className="muted">No spaces assigned — check capacity or pool.</p>
            ) : (
              <ul className="allocation-list">
                {result.assigned.map((w) => (
                  <li key={w.user_id} className="allocation-list-item">
                    <div className="allocation-list-head">
                      <span className="badge on">
                        Space {w.parking_slot ?? w.rank}
                      </span>
                      <strong>
                        <UserLabel userId={w.user_id} userName={w.user_name} />
                      </strong>
                      {w.tier ? <span className="badge">{w.tier}</span> : null}
                      {w.behavior_score != null ? (
                        <span className="muted small">Score {Number(w.behavior_score).toFixed(0)}</span>
                      ) : null}
                    </div>
                    <p className="allocation-summary">{w.summary}</p>
                  </li>
                ))}
              </ul>
            )}
            {result.allocation_id != null ? (
              <p className="muted small mt">Saved as run #{result.allocation_id}</p>
            ) : null}
            {result.waiting_total > 0 ? (
              <p className="muted small mt">
                {result.waiting_total} other driver{result.waiting_total === 1 ? "" : "s"} in the
                pool did not get a space this run (not listed here).
              </p>
            ) : null}
          </article>
        </>
      ) : null}

      {allocationRuns.length > 0 ? (
        <article className="card wide">
          <h2>Previous runs</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Spaces</th>
                  <th>Who got parking</th>
                </tr>
              </thead>
              <tbody>
                {allocationRuns.slice(0, 8).map((r) => (
                  <tr key={r.id}>
                    <td className="small">{r.created_at?.replace("T", " ").slice(0, 19)}</td>
                    <td>{r.capacity}</td>
                    <td>
                      {(r.winners || [])
                        .map(
                          (w) =>
                            `Space ${w.rank}: ${formatUser(w.user_id, w.user_name)}`,
                        )
                        .join(" · ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      ) : null}
    </div>
  );
}
