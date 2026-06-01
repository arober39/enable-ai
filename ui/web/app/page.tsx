"use client";

import { useEffect, useState } from "react";
import BuildOrchestrator from "./components/BuildOrchestrator";
import LoadingPanel from "./components/LoadingPanel";
import PlanDisplay from "./components/PlanDisplay";
import Spinner from "./components/Spinner";
import ToolSelector from "./components/ToolSelector";
import { fetchHealth, listTools, runEnablement } from "./lib/api";
import type { EnablementResponse, ToolSummary } from "./lib/types";

export default function Home() {
  const [tools, setTools] = useState<ToolSummary[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<EnablementResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState<{
    demo_mode: boolean;
    has_anthropic_key: boolean;
  } | null>(null);

  useEffect(() => {
    fetchHealth().then(setHealth).catch(() => setHealth(null));
    listTools()
      .then((data) => {
        setTools(data);
        // Default: pre-select Intercom + Zendesk so first-time visitors see
        // a non-trivial plan when they hit Submit.
        setSelected(new Set(["intercom", "zendesk"]));
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const toggle = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const submit = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const resp = await runEnablement(Array.from(selected));
      setResult(resp);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="space-y-8">
      <header>
        <h1 className="text-2xl font-bold">Enable AI — test UI</h1>
        <p className="mt-1 text-sm text-neutral-600">
          Pick a support stack. Get an EnablementPlan from the Support
          Enablement Agent.
        </p>
        {health && (
          <p className="mt-2 text-xs text-neutral-500">
            backend health: <span className="font-mono">demo_mode={String(health.demo_mode)}</span>{" "}
            · <span className="font-mono">anthropic_key={String(health.has_anthropic_key)}</span>
          </p>
        )}
      </header>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">1. Select your tools</h2>
          <span className="text-xs text-neutral-500">
            {selected.size} of {tools.length} selected
          </span>
        </div>
        {tools.length === 0 && !error ? (
          <div className="rounded-lg border border-neutral-300 bg-white p-4 text-sm text-neutral-500">
            Loading catalog…
          </div>
        ) : (
          <ToolSelector
            tools={tools}
            selected={selected}
            onToggle={toggle}
            disabled={loading}
          />
        )}
      </section>

      <section>
        <h2 className="mb-3 text-base font-semibold">
          2. Run the Support Enablement Agent
        </h2>
        <button
          type="button"
          disabled={selected.size === 0 || loading}
          onClick={submit}
          className={
            "inline-flex items-center gap-2 rounded-md px-4 py-2 font-semibold text-white transition " +
            (selected.size === 0 || loading
              ? "bg-neutral-400 cursor-not-allowed"
              : "bg-accent hover:bg-accent/90")
          }
        >
          {loading && <Spinner className="h-4 w-4" />}
          {loading
            ? "Running…"
            : health?.demo_mode
              ? "Run (demo)"
              : "Run (live LLM)"}
        </button>
        {!health?.demo_mode && !loading && (
          <p className="mt-2 text-xs text-amber-700">
            Live mode is on — each run hits Claude and costs money.
          </p>
        )}
      </section>

      {error && (
        <div className="rounded-md border border-rose-300 bg-rose-50 p-4 text-sm text-rose-800">
          <strong>Error:</strong> {error}
        </div>
      )}

      {loading && (
        <section>
          <h2 className="mb-3 text-base font-semibold">3. In progress</h2>
          <LoadingPanel demoMode={!!health?.demo_mode} />
        </section>
      )}

      {result && !loading && (
        <section>
          <h2 className="mb-3 text-base font-semibold">3. Plan</h2>
          <PlanDisplay response={result} />
        </section>
      )}

      {result && !loading && (
        <section>
          <h2 className="mb-3 text-base font-semibold">
            4. Build the orchestrator
          </h2>
          <p className="mb-3 text-sm text-neutral-700">
            Materialize the orchestrator tree on disk from this plan. The
            files land under{" "}
            <code className="rounded bg-neutral-100 px-1 py-0.5 font-mono text-xs">
              orchestrators/{result.plan.department}/
            </code>
            . Any previous generation at that path is overwritten.
          </p>
          <BuildOrchestrator plan={result.plan} />
        </section>
      )}
    </main>
  );
}
