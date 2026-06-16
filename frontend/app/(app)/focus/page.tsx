"use client"

import { useState } from "react"
import useSWR from "swr"
import { GradientHeading } from "@/components/ui/gradient-heading"
import {
  FeatureVotingRoot,
  FeatureVotingGroup,
  FeatureVotingItem,
  FeatureVotingTrigger,
  FeatureVotingCount,
  FeatureVotingTitle,
  FeatureVotingDescription,
} from "@/components/ui/feature-voting"
import { type FocusEntity } from "@/lib/api"
import { Globe, Lock, Target, TrendingUp } from "lucide-react"
import { fetcher } from "@/lib/fetcher"

// Compute tier from run_count since the API does not return tier
function computeTier(runCount: number): "tier1" | "tier2" | "tier3" {
  if (runCount >= 5) return "tier1"
  if (runCount >= 2) return "tier2"
  return "tier3"
}

const TIER_LABELS: Record<string, string> = {
  tier1: "High",
  tier2: "Medium",
  tier3: "Low",
}

const TIER_COLORS: Record<string, string> = {
  tier1: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  tier2: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  tier3: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
}

type ActivityFilter = "all" | "tier1" | "tier2" | "tier3"

export default function FocusPage() {
  const { data: entities, isLoading } = useSWR<FocusEntity[]>(
    "/api/focus",
    fetcher,
    { refreshInterval: 30_000 }
  )

  const [filter, setFilter] = useState<ActivityFilter>("all")

  const filtered = (entities ?? []).filter((e) => {
    if (filter === "all") return true
    return computeTier(e.run_count) === filter
  })

  // FeatureVoting needs a vote map keyed by entity id — use run_count as proxy score
  const defaultVotes = Object.fromEntries(
    (entities ?? []).map((e) => [e.id, e.run_count ?? 0])
  )

  return (
    <div className="flex flex-col gap-6 max-w-7xl mx-auto w-full">
      <div>
        <GradientHeading size="md" weight="bold">Focus Entities</GradientHeading>
        <p className="text-sm text-[var(--muted-foreground)] mt-1">
          Ranked intelligence targets. Upvote to surface high-priority entities across all projects.
        </p>
      </div>

      {/* Filter pills — keyed by run_count bands */}
      <div className="flex gap-2 flex-wrap">
        {(["all", "tier1", "tier2", "tier3"] as const).map((t) => (
          <button key={t} onClick={() => setFilter(t)}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all border
              ${filter === t
                ? "bg-black dark:bg-white text-white dark:text-black border-transparent"
                : "border-[var(--border)] text-[var(--muted-foreground)] hover:border-black/30"
              }`}>
            {t === "all" ? "All" : `${TIER_LABELS[t]} (≥${t === "tier1" ? 5 : t === "tier2" ? 2 : 1} runs)`}
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
          <Target className="w-10 h-10 text-[var(--muted-foreground)] mx-auto mb-3" />
          <p className="text-sm text-[var(--muted-foreground)]">No focus entities yet.</p>
          <p className="text-xs text-[var(--muted-foreground)] mt-1">
            Run a research task to populate entities automatically.
          </p>
        </div>
      ) : (
        <FeatureVotingRoot defaultValue={defaultVotes}>
          <FeatureVotingGroup sortBy="votes-desc">
            {filtered.map((entity) => {
              const tier = computeTier(entity.run_count)
              return (
                <FeatureVotingItem key={entity.id} value={entity.id}>
                  <div className="flex items-start gap-4 p-4 rounded-2xl border border-[var(--border)]
                                  bg-[var(--card)] hover:shadow-sm transition-shadow">
                    <FeatureVotingTrigger className="flex flex-col items-center gap-1 shrink-0 min-w-[48px]
                      rounded-xl border border-[var(--border)] p-2 hover:bg-[var(--muted)]
                      data-[voted=true]:bg-black data-[voted=true]:text-white
                      dark:data-[voted=true]:bg-white dark:data-[voted=true]:text-black transition-all">
                      <TrendingUp className="w-4 h-4" />
                      <FeatureVotingCount className="text-xs font-bold tabular-nums" />
                    </FeatureVotingTrigger>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <FeatureVotingTitle className="font-semibold text-sm">
                          {entity.name}
                        </FeatureVotingTitle>
                        {/* Tier badge computed from run_count */}
                        <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${TIER_COLORS[tier]}`}>
                          {TIER_LABELS[tier]}
                        </span>
                        {/* Run count display */}
                        <span className="text-xs px-2 py-0.5 rounded-full bg-[var(--muted)] text-[var(--muted-foreground)]">
                          {entity.run_count} {entity.run_count === 1 ? "run" : "runs"}
                        </span>
                        {entity.type && (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-[var(--muted)] text-[var(--muted-foreground)]">
                            {entity.type}
                          </span>
                        )}
                      </div>
                      {entity.description && (
                        <FeatureVotingDescription className="text-xs text-[var(--muted-foreground)] mt-1 line-clamp-2">
                          {entity.description}
                        </FeatureVotingDescription>
                      )}
                      <div className="flex items-center gap-3 mt-2 text-xs text-[var(--muted-foreground)]">
                        {entity.public_findings !== undefined && (
                          <span className="flex items-center gap-1">
                            <Globe className="w-3 h-3 text-blue-400" /> {entity.public_findings}
                          </span>
                        )}
                        {entity.private_signals !== undefined && (
                          <span className="flex items-center gap-1">
                            <Lock className="w-3 h-3 text-amber-400" /> {entity.private_signals}
                          </span>
                        )}
                        {entity.last_researched && (
                          <span className="ml-auto">
                            Last: {new Date(entity.last_researched).toLocaleDateString()}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </FeatureVotingItem>
              )
            })}
          </FeatureVotingGroup>
        </FeatureVotingRoot>
      )}
    </div>
  )
}
