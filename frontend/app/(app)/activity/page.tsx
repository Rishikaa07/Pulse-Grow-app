"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { clockTime, moveClass, pct, since } from "@/lib/format";
import type { ChangeEvent } from "@/lib/types";
import { AppShell } from "@/components/AppShell";

type Filter = "new" | "reviewed" | "all";

/**
 * The attention inbox.
 *
 * A change you have acknowledged stops competing for your attention. That is
 * the whole feature: without it, the same move greets you every time you open
 * the page, and the product becomes the noise it was built to remove.
 */
export default function ActivityPage() {
  const { activeId } = useSession();
  const [filter, setFilter] = useState<Filter>("new");
  const [events, setEvents] = useState<ChangeEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!activeId) return;
    try {
      setEvents(await api.changes(activeId, filter === "all" ? undefined : filter));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load your inbox.");
    }
  }, [activeId, filter]);

  useEffect(() => {
    setEvents(null);
    load();
  }, [load]);

  async function setStatus(event: ChangeEvent, status: "reviewed" | "dismissed" | "new") {
    await api.review(event.id, status).catch(() => undefined);
    load();
  }

  return (
    <AppShell onChanged={load}>
      <div className="mx-auto w-full max-w-[880px] px-5 pb-24 md:px-10">
        <header className="pt-10 md:pt-14">
          <h1 className="text-title font-semibold text-ink">Activity</h1>
          <p className="mt-3 max-w-[54ch] text-ink-2">
            Every change the engine judged worth surfacing, and what you did about it.
          </p>
        </header>

        <div className="mt-8 flex gap-1 rounded-md border border-line p-0.5" role="group" aria-label="Filter">
          {(["new", "reviewed", "all"] as Filter[]).map((option) => (
            <button
              key={option}
              onClick={() => setFilter(option)}
              aria-pressed={filter === option}
              className={`rounded px-4 py-1.5 text-sm capitalize transition-colors duration-200 ${
                filter === option ? "bg-white/[0.07] text-ink" : "text-ink-3 hover:text-ink"
              }`}
            >
              {option}
            </button>
          ))}
        </div>

        {error && <p role="alert" className="mt-6 text-sm text-down">{error}</p>}
        {!events && !error && <div className="skeleton mt-10 h-24 w-full rounded" />}

        {events && events.length === 0 && (
          <p className="mt-16 text-center text-ink-3">
            {filter === "new"
              ? "Nothing unreviewed. You're all caught up."
              : "Nothing here yet."}
          </p>
        )}

        <ul className="mt-8 divide-y divide-white/[0.05]">
          {(events ?? []).map((event) => {
            const move = Number(event.metrics.changeSinceVisitPct ?? 0);
            return (
              <li key={event.id} className="py-6">
                <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                  <span className="font-mono text-lg text-ink">{event.symbol}</span>
                  <span className={`tnum font-mono ${moveClass(move)}`}>{pct(move)}</span>
                  <span className="text-sm text-ink-4">
                    {clockTime(event.detectedAt)} · {since(event.detectedAt)} ago
                  </span>
                  <span className="tnum ml-auto font-mono text-sm text-ink-2">
                    {event.attentionScore}
                  </span>
                </div>
                <p className="mt-2 max-w-[64ch] leading-relaxed text-ink-2">{event.explanation}</p>
                <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-micro text-ink-4">
                  <span>{event.severity} severity</span>
                  <span>{event.confidence} confidence</span>
                  <span className="capitalize">{event.status}</span>
                  {event.status === "new" ? (
                    <>
                      <button onClick={() => setStatus(event, "reviewed")} className="text-accent hover:opacity-75">
                        Mark reviewed
                      </button>
                      <button onClick={() => setStatus(event, "dismissed")} className="hover:text-ink">
                        Dismiss
                      </button>
                    </>
                  ) : (
                    <button onClick={() => setStatus(event, "new")} className="hover:text-ink">
                      Move back to new
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </AppShell>
  );
}
