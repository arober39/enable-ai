# Support Enablement Agent — Domain Knowledge

This document is the Support Enablement Agent's reference for what AI-enabled customer support looks like. The agent reads it as part of its system prompt context and grounds its capability assessments and recommendations against it.

It does **not** describe the runtime support orchestrator's behavior. It describes the *space of capabilities* a customer-support function might want to enable with AI, so the agent can compare a department's declared stack against that space and recommend coverage, augmentation, consolidation, or orchestration.

## Functional capabilities of an AI-enabled support function

There are seven capabilities the agent should consider on every assessment. For each, it should ask: which tool in the stack covers this today (native AI, manual workflow, neither)? If covered, is the coverage strong, partial, or only superficial? If missing or weak, is the right move to use a tool's native AI more deeply, augment with custom AI, consolidate to a better-covered tool, or orchestrate across multiple tools?

### 1. Intent classification

Categorizing inbound messages by what the customer is asking for: refund, escalation, FAQ, status check, complaint, sales inquiry, billing, account change, etc. Good intent classification routes the conversation to the right downstream skill or human, surfaces volume trends to ops, and lets the orchestrator pick a response template appropriate to the category.

Examples of native AI features that cover this: Zendesk's intelligent triage, Intercom's Fin (partial — primarily resolution-focused but does some routing). Custom AI augmentation looks like a small classifier trained or prompted on the team's last 90 days of categorized tickets, exposed as a tool the orchestrator calls before anything else.

### 2. First-response drafting

Generating the first reply to a customer ticket based on the message content, the customer's history, and the team's policies. The draft is usually reviewed by a human at tier-1; in mature setups the orchestrator sends it directly for low-risk categories and only routes ambiguous or high-stakes tickets to humans.

Native AI features that cover this: Intercom's AI Compose, Zendesk's generative replies. Both are competent but limited to the data inside their host tool — they can't pull policy from a knowledge base outside Zendesk, or customer plan tier from the CRM, without additional integration work. The augmentation pattern is to wrap a custom LLM call with retrieval over the team's actual policy and CRM data.

### 3. Escalation routing

Deciding when a ticket needs to leave tier-1 — to a team lead, to legal, to finance, to product engineering — and routing it accordingly. The decision is multi-factor: customer tone, financial impact, mention of legal action, plan tier, prior escalations.

There is generally no native AI that does this well across an entire stack — escalation routing is the canonical multi-signal problem, and most native tools see only one signal. The augmentation pattern is a custom classifier that reads from CRM, ticketing, and policy at once and posts a structured handoff message to the right Slack channel. This is the right place for an orchestrator to add value.

### 4. FAQ retrieval

Looking up the answer to a common question from a knowledge base and returning it with citations. The customer might ask in a phrase the article doesn't use ("how do I cancel" vs. "termination policy"); good retrieval is semantic, not lexical.

Native AI features that cover this: Zendesk AI Agents and Intercom Fin both retrieve and answer from connected help content. Coverage is strong when the knowledge base is well-maintained, weaker when it isn't. Custom augmentation rarely beats the native tools at this — the right move is usually to invest in knowledge base quality first.

### 5. Sentiment analysis

Detecting emotional tone (anxious, frustrated, hostile, satisfied) from the customer's message and surfacing it to the agent or routing logic. Sentiment is a useful signal for escalation routing and for prioritizing inbox order, but it is rarely actionable on its own — a frustrated customer asking a simple question is still a simple question.

Native coverage: most modern ticketing tools include basic sentiment classifiers. Custom augmentation is rarely worth the effort unless sentiment is feeding into a specific downstream decision (e.g., gating which response variations a guarded rollout is allowed to serve).

### 6. Conversation summarization

Producing a short, structured summary of a long conversation at handoff time so the next agent doesn't have to read the whole thread. Useful at human-to-human handoffs, AI-to-human escalations, and end-of-day reporting.

