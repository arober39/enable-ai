"use client";

import { useState } from "react";
import { saveRecommendation } from "../lib/api";
import type { EnablementPlan, Recommendation } from "../lib/types";

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
  plan: EnablementPlan;
  roleId: string;
  selectedTools: string[];
  onSaved: () => void;
  selectedRecommendationId: string | null;
  onSelectRecommendation: (id: string) => void;
}

export default function BuildOrchestrator({
  plan,
  roleId,
  selectedTools,
  onSaved,
  selectedRecommendationId,
  onSelectRecommendation,
}: Props) {
  const recs = plan.recommendations;
  const selectedRecId = recs.some((rec) => rec.id === selectedRecommendationId)
    ? selectedRecommendationId
    : null;
  const [savingIds, setSavingIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

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
        Plan returned no recommendations.
      </div>
    );
  }

  return (
    <div className="space-y-4">
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
                  onChange={() => onSelectRecommendation(r.id)}
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
                      disabled={isSaving}
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
      {error && (
        <p className="text-sm text-rose-700">
          <strong>Error:</strong> {error}
        </p>
      )}
    </div>
  );
}
