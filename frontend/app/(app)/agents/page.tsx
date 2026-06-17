"use client"

import { useState, useMemo } from "react"
import useSWR from "swr"
import { GradientHeading } from "@/components/ui/gradient-heading"
import {
  agents as agentsApi, settings as settingsApi,
  type AgentSpec, type FlatSentinelConfig,
} from "@/lib/api"
import { fetcher } from "@/lib/fetcher"
import { Plus, ChevronDown, ChevronUp } from "lucide-react"

// ── Feature flag toggle ───────────────────────────────────────────────────────

function FlagToggle({
  label, value, onChange, disabled,
}: {
  label: string
  value: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
}) {
  return (
    <div className="flex items-center justify-between px-4 py-3 rounded-xl border border-[var(--border)] bg-[var(--card)] min-w-[160px]">
      <span className="text-sm font-medium">{label}</span>
      <button
        onClick={() => !disabled && onChange(!value)}
        disabled={disabled}
        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors duration-200
                    focus:outline-none disabled:opacity-40
                    ${value ? "bg-black dark:bg-white" : "bg-[var(--muted)]"}`}
      >
        <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white dark:bg-black shadow
                          transform transition-transform duration-200
                          ${value ? "translate-x-[18px]" : "translate-x-[2px]"}`} />
        <span className="sr-only">{value ? "ON" : "OFF"}</span>
      </button>
      <span className={`text-xs font-semibold ml-2 w-7 ${value ? "text-[var(--foreground)]" : "text-[var(--muted-foreground)]"}`}>
        {value ? "ON" : "OFF"}
      </span>
    </div>
  )
}

// ── Inline edit row ───────────────────────────────────────────────────────────

const ROLES = ["extractor", "synthesizer", "planner", "orchestrator", "grader", "public_research", "private_research"]
const MODELS = ["default", "gemma-4-12b-it", "gemma-4-27b-it", "gemini-2.0-flash", "gemini-2.5-pro"]

