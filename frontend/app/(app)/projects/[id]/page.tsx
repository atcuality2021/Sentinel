"use client"

import { use, useState, useEffect, Suspense } from "react"
import { useSearchParams, useRouter } from "next/navigation"
import useSWR from "swr"
import Link from "next/link"
import { AnimatePresence, motion } from "motion/react"
import { GradientHeading } from "@/components/ui/gradient-heading"
import { AnimatedNumber } from "@/components/ui/animated-number"
import { useToast } from "@/components/ui/toast"
import {
  type Project, type Task, type MemoryData, type KBData, type KBSource, type KBSearchResult, type KBChunk, type Artifact,
  tasks as tasksApi, kb as kbApi, memory as memoryApi,
} from "@/lib/api"
import {
  Plus, Play, Globe, Lock, AlertTriangle, Clock, CheckCircle2,
  XCircle, Loader2, BookOpen, FileText, Search,
  Trash2, RefreshCw, Pencil, Check, ChevronDown, ChevronUp, Clipboard,
  X, Target, Zap, BarChart3, Brain, ArrowRight, Building2, Library,
  PlayCircle, Users, Film, File, Layers, FileImage,
} from "lucide-react"
import { fetcher } from "@/lib/fetcher"

// ── Domain display labels ──────────────────────────────────────────────────────
const DOMAIN_LABELS: Record<string, string> = {
  market:           "Market Intelligence",
  software:         "Software Analysis",
  finance:          "Financial Research",
  academic:         "Academic Research",
  product_research: "Product Research",
  travel:           "Travel Planning",
  nutrition:        "Nutrition & Health",
  govt_proposal:    "Government Proposal",
}

const DOMAIN_ICONS: Record<string, React.ReactNode> = {
  market:           <BarChart3 className="w-3 h-3" />,
  software:         <Zap className="w-3 h-3" />,
  finance:          <BarChart3 className="w-3 h-3" />,
  academic:         <BookOpen className="w-3 h-3" />,
  product_research: <Target className="w-3 h-3" />,
  travel:           <Globe className="w-3 h-3" />,
  nutrition:        <Brain className="w-3 h-3" />,
  govt_proposal:    <FileText className="w-3 h-3" />,
}

// ── Tab definitions ────────────────────────────────────────────────────────────
const TABS = [
  { key: "tasks",     label: "Tasks" },
  { key: "kb",        label: "Knowledge Base" },
  { key: "memory",    label: "Memory" },
  { key: "artifacts", label: "Artifacts" },
] as const
type TabKey = (typeof TABS)[number]["key"]

// ── Tab bar (controlled, URL-driven) ──────────────────────────────────────────
function TabBar({ active, onChange }: { active: TabKey; onChange: (t: TabKey) => void }) {
  return (
    <div className="flex gap-1 p-1 rounded-full bg-neutral-800 w-fit">
      {TABS.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={`relative px-4 py-1.5 rounded-full text-xs sm:text-sm font-medium transition-colors
            ${active === t.key ? "text-white" : "text-neutral-400 hover:text-neutral-200"}`}
        >
          {active === t.key && (
            <motion.span
              layoutId="project-tab-bubble"
              className="absolute inset-0 z-0 bg-neutral-700 rounded-full border border-white/10"
              transition={{ type: "spring", bounce: 0.19, duration: 0.4 }}
            />
          )}
          <span className="relative z-10">{t.label}</span>
        </button>
      ))}
    </div>
  )
}

