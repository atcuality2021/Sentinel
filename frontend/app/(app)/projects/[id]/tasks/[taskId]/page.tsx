"use client"

import { use, useState } from "react"
import useSWR from "swr"
import Link from "next/link"
import { TextureCard } from "@/components/ui/texture-card"
import { TerminalAnimation } from "@/components/ui/terminal-animation"
import { AnimatedNumber } from "@/components/ui/animated-number"
import { DirectionAwareTabs } from "@/components/ui/direction-aware-tabs"
import {
  type Task, type TaskStatus, type Project, type ArtifactData, type PlanData, type PlanStep,
  tasks as tasksApi,
} from "@/lib/api"
import {
  Globe, Lock, AlertTriangle, ThumbsUp, ThumbsDown,
  Play, Download, Loader2, CheckCircle2, XCircle, Clock,
  ChevronDown, ChevronUp, Send, Sparkles, FileText, Lightbulb,
} from "lucide-react"
import { fetcher } from "@/lib/fetcher"

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtLabel(key: string) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}

// Convert an agent_spec_id like "created-market-program_strategy" or "seed-competitor-market"
// to a readable label: strip the prefix/domain wrappers, then title-case.
function friendlySpecId(specId: string): string {
  if (!specId || specId === "—") return specId
  // "created-{domain}-{capability}" → capability
  const createdMatch = specId.match(/^created-[^-]+-(.+)$/)
  if (createdMatch) return fmtLabel(createdMatch[1])
  // "seed-{capability}-{domain}" → capability
  const seedMatch = specId.match(/^seed-(.+)-[^-]+$/)
  if (seedMatch) return fmtLabel(seedMatch[1])
  return fmtLabel(specId)
}

// Extract a human-readable label from a step id+capability pair.
// Step IDs encode the target: comp_zoom → "Zoom", research_dept_flood_management → "Flood Management".
// Falls back to prettifying capability when no target prefix is found.
function stepLabel(step: { id: string; capability: string }): string {
  const prefixes = ["comp_", "competitor_", "compare_", "profile_", "research_dept_"]
  for (const p of prefixes) {
    if (step.id.startsWith(p)) {
      const remainder = step.id.slice(p.length).replace(/_/g, " ")
      if (remainder) return remainder.replace(/\b\w/g, (c) => c.toUpperCase())
    }
  }
  return step.capability.replace(/_/g, " ")
}

// Case-insensitive prefix strip so "research_dept_..." and "RESEARCH_DEPT_..." both work
function cleanArtType(type: string): string {
  return (
    type
      .replace(/^(research_dept_|govt_dept_|dept_|research_|govt_)/i, "")
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase())
      .trim() || "Report"
  )
}

// Pull the real entity name from artifact content (dept, entity, etc.)
// rather than using art.target which is usually the task objective
function getArtTitle(art: ArtifactData): string {
  const c = art.content
  for (const f of ["department", "dept", "department_name", "entity_name", "entity", "name", "title"]) {
    const v = c[f]
    if (typeof v === "string" && v.length > 2 && v.length < 120) return v
  }
  const cleaned = cleanArtType(art.type)
  if (cleaned !== "Report") return cleaned
  return art.target.length > 80 ? art.target.slice(0, 78) + "…" : art.target
}

function extractSummary(art: ArtifactData): { brief?: string; insights: string[] } {
  const c = art.content
  const brief =
    (typeof c.executive_summary === "string" && (c.executive_summary as string).length > 20
      ? (c.executive_summary as string) : null) ??
    (typeof c.summary === "string" && (c.summary as string).length > 20
      ? (c.summary as string) : null) ??
    (typeof c.overview === "string" && (c.overview as string).length > 20
      ? (c.overview as string) : null) ??
    (typeof c.assessment === "string" && (c.assessment as string).length > 20
      ? (c.assessment as string) : null) ??
    (typeof c.positioning === "string" && (c.positioning as string).length > 20
      ? (c.positioning as string) : null) ??
    (typeof c.one_line_summary === "string" && (c.one_line_summary as string).length > 10
      ? (c.one_line_summary as string) : null) ??
    undefined

  const insights: string[] = []
  for (const field of [
    "key_findings", "key_insights", "highlights", "insights", "recommendations",
    "strengths", "how_to_win", "action_plan", "weaknesses",
  ]) {
    const arr = c[field]
    if (!Array.isArray(arr)) continue
    for (const item of arr as unknown[]) {
      if (typeof item === "string" && item.length > 15) insights.push(item)
      else if (typeof item === "object" && item !== null) {
        const o = item as Record<string, unknown>
        const t = o.summary ?? o.text ?? o.finding ?? o.insight ?? o.title ?? o.content
        if (typeof t === "string" && t.length > 15) insights.push(t)
      }
      if (insights.length >= 6) break
    }
    if (insights.length >= 6) break
  }
  return { brief, insights }
}

// ── Markdown renderer ─────────────────────────────────────────────────────────

function InlineMd({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/)
  return (
    <>
      {parts.map((p, i) => {
        if (p.startsWith("**") && p.endsWith("**"))
          return <strong key={i} className="font-semibold">{p.slice(2, -2)}</strong>
        if (p.startsWith("*") && p.endsWith("*"))
          return <em key={i}>{p.slice(1, -1)}</em>
        if (p.startsWith("`") && p.endsWith("`"))
          return <code key={i} className="text-[11px] bg-neutral-700 px-1 rounded font-mono">{p.slice(1, -1)}</code>
        return <span key={i}>{p}</span>
      })}
    </>
  )
}

function MdMessage({ text }: { text: string }) {
  return (
    <div className="flex flex-col gap-2">
      {text.split(/\n\n+/).map((block, i) => {
        const lines = block.split("\n").filter(Boolean)
        if (!lines.length) return null
        const first = lines[0].trim()
        if (/^\d+\./.test(first))
          return (
            <ol key={i} className="list-decimal pl-5 space-y-0.5">
              {lines.map((l, j) => (
                <li key={j} className="text-sm leading-relaxed">
                  <InlineMd text={l.replace(/^\d+\.\s*/, "")} />
                </li>
              ))}
            </ol>
          )
        if (/^[-*•]/.test(first))
          return (
            <ul key={i} className="list-disc pl-5 space-y-0.5">
              {lines.map((l, j) => (
                <li key={j} className="text-sm leading-relaxed">
                  <InlineMd text={l.replace(/^[-*•]\s*/, "")} />
                </li>
              ))}
            </ul>
          )
        return (
          <p key={i} className="text-sm leading-relaxed">
            <InlineMd text={block} />
          </p>
        )
      })}
    </div>
  )
}

// ── Content renderers ─────────────────────────────────────────────────────────

const VERDICT_STYLE: Record<string, string> = {
  win:    "bg-green-900/40 text-green-300 border border-green-700/40",
  loss:   "bg-red-900/40 text-red-300 border border-red-700/40",
  parity: "bg-[var(--muted)] dark:bg-neutral-800 text-[var(--foreground)] dark:text-neutral-300 border border-[var(--border)] dark:border-neutral-700",
}

