"use client";

import { useMemo, useState } from "react";
import { pct } from "@/lib/format";
import type { AttentionItem } from "@/lib/types";

/**
 * Change Constellation.
 *
 * Answers one question: did this move *with* its context, or against it?
 *
 * All three bars share a signed scale anchored at zero, and the bracket between
 * the stock and its sector is the relative edge — the number that turns "NVDA
 * rose" into "NVDA rose more than the thing that usually moves it".
 */

const WIDTH = 640;
const ROW_HEIGHT = 62;
const AXIS_X = WIDTH * 0.42;
const MAX_BAR = WIDTH * 0.45;

export function ChangeConstellation({
  items,
  onOpen,
}: {
  items: AttentionItem[];
  onOpen: (symbol: string) => void;
}) {
  const candidates = useMemo(() => items.slice(0, 5), [items]);
  const [symbol, setSymbol] = useState<string | null>(null);
  const item = candidates.find((c) => c.symbol === symbol) ?? candidates[0];

  if (!item) return null;

  const rows = [
    { label: item.symbol, value: item.changes.sinceVisitPct, tone: "#5CE1FF", strong: true },
    {
      label: item.benchmarks.sectorLabel,
      value: item.benchmarks.sectorChangePct,
      tone: "#7C7BFF",
      strong: false,
    },
    { label: "Broad market", value: item.benchmarks.marketChangePct, tone: "#6E7686", strong: false },
  ];

  const scale = Math.max(0.35, ...rows.map((row) => Math.abs(row.value ?? 0))) * 1.15;
  const barWidth = (value: number) => (Math.abs(value) / scale) * MAX_BAR;
  const signedWidth = (value: number) => (value >= 0 ? barWidth(value) : -barWidth(value));

  const stockValue = rows[0].value ?? 0;
  const sectorValue = rows[1].value;

  const edge = item.benchmarks.relativeEdgePct;
  const height = ROW_HEIGHT * rows.length + 34;

  return (
    <section aria-label="Change Constellation" className="mt-16">
      <div className="flex flex-wrap items-baseline justify-between gap-4 border-b border-line pb-3">
        <div>
          <h2 className="text-heading font-medium text-ink">Change Constellation</h2>
          <p className="mt-1.5 text-sm text-ink-3">
            The same window, measured against the things that usually move it.
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Choose a symbol">
          {candidates.map((candidate) => (
            <button
              key={candidate.symbol}
              onClick={() => setSymbol(candidate.symbol)}
              aria-pressed={candidate.symbol === item.symbol}
              className={`rounded border px-2.5 py-1 font-mono text-micro transition-colors duration-200 ${
                candidate.symbol === item.symbol
                  ? "border-line-strong text-ink"
                  : "border-line text-ink-3 hover:text-ink"
              }`}
            >
              {candidate.symbol}
            </button>
          ))}
        </div>
      </div>

      <svg
        viewBox={`0 0 ${WIDTH} ${height}`}
        className="mt-7 w-full"
        role="img"
        aria-label={`${item.symbol} moved ${pct(item.changes.sinceVisitPct)} since your last check, ${
          item.benchmarks.sectorLabel
        } moved ${pct(item.benchmarks.sectorChangePct)}, the broad market moved ${pct(
          item.benchmarks.marketChangePct,
        )}. Relative edge ${pct(edge)}.`}
      >
        <line
          x1={AXIS_X}
          y1={8}
          x2={AXIS_X}
          y2={height - 20}
          stroke="rgba(255,255,255,0.12)"
        />
        <text x={AXIS_X} y={height - 6} textAnchor="middle" className="fill-[#3A404B] text-[10px]">
          0%
        </text>

        {rows.map((row, index) => {
          const y = 26 + index * ROW_HEIGHT;
          const value = row.value;
          if (value === null) {
            return (
              <g key={row.label}>
                <text x={AXIS_X - 14} y={y + 5} textAnchor="end" className="fill-[#949BA8] text-[13px]">
                  {row.label}
                </text>
                <text x={AXIS_X + 14} y={y + 5} className="fill-[#3A404B] text-[12px]">
                  No benchmark available
                </text>
              </g>
            );
          }
          const width = barWidth(value);
          const x = value >= 0 ? AXIS_X : AXIS_X - width;
          return (
            <g key={row.label}>
              <text
                x={AXIS_X - 14}
                y={y + 5}
                textAnchor="end"
                className={row.strong ? "fill-[#EDEFF3] text-[13px]" : "fill-[#949BA8] text-[13px]"}
              >
                {row.label}
              </text>
              <rect
                x={x}
                y={y - 7}
                width={Math.max(1.5, width)}
                height={14}
                rx={2}
                fill={row.tone}
                fillOpacity={row.strong ? 0.9 : 0.45}
              />
              <text
                x={value >= 0 ? x + width + 10 : x - 10}
                y={y + 5}
                textAnchor={value >= 0 ? "start" : "end"}
                className="fill-[#949BA8] text-[12px]"
                style={{ fontVariantNumeric: "tabular-nums" }}
              >
                {pct(value)}
              </text>
            </g>
          );
        })}

        {/* The bracket is the point of the chart. */}
        {edge !== null && sectorValue !== null && (
          <path
            d={bracketPath(
              AXIS_X + signedWidth(stockValue),
              26,
              AXIS_X + signedWidth(sectorValue),
              26 + ROW_HEIGHT,
            )}
            fill="none"
            stroke="rgba(92,225,255,0.4)"
            strokeWidth={1}
          />
        )}
      </svg>

      <div className="mt-2 flex flex-wrap items-baseline gap-x-8 gap-y-2 border-t border-line pt-5">
        <div className="flex items-baseline gap-3">
          <span className="text-sm text-ink-3">Relative edge</span>
          <span className="tnum font-mono text-2xl text-ink">{pct(edge)}</span>
        </div>
        <p className="max-w-[46ch] text-sm leading-relaxed text-ink-2">
          {edge === null
            ? "No sector benchmark is available for this symbol, so its move can't be placed in context."
            : Math.abs(edge) < 0.25
              ? `${item.symbol} is moving with ${item.benchmarks.sectorLabel.toLowerCase()}, not apart from it.`
              : `${item.symbol} moved ${Math.abs(edge).toFixed(2)} points ${
                  edge > 0 ? "ahead of" : "behind"
                } ${item.benchmarks.sectorLabel.toLowerCase()} over the same window.`}
        </p>
        <button
          onClick={() => onOpen(item.symbol)}
          className="text-sm text-accent transition-opacity duration-200 hover:opacity-75"
        >
          Open {item.symbol}
        </button>
      </div>
    </section>
  );
}

function bracketPath(x1: number, y1: number, x2: number, y2: number): string {
  const reach = Math.max(x1, x2) + 26;
  return `M ${x1} ${y1} H ${reach} V ${y2} H ${x2}`;
}
