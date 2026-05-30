import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { API, fetchJson, usersBehaviorScoreUrl } from "../api/client";
import { formatUserLabel } from "../utils/userDisplay";

type ScorePayload = {
  user_id: string;
  user_name?: string;
  group_id: string;
  score: number;
  tier: string;
  reward_total_rolling: number;
  last_penalty_at: string | null;
  updated_at: string;
};

export function UserScorePage() {
  const { userId = "" } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [data, setData] = useState<ScorePayload | null>(null);

  useEffect(() => {
    if (!userId) return;
    let cancelled = false;
    setLoading(true);
    setErr(null);
    setData(null);
    fetchJson<ScorePayload>(`${API}/users/${encodeURIComponent(userId)}/behavior-score`)
      .then((j) => {
        if (!cancelled) setData(j);
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e instanceof Error ? e.message : e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [userId]);

  const specUrl = usersBehaviorScoreUrl(userId);

  return (
    <div className="grid-inner">
      <article className="card wide">
        <div className="row">
          <h2>Behaviour · {data ? formatUserLabel(data.user_id, data.user_name) : userId}</h2>
          <div className="row-inline">
            <button type="button" className="secondary sm" onClick={() => navigate(-1)}>
              Back
            </button>
            <Link to="/dashboard" className="muted small">
              Dashboard
            </Link>
          </div>
        </div>
        <div className="modal-body" style={{ padding: 0 }}>
          {loading && <p className="muted">Loading…</p>}
          {err && <p className="callout err">{err}</p>}
          {data && (
            <dl>
              <dt>Score</dt>
              <dd>{Number(data.score).toFixed(2)}</dd>
              <dt>Tier</dt>
              <dd>{data.tier}</dd>
              <dt>Group</dt>
              <dd>{data.group_id}</dd>
              <dt>Reward rolling (28d)</dt>
              <dd>{Number(data.reward_total_rolling).toFixed(2)}</dd>
              <dt>Last penalty</dt>
              <dd>{data.last_penalty_at || "—"}</dd>
              <dt>Updated</dt>
              <dd>{data.updated_at}</dd>
            </dl>
          )}
        </div>
        <footer className="modal-foot muted small">
          REST: <code>{`${API}/users/${userId}/behavior-score`}</code>
          <br />
          Spec: <code>{specUrl}</code>
        </footer>
      </article>
    </div>
  );
}
