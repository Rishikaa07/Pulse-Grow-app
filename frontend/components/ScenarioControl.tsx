"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { DemoState } from "@/lib/types";

/**
 * Demo controls.
 *
 * The tape is deterministic, so switching scenarios is a real state change on
 * the server rather than a UI mock: the reconciler, the freshness policy and
 * the engine all see the new conditions. Selecting a scenario also re-anchors
 * its scripted move to the last hour or so, so it is visible immediately.
 */
export function ScenarioControl({
  compact = false,
  onChanged,
}: {
  compact?: boolean;
  onChanged?: () => void;
}) {
  const [state, setState] = useState<DemoState | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.demoState().then(setState).catch(() => undefined);
  }, []);

  async function apply(patch: Partial<Omit<DemoState, "scenarios">>) {
    setBusy(true);
    try {
      setState(await api.setDemoState(patch));
      onChanged?.();
    } finally {
      setBusy(false);
    }
  }

  if (!state) return null;
  const current = state.scenarios.find((s) => s.key === state.scenario);

  return (
    <section aria-label="Demo controls" className={compact ? "mt-16 border-t border-line pt-8" : ""}>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className={compact ? "text-sm text-ink-2" : "text-heading font-medium text-ink"}>
          Demo market
        </h2>
        <p className="text-micro text-ink-4">
          Deterministic tape · the same scenario always reproduces the same prices
        </p>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {state.scenarios.map((scenario) => (
          <button
            key={scenario.key}
            disabled={busy}
            onClick={() => apply({ scenario: scenario.key })}
            aria-pressed={scenario.key === state.scenario}
            title={scenario.description}
            className={`rounded-md border px-3 py-1.5 text-sm transition-colors duration-200 disabled:opacity-50 ${
              scenario.key === state.scenario
                ? "border-line-strong bg-white/[0.05] text-ink"
                : "border-line text-ink-3 hover:border-line-strong hover:text-ink"
            }`}
          >
            {scenario.label}
          </button>
        ))}
      </div>

      {current && <p className="mt-3 max-w-[62ch] text-sm text-ink-3">{current.description}</p>}

      <div className="mt-5 flex flex-wrap gap-6">
        <Toggle
          label="Primary feed outage"
          checked={state.primaryOutage}
          disabled={busy}
          onChange={(value) => apply({ primaryOutage: value })}
        />
        <Toggle
          label="Secondary feed timeout"
          checked={state.secondaryOutage}
          disabled={busy}
          onChange={(value) => apply({ secondaryOutage: value })}
        />
      </div>
      <p className="mt-3 max-w-[62ch] text-micro leading-relaxed text-ink-4">
        Turn both feeds off to see the fallback: the last verified snapshot, honestly labelled,
        with confidence reduced. The page does not break.
      </p>
    </section>
  );
}

function Toggle({
  label,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  checked: boolean;
  disabled: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2.5 text-sm text-ink-2">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="h-4 w-4 accent-[#5CE1FF]"
      />
      {label}
    </label>
  );
}
