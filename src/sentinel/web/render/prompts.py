"""render.prompts — split from render.py (presentation only)."""

from __future__ import annotations
from html import escape

from .base import shell
from .settings import _ROLE_COLOURS

_PROMPT_GROUPS_ORDER = [
    "competitor", "client", "self_profile", "finance", "software",
    "academic", "nutrition", "travel", "compare", "orchestrator",
    "coordinator", "program", "eval", "persona",
]


def _prompt_role_badge(key: str, cfg) -> str:
    ac = cfg.agents.get(key)
    role = ac.role if ac else ""
    if not role:
        return ""
    colour, bg = _ROLE_COLOURS.get(role, ("#9aa0a6", "rgba(150,160,170,.15)"))
    return (
        f"<span class='badge' style='margin-left:10px;"
        f"color:{colour};background:{bg}'>{escape(role)}</span>"
    )


def _prompt_crud_card(key: str, p, cfg) -> str:
    is_custom = p.default_template is None
    vars_html = (
        "<p class='varsHint'>vars: "
        + escape(", ".join("{" + v + "}" for v in p.variables))
        + "</p>"
    ) if p.variables else "<p class='varsHint'>no required vars</p>"

    reset_btn = (
        f"<form method='post' action='/settings/prompts/{escape(key)}/reset' style='display:inline'>"
        "<button class='btn ghost sm' type='submit'>Reset to default</button>"
        "</form>"
    ) if not is_custom else (
        f"<form method='post' action='/settings/prompts/{escape(key)}/delete' style='display:inline' "
        f"onsubmit=\"return confirm('Delete custom prompt {escape(key)}? This cannot be undone.')\">"
        "<button class='btn danger sm' type='submit'>Delete</button>"
        "</form>"
    )

    custom_badge = (
        "<span class='badge warn' style='margin-left:8px'>custom</span>"
        if is_custom else ""
    )

    return (
        f"<details class='card prompt-card' data-key='{escape(key)}' "
        "style='margin-bottom:10px;padding:0'>"
        f"<summary style='padding:14px 18px;cursor:pointer;display:flex;align-items:center;"
        "gap:4px;border-radius:14px;list-style:none'>"
        f"<span class='agent-key'>{escape(key)}</span>"
        f"{_prompt_role_badge(key, cfg)}{custom_badge}"
        "</summary>"
        "<div style='padding:0 18px 18px'>"
        f"<form method='post' action='/settings/prompts/{escape(key)}' class='set-grid'>"
        f"<div class='field'><textarea class='mono' name='template' rows='8'>{escape(p.template)}</textarea></div>"
        f"{vars_html}"
        "<div class='set-actions'>"
        "<button class='btn sm' type='submit'>Save</button>"
        f"{reset_btn}"
        "</div>"
        "</form></div></details>"
    )


