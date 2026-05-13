import { type FormEvent, useEffect, useRef, useState } from "react";
import { fetchJson } from "../../api/client";
import { useData } from "../../context/DataContext";

type Props = {
  groupOpen: boolean;
  userOpen: boolean;
  onCloseGroup: () => void;
  onCloseUser: () => void;
};

export function FormModals({ groupOpen, userOpen, onCloseGroup, onCloseUser }: Props) {
  const { API, groups, reloadAll } = useData();
  const [groupMsg, setGroupMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const [userMsg, setUserMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const [groupPriorityMeta, setGroupPriorityMeta] = useState("");
  const [hiddenGroupPrio, setHiddenGroupPrio] = useState("100");
  const groupFirstRef = useRef<HTMLInputElement>(null);
  const userFirstRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (groupOpen) {
      setGroupMsg(null);
      queueMicrotask(() => groupFirstRef.current?.focus());
    }
  }, [groupOpen]);

  useEffect(() => {
    if (userOpen) {
      setUserMsg(null);
      queueMicrotask(() => userFirstRef.current?.focus());
    }
  }, [userOpen]);

  function onUserGroupChange(gid: string) {
    const g = groups.find((x) => x.group_id === gid);
    const p = g ? String(g.group_priority) : "100";
    setHiddenGroupPrio(p);
    setGroupPriorityMeta(
      gid && g
        ? `Registered group allocation priority: ${p} (included in save request).`
        : "",
    );
  }

  async function submitGroup(e: FormEvent) {
    e.preventDefault();
    const fd = new FormData(e.target as HTMLFormElement);
    try {
      await fetchJson(`${API}/admin/groups`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          group_id: String(fd.get("group_id")).trim(),
          group_priority: Number(fd.get("group_priority")),
        }),
      });
      setGroupMsg({ text: "Group saved to registry.", ok: true });
      (e.target as HTMLFormElement).reset();
      const gp = (e.target as HTMLFormElement).elements.namedItem("group_priority") as HTMLInputElement;
      if (gp) gp.value = "1";
      await reloadAll();
    } catch (err) {
      setGroupMsg({ text: String(err instanceof Error ? err.message : err), ok: false });
    }
  }

  async function submitUser(e: FormEvent) {
    e.preventDefault();
    const fd = new FormData(e.target as HTMLFormElement);
    const gid = String(fd.get("group_id") || "").trim();
    if (!gid) {
      setUserMsg({ text: "Select a group (create one with New group first).", ok: false });
      return;
    }
    try {
      await fetchJson(`${API}/admin/users`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify([
          {
            user_id: String(fd.get("user_id")).trim(),
            group_id: gid,
            group_priority: Number(fd.get("group_priority")),
            user_priority: Number(fd.get("user_priority")),
          },
        ]),
      });
      setUserMsg({ text: "User saved.", ok: true });
      (e.target as HTMLFormElement).reset();
      const up = (e.target as HTMLFormElement).elements.namedItem("user_priority") as HTMLInputElement;
      if (up) up.value = "10";
      setHiddenGroupPrio("100");
      setGroupPriorityMeta("");
      await reloadAll();
    } catch (err) {
      setUserMsg({ text: String(err instanceof Error ? err.message : err), ok: false });
    }
  }

  return (
    <>
      <div
        className="modal-backdrop"
        hidden={!groupOpen}
        aria-hidden={!groupOpen}
        onClick={(e) => e.target === e.currentTarget && onCloseGroup()}
      >
        <div className="modal" role="dialog" onClick={(e) => e.stopPropagation()}>
          <header className="modal-head">
            <h2>Create group</h2>
            <button type="button" className="icon-btn" aria-label="Close" onClick={onCloseGroup}>
              ×
            </button>
          </header>
          <div className="modal-body">
            <p className="muted small">
              Define a team / parking pool. Lower <strong>group priority</strong> ranks earlier in allocation.
            </p>
            <form className="stack mt" onSubmit={submitGroup}>
              <label>
                Group id
                <input name="group_id" required placeholder="engineering" autoComplete="off" ref={groupFirstRef} />
              </label>
              <label>
                Group priority
                <input name="group_priority" type="number" defaultValue={1} />
              </label>
              <button type="submit">Create / update group</button>
            </form>
            {groupMsg && (
              <div className={`callout mt ${groupMsg.ok ? "ok" : "err"}`}>{groupMsg.text}</div>
            )}
          </div>
        </div>
      </div>

      <div
        className="modal-backdrop"
        hidden={!userOpen}
        aria-hidden={!userOpen}
        onClick={(e) => e.target === e.currentTarget && onCloseUser()}
      >
        <div className="modal" role="dialog" onClick={(e) => e.stopPropagation()}>
          <header className="modal-head">
            <h2>Register user</h2>
            <button type="button" className="icon-btn" aria-label="Close" onClick={onCloseUser}>
              ×
            </button>
          </header>
          <div className="modal-body">
            <p className="muted small">Pick an existing group, then set this user’s individual priority.</p>
            <form className="stack mt" onSubmit={submitUser}>
              <label>
                User id
                <input name="user_id" required placeholder="alice" autoComplete="off" ref={userFirstRef} />
              </label>
              <label>
                Group
                <select
                  name="group_id"
                  required
                  defaultValue=""
                  onChange={(e) => onUserGroupChange(e.target.value)}
                >
                  <option value="" disabled>
                    {groups.length ? "— Select group —" : "No groups — use New group first"}
                  </option>
                  {groups.map((g) => (
                    <option key={g.group_id} value={g.group_id}>
                      {g.group_id} (allocation prio {g.group_priority})
                    </option>
                  ))}
                </select>
              </label>
              <input type="hidden" name="group_priority" value={hiddenGroupPrio} />
              {groupPriorityMeta && <p className="muted small">{groupPriorityMeta}</p>}
              <label>
                User priority
                <input name="user_priority" type="number" defaultValue={10} />
              </label>
              <button type="submit">Save user</button>
            </form>
            {userMsg && <div className={`callout mt ${userMsg.ok ? "ok" : "err"}`}>{userMsg.text}</div>}
          </div>
        </div>
      </div>
    </>
  );
}
