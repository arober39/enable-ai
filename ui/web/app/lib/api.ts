import type {
  CredentialRevealResponse,
  CredentialSummary,
  RequiredCredentials,
  EnablementPlan,
  EnablementResponse,
  GeneratorRunResult,
  DeclaredStack,
  OrchestratorResponse,
  OutcomeRecord,
  RecommendationMetrics,
  Recommendation,
  RoleSummary,
  RunOrchestratorRequest,
  SavedRecommendation,
  ToolSummary,
  UserPreferences,
  WorkflowDefinition,
  BuildResult,
  WorkflowRunResult,
} from "./types";

// In dev we call the FastAPI backend directly (CORS configured server-side
// in ui/api/server.py). Going through Next.js's dev-server proxy works for
// short paths but its built-in timeout (~30s) kills slow live-mode calls.
// Override with NEXT_PUBLIC_API_BASE_URL if your backend lives elsewhere.
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

// A plan or a workflow build often takes about 30 seconds and should keep
// its loading UI up the whole time. The browser fetch has no default
// timeout; this limit only turns a hung backend into an error.
const REQUEST_TIMEOUT_MS = 120_000;

/** HTTP failure from the FastAPI backend. `status` is the response code. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

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
      throw new ApiError(res.status, detail);
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

export function researchTool(name: string): Promise<ToolSummary> {
  return fetchJson<ToolSummary>("/api/tools/research", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function deleteCachedTool(name: string): Promise<{ removed: boolean }> {
  return fetchJson<{ removed: boolean }>(
    `/api/tools/cache/${encodeURIComponent(name)}`,
    { method: "DELETE" },
  );
}

export function runEnablement(
  tools: string[],
  role?: string,
): Promise<EnablementResponse> {
  return fetchJson<EnablementResponse>("/api/enablement", {
    method: "POST",
    body: JSON.stringify({ tools, ...(role ? { role } : {}) }),
  });
}

export function listRoles(): Promise<RoleSummary[]> {
  return fetchJson<RoleSummary[]>("/api/roles");
}

export function researchRole(name: string): Promise<RoleSummary> {
  return fetchJson<RoleSummary>("/api/roles/research", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function deleteCachedRole(id: string): Promise<{ removed: boolean }> {
  return fetchJson<{ removed: boolean }>(
    `/api/roles/cache/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
}

export function getPreferences(): Promise<UserPreferences> {
  return fetchJson<UserPreferences>("/api/preferences");
}

export function setSelectedRole(role: string): Promise<UserPreferences> {
  return fetchJson<UserPreferences>("/api/preferences/role", {
    method: "PUT",
    body: JSON.stringify({ role }),
  });
}

export function generateOrchestrator(
  plan: EnablementPlan,
  selectedRecommendationId: string,
  role?: string,
): Promise<GeneratorRunResult> {
  return fetchJson<GeneratorRunResult>("/api/generate-orchestrator", {
    method: "POST",
    body: JSON.stringify({
      plan,
      selected_recommendation_id: selectedRecommendationId,
      ...(role ? { role } : {}),
    }),
  });
}

// ----- Saved recommendations -----

export function listSavedRecommendations(): Promise<SavedRecommendation[]> {
  return fetchJson<SavedRecommendation[]>("/api/saved-recommendations");
}

export function saveRecommendation(args: {
  role_id: string;
  tools: string[];
  plan_summary: string;
  recommendation: Recommendation;
}): Promise<SavedRecommendation> {
  return fetchJson<SavedRecommendation>("/api/saved-recommendations", {
    method: "POST",
    body: JSON.stringify(args),
  });
}

export function deleteSavedRecommendation(
  id: string,
): Promise<{ removed: boolean }> {
  return fetchJson<{ removed: boolean }>(
    `/api/saved-recommendations/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
}

export function fetchHealth(): Promise<{
  ok: boolean;
  demo_mode: boolean;
  has_anthropic_key: boolean;
  boot_id: string;
}> {
  return fetchJson("/api/health");
}

// ----- Credentials -----

export async function synthesizeSpeech(text: string): Promise<Blob> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}/api/speech`, {
      method: "POST",
      signal: controller.signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        if (body?.detail) detail = String(body.detail);
      } catch {
        /* audio errors may not be JSON */
      }
      throw new ApiError(res.status, detail);
    }
    return await res.blob();
  } finally {
    clearTimeout(timeoutId);
  }
}