/** Detect the semantic type of a structured object from its keys. */
function detectShape(o: Record<string, unknown>): string {
  if ("axis" in o && "ours" in o && "theirs" in o) return "axis"
  if ("what_was_missing" in o) return "gap"
  if ("summary" in o && "evidence" in o) return "finding"
  if ("boundary" in o && "label" in o) return "citation"
  if ("name" in o && ("category" in o || "positioning" in o)) return "product"
  if ("step" in o || "action" in o) return "action"
  return "generic"
}

function AxisRow({ o }: { o: Record<string, unknown> }) {
  const verdict = (typeof o.verdict === "string" ? o.verdict : "").toLowerCase()
  const cls = VERDICT_STYLE[verdict] ?? VERDICT_STYLE.parity
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--muted)]/40 p-3 flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-bold text-[var(--foreground)]">{String(o.axis ?? "")}</span>
        {verdict && (
          <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wide ${cls}`}>
            {verdict}
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <p className="text-[10px] font-semibold text-green-400 uppercase tracking-wide mb-0.5">Us</p>
          <p className="text-[var(--foreground)] leading-relaxed">{String(o.ours ?? "")}</p>
        </div>
        <div>
          <p className="text-[10px] font-semibold text-neutral-400 uppercase tracking-wide mb-0.5">Them</p>
          <p className="text-[var(--muted-foreground)] leading-relaxed">{String(o.theirs ?? "")}</p>
        </div>
      </div>
      {Boolean(o.note) && <p className="text-[11px] text-[var(--muted-foreground)] italic">{String(o.note)}</p>}
    </div>
  )
}

function GapRow({ o }: { o: Record<string, unknown> }) {
  return (
    <div className="rounded-lg border border-red-800/30 bg-red-900/10 p-3 flex flex-col gap-1">
      <p className="text-sm text-red-300">{String(o.what_was_missing ?? o.gap ?? "")}</p>
      {Boolean(o.impact) && <p className="text-xs text-[var(--muted-foreground)]">Impact: {String(o.impact)}</p>}
    </div>
  )
}

function FindingRow({ o }: { o: Record<string, unknown> }) {
  return (
    <div className="flex items-start gap-2">
      <span className="text-violet-400 shrink-0 text-xs mt-0.5">◆</span>
      <div className="min-w-0">
        <p className="text-sm leading-relaxed">{String(o.summary ?? o.finding ?? "")}</p>
        {Boolean(o.evidence) && <p className="text-xs text-[var(--muted-foreground)] mt-0.5">{String(o.evidence)}</p>}
      </div>
    </div>
  )
}

function CitationRow({ o }: { o: Record<string, unknown> }) {
  const label = String(o.label ?? o.name ?? "Source")
  const url = typeof o.url === "string" ? o.url : undefined
  const isPublic = o.boundary !== "private"
  return (
    <div className="flex items-center gap-2">
      <span className={`shrink-0 ${isPublic ? "text-blue-400" : "text-amber-400"}`}>
        {isPublic ? <Globe className="w-3 h-3" /> : <Lock className="w-3 h-3" />}
      </span>
      {url ? (
        <a href={url} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline text-sm truncate">{label}</a>
      ) : (
        <span className="text-sm text-[var(--muted-foreground)]">{label}</span>
      )}
    </div>
  )
}

function ArtifactItem({ item }: { item: unknown }) {
  if (typeof item === "string") {
    const trimmed = item.trim()
    if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
      try { return <ArtifactItem item={JSON.parse(trimmed)} /> } catch {}
    }
    return <span className="text-sm leading-relaxed">{item}</span>
  }
  if (typeof item !== "object" || item === null) return <span className="text-sm">{String(item)}</span>
  const o = item as Record<string, unknown>
  const shape = detectShape(o)
  if (shape === "axis")     return <AxisRow o={o} />
  if (shape === "gap")      return <GapRow o={o} />
  if (shape === "finding")  return <FindingRow o={o} />
  if (shape === "citation") return <CitationRow o={o} />
  // Generic: prefer human-readable label fields
  const url = typeof o.url === "string" ? o.url : undefined
  const label = String(o.text ?? o.summary ?? o.name ?? o.title ?? o.action ?? o.content ?? "")
  if (label && label !== "[object Object]") {
    if (url) return <a href={url} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline text-sm break-all">{label}</a>
    return <span className="text-sm leading-relaxed">{label}</span>
  }
  return (
    <pre className="text-[11px] text-[var(--muted-foreground)] whitespace-pre-wrap bg-[var(--muted)] rounded-lg p-2 overflow-auto">
      {JSON.stringify(o, null, 2)}
    </pre>
  )
}

function CollapsibleList({ items, sectionKey }: { items: unknown[]; sectionKey?: string }) {
  const [expanded, setExpanded] = useState(false)
  // Axes need more space — show fewer collapsed
  const LIMIT = sectionKey === "axes" ? 3 : 4
  const visible = expanded ? items : items.slice(0, LIMIT)
  const overflow = items.length - LIMIT
  // Axes get card layout; others get bullet list
  const isCards = items.length > 0 && typeof items[0] === "object" && items[0] !== null &&
    ["axis", "gap", "product"].includes(detectShape(items[0] as Record<string, unknown>))
  return (
    <>
      <div className={isCards ? "flex flex-col gap-2" : "flex flex-col gap-1.5"}>
        {visible.map((item, j) => (
          isCards ? (
            <ArtifactItem key={j} item={item} />
          ) : (
            <div key={j} className="flex items-start gap-2">
              {typeof item !== "object" || detectShape(item as Record<string, unknown>) === "finding"
                ? null
                : <span className="text-[var(--muted-foreground)] mt-1 shrink-0 text-xs">·</span>}
              <ArtifactItem item={item} />
            </div>
          )
        ))}
      </div>
      {overflow > 0 && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="mt-2 text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)] flex items-center gap-1 transition-colors">
          {expanded
            ? <><ChevronUp className="w-3 h-3" /> Show less</>
            : <><ChevronDown className="w-3 h-3" /> Show {overflow} more</>}
        </button>
      )}
    </>
  )
}

function LongText({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false)
  const isLong = text.length > 280
  return (
    <div>
      <p className={`text-sm leading-relaxed ${isLong && !expanded ? "line-clamp-4" : ""}`}>{text}</p>
      {isLong && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="mt-1 text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)] flex items-center gap-1 transition-colors">
          {expanded
            ? <><ChevronUp className="w-3 h-3" /> Show less</>
            : <><ChevronDown className="w-3 h-3" /> Show more</>}
        </button>
      )}
    </div>
  )
}

// ── Accordion card for Reports tab ────────────────────────────────────────────

function ArtifactAccordion({ art, defaultOpen }: { art: ArtifactData; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen ?? false)
  const title = getArtTitle(art)
  const typeLabel = cleanArtType(art.type)

  const contentEntries = Object.entries(art.content).filter(([k, v]) => {
    if (k.startsWith("_")) return false
    if (v === null || v === undefined || v === "") return false
    if (Array.isArray(v) && v.length === 0) return false
    return true
  })

  return (
    <div className={`rounded-2xl border transition-colors ${
      open ? "border-violet-500/30 bg-[var(--card)]" : "border-[var(--border)] bg-[var(--card)]"
    }`}>
      {/* Header — always visible */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-4 px-5 py-4 text-left
                   hover:bg-[var(--muted)] rounded-2xl transition-colors">
        <div className="min-w-0 flex-1">
          <span className="text-[10px] font-bold uppercase tracking-widest text-[var(--muted-foreground)]">
            {typeLabel}
          </span>
          <p className="text-sm font-semibold mt-0.5 truncate">{title}</p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {art.public_count > 0 && (
            <span className="flex items-center gap-1 text-xs text-blue-400">
              <Globe className="w-3 h-3" /> {art.public_count}
            </span>
          )}
          {art.private_count > 0 && (
            <span className="flex items-center gap-1 text-xs text-amber-400">
              <Lock className="w-3 h-3" /> {art.private_count}
            </span>
          )}
          {art.gaps > 0 && (
            <span className="flex items-center gap-1 text-xs text-red-400">
              <AlertTriangle className="w-3 h-3" /> {art.gaps}
            </span>
          )}
          <span className="text-[11px] text-[var(--muted-foreground)]">
            {contentEntries.length} section{contentEntries.length !== 1 ? "s" : ""}
          </span>
          {open
            ? <ChevronUp className="w-4 h-4 text-[var(--muted-foreground)]" />
            : <ChevronDown className="w-4 h-4 text-[var(--muted-foreground)]" />}
        </div>
      </button>

      {/* Expanded content */}
      {open && (
        <>
          <div className="h-px bg-[var(--border)] mx-5" />
          <div className="p-5 flex flex-col gap-5">
            {contentEntries.map(([key, val]) => {
              // Skip internal/redundant fields that are already visible elsewhere
              if (["org", "target", "subject", "vertical_context"].includes(key) &&
                  typeof val === "string" && val.length < 120) return null
              return (
                <div key={key}>
                  <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--muted-foreground)] mb-2">
                    {fmtLabel(key)}
                  </p>
                  {Array.isArray(val) ? (
                    <CollapsibleList items={val as unknown[]} sectionKey={key} />
                  ) : typeof val === "object" && val !== null ? (
                    // Try to render objects as readable citations/items
                    (() => {
                      const o = val as Record<string, unknown>
                      const shape = detectShape(o)
                      if (shape !== "generic") return <ArtifactItem item={val} />
                      return (
                        <pre className="text-xs text-[var(--muted-foreground)] whitespace-pre-wrap bg-[var(--muted)] rounded-xl p-3 overflow-auto border border-[var(--border)]">
                          {JSON.stringify(val, null, 2)}
                        </pre>
                      )
                    })()
                  ) : typeof val === "string" && val.length > 280 ? (
                    <LongText text={val} />
                  ) : (
                    <p className="text-sm leading-relaxed">{String(val)}</p>
                  )}
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

// ── LiveRunPanel ──────────────────────────────────────────────────────────────

function LiveRunPanel({
  projectId, taskId, onRerun,
}: {
  projectId: string
  taskId: string
  onRerun?: () => void
}) {
  const startRef = useState(() => Date.now())[0]
  const { data: status } = useSWR<TaskStatus>(
    `/projects/${projectId}/tasks/${taskId}/status.json`,
    fetcher,
    { refreshInterval: (d) => (d?.state === "done" || d?.state === "failed" ? 0 : 2000) }
  )
  // Plan data: shown as a pending-steps preview before live steps arrive
  const { data: plan } = useSWR<PlanData>(
    `/api/projects/${projectId}/tasks/${taskId}/plan`,
    fetcher,
  )

  const steps = status?.steps ?? []
  const planSteps = plan?.steps ?? []
  const runningStep = steps.find((s) => s.status === "running")
  const lastDoneStep = [...steps].filter((s) => s.status === "done").pop()
  const doneCount = steps.filter((s) => s.status === "done").length
  // All live steps returned as "pending" = pipeline started but no step has actually begun work yet
  const allPending = steps.length > 0 && steps.every((s) => s.status === "pending")
  const logLines = (status?.log ?? []).map((l) => ({
    command: `[${l.agent}] ${l.message}`,
    output: l.type === "error" ? "ERROR" : undefined,
  }))
  const elapsed = Date.now() - startRef
  const timedOut = elapsed > 20000 && steps.length === 0
  const hasFailed = status?.state === "failed" || timedOut
  // Warming-up = plan loaded but nothing running yet (covers both the pre-step phase where the
  // status endpoint returns [] and the phase where it returns all-pending steps)
  const isWarmingUp = !runningStep && !hasFailed && (
    (steps.length === 0 && planSteps.length > 0) || allPending
  )

  // Show live steps when available; fall back to plan steps as dim pending preview
  const displaySteps: Array<{ id: string; capability: string; status: string; agent?: string; model?: string; pending?: boolean }> =
    steps.length > 0
      ? steps
      : planSteps.map((ps) => ({
          id: ps.id,
          capability: ps.capability,
          status: "pending",
          agent: ps.agent_spec_id,
          pending: true,
        }))

  return (
    <div className="flex flex-col gap-6">

      {/* ── Fallback banner ── vLLM was down; running on Gemini/Claude instead */}
      {status?.fallback_active && (
        <div className="rounded-2xl border border-yellow-500/40 bg-yellow-950/20 p-4">
          <div className="flex items-start gap-3">
            <span className="text-yellow-400 text-lg shrink-0">⚡</span>
            <div>
              <p className="text-sm font-semibold text-yellow-300">
                Switched to cloud fallback
              </p>
              <p className="text-xs text-yellow-400/70 mt-0.5">
                {status.fallback_reason ?? "vLLM was unreachable — pipeline is running on the cloud backend."}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ── Warming-up banner ── plan loaded but no step is running yet */}
      {isWarmingUp && (
        <div className="rounded-2xl border border-violet-500/30 bg-violet-950/20 p-5">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-violet-500" />
            </span>
            <span className="text-[10px] font-bold text-violet-400 uppercase tracking-wider animate-pulse">
              {allPending ? `Pipeline starting · ${steps.length} steps queued` : `Warming up · ${planSteps.length} steps queued`}
            </span>
          </div>
          <p className="text-sm text-violet-300/70 mt-2">
            {allPending
              ? "Steps are loaded — agents will begin executing shortly."
              : "Agents are initialising — the first step will begin shortly."}
          </p>
        </div>
      )}

      {/* ── Active-agent hero banner ── shown while a step is running */}
      {runningStep && (
        <div className="rounded-2xl border border-amber-500/30 bg-amber-950/20 p-5">
          <div className="flex items-center gap-2 mb-3">
            {/* Pulsing live dot */}
            <span className="relative flex h-2.5 w-2.5 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500" />
            </span>
            <span className="text-[10px] font-bold text-amber-400 uppercase tracking-wider">
              Live · {doneCount}/{steps.length} steps done
            </span>
          </div>
          <p className="text-base font-semibold capitalize text-[var(--foreground)]">
            {stepLabel(runningStep)}
          </p>
          {runningStep.agent && (
            <p className="text-sm font-mono text-amber-300/80 mt-0.5">{runningStep.agent}</p>
          )}
          {/* Model handover: prev model → current model */}
          {(lastDoneStep?.model || runningStep.model) && (
            <div className="flex items-center gap-2 mt-2 flex-wrap">
              {lastDoneStep?.model && lastDoneStep.model !== runningStep.model && (
                <>
                  <span className="px-2 py-0.5 rounded text-xs bg-[var(--muted)] dark:bg-neutral-800 text-[var(--muted-foreground)] dark:text-neutral-400 font-mono">
                    {lastDoneStep.model}
                  </span>
                  <span className="text-[var(--muted-foreground)] text-xs">→</span>
                </>
              )}
              {runningStep.model && (
                <span className="px-2 py-0.5 rounded text-xs bg-amber-900/40 text-amber-300 font-mono font-semibold">
                  {runningStep.model}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Pipeline steps card ── */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
        <div className="flex items-center justify-between mb-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
            Pipeline
          </p>
          {steps.length > 0 && !allPending && (
            <span className="text-xs font-mono text-[var(--muted-foreground)]">
              {doneCount}/{steps.length} STEPS
            </span>
          )}
          {(steps.length === 0 || allPending) && (steps.length > 0 || planSteps.length > 0) && (
            <span className="text-xs font-mono text-violet-400/70 animate-pulse">
              {steps.length || planSteps.length} planned
            </span>
          )}
        </div>

        {displaySteps.length === 0 ? (
          hasFailed ? (
            <div className="flex items-start gap-3 py-2">
              <XCircle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-red-600 dark:text-red-400">
                  {status?.error ?? "Pipeline failed to start"}
                </p>
                <p className="text-xs text-[var(--muted-foreground)] mt-0.5">
                  Server may have restarted mid-run. Re-run to retry.
                </p>
                {onRerun && (
                  <button
                    onClick={onRerun}
                    className="mt-3 flex items-center gap-1.5 px-3 py-1.5 rounded-lg
                               bg-black dark:bg-white text-white dark:text-black
                               text-xs font-semibold hover:opacity-80 transition-opacity">
                    <Play className="w-3 h-3" /> Re-run research
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="flex items-center gap-3 animate-pulse">
                  <div className="w-6 h-6 rounded-full bg-[var(--muted)] shrink-0" />
                  <div className="h-3 rounded bg-[var(--muted)]" style={{ width: `${40 + i * 15}%` }} />
                </div>
              ))}
              <p className="text-xs text-[var(--muted-foreground)] mt-1 animate-pulse">
                Initialising pipeline…
              </p>
            </div>
          )
        ) : (
          <div className="flex flex-col gap-2">
            {displaySteps.map((step) => {
              const isRunning = step.status === "running"
              const isDone = step.status === "done"
              const isStepFailed = step.status === "failed"
              const isPending = step.pending || step.status === "pending"
              return (
                <div
                  key={step.id}
                  className={`rounded-xl px-3 py-2.5 flex items-start gap-3 transition-all duration-300
                    ${isRunning    ? "bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800" :
                      isDone       ? "bg-green-50 dark:bg-green-950/20 border border-green-100 dark:border-green-900" :
                      isStepFailed ? "bg-red-50 dark:bg-red-950/20 border border-red-100 dark:border-red-900" :
                      (steps.length === 0 || allPending) ? "border border-transparent opacity-60 animate-pulse" :
                      "border border-transparent opacity-50"}`}
                >
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-0.5
                    ${isDone       ? "bg-green-100 dark:bg-green-900 text-green-600" :
                      isRunning    ? "bg-amber-100 dark:bg-amber-900 text-amber-600" :
                      isStepFailed ? "bg-red-100 dark:bg-red-900 text-red-600" :
                      "bg-[var(--muted)] text-[var(--muted-foreground)]"}`}>
                    {isDone       ? <CheckCircle2 className="w-3.5 h-3.5" /> :
                     isRunning    ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> :
                     isStepFailed ? <XCircle className="w-3.5 h-3.5" /> :
                     <Clock className="w-3.5 h-3.5" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium capitalize">
                        {stepLabel(step)}
                      </span>
                      {!isPending && (
                        <span className={`text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded
                          ${isDone       ? "bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300" :
                            isRunning    ? "bg-amber-100 dark:bg-amber-900 text-amber-700 dark:text-amber-300 animate-pulse" :
                            isStepFailed ? "bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300" :
                            "bg-[var(--muted)] text-[var(--muted-foreground)]"}`}>
                          {step.status}
                        </span>
                      )}
                    </div>
                    {(step.agent || step.model) && (
                      <p className={`text-[11px] mt-0.5 truncate font-mono
                        ${isPending ? "text-[var(--muted-foreground)]/40" : "text-[var(--muted-foreground)]"}`}>
                        {step.agent && <span>{step.agent}</span>}
                        {step.agent && step.model && <span className="mx-1">·</span>}
                        {step.model && <span>{step.model}</span>}
                      </p>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Live stats */}
      {(status?.findings_so_far !== undefined || status?.sources_checked !== undefined) && (
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4 text-center">
            <AnimatedNumber value={status?.findings_so_far ?? 0} className="text-2xl font-bold text-blue-500" />
            <p className="text-xs text-[var(--muted-foreground)] mt-1">findings so far</p>
          </div>
          <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4 text-center">
            <AnimatedNumber value={status?.sources_checked ?? 0} className="text-2xl font-bold" />
            <p className="text-xs text-[var(--muted-foreground)] mt-1">sources checked</p>
          </div>
        </div>
      )}

      {logLines.length > 0 && (
        <TerminalAnimation scenarios={[{ id: "live", label: "Live Log", steps: logLines }]} autoPlay />
      )}
    </div>
  )
}

// ── PipelinePanel ─────────────────────────────────────────────────────────────

function computeDepths(steps: PlanStep[]): Map<string, number> {
  const byId = new Map(steps.map((s) => [s.id, s]))
  const depth = new Map<string, number>()
  function d(sid: string, seen: Set<string> = new Set()): number {
    if (depth.has(sid)) return depth.get(sid)!
    const step = byId.get(sid)
    const deps = (step?.depends_on ?? []).filter((p) => byId.has(p) && !seen.has(p))
    const val = deps.length > 0
      ? 1 + Math.max(...deps.map((p) => d(p, new Set([...seen, sid]))))
      : 0
    depth.set(sid, val)
    return val
  }
  steps.forEach((s) => d(s.id))
  return depth
}

const _SUBSTEP_ICONS: Record<string, string> = {
  planner: "🗺",
  public_research: "🔍",
  ecom_prices: "🛒",
  research: "🔍",
  synthesizer: "🧠",
  extractor: "🔬",
  dept_research: "🏛",
  synthesis: "🧠",
  competitor: "🔍",
  compare: "⚖",
  self_profile: "🏢",
  client: "👤",
}

function callsBadge(calls: string) {
  const cls =
    calls.includes("web")
      ? "bg-blue-900/40 text-blue-300 border border-blue-700/40"
      : calls.includes("MCP")
      ? "bg-amber-900/40 text-amber-300 border border-amber-700/40"
      : "bg-[var(--muted)] dark:bg-neutral-800 text-[var(--muted-foreground)] dark:text-neutral-400 border border-[var(--border)] dark:border-neutral-700"
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded-full font-mono ${cls}`}>{calls}</span>
  )
}

function PipelinePanel({ projectId, taskId }: { projectId: string; taskId: string }) {
  const { data: plan } = useSWR<PlanData>(
    `/api/projects/${projectId}/tasks/${taskId}/plan`,
    fetcher
  )

  const steps = plan?.steps ?? []

  if (steps.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-[var(--border)] p-10 text-center">
        <p className="text-sm text-[var(--muted-foreground)]">No pipeline data available.</p>
      </div>
    )
  }

  // ── DAG depth for Flow layout ────────────────────────────────────────────
  const depths = computeDepths(steps)
  const maxDepth = Math.max(...Array.from(depths.values()))
  const columns: PlanStep[][] = Array.from({ length: maxDepth + 1 }, () => [])
  steps.forEach((s) => columns[depths.get(s.id) ?? 0].push(s))

  // ── How the agent worked — timeline ─────────────────────────────────────
  const timeline = (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
      <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--muted-foreground)] mb-4">
        How the agent worked
      </p>
      <div className="flex flex-col gap-1">
        {steps.map((step) => {
          const isDone = step.status === "done"
          const dotColor = isDone ? "bg-green-500" : step.status === "failed" ? "bg-red-500" : "bg-neutral-600"
          if (step.sub_steps.length > 0) {
            return (
              <div key={step.id}>
                <div className="flex items-center gap-3 py-2">
                  <div className={`w-2 h-2 rounded-full shrink-0 ${dotColor}`} />
                  <span className="text-sm font-semibold capitalize">{stepLabel(step)}</span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-green-900/30 text-green-400 border border-green-700/30 font-mono">
                    full pipeline
                  </span>
                </div>
                <div className="ml-5 pl-3 border-l border-[var(--border)] flex flex-col gap-1 mb-1">
                  {step.sub_steps.map((ss) => (
                    <div key={ss.key} className="flex items-start gap-2 py-1.5">
                      <span className="text-sm shrink-0">{_SUBSTEP_ICONS[ss.key] ?? "⚙"}</span>
                      <div className="min-w-0">
                        <p className="text-sm font-medium">{ss.key}</p>
                        <p className="text-xs text-[var(--muted-foreground)] leading-relaxed">{ss.label}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )
          }
          const icon = _SUBSTEP_ICONS[step.capability] ?? "⚙"
          return (
            <div key={step.id} className="flex items-start gap-3 py-2">
              <div className={`w-2 h-2 rounded-full shrink-0 mt-1.5 ${dotColor}`} />
              <span className="text-sm shrink-0">{icon}</span>
              <div className="min-w-0">
                <p className="text-sm font-medium capitalize">{stepLabel(step)}</p>
                <p className="text-xs text-[var(--muted-foreground)]">{callsBadge(step.calls)}</p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )

  // ── Flow DAG ────────────────────────────────────────────────────────────
  const flowDag = (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 overflow-x-auto">
      <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--muted-foreground)] mb-4">
        Flow
      </p>
      <div className="flex items-center gap-3 min-w-max">
        {columns.map((col, ci) => (
          <div key={ci} className="flex items-center gap-3">
            <div className="flex flex-col gap-3 justify-center">
              {col.map((step) => (
                <div
                  key={step.id}
                  className={`rounded-xl border p-3 min-w-[140px] max-w-[180px] ${
                    step.is_new
                      ? "border-dashed border-violet-500/50 bg-violet-900/10"
                      : "border-[var(--border)] bg-[var(--muted)]"
                  }`}
                >
                  <p className="text-[10px] font-mono text-[var(--muted-foreground)] truncate">{step.id}</p>
                  <p className="text-sm font-semibold capitalize mt-0.5">{stepLabel(step)}</p>
                  <div className="mt-1.5">{callsBadge(step.calls)}</div>
                  <p className="text-[10px] text-[var(--muted-foreground)] mt-1.5 break-all leading-relaxed" title={step.agent_spec_id}>
                    {friendlySpecId(step.agent_spec_id)}
                  </p>
                </div>
              ))}
            </div>
            {ci < columns.length - 1 && (
              <span className="text-[var(--muted-foreground)] text-xl shrink-0">→</span>
            )}
          </div>
        ))}
      </div>
    </div>
  )

  // ── Step DAG table ───────────────────────────────────────────────────────
  const stepTable = (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] overflow-hidden">
      <div className="px-5 py-4 border-b border-[var(--border)]">
        <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--muted-foreground)]">
          Step DAG — task → assigned agents
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-[10px] uppercase tracking-widest text-[var(--muted-foreground)]">
              <th className="px-4 py-3 text-left font-semibold">Step</th>
              <th className="px-4 py-3 text-left font-semibold">Capability</th>
              <th className="px-4 py-3 text-left font-semibold">Calls</th>
              <th className="px-4 py-3 text-left font-semibold">Depends On</th>
              <th className="px-4 py-3 text-left font-semibold">Assigned Agent</th>
              <th className="px-4 py-3 text-left font-semibold"></th>
            </tr>
          </thead>
          <tbody>
            {steps.map((step, i) => (
              <tr
                key={step.id}
                className={`border-b border-[var(--border)] last:border-0 ${
                  i % 2 === 0 ? "bg-transparent" : "bg-[var(--muted)]/30"
                }`}
              >
                <td className="px-4 py-3 font-mono text-xs text-[var(--muted-foreground)]">{step.id}</td>
                <td className="px-4 py-3 font-semibold capitalize">{stepLabel(step)}</td>
                <td className="px-4 py-3">{callsBadge(step.calls)}</td>
                <td className="px-4 py-3 font-mono text-xs text-[var(--muted-foreground)]">
                  {step.depends_on.length > 0 ? step.depends_on.join(", ") : "—"}
                </td>
                <td className="px-4 py-3 text-xs text-[var(--muted-foreground)] max-w-[260px]" title={step.agent_spec_id}>
                  <span className="block break-all leading-relaxed">{friendlySpecId(step.agent_spec_id)}</span>
                </td>
                <td className="px-4 py-3">
                  {step.is_new ? (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-violet-900/30 text-violet-300 border border-violet-700/40 font-semibold">
                      NEW
                    </span>
                  ) : (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-green-900/30 text-green-300 border border-green-700/40 font-semibold">
                      REUSE
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )

  return (
    <div className="flex flex-col gap-5">
      {timeline}
      {flowDag}
      {stepTable}
    </div>
  )
}

// ── ResultPanel ───────────────────────────────────────────────────────────────

function ResultPanel({ task }: { task: Task }) {
  const [chatMsg, setChatMsg] = useState("")
  const [chatLoading, setChatLoading] = useState(false)
  const [chatHistory, setChatHistory] = useState(task.chat ?? [])
  const [feedback, setFeedback] = useState<1 | -1 | null>(null)

  const result = task.result
  if (!result) return null

  // Scan all artifacts for brief + insights — prefer synthesis/compare types for brief,
  // fall back to whichever artifact has a usable summary field first.
  let brief: string | undefined
  const insights: string[] = []
  const orderedArts = [
    ...result.artifacts.filter((a) => /synthesis|overview|executive|compare/i.test(a.type)),
    ...result.artifacts.filter((a) => !/synthesis|overview|executive|compare/i.test(a.type)),
  ]
  for (const art of orderedArts) {
    const { brief: b, insights: ins } = extractSummary(art)
    if (!brief && b) brief = b
    for (const i of ins) { if (!insights.includes(i) && insights.length < 6) insights.push(i) }
  }

  async function sendChat(e: React.FormEvent) {
    e.preventDefault()
    if (!chatMsg.trim()) return
    const msg = chatMsg
    setChatMsg("")
    setChatHistory((prev) => [...prev, { role: "user" as const, content: msg, timestamp: new Date().toISOString() }])
    setChatLoading(true)
    try {
      const res = (await tasksApi.chat(task.project_id, task.id, msg)) as {
        reply?: string; chat?: typeof task.chat
      }
      if (res?.chat) setChatHistory(res.chat ?? [])
      else if (res?.reply)
        setChatHistory((prev) => [...prev, { role: "assistant" as const, content: res.reply!, timestamp: new Date().toISOString() }])
    } catch {
      setChatHistory((prev) => [...prev, { role: "assistant" as const, content: "Error: could not get reply.", timestamp: new Date().toISOString() }])
    } finally {
      setChatLoading(false)
    }
  }

  async function sendFeedback(signal: 1 | -1) {
    setFeedback(signal)
    await tasksApi.feedback(task.project_id, task.id, signal).catch(() => {})
  }

  const SUGGESTIONS = [
    "What was the most important finding?",
    "Summarise the key risks",
    "What are the recommended next steps?",
    "List the main sources used",
  ]

  // ── Inline chat ─────────────────────────────────────────────────────────────
  const inlineChat = (
    <div className="rounded-2xl border border-[var(--border)] dark:border-neutral-800 bg-[var(--card)] dark:bg-neutral-950 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--border)] dark:border-neutral-800">
        <Sparkles className="w-3.5 h-3.5 text-violet-500 dark:text-violet-400" />
        <span className="text-xs font-semibold text-[var(--foreground)] dark:text-neutral-200">Follow-up Questions</span>
      </div>

      {chatHistory.length > 0 && (
        <div className="px-4 py-4 flex flex-col gap-3 max-h-80 overflow-y-auto">
          {chatHistory.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`px-4 py-2.5 rounded-2xl max-w-[85%] leading-relaxed
                ${m.role === "user"
                  ? "bg-violet-600 text-white text-sm rounded-br-sm"
                  : "bg-[var(--muted)] dark:bg-neutral-800 text-[var(--foreground)] dark:text-neutral-100 rounded-bl-sm border border-[var(--border)] dark:border-neutral-700"}`}>
                {m.role === "user" ? m.content : <MdMessage text={m.content} />}
              </div>
            </div>
          ))}
          {chatLoading && (
            <div className="flex justify-start">
              <div className="bg-[var(--muted)] dark:bg-neutral-800 border border-[var(--border)] dark:border-neutral-700 rounded-2xl rounded-bl-sm px-4 py-3">
                <div className="flex gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-[var(--muted-foreground)] dark:bg-neutral-400 animate-bounce [animation-delay:0ms]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-[var(--muted-foreground)] dark:bg-neutral-400 animate-bounce [animation-delay:150ms]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-[var(--muted-foreground)] dark:bg-neutral-400 animate-bounce [animation-delay:300ms]" />
                </div>
              </div>
            </div>
          )}
          <div ref={(el) => el?.scrollIntoView({ behavior: "smooth" })} />
        </div>
      )}

      {chatHistory.length === 0 && (
        <div className="px-4 py-3 flex flex-wrap gap-1.5">
          {SUGGESTIONS.map((q) => (
            <button
              key={q}
              onClick={() => setChatMsg(q)}
              className="text-[11px] px-3 py-1.5 rounded-full border border-[var(--border)] dark:border-neutral-700
                         text-[var(--muted-foreground)] dark:text-neutral-300 hover:border-violet-500 hover:text-violet-600 dark:hover:text-white
                         transition-colors bg-[var(--muted)] dark:bg-neutral-900">
              {q}
            </button>
          ))}
        </div>
      )}

      <form onSubmit={sendChat} className="flex gap-2 items-center p-3 border-t border-[var(--border)] dark:border-neutral-800">
        <input
          value={chatMsg}
          onChange={(e) => setChatMsg(e.target.value)}
          placeholder="Ask a follow-up question…"
          className="flex-1 rounded-xl border border-[var(--border)] dark:border-neutral-700 bg-[var(--muted)] dark:bg-neutral-900
                     px-4 py-2 text-sm text-[var(--foreground)] dark:text-white placeholder:text-[var(--muted-foreground)] dark:placeholder:text-neutral-500
                     outline-none focus:border-violet-500 transition-colors" />
        <button
          type="submit"
          disabled={chatLoading || !chatMsg.trim()}
          className="w-9 h-9 rounded-xl bg-violet-600 hover:bg-violet-500 disabled:opacity-40
                     flex items-center justify-center transition-colors shrink-0">
          {chatLoading
            ? <Loader2 className="w-4 h-4 text-white animate-spin" />
            : <Send className="w-4 h-4 text-white" />}
        </button>
      </form>
    </div>
  )

  // Count total gaps across all artifacts; fall back to content.gaps array length when field is 0
  const totalGaps = result.artifacts.reduce((n, a) => {
    if (a.gaps > 0) return n + a.gaps
    const contentGapsArr = (a.content as Record<string, unknown>)?.gaps
    return n + (Array.isArray(contentGapsArr) ? contentGapsArr.length : 0)
  }, 0)
  const totalPublic = result.artifacts.reduce((n, a) => n + (a.public_count ?? 0), 0)

  // ── Overview tab ────────────────────────────────────────────────────────────
  const overviewContent = (
    <div className="flex flex-col gap-5">

      {/* Stats strip */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "Reports", value: result.artifacts.length, color: "text-violet-400" },
          { label: "Sources", value: result.citations.length, color: "text-blue-400" },
          { label: "Public Signals", value: totalPublic, color: "text-green-400" },
          { label: "Gaps", value: totalGaps, color: totalGaps > 0 ? "text-red-400" : "text-[var(--muted-foreground)]" },
        ].map(({ label, value, color }) => (
          <div key={label} className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-3 text-center">
            <p className={`text-2xl font-bold ${color}`}>{value}</p>
            <p className="text-[10px] text-[var(--muted-foreground)] mt-0.5 uppercase tracking-wide">{label}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_260px] gap-5 items-start">
        {/* Left: brief + insights */}
        <div className="flex flex-col gap-4">
          {brief && (
            <TextureCard className="p-5">
              <div className="flex items-center gap-2 mb-3">
                <FileText className="w-3.5 h-3.5 text-violet-400" />
                <span className="text-[10px] font-bold uppercase tracking-widest text-[var(--muted-foreground)]">
                  Research Brief
                </span>
              </div>
              <p className="text-sm leading-relaxed">{brief}</p>
            </TextureCard>
          )}

          {insights.length > 0 && (
            <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
              <div className="flex items-center gap-2 mb-3">
                <Lightbulb className="w-3.5 h-3.5 text-amber-400" />
                <span className="text-[10px] font-bold uppercase tracking-widest text-[var(--muted-foreground)]">
                  Key Insights
                </span>
              </div>
              <ul className="flex flex-col gap-2.5">
                {insights.map((pt, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-sm leading-relaxed">
                    <span className="text-violet-400 shrink-0 text-xs mt-0.5">◆</span>
                    <span>{pt}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {!brief && insights.length === 0 && (
            <div className="rounded-2xl border border-dashed border-[var(--border)] p-6 text-center">
              <FileText className="w-8 h-8 text-[var(--muted-foreground)] mx-auto mb-2 opacity-40" />
              <p className="text-sm text-[var(--muted-foreground)]">
                {result.artifacts.length} report{result.artifacts.length !== 1 ? "s" : ""} generated —
                open the <strong className="text-[var(--foreground)]">Reports</strong> tab to read them.
              </p>
            </div>
          )}
        </div>

        {/* Right: reports list + quality grade */}
        <div className="flex flex-col gap-4">
          {result.artifacts.length > 0 && (
            <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-4">
              <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--muted-foreground)] mb-3">
                Reports ({result.artifacts.length})
              </p>
              <ul className="flex flex-col gap-2.5">
                {result.artifacts.map((a, i) => (
                  <li key={i} className="flex items-start gap-2.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-violet-400 shrink-0 mt-1.5" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium leading-snug">{getArtTitle(a)}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <p className="text-[10px] text-[var(--muted-foreground)]">{cleanArtType(a.type)}</p>
                        {a.public_count > 0 && (
                          <span className="flex items-center gap-0.5 text-[10px] text-blue-400">
                            <Globe className="w-2.5 h-2.5" />{a.public_count}
                          </span>
                        )}
                        {a.gaps > 0 && (
                          <span className="flex items-center gap-0.5 text-[10px] text-red-400">
                            <AlertTriangle className="w-2.5 h-2.5" />{a.gaps} gap{a.gaps !== 1 ? "s" : ""}
                          </span>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {result.grade && (
            <div className={`rounded-2xl border p-4 ${result.grade.passed
              ? "border-green-500/30 bg-green-900/10"
              : "border-red-500/30 bg-red-900/10"}`}>
              <div className="flex items-center gap-2">
                {result.grade.passed
                  ? <CheckCircle2 className="w-4 h-4 text-green-400" />
                  : <XCircle className="w-4 h-4 text-red-400" />}
                <span className="text-sm font-semibold">
                  Quality {result.grade.passed ? "passed" : "failed"}
                  {result.grade.score !== undefined && ` · ${result.grade.score}/5`}
                </span>
              </div>
              {result.grade.hard_failures.length > 0 && (
                <ul className="mt-2 flex flex-col gap-1">
                  {result.grade.hard_failures.map((f, i) => (
                    <li key={i} className="text-xs text-red-400">· {f}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Citations preview */}
          {result.citations.length > 0 && (
            <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-4">
              <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--muted-foreground)] mb-3">
                Top Sources
              </p>
              <div className="flex flex-col gap-1.5">
                {result.citations.slice(0, 5).map((c, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm min-w-0">
                    <span className={`shrink-0 ${c.boundary === "public" ? "text-blue-400" : "text-amber-400"}`}>
                      {c.boundary === "public" ? <Globe className="w-3 h-3" /> : <Lock className="w-3 h-3" />}
                    </span>
                    {c.url ? (
                      <a href={c.url} target="_blank" rel="noopener noreferrer"
                         className="text-blue-400 hover:underline truncate text-xs">{c.label}</a>
                    ) : (
                      <span className="text-[var(--muted-foreground)] text-xs truncate">{c.label}</span>
                    )}
                  </div>
                ))}
                {result.citations.length > 5 && (
                  <p className="text-[10px] text-[var(--muted-foreground)] mt-1">
                    +{result.citations.length - 5} more in Sources tab
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {inlineChat}

      <div className="flex items-center gap-2">
        <span className="text-xs text-[var(--muted-foreground)]">Helpful?</span>
        <button
          onClick={() => sendFeedback(1)}
          className={`p-1.5 rounded-lg transition-all ${feedback === 1
            ? "bg-green-100 text-green-600"
            : "hover:bg-[var(--muted)] text-[var(--muted-foreground)]"}`}>
          <ThumbsUp className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => sendFeedback(-1)}
          className={`p-1.5 rounded-lg transition-all ${feedback === -1
            ? "bg-red-100 text-red-600"
            : "hover:bg-[var(--muted)] text-[var(--muted-foreground)]"}`}>
          <ThumbsDown className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  )

  // ── Reports tab — accordion, all collapsed by default ────────────────────────
  const reportsContent = (
    <div className="flex flex-col gap-3">
      {result.artifacts.map((art, i) => (
        <ArtifactAccordion key={i} art={art} defaultOpen={i === 0} />
      ))}
    </div>
  )

  // ── Sources tab ──────────────────────────────────────────────────────────────
  const publicCitations  = result.citations.filter((c) => c.boundary === "public")
  const privateCitations = result.citations.filter((c) => c.boundary !== "public")

  const sourcesContent =
    result.citations.length > 0 ? (
      <div className="flex flex-col gap-4">
        {/* Stats */}
        <div className={`grid gap-3 ${privateCitations.length > 0 ? "grid-cols-2" : "grid-cols-1 max-w-xs"}`}>
          <div className="rounded-xl border border-blue-700/30 bg-blue-900/10 p-4 text-center">
            <p className="text-2xl font-bold text-blue-400">{publicCitations.length}</p>
            <p className="text-[10px] text-[var(--muted-foreground)] mt-0.5 uppercase tracking-wide flex items-center justify-center gap-1">
              <Globe className="w-3 h-3" /> Public Sources
            </p>
          </div>
          {privateCitations.length > 0 && (
            <div className="rounded-xl border border-amber-700/30 bg-amber-900/10 p-4 text-center">
              <p className="text-2xl font-bold text-amber-400">{privateCitations.length}</p>
              <p className="text-[10px] text-[var(--muted-foreground)] mt-0.5 uppercase tracking-wide flex items-center justify-center gap-1">
                <Lock className="w-3 h-3" /> Private Sources
              </p>
            </div>
          )}
        </div>

        {/* Public sources */}
        {publicCitations.length > 0 && (
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] overflow-hidden">
            <div className="px-5 py-3 border-b border-[var(--border)] flex items-center gap-2">
              <Globe className="w-3.5 h-3.5 text-blue-400" />
              <span className="text-[10px] font-bold uppercase tracking-widest text-[var(--muted-foreground)]">
                Public Intelligence ({publicCitations.length})
              </span>
            </div>
            <div className="divide-y divide-[var(--border)]">
              {publicCitations.map((c, i) => (
                <div key={i} className="px-5 py-3 flex items-center gap-3">
                  <span className="text-[10px] text-[var(--muted-foreground)] font-mono w-5 shrink-0">{i + 1}</span>
                  {c.url ? (
                    <a href={c.url} target="_blank" rel="noopener noreferrer"
                       className="text-blue-400 hover:underline text-sm flex-1 min-w-0 truncate">{c.label}</a>
                  ) : (
                    <span className="text-sm text-[var(--foreground)] flex-1 min-w-0">{c.label}</span>
                  )}
                  {c.url && (
                    <span className="text-[10px] text-[var(--muted-foreground)] font-mono shrink-0 hidden sm:block truncate max-w-[180px]">
                      {(() => { try { return new URL(c.url).hostname } catch { return "" } })()}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Private sources */}
        {privateCitations.length > 0 && (
          <div className="rounded-2xl border border-amber-700/20 bg-[var(--card)] overflow-hidden">
            <div className="px-5 py-3 border-b border-amber-700/20 flex items-center gap-2">
              <Lock className="w-3.5 h-3.5 text-amber-400" />
              <span className="text-[10px] font-bold uppercase tracking-widest text-[var(--muted-foreground)]">
                Private Intelligence ({privateCitations.length})
              </span>
            </div>
            <div className="divide-y divide-amber-700/10">
              {privateCitations.map((c, i) => (
                <div key={i} className="px-5 py-3 flex items-center gap-3">
                  <span className="text-[10px] text-[var(--muted-foreground)] font-mono w-5 shrink-0">{i + 1}</span>
                  <span className="text-sm text-[var(--foreground)] flex-1 min-w-0">{c.label}</span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-900/30 text-amber-300 border border-amber-700/30 font-semibold">
                    PRIVATE
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    ) : null

  const pipelineContent = <PipelinePanel projectId={task.project_id} taskId={task.id} />

  const tabs = [
    { id: 0, label: "Overview", content: overviewContent },
    ...(result.artifacts.length > 0
      ? [{ id: 1, label: `Reports (${result.artifacts.length})`, content: reportsContent }]
      : []),
    ...(sourcesContent ? [{ id: 2, label: "Sources", content: sourcesContent }] : []),
    { id: 3, label: "Pipeline", content: pipelineContent },
  ]

  return <DirectionAwareTabs tabs={tabs} />
}

function splitObjective(obj: string): { question: string; target?: string } {
  const m = obj.match(/^([\s\S]*?)\s*\[Target:\s*([^\]]+)\]\s*$/)
  if (m) return { question: m[1].trim(), target: m[2].trim() }
  return { question: obj }
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function TaskDetailPage({
  params,
}: {
  params: Promise<{ id: string; taskId: string }>
}) {
  const { id: projectId, taskId } = use(params)

  const { data: task, mutate: refresh } = useSWR<Task>(
    `/api/projects/${projectId}/tasks/${taskId}`,
    fetcher,
    { refreshInterval: (data: Task | undefined) =>
        (data?.status === "running" || data?.status === "created" || data?.status === "planned" ? 2000 : 0) }
  )

  const { data: project } = useSWR<Project>(`/api/projects/${projectId}`, fetcher)

  const [launching, setLaunching] = useState(false)

  async function runTask() {
    if (launching) return
    setLaunching(true)
    try {
      await tasksApi.run(projectId, taskId)
      refresh({ ...task, status: "running" } as Task, false)
    } catch {
      // SWR reconciles on next poll
    } finally {
      setLaunching(false)
    }
  }

  return (
    <div className="flex flex-col gap-5 max-w-5xl mx-auto">
      {/* Breadcrumb */}
      {(() => {
        const { question } = splitObjective(task?.objective ?? "Task")
        return (
          <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
            <Link href="/projects" className="hover:underline">Projects</Link>
            <span>/</span>
            <Link href={`/projects/${projectId}`} className="hover:underline truncate max-w-[160px]">
              {project?.name ?? "Project"}
            </Link>
            <span>/</span>
            <span className="truncate max-w-[260px] text-[var(--foreground)]">{question}</span>
          </div>
        )
      })()}

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          {(() => {
            const { question, target } = splitObjective(task?.objective ?? "")
            return (
              <>
                <h1 className="text-xl font-bold leading-snug text-[var(--foreground)] line-clamp-2">
                  {question || "Loading…"}
                </h1>
                <div className="flex items-center gap-2 mt-2 flex-wrap">
                  {target && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900/20 dark:text-blue-300 font-medium">
                      🎯 {target}
                    </span>
                  )}
                  {task?.domain && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-[var(--muted)] text-[var(--muted-foreground)] font-medium">
                      {task.domain}
                    </span>
                  )}
                  {task?.persona && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-purple-100 text-purple-700 dark:bg-purple-900/20 dark:text-purple-300 font-medium">
                      {task.persona}
                    </span>
                  )}
                </div>
              </>
            )
          })()}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {task?.status === "done" && task.result && (
            <a
              href={`/projects/${task.project_id}/tasks/${task.id}/export.html`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border)]
                         text-xs font-semibold hover:bg-[var(--muted)] transition-colors">
              <Download className="w-3.5 h-3.5" /> Export
            </a>
          )}
          {task && task.status !== "running" && (
            <button
              onClick={runTask}
              disabled={launching}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-black dark:bg-white
                         text-white dark:text-black text-sm font-semibold hover:opacity-80
                         disabled:opacity-50 transition-opacity">
              {launching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
              {task.status === "done" ? "Re-run" : "Run"}
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      {task?.status === "running" && <LiveRunPanel projectId={projectId} taskId={taskId} onRerun={runTask} />}
      {task?.status === "done" && task.result && <ResultPanel task={task} />}
      {task?.status === "failed" && (
        <div className="rounded-2xl border border-red-200 bg-red-50 dark:bg-red-900/10 p-6">
          <div className="flex items-start gap-3">
            <XCircle className="w-6 h-6 text-red-500 shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="font-semibold text-red-700 dark:text-red-400">Task failed</p>
              {task.fail_reason && (
                <p className="mt-1 text-sm text-red-600 dark:text-red-300 font-mono break-all leading-relaxed">
                  {task.fail_reason}
                </p>
              )}
              <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                Re-run the task to retry with the same pipeline.
              </p>
            </div>
          </div>
          <div className="mt-4">
            <button
              onClick={runTask}
              className="px-4 py-2 rounded-lg bg-red-600 text-white text-sm font-semibold hover:opacity-80 transition-opacity">
              Retry
            </button>
          </div>
        </div>
      )}
      {task?.status === "created" && (
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6">
          <div className="flex items-center justify-between mb-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
              Pipeline
            </p>
          </div>
          <div className="flex flex-col gap-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex items-center gap-3 animate-pulse">
                <div className="w-6 h-6 rounded-full bg-[var(--muted)] shrink-0" />
                <div className="h-3 rounded bg-[var(--muted)]" style={{ width: `${40 + i * 15}%` }} />
              </div>
            ))}
            <p className="text-xs text-[var(--muted-foreground)] mt-1 animate-pulse">
              Planning research pipeline…
            </p>
          </div>
        </div>
      )}
      {task?.status === "planned" && (
        <div className="rounded-2xl border border-dashed border-[var(--border)] p-12 text-center">
          <Play className="w-8 h-8 text-[var(--muted-foreground)] mx-auto mb-3" />
          <p className="text-sm text-[var(--muted-foreground)]">
            Plan ready — hit <strong>Run</strong> to start the research pipeline.
          </p>
        </div>
      )}
    </div>
  )
}
