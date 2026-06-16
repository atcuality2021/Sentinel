"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import { useTheme } from "@/lib/theme"
import {
  LayoutDashboard,
  FolderOpen,
  Target,
  Bot,
  Users,
  Settings,
  Zap,
  Shield,
  Sun,
  Moon,
} from "lucide-react"

const NAV = [
  { href: "/", icon: LayoutDashboard, label: "Dashboard" },
  { href: "/projects",  icon: FolderOpen,       label: "Projects"  },
  { href: "/focus",     icon: Target,            label: "Focus"     },
  { href: "/agents",    icon: Bot,               label: "Agents"    },
  { href: "/personas",  icon: Users,             label: "Personas"  },
  { href: "/artifacts", icon: Zap,               label: "Artifacts" },
  { href: "/settings",  icon: Settings,          label: "Settings"  },
]

export function Sidebar() {
  const path = usePathname()
  const { theme, toggle } = useTheme()

  return (
    <aside className="fixed left-0 top-0 h-full w-16 z-40 flex flex-col items-center py-4 gap-1
                      bg-[var(--card)] border-r border-[var(--border)]">
      {/* Logo */}
      <Link href="/" className="mb-4 flex items-center justify-center w-10 h-10
                                 bg-black dark:bg-white rounded-xl">
        <Shield className="w-5 h-5 text-white dark:text-black" />
      </Link>

      {NAV.map(({ href, icon: Icon, label }) => {
        const active = href === "/" ? path === "/" : path.startsWith(href)
        return (
          <Link
            key={href}
            href={href}
            title={label}
            className={cn(
              "group relative flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-150",
              active
                ? "bg-black dark:bg-white text-white dark:text-black"
                : "text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
            )}
          >
            <Icon className="w-4 h-4" />
            <span className="pointer-events-none absolute left-14 whitespace-nowrap
                             rounded-md bg-black dark:bg-white text-white dark:text-black
                             px-2 py-1 text-xs font-medium opacity-0 group-hover:opacity-100
                             transition-opacity shadow-lg z-50">
              {label}
            </span>
          </Link>
        )
      })}

      {/* Theme toggle — pinned to bottom */}
      <div className="mt-auto">
        <button
          onClick={toggle}
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          className="group relative flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-150
                     text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
        >
          {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          <span className="pointer-events-none absolute left-14 whitespace-nowrap
                           rounded-md bg-black dark:bg-white text-white dark:text-black
                           px-2 py-1 text-xs font-medium opacity-0 group-hover:opacity-100
                           transition-opacity shadow-lg z-50">
            {theme === "dark" ? "Light mode" : "Dark mode"}
          </span>
        </button>
      </div>
    </aside>
  )
}