function AgentEditRow({
  agent,
  onSaved,
  onCancel,
}: {
  agent: AgentSpec
  onSaved: () => void
  onCancel: () => void
}) {
  const [model, setModel]  = useState(agent.model ?? "default")
  const [role, setRole]    = useState(agent.role ?? "extractor")
  const [temp, setTemp]    = useState("0.2")
  const [maxTok, setMaxTok] = useState("2048")
  const [enabled, setEnabled] = useState(agent.enabled)
  const [saving, setSaving] = useState(false)

  const inputCls =
    "rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-1.5 text-sm " +
    "outline-none focus:ring-1 focus:ring-black dark:focus:ring-white w-full"

  async function handleSave() {
    setSaving(true)
    try {
      await agentsApi.update(agent.name, {
        enabled,
        model: model === "default" ? undefined : model,
        role,
        generation: { temperature: parseFloat(temp) || 0.2, max_output_tokens: parseInt(maxTok) || 2048 },
      })
      onSaved()
    } catch { /* ignore */ }
    setSaving(false)
  }

  return (
    <tr className="bg-[var(--muted)]/40">
      <td colSpan={6} className="px-4 py-3">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div>
            <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Model</label>
            <select value={model} onChange={(e) => setModel(e.target.value)} className={inputCls}>
              <option value="default">default (from Settings)</option>
              {MODELS.filter((m) => m !== "default").map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Role</label>
            <select value={role} onChange={(e) => setRole(e.target.value)} className={inputCls}>
              {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Temperature</label>
            <input type="number" step="0.05" min="0" max="2" value={temp}
              onChange={(e) => setTemp(e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Max tokens</label>
            <input type="number" step="256" min="256" value={maxTok}
              onChange={(e) => setMaxTok(e.target.value)} className={inputCls} />
          </div>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)}
              className="w-4 h-4 rounded border-[var(--border)]" />
            <span className="text-sm">Enabled</span>
          </label>
          <button onClick={handleSave} disabled={saving}
            className="px-4 py-1.5 rounded-lg bg-black dark:bg-white text-white dark:text-black
                       text-sm font-semibold hover:opacity-80 disabled:opacity-40 transition-opacity">
            {saving ? "Saving…" : "Save"}
          </button>
          <button onClick={onCancel}
            className="px-3 py-1.5 rounded-lg border border-[var(--border)] text-sm hover:bg-[var(--muted)] transition-colors">
            Cancel
          </button>
        </div>
      </td>
    </tr>
  )
}

// ── Agent table row ───────────────────────────────────────────────────────────

const ROLE_CLS: Record<string, string> = {
  extractor:     "bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300",
  synthesizer:   "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300",
  planner:       "bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300",
  orchestrator:  "bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300",
  grader:        "bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300",
  public_research: "bg-sky-100 dark:bg-sky-900/30 text-sky-700 dark:text-sky-300",
}

function AgentRow({
  agent,
  expanded,
  onToggleExpand,
  onSaved,
  onToggle,
}: {
  agent: AgentSpec
  expanded: boolean
  onToggleExpand: () => void
  onSaved: () => void
  onToggle: () => void
}) {
  const roleCls = ROLE_CLS[agent.role ?? ""] ?? "bg-[var(--muted)] text-[var(--muted-foreground)]"

  async function handleToggle(e: React.MouseEvent) {
    e.stopPropagation()
    await agentsApi.update(agent.name, { enabled: !agent.enabled, role: agent.role ?? "extractor" }).catch(() => {})
    onToggle()
  }

  return (
    <>
      <tr
        className={`border-b border-[var(--border)] hover:bg-[var(--muted)]/30 transition-colors cursor-pointer
                    ${!agent.enabled ? "opacity-50" : ""}`}
        onClick={onToggleExpand}
      >
        <td className="px-4 py-2.5">
          <span className="text-sm font-mono">{agent.name}</span>
        </td>
        <td className="px-4 py-2.5">
          <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold uppercase ${roleCls}`}>
            {agent.role ?? "—"}
          </span>
        </td>
        <td className="px-4 py-2.5 text-sm text-[var(--muted-foreground)] font-mono">
          {agent.model ?? "default"}
        </td>
        <td className="px-4 py-2.5 text-sm text-[var(--muted-foreground)]">0.2</td>
        <td className="px-4 py-2.5">
          <button
            onClick={handleToggle}
            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors duration-200
                        ${agent.enabled ? "bg-black dark:bg-white" : "bg-[var(--muted)]"}`}
          >
            <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white dark:bg-black shadow
                              transform transition-transform duration-200
                              ${agent.enabled ? "translate-x-[18px]" : "translate-x-[2px]"}`} />
          </button>
        </td>
        <td className="px-4 py-2.5 text-right">
          <button
            onClick={(e) => { e.stopPropagation(); onToggleExpand() }}
            className="px-3 py-1 rounded-lg border border-[var(--border)] text-xs hover:bg-[var(--muted)] transition-colors"
          >
            {expanded ? "Close" : "Edit"}
          </button>
        </td>
      </tr>
      {expanded && (
        <AgentEditRow
          agent={agent}
          onSaved={() => { onSaved(); }}
          onCancel={onToggleExpand}
        />
      )}
    </>
  )
}

// ── Add custom agent form ─────────────────────────────────────────────────────

function AddAgentForm({ onSaved, onCancel }: { onSaved: () => void; onCancel: () => void }) {
  const [name, setName]       = useState("")
  const [capability, setCap]  = useState("")
  const [role, setRole]       = useState("extractor")
  const [saving, setSaving]   = useState(false)
  const [error, setError]     = useState<string | null>(null)

  const inputCls =
    "rounded-lg border border-[var(--border)] bg-[var(--muted)] px-3 py-2 text-sm " +
    "outline-none focus:ring-2 focus:ring-black dark:focus:ring-white w-full"

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setSaving(true)
    setError(null)
    try {
      await agentsApi.create({ name, capability, role, enabled: true })
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 max-w-xl">
      <h3 className="text-sm font-semibold mb-4">Add custom agent</h3>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Name *</label>
            <input value={name} onChange={(e) => setName(e.target.value)} required
              placeholder="my_extractor" className={inputCls} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Capability</label>
            <input value={capability} onChange={(e) => setCap(e.target.value)}
              placeholder="e.g. self_profile" className={inputCls} />
          </div>
        </div>
        <div>
          <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Role</label>
          <select value={role} onChange={(e) => setRole(e.target.value)} className={inputCls}>
            {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <div className="flex gap-2">
          <button type="submit" disabled={saving || !name.trim()}
            className="flex-1 rounded-lg bg-black dark:bg-white text-white dark:text-black
                       py-2 text-sm font-semibold hover:opacity-80 disabled:opacity-40 transition-opacity">
            {saving ? "Saving…" : "Add agent"}
          </button>
          <button type="button" onClick={onCancel}
            className="px-4 rounded-lg border border-[var(--border)] text-sm hover:bg-[var(--muted)] transition-colors">
            Cancel
          </button>
        </div>
      </form>
    </div>
  )
}

// ── Domain group ──────────────────────────────────────────────────────────────

function DomainGroup({
  domain,
  agents,
  expandedId,
  onToggleExpand,
  onRefresh,
}: {
  domain: string
  agents: AgentSpec[]
  expandedId: string | null
  onToggleExpand: (id: string) => void
  onRefresh: () => void
}) {
  const [open, setOpen] = useState(true)

  return (
    <div className="rounded-2xl border border-[var(--border)] overflow-hidden">
      {/* Group header */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 bg-[var(--muted)]/40
                   hover:bg-[var(--muted)] transition-colors text-left"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold capitalize">{domain}</span>
          <span className="text-xs text-[var(--muted-foreground)]">{agents.length} agents</span>
        </div>
        {open ? <ChevronUp className="w-4 h-4 text-[var(--muted-foreground)]" /> :
                <ChevronDown className="w-4 h-4 text-[var(--muted-foreground)]" />}
      </button>

      {open && (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-xs font-semibold uppercase
                           tracking-wider text-[var(--muted-foreground)]">
              <th className="px-4 py-2 text-left">AGENT</th>
              <th className="px-4 py-2 text-left">ROLE</th>
              <th className="px-4 py-2 text-left">MODEL</th>
              <th className="px-4 py-2 text-left">TEMP</th>
              <th className="px-4 py-2 text-left">ENABLED</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {agents.map((a) => (
              <AgentRow
                key={a.name}
                agent={a}
                expanded={expandedId === a.name}
                onToggleExpand={() => onToggleExpand(a.name)}
                onSaved={() => { onRefresh() }}
                onToggle={() => onRefresh()}
              />
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AgentsPage() {
  const { data: agentList, isLoading, mutate } = useSWR<AgentSpec[]>("/api/agents", fetcher)
  const { data: cfg, mutate: mutateCfg } = useSWR<FlatSentinelConfig>("/api/settings", fetcher)

  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)
  const [savingFlag, setSavingFlag] = useState<string | null>(null)

  async function toggleFlag(key: "two_tier" | "coordinator" | "strategy_overlay", value: boolean) {
    setSavingFlag(key)
    try {
      await settingsApi.updateGeneration({} as never)  // warm connection
      await fetch("/api/settings", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [key]: value }),
      })
      void mutateCfg()
    } catch { /* ignore */ }
    setSavingFlag(null)
  }

  // Group agents by domain prefix (e.g. "academic_extractor" → "academic")
  const groups = useMemo(() => {
    const map = new Map<string, AgentSpec[]>()
    for (const a of agentList ?? []) {
      const parts = (a.capability || a.name).split("_")
      const domain = parts.length > 1 ? parts.slice(0, -1).join("_") : parts[0]
      const key = domain || "custom"
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(a)
    }
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b))
  }, [agentList])

  function handleToggleExpand(id: string) {
    setExpandedId((prev) => (prev === id ? null : id))
  }

  const flags = {
    two_tier: cfg?.two_tier ?? false,
    coordinator: cfg?.coordinator ?? false,
    strategy_overlay: cfg?.strategy_overlay ?? false,
  }

  return (
    <div className="flex flex-col gap-6 max-w-7xl mx-auto w-full">
      <div>
        <GradientHeading size="md" weight="bold">Agents</GradientHeading>
        <p className="text-sm text-[var(--muted-foreground)] mt-1">
          Configure the agents Sentinel runs — grouped by domain. Click Edit on any row to change
          model, role, or generation settings.
        </p>
      </div>

      {/* Feature flags */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-3">
          Feature flags
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <FlagToggle
            label="Two-tier extractor"
            value={flags.two_tier}
            onChange={(v) => toggleFlag("two_tier", v)}
            disabled={savingFlag === "two_tier"}
          />
          <FlagToggle
            label="Strategy overlay"
            value={flags.strategy_overlay}
            onChange={(v) => toggleFlag("strategy_overlay", v)}
            disabled={savingFlag === "strategy_overlay"}
          />
          <FlagToggle
            label="Private boundary"
            value={false}
            onChange={() => {}}
            disabled
          />
          <FlagToggle
            label="Coordinator"
            value={flags.coordinator}
            onChange={(v) => toggleFlag("coordinator", v)}
            disabled={savingFlag === "coordinator"}
          />
        </div>
      </div>

      {/* Add custom agent */}
      {!showAddForm ? (
        <div>
          <button
            onClick={() => setShowAddForm(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-[var(--border)]
                       text-sm font-medium hover:bg-[var(--muted)] transition-colors"
          >
            <Plus className="w-4 h-4" /> Add custom agent
          </button>
        </div>
      ) : (
        <AddAgentForm
          onSaved={() => { void mutate(); setShowAddForm(false) }}
          onCancel={() => setShowAddForm(false)}
        />
      )}

      {/* Roster */}
      {isLoading ? (
        <div className="flex flex-col gap-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-32 rounded-2xl bg-[var(--muted)] animate-pulse" />
          ))}
        </div>
      ) : groups.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-[var(--border)] p-16 text-center">
          <p className="text-sm text-[var(--muted-foreground)]">No agents registered.</p>
        </div>
      ) : (
        <div className="rounded-2xl border border-[var(--border)] overflow-hidden">
          <div className="px-4 py-3 border-b border-[var(--border)] bg-[var(--card)]">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">
              Roster
            </h3>
          </div>
          <div className="flex flex-col divide-y divide-[var(--border)]">
            {groups.map(([domain, agents]) => (
              <DomainGroup
                key={domain}
                domain={domain}
                agents={agents}
                expandedId={expandedId}
                onToggleExpand={handleToggleExpand}
                onRefresh={() => void mutate()}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
