import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useQueries, useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Run, TimeseriesMetric } from '../api/types'
import { DistChart, FunnelChart, RunsChart, TimeseriesChart } from '../components/charts'
import type { SeriesDef } from '../components/charts'
import { Button, Card, EmptyState, ErrorBox, PageHeader, RunChip, Skeleton, SkeletonRows } from '../components/ui'
import { daysAgo, fmtDateTime, fmtDuration, fmtNum, fmtPct, isoDay } from '../lib/format'
import { distLink, funnelLink, kpiLink } from '../lib/drill'

const KPIS: { key: keyof import('../api/types').Kpis; label: string; hint: string }[] = [
  { key: 'total_unique_jobs', label: 'Unique jobs discovered', hint: 'Duplicate listings are counted once' },
  { key: 'latest_run_discovered', label: 'Latest run: discovered', hint: 'Unique jobs seen in the most recent run' },
  { key: 'new_since_previous_run', label: 'New since previous run', hint: 'First seen in the last successful run' },
  { key: 'previously_seen', label: 'Previously seen', hint: 'Seen again in the last successful run' },
  { key: 'passed_filters', label: 'Passed filters', hint: 'Met the search profile filters' },
  { key: 'matched', label: 'Matched', hint: 'AI score at or above the threshold' },
  { key: 'shortlisted', label: 'Shortlisted', hint: 'Reached shortlisted or later' },
  { key: 'drafts_generated', label: 'Email drafts generated', hint: 'Drafts written in this app' },
  { key: 'gmail_drafts_created', label: 'Gmail drafts created', hint: 'Drafts saved in your Gmail (not sent)' },
  { key: 'applied', label: 'Applications submitted', hint: 'Marked as applied by you' },
  { key: 'employer_replied', label: 'Employer replies', hint: 'Marked as replied' },
  { key: 'interviews', label: 'Interviews', hint: 'Interview scheduled or completed' },
  { key: 'offers', label: 'Offers', hint: 'Offer received' },
]
const SERIES: (SeriesDef & { metric: TimeseriesMetric })[] = [
  { key: 'discovered', name: 'Discovered', metric: 'discovered' }, { key: 'new', name: 'New', metric: 'new', dash: '4 3' },
  { key: 'matched', name: 'Matched', metric: 'matched' }, { key: 'applied', name: 'Applied', metric: 'applied' },
  { key: 'replied', name: 'Replied', metric: 'replied' },
]

function RunStrip({ label, run }: { label: string; run: Run | null }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      {run ? (
        <Link to={`/runs/${run.id}`} className="mt-1 block text-sm hover:underline">
          <span className="mr-2 font-semibold">Run #{run.id}</span><RunChip status={run.status} />
          <div className="mt-1 text-slate-600">{fmtDateTime(run.started_at)} · {fmtDuration(run.duration_s)}</div>
        </Link>
      ) : <div className="mt-1 text-sm text-slate-500">No run yet</div>}
    </div>
  )
}

