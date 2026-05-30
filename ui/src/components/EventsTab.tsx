import { type FormEvent, useCallback, useEffect, useState } from "react";
import { API, fetchJson } from "../api/client";
import { useData } from "../context/DataContext";
import type { EventRow } from "../types";
import { UserSearchSelect } from "./UserSearchSelect";
import { ScoreDeltaBadge } from "../utils/scoreDelta";
import { UserLabel } from "../utils/userDisplay";

type EventLogResponse = {
  applied?: boolean;
  detail?: string;
  score_before?: number;
  score_after?: number;
  score_delta?: number;
  tier_before?: string;
  tier_after?: string;
};

const EVENT_LABELS: Record<string, string> = {
  "booking.created": "Booking created",
  "booking.cancelled": "Booking cancelled",
  "booking.completed": "Booking completed",
  "gate.entry_detected": "Gate entry",
  "offence.reported": "Offence / nudge",
  "carpool.detected": "Carpool",
  unused_booking: "Unused booking",
  free_space_used: "Free space used",
  weekly_decay: "Weekly decay",
};

const EVENT_TYPES = Object.keys(EVENT_LABELS);

function eventLabel(type: string): string {
  return EVENT_LABELS[type] || type;
}

function formatWhen(ts: string | null | undefined): string {
  if (!ts) return "—";
  return ts.replace("T", " ").slice(0, 19);
}

