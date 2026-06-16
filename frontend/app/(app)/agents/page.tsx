"use client"

import { useState, useMemo } from "react"
import useSWR from "swr"
import { GradientHeading } from "@/components/ui/gradient-heading"
import { TextureCard, TextureCardContent } from "@/components/ui/texture-card"
import { agents as agentsApi, type AgentSpec } from "@/lib/api"
import { Zap, Globe, Lock, Database, Brain, Search, FileText, Bot, Trash2 } from "lucide-react"

const fetcher = (url: string) => fetch(url, { credentials: "include" }).then((r) => r.json())

const CAPABILITY_ICONS: Record<string, React.ReactNode> = {
  web_search:        <Search className="w-3.5 h-3.5" />,
  private_retrieval: <Lock className="w-3.5 h-3.5" />,
  memory_read:       <Brain className="w-3.5 h-3.5" />,
  memory_write:      <Brain className="w-3.5 h-3.5" />,
  kb_search:         <Database className="w-3.5 h-3.5" />,
  report_write:      <FileText className="w-3.5 h-3.5" />,
  public_read:       <Globe className="w-3.5 h-3.5" />,
}

const BOUNDARY_BADGE: Record<string, string> = {
  public_only:  "badge-public",
  private_only: "badge-private",
  both:         "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300 px-2 py-0.5 rounded text-xs font-semibold",
  orchestrator: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300 px-2 py-0.5 rounded text-xs font-semibold",
}

const ROLE_BADGE: Record<string, string> = {
  extractor:    "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  synthesiser:  "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300",
  synthesizer:  "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300",
  grader:       "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300",
  orchestrator: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300",
}

// TextureCard border tints per boundary type — outer className overrides
const BOUNDARY_TEXTURE_CLS: Record<string, string> = {
  public_only:  "border-blue-200 dark:border-blue-800/50",
  private_only: "border-amber-200 dark:border-amber-800/50",
  both:         "",
  orchestrator: "border-purple-200 dark:border-purple-800/50",
}

function EvalBadge({ score }: { score: number }) {
  return (
    <span className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded text-xs font-semibold
                     bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300">
      ★ {score.toFixed(1)}
    </span>
  )
}

function AgentCard({
  agent,
  onToggle,
  onDelete,
}: {
  agent: AgentSpec
  onToggle: () => void
  onDelete: () => void
}) {
  const [toggling, setToggling] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const textureCls = BOUNDARY_TEXTURE_CLS[agent.boundary ?? "both"] ?? ""
  const badgeCls   = BOUNDARY_BADGE[agent.boundary ?? "both"]  ?? BOUNDARY_BADGE.both
  const roleCls    = ROLE_BADGE[agent.role ?? ""] ?? "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300"
  const isCustom   = !agent.name.startsWith("sentinel_")

  async function handleToggle(e: React.MouseEvent) {
    e.preventDefault()
    setToggling(true)
    await agentsApi.update(agent.name, { enabled: !agent.enabled }).catch(() => {})
    onToggle()
    setToggling(false)
  }

  async function handleDelete(e: React.MouseEvent) {
    e.preventDefault()
    if (!confirm(`Delete agent "${agent.name}"? This cannot be undone.`)) return
    setDeleting(true)
    await agentsApi.delete(agent.name).catch(() => {})
    onDelete()
    setDeleting(false)
  }

  return (
    <TextureCard className={`group relative ${textureCls} ${!agent.enabled ? "opacity-60" : ""}`}>
      <TextureCardContent className="p-5 flex flex-col gap-3">
        {/* Top row: icon + name + eval badge + toggle + (optional delete) */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-xl bg-black dark:bg-white flex items-center justify-center shrink-0">
              <Bot className="w-5 h-5 text-white dark:text-black" />
            </div>
            <div>
              <h3 className="font-semibold text-sm">{agent.name}</h3>
              {agent.model && (
                <span className="text-xs text-[var(--muted-foreground)] font-mono">{agent.model}</span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {/* Eval score badge */}
            {agent.eval_score != null && <EvalBadge score={agent.eval_score} />}

            <span className={badgeCls}>{agent.boundary ?? "both"}</span>

            {/* Enable / disable pill toggle */}
            <button
              onClick={handleToggle}
              disabled={toggling}
              title={agent.enabled ? "Disable agent" : "Enable agent"}
              className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold
                          border transition-all select-none
                          ${agent.enabled
                            ? "bg-green-100 border-green-300 text-green-700 dark:bg-green-900/30 dark:border-green-700 dark:text-green-300"
                            : "bg-gray-100 border-gray-300 text-gray-500 dark:bg-gray-800 dark:border-gray-600 dark:text-gray-400"}
                          disabled:opacity-40`}
            >
              {agent.enabled ? "● On" : "○ Off"}
            </button>

            {/* Delete — only for custom agents */}
            {isCustom && (
              <button
                onClick={handleDelete}
                disabled={deleting}
                title="Delete agent"
                className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-red-500
                           hover:bg-red-50 dark:hover:bg-red-900/20 transition-all disabled:opacity-40"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Role badge */}
        {agent.role && (
          <div>
            <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ${roleCls}`}>
              {agent.role}
            </span>
            {!agent.enabled && (
              <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold
                               bg-gray-200 text-gray-500 dark:bg-gray-700 dark:text-gray-400">
                Disabled
              </span>
            )}
          </div>
        )}

        {agent.description && (
          <p className="text-xs text-[var(--muted-foreground)] leading-relaxed">{agent.description}</p>
        )}

        {agent.capabilities && agent.capabilities.length > 0 && (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-2">
              Capabilities
            </p>
            <div className="flex flex-wrap gap-1.5">
              {agent.capabilities.map((cap) => (
                <span key={cap}
                  className="inline-flex items-center gap-1 px-2 py-1 rounded-lg
                             bg-[var(--muted)] text-[var(--muted-foreground)] text-xs font-medium">
                  {CAPABILITY_ICONS[cap] ?? <Zap className="w-3.5 h-3.5" />}
                  {cap.replace(/_/g, " ")}
                </span>
              ))}
            </div>
          </div>
        )}

        {agent.tools && agent.tools.length > 0 && (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-2">
              Tools
            </p>
            <div className="flex flex-wrap gap-1">
              {agent.tools.map((tool) => (
                <code key={tool}
                  className="text-xs bg-[var(--muted)] text-[var(--muted-foreground)]
                             px-2 py-0.5 rounded font-mono">
                  {tool}
                </code>
              ))}
            </div>
          </div>
        )}
      </TextureCardContent>
    </TextureCard>
  )
}

