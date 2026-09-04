"use client";

import { useState } from "react";
import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { AppShell } from "@/components/AppShell";

/**
 * Management is deliberately plain. It is a place you visit occasionally, so it
 * gets no visualisation, no score, and no colour — all of which belong on Pulse.
 */
export default function WatchlistsPage() {
  const { watchlists, activeId, setActiveId, refreshWatchlists, loading } = useSession();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [renaming, setRenaming] = useState<number | null>(null);
  const [draft, setDraft] = useState("");

  async function guard(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await refreshWatchlists();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  async function move(listId: number, symbols: string[], from: number, to: number) {
    if (to < 0 || to >= symbols.length) return;
    const next = [...symbols];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    await guard(() => api.reorder(listId, next));
  }

  return (
    <AppShell onChanged={refreshWatchlists}>
      <div className="mx-auto w-full max-w-[880px] px-5 pb-24 md:px-10">
        <header className="pt-10 md:pt-14">
          <h1 className="text-title font-semibold text-ink">Watchlists</h1>
          <p className="mt-3 max-w-[54ch] text-ink-2">
            Each list keeps its own visit history, so switching lists doesn't disturb what you have
            already seen elsewhere.
          </p>
        </header>

        <form
          className="mt-9 flex flex-wrap gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (!name.trim()) return;
            guard(async () => {
              await api.createWatchlist(name.trim());
              setName("");
            });
          }}
        >
          <label htmlFor="new-list" className="sr-only">
            New watchlist name
          </label>
          <input
            id="new-list"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Name a new watchlist"
            maxLength={120}
            className="min-w-0 flex-1 rounded-md border border-line bg-white/[0.03] px-4 py-2.5 text-ink placeholder:text-ink-4"
          />
          <button
            type="submit"
            disabled={busy || !name.trim()}
            className="rounded-md border border-line px-5 py-2.5 text-sm text-ink-2 transition-colors duration-200 hover:border-line-strong hover:text-ink disabled:opacity-40"
          >
            Create
          </button>
        </form>

        {error && (
          <p role="alert" className="mt-4 text-sm text-down">
            {error}
          </p>
        )}

        {loading && <p className="mt-10 text-ink-3">Loading…</p>}

        <div className="mt-12 space-y-12">
          {watchlists.map((list) => {
            const symbols = list.items.map((item) => item.symbol);
            return (
              <section key={list.id}>
                <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-line pb-3">
                  {renaming === list.id ? (
                    <form
                      className="flex gap-2"
                      onSubmit={(event) => {
                        event.preventDefault();
                        guard(async () => {
                          await api.renameWatchlist(list.id, draft);
                          setRenaming(null);
                        });
                      }}
                    >
                      <input
                        value={draft}
                        onChange={(event) => setDraft(event.target.value)}
                        aria-label={`Rename ${list.name}`}
                        className="rounded border border-line bg-white/[0.03] px-3 py-1 text-ink"
                        autoFocus
                      />
                      <button type="submit" className="text-sm text-accent">
                        Save
                      </button>
                      <button type="button" onClick={() => setRenaming(null)} className="text-sm text-ink-3">
                        Cancel
                      </button>
                    </form>
                  ) : (
                    <h2 className="text-heading font-medium text-ink">
                      {list.name}
                      {list.id === activeId && (
                        <span className="ml-3 text-micro text-accent">active</span>
                      )}
                    </h2>
                  )}

                  <div className="flex gap-4 text-sm">
                    {list.id !== activeId && (
                      <button onClick={() => setActiveId(list.id)} className="text-accent hover:opacity-75">
                        Make active
                      </button>
                    )}
                    <button
                      onClick={() => {
                        setRenaming(list.id);
                        setDraft(list.name);
                      }}
                      className="text-ink-3 hover:text-ink"
                    >
                      Rename
                    </button>
                    <button
                      onClick={() =>
                        guard(async () => {
                          await api.resetBaseline(list.id);
                        })
                      }
                      className="text-ink-3 hover:text-ink"
                      title="Treat everything from now on as new"
                    >
                      Reset baseline
                    </button>
                    <button
                      onClick={() => guard(() => api.deleteWatchlist(list.id))}
                      disabled={watchlists.length <= 1}
                      className="text-ink-3 hover:text-down disabled:opacity-30"
                      title={watchlists.length <= 1 ? "Keep at least one watchlist" : undefined}
                    >
                      Delete
                    </button>
                  </div>
                </div>

                {list.items.length === 0 ? (
                  <p className="py-6 text-ink-3">
                    Empty. Press{" "}
                    <kbd className="rounded border border-line px-1.5 py-0.5 font-mono text-[11px]">⌘K</kbd>{" "}
                    to add symbols.
                  </p>
                ) : (
                  <ul className="divide-y divide-white/[0.05]">
                    {list.items.map((item, index) => (
                      <li key={item.symbol} className="flex items-center gap-4 py-3">
                        <span className="tnum w-6 font-mono text-micro text-ink-4">{index + 1}</span>
                        <span className="w-16 font-mono text-sm text-ink">{item.symbol}</span>
                        <span className="min-w-0 flex-1 truncate text-sm text-ink-2">{item.name}</span>
                        <span className="hidden text-micro text-ink-4 sm:block">{item.sector}</span>
                        <span className="flex gap-1">
                          <button
                            onClick={() => move(list.id, symbols, index, index - 1)}
                            disabled={index === 0 || busy}
                            aria-label={`Move ${item.symbol} up`}
                            className="rounded px-1.5 py-0.5 text-ink-4 hover:text-ink disabled:opacity-20"
                          >
                            ↑
                          </button>
                          <button
                            onClick={() => move(list.id, symbols, index, index + 1)}
                            disabled={index === list.items.length - 1 || busy}
                            aria-label={`Move ${item.symbol} down`}
                            className="rounded px-1.5 py-0.5 text-ink-4 hover:text-ink disabled:opacity-20"
                          >
                            ↓
                          </button>
                        </span>
                        <button
                          onClick={() => guard(() => api.removeStock(list.id, item.symbol))}
                          aria-label={`Remove ${item.symbol}`}
                          className="text-micro text-ink-4 hover:text-down"
                        >
                          Remove
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            );
          })}
        </div>
      </div>
    </AppShell>
  );
}
