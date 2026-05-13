import { useEffect, useRef, useState } from "react";
import { fetchJson } from "../api/client";
import { useData } from "../context/DataContext";
import { InsightsPanel, type InsightsBundle } from "./InsightsPanel";
import { LlmMessageBody } from "./LlmMessageBody";

type LlmChatTurn = {
  role: "user" | "assistant";
  content: string;
  tone?: "neutral" | "error";
};

type ShadowPayload = {
  newton: { rank: number; user_id: string }[];
  legacy_mock: { rank: number; user_id: string }[];
  diff: {
    user_id: string;
    newton_rank: number | null;
    legacy_rank: number | null;
    delta_newton_minus_legacy: number | null;
  }[];
};

export function IntelTab() {
  const { API, users, getPoolUserIds, health } = useData();
  const aiName = String(health?.features?.llm_character ?? "Shakeel").trim() || "Shakeel";
  const [seed, setSeed] = useState(42);
  const [focus, setFocus] = useState("");
  const [narrative, setNarrative] = useState("");
  const [above, setAbove] = useState<{ rank: number; user_id: string; explain: string }[]>([]);
  const [showExplain, setShowExplain] = useState(false);

  const [shadow, setShadow] = useState<ShadowPayload | null>(null);
  const [showShadow, setShowShadow] = useState(false);

  const [historyRows, setHistoryRows] = useState<
    { created_at?: string; event_type: string; score: number; tier: string; applied: boolean; detail: string }[]
  >([]);
  const [historyNote, setHistoryNote] = useState("");
  const [showHistory, setShowHistory] = useState(false);

  const [insightsBundle, setInsightsBundle] = useState<InsightsBundle | null>(null);
  const [showInsights, setShowInsights] = useState(false);

  const [llmChat, setLlmChat] = useState<LlmChatTurn[]>([]);
  const [llmDraft, setLlmDraft] = useState("");
  const [llmBusy, setLlmBusy] = useState(false);
  const [llmMeta, setLlmMeta] = useState("");
  const llmEndRef = useRef<HTMLDivElement>(null);

  const idsParam = () => getPoolUserIds().join(",");

  useEffect(() => {
    llmEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [llmChat, llmBusy]);

  async function postExplainLlm(body: Record<string, unknown>) {
    return fetchJson<{
      text?: string;
      mode?: string;
      hint?: string;
      error?: string;
      echo_user?: string;
    }>(`${API}/allocation/explain-llm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  async function runExplain() {
    const ids = idsParam();
    const f = focus.trim();
    if (!f || !ids) {
      window.alert("Pick focus user and ensure pool has users.");
      return;
    }
    try {
      const ex = await fetchJson<{
        error?: string;
        narrative?: string;
        users_above?: { rank: number; user_id: string; explain: string }[];
      }>(
        `${API}/allocation/explain?user_ids=${encodeURIComponent(ids)}&focus=${encodeURIComponent(f)}&seed=${seed}`,
      );
      if (ex.error) {
        window.alert(ex.error);
        return;
      }
      setNarrative(ex.narrative || "");
      setAbove(ex.users_above || []);
      setShowExplain(true);
    } catch (e) {
      window.alert(String(e instanceof Error ? e.message : e));
    }
  }

  async function runShadow() {
    const ids = idsParam();
    if (!ids) {
      window.alert("No users in pool.");
      return;
    }
    try {
      const sh = await fetchJson<ShadowPayload>(
        `${API}/allocation/shadow?user_ids=${encodeURIComponent(ids)}&seed=${seed}`,
      );
      setShadow(sh);
      setShowShadow(true);
    } catch (e) {
      window.alert(String(e instanceof Error ? e.message : e));
    }
  }

  async function runHistory() {
    const f = focus.trim();
    if (!f) {
      window.alert("Select focus user.");
      return;
    }
    try {
      const data = await fetchJson<{ snapshots?: typeof historyRows; note?: string }>(
        `${API}/users/${encodeURIComponent(f)}/score-history?limit=40`,
      );
      setHistoryRows(data.snapshots || []);
      setHistoryNote(data.note && !(data.snapshots || []).length ? data.note : "");
      setShowHistory(true);
    } catch (e) {
      window.alert(String(e instanceof Error ? e.message : e));
    }
  }

  async function runInsights() {
    const f = focus.trim();
    if (!f) {
      window.alert("Select focus user.");
      return;
    }
    try {
      const data = await fetchJson<{ anomaly: unknown; no_show: unknown; ensemble: unknown }>(
        `${API}/users/${encodeURIComponent(f)}/insights`,
      );
      setInsightsBundle({
        anomaly: data.anomaly as InsightsBundle["anomaly"],
        no_show: data.no_show as InsightsBundle["no_show"],
        ensemble: data.ensemble as InsightsBundle["ensemble"],
      });
      setShowInsights(true);
    } catch (e) {
      window.alert(String(e instanceof Error ? e.message : e));
    }
  }

  function appendAssistantOnly(res: {
    text?: string;
    mode?: string;
    hint?: string;
    error?: string;
  }) {
    let assistantTurn: LlmChatTurn;
    if (res.mode === "ollama") {
      assistantTurn = { role: "assistant", content: res.text || "", tone: "neutral" };
    } else if (res.mode === "template") {
      const hint = res.hint ? `\n\n_${res.hint}_` : "";
      assistantTurn = {
        role: "assistant",
        content: `${res.text || ""}${hint}`.trim(),
        tone: "neutral",
      };
    } else {
      assistantTurn = {
        role: "assistant",
        content: res.error || res.text || "Request failed.",
        tone: "error",
      };
    }
    setLlmChat((c) => [...c, assistantTurn]);
    setLlmMeta(`Last response: ${res.mode || "?"}`);
  }

  async function sendLlmMessage() {
    const ids = idsParam();
    if (!ids) {
      window.alert("No users.");
      return;
    }
    const rawDraft = llmDraft;
    const msg = rawDraft.trim();
    const isFirst = llmChat.length === 0;
    if (!isFirst && !msg) {
      window.alert("Enter a message.");
      return;
    }

    const displayBubble = isFirst ? msg || "Explain this parking allocation ranking." : msg;
    const transcriptForApi = !isFirst ? llmChat.map(({ role, content }) => ({ role, content })) : [];

    setLlmChat((c) => [...c, { role: "user", content: displayBubble }]);
    setLlmDraft("");

    setLlmBusy(true);
    setLlmMeta("Sending…");
    try {
      let res: Awaited<ReturnType<typeof postExplainLlm>>;
      if (isFirst) {
        res = await postExplainLlm({
          user_ids: ids,
          seed,
          context: msg,
          messages: [],
        });
      } else {
        res = await postExplainLlm({
          user_ids: ids,
          seed,
          messages: transcriptForApi,
          follow_up: msg,
        });
      }
      appendAssistantOnly(res);
    } catch (e) {
      setLlmChat((c) => (c.length > 0 && c[c.length - 1]?.role === "user" ? c.slice(0, -1) : c));
      setLlmDraft(rawDraft);
      window.alert(String(e instanceof Error ? e.message : e));
      setLlmMeta("");
    } finally {
      setLlmBusy(false);
    }
  }

  function clearLlmChat() {
    setLlmChat([]);
    setLlmDraft("");
    setLlmMeta("");
  }

  return (
    <div className="grid-inner">
        <article className="card wide">
          <div className="row-inline wrap">
            <label>
              Focus user
              <select value={focus} onChange={(e) => setFocus(e.target.value)}>
                <option value="">{users.length ? "Select user…" : "No users — register first"}</option>
                {users.map((u) => (
                  <option key={u.user_id} value={u.user_id}>
                    {u.user_id} ({u.tier})
                  </option>
                ))}
              </select>
            </label>
            <label className="inline">
              Seed
              <input className="w-short" type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} />
            </label>
            <button type="button" onClick={() => void runExplain()}>
              Why this rank?
            </button>
            <button type="button" className="secondary" onClick={() => void runHistory()}>
              Score history
            </button>
            <button type="button" className="secondary" onClick={() => void runInsights()}>
              Insights / risk
            </button>
          </div>
        </article>

        {showExplain && (
          <article className="card wide" id="box-explain">
            <h2>Explainability</h2>
            <p className="narrative">{narrative}</p>
            <h3 className="subh">Users ranked above focus</h3>
            <div className="table-wrap">
              <table id="tbl-above">
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>User</th>
                    <th>Explain</th>
                  </tr>
                </thead>
                <tbody>
                  {above.map((r) => (
                    <tr key={r.user_id + r.rank}>
                      <td>{r.rank}</td>
                      <td>{r.user_id}</td>
                      <td>{r.explain}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        )}

        {showShadow && shadow && (
          <article className="card wide" id="box-shadow">
            <h2>Shadow mode — Newton vs mock legacy</h2>
            <p className="muted small">Legacy ignores behaviour score; only group &amp; user priority + tie-break.</p>
            <div className="split">
              <div>
                <h3 className="subh">Newton 3</h3>
                <div className="table-wrap">
                  <table id="tbl-newton">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>User</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(shadow.newton || []).map((r) => (
                        <tr key={r.user_id}>
                          <td>{r.rank}</td>
                          <td>{r.user_id}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <div>
                <h3 className="subh">Mock legacy</h3>
                <div className="table-wrap">
                  <table id="tbl-legacy">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>User</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(shadow.legacy_mock || []).map((r) => (
                        <tr key={r.user_id}>
                          <td>{r.rank}</td>
                          <td>{r.user_id}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
            <h3 className="subh">Rank delta (Newton − legacy)</h3>
            <div className="table-wrap">
              <table id="tbl-diff">
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Newton</th>
                    <th>Legacy</th>
                    <th>Δ</th>
                  </tr>
                </thead>
                <tbody>
                  {(shadow.diff || []).map((d) => (
                    <tr key={d.user_id}>
                      <td>{d.user_id}</td>
                      <td>{d.newton_rank ?? "—"}</td>
                      <td>{d.legacy_rank ?? "—"}</td>
                      <td>
                        {d.delta_newton_minus_legacy === null || d.delta_newton_minus_legacy === undefined
                          ? "—"
                          : d.delta_newton_minus_legacy}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        )}

        {showHistory && (
          <article className="card wide" id="box-history">
            <h2>Score &amp; tier history</h2>
            <div className="table-wrap">
              <table id="tbl-history">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Event</th>
                    <th>Score</th>
                    <th>Tier</th>
                    <th>Applied</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {historyNote ? (
                    <tr>
                      <td colSpan={6}>{historyNote}</td>
                    </tr>
                  ) : (
                    historyRows.map((s, i) => (
                      <tr key={i}>
                        <td>{s.created_at || ""}</td>
                        <td>{s.event_type}</td>
                        <td>{Number(s.score).toFixed(2)}</td>
                        <td>{s.tier}</td>
                        <td>{s.applied ? "yes" : "no"}</td>
                        <td>{s.detail}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </article>
        )}

        {showInsights && insightsBundle && (
          <article className="card wide" id="box-insights">
            <h2>Insights &amp; risk signals</h2>
            <p className="muted small insight-intro">
              Plain-language readouts from Newton&apos;s built-in heuristics — useful for triage, not a substitute for
              your policies or ground truth.
            </p>
            <InsightsPanel bundle={insightsBundle} />
          </article>
        )}

        <article className="card wide">
          <h2>LLM chat</h2>
          <p className="muted small">
            Ranking is refreshed from the pool and seed on every send. First send can be blank for a default summary.
          </p>
          <div className="llm-chat-actions">
            <button type="button" className="secondary" disabled={llmBusy || llmChat.length === 0} onClick={clearLlmChat}>
              Clear conversation
            </button>
            {llmMeta ? <span className="muted small">{llmMeta}</span> : null}
          </div>
          <div className="llm-chat-panel mt">
            <div className="llm-chat" aria-live="polite">
              {llmChat.length === 0 ? (
                <div className="llm-host-welcome">
                  <div className="llm-host-avatar" aria-hidden="true">
                    {aiName.slice(0, 1).toUpperCase()}
                  </div>
                  <div className="llm-host-copy">
                    <p className="llm-host-greeting">
                      Hi — I&apos;m <strong>{aiName}</strong>, your Newton 3 allocation guide.
                    </p>
                    <p className="muted small">
                      Ask anything about the ranking, say hi, or press <strong>Send</strong> with an empty box and
                      I&apos;ll give you a short default walkthrough.
                    </p>
                  </div>
                </div>
              ) : (
                llmChat.map((turn, i) => (
                  <div
                    key={i}
                    className={
                      "llm-msg " +
                      (turn.role === "user" ? "llm-msg-user" : "llm-msg-assistant") +
                      (turn.tone === "error" ? " llm-msg-tone-error" : "")
                    }
                  >
                    {turn.role === "assistant" ? (
                      <>
                        <div className="llm-msg-from">{aiName}</div>
                        <LlmMessageBody content={turn.content} />
                      </>
                    ) : (
                      turn.content
                    )}
                  </div>
                ))
              )}
              {llmBusy ? <div className="muted small llm-chat-meta">Thinking…</div> : null}
              <div ref={llmEndRef} />
            </div>
            <div className="llm-follow-row mt">
              <input
                type="text"
                value={llmDraft}
                onChange={(e) => setLlmDraft(e.target.value)}
                placeholder={
                  llmChat.length === 0
                    ? "Prompt: ask about the ranking, fairness, or leave blank for a short tour…"
                    : "Prompt: follow-up question…"
                }
                disabled={llmBusy}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void sendLlmMessage();
                  }
                }}
              />
              <button
                type="button"
                disabled={
                  llmBusy ||
                  !idsParam() ||
                  (llmChat.length > 0 && !llmDraft.trim())
                }
                onClick={() => void sendLlmMessage()}
              >
                Send
              </button>
            </div>
          </div>
        </article>
      </div>
  );
}

