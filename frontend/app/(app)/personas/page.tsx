"use client"

import { useState } from "react"
import useSWR from "swr"
import { GradientHeading } from "@/components/ui/gradient-heading"
import {
  personas as personasApi,
  type Persona, type BuiltInPersona, type PersonasResponse,
} from "@/lib/api"
import { fetcher } from "@/lib/fetcher"
import {
  UserCircle, Sparkles, Plus, Trash2, Edit2, RotateCcw, Lock,
} from "lucide-react"

const READING_LEVELS = [
  "professional", "general public", "technical", "executive",
  "professional (engineering)", "professional (clinical)", "K-12 to undergraduate",
] as const
const TONES = ["neutral", "technical", "plain", "strategic", "clinical"] as const
const FORMATS = [
  "brief", "report", "bullets", "table",
  "comparison table with code-level notes",
  "short bullets ending in a clear recommendation",
  "study guide with definitions and worked examples",
  "structured brief with evidence levels per claim",
  "checklist with a one-line rationale per item",
] as const

interface FormState {
  name: string
  description: string
  reading_level: string
  tone: string
  format: string
  source_policy: string
}

const EMPTY: FormState = {
  name: "", description: "", reading_level: "professional",
  tone: "neutral", format: "brief", source_policy: "",
}

// ── Input helpers ─────────────────────────────────────────────────────────────

const inputCls =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--muted)] px-3 py-2 text-sm " +
  "outline-none focus:ring-2 focus:ring-black dark:focus:ring-white"

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">{label}</label>
      {children}
    </div>
  )
}

// ── Right panel: create / edit form + generator ───────────────────────────────

