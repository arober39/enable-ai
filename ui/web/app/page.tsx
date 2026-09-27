"use client";

import { useEffect, useRef, useState } from "react";
import AgentBlueprintView from "./components/AgentBlueprintView";
import BuildOrchestrator from "./components/BuildOrchestrator";
import GrokbotHandoff from "./components/GrokbotHandoff";
import LoadingPanel from "./components/LoadingPanel";
import PlanDisplay from "./components/PlanDisplay";
import RolePicker from "./components/RolePicker";
import SavedRecommendations from "./components/SavedRecommendations";
import Spinner from "./components/Spinner";
import ToolPicker from "./components/ToolPicker";
import WorkIntelligence from "./components/WorkIntelligence";
import {
  ApiError,
  cancelJob,
  deleteCachedRole,
  deleteCachedTool,
  fetchHealth,
  fetchJob,
  listRoles,
  listSavedRecommendations,
  listTools,
  listWorkTasks,
  researchRole,
  researchTool,
  setSelectedRole,
  startEnablementJob,
} from "./lib/api";
import {
  buildCustomRecommendation,
  CUSTOM_RECOMMENDATION_ID,
  isCustomRecommendationId,
  sameHandoffRecommendation,
  type HandoffRecommendation,
} from "./lib/customRecommendation";
import {
  readSession,
  SESSION_KEY,
  writePendingKeys,
  writePendingTools,
  type HomeSession,
} from "./lib/homeSession";
import type {
  EnablementResponse,
  RoleSummary,
  SavedRecommendation,
  TaskChoice,
  TaskSelection,
  ToolSummary,
  WorkTask,
} from "./lib/types";

