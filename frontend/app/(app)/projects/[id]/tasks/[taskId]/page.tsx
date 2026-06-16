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
      ? (c.executive_summary as string)
      : null) ??
    (typeof c.summary === "string" && (c.summary as string).length > 20
      ? (c.summary as string)
      : null) ??
    (typeof c.overview === "string" && (c.overview as string).length > 20
      ? (c.overview as string)
      : null) ??
    undefined

  const insights: string[] = []
  for (const field of ["key_findings", "key_insights", "highlights", "insights", "recommendations"]) {
    const arr = c[field]
    if (!Array.isArray(arr)) continue
    for (const item of arr as unknown[]) {
      if (typeof item === "string" && item.length > 15) insights.push(item)
      else if (typeof item === "object" && item !== null) {
        const o = item as Record<string, unknown>
        const t = o.text ?? o.finding ?? o.insight ?? o.title ?? o.content
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

function ArtifactItem({ item }: { item: unknown }) {
  if (typeof item === "string") return <span>{item}</span>
  if (typeof item === "object" && item !== null) {
    const o = item as Record<string, unknown>
    const url = typeof o.url === "string" ? o.url : undefined
    const label = String(o.text ?? o.name ?? o.title ?? o.action ?? JSON.stringify(item))
    if (url)
      return (
        <a href={url} target="_blank" rel="noopener noreferrer"
           className="text-blue-400 hover:underline break-all">{label}</a>
      )
    return <span>{label}</span>
  }
  return <span>{String(item)}</span>
}

function CollapsibleList({ items }: { items: unknown[] }) {
  const [expanded, setExpanded] = useState(false)
  const LIMIT = 4
  const visible = expanded ? items : items.slice(0, LIMIT)
  const overflow = items.length - LIMIT
  return (
    <>
      <ul className="flex flex-col gap-1">
        {visible.map((item, j) => (
          <li key={j} className="text-sm flex items-start gap-2">
            <span className="text-[var(--muted-foreground)] mt-0.5 shrink-0">·</span>
            <ArtifactItem item={item} />
          </li>
        ))}
      </ul>
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
            {contentEntries.map(([key, val]) => (
              <div key={key}>
                <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--muted-foreground)] mb-2">
                  {fmtLabel(key)}
                </p>
                {Array.isArray(val) ? (
                  <CollapsibleList items={val as unknown[]} />
                ) : typeof val === "object" ? (
                  <pre className="text-xs text-[var(--muted-foreground)] whitespace-pre-wrap bg-[var(--muted)] rounded-xl p-3 overflow-auto border border-[var(--border)]">
                    {JSON.stringify(val, null, 2)}
                  </pre>
                ) : typeof val === "string" && val.length > 280 ? (
                  <LongText text={val} />
                ) : (
                  <p className="text-sm leading-relaxed">{String(val)}</p>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ── LiveRunPanel ──────────────────────────────────────────────────────────────

function LiveRunPanel({ projectId, taskId }: { projectId: string; taskId: string }) {
  const { data: status } = useSWR<TaskStatus>(
    `/projects/${projectId}/tasks/${taskId}/status.json`,
    fetcher,
    { refreshInterval: (d) => (d?.state === "done" || d?.state === "failed" ? 0 : 2000) }
  )

  const steps = status?.steps ?? []
  const logLines = (status?.log ?? []).map((l) => ({
    command: `[${l.agent}] ${l.message}`,
    output: l.type === "error" ? "ERROR" : undefined,
  }))

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-4">
          Pipeline
        </p>
        <div className="flex flex-col gap-2">
          {steps.map((step) => (
            <div key={step.id} className="flex items-center gap-3">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0
                ${step.status === "done"    ? "bg-green-100 text-green-600" :
                  step.status === "running" ? "bg-amber-100 text-amber-600" :
                  step.status === "failed"  ? "bg-red-100 text-red-600" :
                  "bg-[var(--muted)] text-[var(--muted-foreground)]"}`}>
                {step.status === "done"    ? <CheckCircle2 className="w-3.5 h-3.5" /> :
                 step.status === "running" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> :
                 step.status === "failed"  ? <XCircle className="w-3.5 h-3.5" /> :
                 <Clock className="w-3.5 h-3.5" />}
              </div>
              <span className="text-sm capitalize">{step.capability.replace(/_/g, " ")}</span>
              {step.status === "running" && status?.current_step === step.id && (
                <span className="text-xs text-amber-600 animate-pulse">Running…</span>
              )}
            </div>
          ))}
        </div>
      </div>

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
      : "bg-neutral-800 text-neutral-400 border border-neutral-700"
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
                  <span className="text-sm font-semibold capitalize">{step.capability.replace(/_/g, " ")}</span>
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
                <p className="text-sm font-medium capitalize">{step.capability.replace(/_/g, " ")}</p>
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
                  <p className="text-sm font-semibold capitalize mt-0.5">{step.capability.replace(/_/g, " ")}</p>
                  <div className="mt-1.5">{callsBadge(step.calls)}</div>
                  <p className="text-[10px] font-mono text-[var(--muted-foreground)] mt-1.5 truncate">
                    {step.agent_spec_id}
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
                <td className="px-4 py-3 font-semibold capitalize">{step.capability.replace(/_/g, " ")}</td>
                <td className="px-4 py-3">{callsBadge(step.calls)}</td>
                <td className="px-4 py-3 font-mono text-xs text-[var(--muted-foreground)]">
                  {step.depends_on.length > 0 ? step.depends_on.join(", ") : "—"}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-[var(--muted-foreground)] max-w-[200px] truncate">
                  {step.agent_spec_id}
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

  const synthArt =
    result.artifacts.find((a) => /synthesis|overview|executive/i.test(a.type)) ??
    (result.artifacts.length > 0 ? result.artifacts[result.artifacts.length - 1] : null)

  const { brief, insights } = synthArt ? extractSummary(synthArt) : { brief: undefined, insights: [] }

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
    <div className="rounded-2xl border border-neutral-800 bg-neutral-950 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-neutral-800">
        <Sparkles className="w-3.5 h-3.5 text-violet-400" />
        <span className="text-xs font-semibold text-neutral-200">Follow-up Questions</span>
      </div>

      {chatHistory.length > 0 && (
        <div className="px-4 py-4 flex flex-col gap-3 max-h-80 overflow-y-auto">
          {chatHistory.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`px-4 py-2.5 rounded-2xl max-w-[85%] leading-relaxed
                ${m.role === "user"
                  ? "bg-violet-600 text-white text-sm rounded-br-sm"
                  : "bg-neutral-800 text-neutral-100 rounded-bl-sm border border-neutral-700"}`}>
                {m.role === "user" ? m.content : <MdMessage text={m.content} />}
              </div>
            </div>
          ))}
          {chatLoading && (
            <div className="flex justify-start">
              <div className="bg-neutral-800 border border-neutral-700 rounded-2xl rounded-bl-sm px-4 py-3">
                <div className="flex gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-neutral-400 animate-bounce [animation-delay:0ms]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-neutral-400 animate-bounce [animation-delay:150ms]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-neutral-400 animate-bounce [animation-delay:300ms]" />
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
              className="text-[11px] px-3 py-1.5 rounded-full border border-neutral-700
                         text-neutral-300 hover:border-violet-500 hover:text-white
                         transition-colors bg-neutral-900">
              {q}
            </button>
          ))}
        </div>
      )}

      <form onSubmit={sendChat} className="flex gap-2 items-center p-3 border-t border-neutral-800">
        <input
          value={chatMsg}
          onChange={(e) => setChatMsg(e.target.value)}
          placeholder="Ask a follow-up question…"
          className="flex-1 rounded-xl border border-neutral-700 bg-neutral-900
                     px-4 py-2 text-sm text-white placeholder:text-neutral-500
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

  // ── Overview tab — 2-column layout ────────────────────────────────────────────
  const overviewContent = (
    <div className="flex flex-col gap-5">
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
            <TextureCard className="p-5">
              <p className="text-sm text-[var(--muted-foreground)]">
                Research complete —{" "}
                <span className="font-semibold text-[var(--foreground)]">{result.artifacts.length}</span>{" "}
                report{result.artifacts.length !== 1 ? "s" : ""} generated. See the{" "}
                <span className="font-semibold text-[var(--foreground)]">Reports</span> tab.
              </p>
            </TextureCard>
          )}
        </div>

        {/* Right: reports list + grade */}
        <div className="flex flex-col gap-4">
          {result.artifacts.length > 0 && (
            <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-4">
              <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--muted-foreground)] mb-3">
                Reports ({result.artifacts.length})
              </p>
              <ul className="flex flex-col gap-2">
                {result.artifacts.map((a, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <span className="w-1.5 h-1.5 rounded-full bg-violet-400 shrink-0 mt-1.5" />
                    <div className="min-w-0">
                      <p className="font-medium leading-snug truncate">{getArtTitle(a)}</p>
                      <p className="text-[10px] text-[var(--muted-foreground)] mt-0.5">{cleanArtType(a.type)}</p>
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
  const sourcesContent =
    result.citations.length > 0 ? (
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
        <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--muted-foreground)] mb-4">
          Sources
        </p>
        <div className="flex flex-col gap-2">
          {result.citations.map((c, i) => (
            <div key={i} className="flex items-center gap-2 text-sm">
              <span className={`shrink-0 ${c.boundary === "public" ? "text-blue-400" : "text-amber-400"}`}>
                {c.boundary === "public" ? <Globe className="w-3 h-3" /> : <Lock className="w-3 h-3" />}
              </span>
              {c.url ? (
                <a href={c.url} target="_blank" rel="noopener noreferrer"
                   className="text-blue-400 hover:underline truncate">{c.label}</a>
              ) : (
                <span className="text-[var(--muted-foreground)]">{c.label}</span>
              )}
            </div>
          ))}
        </div>
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
    { refreshInterval: (data: Task | undefined) => (data?.status === "running" ? 3000 : 0) }
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
      <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
        <Link href="/projects" className="hover:underline">Projects</Link>
        <span>/</span>
        <Link href={`/projects/${projectId}`} className="hover:underline truncate max-w-[160px]">
          {project?.name ?? "Project"}
        </Link>
        <span>/</span>
        <span className="truncate max-w-[260px] text-[var(--foreground)]">
          {task?.objective ?? "Task"}
        </span>
      </div>

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-bold leading-snug text-[var(--foreground)] line-clamp-2">
            {task?.objective ?? "Loading…"}
          </h1>
          <div className="flex items-center gap-2 mt-2 flex-wrap">
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
      {task?.status === "running" && <LiveRunPanel projectId={projectId} taskId={taskId} />}
      {task?.status === "done" && task.result && <ResultPanel task={task} />}
      {task?.status === "failed" && (
        <div className="rounded-2xl border border-red-200 bg-red-50 dark:bg-red-900/10 p-6 text-center">
          <XCircle className="w-8 h-8 text-red-500 mx-auto mb-2" />
          <p className="font-semibold text-red-700 dark:text-red-400">Task failed</p>
          <button
            onClick={runTask}
            className="mt-3 px-4 py-2 rounded-lg bg-red-600 text-white text-sm font-semibold hover:opacity-80 transition-opacity">
            Retry
          </button>
        </div>
      )}
      {(task?.status === "created" || task?.status === "planned") && (
        <div className="rounded-2xl border border-dashed border-[var(--border)] p-12 text-center">
          <Play className="w-8 h-8 text-[var(--muted-foreground)] mx-auto mb-3" />
          <p className="text-sm text-[var(--muted-foreground)]">
            Task is ready. Hit <strong>Run</strong> to start the research pipeline.
          </p>
          <div className="flex items-center justify-center gap-2 mt-3 flex-wrap">
            {task.domain && (
              <span className="text-xs bg-[var(--muted)] px-2 py-0.5 rounded">{task.domain}</span>
            )}
            {task?.persona && (
              <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded">{task.persona}</span>
            )}
            {task?.status === "planned" && (
              <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">Plan ready</span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
