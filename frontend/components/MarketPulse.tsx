"use client";

import { useMemo, useState } from "react";
import { moveClass, pct } from "@/lib/format";
import type { AttentionItem } from "@/lib/types";

/**
 * Market Pulse.
 *
 * A field, not a graph. The encoding is fixed and stated on the chart itself:
 *
 *   distance from centre = attention (urgent things are close)
 *   node size            = attention
 *   fill                 = severity
 *   ring                 = you haven't reviewed this yet
 *   angle                = sector, so peers sit together and a sector-wide move
 *                          reads as a cluster rather than as five separate rows
 *
 * Position is deterministic: the same watchlist always lays out the same way,
 * so returning users read it by memory instead of re-reading it.
 */

const WIDTH = 720;
const HEIGHT = 470;
const CX = WIDTH / 2;
const CY = HEIGHT / 2 + 6;
const R_MIN = 46;
const R_MAX = 202;

const radiusFor = (score: number) => R_MIN + (1 - Math.min(100, score) / 100) * (R_MAX - R_MIN);

const FILL: Record<string, string> = {
  high: "#5CE1FF",
  medium: "#7C7BFF",
  low: "#6E7686",
  none: "#39404C",
};

interface Node {
  item: AttentionItem;
  x: number;
  y: number;
  r: number;
  angle: number;
}

