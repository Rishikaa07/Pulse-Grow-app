"use client";

import { useState } from "react";
import { arrow, moveClass, pct, plural, price } from "@/lib/format";
import type { AttentionItem, Overview } from "@/lib/types";
import { AttentionMeter, ConfidenceDot, FreshnessNote } from "./Indicators";

/**
 * Ranked by attention, not by percentage change.
 *
 * The numbering is real: these rows are a priority order, so 01/02/03 encodes
 * something. The quiet group is collapsed by default and counted, never listed —
 * the product's job is to reduce what you have to read.
 */
export function AttentionFeed({
  overview,
  onOpen,
  onReview,
}: {
  overview: Overview;
  onOpen: (symbol: string) => void;
  onReview: (item: AttentionItem) => void;
}) {
  const high = overview.items.filter((item) => item.severity === "high");
  const medium = overview.items.filter((item) => item.severity === "medium");
  const rest = overview.items.filter(
    (item) => item.severity === "low" || item.severity === "none",
  );

  if (!overview.items.length) {
    return (
      <p className="mt-14 text-ink-3">
        This watchlist is empty. Press{" "}
        <kbd className="rounded border border-line px-1.5 py-0.5 font-mono text-[11px]">⌘K</kbd> to
        add a symbol.
      </p>
    );
  }

  if (!high.length && !medium.length) return <MarketSilence overview={overview} />;

  return (
    <div className="mt-14 space-y-14">
      {high.length > 0 && (
        <Section title="Needs your attention" count={high.length}>
          {high.map((item, index) => (
            <Row
              key={item.symbol}
              item={item}
              rank={index + 1}
              onOpen={onOpen}
              onReview={onReview}
              emphasis
            />
          ))}
        </Section>
      )}

      {medium.length > 0 && (
        <Section title="Worth a look" count={medium.length}>
          {medium.map((item, index) => (
            <Row
              key={item.symbol}
              item={item}
              rank={high.length + index + 1}
              onOpen={onOpen}
              onReview={onReview}
            />
          ))}
        </Section>
      )}

      {rest.length > 0 && <QuietGroup items={rest} onOpen={onOpen} />}
    </div>
  );
}

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section aria-label={title}>
      <div className="flex items-baseline justify-between border-b border-line pb-3">
        <h2 className="text-heading font-medium text-ink">{title}</h2>
        <span className="tnum font-mono text-sm text-ink-4">{count}</span>
      </div>
      <ul className="divide-y divide-white/[0.05]">{children}</ul>
    </section>
  );
}

function Row({
  item,
  rank,
  onOpen,
  onReview,
  emphasis = false,
}: {
  item: AttentionItem;
  rank: number;
  onOpen: (symbol: string) => void;
  onReview: (item: AttentionItem) => void;
  emphasis?: boolean;
}) {
  const move = item.changes.sinceVisitPct;

  return (
    <li className="group relative">
      <div className="flex flex-col gap-4 py-6 md:flex-row md:items-start md:gap-8">
        <span
          aria-hidden
          className="tnum hidden w-7 pt-1 font-mono text-sm text-ink-4 md:block"
        >
          {String(rank).padStart(2, "0")}
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <button
              onClick={() => onOpen(item.symbol)}
              className="font-mono text-xl tracking-tight text-ink transition-colors duration-200 hover:text-accent"
            >
              {item.symbol}
              {item.status === "new" && (
                <span className="ml-2 align-middle text-[10px] text-accent" aria-label="New since your last visit">
                  ●
                </span>
              )}
            </button>
            <span className={`tnum font-mono text-lg ${moveClass(move)}`}>
              <span aria-hidden className="mr-1 text-[10px]">
                {arrow(move)}
              </span>
              {pct(move)}
            </span>
            <span className="text-sm text-ink-4">since your last check</span>
          </div>

          <p className={`mt-2.5 max-w-[62ch] leading-relaxed ${emphasis ? "text-ink-2" : "text-ink-3"}`}>
            {item.explanation}
          </p>

          <div className="mt-3.5 flex flex-wrap items-center gap-x-5 gap-y-2 text-micro text-ink-4">
            <span className="tnum font-mono">${price(item.price)}</span>
            {item.volumeRatio !== null && (
              <span className="tnum">{item.volumeRatio.toFixed(1)}× volume</span>
            )}
            {item.benchmarks.relativeEdgePct !== null && (
              <span className="tnum">
                {pct(item.benchmarks.relativeEdgePct)} vs {item.benchmarks.sectorLabel.toLowerCase()}
              </span>
            )}
            <ConfidenceDot level={item.confidence.level} />
            <FreshnessNote freshness={item.freshness} />
          </div>
        </div>

        <div className="flex items-center gap-6 md:flex-col md:items-end md:gap-3">
          <AttentionMeter score={item.attentionScore} severity={item.severity} />
          <div className="flex gap-3">
            <button
              onClick={() => onOpen(item.symbol)}
              className="text-sm text-accent transition-opacity duration-200 hover:opacity-75"
            >
              Why?
            </button>
            {item.changeEventId && item.status === "new" && (
              <button
                onClick={() => onReview(item)}
                className="text-sm text-ink-3 transition-colors duration-200 hover:text-ink"
              >
                Mark reviewed
              </button>
            )}
          </div>
        </div>
      </div>
    </li>
  );
}

function QuietGroup({
  items,
  onOpen,
}: {
  items: AttentionItem[];
  onOpen: (symbol: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <section aria-label="No significant change">
      <div className="flex items-baseline justify-between border-b border-line pb-3">
        <h2 className="text-heading font-medium text-ink-2">No significant change</h2>
        <button
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          className="text-sm text-accent transition-opacity duration-200 hover:opacity-75"
        >
          {open ? "Hide" : "View all"}
        </button>
      </div>
      <p className="py-5 text-ink-3">
        {plural(items.length, "other stock")} stayed within normal movement.
      </p>
      {open && (
        <ul className="grid gap-x-8 gap-y-3 pb-2 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <li key={item.symbol}>
              <button
                onClick={() => onOpen(item.symbol)}
                className="flex w-full items-baseline justify-between gap-4 rounded px-1 py-1.5 text-left transition-colors duration-200 hover:bg-white/[0.03]"
              >
                <span className="font-mono text-sm text-ink-2">{item.symbol}</span>
                <span className={`tnum font-mono text-sm ${moveClass(item.changes.sinceVisitPct)}`}>
                  {pct(item.changes.sinceVisitPct)}
                </span>
                <span className="tnum w-7 text-right font-mono text-micro text-ink-4">
                  {item.attentionScore}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** The low-signal state, treated as a result rather than an absence. */
export function MarketSilence({ overview }: { overview: Overview }) {
  return (
    <section className="mt-16 border-t border-line pt-16 text-center">
      <p className="text-title font-semibold text-ink">You're all caught up.</p>
      <p className="mx-auto mt-4 max-w-[38ch] text-ink-2">
        The market moved. Nothing in this watchlist moved in a way that was unusual for it.
      </p>
      <dl className="mx-auto mt-10 flex max-w-md justify-center gap-12">
        <div>
          <dd className="tnum font-mono text-3xl text-ink">{overview.summary.tracked}</dd>
          <dt className="mt-1.5 text-micro text-ink-4">stocks monitored</dt>
        </div>
        <div>
          <dd className="tnum font-mono text-3xl text-ink">0</dd>
          <dt className="mt-1.5 text-micro text-ink-4">meaningful changes</dt>
        </div>
      </dl>
    </section>
  );
}
