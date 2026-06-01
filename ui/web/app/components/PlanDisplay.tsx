"use client";

import type { EnablementResponse, CapabilityFinding, Recommendation } from "../lib/types";

const STATUS_STYLES: Record<CapabilityFinding["status"], string> = {
  covered: "bg-emerald-100 text-emerald-800",
  partial: "bg-amber-100 text-amber-800",
  gap: "bg-rose-100 text-rose-800",
  redundant: "bg-violet-100 text-violet-800",
};

const KIND_STYLES: Record<Recommendation["kind"], string> = {
  use_native_ai: "bg-sky-100 text-sky-800",
  augment_with_custom_ai: "bg-indigo-100 text-indigo-800",
  consolidate: "bg-fuchsia-100 text-fuchsia-800",
  orchestrate: "bg-emerald-100 text-emerald-800",
};

const EFFORT_LABEL: Record<Recommendation["effort"], string> = {
  small: "S",
  medium: "M",
  large: "L",
};

interface Props {
  response: EnablementResponse;
}

export default function PlanDisplay({ response }: Props) {
  const { mode, plan } = response;
  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-neutral-300 bg-white p-4">
        <div className="mb-1 flex items-center gap-2">
          <span
            className={
              "rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide " +
              (mode === "live"
                ? "bg-emerald-100 text-emerald-800"
                : "bg-amber-100 text-amber-800")
            }
          >
            {mode} mode
          </span>
          <span className="text-xs text-neutral-500">
            agent: {plan.metadata.agent_name} v{plan.metadata.agent_version}
          </span>
        </div>
        <h2 className="mb-2 text-lg font-semibold">Plan summary</h2>
        <p className="text-sm leading-relaxed text-neutral-700">{plan.summary}</p>
      </div>

      <section>
        <h3 className="mb-2 text-base font-semibold">
          Capability findings ({plan.capability_coverage.length})
        </h3>
        <ul className="space-y-2">
          {plan.capability_coverage.map((f, i) => (
            <li
              key={i}
              className="rounded-md border border-neutral-200 bg-white p-3"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-sm">{f.capability}</span>
                <span
                  className={
                    "rounded px-2 py-0.5 text-xs font-semibold uppercase " +
                    STATUS_STYLES[f.status]
                  }
                >
                  {f.status}
                </span>
              </div>
              {f.tools_involved.length > 0 && (
                <div className="mt-1 text-xs text-neutral-500">
                  tools: {f.tools_involved.join(", ")}
                </div>
              )}
              {f.notes && (
                <div className="mt-1 text-xs text-neutral-700">{f.notes}</div>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3 className="mb-2 text-base font-semibold">
          Recommendations ({plan.recommendations.length})
        </h3>
        <ul className="space-y-2">
          {plan.recommendations.map((r) => (
            <li
              key={r.id}
              className="rounded-md border border-neutral-200 bg-white p-3"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-sm">{r.id}</span>
                <div className="flex items-center gap-1.5">
                  <span
                    className={
                      "rounded px-2 py-0.5 text-xs font-semibold uppercase " +
                      KIND_STYLES[r.kind]
                    }
                  >
                    {r.kind.replace(/_/g, " ")}
                  </span>
                  <span
                    className="rounded bg-neutral-200 px-1.5 py-0.5 text-[10px] font-bold"
                    title={`effort: ${r.effort}`}
                  >
                    {EFFORT_LABEL[r.effort]}
                  </span>
                </div>
              </div>
              <p className="mt-2 text-sm text-neutral-700">{r.description}</p>
              {r.tools_affected.length > 0 && (
                <div className="mt-1 text-xs text-neutral-500">
                  tools affected: {r.tools_affected.join(", ")}
                </div>
              )}
              {r.notes && (
                <div className="mt-1 text-xs text-neutral-700">{r.notes}</div>
              )}
            </li>
          ))}
        </ul>
      </section>

      {plan.orchestrator_pr_plan && (
        <section>
          <h3 className="mb-2 text-base font-semibold">Orchestrator PR plan</h3>
          <div className="rounded-md border border-neutral-200 bg-white p-3 text-sm">
            <div>
              <span className="font-medium">Branch:</span>{" "}
              <span className="font-mono">
                {plan.orchestrator_pr_plan.branch}
              </span>
            </div>
            <div className="mt-2">
              <span className="font-medium">MCP servers used:</span>{" "}
              {plan.orchestrator_pr_plan.mcp_servers_used.join(", ") || "—"}
            </div>
            <div>
              <span className="font-medium">MCP servers to generate:</span>{" "}
              {plan.orchestrator_pr_plan.mcp_servers_to_generate.join(", ") ||
                "—"}
            </div>
            <div>
              <span className="font-medium">AI Configs:</span>{" "}
              {plan.orchestrator_pr_plan.ai_configs_to_create.join(", ") || "—"}
            </div>
            <div>
              <span className="font-medium">Env vars required:</span>{" "}
              <span className="font-mono text-xs">
                {plan.orchestrator_pr_plan.env_vars_required.join(", ")}
              </span>
            </div>
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-neutral-600">
                {plan.orchestrator_pr_plan.files_to_create.length} files to
                create
              </summary>
              <ul className="mt-1 list-inside list-disc font-mono text-xs text-neutral-600">
                {plan.orchestrator_pr_plan.files_to_create.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            </details>
          </div>
        </section>
      )}

      <details className="text-xs">
        <summary className="cursor-pointer text-neutral-500">
          Raw plan JSON
        </summary>
        <pre className="mt-2 overflow-x-auto rounded bg-neutral-900 p-3 text-neutral-100">
          {JSON.stringify(plan, null, 2)}
        </pre>
      </details>
    </div>
  );
}
