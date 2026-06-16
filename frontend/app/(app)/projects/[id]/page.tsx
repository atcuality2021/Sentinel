"use client"

import { use, useState } from "react"
import useSWR from "swr"
import Link from "next/link"
import { GradientHeading } from "@/components/ui/gradient-heading"
import { DirectionAwareTabs } from "@/components/ui/direction-aware-tabs"
import { AnimatedNumber } from "@/components/ui/animated-number"
import { PopoverForm, PopoverFormButton, PopoverFormSuccess } from "@/components/ui/popover-form"
import { useToast } from "@/components/ui/toast"
import {
  type Project, type Task, type MemoryData, type KBData, type Artifact,
  tasks as tasksApi, kb as kbApi, memory as memoryApi,
} from "@/lib/api"
import {
  Plus, Play, Globe, Lock, AlertTriangle, Clock, CheckCircle2,
  XCircle, Loader2, BookOpen, FileText, Brain,
  Trash2, RefreshCw, Pencil, Check, ChevronDown, ChevronUp, Clipboard,
} from "lucide-react"

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
function TaskRow({
  task,
  projectId,
  onRun,
  onDelete,
}: {
  task: Task
  projectId: string
  onRun: () => void
  onDelete: () => void
}) {
  const { toast } = useToast()
  const [running, setRunning] = useState(false)
  const [deleting, setDeleting] = useState(false)

  async function handleRun(e: React.MouseEvent) {
    e.preventDefault()
    setRunning(true)
    await tasksApi.run(projectId, task.id).catch((err) => toast(err?.message ?? "Something went wrong", "error"))
    onRun()
    setRunning(false)
  }

  async function handleDelete(e: React.MouseEvent) {
    e.preventDefault()
    e.stopPropagation()
    if (!confirm(`Delete task "${task.objective}"? This cannot be undone.`)) return
    setDeleting(true)
    await tasksApi.delete(projectId, task.id).catch((err) => toast(err?.message ?? "Something went wrong", "error"))
    toast("Task deleted", "success")
    onDelete()
    setDeleting(false)
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
      <button
        onClick={handleDelete}
        disabled={deleting}
        title="Delete task"
        className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-red-500
                   hover:bg-red-50 dark:hover:bg-red-900/20 transition-all disabled:opacity-40"
      >
        {deleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
      </button>
    </Link>
  )
}

// ── Create task form (kept for direct use inside PopoverForm) ──────────────
function CreateTaskForm({ projectId, onCreated }: { projectId: string; onCreated: () => void }) {
  const [objective, setObjective] = useState("")
  const [domain, setDomain] = useState("market")
  const [persona, setPersona] = useState("auto")
  const [context, setContext] = useState("")
  const [loading, setLoading] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const domains = ["market", "software", "finance", "academic", "product_research", "travel", "nutrition", "govt_proposal"]
  const personaOptions = ["auto", "enterprise", "developer", "consumer", "student", "doctor", "nurse"]

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setCreateError(null)
    try {
      const res = await fetch(`/api/projects/${projectId}/tasks`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          objective,
          domain,
          persona: persona === "auto" ? undefined : persona,
          context: context.trim() || undefined,
        }),
      })
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      onCreated()
      setObjective(""); setContext("")
    } catch (err: unknown) {
      setCreateError(err instanceof Error ? err.message : "Failed to create task")
    } finally {
      setLoading(false)
    }
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
      <div className="grid grid-cols-2 gap-3">
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
        <div>
          <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Persona</label>
          <select
            value={persona} onChange={(e) => setPersona(e.target.value)}
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--muted)]
                       px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white"
          >
            {personaOptions.map((p) => (
              <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
            ))}
          </select>
        </div>
      </div>
      <div>
        <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">
          Additional Context <span className="font-normal">(optional)</span>
        </label>
        <textarea
          value={context} onChange={(e) => setContext(e.target.value)} rows={2}
          placeholder="Additional context for this research task…"
          className="w-full rounded-lg border border-[var(--border)] bg-[var(--muted)]
                     px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white resize-none"
        />
      </div>
      {createError && <p className="text-xs text-red-500">{createError}</p>}
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

