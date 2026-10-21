import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Draft, DraftStatus, GmailBulkResult } from '../api/types'
import { Button, Card, ConfirmDialog, EmptyState, ErrorBox, PageHeader, Pagination, SkeletonRows, Tag, cx, inputCls, useToast } from '../components/ui'
import { fmtDateTime } from '../lib/format'

const PAGE_SIZE = 25
const STATUS_TEXT: Record<DraftStatus, string> = { generated: 'Generated', approved: 'Approved', gmail_draft: 'In Gmail drafts', discarded: 'Discarded' }
const eligible = (d: Draft) => !d.gmail_draft_id && d.status !== 'discarded'

function Editor({ draft, onSaved }: { draft: Draft; onSaved: () => void }) {
  const toast = useToast()
  const [subject, setSubject] = useState(draft.subject)
  const [body, setBody] = useState(draft.body)
  const [confirmRegen, setConfirmRegen] = useState(false)
  const [confirmDiscard, setConfirmDiscard] = useState(false)
  useEffect(() => { setSubject(draft.subject); setBody(draft.body) }, [draft.id, draft.subject, draft.body])
  const locked = !!draft.gmail_draft_id
  const dirty = subject !== draft.subject || body !== draft.body

  const patch = useMutation({
    mutationFn: (b: Parameters<typeof api.patchDraft>[1]) => api.patchDraft(draft.id, b),
    onSuccess: () => { toast('success', 'Draft updated'); onSaved() }, onError: (e: Error) => toast('error', e.message),
  })
  const regen = useMutation({
    mutationFn: () => api.regenerateDraft(draft.id),
    onSuccess: () => { toast('success', 'Draft regenerated'); setConfirmRegen(false); onSaved() },
    onError: (e: Error) => { toast('error', e.message); setConfirmRegen(false) },
  })
  const download = async () => {
    try {
      const text = await api.draftMarkdown(draft.id)
      const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown' }))
      const a = document.createElement('a')
      a.href = url; a.download = `draft_${draft.id}.md`; a.click(); URL.revokeObjectURL(url)
    } catch (e) { toast('error', (e as Error).message) }
  }

  return (
    <Card title={`Draft #${draft.id}`} actions={<div className="flex items-center gap-2">{draft.edited && <Tag tone="amber">Edited</Tag>}<Tag>{draft.source === 'ai' ? 'AI-written' : 'Template'}</Tag></div>}>
      {locked && (
        <p role="note" className="mb-3 rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-700">
          This draft is already in your Gmail drafts, so it is read-only here. Edit it in Gmail.{' '}
          {draft.gmail_url && <a className="text-indigo-700 underline" href={draft.gmail_url} target="_blank" rel="noreferrer">Open in Gmail</a>}
        </p>
      )}
      <div className="space-y-3">
        <label className="block text-sm font-medium">To<input className={inputCls} value={draft.recipient} readOnly /></label>
        <label className="block text-sm font-medium">Subject<input className={inputCls} value={subject} onChange={(e) => setSubject(e.target.value)} disabled={locked} /></label>
        <label className="block text-sm font-medium">Body<textarea className={cx(inputCls, 'font-mono')} rows={16} value={body} onChange={(e) => setBody(e.target.value)} disabled={locked} /></label>
        <p className="text-xs text-slate-600">Roles: {draft.job_titles.join(', ')} · {draft.job_ids.map((id) => <Link key={id} className="mr-1 text-indigo-700 underline" to={`/jobs/${id}`}>job {id}</Link>)} · Updated {fmtDateTime(draft.updated_at)} · {STATUS_TEXT[draft.status]}</p>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" disabled={locked || !dirty || patch.isPending} onClick={() => patch.mutate({ subject, body })}>{patch.isPending ? 'Saving…' : 'Save edits'}</Button>
          <Button disabled={locked || draft.status === 'approved' || patch.isPending} onClick={() => patch.mutate({ status: 'approved' })}>Approve</Button>
          <Button disabled={locked || regen.isPending} onClick={() => setConfirmRegen(true)}>Regenerate</Button>
          <Button onClick={download}>Download .md</Button>
          <Button disabled={locked || draft.status === 'discarded'} onClick={() => setConfirmDiscard(true)}>Discard</Button>
        </div>
      </div>
      <ConfirmDialog open={confirmRegen} title="Regenerate this draft?" confirmLabel="Regenerate" busy={regen.isPending} onCancel={() => setConfirmRegen(false)} onConfirm={() => regen.mutate()}>
        The AI will write a new subject and body. {dirty || draft.edited ? 'Your edits to this draft will be replaced.' : ''}
      </ConfirmDialog>
      <ConfirmDialog open={confirmDiscard} title="Discard this draft?" confirmLabel="Discard" danger onCancel={() => setConfirmDiscard(false)}
        onConfirm={() => { patch.mutate({ status: 'discarded' }); setConfirmDiscard(false) }}>
        It will no longer be offered for Gmail. This does not delete the job.
      </ConfirmDialog>
    </Card>
  )
}

