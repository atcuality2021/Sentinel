"use client"

import useSWR from "swr"
import Link from "next/link"
import { AnimatedNumber } from "@/components/ui/animated-number"
import { GradientHeading } from "@/components/ui/gradient-heading"
import { type DashboardData, type RunRecord } from "@/lib/api"
import { Clock, Globe, Lock, AlertTriangle, RefreshCw } from "lucide-react"

const fetcher = (url: string) =>
  fetch(url, { credentials: "include" }).then((r) => r.json())

function RunCard({ run }: { run: RunRecord }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4 flex flex-col gap-2
                    hover:shadow-md transition-shadow cursor-pointer">
      <div className="flex items-start justify-between gap-2">
        <span className="font-semibold text-sm truncate">{run.target || run.entity}</span>
        <span className={`shrink-0 text-xs px-2 py-0.5 rounded font-semibold uppercase
          ${run.mode === "competitor" ? "bg-purple-100 text-purple-700" : "bg-blue-100 text-blue-700"}`}>
          {run.mode}
        </span>
      </div>
      <div className="flex items-center gap-3 text-xs text-[var(--muted-foreground)]">
        <span className="flex items-center gap-1">
          <Globe className="w-3 h-3 text-blue-500" /> {run.public}
        </span>
        <span className="flex items-center gap-1">
          <Lock className="w-3 h-3 text-amber-500" /> {run.private}
        </span>
        {run.gaps > 0 && (
          <span className="flex items-center gap-1 text-red-500">
            <AlertTriangle className="w-3 h-3" /> {run.gaps}
          </span>
        )}
        <span className="ml-auto flex items-center gap-1">
          <Clock className="w-3 h-3" />
          {new Date(run.created_at).toLocaleDateString()}
        </span>
      </div>
      <div className="flex items-center gap-1.5 mt-1">
        <span className={`text-xs px-1.5 py-0.5 rounded font-mono
          ${run.backend === "vllm" ? "bg-purple-50 text-purple-600" : "bg-gray-100 text-gray-600"}`}>
          {run.backend}
        </span>
      </div>
    </div>
  )
}

function KPICard({
  label, value, icon: Icon, color,
}: {
  label: string
  value: number
  icon: React.ElementType
  color: string
}) {
  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
          {label}
        </span>
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${color}`}>
          <Icon className="w-4 h-4" />
        </div>
      </div>
      <AnimatedNumber
        value={value}
        className="text-3xl font-bold tabular-nums"
      />
    </div>
  )
}

export default function DashboardPage() {
  const { data, isLoading, error, mutate } = useSWR<DashboardData>(
    "/api/dashboard",
    fetcher,
    { refreshInterval: 30_000 }
  )

  const kpis = [
    { label: "Total Runs",     value: data?.total_runs ?? 0,             icon: Clock,        color: "bg-gray-100 text-gray-700" },
    { label: "Artifacts",      value: data?.total_artifacts ?? 0,        icon: Globe,        color: "bg-blue-100 text-blue-700" },
    { label: "Public Findings",value: data?.total_public_findings ?? 0,  icon: Globe,        color: "bg-blue-100 text-blue-600" },
    { label: "Private Signals",value: data?.total_private_findings ?? 0, icon: Lock,         color: "bg-amber-100 text-amber-600" },
  ]

  return (
    <div className="flex flex-col gap-8 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <GradientHeading size="md" weight="bold">
            Intelligence Dashboard
          </GradientHeading>
          <p className="text-sm text-[var(--muted-foreground)] mt-1">
            Sovereign research — public/private boundary enforced at the tool layer.
          </p>
        </div>
        <a
          href="/projects"
          className="px-4 py-2 rounded-lg bg-black dark:bg-white text-white dark:text-black
                     text-sm font-semibold hover:opacity-80 transition-opacity"
        >
          New Project
        </a>
      </div>

      {/* Error banner */}
      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 dark:bg-red-900/20 dark:border-red-800
                        px-4 py-3 flex items-center gap-2 text-sm text-red-700 dark:text-red-400">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          Failed to load dashboard data. Check that the backend is running.
          <button
            onClick={() => mutate()}
            className="ml-auto text-xs font-semibold underline hover:no-underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {kpis.map((k) => (
          <KPICard key={k.label} {...k} />
        ))}
      </div>

      {/* Provenance bar */}
      {data && (data.total_public_findings + data.total_private_findings) > 0 && (
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-3">
            Finding Provenance
          </p>
          <div className="flex h-3 rounded-full overflow-hidden gap-0.5">
            {(() => {
              const total = data.total_public_findings + data.total_private_findings
              const pubPct = Math.round((data.total_public_findings / total) * 100)
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
              <span className="w-2.5 h-2.5 rounded-full bg-blue-400 inline-block" />
              Public ({data.total_public_findings})
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-400 inline-block" />
              Private ({data.total_private_findings})
            </span>
          </div>
        </div>
      )}

      {/* Recent Activity */}
      <div>
        <div className="flex items-center gap-3 mb-3">
          <h2 className="text-sm font-semibold text-[var(--muted-foreground)] uppercase tracking-wider">
            Recent Activity
          </h2>
          <span className="flex items-center gap-1 text-xs text-[var(--muted-foreground)] bg-[var(--muted)]
                           px-2 py-0.5 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-green-400 inline-block animate-pulse" />
            Live · refreshes every 30s
          </span>
          <button
            onClick={() => mutate()}
            title="Refresh now"
            className="ml-auto p-1.5 rounded-lg hover:bg-[var(--muted)] text-[var(--muted-foreground)]
                       transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-28 rounded-xl bg-[var(--muted)] animate-pulse" />
            ))}
          </div>
        ) : (data?.recent_runs ?? []).length === 0 ? (
          <div className="rounded-2xl border border-dashed border-[var(--border)] p-12 text-center">
            <p className="text-[var(--muted-foreground)] text-sm">No runs yet.</p>
            <a href="/projects" className="mt-3 inline-block text-sm font-semibold underline">
              Create your first project →
            </a>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {(data?.recent_runs ?? []).map((run) => (
              <Link
                key={run.id}
                href={run.project_id ? `/projects/${run.project_id}` : "#"}
                className="block"
              >
                <RunCard run={run} />
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
