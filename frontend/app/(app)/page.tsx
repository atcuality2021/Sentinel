"use client"

import { useMemo } from "react"
import useSWR from "swr"
import Link from "next/link"
import { AnimatedNumber } from "@/components/ui/animated-number"
import { GradientHeading } from "@/components/ui/gradient-heading"
import { TextureCard, TextureCardContent } from "@/components/ui/texture-card"
import {
  type DashboardData, type RunRecord, type Project, type Artifact,
} from "@/lib/api"
import {
  Clock, Globe, Lock, AlertTriangle, RefreshCw, FolderOpen,
  Play, CheckCircle2, Loader2, ArrowRight, Plus, FileText, Zap,
} from "lucide-react"
import { fetcher } from "@/lib/fetcher"

// ── Domain colour map ─────────────────────────────────────────────────────────
const DOMAIN_COLORS: Record<string, string> = {
  market:           "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  software:         "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300",
  finance:          "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300",
  academic:         "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  product_research: "bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-300",
  travel:           "bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300",
  nutrition:        "bg-lime-100 text-lime-700 dark:bg-lime-900/30 dark:text-lime-300",
  govt_proposal:    "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300",
  orchestrated:     "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
}

// ── Project card ──────────────────────────────────────────────────────────────
function ProjectCard({ project, runs }: { project: Project; runs: RunRecord[] }) {
  const projectRuns = runs.filter((r) => r.project_id === project.id)
  const lastRun = projectRuns[0]
  const findings = projectRuns.reduce((s, r) => s + (r.public || 0) + (r.private || 0), 0)

  return (
    <Link href={`/projects/${project.id}`}>
      <TextureCard className="group h-full hover:shadow-md transition-all cursor-pointer">
        <TextureCardContent className="p-4 flex flex-col gap-3">
          {/* Icon + name */}
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-400 to-violet-500
                            flex items-center justify-center text-white font-bold text-sm shrink-0">
              {project.name.charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0">
              <p className="font-semibold text-sm truncate group-hover:text-blue-500 dark:group-hover:text-blue-400 transition-colors">
                {project.name}
              </p>
              {project.description && (
                <p className="text-xs text-[var(--muted-foreground)] line-clamp-1 mt-0.5">
                  {project.description}
                </p>
              )}
            </div>
          </div>

          {/* Stats row */}
          <div className="flex items-center gap-3 text-xs text-[var(--muted-foreground)]">
            <span className="flex items-center gap-1">
              <Play className="w-3 h-3" /> {projectRuns.length} run{projectRuns.length !== 1 ? "s" : ""}
            </span>
            {findings > 0 && (
              <span className="flex items-center gap-1">
                <Globe className="w-3 h-3 text-blue-400" /> {findings} findings
              </span>
            )}
            {lastRun && (
              <span className="ml-auto flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {new Date(lastRun.created_at).toLocaleDateString()}
              </span>
            )}
          </div>

          {/* Website pill */}
          {project.website && (
            <span className="self-start text-[10px] px-2 py-0.5 rounded-full bg-[var(--muted)]
                             text-[var(--muted-foreground)] truncate max-w-full">
              {project.website.replace(/^https?:\/\//, "")}
            </span>
          )}

          {/* Arrow */}
          <div className="flex justify-end mt-auto">
            <ArrowRight className="w-3.5 h-3.5 text-[var(--muted-foreground)] opacity-0
                                    group-hover:opacity-100 transition-all" />
          </div>
        </TextureCardContent>
      </TextureCard>
    </Link>
  )
}

// ── Recent run row (activity feed) ────────────────────────────────────────────
function RunRow({ run, projectName }: { run: RunRecord; projectName?: string }) {
  const label = run.target?.trim() || run.entity || "Research run"
  // Derive a cleaner mode label
  const domain = run.mode === "orchestrated" ? "research" : run.mode
  const domainCls = DOMAIN_COLORS[run.mode] ?? DOMAIN_COLORS.orchestrated
  // Backend: simplify "v11k"/"v21k" → "Local AI", "gemini" → "Gemini"
  const backendLabel = run.backend?.startsWith("v") ? "Local AI"
    : run.backend === "gemini" ? "Gemini"
    : run.backend ?? "AI"

  return (
    <Link href={run.project_id ? `/projects/${run.project_id}` : "#"}>
      <div className="flex items-start gap-3 px-4 py-3 rounded-xl border border-[var(--border)]
                      bg-[var(--card)] hover:border-black/10 dark:hover:border-white/10
                      hover:shadow-sm transition-all cursor-pointer group">
        {/* Icon */}
        <div className="w-7 h-7 rounded-lg bg-[var(--muted)] flex items-center justify-center shrink-0 mt-0.5">
          <FileText className="w-3.5 h-3.5 text-[var(--muted-foreground)]" />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate group-hover:text-blue-500
                        dark:group-hover:text-blue-400 transition-colors">
            {label}
          </p>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            {projectName && (
              <span className="text-xs text-[var(--muted-foreground)]">{projectName}</span>
            )}
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold capitalize ${domainCls}`}>
              {domain}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--muted)] text-[var(--muted-foreground)]">
              {backendLabel}
            </span>
          </div>
        </div>

        {/* Right side */}
        <div className="flex flex-col items-end gap-1 shrink-0">
          <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
            {run.public > 0 && (
              <span className="flex items-center gap-0.5">
                <Globe className="w-3 h-3 text-blue-400" /> {run.public}
              </span>
            )}
            {run.private > 0 && (
              <span className="flex items-center gap-0.5">
                <Lock className="w-3 h-3 text-amber-400" /> {run.private}
              </span>
            )}
            {run.gaps > 0 && (
              <span className="flex items-center gap-0.5 text-red-400">
                <AlertTriangle className="w-3 h-3" /> {run.gaps}
              </span>
            )}
          </div>
          <span className="text-[10px] text-[var(--muted-foreground)]">
            {new Date(run.created_at).toLocaleDateString()}
          </span>
        </div>
      </div>
    </Link>
  )
}

// ── KPI tile ──────────────────────────────────────────────────────────────────
function KPITile({
  label, value, sub, icon: Icon, color, href,
}: {
  label: string; value: number; sub?: string
  icon: React.ElementType; color: string; href?: string
}) {
  const inner = (
    <TextureCard className={`h-full ${href ? "hover:shadow-lg transition-all cursor-pointer" : ""}`}>
      <TextureCardContent className="p-5 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
            {label}
          </span>
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${color}`}>
            <Icon className="w-4 h-4" />
          </div>
        </div>
        <div>
          <AnimatedNumber value={value} className="text-3xl font-bold tabular-nums" />
          {sub && <p className="text-xs text-[var(--muted-foreground)] mt-0.5">{sub}</p>}
        </div>
      </TextureCardContent>
    </TextureCard>
  )
  return href ? <Link href={href}>{inner}</Link> : inner
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const { data, isLoading, error, mutate } = useSWR<DashboardData>(
    "/api/dashboard",
    fetcher,
    { refreshInterval: 30_000 },
  )
  const { data: projectList } = useSWR<Project[]>("/api/projects", fetcher, { refreshInterval: 60_000 })

  // Build a project name lookup for enriching run rows
  const projectMap = useMemo(() => {
    const m: Record<string, string> = {}
    ;(projectList ?? []).forEach((p) => { m[p.id] = p.name })
    return m
  }, [projectList])

  const runs = data?.recent_runs ?? []
  const projects = projectList ?? []

  // Deduplicate runs by entity+project to avoid repeated "E2E Gemma Suite" rows
  const dedupedRuns = useMemo(() => {
    const seen = new Set<string>()
    return runs.filter((r) => {
      const key = `${r.project_id ?? ""}:${r.entity}:${r.target ?? ""}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    }).slice(0, 12)
  }, [runs])

  const hasFindings = (data?.total_public_findings ?? 0) + (data?.total_private_findings ?? 0) > 0

  return (
    <div className="flex flex-col gap-8 max-w-7xl mx-auto w-full">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <GradientHeading size="md" weight="bold">Intelligence Dashboard</GradientHeading>
          <p className="text-sm text-[var(--muted-foreground)] mt-1">
            Sovereign AI research — public / private boundary enforced at every layer.
          </p>
        </div>
        <Link
          href="/projects"
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-black dark:bg-white
                     text-white dark:text-black text-sm font-semibold hover:opacity-80 transition-opacity"
        >
          <Plus className="w-4 h-4" /> New Project
        </Link>
      </div>

      {/* Error banner */}
      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 dark:bg-red-900/20 dark:border-red-800
                        px-4 py-3 flex items-center gap-2 text-sm text-red-700 dark:text-red-400">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          Backend unreachable — check that the Sentinel server is running on port 8094.
          <button onClick={() => mutate()}
            className="ml-auto text-xs font-semibold underline hover:no-underline">
            Retry
          </button>
        </div>
      )}

      {/* KPI row — actionable metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPITile
          label="Projects"
          value={projects.length}
          sub="active workspaces"
          icon={FolderOpen}
          color="bg-blue-100 text-blue-700"
          href="/projects"
        />
        <KPITile
          label="Research Runs"
          value={data?.total_runs ?? 0}
          sub="total executions"
          icon={Play}
          color="bg-violet-100 text-violet-700"
        />
        <KPITile
          label="Public Findings"
          value={data?.total_public_findings ?? 0}
          sub="open-source intelligence"
          icon={Globe}
          color="bg-green-100 text-green-700"
        />
        <KPITile
          label="Private Signals"
          value={data?.total_private_findings ?? 0}
          sub="proprietary intelligence"
          icon={Lock}
          color="bg-amber-100 text-amber-700"
        />
      </div>

      {/* Projects section */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
            Your Projects
          </h2>
          <Link href="/projects"
            className="text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]
                       flex items-center gap-1 transition-colors">
            View all <ArrowRight className="w-3 h-3" />
          </Link>
        </div>

        {projects.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-[var(--border)] p-12 text-center">
            <FolderOpen className="w-10 h-10 text-[var(--muted-foreground)] mx-auto mb-3" />
            <p className="text-sm text-[var(--muted-foreground)] mb-3">
              No projects yet. Create one to start your research.
            </p>
            <Link href="/projects"
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-black dark:bg-white
                         text-white dark:text-black text-sm font-semibold hover:opacity-80 transition-opacity">
              <Plus className="w-4 h-4" /> Create First Project
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {projects.slice(0, 6).map((p) => (
              <ProjectCard key={p.id} project={p} runs={runs} />
            ))}
            {projects.length > 6 && (
              <Link href="/projects">
                <div className="h-full rounded-2xl border border-dashed border-[var(--border)]
                                flex items-center justify-center p-6 hover:border-black/20
                                dark:hover:border-white/20 transition-all group cursor-pointer">
                  <span className="text-sm text-[var(--muted-foreground)] group-hover:text-[var(--foreground)]
                                   flex items-center gap-1.5 transition-colors">
                    +{projects.length - 6} more <ArrowRight className="w-3.5 h-3.5" />
                  </span>
                </div>
              </Link>
            )}
          </div>
        )}
      </div>

      {/* Finding provenance — only show when both sides have data */}
      {hasFindings && (data?.total_private_findings ?? 0) > 0 && (
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-3">
            Finding Provenance
          </p>
          <div className="flex h-2.5 rounded-full overflow-hidden bg-[var(--muted)]">
            {(() => {
              const total = (data?.total_public_findings ?? 0) + (data?.total_private_findings ?? 0)
              const pubPct = Math.round(((data?.total_public_findings ?? 0) / total) * 100)
              return (
                <>
                  <div className="bg-blue-400 rounded-l-full transition-all" style={{ width: `${pubPct}%` }} />
                  <div className="bg-amber-400 rounded-r-full transition-all" style={{ width: `${100 - pubPct}%` }} />
                </>
              )
            })()}
          </div>
          <div className="flex items-center gap-4 mt-2 text-xs text-[var(--muted-foreground)]">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-blue-400" />
              Public ({data?.total_public_findings})
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-amber-400" />
              Private ({data?.total_private_findings})
            </span>
          </div>
        </div>
      )}

      {/* Recent activity feed */}
      <div>
        <div className="flex items-center gap-3 mb-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
            Recent Activity
          </h2>
          <span className="flex items-center gap-1 text-xs text-[var(--muted-foreground)]
                           bg-[var(--muted)] px-2 py-0.5 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
            Live · 30s
          </span>
          <button onClick={() => mutate()} title="Refresh"
            className="ml-auto p-1.5 rounded-lg hover:bg-[var(--muted)] text-[var(--muted-foreground)] transition-colors">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>

        {isLoading ? (
          <div className="flex flex-col gap-2">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-16 rounded-xl bg-[var(--muted)] animate-pulse" />
            ))}
          </div>
        ) : dedupedRuns.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-[var(--border)] p-10 text-center">
            <Zap className="w-8 h-8 text-[var(--muted-foreground)] mx-auto mb-2" />
            <p className="text-sm text-[var(--muted-foreground)]">
              No runs yet — create a project and run your first research task.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {dedupedRuns.map((run) => (
              <RunRow key={run.id} run={run} projectName={projectMap[run.project_id ?? ""]} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
