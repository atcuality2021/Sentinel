"use client"

import { use, useState, useRef, useEffect } from "react"
import useSWR from "swr"
import Link from "next/link"
import { Drawer } from "vaul"
import { GradientHeading } from "@/components/ui/gradient-heading"
import { TerminalAnimation } from "@/components/ui/terminal-animation"
import { AnimatedNumber } from "@/components/ui/animated-number"
import { DirectionAwareTabs } from "@/components/ui/direction-aware-tabs"
import { TextureCard } from "@/components/ui/texture-card"
import { type Task, type TaskStatus, type Project, tasks as tasksApi } from "@/lib/api"
import {
  Globe, Lock, AlertTriangle, ThumbsUp, ThumbsDown,
  Play, Download, MessageSquare, Loader2, CheckCircle2,
  XCircle, Clock, ChevronDown, ChevronUp, Send, Sparkles,
} from "lucide-react"
import { fetcher } from "@/lib/fetcher"

function fmtLabel(key: string) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}

// ── Live status poller ──────────────────────────────────────────────────────
function LiveRunPanel({ projectId, taskId }: { projectId: string; taskId: string }) {
  const { data: status } = useSWR<TaskStatus>(
    `/projects/${projectId}/tasks/${taskId}/status.json`,
    fetcher,
    {
      refreshInterval: (statusData) =>
        statusData?.status === "done" || statusData?.status === "failed" ? 0 : 2000,
    }
  )

  const steps = status?.steps ?? []
  const logLines = (status?.log ?? []).map((l) => ({
    command: `[${l.agent}] ${l.message}`,
    output: l.type === "error" ? "ERROR" : undefined,
  }))

  return (
    <div className="flex flex-col gap-6">
      {/* Step timeline */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-4">
          Pipeline
        </p>
        <div className="flex flex-col gap-2">
          {steps.map((step, i) => (
            <div key={step.id} className="flex items-center gap-3">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 text-xs
                ${step.status === "done"    ? "bg-green-100 text-green-600" :
                  step.status === "running" ? "bg-amber-100 text-amber-600" :
                  step.status === "failed"  ? "bg-red-100 text-red-600" :
                  "bg-[var(--muted)] text-[var(--muted-foreground)]"}`}>
                {step.status === "done"    ? <CheckCircle2 className="w-3.5 h-3.5" /> :
                 step.status === "running" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> :
                 step.status === "failed"  ? <XCircle className="w-3.5 h-3.5" /> :
                 <Clock className="w-3.5 h-3.5" />}
              </div>
              {i < steps.length - 1 && (
                <div className="absolute left-3 top-6 w-px h-full bg-[var(--border)]" />
              )}
              <span className="text-sm capitalize">{step.capability.replace(/_/g, " ")}</span>
              {step.status === "running" && status?.current_step === step.id && (
                <span className="text-xs text-amber-600 animate-pulse">Running…</span>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Live counters */}
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

      {/* Terminal log */}
      {logLines.length > 0 && (
        <TerminalAnimation
          scenarios={[{ id: "live", label: "Live Log", steps: logLines }]}
          autoPlay
        />
      )}
    </div>
  )
}

// ── Finding block ───────────────────────────────────────────────────────────
function FindingBlock({
  text, boundary, sourceLabel,
}: { text: string; boundary: "public" | "private" | "gap"; sourceLabel?: string }) {
  const cls = boundary === "public"  ? "finding-public"  :
              boundary === "private" ? "finding-private" : "finding-gap"
  const badge = boundary === "public"  ? "badge-public"  :
                boundary === "private" ? "badge-private" : "badge-gap"
  const icon = boundary === "public"  ? <Globe className="w-3 h-3" /> :
               boundary === "private" ? <Lock className="w-3 h-3" /> :
               <AlertTriangle className="w-3 h-3" />

  return (
    <div className={`${cls} py-2 mb-2`}>
      <p className="text-sm leading-relaxed">{text}</p>
      {sourceLabel && (
        <span className={`inline-flex items-center gap-1 mt-1.5 ${badge}`}>
          {icon} {sourceLabel}
        </span>
      )}
    </div>
  )
}

// ── Artifact content item renderer ──────────────────────────────────────────
function ArtifactItem({ item }: { item: unknown }) {
  if (typeof item === "string") return <span>{item}</span>
  if (typeof item === "object" && item !== null) {
    const o = item as Record<string, unknown>
    const url = typeof o.url === "string" ? o.url : undefined
    const label = String(o.text ?? o.name ?? o.title ?? o.action ?? JSON.stringify(item))
    if (url) {
      return (
        <a href={url} target="_blank" rel="noopener noreferrer"
           className="text-blue-500 hover:underline break-all">
          {label}
        </a>
      )
    }
    return <span>{label}</span>
  }
  return <span>{String(item)}</span>
}

// ── Collapsible list ────────────────────────────────────────────────────────
function CollapsibleList({ items }: { items: unknown[] }) {
  const [expanded, setExpanded] = useState(false)
  const LIMIT = 3
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
        <button onClick={() => setExpanded((v) => !v)}
          className="mt-2 text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)] flex items-center gap-1 transition-colors">
          {expanded
            ? <><ChevronUp className="w-3 h-3" /> Show less</>
            : <><ChevronDown className="w-3 h-3" /> Show {overflow} more</>}
        </button>
      )}
    </>
  )
}

// ── Long text with "Show more" ───────────────────────────────────────────────
function LongText({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false)
  const isLong = text.length > 200
  return (
    <div>
      <p className={`text-sm leading-relaxed ${isLong && !expanded ? "line-clamp-3" : ""}`}>
        {text}
      </p>
      {isLong && (
        <button onClick={() => setExpanded((v) => !v)}
          className="mt-1 text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)] flex items-center gap-1 transition-colors">
          {expanded
            ? <><ChevronUp className="w-3 h-3" /> Show less</>
            : <><ChevronDown className="w-3 h-3" /> Show more</>}
        </button>
      )}
    </div>
  )
}

// ── Result panel ────────────────────────────────────────────────────────────
function ResultPanel({ task }: { task: Task }) {
  const [chatOpen, setChatOpen] = useState((task.chat ?? []).length > 0)
  const [chatMsg, setChatMsg] = useState("")
  const [chatLoading, setChatLoading] = useState(false)
  const [chatHistory, setChatHistory] = useState(task.chat ?? [])
  const [feedback, setFeedback] = useState<1 | -1 | null>(null)
  const result = task.result
  if (!result) return null

  async function sendChat(e: React.FormEvent) {
    e.preventDefault()
    if (!chatMsg.trim()) return
    const userMsg = chatMsg
    setChatMsg("")
    // Optimistically add user message
    setChatHistory((prev) => [...prev, { role: "user" as const, content: userMsg, timestamp: new Date().toISOString() }])
    setChatLoading(true)
    try {
      const res = await tasksApi.chat(task.project_id, task.id, userMsg) as { reply?: string; chat?: typeof task.chat }
      if (res?.chat) {
        setChatHistory(res.chat ?? [])
      } else if (res?.reply) {
        setChatHistory((prev) => [...prev, { role: "assistant" as const, content: res.reply!, timestamp: new Date().toISOString() }])
      }
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

  // ── Tab content components ──────────────────────────────────────────────

  // Detect the raw machine-generated summary and replace with a friendlier header
  const isRawSummary = /^produced \d+ artifact/i.test(result.summary ?? "")
  const artifactNames = isRawSummary
    ? result.summary.replace(/^produced \d+ artifact\(s?\)\s*—?\s*/i, "").split(/,\s*/).filter(Boolean)
    : []

  const overviewContent = (
    <div className="flex flex-col gap-4">
      {/* Summary card */}
      <TextureCard className="p-6">
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-3">
          Summary
        </p>
        {isRawSummary ? (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-[var(--muted-foreground)]">
              Research complete — produced {result.artifacts.length} report{result.artifacts.length !== 1 ? "s" : ""}.
            </p>
            {artifactNames.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {artifactNames.map((n) => (
                  <span key={n} className="text-[11px] px-2 py-0.5 rounded-full border border-[var(--border)] bg-[var(--muted)] text-[var(--muted-foreground)]">
                    {fmtLabel(n)}
                  </span>
                ))}
              </div>
            )}
            {result.artifacts.length > 0 && (
              <p className="text-xs text-[var(--muted-foreground)]">
                Switch to the <span className="font-semibold text-[var(--foreground)]">Artifacts</span> tab to read the full reports.
              </p>
            )}
          </div>
        ) : (
          <p className="text-sm leading-relaxed">{result.summary}</p>
        )}
      </TextureCard>

      {/* Artifact count chips (when we have real content) */}
      {result.artifacts.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-3 text-center">
            <p className="text-xl font-bold">{result.artifacts.length}</p>
            <p className="text-[11px] text-[var(--muted-foreground)] mt-0.5">reports</p>
          </div>
          <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-3 text-center">
            <p className="text-xl font-bold text-blue-400">
              {result.artifacts.reduce((s, a) => s + (a.public_count ?? 0), 0)}
            </p>
            <p className="text-[11px] text-[var(--muted-foreground)] mt-0.5">public findings</p>
          </div>
          <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-3 text-center">
            <p className="text-xl font-bold text-amber-400">
              {result.artifacts.reduce((s, a) => s + (a.gaps ?? 0), 0)}
            </p>
            <p className="text-[11px] text-[var(--muted-foreground)] mt-0.5">open gaps</p>
          </div>
        </div>
      )}

      {/* Grade */}
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
    </div>
  )

  const artifactsContent = (
    <div className="flex flex-col gap-4">
      {result.artifacts.map((art, i) => (
        <TextureCard key={i} className="p-6">
          {/* Header */}
          <div className="flex items-start justify-between mb-5 gap-3">
            <div className="min-w-0">
              <span className="text-[10px] font-bold uppercase tracking-widest text-[var(--muted-foreground)]">
                {fmtLabel(art.type)}
              </span>
              <h3 className="font-semibold text-base mt-1 leading-snug">{art.target}</h3>
            </div>
            <div className="flex items-center gap-3 text-xs shrink-0">
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

          {/* Divider */}
          <div className="h-px bg-[var(--border)] mb-5" />

          {/* Content fields */}
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
                ) : typeof val === "string" && val.length > 200 ? (
                  <LongText text={val} />
                ) : (
                  <p className="text-sm leading-relaxed text-[var(--foreground)]">{String(val)}</p>
                )}
              </div>
            )
          })}
        </TextureCard>
      ))}
    </div>
  )

  const citationsContent = (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
      <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-3">
        Sources
      </p>
      <div className="flex flex-col gap-1.5">
        {result.citations.map((c, i) => (
          <div key={i} className="flex items-center gap-2 text-xs">
            <span className={c.boundary === "public" ? "badge-public" : "badge-private"}>
              {c.boundary === "public" ? <Globe className="w-2.5 h-2.5 inline" /> : <Lock className="w-2.5 h-2.5 inline" />}
              {" "}{c.boundary}
            </span>
            {c.url ? (
              <a href={c.url} target="_blank" rel="noopener noreferrer"
                 className="text-blue-500 hover:underline truncate">{c.label}</a>
            ) : (
              <span className="text-[var(--muted-foreground)]">{c.label}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  )

  // Build tab list conditionally
  const tabs = [
    { id: 0, label: "Overview", content: overviewContent },
    ...(result.artifacts.length > 0
      ? [{ id: 1, label: "Artifacts", content: artifactsContent }]
      : []),
    ...(result.citations.length > 0
      ? [{ id: result.artifacts.length > 0 ? 2 : 1, label: "Citations", content: citationsContent }]
      : []),
  ]

  return (
    <div className="flex flex-col gap-6">
      {/* Direction-aware tabs for result sections */}
      <DirectionAwareTabs tabs={tabs} />

      {/* Feedback bar + export — always visible below tabs */}
      <div className="flex items-center gap-3">
        <span className="text-xs text-[var(--muted-foreground)]">Was this useful?</span>
        <button onClick={() => sendFeedback(1)}
          className={`p-2 rounded-lg transition-all ${feedback === 1 ? "bg-green-100 text-green-600" : "hover:bg-[var(--muted)]"}`}>
          <ThumbsUp className="w-4 h-4" />
        </button>
        <button onClick={() => sendFeedback(-1)}
          className={`p-2 rounded-lg transition-all ${feedback === -1 ? "bg-red-100 text-red-600" : "hover:bg-[var(--muted)]"}`}>
          <ThumbsDown className="w-4 h-4" />
        </button>

        {/* vaul Drawer trigger for chat */}
        <Drawer.Root open={chatOpen} onOpenChange={setChatOpen}>
          <Drawer.Trigger asChild>
            <button
              className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border)]
                         text-xs font-semibold hover:bg-[var(--muted)] transition-colors">
              <MessageSquare className="w-3.5 h-3.5" /> Refine with chat
            </button>
          </Drawer.Trigger>
          <Drawer.Portal>
            <Drawer.Overlay className="fixed inset-0 bg-black/60 z-40 backdrop-blur-sm" />
            <Drawer.Content className="fixed bottom-0 left-0 right-0 z-50 flex flex-col
                                       bg-neutral-950 border-t border-neutral-800
                                       rounded-t-3xl max-h-[82vh]">
              <Drawer.Handle className="mx-auto mt-3 h-1 w-10 rounded-full bg-neutral-700" />

              {/* Header */}
              <div className="flex items-center gap-2 px-5 py-3 border-b border-neutral-800">
                <Sparkles className="w-4 h-4 text-violet-400" />
                <h3 className="text-sm font-semibold text-white">Refine Result</h3>
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-3">
                {chatHistory.length === 0 ? (
                  <div className="flex flex-col items-center gap-4 py-6">
                    <p className="text-xs text-neutral-500 text-center">
                      Ask a follow-up question about this research result.
                    </p>
                    {/* Suggestion chips */}
                    <div className="flex flex-wrap gap-2 justify-center">
                      {[
                        "What was the most important finding?",
                        "Summarise the key risks",
                        "What are the recommended next steps?",
                        "List the main sources used",
                      ].map((q) => (
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
                  </div>
                ) : (
                  chatHistory.map((m, i) => (
                    <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                      <div className={`text-sm px-4 py-2.5 rounded-2xl max-w-[80%] leading-relaxed
                        ${m.role === "user"
                          ? "bg-violet-600 text-white rounded-br-sm"
                          : "bg-neutral-800 text-neutral-100 rounded-bl-sm border border-neutral-700"}`}>
                        {m.content}
                      </div>
                    </div>
                  ))
                )}
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

              {/* Input */}
              <div className="p-4 border-t border-neutral-800 bg-neutral-950">
                <form onSubmit={sendChat} className="flex gap-2 items-end">
                  <input
                    value={chatMsg}
                    onChange={(e) => setChatMsg(e.target.value)}
                    placeholder="Ask a follow-up question…"
                    className="flex-1 rounded-xl border border-neutral-700 bg-neutral-900
                               px-4 py-2.5 text-sm text-white placeholder:text-neutral-500
                               outline-none focus:border-violet-500 transition-colors" />
                  <button
                    type="submit"
                    disabled={chatLoading || !chatMsg.trim()}
                    className="w-10 h-10 rounded-xl bg-violet-600 hover:bg-violet-500 disabled:opacity-40
                               flex items-center justify-center transition-colors shrink-0">
                    {chatLoading
                      ? <Loader2 className="w-4 h-4 text-white animate-spin" />
                      : <Send className="w-4 h-4 text-white" />}
                  </button>
                </form>
              </div>
            </Drawer.Content>
          </Drawer.Portal>
        </Drawer.Root>

        <a href={`/projects/${task.project_id}/tasks/${task.id}/export.html`}
           target="_blank" rel="noopener noreferrer"
           className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border)]
                      text-xs font-semibold hover:bg-[var(--muted)] transition-colors">
          <Download className="w-3.5 h-3.5" /> Export
        </a>
      </div>
    </div>
  )
}

// ── Main ─────────────────────────────────────────────────────────────────────
export default function TaskDetailPage({
  params,
}: { params: Promise<{ id: string; taskId: string }> }) {
  const { id: projectId, taskId } = use(params)

  const { data: task, mutate: refresh } = useSWR<Task>(
    `/api/projects/${projectId}/tasks/${taskId}`,
    fetcher,
    { refreshInterval: (data: Task | undefined) => data?.status === "running" ? 3000 : 0 }
  )

  const { data: project } = useSWR<Project>(
    `/api/projects/${projectId}`,
    fetcher
  )

  const [launching, setLaunching] = useState(false)

  async function runTask() {
    if (launching) return
    setLaunching(true)
    try {
      await tasksApi.run(projectId, taskId)
      // Optimistically flip to "running" so LiveRunPanel mounts immediately;
      // the 3-second SWR poller will reconcile with the real server state.
      refresh({ ...task, status: "running" } as Task, false)
    } catch {
      // Non-fatal: SWR will refetch on the next interval and show real status
    } finally {
      setLaunching(false)
    }
  }

  return (
    <div className="flex flex-col gap-6 max-w-4xl mx-auto">
      {/* Breadcrumb + header */}
      <div>
        <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)] mb-2">
          <Link href="/projects" className="hover:underline">Projects</Link>
          <span>/</span>
          <Link href={`/projects/${projectId}`} className="hover:underline">
            {project?.name ?? "Project"}
          </Link>
          <span>/</span>
          <span className="truncate">{task?.objective ?? "Task"}</span>
        </div>
        <div className="flex items-start justify-between gap-4">
          <GradientHeading size="sm" weight="bold">
            {task?.objective ?? "Loading…"}
          </GradientHeading>
          <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
            {task?.domain && (
              <span className="text-xs px-2 py-0.5 rounded bg-[var(--muted)] text-[var(--muted-foreground)] font-medium">
                {task.domain}
              </span>
            )}
            {task?.persona && (
              <span className="text-xs px-2 py-0.5 rounded bg-purple-100 text-purple-700 dark:bg-purple-900/20 dark:text-purple-300 font-medium">
                {task.persona}
              </span>
            )}
            {task && task.status !== "running" && (
              <button onClick={runTask} disabled={launching}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-black dark:bg-white
                           text-white dark:text-black text-sm font-semibold hover:opacity-80
                           disabled:opacity-50 transition-opacity">
                {launching
                  ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  : <Play className="w-3.5 h-3.5" />}
                {task.status === "done" ? "Re-run" : "Run"}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Content */}
      {task?.status === "running" && <LiveRunPanel projectId={projectId} taskId={taskId} />}
      {task?.status === "done" && task.result && <ResultPanel task={task} />}
      {task?.status === "failed" && (
        <div className="rounded-2xl border border-red-200 bg-red-50 dark:bg-red-900/10 p-6 text-center">
          <XCircle className="w-8 h-8 text-red-500 mx-auto mb-2" />
          <p className="font-semibold text-red-700 dark:text-red-400">Task failed</p>
          <button onClick={runTask}
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
