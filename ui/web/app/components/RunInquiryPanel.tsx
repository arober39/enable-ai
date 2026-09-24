"use client";

import { useEffect, useState } from "react";
import {
  getPreferences,
  listOutcomes,
  listWorkflows,
  outcomeSummary,
  rollbackRecommendation,
  runWorkflow,
  workflowCredentials,
} from "../lib/api";
import { writePendingKeys } from "../lib/homeSession";
import type { RequiredCredential } from "../lib/types";
import type {
  OutcomeRecord,
  RecommendationMetrics,
  StepTrace,
  WorkflowRunResult,
} from "../lib/types";
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
  const [outcomes, setOutcomes] = useState<OutcomeRecord[]>([]);
  const [metrics, setMetrics] = useState<RecommendationMetrics[]>([]);
  const [roleId, setRoleId] = useState<string | null>(null);
  const [rollingBack, setRollingBack] = useState<string | null>(null);
  const [requiredKeys, setRequiredKeys] = useState<RequiredCredential[]>([]);
  const [missingKeys, setMissingKeys] = useState<string[]>([]);
  const [checkingKeys, setCheckingKeys] = useState(false);

  // On mount, fetch the user's persisted workflow for the current role and
  // pre-fill the textarea from its sample_request. Falls back gracefully if
  // no workflow exists yet, the workflow predates the sample_request field,
  // or any of these calls fail.
  useEffect(() => {
    Promise.all([listWorkflows(), getPreferences()])
      .then(([workflows, prefs]) => {
        setRoleId(prefs.selected_role);
        refreshMeasure(prefs.selected_role);
        refreshKeys(prefs.selected_role).catch(() => {
          /* the run button still rechecks */
        });
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

  const refreshKeys = async (forRole: string | null) => {
    const report = await workflowCredentials(forRole ?? undefined);
    setRequiredKeys(report.required);
    setMissingKeys(report.missing);
    writePendingKeys(report.missing);
    return report.missing;
  };

  const refreshMeasure = (forRole: string | null) => {
    listOutcomes()
      .then((recorded) => {
        setOutcomes(
          forRole ? recorded.filter((row) => row.role_id === forRole) : recorded,
        );
      })
      .catch(() => {
        /* history is optional; the run form still works */
      });
    outcomeSummary()
      .then((rows) => {
        setMetrics(forRole ? rows.filter((row) => row.role_id === forRole) : rows);
      })
      .catch(() => {
        /* rates are optional */
      });
  };

  const onRollback = async (recommendationId: string) => {
    if (!roleId) return;
    setRollingBack(recommendationId);
    setError(null);
    try {
      await rollbackRecommendation(recommendationId, roleId);
      setResult(null);
      refreshMeasure(roleId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRollingBack(null);
    }
  };

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
      const stillMissing = await refreshKeys(roleId);
      if (stillMissing.length > 0) {
        setError(null);
        return;
      }
      const resp = await runWorkflow(parsed);
      setResult(resp);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      refreshMeasure(roleId);
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
        {requiredKeys.length > 0 && missingKeys.length > 0 && (
          <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm">
            <p className="font-semibold text-amber-950">
              Add these keys before running
            </p>
            <p className="mt-1 text-amber-950">
              This workflow reads them from the vault. Open{" "}
              <a href="/settings" className="font-medium underline">
                Settings
              </a>
              , add each one, then come back and check again.
            </p>
            <ul className="mt-2 space-y-1 font-mono text-xs">
              {requiredKeys
                .filter((row) => missingKeys.includes(row.key))
                .map((row) => (
                  <li key={`${row.tool}:${row.key}`}>
                    {row.tool} → {row.key}
                  </li>
                ))}
            </ul>
            <button
              type="button"
              onClick={() => {
                setCheckingKeys(true);
                refreshKeys(roleId)
                  .catch((e: Error) => setError(e.message))
                  .finally(() => setCheckingKeys(false));
              }}
              disabled={checkingKeys}
              className="mt-3 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-white disabled:bg-neutral-400"
            >
              {checkingKeys ? "Checking Settings…" : "I've added these in Settings"}
            </button>
          </div>
        )}
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

      <div className="rounded-lg border border-neutral-300 bg-white p-4">
        <h3 className="mb-2 text-sm font-semibold">Measured outcomes</h3>
        <p className="mb-3 text-xs text-neutral-500">
          Per recommendation: run success, error rate, and how often tool
          calls were real API calls rather than stubs. Rollback uninstalls
          the runtime for that recommendation.
        </p>
        {metrics.length > 0 && (
          <ul className="mb-4 space-y-2">
            {metrics.map((row) => {
              const key = `${row.role_id}:${row.recommendation_id ?? "none"}`;
              const pct = (rate: number) => `${Math.round(rate * 100)}%`;
              return (
                <li key={key} className="rounded border border-neutral-200 p-2 text-xs">
                  <div className="flex flex-wrap items-center gap-2">
                    <code className="font-mono">
                      {row.recommendation_id ?? "unscoped"}
                    </code>
                    <span className="text-neutral-600">
                      {row.runs} run{row.runs === 1 ? "" : "s"} · success{" "}
                      {pct(row.success_rate)} · errors {pct(row.error_rate)} ·
                      real calls {pct(row.real_call_rate)} · escalations{" "}
                      {pct(row.escalation_rate)}
                    </span>
                    {row.installed && row.recommendation_id && (
                      <button
                        type="button"
                        className="ml-auto rounded border border-rose-300 px-2 py-0.5 text-rose-800 hover:bg-rose-50 disabled:opacity-50"
                        disabled={rollingBack === row.recommendation_id}
                        onClick={() => onRollback(row.recommendation_id as string)}
                      >
                        {rollingBack === row.recommendation_id
                          ? "Rolling back…"
                          : "Roll back"}
                      </button>
                    )}
                  </div>
                  {row.rollbacks > 0 && (
                    <p className="mt-1 text-neutral-500">
                      Rolled back {row.rollbacks} time
                      {row.rollbacks === 1 ? "" : "s"}.
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        {outcomes.length === 0 ? (
          <p className="text-xs text-neutral-500">No runs recorded yet.</p>
        ) : (
          <ul className="space-y-2">
            {outcomes.slice(0, 8).map((outcome) => (
              <li
                key={outcome.id}
                className="rounded border border-neutral-200 p-2 text-xs"
              >
                <div className="flex items-center gap-2">
                  <span>
                    {outcome.status === "ok"
                      ? "✓"
                      : outcome.status === "rolled_back"
                        ? "↩"
                        : "✗"}
                  </span>
                  <code className="font-mono">{outcome.id}</code>
                  {outcome.recommendation_id && (
                    <span className="text-neutral-500">
                      · {outcome.recommendation_id}
                    </span>
                  )}
                  <span className="ml-auto text-neutral-500">
                    {outcome.duration_ms}ms
                  </span>
                </div>
                {outcome.error && (
                  <p className="mt-1 text-rose-700">{outcome.error}</p>
                )}
                {outcome.step_summaries.length > 0 && (
                  <p className="mt-1 font-mono text-[11px] text-neutral-600">
                    {outcome.step_summaries
                      .map((step) => {
                        const mode = step.mode ? ` (${step.mode})` : "";
                        return `${step.tool}.${step.action}${mode}`;
                      })
                      .join(" → ")}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
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