// ── Task popover form content ───────────────────────────────────────────────
function TaskFormContent({
  projectId,
  loading,
  onSubmit,
}: {
  projectId: string
  loading: boolean
  onSubmit: (data: { objective: string; domain: string; persona?: string }) => void
}) {
  const [objective, setObjective] = useState("")
  const [domain, setDomain] = useState("market")
  const [persona, setPersona] = useState("auto")

  const domains = ["market", "software", "finance", "academic", "product_research", "travel", "nutrition", "govt_proposal"]
  const personaOptions = ["auto", "enterprise", "developer", "consumer", "student", "doctor", "nurse"]

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onSubmit({ objective, domain, persona: persona === "auto" ? undefined : persona })
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 p-3 h-full">
      <div className="mt-6">
        <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Research Objective *</label>
        <textarea
          value={objective} onChange={(e) => setObjective(e.target.value)} required rows={3}
          placeholder="What competitive advantages does Acme Corp have in the BFSI sector?"
          className="w-full rounded-lg border border-[var(--border)] bg-[var(--background)]
                     px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white resize-none"
        />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Domain</label>
          <select
            value={domain} onChange={(e) => setDomain(e.target.value)}
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--background)]
                       px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white"
          >
            {domains.map((d) => (
              <option key={d} value={d}>{d.replace("_", " ")}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Persona</label>
          <select
            value={persona} onChange={(e) => setPersona(e.target.value)}
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--background)]
                       px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white"
          >
            {personaOptions.map((p) => (
              <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
            ))}
          </select>
        </div>
      </div>
      <div className="flex justify-end mt-auto pt-1">
        <PopoverFormButton loading={loading} text="Start Research" />
      </div>
    </form>
  )
}

