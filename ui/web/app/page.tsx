"use client";

import { useEffect, useState } from "react";
import BuildOrchestrator from "./components/BuildOrchestrator";
import LoadingPanel from "./components/LoadingPanel";
import PlanDisplay from "./components/PlanDisplay";
import RolePicker from "./components/RolePicker";
import RunInquiryPanel from "./components/RunInquiryPanel";
import SavedRecommendations from "./components/SavedRecommendations";
import Spinner from "./components/Spinner";
import ToolPicker from "./components/ToolPicker";
import {
  deleteCachedTool,
  fetchHealth,
  getPreferences,
  listRoles,
  listSavedRecommendations,
  listTools,
  researchTool,
  runEnablement,
  setSelectedRole,
} from "./lib/api";
import type {
  ArtifactKind,
  EnablementResponse,
  RoleSummary,
  SavedRecommendation,
  ToolSummary,
} from "./lib/types";

export default function Home() {
  const [tools, setTools] = useState<ToolSummary[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [roles, setRoles] = useState<RoleSummary[]>([]);
  const [selectedRole, setSelectedRoleState] = useState<string | null>(null);
  const [savedRecs, setSavedRecs] = useState<SavedRecommendation[]>([]);
  const [result, setResult] = useState<EnablementResponse | null>(null);
  // The artifact kind from the most recent successful build, or null
  // if no build has happened (or last attempt failed). Step 6 (Send an
  // inquiry) shows only when this is "workflow" — setup guides and
  // migration plans don't have a runtime to call.
  const [lastArtifactKind, setLastArtifactKind] = useState<ArtifactKind | null>(null);
  // Incremented after each successful workflow build. Used as a React
  // `key` on RunInquiryPanel so it remounts and re-fetches the freshly
  // persisted workflow's sample_request.
  const [buildVersion, setBuildVersion] = useState(0);

  const handleBuilt = (kind: ArtifactKind | null) => {
    setLastArtifactKind(kind);
    // Only bump buildVersion (which forces RunInquiryPanel to refetch)
    // when a runtime workflow was actually built. Other artifact kinds
    // don't change what the panel would display.
    if (kind === "workflow") {
      setBuildVersion((v) => v + 1);
    }
  };
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
        // Default: pre-select Intercom + Zendesk if they exist in the
        // catalog (seed tools), so first-time visitors see a non-trivial
        // plan when they hit Submit.
        const seeds = new Set(data.map((t) => t.name));
        const presel = new Set<string>();
        if (seeds.has("intercom")) presel.add("intercom");
        if (seeds.has("zendesk")) presel.add("zendesk");
        setSelected(presel);
      })
      .catch((e: Error) => setError(e.message));
    Promise.all([listRoles(), getPreferences()])
      .then(([roleList, prefs]) => {
        setRoles(roleList);
        setSelectedRoleState(prefs.selected_role);
      })
      .catch((e: Error) => setError(e.message));
    refreshSaved();
  }, []);

  const refreshSaved = () => {
    listSavedRecommendations()
      .then(setSavedRecs)
      .catch(() => {
        /* non-fatal */
      });
  };

  const onRoleChange = (roleId: string) => {
    setSelectedRoleState(roleId);
    // Persist asynchronously; surface failures via the error pane but don't
    // block the optimistic UI update — the picker should feel instant.
    setSelectedRole(roleId).catch((e: Error) => setError(e.message));
  };

  const onResearch = async (name: string) => {
    const added = await researchTool(name);
    setTools((prev) => {
      const next = prev.filter((t) => t.name !== added.name);
      next.push(added);
      next.sort((a, b) => a.vendor.localeCompare(b.vendor));
      return next;
    });
    setSelected((prev) => new Set(prev).add(added.name));
  };

  const onDeleteCached = async (name: string) => {
    await deleteCachedTool(name);
    setTools((prev) => prev.filter((t) => t.name !== name));
    setSelected((prev) => {
      const next = new Set(prev);
      next.delete(name);
      return next;
    });
  };

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
      const resp = await runEnablement(
        Array.from(selected),
        selectedRole ?? undefined,
      );
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
          Pick a role and a stack. The Enablement Agent proposes
          recommendations; pick one to generate a runnable orchestrator.
        </p>
        {health && (
          <p className="mt-2 text-xs text-neutral-500">
            backend health: <span className="font-mono">demo_mode={String(health.demo_mode)}</span>{" "}
            · <span className="font-mono">anthropic_key={String(health.has_anthropic_key)}</span>
          </p>
        )}
      </header>

      <SavedRecommendations items={savedRecs} onRemoved={refreshSaved} />


      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">1. Pick your role</h2>
          <span className="text-xs text-neutral-500">
            Loads role-specific agent context
          </span>
        </div>
        <RolePicker
          roles={roles}
          selected={selectedRole}
          onSelect={onRoleChange}
          disabled={loading}
        />
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">2. Select your tools</h2>
          <span className="text-xs text-neutral-500">
            {selected.size} of {tools.length} selected
          </span>
        </div>
        {tools.length === 0 && !error ? (
          <div className="rounded-lg border border-neutral-300 bg-white p-4 text-sm text-neutral-500">
            Loading catalog…
          </div>
        ) : (
          <ToolPicker
            tools={tools}
            selected={selected}
            onToggle={toggle}
            onResearch={onResearch}
            onDeleteCached={onDeleteCached}
            disabled={loading}
          />
        )}
      </section>

      <section>
        <h2 className="mb-3 text-base font-semibold">
          3. Run the Enablement Agent
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
          <h2 className="mb-3 text-base font-semibold">4. In progress</h2>
          <LoadingPanel demoMode={!!health?.demo_mode} />
        </section>
      )}

      {result && !loading && (
        <section>
          <h2 className="mb-3 text-base font-semibold">4. Plan</h2>
          <PlanDisplay response={result} />
        </section>
      )}

      {result && !loading && selectedRole && (
        <section>
          <h2 className="mb-3 text-base font-semibold">
            5. Pick one recommendation and build
          </h2>
          <p className="mb-3 text-sm text-neutral-700">
            The LLM-driven 4-stage pipeline writes one{" "}
            <code className="rounded bg-neutral-100 px-1 py-0.5 font-mono text-xs">
              orchestrator.py
            </code>{" "}
            under{" "}
            <code className="rounded bg-neutral-100 px-1 py-0.5 font-mono text-xs">
              orchestrators/local/{selectedRole}/
            </code>
            . Other recommendations can be parked for later from this list.
          </p>
          <BuildOrchestrator
            plan={result.plan}
            roleId={selectedRole}
            selectedTools={Array.from(selected)}
            onSaved={refreshSaved}
            onBuilt={handleBuilt}
          />
        </section>
      )}

      {result && !loading && lastArtifactKind === "workflow" && (
        <section>
          <h2 className="mb-3 text-base font-semibold">6. Send an inquiry</h2>
          <p className="mb-3 text-xs text-neutral-500">
            Shown only because the most recent build produced a runtime
            workflow. If you build a setup guide or migration plan next,
            this section will hide — those kinds don't have a runtime to
            call.
          </p>
          {/* `key` changes on each workflow build → remounts the panel
              → its useEffect re-fetches the latest workflow's sample. */}
          <RunInquiryPanel key={buildVersion} />
        </section>
      )}
    </main>
  );
}
