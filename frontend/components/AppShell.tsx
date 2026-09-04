"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useSession } from "@/lib/session";
import { since } from "@/lib/format";
import type { Freshness } from "@/lib/types";
import { CommandPalette } from "./CommandPalette";

const NAV = [
  { href: "/pulse", label: "Pulse", icon: PulseIcon },
  { href: "/watchlists", label: "Watchlists", icon: ListIcon },
  { href: "/activity", label: "Activity", icon: InboxIcon },
  { href: "/settings", label: "Settings", icon: GearIcon },
] as const;

export function AppShell({
  children,
  freshness,
  lastCheckedIso,
  onChanged,
}: {
  children: React.ReactNode;
  freshness?: Freshness;
  lastCheckedIso?: string | null;
  onChanged?: () => void;
}) {
  const pathname = usePathname();
  const { user, watchlists, activeId, setActiveId, signOut } = useSession();
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="flex min-h-dvh flex-col md:flex-row">
      {/* Rail: icons on desktop, a bottom bar on phones. */}
      <nav
        aria-label="Primary"
        className="order-2 flex shrink-0 items-center justify-around border-t border-line bg-void/85 px-2 py-2 backdrop-blur md:order-1 md:h-dvh md:w-[68px] md:flex-col md:justify-start md:gap-1 md:border-r md:border-t-0 md:py-5 md:sticky md:top-0"
      >
        <span className="hidden md:mb-6 md:block" aria-hidden>
          <span className="mx-auto block h-2 w-2 rounded-full bg-accent" />
        </span>
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={`group flex flex-1 flex-col items-center gap-1 rounded-md px-3 py-2 text-micro transition-colors duration-200 md:flex-none md:w-[52px] ${
                active ? "text-accent" : "text-ink-3 hover:text-ink"
              }`}
            >
              <Icon />
              <span className="md:sr-only">{label}</span>
              <span className="sr-only md:not-sr-only md:hidden">{label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="order-1 flex min-w-0 flex-1 flex-col md:order-2">
        <header className="sticky top-0 z-30 flex flex-wrap items-center gap-x-5 gap-y-3 border-b border-line bg-void/80 px-5 py-3 backdrop-blur-xl md:px-8">
          <WatchlistSwitcher
            watchlists={watchlists}
            activeId={activeId}
            onSelect={(id) => {
              setActiveId(id);
              onChanged?.();
            }}
          />

          <button
            onClick={() => setPaletteOpen(true)}
            className="flex flex-1 items-center gap-2.5 rounded-md border border-line px-3 py-1.5 text-left text-sm text-ink-3 transition-colors duration-200 hover:border-line-strong hover:text-ink-2 sm:max-w-xs"
          >
            <SearchIcon />
            <span className="flex-1">Search or add a symbol</span>
            <kbd className="hidden rounded border border-line px-1.5 py-0.5 font-mono text-[10px] text-ink-4 sm:block">
              ⌘K
            </kbd>
          </button>

          <div className="ml-auto flex items-center gap-5">
            {freshness && <MarketStatus freshness={freshness} />}
            {lastCheckedIso && (
              <p className="hidden text-sm text-ink-3 lg:block">
                Checked {since(lastCheckedIso)} ago
              </p>
            )}
            <UserMenu name={user?.displayName ?? "…"} onSignOut={signOut} />
          </div>
        </header>

        <main id="main" className="min-w-0 flex-1">
          {children}
        </main>
      </div>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onChanged={() => onChanged?.()}
      />
    </div>
  );
}

function WatchlistSwitcher({
  watchlists,
  activeId,
  onSelect,
}: {
  watchlists: { id: number; name: string; itemCount: number }[];
  activeId: number | null;
  onSelect: (id: number) => void;
}) {
  if (!watchlists.length) return <span className="text-sm text-ink-3">No watchlists</span>;
  return (
    <div className="flex items-center gap-2">
      <label htmlFor="watchlist-switcher" className="sr-only">
        Active watchlist
      </label>
      <select
        id="watchlist-switcher"
        value={activeId ?? ""}
        onChange={(event) => onSelect(Number(event.target.value))}
        className="max-w-[10rem] cursor-pointer truncate rounded-md border border-line bg-transparent py-1.5 pl-2.5 pr-7 text-sm text-ink transition-colors duration-200 hover:border-line-strong"
      >
        {watchlists.map((list) => (
          <option key={list.id} value={list.id} className="bg-surface">
            {list.name} · {list.itemCount}
          </option>
        ))}
      </select>
    </div>
  );
}

const STATUS_COPY: Record<Freshness, { label: string; className: string; glyph: string }> = {
  fresh: { label: "Live", className: "text-up", glyph: "●" },
  delayed: { label: "Delayed", className: "text-accent", glyph: "◐" },
  stale: { label: "Stale data", className: "text-down", glyph: "◍" },
  unavailable: { label: "Feed down", className: "text-down", glyph: "○" },
};

export function MarketStatus({ freshness }: { freshness: Freshness }) {
  const status = STATUS_COPY[freshness];
  return (
    <p className={`flex items-center gap-2 text-sm ${status.className}`}>
      <span aria-hidden className="text-[10px]">
        {status.glyph}
      </span>
      {status.label}
    </p>
  );
}

function UserMenu({ name, onSignOut }: { name: string; onSignOut: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex h-7 w-7 items-center justify-center rounded-full border border-line text-xs text-ink-2 transition-colors duration-200 hover:border-line-strong hover:text-ink"
      >
        {name.slice(0, 1).toUpperCase()}
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-9 z-40 w-44 rounded-md border border-line bg-surface p-1 shadow-2xl"
        >
          <p className="truncate px-3 py-2 text-sm text-ink-3">{name}</p>
          <button
            role="menuitem"
            onClick={onSignOut}
            className="w-full rounded px-3 py-2 text-left text-sm text-ink-2 hover:bg-white/5 hover:text-ink"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

/* Hand-rolled icons: four small paths beat a 30 kB icon dependency. */
const iconProps = {
  width: 17,
  height: 17,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

function PulseIcon() {
  return (
    <svg {...iconProps}>
      <path d="M2 12h4l3-8 5 16 3-8h5" />
    </svg>
  );
}
function ListIcon() {
  return (
    <svg {...iconProps}>
      <path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01" />
    </svg>
  );
}
function InboxIcon() {
  return (
    <svg {...iconProps}>
      <path d="M3 13h5l1.5 3h5L16 13h5" />
      <path d="M5.5 5h13l2.5 8v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5z" />
    </svg>
  );
}
function GearIcon() {
  return (
    <svg {...iconProps}>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1L7 17M17 7l2.1-2.1" />
    </svg>
  );
}
function SearchIcon() {
  return (
    <svg {...iconProps} width={15} height={15}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.6-3.6" />
    </svg>
  );
}
