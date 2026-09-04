/** Formatting helpers. Numbers are always tabular and always signed where signed matters. */

export const pct = (value: number | null | undefined, digits = 2): string =>
  value === null || value === undefined ? "—" : `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;

export const price = (value: number): string =>
  value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const compactNumber = (value: number): string => {
  if (value >= 1e9) return `${(value / 1e9).toFixed(1)}B`;
  if (value >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(1)}K`;
  return String(Math.round(value));
};

/** "3h 18m", "12m", "just now" — the phrasing the product speaks in. */
export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const s = Math.max(0, Math.round(seconds));
  if (s < 45) return "just now";
  const minutes = Math.round(s / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours < 24) return rest ? `${hours}h ${rest}m` : `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d ${hours % 24}h`;
}

export function since(iso: string | null | undefined): string {
  if (!iso) return "—";
  return duration((Date.now() - new Date(iso).getTime()) / 1000);
}

export function clockTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export const direction = (value: number): "up" | "down" | "flat" =>
  value > 0.005 ? "up" : value < -0.005 ? "down" : "flat";

/** Muted mint / rose at text weight only. Never a filled block. */
export const moveClass = (value: number): string => {
  const d = direction(value);
  return d === "up" ? "text-up" : d === "down" ? "text-down" : "text-ink-2";
};

export const arrow = (value: number): string => {
  const d = direction(value);
  return d === "up" ? "▲" : d === "down" ? "▼" : "•";
};

export const SEVERITY_LABEL: Record<string, string> = {
  high: "Needs your attention",
  medium: "Worth a look",
  low: "Minor",
  none: "No significant change",
};

export const plural = (n: number, one: string, many?: string) =>
  `${n} ${n === 1 ? one : (many ?? one + "s")}`;
