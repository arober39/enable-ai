// TypeScript types mirroring the Pydantic schemas in `coordinator/schemas.py`
// and the FastAPI response shapes in `ui/api/server.py`.

export type CapabilityStatus = "covered" | "partial" | "gap" | "redundant";
export type RecommendationKind =
  | "use_native_ai"
  | "augment_with_custom_ai"
  | "consolidate"
  | "orchestrate";
export type Effort = "small" | "medium" | "large";

export interface ToolSummary {
  name: string;
  vendor: string;
  primary_use: string;
  categories: string[];
  has_native_ai: boolean;
  has_mcp_server: boolean;
  mcp_origin: string | null;
  notes: string | null;
}

export interface CapabilityFinding {
  capability: string;
  status: CapabilityStatus;
  tools_involved: string[];
  notes: string | null;
}

export interface Recommendation {
  id: string;
  kind: RecommendationKind;
  description: string;
  tools_affected: string[];
  effort: Effort;
  notes: string | null;
}

export interface OrchestratorPRPlan {
  branch: string;
  files_to_create: string[];
  mcp_servers_used: string[];
  mcp_servers_to_generate: string[];
  ai_configs_to_create: string[];
  env_vars_required: string[];
}

export interface PlanMetadata {
  generated_at: string;
  agent_name: string;
  agent_version: string;
  stack_file_hash: string;
  coordinator_session_id: string;
}

export interface EnablementPlan {
  department: string;
  summary: string;
  capability_coverage: CapabilityFinding[];
  recommendations: Recommendation[];
  orchestrator_pr_plan: OrchestratorPRPlan | null;
  metadata: PlanMetadata;
}

export interface EnablementResponse {
  mode: "demo" | "live";
  plan: EnablementPlan;
}

export interface OrchestratorRunResult {
  department: string;
  files_created: string[];
  mcp_servers_generated: string[];
  ai_configs_manifest_path: string;
  env_vars_required: string[];
  plan_reference: PlanMetadata;
}

export interface EnvVarHint {
  name: string;
  required: boolean;
  explanation: string;
}

export interface GenerateOrchestratorResponse {
  result: OrchestratorRunResult;
  output_path: string;
  env_var_hints: EnvVarHint[];
}

export interface ApiErrorBody {
  detail: string;
}