export default function Home() {
  const [sessionReady, setSessionReady] = useState(false);
  const [tools, setTools] = useState<ToolSummary[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [roles, setRoles] = useState<RoleSummary[]>([]);
  const [selectedRole, setSelectedRoleState] = useState<string | null>(null);
  const [workTasks, setWorkTasks] = useState<WorkTask[]>([]);
  const [customTasks, setCustomTasks] = useState<TaskChoice[]>([]);
  const [checkedTaskIds, setCheckedTaskIds] = useState<Set<string>>(new Set());
  const [tasksLoadedFor, setTasksLoadedFor] = useState<string | null>(null);
  const [friction, setFriction] = useState("");
  const restoredTasks = useRef<{ role: string; ids: string[] } | null>(null);
  const [savedRecs, setSavedRecs] = useState<SavedRecommendation[]>([]);
  const [result, setResult] = useState<EnablementResponse | null>(null);
  const [selectedRecommendationId, setSelectedRecommendationId] = useState<
    string | null
  >(null);
  // Step 6 follows the last submitted recommendation. The radio above it
  // can move without replacing the handoff.
  const [submittedRecommendationId, setSubmittedRecommendationId] = useState<
    string | null
  >(null);
  const [customTitle, setCustomTitle] = useState("");
  const [customBody, setCustomBody] = useState("");
  const [submittedCustomRecommendation, setSubmittedCustomRecommendation] =
    useState<HandoffRecommendation | null>(null);
  const [handoffSubmitVersion, setHandoffSubmitVersion] = useState(0);

  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [enablementJobId, setEnablementJobId] = useState<string | null>(null);
  const [enablementStartedAt, setEnablementStartedAt] = useState<number | null>(
    null,
  );
  const [buildJobId, setBuildJobId] = useState<string | null>(null);
  const [health, setHealth] = useState<{
    demo_mode: boolean;
    has_anthropic_key: boolean;
    boot_id: string;
  } | null>(null);
  // Tool set and role the current plan was shown for. A later change drops
  // the plan so a previous run cannot stay on screen for a new selection.
  const planSelectionKey = useRef<string | null>(null);

  useEffect(() => {
    const saved = readSession();
    fetchHealth()
      .then((report) => {
        setHealth(report);
        const sameServer =
          Boolean(saved?.bootId) && saved?.bootId === report.boot_id;
        if (saved && sameServer) {
          setSelected(new Set(saved.selected));
          setSelectedRoleState(saved.selectedRole);
          setFriction(saved.friction ?? "");
          setCustomTasks(saved.customTasks ?? []);
          if (saved.selectedRole && Array.isArray(saved.selectedTaskIds)) {
            restoredTasks.current = {
              role: saved.selectedRole,
              ids: saved.selectedTaskIds,
            };
            setCheckedTaskIds(new Set(saved.selectedTaskIds));
          }
          setResult(saved.result);
          setSelectedRecommendationId(saved.selectedRecommendationId ?? null);
          setSubmittedRecommendationId(saved.submittedRecommendationId ?? null);
          setCustomTitle(saved.customRecommendationTitle ?? "");
          setCustomBody(saved.customRecommendationBody ?? "");
          setSubmittedCustomRecommendation(
            saved.submittedCustomRecommendation?.id === CUSTOM_RECOMMENDATION_ID
              ? saved.submittedCustomRecommendation
              : null,
          );
          setEnablementJobId(saved.enablementJobId ?? null);
          setEnablementStartedAt(saved.enablementStartedAt ?? null);
          setBuildJobId(saved.buildJobId ?? null);
          if (saved.enablementJobId) setLoading(true);
          return;
        }
        setSelected(new Set());
        setSelectedRoleState(null);
        setWorkTasks([]);
        setCustomTasks([]);
        setCheckedTaskIds(new Set());
        setTasksLoadedFor(null);
        setFriction("");
        setResult(null);
        setSelectedRecommendationId(null);
        setSubmittedRecommendationId(null);
        setCustomTitle("");
        setCustomBody("");
        setSubmittedCustomRecommendation(null);
        setEnablementJobId(null);
        setEnablementStartedAt(null);
        setBuildJobId(null);
        writePendingTools([]);
        writePendingKeys([]);
      })
      .catch(() => setHealth(null))
      .finally(() => setSessionReady(true));
  }, []);

  useEffect(() => {
    listTools()
      .then((data) => {
        setTools(data);
      })
      .catch((e: Error) => setError(e.message));
    listRoles()
      .then(setRoles)
      .catch((e: Error) => setError(e.message));
    refreshSaved();
  }, []);

  useEffect(() => {
    if (!sessionReady || !health?.boot_id) return;
    const payload: HomeSession = {
      bootId: health.boot_id,
      selected: Array.from(selected),
      selectedRole,
      selectedTaskIds: Array.from(checkedTaskIds),
      customTasks,
      friction,
      result,
      selectedRecommendationId,
      submittedRecommendationId,
      customRecommendationTitle: customTitle,
      customRecommendationBody: customBody,
      submittedCustomRecommendation,
      enablementJobId,
      enablementStartedAt,
      buildJobId,
    };
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(payload));
    writePendingTools([]);
  }, [
    sessionReady,
    health,
    selected,
    selectedRole,
    checkedTaskIds,
    customTasks,
    friction,
    result,
    selectedRecommendationId,
    submittedRecommendationId,
    customTitle,
    customBody,
    submittedCustomRecommendation,
    enablementJobId,
    enablementStartedAt,
    buildJobId,
  ]);

  const taskKey = Array.from(checkedTaskIds).sort().join(",");
  const selectionKey = `${selectedRole ?? ""}::${Array.from(selected).sort().join(",")}::${taskKey}::${friction.trim()}`;

  useEffect(() => {
    if (!sessionReady) return;
    if (planSelectionKey.current === null) {
      planSelectionKey.current = selectionKey;
      return;
    }
    if (planSelectionKey.current === selectionKey) return;
    planSelectionKey.current = selectionKey;
    setResult(null);
    setSelectedRecommendationId(null);
    setSubmittedRecommendationId(null);
    setCustomTitle("");
    setCustomBody("");
    setSubmittedCustomRecommendation(null);
    setBuildJobId(null);
  }, [sessionReady, selectionKey]);

  const refreshSaved = () => {
    listSavedRecommendations()
      .then(setSavedRecs)
      .catch(() => {
        /* non-fatal */
      });
  };

  useEffect(() => {
    if (!selectedRole) {
      setWorkTasks([]);
      setTasksLoadedFor(null);
      return;
    }
    let cancelled = false;
    listWorkTasks(selectedRole)
      .then((tasks) => {
        if (cancelled) return;
        setWorkTasks(tasks);
        setCheckedTaskIds((current) => {
          const restored = restoredTasks.current;
          if (restored && restored.role === selectedRole) {
            restoredTasks.current = null;
            return new Set(restored.ids);
          }
          const next = new Set(tasks.map((task) => task.id));
          for (const id of current) {
            if (id.startsWith("custom-")) next.add(id);
          }
          return next;
        });
        setTasksLoadedFor(selectedRole);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRole]);

  const onRoleChange = (roleId: string) => {
    if (roleId === selectedRole) {
      setSelectedRoleState(null);
      setCustomTasks([]);
      setCheckedTaskIds(new Set());
      return;
    }
    setCustomTasks([]);
    setCheckedTaskIds(new Set());
    setTasksLoadedFor(null);
    setSelectedRoleState(roleId);
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

  const onResearchRole = async (name: string, roleId?: string) => {
    const added = await researchRole(name, roleId);
    const listed = await listRoles();
    const next = listed.some((role) => role.id === added.id)
      ? listed
      : [...listed, added].sort((a, b) =>
          a.display_name.localeCompare(b.display_name),
        );
    setRoles(next);
    if (added.id !== selectedRole) {
      setCustomTasks([]);
      setCheckedTaskIds(new Set());
      setTasksLoadedFor(null);
    }
    setSelectedRoleState(added.id);
    setSelectedRole(added.id).catch((e: Error) => setError(e.message));
  };

  const onDeleteCachedRole = async (id: string) => {
    await deleteCachedRole(id);
    setRoles(await listRoles());
    setSelectedRoleState((current) => (current === id ? null : current));
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

  const toggleTask = (id: string) => {
    setCheckedTaskIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const addTask = (label: string) => {
    const id = `custom-${Date.now()}`;
    const task: TaskChoice = {
      id,
      label,
      detail: "Added from the work you actually do.",
      source: "actual",
    };
    setCustomTasks((prev) => [...prev, task]);
    setCheckedTaskIds((prev) => new Set(prev).add(id));
  };

  const removeTask = (id: string) => {
    setCustomTasks((prev) => prev.filter((task) => task.id !== id));
    setCheckedTaskIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
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

  const taskRows: TaskChoice[] = [...workTasks, ...customTasks];
  const taskSelections = (): TaskSelection[] =>
    taskRows
      .filter((task) => checkedTaskIds.has(task.id))
      .map((task) => ({
        id: task.id,
        label: task.label,
        source: task.source,
      }));

  const submit = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    setSelectedRecommendationId(null);
    setSubmittedRecommendationId(null);
    setCustomTitle("");
    setCustomBody("");
    setSubmittedCustomRecommendation(null);
    setBuildJobId(null);
    try {
      const confirmed =
        selectedRole && tasksLoadedFor === selectedRole
          ? taskSelections()
          : undefined;
      const job = await startEnablementJob(
        Array.from(selected),
        selectedRole ?? undefined,
        confirmed,
        friction.trim(),
      );
      setEnablementJobId(job.id);
      setEnablementStartedAt(Date.parse(job.started_at));
    } catch (e) {
      setLoading(false);
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    if (!enablementJobId) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const job = await fetchJob<EnablementResponse>(enablementJobId);
        if (cancelled) return;
        if (job.status === "running") {
          const started = Date.parse(job.started_at);
          if (!Number.isNaN(started)) setEnablementStartedAt(started);
          return;
        }
        setEnablementJobId(null);
        setEnablementStartedAt(null);
        setLoading(false);
        if (job.status === "cancelled") return;
        if (job.status === "done" && job.result) {
          const plan = job.result;
          setResult(plan);
          setSubmittedRecommendationId(null);
          setSubmittedCustomRecommendation(null);
          setCustomTitle("");
          setCustomBody("");
          const ids = new Set(plan.plan.recommendations.map((rec) => rec.id));
          setSelectedRecommendationId((current) =>
            current && !isCustomRecommendationId(current) && ids.has(current)
              ? current
              : null,
          );
        } else setError(job.error ?? "Enablement run failed.");
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) {
          setEnablementJobId(null);
          setEnablementStartedAt(null);
          setLoading(false);
          setError("The backend stopped, so this run did not finish.");
        }
      }
    };
    const timer = setInterval(tick, 1000);
    void tick();
    const onVisible = () => {
      if (document.visibilityState === "visible") void tick();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [enablementJobId]);

  const stopEnablement = async () => {
    const jobId = enablementJobId;
    setEnablementJobId(null);
    setEnablementStartedAt(null);
    setLoading(false);
    if (!jobId) return;
    try {
      await cancelJob(jobId);
    } catch {
      // The poller also treats a missing job as finished.
    }
  };

  const customSelected = isCustomRecommendationId(selectedRecommendationId);
  const systemDraft =
    result?.plan.recommendations.find((rec) => rec.id === selectedRecommendationId) ??
    null;
  const customDraft = customSelected
    ? buildCustomRecommendation(
        { title: customTitle, body: customBody },
        Array.from(selected),
      )
    : null;
  const submittedRecommendation: HandoffRecommendation | null =
    isCustomRecommendationId(submittedRecommendationId)
      ? submittedCustomRecommendation
      : (result?.plan.recommendations.find(
          (rec) => rec.id === submittedRecommendationId,
        ) ?? null);
  const draftId = customSelected
    ? CUSTOM_RECOMMENDATION_ID
    : (systemDraft?.id ?? null);
  const customDirty =
    customSelected &&
    isCustomRecommendationId(submittedRecommendation?.id) &&
    !sameHandoffRecommendation(customDraft, submittedRecommendation);
  const handoffHint = !submittedRecommendation
    ? "Select a recommendation and press Submit to hand it to Grokbot."
    : (draftId && draftId !== submittedRecommendation.id) || customDirty
      ? `The Grokbot handoff stays on ${submittedRecommendation.id} until you submit again.`
      : null;
  const canSubmitRecommendation = customSelected
    ? customDraft != null
    : systemDraft != null;
  const submitRecommendation = () => {
    if (customSelected) {
      if (!customDraft) return;
      setSubmittedCustomRecommendation(customDraft);
      setSubmittedRecommendationId(customDraft.id);
      setHandoffSubmitVersion((version) => version + 1);
      return;
    }
    if (!systemDraft) return;
    setSubmittedCustomRecommendation(null);
    setSubmittedRecommendationId(systemDraft.id);
    setHandoffSubmitVersion((version) => version + 1);
  };
  const roleName =
    roles.find((role) => role.id === selectedRole)?.display_name ??
    selectedRole ??
    "Enable AI";

  return (
    <main className="space-y-8">
      <header>
        <h1 className="text-2xl font-bold">Enable AI — Agent Architect</h1>
        <p className="mt-1 text-sm text-neutral-600">
          Figure out what agent to build. Start from the work you actually do,
          then design the workflows you supervise. The blueprint feeds OpenAI
          Agents SDK, Claude, LangGraph, n8n, Copilot Studio, Zapier, and
          custom MCP.
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
          <h2 className="text-base font-semibold">1. Work intelligence</h2>
          <span className="text-xs text-neutral-500">
            Role, then the tasks you actually do
          </span>
        </div>
        <RolePicker
          roles={roles}
          selected={selectedRole}
          onSelect={onRoleChange}
          onResearch={onResearchRole}
          onDeleteCached={onDeleteCachedRole}
          disabled={loading}
        />
        {selectedRole && (
          <WorkIntelligence
            tasks={taskRows}
            selectedIds={checkedTaskIds}
            onToggle={toggleTask}
            onAdd={addTask}
            onRemove={removeTask}
            disabled={loading}
          />
        )}
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">2. Tools and friction</h2>
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
        <label className="mt-4 block text-sm font-medium" htmlFor="work-friction">
          Where this work gets stuck
        </label>
        <textarea
          id="work-friction"
          value={friction}
          onChange={(event) => setFriction(event.target.value)}
          disabled={loading}
          rows={3}
          placeholder="Name the retyping, the wait, or the handoff that breaks."
          className="mt-1 w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm"
        />
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
        {loading && (
          <div className="mt-4">
            <LoadingPanel
              demoMode={!!health?.demo_mode}
              startedAt={enablementStartedAt}
              onStop={stopEnablement}
            />
          </div>
        )}
      </section>

      {error && (
        <div className="rounded-md border border-rose-300 bg-rose-50 p-4 text-sm text-rose-800">
          <strong>Error:</strong> {error}
        </div>
      )}

      {result && !loading && (
        <section>
          <h2 className="mb-3 text-base font-semibold">4. Agent Blueprint</h2>
          {result.blueprint && (
            <AgentBlueprintView blueprint={result.blueprint} />
          )}
          <PlanDisplay response={result} />
        </section>
      )}

      {result && !loading && selectedRole && (
        <section>
          <h2 className="mb-3 text-base font-semibold">
            5. Pick one recommendation
          </h2>
          <p className="mb-3 text-sm text-neutral-700">
            Pick a recommendation to hand to Grokbot, or suggest your own.
            Grok Bot does the work.
          </p>
          <BuildOrchestrator
            plan={result.plan}
            roleId={selectedRole}
            selectedTools={Array.from(selected)}
            selectedRecommendationId={selectedRecommendationId}
            onSelectRecommendation={setSelectedRecommendationId}
            customTitle={customTitle}
            customBody={customBody}
            onCustomTitleChange={setCustomTitle}
            onCustomBodyChange={setCustomBody}
            onSaved={refreshSaved}
          />
          <button
            type="button"
            disabled={!canSubmitRecommendation}
            onClick={submitRecommendation}
            className={
              "mt-4 inline-flex items-center gap-2 rounded-md px-4 py-2 font-semibold text-white transition " +
              (!canSubmitRecommendation
                ? "cursor-not-allowed bg-neutral-400"
                : "bg-accent hover:bg-accent/90")
            }
          >
            Submit
          </button>
          {handoffHint && (
            <p className="mt-2 text-xs text-neutral-500">{handoffHint}</p>
          )}
        </section>
      )}

      {result && !loading && selectedRole && submittedRecommendation && (
        <section>
          <h2 className="mb-3 text-base font-semibold">
            6. Hand {submittedRecommendation.id} to Grokbot
          </h2>
          <GrokbotHandoff
            key={`${submittedRecommendation.id}:${handoffSubmitVersion}`}
            recommendation={submittedRecommendation}
            roleName={roleName}
            roleId={selectedRole}
            tools={
              submittedRecommendation.tools_affected.length > 0
                ? submittedRecommendation.tools_affected
                : Array.from(selected)
            }
          />
        </section>
      )}

    </main>
  );
}