export default function AgentsPage() {
  const { data: agentList, isLoading, mutate } = useSWR<AgentSpec[]>("/api/agents", fetcher)
  const [boundaryFilter, setBoundaryFilter] = useState<string>("all")

  // Derive unique boundary values from the agent list
  const boundaryOptions = useMemo(() => {
    const values = new Set<string>()
    for (const a of agentList ?? []) {
      if (a.boundary) values.add(a.boundary)
    }
    return ["all", ...Array.from(values).sort()]
  }, [agentList])

  const visibleAgents = useMemo(() => {
    if (boundaryFilter === "all") return agentList ?? []
    return (agentList ?? []).filter((a) => a.boundary === boundaryFilter)
  }, [agentList, boundaryFilter])

  return (
    <div className="flex flex-col gap-6 max-w-5xl mx-auto">
      <div>
        <GradientHeading size="md" weight="bold">Agent Roster</GradientHeading>
        <p className="text-sm text-[var(--muted-foreground)] mt-1">
          Sovereign agents with hard-coded boundary enforcement — public tools never touch private data.
        </p>
      </div>

      {/* Legend */}
      <div className="flex gap-4 text-xs text-[var(--muted-foreground)] flex-wrap">
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-sm bg-blue-200 border border-blue-300 inline-block" />
          Public-only agent
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-sm bg-amber-200 border border-amber-300 inline-block" />
          Private-only agent
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-sm bg-purple-200 border border-purple-300 inline-block" />
          Orchestrator
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-sm bg-[var(--muted)] border border-[var(--border)] inline-block" />
          Dual-boundary
        </span>
      </div>

      {/* Boundary filter pills */}
      {!isLoading && boundaryOptions.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {boundaryOptions.map((b) => (
            <button
              key={b}
              onClick={() => setBoundaryFilter(b)}
              className={`px-3 py-1 rounded-full text-xs font-semibold border transition-all
                          ${boundaryFilter === b
                            ? "bg-black text-white border-black dark:bg-white dark:text-black dark:border-white"
                            : "bg-[var(--muted)] text-[var(--muted-foreground)] border-[var(--border)] hover:border-black/40 dark:hover:border-white/40"
                          }`}
            >
              {b === "all" ? "All" : b.replace(/_/g, " ")}
            </button>
          ))}
        </div>
      )}

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-48 rounded-2xl bg-[var(--muted)] animate-pulse" />
          ))}
        </div>
      ) : (agentList ?? []).length === 0 ? (
        <div className="rounded-2xl border border-dashed border-[var(--border)] p-16 text-center">
          <Bot className="w-10 h-10 text-[var(--muted-foreground)] mx-auto mb-3" />
          <p className="text-sm text-[var(--muted-foreground)]">No agents registered.</p>
          <p className="text-xs text-[var(--muted-foreground)] mt-1">
            Agents are defined in the Sentinel backend configuration.
          </p>
        </div>
      ) : visibleAgents.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-[var(--border)] p-12 text-center">
          <p className="text-sm text-[var(--muted-foreground)]">No agents match the selected filter.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {visibleAgents.map((a) => (
            <AgentCard
              key={a.name}
              agent={a}
              onToggle={() => mutate()}
              onDelete={() => mutate()}
            />
          ))}
        </div>
      )}
    </div>
  )
}
