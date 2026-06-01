---
name: replay-traffic
description: Drive synthetic support traffic through a specific AI Config variation for tutorial reproduction.
argument-hint: "<variation-name>"
context: main
allowed-tools: ["Bash"]
---

# /replay-traffic

Run the synthetic traffic replay against a named AI Config variation. This is used for tutorial reproduction (e.g., generating the traffic pattern that the multi-signal guardrails tutorial responds to).

## Why `context: main`

This skill is a shell wrapper — it invokes `scripts/replay_traffic.py` and reports the result. There is no investigative context to isolate. Forking would just add a layer that prevents the output from flowing back naturally.

## Steps

1. Confirm `$ARGUMENTS` is a non-empty variation name. If empty, print usage and stop.
2. Confirm `data/support/replay_scenarios.json` exists. If not, the user needs to run `make install` and Phase 6 setup first.
3. Run `make replay-traffic VARIATION=$ARGUMENTS`. Stream the output.
4. After completion, summarize: number of conversations sent, latency stats, any errors observed.

## What this skill does NOT do

- It does not modify the AI Config (no traffic routing changes — that is `scripts/setup_ai_configs.py`).
- It does not assert anything about the variation's quality — interpretation of the replay output is the user's call.
