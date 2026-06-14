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
        f"<span style='font-size:11px;font-weight:700;text-transform:uppercase;"
        f"letter-spacing:.07em;padding:2px 8px;border-radius:999px;"
        f"color:{colour};background:{bg};margin-left:10px'>{escape(role)}</span>"
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
        "<button class='btn ghost' type='submit' style='font-size:12px;padding:7px 12px'>Reset to default</button>"
        "</form>"
    ) if not is_custom else (
        f"<form method='post' action='/settings/prompts/{escape(key)}/delete' style='display:inline' "
        f"onsubmit=\"return confirm('Delete custom prompt {escape(key)}? This cannot be undone.')\">"
        "<button class='btn ghost' type='submit' style='font-size:12px;padding:7px 12px;"
        "color:#f28b82;border-color:#5a1f1f'>Delete</button>"
        "</form>"
    )

    custom_badge = (
        "<span style='font-size:10px;color:#fdd663;background:rgba(251,188,4,.15);"
        "border-radius:999px;padding:1px 7px;margin-left:8px;font-weight:700'>custom</span>"
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
        f"<textarea name='template' rows='8' style='font-size:12px'>{escape(p.template)}</textarea>"
        f"{vars_html}"
        "<div class='set-actions'>"
        "<button class='btn' type='submit' style='font-size:12px;padding:7px 14px'>Save</button>"
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
            f"<h2 class='sec' style='margin-top:28px' id='group-{escape(group)}'>"
            f"{escape(group.replace('_',' ').title())} "
            f"<span style='color:var(--muted);font-weight:400;font-size:11px'>{len(keys)} prompts</span>"
            f"</h2>{cards}"
        )

    # Create new prompt form
    create_form = (
        "<div class='card' style='margin-bottom:24px'>"
        "<h2 class='sec' style='margin-top:0'>New custom prompt</h2>"
        "<form method='post' action='/settings/prompts/create' class='set-grid'>"
        "<div class='row2'>"
        "<div><label class='lbl' for='new-key'>Key <span class='note'>(e.g. finance.custom_scorer)</span></label>"
        "<input id='new-key' name='key' placeholder='skill.step_name' required></div>"
        "<div><label class='lbl' for='new-vars'>Variables <span class='note'>(comma-separated, no braces)</span></label>"
        "<input id='new-vars' name='variables' placeholder='target, research_plan'></div>"
        "</div>"
        "<div><label class='lbl' for='new-tmpl'>Template</label>"
        "<textarea id='new-tmpl' name='template' rows='5' "
        "placeholder='You are a researcher. The topic is {target}...' required></textarea></div>"
        "<div class='set-actions'>"
        "<button class='btn' type='submit'>Create prompt</button>"
        "<span class='note' style='align-self:center;margin-left:8px'>Custom prompts can be deleted; shipped prompts can only be reset.</span>"
        "</div></form></div>"
    )

    # Search + jump bar
    group_links = " ".join(
        f"<a href='#group-{escape(g)}' style='color:var(--accent-2);font-size:12px;"
        f"padding:4px 10px;border:1px solid var(--line);border-radius:999px;"
        f"background:var(--panel-2)'>{escape(g)}</a>"
        for g, _ in ordered
    )
    controls = (
        "<div style='display:flex;align-items:center;gap:12px;margin-bottom:20px;flex-wrap:wrap'>"
        "<input id='prompt-search' placeholder='Filter prompts…' oninput='filterPrompts()' "
        "style='width:260px;padding:9px 13px;font-size:13px'>"
        f"<div style='display:flex;gap:7px;flex-wrap:wrap'>{group_links}</div>"
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
        "<div class='card' style='margin-bottom:20px;padding:14px 18px;"
        "display:flex;gap:24px;align-items:center'>"
        f"<span class='pill'><b>{total}</b> total prompts</span>"
        f"<span class='pill'><b>{len(ordered)}</b> skill groups</span>"
        f"<span class='pill'><b>{custom_count}</b> custom</span>"
        "<span style='flex:1'></span>"
        "<a href='/settings' class='btn ghost' style='font-size:12px;padding:7px 12px'>← Settings</a>"
        "</div>"
    )

    content = banner + summary_bar + controls + create_form + "".join(sections)
    return shell(active="prompts", title="Prompts", content=content, backend=backend)
