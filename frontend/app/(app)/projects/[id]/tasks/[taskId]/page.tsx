"use client"

import { use, useState } from "react"
import useSWR from "swr"
import Link from "next/link"
import { GradientHeading } from "@/components/ui/gradient-heading"
import { TerminalAnimation } from "@/components/ui/terminal-animation"
import { AnimatedNumber } from "@/components/ui/animated-number"
import { type Task, type TaskStatus, tasks as tasksApi } from "@/lib/api"
import {
  Globe, Lock, AlertTriangle, ThumbsUp, ThumbsDown,
  Play, Download, MessageSquare, Loader2, CheckCircle2,
  XCircle, Clock, ChevronDown, ChevronUp,
} from "lucide-react"

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
const fetcher = (url: string) => fetch(url, { credentials: "include" }).then((r) => r.json())

// ── Live status poller ──────────────────────────────────────────────────────
function LiveRunPanel({ projectId, taskId }: { projectId: string; taskId: string }) {
  const { data: status } = useSWR<TaskStatus>(
    `${API}/projects/${projectId}/tasks/${taskId}/status.json`,
    fetcher,
    { refreshInterval: 2000 }
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

// ── Result panel ────────────────────────────────────────────────────────────
function ResultPanel({ task }: { task: Task }) {
  const [chatOpen, setChatOpen] = useState(false)
  const [chatMsg, setChatMsg] = useState("")
  const [chatLoading, setChatLoading] = useState(false)
  const [feedback, setFeedback] = useState<1 | -1 | null>(null)
  const result = task.result
  if (!result) return null

  async function sendChat(e: React.FormEvent) {
    e.preventDefault()
    if (!chatMsg.trim()) return
    setChatLoading(true)
    await tasksApi.chat(task.project_id, task.id, chatMsg).catch(() => {})
    setChatMsg(""); setChatLoading(false)
  }

  async function sendFeedback(signal: 1 | -1) {
    setFeedback(signal)
    await tasksApi.feedback(task.project_id, task.id, signal).catch(() => {})
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Summary */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6">
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-3">
          Summary
        </p>
        <p className="text-sm leading-relaxed">{result.summary}</p>
      </div>

      {/* Artifacts */}
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
            if (val === null || val === undefined || val === "") return null
            if (Array.isArray(val) && val.length === 0) return null
            // Coerce an item to a display string: prefer .text/.name/.title, else JSON
            function itemText(item: unknown): string {
              if (typeof item === "string") return item
              if (typeof item === "object" && item !== null) {
                const o = item as Record<string, unknown>
                return String(o.text ?? o.name ?? o.title ?? o.action ?? JSON.stringify(item))
              }
              return String(item)
            }
            return (
              <div key={key} className="mb-4">
                <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-2">
                  {key.replace(/_/g, " ")}
                </p>
                {Array.isArray(val) ? (
                  <ul className="flex flex-col gap-1">
                    {(val as unknown[]).map((item, j) => (
                      <li key={j} className="text-sm flex items-start gap-2">
                        <span className="text-[var(--muted-foreground)] mt-0.5">·</span>
                        {itemText(item)}
                      </li>
                    ))}
                  </ul>
                ) : typeof val === "object" ? (
                  <pre className="text-xs text-[var(--muted-foreground)] whitespace-pre-wrap bg-[var(--muted)] rounded-lg p-3 overflow-auto">
                    {JSON.stringify(val, null, 2)}
                  </pre>
                ) : (
                  <p className="text-sm leading-relaxed">{String(val)}</p>
                )}
              </div>
            )
          })}
        </div>
      ))}

      {/* Citations */}
      {result.citations.length > 0 && (
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
      )}

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

      {/* Feedback + chat */}
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
        <button onClick={() => setChatOpen(true)}
          className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border)]
                     text-xs font-semibold hover:bg-[var(--muted)] transition-colors">
          <MessageSquare className="w-3.5 h-3.5" /> Refine with chat
        </button>
        <a href={`${API}/projects/${task.project_id}/tasks/${task.id}/export.html`}
           target="_blank" rel="noopener noreferrer"
           className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border)]
                      text-xs font-semibold hover:bg-[var(--muted)] transition-colors">
          <Download className="w-3.5 h-3.5" /> Export
        </a>
      </div>

      {/* Chat drawer */}
      {chatOpen && (
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
          <h3 className="font-semibold text-sm mb-3">Refine Result</h3>
          <div className="flex flex-col gap-3 mb-3 max-h-64 overflow-y-auto">
            {(task.chat ?? []).map((m, i) => (
              <div key={i} className={`text-sm p-3 rounded-xl ${m.role === "user"
                ? "bg-black text-white dark:bg-white dark:text-black self-end max-w-xs"
                : "bg-[var(--muted)] max-w-sm"}`}>
                {m.content}
              </div>
            ))}
          </div>
          <form onSubmit={sendChat} className="flex gap-2">
            <input value={chatMsg} onChange={(e) => setChatMsg(e.target.value)}
              placeholder="Ask a follow-up question…"
              className="flex-1 rounded-lg border border-[var(--border)] bg-[var(--muted)]
                         px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white" />
            <button type="submit" disabled={chatLoading || !chatMsg}
              className="px-4 py-2 rounded-lg bg-black dark:bg-white text-white dark:text-black
                         text-sm font-semibold hover:opacity-80 disabled:opacity-40 transition-opacity">
              {chatLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Send"}
            </button>
          </form>
        </div>
      )}
    </div>
  )
}

// ── Main ─────────────────────────────────────────────────────────────────────
export default function TaskDetailPage({
  params,
}: { params: Promise<{ id: string; taskId: string }> }) {
  const { id: projectId, taskId } = use(params)
  const { data: task, mutate: refresh } = useSWR<Task>(
    `${API}/api/projects/${projectId}/tasks/${taskId}`,
    fetcher,
    { refreshInterval: (data: Task | undefined) => data?.status === "running" ? 3000 : 0 }
  )

  async function runTask() {
    await tasksApi.run(projectId, taskId)
    refresh()
  }

  return (
    <div className="flex flex-col gap-6 max-w-4xl mx-auto">
      {/* Breadcrumb + header */}
      <div>
        <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)] mb-2">
          <Link href="/projects" className="hover:underline">Projects</Link>
          <span>/</span>
          <Link href={`/projects/${projectId}`} className="hover:underline">Project</Link>
          <span>/</span>
          <span className="truncate">{task?.objective ?? "Task"}</span>
        </div>
        <div className="flex items-start justify-between gap-4">
          <GradientHeading size="sm" weight="bold">
            {task?.objective ?? "Loading…"}
          </GradientHeading>
          <div className="flex items-center gap-2 shrink-0">
            {task?.domain && (
              <span className="text-xs px-2 py-0.5 rounded bg-[var(--muted)] text-[var(--muted-foreground)] font-medium">
                {task.domain}
              </span>
            )}
            {task && task.status !== "running" && task.status !== "done" && (
              <button onClick={runTask}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-black dark:bg-white
                           text-white dark:text-black text-sm font-semibold hover:opacity-80 transition-opacity">
                <Play className="w-3.5 h-3.5" /> Run
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
        </div>
      )}
    </div>
  )
}
