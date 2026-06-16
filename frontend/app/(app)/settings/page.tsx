"use client"

import { useState } from "react"
import useSWR from "swr"
import { GradientHeading } from "@/components/ui/gradient-heading"
import { DirectionAwareTabs } from "@/components/ui/direction-aware-tabs"
import { type FlatSentinelConfig as SentinelConfig } from "@/lib/api"
import {
  Server, Cpu, Shield, Search, Brain, FileText, MessageSquare,
  Save, RotateCcw, CheckCircle2, AlertTriangle, Loader2,
} from "lucide-react"

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
const fetcher = (url: string) => fetch(url, { credentials: "include" }).then((r) => r.json())

// ── Reusable field components ────────────────────────────────────────────────
function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-semibold text-[var(--foreground)]">{label}</label>
      {children}
      {hint && <p className="text-xs text-[var(--muted-foreground)]">{hint}</p>}
    </div>
  )
}

function TextInput({ value, onChange, placeholder, type = "text" }: {
  value: string; onChange: (v: string) => void; placeholder?: string; type?: string
}) {
  return (
    <input type={type} value={value} onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="rounded-lg border border-[var(--border)] bg-[var(--muted)]
                 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white" />
  )
}

function NumberInput({ value, onChange, min, max, step }: {
  value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number
}) {
  return (
    <input type="number" value={value} min={min} max={max} step={step}
      onChange={(e) => onChange(Number(e.target.value))}
      className="rounded-lg border border-[var(--border)] bg-[var(--muted)]
                 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white w-36" />
  )
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex items-center gap-3 cursor-pointer select-none">
      <button type="button" role="switch" aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors
          ${checked ? "bg-black dark:bg-white" : "bg-[var(--muted)] border border-[var(--border)]"}`}>
        <span className={`inline-block h-4 w-4 transform rounded-full bg-white dark:bg-black transition-transform
          ${checked ? "translate-x-6" : "translate-x-1"}`} />
      </button>
      <span className="text-sm">{label}</span>
    </label>
  )
}

function SelectInput({ value, onChange, options }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[]
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}
      className="rounded-lg border border-[var(--border)] bg-[var(--muted)]
                 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white">
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  )
}

// ── Tab panels ───────────────────────────────────────────────────────────────
function BackendTab({ config, onChange }: { config: SentinelConfig; onChange: (c: Partial<SentinelConfig>) => void }) {
  return (
    <div className="flex flex-col gap-5">
      <Field label="Backend" hint="gemini uses Google ADK; vllm requires an on-prem endpoint.">
        <SelectInput value={config.backend ?? "gemini"}
          onChange={(v) => onChange({ backend: v as "gemini" | "vllm" })}
          options={[
            { value: "gemini", label: "Gemini (Google ADK)" },
            { value: "vllm", label: "vLLM (on-prem)" },
          ]} />
      </Field>

      {config.backend === "vllm" && (
        <Field label="vLLM Base URL" hint="Endpoint your vLLM server is serving on.">
          <TextInput value={config.vllm_base_url ?? ""} onChange={(v) => onChange({ vllm_base_url: v })}
            placeholder="http://localhost:8080" />
        </Field>
      )}

      <Field label="Model">
        <TextInput value={config.model ?? ""} onChange={(v) => onChange({ model: v })}
          placeholder="gemini-2.0-flash" />
      </Field>

      <Field label="Governance Mode" hint="Controls where computation is allowed to run.">
        <SelectInput value={config.governance ?? "cloud_ok"}
          onChange={(v) => onChange({ governance: v as SentinelConfig["governance"] })}
          options={[
            { value: "cloud_ok",          label: "Cloud OK — any provider" },
            { value: "on_prem_preferred", label: "On-Prem Preferred — fall back to cloud" },
            { value: "on_prem_required",  label: "On-Prem Required — no cloud calls" },
          ]} />
      </Field>
    </div>
  )
}

function GenerationTab({ config, onChange }: { config: SentinelConfig; onChange: (c: Partial<SentinelConfig>) => void }) {
  return (
    <div className="flex flex-col gap-5">
      <Field label="Temperature" hint="0 = deterministic, 1 = creative. Default: 0.3">
        <NumberInput value={config.temperature ?? 0.3} onChange={(v) => onChange({ temperature: v })}
          min={0} max={2} step={0.05} />
      </Field>

      <Field label="Max Tokens">
        <NumberInput value={config.max_tokens ?? 8192} onChange={(v) => onChange({ max_tokens: v })}
          min={256} max={32768} step={256} />
      </Field>

      <Field label="Thinking Budget (tokens)" hint="0 = disabled. Used by extended-thinking capable models.">
        <NumberInput value={config.thinking_budget ?? 0} onChange={(v) => onChange({ thinking_budget: v })}
          min={0} max={16384} step={128} />
      </Field>
    </div>
  )
}

function SearchTab({ config, onChange }: { config: SentinelConfig; onChange: (c: Partial<SentinelConfig>) => void }) {
  return (
    <div className="flex flex-col gap-5">
      <Toggle checked={!!config.enable_web_search} onChange={(v) => onChange({ enable_web_search: v })}
        label="Enable web search" />

      <Field label="Max Web Results per query">
        <NumberInput value={config.max_web_results ?? 10} onChange={(v) => onChange({ max_web_results: v })}
          min={1} max={50} step={1} />
      </Field>

      <Toggle checked={!!config.enable_private_retrieval}
        onChange={(v) => onChange({ enable_private_retrieval: v })}
        label="Enable private retrieval (ChromaDB)" />

      <Toggle checked={!!config.enable_kb}
        onChange={(v) => onChange({ enable_kb: v })}
        label="Enable knowledge base search" />
    </div>
  )
}

function StrategyTab({ config, onChange }: { config: SentinelConfig; onChange: (c: Partial<SentinelConfig>) => void }) {
  return (
    <div className="flex flex-col gap-5">
      <Toggle checked={!!config.enable_grading} onChange={(v) => onChange({ enable_grading: v })}
        label="Enable quality grading" />

      <Toggle checked={!!config.enable_gap_analysis} onChange={(v) => onChange({ enable_gap_analysis: v })}
        label="Enable gap analysis (flags missing intelligence)" />

      <Field label="Gap Threshold" hint="Number of missing required fields before flagging a gap.">
        <NumberInput value={config.gap_threshold ?? 3} onChange={(v) => onChange({ gap_threshold: v })}
          min={1} max={20} step={1} />
      </Field>

      <Toggle checked={!!config.enable_citation} onChange={(v) => onChange({ enable_citation: v })}
        label="Require source citations" />
    </div>
  )
}

function MemoryTab({ config, onChange }: { config: SentinelConfig; onChange: (c: Partial<SentinelConfig>) => void }) {
  return (
    <div className="flex flex-col gap-5">
      <Toggle checked={!!config.enable_memory} onChange={(v) => onChange({ enable_memory: v })}
        label="Enable episode memory (Zep)" />

      <Toggle checked={!!config.enable_semantic_memory} onChange={(v) => onChange({ enable_semantic_memory: v })}
        label="Enable semantic memory extraction" />

      <Field label="Memory TTL (days)" hint="How long memories are retained. 0 = indefinite.">
        <NumberInput value={config.memory_ttl_days ?? 90} onChange={(v) => onChange({ memory_ttl_days: v })}
          min={0} max={365} step={1} />
      </Field>

      <Field label="ChromaDB Collection Prefix">
        <TextInput value={config.chroma_prefix ?? "sentinel"} onChange={(v) => onChange({ chroma_prefix: v })}
          placeholder="sentinel" />
      </Field>
    </div>
  )
}

function PromptsTab({ config, onChange }: { config: SentinelConfig; onChange: (c: Partial<SentinelConfig>) => void }) {
  return (
    <div className="flex flex-col gap-5">
      <Field label="Competitor Research System Prompt Override"
        hint="Leave blank to use the built-in prompt.">
        <textarea value={config.competitor_system_prompt ?? ""}
          onChange={(e) => onChange({ competitor_system_prompt: e.target.value })}
          rows={5} placeholder="You are a competitive intelligence analyst…"
          className="rounded-lg border border-[var(--border)] bg-[var(--muted)]
                     px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white resize-none" />
      </Field>

      <Field label="Account Brief System Prompt Override">
        <textarea value={config.account_system_prompt ?? ""}
          onChange={(e) => onChange({ account_system_prompt: e.target.value })}
          rows={5} placeholder="You are a senior account researcher…"
          className="rounded-lg border border-[var(--border)] bg-[var(--muted)]
                     px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white resize-none" />
      </Field>
    </div>
  )
}

// ── Main ─────────────────────────────────────────────────────────────────────
export default function SettingsPage() {
  const { data: serverConfig, mutate } = useSWR<SentinelConfig>(`${API}/api/settings`, fetcher)
  const [local, setLocal] = useState<Partial<SentinelConfig>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const config: SentinelConfig = { ...(serverConfig ?? {}), ...local } as SentinelConfig

  function patch(partial: Partial<SentinelConfig>) {
    setLocal((prev) => ({ ...prev, ...partial }))
    setSaved(false)
  }

  function reset() {
    setLocal({})
    setSaved(false)
  }

  async function save() {
    setSaving(true)
    await fetch(`${API}/api/settings`, {
      method: "POST", credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }).catch(() => {})
    await mutate()
    setLocal({})
    setSaving(false)
    setSaved(true)
    setTimeout(() => setSaved(false), 3000)
  }

  const hasPendingChanges = Object.keys(local).length > 0

  const tabs = [
    { id: 0, label: "Backend",    content: <BackendTab    config={config} onChange={patch} /> },
    { id: 1, label: "Generation", content: <GenerationTab config={config} onChange={patch} /> },
    { id: 2, label: "Search",     content: <SearchTab     config={config} onChange={patch} /> },
    { id: 3, label: "Strategy",   content: <StrategyTab   config={config} onChange={patch} /> },
    { id: 4, label: "Memory",     content: <MemoryTab     config={config} onChange={patch} /> },
    { id: 5, label: "Prompts",    content: <PromptsTab    config={config} onChange={patch} /> },
  ]

  return (
    <div className="flex flex-col gap-6 max-w-3xl mx-auto">
      <div className="flex items-end justify-between">
        <div>
          <GradientHeading size="md" weight="bold">Settings</GradientHeading>
          <p className="text-sm text-[var(--muted-foreground)] mt-1">
            Configure Sentinel's backend, generation parameters, and governance policy.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {hasPendingChanges && (
            <button onClick={reset}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border)]
                         text-sm text-[var(--muted-foreground)] hover:bg-[var(--muted)] transition-colors">
              <RotateCcw className="w-3.5 h-3.5" /> Reset
            </button>
          )}
          <button onClick={save} disabled={!hasPendingChanges || saving}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-black dark:bg-white
                       text-white dark:text-black text-sm font-semibold
                       hover:opacity-80 disabled:opacity-40 transition-opacity">
            {saving
              ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Saving…</>
              : saved
              ? <><CheckCircle2 className="w-3.5 h-3.5 text-green-400" /> Saved</>
              : <><Save className="w-3.5 h-3.5" /> Save</>}
          </button>
        </div>
      </div>

      {hasPendingChanges && (
        <div className="flex items-center gap-2 px-4 py-2.5 rounded-xl
                        border border-amber-200 bg-amber-50 dark:bg-amber-900/10 text-xs text-amber-700 dark:text-amber-400">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          You have unsaved changes.
        </div>
      )}

      <DirectionAwareTabs tabs={tabs} />
    </div>
  )
}
