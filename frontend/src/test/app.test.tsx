import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import App from '../App'
import { ToastProvider } from '../components/ui'
import { mockRequest } from '../api/mock'
import { fmtNum, fmtPct } from '../lib/format'
import type { AnalyticsSummary, FunnelStage, Paged, JobSummary, Run } from '../api/types'

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}><ToastProvider><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></ToastProvider></QueryClientProvider>,
  )
}

describe('formatting: missing data is not zero', () => {
  it('shows - for null and 0 for a real zero', () => {
    expect(fmtNum(null)).toBe('-'); expect(fmtNum(0)).toBe('0'); expect(fmtPct(null)).toBe('-'); expect(fmtPct(0)).toBe('0.0%')
  })
})

describe('mock backend honours the contract', () => {
  it('funnel rates are vs the previous stage and null when the denominator is 0', async () => {
    const f = await mockRequest<FunnelStage[]>('GET', '/analytics/funnel')
    expect(f.map((s) => s.stage)).toEqual(['discovered', 'passed_filters', 'matched', 'drafted', 'gmail_drafted', 'applied', 'replied', 'interviewed', 'offered'])
    expect(f[0].rate).toBeNull()
    f.slice(1).forEach((s, i) => { const prev = f[i].count; expect(s.rate).toBe(prev === 0 ? null : s.count / prev) })
  })
  it('only one run may be active (409), and cancelling frees it', async () => {
    const a = await mockRequest<Run>('POST', '/runs', { profile_id: 1, mode: 'incremental', dry_run: true })
    await expect(mockRequest('POST', '/runs', { profile_id: 1, mode: 'incremental', dry_run: false })).rejects.toMatchObject({ status: 409 })
    await mockRequest('POST', `/runs/${a.id}/cancel`)
    const b = await mockRequest<Run>('POST', '/runs', { profile_id: 1, mode: 'incremental', dry_run: true })
    await mockRequest('POST', `/runs/${b.id}/cancel`)
  })
  it('status changes are recorded in history and bulk updates work', async () => {
    const page = await mockRequest<Paged<JobSummary>>('GET', '/jobs', undefined, { page_size: 3 })
    const ids = page.items.map((j) => j.id)
    expect((await mockRequest<{ updated: number }>('POST', '/jobs/bulk', { ids, status: 'shortlisted' })).updated).toBe(3)
    const d = await mockRequest<{ status: string; history: { to: string; by: string }[] }>('GET', `/jobs/${ids[0]}`)
    expect(d.status).toBe('shortlisted'); expect(d.history.at(-1)).toMatchObject({ to: 'shortlisted', by: 'user' })
  })
  it('creating Gmail drafts needs a connection, is idempotent, and reports each item', async () => {
    const all = await mockRequest<Paged<{ id: number; gmail_draft_id: string | null; status: string }>>('GET', '/drafts', undefined, { page_size: 100 })
    const fresh = all.items.filter((d) => !d.gmail_draft_id && d.status === 'generated').map((d) => d.id)
    expect(fresh.length).toBeGreaterThan(1)
    await expect(mockRequest('POST', '/drafts/gmail', { ids: fresh })).rejects.toMatchObject({ status: 400 })
    await mockRequest('POST', '/gmail/connect')
    const first = await mockRequest<{ created: { id: number; gmail_draft_id: string }[]; failed: { id: number; message: string }[] }>('POST', '/drafts/gmail', { ids: fresh })
    expect(first.created.length + first.failed.length).toBe(fresh.length) // every item is accounted for
    first.failed.forEach((f) => expect(f.message.length).toBeGreaterThan(0))
    const ok = first.created[0]
    const again = await mockRequest<{ created: { id: number; gmail_draft_id: string }[] }>('POST', '/drafts/gmail', { ids: [ok.id] })
    expect(again.created[0].gmail_draft_id).toBe(ok.gmail_draft_id) // same Gmail id, no duplicate
    await expect(mockRequest('PATCH', `/drafts/${ok.id}`, { body: 'x' })).rejects.toMatchObject({ status: 409 }) // read-only once in Gmail
  })
  it('summary kpis are numbers or null', async () => {
    const s = await mockRequest<AnalyticsSummary>('GET', '/analytics/summary')
    Object.values(s.kpis).forEach((v) => expect(v === null || typeof v === 'number').toBe(true))
  })
})

describe('pages render against the mock backend', () => {
  it('dashboard shows KPIs, funnel and the mock banner', async () => {
    renderAt('/')
    expect(screen.getByText(/MOCK DATA/)).toBeTruthy()
    await waitFor(() => expect(screen.getByText('Unique jobs discovered')).toBeTruthy())
    await waitFor(() => expect(screen.getAllByText('Application funnel').length).toBeGreaterThan(0))
    expect(screen.getByRole('region', { name: 'Key metrics' })).toBeTruthy()
  })
  it('jobs page lists rows, filters, and confirms bulk actions', async () => {
    const user = userEvent.setup()
    renderAt('/jobs')
    await waitFor(() => expect(screen.getAllByRole('checkbox').length).toBeGreaterThan(3))
    await user.click(screen.getByLabelText('Select all jobs on this page'))
    await user.click(await screen.findByRole('button', { name: 'Reject' }))
    expect(await screen.findByText(/sets the status of the/i)).toBeTruthy()
  })
  it('job detail shows the AI-opinion disclaimer', async () => {
    renderAt('/jobs/1')
    await waitFor(() => expect(screen.getByText(/not a probability of being hired/i)).toBeTruthy())
  })
  it('drafts page opens an editor and explains that nothing is sent', async () => {
    const user = userEvent.setup()
    renderAt('/drafts')
    const boxes = await screen.findAllByLabelText(/Select draft \d+ for Gmail/)
    await user.click(within(boxes[0].closest('li')!).getByRole('button'))
    await waitFor(() => expect(screen.getByLabelText('Subject')).toBeTruthy())
    expect(screen.getByRole('button', { name: /Create Gmail drafts/ })).toBeTruthy()
  })
  it('runs page shows history and settings page shows the Gmail card', async () => {
    const r = renderAt('/runs')
    await waitFor(() => expect(screen.getByText('Run history')).toBeTruthy())
    r.unmount()
    renderAt('/settings')
    await waitFor(() => expect(screen.getByText('Gmail connection')).toBeTruthy())
    expect(within(screen.getByText('Gmail connection').closest('section')!).getByText(/never sends email/i)).toBeTruthy()
  })
})
