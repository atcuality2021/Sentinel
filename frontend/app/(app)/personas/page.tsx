"use client"

import { useState } from "react"
import useSWR from "swr"
import { GradientHeading } from "@/components/ui/gradient-heading"
import { TextureCard } from "@/components/ui/texture-card"
import { personas as personasApi, type Persona } from "@/lib/api"
import { UserCircle, Sparkles, Plus, Trash2, ChevronDown, ChevronUp } from "lucide-react"

const READING_LEVELS = ["professional", "general public", "technical", "executive"] as const
const TONES = ["neutral", "technical", "plain", "strategic"] as const
const FORMATS = ["brief", "report", "bullets", "table"] as const

// ── Pill ─────────────────────────────────────────────────────────────────────

function Pill({ label, color }: { label: string; color?: string }) {
  const base =
    "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium capitalize"
  const palette = color ?? "bg-[var(--muted)] text-[var(--muted-foreground)]"
  return <span className={`${base} ${palette}`}>{label}</span>
}

// ── Persona card ──────────────────────────────────────────────────────────────

function PersonaCard({ persona, onDelete }: { persona: Persona; onDelete: () => void }) {
  const [deleting, setDeleting] = useState(false)

  async function handleDelete(e: React.MouseEvent) {
    e.stopPropagation()
    if (!confirm(`Delete persona "${persona.name}"?`)) return
    setDeleting(true)
    try {
      await personasApi.delete(persona.id)
    } catch {
      // ignore
    }
    onDelete()
    setDeleting(false)
  }

  return (
    <TextureCard className="group relative p-5 rounded-2xl border border-[var(--border)] flex flex-col gap-4">
      {/* header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-400 to-blue-500
                        flex items-center justify-center text-white font-bold text-sm shrink-0"
          >
            {persona.name.charAt(0).toUpperCase()}
          </div>
          <div>
            <h3 className="font-semibold text-sm">{persona.name}</h3>
            {persona.role && (
              <span className="text-xs text-[var(--muted-foreground)]">{persona.role}</span>
            )}
          </div>
        </div>
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg hover:bg-red-50
                     dark:hover:bg-red-900/20 text-red-500 transition-all"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* description */}
      {persona.description && (
        <p className="text-xs text-[var(--muted-foreground)] leading-relaxed line-clamp-3">
          {persona.description}
        </p>
      )}

      {/* pills: reading_level, tone, format */}
      <div className="flex flex-wrap gap-1.5">
        {persona.reading_level && (
          <Pill
            label={persona.reading_level}
            color="bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300"
          />
        )}
        {persona.tone && (
          <Pill
            label={persona.tone}
            color="bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300"
          />
        )}
        {persona.format && (
          <Pill
            label={persona.format}
            color="bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
          />
        )}
        {persona.domains?.map((d) => (
          <Pill key={d} label={d} />
        ))}
      </div>

      {/* source_policy */}
      {persona.source_policy && (
        <p className="text-[11px] text-[var(--muted-foreground)] italic leading-snug">
          Sources: {persona.source_policy}
        </p>
      )}
    </TextureCard>
  )
}

// ── Create / edit form ────────────────────────────────────────────────────────

interface FormState {
  name: string
  description: string
  reading_level: string
  tone: string
  format: string
  source_policy: string
}

const EMPTY_FORM: FormState = {
  name: "",
  description: "",
  reading_level: "professional",
  tone: "neutral",
  format: "report",
  source_policy: "",
}