def prompts_page(cfg, *, backend: str, ok: str = "", err: str = "") -> str:
    """Full CRUD page for all agent prompt templates, grouped by skill domain."""
    banner = ""
    if ok:
        banner = f"<div class='card banner ok' style='margin-bottom:16px'>{escape(ok)}</div>"
    elif err:
        banner = f"<div class='card banner bad' style='margin-bottom:16px'>{escape(err)}</div>"

    # Group prompt keys by prefix
    groups: dict[str, list[str]] = {}
    for k in sorted(cfg.prompts):
        prefix = k.split(".")[0]
        groups.setdefault(prefix, []).append(k)

    ordered = [(g, groups[g]) for g in _PROMPT_GROUPS_ORDER if g in groups]
    ordered += [(g, groups[g]) for g in sorted(groups) if g not in _PROMPT_GROUPS_ORDER]

    # Build group sections
    sections = []
    for group, keys in ordered:
        cards = "".join(_prompt_crud_card(k, cfg.prompts[k], cfg) for k in keys)
        sections.append(
            f"<div class='page-head' style='margin-top:28px' id='group-{escape(group)}'>"
            f"<div class='grow'><h2>{escape(group.replace('_',' ').title())} "
            f"<span class='muted' style='font-weight:400;font-size:11px'>{len(keys)} prompts</span>"
            f"</h2></div></div>{cards}"
        )

    # Create new prompt form
    create_form = (
        "<div class='card' style='margin-bottom:24px' id='new-prompt'>"
        "<div class='card-head'><h2>New custom prompt</h2></div>"
        "<form method='post' action='/settings/prompts/create' class='set-grid'>"
        "<div class='grid cols-2'>"
        "<div class='field'><label for='new-key'>Key <span class='hint'>(e.g. finance.custom_scorer)</span></label>"
        "<input class='input mono' id='new-key' name='key' placeholder='skill.step_name' required></div>"
        "<div class='field'><label for='new-vars'>Variables <span class='hint'>(comma-separated, no braces)</span></label>"
        "<input class='input mono' id='new-vars' name='variables' placeholder='target, research_plan'></div>"
        "</div>"
        "<div class='field'><label for='new-tmpl'>Template</label>"
        "<textarea class='mono' id='new-tmpl' name='template' rows='5' "
        "placeholder='You are a researcher. The topic is {target}...' required></textarea></div>"
        "<div class='set-actions'>"
        "<button class='btn' type='submit'>Create prompt</button>"
        "<span class='note' style='align-self:center;margin-left:8px'>Custom prompts can be deleted; shipped prompts can only be reset.</span>"
        "</div></form></div>"
    )

    # Search + jump bar
    group_links = " ".join(
        f"<a class='pill' href='#group-{escape(g)}'>{escape(g)}</a>"
        for g, _ in ordered
    )
    controls = (
        "<div class='inline' style='gap:12px;margin-bottom:20px'>"
        "<input class='input' id='prompt-search' placeholder='Filter prompts…' oninput='filterPrompts()' "
        "style='width:260px'>"
        f"<div class='inline' style='gap:7px'>{group_links}</div>"
        "</div>"
        "<script>"
        "function filterPrompts(){"
        "  const q=document.getElementById('prompt-search').value.toLowerCase();"
        "  document.querySelectorAll('.prompt-card').forEach(c=>{"
        "    c.style.display=c.dataset.key.toLowerCase().includes(q)?'':'none'"
        "  });"
        "  document.querySelectorAll('h2.sec[id^=group-]').forEach(h=>{"
        "    const cards=[...document.querySelectorAll('.prompt-card[data-key]')]"
        "      .filter(c=>c.previousElementSibling===h||"
        "        [...h.parentElement.children].indexOf(c)>"
        "        [...h.parentElement.children].indexOf(h));"
        "    h.style.display=cards.some(c=>c.style.display!=='none')?'':'none';"
        "  });"
        "}"
        "</script>"
    )

    total = len(cfg.prompts)
    custom_count = sum(1 for p in cfg.prompts.values() if p.default_template is None)

    summary_bar = (
        "<div class='card pad-sm' style='margin-bottom:20px'>"
        "<div class='row-between'>"
        "<div class='inline' style='gap:24px'>"
        f"<span class='pill'><b>{total}</b> total prompts</span>"
        f"<span class='pill'><b>{len(ordered)}</b> skill groups</span>"
        f"<span class='pill'><b>{custom_count}</b> custom</span>"
        "</div>"
        "<a href='/settings' class='btn ghost sm'>← Settings</a>"
        "</div></div>"
    )

    page_head = (
        "<div class='page-head'><div class='grow'><h1>Prompts</h1>"
        f"<p>System prompt library — {total} prompts across {len(ordered)} groups.</p></div>"
        "<a class='btn' href='#new-prompt'>＋ New prompt</a></div>"
    )

    content = page_head + banner + summary_bar + controls + create_form + "".join(sections)
    return shell(active="prompts", title="Prompts", content=content, backend=backend)
