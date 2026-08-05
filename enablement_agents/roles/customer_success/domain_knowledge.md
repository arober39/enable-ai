# Customer Success Enablement — Domain Knowledge

This document is the Customer Success Enablement Agent's reference for what AI-enabled customer success looks like. Ground recommendations against it.

## Functional capabilities of an AI-enabled CS function

### 1. Health score modeling

Producing a per-account health score that predicts renewal likelihood. Native AI in CS platforms (Gainsight, ChurnZero, Vitally) does this with built-in product-usage + support-ticket signals. Custom AI augments by adding signals these platforms can't see — call sentiment, executive engagement, contract changes — and by recomputing daily rather than weekly.

Failure mode: a health score that doesn't move until the account is already lost. The signal a score is real is whether it precedes churn by 60+ days, not lags it.

### 2. Churn risk prediction

Identifying accounts likely to churn at next renewal, with enough lead time to intervene. Native AI does this with usage decay heuristics. Custom AI augments by reading the actual customer's reasons (support tickets, call transcripts, email sentiment) and proposing a specific intervention — "executive QBR" vs. "discount renewal" vs. "feature training" — rather than generic risk flags.

Failure mode: high-confidence churn predictions with no actionable recommendation. A risk score is only useful when paired with a play the CSM can run.

### 3. Renewal forecasting

Modeling the renewal pipeline: expected close dates, expansion vs. flat vs. downgrade, dollar amounts. Native AI in CRMs covers basic forecasting. Custom AI augments by joining historical renewal motion with current account state — "this customer is showing the same pattern as last 3 churns at this stage" — that humans can't pattern-match across thousands of accounts.

Failure mode: forecast confidence that doesn't degrade when input signals are stale.

### 4. Expansion identification

Spotting accounts ready for upsell (more seats, higher tier, additional product). Native AI flags usage caps. Custom AI augments by combining usage patterns with org-chart data, recent funding events, and product roadmap fit — proposing not just "they're at the seat cap" but "they hit the cap two weeks ago and three more users tried to log in yesterday — pitch the next tier this week."

Failure mode: pitching expansion to accounts mid-churn. The orchestrator must refuse to flag expansion when health score is red.

### 5. QBR and EBR preparation

Generating the deck and talking points for executive business reviews. Native AI in CS platforms produces templated decks. Custom AI augments by pulling product usage trends, recent support tickets, ROI calculations, and executive priorities from CRM notes — producing a draft that the CSM edits rather than writes from scratch.

Failure mode: a deck full of metrics the executive doesn't care about. Personalization to the customer's actual priorities is the differentiator.

### 6. CS playbook recommendation

Choosing which playbook (onboarding nudge, executive escalation, training session, etc.) to run for a given account state. Native AI in CS platforms triggers playbooks on rules. Custom AI augments by reading the full account context and recommending a play even when no rule fires — catching the long-tail of situations rule engines miss.

Failure mode: too many playbook recommendations, none acted on. The agent's job is curation, not generation.

### 7. Call and email summarization

Producing structured summaries of customer calls and email threads. Native AI in call platforms (Gong, Chorus) does this well. Custom AI augments by joining the summary with CRM context — "this is the third escalation about this feature; previous two were closed without resolution" — so the summary is actionable, not just descriptive.

Failure mode: summaries that capture what was said but not what to do next. Every summary should end with proposed next actions.

## Tool integration patterns

A modern CS stack has a CRM (Salesforce, HubSpot), a CS platform (Gainsight, ChurnZero), a product analytics tool (Amplitude, Pendo), a call recording tool (Gong, Chorus), and a ticketing tool (Zendesk, Intercom). AI orchestrators add value by stitching these together — the most valuable signals always cross tool boundaries.

## Failure modes specific to CS

- **Over-alerting.** CSMs ignore an alert stream that fires constantly. The orchestrator must aggregate signals into a small number of high-confidence asks per week.
- **Hallucinated account state.** AI that confidently misreports usage or contract details destroys trust. Every account-state claim must cite its source row.
- **Playbook drift.** AI-recommended plays must match the plays the CS team actually runs. Generic plays from training data don't fit.
- **Renewal blind spots.** Models trained on annual renewal data miss monthly/quarterly accounts. The orchestrator should expose the time-horizon assumption explicitly.
