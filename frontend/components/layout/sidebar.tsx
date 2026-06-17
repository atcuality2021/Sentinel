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
    <aside className="group/sidebar fixed left-0 top-0 h-full z-40 flex flex-col py-4 gap-1
                      bg-[var(--card)] border-r border-[var(--border)]
                      w-16 hover:w-48 overflow-hidden transition-[width] duration-200 ease-in-out">
      {/* Logo */}
      <Link href="/" className="mb-4 mx-3 flex items-center gap-3 shrink-0">
        <div className="w-10 h-10 shrink-0 flex items-center justify-center bg-black dark:bg-white rounded-xl">
          <Shield className="w-5 h-5 text-white dark:text-black" />
        </div>
        <span className="text-sm font-bold whitespace-nowrap opacity-0 group-hover/sidebar:opacity-100
                         transition-opacity duration-150 delay-75">
          Sentinel
        </span>
      </Link>

      {NAV.map(({ href, icon: Icon, label }) => {
        const active = href === "/" ? path === "/" : path.startsWith(href)
        return (
          <Link
            key={href}
            href={href}
            className={cn(
              "mx-3 flex items-center gap-3 px-0 h-10 rounded-xl transition-all duration-150 shrink-0",
              active
                ? "bg-black dark:bg-white text-white dark:text-black"
                : "text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
            )}
          >
            <div className="w-10 h-10 shrink-0 flex items-center justify-center">
              <Icon className="w-4 h-4" />
            </div>
            <span className="text-sm font-medium whitespace-nowrap opacity-0
                             group-hover/sidebar:opacity-100 transition-opacity duration-150 delay-75">
              {label}
            </span>
          </Link>
        )
      })}

      {/* Theme toggle — pinned to bottom */}
      <div className="mt-auto mx-3">
        <button
          onClick={toggle}
          className="flex items-center gap-3 h-10 w-full rounded-xl transition-all duration-150
                     text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
        >
          <div className="w-10 h-10 shrink-0 flex items-center justify-center">
            {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </div>
          <span className="text-sm font-medium whitespace-nowrap opacity-0
                           group-hover/sidebar:opacity-100 transition-opacity duration-150 delay-75">
            {theme === "dark" ? "Light mode" : "Dark mode"}
          </span>
        </button>
      </div>
    </aside>
  )
}
