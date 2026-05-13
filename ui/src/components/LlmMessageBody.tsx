import { useMemo } from "react";

/** Shape some models return instead of Markdown (we render it nicely when detected). */
export type NewtonNarrativeJson = {
  title: string;
  summary: string;
  bullets: string[];
  rank_notes: { rank: number; user_id: string; note: string }[];
  fairness: string;
};

function stripCodeFence(s: string): string {
  const t = s.trim();
  const m = /^```(?:json)?\s*([\s\S]*?)```$/im.exec(t);
  return m ? m[1].trim() : t;
}

function normalizeBullets(b: unknown): string[] {
  if (!Array.isArray(b)) return [];
  const out: string[] = [];
  for (const x of b) {
    if (typeof x === "string" && x.trim()) out.push(x.trim());
  }
  return out;
}

function normalizeRankNotes(x: unknown): { rank: number; user_id: string; note: string }[] {
  if (!Array.isArray(x)) return [];
  return x
    .filter((r): r is Record<string, unknown> => r !== null && typeof r === "object")
    .map((r) => ({
      rank: typeof r.rank === "number" && !Number.isNaN(r.rank) ? r.rank : Number(r.rank) || 0,
      user_id: String(r.user_id ?? "").trim(),
      note: typeof r.note === "string" ? r.note.trim() : "",
    }))
    .filter((r) => r.user_id.length > 0)
    .sort((a, b) => a.rank - b.rank);
}

/** Parse narrative-shaped JSON some LLMs emit; returns null if not a match or invalid JSON. */
export function parseNewtonNarrativeJson(raw: string): NewtonNarrativeJson | null {
  let s = stripCodeFence(raw);
  if (!s.startsWith("{")) return null;
  try {
    const obj = JSON.parse(s) as unknown;
    if (!obj || typeof obj !== "object") return null;
    const o = obj as Record<string, unknown>;
    const title = o.title;
    if (typeof title !== "string" || !title.trim()) return null;
    const summary = typeof o.summary === "string" ? o.summary.trim() : "";
    const bullets = normalizeBullets(o.bullets);
    if (!summary && bullets.length === 0) return null;
    const fairness = typeof o.fairness === "string" ? o.fairness.trim() : "";
    return {
      title: title.trim(),
      summary,
      bullets,
      rank_notes: normalizeRankNotes(o.rank_notes),
      fairness,
    };
  } catch {
    return null;
  }
}

function NarrativeCard({ data }: { data: NewtonNarrativeJson }) {
  return (
    <div className="llm-narrative">
      <h4 className="llm-narrative-title">{data.title}</h4>
      {data.summary ? <p className="llm-narrative-summary">{data.summary}</p> : null}
      {data.bullets.length > 0 ? (
        <ul className="llm-narrative-bullets">
          {data.bullets.map((b, i) => (
            <li key={i}>{b}</li>
          ))}
        </ul>
      ) : null}
      {data.rank_notes.length > 0 ? (
        <div className="llm-narrative-ranks">
          <p className="llm-narrative-subhead">This allocation</p>
          <ul className="llm-narrative-rank-list">
            {data.rank_notes.map((r) => (
              <li key={r.user_id + r.rank}>
                <strong>#{r.rank}</strong> {r.user_id}
                {r.note ? <span className="muted"> — {r.note}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {data.fairness ? <p className="llm-narrative-fairness">{data.fairness}</p> : null}
    </div>
  );
}

/** Renders assistant text; detects narrative JSON and shows a formatted card instead of a raw blob. */
export function LlmMessageBody({ content }: { content: string }) {
  const structured = useMemo(() => parseNewtonNarrativeJson(content), [content]);
  if (structured) {
    return <NarrativeCard data={structured} />;
  }
  return <div className="llm-msg-plain">{content}</div>;
}
