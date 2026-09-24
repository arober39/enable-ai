"use client";

import { useEffect, useState } from "react";
import { fetchGrokbotHandoff, type GrokbotHandoffText } from "../lib/api";
import type { Recommendation } from "../lib/types";
import Spinner from "./Spinner";

interface Props {
  recommendation: Recommendation;
  roleName: string;
  tools: string[];
}

function copyWithSelection(value: string): boolean {
  const area = document.createElement("textarea");
  area.value = value;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.top = "0";
  area.style.left = "0";
  area.style.width = "1px";
  area.style.height = "1px";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.focus();
  area.select();
  area.setSelectionRange(0, area.value.length);
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  } finally {
    document.body.removeChild(area);
  }
  return ok;
}

async function writeClipboard(value: string): Promise<void> {
  if (copyWithSelection(value)) return;
  const write = navigator.clipboard?.writeText;
  if (!write) {
    throw new Error("Copy failed. Select the text and copy it manually.");
  }
  await Promise.race([
    write.call(navigator.clipboard, value),
    new Promise<never>((_resolve, reject) => {
      window.setTimeout(() => reject(new Error("Copy timed out.")), 800);
    }),
  ]);
}

export default function GrokbotHandoff({
  recommendation,
  roleName,
  tools,
}: Props) {
  const [handoff, setHandoff] = useState<GrokbotHandoffText | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const toolKey = tools.join("\n");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setHandoff(null);
    fetchGrokbotHandoff({
      recommendation_id: recommendation.id,
      kind: recommendation.kind,
      description: recommendation.description,
      notes: recommendation.notes,
      role_name: roleName,
      tools,
    })
      .then((next) => {
        if (!cancelled) setHandoff(next);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setHandoff(null);
          setError(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // toolKey is the stable form of tools.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    recommendation.id,
    recommendation.kind,
    recommendation.description,
    recommendation.notes,
    roleName,
    toolKey,
  ]);

  const onCopy = (label: string, value: string) => {
    setError(null);
    const markCopied = () => {
      setCopied(label);
      window.setTimeout(() => {
        setCopied((current) => (current === label ? null : current));
      }, 2500);
    };
    if (copyWithSelection(value)) {
      markCopied();
      return;
    }
    void writeClipboard(value).then(markCopied, (e: unknown) => {
      setError(e instanceof Error ? e.message : String(e));
    });
  };

  const toolLabel = tools.length ? tools.join(", ") : "these tools";

  return (
    <div className="space-y-4 rounded-lg border border-neutral-300 bg-white p-4">
      <p className="text-sm text-neutral-700">
        Enable AI does not call {toolLabel}. Finish this in Grok Bot: create
        or update the bot yourself, and that bot does the work.
      </p>
      <div>
        <h3 className="text-sm font-semibold text-neutral-900">Next steps</h3>
        <ol className="mt-1 list-decimal space-y-1 pl-5 text-sm text-neutral-700">
          <li>Open Grok Bot.</li>
          <li>Create a new bot, or edit an existing one.</li>
          <li>Paste the name, title, and description below.</li>
        </ol>
        <p className="mt-2 text-sm text-neutral-600">
          You can also paste the description into a Grok Bot chat and ask the
          assistant to create the teammate.
        </p>
      </div>
      {loading && (
        <p className="inline-flex items-center gap-2 text-sm text-neutral-500">
          <Spinner className="h-4 w-4" />
          Preparing the assignment…
        </p>
      )}
      {error && (
        <p className="text-sm text-rose-700">
          <strong>Error:</strong> {error}
        </p>
      )}
      {handoff && (
        <div className="space-y-3">
          <Field
            label="Bot name"
            value={handoff.name}
            copied={copied === "name"}
            onCopy={() => onCopy("name", handoff.name)}
          />
          <Field
            label="Title"
            value={handoff.title}
            copied={copied === "title"}
            onCopy={() => onCopy("title", handoff.title)}
          />
          <div className="space-y-1">
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
                Description
              </span>
              <button
                type="button"
                onClick={() => onCopy("description", handoff.description)}
                className="rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-accent/90"
              >
                {copied === "description" ? "Copied" : "Copy description"}
              </button>
            </div>
            <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-md border border-neutral-200 bg-neutral-50 p-3 font-sans text-sm text-neutral-800">
              {handoff.description}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  value,
  copied,
  onCopy,
}: {
  label: string;
  value: string;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div>
        <div className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
          {label}
        </div>
        <div className="mt-0.5 text-sm text-neutral-900">{value}</div>
      </div>
      <button
        type="button"
        onClick={onCopy}
        className="shrink-0 rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-50"
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
