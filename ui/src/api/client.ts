const ORIGIN_BASE =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim().replace(/\/$/, "") ?? "";

/**
 * Base URL for Newton JSON API (`/api/...` same-origin, or `http://host:port/api` when standalone).
 */
export const API = ORIGIN_BASE ? `${ORIGIN_BASE}/api` : "/api";

/** Spec-style behaviour score URL (no `/api` prefix), for display or direct fetch. */
export function usersBehaviorScoreUrl(userId: string): string {
  const path = `/users/${encodeURIComponent(userId)}/behavior-score`;
  return ORIGIN_BASE ? `${ORIGIN_BASE}${path}` : path;
}

export async function fetchJson<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(url, opts);
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!res.ok) {
    let msg = text;
    if (typeof body === "object" && body !== null && "detail" in body) {
      const d = (body as { detail: unknown }).detail;
      msg = typeof d === "string" ? d : JSON.stringify(d);
    }
    throw new Error(msg || res.statusText);
  }
  return body as T;
}
