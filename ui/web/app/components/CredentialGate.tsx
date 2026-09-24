"use client";

import { useEffect, useState } from "react";
import { requiredCredentials } from "../lib/api";
import type { RequiredCredential } from "../lib/types";
import Spinner from "./Spinner";

interface Props {
  tools: string[];
  onConfirmed: () => void;
}

export default function CredentialGate({ tools, onConfirmed }: Props) {
  const [required, setRequired] = useState<RequiredCredential[]>([]);
  const [missing, setMissing] = useState<string[] | null>(null);
  const [checking, setChecking] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    requiredCredentials(tools)
      .then((report) => {
        if (cancelled) return;
        setRequired(report.required);
        if (report.required.length === 0) onConfirmed();
      })
      .catch((e: Error) => {
        if (!cancelled) setLoadError(e.message);
      });
    return () => {
      cancelled = true;
    };
    // tools identity changes when the parent re-renders; key off the names.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tools.join(",")]);

  const onCheck = async () => {
    setChecking(true);
    setLoadError(null);
    try {
      const report = await requiredCredentials(tools);
      setMissing(report.missing);
      if (report.missing.length === 0) onConfirmed();
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e));
    } finally {
      setChecking(false);
    }
  };

  if (required.length === 0 && !loadError) {
    return <p className="text-sm text-neutral-500">Checking which keys this plan needs…</p>;
  }

  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm">
      <h3 className="font-semibold text-amber-950">Add tool keys before continuing</h3>
      <p className="mt-2 text-amber-950">
        Open{" "}
        <a href="/settings" target="_blank" rel="noreferrer" className="font-medium underline">
          Settings
        </a>{" "}
        in a new tab (it is also in the header). Settings repeats this list, so
        you can add each key there, then come back here and confirm. This page
        keeps your plan.
      </p>
      <ul className="mt-3 space-y-1 font-mono text-xs">
        {required.map((row) => (
          <li key={`${row.tool}:${row.key}`}>
            {row.tool} → {row.key}
          </li>
        ))}
      </ul>
      {missing && missing.length > 0 && (
        <p className="mt-3 text-rose-800">
          Still missing: {missing.join(", ")}. Add those on Settings, then confirm again.
        </p>
      )}
      {loadError && <p className="mt-3 text-rose-800">{loadError}</p>}
      <button
        type="button"
        onClick={onCheck}
        disabled={checking}
        className="mt-4 inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 font-semibold text-white disabled:bg-neutral-400"
      >
        {checking && <Spinner className="h-4 w-4" />}
        {checking ? "Checking Settings…" : "I've added these in Settings"}
      </button>
    </div>
  );
}
