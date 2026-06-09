---
name: account-strategy
mode: client
description: Default framework for turning an account brief into prioritized next moves.
---
## Framework
Rank moves by (deal impact × winnability). Lead with the highest-impact step that is currently
unblocked. Prefer moves that act on a **merged insight** (where public and private signal combine)
over moves that restate a single fact. If the private boundary was not connected, plan around the
public signal and flag the missing private context as the reason a move is lower-confidence.

## Output template
- assessment: current standing of the relationship + the single best angle, in <= 2 sentences.
- action_plan: 3-5 actions, each {action, priority, timeline, rationale}; every rationale must cite a
  specific finding or merged insight from the brief.
- objection_handling: the 2-3 most likely buyer objections, each with an evidence-based reframe drawn
  from the brief.

## House rules
- Never restate a raw PRIVATE fact in the assessment or action text unless it already appears in the
  brief as a merged insight.
- No fabricated specifics (names, dates, numbers) that are not present in the brief.
- If the brief records a gap, prefer an action that closes that gap over one that assumes the answer.
