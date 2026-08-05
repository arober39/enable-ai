"use client";

import { useState } from "react";
import { buildWorkflow, saveRecommendation } from "../lib/api";
import type {
  BuildResult,
  EnablementPlan,
  Recommendation,
} from "../lib/types";
import BuildArtifactView from "./BuildArtifactView";
import Spinner from "./Spinner";

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

/** What the build button reads as for each recommendation kind. */
const BUILD_BUTTON_LABEL: Record<Recommendation["kind"], string> = {
  use_native_ai: "Generate setup guide",
  augment_with_custom_ai: "Build workflow",
  consolidate: "Generate migration plan",
  orchestrate: "Build workflow",
};

/** One-line subhead explaining what gets produced for each kind. */
const KIND_SUBHEAD: Record<Recommendation["kind"], string> = {
  use_native_ai:
    "This kind produces a step-by-step configuration guide. No runtime workflow.",
  augment_with_custom_ai:
    "This kind produces a runtime workflow (JSON). The interpreter runs it when you send a request.",
  consolidate:
    "This kind produces a migration plan + checklist. No runtime workflow.",
  orchestrate:
    "This kind produces a runtime workflow (JSON). The interpreter runs it when you send a request.",
};

interface Props {
  plan: EnablementPlan;
  roleId: string;
  selectedTools: string[];
  onSaved: () => void;
  /**
   * Called after every build attempt (success or failure) with the
   * artifact_kind of the result, or `null` on failure. The page uses
   * this to (a) decide whether to show the Send-an-Inquiry surface
   * (only when the last build was a workflow) and (b) remount the
   * RunInquiryPanel so it picks up the just-persisted workflow's
   * sample_request.
   */
  onBuilt: (artifactKind: BuildResult["artifact_kind"] | null) => void;
}

export default function BuildOrchestrator({
  plan,
  roleId,
  selectedTools,
  onSaved,
  onBuilt,
}: Props) {
  const recs = plan.recommendations;
  const [selectedRecId, setSelectedRecId] = useState<string | null>(
    recs[0]?.id ?? null,
  );
  const [savingIds, setSavingIds] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<BuildResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);

  const selectedRec = recs.find((r) => r.id === selectedRecId) ?? null;
  const buildLabel = selectedRec
    ? BUILD_BUTTON_LABEL[selectedRec.kind]
    : "Build";
  const kindSubhead = selectedRec ? KIND_SUBHEAD[selectedRec.kind] : null;

  const onBuild = async () => {
    if (!selectedRecId) return;
    setBuilding(true);
    setError(null);
    setResult(null);
    try {
      const resp = await buildWorkflow(
        plan,
        selectedRecId,
        selectedTools,
        roleId,
      );
      setResult(resp);
      // Always notify the parent of what was last built. On failure
      // we send `null` so the page can clear any stale "workflow built"
      // state if it was carrying one.
      onBuilt(resp.ok ? resp.artifact_kind : null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBuilding(false);
    }
  };

  const onSave = async (rec: Recommendation) => {
    setSavingIds((prev) => new Set(prev).add(rec.id));
    try {
      await saveRecommendation({
        role_id: roleId,
        tools: selectedTools,
        plan_summary: plan.summary,
        recommendation: rec,
      });
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingIds((prev) => {
        const next = new Set(prev);
        next.delete(rec.id);
        return next;
      });
    }
  };

  if (recs.length === 0) {
    return (
      <div className="rounded-lg border border-neutral-300 bg-white p-4 text-sm text-neutral-500">
        Plan returned no recommendations — nothing to build.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-neutral-700">
        Pick one recommendation. What gets built depends on its{" "}
        <code className="rounded bg-neutral-100 px-1 py-0.5 font-mono text-xs">
          kind
        </code>
        :
      </p>
      <ul className="list-inside list-disc text-xs text-neutral-600">
        <li>
          <span className="font-semibold">orchestrate</span> /{" "}
          <span className="font-semibold">augment_with_custom_ai</span> →
          runtime <strong>workflow</strong> the interpreter executes
        </li>
        <li>
          <span className="font-semibold">use_native_ai</span> →{" "}
          <strong>setup guide</strong> for the vendor's feature
        </li>
        <li>
          <span className="font-semibold">consolidate</span> →{" "}
          <strong>migration plan</strong> with checklists
        </li>
      </ul>

      <ul className="space-y-2">
        {recs.map((r) => {
          const isSelected = r.id === selectedRecId;
          const isSaving = savingIds.has(r.id);
          return (
            <li
              key={r.id}
              className={
                "rounded-md border p-3 transition " +
                (isSelected
                  ? "border-accent bg-accent/5"
                  : "border-neutral-200 bg-white hover:border-neutral-300")
              }
            >
              <label className="flex cursor-pointer items-start gap-3">
                <input
                  type="radio"
                  name="rec-pick"
                  className="mt-1 h-4 w-4 accent-current text-accent"
                  checked={isSelected}
                  onChange={() => setSelectedRecId(r.id)}
                  disabled={building}
                />
                <div className="flex-1">
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
                  <p className="mt-1 text-sm text-neutral-700">
                    {r.description}
                  </p>
                  {r.tools_affected.length > 0 && (
                    <div className="mt-1 text-xs text-neutral-500">
                      tools affected: {r.tools_affected.join(", ")}
                    </div>
                  )}
                  {r.notes && (
                    <div className="mt-1 text-xs text-neutral-700">{r.notes}</div>
                  )}
                  <div className="mt-2">
                    <button
                      type="button"
                      onClick={() => onSave(r)}
                      disabled={isSaving || building}
                      className="text-xs text-accent hover:underline disabled:text-neutral-400 disabled:no-underline"
                    >
                      {isSaving ? "Saving…" : "Save for later"}
                    </button>
                  </div>
                </div>
              </label>
            </li>
          );
        })}
      </ul>

      <div className="space-y-2">
        {kindSubhead && (
          <p className="text-xs text-neutral-500">{kindSubhead}</p>
        )}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onBuild}
            disabled={!selectedRecId || building}
            className={
              "inline-flex items-center gap-2 rounded-md px-4 py-2 font-semibold text-white transition " +
              (!selectedRecId || building
                ? "bg-neutral-400 cursor-not-allowed"
                : "bg-emerald-600 hover:bg-emerald-700")
            }
          >
            {building && <Spinner className="h-4 w-4" />}
            {building ? "Running pipeline…" : buildLabel}
          </button>
          {building && (
            <span className="text-xs text-neutral-600">
              2-stage LLM pipeline — ~10-20 seconds.
            </span>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-rose-300 bg-rose-50 p-4 text-sm text-rose-800">
          <strong>Error:</strong> {error}
        </div>
      )}

      {result && <BuildArtifactView result={result} />}
    </div>
  );
}
