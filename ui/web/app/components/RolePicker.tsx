"use client";

import { useState } from "react";
import { visiblePickerItems } from "../lib/pickerItems";
import { rolesPrefixedBy } from "../lib/roleQuery";
import type { RoleSummary } from "../lib/types";
import Spinner from "./Spinner";

interface Props {
  roles: RoleSummary[];
  selected: string | null;
  onSelect: (roleId: string) => void;
  onResearch: (name: string, roleId?: string) => Promise<void>;
  onDeleteCached: (id: string) => Promise<void>;
  disabled?: boolean;
}

const _MIN_QUERY = 2;
const _PREVIEW_COUNT = 3;

export default function RolePicker({
  roles,
  selected,
  onSelect,
  onResearch,
  onDeleteCached,
  disabled,
}: Props) {
  const [query, setQuery] = useState("");
  const [researching, setResearching] = useState(false);
  const [researchingId, setResearchingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const q = query.trim().toLowerCase();
  const matchesRole = (role: RoleSummary, queryText: string) =>
    role.display_name.toLowerCase().includes(queryText) ||
    role.id.toLowerCase().includes(queryText) ||
    role.department.toLowerCase().includes(queryText) ||
    role.description.toLowerCase().includes(queryText);
  const visible = q ? roles.filter((role) => matchesRole(role, q)) : roles;

  const exactMatch =
    q.length > 0 &&
    roles.some(
      (r) =>
        r.id.toLowerCase() === q || r.display_name.toLowerCase() === q,
    );
  const prefixOf = rolesPrefixedBy(query, roles);
  const canResearch =
    q.length >= _MIN_QUERY &&
    !exactMatch &&
    prefixOf.length === 0 &&
    !researching;
  const shown = visiblePickerItems({
    items: roles,
    query,
    matches: matchesRole,
    isSelected: (role) => role.id === selected,
    previewCount: _PREVIEW_COUNT,
    pinSelected: true,
  });

  const researchSeed = async (role: RoleSummary) => {
    setResearchingId(role.id);
    setError(null);
    try {
      await onResearch(role.display_name, role.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setResearchingId(null);
    }
  };

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

  const tryDelete = async (role: RoleSummary) => {
    if (!confirm(`Remove "${role.display_name}" from your researched roles?`))
      return;
    try {
      await onDeleteCached(role.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  if (roles.length === 0) {
    return (
      <div className="rounded-lg border border-neutral-300 bg-white p-4 text-sm text-neutral-500">
        Loading roles…
      </div>
    );
  }

  const current = roles.find((r) => r.id === selected) ?? null;

  return (
    <div className="space-y-3">
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search or type a job to research with Claude…"
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

      {q.length >= _MIN_QUERY && prefixOf.length > 0 && !researching && (
        <p className="text-xs text-neutral-500">
          This matches {prefixOf.map((role) => role.display_name).join(", ")}.
          Use Research on that card.
        </p>
      )}

      {visible.length === 0 && !canResearch && (
        <div className="rounded-lg border border-neutral-300 bg-white p-3 text-xs text-neutral-500">
          No matching roles. Type at least {_MIN_QUERY} characters to research a
          new one.
        </div>
      )}

      <div className="grid grid-cols-1 items-stretch gap-2 sm:grid-cols-2">
        {shown.map((r) => {
          const isActive = r.id === selected;
          return (
            <div
              key={r.id}
              className={
                "flex h-full items-start justify-between gap-3 rounded-lg border px-3 py-2 transition " +
                (isActive
                  ? "border-accent bg-accent/5"
                  : "border-neutral-300 bg-white")
              }
            >
              <button
                type="button"
                onClick={() => onSelect(r.id)}
                disabled={disabled}
                className={
                  "flex-1 text-left " +
                  (disabled ? "cursor-not-allowed opacity-60" : "")
                }
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2">
                    <span className="text-sm font-semibold">
                      {r.display_name}
                    </span>
                    {r.source === "researched" && (
                      <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-emerald-700">
                        researched
                      </span>
                    )}
                  </span>
                </div>
                <p className="mt-1 line-clamp-3 text-xs text-neutral-600">
                  {r.description}
                </p>
              </button>
              <div className="flex shrink-0 items-center gap-2">
                {r.source === "seed" && (
                  <button
                    type="button"
                    onClick={() => researchSeed(r)}
                    disabled={disabled || researchingId === r.id}
                    className="text-xs text-accent hover:underline"
                  >
                    {researchingId === r.id ? "Researching…" : "Research"}
                  </button>
                )}
                {r.source === "researched" && (
                  <button
                    type="button"
                    onClick={() => tryDelete(r)}
                    disabled={disabled}
                    className="text-xs text-rose-600 hover:underline"
                  >
                    Delete
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => onSelect(r.id)}
                  disabled={disabled}
                  className={
                    "rounded px-2 py-1 text-xs " +
                    (isActive
                      ? "bg-accent text-white"
                      : "border border-neutral-300 text-neutral-700 hover:bg-neutral-50")
                  }
                >
                  {isActive ? "Selected" : "Add"}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {canResearch && (
        <button
          type="button"
          onClick={tryResearch}
          disabled={disabled || researching}
          className={
            "inline-flex w-full items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition " +
            (researching
              ? "cursor-not-allowed bg-neutral-200 text-neutral-500"
              : "bg-accent text-white hover:bg-accent/90")
          }
        >
          {researching && <Spinner className="h-4 w-4" />}
          {researching
            ? `Researching "${query}"…`
            : `Research "${query}" with Claude`}
        </button>
      )}

      {current && current.capabilities.length > 0 && (
        <p className="text-xs text-neutral-500">
          <span className="font-medium">Capabilities loaded:</span>{" "}
          {current.capabilities.join(" · ")}
        </p>
      )}
    </div>
  );
}
