import { useState } from "react";
import { useData } from "../context/DataContext";
import { UserLabel } from "../utils/userDisplay";
import { DashboardCharts } from "./DashboardCharts";
import { RawCsvImport } from "./RawCsvImport";

function tierBadgeClass(tier: string) {
  const t = tier.toLowerCase();
  if (t === "platinum") return "on";
  if (t === "restricted") return "off";
  return "";
}

type DashProps = {
  onOpenGroup: () => void;
  onOpenUser: () => void;
  onScoreUser: (id: string) => void;
};

export function Dashboard({ onOpenGroup, onOpenUser, onScoreUser }: DashProps) {
  const { groups, users, recentEvents, eventsLimit, setEventsLimit, reloadAll, loadEvents } = useData();
  const [showScores, setShowScores] = useState(true);

  return (
    <div className="grid-inner">
        <RawCsvImport onImported={() => reloadAll()} />

        <article className="card">
          <h2>Groups &amp; users</h2>
          <p className="muted small">
            Add a <strong>group</strong> first (team / parking pool), then register <strong>users</strong>.
            Lower group priority ranks earlier in allocation.
          </p>
          <div className="row-inline mt">
            <button type="button" onClick={onOpenGroup}>
              New group
            </button>
            <button type="button" className="secondary" onClick={onOpenUser}>
              New user
            </button>
          </div>
        </article>

        <article className="card">
          <h2>Quick stats</h2>
          <dl className="stats" id="dash-stats">
            <div>
              <dt>Groups</dt>
              <dd>{groups.length}</dd>
            </div>
            <div>
              <dt>Users</dt>
              <dd>
                {users.length}
                {users.length > 100 ? (
                  <span className="muted small" title="Full list in table below">
                    {" "}
                    (all loaded)
                  </span>
                ) : null}
              </dd>
            </div>
            <div>
              <dt>Events (loaded)</dt>
              <dd>{recentEvents.length}</dd>
            </div>
          </dl>
          <p className="muted small">Use tabs above for streams, ranking, shadow mode, and tenant weights.</p>
        </article>

        <DashboardCharts />

        <article className="card wide">
          <div className="row">
            <h2>Users</h2>
            <div className="row-inline">
              <label className="inline">
                <span className="muted">Show score</span>
                <input type="checkbox" checked={showScores} onChange={(e) => setShowScores(e.target.checked)} />
              </label>
              <button type="button" className="secondary sm" onClick={() => reloadAll().catch(alertErr)}>
                Reload table
              </button>
            </div>
          </div>
          <div className="table-wrap">
            <table className={showScores ? "" : "hide-score"} id="tbl-users">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Group</th>
                  <th>G/U prio</th>
                  <th className="col-sc">Score</th>
                  <th className="col-ti">Tier</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.user_id}>
                    <td>
                      <UserLabel userId={u.user_id} userName={u.user_name} />
                    </td>
                    <td>{u.group_id}</td>
                    <td>
                      {u.group_priority} / {u.user_priority}
                    </td>
                    <td className="col-sc">{Number(u.score).toFixed(2)}</td>
                    <td className="col-ti">
                      <span className={`badge ${tierBadgeClass(u.tier)}`}>{u.tier}</span>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="linkish"
                        onClick={() => onScoreUser(u.user_id)}
                      >
                        Score detail
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className="card wide">
          <div className="row">
            <h2>Recent events</h2>
            <div className="row-inline">
              <label className="inline">
                Limit
                <input
                  type="number"
                  className="w-short"
                  value={eventsLimit}
                  min={5}
                  max={200}
                  onChange={(e) => setEventsLimit(Number(e.target.value) || 40)}
                />
              </label>
              <button type="button" className="secondary sm" onClick={() => loadEvents().catch(alertErr)}>
                Reload
              </button>
            </div>
          </div>
          <div className="table-wrap">
            <table id="tbl-events">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Type</th>
                  <th>User</th>
                  <th>Payload</th>
                </tr>
              </thead>
              <tbody>
                {recentEvents.map((ev, i) => (
                  <tr key={`${ev.timestamp}-${i}`}>
                    <td>{ev.timestamp || ""}</td>
                    <td>{ev.event_type}</td>
                    <td>
                      <UserLabel userId={ev.user_id} userName={ev.user_name} />
                    </td>
                    <td>
                      <code>{JSON.stringify(ev.payload || {})}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </div>
  );
}

function alertErr(e: unknown) {
  window.alert(String(e instanceof Error ? e.message : e));
}
