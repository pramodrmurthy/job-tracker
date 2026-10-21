import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { RunProgress, RunStatsGrid } from '../components/RunStats'
import { Button, Card, EmptyState, ErrorBox, PageHeader, RunChip, SkeletonRows, Tag, useToast } from '../components/ui'
import { fmtDateTime, fmtDuration } from '../lib/format'

export default function RunDetail() {
  const id = Number(useParams().id)
  const qc = useQueryClient()
  const toast = useToast()
  const run = useQuery({ queryKey: ['run', id], queryFn: () => api.getRun(id), refetchInterval: (q) => (q.state.data && (q.state.data.status === 'queued' || q.state.data.status === 'running') ? 2000 : false) })
  const refresh = () => { qc.invalidateQueries({ queryKey: ['run', id] }); qc.invalidateQueries({ queryKey: ['runs'] }) }
  const cancel = useMutation({ mutationFn: () => api.cancelRun(id), onSuccess: () => { toast('success', 'Run cancelled'); refresh() }, onError: (e: Error) => toast('error', e.message) })
  const retry = useMutation({ mutationFn: () => api.retryRun(id), onSuccess: (r) => { toast('success', `Retry started as run #${r.id}`); refresh() }, onError: (e: Error) => toast('error', e.message) })

  if (run.isLoading) return <SkeletonRows rows={6} />
  if (run.error) return <ErrorBox error={run.error} onRetry={() => run.refetch()} />
  const r = run.data!
  const active = r.status === 'queued' || r.status === 'running'
  return (
    <>
      <p className="mb-2 text-sm"><Link to="/runs" className="text-indigo-700 hover:underline">← Back to runs</Link></p>
      <PageHeader title={`Run #${r.id}`} subtitle={<>{r.mode} · profile {r.profile_id} · started {fmtDateTime(r.started_at)} · {fmtDuration(r.duration_s)}</>}
        actions={<><RunChip status={r.status} />{r.dry_run && <Tag>Dry run</Tag>}
          {active && <Button variant="danger" disabled={cancel.isPending} onClick={() => cancel.mutate()}>Cancel run</Button>}
          {(r.status === 'failed' || r.status === 'partial') && <Button variant="primary" disabled={retry.isPending} onClick={() => retry.mutate()}>Retry</Button>}
          <Link className="text-sm text-indigo-700 underline" to={`/jobs?run_id=${r.id}`}>Jobs seen in this run</Link></>} />
      <div className="space-y-4">
        {active && <Card title="Progress"><RunProgress run={r} /></Card>}
        <Card title="Results"><RunStatsGrid stats={r.stats} /><p className="mt-2 text-xs text-slate-600">A dash (-) means that stage has not run, which is different from 0.</p></Card>
        <Card title={`Errors and skipped records (${r.errors.length})`}>
          {r.errors.length === 0 ? <EmptyState title="No errors" hint="Completed work is kept even when later stages fail." /> : (
            <ul className="divide-y divide-slate-100 text-sm">
              {r.errors.map((e, i) => (
                <li key={i} className="py-2"><Tag tone="amber">{e.stage}</Tag> {e.job_id !== null && <Link className="text-indigo-700 underline" to={`/jobs/${e.job_id}`}>job {e.job_id}</Link>} <span className="text-slate-800">{e.message}</span></li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  )
}
