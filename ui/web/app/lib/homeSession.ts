import type { ArtifactKind, EnablementResponse } from "./types";

export const SESSION_KEY = "enable-ai-home-session";
const PENDING_TOOLS_KEY = "enable-ai-pending-tools";
const PENDING_KEYS_KEY = "enable-ai-pending-keys";

export type HomeSession = {
  bootId: string | null;
  selected: string[];
  selectedRole: string | null;
  result: EnablementResponse | null;
  keysReady: boolean;
  lastArtifactKind: ArtifactKind | null;
  buildVersion: number;
  selectedRecommendationId?: string | null;
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

/** Tools whose keys the workflow is waiting on. Shared across tabs, with this tab's session as a fallback. */
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
  const session = readSession();
  if (session?.result && !session.keysReady) return session.selected;
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
