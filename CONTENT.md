# Content System

*The build-in-public program for Enable AI. This is a system, not a calendar: formats and triggers are fixed; topics come from shipped work. Companion to `VISION.md`.*

**Series name (working):** *Factory Floor* — building an AI enablement platform with a software factory, in public.

## The rule

Content is derived from shipped work, never written speculatively. The factory's exhaust — work orders, gate results, provenance, what broke — is the raw material. If nothing shipped, nothing publishes.

## Format tiers

Triggered by the size of what shipped, not the calendar. Not every work order deserves the full ladder.

### Tier 1 — every shipped work order (~weekly, ≤30 min)
- One LinkedIn text post: what the work order was, what happened, one lesson.
- Links to the public artifacts (work-order issue, PR, gate results). The factory already produced the receipts.

### Tier 2 — every milestone (~monthly)
Run the ladder in order — each step is cut from the one before it:
1. **Live stream** the work (cheapest: no editing, the work is the content).
2. **Short-form clips** (2–3) cut from the recording.
3. **Tutorial** — the durable, searchable artifact. Secretly a guide chapter.
4. **LinkedIn posts** announcing each of the above.

### Tier 3 — season scale (quarterly+)
- **The free guide** (*Building Software Factories with AI Enablement in Mind*) is a **compilation** of milestone tutorials, edited after 6–8 episodes. The finale, not the pilot.
- **CFPs** draw from `talks.md`: a running file of one-paragraph talk abstracts, one added as each milestone closes. By conference season, choose among real narratives.

## Episode kit (checklist per episode)

- [ ] Link to the work order (public issue)
- [ ] Before/after (code, UI, or metric)
- [ ] Gate results screenshot (tests, review agents, judge scores)
- [ ] What broke, and what changed in the harness because of it
- [ ] One lesson, stated plainly
- [ ] LaunchDarkly angle if there is one (never forced)

## Experiment work orders

The standing invitation that keeps this long-term: any new tool or technology — LaunchDarkly or otherwise — enters as an `experiment` work order (integrate, measure against the gates, keep or revert). Every experiment is automatically an episode: "I swapped X into the factory — verdict after two weeks." Opinionated verdicts outperform tutorials; honest reverts build more trust than wins.

## Rolling outlook (only ever 4–6 weeks ahead)

| Episode | Trigger | Tier |
|---|---|---|
| 1. "I built an AI workflow builder. Now I'm rethinking it — and building a software factory to finish it." | Milestone 0 ships (repo public, VISION.md) | 2 |
| 2. "A factory is gates first, robots second." | Milestone 1 (CI + review agents) | 2 |
| 3. "The first work order: an agent fixes my adapter inconsistency, warts included." | Milestone 2 (first agent-executed work order) | 2 |
| — Tier-1 posts between each, per shipped work order | continuous | 1 |

## Boundaries

- Demo everything on Serenia & Co. data — nothing real-customer-shaped, ever.
- No credentials, keys, or internal LaunchDarkly material on stream; `.env` and the credential store stay off-screen.
- Failures are content; blame is not. Critique tools by evidence from the gates.
