"use client"

import { useState } from "react"
import useSWR from "swr"
import { GradientHeading } from "@/components/ui/gradient-heading"
import { TextureCard } from "@/components/ui/texture-card"
import { type Persona } from "@/lib/api"
import { UserCircle, Globe, Lock, Briefcase, Plus, Trash2 } from "lucide-react"

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
const fetcher = (url: string) => fetch(url, { credentials: "include" }).then((r) => r.json())

function PersonaCard({ persona, onDelete }: { persona: Persona; onDelete: () => void }) {
  const [deleting, setDeleting] = useState(false)

  async function handleDelete(e: React.MouseEvent) {
    e.stopPropagation()
    if (!confirm(`Delete persona "${persona.name}"?`)) return
    setDeleting(true)
    await fetch(`${API}/api/personas/${persona.id}`, {
      method: "DELETE", credentials: "include"
    }).catch(() => {})
    onDelete()
    setDeleting(false)
  }

  return (
    <TextureCard className="group relative p-5 rounded-2xl border border-[var(--border)] flex flex-col gap-4">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-400 to-blue-500
                          flex items-center justify-center text-white font-bold text-sm shrink-0">
            {persona.name.charAt(0).toUpperCase()}
          </div>
          <div>
            <h3 className="font-semibold text-sm">{persona.name}</h3>
            {persona.role && (
              <span className="text-xs text-[var(--muted-foreground)] flex items-center gap-1">
                <Briefcase className="w-3 h-3" /> {persona.role}
              </span>
            )}
          </div>
        </div>
        <button onClick={handleDelete} disabled={deleting}
          className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg hover:bg-red-50
                     dark:hover:bg-red-900/20 text-red-500 transition-all">
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {persona.description && (
        <p className="text-xs text-[var(--muted-foreground)] leading-relaxed line-clamp-3">
          {persona.description}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        {persona.public_sources && (
          <span className="badge-public flex items-center gap-1">
            <Globe className="w-3 h-3" /> {persona.public_sources} pub
          </span>
        )}
        {persona.private_sources && (
          <span className="badge-private flex items-center gap-1">
            <Lock className="w-3 h-3" /> {persona.private_sources} priv
          </span>
        )}
        {persona.domains?.map((d) => (
          <span key={d} className="text-xs px-2 py-0.5 rounded-full bg-[var(--muted)]
                                    text-[var(--muted-foreground)] capitalize">
            {d}
          </span>
        ))}
      </div>

      {persona.system_prompt && (
        <div className="rounded-lg bg-[var(--muted)] p-3">
          <p className="text-xs font-mono text-[var(--muted-foreground)] line-clamp-3 leading-relaxed">
            {persona.system_prompt}
          </p>
        </div>
      )}
    </TextureCard>
  )
}

function CreatePersonaForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("")
  const [role, setRole] = useState("")
  const [description, setDescription] = useState("")
  const [systemPrompt, setSystemPrompt] = useState("")
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    await fetch(`${API}/api/personas`, {
      method: "POST", credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, role, description, system_prompt: systemPrompt }),
    }).catch(() => {})
    onCreated()
    setName(""); setRole(""); setDescription(""); setSystemPrompt("")
    setLoading(false)
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Name *</label>
          <input value={name} onChange={(e) => setName(e.target.value)} required
            placeholder="Senior Analyst"
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--muted)]
                       px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white" />
        </div>
        <div>
          <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Role</label>
          <input value={role} onChange={(e) => setRole(e.target.value)}
            placeholder="Competitive Intelligence"
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--muted)]
                       px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white" />
        </div>
      </div>
      <div>
        <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Description</label>
        <input value={description} onChange={(e) => setDescription(e.target.value)}
          placeholder="Expert in BFSI sector competitive analysis"
          className="w-full rounded-lg border border-[var(--border)] bg-[var(--muted)]
                     px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white" />
      </div>
      <div>
        <label className="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">
          System Prompt Override
        </label>
        <textarea value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)}
          rows={3} placeholder="You are a senior analyst specialising in…"
          className="w-full rounded-lg border border-[var(--border)] bg-[var(--muted)]
                     px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black dark:focus:ring-white resize-none" />
      </div>
      <button type="submit" disabled={loading || !name}
        className="rounded-lg bg-black dark:bg-white text-white dark:text-black
                   py-2 text-sm font-semibold hover:opacity-80 disabled:opacity-40 transition-opacity">
        {loading ? "Creating…" : "Create Persona"}
      </button>
    </form>
  )
}

export default function PersonasPage() {
  const { data: personas, isLoading, mutate } = useSWR<Persona[]>(`${API}/api/personas`, fetcher)
  const [showForm, setShowForm] = useState(false)

  return (
    <div className="flex flex-col gap-6 max-w-5xl mx-auto">
      <div className="flex items-end justify-between">
        <div>
          <GradientHeading size="md" weight="bold">Personas</GradientHeading>
          <p className="text-sm text-[var(--muted-foreground)] mt-1">
            Analyst personas shape how agents frame findings and what sources they prioritise.
          </p>
        </div>
        <button onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-black dark:bg-white
                     text-white dark:text-black text-sm font-semibold hover:opacity-80 transition-opacity">
          <Plus className="w-4 h-4" /> New Persona
        </button>
      </div>

      {showForm && (
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 max-w-xl">
          <h3 className="font-semibold text-sm mb-4">New Persona</h3>
          <CreatePersonaForm onCreated={() => { mutate(); setShowForm(false) }} />
        </div>
      )}

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-48 rounded-2xl bg-[var(--muted)] animate-pulse" />
          ))}
        </div>
      ) : (personas ?? []).length === 0 && !showForm ? (
        <div className="rounded-2xl border border-dashed border-[var(--border)] p-16 text-center">
          <UserCircle className="w-10 h-10 text-[var(--muted-foreground)] mx-auto mb-3" />
          <p className="text-sm text-[var(--muted-foreground)]">No personas yet.</p>
          <button onClick={() => setShowForm(true)} className="mt-3 text-sm font-semibold underline">
            Create your first persona →
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {(personas ?? []).map((p) => (
            <PersonaCard key={p.id} persona={p} onDelete={mutate} />
          ))}
        </div>
      )}
    </div>
  )
}
