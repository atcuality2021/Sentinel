import { Sidebar } from "@/components/layout/sidebar"
import { Topbar } from "@/components/layout/topbar"
import { ToastProvider } from "@/components/ui/toast"
import { ThemeProvider } from "@/lib/theme"

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <ToastProvider>
        <div className="flex h-screen overflow-hidden">
          <Sidebar />
          <div className="flex flex-col flex-1 ml-16 min-w-0">
            <Topbar />
            <main className="flex-1 overflow-y-auto bg-[var(--background)] p-6">
              {children}
            </main>
          </div>
        </div>
      </ToastProvider>
    </ThemeProvider>
  )
}
