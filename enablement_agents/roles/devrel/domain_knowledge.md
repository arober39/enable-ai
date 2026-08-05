# Developer Relations Enablement — Domain Knowledge

This document is the DevRel Enablement Agent's reference for what AI-enabled developer relations looks like. Ground recommendations against it.

## Functional capabilities of an AI-enabled DevRel function

### 1. Tutorial and blog drafting

First-pass developer content — tutorials, blog posts, integration guides, release notes. Native AI in CMS platforms (Contentful AI, Notion AI) drafts generic prose. Custom AI augments by writing against your actual API surface — reading the OpenAPI spec, the SDK code, the existing docs — so the draft uses real endpoints and real code, not plausible-sounding inventions.

Failure mode: tutorials that hallucinate APIs that don't exist. Mitigation: every code snippet runs through a verification step before publish.

### 2. Code sample generation and verification

Producing example code for SDK use, common integrations, and tutorials. Native AI is decent at generating code; it is bad at guaranteeing the code runs. Custom AI augments by executing every snippet against a sandbox or test harness and refusing to ship samples that fail.

Failure mode: copy-pasteable code that breaks on the developer's machine. The signal a code sample is real is reproducibility, not plausibility.

### 3. Community sentiment analysis

Reading what developers are saying about your product across Discord, GitHub, Stack Overflow, Reddit, and forums. Native AI in community platforms is limited to that platform's surface. Custom AI augments by unifying across channels and surfacing themes — "complaints about cold starts have tripled this week" — that no single channel reveals.

Failure mode: false positives that send DevRel chasing non-issues. Mitigation: every theme must cite ≥3 source posts before it lands in the digest.

### 4. Documentation gap identification

Finding gaps between what developers ask about and what the docs cover. AI is well-suited to this: cluster forum questions and support tickets, intersect with the docs site map, surface the un-covered topics. Native tools rarely do this; custom AI is the standard pattern.

Failure mode: gap reports that flag topics the docs already cover (the AI just didn't find them). Mitigation: the agent must read the docs before declaring a gap.

### 5. Open-source issue and PR triage

For OSS projects, categorizing inbound issues (bug, feature, support question, duplicate) and triaging PRs (ready for review, needs author changes, ready to merge). Native AI in GitHub (Copilot for PRs) does this. Custom AI augments by reading the project's contribution guide + recent maintainer decisions + the issue's actual reproduction steps to produce a richer triage than label-and-assign.

Failure mode: confident triages on issues the AI didn't actually reproduce or understand. Maintainers stop trusting the labels.

### 6. Developer survey synthesis

Reading open-text survey responses and producing structured insights. Generic NLP tools cluster responses; they don't relate clusters to product decisions. Custom AI augments by joining survey themes with current roadmap items — "respondents are asking for a feature you already shipped in beta" → marketing problem, not product problem.

Failure mode: themes that don't connect to actions. Every theme should propose a specific intervention (doc change, product change, marketing change).

### 7. Conference talk and content recommendation

Choosing which talks to give, which podcasts to appear on, and which content to publish based on developer interest data. Native AI doesn't cover this. Custom AI augments by joining community-sentiment themes (capability 3), documentation gaps (capability 4), and product roadmap to recommend a content calendar that matches what developers actually want.

Failure mode: recommendations that ignore DevRel team bandwidth. The agent should propose a content slate, not a content tsunami.

## Tool integration patterns

DevRel stacks blend public surfaces (Discord, GitHub, Stack Overflow, forums, X) with internal tools (CMS, analytics, CRM-for-developers like Common Room or Orbit). AI orchestrators are valuable when they bridge public + private surfaces — e.g., "this Discord thread is about a bug filed yesterday by an account on our highest plan" → priority signal no single tool sees.

## Failure modes specific to DevRel

- **Hallucinated APIs.** The single most damaging failure mode. Every code-touching output must verify against the real API surface before shipping.
- **Tone-deaf community responses.** AI-drafted community replies that read as corporate marketing destroy DevRel credibility. Mitigation: every public reply passes a "does this sound like an engineer wrote it" judge.
- **Triage fatigue.** AI that floods maintainers with low-confidence triage labels gets disabled. The orchestrator must default to "uncertain" and stay quiet.
- **Engagement vanity.** AI-recommended content that wins on impressions but loses on developer activation. Every recommendation should tie back to a signup, an integration, or a documented use case.
