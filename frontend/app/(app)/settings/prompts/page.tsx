"use client"

import { useState, useMemo } from "react"
import useSWR from "swr"
import { GradientHeading } from "@/components/ui/gradient-heading"
import { prompts as promptsApi, type PromptTemplate } from "@/lib/api"
import {
  Search, ChevronDown, ChevronUp, Save, RotateCcw,
  Plus, CheckCircle2, XCircle, Loader2, Tag,
} from "lucide-react"

// ── Helpers ──────────────────────────────────────────────────────────────────
function VariablePill({ name }: { name: string }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full
                     bg-[var(--muted)] border border-[var(--border)]
                     text-xs font-mono text-[var(--muted-foreground)]">
      <Tag className="w-2.5 h-2.5" />{name}
    </span>
  )
}

type CardStatus = "idle" | "saving" | "saved" | "error" | "resetting"

// ── Single prompt card ────────────────────────────────────────────────────────
function PromptCard({ prompt, onMutate }: { prompt: PromptTemplate; onMutate: () => void }) {
  const [expanded, setExpanded] = useState(false)
  const [draft, setDraft] = useState(prompt.template)
  const [status, setStatus] = useState<CardStatus>("idle")
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const isDirty = draft !== prompt.template

  async function handleSave() {
    setStatus("saving")
    setErrorMsg(null)
    try {
      await promptsApi.update(prompt.key, draft)
      await onMutate()
      setStatus("saved")
      setTimeout(() => setStatus("idle"), 2000)
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Save failed")
      setStatus("error")
      setTimeout(() => setStatus("idle"), 4000)
    }
  }

  async function handleReset() {
    setStatus("resetting")
    setErrorMsg(null)
    try {
      await promptsApi.reset(prompt.key)
      await onMutate()
      setDraft(prompt.default_template)
      setStatus("saved")
      setTimeout(() => setStatus("idle"), 2000)
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Reset failed")
      setStatus("error")
      setTimeout(() => setStatus("idle"), 4000)
    }
  }

  const busy = status === "saving" || status === "resetting"

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] overflow-hidden">
      {/* Header row */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between gap-3 px-5 py-4
                   hover:bg-[var(--muted)] transition-colors text-left"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="font-mono font-semibold text-sm truncate">{prompt.key}</span>
          {prompt.is_custom && (
            <span className="shrink-0 px-2 py-0.5 rounded-full text-xs font-semibold
                             bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300">
              Custom
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {prompt.variables.length > 0 && (
            <span className="text-xs text-[var(--muted-foreground)]">
              {prompt.variables.length} var{prompt.variables.length !== 1 ? "s" : ""}
            </span>
          )}
          {expanded
            ? <ChevronUp className="w-4 h-4 text-[var(--muted-foreground)]" />
            : <ChevronDown className="w-4 h-4 text-[var(--muted-foreground)]" />}
        </div>
      </button>

      {/* Expanded body */}
      {expanded && (
        <div className="px-5 pb-5 flex flex-col gap-4 border-t border-[var(--border)]">
          {/* Variables */}
          {prompt.variables.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-3">
              {prompt.variables.map((v) => <VariablePill key={v} name={v} />)}
            </div>
          )}

          {/* Template textarea */}
          <textarea
            value={draft}
            onChange={(e) => { setDraft(e.target.value); setStatus("idle"); setErrorMsg(null) }}
            rows={8}
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--muted)]
                       px-3 py-2 text-sm font-mono outline-none resize-y
                       focus:ring-2 focus:ring-black dark:focus:ring-white"
          />

          {/* Status banner */}
          {status === "error" && errorMsg && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg
                            border border-red-200 bg-red-50 dark:bg-red-900/10
                            text-xs text-red-700 dark:text-red-400">
              <XCircle className="w-3.5 h-3.5 shrink-0" />
              {errorMsg}
            </div>
          )}
          {status === "saved" && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg
                            border border-green-200 bg-green-50 dark:bg-green-900/10
                            text-xs text-green-700 dark:text-green-400">
              <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
              Saved successfully.
            </div>
          )}

          {/* Action buttons */}
          <div className="flex items-center gap-2">
            <button
              onClick={handleSave}
              disabled={!isDirty || busy}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg
                         bg-black dark:bg-white text-white dark:text-black
                         text-xs font-semibold hover:opacity-80 disabled:opacity-40 transition-opacity"
            >
              {status === "saving"
                ? <><Loader2 className="w-3 h-3 animate-spin" /> Saving…</>
                : <><Save className="w-3 h-3" /> Save</>}
            </button>

            {prompt.is_custom && (
              <button
                onClick={handleReset}
                disabled={busy}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg
                           border border-[var(--border)] text-xs text-[var(--muted-foreground)]
                           hover:bg-[var(--muted)] disabled:opacity-40 transition-colors"
              >
                {status === "resetting"
                  ? <><Loader2 className="w-3 h-3 animate-spin" /> Resetting…</>
                  : <><RotateCcw className="w-3 h-3" /> Reset to default</>}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── New custom prompt form ────────────────────────────────────────────────────
function NewPromptForm({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false)
  const [key, setKey] = useState("")
  const [variables, setVariables] = useState("")
  const [template, setTemplate] = useState("")
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle")
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  async function handleCreate() {
    if (!key.trim() || !template.trim()) return
    setStatus("saving")
    setErrorMsg(null)
    try {
      const vars = variables
        .split(",")
        .map((v) => v.trim())
        .filter(Boolean)
      await promptsApi.create({ key: key.trim(), template: template.trim(), variables: vars })
      await onCreated()
      setKey("")
      setVariables("")
      setTemplate("")
      setOpen(false)
      setStatus("idle")
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Create failed")
      setStatus("error")
      setTimeout(() => setStatus("idle"), 4000)
    }
  }

  return (
    <div className="rounded-2xl border border-dashed border-[var(--border)] bg-[var(--card)] overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-5 py-4
                   hover:bg-[var(--muted)] transition-colors text-left"
      >
        <Plus className="w-4 h-4 text-[var(--muted-foreground)]" />
        <span className="text-sm font-semibold text-[var(--muted-foreground)]">New Custom Prompt</span>
        <span className="ml-auto">
          {open
            ? <ChevronUp className="w-4 h-4 text-[var(--muted-foreground)]" />
            : <ChevronDown className="w-4 h-4 text-[var(--muted-foreground)]" />}
        </span>
      </button>

      {open && (
        <div className="px-5 pb-5 flex flex-col gap-4 border-t border-[var(--border)]">
          <div className="flex flex-col gap-1.5 pt-3">
            <label className="text-xs font-semibold">Key <span className="text-red-500">*</span></label>
            <input
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="my_custom_prompt"
              className="rounded-lg border border-[var(--border)] bg-[var(--muted)]
                         px-3 py-2 text-sm font-mono outline-none
                         focus:ring-2 focus:ring-black dark:focus:ring-white"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold">Variables</label>
            <input
              value={variables}
              onChange={(e) => setVariables(e.target.value)}
              placeholder="target, domain, persona"
              className="rounded-lg border border-[var(--border)] bg-[var(--muted)]
                         px-3 py-2 text-sm outline-none
                         focus:ring-2 focus:ring-black dark:focus:ring-white"
            />
            <p className="text-xs text-[var(--muted-foreground)]">Comma-separated variable names.</p>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold">Template <span className="text-red-500">*</span></label>
            <textarea
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              rows={6}
              placeholder="You are a researcher analyzing {target} in the {domain} domain…"
              className="rounded-lg border border-[var(--border)] bg-[var(--muted)]
                         px-3 py-2 text-sm font-mono outline-none resize-y
                         focus:ring-2 focus:ring-black dark:focus:ring-white"
            />
          </div>

          {status === "error" && errorMsg && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg
                            border border-red-200 bg-red-50 dark:bg-red-900/10
                            text-xs text-red-700 dark:text-red-400">
              <XCircle className="w-3.5 h-3.5 shrink-0" />
              {errorMsg}
            </div>
          )}

          <div className="flex items-center gap-2">
            <button
              onClick={handleCreate}
              disabled={!key.trim() || !template.trim() || status === "saving"}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg
                         bg-black dark:bg-white text-white dark:text-black
                         text-xs font-semibold hover:opacity-80 disabled:opacity-40 transition-opacity"
            >
              {status === "saving"
                ? <><Loader2 className="w-3 h-3 animate-spin" /> Creating…</>
                : <><Plus className="w-3 h-3" /> Create Prompt</>}
            </button>
            <button
              onClick={() => { setOpen(false); setStatus("idle"); setErrorMsg(null) }}
              className="px-3 py-1.5 rounded-lg border border-[var(--border)]
                         text-xs text-[var(--muted-foreground)]
                         hover:bg-[var(--muted)] transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function PromptsPage() {
  const { data, mutate, isLoading } = useSWR<PromptTemplate[]>("/api/prompts", promptsApi.list)
  const [query, setQuery] = useState("")

  const filtered = useMemo(() => {
    if (!data) return []
    if (!query.trim()) return data
    const q = query.toLowerCase()
    return data.filter((p) => p.key.toLowerCase().includes(q))
  }, [data, query])

  return (
    <div className="flex flex-col gap-6 max-w-3xl mx-auto">
      {/* Header */}
      <div>
        <GradientHeading size="md" weight="bold">Prompt Templates</GradientHeading>
        <p className="text-sm text-[var(--muted-foreground)] mt-1">
          Customize the system prompts used by each Sentinel agent. Custom prompts override built-in defaults.
        </p>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--muted-foreground)]" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter prompts by key…"
          className="w-full rounded-xl border border-[var(--border)] bg-[var(--muted)]
                     pl-9 pr-3 py-2 text-sm outline-none
                     focus:ring-2 focus:ring-black dark:focus:ring-white"
        />
      </div>

      {/* New prompt form — always at top */}
      <NewPromptForm onCreated={mutate} />

      {/* Prompt list */}
      {isLoading ? (
        <div className="flex items-center justify-center py-16 text-[var(--muted-foreground)]">
          <Loader2 className="w-5 h-5 animate-spin mr-2" />
          <span className="text-sm">Loading prompts…</span>
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 gap-2
                        text-[var(--muted-foreground)]">
          <Search className="w-8 h-8 opacity-30" />
          <p className="text-sm">{query ? `No prompts matching "${query}"` : "No prompts found."}</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {filtered.map((p) => (
            <PromptCard key={p.key} prompt={p} onMutate={mutate} />
          ))}
        </div>
      )}
    </div>
  )
}
