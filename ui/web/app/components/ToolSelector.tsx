"use client";

import type { ToolSummary } from "../lib/types";

interface Props {
  tools: ToolSummary[];
  selected: Set<string>;
  onToggle: (name: string) => void;
  disabled?: boolean;
}

/** Card-style multiselect over the catalog tools. */
export default function ToolSelector({
  tools,
  selected,
  onToggle,
  disabled,
}: Props) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {tools.map((t) => {
        const active = selected.has(t.name);
        return (
          <button
            key={t.name}
            type="button"
            disabled={disabled}
            onClick={() => onToggle(t.name)}
            className={
              "relative rounded-lg border p-4 text-left transition " +
              (active
                ? "border-accent bg-accent/5"
                : "border-neutral-300 bg-white hover:border-neutral-400") +
              (disabled ? " opacity-60" : "")
            }
            aria-pressed={active}
          >
            <div className="flex items-start justify-between">
              <div>
                <div className="font-semibold capitalize">{t.name}</div>
                <div className="text-xs text-neutral-500">{t.vendor}</div>
              </div>
              <div
                className={
                  "h-5 w-5 shrink-0 rounded-full border-2 " +
                  (active
                    ? "border-accent bg-accent"
                    : "border-neutral-400 bg-transparent")
                }
                aria-hidden
              />
            </div>
            <div className="mt-2 text-xs text-neutral-600">
              <span className="font-medium">Use:</span> {t.primary_use || "—"}
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {t.has_native_ai && (
                <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-neutral-700">
                  native AI
                </span>
              )}
              {t.has_mcp_server ? (
                <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-emerald-700">
                  MCP {t.mcp_origin}
                </span>
              ) : (
                <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-amber-700">
                  MCP stub
                </span>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}
