// TypeScript types mirroring the Pydantic schemas in `coordinator/schemas.py`
// and the FastAPI response shapes in `ui/api/server.py`.

export type CapabilityStatus = "covered" | "partial" | "gap" | "redundant";
export type RecommendationKind =
  | "use_native_ai"
  | "augment_with_custom_ai"
  | "consolidate"
  | "orchestrate";
export type Effort = "small" | "medium" | "large";

export type ToolSource = "seed" | "researched";

export interface ToolSummary {
  name: string;
  vendor: string;
  categories: string[];
  has_native_ai: boolean;
  has_mcp_server: boolean;
  mcp_origin: string | null;
  notes: string | null;
  source: ToolSource;
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

// ----- Phase 2.1 workflow DAG -----

export interface EqualityCondition {
  op: "eq" | "neq";
  left: unknown;
  right: unknown;
}

export interface WorkflowStep {
  id: string;
  tool: string;
  action: string;
  params: Record<string, unknown>;
  condition: EqualityCondition | null;
  output_key: string | null;
  description: string | null;
}

export interface WorkflowDefinition {
  name: string;
  description: string;
  role_id: string;
  recommendation_id: string;
  tools_used: string[];
  env_vars_required: string[];
  request_schema: Record<string, unknown>;
  response_schema: Record<string, unknown>;
  sample_request: Record<string, unknown>;
  steps: WorkflowStep[];
}

export type ArtifactKind =
  | "workflow"
  | "native_ai_setup"
  | "consolidation_plan"
  | "none";

export interface SetupStep {
  order: number;
  title: string;
  detail: string;
  optional: boolean;
}

export interface NativeAISetupArtifact {
  kind: "native_ai_setup";
  name: string;
  summary: string;
  primary_tool: string;
  feature_name: string;
  setup_steps: SetupStep[];
  connected_sources: string[];
  success_criteria: string[];
  notes: string | null;
}

export interface MigrationItem {
  name: string;
  source: string;
  target: string;
  method: string;
  notes: string | null;
}

export interface ConsolidationPlanArtifact {
  kind: "consolidation_plan";
  name: string;
  summary: string;
  source_tool: string;
  target_tool: string;
  items_to_migrate: MigrationItem[];
  pre_migration_checklist: string[];
  post_migration_checklist: string[];
  risks: string[];
  notes: string | null;
}

export interface BuildResult {
  ok: boolean;
  stages: StageResult[];
  artifact_kind: ArtifactKind;
  workflow: WorkflowDefinition | null;
  native_ai_setup: NativeAISetupArtifact | null;
  consolidation_plan: ConsolidationPlanArtifact | null;
  explanation: string | null;
  env_vars_required: string[];
}


export interface StepTrace {
  id: string;
  tool: string;
  action: string;
  skipped: boolean;
  started_at: string;
  ended_at: string;
  params_resolved: Record<string, unknown>;
  output: Record<string, unknown> | null;
  error: string | null;
}

export interface WorkflowRunResult {
  ok: boolean;
  output: Record<string, unknown>;
  trace: StepTrace[];
  error: string | null;
}

// ----- Phase 1.4 generator pipeline (legacy) -----

export type StageName = "research" | "plan" | "generate" | "verify";

export interface StageResult {
  name: StageName;
  ok: boolean;
  started_at: string;
  ended_at: string;
  detail: string | null;
  output_preview: string | null;
}

export interface CodeFilePlan {
  path: string;
  purpose: string;
  key_exports: string[];
}

export interface CodePlan {
  summary: string;
  files: CodeFilePlan[];
  env_vars_required: string[];
  request_input_schema: Record<string, unknown>;
  response_output_schema: Record<string, unknown>;
}

export interface GeneratorRunResult {
  ok: boolean;
  output_path: string;
  stages: StageResult[];
  plan: CodePlan | null;
  explanation: string | null;
  env_vars_required: string[];
}

// ----- Saved-for-later recommendations -----

export interface SavedRecommendation {
  id: string;
  role_id: string;
  tools: string[];
  plan_summary: string;
  recommendation: Recommendation;
  saved_at: string;
}

export interface ApiErrorBody {
  detail: string;
}

// ----- Role registry + user preferences -----

export interface RoleSummary {
  id: string;
  display_name: string;
  department: string;
  description: string;
  capabilities: string[];
}

export interface UserPreferences {
  selected_role: string;
}

// ----- Credential vault (UI-managed, Convex-style) -----

export interface CredentialSummary {
  key: string;
  masked_value: string;
}

export interface CredentialRevealResponse {
  key: string;
  value: string;
}

// ----- Run orchestrator (free-form payload → generated handle_request) -----

export interface RunOrchestratorRequest {
  payload: Record<string, unknown>;
  role?: string;
}

export type OrchestratorResponse = Record<string, unknown>;
