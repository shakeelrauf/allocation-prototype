/** Display user_id with optional complaint-cohort name. */

export function formatUserLabel(userId: string, userName?: string | null): string {
  const id = (userId || "").trim();
  const name = (userName || "").trim();
  if (!id) return name || "—";
  if (name && name !== id) return `${name} (${id})`;
  return id;
}

/** Option text for native select: name first, then id and tier. */
export function formatSelectUserOption(
  userId: string,
  userName?: string | null,
  tier?: string | null,
): string {
  const id = (userId || "").trim();
  const name = (userName || "").trim();
  const tierPart = tier ? ` · ${tier}` : "";
  if (name && name !== id) return `${name} — ${id}${tierPart}`;
  return `${id}${tierPart}`;
}

type UserLabelProps = {
  userId: string;
  userName?: string | null;
  className?: string;
};

export function UserLabel({ userId, userName, className }: UserLabelProps) {
  const id = (userId || "").trim();
  const name = (userName || "").trim();
  if (!name || name === id) {
    return <span className={className ?? "mono"}>{id || "—"}</span>;
  }
  return (
    <span className={className}>
      {name} <span className="muted small mono">({id})</span>
    </span>
  );
}
