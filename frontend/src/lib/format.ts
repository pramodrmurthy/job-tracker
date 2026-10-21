import type { RunStatus, Status } from '../api/types'

/** null/undefined means "no data" and renders as "-"; a real 0 renders as "0". */
export const fmtNum = (v: number | null | undefined): string => (v === null || v === undefined ? '-' : v.toLocaleString())
export const fmtPct = (v: number | null | undefined): string => (v === null || v === undefined ? '-' : `${(v * 100).toFixed(1)}%`)

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '-' : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '-' : d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
export function fmtDuration(s: number | null | undefined): string {
  if (s === null || s === undefined) return '-'
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  return m < 60 ? `${m}m ${s % 60}s` : `${Math.floor(m / 60)}h ${m % 60}m`
}

export const isoDay = (d: Date): string => d.toISOString().slice(0, 10)
export const daysAgo = (n: number): string => isoDay(new Date(Date.now() - n * 86_400_000))

/** Text + colour classes for each lifecycle status (the label is always shown, so colour is never the only cue). */
export const STATUS_STYLE: Record<Status, string> = {
  discovered: 'bg-slate-100 text-slate-700 ring-slate-300',
  matched: 'bg-sky-50 text-sky-800 ring-sky-300',
  shortlisted: 'bg-indigo-50 text-indigo-800 ring-indigo-300',
  draft_generated: 'bg-violet-50 text-violet-800 ring-violet-300',
  gmail_draft_created: 'bg-fuchsia-50 text-fuchsia-800 ring-fuchsia-300',
  applied: 'bg-blue-50 text-blue-800 ring-blue-300',
  employer_replied: 'bg-teal-50 text-teal-800 ring-teal-300',
  interview_scheduled: 'bg-emerald-50 text-emerald-800 ring-emerald-300',
  interview_completed: 'bg-emerald-50 text-emerald-800 ring-emerald-300',
  offer_received: 'bg-green-100 text-green-900 ring-green-400',
  rejected: 'bg-rose-50 text-rose-800 ring-rose-300',
  withdrawn: 'bg-amber-50 text-amber-800 ring-amber-300',
  closed: 'bg-zinc-100 text-zinc-700 ring-zinc-300',
  not_interested: 'bg-zinc-100 text-zinc-600 ring-zinc-300',
}
export const RUN_STYLE: Record<RunStatus, string> = {
  queued: 'bg-slate-100 text-slate-700 ring-slate-300',
  running: 'bg-blue-50 text-blue-800 ring-blue-300',
  succeeded: 'bg-green-50 text-green-800 ring-green-300',
  partial: 'bg-amber-50 text-amber-800 ring-amber-300',
  failed: 'bg-rose-50 text-rose-800 ring-rose-300',
  cancelled: 'bg-zinc-100 text-zinc-700 ring-zinc-300',
}
/** Colour-blind-safe categorical palette (Okabe-Ito) used by every chart. */
export const PALETTE = ['#0072B2', '#E69F00', '#009E73', '#CC79A7', '#56B4E9', '#D55E00', '#F0E442', '#000000']
