import type {
  EnablementPlan,
  EnablementResponse,
  GenerateOrchestratorResponse,
  ToolSummary,
} from "./types";

// In dev we call the FastAPI backend directly (CORS configured server-side
// in ui/api/server.py). Going through Next.js's dev-server proxy works for
// short paths but its built-in timeout (~30s) kills slow live-mode calls.
// Override with NEXT_PUBLIC_API_BASE_URL if your backend lives elsewhere.
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

// Live-mode runs can take 30–90 seconds. The browser fetch has no default
// timeout but we set one explicitly so a hung backend surfaces as an error
// instead of a tab that spins forever.
const REQUEST_TIMEOUT_MS = 120_000;

/**
 * Tiny fetch wrapper. Always points at the FastAPI backend directly.
 */
async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(
    () => controller.abort(),
    REQUEST_TIMEOUT_MS,
  );
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        if (body?.detail) detail = body.detail;
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(
        `Request timed out after ${REQUEST_TIMEOUT_MS / 1000}s. ` +
          "Live-mode runs that exceed this limit are usually a sign " +
          "the backend or LLM is stuck. Check the backend terminal.",
      );
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

export function listTools(): Promise<ToolSummary[]> {
  return fetchJson<ToolSummary[]>("/api/tools");
}

export function runEnablement(tools: string[]): Promise<EnablementResponse> {
  return fetchJson<EnablementResponse>("/api/enablement", {
    method: "POST",
    body: JSON.stringify({ tools }),
  });
}

export function generateOrchestrator(
  plan: EnablementPlan,
): Promise<GenerateOrchestratorResponse> {
  return fetchJson<GenerateOrchestratorResponse>("/api/generate-orchestrator", {
    method: "POST",
    body: JSON.stringify({ plan }),
  });
}

export function fetchHealth(): Promise<{
  ok: boolean;
  demo_mode: boolean;
  has_anthropic_key: boolean;
}> {
  return fetchJson("/api/health");
}
