"use client";

import type { RoleSummary } from "../lib/types";

interface Props {
  roles: RoleSummary[];
  selected: string | null;
  onSelect: (roleId: string) => void;
  disabled?: boolean;
}

export default function RolePicker({
  roles,
  selected,
  onSelect,
  disabled,
}: Props) {
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
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {roles.map((r) => {
          const isActive = r.id === selected;
          return (
            <button
              key={r.id}
              type="button"
              onClick={() => onSelect(r.id)}
              disabled={disabled}
              className={
                "rounded-lg border px-3 py-2 text-left transition " +
                (isActive
                  ? "border-accent bg-accent/5"
                  : "border-neutral-300 bg-white hover:border-neutral-400") +
                (disabled ? " opacity-60 cursor-not-allowed" : "")
              }
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold">{r.display_name}</span>
                {isActive && (
                  <span className="text-xs font-medium text-accent">
                    Selected
                  </span>
                )}
              </div>
              <p className="mt-1 text-xs text-neutral-600">{r.description}</p>
            </button>
          );
        })}
      </div>
      {current && current.capabilities.length > 0 && (
        <p className="text-xs text-neutral-500">
          <span className="font-medium">Capabilities loaded:</span>{" "}
          {current.capabilities.join(" · ")}
        </p>
      )}
    </div>
  );
}
