import type { EnablementResponse } from "./types";

export const SESSION_KEY = "enable-ai-home-session";
const PENDING_TOOLS_KEY = "enable-ai-pending-tools";
const PENDING_KEYS_KEY = "enable-ai-pending-keys";

export type HomeSession = {
  bootId: string | null;
  selected: string[];
  selectedRole: string | null;
  result: EnablementResponse | null;
  selectedRecommendationId?: string | null;
  submittedRecommendationId?: string | null;
  enablementJobId?: string | null;
  enablementStartedAt?: number | null;
  buildJobId?: string | null;
};

export function writePendingKeys(keys: string[]): void {
  if (typeof window === "undefined") return;
  if (keys.length === 0) {
    localStorage.removeItem(PENDING_KEYS_KEY);
    return;
  }
  localStorage.setItem(PENDING_KEYS_KEY, JSON.stringify(keys));
}

export function readPendingKeys(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(PENDING_KEYS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((key): key is string => typeof key === "string");
  } catch {
    return [];
  }
}

export function writePendingTools(tools: string[]): void {
  if (typeof window === "undefined") return;
  if (tools.length === 0) {
    localStorage.removeItem(PENDING_TOOLS_KEY);
    return;
  }
  localStorage.setItem(PENDING_TOOLS_KEY, JSON.stringify(tools));
}

/** Tool names a previous page left for Settings. The handoff does not add to this list. */
export function readPendingTools(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(PENDING_TOOLS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as unknown;
      if (Array.isArray(parsed)) {
        const names = parsed.filter((name): name is string => typeof name === "string");
        if (names.length > 0) return names;
      }
    }
  } catch {
    // Fall through to this tab's workflow session.
  }
  return [];
}

export function readSession(): HomeSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as HomeSession;
    if (!parsed || !Array.isArray(parsed.selected)) return null;
    return parsed;
  } catch {
    return null;
  }
}
