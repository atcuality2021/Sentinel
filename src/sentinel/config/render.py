"""Prompt rendering + validation.

We do NOT substitute ADK state variables here — ADK injects `{state_key}` at run time. Our job
is to *validate* a (possibly admin-edited) template: every declared required variable is present,
and the template references no unknown `{var}` outside the reserved ADK/builder set. This catches
a broken prompt edit at build time instead of at run time (spec FR-4, AC-6).
"""

from __future__ import annotations

import re

from sentinel.config.schema import PromptTemplate

# ADK state keys the pipeline injects + builder-substituted vars. Edited prompts may use these.
# battlecard / account_brief (SENTINEL-009): the synthesizer writes these to state; the strategist
# reads them as its input.
RESERVED_VARS = frozenset(
    {"target", "vertical_context", "research_plan", "public_findings", "private_findings",
     "private_note", "battlecard", "account_brief",
     # extractions (SENTINEL-008): the extractor writes this; the two-tier synthesizer reads it.
     "extractions"}
)

_TOKEN = re.compile(r"{([a-zA-Z_][a-zA-Z0-9_]*)}")


def render_prompt(tmpl: PromptTemplate) -> str:
    """Validate a prompt template and return its text unchanged (ADK does state injection)."""
    found = set(_TOKEN.findall(tmpl.template))
    declared = set(tmpl.variables)

    missing = declared - found
    if missing:
        raise ValueError(
            f"Prompt is missing required variable(s) {sorted(missing)} — "
            f"each must appear as {{var}} in the template."
        )

    unknown = found - declared - RESERVED_VARS
    if unknown:
        raise ValueError(
            f"Prompt references unknown variable(s) {sorted(unknown)}. "
            f"Declare them in 'variables' or use a reserved var {sorted(RESERVED_VARS)}."
        )
    return tmpl.template
