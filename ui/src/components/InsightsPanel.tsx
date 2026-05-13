/** Human-readable presentation of /api/users/:id/insights payloads (+ collapsible raw JSON). */

import { Fragment, type ReactNode } from "react";

export type ScoreAnomalyPayload = {
  user_id?: string;
  z_score?: number | null;
  population_mean?: number | null;
  population_stdev?: number | null;
  score?: number | null;
  tier?: string;
  flag_outlier?: boolean;
  note?: string;
};

export type NoShowRiskPayload = {
  user_id?: string;
  unused_booking_events_seen?: number;
  carpool_events_seen?: number;
  estimated_no_show_risk_0_1?: number;
  model?: string;
};

export type EnsemblePayload = {
  user_id?: string;
  z_score?: number | null;
  z_flag?: boolean;
  no_show_risk?: number;
  burst_unused_bookings?: boolean;
  ensemble_flag?: boolean;
  note?: string;
};

export type InsightsBundle = {
  anomaly: ScoreAnomalyPayload;
  no_show: NoShowRiskPayload;
  ensemble: EnsemblePayload;
};

function fmtNum(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return Number(n).toFixed(digits);
}

function riskBand(r: number): { label: string; pill: "ok" | "warn" | "danger" } {
  if (r < 0.28) return { label: "Low — typical pattern", pill: "ok" };
  if (r < 0.48) return { label: "Moderate — keep an eye on bookings", pill: "warn" };
  if (r < 0.68) return { label: "Elevated — consider outreach or rules review", pill: "danger" };
  return { label: "High — prioritise review alongside other signals", pill: "danger" };
}

function RawDetails({ label, data }: { label: string; data: unknown }) {
  return (
    <details className="insight-raw">
      <summary>{label}</summary>
      <pre tabIndex={0}>{JSON.stringify(data, null, 2)}</pre>
    </details>
  );
}

function Pill({ className, children }: { className?: string; children: ReactNode }) {
  return <span className={`insight-pill ${className || ""}`.trim()}>{children}</span>;
}

function DefinitionList({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="insight-dl">
      {rows.map(([k, v], i) => (
        <Fragment key={`${k}-${i}`}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </Fragment>
      ))}
    </dl>
  );
}

function AnomalyCard({ data }: { data: ScoreAnomalyPayload }) {
  const uid = data.user_id ?? "This driver";
  const z = data.z_score;
  const hasZ = z !== null && z !== undefined && !Number.isNaN(z);

  const direction = hasZ ? (z >= 0 ? "above" : "below") : "";
  const adverb = hasZ ? (Math.abs(z) >= 2 ? "well" : Math.abs(z) >= 1 ? "noticeably" : "slightly") : "";

  const pills: ReactNode[] = [];
  if (data.flag_outlier) pills.push(<Pill className="warn">Possible outlier vs peers — worth a manual glance</Pill>);
  if (data.tier) pills.push(<Pill>Tier: {data.tier}</Pill>);

  const rows: [string, ReactNode][] = [];
  if (data.score !== null && data.score !== undefined) rows.push(["Their score", fmtNum(data.score)]);
  if (data.population_mean !== null && data.population_mean !== undefined)
    rows.push(["Average across pool", fmtNum(data.population_mean)]);
  if (data.population_stdev !== null && data.population_stdev !== undefined)
    rows.push(["Spread (stdev)", fmtNum(data.population_stdev)]);

  return (
    <section className="insight-human-card">
      <h3>Compared with everyone else</h3>
      <p className="insight-lede">
        {data.note && !hasZ ? (
          data.note
        ) : hasZ ? (
          <>
            <strong>{uid}&apos;s behaviour score</strong> sits {adverb} <strong>{direction}</strong> the site average
            — about <strong>{Math.abs(z).toFixed(2)}</strong> standard deviations. That&apos;s a statistical snapshot
            across everyone registered here, not a verdict on character.
          </>
        ) : (
          <>Not enough peers are registered yet to compute a stable comparison.</>
        )}
      </p>
      {pills.length > 0 ? <div className="insight-pill-row">{pills}</div> : null}
      {rows.length > 0 ? <DefinitionList rows={rows} /> : null}
      <RawDetails label="View raw numbers (JSON)" data={data} />
    </section>
  );
}