export function EventsTab() {
  const { users, reloadAll, formatUser } = useData();
  const [selectedUserId, setSelectedUserId] = useState("");
  const [events, setEvents] = useState<EventRow[]>([]);
  const [eventsBusy, setEventsBusy] = useState(false);
  const [eventsNote, setEventsNote] = useState("");

  const [showLogForm, setShowLogForm] = useState(true);
  const [eventType, setEventType] = useState("unused_booking");
  const [logMsg, setLogMsg] = useState("");
  const [logOk, setLogOk] = useState<boolean | null>(null);
  const [lastLogDelta, setLastLogDelta] = useState<EventLogResponse | null>(null);

  const loadEvents = useCallback(async () => {
    setEventsBusy(true);
    setEventsNote("");
    try {
      const params = new URLSearchParams({ limit: "80" });
      if (selectedUserId) params.set("user_id", selectedUserId);
      const data = await fetchJson<{ events: EventRow[] }>(
        `${API}/events/recent?${params.toString()}`,
      );
      setEvents(data.events || []);
      if (!data.events?.length) {
        setEventsNote(
          selectedUserId
            ? "No events for this user yet — log one above."
            : "No events yet — import users or log an event.",
        );
      }
    } catch (e) {
      setEvents([]);
      setEventsNote(String(e instanceof Error ? e.message : e));
    } finally {
      setEventsBusy(false);
    }
  }, [selectedUserId]);

  useEffect(() => {
    void loadEvents();
  }, [loadEvents]);

  function onUserSelectChange(uid: string) {
    setSelectedUserId(uid);
    setLogMsg("");
    setLogOk(null);
    setLastLogDelta(null);
  }

  async function submitEvent(e: FormEvent) {
    e.preventDefault();
    const uid = selectedUserId || users[0]?.user_id;
    if (!uid) {
      setLogMsg("Import users first, then pick someone in Find a user.");
      setLogOk(false);
      return;
    }
    try {
      const res = await fetchJson<EventLogResponse>(`${API}/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_type: eventType, user_id: uid, payload: {} }),
      });
      setLogMsg(`Logged «${eventLabel(eventType)}» for ${formatUser(uid)}.`);
      setLogOk(true);
      setLastLogDelta(res);
      await reloadAll();
      await loadEvents();
    } catch (err) {
      setLogMsg(String(err instanceof Error ? err.message : err));
      setLogOk(false);
      setLastLogDelta(null);
    }
  }

  const filterLabel = selectedUserId
    ? formatUser(selectedUserId, users.find((u) => u.user_id === selectedUserId)?.user_name)
    : "Everyone";

  const logTargetId = selectedUserId || users[0]?.user_id || "";

  return (
    <div className="grid-inner events-page">
      <article className="card wide events-hero">
        <h2>Behaviour events</h2>
        <p className="muted small">
          Pick a user from the list to filter the timeline, or choose <strong>Everyone</strong>. Log
          new events at the top — newest first below.
        </p>
      </article>

      <article className="card wide events-log-card">
        <button
          type="button"
          className="events-log-toggle"
          onClick={() => setShowLogForm((v) => !v)}
          aria-expanded={showLogForm}
        >
          {showLogForm ? "Hide" : "Log a new event"} →
        </button>
        {showLogForm ? (
          <form className="events-log-form stack" onSubmit={submitEvent}>
            <UserSearchSelect
              label="Find a user"
              value={selectedUserId}
              onChange={onUserSelectChange}
              users={users}
              everyoneLabel="Everyone — all recent events"
              hint="Type a name or user id, then pick from the list."
            />

            <div className="events-type-picker" role="group" aria-label="What happened?">
              <span className="muted small events-type-picker-label">What happened?</span>
              <div className="events-type-buttons">
                {EVENT_TYPES.map((t) => (
                  <button
                    key={t}
                    type="button"
                    className={`events-type-btn${eventType === t ? " events-type-btn--active" : ""}`}
                    aria-pressed={eventType === t}
                    onClick={() => setEventType(t)}
                  >
                    {eventLabel(t)}
                  </button>
                ))}
              </div>
            </div>

            <p className="muted small">
              {selectedUserId ? (
                <>
                  Saving event for{" "}
                  <UserLabel
                    userId={selectedUserId}
                    userName={users.find((u) => u.user_id === selectedUserId)?.user_name}
                  />
                </>
              ) : (
                <>Pick a specific user above to log an event for them (not Everyone).</>
              )}
            </p>

            <button type="submit" disabled={users.length === 0 || !logTargetId || !selectedUserId}>
              Save event
            </button>
            {logMsg ? (
              <div className={`callout small ${logOk ? "ok" : "err"}`}>
                <p className="events-log-msg">{logMsg}</p>
                {logOk && lastLogDelta ? (
                  <ScoreDeltaBadge
                    delta={lastLogDelta.score_delta}
                    scoreBefore={lastLogDelta.score_before}
                    scoreAfter={lastLogDelta.score_after}
                    tierAfter={lastLogDelta.tier_after}
                  />
                ) : null}
              </div>
            ) : null}
          </form>
        ) : null}
      </article>

      <article className="card wide">
        <div className="events-timeline-head">
          <h2 className="events-section-title">Timeline</h2>
          <button
            type="button"
            className="secondary sm"
            disabled={eventsBusy}
            onClick={() => void loadEvents()}
          >
            {eventsBusy ? "Loading…" : "Refresh"}
          </button>
        </div>
        <p className="muted small events-filter-line">
          Showing events for: <strong>{filterLabel}</strong>
          {events.length > 0 ? ` · ${events.length} recent` : ""}
        </p>
        {eventsNote && events.length === 0 ? <p className="muted">{eventsNote}</p> : null}
        {events.length > 0 ? (
          <ul className="events-timeline">
            {events.map((ev, i) => (
              <li key={`${ev.timestamp}-${ev.user_id}-${i}`} className="events-timeline-item">
                <div className="events-timeline-main">
                  <span className="events-timeline-when">{formatWhen(ev.timestamp)}</span>
                  <span className="badge">{eventLabel(ev.event_type)}</span>
                  <UserLabel userId={ev.user_id} userName={ev.user_name} />
                </div>
                {ev.score_delta != null || ev.score_after != null ? (
                  <ScoreDeltaBadge
                    delta={ev.score_delta}
                    scoreBefore={ev.score_before}
                    scoreAfter={ev.score_after}
                    tierAfter={ev.tier_after}
                    compact
                  />
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}
      </article>
    </div>
  );
}