function RightPanel({
  initial,
  title,
  onSaved,
  onCancel,
  isEditingBuiltIn,
}: {
  initial?: Partial<FormState>
  title?: string
  onSaved: () => void
  onCancel: () => void
  isEditingBuiltIn?: boolean
}) {
  const [form, setForm] = useState<FormState>({ ...EMPTY, ...initial })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [genDesc, setGenDesc] = useState("")
  const [generating, setGenerating] = useState(false)

  function set(k: keyof FormState) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      setForm((f) => ({ ...f, [k]: e.target.value }))
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    if (!form.name.trim()) return
    setSaving(true)
    setError(null)
    try {
      await personasApi.create({
        name: form.name, description: form.description || undefined,
        reading_level: form.reading_level || undefined, tone: form.tone || undefined,
        format: form.format || undefined, source_policy: form.source_policy || undefined,
      })
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save")
    } finally {
      setSaving(false)
    }
  }

  async function handleGenerate(e: React.FormEvent) {
    e.preventDefault()
    if (!genDesc.trim()) return
    setGenerating(true)
    setError(null)
    try {
      const result = await personasApi.generate(genDesc)
      setForm({
        name: result.name ?? "",
        description: result.description ?? "",
        reading_level: result.reading_level ?? "professional",
        tone: result.tone ?? "neutral",
        format: result.format ?? "brief",
        source_policy: result.source_policy ?? "",
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed")
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="flex flex-col gap-4 sticky top-6">
      {/* New / Edit form */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold">{title ?? "New persona"}</h3>
          {onCancel && (
            <button onClick={onCancel} className="text-xs text-[var(--muted-foreground)] hover:underline">
              Cancel
            </button>
          )}
        </div>
        <form onSubmit={handleSave} className="flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Name *">
              <input value={form.name} onChange={set("name")} required
                placeholder="e.g. CFO brief" className={inputCls}
                readOnly={isEditingBuiltIn} />
            </Field>
            <Field label="Description">
              <input value={form.description} onChange={set("description")}
                placeholder="who this audience is" className={inputCls} />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Reading level">
              <select value={form.reading_level} onChange={set("reading_level")} className={inputCls}>
                {READING_LEVELS.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field label="Tone">
              <select value={form.tone} onChange={set("tone")} className={inputCls}>
                {TONES.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Output format">
              <select value={form.format} onChange={set("format")} className={inputCls}>
                {FORMATS.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field label="Source policy">
              <input value={form.source_policy} onChange={set("source_policy")}
                placeholder="(none)" className={inputCls} />
            </Field>
          </div>
          {error && <p className="text-xs text-red-500">{error}</p>}
          <button type="submit" disabled={saving || !form.name.trim()}
            className="w-full rounded-lg bg-black dark:bg-white text-white dark:text-black
                       py-2 text-sm font-semibold hover:opacity-80 disabled:opacity-40 transition-opacity">
            {saving ? "Saving…" : "Save persona"}
          </button>
        </form>
        <p className="text-xs text-[var(--muted-foreground)] mt-3">
          Saved personas appear in every task form&apos;s persona dropdown.
        </p>
      </div>

      {/* AI generator */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles className="w-4 h-4 text-purple-500" />
          <h3 className="text-sm font-semibold">Generate a persona</h3>
        </div>
        <p className="text-xs text-[var(--muted-foreground)] mb-3">
          Describe the audience in plain words — the vllm model drafts the full profile,
          which lands in the form above for review before saving.
        </p>
        <form onSubmit={handleGenerate} className="flex flex-col gap-2">
          <Field label="Audience description">
            <textarea value={genDesc} onChange={(e) => setGenDesc(e.target.value)}
              rows={3} placeholder="e.g. A hospital procurement officer comparing medical-device vendors under strict budget rules"
              className={`${inputCls} resize-none`} />
          </Field>
          <Field label="Persona name (optional — carried into the form)">
            <input value={form.name} onChange={set("name")}
              placeholder="e.g. procurement officer" className={inputCls} />
          </Field>
          <button type="submit" disabled={generating || !genDesc.trim()}
            className="w-full rounded-lg border border-[var(--border)] py-2 text-sm font-semibold
                       hover:bg-[var(--muted)] disabled:opacity-40 transition-colors flex items-center justify-center gap-2">
            <Sparkles className="w-3.5 h-3.5 text-purple-500" />
            {generating ? "Generating…" : "Generate profile"}
          </button>
        </form>
      </div>
    </div>
  )
}

// ── Saved persona card ────────────────────────────────────────────────────────

function CustomPersonaCard({ persona, onDelete }: { persona: Persona; onDelete: () => void }) {
  const [deleting, setDeleting] = useState(false)

  async function handleDelete() {
    if (!confirm(`Delete persona "${persona.name}"?`)) return
    setDeleting(true)
    try { await personasApi.delete(persona.id) } catch { /* ignore */ }
    onDelete()
    setDeleting(false)
  }

  return (
    <div className="group rounded-xl border border-[var(--border)] bg-[var(--card)] p-4 flex flex-col gap-2">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-400 to-blue-500
                          flex items-center justify-center text-white font-bold text-xs shrink-0">
            {persona.name.charAt(0).toUpperCase()}
          </div>
          <div>
            <p className="text-sm font-semibold">{persona.name}</p>
            {persona.role && <p className="text-xs text-[var(--muted-foreground)]">{persona.role}</p>}
          </div>
        </div>
        <button onClick={handleDelete} disabled={deleting}
          className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-50 dark:hover:bg-red-900/20
                     text-red-500 transition-all">
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
      {persona.description && (
        <p className="text-xs text-[var(--muted-foreground)] line-clamp-2">{persona.description}</p>
      )}
      <div className="flex flex-wrap gap-1 text-[10px]">
        {persona.reading_level && (
          <span className="px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
            {persona.reading_level}
          </span>
        )}
        {persona.tone && (
          <span className="px-1.5 py-0.5 rounded bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300">
            {persona.tone}
          </span>
        )}
        {persona.format && (
          <span className="px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300">
            {persona.format}
          </span>
        )}
      </div>
      {persona.source_policy && (
        <p className="text-[11px] text-[var(--muted-foreground)] italic">{persona.source_policy}</p>
      )}
    </div>
  )
}

// ── Built-in persona row ──────────────────────────────────────────────────────

function BuiltInRow({
  persona,
  onEdit,
}: {
  persona: BuiltInPersona
  onEdit: (p: BuiltInPersona) => void
}) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-sm">{persona.name}</span>
          <span className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded
                           bg-[var(--muted)] text-[var(--muted-foreground)]">
            BUILT-IN
          </span>
          {persona.has_override && (
            <span className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded
                             bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300">
              OVERRIDDEN
            </span>
          )}
        </div>
        {persona.editable ? (
          <button onClick={() => onEdit(persona)}
            className="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-[var(--border)]
                       text-xs hover:bg-[var(--muted)] transition-colors">
            <Edit2 className="w-3 h-3" /> Edit
          </button>
        ) : (
          <span className="flex items-center gap-1 text-xs text-[var(--muted-foreground)]">
            <Lock className="w-3 h-3" /> read-only
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-x-8 gap-y-0.5 text-xs text-[var(--muted-foreground)]">
        {persona.reading_level && (
          <><span className="font-medium text-[var(--foreground)]">reading level</span>
          <span>{persona.reading_level}</span></>
        )}
        {persona.tone && (
          <><span className="font-medium text-[var(--foreground)]">tone</span>
          <span>{persona.tone}</span></>
        )}
        {persona.format && (
          <><span className="font-medium text-[var(--foreground)]">format</span>
          <span>{persona.format}</span></>
        )}
        {persona.source_policy && (
          <><span className="font-medium text-[var(--foreground)]">sources</span>
          <span>{persona.source_policy}</span></>
        )}
      </div>
      {persona.name === "enterprise" && (
        <p className="text-xs text-[var(--muted-foreground)] mt-2 italic">
          Default audience — tasks with this persona skip the extra render pass (kept read-only).
        </p>
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PersonasPage() {
  const { data, isLoading, mutate } = useSWR<PersonasResponse>("/api/personas", fetcher)

  const [editTarget, setEditTarget] = useState<{
    form: Partial<FormState>
    title: string
    isBuiltIn: boolean
  } | null>(null)

  function handleEditBuiltIn(p: BuiltInPersona) {
    setEditTarget({
      form: {
        name: p.name,
        reading_level: p.reading_level,
        tone: p.tone,
        format: p.format,
        source_policy: p.source_policy,
      },
      title: `Edit ${p.name}`,
      isBuiltIn: true,
    })
  }

  const builtIns = data?.built_in ?? []
  const customs  = data?.custom ?? []

  return (
    <div className="flex flex-col gap-6 max-w-7xl mx-auto w-full">
      <div>
        <GradientHeading size="md" weight="bold">Personas</GradientHeading>
        <p className="text-sm text-[var(--muted-foreground)] mt-1">
          Audience profiles that shape reading level, tone, and format.
        </p>
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6 items-start">
        {/* Left: custom + built-ins */}
        <div className="flex flex-col gap-6">
          {/* Saved personas */}
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold">Saved personas</h3>
              <button onClick={() => setEditTarget({ form: EMPTY, title: "New persona", isBuiltIn: false })}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-black dark:bg-white
                           text-white dark:text-black text-xs font-semibold hover:opacity-80 transition-opacity">
                <Plus className="w-3.5 h-3.5" /> New
              </button>
            </div>
            {isLoading ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {[...Array(2)].map((_, i) => (
                  <div key={i} className="h-32 rounded-xl bg-[var(--muted)] animate-pulse" />
                ))}
              </div>
            ) : customs.length === 0 ? (
              <div className="flex flex-col items-center py-10 gap-2">
                <UserCircle className="w-8 h-8 text-[var(--muted-foreground)]" />
                <p className="text-sm text-[var(--muted-foreground)]">
                  No saved personas yet — create or generate one.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {customs.map((p) => (
                  <CustomPersonaCard key={p.id} persona={p} onDelete={() => void mutate()} />
                ))}
              </div>
            )}
          </div>

          {/* Built-in personas */}
          <div>
            <h3 className="text-sm font-semibold mb-1">Built-in personas</h3>
            <p className="text-xs text-[var(--muted-foreground)] mb-3">
              <strong>Edit</strong> tweaks a built-in for every task (saved as an override);{" "}
              <strong>Reset to default</strong> restores the code profile.{" "}
              <strong>enterprise</strong> stays read-only. Pick <strong>auto</strong> in the task
              form to let the agent choose one by domain.
            </p>
            <div className="flex flex-col gap-3">
              {isLoading
                ? [...Array(4)].map((_, i) => (
                    <div key={i} className="h-20 rounded-xl bg-[var(--muted)] animate-pulse" />
                  ))
                : builtIns.map((p) => (
                    <BuiltInRow key={p.id} persona={p} onEdit={handleEditBuiltIn} />
                  ))}
            </div>
          </div>
        </div>

        {/* Right: always-visible form panel */}
        <RightPanel
          key={editTarget?.title ?? "new"}
          initial={editTarget?.form ?? EMPTY}
          title={editTarget?.title ?? "New persona"}
          isEditingBuiltIn={editTarget?.isBuiltIn}
          onSaved={() => { void mutate(); setEditTarget(null) }}
          onCancel={() => setEditTarget(null)}
        />
      </div>
    </div>
  )
}
