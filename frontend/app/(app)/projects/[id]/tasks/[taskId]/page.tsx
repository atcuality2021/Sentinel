"use client"

import { use, useState } from "react"
import useSWR from "swr"
import Link from "next/link"
import { TextureCard } from "@/components/ui/texture-card"
import { TerminalAnimation } from "@/components/ui/terminal-animation"
import { AnimatedNumber } from "@/components/ui/animated-number"
import { DirectionAwareTabs } from "@/components/ui/direction-aware-tabs"
import {
  type Task, type TaskStatus, type Project, type ArtifactData,
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

function cleanArtType(type: string): string {
  return (
    type
      .replace(/^(RESEARCH_DEPT_|GOVT_DEPT_|DEPT_|RESEARCH_|GOVT_)/, "")
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase())
      .trim() || "Report"
  )
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
          return (
            <code key={i} className="text-[11px] bg-neutral-700 px-1 rounded font-mono">
              {p.slice(1, -1)}
            </code>
          )
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
        if (/^\d+\./.test(first)) {
          return (
            <ol key={i} className="list-decimal pl-5 space-y-0.5">
              {lines.map((l, j) => (
                <li key={j} className="text-sm leading-relaxed">
                  <InlineMd text={l.replace(/^\d+\.\s*/, "")} />
                </li>
              ))}
            </ol>
          )
        }
        if (/^[-*•]/.test(first)) {
          return (
            <ul key={i} className="list-disc pl-5 space-y-0.5">
              {lines.map((l, j) => (
                <li key={j} className="text-sm leading-relaxed">
                  <InlineMd text={l.replace(/^[-*•]\s*/, "")} />
                </li>
              ))}
            </ul>
          )
        }
        return (
          <p key={i} className="text-sm leading-relaxed">
            <InlineMd text={block} />
          </p>
        )
      })}
    </div>
  )
}

// ── Artifact content renderers ────────────────────────────────────────────────

