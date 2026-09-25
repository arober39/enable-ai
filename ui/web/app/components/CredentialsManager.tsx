"use client";

import { useEffect, useState } from "react";
import {
  deleteCredential,
  listCredentials,
  requiredCredentials,
  revealCredential,
  upsertCredential,
} from "../lib/api";
import { readPendingKeys, readPendingTools } from "../lib/homeSession";
import type { CredentialSummary, RequiredCredential } from "../lib/types";
import Spinner from "./Spinner";

interface RevealedState {
  [key: string]: string | undefined;
}

export default function CredentialsManager() {
  const [creds, setCreds] = useState<CredentialSummary[]>([]);
  const [revealed, setRevealed] = useState<RevealedState>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);
  const [needed, setNeeded] = useState<RequiredCredential[]>([]);

  const startAdd = (key: string) => {
    setNewKey(key);
    setNewValue("");
    setError(null);
    setShowForm(true);
  };

  const openForm = () => {
    setNewKey("");
    setNewValue("");
    setError(null);
    setShowForm(true);
  };

  const cancelForm = () => {
    setNewKey("");
    setNewValue("");
    setShowForm(false);
  };

  const refresh = async () => {
    try {
      const data = await listCredentials();
      setCreds(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    const names = readPendingTools();
    const explicit = readPendingKeys().map((key) => ({ tool: "workflow", key }));
    const neededRequest =
      names.length === 0
        ? Promise.resolve(explicit)
        : requiredCredentials(names)
            .then((report) => {
              const seen = new Set(report.required.map((row) => row.key));
              return [
                ...report.required,
                ...explicit.filter((row) => !seen.has(row.key)),
              ];
            })
            .catch(() => explicit);
    Promise.all([refresh(), neededRequest])
      .then(([, rows]) => setNeeded(rows))
      .finally(() => setLoading(false));
  }, []);

  const onSave = async () => {
    const key = newKey.trim();
    const value = newValue;
    if (!key || !value) return;
    setSaving(true);
    setError(null);
    try {
      await upsertCredential(key, value);
      setNewKey("");
      setNewValue("");
      setShowForm(false);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const onReveal = async (key: string) => {
    if (revealed[key] !== undefined) {
      // Already revealed → hide
      setRevealed((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
      return;
    }
    try {
      const { value } = await revealCredential(key);
      setRevealed((prev) => ({ ...prev, [key]: value }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const onCopy = async (key: string) => {
    try {
      let value = revealed[key];
      if (value === undefined) {
        const resp = await revealCredential(key);
        value = resp.value;
      }
      await navigator.clipboard.writeText(value);
      setCopyFeedback(key);
      setTimeout(() => setCopyFeedback(null), 1500);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const onDelete = async (key: string) => {
    if (!confirm(`Delete credential ${key}?`)) return;
    try {
      await deleteCredential(key);
      setRevealed((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  if (loading) {
    return (
      <div className="rounded-lg border border-neutral-300 bg-white p-4 text-sm text-neutral-500">
        Loading credentials…
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-md border border-rose-300 bg-rose-50 p-3 text-sm text-rose-800">
          <strong>Error:</strong> {error}
        </div>
      )}

      {needed.length > 0 && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm">
          <h3 className="font-semibold text-amber-950">
            Keys still listed from an earlier plan
          </h3>
          <p className="mt-2 text-amber-950">
            Grok Bot uses its own accounts for these tools. You do not need to
            add them here for the handoff.
          </p>
          <ul className="mt-3 space-y-2">
            {needed.map((row) => {
              const stored = creds.some((c) => c.key === row.key);
              return (
                <li
                  key={`${row.tool}:${row.key}`}
                  className="flex flex-wrap items-center gap-2"
                >
                  <span className="font-mono text-xs">
                    {row.tool} → {row.key}
                  </span>
                  {stored ? (
                    <span className="text-xs font-medium text-emerald-800">Stored</span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => startAdd(row.key)}
                      className="rounded-md bg-accent px-2 py-1 text-xs font-semibold text-white"
                    >
                      Add {row.key}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
          <a href="/" className="mt-3 inline-block font-medium text-amber-950 underline">
            Back to Enable AI
          </a>
        </div>
      )}

      {!showForm ? (
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={openForm}
            className="inline-flex items-center gap-1.5 rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50"
          >
            <span aria-hidden>+</span>
            Add environment variable
          </button>
          <p className="text-xs text-neutral-500">
            Stored at{" "}
            <code className="font-mono">
              agent-state/local/credentials.json
            </code>
          </p>
        </div>
      ) : (
        <div className="rounded-lg border border-neutral-300 bg-white p-4">
          <h3 className="mb-3 text-sm font-semibold text-neutral-700">
            New environment variable
          </h3>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <label className="flex flex-1 flex-col gap-1">
              <span className="text-xs font-medium text-neutral-600">Key</span>
              <input
                type="text"
                value={newKey}
                onChange={(e) => setNewKey(e.target.value.toUpperCase())}
                placeholder="ANTHROPIC_API_KEY"
                className="rounded border border-neutral-300 px-2 py-1 font-mono text-sm"
                disabled={saving}
                autoFocus
              />
            </label>
            <label className="flex flex-[2] flex-col gap-1">
              <span className="text-xs font-medium text-neutral-600">Value</span>
              <input
                type="password"
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                placeholder="sk-ant-…"
                className="rounded border border-neutral-300 px-2 py-1 font-mono text-sm"
                disabled={saving}
                autoComplete="off"
              />
            </label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={onSave}
                disabled={saving || !newKey.trim() || !newValue}
                className={
                  "inline-flex items-center gap-2 rounded-md px-4 py-1.5 text-sm font-semibold text-white transition " +
                  (saving || !newKey.trim() || !newValue
                    ? "bg-neutral-400 cursor-not-allowed"
                    : "bg-accent hover:bg-accent/90")
                }
              >
                {saving && <Spinner className="h-4 w-4" />}
                {saving ? "Saving…" : "Save"}
              </button>
              <button
                type="button"
                onClick={cancelForm}
                disabled={saving}
                className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm text-neutral-700 hover:bg-neutral-50"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      <div>
        <h3 className="mb-2 text-sm font-semibold text-neutral-700">
          Stored ({creds.length})
        </h3>
        {creds.length === 0 ? (
          <div className="rounded-lg border border-dashed border-neutral-300 bg-neutral-50 p-4 text-sm text-neutral-500">
            No credentials yet. Add one above.
          </div>
        ) : (
          <ul className="divide-y divide-neutral-200 rounded-lg border border-neutral-300 bg-white">
            {creds.map((c) => (
              <li
                key={c.key}
                className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center"
              >
                <span className="flex-1 font-mono text-sm">{c.key}</span>
                <span className="flex-1 font-mono text-xs text-neutral-600">
                  {revealed[c.key] ?? c.masked_value}
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => onReveal(c.key)}
                    className="rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-50"
                  >
                    {revealed[c.key] !== undefined ? "Hide" : "Reveal"}
                  </button>
                  <button
                    type="button"
                    onClick={() => onCopy(c.key)}
                    className="rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-50"
                  >
                    {copyFeedback === c.key ? "Copied!" : "Copy"}
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(c.key)}
                    className="rounded border border-rose-300 px-2 py-1 text-xs text-rose-700 hover:bg-rose-50"
                  >
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
