import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../api/client'
import type { Run, StartRun } from '../api/types'
import { RunProgress, RunStatsGrid } from '../components/RunStats'
import { Button, Card, ConfirmDialog, EmptyState, ErrorBox, PageHeader, Pagination, RunChip, SkeletonRows, Tag, inputCls, useToast } from '../components/ui'
import { fmtDateTime, fmtDuration, fmtNum } from '../lib/format'

const PAGE_SIZE = 15
const isActive = (r: Run) => r.status === 'queued' || r.status === 'running'

export default function Runs() {
  const qc = useQueryClient()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: api.listProfiles })
  const runs = useQuery({
    queryKey: ['runs', page], queryFn: () => api.listRuns(page, PAGE_SIZE), placeholderData: (p) => p,
    refetchInterval: (q) => (q.state.data?.items.some(isActive) ? 2000 : false),
  })
  const [profileId, setProfileId] = useState<number | null>(null)
  const [mode, setMode] = useState<StartRun['mode']>('incremental')
  const [dryRun, setDryRun] = useState(false)
  const [conflict, setConflict] = useState<string | null>(null)
  const [confirmFull, setConfirmFull] = useState(false)

  const active = runs.data?.items.find(isActive)
  const effectiveProfile = profileId ?? profiles.data?.[0]?.id ?? 1
  const start = useMutation({
    mutationFn: () => api.startRun({ profile_id: effectiveProfile, mode, dry_run: dryRun }),
    onSuccess: (r) => { setConflict(null); setConfirmFull(false); toast('success', `Run #${r.id} started`); qc.invalidateQueries({ queryKey: ['runs'] }) },
    onError: (e: Error) => {
      setConfirmFull(false)
      if (e instanceof ApiError && e.status === 409) { setConflict('A run is already in progress. Wait for it to finish, or cancel it below, then start a new one.'); qc.invalidateQueries({ queryKey: ['runs'] }) }
      else toast('error', e.message)
    },
  })
  const cancel = useMutation({
    mutationFn: (id: number) => api.cancelRun(id),
    onSuccess: () => { toast('success', 'Run cancelled'); qc.invalidateQueries({ queryKey: ['runs'] }) }, onError: (e: Error) => toast('error', e.message),
  })
  const retry = useMutation({
    mutationFn: (id: number) => api.retryRun(id),
    onSuccess: (r) => { toast('success', `Retry started as run #${r.id}`); qc.invalidateQueries({ queryKey: ['runs'] }) },
    onError: (e: Error) => toast('error', e.message),
  })

  return (
    <>
      <PageHeader title="Runs" subtitle="Each run fetches jobs, scores them against your resume and writes email drafts. Nothing is sent." />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Start a run">
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); setConflict(null); if (mode === 'full') setConfirmFull(true); else start.mutate() }}>
            <label className="block text-sm font-medium">Search profile
              <select className={inputCls} value={effectiveProfile} onChange={(e) => setProfileId(Number(e.target.value))} disabled={profiles.isLoading}>
                {profiles.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>) ?? <option value={1}>Default</option>}
              </select>
            </label>
            <fieldset>
              <legend className="text-sm font-medium">Mode</legend>
              <label className="mt-1 flex items-start gap-2 text-sm"><input type="radio" name="mode" checked={mode === 'incremental'} onChange={() => setMode('incremental')} className="mt-1" />
                <span><strong>Incremental</strong><br /><span className="text-slate-600">Only look at jobs not seen before. Fast; use this normally.</span></span></label>
              <label className="mt-2 flex items-start gap-2 text-sm"><input type="radio" name="mode" checked={mode === 'full'} onChange={() => setMode('full')} className="mt-1" />
                <span><strong>Full</strong><br /><span className="text-slate-600">Re-read every listing. Slow; known jobs and drafts are not duplicated.</span></span></label>
            </fieldset>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} /> Dry run (fetch and score, but write no drafts)</label>
            {conflict && <p role="alert" className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">{conflict}</p>}
            <Button variant="primary" type="submit" disabled={start.isPending || !!active}>{start.isPending ? 'Starting…' : active ? 'A run is in progress' : 'Start run'}</Button>
          </form>
        </Card>
        <Card title={active ? `Run #${active.id} in progress` : 'No run in progress'} className="lg:col-span-2"
          actions={active && <Button variant="danger" disabled={cancel.isPending} onClick={() => cancel.mutate(active.id)}>Cancel run</Button>}>
          {active ? <div className="space-y-4"><RunProgress run={active} /><RunStatsGrid stats={active.stats} /></div>
            : <p className="text-sm text-slate-600">Start a run on the left. Progress appears here and updates every two seconds.</p>}
        </Card>
      </div>

      <h2 className="mb-2 mt-6 text-sm font-semibold text-slate-800">Run history</h2>
      {runs.error ? <ErrorBox error={runs.error} onRetry={() => runs.refetch()} /> : runs.isLoading ? <SkeletonRows rows={5} />
        : !runs.data?.items.length ? <EmptyState title="No runs yet" hint="Start your first run above." />
          : (
            <>
              <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
                <table className="w-full min-w-[48rem] text-left text-sm">
                  <caption className="sr-only">Run history</caption>
                  <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-600">
                    <tr>{['Run', 'Status', 'Started', 'Duration', 'New', 'Known', 'Matched', 'Drafts', 'Errors', ''].map((h) => <th key={h} scope="col" className="px-3 py-2">{h}</th>)}</tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {runs.data.items.map((r) => (
                      <tr key={r.id} className="hover:bg-slate-50">
                        <td className="px-3 py-2"><Link to={`/runs/${r.id}`} className="font-medium text-indigo-800 hover:underline">#{r.id}</Link> {r.dry_run && <Tag>Dry run</Tag>}</td>
                        <td className="px-3 py-2"><RunChip status={r.status} /></td><td className="px-3 py-2 whitespace-nowrap">{fmtDateTime(r.started_at)}</td>
                        <td className="px-3 py-2">{fmtDuration(r.duration_s)}</td><td className="px-3 py-2">{fmtNum(r.stats.new_jobs)}</td><td className="px-3 py-2">{fmtNum(r.stats.known_jobs)}</td>
                        <td className="px-3 py-2">{fmtNum(r.stats.matched)}</td><td className="px-3 py-2">{fmtNum(r.stats.drafts_generated)}</td><td className="px-3 py-2">{fmtNum(r.stats.errors)}</td>
                        <td className="px-3 py-2 text-right">{(r.status === 'failed' || r.status === 'partial') && <Button disabled={!!active || retry.isPending} onClick={() => retry.mutate(r.id)}>Retry</Button>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination page={page} pageSize={PAGE_SIZE} total={runs.data.total} onPage={setPage} />
            </>
          )}
      <ConfirmDialog open={confirmFull} title="Start a full run?" confirmLabel="Start full run" busy={start.isPending} onCancel={() => setConfirmFull(false)} onConfirm={() => start.mutate()}>
        A full run re-reads every listing and can take several minutes and many AI calls. Known jobs and existing drafts are not duplicated.
      </ConfirmDialog>
    </>
  )
}
