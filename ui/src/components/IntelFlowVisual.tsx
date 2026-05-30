import type { ReactNode } from "react";
import { IntelFocusBreakdown, type FocusDetail } from "./IntelFocusBreakdown";
import { UserLabel } from "../utils/userDisplay";

function FlowArrow({ label }: { label?: string }) {
  return (
    <div className="alloc-flow-arrow" aria-hidden>
      <svg viewBox="0 0 48 24" className="alloc-flow-arrow-svg">
        <defs>
          <linearGradient id="intelArrowGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#5c6b8a" />
            <stop offset="100%" stopColor="#a78bfa" />
          </linearGradient>
        </defs>
        <path
          d="M4 12 H36 M30 6 L40 12 L30 18"
          fill="none"
          stroke="url(#intelArrowGrad)"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {label ? <span className="alloc-flow-arrow-label">{label}</span> : null}
    </div>
  );
}

function FlowArrowDown({ label }: { label?: string }) {
  return (
    <div className="alloc-flow-arrow alloc-flow-arrow-down" aria-hidden>
      <svg viewBox="0 0 24 48" className="alloc-flow-arrow-svg-v">
        <path
          d="M12 4 V36 M6 30 L12 40 L18 30"
          fill="none"
          stroke="#a78bfa"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {label ? <span className="alloc-flow-arrow-label">{label}</span> : null}
    </div>
  );
}

function IntelStepCard({
  step,
  title,
  body,
  tone = "neutral",
  highlight,
}: {
  step: number;
  title: string;
  body: ReactNode;
  tone?: "focus" | "rank" | "tools" | "ai";
  highlight?: boolean;
}) {
  return (
    <div
      className={`alloc-flow-step intel-flow-step intel-flow-step--${tone}${highlight ? " alloc-flow-step--active" : ""}`}
    >
      <span className="alloc-flow-step-num">{step}</span>
      <h3 className="alloc-flow-step-title">{title}</h3>
      <p className="alloc-flow-step-body">{body}</p>
    </div>
  );
}

export function IntelIntroFlow({
  poolCount,
  focusLabel,
  hasFocus,
}: {
  poolCount: number;
  focusLabel: string;
  hasFocus: boolean;
}) {
  const activeStep = hasFocus ? 3 : poolCount > 0 ? 2 : 1;

  return (
    <section className="alloc-flow intel-flow-intro" aria-label="How explain and AI works">
      <p className="alloc-flow-lead">
        Pick one person, then follow the arrows — each tool answers a different question about
        their place in the ranking.
      </p>
      <div className="alloc-flow-track">
        <IntelStepCard
          step={1}
          tone="rank"
          title="Same pool as Parking"
          highlight={activeStep === 1}
          body={
            <>
              <strong>{poolCount}</strong> driver{poolCount === 1 ? "" : "s"} in the allocation
              pool
            </>
          }
        />
        <FlowArrow label="zoom in on one" />
        <IntelStepCard
          step={2}
          tone="focus"
          title="Focus person"
          highlight={activeStep === 2}
          body={
            hasFocus ? (
              <>
                Explaining <strong>{focusLabel}</strong>
              </>
            ) : (
              <>Choose who you want to understand</>
            )
          }
        />
        <FlowArrow label="pick a lens" />
        <IntelStepCard
          step={3}
          tone="tools"
          title="Why / history / risk"
          highlight={activeStep === 3}
          body={<>See who ranks above them, score timeline, or risk signals</>}
        />
        <FlowArrow label="or chat" />
        <IntelStepCard
          step={4}
          tone="ai"
          title="AI guide"
          body={<>Plain-language Q&amp;A about fairness and the ranked list</>}
        />
      </div>
    </section>
  );
}

export type IntelToolId = "explain" | "history" | "insights" | "shadow";

const TOOL_META: Record<
  IntelToolId,
  { step: string; title: string; desc: string; tone: string }
