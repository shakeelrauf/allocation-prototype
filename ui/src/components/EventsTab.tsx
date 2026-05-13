import { type FormEvent, useState } from "react";
import { fetchJson } from "../api/client";
import { useData } from "../context/DataContext";

const EVENT_TYPES = [
  "booking.created",
  "booking.cancelled",
  "booking.completed",
  "gate.entry_detected",
  "offence.reported",
  "carpool.detected",
  "unused_booking",
  "free_space_used",
  "weekly_decay",
];

export function EventsTab() {
  const { API, users, reloadAll } = useData();
  const [payloadText, setPayloadText] = useState("");
  const [eventType, setEventType] = useState(EVENT_TYPES[0]);
  const [eventUser, setEventUser] = useState("");
  const [eventResult, setEventResult] = useState<{ text: string; ok: boolean } | null>(null);
  const [bulkText, setBulkText] = useState("");
  const [bulkStatus, setBulkStatus] = useState("");
  const [bulkResult, setBulkResult] = useState("");

  const defaultUser = users[0]?.user_id || "";

  async function submitEvent(e: FormEvent) {
    e.preventDefault();
    let payload: Record<string, unknown> = {};
    const raw = payloadText.trim();
    try {
      if (raw) payload = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      setEventResult({ text: "Invalid JSON in payload", ok: false });
      return;
    }
    const uid = eventUser.trim() || defaultUser;
    try {
      const res = await fetchJson(`${API}/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_type: eventType, user_id: uid, payload }),
      });
      setEventResult({ text: JSON.stringify(res, null, 2), ok: true });
      await reloadAll();
    } catch (err) {
      setEventResult({ text: String(err instanceof Error ? err.message : err), ok: false });
    }
  }

  async function runBulk() {
    const raw = bulkText.trim();
    if (!raw) {
      setBulkStatus("Paste NDJSON first.");
      return;
    }
    let events: unknown[];
    try {
      events = raw
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean)
        .map((line) => JSON.parse(line));
    } catch (e) {
      setBulkStatus("Invalid JSON: " + String(e instanceof Error ? e.message : e));
      return;
    }
    setBulkStatus(`Sending ${events.length} events…`);
    try {
      const res = await fetchJson<{ count: number }>(`${API}/events/bulk`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ events }),
      });
      setBulkStatus(`Done · ${res.count} processed`);
      setBulkResult(JSON.stringify(res, null, 2));
      await reloadAll();
    } catch (err) {
      setBulkStatus("Error");
      setBulkResult(String(err instanceof Error ? err.message : err));
    }
  }

  return (
    <div className="grid-inner">
        <article className="card">
          <h2>Send single event</h2>
          <form className="stack" onSubmit={submitEvent}>
            <label>
              Event type
              <select value={eventType} onChange={(e) => setEventType(e.target.value)}>
                {EVENT_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
            <label>
              User
              <select
                value={users.length === 0 ? "" : eventUser || defaultUser}
                onChange={(e) => setEventUser(e.target.value)}
                required
                disabled={users.length === 0}
              >
                {users.length === 0 ? (
                  <option value="">No users yet</option>
                ) : (
                  users.map((u) => (
                    <option key={u.user_id} value={u.user_id}>
                      {u.user_id} · {u.group_id}
                    </option>
                  ))
                )}
              </select>
            </label>
            <label>
              Payload JSON
              <textarea
                rows={4}
                value={payloadText}
                onChange={(e) => setPayloadText(e.target.value)}
                placeholder='{"weeks": 2}'
              />
            </label>
            <div className="preset-row">
              <span className="muted small">Presets:</span>
              <button type="button" className="secondary sm" onClick={() => setPayloadText('{"weeks":1}')}>
                weekly_decay ×1
              </button>
              <button type="button" className="secondary sm" onClick={() => setPayloadText('{"weeks":4}')}>
                weekly_decay ×4
              </button>
              <button type="button" className="secondary sm" onClick={() => setPayloadText("")}>
                clear payload
              </button>
            </div>
            <button type="submit" disabled={users.length === 0}>
              Process event
            </button>
          </form>
          {eventResult && (
            <div className={`callout mt ${eventResult.ok ? "ok" : "err"}`}>{eventResult.text}</div>
          )}
        </article>

        <article className="card wide">
          <h2>Event stream (NDJSON)</h2>
          <p className="muted small">
            One JSON object per line:
            <code>{'{"event_type":"unused_booking","user_id":"bob","payload":{}}'}</code>
          </p>
          <textarea
            className="mono"
            rows={10}
            value={bulkText}
            onChange={(e) => setBulkText(e.target.value)}
            placeholder='{"event_type":"carpool.detected","user_id":"alice","payload":{}}'
          />
          <div className="row-inline mt">
            <button
              type="button"
              onClick={() => {
                const lines = [
                  { event_type: "booking.created", user_id: "alice", payload: {} },
                  { event_type: "carpool.detected", user_id: "alice", payload: {} },
                  { event_type: "unused_booking", user_id: "bob", payload: {} },
                  { event_type: "weekly_decay", user_id: "bob", payload: { weeks: 2 } },
                  { event_type: "offence.reported", user_id: "carol", payload: {} },
                ];
                setBulkText(lines.map((x) => JSON.stringify(x)).join("\n"));
              }}
            >
              Insert sample stream
            </button>
            <button type="button" className="secondary" onClick={() => void runBulk()}>
              Run bulk (server-side)
            </button>
            <span className="muted small">{bulkStatus}</span>
          </div>
          {bulkResult && (
            <pre className="mono muted scroll-max mt">{bulkResult}</pre>
          )}
        </article>
      </div>
  );
}
