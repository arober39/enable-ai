"use client";

import { useState } from "react";
import type { ToolSummary } from "../lib/types";
import Spinner from "./Spinner";

interface Props {
  tools: ToolSummary[];
  selected: Set<string>;
  onToggle: (name: string) => void;
  onResearch: (name: string) => Promise<void>;
  onDeleteCached: (name: string) => Promise<void>;
  disabled?: boolean;
}

const _MIN_QUERY = 2;

export default function ToolPicker({
  tools,
  selected,
  onToggle,
  onResearch,
  onDeleteCached,
  disabled,
}: Props) {
  const [query, setQuery] = useState("");
  const [researching, setResearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const q = query.trim().toLowerCase();
  const visible = q
    ? tools.filter(
        (t) =>
          t.vendor.toLowerCase().includes(q) ||
          t.name.toLowerCase().includes(q) ||
          t.categories.some((c) => c.toLowerCase().includes(q)),
      )
    : tools;

  const exactMatch =
    q.length > 0 &&
    tools.some(
      (t) => t.name === q || t.vendor.toLowerCase() === q,
    );
  const canResearch = q.length >= _MIN_QUERY && !exactMatch && !researching;

  const tryResearch = async () => {
    setResearching(true);
    setError(null);
    try {
      await onResearch(query.trim());
      setQuery("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setResearching(false);
    }
  };

  const tryDelete = async (name: string) => {
    if (!confirm(`Remove "${name}" from your researched tools?`)) return;
    try {
      await onDeleteCached(name);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="space-y-3">
      {/* Selected chips */}
      <div className="flex min-h-[2rem] flex-wrap items-center gap-2">
        {selected.size === 0 ? (
          <span className="text-xs text-neutral-500">
            No tools selected yet — search or research one below.
          </span>
        ) : (
          [...selected].map((name) => {
            const t = tools.find((x) => x.name === name);
            const label = t?.vendor ?? name;
            return (
              <span
                key={name}
                className="inline-flex items-center gap-1.5 rounded-full border border-accent/30 bg-accent/10 px-2 py-1 text-xs"
              >
                <span className="font-medium">{label}</span>
                <button
                  type="button"
                  onClick={() => onToggle(name)}
                  disabled={disabled}
                  aria-label={`Remove ${label}`}
                  className="text-neutral-500 hover:text-neutral-800"
                >
                  ×
                </button>
              </span>
            );
          })
        )}
      </div>

      {/* Search input */}
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search or type a tool name to research with Claude…"
          className="w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm"
          disabled={disabled || researching}
        />
        {researching && (
          <Spinner className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2" />
        )}
      </div>

      {error && (
        <div className="rounded-md border border-rose-300 bg-rose-50 p-2 text-xs text-rose-800">
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Catalog list */}
      <div className="rounded-lg border border-neutral-300 bg-white">
        {visible.length === 0 && !canResearch && (
          <div className="p-3 text-xs text-neutral-500">
            No matching tools. Type at least {_MIN_QUERY} characters to research a new one.
          </div>
        )}

        <ul className="divide-y divide-neutral-200">
          {visible.map((t) => {
            const isSelected = selected.has(t.name);
            return (
              <li
                key={t.name}
                className="flex items-start justify-between gap-3 px-3 py-2"
              >
                <button
                  type="button"
                  onClick={() => onToggle(t.name)}
                  disabled={disabled}
                  className="flex-1 text-left"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{t.vendor}</span>
                    <span
                      className={
                        "rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wide " +
                        (t.source === "researched"
                          ? "bg-emerald-100 text-emerald-700"
                          : "bg-neutral-100 text-neutral-600")
                      }
                    >
                      {t.source}
                    </span>
                    {t.has_native_ai && (
                      <span className="rounded bg-sky-100 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-sky-700">
                        native AI
                      </span>
                    )}
                    {t.has_mcp_server && (
                      <span className="rounded bg-violet-100 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-violet-700">
                        MCP
                      </span>
                    )}
                  </div>
                  {t.notes && (
                    <p className="mt-0.5 line-clamp-2 text-xs text-neutral-600">
                      {t.notes}
                    </p>
                  )}
                </button>
                <div className="flex shrink-0 items-center gap-2">
                  {t.source === "researched" && (
                    <button
                      type="button"
                      onClick={() => tryDelete(t.name)}
                      disabled={disabled}
                      className="text-xs text-rose-600 hover:underline"
                    >
                      Delete
                    </button>
                  )}
                  <span
                    className={
                      "rounded px-2 py-1 text-xs " +
                      (isSelected
                        ? "bg-accent text-white"
                        : "border border-neutral-300 text-neutral-700")
                    }
                  >
                    {isSelected ? "Selected" : "Add"}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>

        {canResearch && (
          <div className="border-t border-neutral-200 p-2">
            <button
              type="button"
              onClick={tryResearch}
              disabled={disabled || researching}
              className={
                "inline-flex w-full items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition " +
                (researching
                  ? "bg-neutral-200 text-neutral-500 cursor-not-allowed"
                  : "bg-accent text-white hover:bg-accent/90")
              }
            >
              {researching && <Spinner className="h-4 w-4" />}
              {researching
                ? `Researching "${query}"…`
                : `Research "${query}" with Claude`}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
