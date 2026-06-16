"use client"

import { useEffect, useState } from "react"
import { cn } from "@/lib/utils"

type Backend = "gemini" | "vllm" | "unknown"
type GovernanceMode = "cloud_ok" | "on_prem_preferred" | "on_prem_required"

const GOV_LABEL: Record<GovernanceMode, string> = {
  cloud_ok:           "Cloud OK",
  on_prem_preferred:  "On-prem Preferred",
  on_prem_required:   "🔒 Sovereign",
}
const GOV_CLASS: Record<GovernanceMode, string> = {
  cloud_ok:           "gov-cloud-ok",
  on_prem_preferred:  "gov-on-prem-preferred",
  on_prem_required:   "gov-on-prem-required",
}

export function Topbar({ title }: { title?: string }) {
  const [backend, setBackend] = useState<Backend>("unknown")
  const [gov, setGov] = useState<GovernanceMode>("cloud_ok")

  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/settings`, {
      credentials: "include",
    })
      .then((r) => r.json())
      .then((d) => {
        setBackend(d?.backend?.default ?? "unknown")
        setGov(d?.governance?.compliance_mode ?? "cloud_ok")
      })
      .catch(() => {})
  }, [])

  return (
    <header className="h-12 flex items-center justify-between px-4
                        border-b border-[var(--border)] bg-[var(--card)]">
      <span className="text-sm font-semibold text-[var(--foreground)] truncate">
        {title ?? "Sentinel"}
      </span>

      <div className="flex items-center gap-2">
        {/* Backend pill */}
        <span className={cn(
          "px-2 py-0.5 rounded text-xs font-mono font-semibold uppercase",
          backend === "vllm"
            ? "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300"
            : "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300"
        )}>
          {backend === "unknown" ? "…" : backend}
        </span>

        {/* Governance badge */}
        <span className={cn(
          "px-2 py-0.5 rounded text-xs font-semibold",
          GOV_CLASS[gov]
        )}>
          {GOV_LABEL[gov]}
        </span>
      </div>
    </header>
  )
}
