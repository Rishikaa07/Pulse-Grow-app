"use client";

import { useEffect, useState } from "react";
import { clockTime, duration, plural } from "@/lib/format";
import type { Overview } from "@/lib/types";

/**
 * The first thing on the screen is a sentence, not a table.
 *
 * "You were away for 3h 18m" is the whole premise of the product, so it gets
 * display type and nothing competes with it.
 */
export function WelcomeHeader({ overview }: { overview: Overview }) {
  const { visit, summary } = overview;
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);

  const away = visit.awaySeconds;
  const total = summary.meaningfulChanges + summary.unusualMoves;

  const subtitle = !visit.lastVisitAt
    ? "This is your first visit, so everything is measured from today's open."
    : away && away > 120
      ? `You were last here ${duration(away)} ago.`
      : "You were here a moment ago.";

  const verdict =
    summary.meaningfulChanges > 0
      ? `${plural(summary.meaningfulChanges, "thing")} deserve${summary.meaningfulChanges === 1 ? "s" : ""} your attention.`
      : total > 0
        ? "Nothing major, but a few names moved more than usual."
        : "Nothing unusual happened.";

  return (
    <header className="pt-10 md:pt-14">
      <p className="text-sm text-ink-3">{subtitle}</p>
      <h1 className="mt-3 text-title font-semibold text-ink">
        {summary.meaningfulChanges > 0 ? "Here's what changed." : "You're all caught up."}
      </h1>
      <p className="mt-3 max-w-[52ch] text-lg text-ink-2">{verdict}</p>
      <p className="mt-2 text-micro text-ink-4" suppressHydrationWarning>
        Updated {clockTime(overview.generatedAt)} · comparing against{" "}
        {visit.baselineSource === "last_visit"
          ? "the prices you last saw"
          : "today's open"}
        {now ? "" : ""}
      </p>
    </header>
  );
}

/**
 * One proportional bar instead of four metric cards. The width of each segment
 * is the honest share of the watchlist it represents, so the quiet majority
 * visually dominates on a quiet day — which is the point.
 */
export function ChangeSummary({ overview }: { overview: Overview }) {
  const { summary } = overview;
  const segments = [
    { key: "meaningful", label: "meaningful changes", value: summary.meaningfulChanges, className: "bg-accent" },
    { key: "unusual", label: "unusual moves", value: summary.unusualMoves, className: "bg-indigo" },
    { key: "events", label: "events", value: summary.events, className: "bg-ink-2" },
    {
      key: "quiet",
      label: "within normal movement",
      value: Math.max(0, summary.tracked - summary.meaningfulChanges),
      className: "bg-white/10",
    },
  ];
  const total = segments.reduce((sum, segment) => sum + segment.value, 0) || 1;

  return (
    <section aria-label="Summary of changes" className="mt-9">
      <div className="flex h-1.5 gap-1 overflow-hidden rounded-full" role="presentation">
        {segments
          .filter((segment) => segment.value > 0)
          .map((segment) => (
            <span
              key={segment.key}
              className={`${segment.className} h-full rounded-full transition-[width] duration-700 ease-pulse`}
              style={{ width: `${(segment.value / total) * 100}%` }}
            />
          ))}
      </div>

      <dl className="mt-5 flex flex-wrap gap-x-10 gap-y-4">
        {segments.map((segment) => (
          <div key={segment.key} className="flex items-baseline gap-2.5">
            <dt className="sr-only">{segment.label}</dt>
            <dd className="tnum font-mono text-2xl text-ink">{segment.value}</dd>
            <span className="text-sm text-ink-3">{segment.label}</span>
          </div>
        ))}
      </dl>
    </section>
  );
}
