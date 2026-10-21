import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { JobQuery, Status } from '../api/types'
import { STATUSES, STATUS_LABELS } from '../api/types'
import { Button, Card, ConfirmDialog, EmptyState, ErrorBox, PageHeader, Pagination, ScoreBadge, SkeletonRows, StatusChip, Tag, inputCls, useDebounced, useToast } from '../components/ui'
import { fmtDate } from '../lib/format'

const PAGE_SIZE = 25
const BULK: { status: Status; label: string; danger?: boolean }[] = [
  { status: 'shortlisted', label: 'Shortlist' }, { status: 'applied', label: 'Mark applied' },
  { status: 'rejected', label: 'Reject', danger: true }, { status: 'not_interested', label: 'Not interested', danger: true },
]

export default function Jobs() {
  const [sp, setSp] = useSearchParams()
  const toast = useToast()
  const qc = useQueryClient()
  const get = (k: string) => sp.get(k) ?? ''
  const set = (patch: Record<string, string | null>) => {
    const n = new URLSearchParams(sp)
    for (const [k, v] of Object.entries(patch)) { if (v === null || v === '') n.delete(k); else n.set(k, v) }
    if (!('page' in patch)) n.delete('page')
    setSp(n, { replace: true })
  }

  const [search, setSearch] = useState(get('query'))
  const debounced = useDebounced(search)
  useEffect(() => { if (debounced !== get('query')) set({ query: debounced }) /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [debounced])
  useEffect(() => { setSearch(get('query')) /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [sp.get('query')])

  const page = Number(get('page') || 1)
  const query: JobQuery = {
    query: get('query') || undefined, status: get('status') || undefined, country: get('country') || undefined, category: get('category') || undefined,
    min_score: get('min_score') ? Number(get('min_score')) : undefined, max_score: get('max_score') ? Number(get('max_score')) : undefined,
    run_id: get('run_id') ? Number(get('run_id')) : undefined, new_only: get('new_only') === 'true' || undefined,
    has_draft: get('has_draft') === 'true' ? true : get('has_draft') === 'false' ? false : undefined,
    recruiter_contacted: get('recruiter_contacted') === 'true' ? true : get('recruiter_contacted') === 'false' ? false : undefined,
    sort: (get('sort') as JobQuery['sort']) || 'first_seen', order: (get('order') as JobQuery['order']) || 'desc', page, page_size: PAGE_SIZE,
  }
  const jobs = useQuery({ queryKey: ['jobs', query], queryFn: () => api.listJobs(query), placeholderData: (prev) => prev })
  const countries = useQuery({ queryKey: ['dist', 'country', 'all'], queryFn: () => api.distributions('country', { from: '2000-01-01' }) })
  const categories = useQuery({ queryKey: ['dist', 'category', 'all'], queryFn: () => api.distributions('category', { from: '2000-01-01' }) })

  const [selected, setSelected] = useState<Set<number>>(new Set())
  useEffect(() => setSelected(new Set()), [sp])
  const [pending, setPending] = useState<{ status: Status; label: string; danger?: boolean } | null>(null)
  const bulk = useMutation({
    mutationFn: (status: Status) => api.bulkJobs([...selected], status),
    onSuccess: (r, status) => { toast('success', `${r.updated} job(s) set to "${STATUS_LABELS[status]}"`); setPending(null); setSelected(new Set()); qc.invalidateQueries() },
    onError: (e: Error) => { toast('error', e.message); setPending(null) },
  })

  const items = jobs.data?.items ?? []
  const allOnPage = items.length > 0 && items.every((j) => selected.has(j.id))
  const toggleAll = () => setSelected(allOnPage ? new Set() : new Set(items.map((j) => j.id)))
  const activeFilters = useMemo(() => ['query', 'status', 'country', 'category', 'min_score', 'max_score', 'run_id', 'new_only', 'has_draft', 'recruiter_contacted'].filter((k) => sp.get(k)), [sp])
  const sortKey = `${query.sort}:${query.order}`

  return (
    <>
      <PageHeader title="Jobs" subtitle="Everything discovered, with the AI match assessment and your application status." />
      <Card>
        <form className="grid gap-3 md:grid-cols-3 xl:grid-cols-6" onSubmit={(e) => e.preventDefault()} aria-label="Job filters">
          <label className="text-sm md:col-span-2">Search
            <input className={inputCls} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Title, company, recruiter email…" />
          </label>
          <label className="text-sm">Status
            <select className={inputCls} value={get('status')} onChange={(e) => set({ status: e.target.value })}>
              <option value="">Any</option>{STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
            </select>
          </label>
          <label className="text-sm">Country
            <select className={inputCls} value={get('country')} onChange={(e) => set({ country: e.target.value })}>
              <option value="">Any</option>{get('country') && !countries.data?.some((c) => c.label === get('country')) && <option>{get('country')}</option>}
              {countries.data?.map((c) => <option key={c.label} value={c.label}>{c.label}</option>)}
            </select>
          </label>
          <label className="text-sm">Category
            <select className={inputCls} value={get('category')} onChange={(e) => set({ category: e.target.value })}>
              <option value="">Any</option>{get('category') && !categories.data?.some((c) => c.label === get('category')) && <option>{get('category')}</option>}
              {categories.data?.map((c) => <option key={c.label} value={c.label}>{c.label}</option>)}
            </select>
          </label>
          <label className="text-sm">Sort
            <select className={inputCls} value={sortKey} onChange={(e) => { const [s, o] = e.target.value.split(':'); set({ sort: s, order: o }) }}>
              <option value="first_seen:desc">Newest first</option><option value="first_seen:asc">Oldest first</option>
              <option value="score:desc">Score, high to low</option><option value="score:asc">Score, low to high</option>
              <option value="title:asc">Title A–Z</option>
            </select>
          </label>
          <label className="text-sm">Min score
            <input type="number" min={0} max={100} className={inputCls} value={get('min_score')} onChange={(e) => set({ min_score: e.target.value })} />
          </label>
          <label className="text-sm">Max score
            <input type="number" min={0} max={100} className={inputCls} value={get('max_score')} onChange={(e) => set({ max_score: e.target.value })} />
          </label>
          <label className="flex items-end gap-2 pb-1.5 text-sm"><input type="checkbox" checked={get('new_only') === 'true'} onChange={(e) => set({ new_only: e.target.checked ? 'true' : null })} /> New only</label>
          <label className="flex items-end gap-2 pb-1.5 text-sm"><input type="checkbox" checked={get('has_draft') === 'true'} onChange={(e) => set({ has_draft: e.target.checked ? 'true' : null })} /> Has draft</label>
          <label className="text-sm">Recruiter
            <select className={inputCls} value={get('recruiter_contacted')} onChange={(e) => set({ recruiter_contacted: e.target.value })}>
              <option value="">Any</option><option value="true">Already contacted</option><option value="false">Not contacted yet</option>
            </select>
          </label>
          <div className="flex items-end">{activeFilters.length > 0 && <Button onClick={() => setSp({}, { replace: true })}>Clear filters ({activeFilters.length})</Button>}</div>
        </form>
        {get('run_id') && <p className="mt-2 text-xs text-slate-600">Showing jobs seen in run #{get('run_id')}.</p>}
      </Card>

      <div className="mt-4">
        {selected.size > 0 && (
          <div role="region" aria-label="Bulk actions" className="mb-3 flex flex-wrap items-center gap-2 rounded-md bg-indigo-50 px-3 py-2 text-sm">
            <strong>{selected.size} selected</strong>
            {BULK.map((b) => <Button key={b.status} variant={b.danger ? 'secondary' : 'primary'} onClick={() => setPending(b)}>{b.label}</Button>)}
            <Button variant="ghost" onClick={() => setSelected(new Set())}>Clear</Button>
          </div>
        )}
        {jobs.error ? <ErrorBox error={jobs.error} onRetry={() => jobs.refetch()} />
          : jobs.isLoading ? <SkeletonRows rows={8} />
            : items.length === 0 ? <EmptyState title={activeFilters.length ? 'No jobs match these filters' : 'No jobs yet'} hint={activeFilters.length ? 'Try clearing a filter.' : 'Start a run from the Runs page to discover jobs.'}
              action={activeFilters.length ? <Button onClick={() => setSp({}, { replace: true })}>Clear filters</Button> : <Link className="text-sm text-indigo-700 underline" to="/runs">Go to Runs</Link>} />
              : (
                <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
                  <table className="w-full min-w-[56rem] text-left text-sm">
                    <caption className="sr-only">Jobs, {jobs.data?.total} results</caption>
                    <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-600">
                      <tr>
                        <th scope="col" className="w-10 px-3 py-2"><input type="checkbox" aria-label="Select all jobs on this page" checked={allOnPage} onChange={toggleAll} /></th>
                        <th scope="col" className="px-3 py-2">Title</th><th scope="col" className="px-3 py-2">Country</th><th scope="col" className="px-3 py-2">Exp.</th>
                        <th scope="col" className="px-3 py-2">Score</th><th scope="col" className="px-3 py-2">Status</th><th scope="col" className="px-3 py-2">First seen</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {items.map((j) => (
                        <tr key={j.id} className={selected.has(j.id) ? 'bg-indigo-50/50' : 'hover:bg-slate-50'}>
                          <td className="px-3 py-2"><input type="checkbox" aria-label={`Select ${j.title}`} checked={selected.has(j.id)}
                            onChange={() => setSelected((s) => { const n = new Set(s); if (n.has(j.id)) n.delete(j.id); else n.add(j.id); return n })} /></td>
                          <td className="px-3 py-2">
                            <Link to={`/jobs/${j.id}`} className="font-medium text-indigo-800 hover:underline">{j.title}</Link>
                            <div className="text-xs text-slate-500">{j.company ?? j.hr_email ?? j.external_id}</div>
                            <div className="mt-0.5 flex gap-1">{j.has_draft && <Tag tone="green">Draft</Tag>}{j.recruiter_contacted_at && <Tag tone="amber"><span title={`This recruiter was last emailed on ${fmtDate(j.recruiter_contacted_at)} (about this or another job). It does not block drafting.`}>Recruiter contacted {fmtDate(j.recruiter_contacted_at)}</span></Tag>}{j.listing_status === 'missing' && <Tag tone="amber">No longer listed</Tag>}</div>
                          </td>
                          <td className="px-3 py-2">{j.country ?? '-'}</td><td className="px-3 py-2">{j.experience_level ?? '-'}</td>
                          <td className="px-3 py-2"><ScoreBadge score={j.score} /></td><td className="px-3 py-2"><StatusChip status={j.status} /></td>
                          <td className="px-3 py-2 whitespace-nowrap">{fmtDate(j.first_seen_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
        {jobs.data && jobs.data.total > 0 && <Pagination page={page} pageSize={PAGE_SIZE} total={jobs.data.total} onPage={(p) => set({ page: String(p) })} />}
      </div>

      <ConfirmDialog open={!!pending} title={`${pending?.label ?? ''}: ${selected.size} job(s)?`} confirmLabel={pending?.label} danger={pending?.danger} busy={bulk.isPending}
        onCancel={() => setPending(null)} onConfirm={() => pending && bulk.mutate(pending.status)}>
        This sets the status of the {selected.size} selected job(s) to <strong>{pending ? STATUS_LABELS[pending.status] : ''}</strong> and records it in each job's history.
        {pending?.status === 'applied' && ' Only mark jobs as applied once you have actually sent the application.'}
      </ConfirmDialog>
    </>
  )
}
