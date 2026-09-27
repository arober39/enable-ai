"use client";

import { useEffect, useState } from "react";
import type { AgentBlueprint, HitlKind } from "../lib/types";

interface Props {
  blueprint: AgentBlueprint;
}

const HITL_LABEL: Record<HitlKind, string> = {
  direct: "Direct",
  review: "Review",
  approve: "Approve",
  exception: "Exception handling",
};

export default function AgentBlueprintView({ blueprint }: Props) {
  const [chosen, setChosen] = useState<Set<string>>(
    () =>
      new Set(
        blueprint.build_targets
          .filter((target) => target.recommended)
          .map((target) => target.id),
      ),
  );

  useEffect(() => {
    setChosen(
      new Set(
        blueprint.build_targets
          .filter((target) => target.recommended)
          .map((target) => target.id),
      ),
    );
  }, [blueprint]);

  const toggleTarget = (id: string) => {
    setChosen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="mb-8 space-y-6">
      <div className="rounded-lg border border-neutral-300 bg-white p-4">
        <p className="text-sm leading-relaxed text-neutral-800">
          {blueprint.supervision_shift}
        </p>
      </div>

      <section>
        <h3 className="mb-1 text-base font-semibold">Current workflow</h3>
        <p className="text-sm text-neutral-700">{blueprint.current_workflow}</p>
      </section>

      <section>
        <h3 className="mb-2 text-base font-semibold">Pain points</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm text-neutral-700">
          {blueprint.pain_points.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
      </section>

      <section className="rounded-lg border border-neutral-300 bg-white p-4">
        <h3 className="mb-2 text-base font-semibold">Recommended agent</h3>
        <p className="text-sm text-neutral-700">
          <span className="font-medium">Trigger. </span>
          {blueprint.trigger}
        </p>
        <p className="mt-2 text-sm text-neutral-700">
          <span className="font-medium">Tools. </span>
          {blueprint.tools.length > 0 ? blueprint.tools.join(", ") : "None selected."}
        </p>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-neutral-700">
          {blueprint.agent_responsibilities.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </section>

      <section>
        <h3 className="mb-1 text-base font-semibold">Suggested architecture</h3>
        <p className="text-sm text-neutral-700">{blueprint.architecture}</p>
      </section>

      <section>
        <h3 className="mb-1 text-base font-semibold">Supervision Plan</h3>
        <p className="mb-2 text-sm text-neutral-600">
          Each task is AUTOMATE, ASSIST, AGENTIC, or HUMAN. A deterministic
          workflow is the recommendation when a fixed check is enough. You
          supervise with Direct, Review, Approve, or Exception handling.
        </p>
        {blueprint.assessments.length === 0 ? (
          <p className="text-sm text-neutral-600">
            No tasks confirmed. Check the work you actually do and run again.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-neutral-300 bg-white">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-neutral-50 text-xs uppercase tracking-wide text-neutral-500">
                <tr>
                  <th className="px-3 py-2 font-medium">Task</th>
                  <th className="px-3 py-2 font-medium">Class</th>
                  <th className="px-3 py-2 font-medium">AI</th>
                  <th className="px-3 py-2 font-medium">Human</th>
                  <th className="px-3 py-2 font-medium">HITL</th>
                </tr>
              </thead>
              <tbody>
                {blueprint.assessments.map((item) => (
                  <tr key={item.task_id} className="border-t border-neutral-200 align-top">
                    <td className="px-3 py-2">
                      <div className="font-medium">{item.label}</div>
                      <p className="mt-1 text-xs text-neutral-600">{item.why}</p>
                      {item.deterministic_preferred && (
                        <p className="mt-1 text-xs font-medium text-sky-800">
                          Deterministic workflow
                        </p>
                      )}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">{item.classification}</td>
                    <td className="px-3 py-2 text-neutral-700">{item.ai_steps}</td>
                    <td className="px-3 py-2 text-neutral-700">{item.human_steps}</td>
                    <td className="px-3 py-2">{HITL_LABEL[item.hitl]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <h3 className="mb-1 text-base font-semibold">Build this</h3>
        <p className="mb-2 text-sm text-neutral-600">
          This product feeds the systems below. It is the place to decide what
          agent to build.
        </p>
        <ul className="space-y-2">
          {blueprint.build_targets.map((target) => (
            <li
              key={target.id}
              className="rounded-lg border border-neutral-300 bg-white px-3 py-2"
            >
              <label className="flex cursor-pointer items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={chosen.has(target.id)}
                  aria-label={target.label}
                  onChange={() => toggleTarget(target.id)}
                />
                <span>
                  <span className="text-sm font-medium">{target.label}</span>
                  {target.recommended && (
                    <span className="ml-2 rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-emerald-800">
                      Recommended
                    </span>
                  )}
                  <span className="mt-1 block text-xs text-neutral-600">{target.why}</span>
                </span>
              </label>
            </li>
          ))}
        </ul>
      </section>

      <p className="text-xs text-neutral-500">{blueprint.autonomy_note}</p>
    </div>
  );
}