export default function Dashboard() {
  const nav = useNavigate()
  const [sp, setSp] = useSearchParams()
  const range = { from: sp.get('from') ?? daysAgo(90), to: sp.get('to') ?? isoDay(new Date()) }
  const [bucket, setBucket] = useState<'day' | 'week'>('day')
  const setRange = (k: 'from' | 'to', v: string) => { const n = new URLSearchParams(sp); n.set(k, v); setSp(n, { replace: true }) }

  const summary = useQuery({ queryKey: ['summary', range], queryFn: () => api.summary(range) })
  const funnel = useQuery({ queryKey: ['funnel', range], queryFn: () => api.funnel(range) })
  const rates = useQuery({ queryKey: ['rates', range], queryFn: () => api.rates(range) })
  const runSeries = useQuery({ queryKey: ['runSeries', range], queryFn: () => api.runSeries(range) })
  const ts = useQueries({ queries: SERIES.map((s) => ({ queryKey: ['ts', s.metric, bucket, range], queryFn: () => api.timeseries(s.metric, bucket, range) })) })
  const dist = useQueries({ queries: (['country', 'category', 'score', 'status'] as const).map((by) => ({ queryKey: ['dist', by, range], queryFn: () => api.distributions(by, range) })) })

  const tsData = useMemo(() => {
    const byDate = new Map<string, Record<string, number | string>>()
    ts.forEach((q, i) => q.data?.forEach((p) => { const row = byDate.get(p.date) ?? { date: p.date }; row[SERIES[i].key] = p.value; byDate.set(p.date, row) }))
    return [...byDate.values()].sort((a, b) => String(a.date).localeCompare(String(b.date)))
  }, [ts])
  const tsLoading = ts.some((q) => q.isLoading), tsError = ts.find((q) => q.error)?.error

  const latestId = summary.data?.latest_run?.id
  const inputCls = 'rounded-md border border-slate-300 bg-white px-2 py-1 text-sm'

  return (
    <>
      <PageHeader title="Dashboard" subtitle="Your job search at a glance. A dash (-) means no data; 0 is a real zero."
        actions={
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <label className="flex items-center gap-1">From <input type="date" className={inputCls} value={range.from} max={range.to} onChange={(e) => setRange('from', e.target.value)} /></label>
            <label className="flex items-center gap-1">To <input type="date" className={inputCls} value={range.to} min={range.from} onChange={(e) => setRange('to', e.target.value)} /></label>
          </div>
        } />

      {summary.error && <ErrorBox error={summary.error} onRetry={() => summary.refetch()} />}
      {summary.isLoading && <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-20" />)}</div>}
      {summary.data && (
        <>
          <section aria-label="Key metrics" className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
            {KPIS.map((k) => (
              <Link key={k.key} to={kpiLink(k.key, latestId)} title={k.hint}
                className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition hover:border-indigo-300 hover:shadow">
                <div className="text-xs font-medium text-slate-600">{k.label}</div>
                <div className="mt-1 text-2xl font-semibold text-slate-900">{fmtNum(summary.data.kpis[k.key])}</div>
              </Link>
            ))}
          </section>
          <section aria-label="Run status" className="mt-4 grid gap-3 md:grid-cols-3">
            <RunStrip label="Latest run" run={summary.data.latest_run} />
            <RunStrip label="Last successful run" run={summary.data.last_successful_run} />
            <RunStrip label="Last attempted run" run={summary.data.last_attempted_run} />
          </section>
        </>
      )}

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Card title="Application funnel" className="lg:col-span-2" actions={<span className="text-xs text-slate-500">Each rate is vs the previous stage. Click a bar to see the jobs.</span>}>
          {funnel.error ? <ErrorBox error={funnel.error} onRetry={() => funnel.refetch()} />
            : funnel.isLoading ? <SkeletonRows /> : funnel.data && funnel.data[0]?.count === 0
              ? <EmptyState title="No jobs in this date range" hint="Run the pipeline from the Runs page, or widen the dates." />
              : funnel.data && <FunnelChart stages={funnel.data} onSelect={(s) => nav(funnelLink(s))} />}
        </Card>
        <Card title="Outcome rates (of applications submitted)">
          {rates.error ? <ErrorBox error={rates.error} onRetry={() => rates.refetch()} /> : rates.isLoading ? <SkeletonRows rows={3} /> : (
            <dl className="space-y-4">
              {Object.entries(rates.data ?? {}).map(([k, r]) => (
                <div key={k}>
                  <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{k.replace(/_/g, ' ')}</dt>
                  <dd className="text-2xl font-semibold">{fmtPct(r.value)}</dd>
                  <dd className="text-xs text-slate-600">{r.numerator} of {r.denominator} · {r.definition}</dd>
                  {r.value === null && <dd className="text-xs text-slate-500">No applications yet, so there is nothing to divide by.</dd>}
                </div>
              ))}
            </dl>
          )}
        </Card>
      </div>

      <Card title="Activity over time" className="mt-4" actions={
        <div role="group" aria-label="Bucket size" className="flex gap-1">
          {(['day', 'week'] as const).map((b) => <Button key={b} variant={bucket === b ? 'primary' : 'secondary'} aria-pressed={bucket === b} onClick={() => setBucket(b)}>{b === 'day' ? 'Daily' : 'Weekly'}</Button>)}
        </div>}>
        {tsError ? <ErrorBox error={tsError} onRetry={() => ts.forEach((q) => q.refetch())} /> : tsLoading ? <SkeletonRows /> : <TimeseriesChart data={tsData} series={SERIES} />}
      </Card>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {([['country', 'Jobs by country', 0], ['category', 'Jobs by category', 1], ['score', 'Match-score distribution', 2], ['status', 'Application status', 3]] as const).map(([by, title, color], i) => (
          <Card key={by} title={title}>
            {dist[i].error ? <ErrorBox error={dist[i].error} onRetry={() => dist[i].refetch()} />
              : dist[i].isLoading ? <SkeletonRows rows={4} />
                : dist[i].data && dist[i].data!.length ? <DistChart title={title} data={dist[i].data!} color={color} onSelect={(l) => nav(distLink(by, l))} />
                  : <EmptyState title="No data" />}
          </Card>
        ))}
      </div>

      <Card title="Each run: new versus previously seen" className="mt-4">
        {runSeries.error ? <ErrorBox error={runSeries.error} onRetry={() => runSeries.refetch()} /> : runSeries.isLoading ? <SkeletonRows /> : runSeries.data && runSeries.data.length
          ? <RunsChart data={runSeries.data} /> : <EmptyState title="No runs in this range" hint="Start one from the Runs page." action={<Link className="text-sm text-indigo-700 underline" to="/runs">Go to Runs</Link>} />}
      </Card>
    </>
  )
}