export function MarketPulse({
  items,
  onOpen,
  selected,
}: {
  items: AttentionItem[];
  onOpen: (symbol: string) => void;
  selected?: string | null;
}) {
  const [view, setView] = useState<"field" | "list">("field");
  const [hovered, setHovered] = useState<string | null>(null);

  const { nodes, sectors } = useMemo(() => buildLayout(items), [items]);
  const active = hovered ?? selected ?? null;
  const activeNode = nodes.find((node) => node.item.symbol === active);

  const summary = `Attention field for ${items.length} stocks. ${
    items.filter((i) => i.severity === "high").length
  } need attention, ${items.filter((i) => i.severity === "medium").length} are worth a look.`;

  return (
    <section aria-label="Market Pulse" className="mt-16">
      <div className="flex items-baseline justify-between border-b border-line pb-3">
        <div>
          <h2 className="text-heading font-medium text-ink">Market Pulse</h2>
          <p className="mt-1.5 text-sm text-ink-3">
            Closer to the centre means more of your attention. Grouped by sector.
          </p>
        </div>
        <div className="flex gap-1 rounded-md border border-line p-0.5" role="group" aria-label="View mode">
          {(["field", "list"] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => setView(mode)}
              aria-pressed={view === mode}
              className={`rounded px-3 py-1 text-micro capitalize transition-colors duration-200 ${
                view === mode ? "bg-white/[0.07] text-ink" : "text-ink-3 hover:text-ink"
              }`}
            >
              {mode}
            </button>
          ))}
        </div>
      </div>

      {/* The field is desktop-first; phones always get the list, which is the
          same information in a form that actually works at 380px. */}
      <div className={view === "field" ? "hidden md:block" : "hidden"}>
        <div className="relative">
          <svg
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            className="mt-6 w-full"
            role="img"
            aria-label={summary}
          >
            <defs>
              <radialGradient id="pulse-core" cx="50%" cy="50%">
                <stop offset="0%" stopColor="#5CE1FF" stopOpacity="0.16" />
                <stop offset="100%" stopColor="#5CE1FF" stopOpacity="0" />
              </radialGradient>
            </defs>

            <circle cx={CX} cy={CY} r={R_MIN + 26} fill="url(#pulse-core)" />

            {/* Threshold rings, labelled — the scale is part of the chart. */}
            {[
              { score: 70, label: "Needs attention" },
              { score: 45, label: "Worth a look" },
              { score: 0, label: "Within normal range" },
            ].map((ring) => (
              <g key={ring.score}>
                <circle
                  cx={CX}
                  cy={CY}
                  r={radiusFor(ring.score)}
                  fill="none"
                  stroke="rgba(255,255,255,0.06)"
                  strokeDasharray="2 6"
                />
                <text
                  x={CX}
                  y={CY - radiusFor(ring.score) - 7}
                  textAnchor="middle"
                  className="fill-[#3A404B] text-[10px]"
                >
                  {ring.label}
                </text>
              </g>
            ))}

            {/* Sector arcs: peers occupy the same wedge. */}
            {sectors.map((sector) => (
              <text
                key={sector.label}
                x={CX + Math.cos(sector.midAngle) * (R_MAX + 34)}
                y={CY + Math.sin(sector.midAngle) * (R_MAX + 34)}
                textAnchor="middle"
                dominantBaseline="middle"
                className="fill-[#4A5160] text-[10px]"
              >
                {sector.label}
              </text>
            ))}

            {nodes.map((node) => {
              const { item } = node;
              const isActive = active === item.symbol;
              const unreviewed = item.status === "new" && item.severity !== "none";
              return (
                <g
                  key={item.symbol}
                  tabIndex={0}
                  role="button"
                  aria-label={`${item.symbol}, attention ${item.attentionScore} out of 100, ${pct(
                    item.changes.sinceVisitPct,
                  )} since your last check. ${item.headline}.`}
                  onClick={() => onOpen(item.symbol)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onOpen(item.symbol);
                    }
                  }}
                  onMouseEnter={() => setHovered(item.symbol)}
                  onMouseLeave={() => setHovered(null)}
                  onFocus={() => setHovered(item.symbol)}
                  onBlur={() => setHovered(null)}
                  className="cursor-pointer outline-none"
                >
                  {/* Motion is reserved for "high severity and you haven't seen it". */}
                  {item.severity === "high" && unreviewed && (
                    <circle
                      cx={node.x}
                      cy={node.y}
                      r={node.r}
                      fill={FILL.high}
                      className="animate-node-pulse origin-center"
                      style={{ transformBox: "fill-box", transformOrigin: "center" }}
                    />
                  )}
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={node.r}
                    fill={FILL[item.severity]}
                    fillOpacity={item.severity === "none" ? 0.5 : 0.9}
                    stroke={unreviewed ? FILL[item.severity] : "transparent"}
                    strokeOpacity={0.35}
                    strokeWidth={isActive ? 8 : 5}
                    className="transition-[stroke-width] duration-200"
                  />
                  <text
                    x={node.x}
                    y={node.y - node.r - 8}
                    textAnchor="middle"
                    className={`text-[10px] transition-colors duration-200 ${
                      isActive ? "fill-[#EDEFF3]" : "fill-[#7A8290]"
                    }`}
                  >
                    {item.symbol}
                  </text>
                </g>
              );
            })}
          </svg>

          {activeNode && (
            <figcaption
              className="pointer-events-none absolute left-1/2 top-1/2 w-56 -translate-x-1/2 -translate-y-1/2 text-center"
              aria-hidden
            >
              <p className="font-mono text-lg text-ink">{activeNode.item.symbol}</p>
              <p className={`tnum font-mono text-sm ${moveClass(activeNode.item.changes.sinceVisitPct)}`}>
                {pct(activeNode.item.changes.sinceVisitPct)}
              </p>
              <p className="mt-1.5 text-micro leading-snug text-ink-3">
                {activeNode.item.headline}
              </p>
            </figcaption>
          )}
        </div>
      </div>

      {/* Always rendered on small screens; the toggle controls it on desktop. */}
      <div className={view === "list" ? "block" : "block md:hidden"}>
        <table className="mt-6 w-full text-left">
          <caption className="sr-only">{summary}</caption>
          <thead>
            <tr className="text-micro text-ink-4">
              <th scope="col" className="pb-2 font-normal">
                Symbol
              </th>
              <th scope="col" className="pb-2 font-normal">
                Sector
              </th>
              <th scope="col" className="pb-2 text-right font-normal">
                Since last check
              </th>
              <th scope="col" className="pb-2 text-right font-normal">
                Attention
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.05]">
            {items.map((item) => (
              <tr key={item.symbol} className="transition-colors duration-200 hover:bg-white/[0.02]">
                <th scope="row" className="py-2.5 font-normal">
                  <button
                    onClick={() => onOpen(item.symbol)}
                    className="font-mono text-sm text-ink hover:text-accent"
                  >
                    {item.symbol}
                  </button>
                </th>
                <td className="py-2.5 text-sm text-ink-3">{item.benchmarks.sectorLabel}</td>
                <td className={`tnum py-2.5 text-right font-mono text-sm ${moveClass(item.changes.sinceVisitPct)}`}>
                  {pct(item.changes.sinceVisitPct)}
                </td>
                <td className="tnum py-2.5 text-right font-mono text-sm text-ink-2">
                  {item.attentionScore}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function buildLayout(items: AttentionItem[]) {
  const bySector = new Map<string, AttentionItem[]>();
  for (const item of items) {
    const key = item.benchmarks.sectorLabel;
    if (!bySector.has(key)) bySector.set(key, []);
    bySector.get(key)!.push(item);
  }

  const groups = [...bySector.entries()].sort(([a], [b]) => a.localeCompare(b));
  const total = items.length || 1;
  const nodes: Node[] = [];
  const sectors: { label: string; midAngle: number }[] = [];

  let cursor = -Math.PI / 2; // start at twelve o'clock
  for (const [label, members] of groups) {
    const span = (members.length / total) * Math.PI * 2;
    const padding = Math.min(0.09, span * 0.2);
    const start = cursor + padding / 2;
    const usable = span - padding;

    members
      .slice()
      .sort((a, b) => b.attentionScore - a.attentionScore)
      .forEach((item, index) => {
        const step = members.length === 1 ? usable / 2 : (usable / (members.length - 1 || 1)) * index;
        const angle = start + step;
        const r = radiusFor(item.attentionScore);
        nodes.push({
          item,
          angle,
          x: CX + Math.cos(angle) * r,
          y: CY + Math.sin(angle) * r,
          r: 4.5 + (item.attentionScore / 100) * 8.5,
        });
      });

    sectors.push({ label, midAngle: cursor + span / 2 });
    cursor += span;
  }

  return { nodes, sectors };
}
