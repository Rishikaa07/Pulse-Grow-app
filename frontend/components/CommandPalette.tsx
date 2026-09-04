"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { SearchResult } from "@/lib/types";

/**
 * Cmd/Ctrl-K search. CRUD lives here rather than in the main view: adding a
 * symbol is a two-second errand, not a screen.
 */
export function CommandPalette({
  open,
  onClose,
  onChanged,
}: {
  open: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { activeId, watchlists, refreshWatchlists } = useSession();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [cursor, setCursor] = useState(0);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const active = watchlists.find((list) => list.id === activeId);
  const owned = new Set(active?.items.map((item) => item.symbol) ?? []);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setStatus(null);
    setCursor(0);
    const id = window.setTimeout(() => inputRef.current?.focus(), 10);
    return () => window.clearTimeout(id);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    // Debounced: one request per pause, not one per keystroke.
    const timer = window.setTimeout(async () => {
      try {
        const found = await api.search(query);
        if (!cancelled) {
          setResults(found);
          setCursor(0);
        }
      } catch {
        if (!cancelled) setResults([]);
      }
    }, 140);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, open]);

  async function add(result: SearchResult) {
    if (!activeId || busy) return;
    setBusy(true);
    try {
      await api.addStock(activeId, result.symbol);
      await refreshWatchlists();
      onChanged();
      setStatus(`Added ${result.symbol} to ${active?.name ?? "your list"}`);
    } catch (error) {
      setStatus(error instanceof ApiError ? error.message : "Couldn't add that symbol.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(result: SearchResult) {
    if (!activeId || busy) return;
    setBusy(true);
    try {
      await api.removeStock(activeId, result.symbol);
      await refreshWatchlists();
      onChanged();
      setStatus(`Removed ${result.symbol}`);
    } catch (error) {
      setStatus(error instanceof ApiError ? error.message : "Couldn't remove that symbol.");
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-void/70 px-4 pt-[12vh] backdrop-blur-sm animate-fade-in"
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search symbols"
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-xl overflow-hidden rounded-lg border border-line-strong bg-surface shadow-2xl"
      >
        <div className="flex items-center gap-3 border-b border-line px-4">
          <span className="text-ink-4" aria-hidden>
            ›
          </span>
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") onClose();
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setCursor((c) => Math.min(c + 1, results.length - 1));
              }
              if (event.key === "ArrowUp") {
                event.preventDefault();
                setCursor((c) => Math.max(c - 1, 0));
              }
              if (event.key === "Enter" && results[cursor]) {
                const result = results[cursor];
                owned.has(result.symbol) ? remove(result) : add(result);
              }
            }}
            placeholder="Add NVIDIA, search semiconductors…"
            aria-label="Search symbols"
            className="w-full bg-transparent py-4 text-[15px] text-ink outline-none placeholder:text-ink-4"
          />
        </div>

        <ul className="max-h-80 overflow-y-auto scrollbar-thin py-1" role="listbox">
          {results.map((result, index) => {
            const already = owned.has(result.symbol);
            return (
              <li key={result.symbol} role="option" aria-selected={index === cursor}>
                <button
                  onMouseEnter={() => setCursor(index)}
                  onClick={() => (already ? remove(result) : add(result))}
                  disabled={busy}
                  className={`flex w-full items-center gap-4 px-4 py-2.5 text-left transition-colors duration-150 ${
                    index === cursor ? "bg-white/[0.045]" : ""
                  }`}
                >
                  <span className="tnum w-16 font-mono text-sm text-ink">{result.symbol}</span>
                  <span className="min-w-0 flex-1 truncate text-sm text-ink-2">{result.name}</span>
                  <span className="hidden text-micro text-ink-4 sm:block">{result.sectorLabel}</span>
                  <span className={`text-micro ${already ? "text-ink-4" : "text-accent"}`}>
                    {already ? "Remove" : "Add"}
                  </span>
                </button>
              </li>
            );
          })}
          {!results.length && (
            <li className="px-4 py-6 text-sm text-ink-3">
              No symbol matches “{query}”. Pulse tracks a fixed demo universe of 24 names.
            </li>
          )}
        </ul>

        <p aria-live="polite" className="border-t border-line px-4 py-2.5 text-micro text-ink-4">
          {status ?? "↑↓ to move · Enter to add or remove · Esc to close"}
        </p>
      </div>
    </div>
  );
}
