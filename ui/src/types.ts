export type UserRow = {
  user_id: string;
  group_id: string;
  group_priority: number;
  user_priority: number;
  score: number;
  tier: string;
  last_penalty_at: string | null;
  reward_total_rolling: number;
  updated_at: string;
};

export type GroupRow = { group_id: string; group_priority: number };

export type EventRow = {
  event_type: string;
  user_id: string;
  payload: Record<string, unknown>;
  timestamp: string | null;
};

export type HealthResponse = {
  status: string;
  store: string;
  /** Absolute path when backend uses SqliteStore (check persisted data here). */
  sqlite_path?: string;
  features: Record<string, boolean | string | undefined> & {
    llm_backend?: string;
    llm_auto_ollama?: boolean;
    llm_explain_env?: boolean;
    llm_character?: string;
  };
};

export type AllocationRunRow = {
  id: number;
  created_at: string;
  seed: number | null;
  capacity: number;
  pool_user_ids: string[];
  winners: {
    rank: number;
    user_id: string;
    explain: string;
    behavior_score: number;
    tier: string;
  }[];
};

export type FairnessRow = {
  user_id: string;
  user_name: string;
  company_name: string;
  office_name: string;
  group_name: string;
  guaranteed_team: string;
  team_daily_priority: number;
  individual_priority: number;
  has_assigned_space: string;
  requests_3mo: number;
  bookings_3mo: number;
  rejected_3mo: number;
  unused_bookings_3mo: number;
  nudge_offences_3mo: number;
  approval_rate_pct: number;
  rejection_rate_pct: number;
  used_rate_pct: number;
  score: number;
  tier: string;
};

export type FairnessReportResponse = {
  summary: {
    window_days: number;
    users: number;
    high_risk_users: number;
    avg_rejection_rate_pct: number;
  };
  rows: FairnessRow[];
};
