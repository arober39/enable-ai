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

function isRelationship(finding: CapabilityFinding): boolean {
  return finding.focus === "relationship" || finding.tools_involved.length > 1;
}

export default function PlanDisplay({ response }: Props) {
  const { mode, plan } = response;
  const relationships = plan.capability_coverage.filter(isRelationship);
  const individuals = plan.capability_coverage.filter(
    (finding) => !isRelationship(finding),
  );
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

      {relationships.length > 0 && (
        <section>
          <h3 className="mb-1 text-base font-semibold">
            How these tools work together
          </h3>
          <p className="mb-2 text-sm text-neutral-600">
            Relationship and combined workflow for the tools in this plan.
          </p>
          <ul className="space-y-2">
            {relationships.map((finding, index) => (
              <FindingCard key={`rel-${index}`} finding={finding} prominent />
            ))}
          </ul>
        </section>
      )}

      <section>
        <h3 className="mb-2 text-base font-semibold">
          Capability findings ({individuals.length})
        </h3>
        <ul className="space-y-2">
          {individuals.map((finding, index) => (
            <FindingCard key={`tool-${index}`} finding={finding} />
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

function FindingCard({
  finding,
  prominent = false,
}: {
  finding: CapabilityFinding;
  prominent?: boolean;
}) {
  return (
    <li
      className={
        "rounded-md border p-3 " +
        (prominent
          ? "border-accent/40 bg-accent/5"
          : "border-neutral-200 bg-white")
      }
    >
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-semibold">{finding.capability}</span>
        <span
          className={
            "shrink-0 rounded px-2 py-0.5 text-xs font-semibold uppercase " +
            STATUS_STYLES[finding.status]
          }
        >
          {finding.status}
        </span>
      </div>
      {finding.tools_involved.length > 0 && (
        <div className="mt-1 text-xs text-neutral-500">
          tools: {finding.tools_involved.join(", ")}
        </div>
      )}
      {finding.notes && (
        <div className="mt-2 whitespace-pre-line text-sm leading-relaxed text-neutral-800">
          {finding.notes}
        </div>
      )}
    </li>
  );
}
