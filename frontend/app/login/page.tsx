"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Shield } from "lucide-react"

export default function LoginPage() {
  const router = useRouter()
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError("")
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/login`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({ password }),
        }
      )
      if (res.ok || res.redirected) {
        router.push("/")
      } else {
        setError("Invalid password. Try again.")
      }
    } catch {
      setError("Cannot reach Sentinel backend.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--background)]
                    bg-[radial-gradient(ellipse_at_top,_#1e293b_0%,_transparent_60%)]">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8 gap-3">
          <div className="w-14 h-14 bg-black dark:bg-white rounded-2xl flex items-center justify-center shadow-xl">
            <Shield className="w-7 h-7 text-white dark:text-black" />
          </div>
          <div className="text-center">
            <h1 className="text-2xl font-bold tracking-tight">Sentinel</h1>
            <p className="text-sm text-[var(--muted-foreground)] mt-1">
              Sovereign Intelligence Platform
            </p>
          </div>
        </div>

        {/* Card */}
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-xl">
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider
                                text-[var(--muted-foreground)] mb-1.5">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                required
                autoFocus
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--muted)]
                           px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-black
                           dark:focus:ring-white transition-all"
              />
            </div>

            {error && (
              <p className="text-xs text-red-600 dark:text-red-400 font-medium">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading || !password}
              className="w-full rounded-lg bg-black dark:bg-white text-white dark:text-black
                         py-2.5 text-sm font-semibold tracking-wide transition-all
                         hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-[var(--muted-foreground)] mt-4">
          Biltiq — Sovereign AI Platform
        </p>
      </div>
    </div>
  )
}
