"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { since } from "@/lib/format";
import { AppShell } from "@/components/AppShell";
import { ScenarioControl } from "@/components/ScenarioControl";

const WEIGHT_LABELS: Record<string, string> = {
  price_move: "Price movement",
  volume_anomaly: "Volume anomaly",
  sector_outperformance: "Versus sector",
  market_outperformance: "Versus market",
  historical_unusualness: "Versus its own history",
  event: "Events",
  missed_while_away: "Missed while away",
};

const THRESHOLD_LABELS: Record<string, string> = {
  high_threshold: "Needs attention at",
  medium_threshold: "Worth a look at",
};

/**
 * Scoring is configurable because "meaningful" is a judgement, not a constant.
 * The weights here are the same object the engine reads, validated server-side.
 */
export default function SettingsPage() {
  const [weights, setWeights] = useState<Record<string, number> | null>(null);
  const [defaults, setDefaults] = useState<Record<string, number>>({});
  const [presets, setPresets] = useState<Record<string, Record<string, number>>>({});
  const [saved, setSaved] = useState<string | null>(null);
  const [quality, setQuality] = useState<
    { id: number; symbol: string | null; kind: string; detail: string; detectedAt: string }[]
  >([]);

  useEffect(() => {
    api.attentionProfile().then((profile) => {
      setWeights(profile.weights);
      setDefaults(profile.defaults);
      setPresets(profile.presets);
    });
    api.dataQuality().then(setQuality).catch(() => undefined);
  }, []);

  async function save(next: Record<string, number>) {
    setWeights(next);
    const result = await api.saveAttentionProfile(next);
    setWeights(result.weights);
    setSaved("Saved. Reload Pulse to score against the new weights.");
  }

  return (
    <AppShell>
      <div className="mx-auto w-full max-w-[880px] px-5 pb-24 md:px-10">
        <header className="pt-10 md:pt-14">
          <h1 className="text-title font-semibold text-ink">Settings</h1>
          <p className="mt-3 max-w-[54ch] text-ink-2">
            What counts as meaningful is a judgement call, so it's yours to make.
          </p>
        </header>

        <section className="mt-12">
          <h2 className="text-heading font-medium text-ink">Attention weights</h2>
          <p className="mt-2 max-w-[58ch] text-sm text-ink-3">
            The maximum points each signal can contribute. They deliberately sum above 100, so a
            stock has to light up on several independent axes to saturate the score.
          </p>

          <div className="mt-5 flex flex-wrap gap-2">
            {Object.keys(presets).map((name) => (
              <button
                key={name}
                onClick={() => save(presets[name])}
                className="rounded-md border border-line px-3 py-1.5 text-sm capitalize text-ink-3 transition-colors duration-200 hover:border-line-strong hover:text-ink"
              >
                {name.replace("_", " ")}
              </button>
            ))}
            <button
              onClick={() => save(defaults)}
              className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-3 transition-colors duration-200 hover:border-line-strong hover:text-ink"
            >
              Reset to defaults
            </button>
          </div>

          {weights && (
            <div className="mt-8 space-y-5">
              {Object.keys(WEIGHT_LABELS).map((key) => (
                <Slider
                  key={key}
                  id={key}
                  label={WEIGHT_LABELS[key]}
                  value={weights[key] ?? 0}
                  max={60}
                  onChange={(value) => setWeights({ ...weights, [key]: value })}
                  onCommit={(value) => save({ ...weights, [key]: value })}
                />
              ))}
              <div className="border-t border-line pt-6">
                {Object.keys(THRESHOLD_LABELS).map((key) => (
                  <Slider
                    key={key}
                    id={key}
                    label={THRESHOLD_LABELS[key]}
                    value={weights[key] ?? 0}
                    max={100}
                    onChange={(value) => setWeights({ ...weights, [key]: value })}
                    onCommit={(value) => save({ ...weights, [key]: value })}
                  />
                ))}
              </div>
            </div>
          )}

          <p aria-live="polite" className="mt-5 text-micro text-ink-4">
            {saved ?? ""}
          </p>
        </section>

        <div className="mt-16 border-t border-line pt-10">
          <ScenarioControl />
        </div>

        <section className="mt-16 border-t border-line pt-10">
          <h2 className="text-heading font-medium text-ink">Data quality log</h2>
          <p className="mt-2 max-w-[58ch] text-sm text-ink-3">
            Every time the feeds disagreed or one went down. Discrepancies are recorded, never
            silently resolved.
          </p>
          {quality.length === 0 ? (
            <p className="mt-6 text-sm text-ink-3">Nothing recorded. Both feeds have agreed.</p>
          ) : (
            <ul className="mt-6 divide-y divide-white/[0.05]">
              {quality.map((row) => (
                <li key={row.id} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 py-3">
                  <span className="w-20 font-mono text-micro uppercase text-ink-4">{row.kind}</span>
                  <span className="min-w-0 flex-1 text-sm text-ink-2">{row.detail}</span>
                  <span className="text-micro text-ink-4">{since(row.detectedAt)} ago</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </AppShell>
  );
}

function Slider({
  id,
  label,
  value,
  max,
  onChange,
  onCommit,
}: {
  id: string;
  label: string;
  value: number;
  max: number;
  onChange: (value: number) => void;
  onCommit: (value: number) => void;
}) {
  return (
    <div className="flex items-center gap-5">
      <label htmlFor={id} className="w-52 flex-none text-sm text-ink-2">
        {label}
      </label>
      <input
        id={id}
        type="range"
        min={0}
        max={max}
        step={1}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        onMouseUp={(event) => onCommit(Number((event.target as HTMLInputElement).value))}
        onTouchEnd={(event) => onCommit(Number((event.target as HTMLInputElement).value))}
        onKeyUp={(event) => onCommit(Number((event.target as HTMLInputElement).value))}
        className="h-1 flex-1 accent-[#5CE1FF]"
      />
      <output htmlFor={id} className="tnum w-10 text-right font-mono text-sm text-ink">
        {Math.round(value)}
      </output>
    </div>
  );
}