export function workflowCredentials(role?: string): Promise<RequiredCredentials> {
  const query = role ? `?role=${encodeURIComponent(role)}` : "";
  return fetchJson<RequiredCredentials>(`/api/credentials/for-workflow${query}`);
}

export function requiredCredentials(tools: string[]): Promise<RequiredCredentials> {
  const query = encodeURIComponent(tools.join(","));
  return fetchJson<RequiredCredentials>(`/api/credentials/required?tools=${query}`);
}

export function listCredentials(): Promise<CredentialSummary[]> {
  return fetchJson<CredentialSummary[]>("/api/credentials");
}

export function upsertCredential(
  key: string,
  value: string,
): Promise<CredentialSummary> {
  return fetchJson<CredentialSummary>(`/api/credentials/${encodeURIComponent(key)}`, {
    method: "PUT",
    body: JSON.stringify({ value }),
  });
}

export function deleteCredential(key: string): Promise<{ deleted: boolean }> {
  return fetchJson<{ deleted: boolean }>(
    `/api/credentials/${encodeURIComponent(key)}`,
    { method: "DELETE" },
  );
}

export function revealCredential(
  key: string,
): Promise<CredentialRevealResponse> {
  return fetchJson<CredentialRevealResponse>(
    `/api/credentials/${encodeURIComponent(key)}/reveal`,
  );
}

// ----- Run orchestrator -----

export function runOrchestrator(
  req: RunOrchestratorRequest,
): Promise<OrchestratorResponse> {
  return fetchJson<OrchestratorResponse>("/api/run-orchestrator", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

// ----- Phase 2.1 workflow endpoints (the new primary path) -----

export function buildWorkflow(
  plan: EnablementPlan,
  selectedRecommendationId: string,
  tools: string[],
  role?: string,
): Promise<BuildResult> {
  return fetchJson<BuildResult>("/api/build-workflow", {
    method: "POST",
    body: JSON.stringify({
      plan,
      selected_recommendation_id: selectedRecommendationId,
      tools,
      ...(role ? { role } : {}),
    }),
  });
}

export function runWorkflow(
  payload: Record<string, unknown>,
  role?: string,
): Promise<WorkflowRunResult> {
  return fetchJson<WorkflowRunResult>("/api/run-workflow", {
    method: "POST",
    body: JSON.stringify({ payload, ...(role ? { role } : {}) }),
  });
}

export function getDeclaredStack(roleId: string): Promise<DeclaredStack> {
  return fetchJson<DeclaredStack>(`/api/stacks/${encodeURIComponent(roleId)}`);
}

export function listOutcomes(): Promise<OutcomeRecord[]> {
  return fetchJson<OutcomeRecord[]>("/api/outcomes");
}

export function outcomeSummary(): Promise<RecommendationMetrics[]> {
  return fetchJson<RecommendationMetrics[]>("/api/outcomes/summary");
}

export function rollbackRecommendation(
  recommendationId: string,
  role?: string,
): Promise<OutcomeRecord> {
  return fetchJson<OutcomeRecord>("/api/rollback", {
    method: "POST",
    body: JSON.stringify({
      recommendation_id: recommendationId,
      ...(role ? { role } : {}),
    }),
  });
}

export type GrokbotHandoffText = {
  name: string;
  title: string;
  description: string;
  placement: string;
  action: "create" | "update" | "create_fallback";
  existing_bot_name: string | null;
};

export function fetchGrokbotHandoff(args: {
  recommendation_id: string;
  kind: string;
  description: string;
  notes: string | null;
  role_name: string;
  tools: string[];
}): Promise<GrokbotHandoffText> {
  return fetchJson<GrokbotHandoffText>("/api/grokbot/handoff", {
    method: "POST",
    body: JSON.stringify(args),
  });
}

export function listWorkflows(): Promise<WorkflowDefinition[]> {
  return fetchJson<WorkflowDefinition[]>("/api/workflows");
}

export function deleteWorkflow(roleId: string): Promise<{ removed: boolean }> {
  return fetchJson<{ removed: boolean }>(
    `/api/workflows/${encodeURIComponent(roleId)}`,
    { method: "DELETE" },
  );
}
