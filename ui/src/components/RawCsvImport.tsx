import { useRef, useState } from "react";
import { API, postFormJson } from "../api/client";
import { useData } from "../context/DataContext";

const ACCEPT = ".csv,.tsv,text/csv,text/tab-separated-values";
const MAX_BYTES = 15 * 1024 * 1024;
const ALLOWED_EXT = new Set([".csv", ".tsv", ".txt"]);

type ImportResult = {
  ok: boolean;
  users_in_db?: number;
  sqlite_path?: string;
  store?: string;
  migration_audit?: { users?: number; events_applied?: number };
  validation?: { valid_rows?: number; skipped_rows?: number };
};

function preflight(file: File): string | null {
  const ext = file.name.includes(".") ? `.${file.name.split(".").pop()!.toLowerCase()}` : "";
  if (!ALLOWED_EXT.has(ext)) {
    return "Please choose a .csv or .tsv file (e.g. Metabase export).";
  }
  if (file.size > MAX_BYTES) {
    return "File must be under 15 MB.";
  }
  return null;
}

type Props = {
  onImported?: () => void | Promise<void>;
};

/** Upload raw Metabase/user export CSV from the browser → SQLite (no fixture picker). */
export function RawCsvImport({ onImported }: Props) {
  const { reloadAll, health } = useData();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [success, setSuccess] = useState("");

  async function onFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    const pre = preflight(file);
    if (pre) {
      setErr(pre);
      setSuccess("");
      return;
    }

    setBusy(true);
    setErr("");
    setSuccess("");

    const form = new FormData();
    form.append("file", file, file.name);

    try {
      const res = await postFormJson<ImportResult>(`${API}/admin/import-users-csv`, form);
      await reloadAll();
      await onImported?.();
      const users = res.users_in_db ?? res.migration_audit?.users;
      const events = res.migration_audit?.events_applied;
      const db = res.sqlite_path || health?.sqlite_path;
      setSuccess(
        users != null
          ? `Imported ${users} users${events != null ? `, ${events} behaviour events` : ""} into ${
              res.store ?? "database"
            }${db ? ` (${db})` : ""}.`
          : "Import finished.",
      );
    } catch (ex) {
      setSuccess("");
      setErr(String(ex instanceof Error ? ex.message : ex));
    } finally {
      setBusy(false);
      if (inputRef.current) {
        inputRef.current.value = "";
      }
    }
  }

  return (
    <article className="card wide">
      <h2>Import Metabase CSV (one step)</h2>
      <p className="muted small">
        Pick <em>Algorithm User Complaints - Metabase.csv</em> (or the same export from Metabase).
        One upload runs validation, user import, behaviour events, and saves to{" "}
        <strong>{health?.sqlite_path ? "SQLite" : "the database"}</strong>
        {health?.sqlite_path ? (
          <>
            {" "}
            (<code className="mono">{health.sqlite_path}</code>)
          </>
        ) : null}
        . No manual scripts — same as <code>POST /api/admin/import-users-csv</code>.
      </p>
      <label className="file-upload-field stack">
        <span className="file-upload-label">
          {busy ? "Importing…" : "Select CSV file — import starts automatically"}
        </span>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          disabled={busy}
          onChange={(e) => void onFileSelected(e)}
        />
      </label>
      {success ? <p className="callout ok mt">{success}</p> : null}
      {err ? <p className="callout err mt">{err}</p> : null}
    </article>
  );
}
