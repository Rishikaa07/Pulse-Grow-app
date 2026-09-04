"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, api } from "./api";
import type { User, Watchlist } from "./types";

/** Which list you were last looking at is a UI preference, so it may live here. */
const LAST_LIST_KEY = "pulse.lastWatchlistId";

interface SessionValue {
  user: User | null;
  watchlists: Watchlist[];
  activeId: number | null;
  loading: boolean;
  setActiveId: (id: number) => void;
  refreshWatchlists: () => Promise<Watchlist[]>;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [activeId, setActive] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshWatchlists = useCallback(async () => {
    const lists = await api.watchlists();
    setWatchlists(lists);
    setActive((current) => {
      if (current && lists.some((l) => l.id === current)) return current;
      const stored = Number(window.localStorage.getItem(LAST_LIST_KEY));
      if (stored && lists.some((l) => l.id === stored)) return stored;
      return lists[0]?.id ?? null;
    });
    return lists;
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await api.me();
        if (cancelled) return;
        setUser(me);
        await refreshWatchlists();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) router.replace("/");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshWatchlists, router]);

  const setActiveId = useCallback((id: number) => {
    setActive(id);
    window.localStorage.setItem(LAST_LIST_KEY, String(id));
  }, []);

  const signOut = useCallback(async () => {
    await api.logout().catch(() => undefined);
    setUser(null);
    router.replace("/");
  }, [router]);

  const value = useMemo(
    () => ({ user, watchlists, activeId, loading, setActiveId, refreshWatchlists, signOut }),
    [user, watchlists, activeId, loading, setActiveId, refreshWatchlists, signOut],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside SessionProvider");
  return context;
}
