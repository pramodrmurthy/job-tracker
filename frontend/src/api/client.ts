// The only module that talks to the backend. Every function maps 1:1 to an endpoint in docs/API.md.
import type {
  AnalyticsSummary, DateRange, Distribution, DistributionBy, Draft, FunnelStage, GmailBulkResult,
  GmailStatus, JobDetail, JobQuery, JobSummary, Paged, Profile, Rates, ResumeInfo, Run, RunPoint,
  Settings, SettingsUpdate, StartRun, Status, TimePoint, TimeseriesMetric,
} from './types'

export const MOCK = import.meta.env.VITE_MOCK === '1'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

type Query = Record<string, string | number | boolean | undefined | null>

export function qs(query?: Query): string {
  if (!query) return ''
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === '') continue
    p.set(k, String(v))
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

async function parseError(res: Response): Promise<ApiError> {
  let detail = `Request failed (${res.status})`
  try {
    const data = await res.json()
    if (data && typeof data.detail === 'string') detail = data.detail
    else if (data && Array.isArray(data.detail)) detail = data.detail.map((d: { msg?: string }) => d.msg).join('; ')
  } catch { /* body was not JSON */ }
  return new ApiError(res.status, detail)
}

async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  const url = `/api${path}${qs(query)}`
  if (MOCK) {
    const { mockRequest } = await import('./mock')
    return mockRequest<T>(method, path, body, query)
  }
  const isForm = body instanceof FormData
  let res: Response
  try {
    res = await fetch(url, {
      method,
      headers: body !== undefined && !isForm ? { 'Content-Type': 'application/json' } : undefined,
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'Cannot reach the backend. Is it running on port 8000?')
  }
  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

const range = (r?: DateRange): Query => ({ from: r?.from, to: r?.to })

export const api = {
  // settings
  getSettings: () => request<Settings>('GET', '/settings'),
  updateSettings: (body: SettingsUpdate) => request<Settings>('PUT', '/settings', body),
  uploadResume: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<ResumeInfo>('POST', '/resume', form)
  },
  // profiles
  listProfiles: () => request<Profile[]>('GET', '/profiles'),
  getProfile: (id: number) => request<Profile>('GET', `/profiles/${id}`),
  updateProfile: (p: Profile) => request<Profile>('PUT', `/profiles/${p.id}`, p),
  // runs
  startRun: (body: StartRun) => request<Run>('POST', '/runs', body),
  listRuns: (page = 1, page_size = 20) => request<Paged<Run>>('GET', '/runs', undefined, { page, page_size }),
  getRun: (id: number) => request<Run>('GET', `/runs/${id}`),
  cancelRun: (id: number) => request<Run>('POST', `/runs/${id}/cancel`),
  retryRun: (id: number) => request<Run>('POST', `/runs/${id}/retry`),
  // jobs
  listJobs: (q: JobQuery) => request<Paged<JobSummary>>('GET', '/jobs', undefined, q as Query),
  getJob: (id: number) => request<JobDetail>('GET', `/jobs/${id}`),
  patchJob: (id: number, body: { status?: Status; notes?: string }) => request<JobDetail>('PATCH', `/jobs/${id}`, body),
  bulkJobs: (ids: number[], status: Status) => request<{ updated: number }>('POST', '/jobs/bulk', { ids, status }),
  rescoreJob: (id: number) => request<JobDetail>('POST', `/jobs/${id}/rescore`),
  // drafts
  listDrafts: (q: { status?: string; page?: number; page_size?: number }) => request<Paged<Draft>>('GET', '/drafts', undefined, q),
  getDraft: (id: number) => request<Draft>('GET', `/drafts/${id}`),
  patchDraft: (id: number, body: { subject?: string; body?: string; status?: 'generated' | 'approved' | 'discarded' }) =>
    request<Draft>('PATCH', `/drafts/${id}`, body),
  regenerateDraft: (id: number) => request<Draft>('POST', `/drafts/${id}/regenerate`),
  createGmailDrafts: (ids: number[]) => request<GmailBulkResult>('POST', '/drafts/gmail', { ids }),
  /** The markdown endpoint returns a file, so this returns the text for the browser to save. */
  draftMarkdown: async (id: number): Promise<string> => {
    if (MOCK) {
      const { mockMarkdown } = await import('./mock')
      return mockMarkdown(id)
    }
    const res = await fetch(`/api/drafts/${id}/markdown`)
    if (!res.ok) throw await parseError(res)
    return res.text()
  },
  // gmail
  gmailStatus: () => request<GmailStatus>('GET', '/gmail/status'),
  gmailConnect: () => request<GmailStatus>('POST', '/gmail/connect'),
  gmailDisconnect: () => request<GmailStatus>('POST', '/gmail/disconnect'),
  // analytics
  summary: (r?: DateRange) => request<AnalyticsSummary>('GET', '/analytics/summary', undefined, range(r)),
  funnel: (r?: DateRange) => request<FunnelStage[]>('GET', '/analytics/funnel', undefined, range(r)),
  rates: (r?: DateRange) => request<Rates>('GET', '/analytics/rates', undefined, range(r)),
  timeseries: (metric: TimeseriesMetric, bucket: 'day' | 'week', r?: DateRange) =>
    request<TimePoint[]>('GET', '/analytics/timeseries', undefined, { metric, bucket, ...range(r) }),
  distributions: (by: DistributionBy, r?: DateRange) =>
    request<Distribution[]>('GET', '/analytics/distributions', undefined, { by, ...range(r) }),
  runSeries: (r?: DateRange) => request<RunPoint[]>('GET', '/analytics/runs', undefined, range(r)),
}
