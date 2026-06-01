"use client";

import { useEffect, useState } from "react";
import Spinner from "./Spinner";

interface Props {
  demoMode: boolean;
}

/** Prominent "in-progress" panel shown while a run is in flight.
 *
 *  Three signals to make sure the user knows things are happening:
 *    1. Big spinner (CSS animation, runs continuously)
 *    2. Live elapsed-time counter (tabular nums, updates 10x/sec)
 *    3. Indeterminate animated progress bar at the bottom
 *
 *  Different copy for demo vs. live mode so the user has a sense of how
 *  long to expect.
 */
export default function LoadingPanel({ demoMode }: Props) {
  const [elapsedMs, setElapsedMs] = useState(0);

  useEffect(() => {
    const start = Date.now();
    const interval = setInterval(() => {
      setElapsedMs(Date.now() - start);
    }, 100);
    return () => clearInterval(interval);
  }, []);

  return (
    <div
      className="rounded-lg border border-accent/40 bg-accent/5 p-6 shadow-sm"
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-4">
        <Spinner className="h-7 w-7 text-accent" />
        <div className="flex-1">
          <h3 className="font-semibold text-ink">
            Running Support Enablement Agent…
          </h3>
          <p className="mt-1 text-sm text-neutral-700">
            {demoMode ? (
              <>Building synthetic plan from the tool catalog. Should take under a second.</>
            ) : (
              <>
                Agent is gathering tool capabilities, consulting domain
                knowledge, and drafting recommendations. This typically takes
                <span className="font-medium"> 10–30 seconds</span> in live mode.
              </>
            )}
          </p>
        </div>
        <div
          className="font-mono text-3xl tabular-nums text-accent"
          aria-label={`${(elapsedMs / 1000).toFixed(1)} seconds elapsed`}
        >
          {(elapsedMs / 1000).toFixed(1)}s
        </div>
      </div>

      {/* Indeterminate progress bar — the bar slides left-to-right
          continuously. CSS keyframes are in globals.css. */}
      <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-accent/10">
        <div className="animate-indeterminate h-full w-1/3 rounded-full bg-accent" />
      </div>

      {!demoMode && elapsedMs > 35_000 && (
        <p className="mt-3 text-xs text-amber-700">
          Taking longer than usual — the agent may be on its second or third
          turn of tool calls. Hang tight, or check the backend terminal for
          progress.
        </p>
      )}
    </div>
  );
}
