import { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from 'react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import type { RunStatus, Status } from '../api/types'
import { STATUS_LABELS } from '../api/types'
import { RUN_STYLE, STATUS_STYLE } from '../lib/format'

export const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(' ')

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'
const VARIANTS: Record<Variant, string> = {
  primary: 'bg-indigo-700 text-white hover:bg-indigo-800 disabled:bg-indigo-300',
  secondary: 'bg-white text-slate-800 ring-1 ring-slate-300 hover:bg-slate-50 disabled:text-slate-400',
  danger: 'bg-rose-700 text-white hover:bg-rose-800 disabled:bg-rose-300',
  ghost: 'text-slate-700 hover:bg-slate-100 disabled:text-slate-400',
}
export function Button({ variant = 'secondary', className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type="button"
      {...rest}
      className={cx('inline-flex items-center justify-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed', VARIANTS[variant], className)}
    />
  )
}

export function Card({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx('rounded-lg border border-slate-200 bg-white shadow-sm', className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-800">{title}</h2>
          {actions}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-slate-600">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

const chip = 'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset whitespace-nowrap'
export const StatusChip = ({ status }: { status: Status }) => <span className={cx(chip, STATUS_STYLE[status])}>{STATUS_LABELS[status]}</span>
export const RunChip = ({ status }: { status: RunStatus }) => <span className={cx(chip, RUN_STYLE[status])}>{status}</span>
export const Tag = ({ children, tone = 'slate' }: { children: ReactNode; tone?: 'slate' | 'amber' | 'green' }) => (
  <span className={cx(chip, tone === 'amber' ? 'bg-amber-50 text-amber-800 ring-amber-300' : tone === 'green' ? 'bg-green-50 text-green-800 ring-green-300' : 'bg-slate-100 text-slate-700 ring-slate-300')}>{children}</span>
)

/** Score shown as number + band word so it is readable without colour. This is an LLM opinion, not a probability. */
export function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return <span className="text-slate-400" aria-label="not scored">-</span>
  const band = score >= 80 ? 'Strong' : score >= 60 ? 'Good' : score >= 40 ? 'Weak' : 'Poor'
  const tone = score >= 80 ? 'bg-green-50 text-green-800 ring-green-300' : score >= 60 ? 'bg-sky-50 text-sky-800 ring-sky-300' : score >= 40 ? 'bg-amber-50 text-amber-800 ring-amber-300' : 'bg-slate-100 text-slate-600 ring-slate-300'
  return <span className={cx(chip, tone)} title="AI-generated match score; not a prediction of hiring outcome">{score} · {band}</span>
}

export const Skeleton = ({ className }: { className?: string }) => <div aria-hidden className={cx('skeleton h-4 w-full', className)} />
export const SkeletonRows = ({ rows = 5 }: { rows?: number }) => (
  <div role="status" aria-label="Loading" className="space-y-3">
    {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-6" />)}
  </div>
)

export function EmptyState({ title, hint, action }: { title: string; hint?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-slate-300 bg-white px-6 py-10 text-center">
      <p className="font-medium text-slate-800">{title}</p>
      {hint && <p className="max-w-md text-sm text-slate-600">{hint}</p>}
      {action}
    </div>
  )
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : 'Something went wrong'
  return (
    <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">
      <span>{message}</span>
      {onRetry && <Button onClick={onRetry}>Retry</Button>}
    </div>
  )
}

export function ProgressBar({ done, total, label }: { done: number; total: number; label: string }) {
  const pct = total ? Math.min(100, Math.round((done / total) * 100)) : 0
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-slate-600"><span>{label}</span><span>{pct}%</span></div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-200" role="progressbar" aria-label={label} aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-full bg-indigo-600 transition-all" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: (id: string) => ReactNode }) {
  const id = useId()
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium text-slate-800">{label}</label>
      {children(id)}
      {hint && <p className="text-xs text-slate-500">{hint}</p>}
    </div>
  )
}
export const inputCls = 'w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-900 placeholder:text-slate-400 disabled:bg-slate-100'

/** Native <dialog>: focus is trapped, Escape closes, and the page behind is inert. */
export function ConfirmDialog({
  open, title, children, confirmLabel = 'Confirm', danger, busy, onConfirm, onCancel,
}: { open: boolean; title: string; children: ReactNode; confirmLabel?: string; danger?: boolean; busy?: boolean; onConfirm: () => void; onCancel: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])
  return (
    <dialog ref={ref} onCancel={(e) => { e.preventDefault(); onCancel() }} aria-labelledby="dlg-title" className="m-auto w-[min(32rem,92vw)] rounded-lg p-0 shadow-xl backdrop:bg-slate-900/40">
      <div className="p-5">
        <h2 id="dlg-title" className="text-base font-semibold text-slate-900">{title}</h2>
        <div className="mt-2 text-sm text-slate-700">{children}</div>
        <div className="mt-5 flex justify-end gap-2">
          <Button onClick={onCancel} disabled={busy}>Cancel</Button>
          <Button variant={danger ? 'danger' : 'primary'} onClick={onConfirm} disabled={busy}>{busy ? 'Working…' : confirmLabel}</Button>
        </div>
      </div>
    </dialog>
  )
}

// ---------- toasts ----------
interface Toast { id: number; kind: 'success' | 'error'; text: string }
const ToastCtx = createContext<(kind: Toast['kind'], text: string) => void>(() => {})
export const useToast = () => useContext(ToastCtx)
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const push = useCallback((kind: Toast['kind'], text: string) => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, kind, text }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === 'error' ? 8000 : 4000)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex w-80 max-w-[92vw] flex-col gap-2" role="region" aria-label="Notifications" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} role={t.kind === 'error' ? 'alert' : 'status'} className={cx('rounded-md border px-4 py-3 text-sm shadow-md', t.kind === 'error' ? 'border-rose-200 bg-rose-50 text-rose-900' : 'border-green-200 bg-green-50 text-green-900')}>
            <strong className="mr-1">{t.kind === 'error' ? 'Error:' : 'Done:'}</strong>{t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1
  const to = Math.min(total, page * pageSize)
  return (
    <nav aria-label="Pagination" className="flex flex-wrap items-center justify-between gap-2 pt-3 text-sm text-slate-600">
      <span>{from}–{to} of {total.toLocaleString()}</span>
      <div className="flex items-center gap-2">
        <Button onClick={() => onPage(page - 1)} disabled={page <= 1}>Previous</Button>
        <span>Page {page} of {pages}</span>
        <Button onClick={() => onPage(page + 1)} disabled={page >= pages}>Next</Button>
      </div>
    </nav>
  )
}

export function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value)
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t) }, [value, ms])
  return v
}
