"use client";

import { useState } from "react";
import type { TaskChoice, TaskSource } from "../lib/types";

interface Props {
  tasks: TaskChoice[];
  selectedIds: Set<string>;
  onToggle: (id: string) => void;
  onAdd: (label: string) => void;
  onRemove: (id: string) => void;
  disabled?: boolean;
}

const SOURCE_LABEL: Record<TaskSource, string> = {
  occupational: "Occupational baseline",
  job_description: "Job description",
  actual: "Your job",
};

export default function WorkIntelligence({
  tasks,
  selectedIds,
  onToggle,
  onAdd,
  onRemove,
  disabled,
}: Props) {
  const [draft, setDraft] = useState("");

  const addTask = () => {
    const label = draft.trim();
    if (!label || disabled) return;
    onAdd(label);
    setDraft("");
  };

  return (
    <div className="mt-4 space-y-3">
      <div>
        <h3 className="text-sm font-semibold">Which of these do you actually do?</h3>
        <p className="mt-1 text-xs text-neutral-600">
          Occupational baseline and job-description patterns are a first pass.
          These are tasks you may not need to do manually. Your checks outrank
          both lists. Add anything they missed, then design workflows you supervise.
        </p>
      </div>
      {tasks.length === 0 ? (
        <p className="rounded-lg border border-neutral-300 bg-white p-3 text-xs text-neutral-500">
          No baseline tasks for this role yet. Add the work you actually do.
        </p>
      ) : (
        <ul className="space-y-2">
          {tasks.map((task) => {
            const checked = selectedIds.has(task.id);
            return (
              <li
                key={task.id}
                onClick={() => {
                  if (!disabled) onToggle(task.id);
                }}
                className={
                  "flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2 " +
                  (disabled ? "cursor-not-allowed opacity-60 " : "") +
                  (checked
                    ? "border-accent bg-accent/5"
                    : "border-neutral-300 bg-white")
                }
              >
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={checked}
                  aria-label={task.label}
                  disabled={disabled}
                  onClick={(event) => event.stopPropagation()}
                  onChange={() => onToggle(task.id)}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium">{task.label}</span>
                    <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-neutral-600">
                      {SOURCE_LABEL[task.source]}
                    </span>
                  </div>
                  {task.detail && (
                    <p className="mt-1 text-xs text-neutral-600">{task.detail}</p>
                  )}
                </div>
                {task.source === "actual" && (
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      onRemove(task.id);
                    }}
                    disabled={disabled}
                    className="text-xs text-rose-600 hover:underline"
                  >
                    Remove
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          addTask();
        }}
      >
        <input
          type="text"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Add a task you actually do"
          aria-label="Add a task you actually do"
          disabled={disabled}
          className="flex-1 rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={disabled || draft.trim().length === 0}
          className={
            "rounded-md px-3 py-2 text-sm font-medium text-white " +
            (disabled || draft.trim().length === 0
              ? "cursor-not-allowed bg-neutral-400"
              : "bg-accent hover:bg-accent/90")
          }
        >
          Add task
        </button>
      </form>
    </div>
  );
}
