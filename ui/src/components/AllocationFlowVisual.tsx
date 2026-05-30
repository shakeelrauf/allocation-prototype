import type { ReactNode } from "react";
import { UserLabel } from "../utils/userDisplay";

type AllocRow = {
  rank: number;
  user_id: string;
  user_name?: string;
  parking_slot?: number | null;
};

type FlowProps = {
  poolCount: number;
  capacity: number;
  busy?: boolean;
  result?: {
    pool_size: number;
    capacity: number;
    assigned: AllocRow[];
    waiting_total: number;
    how_it_works?: string;
  } | null;
};

function FlowArrow({ label }: { label?: string }) {
  return (
    <div className="alloc-flow-arrow" aria-hidden>
      <svg viewBox="0 0 48 24" className="alloc-flow-arrow-svg">
        <defs>
          <linearGradient id="allocArrowGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#5c6b8a" />
            <stop offset="100%" stopColor="#77a3ff" />
          </linearGradient>
        </defs>
        <path
          d="M4 12 H36 M30 6 L40 12 L30 18"
          fill="none"
          stroke="url(#allocArrowGrad)"
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
          stroke="#77a3ff"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {label ? <span className="alloc-flow-arrow-label">{label}</span> : null}
    </div>
  );
}

function StepCard({
  step,
  title,
  body,
  tone = "neutral",
  highlight,
}: {
  step: number;
  title: string;
  body: ReactNode;
  tone?: "neutral" | "pool" | "rank" | "win" | "wait";
  highlight?: boolean;
}) {
  return (
    <div
      className={`alloc-flow-step alloc-flow-step--${tone}${highlight ? " alloc-flow-step--active" : ""}`}
    >
      <span className="alloc-flow-step-num">{step}</span>
      <h3 className="alloc-flow-step-title">{title}</h3>
      <p className="alloc-flow-step-body">{body}</p>
    </div>
  );
}

/** Horizontal explainer: pool → rank → assign → wait */
export function AllocationSetupFlow({ poolCount, capacity, busy }: FlowProps) {
  const cap = Math.max(1, capacity || 1);
  const activeStep = busy ? 3 : poolCount > 0 ? 2 : 1;

  return (
    <section className="alloc-flow alloc-flow-setup" aria-label="How parking assignment works">
      <p className="alloc-flow-lead">
        Follow the path left to right — each arrow is the next thing Newton does.
      </p>
      <div className="alloc-flow-track">
        <StepCard
          step={1}
          tone="pool"
          title="Who competes"
          highlight={activeStep === 1}
          body={
            <>
              <strong>{poolCount}</strong> driver{poolCount === 1 ? "" : "s"} in today&apos;s pool
              {poolCount === 0 ? (
                <span className="alloc-flow-hint"> — import CSV on Dashboard first</span>
              ) : null}
            </>
          }
        />
        <FlowArrow label="everyone enters" />
        <StepCard
          step={2}
          tone="rank"
          title="One ranked list"
          highlight={activeStep === 2}
          body={
            <>
              Team rules, then individual priority, then <strong>behaviour score</strong> — best
              drivers rise to the top.
            </>
          }
        />
        <FlowArrow label="top ranks win" />
        <StepCard
          step={3}
          tone="win"
          title="Parking spaces"
          highlight={activeStep === 3 || busy}
          body={
            <>
              <strong>{cap}</strong> free space{cap === 1 ? "" : "s"} → winners listed below (Space
              #1, #2 …)
            </>
          }
        />
      </div>
    </section>
  );
}

/** After a run: funnel diagram with arrows into winners vs waiting */
export function AllocationResultFlow({ result }: { result: NonNullable<FlowProps["result"]> }) {
  const topAssigned = result.assigned.slice(0, 4);
  const nextWaiting = result.waiting_total;
  const cap = result.capacity;

  return (
    <section className="alloc-flow alloc-flow-result" aria-label="This run explained">
      <h3 className="alloc-flow-result-heading">What happened in this run</h3>
      {result.how_it_works ? <p className="muted small alloc-flow-result-sub">{result.how_it_works}</p> : null}

      <div className="alloc-flow-funnel">
        <div className="alloc-flow-funnel-top">
          <div className="alloc-flow-bubble pool">
            <span className="alloc-flow-bubble-label">Started with</span>
            <strong>{result.pool_size}</strong>
            <span>drivers in the pool</span>
          </div>
          <FlowArrowDown label="Newton sorts into one line" />
          <div className="alloc-flow-bubble rank">
            <span className="alloc-flow-bubble-label">Ranked list</span>
            <strong>#1</strong>
            <span>best driver</span>
            <span className="alloc-flow-ellipsis">…</span>
            <strong>#{result.pool_size}</strong>
            <span>last</span>
          </div>
          <FlowArrowDown label={`top ${cap} get a booking`} />
        </div>

        <div className="alloc-flow-winners-only">
          <div className="alloc-flow-branch win">
            <div className="alloc-flow-branch-head">
              <span className="alloc-flow-pointer" aria-hidden>
                ↓
              </span>
              <strong>Got parking</strong>
              <span className="muted small">
                ranks 1–{cap} → Space #1 … #{cap}
              </span>
            </div>
            <ul className="alloc-flow-mini-list">
              {topAssigned.map((w) => (
                <li key={w.user_id} className="alloc-flow-mini-item">
                  <span className="alloc-flow-mini-arrow" aria-hidden>
                    →
                  </span>
                  <span className="badge on">Space {w.parking_slot ?? w.rank}</span>
                  <UserLabel userId={w.user_id} userName={w.user_name} />
                  <span className="muted small">was rank #{w.rank}</span>
                </li>
              ))}
              {result.assigned.length > topAssigned.length ? (
                <li className="alloc-flow-mini-more muted small">
                  + {result.assigned.length - topAssigned.length} more with a space
                </li>
              ) : null}
            </ul>
          </div>
          {nextWaiting > 0 ? (
            <p className="muted small alloc-flow-wait-note">
              {nextWaiting} other driver{nextWaiting === 1 ? "" : "s"} ranked below the cut-off —
              not shown in detail.
            </p>
          ) : null}
        </div>
      </div>
    </section>
  );
}