function ArtifactItem({ item }: { item: unknown }) {
  if (typeof item === "string") return <span>{item}</span>
  if (typeof item === "object" && item !== null) {
    const o = item as Record<string, unknown>
    const url = typeof o.url === "string" ? o.url : undefined
    const label = String(o.text ?? o.name ?? o.title ?? o.action ?? JSON.stringify(item))
    if (url)
      return (
        <a href={url} target="_blank" rel="noopener noreferrer"
           className="text-blue-400 hover:underline break-all">
          {label}
        </a>
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
  const isLong = text.length > 250
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

// ── LiveRunPanel ──────────────────────────────────────────────────────────────

function LiveRunPanel({ projectId, taskId }: { projectId: string; taskId: string }) {
  const { data: status } = useSWR<TaskStatus>(
    `/projects/${projectId}/tasks/${taskId}/status.json`,
    fetcher,
    { refreshInterval: (d) => (d?.status === "done" || d?.status === "failed" ? 0 : 2000) }
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

// ── ResultPanel ───────────────────────────────────────────────────────────────

function ResultPanel({ task }: { task: Task }) {
  const [chatMsg, setChatMsg] = useState("")
  const [chatLoading, setChatLoading] = useState(false)
  const [chatHistory, setChatHistory] = useState(task.chat ?? [])
  const [feedback, setFeedback] = useState<1 | -1 | null>(null)

  const result = task.result
  if (!result) return null

  // Use the last artifact (often the synthesis) for the brief
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

  // ── Inline chat ─────────────────────────────────────────────────────────────
  const SUGGESTIONS = [
    "What was the most important finding?",
    "Summarise the key risks",
    "What are the recommended next steps?",
    "List the main sources used",
  ]

  const inlineChat = (
    <div className="rounded-2xl border border-neutral-800 bg-neutral-950 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-neutral-800">
        <Sparkles className="w-3.5 h-3.5 text-violet-400" />
        <span className="text-xs font-semibold text-neutral-200">Follow-up Questions</span>
      </div>

      {chatHistory.length > 0 && (
        <div className="px-4 py-4 flex flex-col gap-3 max-h-72 overflow-y-auto">
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

  // ── Overview tab ─────────────────────────────────────────────────────────────
  const overviewContent = (
    <div className="flex flex-col gap-5">
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
            report{result.artifacts.length !== 1 ? "s" : ""} generated. Open the{" "}
            <span className="font-semibold text-[var(--foreground)]">Reports</span> tab for full findings.
          </p>
        </TextureCard>
      )}

      {result.artifacts.length > 0 && (
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--muted-foreground)] mb-2.5">
            Reports Generated ({result.artifacts.length})
          </p>
          <div className="flex flex-wrap gap-2">
            {result.artifacts.map((a, i) => (
              <span
                key={i}
                className="text-xs px-2.5 py-1 rounded-full border border-[var(--border)]
                           bg-[var(--card)] text-[var(--foreground)] font-medium">
                {a.target}
              </span>
            ))}
          </div>
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
              Quality check {result.grade.passed ? "passed" : "failed"}
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

      {inlineChat}

      <div className="flex items-center gap-2 pt-1">
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

  // ── Reports tab ──────────────────────────────────────────────────────────────
  const reportsContent = (
    <div className="flex flex-col gap-5">
      {result.artifacts.map((art, i) => (
        <TextureCard key={i} className="p-6">
          <div className="flex items-start justify-between gap-3 mb-4">
            <div className="min-w-0">
              <span className="inline-block text-[10px] font-bold uppercase tracking-widest
                               text-[var(--muted-foreground)] bg-[var(--muted)] px-2 py-0.5 rounded-full mb-2">
                {cleanArtType(art.type)}
              </span>
              <h3 className="text-base font-semibold leading-snug">{art.target}</h3>
            </div>
            <div className="flex items-center gap-3 text-xs shrink-0 mt-1">
              {art.public_count > 0 && (
                <span className="flex items-center gap-1 text-blue-400">
                  <Globe className="w-3 h-3" /> {art.public_count}
                </span>
              )}
              {art.private_count > 0 && (
                <span className="flex items-center gap-1 text-amber-400">
                  <Lock className="w-3 h-3" /> {art.private_count}
                </span>
              )}
              {art.gaps > 0 && (
                <span className="flex items-center gap-1 text-red-400">
                  <AlertTriangle className="w-3 h-3" /> {art.gaps}
                </span>
              )}
            </div>
          </div>

          <div className="h-px bg-[var(--border)] mb-4" />

          {Object.entries(art.content).map(([key, val]) => {
            if (key.startsWith("_")) return null
            if (val === null || val === undefined || val === "") return null
            if (Array.isArray(val) && val.length === 0) return null
            return (
              <div key={key} className="mb-5 last:mb-0">
                <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--muted-foreground)] mb-2">
                  {fmtLabel(key)}
                </p>
                {Array.isArray(val) ? (
                  <CollapsibleList items={val as unknown[]} />
                ) : typeof val === "object" ? (
                  <pre className="text-xs text-[var(--muted-foreground)] whitespace-pre-wrap bg-[var(--muted)] rounded-xl p-3 overflow-auto border border-[var(--border)]">
                    {JSON.stringify(val, null, 2)}
                  </pre>
                ) : typeof val === "string" && val.length > 250 ? (
                  <LongText text={val} />
                ) : (
                  <p className="text-sm leading-relaxed">{String(val)}</p>
                )}
              </div>
            )
          })}
        </TextureCard>
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
                {c.boundary === "public"
                  ? <Globe className="w-3 h-3" />
                  : <Lock className="w-3 h-3" />}
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

  const tabs = [
    { id: 0, label: "Overview", content: overviewContent },
    ...(result.artifacts.length > 0
      ? [{ id: 1, label: `Reports (${result.artifacts.length})`, content: reportsContent }]
      : []),
    ...(sourcesContent
      ? [{ id: 2, label: "Sources", content: sourcesContent }]
      : []),
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
    <div className="flex flex-col gap-5 max-w-3xl mx-auto">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
        <Link href="/projects" className="hover:underline">Projects</Link>
        <span>/</span>
        <Link href={`/projects/${projectId}`} className="hover:underline truncate max-w-[160px]">
          {project?.name ?? "Project"}
        </Link>
        <span>/</span>
        <span className="truncate max-w-[200px] text-[var(--foreground)]">
          {task?.objective ?? "Task"}
        </span>
      </div>

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-bold leading-snug text-[var(--foreground)]">
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
