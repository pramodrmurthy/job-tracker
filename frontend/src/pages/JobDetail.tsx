import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Status } from '../api/types'
import { STATUSES, STATUS_LABELS } from '../api/types'
import { Button, Card, ErrorBox, PageHeader, ScoreBadge, SkeletonRows, StatusChip, Tag, inputCls, useToast } from '../components/ui'
import { fmtDate, fmtDateTime } from '../lib/format'

export default function JobDetail() {
  const id = Number(useParams().id)
  const toast = useToast()
  const qc = useQueryClient()
  const job = useQuery({ queryKey: ['job', id], queryFn: () => api.getJob(id) })
  const [status, setStatus] = useState<Status>('discovered')
  const [notes, setNotes] = useState('')
  useEffect(() => { if (job.data) { setStatus(job.data.status); setNotes(job.data.application.notes) } }, [job.data])

  const refresh = () => { qc.invalidateQueries({ queryKey: ['job', id] }); qc.invalidateQueries({ queryKey: ['jobs'] }); qc.invalidateQueries({ queryKey: ['summary'] }) }
  const save = useMutation({
    mutationFn: () => api.patchJob(id, { status: status !== job.data?.status ? status : undefined, notes: notes !== job.data?.application.notes ? notes : undefined }),
    onSuccess: () => { toast('success', 'Saved'); refresh() }, onError: (e: Error) => toast('error', e.message),
  })
  const rescore = useMutation({
    mutationFn: () => api.rescoreJob(id),
    onSuccess: () => { toast('success', 'Re-scored'); refresh() }, onError: (e: Error) => toast('error', e.message),
  })

  if (job.isLoading) return <SkeletonRows rows={8} />
  if (job.error) return <ErrorBox error={job.error} onRetry={() => job.refetch()} />
  const j = job.data!
  const dirty = status !== j.status || notes !== j.application.notes

  return (
    <>
      <p className="mb-2 text-sm"><Link to="/jobs" className="text-indigo-700 hover:underline">← Back to jobs</Link></p>
      <PageHeader title={j.title} subtitle={<>{[j.company, j.city, j.country].filter(Boolean).join(' · ') || 'Location not listed'} · {j.external_id}</>}
        actions={<StatusChip status={j.status} />} />
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card title="Description">
            <p className="whitespace-pre-wrap text-sm text-slate-800">{j.description || 'No description was provided.'}</p>
            {j.skills.length > 0 && <div className="mt-3 flex flex-wrap gap-1" aria-label="Skills">{j.skills.map((s) => <Tag key={s}>{s}</Tag>)}</div>}
          </Card>
          <Card title="Match assessment" actions={<Button onClick={() => rescore.mutate()} disabled={rescore.isPending}>{rescore.isPending ? 'Re-scoring…' : 'Re-score'}</Button>}>
            {j.assessment ? (
              <div className="space-y-2 text-sm">
                <div className="flex items-center gap-3"><ScoreBadge score={j.assessment.score} /><span>{j.assessment.relevant ? 'Considered relevant' : 'Considered not relevant'}</span></div>
                <p className="text-slate-800">{j.assessment.reason}</p>
                <p className="text-xs text-slate-500">Scored by {j.assessment.model} on {fmtDateTime(j.assessment.created_at)}.</p>
                <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-900">This score is an AI model's opinion of how well the role fits your resume. It is not a probability of being hired and can be wrong. Read the job yourself before applying.</p>
              </div>
            ) : <p className="text-sm text-slate-600">This job has not been scored yet.</p>}
          </Card>
          <Card title="Status history">
            {j.history.length === 0 ? <p className="text-sm text-slate-600">No changes recorded.</p> : (
              <ol className="space-y-2 border-l-2 border-slate-200 pl-4 text-sm">
                {[...j.history].reverse().map((h, i) => (
                  <li key={i}><span className="font-medium">{h.from ? `${STATUS_LABELS[h.from]} → ` : ''}{STATUS_LABELS[h.to]}</span>
                    <span className="text-slate-600"> · {fmtDateTime(h.at)} · {h.by === 'user' ? 'by you' : 'automatic'}</span>{h.note && <div className="text-slate-600">{h.note}</div>}</li>
                ))}
              </ol>
            )}
          </Card>
        </div>
        <div className="space-y-4">
          <Card title="Your application">
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
              <label className="block text-sm font-medium">Status
                <select className={inputCls} value={status} onChange={(e) => setStatus(e.target.value as Status)}>
                  {STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
                </select>
              </label>
              {status === 'applied' && j.status !== 'applied' && <p className="text-xs text-slate-600">Mark as applied only after you have actually sent the application.</p>}
              <label className="block text-sm font-medium">Notes
                <textarea className={inputCls} rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} />
              </label>
              <Button variant="primary" type="submit" disabled={!dirty || save.isPending}>{save.isPending ? 'Saving…' : 'Save changes'}</Button>
            </form>
            <dl className="mt-4 space-y-1 text-xs text-slate-600">
              <div className="flex justify-between"><dt>Applied</dt><dd>{fmtDate(j.application.applied_at)}</dd></div>
              <div className="flex justify-between"><dt>Last follow-up</dt><dd>{fmtDate(j.application.last_follow_up_at)}</dd></div>
            </dl>
          </Card>
          <Card title="Job info">
            <dl className="space-y-1 text-sm">
              {([['Category', j.category], ['Sub-category', j.sub_category], ['Experience', j.experience_level], ['Employment', j.employment_type], ['Work mode', j.work_mode],
                ['Salary', j.salary_text], ['Visa sponsored', j.visa_sponsored === null ? null : j.visa_sponsored ? 'Yes' : 'No'], ['Recruiter', j.hr_name], ['Email', j.hr_email ? (j.recruiter_contacted_at ? `${j.hr_email} (already contacted ${fmtDate(j.recruiter_contacted_at)})` : j.hr_email) : null],
                ['Phone', j.hr_phone], ['Posted', j.posted_at ? fmtDate(j.posted_at) : null], ['First seen', fmtDate(j.first_seen_at)], ['Last seen', fmtDate(j.last_seen_at)], ['Listing', j.listing_status]] as [string, string | null][]).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3"><dt className="text-slate-600">{k}</dt><dd className="text-right">{v ?? '-'}</dd></div>
              ))}
            </dl>
          </Card>
          <Card title="Email drafts">
            {j.drafts.length === 0 ? <p className="text-sm text-slate-600">No draft for this job yet.</p> : (
              <ul className="space-y-2 text-sm">
                {j.drafts.map((d) => (
                  <li key={d.id}><Link className="text-indigo-800 hover:underline" to={`/drafts?open=${d.id}`}>{d.subject}</Link>
                    <div className="text-xs text-slate-600">To {d.recipient} · {d.status === 'gmail_draft' ? 'in Gmail drafts' : d.status}</div></li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  )
}