function NoShowCard({ data }: { data: NoShowRiskPayload }) {
  const risk = typeof data.estimated_no_show_risk_0_1 === "number" ? data.estimated_no_show_risk_0_1 : 0;
  const band = riskBand(risk);
  const pct = Math.round(Math.min(100, Math.max(0, risk * 100)));
  const fillTone =
    band.pill === "ok" ? "var(--insight-meter-ok, #2d6a4f)" : band.pill === "warn" ? "#b8892a" : "#a84848";

  const unused = data.unused_booking_events_seen ?? 0;
  const carpool = data.carpool_events_seen ?? 0;

  return (
    <section className="insight-human-card">
      <h3>No-show &amp; wasted booking risk</h3>
      <p className="insight-lede">
        A simple rolling check on recent events: unused bookings push risk up; carpool signals pull it down a bit.
        Treat this as a <strong>planning hint</strong>, not a prediction that someone will skip a slot.
      </p>
      <div className="insight-meter-wrap">
        <div className="insight-meter-label">
          <span>Estimated risk index</span>
          <span>
            {pct}% · {band.label}
          </span>
        </div>
        <div className="insight-meter-track" role="presentation">
          <div className="insight-meter-fill" style={{ width: `${pct}%`, background: fillTone }} />
        </div>
      </div>
      <DefinitionList
        rows={[
          ["Unused bookings seen (recent window)", String(unused)],
          ["Carpool / rideshare signals", String(carpool)],
          ["Model tag", data.model ?? "heuristic"],
        ]}
      />
      <RawDetails label="View raw payload (JSON)" data={data} />
    </section>
  );
}

function EnsembleCard({ data }: { data: EnsemblePayload }) {
  const flagged = !!data.ensemble_flag;
  const reasons: string[] = [];
  if (data.z_flag) reasons.push("the score looks unusual versus the rest of the population");
  if (data.burst_unused_bookings) reasons.push("several unused bookings appeared in the recent stream");

  let summary: string;
  if (flagged) {
    summary =
      reasons.length > 0
        ? `Together, Newton would flag this profile: ${reasons.join("; ")}.`
        : "Newton would flag this profile based on the combined checks.";
  } else {
    summary =
      "Nothing in these lightweight checks crosses the combined alert line — still apply your normal operational judgement.";
  }

  return (
    <section className="insight-human-card">
      <h3>Combined signal</h3>
      <div className="insight-pill-row">
        {flagged ? <Pill className="danger">Review suggested</Pill> : <Pill className="ok">No ensemble alert</Pill>}
      </div>
      <p className="insight-lede">{summary}</p>
      <DefinitionList
        rows={[
          ["Z-score flag", data.z_flag ? "Yes" : "No"],
          ["Unused-booking burst", data.burst_unused_bookings ? "Yes" : "No"],
          ["Risk index (same heuristic as card above)", fmtNum(data.no_show_risk, 3)],
          ["Z-score (if available)", data.z_score === null || data.z_score === undefined ? "—" : fmtNum(data.z_score, 2)],
        ]}
      />
      {data.note ? <p className="muted small insight-footnote">{data.note}</p> : null}
      <RawDetails label="View raw payload (JSON)" data={data} />
    </section>
  );
}

export function InsightsPanel({ bundle }: { bundle: InsightsBundle }) {
  return (
    <div className="insights-human-grid">
      <AnomalyCard data={bundle.anomaly} />
      <NoShowCard data={bundle.no_show} />
      <EnsembleCard data={bundle.ensemble} />
    </div>
  );
}
