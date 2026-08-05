"use client";

import { useEffect, useState } from "react";
import { getPreferences, listWorkflows, runWorkflow } from "../lib/api";
import type { StepTrace, WorkflowRunResult } from "../lib/types";
import Spinner from "./Spinner";

const _FALLBACK_PAYLOAD = JSON.stringify(
  { example: "no workflow built yet — replace with your input" },
  null,
  2,
);

export default function RunInquiryPanel() {
  const [payloadText, setPayloadText] = useState(_FALLBACK_PAYLOAD);
  const [sampleSource, setSampleSource] = useState<"workflow" | "fallback">(
    "fallback",
  );
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<WorkflowRunResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // On mount, fetch the user's persisted workflow for the current role and
  // pre-fill the textarea from its sample_request. Falls back gracefully if
  // no workflow exists yet, the workflow predates the sample_request field,
  // or any of these calls fail.
  useEffect(() => {
    Promise.all([listWorkflows(), getPreferences()])
      .then(([workflows, prefs]) => {
        const wf = workflows.find((w) => w.role_id === prefs.selected_role);
        if (wf && wf.sample_request && Object.keys(wf.sample_request).length > 0) {
          setPayloadText(JSON.stringify(wf.sample_request, null, 2));
          setSampleSource("workflow");
        }
      })
      .catch(() => {
        /* non-fatal — keep the fallback payload */
      });
  }, []);

  const onRun = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    let parsed: Record<string, unknown>;
    try {
      const obj = JSON.parse(payloadText);
      if (typeof obj !== "object" || obj === null || Array.isArray(obj)) {
        throw new Error("payload must be a JSON object");
      }
      parsed = obj as Record<string, unknown>;
    } catch (e) {
      setError(`Invalid JSON: ${e instanceof Error ? e.message : String(e)}`);
      setLoading(false);
      return;
    }

    try {
      const resp = await runWorkflow(parsed);
      setResult(resp);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-neutral-700">
        Send a JSON payload to the interpreter. It executes the persisted
        <strong> WorkflowDefinition</strong> for your selected role —
        credentials pulled from your{" "}
        <a href="/settings" className="text-accent underline">
          Settings vault
        </a>
        , tool adapters from the reviewed registry.
      </p>

      <div className="rounded-lg border border-neutral-300 bg-white p-4">
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-neutral-600">
            Request payload (JSON)
            {sampleSource === "workflow" && (
              <span className="ml-2 text-neutral-400">
                · prefilled from your workflow's sample_request
              </span>
            )}
            {sampleSource === "fallback" && (
              <span className="ml-2 text-neutral-400">
                · no workflow sample available — paste your own input
              </span>
            )}
          </span>
          <textarea
            value={payloadText}
            onChange={(e) => setPayloadText(e.target.value)}
            rows={6}
            className="rounded border border-neutral-300 px-2 py-1 font-mono text-xs"
            disabled={loading}
            spellCheck={false}
          />
        </label>
        <div className="mt-3">
          <button
            type="button"
            onClick={onRun}
            disabled={loading || !payloadText.trim()}
            className={
              "inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-semibold text-white transition " +
              (loading || !payloadText.trim()
                ? "bg-neutral-400 cursor-not-allowed"
                : "bg-accent hover:bg-accent/90")
            }
          >
            {loading && <Spinner className="h-4 w-4" />}
            {loading ? "Running…" : "Run workflow"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-rose-300 bg-rose-50 p-3 text-sm text-rose-800">
          <strong>Error:</strong> {error}
        </div>
      )}

      {result && (
        <div
          className={
            "rounded-lg border p-4 " +
            (result.ok
              ? "border-emerald-300 bg-emerald-50"
              : "border-rose-300 bg-rose-50")
          }
        >
          <h3 className="mb-2 text-sm font-semibold">
            {result.ok ? "Workflow output" : "Workflow failed"}
          </h3>
          <pre className="overflow-x-auto rounded bg-white p-3 text-xs">
            {JSON.stringify(result.output, null, 2)}
          </pre>
          {result.error && (
            <p className="mt-2 text-xs text-rose-700">{result.error}</p>
          )}
          {result.trace.length > 0 && (
            <details className="mt-3">
              <summary className="cursor-pointer text-xs font-medium text-neutral-700">
                Execution trace ({result.trace.length} step
                {result.trace.length === 1 ? "" : "s"})
              </summary>
              <ol className="mt-2 space-y-1.5">
                {result.trace.map((t) => (
                  <TraceRow key={t.id} trace={t} />
                ))}
              </ol>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

function TraceRow({ trace }: { trace: StepTrace }) {
  const dur =
    new Date(trace.ended_at).getTime() - new Date(trace.started_at).getTime();
  const icon = trace.error ? "✗" : trace.skipped ? "⊘" : "✓";
  return (
    <li className="rounded border border-neutral-200 bg-white p-2 text-xs">
      <div className="flex items-center gap-2">
        <span>{icon}</span>
        <code className="font-mono">{trace.id}</code>
        <span className="text-neutral-500">·</span>
        <code className="font-mono text-neutral-700">
          {trace.tool}.{trace.action}
        </code>
        <span className="ml-auto text-neutral-500">
          {trace.skipped ? "skipped" : `${dur}ms`}
        </span>
      </div>
      {trace.error && (
        <p className="mt-1 text-rose-700">{trace.error}</p>
      )}
      {!trace.skipped && trace.output && (
        <details className="mt-1">
          <summary className="cursor-pointer text-[11px] text-neutral-500">
            output
          </summary>
          <pre className="mt-1 overflow-x-auto rounded bg-neutral-50 p-2 text-[11px]">
            {JSON.stringify(trace.output, null, 2)}
          </pre>
        </details>
      )}
    </li>
  );
}
