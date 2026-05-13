import { useEffect, useMemo, useState } from "react";
import { API, fetchJson } from "../api/client";
import type { FairnessReportResponse, FairnessRow } from "../types";

export function ReportsTab() {
  const [windowDays, setWindowDays] = useState(90);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [report, setReport] = useState<FairnessReportResponse | null>(null);

  async function loadReport() {
    setBusy(true);
    setErr("");
    try {
      const d = await fetchJson<FairnessReportResponse>(
        `${API}/reports/fairness?window_days=${Math.max(1, windowDays)}&format=json`,
      );
      setReport(d);
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
      setReport(null);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void loadReport();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const csvHref = useMemo(
    () => `${API}/reports/fairness?window_days=${Math.max(1, windowDays)}&format=csv`,
    [windowDays],
  );

  return (
    <div className="grid-inner">
      <article className="card wide">
        <h2>Fairness report</h2>
        <p className="muted small">
          Exports user-level fairness indicators similar to your complaint-cohort sheet.
        </p>
        <div className="row-inline mt">
          <label className="inline">
            Window days
            <input
              className="w-short"
              type="number"
              min={1}
              max={366}
              value={windowDays}
              onChange={(e) => setWindowDays(Number(e.target.value))}
            />
          </label>
          <button type="button" onClick={() => void loadReport()} disabled={busy}>
            {busy ? "Loading..." : "Refresh report"}
          </button>
          <a className="button secondary" href={csvHref}>
            Download CSV
          </a>
        </div>
        {err ? <p className="callout err mt">{err}</p> : null}
      </article>

      <article className="card wide">
        <h2>Summary</h2>
        {report ? (
          <div className="badges">
            <span className="badge on">Users: {report.summary.users}</span>
            <span className="badge on">High risk (M/X): {report.summary.high_risk_users}</span>
            <span className="badge on">Avg rejection: {report.summary.avg_rejection_rate_pct}%</span>
          </div>
        ) : (
          <p className="muted">No report loaded.</p>
        )}
      </article>

      <article className="card wide">
        <h2>Rows</h2>
        <div className="table-wrap mt">
          <table>
            <thead>
              <tr>
                <th>User</th>
                <th>Group</th>
                <th>Req</th>
                <th>Bookings</th>
                <th>Rejected</th>
                <th>Unused</th>
                <th>Nudge</th>
                <th>Rej %</th>
                <th>Score</th>
                <th>Tier</th>
              </tr>
            </thead>
            <tbody>
              {(report?.rows || []).map((r: FairnessRow) => (
                <tr key={r.user_id}>
                  <td>{r.user_id}</td>
                  <td>{r.group_name}</td>
                  <td>{r.requests_3mo}</td>
                  <td>{r.bookings_3mo}</td>
                  <td>{r.rejected_3mo}</td>
                  <td>{r.unused_bookings_3mo}</td>
                  <td>{r.nudge_offences_3mo}</td>
                  <td>{r.rejection_rate_pct}</td>
                  <td>{r.score}</td>
                  <td>{r.tier}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>
    </div>
  );
}