export default function Drafts() {
  const [sp, setSp] = useSearchParams()
  const qc = useQueryClient()
  const toast = useToast()
  const page = Number(sp.get('page') || 1)
  const status = sp.get('status') ?? ''
  const openId = sp.get('open') ? Number(sp.get('open')) : null
  const setParam = (patch: Record<string, string | null>) => {
    const n = new URLSearchParams(sp)
    for (const [k, v] of Object.entries(patch)) { if (v === null || v === '') n.delete(k); else n.set(k, v) }
    setSp(n, { replace: true })
  }

  const list = useQuery({ queryKey: ['drafts', status, page], queryFn: () => api.listDrafts({ status: status || undefined, page, page_size: PAGE_SIZE }), placeholderData: (p) => p })
  const open = useQuery({ queryKey: ['draft', openId], queryFn: () => api.getDraft(openId!), enabled: openId !== null })
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [confirmGmail, setConfirmGmail] = useState(false)
  const [result, setResult] = useState<GmailBulkResult | null>(null)
  const items = list.data?.items ?? []
  const eligibleOnPage = items.filter(eligible)

  const refresh = () => { qc.invalidateQueries({ queryKey: ['drafts'] }); qc.invalidateQueries({ queryKey: ['draft'] }); qc.invalidateQueries({ queryKey: ['jobs'] }); qc.invalidateQueries({ queryKey: ['summary'] }) }
  const gmail = useMutation({
    mutationFn: () => api.createGmailDrafts([...selected]),
    onSuccess: (r) => {
      setResult(r); setConfirmGmail(false); setSelected(new Set()); refresh()
      toast(r.failed.length ? 'error' : 'success', `${r.created.length} Gmail draft(s) created${r.failed.length ? `, ${r.failed.length} failed` : ''}`)
    },
    onError: (e: Error) => { setConfirmGmail(false); toast('error', e.message) },
  })

  return (
    <>
      <PageHeader title="Drafts" subtitle="Review and edit application emails. Creating a Gmail draft never sends anything." />
      <div className="grid gap-4 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <label className="text-sm">Status{' '}
              <select className={cx(inputCls, 'w-auto')} value={status} onChange={(e) => setParam({ status: e.target.value, page: null })}>
                <option value="">All</option>{(Object.keys(STATUS_TEXT) as DraftStatus[]).map((s) => <option key={s} value={s}>{STATUS_TEXT[s]}</option>)}
              </select>
            </label>
            <Button variant="primary" disabled={selected.size === 0 || gmail.isPending} onClick={() => setConfirmGmail(true)}>Create Gmail drafts ({selected.size})</Button>
          </div>
          {result && (
            <div role="status" className="mb-3 rounded-md border border-slate-200 bg-white p-3 text-sm">
              <div className="flex justify-between"><strong>Gmail result</strong><button className="text-xs text-slate-500 underline" onClick={() => setResult(null)}>Dismiss</button></div>
              <p className="text-green-800">{result.created.length} created (drafts only, nothing sent)</p>
              {result.failed.length > 0 && <ul className="mt-1 list-disc pl-5 text-rose-800">{result.failed.map((f) => <li key={f.id}>Draft #{f.id}: {f.message}</li>)}</ul>}
            </div>
          )}
          {list.error ? <ErrorBox error={list.error} onRetry={() => list.refetch()} /> : list.isLoading ? <SkeletonRows rows={6} />
            : items.length === 0 ? <EmptyState title="No drafts" hint="Drafts appear here after a pipeline run finds matching jobs." action={<Link className="text-sm text-indigo-700 underline" to="/runs">Go to Runs</Link>} />
              : (
                <>
                  <label className="mb-2 flex items-center gap-2 text-sm"><input type="checkbox" disabled={eligibleOnPage.length === 0} checked={eligibleOnPage.length > 0 && eligibleOnPage.every((d) => selected.has(d.id))}
                    onChange={(e) => setSelected(e.target.checked ? new Set(eligibleOnPage.map((d) => d.id)) : new Set())} /> Select all eligible on this page</label>
                  <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white shadow-sm">
                    {items.map((d) => (
                      <li key={d.id} className={cx('flex gap-3 p-3', d.id === openId && 'bg-indigo-50')}>
                        <input type="checkbox" className="mt-1" aria-label={`Select draft ${d.id} for Gmail`} disabled={!eligible(d)} checked={selected.has(d.id)}
                          onChange={() => setSelected((s) => { const n = new Set(s); if (n.has(d.id)) n.delete(d.id); else n.add(d.id); return n })} />
                        <button className="min-w-0 flex-1 text-left" onClick={() => setParam({ open: String(d.id) })} aria-current={d.id === openId}>
                          <div className="truncate text-sm font-medium text-slate-900">{d.job_titles.join(', ')}</div>
                          <div className="truncate text-xs text-slate-600">{d.recipient}</div>
                          <div className="mt-1 flex gap-1"><Tag tone={d.status === 'gmail_draft' ? 'green' : d.status === 'discarded' ? 'amber' : 'slate'}>{STATUS_TEXT[d.status]}</Tag>{d.source === 'template' && <Tag tone="amber">Template</Tag>}</div>
                        </button>
                      </li>
                    ))}
                  </ul>
                  {list.data && <Pagination page={page} pageSize={PAGE_SIZE} total={list.data.total} onPage={(p) => setParam({ page: String(p) })} />}
                </>
              )}
        </div>
        <div className="lg:col-span-3">
          {openId === null ? <EmptyState title="Select a draft to review" hint="Pick one from the list. You can edit it, regenerate it, or download it as Markdown." />
            : open.isLoading ? <SkeletonRows rows={8} /> : open.error ? <ErrorBox error={open.error} onRetry={() => open.refetch()} />
              : open.data && <Editor draft={open.data} onSaved={refresh} />}
        </div>
      </div>
      <ConfirmDialog open={confirmGmail} title={`Create ${selected.size} Gmail draft(s)?`} confirmLabel="Create drafts" busy={gmail.isPending} onCancel={() => setConfirmGmail(false)} onConfirm={() => gmail.mutate()}>
        These will be saved in your Gmail <strong>Drafts</strong> folder with your resume attached. <strong>Nothing is sent.</strong> You review and send each one yourself in Gmail.
        Drafts that are already in Gmail are skipped, so this cannot create duplicates.
      </ConfirmDialog>
    </>
  )
}
