# Serenia & Co. — World Bible

Serenia & Co. is the fictional company that Enable AI operates on. This document is the world bible: who works there, who buys from them, what scenarios recur, and how the brand sounds. All synthetic data in `data/` should be consistent with what is described here.

## What Serenia does

Serenia & Co. is a mid-sized **events and venues company**. Customers book Serenia to host weddings, corporate offsites, conferences, and private parties at one of Serenia's three owned venues — or, when the event calls for a location Serenia doesn't own, at a curated partner venue Serenia coordinates on the customer's behalf.

The three owned venues:

- **Hudson Valley (Garrison, NY)** — Serenia's East Coast flagship. Restored 1890s estate; capacity ~180. Weddings, milestone celebrations.
- **Sonoma (Glen Ellen, CA)** — Wine-country property. Capacity ~120. Strong for corporate offsites and intimate weddings.
- **Big Sur (Big Sur, CA)** — Coastal premium. Capacity ~90. Higher-end partner retreats, leadership offsites, destination weddings.

Customers book Serenia to plan and run a single high-stakes event (a wedding, a 50-person company retreat, a milestone birthday). For events at the three owned venues, Serenia is the operator; for partner-venue events, Serenia coordinates venues, vendors, catering, lodging, and on-site staffing on the customer's behalf.

- Founded **2018** in Portland, OR (corporate HQ; venues are separate). Roughly **280 employees** as of early 2026.
- Annual revenue ~$78M. Mid-sized: not a marketplace, not a tiny boutique. Each engagement is a meaningful project, not a SaaS subscription.
- Customers are a mix of individuals (milestone weddings, family reunions) and SMB / mid-market companies (offsites, sales kickoffs).
- The product is part SaaS (event-planning surface, vendor catalog, RSVPs), part services (a Serenia "event lead" assigned to every booking above a threshold).

The events context matters for Enable AI: support tickets are urgent (an event is *next week*), refunds are large and policy-sensitive, and the brand voice has to be reassuring without overpromising.

## Org chart — 8 departments

| Department      | Head                  | Headcount | Brief                                                                          |
|-----------------|-----------------------|-----------|--------------------------------------------------------------------------------|
| Engineering     | Priya Venkataraman    | 62        | Platform, vendor catalog, booking surface, integrations.                       |
| Product         | Marcus Holm           | 18        | PMs and designers across booking, planner tools, and event-day app.            |
| Customer Support| Naomi Eze             | 34        | Front-line ticketing, escalation, customer success ops.                        |
| Sales           | Diego Restrepo        | 26        | SMB and mid-market outbound; account execs for corporate offsites.             |
| Marketing       | Elena Petrova         | 14        | Content, brand, partnerships, paid acquisition.                                |
| HR / People Ops | Jordan Whitfield      | 9         | Recruiting, onboarding, benefits, employee relations.                          |
| Legal           | Annika Sørensen       | 5         | Vendor contracts, customer agreements, refund disputes, IP.                    |
| Finance         | Wendell Park          | 11        | AR/AP, vendor payouts, customer refunds, internal forecasting.                 |

The remaining ~100 staff are field event leads, vendor relations, and operations.

### Named employees per department (3-5 each)

These are the names that appear in synthetic tickets, Slack threads, internal handoffs.

**Engineering**
- Priya Venkataraman — VP Engineering
- Sam Okafor — Staff engineer, vendor catalog
- Lena Markovic — Senior engineer, booking surface
- Tariq Hassan — Engineering manager, integrations

**Product**
- Marcus Holm — VP Product
- Hana Kobayashi — Senior PM, planner tools
- Quentin Moreau — PM, event-day app
- Iris Donovan — Lead designer

**Customer Support**
- Naomi Eze — Director of Support
- Reuben Vasquez — Support team lead (tier 2)
- Aaliyah Brennan — Senior support specialist
- Felix Thanh — Support specialist
- Margaux Lefebvre — Support specialist

**Sales**
- Diego Restrepo — VP Sales
- Yuki Nakamura — Senior AE, mid-market
- Ronan Carmichael — AE, SMB
- Inés Calderón — Sales operations

**Marketing**
- Elena Petrova — VP Marketing
- Cyrus Abadi — Brand manager
- Marisol Henriquez — Content lead
- Theo Lindqvist — Performance marketing

**HR / People Ops**
- Jordan Whitfield — Head of People
- Sade Adeyemi — Recruiter
- Connor Bishop — People ops generalist

**Legal**
- Annika Sørensen — General Counsel
- Devon Pritchard — Contracts associate
- Mei-Lin Chu — Paralegal

**Finance**
- Wendell Park — VP Finance
- Beatriz Sandoval — Senior accountant
- Henrik Olafsson — AP specialist
- Camille Rousseau — Financial analyst

## Customer personas (5)

These five personas drive the synthetic ticket data in `data/support/tickets.json`.

### 1. The First-Time Wedding Couple — *Avery & Jordan Patel*
- Booking a 110-person wedding 11 months out. Combined HHI ~$220k. Anxious, detail-oriented, will email about anything from napkin color to cancellation policy.
- Plan tier: **Signature** (mid-tier).
- Typical ticket: "Can we still change the appetizer selection?" "What happens if our florist cancels?"
- Failure mode if mishandled: posts a 1-star review citing slow response time.

