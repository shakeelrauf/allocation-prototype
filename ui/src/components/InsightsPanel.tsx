/** Plain-language risk readout for Explain & AI (technical JSON tucked away). */

import type { ReactNode } from "react";
import { formatUserLabel } from "../utils/userDisplay";

export type ScoreAnomalyPayload = {
  user_id?: string;
  user_name?: string;
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
  user_name?: string;
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

type VerdictTone = "ok" | "watch" | "review";

function driverName(data: { user_id?: string; user_name?: string }): string {
  const id = data.user_id?.trim();
  const name = data.user_name?.trim();
  if (id) return formatUserLabel(id, name);
  return "This driver";
}

function overallVerdict(bundle: InsightsBundle): {
  tone: VerdictTone;
  title: string;
  summary: string;
  action: string;
} {
  const flagged = !!bundle.ensemble.ensemble_flag;
  const risk = bundle.no_show.estimated_no_show_risk_0_1 ?? 0;
  const outlier = !!bundle.anomaly.flag_outlier;

  if (flagged) {
    return {
      tone: "review",
      title: "Worth a quick review",
      summary:
        "At least one check stood out — unusual score and/or several unused bookings in recent history.",
      action: "Open their score history or speak with them before changing parking rules.",
    };
  }
  if (risk >= 0.48 || outlier) {
    return {
      tone: "watch",
      title: "Keep an eye on",
      summary: outlier
        ? "Their behaviour score is a bit different from most people on site."
        : "Recent booking patterns suggest a moderate no-show / waste risk.",
      action: "No urgent action — monitor the next few allocation runs.",
    };
  }
  return {
    tone: "ok",
    title: "Looks typical",
    summary: "Nothing in these quick checks is shouting for immediate intervention.",
    action: "Use your normal parking policies; re-run after new events if behaviour changes.",
  };
}

function scoreCheck(anomaly: ScoreAnomalyPayload): {
  tone: VerdictTone;
  headline: string;
  detail: string;
} {
  const z = anomaly.z_score;
  const score = anomaly.score;
  const tier = anomaly.tier;
  const hasZ = z !== null && z !== undefined && !Number.isNaN(z);

  if (anomaly.note && !hasZ) {
    return {
      tone: "watch",
      headline: "Not enough people to compare",
      detail: anomaly.note,
    };
  }
  if (anomaly.flag_outlier) {
    const dir = hasZ && z! > 0 ? "higher" : "lower";
    return {
      tone: "review",
      headline: "Score stands out",
      detail: `Behaviour score is unusually ${dir} than everyone else registered here${tier ? ` (${tier} tier)` : ""}.`,
    };
  }
  if (hasZ && Math.abs(z!) >= 1) {
    const dir = z! > 0 ? "above" : "below";
    return {
      tone: "watch",
      headline: "Score a bit off average",
      detail: `Sits ${dir} the typical site score${score != null ? ` — currently ${Number(score).toFixed(0)}` : ""}.`,
    };
  }
  return {
    tone: "ok",
    headline: "Score looks normal",
    detail: `In line with most drivers on site${score != null ? ` (score ${Number(score).toFixed(0)}${tier ? `, ${tier}` : ""})` : ""}.`,
  };
}

function bookingCheck(noShow: NoShowRiskPayload): {
  tone: VerdictTone;
  headline: string;
  detail: string;
  pct: number;
} {
  const risk = typeof noShow.estimated_no_show_risk_0_1 === "number" ? noShow.estimated_no_show_risk_0_1 : 0;
  const pct = Math.round(Math.min(100, Math.max(0, risk * 100)));
  const unused = noShow.unused_booking_events_seen ?? 0;
  const carpool = noShow.carpool_events_seen ?? 0;

  let tone: VerdictTone = "ok";
  let headline = "Low booking-waste risk";
  if (risk >= 0.68) {
    tone = "review";
    headline = "Higher waste / no-show risk";
  } else if (risk >= 0.28) {
    tone = "watch";
    headline = "Some booking-waste risk";
  }

  const parts = [`${unused} unused booking${unused === 1 ? "" : "s"} seen recently`];
  if (carpool > 0) parts.push(`${carpool} carpool signal${carpool === 1 ? "" : "s"} (helps lower risk)`);

  return {
    tone,
    headline,
    detail: parts.join(" · ") + ". This is a rough hint, not a prediction they will skip parking.",
    pct,
  };
}

function alertCheck(ensemble: EnsemblePayload): { tone: VerdictTone; headline: string; detail: string } {
  if (ensemble.ensemble_flag) {
    const bits: string[] = [];
    if (ensemble.z_flag) bits.push("unusual behaviour score");
    if (ensemble.burst_unused_bookings) bits.push("cluster of unused bookings");
    return {
      tone: "review",
      headline: "Combined alert",
      detail:
        bits.length > 0
          ? `Newton flags this profile because: ${bits.join(" and ")}.`
          : "Newton flags this profile when signals are combined.",
    };
  }
  return {
    tone: "ok",
    headline: "No combined alert",
    detail: "Score and booking checks together do not cross the alert line.",
  };
}

function SignalRow({
  step,
  title,
  tone,
  headline,
  detail,
  extra,
}: {
  step: string;
  title: string;
  tone: VerdictTone;
  headline: string;
  detail: string;
  extra?: ReactNode;
}) {
  return (
    <li className={`insights-signal insights-signal--${tone}`}>
      <div className="insights-signal-step" aria-hidden>
        {step}
      </div>
      <div className="insights-signal-body">
        <span className="insights-signal-tag">{title}</span>
        <strong className="insights-signal-headline">{headline}</strong>
        <p className="insights-signal-detail">{detail}</p>
        {extra}
      </div>
    </li>
  );
}

export function InsightsPanel({ bundle }: { bundle: InsightsBundle }) {
  const verdict = overallVerdict(bundle);
  const name = driverName(bundle.anomaly);
  const score = scoreCheck(bundle.anomaly);
  const booking = bookingCheck(bundle.no_show);
  const alert = alertCheck(bundle.ensemble);

  const meterColor =
    booking.tone === "ok"
      ? "#2d6a4f"
      : booking.tone === "watch"
        ? "#b0892e"
        : "#a84848";

  return (
    <div className="insights-simple">
      <div className={`insights-verdict insights-verdict--${verdict.tone}`}>
        <p className="insights-verdict-label">Overall for {name}</p>
        <h3 className="insights-verdict-title">{verdict.title}</h3>
        <p className="insights-verdict-summary">{verdict.summary}</p>
        <p className="insights-verdict-action">
          <span className="insights-verdict-arrow" aria-hidden>
            →
          </span>
          {verdict.action}
        </p>
      </div>

      <p className="muted small insights-simple-lead">
        Three quick checks (same seed pool as Parking). Expand technical details only if you need
        raw numbers.
      </p>

      <ol className="insights-signal-list">
        <SignalRow step="1" title="Behaviour score" tone={score.tone} headline={score.headline} detail={score.detail} />
        <SignalRow
          step="2"
          title="Booking habits"
          tone={booking.tone}
          headline={booking.headline}
          detail={booking.detail}
          extra={
            <div className="insights-risk-bar" aria-hidden>
              <div
                className="insights-risk-bar-fill"
                style={{ width: `${booking.pct}%`, background: meterColor }}
              />
            </div>
          }
        />
        <SignalRow step="3" title="Combined" tone={alert.tone} headline={alert.headline} detail={alert.detail} />
      </ol>

      <details className="insight-raw insights-technical">
        <summary>Technical details (for admins)</summary>
        <pre tabIndex={0}>{JSON.stringify(bundle, null, 2)}</pre>
      </details>
    </div>
  );
}
