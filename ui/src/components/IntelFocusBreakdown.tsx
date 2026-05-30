import { UserLabel } from "../utils/userDisplay";

export type CalcStep = {
  step: number;
  title: string;
  value: string;
  detail: string;
};

export type SortKeyParts = {
  group_priority: number;
  user_priority: number;
  neg_behavior_score: number;
  tie_breaker: number;
};

export type FocusDetail = {
  user_id: string;
  user_name?: string;
  rank: number;
  pool_size: number;
  seed?: number | null;
  group_id: string;
  group_priority: number;
  user_priority: number;
  behavior_score: number;
  tier: string;
  tie_breaker: number;
  sort_key: SortKeyParts;
  restricted_deferred?: boolean;
  eligible_count?: number;
  sort_formula?: string;
  calculation_steps: CalcStep[];
};

export function IntelFocusBreakdown({ detail }: { detail: FocusDetail }) {
  const sk = detail.sort_key;

  return (
    <div className="intel-focus-breakdown" aria-label="Full rank calculation for focus user">
      <div className="intel-focus-breakdown-head">
        <h3 className="subh">Full explanation — your numbers &amp; rank math</h3>
        <p className="muted small">
          Selected:{" "}
          <strong>
            <UserLabel userId={detail.user_id} userName={detail.user_name} />
          </strong>{" "}
          · Rank <strong>#{detail.rank}</strong> of {detail.pool_size}
          {detail.seed != null ? ` · seed ${detail.seed}` : ""}
        </p>
      </div>

      <div className="intel-metric-grid">
        <div className="intel-metric-card">
          <span className="intel-metric-label">Team priority</span>
          <span className="intel-metric-value">{detail.group_priority}</span>
          <span className="intel-metric-hint">Group «{detail.group_id}» — lower wins</span>
        </div>
        <div className="intel-metric-card">
          <span className="intel-metric-label">Individual priority</span>
          <span className="intel-metric-value">{detail.user_priority}</span>
          <span className="intel-metric-hint">Lower wins within team</span>
        </div>
        <div className="intel-metric-card highlight">
          <span className="intel-metric-label">Behaviour score</span>
          <span className="intel-metric-value">{Number(detail.behavior_score).toFixed(2)}</span>
          <span className="intel-metric-hint">Tier: {detail.tier}</span>
        </div>
        <div className="intel-metric-card">
          <span className="intel-metric-label">Tie-breaker</span>
          <span className="intel-metric-value">{detail.tie_breaker.toFixed(6)}</span>
          <span className="intel-metric-hint">Lower wins on exact ties</span>
        </div>
      </div>

      <div className="intel-sort-key-box">
        <span className="intel-narrative-label">Sort key used in ranking (smaller = earlier)</span>
        <code className="intel-sort-key-code">
          ({sk.group_priority}, {sk.user_priority}, {sk.neg_behavior_score.toFixed(2)},{" "}
          {sk.tie_breaker.toFixed(6)})
        </code>
        <p className="muted small intel-sort-key-legend">
          = (team priority, individual priority, <strong>minus</strong> behaviour score, tie-breaker)
        </p>
        {detail.sort_formula ? <p className="muted small">{detail.sort_formula}</p> : null}
        {detail.restricted_deferred ? (
          <p className="callout warn small mt">
            Restricted tier: ranked after all {detail.eligible_count ?? "other eligible"} drivers in
            this pool.
          </p>
        ) : null}
      </div>

      <h4 className="intel-steps-title">How your rank is calculated</h4>
      <ol className="intel-calc-steps">
        {detail.calculation_steps.map((s) => (
          <li key={s.step} className="intel-calc-step">
            <div className="intel-calc-step-head">
              <span className="intel-calc-step-num">{s.step}</span>
              <strong>{s.title}</strong>
              <span className="intel-calc-step-value">{s.value}</span>
            </div>
            <p className="intel-calc-step-detail">{s.detail}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}