// ── KB source form content ─────────────────────────────────────────────────
function KBSourceFormContent({
  loading,
  onSubmit,
}: {
  loading: boolean
  onSubmit: (url: string) => void
}) {
  const [url, setUrl] = useState("")

  async function handlePaste() {
    try {
      const text = await navigator.clipboard.readText()
      setUrl(text.trim())
    } catch {
      // clipboard not available — silently ignore
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (url.trim()) onSubmit(url.trim())
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 p-3 h-full">
      <div className="mt-6">
        <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Source URL</label>
        <div className="flex gap-2">
          <input
            value={url} onChange={(e) => setUrl(e.target.value)} required
            placeholder="https://docs.example.com"
            className="flex-1 rounded-lg border border-[var(--border)] bg-[var(--background)]
                       px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white"
          />
          <button
            type="button"
            onClick={handlePaste}
            title="Paste from clipboard"
            className="p-2 rounded-lg border border-[var(--border)] hover:bg-[var(--muted)] transition-colors"
          >
            <Clipboard className="w-3.5 h-3.5 text-[var(--muted-foreground)]" />
          </button>
        </div>
      </div>
      <div className="flex justify-end mt-auto pt-1">
        <PopoverFormButton loading={loading} text="Add Source" />
      </div>
    </form>
  )
}

// ── KB tab ──────────────────────────────────────────────────────────────────
function KBTab({ projectId }: { projectId: string }) {
  const { toast } = useToast()
  const { data, mutate: refresh } = useSWR<KBData>(
    `/api/projects/${projectId}/kb`,
    fetcher,
    { refreshInterval: (kbData) => kbData?.sources?.some(s => s.status === "pending" || s.status === "crawling") ? 3000 : 0 }
  )
  const [urlFormOpen, setUrlFormOpen] = useState(false)
  const [showUrlSuccess, setShowUrlSuccess] = useState(false)
  const [addingUrl, setAddingUrl] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [searchResults, setSearchResults] = useState<Array<{ text: string; source: string; score: number }>>([])
  const [searching, setSearching] = useState(false)

  async function handleAddSource(url: string) {
    setAddingUrl(true)
    try {
      await kbApi.addSource(projectId, url)
      setShowUrlSuccess(true)
      toast("Source added — crawling started", "success")
      refresh()
      setTimeout(() => {
        setUrlFormOpen(false)
        setShowUrlSuccess(false)
      }, 2000)
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : "Something went wrong", "error")
    } finally {
      setAddingUrl(false)
    }
  }

  async function retrySource(sourceId: string) {
    await fetch(`/api/projects/${projectId}/kb/sources/${sourceId}/retry`, {
      method: "POST",
      credentials: "include",
    }).catch((err) => toast(err?.message ?? "Something went wrong", "error"))
    refresh()
  }

  async function deleteSource(sourceId: string) {
    if (!confirm("Remove this knowledge source?")) return
    await kbApi.deleteSource(projectId, sourceId).catch((err) => toast(err?.message ?? "Something went wrong", "error"))
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
    } catch {
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }

  const statusIcon = (s: string) => ({
    indexed:  <CheckCircle2 className="w-3 h-3 text-green-500" />,
    crawling: <Loader2 className="w-3 h-3 text-blue-500 animate-spin" />,
    failed:   <XCircle className="w-3 h-3 text-red-500" />,
    pending:  <Clock className="w-3 h-3 text-gray-400" />,
  }[s] ?? null)

  return (
    <div className="flex flex-col gap-4">
      {/* Add Source popover */}
      <div className="relative">
        <PopoverForm
          title="Add Source"
          open={urlFormOpen}
          setOpen={(open) => {
            setUrlFormOpen(open)
            if (!open) setShowUrlSuccess(false)
          }}
          showSuccess={showUrlSuccess}
          width="380px"
          height="180px"
          openChild={
            <KBSourceFormContent
              loading={addingUrl}
              onSubmit={handleAddSource}
            />
          }
          successChild={
            <PopoverFormSuccess
              title="Source Queued"
              description="Crawling started — check status below."
            />
          }
        />
      </div>

      <div className="flex flex-col gap-2">
        {(data?.sources ?? []).map((s) => (
          <div key={s.id}
            className="group flex flex-col gap-1 p-3 rounded-xl border border-[var(--border)] bg-[var(--card)]">
            <div className="flex items-center gap-3">
              {statusIcon(s.status)}
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--muted)] text-[var(--muted-foreground)]">
                {s.source_type || "web"}
              </span>
              <span className="text-xs truncate flex-1 font-mono text-[var(--muted-foreground)]">{s.url}</span>
              {s.chunk_count > 0 && (
                <span className="text-xs text-[var(--muted-foreground)] shrink-0">{s.chunk_count} chunks</span>
              )}
              {s.status === "failed" && (
                <button
                  onClick={() => retrySource(s.id)}
                  title="Retry ingestion"
                  className="p-1.5 rounded-lg text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20
                             transition-all shrink-0"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                </button>
              )}
              <button
                onClick={() => deleteSource(s.id)}
                title="Remove source"
                className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-red-500
                           hover:bg-red-50 dark:hover:bg-red-900/20 transition-all shrink-0"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
            {s.status === "failed" && s.error && (
              <p className="text-xs text-red-500 mt-1 truncate pl-6">{s.error}</p>
            )}
          </div>
        ))}
        {(data?.sources ?? []).length === 0 && (
          <p className="text-sm text-[var(--muted-foreground)] text-center py-6">
            No sources yet — add a URL above.
          </p>
        )}
      </div>

      {/* Search KB panel */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] overflow-hidden">
        <button
          onClick={() => setSearchOpen(!searchOpen)}
          className="w-full flex items-center justify-between px-4 py-3 text-sm font-semibold
                     hover:bg-[var(--muted)] transition-colors"
        >
          <span className="flex items-center gap-2">
            <BookOpen className="w-3.5 h-3.5" /> Search KB
          </span>
          {searchOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>
        {searchOpen && (
          <div className="px-4 pb-4 flex flex-col gap-3 border-t border-[var(--border)]">
            <form onSubmit={doSearch} className="flex gap-2 pt-3">
              <input
                value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search the knowledge base…"
                className="flex-1 rounded-lg border border-[var(--border)] bg-[var(--muted)]
                           px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white"
              />
              <button
                type="submit" disabled={searching || !searchQuery.trim()}
                className="px-4 py-2 rounded-lg bg-black dark:bg-white text-white dark:text-black
                           text-sm font-semibold hover:opacity-80 disabled:opacity-40 transition-opacity"
              >
                {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : "Search"}
              </button>
            </form>
            {searchResults.length > 0 && (
              <div className="flex flex-col gap-2">
                {searchResults.map((r, i) => (
                  <div key={i} className="p-3 rounded-lg border border-[var(--border)] bg-[var(--muted)]">
                    <p className="text-xs leading-relaxed">{r.text}</p>
                    <div className="flex items-center justify-between mt-2">
                      <span className="text-[10px] text-[var(--muted-foreground)] truncate font-mono">{r.source}</span>
                      <span className="text-[10px] text-[var(--muted-foreground)] shrink-0 ml-2">
                        score: {r.score.toFixed(3)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
            {searchResults.length === 0 && searchQuery && !searching && (
              <p className="text-xs text-[var(--muted-foreground)] text-center py-2">No results found.</p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Memory tab ──────────────────────────────────────────────────────────────
function MemoryTab({ projectId }: { projectId: string }) {
  const { toast } = useToast()
  const { data, mutate: refreshMemory } = useSWR<MemoryData>(`/api/projects/${projectId}/memory`, fetcher)
  const [tab, setTab] = useState<"episodes" | "facts">("episodes")

  async function deleteEpisode(episodeId: string) {
    if (!confirm("Delete this memory episode? This cannot be undone.")) return
    await memoryApi.deleteRun(projectId, episodeId).catch((err) => toast(err?.message ?? "Something went wrong", "error"))
    toast("Episode deleted", "success")
    refreshMemory()
  }

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
            <div key={ep.id}
              className="group p-3 rounded-xl border border-[var(--border)] bg-[var(--card)]">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{ep.target || ep.entity}</span>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-[var(--muted-foreground)]">
                    {new Date(ep.created_at).toLocaleDateString()}
                  </span>
                  <button
                    onClick={() => deleteEpisode(ep.id)}
                    title="Delete episode"
                    className="opacity-0 group-hover:opacity-100 p-1 rounded-lg text-red-500
                               hover:bg-red-50 dark:hover:bg-red-900/20 transition-all"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
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

// ── Artifacts tab ──────────────────────────────────────────────────────────
function ArtifactsTab({ projectId }: { projectId: string }) {
  const { data: artifacts } = useSWR<Artifact[]>(`/api/artifacts?project=${projectId}`, fetcher)

  if (!artifacts) {
    return (
      <div className="flex items-center justify-center py-10">
        <Loader2 className="w-5 h-5 animate-spin text-[var(--muted-foreground)]" />
      </div>
    )
  }

  if (artifacts.length === 0) {
    return (
      <p className="text-sm text-[var(--muted-foreground)] py-6 text-center">
        Artifacts from all tasks in this project appear here after runs complete.
      </p>
    )
  }

  const typeColor: Record<string, string> = {
    competitor: "bg-purple-100 text-purple-700",
    client:     "bg-blue-100 text-blue-700",
    market:     "bg-green-100 text-green-700",
    product:    "bg-amber-100 text-amber-700",
  }

  return (
    <div className="flex flex-col gap-2">
      {artifacts.map((a) => (
        <div
          key={a.id}
          className="flex items-center gap-3 p-3 rounded-xl border border-[var(--border)] bg-[var(--card)]"
        >
          <FileText className="w-4 h-4 text-[var(--muted-foreground)] shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{a.target}</p>
            <div className="flex items-center gap-2 mt-1">
              <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${typeColor[a.type] ?? "bg-gray-100 text-gray-600"}`}>
                {a.type}
              </span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--muted)] text-[var(--muted-foreground)]">
                {a.mode}
              </span>
              <span className="text-xs text-[var(--muted-foreground)]">
                {new Date(a.created_at).toLocaleDateString()}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-3 text-xs text-[var(--muted-foreground)] shrink-0">
            <span className="flex items-center gap-1"><Globe className="w-3 h-3 text-blue-400" /> {a.public_count}</span>
            <span className="flex items-center gap-1"><Lock className="w-3 h-3 text-amber-400" /> {a.private_count}</span>
            {a.gaps > 0 && (
              <span className="flex items-center gap-1 text-red-400"><AlertTriangle className="w-3 h-3" /> {a.gaps}</span>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Edit project form ──────────────────────────────────────────────────────
function EditProjectForm({
  project,
  onSaved,
  onCancel,
}: {
  project: Project
  onSaved: () => void
  onCancel: () => void
}) {
  const [name, setName] = useState(project.name)
  const [website, setWebsite] = useState(project.website ?? "")
  const [description, setDescription] = useState(project.description ?? "")
  const [context, setContext] = useState(project.context ?? "")
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setSaveError(null)
    try {
      const res = await fetch(`/api/projects/${project.id}/edit`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, website, description, context }),
      })
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      onSaved()
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Failed to save")
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSave} className="flex flex-col gap-3 mt-3 p-4 rounded-xl border border-[var(--border)] bg-[var(--card)]">
      <div>
        <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Name *</label>
        <input
          value={name} onChange={(e) => setName(e.target.value)} required
          className="w-full rounded-lg border border-[var(--border)] bg-[var(--muted)]
                     px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white"
        />
      </div>
      <div>
        <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Website</label>
        <input
          value={website} onChange={(e) => setWebsite(e.target.value)}
          placeholder="https://example.com"
          className="w-full rounded-lg border border-[var(--border)] bg-[var(--muted)]
                     px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white"
        />
      </div>
      <div>
        <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Description</label>
        <textarea
          value={description} onChange={(e) => setDescription(e.target.value)} rows={2}
          className="w-full rounded-lg border border-[var(--border)] bg-[var(--muted)]
                     px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white resize-none"
        />
      </div>
      <div>
        <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Context</label>
        <textarea
          value={context} onChange={(e) => setContext(e.target.value)} rows={2}
          placeholder="Additional context about this project…"
          className="w-full rounded-lg border border-[var(--border)] bg-[var(--muted)]
                     px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white resize-none"
        />
      </div>
      {saveError && <p className="text-xs text-red-500">{saveError}</p>}
      <div className="flex gap-2">
        <button
          type="submit" disabled={saving || !name.trim()}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-black dark:bg-white
                     text-white dark:text-black text-sm font-semibold hover:opacity-80 disabled:opacity-40 transition-opacity"
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
          Save
        </button>
        <button
          type="button" onClick={onCancel}
          className="px-4 py-2 rounded-lg border border-[var(--border)] text-sm font-semibold
                     hover:bg-[var(--muted)] transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────
export default function ProjectDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const { toast } = useToast()
  const [taskFormOpen, setTaskFormOpen] = useState(false)
  const [showTaskSuccess, setShowTaskSuccess] = useState(false)
  const [taskFormLoading, setTaskFormLoading] = useState(false)
  const [editMode, setEditMode] = useState(false)

  const { data: project, mutate: mutateProject } = useSWR<Project>(`/api/projects/${id}`, fetcher)
  const { data: taskList, mutate: refreshTasks } = useSWR<Task[]>(
    `/api/projects/${id}/tasks`,
    fetcher,
    { refreshInterval: (tasks) => tasks?.some(t => t.status === "running") ? 3000 : 0 }
  )

  const runningCount = taskList?.filter(t => t.status === "running").length ?? 0

  async function handleCreateTask(data: { objective: string; domain: string; persona?: string }) {
    setTaskFormLoading(true)
    try {
      await tasksApi.create(id, data)
      setShowTaskSuccess(true)
      toast("Task created and queued for research", "success")
      refreshTasks()
      setTimeout(() => {
        setTaskFormOpen(false)
        setShowTaskSuccess(false)
      }, 2000)
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : "Something went wrong", "error")
    } finally {
      setTaskFormLoading(false)
    }
  }

  const tasksContent = (
    <div className="flex flex-col gap-3">
      <div className="flex justify-between items-center">
        <span className="text-xs text-[var(--muted-foreground)]">
          {(taskList ?? []).length} task{(taskList ?? []).length !== 1 ? "s" : ""}
        </span>
        {/* PopoverForm replaces the old collapsible CreateTaskForm panel */}
        <div className="relative">
          <PopoverForm
            title="New Task"
            open={taskFormOpen}
            setOpen={(open) => {
              setTaskFormOpen(open)
              if (!open) setShowTaskSuccess(false)
            }}
            showSuccess={showTaskSuccess}
            width="420px"
            height="360px"
            openChild={
              <TaskFormContent
                projectId={id}
                loading={taskFormLoading}
                onSubmit={handleCreateTask}
              />
            }
            successChild={
              <PopoverFormSuccess
                title="Research Started!"
                description="Your task is being planned and will start shortly."
              />
            }
          />
        </div>
      </div>
      {(taskList ?? []).map((t) => (
        <TaskRow
          key={t.id}
          task={t}
          projectId={id}
          onRun={refreshTasks}
          onDelete={refreshTasks}
        />
      ))}
      {(taskList ?? []).length === 0 && (
        <p className="text-sm text-[var(--muted-foreground)] text-center py-8">
          No tasks yet. Create one to start researching.
        </p>
      )}
    </div>
  )

  return (
    <div className="flex flex-col gap-6 max-w-5xl mx-auto">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1 flex-1 min-w-0">
          <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
            <Link href="/projects" className="hover:underline">Projects</Link>
            <span>/</span>
            <span>{project?.name ?? "…"}</span>
          </div>
          <div className="flex items-center gap-2">
            <GradientHeading size="md" weight="bold">
              {project?.name ?? "Loading…"}
            </GradientHeading>
            {project && (
              <button
                onClick={() => setEditMode(!editMode)}
                title={editMode ? "Cancel edit" : "Edit project"}
                className="p-1.5 rounded-lg text-[var(--muted-foreground)] hover:bg-[var(--muted)]
                           hover:text-[var(--foreground)] transition-colors"
              >
                <Pencil className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
          {project?.description && (
            <p className="text-sm text-[var(--muted-foreground)]">{project.description}</p>
          )}
          {project?.context && (
            <p className="text-xs text-[var(--muted-foreground)] italic border-l-2 border-[var(--border)] pl-2">
              {project.context}
            </p>
          )}
          {project?.website && (
            <a href={project.website} target="_blank" rel="noopener noreferrer"
               className="flex items-center gap-1 text-xs text-blue-500 hover:underline w-fit">
              <Globe className="w-3 h-3" />
              {project.website.replace(/^https?:\/\//, "")}
            </a>
          )}
          {editMode && project && (
            <EditProjectForm
              project={project}
              onSaved={() => { mutateProject(); setEditMode(false) }}
              onCancel={() => setEditMode(false)}
            />
          )}
        </div>
        <div className="flex gap-2 shrink-0">
          <div className="flex flex-col items-center p-3 rounded-xl border border-[var(--border)] bg-[var(--card)] min-w-[72px]">
            <AnimatedNumber value={taskList?.length ?? 0} className="text-xl font-bold" />
            <span className="text-xs text-[var(--muted-foreground)]">tasks</span>
          </div>
          {runningCount > 0 && (
            <div className="flex flex-col items-center p-3 rounded-xl border border-amber-200 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-800 min-w-[72px]">
              <AnimatedNumber value={runningCount} className="text-xl font-bold text-amber-600 dark:text-amber-400" />
              <span className="text-xs text-amber-600 dark:text-amber-400">running</span>
            </div>
          )}
        </div>
      </div>

      <DirectionAwareTabs
        tabs={[
          { id: 0, label: "Tasks",          content: tasksContent },
          { id: 1, label: "Knowledge Base", content: <KBTab projectId={id} /> },
          { id: 2, label: "Memory",         content: <MemoryTab projectId={id} /> },
          { id: 3, label: "Artifacts",      content: <ArtifactsTab projectId={id} /> },
        ]}
      />
    </div>
  )
}