Native coverage: Intercom's conversation summarization is GA and strong; Zendesk has similar features. Custom augmentation rarely beats the native tools and is typically only worth doing if summaries need to land in a format the native tools don't produce (e.g., as a structured Slack handoff message).

### 7. Knowledge base search (semantic)

Searching the knowledge base from outside the host tool — from a CRM contact view, from a Slack channel, from a custom orchestrator. This is distinct from FAQ retrieval inside the ticketing tool's own UI. The augmentation pattern is exposing the knowledge base's content (often via an MCP server) so other surfaces can ground their responses against it.

This is where MCP-first design pays off. If the knowledge base has an MCP server, every other AI surface in the org can ground against it for free. If it doesn't, the orchestrator builds a minimal server stub against the REST API.

## Common integration patterns

A support orchestrator typically composes from four building blocks:

- **Ticketing as input.** The customer's message arrives in a ticketing tool (Intercom, Zendesk, Freshdesk). The orchestrator triggers off the inbound message via webhook or polling and uses the ticketing tool's API to send the reply.
- **CRM as context.** The customer's plan tier, account history, prior tickets, and subscription status come from the CRM (HubSpot, Salesforce). The orchestrator pulls these to ground its response — a Signature-tier customer with a long history gets a different first response than an Essentials prospect.
- **Knowledge base as ground truth.** Policies, FAQs, and procedural documentation live in the knowledge base (Zendesk Guide, Notion, Confluence) or in version-controlled markdown (`data/<dept>/policies.md` in Enable AI's case). The orchestrator retrieves the relevant content and grounds the reply against it.
- **Internal collaboration as handoff.** Escalations and team coordination happen in Slack. The orchestrator posts structured handoff messages into the right channel when its confidence is low or the case warrants a human.

## Failure modes specific to support

These are the failure modes the agent must protect against when recommending an architecture. They drive recommendations toward augmentation patterns rather than pure use_native_ai when the native tool can't see the data needed to avoid them.

### Hallucinated policy details

The agent's response confidently asserts a policy claim that isn't in the documentation. This is the failure mode the v2-detailed-responses prompt is designed to exhibit — and the multi-signal guardrails tutorial is designed to catch. The mitigation at the architecture level is to ground every policy-touching response in retrieval against the actual policy file, and to attach a factual-accuracy judge to any rollout. Native AI features alone do not protect against this unless the knowledge base is the single source of truth.

### Over-escalation

The agent escalates everything to a human, defeating the purpose of automation. This usually comes from low-confidence routing — the classifier flags too many cases as "uncertain" — or from a system prompt that's too risk-averse. The recommendation pattern is to instrument escalation rate as a metric, ramp confidence thresholds against historical traffic, and only ship aggressive automation behind a guarded rollout.

### Premature resolution

The agent marks a ticket resolved when the customer's actual question wasn't addressed. This happens when intent classification picks the wrong category, or when FAQ retrieval returns a near-miss article that the agent then summarizes confidently. The mitigation is asking the customer to confirm before closing, and instrumenting "reopen rate" as a quality metric.

### Tone-deafness

The response is technically correct but lands wrong — wedding-day panic met with a templated FAQ, refund dispute met with marketing-speak. This is especially costly at Serenia given the events context. The mitigation is brand-voice grounding (the agent's system prompt should reference the brand voice section of the company bible) and a separate judge that scores tone against the voice rules.

## What to do when assessing a stack

For every tool in the declared stack, call `lookup_tool_capability` and read the returned data. Do not guess. For every functional capability above, identify which tool covers it and to what extent. Surface gaps as `gap` findings. Surface near-duplicates as `redundant` findings. Surface tools that need custom AI on top as `augment_with_custom_ai` recommendations. Surface tools that should be operated together as `orchestrate` recommendations. Use `use_native_ai` only when the native feature is genuinely sufficient with no augmentation needed — set a high bar for that.
