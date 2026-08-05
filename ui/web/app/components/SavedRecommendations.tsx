"use client";

import { useState } from "react";
import { deleteSavedRecommendation } from "../lib/api";
import type { SavedRecommendation } from "../lib/types";

interface Props {
  items: SavedRecommendation[];
  onRemoved: () => void;
}

export default function SavedRecommendations({ items, onRemoved }: Props) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (items.length === 0) return null;

  const onDelete = async (id: string) => {
    if (!confirm("Remove this saved recommendation?")) return;
    try {
      await deleteSavedRecommendation(id);
      onRemoved();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50/50">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-4 py-2 text-left"
      >
        <span className="text-sm font-semibold text-amber-900">
          ★ {items.length} saved for later
        </span>
        <span className="text-xs text-amber-700">{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <ul className="space-y-2 px-4 pb-4">
          {error && (
            <li className="rounded border border-rose-300 bg-rose-50 p-2 text-xs text-rose-800">
              {error}
            </li>
          )}
          {items.map((s) => (
            <li
              key={s.id}
              className="rounded border border-neutral-200 bg-white p-3 text-sm"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2 text-xs text-neutral-500">
                    <span className="font-mono">{s.recommendation.id}</span>
                    <span>·</span>
                    <span>role: {s.role_id}</span>
                    <span>·</span>
                    <span>tools: {s.tools.join(", ") || "—"}</span>
                  </div>
                  <p className="mt-1 text-sm text-neutral-700">
                    {s.recommendation.description}
                  </p>
                  <p className="mt-1 text-xs text-neutral-500">
                    saved {new Date(s.saved_at).toLocaleString()}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => onDelete(s.id)}
                  className="text-xs text-rose-600 hover:underline"
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
