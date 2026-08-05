# Marketing Enablement — Domain Knowledge

This document is the Marketing Enablement Agent's reference for what AI-enabled marketing looks like in practice. Use it to ground recommendations; do not freelance capability lists from memory.

## Functional capabilities of an AI-enabled marketing function

There are seven capabilities a credible AI-enabled marketing stack covers. Each maps to a class of automation the agent should evaluate the declared tool stack against.

### 1. Audience segmentation

Splitting an addressable audience into groups whose response to a campaign is meaningfully different. Native AI in CRMs (HubSpot, Salesforce Marketing Cloud) does this with built-in lookalike and behavioral clustering. Custom AI augments it by joining product-usage events with CRM properties — segmentation by usage intensity, feature adoption, churn risk — that no single marketing tool can see alone.

Failure mode: segmentation that splits audiences without lifting conversion. If the segment isn't actionable (no differentiated message, no differentiated channel), it's a vanity slice.

### 2. Content drafting

First-pass content for email, ads, landing pages, and social. Native AI in email platforms (Mailchimp, Klaviyo) is strong at subject lines and short body copy with brand-voice priming. Custom AI augments by inserting product-context the marketing tool can't see — e.g., "this customer is on the Pro plan and just hit the seat limit" → an upgrade email that references their actual usage.

Failure mode: generic copy that performs like a template. The signal a draft is working is whether marketers ship it with light edits vs. rewriting from scratch.

### 3. Campaign A/B test analysis

Reading test results, deciding statistical significance, and recommending the winner. Most marketing tools auto-pick winners on raw conversion, ignoring sample size or downstream metrics (revenue, retention). Custom AI augments by reading the test, the segment, the downstream funnel, and flagging "this winner is significant on click-through but the loser converts better to revenue."

Failure mode: declaring winners on too few sessions. AI should refuse to call a test when the confidence interval is too wide.

### 4. Lead scoring and qualification

Ranking leads by likelihood of conversion. Native AI in marketing automation (HubSpot, Marketo) does behavior-based scoring (page views, email opens). Custom AI augments by joining intent data (firmographic + technographic + product signals) into a unified score that sales actually trusts.

Failure mode: lead scoring inflation. If everyone is "hot," the score is useless. Score discipline is the agent's job.

### 5. Persona generation

Synthesizing observed customer data into named personas marketing can target. AI is good at generating plausible personas from data; it is bad at validating that the personas are real. Custom AI augments by grounding persona claims in actual recorded interviews + survey responses + product usage — refusing to invent attributes without evidence.

Failure mode: confident personas that don't match any real customers. The mitigation is requiring citations to source interactions per persona attribute.

### 6. SEO and SEM keyword research

Identifying target keywords, drafting metadata, and proposing content briefs. Native AI in SEO platforms (Ahrefs, Semrush) covers keyword volume and difficulty. Custom AI augments by ranking keywords against the actual products being sold and the actual content already published — closing the gap between "keywords we could rank for" and "keywords that would convert if we ranked."

Failure mode: chasing high-volume keywords with no buying intent.

### 7. Performance attribution

Connecting marketing spend to revenue. Native AI in attribution platforms is improving but bounded to the channels they can see. Custom AI augments by joining first-party identity (email, account ID) across paid, organic, and product channels to model multi-touch attribution that respects offline conversions.

Failure mode: last-click attribution dressed up as multi-touch. The agent should flag when an attribution model conflates correlation and causation.

## Tool integration patterns

Marketing stacks almost always have a CRM as the system of record, an email/automation platform, an analytics platform, and one or more paid channels. AI orchestrators add value when they sit across these and emit cross-tool signals — e.g., "this user clicked the Pricing page, opened the welcome email twice, and bounced from a tutorial video" → score boost that triggers a sales hand-off.

## Failure modes specific to marketing

- **Brand voice drift.** AI drafts that read off-tone erode trust. Mitigation: every customer-facing draft passes a brand-voice judge before it ships.
- **Compliance exposure.** Auto-personalized content can trip GDPR / CAN-SPAM / health-vertical rules. The orchestrator must refuse to use protected attributes for targeting without explicit opt-in.
- **Stale segments.** Audience segments cached for too long misfire. Recompute cadence is a real configuration decision the orchestrator should expose.
- **Channel cannibalization.** AI that allocates spend within one channel without seeing the others over-invests in the easy channel. Multi-channel attribution must be a first-class input.
