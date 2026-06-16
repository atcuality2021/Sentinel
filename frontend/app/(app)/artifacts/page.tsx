"use client"

import { useState } from "react"
import useSWR from "swr"
import Link from "next/link"
import { GradientHeading } from "@/components/ui/gradient-heading"
import { CodeBlock } from "@/components/ui/code-block"
import { type Artifact } from "@/lib/api"
import { Globe, Lock, AlertTriangle, FileText, Download, ChevronDown, ChevronUp, Calendar } from "lucide-react"

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
const fetcher = (url: string) => fetch(url, { credentials: "include" }).then((r) => r.json())

const TYPE_COLORS: Record<string, string> = {
  battlecard:   "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300",
  accountbrief: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  report:       "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300",
  summary:      "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
}

function ArtifactRow({ artifact }: { artifact: Artifact }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-4 p-4 hover:bg-[var(--muted)]/50 transition-colors text-left"
      >
        <div className="w-9 h-9 rounded-xl bg-[var(--muted)] flex items-center justify-center shrink-0">
          <FileText className="w-4.5 h-4.5 text-[var(--muted-foreground)]" />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-sm truncate">{artifact.target}</span>
            <span className={`text-xs px-2 py-0.5 rounded font-semibold capitalize shrink-0
              ${TYPE_COLORS[artifact.type] ?? TYPE_COLORS.summary}`}>
              {artifact.type}
            </span>
          </div>
          <div className="flex items-center gap-3 mt-1 text-xs text-[var(--muted-foreground)]">
            <span className="flex items-center gap-1">
              <Globe className="w-3 h-3 text-blue-400" /> {artifact.public_count}
            </span>
            <span className="flex items-center gap-1">
              <Lock className="w-3 h-3 text-amber-400" /> {artifact.private_count}
            </span>
            {artifact.gaps > 0 && (
              <span className="flex items-center gap-1 text-red-400">
                <AlertTriangle className="w-3 h-3" /> {artifact.gaps}
              </span>
            )}
            <span className="flex items-center gap-1 ml-auto">
              <Calendar className="w-3 h-3" />
              {new Date(artifact.created_at).toLocaleDateString()}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {artifact.project_id && (
            <Link href={`/projects/${artifact.project_id}`}
              onClick={(e) => e.stopPropagation()}
              className="text-xs text-blue-500 hover:underline hidden sm:block">
              View project
            </Link>
          )}
          <a href={`${API}/api/artifacts/${artifact.id}/export`}
            target="_blank" rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="p-1.5 rounded-lg hover:bg-[var(--muted)] text-[var(--muted-foreground)]">
            <Download className="w-3.5 h-3.5" />
          </a>
          {expanded
            ? <ChevronUp className="w-4 h-4 text-[var(--muted-foreground)]" />
            : <ChevronDown className="w-4 h-4 text-[var(--muted-foreground)]" />}
        </div>
      </button>

      {expanded && artifact.content && (
        <div className="px-4 pb-4 pt-0 border-t border-[var(--border)]">
          <div className="mt-4 flex flex-col gap-4">
            {Object.entries(artifact.content).map(([key, val]) => {
              if (!val || (Array.isArray(val) && val.length === 0)) return null
              return (
                <div key={key}>
                  <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-2">
                    {key.replace(/_/g, " ")}
                  </p>
                  {Array.isArray(val) ? (
                    <ul className="flex flex-col gap-1">
                      {(val as string[]).map((item, i) => (
                        <li key={i} className="text-sm flex items-start gap-2">
                          <span className="text-[var(--muted-foreground)] mt-0.5 shrink-0">·</span>
                          {item}
                        </li>
                      ))}
                    </ul>
                  ) : typeof val === "object" ? (
                    <CodeBlock
                      code={JSON.stringify(val, null, 2)}
                      language="json"
                      className="text-xs"
                    />
                  ) : (
                    <p className="text-sm leading-relaxed">{String(val)}</p>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

export default function ArtifactsPage() {
  const { data: artifacts, isLoading } = useSWR<Artifact[]>(`${API}/api/artifacts`, fetcher)
  const [filter, setFilter] = useState<string>("all")

  const types = ["all", ...Array.from(new Set((artifacts ?? []).map((a) => a.type)))]
  const filtered = filter === "all" ? (artifacts ?? []) : (artifacts ?? []).filter((a) => a.type === filter)

  return (
    <div className="flex flex-col gap-6 max-w-5xl mx-auto">
      <div>
        <GradientHeading size="md" weight="bold">Artifacts</GradientHeading>
        <p className="text-sm text-[var(--muted-foreground)] mt-1">
          All research outputs across every project — battlecards, account briefs, and reports.
        </p>
      </div>

      {/* Type filter */}
      <div className="flex gap-2 flex-wrap">
        {types.map((t) => (
          <button key={t} onClick={() => setFilter(t)}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all border capitalize
              ${filter === t
                ? "bg-black dark:bg-white text-white dark:text-black border-transparent"
                : "border-[var(--border)] text-[var(--muted-foreground)] hover:border-black/30"
              }`}>
            {t}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-20 rounded-2xl bg-[var(--muted)] animate-pulse" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-[var(--border)] p-16 text-center">
          <FileText className="w-10 h-10 text-[var(--muted-foreground)] mx-auto mb-3" />
          <p className="text-sm text-[var(--muted-foreground)]">No artifacts yet.</p>
          <p className="text-xs text-[var(--muted-foreground)] mt-1">
            Run a research task to generate battlecards and account briefs.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {filtered.map((a) => (
            <ArtifactRow key={a.id} artifact={a} />
          ))}
        </div>
      )}
    </div>
  )
}
