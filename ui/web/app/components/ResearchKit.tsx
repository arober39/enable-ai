"use client";

import type { ResearchSource } from "../lib/types";

interface Props {
  items: ResearchSource[];
}

/** Catalog evidence attached to one recommendation. */
export default function ResearchKit({ items }: Props) {
  if (items.length === 0) return null;
  return (
    <div className="mt-3 rounded-md border border-sky-200 bg-sky-50/70 p-3">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-sky-900">
        Research kit
      </h4>
      <ul className="mt-2 space-y-2">
        {items.map((item, index) => (
          <li key={`${item.source}-${index}`}>
            <p className="text-xs font-medium text-neutral-900">{item.title}</p>
            <p className="mt-0.5 text-xs leading-relaxed text-neutral-700">
              {item.evidence}
            </p>
            <p className="mt-0.5 text-[11px] text-neutral-500">
              Source: {item.source}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}
