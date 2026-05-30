import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { API, fetchJson } from "../api/client";
import { formatUserLabel } from "../utils/userDisplay";
import type {
  AllocationRunRow,
  EventRow,
  GroupRow,
  HealthResponse,
  UserRow,
} from "../types";

type Ctx = {
  API: string;
  health: HealthResponse | null;
  users: UserRow[];
  groups: GroupRow[];
  recentEvents: EventRow[];
  allocationRuns: AllocationRunRow[];
  eventsLimit: number;
  setEventsLimit: (n: number) => void;
  allocChecked: Record<string, boolean>;
  setAllocChecked: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
  loadHealth: () => Promise<void>;
  loadEvents: () => Promise<void>;
  loadAllocationRuns: () => Promise<void>;
  reloadAll: () => Promise<void>;
  resetAll: () => Promise<void>;
  getPoolUserIds: () => string[];
  formatUser: (userId: string, userName?: string | null) => string;
};

const DataContext = createContext<Ctx | null>(null);

export function DataProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [groups, setGroups] = useState<GroupRow[]>([]);
  const [recentEvents, setRecentEvents] = useState<EventRow[]>([]);
  const [allocationRuns, setAllocationRuns] = useState<AllocationRunRow[]>([]);
  const [eventsLimit, setEventsLimit] = useState(40);
  const [allocChecked, setAllocChecked] = useState<Record<string, boolean>>({});

  const loadHealth = useCallback(async () => {
    try {
      const h = await fetchJson<HealthResponse>(`${API}/health`);
      setHealth(h);
    } catch {
      setHealth(null);
    }
  }, []);

  const loadGroups = useCallback(async () => {
    try {
      const data = await fetchJson<{ groups: GroupRow[] }>(`${API}/groups`);
      setGroups(data.groups || []);
    } catch {
      setGroups([]);
    }
  }, []);

  const loadUsers = useCallback(async () => {
    const data = await fetchJson<{ users: UserRow[] }>(`${API}/users`);
    setUsers(data.users || []);
  }, []);

  const loadEvents = useCallback(async () => {
    const lim = Math.max(5, Math.min(200, eventsLimit || 40));
    const data = await fetchJson<{ events: EventRow[] }>(`${API}/events/recent?limit=${lim}`);
    setRecentEvents(data.events || []);
  }, [eventsLimit]);

  const loadAllocationRuns = useCallback(async () => {
    try {
      const data = await fetchJson<{ runs: AllocationRunRow[] }>(
        `${API}/allocations?limit=50`,
      );
      setAllocationRuns(data.runs || []);
    } catch {
      setAllocationRuns([]);
    }
  }, []);

  const reloadAll = useCallback(async () => {
    await loadHealth();
    await loadGroups();
    await loadUsers();
    await loadEvents();
    await loadAllocationRuns();
  }, [loadHealth, loadGroups, loadUsers, loadEvents, loadAllocationRuns]);

  const resetAll = useCallback(async () => {
    if (
      !window.confirm(
        "Delete ALL local data (users, groups, events, scores, saved space allocations, tenant config)? This cannot be undone.",
      )
    ) {
      return;
    }
    await fetchJson(`${API}/admin/reset`, { method: "POST" });
    await loadHealth();
    await loadGroups();
    await loadUsers();
    await loadEvents();
    await loadAllocationRuns();
  }, [loadHealth, loadGroups, loadUsers, loadEvents, loadAllocationRuns]);

  useEffect(() => {
    setAllocChecked((prev) => {
      const next = { ...prev };
      for (const u of users) {
        if (next[u.user_id] === undefined) next[u.user_id] = true;
      }
      for (const k of Object.keys(next)) {
        if (!users.some((u) => u.user_id === k)) delete next[k];
      }
      return next;
    });
  }, [users]);

  const getPoolUserIds = useCallback(() => {
    const selected = users.filter((u) => allocChecked[u.user_id]).map((u) => u.user_id);
    return selected.length ? selected : users.map((u) => u.user_id);
  }, [users, allocChecked]);

  const userNameById = useMemo(() => {
    const m = new Map<string, string>();
    for (const u of users) {
      if (u.user_name?.trim()) m.set(u.user_id, u.user_name.trim());
    }
    return m;
  }, [users]);

  const formatUser = useCallback(
    (userId: string, userName?: string | null) =>
      formatUserLabel(userId, userName ?? userNameById.get(userId)),
    [userNameById],
  );

  const value = useMemo(
    () =>
      ({
        API,
        health,
        users,
        groups,
        recentEvents,
        allocationRuns,
        eventsLimit,
        setEventsLimit,
        allocChecked,
        setAllocChecked,
        loadHealth,
        loadEvents,
        loadAllocationRuns,
        reloadAll,
        resetAll,
        getPoolUserIds,
        formatUser,
      }) satisfies Ctx,
    [
      health,
      users,
      groups,
      recentEvents,
      allocationRuns,
      eventsLimit,
      allocChecked,
      loadHealth,
      loadEvents,
      loadAllocationRuns,
      reloadAll,
      resetAll,
      getPoolUserIds,
      formatUser,
    ],
  );

  return <DataContext.Provider value={value}>{children}</DataContext.Provider>;
}

export function useData() {
  const c = useContext(DataContext);
  if (!c) throw new Error("useData outside DataProvider");
  return c;
}
