import { useEffect, useMemo, useState } from "react";
import { API, fetchJson } from "../api/client";
import { RawCsvImport } from "./RawCsvImport";
import { UserLabel } from "../utils/userDisplay";
import type {
  FairnessCohortResponse,
  FairnessCohortRow,
  FairnessReportResponse,
  FairnessRow,
} from "../types";

const PAGE_SIZES = [25, 50, 100, 200] as const;

function paginate<T>(items: T[], page: number, pageSize: number) {
  const total = items.length;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const p = Math.min(Math.max(1, page), pages);
  const start = (p - 1) * pageSize;
  return { slice: items.slice(start, start + pageSize), page: p, pages, total };
}

export function ReportsTab() {
  const [windowDays, setWindowDays] = useState(90);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [report, setReport] = useState<FairnessReportResponse | null>(null);
  const [cohortBusy, setCohortBusy] = useState(false);
  const [cohortErr, setCohortErr] = useState("");
  const [cohort, setCohort] = useState<FairnessCohortResponse | null>(null);
  const [cohortPage, setCohortPage] = useState(1);
  const [cohortPageSize, setCohortPageSize] = useState(50);
  const [reportPage, setReportPage] = useState(1);
  const [reportPageSize, setReportPageSize] = useState(50);

  async function loadReport() {
    setBusy(true);
    setErr("");
    try {
      const d = await fetchJson<FairnessReportResponse>(
        `${API}/reports/fairness?window_days=${Math.max(1, windowDays)}&format=json`,
      );
      setReport(d);
      setReportPage(1);
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
      setReport(null);
    } finally {
      setBusy(false);
    }
  }

  async function loadCohort() {
    setCohortBusy(true);
    setCohortErr("");
    try {
      const d = await fetchJson<FairnessCohortResponse>(
        `${API}/reports/fairness/cohort?seed=1`,
      );
      setCohort(d);
      setCohortPage(1);
    } catch (e) {
      setCohortErr(String(e instanceof Error ? e.message : e));
      setCohort(null);
    } finally {
      setCohortBusy(false);
    }
  }

  async function refreshAfterImport() {
    await loadReport();
    await loadCohort();
  }

  useEffect(() => {
    void loadReport();
    void loadCohort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const csvHref = useMemo(
    () => `${API}/reports/fairness?window_days=${Math.max(1, windowDays)}&format=csv`,
    [windowDays],
  );

  const cohortCsvHref = `${API}/reports/fairness/cohort?seed=1&format=csv`;

  const cohortPageData = useMemo(
    () => paginate(cohort?.rows ?? [], cohortPage, cohortPageSize),
    [cohort?.rows, cohortPage, cohortPageSize],
  );

  const reportPageData = useMemo(
    () => paginate(report?.rows ?? [], reportPage, reportPageSize),
    [report?.rows, reportPage, reportPageSize],
  );

  return (
    <div className="grid-inner">
      <RawCsvImport onImported={refreshAfterImport} />

      <article className="card wide">
        <h2>Fairness report</h2>
        <p className="muted small">
          All imported users (e.g. 904 complaint cohort). Summary is full dataset; table is
          paginated — use CSV for the complete export.
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
            Download fairness CSV
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
        <h2>Legacy vs Newton comparison</h2>
        <p className="muted small">
          After you import a raw CSV above, compare legacy underserved tiers with Newton behaviour
          scores. Use refresh if you have already imported data.
        </p>
        <div className="row-inline mt wrap">
          <button
            type="button"
            className="secondary"
            onClick={() => void loadCohort()}
            disabled={cohortBusy}
          >
            {cohortBusy ? "Loading..." : "Refresh comparison"}
          </button>
          <a className="button secondary" href={cohortCsvHref}>
            Download comparison CSV
          </a>
        </div>
        {cohortErr ? <p className="callout err mt">{cohortErr}</p> : null}
        {cohort?.note ? <p className="callout mt">{cohort.note}</p> : null}
        {cohort && cohort.summary.users > 0 ? (
          <>
            <div className="badges mt">
              <span className="badge on">Cohort users: {cohort.summary.users}</span>
              <span className="badge on">
                Legacy M/X: {cohort.summary.legacy_high_pain_mx ?? 0}
              </span>
              <span className="badge on">
                Newton helps (score ≥80, high pain):{" "}
                {cohort.summary.newton_would_help_count ?? 0}
              </span>
              <span className="badge on">
                Tier label match: {cohort.summary.computed_tier_match_pct ?? 0}%
              </span>
            </div>
            <div className="row-inline mt">
              <label className="inline">
                Per page
                <select
                  value={cohortPageSize}
                  onChange={(e) => {
                    setCohortPageSize(Number(e.target.value));
                    setCohortPage(1);
                  }}
                >
                  {PAGE_SIZES.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
              <span className="muted small">
                Showing {(cohortPage - 1) * cohortPageSize + 1}–
                {Math.min(cohortPage * cohortPageSize, cohortPageData.total)} of{" "}
                {cohortPageData.total}
              </span>
              <button
                type="button"
                className="secondary"
                disabled={cohortPage <= 1}
                onClick={() => setCohortPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </button>
              <button
                type="button"
                className="secondary"
                disabled={cohortPage >= cohortPageData.pages}
                onClick={() => setCohortPage((p) => p + 1)}
              >
                Next
              </button>
            </div>
            <div className="table-wrap mt">
              <table>
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Company</th>
                    <th>Rej %</th>
                    <th>Legacy tier</th>
                    <th>Behaviour</th>
                    <th>Rank in group</th>
                    <th>Helps?</th>
                  </tr>
                </thead>
                <tbody>
                  {cohortPageData.slice.map((r: FairnessCohortRow) => (
                    <tr key={r.user_id}>
                      <td>
                        <UserLabel userId={r.user_id} userName={r.user_name} />
                      </td>
                      <td>{r.company_name}</td>
                      <td>{r.rejection_rate_pct}</td>
                      <td>{r.legacy_underserved_tier}</td>
                      <td>
                        {r.behavior_score} ({r.behavior_tier})
                      </td>
                      <td>
                        {r.newton_rank != null && r.pool_size != null
                          ? `${r.newton_rank} / ${r.pool_size}`
                          : "—"}
                      </td>
                      <td>{r.newton_behavior_helps_eligibility ? "Yes" : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </article>

      <article className="card wide">
        <h2>Fairness rows (all users)</h2>
        {report && report.rows.length > 0 ? (
          <>
            <div className="row-inline mt">
              <label className="inline">
                Per page
                <select
                  value={reportPageSize}
                  onChange={(e) => {
                    setReportPageSize(Number(e.target.value));
                    setReportPage(1);
                  }}
                >
                  {PAGE_SIZES.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
              <span className="muted small">
                Showing {(reportPage - 1) * reportPageSize + 1}–
                {Math.min(reportPage * reportPageSize, reportPageData.total)} of{" "}
                {reportPageData.total}
              </span>
              <button
                type="button"
                className="secondary"
                disabled={reportPage <= 1}
                onClick={() => setReportPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </button>
              <button
                type="button"
                className="secondary"
                disabled={reportPage >= reportPageData.pages}
                onClick={() => setReportPage((p) => p + 1)}
              >
                Next
              </button>
            </div>
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
                  {reportPageData.slice.map((r: FairnessRow) => (
                    <tr key={r.user_id}>
                      <td>
                        <UserLabel userId={r.user_id} userName={r.user_name} />
                      </td>
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
          </>
        ) : (
          <p className="muted mt">Import cohort or register users first.</p>
        )}
      </article>
    </div>
  );
}
