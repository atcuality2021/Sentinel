---
name: competitor-counterplay
mode: competitor
description: Default framework for turning a competitor battlecard into counter-positioning moves.
---
## Framework
Attack where the competitor is weak and the buyer cares. For each recommended move, pair one of the
competitor's weaknesses (or a pricing/positioning signal) with a concrete counter the seller can run.
Prioritize moves that are defensible from the cited findings over generic positioning.

## Output template
- assessment: where this competitor stands and the single best angle to win against them, <= 2
  sentences.
- action_plan: 3-5 counter-moves, each {action, priority, timeline, rationale}; every rationale must
  cite a specific weakness, pricing signal, or development from the battlecard.
- objection_handling: leave empty (handled in client mode).

## House rules
- No fabricated specifics (names, dates, numbers, prices) that are not present in the battlecard.
- If a category had no reliable source (a recorded gap), do not invent a counter for it — say the
  intel is missing.