function CreatePersonaForm({
  initial,
  onCreated,
  onCancel,
}: {
  initial?: Partial<FormState>
  onCreated: () => void
  onCancel: () => void
}) {
  const [form, setForm] = useState<FormState>({ ...EMPTY_FORM, ...initial })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function set(key: keyof FormState) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      setForm((f) => ({ ...f, [key]: e.target.value }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await personasApi.create({
        name: form.name,
        description: form.description || undefined,
        reading_level: form.reading_level || undefined,
        tone: form.tone || undefined,
        format: form.format || undefined,
        source_policy: form.source_policy || undefined,
      })
      onCreated()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create persona")
    } finally {
      setLoading(false)
    }
  }

  const inputCls =
    "w-full rounded-lg border border-[var(--border)] bg-[var(--muted)] px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white"
  const selectCls = inputCls

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      {/* name */}
      <div>
        <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">
          Name *
        </label>
        <input
          value={form.name}
          onChange={set("name")}
          required
          placeholder="Senior Analyst"
          className={inputCls}
        />
      </div>

      {/* description */}
      <div>
        <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">
          Description
        </label>
        <textarea
          value={form.description}
          onChange={set("description")}
          rows={2}
          placeholder="Expert in BFSI sector competitive analysis"
          className={`${inputCls} resize-none`}
        />
      </div>

      {/* reading_level + tone */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">
            Reading level
          </label>
          <select value={form.reading_level} onChange={set("reading_level")} className={selectCls}>
            {READING_LEVELS.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">
            Tone
          </label>
          <select value={form.tone} onChange={set("tone")} className={selectCls}>
            {TONES.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* format + source_policy */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">
            Format
          </label>
          <select value={form.format} onChange={set("format")} className={selectCls}>
            {FORMATS.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">
            Source policy
          </label>
          <input
            value={form.source_policy}
            onChange={set("source_policy")}
            placeholder="peer-reviewed only"
            className={inputCls}
          />
        </div>
      </div>

      {error && <p className="text-xs text-red-500">{error}</p>}

      <div className="flex gap-2 mt-1">
        <button
          type="submit"
          disabled={loading || !form.name}
          className="flex-1 rounded-lg bg-black dark:bg-white text-white dark:text-black
                     py-2 text-sm font-semibold hover:opacity-80 disabled:opacity-40 transition-opacity"
        >
          {loading ? "Creating…" : "Create Persona"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-4 rounded-lg border border-[var(--border)] text-sm hover:bg-[var(--muted)] transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  )
}

// ── Generator section ─────────────────────────────────────────────────────────

function GeneratorSection({ onGenerated }: { onGenerated: (p: Partial<FormState>) => void }) {
  const [open, setOpen] = useState(true)
  const [description, setDescription] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleGenerate(e: React.FormEvent) {
    e.preventDefault()
    if (!description.trim()) return
    setLoading(true)
    setError(null)
    try {
      const result = await personasApi.generate(description)
      onGenerated({
        name: result.name ?? "",
        description: result.description ?? "",
        reading_level: result.reading_level ?? "professional",
        tone: result.tone ?? "neutral",
        format: result.format ?? "report",
        source_policy: result.source_policy ?? "",
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] overflow-hidden">
      {/* header */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-[var(--muted)] transition-colors"
      >
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-purple-500" />
          <span className="text-sm font-semibold">AI Persona Generator</span>
          <span className="text-xs text-[var(--muted-foreground)]">
            — describe your audience and we'll fill the form
          </span>
        </div>
        {open ? (
          <ChevronUp className="w-4 h-4 text-[var(--muted-foreground)]" />
        ) : (
          <ChevronDown className="w-4 h-4 text-[var(--muted-foreground)]" />
        )}
      </button>

      {open && (
        <form onSubmit={handleGenerate} className="px-5 pb-5 flex flex-col gap-3">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            placeholder="e.g. A CFO evaluating enterprise software at a Fortune 500 company"
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--muted)]
                       px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white resize-none"
          />
          {error && <p className="text-xs text-red-500">{error}</p>}
          <button
            type="submit"
            disabled={loading || !description.trim()}
            className="self-start flex items-center gap-2 px-4 py-2 rounded-lg
                       bg-gradient-to-r from-purple-500 to-blue-500 text-white text-sm font-semibold
                       hover:opacity-90 disabled:opacity-40 transition-opacity"
          >
            <Sparkles className="w-3.5 h-3.5" />
            {loading ? "Generating…" : "Generate"}
          </button>
        </form>
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PersonasPage() {
  const { data: personaList, isLoading, mutate } = useSWR<Persona[]>(
    "/api/personas",
    () => personasApi.list(),
  )

  // "new" | "generated" | null
  const [formMode, setFormMode] = useState<"new" | "generated" | null>(null)
  const [prefill, setPrefill] = useState<Partial<FormState>>({})

  function handleGenerated(p: Partial<FormState>) {
    setPrefill(p)
    setFormMode("generated")
  }

  function handleCreated() {
    void mutate()
    setFormMode(null)
    setPrefill({})
  }

  function handleCancel() {
    setFormMode(null)
    setPrefill({})
  }

  const showForm = formMode !== null

  return (
    <div className="flex flex-col gap-6 max-w-7xl mx-auto w-full">
      {/* heading */}
      <div className="flex items-end justify-between">
        <div>
          <GradientHeading size="md" weight="bold">Personas</GradientHeading>
          <p className="text-sm text-[var(--muted-foreground)] mt-1">
            Analyst personas shape how agents frame findings and what sources they prioritise.
          </p>
        </div>
        {!showForm && (
          <button
            onClick={() => setFormMode("new")}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-black dark:bg-white
                       text-white dark:text-black text-sm font-semibold hover:opacity-80 transition-opacity"
          >
            <Plus className="w-4 h-4" /> New Persona
          </button>
        )}
      </div>

      {/* AI generator (always visible unless form is open from "New Persona") */}
      {!showForm && (
        <GeneratorSection onGenerated={handleGenerated} />
      )}

      {/* create form */}
      {showForm && (
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 max-w-xl">
          <h3 className="font-semibold text-sm mb-4">
            {formMode === "generated" ? "Review & save generated persona" : "New Persona"}
          </h3>
          <CreatePersonaForm
            initial={prefill}
            onCreated={handleCreated}
            onCancel={handleCancel}
          />
        </div>
      )}

      {/* list */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-48 rounded-2xl bg-[var(--muted)] animate-pulse" />
          ))}
        </div>
      ) : (personaList ?? []).length === 0 && !showForm ? (
        <div className="rounded-2xl border border-dashed border-[var(--border)] p-16 text-center">
          <UserCircle className="w-10 h-10 text-[var(--muted-foreground)] mx-auto mb-3" />
          <p className="text-sm text-[var(--muted-foreground)]">No personas yet.</p>
          <button
            onClick={() => setFormMode("new")}
            className="mt-3 text-sm font-semibold underline"
          >
            Create your first persona →
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {(personaList ?? []).map((p) => (
            <PersonaCard key={p.id} persona={p} onDelete={() => void mutate()} />
          ))}
        </div>
      )}
    </div>
  )
}
