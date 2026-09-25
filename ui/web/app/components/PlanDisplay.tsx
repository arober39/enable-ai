"use client";

import type { EnablementResponse, CapabilityFinding } from "../lib/types";

const STATUS_STYLES: Record<CapabilityFinding["status"], string> = {
  covered: "bg-emerald-100 text-emerald-800",
  partial: "bg-amber-100 text-amber-800",
  gap: "bg-rose-100 text-rose-800",
  redundant: "bg-violet-100 text-violet-800",
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

      <p className="text-xs text-neutral-500">
        {plan.recommendations.length} recommendation(s) ready —
        pick one to hand to Grokbot.
      </p>

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
