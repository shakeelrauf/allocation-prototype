/** Display behaviour score change after an event. */

export function formatScoreDelta(delta: number | null | undefined): string {
  if (delta === null || delta === undefined || Number.isNaN(delta)) return "No score change";
  const n = Number(delta);
  if (Math.abs(n) < 0.05) return "No score change";
  const rounded = Math.round(n * 10) / 10;
  const sign = rounded > 0 ? "+" : "";
  return `${sign}${rounded} points`;
}

export function scoreDeltaTone(delta: number | null | undefined): "up" | "down" | "neutral" {
  if (delta === null || delta === undefined || Number.isNaN(delta)) return "neutral";
  if (delta > 0.05) return "up";
  if (delta < -0.05) return "down";
  return "neutral";
}

export function ScoreDeltaBadge({
  delta,
  scoreBefore,
  scoreAfter,
  tierAfter,
  compact,
}: {
  delta?: number | null;
  scoreBefore?: number | null;
  scoreAfter?: number | null;
  tierAfter?: string | null;
  compact?: boolean;
}) {
  const tone = scoreDeltaTone(delta);
  const label = formatScoreDelta(delta);

  return (
    <div className={`score-delta score-delta--${tone}${compact ? " score-delta--compact" : ""}`}>
      <span className="score-delta-points">{label}</span>
      {!compact && scoreBefore != null && scoreAfter != null ? (
        <span className="muted small score-delta-detail">
          Score {Number(scoreBefore).toFixed(0)} → {Number(scoreAfter).toFixed(0)}
          {tierAfter ? ` (${tierAfter})` : ""}
        </span>
      ) : null}
    </div>
  );
}
