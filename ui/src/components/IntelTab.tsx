import { useEffect, useMemo, useRef, useState } from "react";
import { fetchJson } from "../api/client";
import { useData } from "../context/DataContext";
import { UserSearchSelect } from "./UserSearchSelect";
import { UserLabel } from "../utils/userDisplay";
import {
  IntelAiHeader,
  IntelExplainLadder,
  IntelIntroFlow,
  IntelShadowCompare,
  IntelToolGrid,
  type IntelToolId,
} from "./IntelFlowVisual";
import type { FocusDetail } from "./IntelFocusBreakdown";
import { InsightsPanel, type InsightsBundle } from "./InsightsPanel";
import { LlmMessageBody } from "./LlmMessageBody";

type LlmChatTurn = {
  role: "user" | "assistant";
  content: string;
  tone?: "neutral" | "error";
};

type ShadowPayload = {
  newton: { rank: number; user_id: string; user_name?: string }[];
  legacy_mock: { rank: number; user_id: string; user_name?: string }[];
  diff: {
    user_id: string;
    user_name?: string;
    newton_rank: number | null;
    legacy_rank: number | null;
    delta_newton_minus_legacy: number | null;
  }[];
};

export function IntelTab() {
  const { API, users, getPoolUserIds, health, formatUser } = useData();
  const aiName = String(health?.features?.llm_character ?? "Shakeel").trim() || "Shakeel";
  const poolCount = getPoolUserIds().length;
  const [seed, setSeed] = useState(42);
  const [focus, setFocus] = useState("");
  const [focusDetail, setFocusDetail] = useState<FocusDetail | null>(null);
  const [above, setAbove] = useState<
    { rank: number; user_id: string; user_name?: string; explain: string }[]
  >([]);
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

  const [toolBusy, setToolBusy] = useState<IntelToolId | null>(null);

  const [llmChat, setLlmChat] = useState<LlmChatTurn[]>([]);
  const [llmDraft, setLlmDraft] = useState("");
  const [llmBusy, setLlmBusy] = useState(false);
  const [llmMeta, setLlmMeta] = useState("");
  const llmEndRef = useRef<HTMLDivElement>(null);

  const idsParam = () => getPoolUserIds().join(",");

  const focusUser = useMemo(
    () => users.find((u) => u.user_id === focus),
    [users, focus],
  );

  const focusLabel = focus ? formatUser(focus, focusUser?.user_name) : "";
  const focusRank = above.length > 0 ? above[above.length - 1].rank + 1 : above.length === 0 && showExplain ? 1 : above.length + 1;

  const activePanel: IntelToolId | null = showExplain
    ? "explain"
    : showShadow
      ? "shadow"
      : showHistory
        ? "history"
        : showInsights
          ? "insights"
          : null;

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
    setToolBusy("explain");
    try {
      const ex = await fetchJson<{
        error?: string;
        narrative?: string;
        focus_detail?: FocusDetail;
        users_above?: {
          rank: number;
          user_id: string;
          user_name?: string;
          explain: string;
          reason?: string;
        }[];
      }>(
        `${API}/allocation/explain?user_ids=${encodeURIComponent(ids)}&focus=${encodeURIComponent(f)}&seed=${seed}`,
      );
      if (ex.error) {
        window.alert(ex.error);
        return;
      }
      setFocusDetail(ex.focus_detail ?? null);
      setAbove(
        (ex.users_above || []).map((r) => ({
          rank: r.rank,
          user_id: r.user_id,
          user_name: r.user_name,
          explain: r.reason || r.explain,
        })),
      );
      setShowExplain(true);
      setShowShadow(false);
      setShowHistory(false);
      setShowInsights(false);
    } catch (e) {
      window.alert(String(e instanceof Error ? e.message : e));
    } finally {
      setToolBusy(null);
    }
  }

  async function runShadow() {
    const ids = idsParam();
    if (!ids) {
      window.alert("No users in pool.");
      return;
    }
    setToolBusy("shadow");
    try {
      const sh = await fetchJson<ShadowPayload>(
        `${API}/allocation/shadow?user_ids=${encodeURIComponent(ids)}&seed=${seed}`,
      );
      setShadow(sh);
      setShowShadow(true);
      setShowExplain(false);
      setShowHistory(false);
      setShowInsights(false);
    } catch (e) {
      window.alert(String(e instanceof Error ? e.message : e));
    } finally {
      setToolBusy(null);
    }
  }

  async function runHistory() {
    const f = focus.trim();
    if (!f) {
      window.alert("Select focus user.");
      return;
    }
    setToolBusy("history");
    try {
      const data = await fetchJson<{ snapshots?: typeof historyRows; note?: string }>(
        `${API}/users/${encodeURIComponent(f)}/score-history?limit=40`,
      );
      setHistoryRows(data.snapshots || []);
      setHistoryNote(data.note && !(data.snapshots || []).length ? data.note : "");
      setShowHistory(true);
      setShowExplain(false);
      setShowShadow(false);
      setShowInsights(false);
    } catch (e) {
      window.alert(String(e instanceof Error ? e.message : e));
    } finally {
      setToolBusy(null);
    }
  }

  async function runInsights() {
    const f = focus.trim();
    if (!f) {
      window.alert("Select focus user.");
      return;
    }
    setToolBusy("insights");
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
      setShowExplain(false);
      setShowShadow(false);
      setShowHistory(false);
    } catch (e) {
      window.alert(String(e instanceof Error ? e.message : e));
    } finally {
      setToolBusy(null);
    }
  }

  function runTool(id: IntelToolId) {
    if (id === "explain") void runExplain();
    else if (id === "history") void runHistory();
    else if (id === "insights") void runInsights();
    else if (id === "shadow") void runShadow();
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

  const computedFocusRank =
    above.length > 0 ? above[above.length - 1].rank + 1 : 1;

  return (
    <div className="grid-inner intel-page">
      <article className="card wide intel-hero">
        <h2>Explain &amp; AI</h2>
        <p className="muted small">
          Understand <strong>why</strong> someone ranks where they do, compare Newton to legacy rules,
          and chat with your allocation guide.
        </p>
        <IntelIntroFlow
          poolCount={poolCount}
          focusLabel={focusLabel}
          hasFocus={!!focus.trim()}
        />
      </article>

      <article className="card wide intel-controls">
        <div className="intel-controls-row">
          <div className="intel-focus-search">
            <UserSearchSelect
              label="Focus person"
              value={focus}
              onChange={setFocus}
              users={users}
              everyoneLabel={users.length ? "Select user…" : undefined}
              placeholder="Search name or user id…"
            />
            {focus ? (
              <span className="intel-focus-selected muted small">
                Selected: <UserLabel userId={focus} userName={focusUser?.user_name} />
              </span>
            ) : null}
          </div>
          <label className="inline stack-tight">
            <span className="muted small">Seed (match Parking tab)</span>
            <input
              className="w-short"
              type="number"
              value={seed}
              onChange={(e) => setSeed(Number(e.target.value))}
            />
          </label>
        </div>
        <IntelToolGrid
          hasFocus={!!focus.trim()}
          activePanel={activePanel}
          busy={toolBusy}
          onRun={runTool}
        />
      </article>

      {showExplain && (
        <article className="card wide intel-panel intel-panel--explain" id="box-explain">
          <div className="intel-panel-head">
            <h2>Why this rank?</h2>
            <span className="allocation-outcome-pointer win">Step A → ladder below</span>
          </div>
          <IntelExplainLadder
            focusUserId={focus}
            focusUserName={focusUser?.user_name}
            focusRank={focusDetail?.rank ?? computedFocusRank}
            above={above}
            focusDetail={focusDetail}
          />
        </article>
      )}

      {showShadow && shadow && (
        <article className="card wide intel-panel intel-panel--shadow" id="box-shadow">
          <div className="intel-panel-head">
            <h2>Shadow mode</h2>
            <span className="allocation-outcome-pointer wait">Step D → Newton vs legacy</span>
          </div>
          <IntelShadowCompare
            newton={shadow.newton || []}
            legacy={shadow.legacy_mock || []}
            diff={shadow.diff || []}
          />
          <details className="insight-raw mt">
            <summary>Full rank delta table</summary>
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
                      <td>
                        <UserLabel userId={d.user_id} userName={d.user_name} />
                      </td>
                      <td>{d.newton_rank ?? "—"}</td>
                      <td>{d.legacy_rank ?? "—"}</td>
                      <td>
                        {d.delta_newton_minus_legacy === null ||
                        d.delta_newton_minus_legacy === undefined
                          ? "—"
                          : d.delta_newton_minus_legacy}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </article>
      )}

      {showHistory && (
        <article className="card wide intel-panel intel-panel--history" id="box-history">
          <div className="intel-panel-head">
            <h2>Score &amp; tier history</h2>
            <span className="allocation-outcome-pointer win">
              Step B → <UserLabel userId={focus} userName={focusUser?.user_name} />
            </span>
          </div>
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
        <article className="card wide intel-panel intel-panel--insights" id="box-insights">
          <div className="intel-panel-head">
            <h2>Insights &amp; risk signals</h2>
            <span className="allocation-outcome-pointer win">
              Step C → signals for focus user
            </span>
          </div>
          <p className="muted small insight-intro">
            A short overall verdict plus three plain checks — no statistics degree required.
          </p>
          <InsightsPanel bundle={insightsBundle} />
        </article>
      )}

      <article className="card wide intel-llm-card">
        <IntelAiHeader aiName={aiName} poolCount={poolCount} />
        <div className="llm-chat-actions">
          <button
            type="button"
            className="secondary"
            disabled={llmBusy || llmChat.length === 0}
            onClick={clearLlmChat}
          >
            Clear conversation
          </button>
          {llmMeta ? <span className="muted small">{llmMeta}</span> : null}
        </div>
        <div className="llm-chat-panel intel-llm-panel mt">
          <div className="llm-chat" aria-live="polite">
            {llmChat.length === 0 ? (
              <div className="llm-host-welcome intel-llm-welcome">
                <div className="llm-host-avatar intel-llm-avatar" aria-hidden="true">
                  {aiName.slice(0, 1).toUpperCase()}
                </div>
                <div className="llm-host-copy">
                  <p className="llm-host-greeting">
                    Hi — I&apos;m <strong>{aiName}</strong>, your Newton 3 allocation guide.
                  </p>
                  <ul className="intel-llm-starters muted small">
                    <li>Why is my rank lower than someone on another team?</li>
                    <li>What would move me up one spot?</li>
                    <li>Press Send with an empty box for a short tour of this pool</li>
                  </ul>
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
            {llmBusy ? (
              <div className="llm-chat-meta intel-llm-thinking">
                <span className="intel-llm-dots" aria-hidden>
                  ···
                </span>{" "}
                Thinking…
              </div>
            ) : null}
            <div ref={llmEndRef} />
          </div>
          <div className="llm-follow-row mt">
            <input
              type="text"
              value={llmDraft}
              onChange={(e) => setLlmDraft(e.target.value)}
              placeholder={
                llmChat.length === 0
                  ? "Ask about ranking, fairness, or leave blank for a short tour…"
                  : "Follow-up question…"
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
              disabled={llmBusy || !idsParam() || (llmChat.length > 0 && !llmDraft.trim())}
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