// ── Status badge ───────────────────────────────────────────────────────────────
function StatusBadge({ status }: { status: Task["status"] }) {
  const map: Record<Task["status"], { label: string; cls: string; icon: React.ReactNode }> = {
    created: { label: "Created",  cls: "bg-gray-700 text-gray-300",      icon: <Clock className="w-3 h-3" /> },
    planned: { label: "Planned",  cls: "bg-blue-900/70 text-blue-300",   icon: <CheckCircle2 className="w-3 h-3" /> },
    running: { label: "Running",  cls: "bg-amber-900/70 text-amber-300", icon: <Loader2 className="w-3 h-3 animate-spin" /> },
    done:    { label: "Done",     cls: "bg-green-900/70 text-green-300", icon: <CheckCircle2 className="w-3 h-3" /> },
    failed:  { label: "Failed",   cls: "bg-red-900/70 text-red-400",     icon: <XCircle className="w-3 h-3" /> },
  }
  const { label, cls, icon } = map[status]
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold ${cls}`}>
      {icon} {label}
    </span>
  )
}

// ── Task card ──────────────────────────────────────────────────────────────────
function TaskCard({ task, projectId, onRun, onDelete }: {
  task: Task; projectId: string; onRun: () => void; onDelete: () => void
}) {
  const { toast } = useToast()
  const [running, setRunning] = useState(false)
  const [deleting, setDeleting] = useState(false)

  async function handleRun(e: React.MouseEvent) {
    e.preventDefault()
    setRunning(true)
    await tasksApi.run(projectId, task.id).catch((err) => toast(err?.message ?? "Run failed", "error"))
    toast("Research started", "success")
    onRun()
    setRunning(false)
  }

  async function handleDelete(e: React.MouseEvent) {
    e.preventDefault(); e.stopPropagation()
    if (!confirm(`Delete "${task.objective}"?`)) return
    setDeleting(true)
    await tasksApi.delete(projectId, task.id).catch((err) => toast(err?.message ?? "Delete failed", "error"))
    toast("Task deleted", "success")
    onDelete()
    setDeleting(false)
  }

  const domainLabel = DOMAIN_LABELS[task.domain] ?? task.domain
  const domainIcon  = DOMAIN_ICONS[task.domain]
  const date = new Date(task.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })

  return (
    <Link
      href={`/projects/${projectId}/tasks/${task.id}`}
      className="group flex items-start gap-4 p-4 rounded-xl border border-[var(--border)]
                 bg-[var(--card)] hover:border-white/20 hover:bg-white/[0.03] transition-all"
    >
      {/* Domain icon pill */}
      <div className="mt-0.5 w-8 h-8 rounded-lg bg-[var(--muted)] border border-[var(--border)]
                      flex items-center justify-center text-[var(--muted-foreground)] shrink-0">
        {domainIcon ?? <FileText className="w-3 h-3" />}
      </div>

      {/* Main content */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium leading-snug line-clamp-2">{task.objective}</p>
        <div className="flex flex-wrap items-center gap-2 mt-2">
          <span className="text-[11px] text-[var(--muted-foreground)] bg-[var(--muted)] px-2 py-0.5 rounded-md">
            {domainLabel}
          </span>
          {task.persona && (
            <span className="text-[11px] text-purple-400 bg-purple-900/20 px-2 py-0.5 rounded-md capitalize">
              {task.persona}
            </span>
          )}
          <span className="text-[11px] text-[var(--muted-foreground)]">{date}</span>
        </div>

        {/* Result preview for done tasks — skip backend log-style strings */}
        {task.status === "done" && task.result?.summary &&
          !/^produced \d+ artifact/i.test(task.result.summary) && (
          <p className="mt-2 text-xs text-[var(--muted-foreground)] line-clamp-2 leading-relaxed">
            {task.result.summary}
          </p>
        )}

        {/* Finding counts — only render non-zero values */}
        {task.status === "done" && task.result && (() => {
          const pub  = task.result.artifacts?.reduce((s, a) => s + (a.public_count  ?? 0), 0) ?? 0
          const priv = task.result.artifacts?.reduce((s, a) => s + (a.private_count ?? 0), 0) ?? 0
          const cit  = task.result.citations?.length ?? 0
          const art  = task.result.artifacts?.length ?? 0
          if (pub === 0 && priv === 0 && cit === 0 && art === 0) return null
          return (
            <div className="flex items-center gap-3 mt-2">
              {pub > 0 && (
                <span className="flex items-center gap-1 text-[11px] text-blue-400">
                  <Globe className="w-3 h-3" /> {pub} public
                </span>
              )}
              {priv > 0 && (
                <span className="flex items-center gap-1 text-[11px] text-amber-400">
                  <Lock className="w-3 h-3" /> {priv} private
                </span>
              )}
              {cit > 0 && (
                <span className="flex items-center gap-1 text-[11px] text-[var(--muted-foreground)]">
                  <BookOpen className="w-3 h-3" /> {cit} citations
                </span>
              )}
              {art > 0 && pub === 0 && priv === 0 && (
                <span className="flex items-center gap-1 text-[11px] text-[var(--muted-foreground)]">
                  <FileText className="w-3 h-3" /> {art} artifact{art !== 1 ? "s" : ""}
                </span>
              )}
            </div>
          )
        })()}
      </div>

      {/* Right side: status + actions */}
      <div className="flex flex-col items-end gap-2 shrink-0">
        <StatusBadge status={task.status} />
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {(task.status === "created" || task.status === "planned" || task.status === "failed") && (
            <button onClick={handleRun} disabled={running}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white text-black text-xs font-semibold
                         hover:opacity-80 disabled:opacity-40 transition-all">
              {running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
              Run
            </button>
          )}
          <button onClick={handleDelete} disabled={deleting}
            className="p-1.5 rounded-lg text-red-400 hover:bg-red-900/30 transition-all disabled:opacity-40">
            {deleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
          </button>
        </div>
        {task.status === "done" && (
          <span className="flex items-center gap-1 text-[10px] text-[var(--muted-foreground)] opacity-0 group-hover:opacity-100 transition-opacity">
            View results <ArrowRight className="w-3 h-3" />
          </span>
        )}
      </div>
    </Link>
  )
}

// ── New Task form ──────────────────────────────────────────────────────────────
// Designed to feel like commissioning intelligence work, not filling a to-do item
function NewTaskForm({ projectId, onCreated, onCancel }: {
  projectId: string; onCreated: () => void; onCancel: () => void
}) {
  const { toast } = useToast()
  const [objective, setObjective] = useState("")
  const [domain, setDomain] = useState("market")
  const [persona, setPersona] = useState("auto")
  const [target, setTarget] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const domains = [
    { value: "market",           label: "Market Intelligence" },
    { value: "software",         label: "Software Analysis" },
    { value: "finance",          label: "Financial Research" },
    { value: "academic",         label: "Academic Research" },
    { value: "product_research", label: "Product Research" },
    { value: "travel",           label: "Travel Planning" },
    { value: "nutrition",        label: "Nutrition & Health" },
    { value: "govt_proposal",    label: "Government Proposal" },
  ]

  const personaOptions = [
    { value: "auto",       label: "Auto-select (recommended)" },
    { value: "enterprise", label: "Enterprise Analyst" },
    { value: "developer",  label: "Developer" },
    { value: "consumer",   label: "Consumer" },
    { value: "student",    label: "Student" },
    { value: "doctor",     label: "Doctor" },
    { value: "nurse",      label: "Nurse" },
  ]

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); setError(null)
    const fullObjective = target.trim()
      ? `${objective.trim()} [Target: ${target.trim()}]`
      : objective.trim()
    try {
      await tasksApi.create(projectId, {
        objective: fullObjective,
        domain,
        persona: persona === "auto" ? undefined : persona,
      })
      toast("Research commissioned — planning in progress", "success")
      onCreated()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to create task"
      setError(msg); toast(msg, "error")
    } finally {
      setLoading(false)
    }
  }

  const fieldCls = "w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2.5 text-sm outline-none focus:ring-1 focus:ring-white/20 transition-colors"

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.18 }}
      className="rounded-2xl border border-white/10 bg-white/[0.04] backdrop-blur-sm overflow-hidden mb-3"
    >
      {/* Form header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-white/8">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-blue-500/20 flex items-center justify-center">
            <Search className="w-3.5 h-3.5 text-blue-400" />
          </div>
          <span className="text-sm font-semibold">Commission Research</span>
        </div>
        <button onClick={onCancel} className="p-1.5 rounded-lg hover:bg-white/8 text-[var(--muted-foreground)] transition-colors">
          <X className="w-4 h-4" />
        </button>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4 p-5">
        {/* Research question */}
        <div>
          <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-2 uppercase tracking-wide">
            Research Question *
          </label>
          <textarea
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            required
            rows={3}
            placeholder="What do you want to know? e.g. &quot;Analyse the competitive landscape for AI-powered legal document review tools in the US market&quot;"
            className={`${fieldCls} resize-none`}
          />
        </div>

        {/* Target entity */}
        <div>
          <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-2 uppercase tracking-wide">
            Target Entity <span className="normal-case font-normal text-[var(--muted-foreground)]/70">(company, person, topic)</span>
          </label>
          <input
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder="e.g. Harvey AI, Salesforce, BFSI sector India"
            className={fieldCls}
          />
        </div>

        {/* Domain + Persona row */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-2 uppercase tracking-wide">
              Research Type
            </label>
            <select value={domain} onChange={(e) => setDomain(e.target.value)} className={fieldCls}>
              {domains.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-2 uppercase tracking-wide">
              Analyst Persona
            </label>
            <select value={persona} onChange={(e) => setPersona(e.target.value)} className={fieldCls}>
              {personaOptions.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </div>
        </div>

        {error && <p className="text-xs text-red-400 bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>}

        {/* Submit */}
        <div className="flex items-center justify-between pt-1">
          <p className="text-xs text-[var(--muted-foreground)]">
            Sentinel will plan, research, and synthesize findings automatically.
          </p>
          <button
            type="submit"
            disabled={loading || !objective.trim()}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white text-black text-sm font-semibold
                       hover:opacity-90 disabled:opacity-40 transition-opacity shrink-0"
          >
            {loading
              ? <><Loader2 className="w-4 h-4 animate-spin" /> Planning…</>
              : <><Zap className="w-4 h-4" /> Start Research</>
            }
          </button>
        </div>
      </form>
    </motion.div>
  )
}

// ── Tasks tab ──────────────────────────────────────────────────────────────────
function TasksTab({ projectId }: { projectId: string }) {
  const { data: taskList, mutate: refreshTasks } = useSWR<Task[]>(
    `/api/projects/${projectId}/tasks`,
    fetcher,
    { refreshInterval: (tasks) => tasks?.some(t => t.status === "running") ? 3000 : 0 }
  )
  const [showForm, setShowForm] = useState(false)

  const grouped = {
    running: (taskList ?? []).filter(t => t.status === "running"),
    planned: (taskList ?? []).filter(t => t.status === "planned" || t.status === "created"),
    done:    (taskList ?? []).filter(t => t.status === "done"),
    failed:  (taskList ?? []).filter(t => t.status === "failed"),
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Action bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xs text-[var(--muted-foreground)]">{(taskList ?? []).length} task{(taskList ?? []).length !== 1 ? "s" : ""}</span>
          {grouped.running.length > 0 && (
            <span className="flex items-center gap-1 text-xs text-amber-400 font-medium">
              <Loader2 className="w-3 h-3 animate-spin" /> {grouped.running.length} running
            </span>
          )}
          {grouped.done.length > 0 && (
            <span className="flex items-center gap-1 text-xs text-green-400">
              <CheckCircle2 className="w-3 h-3" /> {grouped.done.length} done
            </span>
          )}
        </div>
        {!showForm && (
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white text-black
                       text-xs font-semibold hover:opacity-80 transition-opacity"
          >
            <Plus className="w-3.5 h-3.5" /> New Task
          </button>
        )}
      </div>

      {/* New task form — floats above the list */}
      <AnimatePresence>
        {showForm && (
          <NewTaskForm
            projectId={projectId}
            onCreated={() => { setShowForm(false); refreshTasks() }}
            onCancel={() => setShowForm(false)}
          />
        )}
      </AnimatePresence>

      {/* Running tasks first */}
      {grouped.running.length > 0 && (
        <div className="flex flex-col gap-2">
          {grouped.running.map((t) => (
            <TaskCard key={t.id} task={t} projectId={projectId} onRun={() => refreshTasks()} onDelete={() => refreshTasks()} />
          ))}
        </div>
      )}

      {/* All other tasks */}
      {[...grouped.planned, ...grouped.done, ...grouped.failed].length > 0 && (
        <div className="flex flex-col gap-2">
          {[...grouped.planned, ...grouped.done, ...grouped.failed].map((t) => (
            <TaskCard key={t.id} task={t} projectId={projectId} onRun={() => refreshTasks()} onDelete={() => refreshTasks()} />
          ))}
        </div>
      )}

      {/* Next-steps strip — shown when tasks exist but more can be done */}
      {(taskList ?? []).length > 0 && !showForm && (
        <div className="mt-2 grid grid-cols-3 gap-3">
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-2 p-3 rounded-xl border border-dashed border-white/10
                       bg-white/[0.02] hover:bg-white/[0.05] hover:border-white/20 transition-all text-left group"
          >
            <div className="w-7 h-7 rounded-lg bg-blue-500/15 flex items-center justify-center shrink-0">
              <Plus className="w-3.5 h-3.5 text-blue-400" />
            </div>
            <div>
              <p className="text-xs font-semibold group-hover:text-white transition-colors">Commission research</p>
              <p className="text-[10px] text-[var(--muted-foreground)] mt-0.5">Add another task</p>
            </div>
          </button>

          <Link
            href={`/projects/${projectId}?tab=kb`}
            className="flex items-center gap-2 p-3 rounded-xl border border-dashed border-white/10
                       bg-white/[0.02] hover:bg-white/[0.05] hover:border-white/20 transition-all group"
          >
            <div className="w-7 h-7 rounded-lg bg-green-500/15 flex items-center justify-center shrink-0">
              <BookOpen className="w-3.5 h-3.5 text-green-400" />
            </div>
            <div>
              <p className="text-xs font-semibold group-hover:text-white transition-colors">Knowledge base</p>
              <p className="text-[10px] text-[var(--muted-foreground)] mt-0.5">Add source URLs</p>
            </div>
          </Link>

          <Link
            href={`/projects/${projectId}?tab=memory`}
            className="flex items-center gap-2 p-3 rounded-xl border border-dashed border-white/10
                       bg-white/[0.02] hover:bg-white/[0.05] hover:border-white/20 transition-all group"
          >
            <div className="w-7 h-7 rounded-lg bg-purple-500/15 flex items-center justify-center shrink-0">
              <Brain className="w-3.5 h-3.5 text-purple-400" />
            </div>
            <div>
              <p className="text-xs font-semibold group-hover:text-white transition-colors">Explore memory</p>
              <p className="text-[10px] text-[var(--muted-foreground)] mt-0.5">Episodes & signals</p>
            </div>
          </Link>
        </div>
      )}

      {/* Empty state */}
      {(taskList ?? []).length === 0 && !showForm && (
        <div className="flex flex-col items-center py-20 gap-4 text-center">
          <div className="relative">
            <div className="w-16 h-16 rounded-2xl border border-[var(--border)] bg-[var(--card)] flex items-center justify-center">
              <Brain className="w-7 h-7 text-[var(--muted-foreground)]" />
            </div>
            <div className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-blue-500/20 border border-blue-500/40 flex items-center justify-center">
              <Plus className="w-3 h-3 text-blue-400" />
            </div>
          </div>
          <div>
            <p className="text-sm font-semibold">No intelligence tasks yet</p>
            <p className="text-xs text-[var(--muted-foreground)] mt-1 max-w-xs">
              Commission your first research task. Sentinel will autonomously plan, execute, and synthesize findings.
            </p>
          </div>
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white text-black text-sm font-semibold hover:opacity-80 transition-opacity"
          >
            <Zap className="w-4 h-4" /> Commission Research
          </button>
        </div>
      )}
    </div>
  )
}

// ── KB types ───────────────────────────────────────────────────────────────────
type KBCategory   = "context" | "reference" | "subject"
type KBSourceType = "website" | "youtube" | "pdf" | "slides" | "document" | "social" | "business" | "image" | "video"

const KB_CATS: Record<KBCategory, { label: string; icon: React.ReactNode; badge: string; border: string; desc: string }> = {
  context: {
    label: "Your Knowledge",  icon: <Building2 className="w-3 h-3" />,
    badge: "bg-blue-500/15 text-blue-400 border-blue-500/25",
    border: "border-blue-500/20",
    desc: "About you — org docs, SOPs, product info, company constraints.",
  },
  reference: {
    label: "Reference Material", icon: <Library className="w-3 h-3" />,
    badge: "bg-purple-500/15 text-purple-400 border-purple-500/25",
    border: "border-purple-500/20",
    desc: "Domain background — textbooks, syllabi, market reports, guidelines.",
  },
  subject: {
    label: "Research Subject", icon: <Target className="w-3 h-3" />,
    badge: "bg-amber-500/15 text-amber-400 border-amber-500/25",
    border: "border-amber-500/20",
    desc: "About what you're analyzing — competitor sites, student papers, filings.",
  },
}

const KB_SOURCE_TYPES: Record<KBSourceType, { icon: React.ReactNode; label: string; hint: string; color: string }> = {
  website:  { icon: <Globe className="w-4 h-4" />,        label: "Website",       hint: "https://example.com",                            color: "text-sky-400 bg-sky-500/10" },
  youtube:  { icon: <PlayCircle className="w-4 h-4" />,   label: "YouTube",       hint: "youtube.com/watch?v=...",                        color: "text-red-400 bg-red-500/10" },
  pdf:      { icon: <FileText className="w-4 h-4" />,     label: "PDF",           hint: "Direct PDF URL or Google Drive / Dropbox link",  color: "text-orange-400 bg-orange-500/10" },
  slides:   { icon: <Layers className="w-4 h-4" />,       label: "Slides / PPT",  hint: "Google Slides, SlideShare, or hosted PPT URL",   color: "text-yellow-400 bg-yellow-500/10" },
  document: { icon: <File className="w-4 h-4" />,         label: "Word / Doc",    hint: "Google Docs, Notion, or hosted .docx URL",       color: "text-blue-400 bg-blue-500/10" },
  social:   { icon: <Users className="w-4 h-4" />,        label: "Social",        hint: "LinkedIn, Twitter/X, or Instagram profile URL",  color: "text-pink-400 bg-pink-500/10" },
  business: { icon: <Building2 className="w-4 h-4" />,    label: "Business",      hint: "Google Business, Crunchbase, or company URL",    color: "text-emerald-400 bg-emerald-500/10" },
  image:    { icon: <FileImage className="w-4 h-4" />,    label: "Image",         hint: "Direct image URL or hosted image link",          color: "text-violet-400 bg-violet-500/10" },
  video:    { icon: <Film className="w-4 h-4" />,         label: "Video",         hint: "Vimeo, Loom, or other hosted video URL",         color: "text-teal-400 bg-teal-500/10" },
}

interface KBMeta { cat: KBCategory; type: KBSourceType }

function readKBMeta(url: string): KBMeta {
  try {
    const raw = localStorage.getItem(`kb_meta::${url}`)
    if (raw) return JSON.parse(raw) as KBMeta
  } catch { /* storage unavailable */ }
  // Auto-detect from URL pattern
  if (url.includes("youtube.com") || url.includes("youtu.be")) return { cat: "reference", type: "youtube" }
  if (url.includes("linkedin.com") || url.includes("twitter.com") || url.includes("x.com") || url.includes("instagram.com"))
    return { cat: "reference", type: "social" }
  if (url.endsWith(".pdf")) return { cat: "reference", type: "pdf" }
  if (url.endsWith(".ppt") || url.endsWith(".pptx") || url.includes("slides.google") || url.includes("slideshare"))
    return { cat: "reference", type: "slides" }
  if (url.startsWith("artifact://")) return { cat: "reference", type: "document" }
  return { cat: "reference", type: "website" }
}

function writeKBMeta(url: string, meta: KBMeta) {
  try { localStorage.setItem(`kb_meta::${url}`, JSON.stringify(meta)) } catch { /* storage unavailable */ }
}

// ── Add source form ────────────────────────────────────────────────────────────
function AddSourceForm({ projectId, defaultCat = "reference", onAdded, onCancel }: {
  projectId: string; defaultCat?: KBCategory; onAdded: () => void; onCancel: () => void
}) {
  const { toast } = useToast()
  const [url, setUrl] = useState("")
  const [cat, setCat] = useState<KBCategory>(defaultCat)
  const [srcType, setSrcType] = useState<KBSourceType>("website")
  const [loading, setLoading] = useState(false)

  async function handlePaste() {
    try { setUrl((await navigator.clipboard.readText()).trim()) } catch { /* clipboard denied */ }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!url.trim()) return
    setLoading(true)
    try {
      await kbApi.addSource(projectId, url.trim())
      writeKBMeta(url.trim(), { cat, type: srcType })
      toast(`Added to ${KB_CATS[cat].label} — indexing started`, "success")
      onAdded()
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : "Failed to add source", "error")
    } finally { setLoading(false) }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4 p-4 rounded-xl border border-[var(--border)] bg-[var(--card)]">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">Add Knowledge Source</span>
        <button type="button" onClick={onCancel} className="p-1 rounded-lg hover:bg-[var(--muted)] text-[var(--muted-foreground)]">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Step 1 — Category */}
      <div className="flex flex-col gap-1.5">
        <label className="text-[11px] font-semibold text-[var(--muted-foreground)] uppercase tracking-wide">1 · What kind of knowledge?</label>
        <div className="grid grid-cols-3 gap-2">
          {(Object.entries(KB_CATS) as [KBCategory, typeof KB_CATS[KBCategory]][]).map(([key, c]) => (
            <button key={key} type="button" onClick={() => setCat(key)}
              className={`flex flex-col gap-1 p-3 rounded-xl border text-left transition-all
                ${cat === key
                  ? `border ${c.border} bg-white/[0.04] ring-1 ring-white/10`
                  : "border-[var(--border)] hover:border-white/20 hover:bg-white/[0.02]"}`}>
              <span className={`flex items-center gap-1 text-[10px] font-bold px-1.5 py-0.5 rounded-full w-fit border ${c.badge}`}>
                {c.icon} {c.label}
              </span>
              <span className="text-[10px] text-[var(--muted-foreground)] leading-snug mt-0.5">{c.desc.split(" — ")[0]}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Step 2 — Source type */}
      <div className="flex flex-col gap-1.5">
        <label className="text-[11px] font-semibold text-[var(--muted-foreground)] uppercase tracking-wide">2 · What type of source?</label>
        <div className="grid grid-cols-3 gap-1.5">
          {(Object.entries(KB_SOURCE_TYPES) as [KBSourceType, typeof KB_SOURCE_TYPES[KBSourceType]][]).map(([key, t]) => (
            <button key={key} type="button" onClick={() => setSrcType(key)}
              className={`flex items-center gap-2 px-2.5 py-2 rounded-lg border text-left transition-all
                ${srcType === key
                  ? "border-white/25 bg-white/[0.06] ring-1 ring-white/10"
                  : "border-[var(--border)] hover:border-white/20 hover:bg-white/[0.02]"}`}>
              <span className={`flex items-center justify-center w-6 h-6 rounded-md shrink-0 ${t.color}`}>{t.icon}</span>
              <span className="text-[11px] font-medium truncate">{t.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Step 3 — URL */}
      <div className="flex flex-col gap-1.5">
        <label className="text-[11px] font-semibold text-[var(--muted-foreground)] uppercase tracking-wide">3 · Paste URL</label>
        <div className="flex gap-2">
          <input value={url} onChange={(e) => setUrl(e.target.value)} required
            placeholder={KB_SOURCE_TYPES[srcType].hint}
            className="flex-1 rounded-lg border border-[var(--border)] bg-[var(--muted)] px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-white/30" />
          <button type="button" onClick={handlePaste} title="Paste from clipboard"
            className="p-2 rounded-lg border border-[var(--border)] hover:bg-[var(--muted)] transition-colors shrink-0">
            <Clipboard className="w-3.5 h-3.5 text-[var(--muted-foreground)]" />
          </button>
        </div>
        <p className="text-[10px] text-[var(--muted-foreground)] italic">{KB_CATS[cat].desc}</p>
      </div>

      <button type="submit" disabled={loading || !url.trim()}
        className="w-full rounded-lg bg-white text-black py-2 text-sm font-semibold hover:opacity-80 disabled:opacity-40 transition-opacity">
        {loading ? "Indexing…" : `Add ${KB_SOURCE_TYPES[srcType].label} to ${KB_CATS[cat].label}`}
      </button>
    </form>
  )
}

// ── Module-level helpers ───────────────────────────────────────────────────────
function sourceName(url: string): string {
  if (url.startsWith("artifact://")) {
    const raw = url.replace("artifact://", "")
    const last = raw.split(":").pop() ?? raw
    return last.replace(/_/g, " ").trim().slice(0, 60) || raw
  }
  try {
    const u = new URL(url)
    const domain = u.hostname.replace(/^www\./, "")
    const path = u.pathname.replace(/\/$/, "").split("/").pop()
    return path ? `${domain} — ${decodeURIComponent(path).replace(/[-_]/g, " ")}` : domain
  } catch { return url }
}

function sourceHost(url: string): string {
  if (url.startsWith("artifact://")) return "artifact"
  try { return new URL(url).hostname.replace(/^www\./, "") } catch { return url }
}

// ── Chunk inspector drawer ─────────────────────────────────────────────────────
function KBSourceDrawer({ projectId, source, meta, onClose, onDelete }: {
  projectId: string
  source: KBSource
  meta: KBMeta
  onClose: () => void
  onDelete: () => void
}) {
  const typeInfo = KB_SOURCE_TYPES[meta.type]
  const catInfo  = KB_CATS[meta.cat]
  const [chunks, setChunks] = useState<KBChunk[]>([])
  const [loading, setLoading] = useState(true)
  const { toast } = useToast()

  useEffect(() => {
    if (source.status !== "indexed") { setLoading(false); return }
    setLoading(true)
    kbApi.getSourceChunks(projectId, source.id)
      .then((results) => setChunks(Array.isArray(results) ? results : []))
      .catch(() => setChunks([]))
      .finally(() => setLoading(false))
  }, [source.id, projectId])

  const statusLabel: Record<string, string> = {
    indexed: "Indexed", crawling: "Indexing…", pending: "Pending", failed: "Failed",
  }

  return (
    <>
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/40 z-40 backdrop-blur-sm"
        onClick={onClose}
      />
      {/* Drawer */}
      <motion.div
        initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
        transition={{ type: "spring", bounce: 0, duration: 0.3 }}
        className="fixed right-0 top-0 h-full w-[480px] z-50 flex flex-col
                   bg-[var(--background)] border-l border-[var(--border)] shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-start gap-3 p-4 border-b border-[var(--border)] shrink-0">
          <div className={`flex items-center justify-center w-10 h-10 rounded-xl shrink-0 ${typeInfo.color}`}>
            {typeInfo.icon}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold leading-snug">{sourceName(source.url)}</p>
            <p className="text-[11px] text-[var(--muted-foreground)] font-mono mt-0.5 truncate">{source.url}</p>
            <div className="flex items-center gap-2 mt-1.5">
              <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full border ${catInfo.badge}`}>
                {catInfo.icon} {catInfo.label}
              </span>
              <span className="text-[10px] text-[var(--muted-foreground)]">{typeInfo.label}</span>
              <span className={`text-[10px] font-medium ${source.status === "indexed" ? "text-green-400" : source.status === "failed" ? "text-red-400" : "text-blue-400"}`}>
                {statusLabel[source.status] ?? source.status}
              </span>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-[var(--muted)] text-[var(--muted-foreground)] shrink-0">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Stats bar */}
        <div className="flex items-center gap-4 px-4 py-2.5 border-b border-[var(--border)] bg-[var(--muted)] shrink-0">
          <div className="text-center">
            <p className="text-base font-bold">{source.chunk_count ?? 0}</p>
            <p className="text-[10px] text-[var(--muted-foreground)]">total chunks</p>
          </div>
          <div className="w-px h-6 bg-[var(--border)]" />
          <div className="text-center">
            <p className="text-base font-bold">{loading ? "…" : chunks.length}</p>
            <p className="text-[10px] text-[var(--muted-foreground)]">loaded</p>
          </div>
          <div className="w-px h-6 bg-[var(--border)]" />
          <div className="text-center">
            <p className="text-base font-bold">
              {chunks.length > 0
                ? Math.round(chunks.reduce((s, c) => s + c.text.length, 0) / chunks.length)
                : "—"}
            </p>
            <p className="text-[10px] text-[var(--muted-foreground)]">avg chars</p>
          </div>
          <div className="ml-auto">
            <button onClick={() => { onDelete(); onClose() }}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] text-red-400 hover:bg-red-900/20 border border-red-900/30 transition-all">
              <Trash2 className="w-3 h-3" /> Remove
            </button>
          </div>
        </div>

        {/* Chunks list */}
        <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3">
          <p className="text-[11px] font-semibold text-[var(--muted-foreground)] uppercase tracking-wide">
            Knowledge Chunks
          </p>

          {source.status !== "indexed" ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
              {source.status === "crawling" && <Loader2 className="w-6 h-6 text-blue-400 animate-spin" />}
              {source.status === "failed"   && <XCircle className="w-6 h-6 text-red-400" />}
              {source.status === "pending"  && <Clock className="w-6 h-6 text-gray-500" />}
              <p className="text-sm text-[var(--muted-foreground)]">
                {source.status === "crawling" ? "Indexing in progress…" :
                 source.status === "failed"   ? (source.error ?? "Indexing failed") :
                 "Waiting to be indexed"}
              </p>
            </div>
          ) : loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-5 h-5 text-blue-400 animate-spin" />
            </div>
          ) : chunks.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 gap-2 text-center">
              <p className="text-sm text-[var(--muted-foreground)]">No chunks retrieved</p>
              <p className="text-xs text-[var(--muted-foreground)]">Try the Search Context Library to query across all sources</p>
            </div>
          ) : (
            chunks.map((c, i) => (
              <div key={c.id ?? i} className="flex flex-col gap-2 p-3 rounded-xl border border-[var(--border)] bg-[var(--card)]">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono text-[var(--muted-foreground)]">
                    chunk {(c.metadata.chunk_index ?? i) + 1}
                  </span>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded-md bg-[var(--muted)] text-[var(--muted-foreground)]">
                    {c.text.length} chars
                  </span>
                </div>
                <p className="text-xs leading-relaxed text-[var(--foreground)]">{c.text}</p>
                {(c.metadata.url || c.metadata.title) && (
                  <p className="text-[10px] text-[var(--muted-foreground)] font-mono truncate">
                    {c.metadata.title ?? c.metadata.url}
                  </p>
                )}
              </div>
            ))
          )}
        </div>
      </motion.div>
    </>
  )
}