> = {
  explain: {
    step: "A",
    title: "Why this rank?",
    desc: "Who is above them and why each person ranks higher",
    tone: "explain",
  },
  history: {
    step: "B",
    title: "Score history",
    desc: "Events that moved their behaviour score and tier",
    tone: "history",
  },
  insights: {
    step: "C",
    title: "Insights & risk",
    desc: "Simple overall verdict + 3 plain checks",
    tone: "insights",
  },
  shadow: {
    step: "D",
    title: "Shadow compare",
    desc: "Newton vs mock legacy ranking (behaviour on vs off)",
    tone: "shadow",
  },
};

export function IntelToolGrid({
  hasFocus,
  activePanel,
  busy,
  onRun,
}: {
  hasFocus: boolean;
  activePanel: IntelToolId | "ai" | null;
  busy?: IntelToolId | null;
  onRun: (id: IntelToolId) => void;
}) {
  const ids: IntelToolId[] = ["explain", "history", "insights", "shadow"];

  return (
    <div className="intel-tool-grid" role="group" aria-label="Analysis tools">
      {ids.map((id) => {
        const m = TOOL_META[id];
        const needsFocus = id !== "shadow";
        const disabled = needsFocus && !hasFocus;
        const isActive = activePanel === id;
        const isBusy = busy === id;
        return (
          <button
            key={id}
            type="button"
            className={`intel-tool-card intel-tool-card--${m.tone}${isActive ? " intel-tool-card--active" : ""}`}
            disabled={disabled || !!busy}
            onClick={() => onRun(id)}
          >
            <span className="intel-tool-step">{m.step}</span>
            <span className="intel-tool-title">{m.title}</span>
            <span className="intel-tool-desc">{m.desc}</span>
            {disabled ? (
              <span className="intel-tool-hint">Select focus user first</span>
            ) : isBusy ? (
              <span className="intel-tool-hint">Loading…</span>
            ) : (
              <span className="intel-tool-cta">Run →</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

type AboveRow = {
  rank: number;
  user_id: string;
  user_name?: string;
  explain: string;
};

export function IntelExplainLadder({
  focusUserId,
  focusUserName,
  focusRank,
  above,
  focusDetail,
}: {
  focusUserId: string;
  focusUserName?: string;
  focusRank: number;
  above: AboveRow[];
  focusDetail?: FocusDetail | null;
}) {
  const preview = above.slice(0, 6);
  const hidden = above.length - preview.length;

  return (
    <section className="intel-explain-visual" aria-label="Ranking ladder for focus user">
      <div className="intel-explain-ladder">
        <div className="intel-ladder-top">
          <span className="alloc-flow-bubble-label">Better rank = higher in line</span>
          {preview.length === 0 ? (
            <div className="intel-ladder-rung intel-ladder-rung--top">
              <span className="badge on">#1</span>
              <span className="muted small">Nobody above — focus is at the top for this seed</span>
            </div>
          ) : (
            preview.map((r) => (
              <div key={r.user_id + r.rank} className="intel-ladder-rung">
                <span className="intel-ladder-arrow" aria-hidden>
                  ↑
                </span>
                <span className="badge">Rank #{r.rank}</span>
                <UserLabel userId={r.user_id} userName={r.user_name} />
                <p className="intel-ladder-why">{r.explain}</p>
              </div>
            ))
          )}
          {hidden > 0 ? (
            <p className="muted small intel-ladder-more">+ {hidden} more ranked above (not shown)</p>
          ) : null}
          <FlowArrowDown label="then your focus person" />
        </div>
        <div className="intel-ladder-focus">
          <span className="intel-flow-pointer" aria-hidden>
            ★
          </span>
          <span className="badge on">Rank #{focusRank}</span>
          <strong>
            <UserLabel userId={focusUserId} userName={focusUserName} />
          </strong>
          <span className="muted small">— why they are not higher yet</span>
        </div>
      </div>
      {focusDetail ? (
        <div className="intel-narrative-box">
          <IntelFocusBreakdown detail={focusDetail} />
        </div>
      ) : null}
    </section>
  );
}

type ShadowRow = {
  user_id: string;
  user_name?: string;
  newton_rank: number | null;
  legacy_rank: number | null;
  delta_newton_minus_legacy: number | null;
};

export function IntelShadowCompare({
  newton,
  legacy,
  diff,
}: {
  newton: { rank: number; user_id: string; user_name?: string }[];
  legacy: { rank: number; user_id: string; user_name?: string }[];
  diff: ShadowRow[];
}) {
  const movers = diff.filter(
    (d) => d.delta_newton_minus_legacy != null && d.delta_newton_minus_legacy !== 0,
  ).length;

  return (
    <section className="intel-shadow-visual" aria-label="Newton vs legacy comparison">
      <p className="alloc-flow-lead">
        <strong>{movers}</strong> driver{movers === 1 ? "" : "s"} change rank when behaviour score
        is included (Newton) vs ignored (legacy mock).
      </p>
      <div className="intel-shadow-columns">
        <div className="intel-shadow-col newton">
          <h3 className="intel-shadow-col-title">
            <span className="intel-shadow-arrow">→</span> Newton 3
          </h3>
          <p className="muted small">Team → user priority → behaviour score</p>
          <ol className="intel-shadow-ranks">
            {newton.slice(0, 8).map((r) => (
              <li key={r.user_id}>
                <span className="badge on">#{r.rank}</span>
                <UserLabel userId={r.user_id} userName={r.user_name} />
              </li>
            ))}
          </ol>
        </div>
        <div className="intel-shadow-vs" aria-hidden>
          <svg viewBox="0 0 40 120" className="intel-shadow-vs-svg">
            <path
              d="M8 60 H32 M24 52 L32 60 L24 68 M8 60 H8 20 M8 60 H8 100"
              fill="none"
              stroke="#6b7a99"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
          <span className="intel-shadow-vs-label">vs</span>
        </div>
        <div className="intel-shadow-col legacy">
          <h3 className="intel-shadow-col-title">Mock legacy</h3>
          <p className="muted small">Team → user priority only</p>
          <ol className="intel-shadow-ranks">
            {legacy.slice(0, 8).map((r) => (
              <li key={r.user_id}>
                <span className="badge">#{r.rank}</span>
                <UserLabel userId={r.user_id} userName={r.user_name} />
              </li>
            ))}
          </ol>
        </div>
      </div>
      <div className="intel-shadow-delta">
        <h3 className="subh">Biggest rank moves (Δ Newton − legacy)</h3>
        <ul className="intel-delta-list">
          {diff
            .filter((d) => d.delta_newton_minus_legacy != null && d.delta_newton_minus_legacy !== 0)
            .slice(0, 6)
            .map((d) => {
              const delta = d.delta_newton_minus_legacy!;
              const better = delta < 0;
              return (
                <li key={d.user_id} className={`intel-delta-item${better ? " up" : " down"}`}>
                  <span className="intel-delta-arrow" aria-hidden>
                    {better ? "↑" : "↓"}
                  </span>
                  <UserLabel userId={d.user_id} userName={d.user_name} />
                  <span className="muted small">
                    Newton #{d.newton_rank ?? "—"} · Legacy #{d.legacy_rank ?? "—"}
                  </span>
                  <span className={`intel-delta-badge${better ? " good" : ""}`}>
                    {delta > 0 ? "+" : ""}
                    {delta}
                  </span>
                </li>
              );
            })}
        </ul>
      </div>
    </section>
  );
}

export function IntelAiHeader({ aiName, poolCount }: { aiName: string; poolCount: number }) {
  return (
    <div className="intel-ai-header">
      <div className="intel-ai-header-icon" aria-hidden>
        {aiName.slice(0, 1).toUpperCase()}
      </div>
      <div>
        <h2 className="intel-ai-title">Chat with {aiName}</h2>
        <p className="muted small">
          Arrows from step 4 above — ask about the ranked list for{" "}
          <strong>{poolCount}</strong> drivers (same seed as Parking).
        </p>
      </div>
    </div>
  );
}
