"use client";

import { useState } from "react";
import { generateOrchestrator } from "../lib/api";
import type {
  EnablementPlan,
  GenerateOrchestratorResponse,
} from "../lib/types";
import Spinner from "./Spinner";

interface Props {
  plan: EnablementPlan;
}

/**
 * Phase-5-in-the-UI: lets the user materialize the orchestrator tree on
 * disk from a plan they just received. The button is disabled until a
 * plan is available; on click it POSTs the plan to
 * /api/generate-orchestrator and renders the result + env-var checklist.
 */
export default function BuildOrchestrator({ plan }: Props) {
  const [result, setResult] = useState<GenerateOrchestratorResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);

  const run = async () => {
    setBuilding(true);
    setError(null);
    setResult(null);
    try {
      const resp = await generateOrchestrator(plan);
      setResult(resp);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBuilding(false);
    }
  };

  const disabled =
    plan.orchestrator_pr_plan == null || building;

  return (
    <div className="space-y-4">
      <button
        type="button"
        disabled={disabled}
        onClick={run}
        className={
          "inline-flex items-center gap-2 rounded-md px-4 py-2 font-semibold text-white transition " +
          (disabled
            ? "bg-neutral-400 cursor-not-allowed"
            : "bg-emerald-600 hover:bg-emerald-700")
        }
        title={
          plan.orchestrator_pr_plan == null
            ? "Plan has no orchestrator_pr_plan — re-run with that field populated."
            : "Write the orchestrator files to disk."
        }
      >
        {building && <Spinner className="h-4 w-4" />}
        {building ? "Writing files…" : "Build orchestrator from this plan"}
      </button>

      {error && (
        <div className="rounded-md border border-rose-300 bg-rose-50 p-4 text-sm text-rose-800">
          <strong>Error:</strong> {error}
        </div>
      )}

      {result && <BuildResult response={result} />}
    </div>
  );
}

function BuildResult({ response }: { response: GenerateOrchestratorResponse }) {
  const { result, output_path, env_var_hints } = response;
  const required = env_var_hints.filter((h) => h.required);
  const optional = env_var_hints.filter((h) => !h.required);

  return (
    <div className="space-y-5 rounded-lg border border-emerald-300 bg-emerald-50/40 p-5">
      <div>
        <h3 className="text-base font-semibold">
          ✓ Wrote {result.files_created.length} files
        </h3>
        <p className="mt-1 text-sm text-neutral-700">
          Output:{" "}
          <code className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-xs">
            {output_path}/
          </code>
        </p>
        {result.mcp_servers_generated.length > 0 && (
          <p className="mt-1 text-xs text-neutral-600">
            Generated MCP server stubs:{" "}
            <span className="font-mono">
              {result.mcp_servers_generated.join(", ")}
            </span>{" "}
            (vendor or community MCP server unavailable for these tools).
          </p>
        )}
      </div>

      <details>
        <summary className="cursor-pointer text-sm font-medium">
          Files written ({result.files_created.length})
        </summary>
        <ul className="mt-2 list-inside list-disc font-mono text-xs text-neutral-700">
          {result.files_created.map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      </details>

      {required.length > 0 && (
        <section>
          <h4 className="mb-2 text-sm font-semibold text-rose-800">
            Required environment variables
          </h4>
          <ul className="space-y-2">
            {required.map((h) => (
              <li
                key={h.name}
                className="rounded-md border border-rose-200 bg-white p-3"
              >
                <div className="flex items-center gap-2">
                  <code className="font-mono text-sm font-semibold">
                    {h.name}
                  </code>
                  <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-rose-800">
                    required
                  </span>
                </div>
                <p className="mt-1 text-xs text-neutral-700">{h.explanation}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {optional.length > 0 && (
        <section>
          <h4 className="mb-2 text-sm font-semibold text-neutral-700">
            Optional environment variables
          </h4>
          <ul className="space-y-2">
            {optional.map((h) => (
              <li
                key={h.name}
                className="rounded-md border border-neutral-200 bg-white p-3"
              >
                <div className="flex items-center gap-2">
                  <code className="font-mono text-sm">{h.name}</code>
                  <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-neutral-600">
                    optional
                  </span>
                </div>
                <p className="mt-1 text-xs text-neutral-700">{h.explanation}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h4 className="mb-2 text-sm font-semibold">Run it</h4>
        <p className="mb-2 text-xs text-neutral-700">
          The orchestrator is ready to import + invoke. From the repo root:
        </p>
        <pre className="overflow-x-auto rounded bg-neutral-900 p-3 text-xs text-neutral-100">
          {`# Set env vars (see above) in .env at the repo root
cp .env.example .env
# Then edit .env and fill in required keys

# Run the orchestrator against the built-in sample inquiry:
make -C ${output_path} run

# Or import handle_inquiry directly in your own code:
.venv/bin/python -c "
import asyncio
from ${output_path.replace(/\//g, ".")}.orchestrator import Inquiry, handle_inquiry
inq = Inquiry(subject='Refund?', body='Cancel my booking.', customer_id='CUST-001')
print(asyncio.run(handle_inquiry(inq)).model_dump_json(indent=2))
"`}
        </pre>
      </section>
    </div>
  );
}
