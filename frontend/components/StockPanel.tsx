"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { clockTime, compactNumber, moveClass, pct, price, since } from "@/lib/format";
import type { AttentionItem, StockDetail } from "@/lib/types";
import { useCountUp } from "./Indicators";

const SIGNAL_LABEL: Record<string, string> = {
  PRICE_MOVE: "Price movement",
  VOLUME_ANOMALY: "Volume",
  SECTOR_OUTPERFORMANCE: "Versus sector",
  MARKET_OUTPERFORMANCE: "Versus market",
  HISTORICAL_UNUSUALNESS: "Versus its own history",
  EVENT: "Event",
  MISSED_WHILE_AWAY: "Missed while away",
};

/**
 * The detail view is a panel, not a page: you open it to answer one question
 * and close it. Everything expensive (history, events, day range) is fetched
 * only when the panel opens.
 */
export function StockPanel({
  item,
  onClose,
  onReview,
}: {
  item: AttentionItem | null;
  onClose: () => void;
  onReview: (item: AttentionItem) => void;
}) {
  const [detail, setDetail] = useState<StockDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const score = useCountUp(item?.attentionScore ?? 0);

  useEffect(() => {
    if (!item) return;
    setDetail(null);
    setError(null);
    let cancelled = false;
    api
      .stock(item.symbol)
      .then((data) => !cancelled && setDetail(data))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Unavailable"));
    return () => {
      cancelled = true;
    };
  }, [item]);

  useEffect(() => {
    if (!item) return;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [item, onClose]);

  if (!item) return null;

  const material = item.signals.filter((signal) => signal.contribution >= 1);
  const move = item.changes.sinceVisitPct;

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end bg-void/60 backdrop-blur-sm animate-fade-in"
      onClick={onClose}
      role="presentation"
    >
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`${item.symbol} details`}
        onClick={(event) => event.stopPropagation()}
        className="flex h-full w-full max-w-[560px] flex-col overflow-y-auto scrollbar-thin border-l border-line bg-surface animate-panel-in"
      >
        <header className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-line bg-surface/95 px-7 py-5 backdrop-blur">
          <div>
            <p className="font-mono text-2xl tracking-tight text-ink">{item.symbol}</p>
            <p className="mt-1 text-sm text-ink-3">{item.name}</p>
          </div>
          <button
            ref={closeRef}
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1.5 text-ink-3 transition-colors duration-200 hover:text-ink"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.6" aria-hidden>
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </header>

        <div className="px-7 pb-10">
          <div className="flex flex-wrap items-end justify-between gap-6 pt-7">
            <div>
              <p className="tnum font-mono text-4xl text-ink">${price(item.price)}</p>
              <p className={`tnum mt-2 font-mono text-lg ${moveClass(move)}`}>
                {pct(move)} <span className="text-sm text-ink-4">since your last visit</span>
              </p>
            </div>
            <div className="text-right">
              <p className="tnum font-mono text-4xl text-ink">{score}</p>
              <p className="mt-1 text-micro text-ink-4">Attention · {item.confidence.level} confidence</p>
            </div>
          </div>

          <Section title="Why this matters">
            <ul className="space-y-3.5">
              {material.map((signal) => (
                <li key={signal.type} className="flex gap-4">
                  <span aria-hidden className="mt-[3px] text-accent">
                    ✓
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[15px] leading-snug text-ink-2">{signal.detail}</p>
                    <p className="mt-1 flex items-center gap-2 text-micro text-ink-4">
                      <span>{SIGNAL_LABEL[signal.type] ?? signal.type}</span>
                      <span className="tnum">
                        +{signal.contribution.toFixed(0)} of {signal.weight.toFixed(0)} possible
                      </span>
                    </p>
                  </div>
                </li>
              ))}
              {!material.length && (
                <li className="text-[15px] text-ink-3">
                  Nothing here cleared the threshold. {item.explanation}
                </li>
              )}
            </ul>
            <p className="mt-5 border-t border-line pt-4 text-micro leading-relaxed text-ink-4">
              The score is the sum of these measurements. It describes how unusual the move was, not
              whether the stock is worth buying.
            </p>
          </Section>

          <Section title="Your last visit">
            <LastVisitJourney item={item} />
          </Section>

          <Section title="Context">
            <dl className="divide-y divide-white/[0.05]">
              <ContextRow label={item.symbol} value={item.changes.sinceVisitPct} strong />
              <ContextRow label={item.benchmarks.sectorLabel} value={item.benchmarks.sectorChangePct} />
              <ContextRow label="Broad market" value={item.benchmarks.marketChangePct} />
              <ContextRow label="Relative edge" value={item.benchmarks.relativeEdgePct} accent />
            </dl>
            <dl className="mt-5 divide-y divide-white/[0.05] border-t border-line pt-1">
              <ContextRow label="Today" value={item.changes.todayPct} />
              <ContextRow label="This week" value={item.changes.weekPct} />
            </dl>
          </Section>

          {detail && (
            <Section title="60 days">
              <Sparkline points={detail.history.map((point) => point.close)} />
              <dl className="mt-4 grid grid-cols-3 gap-4">
                <Stat label="Day range" value={`${price(detail.dayLow)} – ${price(detail.dayHigh)}`} />
                <Stat label="Volume" value={compactNumber(detail.volume)} />
                <Stat
                  label="Relative volume"
                  value={item.volumeRatio ? `${item.volumeRatio.toFixed(1)}×` : "—"}
                />
              </dl>
            </Section>
          )}

          {!detail && !error && (
            <Section title="60 days">
              <div className="skeleton h-20 rounded" />
            </Section>
          )}

          {error && (
            <Section title="60 days">
              <p className="text-sm text-ink-3">
                Price history is unavailable right now. Everything above was computed from the live
                snapshot and is unaffected.
              </p>
            </Section>
          )}

          {item.events.length > 0 && (
            <Section title="Events">
              <ol className="space-y-4">
                {item.events.map((event) => (
                  <li key={event.id} className="flex gap-4">
                    <span aria-hidden className="mt-[7px] h-1.5 w-1.5 flex-none rounded-full bg-accent" />
                    <div>
                      <p className="text-[15px] leading-snug text-ink-2">{event.headline}</p>
                      <p className="mt-1 text-micro text-ink-4">
                        {event.kind} · {clockTime(event.occurredAt)} · {since(event.occurredAt)} ago
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            </Section>
          )}

          <Section title="Data">
            <dl className="space-y-2.5 text-sm">
              <Row label="Source" value={item.freshness.source || "—"} />
              <Row
                label="Freshness"
                value={`${item.freshness.state} · updated ${since(item.freshness.asOf)} ago`}
              />
              <Row label="Baseline" value={
                item.baseline.source === "last_visit"
                  ? `$${price(item.baseline.price)} at ${clockTime(item.baseline.observedAt)}`
                  : `Today's open, $${price(item.baseline.price)}`
              } />
            </dl>
            {item.confidence.reasons.length > 0 && (
              <ul className="mt-4 space-y-1.5 border-t border-line pt-4">
                {item.confidence.reasons.map((reason) => (
                  <li key={reason} className="text-micro leading-relaxed text-ink-4">
                    {reason}
                  </li>
                ))}
              </ul>
            )}
            {item.freshness.notes.map((note) => (
              <p key={note} className="mt-3 text-micro leading-relaxed text-down">
                {note}
              </p>
            ))}
          </Section>

          {item.changeEventId && (
            <button
              onClick={() => onReview(item)}
              disabled={item.status !== "new"}
              className="mt-10 w-full rounded-md border border-line py-3.5 text-sm text-ink-2 transition-colors duration-200 hover:border-line-strong hover:text-ink disabled:opacity-40"
            >
              {item.status === "new" ? "Mark as reviewed" : "Reviewed"}
            </button>
          )}
        </div>
      </aside>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-10">
      <h3 className="mb-4 text-micro uppercase tracking-[0.14em] text-ink-4">{title}</h3>
      {children}
    </section>
  );
}

function ContextRow({
  label,
  value,
  strong = false,
  accent = false,
}: {
  label: string;
  value: number | null;
  strong?: boolean;
  accent?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between py-2.5">
      <dt className={strong ? "text-[15px] text-ink" : "text-[15px] text-ink-3"}>{label}</dt>
      <dd
        className={`tnum font-mono text-[15px] ${
          accent ? "text-accent" : value === null ? "text-ink-4" : moveClass(value)
        }`}
      >
        {pct(value)}
      </dd>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-ink-3">{label}</dt>
      <dd className="truncate text-right font-mono text-[13px] text-ink-2">{value}</dd>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-micro text-ink-4">{label}</dt>
      <dd className="tnum mt-1 font-mono text-sm text-ink-2">{value}</dd>
    </div>
  );
}

/** The journey between what you saw and what is true now. */
function LastVisitJourney({ item }: { item: AttentionItem }) {
  const from = item.baseline.price;
  const to = item.price;
  const rising = to >= from;
  const lo = Math.min(from, to);
  const hi = Math.max(from, to);
  const padding = Math.max((hi - lo) * 0.9, hi * 0.004);
  const scale = (value: number) => ((value - (lo - padding)) / (hi - lo + padding * 2)) * 100;

  return (
    <div>
      <div className="relative h-16">
        <div className="absolute inset-x-0 top-1/2 h-px bg-line" aria-hidden />
        <div
          className="absolute top-1/2 h-px bg-accent transition-[left,right] duration-700 ease-pulse"
          style={{ left: `${scale(lo)}%`, right: `${100 - scale(hi)}%` }}
          aria-hidden
        />
        <Marker position={scale(from)} label="Last visit" value={from} time={item.baseline.observedAt} above />
        <Marker position={scale(to)} label="Now" value={to} accent above={false} />
      </div>
      <p className="mt-2 text-sm text-ink-3">
        {item.baseline.source === "last_visit"
          ? `You last saw $${price(from)} ${since(item.baseline.observedAt)} ago. It has ${
              rising ? "risen" : "fallen"
            } ${Math.abs(item.changes.sinceVisitPct).toFixed(2)}% since.`
          : `No previous visit on record, so this is measured from today's open of $${price(from)}.`}
      </p>
    </div>
  );
}

function Marker({
  position,
  label,
  value,
  time,
  accent = false,
  above = true,
}: {
  position: number;
  label: string;
  value: number;
  time?: string;
  accent?: boolean;
  above?: boolean;
}) {
  return (
    <div
      className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2"
      style={{ left: `${Math.min(94, Math.max(6, position))}%` }}
    >
      <span
        className={`block h-2 w-2 rounded-full ${accent ? "bg-accent" : "bg-ink-3"}`}
        aria-hidden
      />
      <div
        className={`absolute left-1/2 w-28 -translate-x-1/2 text-center ${
          above ? "bottom-5" : "top-5"
        }`}
      >
        <p className="tnum font-mono text-sm text-ink">${price(value)}</p>
        <p className="text-micro text-ink-4">
          {label}
          {time ? ` · ${since(time)} ago` : ""}
        </p>
      </div>
    </div>
  );
}

function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) return <p className="text-sm text-ink-3">Not enough history to chart.</p>;
  const width = 480;
  const height = 78;
  const lo = Math.min(...points);
  const hi = Math.max(...points);
  const span = hi - lo || 1;
  const path = points
    .map((value, index) => {
      const x = (index / (points.length - 1)) * width;
      const y = height - ((value - lo) / span) * (height - 8) - 4;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full"
      role="img"
      aria-label={`60-day close range from ${lo.toFixed(2)} to ${hi.toFixed(2)}, currently ${points[points.length - 1].toFixed(2)}.`}
    >
      <path d={path} fill="none" stroke="rgba(92,225,255,0.75)" strokeWidth="1.4" />
    </svg>
  );
}
