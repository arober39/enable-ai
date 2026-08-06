# Episode 1 — Launch

*Tier 2. Trigger: Milestone 0 ships (repo public, VISION.md). Formats: LinkedIn post + live stream; clips and tutorial cut from the recording afterward.*

---

## LinkedIn post (draft)

I spent the last two months building an AI workflow builder.

Pick your role, add your tools, and an agent researches them, recommends automations, and builds a workflow you can run from one chat. It works. And somewhere along the way I realized I was building the wrong half of the product.

Here's the thing: "chat that executes tasks across your tools" is being commoditized in real time. Claude and ChatGPT connect to your tools natively now. Zapier, Lindy, n8n — everyone builds workflows from a prompt. That part of my vision stopped being a product and became a feature.

But there's a half nobody builds: **diagnosis**. Every one of those tools assumes you already know what to automate. Nobody looks at a team's actual stack and says: here's the AI feature you're already paying for and not using, here are the two tools doing the same job, here's the one workflow actually worth building — and here's proof it paid off.

My own codebase figured this out before I did. Of the three artifact types my generator produces, only one is an executable workflow. The other two are a setup guide and a consolidation plan. Enablement artifacts. The code voted.

So I'm repositioning: **Enable AI** is now a diagnosis-first AI enablement platform. Diagnose → recommend → execute → measure.

And I'm doing it in a way that doubles the fun: I'm building a **software factory** to build it — work orders in, agent-built PRs through quality gates out, every change traceable — and building the whole thing in public. Every work order becomes a post. Every milestone becomes a live build. Every failure becomes the most useful content.

First live stream: [DATE]. Repo: [LINK]

Gates first, robots second. 🏭

---

## Live stream outline (~60 min): "The rethink, the repo, and the factory"

**1. Cold open (5 min)** — One sentence each: what I built, why I'm rethinking it, what the factory is. Show the commit log: two months of work landing as nine commits, live on screen.

**2. Tour what exists (15 min)** — The working app end to end on Serenia & Co. demo data: pick a role → research a tool by typing its name → recommendations → build one → run an inquiry and walk the step trace. Beat to land: *"LLM output never executes — only validated JSON does, through a runtime I own."*

**3. The rethink (10 min)** — The commoditization argument (platform vendors + MCP registries ate the connectivity moat). The diagnosis gap. The "my code voted" story — screen-share the three artifact kinds. New spine: diagnose → recommend → execute → measure, and why *measure* is the loop nobody closes.

**4. The factory (15 min)** — VISION.md milestones table on screen. What a software factory is (30-second version, credit the buzz). The three work-order types, the gates, provenance. The dogfooding twist: the factory's agents run on the same LaunchDarkly control plane the product uses — same AI Configs, judges, and metrics at both altitudes.

**5. What's next + the invitation (10 min)** — Milestone 1 is gates: CI plus two review agents on every PR, before any agent writes code. The `experiment` work-order standing invitation: suggest a tool in chat, it becomes a work order, I test it against the gates and report honestly. Where to follow.

**6. Q&A (5–10 min)**

## Clip beats (cut from the recording)

1. **"LLM output never executes."** The interpreter docstring + a live step trace. (~45s, from segment 2)
2. **"My code voted for the product before I did."** The three artifact kinds reveal. (~60s, from segment 3)
3. **"Gates first, robots second."** Why the factory starts with quality gates, not coding agents. (~45s, from segment 4)

## Before publishing

- [ ] Fill [DATE] and [LINK]; repo must be public first (team alignment check done)
- [ ] Dry-run the demo path on fresh state — role → research → recommend → build → run — so the live tour has no dead ends
- [ ] Verify nothing sensitive on screen: `.env`, credential store, LD internal dashboards
- [ ] Add Episode 1's talk abstract to `talks.md` after it ships
