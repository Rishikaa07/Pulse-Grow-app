/**
 * API client.
 *
 * Every call goes to the same origin: Next rewrites `/api/*` to FastAPI, so the
 * session cookie is httpOnly and same-site and no credential is ever readable
 * from JavaScript. Nothing here reads or writes localStorage.
 */
import type {
  AttentionItem,
  ChangeEvent,
  DemoState,
  Overview,
  SearchResult,
  StockDetail,
  User,
  Watchlist,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    // The network itself failed. Give the UI something it can render calmly.
    throw new ApiError(0, "Can't reach Pulse. Check that the API is running.");
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const body = text ? safeParse(text) : null;

  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `Request failed (${response.status})`;
    throw new ApiError(response.status, detail);
  }
  return body as T;
}

function safeParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });

export const api = {
  me: () => request<User>("/api/auth/me"),
  loginDemo: () => post<User>("/api/auth/demo"),
  login: (email: string, password: string) => post<User>("/api/auth/login", { email, password }),
  register: (email: string, password: string) =>
    post<User>("/api/auth/register", { email, password }),
  logout: () => post<void>("/api/auth/logout"),

  watchlists: () => request<Watchlist[]>("/api/watchlists"),
  createWatchlist: (name: string, symbols: string[] = []) =>
    post<Watchlist>("/api/watchlists", { name, symbols }),
  renameWatchlist: (id: number, name: string) =>
    request<Watchlist>(`/api/watchlists/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  deleteWatchlist: (id: number) => request<void>(`/api/watchlists/${id}`, { method: "DELETE" }),
  addStock: (id: number, symbol: string) =>
    post<Watchlist>(`/api/watchlists/${id}/stocks`, { symbol }),
  removeStock: (id: number, symbol: string) =>
    request<Watchlist>(`/api/watchlists/${id}/stocks/${symbol}`, { method: "DELETE" }),
  reorder: (id: number, symbols: string[]) =>
    post<Watchlist>(`/api/watchlists/${id}/reorder`, { symbols }),

  overview: (id: number) => request<Overview>(`/api/watchlists/${id}/overview`),
  changes: (id: number, status?: string) =>
    request<ChangeEvent[]>(`/api/watchlists/${id}/changes${status ? `?status=${status}` : ""}`),
  reviewAll: (id: number) => post<unknown>(`/api/watchlists/${id}/changes/review-all`),
  resetBaseline: (id: number) => post<void>(`/api/watchlists/${id}/baseline/reset`),
  review: (eventId: number, status: "reviewed" | "dismissed" | "new") =>
    post<ChangeEvent>(`/api/events/${eventId}/review`, { status }),

  stock: (symbol: string) => request<StockDetail>(`/api/stocks/${symbol}`),
  search: (q: string) => request<SearchResult[]>(`/api/stocks/search?q=${encodeURIComponent(q)}`),

  demoState: () => request<DemoState>("/api/demo/state"),
  setDemoState: (patch: Partial<Omit<DemoState, "scenarios">>) =>
    post<DemoState>("/api/demo/state", patch),

  attentionProfile: () =>
    request<{ weights: Record<string, number>; defaults: Record<string, number>; presets: Record<string, Record<string, number>> }>(
      "/api/settings/attention",
    ),
  saveAttentionProfile: (weights: Record<string, number>) =>
    request<{ weights: Record<string, number> }>("/api/settings/attention", {
      method: "PUT",
      body: JSON.stringify({ weights }),
    }),

  dataQuality: () =>
    request<{ id: number; symbol: string | null; kind: string; detail: string; detectedAt: string }[]>(
      "/api/data-quality",
    ),
};

export const attentionRank = (a: AttentionItem, b: AttentionItem) =>
  b.attentionScore - a.attentionScore;
