"use client"

import { use, useState } from "react"
import useSWR from "swr"
import Link from "next/link"
import { Drawer } from "vaul"
import { GradientHeading } from "@/components/ui/gradient-heading"
import { TerminalAnimation } from "@/components/ui/terminal-animation"
import { AnimatedNumber } from "@/components/ui/animated-number"
import { DirectionAwareTabs } from "@/components/ui/direction-aware-tabs"
import { type Task, type TaskStatus, type Project, tasks as tasksApi } from "@/lib/api"
import {
  Globe, Lock, AlertTriangle, ThumbsUp, ThumbsDown,
  Play, Download, MessageSquare, Loader2, CheckCircle2,
  XCircle, Clock, ChevronDown, ChevronUp,
} from "lucide-react"
import { fetcher } from "@/lib/fetcher"

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

  const overviewContent = (
    <div className="flex flex-col gap-4">
      {/* Summary */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6">
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-3">
          Summary
        </p>
        <p className="text-sm leading-relaxed">{result.summary}</p>
      </div>

      {/* Grade */}
      {result.grade && (
        <div className={`rounded-2xl border p-4 ${result.grade.passed
          ? "border-green-200 bg-green-50 dark:bg-green-900/10"
          : "border-red-200 bg-red-50 dark:bg-red-900/10"}`}>
          <div className="flex items-center gap-2">
            {result.grade.passed
              ? <CheckCircle2 className="w-4 h-4 text-green-600" />
              : <XCircle className="w-4 h-4 text-red-600" />}
            <span className="text-sm font-semibold">
              Quality check {result.grade.passed ? "passed" : "failed"}
              {result.grade.score !== undefined && ` · ${result.grade.score}/5`}
            </span>
          </div>
          {result.grade.hard_failures.length > 0 && (
            <ul className="mt-2 flex flex-col gap-1">
              {result.grade.hard_failures.map((f, i) => (
                <li key={i} className="text-xs text-red-600">· {f}</li>
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
        <div key={i} className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
                {art.type}
              </span>
              <h3 className="font-semibold text-base mt-0.5">{art.target}</h3>
            </div>
            <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
              <span className="flex items-center gap-1"><Globe className="w-3 h-3 text-blue-400" /> {art.public_count}</span>
              <span className="flex items-center gap-1"><Lock className="w-3 h-3 text-amber-400" /> {art.private_count}</span>
              {art.gaps > 0 && <span className="flex items-center gap-1 text-red-400"><AlertTriangle className="w-3 h-3" /> {art.gaps}</span>}
            </div>
          </div>

          {/* Render content fields */}
          {Object.entries(art.content).map(([key, val]) => {
            // Skip internal metadata keys
            if (key.startsWith("_")) return null
            if (val === null || val === undefined || val === "") return null
            if (Array.isArray(val) && val.length === 0) return null

            return (
              <div key={key} className="mb-4">
                <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-2">
                  {key.replace(/_/g, " ")}
                </p>
                {Array.isArray(val) ? (
                  <CollapsibleList items={val as unknown[]} />
                ) : typeof val === "object" ? (
                  <pre className="text-xs text-[var(--muted-foreground)] whitespace-pre-wrap bg-[var(--muted)] rounded-lg p-3 overflow-auto">
                    {JSON.stringify(val, null, 2)}
                  </pre>
                ) : typeof val === "string" && val.length > 200 ? (
                  <LongText text={val} />
                ) : (
                  <p className="text-sm leading-relaxed">{String(val)}</p>
                )}
              </div>
            )
          })}
        </div>
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
            <Drawer.Overlay className="fixed inset-0 bg-black/40 z-40" />
            <Drawer.Content className="fixed bottom-0 left-0 right-0 z-50 flex flex-col
                                       bg-[var(--card)] border-t border-[var(--border)]
                                       rounded-t-2xl max-h-[80vh]">
              <Drawer.Handle className="mx-auto mt-3 h-1.5 w-12 rounded-full bg-[var(--muted-foreground)]/30" />
              <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-3">
                <h3 className="font-semibold text-sm">Refine Result</h3>
                {chatHistory.map((m, i) => (
                  <div key={i} className={`text-sm p-3 rounded-xl ${m.role === "user"
                    ? "bg-black text-white dark:bg-white dark:text-black self-end max-w-xs ml-auto"
                    : "bg-[var(--muted)] max-w-sm"}`}>
                    {m.content}
                  </div>
                ))}
                {chatHistory.length === 0 && (
                  <p className="text-xs text-[var(--muted-foreground)] text-center py-4">
                    Ask a follow-up question about this result.
                  </p>
                )}
              </div>
              <div className="p-4 border-t border-[var(--border)] bg-[var(--card)]">
                <form onSubmit={sendChat} className="flex gap-2">
                  <input value={chatMsg} onChange={(e) => setChatMsg(e.target.value)}
                    placeholder="Ask a follow-up question…"
                    className="flex-1 rounded-lg border border-[var(--border)] bg-[var(--muted)]
                               px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white" />
                  <button type="submit" disabled={chatLoading || !chatMsg.trim()}
                    className="px-4 py-2 rounded-lg bg-black dark:bg-white text-white dark:text-black
                               text-sm font-semibold hover:opacity-80 disabled:opacity-40 transition-opacity">
                    {chatLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Send"}
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
