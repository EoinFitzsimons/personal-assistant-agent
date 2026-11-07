export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type PlanItem = {
  id: number;
  kind: "meeting" | "task" | "commitment" | "follow_up" | "workout" | "meal";
  title: string;
  details: string;
  start: string | null;
  end: string | null;
  duration_min: number;
  priority: number;
  reason: string;
  source_provider: string;
  source_link: string;
  owed_to: string;
  confidence: number;
  status: "proposed" | "approved" | "removed" | "inbox" | "unscheduled";
  fixed: boolean;
  tag: string;
};

export type ChatMessage = { id: number; role: "user" | "assistant"; content: string; created_at: string };

export type Plan = {
  id: number;
  date: string;
  status: "gathering" | "planning" | "ready" | "failed";
  error: string;
  summary: {
    sources?: string[];
    counts?: Record<string, number>;
    health?: Record<string, number>;
    errors?: string[];
  };
  items: PlanItem[];
  messages: ChatMessage[];
};

export type Connection = {
  provider: string;
  name: string;
  category: "work" | "health";
  configured: boolean;
  connected: boolean;
  account: string;
};

export type Settings = {
  name: string;
  timezone: string;
  working_hours: { start: string; end: string };
  weekly_goals: string[];
  vip_people: string[];
  vip_channels: string[];
  workout: { preferred_time: "morning" | "midday" | "evening"; duration_min: number; types: string[] };
  diet: { preferences: string[]; avoid: string[] };
  meals: { breakfast: string; lunch: string; dinner: string };
  health_consent: boolean;
  demo_mode: boolean;
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function getToken(): string | null {
  return typeof window === "undefined" ? null : localStorage.getItem("token");
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem("token", token);
  else localStorage.removeItem("token");
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth")) {
    setToken(null);
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- full reload clears client state on logout
    window.location.assign("/login");
  }
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, message);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}
