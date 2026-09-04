"use client";

import { useEffect, useRef, useState } from "react";
import { duration } from "@/lib/format";
import type { ConfidenceLevel, Freshness, Overview, Severity } from "@/lib/types";

/** Counts the score up on first paint. Motion here shows a value settling. */
export function useCountUp(target: number, durationMs = 550) {
  const [value, setValue] = useState(target);
  const previous = useRef(target);

  useEffect(() => {
    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setValue(target);
      previous.current = target;
      return;
    }
    const from = previous.current;
    const start = performance.now();
    let frame = 0;
    const step = (time: number) => {
      const t = Math.min(1, (time - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(Math.round(from + (target - from) * eased));
      if (t < 1) frame = requestAnimationFrame(step);
      else previous.current = target;
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, durationMs]);

  return value;
}

const SEVERITY_BAR: Record<Severity, string> = {
  high: "bg-accent",
  medium: "bg-indigo",
  low: "bg-ink-3",
  none: "bg-white/15",
};

export function AttentionMeter({ score, severity }: { score: number; severity: Severity }) {
  const animated = useCountUp(score);
  return (
    <div className="flex items-center gap-3 md:flex-col md:items-end md:gap-1.5">
      <div className="flex items-baseline gap-1.5">
        <span className="tnum font-mono text-2xl text-ink animate-score-in">{animated}</span>
        <span className="text-micro text-ink-4">/100</span>
      </div>
      <div
        className="h-[3px] w-24 overflow-hidden rounded-full bg-white/[0.07]"
        role="meter"
        aria-valuenow={score}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Attention score"
      >
        <span
          className={`block h-full rounded-full transition-[width] duration-700 ease-pulse ${SEVERITY_BAR[severity]}`}
          style={{ width: `${score}%` }}
        />
      </div>
    </div>
  );
}

const CONFIDENCE_COPY: Record<ConfidenceLevel, string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
};

export function ConfidenceDot({ level }: { level: ConfidenceLevel }) {
  const tone =
    level === "high" ? "text-ink-4" : level === "medium" ? "text-accent" : "text-down";
  return (
    <span className={`flex items-center gap-1.5 ${tone}`}>
      <span aria-hidden className="text-[8px]">
        {level === "high" ? "●" : level === "medium" ? "◐" : "○"}
      </span>
      {CONFIDENCE_COPY[level]}
    </span>
  );
}

const FRESHNESS_COPY: Record<Freshness, (age: number) => string> = {
  fresh: (age) => `Updated ${duration(age)} ago`,
  delayed: (age) => `Delayed · ${duration(age)} old`,
  stale: (age) => `Stale · ${duration(age)} old`,
  unavailable: () => "Last verified snapshot",
};

export function FreshnessNote({
  freshness,
}: {
  freshness: { state: Freshness; ageSeconds: number; source: string };
}) {
  if (freshness.state === "fresh") return null;
  const tone = freshness.state === "delayed" ? "text-accent" : "text-down";
  return (
    <span className={tone} title={`Source: ${freshness.source}`}>
      {FRESHNESS_COPY[freshness.state](freshness.ageSeconds)}
    </span>
  );
}

/**
 * Data quality is never hidden. If a feed is down, disagreeing, or lagging, the
 * user is told in the same voice as everything else — no red modal, no silence.
 */
export function DataQualityBanner({ overview }: { overview: Overview }) {
  const { dataQuality } = overview;
  const problems: string[] = [];

  const downProviders = dataQuality.providers.filter((provider) => !provider.ok);
  if (downProviders.length === dataQuality.providers.length && downProviders.length > 0) {
    problems.push("Live market data is unavailable. Showing the last verified snapshot.");
  } else if (downProviders.length) {
    problems.push(
      `${downProviders.map((p) => p.name).join(", ")} is not responding. Serving the remaining feed.`,
    );
  }
  if (dataQuality.freshness === "stale" || dataQuality.freshness === "unavailable") {
    problems.push("Some prices have stopped updating, so confidence is reduced.");
  } else if (dataQuality.freshness === "delayed") {
    problems.push("Prices are delayed rather than live.");
  }
  if (dataQuality.discrepancies.length) {
    problems.push(
      `Feeds disagree on ${dataQuality.discrepancies.length === 1 ? "one symbol" : `${dataQuality.discrepancies.length} symbols`}. The higher-priority source was used.`,
    );
  }
  if (dataQuality.missingSymbols.length) {
    problems.push(`No data for ${dataQuality.missingSymbols.join(", ")}.`);
  }

  if (!problems.length) return null;

  return (
    <aside
      role="status"
      className="mt-8 rounded-md border border-line bg-white/[0.025] px-5 py-4"
    >
      <p className="text-sm font-medium text-ink">Data quality</p>
      <ul className="mt-2 space-y-1.5">
        {problems.map((problem) => (
          <li key={problem} className="text-sm leading-relaxed text-ink-2">
            {problem}
          </li>
        ))}
      </ul>
      {dataQuality.discrepancies.length > 0 && (
        <ul className="mt-3 space-y-1 border-t border-line pt-3">
          {dataQuality.discrepancies.map((detail) => (
            <li key={detail} className="font-mono text-micro text-ink-4">
              {detail}
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
