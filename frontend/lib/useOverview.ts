"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Overview } from "./types";

const POLL_MS = 30_000;

/**
 * Polls the overview.
 *
 * Two rules that matter more than they look:
 *  - a failed refresh never clears the data on screen; it raises a banner and
 *    keeps the last good view, because a blank page is worse than a stale one.
 *  - polling pauses while the tab is hidden, so a forgotten tab does not keep a
 *    connection warm for hours.
 */
export function useOverview(watchlistId: number | null) {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const requestId = useRef(0);

  const load = useCallback(
    async (quiet = false) => {
      if (!watchlistId) return;
      const id = ++requestId.current;
      if (quiet) setRefreshing(true);
      try {
        const next = await api.overview(watchlistId);
        // Drop responses that arrived out of order after a list switch.
        if (id !== requestId.current) return;
        setData(next);
        setError(null);
      } catch (err) {
        if (id !== requestId.current) return;
        setError(err instanceof Error ? err.message : "Something went wrong.");
      } finally {
        if (id === requestId.current) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [watchlistId],
  );

  useEffect(() => {
    setLoading(true);
    setData(null);
    load();
  }, [load]);

  useEffect(() => {
    if (!watchlistId) return;
    let timer: ReturnType<typeof setInterval> | null = null;

    const start = () => {
      if (timer) return;
      timer = setInterval(() => load(true), POLL_MS);
    };
    const stop = () => {
      if (timer) clearInterval(timer);
      timer = null;
    };
    const onVisibility = () => {
      if (document.hidden) stop();
      else {
        load(true);
        start();
      }
    };

    if (!document.hidden) start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [load, watchlistId]);

  return { data, error, loading, refreshing, reload: load };
}
