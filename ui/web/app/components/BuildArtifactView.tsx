"use client";

import type {
  BuildResult,
  ConsolidationPlanArtifact,
  NativeAISetupArtifact,
  StageName,
  WorkflowDefinition,
} from "../lib/types";

const STAGE_LABELS: Record<StageName, string> = {
  research: "1. Research selected tools",
  plan: "2. Emit artifact",
  generate: "(unused)",
  verify: "(unused)",
};

/** Renders the pipeline result for any artifact kind. */
export default function BuildArtifactView({ result }: { result: BuildResult }) {
  const ringColor = result.ok ? "border-emerald-300" : "border-rose-300";
  const bgColor = result.ok ? "bg-emerald-50/40" : "bg-rose-50/40";

  return (
    <div className={`space-y-4 rounded-lg border ${ringColor} ${bgColor} p-4`}>
      <div>
        <h3 className="text-base font-semibold">
          {result.ok ? "✓ Pipeline succeeded" : "✗ Pipeline failed"}
        </h3>
        <ArtifactHeader result={result} />
      </div>

      <ol className="space-y-1.5">
        {result.stages.map((s) => (
          <li key={s.name} className="flex items-start gap-2 text-sm">
            <span className="mt-0.5">{s.ok ? "✓" : "✗"}</span>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium">{STAGE_LABELS[s.name]}</span>
                <span className="text-xs text-neutral-500">
                  {ms(
                    new Date(s.ended_at).getTime() -
                      new Date(s.started_at).getTime(),
                  )}
                </span>
              </div>
              {s.detail && (
                <p
                  className={
                    "text-xs " + (s.ok ? "text-neutral-600" : "text-rose-700")
                  }
                >
                  {s.detail}
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>

      {result.explanation && (
        <div>
          <h4 className="text-sm font-semibold text-neutral-700">
            What was built
          </h4>
          <p className="mt-1 text-sm">{result.explanation}</p>
        </div>
      )}

      {result.workflow && <WorkflowDetails workflow={result.workflow} envVars={result.env_vars_required} />}
      {result.native_ai_setup && <NativeAISetupDetails artifact={result.native_ai_setup} />}
      {result.consolidation_plan && <ConsolidationPlanDetails artifact={result.consolidation_plan} />}
    </div>
  );
}

function ArtifactHeader({ result }: { result: BuildResult }) {
  if (!result.ok) return null;
  if (result.artifact_kind === "workflow" && result.workflow) {
    return (
      <p className="mt-1 text-sm text-neutral-700">
        Persisted runtime workflow at{" "}
        <code className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-xs">
          agent-state/local/workflows/{result.workflow.role_id}.json
        </code>
      </p>
    );
  }
  if (result.artifact_kind === "native_ai_setup") {
    return (
      <p className="mt-1 text-sm text-neutral-700">
        Configuration guide — no runtime workflow. Follow the steps in
        the vendor's UI to enable the feature.
      </p>
    );
  }
  if (result.artifact_kind === "consolidation_plan") {
    return (
      <p className="mt-1 text-sm text-neutral-700">
        Migration plan — no runtime workflow. Execute the checklist to
        unify the two tools' coverage of this capability.
      </p>
    );
  }
  return null;
}

// ---------------------------------------------------------------------------
// Workflow details (existing rendering, lightly reformatted)
// ---------------------------------------------------------------------------

function WorkflowDetails({
  workflow,
  envVars,
}: {
  workflow: WorkflowDefinition;
  envVars: string[];
}) {
  return (
    <div className="space-y-3">
      {envVars.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-neutral-700">
            Env vars this workflow uses
          </h4>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {envVars.map((v) => (
              <li
                key={v}
                className="rounded bg-neutral-100 px-2 py-0.5 font-mono text-xs"
              >
                {v}
              </li>
            ))}
          </ul>
          <p className="mt-1 text-xs text-neutral-600">
            Make sure these are saved in{" "}
            <a href="/settings" className="text-accent underline">
              Settings → Credentials
            </a>
            .
          </p>
        </div>
      )}

      <details>
        <summary className="cursor-pointer text-sm font-medium">
          Workflow ({workflow.steps.length} step
          {workflow.steps.length === 1 ? "" : "s"})
        </summary>
        <ol className="mt-2 space-y-1 text-xs">
          {workflow.steps.map((s, i) => (
            <li
              key={s.id}
              className="rounded border border-neutral-200 bg-white p-2"
            >
              <div className="flex items-center gap-2">
                <span className="text-neutral-500">{i + 1}.</span>
                <code className="font-mono">{s.id}</code>
                <span className="text-neutral-500">·</span>
                <code className="font-mono text-neutral-700">
                  {s.tool}.{s.action}
                </code>
                {s.condition && (
                  <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] uppercase text-amber-800">
                    conditional
                  </span>
                )}
              </div>
            </li>
          ))}
        </ol>
      </details>
      <details>
        <summary className="cursor-pointer text-xs text-neutral-500">
          Raw WorkflowDefinition JSON
        </summary>
        <pre className="mt-1 overflow-x-auto rounded bg-neutral-900 p-3 text-[11px] text-neutral-100">
          {JSON.stringify(workflow, null, 2)}
        </pre>
      </details>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Native-AI setup details
// ---------------------------------------------------------------------------

function NativeAISetupDetails({ artifact }: { artifact: NativeAISetupArtifact }) {
  return (
    <div className="space-y-4">
      <div className="rounded border border-sky-200 bg-sky-50 p-3 text-sm">
        <div className="flex items-center gap-2">
          <span className="font-semibold">{artifact.feature_name}</span>
          <span className="text-xs text-neutral-500">in</span>
          <code className="rounded bg-white px-1.5 py-0.5 font-mono text-xs">
            {artifact.primary_tool}
          </code>
        </div>
        <p className="mt-1 text-sm text-neutral-700">{artifact.summary}</p>
      </div>

      <section>
        <h4 className="mb-2 text-sm font-semibold text-neutral-700">
          Setup steps ({artifact.setup_steps.length})
        </h4>
        <ol className="space-y-2">
          {artifact.setup_steps
            .slice()
            .sort((a, b) => a.order - b.order)
            .map((s) => (
              <li
                key={s.order}
                className="rounded border border-neutral-200 bg-white p-3 text-sm"
              >
                <div className="flex items-center gap-2">
                  <span className="rounded bg-neutral-200 px-1.5 py-0.5 font-mono text-[10px]">
                    {s.order}
                  </span>
                  <span className="font-medium">{s.title}</span>
                  {s.optional && (
                    <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] uppercase text-neutral-600">
                      optional
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-neutral-700">{s.detail}</p>
              </li>
            ))}
        </ol>
      </section>

      {artifact.connected_sources.length > 0 && (
        <section>
          <h4 className="mb-2 text-sm font-semibold text-neutral-700">
            Sources to connect
          </h4>
          <ul className="flex flex-wrap gap-1.5">
            {artifact.connected_sources.map((s) => (
              <li
                key={s}
                className="rounded bg-violet-100 px-2 py-0.5 text-xs text-violet-800"
              >
                {s}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h4 className="mb-2 text-sm font-semibold text-neutral-700">
          You'll know it's working when…
        </h4>
        <ul className="list-inside list-disc text-sm text-neutral-700">
          {artifact.success_criteria.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
      </section>

      {artifact.notes && (
        <p className="text-xs text-neutral-600">{artifact.notes}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Consolidation plan details
// ---------------------------------------------------------------------------

function ConsolidationPlanDetails({
  artifact,
}: {
  artifact: ConsolidationPlanArtifact;
}) {
  return (
    <div className="space-y-4">
      <div className="rounded border border-fuchsia-200 bg-fuchsia-50 p-3 text-sm">
        <div className="flex items-center gap-2">
          <code className="rounded bg-white px-1.5 py-0.5 font-mono text-xs">
            {artifact.source_tool}
          </code>
          <span>→</span>
          <code className="rounded bg-white px-1.5 py-0.5 font-mono text-xs">
            {artifact.target_tool}
          </code>
        </div>
        <p className="mt-1 text-sm text-neutral-700">{artifact.summary}</p>
      </div>

      <section>
        <h4 className="mb-2 text-sm font-semibold text-neutral-700">
          Items to migrate ({artifact.items_to_migrate.length})
        </h4>
        <ul className="space-y-2">
          {artifact.items_to_migrate.map((item, i) => (
            <li
              key={i}
              className="rounded border border-neutral-200 bg-white p-3 text-sm"
            >
              <div className="flex items-center gap-2 text-xs text-neutral-500">
                <code className="font-mono">{item.source}</code>
                <span>→</span>
                <code className="font-mono">{item.target}</code>
              </div>
              <div className="mt-0.5 font-medium">{item.name}</div>
              <p className="mt-1 text-xs text-neutral-700">{item.method}</p>
              {item.notes && (
                <p className="mt-1 text-[11px] text-neutral-500">{item.notes}</p>
              )}
            </li>
          ))}
        </ul>
      </section>

      {artifact.pre_migration_checklist.length > 0 && (
        <ChecklistSection
          title="Before you start"
          items={artifact.pre_migration_checklist}
        />
      )}
      {artifact.post_migration_checklist.length > 0 && (
        <ChecklistSection
          title="After migration"
          items={artifact.post_migration_checklist}
        />
      )}

      {artifact.risks.length > 0 && (
        <section>
          <h4 className="mb-2 text-sm font-semibold text-rose-800">Risks</h4>
          <ul className="list-inside list-disc text-sm text-rose-900">
            {artifact.risks.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </section>
      )}

      {artifact.notes && (
        <p className="text-xs text-neutral-600">{artifact.notes}</p>
      )}
    </div>
  );
}

function ChecklistSection({ title, items }: { title: string; items: string[] }) {
  return (
    <section>
      <h4 className="mb-2 text-sm font-semibold text-neutral-700">{title}</h4>
      <ul className="space-y-1 text-sm">
        {items.map((c, i) => (
          <li key={i} className="flex items-start gap-2">
            <span className="mt-0.5 text-neutral-400">☐</span>
            <span>{c}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ms(d: number): string {
  if (d < 1000) return `${d}ms`;
  return `${(d / 1000).toFixed(1)}s`;
}