### 2. The Corporate Offsite Planner — *Devon Reyes (Coordinator at NovaPath Health)*
- Booking a 60-person company offsite 8 weeks out. Buying on behalf of the company; CC'd on every email by their VP People.
- Plan tier: **Enterprise** (custom contract).
- Typical ticket: "We need to add a vegan menu and 4 ADA-accessible rooms by Friday." "Can you send us a SOC 2 attestation?"
- Failure mode if mishandled: escalates to legal/procurement, threatens to pull the booking.

### 3. The Milestone Birthday Host — *Renata Aguilar-Pham*
- Booking a 50-person 60th birthday celebration for her mother in Mexico City, 4 months out.
- Plan tier: **Signature**.
- Typical ticket: "My mom can't fly anymore — can we move this to Sausalito instead?" "Are the vendors bilingual?"
- Failure mode if mishandled: emotional escalation, refund dispute, posts to local community forum.

### 4. The Repeat SMB Customer — *Owen Bridgewater (Founder, Bridgewater Climbing Gyms)*
- Books 2 events/year: an annual customer appreciation party and a staff holiday party. Has been a customer for 3 years.
- Plan tier: **Signature** with loyalty perks.
- Typical ticket: "Same as last year, but 25% bigger." "The vendor you sent for the 2024 party was great — can we get them again?"
- Failure mode if mishandled: silently churns to a competitor.

### 5. The Last-Minute Family Reunion — *The Okonkwo Family (primary contact: Adaeze Okonkwo)*
- 35-person family reunion booked 9 weeks out for a multi-generational gathering. Multiple decision-makers in the family, sometimes conflicting requests.
- Plan tier: **Essentials** (entry tier).
- Typical ticket: "My uncle wants to add 4 kids and switch the menu to halal." "Can you just call my mom directly?"
- Failure mode if mishandled: confusion across family members, double-booking, last-week panic.

## Recurring scenarios (3)

These are the scenarios that show up across departments and that the Support orchestrator (and eventually other orchestrators) must handle gracefully.

### Scenario A: Vendor cancellation, 2 weeks out
A confirmed vendor (catering, florist, AV) cancels with under 3 weeks of lead time. The customer learns either directly from the vendor or from Serenia.

- **Support**: ticket comes in panicked. Needs immediate acknowledgement and a path forward.
- **Operations**: vendor relations scrambles for a replacement.
- **Finance**: deposit return / re-booking fees with the new vendor.
- **Legal**: if the cancellation breaches the vendor contract, contracts associate is looped in.

### Scenario B: Last-week scope change
The customer asks for a non-trivial scope change inside the last 7 days before the event (add 12 guests, change the venue layout, swap menu). Some changes are accommodable, some are not.

- **Support**: triage — feasible vs. infeasible. Needs the planner tool's state to answer.
- **Product / Engineering**: if the planner tool can't represent the change, the event lead does it manually and re-syncs later.
- **Finance**: pricing changes flow through and may trigger a contract amendment.

### Scenario C: Post-event refund dispute
The customer is unhappy after the event (vendor underdelivered, venue issue, weather) and requests a partial refund. Refund authority is tiered: support specialists can offer up to $500, team leads up to $5k, finance approval above that.

- **Support**: tier-1 attempts resolution, escalates when over their authority.
- **Legal**: pulled in if customer threatens chargeback or legal action.
- **Finance**: processes the approved refund and reconciles vendor payouts.

## Brand voice

Serenia's brand voice is **reassuring, capable, and human** — never glib, never corporate. The events context makes this important: customers are usually anxious, sometimes grieving, sometimes celebrating a once-in-a-lifetime moment. The wrong tone is more damaging than a slow response.

Voice traits:

- **Concrete over abstract.** "Your florist confirmed Tuesday at 9am" beats "Vendor coordination is on track."
- **Owns problems, doesn't hide behind policy.** "I see this got dropped — let me fix it" beats "Per our policy, your request was outside the SLA window."
- **Warm but bounded.** Empathy is real; promises are scoped. Never commit to something the team can't deliver.
- **No exclamation points.** No emoji (one carefully placed 🙂 is the absolute limit, and never in policy-sensitive responses).
- **First person plural for the team, first person singular when the responder owns the action.** "We've got you covered" + "I'll send the updated vendor list by 3pm."

What the brand voice rules out for any AI-generated response:

- No "Great question!" / "Happy to help!" filler.
- No marketing language ("magical day", "unforgettable moment") in operational responses.
- No "synergy", "leverage", or any corporate softener that signals the responder isn't really listening.
- No apology padding ("So sorry for any inconvenience this may have caused!") — apologize once, specifically, then move to action.

Any agent (the runtime support orchestrator, or any future generated agent) that produces customer-facing text must conform to this voice. Tests for the runtime orchestrator include voice checks.

## Plan tiers (referenced by personas)

| Tier         | Price band         | Event lead?     | Refund authority shortcuts |
|--------------|--------------------|-----------------|----------------------------|
| Essentials   | $4k – $15k         | Pooled (shared) | Tier-1 up to $250          |
| Signature    | $15k – $60k        | Dedicated       | Tier-1 up to $500          |
| Enterprise   | $60k+              | Dedicated + ops | Tier-1 up to $1,000        |

These are referenced by the synthetic ticket data and the support agent's policy-citing behavior.
