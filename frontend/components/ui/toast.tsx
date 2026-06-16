"use client"
import { AnimatePresence, motion } from "motion/react"
import { createContext, useCallback, useContext, useState } from "react"
import { CheckCircle2, XCircle, AlertTriangle, X } from "lucide-react"

type ToastType = "success" | "error" | "info"
interface Toast { id: string; message: string; type: ToastType }
interface ToastCtx { toast: (message: string, type?: ToastType) => void }

const ToastContext = createContext<ToastCtx>({ toast: () => {} })

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const toast = useCallback((message: string, type: ToastType = "success") => {
    const id = Math.random().toString(36).slice(2)
    setToasts(prev => [...prev, { id, message, type }])
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 4000)
  }, [])

  const dismiss = (id: string) => setToasts(prev => prev.filter(t => t.id !== id))

  const ICON = { success: CheckCircle2, error: XCircle, info: AlertTriangle }
  const COLOR = {
    success: "border-green-200 bg-green-50 text-green-800 dark:bg-green-900/20 dark:border-green-800 dark:text-green-300",
    error:   "border-red-200 bg-red-50 text-red-800 dark:bg-red-900/20 dark:border-red-800 dark:text-red-300",
    info:    "border-blue-200 bg-blue-50 text-blue-800 dark:bg-blue-900/20 dark:border-blue-800 dark:text-blue-300",
  }

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed top-4 right-4 z-[9999] flex flex-col gap-2 pointer-events-none">
        <AnimatePresence>
          {toasts.map(t => {
            const Icon = ICON[t.type]
            return (
              <motion.div
                key={t.id}
                initial={{ opacity: 0, x: 64, scale: 0.95 }}
                animate={{ opacity: 1, x: 0, scale: 1 }}
                exit={{ opacity: 0, x: 64, scale: 0.95 }}
                transition={{ type: "spring", duration: 0.4, bounce: 0.2 }}
                className={`pointer-events-auto flex items-start gap-2.5 px-3.5 py-3 rounded-xl border shadow-md text-sm max-w-xs ${COLOR[t.type]}`}
              >
                <Icon className="w-4 h-4 mt-0.5 shrink-0" />
                <span className="flex-1 leading-snug">{t.message}</span>
                <button onClick={() => dismiss(t.id)} className="shrink-0 opacity-60 hover:opacity-100">
                  <X className="w-3.5 h-3.5" />
                </button>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}

export const useToast = () => useContext(ToastContext)