// ── KB tab ─────────────────────────────────────────────────────────────────────
function KBTab({ projectId }: { projectId: string }) {
  const { toast } = useToast()
  const { data, mutate: refresh } = useSWR<KBData>(
    `/api/projects/${projectId}/kb`,
    fetcher,
    { refreshInterval: (kbData) => kbData?.sources?.some(s => s.status === "pending" || s.status === "crawling") ? 3000 : 0 }
  )
  const [addingCat, setAddingCat] = useState<KBCategory | null>(null)
  const [inspectSource, setInspectSource] = useState<KBSource | null>(null)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [searchResults, setSearchResults] = useState<Array<{ text: string; source: string; score: number }>>([])
  const [searching, setSearching] = useState(false)

  async function retrySource(sourceId: string) {
    await fetch(`/api/projects/${projectId}/kb/sources/${sourceId}/retry`, { method: "POST", credentials: "include" })
      .catch((err) => toast(err?.message ?? "Retry failed", "error"))
    refresh()
  }

  async function deleteSource(sourceId: string) {
    if (!confirm("Remove this knowledge source?")) return
    await kbApi.deleteSource(projectId, sourceId).catch((err) => toast(err?.message ?? "Delete failed", "error"))
    toast("Source removed", "success")
    refresh()
  }

  async function doSearch(e: React.FormEvent) {
    e.preventDefault()
    if (!searchQuery.trim()) return
    setSearching(true)
    try {
      const results = await kbApi.search(projectId, searchQuery)
      setSearchResults(Array.isArray(results) ? results : [])
    } catch { setSearchResults([]) }
    finally { setSearching(false) }
  }

  const statusDot = (s: string) => ({
    indexed:  <span className="w-1.5 h-1.5 rounded-full bg-green-400 shrink-0" />,
    crawling: <Loader2 className="w-3 h-3 text-blue-400 animate-spin shrink-0" />,
    failed:   <span className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" />,
    pending:  <span className="w-1.5 h-1.5 rounded-full bg-gray-500 shrink-0" />,
  }[s] ?? null)

  const sources = data?.sources ?? []

  // Group sources by category from localStorage meta
  const grouped = sources.reduce<Record<KBCategory, typeof sources>>((acc, s) => {
    acc[readKBMeta(s.url).cat].push(s)
    return acc
  }, { context: [], reference: [], subject: [] })

  return (
    <>
    <AnimatePresence>
      {inspectSource && (
        <KBSourceDrawer
          key={inspectSource.id}
          projectId={projectId}
          source={inspectSource}
          meta={readKBMeta(inspectSource.url)}
          onClose={() => setInspectSource(null)}
          onDelete={() => { setInspectSource(null); deleteSource(inspectSource.id) }}
        />
      )}
    </AnimatePresence>
    <div className="flex flex-col gap-5">
      {/* Purpose banner */}
      <div className="flex items-start gap-3 p-3.5 rounded-xl bg-[var(--muted)] border border-[var(--border)]">
        <div className="w-7 h-7 rounded-lg bg-white/10 flex items-center justify-center shrink-0 mt-0.5">
          <BookOpen className="w-3.5 h-3.5 text-[var(--muted-foreground)]" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold">Context Library</p>
          <p className="text-[11px] text-[var(--muted-foreground)] mt-0.5 leading-relaxed">
            Everything here is read by Sentinel before it researches — like briefing an analyst. Keep your own knowledge, reference material, and research targets separate so Sentinel knows how to weight each.
          </p>
          {sources.length > 0 && (
            <p className="text-[10px] text-[var(--muted-foreground)] mt-1.5">
              {sources.length} source{sources.length !== 1 ? "s" : ""} · {data?.chunk_count ?? 0} chunk{(data?.chunk_count ?? 0) !== 1 ? "s" : ""} indexed
            </p>
          )}
        </div>
      </div>

      {/* Add form */}
      <AnimatePresence>
        {addingCat && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden">
            <AddSourceForm projectId={projectId} defaultCat={addingCat}
              onAdded={() => { setAddingCat(null); refresh() }}
              onCancel={() => setAddingCat(null)} />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Three knowledge sections */}
      {(Object.entries(KB_CATS) as [KBCategory, typeof KB_CATS[KBCategory]][]).map(([cat, cfg]) => {
        const catSources = grouped[cat]
        return (
          <div key={cat} className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className={`flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border ${cfg.badge}`}>
                  {cfg.icon} {cfg.label}
                </span>
                {catSources.length > 0 && (
                  <span className="text-[10px] text-[var(--muted-foreground)]">
                    {catSources.length} source{catSources.length !== 1 ? "s" : ""}
                  </span>
                )}
              </div>
              {!addingCat && (
                <button onClick={() => setAddingCat(cat)}
                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-dashed border-white/15 text-[10px] text-[var(--muted-foreground)] hover:border-white/30 hover:text-[var(--foreground)] transition-all">
                  <Plus className="w-3 h-3" /> Add
                </button>
              )}
            </div>

            {catSources.length === 0 ? (
              <div className={`px-3 py-2.5 rounded-xl border border-dashed ${cfg.border} bg-white/[0.01]`}>
                <p className="text-[11px] text-[var(--muted-foreground)] italic">{cfg.desc}</p>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                {catSources.map((s) => {
                  const meta = readKBMeta(s.url)
                  const typeInfo = KB_SOURCE_TYPES[meta.type]
                  return (
                    <button
                      key={s.id}
                      onClick={() => setInspectSource(s)}
                      className="group relative flex flex-col gap-2 p-3 rounded-xl border border-[var(--border)] bg-[var(--card)] hover:border-white/25 hover:bg-white/[0.03] transition-all text-left cursor-pointer"
                    >
                      <div className="flex items-start gap-2.5">
                        <div className={`flex items-center justify-center w-8 h-8 rounded-lg shrink-0 ${typeInfo.color}`}>
                          {typeInfo.icon}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-semibold leading-snug line-clamp-2">{sourceName(s.url)}</p>
                          <p className="text-[10px] text-[var(--muted-foreground)] mt-0.5 truncate font-mono">{sourceHost(s.url)}</p>
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          {statusDot(s.status)}
                        </div>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] text-[var(--muted-foreground)] capitalize">{typeInfo.label}</span>
                        {s.status === "crawling" ? (
                          <span className="text-[10px] text-blue-400 animate-pulse">Indexing…</span>
                        ) : s.status === "indexed" ? (
                          <span className="text-[10px] text-[var(--muted-foreground)] group-hover:text-[var(--foreground)] transition-colors">
                            Inspect →
                          </span>
                        ) : s.status === "failed" ? (
                          <button
                            onClick={(e) => { e.stopPropagation(); retrySource(s.id) }}
                            className="text-[10px] text-blue-400 hover:underline"
                          >
                            Retry
                          </button>
                        ) : null}
                      </div>
                      {s.status === "failed" && s.error && (
                        <p className="text-[10px] text-red-400 truncate">{s.error}</p>
                      )}
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}

      {/* Search */}
      {sources.length > 0 && (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] overflow-hidden">
          <button onClick={() => setSearchOpen(!searchOpen)}
            className="w-full flex items-center justify-between px-4 py-3 text-sm font-semibold hover:bg-[var(--muted)] transition-colors">
            <span className="flex items-center gap-2"><Search className="w-3.5 h-3.5" /> Search Context Library</span>
            {searchOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
          {searchOpen && (
            <div className="px-4 pb-4 flex flex-col gap-3 border-t border-[var(--border)]">
              <form onSubmit={doSearch} className="flex gap-2 pt-3">
                <input value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search indexed content…"
                  className="flex-1 rounded-lg border border-[var(--border)] bg-[var(--muted)] px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-white/30" />
                <button type="submit" disabled={searching || !searchQuery.trim()}
                  className="px-4 py-2 rounded-lg bg-white text-black text-sm font-semibold hover:opacity-80 disabled:opacity-40 transition-opacity">
                  {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : "Search"}
                </button>
              </form>
              {searchResults.map((r, i) => (
                <div key={i} className="p-3 rounded-lg border border-[var(--border)] bg-[var(--muted)]">
                  <p className="text-xs leading-relaxed">{r.text}</p>
                  <div className="flex items-center justify-between mt-2">
                    <span className="text-[10px] text-[var(--muted-foreground)] truncate font-mono">{r.source}</span>
                    <span className="text-[10px] text-[var(--muted-foreground)] shrink-0 ml-2">{r.score.toFixed(3)}</span>
                  </div>
                </div>
              ))}
              {searchResults.length === 0 && searchQuery && !searching && (
                <p className="text-xs text-[var(--muted-foreground)] text-center py-2">No results found.</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
    </>
  )
}

// ── Memory tab ─────────────────────────────────────────────────────────────────
function EpisodeCard({ ep, onDelete }: { ep: MemoryData["episodes"][number]; onDelete: () => void }) {
  const [open, setOpen] = useState(false)
  const findings = ep.finding_texts ?? []
  const kindLabel = ep.kind ? (DOMAIN_LABELS[ep.kind] ?? ep.kind) : ep.mode

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] overflow-hidden">
      {/* clickable header row */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="group w-full text-left p-3 hover:bg-white/5 transition-colors"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 min-w-0">
            <Brain className="w-3.5 h-3.5 text-blue-400 shrink-0" />
            <span className="text-sm font-medium truncate capitalize">{ep.target || ep.entity}</span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-xs text-[var(--muted-foreground)]">
              {new Date(ep.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
            </span>
            <button
              onClick={(e) => { e.stopPropagation(); onDelete() }}
              className="opacity-0 group-hover:opacity-100 p-1 rounded-lg text-red-400 hover:bg-red-900/30 transition-all"
            >
              <Trash2 className="w-3 h-3" />
            </button>
            {open ? <ChevronUp className="w-3.5 h-3.5 text-[var(--muted-foreground)]" />
                   : <ChevronDown className="w-3.5 h-3.5 text-[var(--muted-foreground)]" />}
          </div>
        </div>

        {/* meta row */}
        <div className="flex items-center gap-2 mt-1.5 flex-wrap">
          {kindLabel && (
            <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-900/40 text-blue-300 border border-blue-700/30">
              {kindLabel}
            </span>
          )}
          <span className="px-1.5 py-0.5 rounded text-[10px] bg-[var(--muted)] text-[var(--muted-foreground)]">
            {ep.backend}
          </span>
          <span className="flex items-center gap-1 text-xs text-[var(--muted-foreground)]">
            <Globe className="w-3 h-3 text-blue-400" />{ep.public}
          </span>
          <span className="flex items-center gap-1 text-xs text-[var(--muted-foreground)]">
            <Lock className="w-3 h-3 text-amber-400" />{ep.private}
          </span>
          {ep.gaps > 0 && (
            <span className="flex items-center gap-1 text-xs text-red-400">
              <AlertTriangle className="w-3 h-3" />{ep.gaps} gaps
            </span>
          )}
          {findings.length > 0 && (
            <span className="text-[10px] text-[var(--muted-foreground)]">
              {findings.length} finding{findings.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>
      </button>

      {/* expanded finding_texts */}
      {open && (
        <div className="border-t border-[var(--border)] px-3 py-2.5 flex flex-col gap-1.5">
          {findings.length > 0 ? (
            findings.map((text, i) => (
              <div key={i} className="flex gap-2 text-xs text-[var(--muted-foreground)] leading-relaxed">
                <span className="text-blue-500 shrink-0 mt-0.5">•</span>
                <span>{text}</span>
              </div>
            ))
          ) : (
            <p className="text-xs text-[var(--muted-foreground)] italic">No finding detail stored for this run.</p>
          )}
        </div>
      )}
    </div>
  )
}

function MemoryTab({ projectId }: { projectId: string }) {
  const { toast } = useToast()
  const { data, mutate: refreshMemory } = useSWR<MemoryData>(`/api/projects/${projectId}/memory`, fetcher)
  const [tab, setTab] = useState<"episodes" | "facts">("episodes")

  async function deleteEpisode(episodeId: string) {
    if (!confirm("Delete this memory episode?")) return
    await memoryApi.deleteRun(projectId, episodeId).catch((err) => toast(err?.message ?? "Delete failed", "error"))
    toast("Episode deleted", "success")
    refreshMemory()
  }

  const episodes = data?.episodes ?? []
  const facts = data?.facts ?? []
  const totalGaps = episodes.reduce((s, e) => s + (e.gaps ?? 0), 0)

  return (
    <div className="flex flex-col gap-4">
      {/* Stats — runs / facts / gaps */}
      {(episodes.length > 0 || facts.length > 0) && (
        <div className="grid grid-cols-3 gap-3">
          <div className="p-3 rounded-xl border border-[var(--border)] bg-[var(--card)] text-center">
            <p className="text-xl font-bold text-blue-400">{episodes.length}</p>
            <p className="text-xs text-[var(--muted-foreground)] mt-0.5">Research runs</p>
          </div>
          <div className="p-3 rounded-xl border border-[var(--border)] bg-[var(--card)] text-center">
            <p className="text-xl font-bold text-emerald-400">{facts.length}</p>
            <p className="text-xs text-[var(--muted-foreground)] mt-0.5">Stored facts</p>
          </div>
          <div className={`p-3 rounded-xl border bg-[var(--card)] text-center ${totalGaps > 0 ? "border-red-800/50" : "border-[var(--border)]"}`}>
            <p className={`text-xl font-bold ${totalGaps > 0 ? "text-red-400" : "text-[var(--muted-foreground)]"}`}>{totalGaps}</p>
            <p className="text-xs text-[var(--muted-foreground)] mt-0.5">Knowledge gaps</p>
          </div>
        </div>
      )}

      {/* Sub-tabs */}
      <div className="flex gap-1 p-1 rounded-lg bg-[var(--muted)] w-fit">
        {(["episodes", "facts"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all capitalize
              ${tab === t ? "bg-[var(--card)] shadow-sm text-[var(--foreground)]" : "text-[var(--muted-foreground)]"}`}>
            {t === "episodes" ? `Episodes (${episodes.length})` : `Facts (${facts.length})`}
          </button>
        ))}
      </div>

      {tab === "episodes" && (
        <div className="flex flex-col gap-2">
          {episodes.map((ep) => (
            <EpisodeCard key={ep.id} ep={ep} onDelete={() => deleteEpisode(ep.id)} />
          ))}
          {episodes.length === 0 && (
            <p className="text-sm text-[var(--muted-foreground)] text-center py-10">No research episodes yet. Run a task to populate memory.</p>
          )}
        </div>
      )}

      {tab === "facts" && (
        <div className="flex flex-col gap-2">
          {facts.map((f) => (
            <div key={f.id}
              className={`p-3 rounded-xl border border-[var(--border)] bg-[var(--card)] ${f.boundary === "public" ? "finding-public" : "finding-private"}`}>
              <p className="text-xs leading-relaxed">{f.content}</p>
              <div className="flex items-center gap-2 mt-1.5">
                <span className={f.boundary === "public" ? "badge-public" : "badge-private"}>{f.boundary}</span>
                {f.source_label && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-[var(--muted)] text-[var(--muted-foreground)]">
                    {f.source_label}
                  </span>
                )}
                <span className="text-[10px] text-[var(--muted-foreground)] ml-auto">
                  {new Date(f.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
                </span>
              </div>
            </div>
          ))}
          {facts.length === 0 && (
            <p className="text-sm text-[var(--muted-foreground)] text-center py-10">No semantic facts extracted yet.</p>
          )}
        </div>
      )}
    </div>
  )
}

// ── Artifacts tab ──────────────────────────────────────────────────────────────
const DOMAIN_TYPE_COLOR: Record<string, string> = {
  market:           "bg-green-900/50 text-green-300 border-green-800/50",
  software:         "bg-violet-900/50 text-violet-300 border-violet-800/50",
  finance:          "bg-cyan-900/50 text-cyan-300 border-cyan-800/50",
  academic:         "bg-blue-900/50 text-blue-300 border-blue-800/50",
  product_research: "bg-amber-900/50 text-amber-300 border-amber-800/50",
  travel:           "bg-teal-900/50 text-teal-300 border-teal-800/50",
  nutrition:        "bg-lime-900/50 text-lime-300 border-lime-800/50",
  govt_proposal:    "bg-orange-900/50 text-orange-300 border-orange-800/50",
  competitor:       "bg-purple-900/50 text-purple-300 border-purple-800/50",
  client:           "bg-sky-900/50 text-sky-300 border-sky-800/50",
  self_profile:     "bg-indigo-900/50 text-indigo-300 border-indigo-800/50",
}

function ArtifactCard({ a, projectId }: { a: Artifact; projectId: string }) {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const domainLabel = DOMAIN_LABELS[a.type] ?? a.type
  const domainIcon  = DOMAIN_ICONS[a.type] ?? <FileText className="w-3 h-3" />
  const badgeCls    = DOMAIN_TYPE_COLOR[a.type] ?? "bg-gray-800 text-gray-300 border-gray-700"
  const taskHref    = a.task_id ? `/projects/${projectId}/tasks/${a.task_id}` : null
  const findings    = a.finding_texts ?? []

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] overflow-hidden">
      {/* Header row — always visible */}
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 p-3 text-left hover:bg-white/5 transition-colors"
      >
        <div className={`w-8 h-8 rounded-lg border flex items-center justify-center shrink-0 ${badgeCls}`}>
          {domainIcon}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{a.target}</p>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span className={`text-[10px] px-1.5 py-0.5 rounded border font-semibold ${badgeCls}`}>
              {domainLabel}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--muted)] text-[var(--muted-foreground)] border border-[var(--border)]">
              {a.backend}
            </span>
            <span className="text-[10px] text-[var(--muted-foreground)]">
              {new Date(a.created_at).toLocaleDateString()}
            </span>
            {findings.length > 0 && (
              <span className="text-[10px] text-[var(--muted-foreground)]">
                {findings.length} finding{findings.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {a.gaps > 0 && (
            <span className="flex items-center gap-1 text-xs text-amber-400">
              <AlertTriangle className="w-3 h-3" /> {a.gaps}
            </span>
          )}
          {open ? <ChevronUp className="w-4 h-4 text-[var(--muted-foreground)]" /> : <ChevronDown className="w-4 h-4 text-[var(--muted-foreground)]" />}
        </div>
      </button>

      {/* Expanded findings */}
      {open && (
        <div className="border-t border-[var(--border)] px-3 pb-3 pt-2">
          {findings.length > 0 ? (
            <ul className="flex flex-col gap-1.5">
              {findings.map((f, i) => (
                <li key={i} className="flex gap-2 text-xs text-[var(--muted-foreground)]">
                  <span className="mt-0.5 w-1.5 h-1.5 rounded-full bg-[var(--muted-foreground)] shrink-0 opacity-60" />
                  <span className="leading-relaxed">{f}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-[var(--muted-foreground)] italic">No findings recorded for this run.</p>
          )}
          {taskHref && (
            <button
              onClick={() => router.push(taskHref)}
              className="mt-3 flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 transition-colors"
            >
              <ArrowRight className="w-3 h-3" /> View full task report
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function ArtifactsTab({ projectId }: { projectId: string }) {
  const { data: artifacts } = useSWR<Artifact[]>(`/api/artifacts?project=${projectId}`, fetcher)

  if (!artifacts) {
    return <div className="flex items-center justify-center py-16"><Loader2 className="w-5 h-5 animate-spin text-[var(--muted-foreground)]" /></div>
  }

  if (artifacts.length === 0) {
    return (
      <div className="flex flex-col items-center py-16 gap-3 text-center">
        <div className="w-12 h-12 rounded-2xl border border-[var(--border)] bg-[var(--card)] flex items-center justify-center">
          <FileText className="w-5 h-5 text-[var(--muted-foreground)]" />
        </div>
        <div>
          <p className="text-sm font-medium">No artifacts yet</p>
          <p className="text-xs text-[var(--muted-foreground)] mt-1">Intelligence reports appear here when research tasks complete.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {artifacts.map((a) => (
        <ArtifactCard key={a.id} a={a} projectId={projectId} />
      ))}
    </div>
  )
}

// ── Edit project form ──────────────────────────────────────────────────────────
function EditProjectForm({ project, onSaved, onCancel }: {
  project: Project; onSaved: () => void; onCancel: () => void
}) {
  const { toast } = useToast()
  const [name, setName] = useState(project.name)
  const [website, setWebsite] = useState(project.website ?? "")
  const [description, setDescription] = useState(project.description ?? "")
  const [context, setContext] = useState(project.context ?? "")
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const fieldCls = "w-full rounded-lg border border-[var(--border)] bg-[var(--muted)] px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-white/30"

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true); setSaveError(null)
    try {
      const res = await fetch(`/api/projects/${project.id}/edit`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, website, description, context }),
      })
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      toast("Project updated", "success")
      onSaved()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to save"
      setSaveError(msg); toast(msg, "error")
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSave} className="flex flex-col gap-3 mt-3 p-4 rounded-xl border border-[var(--border)] bg-[var(--card)]">
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-semibold">Edit Project</span>
        <button type="button" onClick={onCancel} className="p-1 rounded-lg hover:bg-[var(--muted)] text-[var(--muted-foreground)]">
          <X className="w-4 h-4" />
        </button>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-[var(--muted-foreground)] mb-1">Name *</label>
          <input value={name} onChange={(e) => setName(e.target.value)} required className={fieldCls} />
        </div>
        <div>
          <label className="block text-xs font-medium text-[var(--muted-foreground)] mb-1">Website</label>
          <input value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="https://example.com" className={fieldCls} />
        </div>
      </div>
      <div>
        <label className="block text-xs font-medium text-[var(--muted-foreground)] mb-1">Description</label>
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} className={`${fieldCls} resize-none`} />
      </div>
      <div>
        <label className="block text-xs font-medium text-[var(--muted-foreground)] mb-1">Research Context</label>
        <textarea value={context} onChange={(e) => setContext(e.target.value)} rows={2}
          placeholder="Background context Sentinel should know for all tasks in this project…" className={`${fieldCls} resize-none`} />
      </div>
      {saveError && <p className="text-xs text-red-400">{saveError}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={saving || !name.trim()}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-white text-black text-sm font-semibold hover:opacity-80 disabled:opacity-40 transition-opacity">
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />} Save
        </button>
        <button type="button" onClick={onCancel}
          className="px-4 py-2 rounded-lg border border-[var(--border)] text-sm font-semibold hover:bg-[var(--muted)] transition-colors">
          Cancel
        </button>
      </div>
    </form>
  )
}

// ── Project intelligence bar ───────────────────────────────────────────────────
// Aggregated stats shown in header, derived from memory + task list
function IntelBar({ projectId, taskList }: { projectId: string; taskList: Task[] | undefined }) {
  const { data: memData } = useSWR<MemoryData>(`/api/projects/${projectId}/memory`, fetcher)

  const totalPublic  = (memData?.episodes ?? []).reduce((s, e) => s + (e.public  ?? 0), 0)
  const totalPrivate = (memData?.episodes ?? []).reduce((s, e) => s + (e.private ?? 0), 0)
  const totalGaps    = (memData?.episodes ?? []).reduce((s, e) => s + (e.gaps   ?? 0), 0)

  const safeList = Array.isArray(taskList) ? taskList : []
  const done    = safeList.filter(t => t.status === "done").length
  const running = safeList.filter(t => t.status === "running").length

  if (!memData && !taskList) return null

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3 px-4 rounded-xl border border-[var(--border)] bg-[var(--card)]/50">
      {done > 0 && (
        <span className="flex items-center gap-1.5 text-xs text-[var(--muted-foreground)]">
          <CheckCircle2 className="w-3.5 h-3.5 text-green-400" />
          <span className="font-semibold text-green-400">{done}</span> completed
        </span>
      )}
      {running > 0 && (
        <span className="flex items-center gap-1.5 text-xs text-[var(--muted-foreground)]">
          <Loader2 className="w-3.5 h-3.5 text-amber-400 animate-spin" />
          <span className="font-semibold text-amber-400">{running}</span> in progress
        </span>
      )}
      {totalPublic > 0 && (
        <span className="flex items-center gap-1.5 text-xs text-[var(--muted-foreground)]">
          <Globe className="w-3.5 h-3.5 text-blue-400" />
          <span className="font-semibold text-blue-400">{totalPublic}</span> public findings
        </span>
      )}
      {totalPrivate > 0 && (
        <span className="flex items-center gap-1.5 text-xs text-[var(--muted-foreground)]">
          <Lock className="w-3.5 h-3.5 text-amber-400" />
          <span className="font-semibold text-amber-400">{totalPrivate}</span> private signals
        </span>
      )}
      {totalGaps > 0 && (
        <span className="flex items-center gap-1.5 text-xs text-red-400">
          <AlertTriangle className="w-3.5 h-3.5" />
          <span className="font-semibold">{totalGaps}</span> knowledge gaps
        </span>
      )}
      {totalPublic === 0 && totalPrivate === 0 && done === 0 && running === 0 && (
        <span className="text-xs text-[var(--muted-foreground)]">No intelligence gathered yet — commission a research task to begin.</span>
      )}
    </div>
  )
}

// ── Inner component (uses useSearchParams → must be inside Suspense) ───────────
function ProjectDetail({ id }: { id: string }) {
  const searchParams = useSearchParams()
  const router = useRouter()
  const { toast } = useToast()
  const [editMode, setEditMode] = useState(false)

  const activeTab = (searchParams.get("tab") as TabKey | null) ?? "tasks"
  function setTab(tab: TabKey) {
    router.push(`/projects/${id}?tab=${tab}`, { scroll: false })
  }

  const { data: project, mutate: mutateProject } = useSWR<Project>(`/api/projects/${id}`, fetcher)
  const { data: taskList } = useSWR<Task[]>(
    `/api/projects/${id}/tasks`,
    fetcher,
    { refreshInterval: (tasks) => tasks?.some(t => t.status === "running") ? 3000 : 0 }
  )

  const tabContent: Record<TabKey, React.ReactNode> = {
    tasks:     <TasksTab projectId={id} />,
    kb:        <KBTab projectId={id} />,
    memory:    <MemoryTab projectId={id} />,
    artifacts: <ArtifactsTab projectId={id} />,
  }

  return (
    <div className="flex flex-col gap-5 max-w-7xl mx-auto w-full">
      {/* ── Header ── */}
      <div>
        {/* Breadcrumb */}
        <div className="flex items-center gap-1.5 text-xs text-[var(--muted-foreground)] mb-3">
          <Link href="/projects" className="hover:text-[var(--foreground)] transition-colors">Projects</Link>
          <span>/</span>
          <span className="truncate text-[var(--foreground)]">{project?.name ?? "…"}</span>
        </div>

        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1.5 flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <GradientHeading size="md" weight="bold">
                {project?.name ?? "Loading…"}
              </GradientHeading>
              {project && !editMode && (
                <button onClick={() => setEditMode(true)} title="Edit project"
                  className="p-1.5 rounded-lg text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--foreground)] transition-colors">
                  <Pencil className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
            {project?.description && (
              <p className="text-sm text-[var(--muted-foreground)]">{project.description}</p>
            )}
            {project?.context && (
              <p className="text-xs text-[var(--muted-foreground)]/70 italic border-l-2 border-[var(--border)] pl-2">
                {project.context}
              </p>
            )}
            {project?.website && (
              <a href={project.website} target="_blank" rel="noopener noreferrer"
                 className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 w-fit transition-colors">
                <Globe className="w-3 h-3" />
                {project.website.replace(/^https?:\/\//, "")}
              </a>
            )}
          </div>

          {/* Task count stat */}
          <div className="flex flex-col items-center p-3 rounded-xl border border-[var(--border)] bg-[var(--card)] min-w-[64px] shrink-0">
            <AnimatedNumber value={taskList?.length ?? 0} className="text-2xl font-bold" />
            <span className="text-xs text-[var(--muted-foreground)]">tasks</span>
          </div>
        </div>

        {/* Edit form */}
        <AnimatePresence>
          {editMode && project && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden">
              <EditProjectForm
                project={project}
                onSaved={() => { mutateProject(); setEditMode(false) }}
                onCancel={() => setEditMode(false)}
              />
            </motion.div>
          )}
        </AnimatePresence>

        {/* Intelligence summary bar */}
        {!editMode && <div className="mt-4"><IntelBar projectId={id} taskList={taskList} /></div>}
      </div>

      {/* ── Tab bar ── */}
      <TabBar active={activeTab} onChange={setTab} />

      {/* ── Tab content ── */}
      <AnimatePresence mode="wait">
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.15 }}
        >
          {tabContent[activeTab]}
        </motion.div>
      </AnimatePresence>
    </div>
  )
}

// ── Page entry ─────────────────────────────────────────────────────────────────
export default function ProjectDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center min-h-64">
        <Loader2 className="w-6 h-6 animate-spin text-[var(--muted-foreground)]" />
      </div>
    }>
      <ProjectDetail id={id} />
    </Suspense>
  )
}
