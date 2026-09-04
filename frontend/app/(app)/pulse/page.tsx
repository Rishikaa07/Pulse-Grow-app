"use client";

import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { useOverview } from "@/lib/useOverview";
import { useSession } from "@/lib/session";
import type { AttentionItem } from "@/lib/types";
import { AppShell } from "@/components/AppShell";
import { AttentionFeed } from "@/components/AttentionFeed";
import { ChangeConstellation } from "@/components/ChangeConstellation";
import { ChangeSummary, WelcomeHeader } from "@/components/ChangeSummary";
import { DataQualityBanner } from "@/components/Indicators";
import { MarketPulse } from "@/components/MarketPulse";
import { ScenarioControl } from "@/components/ScenarioControl";
import { OverviewSkeleton } from "@/components/Skeletons";
import { StockPanel } from "@/components/StockPanel";

export default function PulsePage() {
  const { activeId, loading: sessionLoading } = useSession();
  const { data, error, loading, refreshing, reload } = useOverview(activeId);
  const [openSymbol, setOpenSymbol] = useState<string | null>(null);

  const review = useCallback(
    async (item: AttentionItem) => {
      if (!item.changeEventId) return;
      await api.review(item.changeEventId, "reviewed").catch(() => undefined);
      reload(true);
    },
    [reload],
  );

  const reviewAll = useCallback(async () => {
    if (!activeId) return;
    await api.reviewAll(activeId).catch(() => undefined);
    reload(true);
  }, [activeId, reload]);

  const selected = data?.items.find((item) => item.symbol === openSymbol) ?? null;

  return (
    <AppShell
      freshness={data?.dataQuality.freshness}
      lastCheckedIso={data?.generatedAt}
      onChanged={() => reload(true)}
    >
      {sessionLoading || (loading && !data) ? (
        <OverviewSkeleton />
      ) : !data ? (
        <EmptyOrError message={error} onRetry={() => reload()} />
      ) : (
        <div className="mx-auto w-full max-w-[1080px] px-5 pb-24 md:px-10">
          {error && (
            <p role="status" className="mt-6 rounded-md border border-line bg-white/[0.025] px-4 py-3 text-sm text-ink-2">
              Couldn't refresh just now, so this is the last good view. {error}
            </p>
          )}

          <WelcomeHeader overview={data} />
          <ChangeSummary overview={data} />
          <DataQualityBanner overview={data} />

          {data.summary.newInInbox > 0 && (
            <div className="mt-8 flex flex-wrap items-center gap-4">
              <p className="text-sm text-ink-2">
                {data.summary.newInInbox} unreviewed{" "}
                {data.summary.newInInbox === 1 ? "change" : "changes"} in your inbox.
              </p>
              <button
                onClick={reviewAll}
                className="text-sm text-accent transition-opacity duration-200 hover:opacity-75"
              >
                Mark all reviewed
              </button>
              {refreshing && <span className="text-micro text-ink-4">Refreshing…</span>}
            </div>
          )}

          <AttentionFeed overview={data} onOpen={setOpenSymbol} onReview={review} />

          {data.items.length > 0 && (
            <>
              <MarketPulse items={data.items} onOpen={setOpenSymbol} selected={openSymbol} />
              <ChangeConstellation items={data.items} onOpen={setOpenSymbol} />
            </>
          )}

          <ScenarioControl compact onChanged={() => reload(true)} />
        </div>
      )}

      <StockPanel item={selected} onClose={() => setOpenSymbol(null)} onReview={review} />
    </AppShell>
  );
}

function EmptyOrError({ message, onRetry }: { message: string | null; onRetry: () => void }) {
  return (
    <div className="mx-auto max-w-md px-6 py-32 text-center">
      <p className="text-title font-semibold text-ink">Nothing to show yet</p>
      <p className="mt-4 text-ink-2">
        {message ?? "Create a watchlist and add a few symbols to get started."}
      </p>
      <button
        onClick={onRetry}
        className="mt-8 rounded-md border border-line px-5 py-2.5 text-sm text-ink-2 transition-colors duration-200 hover:border-line-strong hover:text-ink"
      >
        Try again
      </button>
    </div>
  );
}
