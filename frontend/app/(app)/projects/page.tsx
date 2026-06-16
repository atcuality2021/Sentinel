"use client"

import { useState } from "react"
import useSWR, { mutate } from "swr"
import { GradientHeading } from "@/components/ui/gradient-heading"
import { type Project, projects as projectsApi } from "@/lib/api"
import { FolderOpen, Globe, Trash2, ChevronRight, Plus, Calendar } from "lucide-react"
import Link from "next/link"

const fetcher = (url: string) => fetch(url, { credentials: "include" }).then((r) => r.json())
const PROJECTS_KEY = "/api/projects"

function ProjectCard({ project, onDelete }: { project: Project; onDelete: () => void }) {
  const [deleting, setDeleting] = useState(false)

  async function handleDelete(e: React.MouseEvent) {
    e.preventDefault()
    if (!confirm(`Delete "${project.name}"? This cannot be undone.`)) return
    setDeleting(true)
    await projectsApi.delete(project.id).catch(() => {})
    onDelete()
    setDeleting(false)
  }

  return (
    <Link
      href={`/projects/${project.id}`}
      className="group relative flex flex-col gap-3 rounded-2xl border border-[var(--border)]
                 bg-[var(--card)] p-5 hover:shadow-lg hover:border-black/20 dark:hover:border-white/20
                 transition-all duration-200"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="w-10 h-10 rounded-xl bg-[var(--muted)] flex items-center justify-center shrink-0">
          <FolderOpen className="w-5 h-5 text-[var(--muted-foreground)]" />
        </div>
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg hover:bg-red-50
                     dark:hover:bg-red-900/20 text-red-500 transition-all"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      <div>
        <h3 className="font-semibold text-sm">{project.name}</h3>
        {project.description && (
          <p className="text-xs text-[var(--muted-foreground)] mt-0.5 line-clamp-2">
            {project.description}
          </p>
        )}
        {project.context && (
          <p className="text-xs text-[var(--muted-foreground)] italic line-clamp-1 mt-0.5">
            {project.context}
          </p>
        )}
      </div>

      <div className="flex items-center gap-3 text-xs text-[var(--muted-foreground)]">
        {project.website && (
          <span className="flex items-center gap-1 truncate">
            <Globe className="w-3 h-3 shrink-0" />
            {project.website.replace(/^https?:\/\//, "")}
          </span>
        )}
        <span className="ml-auto flex items-center gap-1 shrink-0">
          <Calendar className="w-3 h-3" />
          {new Date(project.created_at).toLocaleDateString()}
        </span>
      </div>

      <div className="flex items-center justify-between text-xs">
        <div className="flex gap-3">
          {project.task_count !== undefined && (
            <span className="text-[var(--muted-foreground)]">{project.task_count} tasks</span>
          )}
          {project.artifact_count !== undefined && (
            <span className="text-[var(--muted-foreground)]">{project.artifact_count} artifacts</span>
          )}
        </div>
        <ChevronRight className="w-4 h-4 text-[var(--muted-foreground)] group-hover:translate-x-0.5 transition-transform" />
      </div>
    </Link>
  )
}

function CreateProjectForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("")
  const [website, setWebsite] = useState("")
  const [description, setDescription] = useState("")
  const [context, setContext] = useState("")
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    await projectsApi.create({
      name,
      website: website || undefined,
      description: description || undefined,
      context: context || undefined,
    })
    onCreated()
    setName(""); setWebsite(""); setDescription(""); setContext("")
    setLoading(false)
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <div>
        <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">
          Project name *
        </label>
        <input
          value={name} onChange={(e) => setName(e.target.value)} required
          placeholder="Acme Corp competitor analysis"
          className="w-full rounded-lg border border-[var(--border)] bg-[var(--muted)]
                     px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white"
        />
      </div>
      <div>
        <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">
          Website (auto-crawled into KB)
        </label>
        <input
          value={website} onChange={(e) => setWebsite(e.target.value)}
          placeholder="https://acme.com"
          className="w-full rounded-lg border border-[var(--border)] bg-[var(--muted)]
                     px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white"
        />
      </div>
      <div>
        <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">
          Description
        </label>
        <textarea
          value={description} onChange={(e) => setDescription(e.target.value)}
          rows={2} placeholder="Context for AI agents…"
          className="w-full rounded-lg border border-[var(--border)] bg-[var(--muted)]
                     px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white resize-none"
        />
      </div>
      <div>
        <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">
          Context (optional)
        </label>
        <textarea
          value={context} onChange={(e) => setContext(e.target.value)}
          rows={2} placeholder="e.g. Focus on BFSI sector competitors…"
          className="w-full rounded-lg border border-[var(--border)] bg-[var(--muted)]
                     px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white resize-none"
        />
      </div>
      <button
        type="submit" disabled={loading || !name}
        className="w-full rounded-lg bg-black dark:bg-white text-white dark:text-black
                   py-2 text-sm font-semibold hover:opacity-80 disabled:opacity-40 transition-opacity"
      >
        {loading ? "Creating…" : "Create Project"}
      </button>
    </form>
  )
}

export default function ProjectsPage() {
  const { data, isLoading } = useSWR<Project[]>(PROJECTS_KEY, fetcher)
  const [showForm, setShowForm] = useState(false)

  const refresh = () => mutate(PROJECTS_KEY)
  const projectCount = (data ?? []).length

  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto">
      <div className="flex items-end justify-between">
        <div>
          <div className="flex items-center gap-3">
            <GradientHeading size="md" weight="bold">Projects</GradientHeading>
            {!isLoading && (
              <span className="px-2 py-0.5 rounded-full text-xs font-semibold
                               bg-[var(--muted)] text-[var(--muted-foreground)] border border-[var(--border)]">
                {projectCount} {projectCount === 1 ? "project" : "projects"}
              </span>
            )}
          </div>
          <p className="text-sm text-[var(--muted-foreground)] mt-1">
            Organise research into projects. Each project has tasks, a knowledge base, and memory.
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-black dark:bg-white
                     text-white dark:text-black text-sm font-semibold hover:opacity-80 transition-opacity"
        >
          <Plus className="w-4 h-4" /> New Project
        </button>
      </div>

      {showForm && (
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 max-w-md">
          <h3 className="font-semibold text-sm mb-4">New Project</h3>
          <CreateProjectForm onCreated={() => { refresh(); setShowForm(false) }} />
        </div>
      )}

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-44 rounded-2xl bg-[var(--muted)] animate-pulse" />
          ))}
        </div>
      ) : (data ?? []).length === 0 ? (
        <div className="rounded-2xl border border-dashed border-[var(--border)] p-16 text-center">
          <FolderOpen className="w-10 h-10 text-[var(--muted-foreground)] mx-auto mb-3" />
          <p className="text-[var(--muted-foreground)] text-sm">No projects yet.</p>
          <button
            onClick={() => setShowForm(true)}
            className="mt-3 text-sm font-semibold underline"
          >
            Create your first project →
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {(data ?? []).map((p) => (
            <ProjectCard key={p.id} project={p} onDelete={refresh} />
          ))}
        </div>
      )}
    </div>
  )
}
