"use client"

import { use, useState } from "react"
import useSWR, { mutate } from "swr"
import Link from "next/link"
import { GradientHeading } from "@/components/ui/gradient-heading"
import { DirectionAwareTabs } from "@/components/ui/direction-aware-tabs"
import { AnimatedNumber } from "@/components/ui/animated-number"
import {
  type Project, type Task, type MemoryData, type KBData,
  type Artifact, tasks as tasksApi, kb as kbApi, projects as projectsApi,
} from "@/lib/api"
import {
  Plus, Play, Globe, Lock, AlertTriangle, Clock, CheckCircle2,
  XCircle, Loader2, BookOpen, Database, Zap, FileText, Brain,
} from "lucide-react"

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
const fetcher = (url: string) => fetch(url, { credentials: "include" }).then((r) => r.json())

// ── Status chip ────────────────────────────────────────────────────────────
function StatusBadge({ status }: { status: Task["status"] }) {
  const map: Record<Task["status"], { label: string; cls: string; icon: React.ReactNode }> = {
    created: { label: "Created",  cls: "bg-gray-100 text-gray-600",    icon: <Clock className="w-3 h-3" /> },
    planned: { label: "Planned",  cls: "bg-blue-100 text-blue-700",    icon: <CheckCircle2 className="w-3 h-3" /> },
    running: { label: "Running",  cls: "bg-amber-100 text-amber-700",  icon: <Loader2 className="w-3 h-3 animate-spin" /> },
    done:    { label: "Done",     cls: "bg-green-100 text-green-700",  icon: <CheckCircle2 className="w-3 h-3" /> },
    failed:  { label: "Failed",   cls: "bg-red-100 text-red-600",      icon: <XCircle className="w-3 h-3" /> },
  }
  const { label, cls, icon } = map[status]
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${cls}`}>
      {icon} {label}
    </span>
  )
}

// ── Task row ───────────────────────────────────────────────────────────────
function TaskRow({ task, projectId, onRun }: { task: Task; projectId: string; onRun: () => void }) {
  const [running, setRunning] = useState(false)

  async function handleRun(e: React.MouseEvent) {
    e.preventDefault()
    setRunning(true)
    await tasksApi.run(projectId, task.id).catch(() => {})
    onRun()
    setRunning(false)
  }

  return (
    <Link
      href={`/projects/${projectId}/tasks/${task.id}`}
      className="group flex items-center gap-3 p-3 rounded-xl border border-[var(--border)]
                 bg-[var(--card)] hover:shadow-sm hover:border-black/10 dark:hover:border-white/10
                 transition-all"
    >
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{task.objective}</p>
        <div className="flex items-center gap-2 mt-1">
          <span className="text-xs text-[var(--muted-foreground)]">{task.domain}</span>
          {task.persona && (
            <span className="text-xs text-[var(--muted-foreground)]">· {task.persona}</span>
          )}
        </div>
      </div>
      <StatusBadge status={task.status} />
      {(task.status === "created" || task.status === "planned" || task.status === "failed") && (
        <button
          onClick={handleRun}
          disabled={running}
          className="opacity-0 group-hover:opacity-100 flex items-center gap-1 px-2.5 py-1.5
                     rounded-lg bg-black dark:bg-white text-white dark:text-black text-xs font-semibold
                     hover:opacity-80 disabled:opacity-40 transition-all"
        >
          {running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
          Run
        </button>
      )}
    </Link>
  )
}

// ── Create task form ───────────────────────────────────────────────────────
function CreateTaskForm({ projectId, onCreated }: { projectId: string; onCreated: () => void }) {
  const [objective, setObjective] = useState("")
  const [domain, setDomain] = useState("market")
  const [loading, setLoading] = useState(false)

  const domains = ["market", "software", "finance", "academic", "product_research", "travel", "nutrition", "govt_proposal"]

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    await fetch(`${API}/api/projects/${projectId}/tasks`, {
      method: "POST", credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ objective, domain }),
    })
    onCreated()
    setObjective(""); setLoading(false)
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <div>
        <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Research Objective *</label>
        <textarea
          value={objective} onChange={(e) => setObjective(e.target.value)} required rows={2}
          placeholder="What competitive advantages does Acme Corp have in the BFSI sector?"
          className="w-full rounded-lg border border-[var(--border)] bg-[var(--muted)]
                     px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white resize-none"
        />
      </div>
      <div>
        <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Domain</label>
        <select
          value={domain} onChange={(e) => setDomain(e.target.value)}
          className="w-full rounded-lg border border-[var(--border)] bg-[var(--muted)]
                     px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white"
        >
          {domains.map((d) => (
            <option key={d} value={d}>{d.replace("_", " ")}</option>
          ))}
        </select>
      </div>
      <button
        type="submit" disabled={loading || !objective}
        className="rounded-lg bg-black dark:bg-white text-white dark:text-black
                   py-2 text-sm font-semibold hover:opacity-80 disabled:opacity-40 transition-opacity"
      >
        {loading ? "Creating…" : "Create Task"}
      </button>
    </form>
  )
}

// ── KB tab ──────────────────────────────────────────────────────────────────
function KBTab({ projectId }: { projectId: string }) {
  const { data, mutate: refresh } = useSWR<KBData>(`${API}/api/projects/${projectId}/kb`, fetcher)
  const [url, setUrl] = useState("")
  const [adding, setAdding] = useState(false)

  async function addSource(e: React.FormEvent) {
    e.preventDefault()
    setAdding(true)
    await kbApi.addSource(projectId, url).catch(() => {})
    setUrl(""); refresh(); setAdding(false)
  }

  const statusIcon = (s: string) => ({
    indexed:  <CheckCircle2 className="w-3 h-3 text-green-500" />,
    crawling: <Loader2 className="w-3 h-3 text-blue-500 animate-spin" />,
    failed:   <XCircle className="w-3 h-3 text-red-500" />,
    pending:  <Clock className="w-3 h-3 text-gray-400" />,
  }[s] ?? null)

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={addSource} className="flex gap-2">
        <input
          value={url} onChange={(e) => setUrl(e.target.value)} required
          placeholder="https://docs.example.com or paste article URL"
          className="flex-1 rounded-lg border border-[var(--border)] bg-[var(--muted)]
                     px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white"
        />
        <button
          type="submit" disabled={adding || !url}
          className="px-4 py-2 rounded-lg bg-black dark:bg-white text-white dark:text-black
                     text-sm font-semibold hover:opacity-80 disabled:opacity-40 transition-opacity"
        >
          {adding ? "Adding…" : "Add"}
        </button>
      </form>
      <div className="flex flex-col gap-2">
        {(data?.sources ?? []).map((s) => (
          <div key={s.id} className="flex items-center gap-3 p-3 rounded-xl border border-[var(--border)] bg-[var(--card)]">
            {statusIcon(s.status)}
            <span className="text-xs truncate flex-1 font-mono text-[var(--muted-foreground)]">{s.url}</span>
            <span className="text-xs text-[var(--muted-foreground)] shrink-0">{s.chunk_count} chunks</span>
          </div>
        ))}
        {(data?.sources ?? []).length === 0 && (
          <p className="text-sm text-[var(--muted-foreground)] text-center py-6">
            No sources yet — add a URL above.
          </p>
        )}
      </div>
    </div>
  )
}

// ── Memory tab ──────────────────────────────────────────────────────────────
function MemoryTab({ projectId }: { projectId: string }) {
  const { data } = useSWR<MemoryData>(`${API}/api/projects/${projectId}/memory`, fetcher)
  const [tab, setTab] = useState<"episodes" | "facts">("episodes")

  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-1 p-1 rounded-lg bg-[var(--muted)] w-fit">
        {(["episodes", "facts"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all capitalize
              ${tab === t ? "bg-[var(--card)] shadow-sm" : "text-[var(--muted-foreground)]"}`}>
            {t}
          </button>
        ))}
      </div>

      {tab === "episodes" && (
        <div className="flex flex-col gap-2">
          {(data?.episodes ?? []).map((ep) => (
            <div key={ep.id} className="p-3 rounded-xl border border-[var(--border)] bg-[var(--card)]">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{ep.target || ep.entity}</span>
                <span className="text-xs text-[var(--muted-foreground)]">
                  {new Date(ep.created_at).toLocaleDateString()}
                </span>
              </div>
              <div className="flex gap-3 mt-1.5 text-xs text-[var(--muted-foreground)]">
                <span className="flex items-center gap-1"><Globe className="w-3 h-3 text-blue-400" /> {ep.public}</span>
                <span className="flex items-center gap-1"><Lock className="w-3 h-3 text-amber-400" /> {ep.private}</span>
                {ep.gaps > 0 && <span className="flex items-center gap-1 text-red-400"><AlertTriangle className="w-3 h-3" /> {ep.gaps}</span>}
              </div>
            </div>
          ))}
          {(data?.episodes ?? []).length === 0 && (
            <p className="text-sm text-[var(--muted-foreground)] text-center py-6">No research runs yet.</p>
          )}
        </div>
      )}

      {tab === "facts" && (
        <div className="flex flex-col gap-2">
          {(data?.facts ?? []).map((f) => (
            <div key={f.id}
              className={`p-3 rounded-xl border border-[var(--border)] bg-[var(--card)]
                          ${f.boundary === "public" ? "finding-public" : "finding-private"}`}>
              <p className="text-xs">{f.content}</p>
              <div className="flex items-center gap-2 mt-1.5">
                <span className={f.boundary === "public" ? "badge-public" : "badge-private"}>
                  {f.boundary}
                </span>
                <span className="text-xs text-[var(--muted-foreground)]">{f.source_label}</span>
              </div>
            </div>
          ))}
          {(data?.facts ?? []).length === 0 && (
            <p className="text-sm text-[var(--muted-foreground)] text-center py-6">No semantic facts yet.</p>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────
export default function ProjectDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const [showTaskForm, setShowTaskForm] = useState(false)

  const { data: project } = useSWR<Project>(`${API}/api/projects/${id}`, fetcher)
  const { data: taskList, mutate: refreshTasks } = useSWR<Task[]>(`${API}/api/projects/${id}/tasks`, fetcher)

  const tasksContent = (
    <div className="flex flex-col gap-3">
      <div className="flex justify-between items-center">
        <span className="text-xs text-[var(--muted-foreground)]">
          {(taskList ?? []).length} task{(taskList ?? []).length !== 1 ? "s" : ""}
        </span>
        <button
          onClick={() => setShowTaskForm(!showTaskForm)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-black dark:bg-white
                     text-white dark:text-black text-xs font-semibold hover:opacity-80 transition-opacity"
        >
          <Plus className="w-3.5 h-3.5" /> New Task
        </button>
      </div>
      {showTaskForm && (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
          <CreateTaskForm projectId={id} onCreated={() => { refreshTasks(); setShowTaskForm(false) }} />
        </div>
      )}
      {(taskList ?? []).map((t) => (
        <TaskRow key={t.id} task={t} projectId={id} onRun={refreshTasks} />
      ))}
      {(taskList ?? []).length === 0 && !showTaskForm && (
        <p className="text-sm text-[var(--muted-foreground)] text-center py-8">
          No tasks yet. Create one to start researching.
        </p>
      )}
    </div>
  )

  return (
    <div className="flex flex-col gap-6 max-w-5xl mx-auto">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
            <Link href="/projects" className="hover:underline">Projects</Link>
            <span>/</span>
            <span>{project?.name ?? "…"}</span>
          </div>
          <GradientHeading size="md" weight="bold">
            {project?.name ?? "Loading…"}
          </GradientHeading>
          {project?.description && (
            <p className="text-sm text-[var(--muted-foreground)]">{project.description}</p>
          )}
          {project?.website && (
            <a href={project.website} target="_blank" rel="noopener noreferrer"
               className="flex items-center gap-1 text-xs text-blue-500 hover:underline w-fit">
              <Globe className="w-3 h-3" />
              {project.website.replace(/^https?:\/\//, "")}
            </a>
          )}
        </div>
        <div className="flex gap-2 shrink-0">
          <div className="flex flex-col items-center p-3 rounded-xl border border-[var(--border)] bg-[var(--card)] min-w-[72px]">
            <AnimatedNumber value={taskList?.length ?? 0} className="text-xl font-bold" />
            <span className="text-xs text-[var(--muted-foreground)]">tasks</span>
          </div>
        </div>
      </div>

      <DirectionAwareTabs
        tabs={[
          { id: 0, label: "Tasks",          content: tasksContent },
          { id: 1, label: "Knowledge Base", content: <KBTab projectId={id} /> },
          { id: 2, label: "Memory",         content: <MemoryTab projectId={id} /> },
          { id: 3, label: "Artifacts",      content: (
            <p className="text-sm text-[var(--muted-foreground)] py-6 text-center">
              Artifacts from all tasks in this project appear here after runs complete.
            </p>
          )},
        ]}
      />
    </div>
  )
}
