/** Wire types. Mirrors the FastAPI response models exactly. */

export type Severity = "high" | "medium" | "low" | "none";
export type Freshness = "fresh" | "delayed" | "stale" | "unavailable";
export type ConfidenceLevel = "high" | "medium" | "low";
export type ReviewStatus = "new" | "reviewed" | "dismissed";

export interface User {
  id: number;
  email: string;
  displayName: string;
  isDemo: boolean;
  attentionProfile: Record<string, number>;
}

export interface WatchlistItem {
  symbol: string;
  name: string;
  sector: string;
  position: number;
}

export interface Watchlist {
  id: number;
  name: string;
  position: number;
  itemCount: number;
  items: WatchlistItem[];
}

export interface Signal {
  type:
    | "PRICE_MOVE"
    | "VOLUME_ANOMALY"
    | "SECTOR_OUTPERFORMANCE"
    | "MARKET_OUTPERFORMANCE"
    | "HISTORICAL_UNUSUALNESS"
    | "EVENT"
    | "MISSED_WHILE_AWAY";
  value: number;
  display: string;
  weight: number;
  contribution: number;
  detail: string;
}

export interface MarketEvent {
  id: string;
  headline: string;
  kind: string;
  occurredAt: string;
}

export interface AttentionItem {
  symbol: string;
  name: string;
  attentionScore: number;
  severity: Severity;
  headline: string;
  explanation: string;
  price: number;
  changes: { sinceVisitPct: number; todayPct: number; weekPct: number | null };
  benchmarks: {
    sectorCode: string;
    sectorLabel: string;
    sectorChangePct: number | null;
    marketChangePct: number | null;
    relativeEdgePct: number | null;
  };
  baseline: { price: number; observedAt: string; source: string };
  signals: Signal[];
  confidence: { level: ConfidenceLevel; score: number; reasons: string[] };
  freshness: { state: Freshness; ageSeconds: number; source: string; asOf: string; notes: string[] };
  volumeRatio: number | null;
  sigmaMultiple: number | null;
  changedSinceLastVisit: boolean;
  events: MarketEvent[];
  status: ReviewStatus;
  changeEventId: number | null;
  fingerprint: string;
}

export interface Overview {
  watchlist: Watchlist;
  visit: {
    startedAt: string;
    isNewVisit: boolean;
    lastVisitAt: string | null;
    awaySeconds: number | null;
    baselineSource: string;
  };
  summary: {
    tracked: number;
    meaningfulChanges: number;
    unusualMoves: number;
    events: number;
    quiet: number;
    newInInbox: number;
  };
  items: AttentionItem[];
  indices: { key: string; label: string; changeTodayPct: number }[];
  dataQuality: {
    freshness: Freshness;
    degraded: boolean;
    providers: { name: string; priority: number; ok: boolean; detail: string }[];
    discrepancies: string[];
    missingSymbols: string[];
  };
  scenario: string;
  generatedAt: string;
}

export interface StockDetail {
  symbol: string;
  name: string;
  exchange: string;
  sector: string;
  sectorLabel: string;
  price: number;
  prevClose: number;
  openPrice: number;
  dayHigh: number;
  dayLow: number;
  volume: number;
  freshness: { state: Freshness; ageSeconds: number; source: string; asOf: string; notes: string[] };
  stats: Record<string, number>;
  history: { day: string; close: number; volume: number }[];
  events: MarketEvent[];
}

export interface SearchResult {
  symbol: string;
  name: string;
  exchange: string;
  sector: string;
  sectorLabel: string;
}

export interface ChangeEvent {
  id: number;
  symbol: string;
  attentionScore: number;
  severity: string;
  headline: string;
  explanation: string;
  signals: Signal[];
  metrics: Record<string, number | null>;
  confidence: string;
  status: ReviewStatus;
  detectedAt: string;
  reviewedAt: string | null;
}

export interface DemoState {
  scenario: string;
  primaryOutage: boolean;
  secondaryOutage: boolean;
  scenarios: { key: string; label: string; description: string }[];
}
