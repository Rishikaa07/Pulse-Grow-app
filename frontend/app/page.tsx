"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ApiError, api } from "@/lib/api";

type Mode = "demo" | "signin" | "register";

const SAMPLE = [
  { label: "Price moved 4.2%, 2.8× its normal range", points: 27 },
  { label: "Volume running 2.4× its usual pace", points: 22 },
  { label: "3.1 points ahead of semiconductors", points: 20 },
  { label: "Guidance raised 54 minutes ago", points: 10 },
  { label: "Top 1% of its daily history", points: 12 },
];

export default function Landing() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("demo");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      router.push("/pulse");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
      setBusy(false);
    }
  }

  const total = SAMPLE.reduce((sum, s) => sum + s.points, 0);

  return (
    <main id="main" className="mx-auto grid min-h-dvh max-w-[1180px] items-center gap-16 px-6 py-16 lg:grid-cols-[1.05fr_0.95fr] lg:gap-20 lg:py-0">
      <section>
        <p className="mb-8 flex items-center gap-2.5 text-sm text-ink-3">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-accent" aria-hidden />
          Pulse
        </p>

        <h1 className="text-display font-semibold text-ink">Know what changed.</h1>

        <p className="mt-7 max-w-[46ch] text-lg leading-relaxed text-ink-2">
          Your market watchlist, distilled into the moves that actually deserve your attention.
          Pulse compares the market against what <em className="not-italic text-ink">you</em> last
          saw, not against the opening bell.
        </p>

        <div className="mt-10 max-w-md">
          {mode === "demo" ? (
            <div className="flex flex-col gap-3 sm:flex-row">
              <button
                onClick={() => run(api.loginDemo)}
                disabled={busy}
                className="rounded-md bg-ink px-6 py-3.5 text-[15px] font-medium text-void transition-opacity duration-200 hover:opacity-90 disabled:opacity-50"
              >
                {busy ? "Opening…" : "Enter Market Pulse"}
              </button>
              <button
                onClick={() => setMode("signin")}
                className="rounded-md border border-line px-6 py-3.5 text-[15px] text-ink-2 transition-colors duration-200 hover:border-line-strong hover:text-ink"
              >
                Use an account
              </button>
            </div>
          ) : (
            <form
              className="flex flex-col gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                run(() =>
                  mode === "register"
                    ? api.register(email, password)
                    : api.login(email, password),
                );
              }}
            >
              <label className="text-sm text-ink-2" htmlFor="email">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="rounded-md border border-line bg-white/[0.03] px-4 py-3 text-ink placeholder:text-ink-4"
                placeholder="you@example.com"
              />
              <label className="mt-2 text-sm text-ink-2" htmlFor="password">
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                minLength={8}
                autoComplete={mode === "register" ? "new-password" : "current-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="rounded-md border border-line bg-white/[0.03] px-4 py-3 text-ink placeholder:text-ink-4"
                placeholder="At least 8 characters"
              />
              <button
                type="submit"
                disabled={busy}
                className="mt-3 rounded-md bg-ink px-6 py-3.5 text-[15px] font-medium text-void hover:opacity-90 disabled:opacity-50"
              >
                {busy ? "Working…" : mode === "register" ? "Create account" : "Sign in"}
              </button>
              <div className="mt-1 flex gap-4 text-sm text-ink-3">
                <button type="button" onClick={() => setMode(mode === "register" ? "signin" : "register")} className="hover:text-ink">
                  {mode === "register" ? "I already have an account" : "Create an account"}
                </button>
                <button type="button" onClick={() => setMode("demo")} className="hover:text-ink">
                  Use the demo instead
                </button>
              </div>
            </form>
          )}

          {error && (
            <p role="alert" className="mt-4 text-sm text-down">
              {error}
            </p>
          )}
        </div>
      </section>

      {/* The hero is the product's actual claim: a score you can audit. */}
      <section aria-label="How an attention score is built" className="lg:pl-4">
        <div className="glass rounded-lg p-7">
          <div className="flex items-baseline justify-between">
            <div>
              <p className="font-mono text-2xl tracking-tight text-ink">NVDA</p>
              <p className="mt-1 text-sm text-ink-3">NVIDIA Corporation</p>
            </div>
            <div className="text-right">
              <p className="tnum font-mono text-3xl text-ink">{total}</p>
              <p className="mt-1 text-micro uppercase tracking-widest text-ink-3">Attention</p>
            </div>
          </div>

          <ul className="mt-7 space-y-3.5">
            {SAMPLE.map((signal) => (
              <li key={signal.label} className="flex items-center gap-4">
                <span className="flex-1 text-sm leading-snug text-ink-2">{signal.label}</span>
                <span className="h-px w-10 flex-none bg-line" aria-hidden />
                <span className="tnum w-9 flex-none text-right font-mono text-sm text-accent">
                  +{signal.points}
                </span>
              </li>
            ))}
          </ul>

          <p className="mt-7 border-t border-line pt-5 text-sm leading-relaxed text-ink-3">
            Every point is attributable to a measurement. No model decided this, and no part of it
            is a recommendation to buy or sell anything.
          </p>
        </div>
      </section>
    </main>
  );
}
