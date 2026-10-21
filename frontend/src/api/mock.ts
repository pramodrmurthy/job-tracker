// In-browser mock backend used only when VITE_MOCK=1. Serves fixture data for every endpoint in
// docs/API.md and keeps state in memory (resets on reload). Everything here is FAKE data.
import { ApiError } from './client'
import type {
  Application, Assessment, Draft, DraftStatus, HistoryEntry, JobDetail, JobSummary, Profile, Run, RunStats,
  Settings, Status,
} from './types'
import { STATUSES } from './types'

type Q = Record<string, string | number | boolean | undefined | null> | undefined

// ---------- deterministic fixtures ----------
let seed = 42
const rnd = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296 }
const pick = <T,>(arr: T[]): T => arr[Math.floor(rnd() * arr.length)]
const DAY = 86_400_000
const iso = (ms: number) => new Date(ms).toISOString()
const now = Date.now()

const TITLES = ['AI/ML Architect', 'Senior AI Engineer', 'Principal Solution Architect – AI & Cloud Native', 'Head of AI Engineering',
  'AI Agentic / LLM Engineer', 'Data Architect', 'Senior Data Engineer', 'DevOps Lead', 'SAP Basis Consultant', 'Cloud Security Architect',
  'GenAI Solutions Engineer', 'Enterprise Architect', 'QA Automation Lead', 'Network Engineer', 'MLOps Engineer']
const COUNTRIES = ['UAE', 'UAE', 'UAE', 'SINGAPORE', 'MALAYSIA', 'MALAYSIA', 'POLAND']
const CITIES: Record<string, string> = { UAE: 'Dubai', SINGAPORE: 'Singapore', MALAYSIA: 'Kuala Lumpur', POLAND: 'Warsaw' }
const COMPANIES = [null, null, 'Unison Group', 'Kamlax Global', 'Harjai Computers', 'CloudJune', 'IDC Technologies']
const CATS = ['IT', 'IT', 'IT', 'NON-IT']
const SUBS = ['Data Science, AI & Machine Learning', 'DevOps, Cloud & SRE', 'Software Engineering & Full Stack', 'SAP & Enterprise ERP']
const REASONS = [
  'Core of the role is LLM agents and RAG; matches the candidate\'s production RAG system and agent workflows.',
  'Data engineering focus with only light ML work; missing Databricks and Snowflake.',
  'Senior architect scope fits 13+ years; requires 5+ years of sovereign cloud, which the resume does not show.',
  'AI is mentioned in passing; the job is mainly infrastructure operations.',
  'Strong fit: GenAI architecture, LangChain, vector databases and team leadership are all explicit requirements.',
]
const EXPERIENCE = ['10', '10+', '12+', '15+']

interface MockJob extends JobDetail { _rank: number; _reached: Status[] }

const jobs: MockJob[] = []
for (let i = 1; i <= 90; i++) {
  const country = pick(COUNTRIES)
  const first = now - Math.floor(rnd() * 56) * DAY - Math.floor(rnd() * DAY)
  const score = rnd() < 0.55 ? Math.floor(10 + rnd() * 40) : Math.floor(50 + rnd() * 50)
  const status: Status = score >= 60
    ? pick<Status>(['matched', 'matched', 'draft_generated', 'gmail_draft_created', 'applied', 'employer_replied', 'interview_scheduled', 'shortlisted'])
    : pick<Status>(['discovered', 'discovered', 'discovered', 'not_interested', 'rejected'])
  const title = pick(TITLES)
  const email = rnd() < 0.95 ? `recruiter${(i % 30) + 1}@agency${(i % 12) + 1}.com` : null
  const history: HistoryEntry[] = [{ from: null, to: 'discovered', at: iso(first), by: 'system', note: null }]
  if (status !== 'discovered') history.push({ from: 'discovered', to: status, at: iso(first + DAY), by: score >= 60 ? 'system' : 'user', note: null })
  const application: Application = {
    status, notes: '', applied_at: ['applied', 'employer_replied', 'interview_scheduled'].includes(status) ? iso(first + 3 * DAY) : null,
    last_follow_up_at: null,
  }
  jobs.push({
    id: i, external_id: `HA${String(100000 + i)}`, title, company: pick(COMPANIES), country, city: CITIES[country], category: pick(CATS),
    sub_category: pick(SUBS), experience_level: pick(EXPERIENCE), hr_email: email, score, relevant: score >= 60, reason: pick(REASONS),
    status, first_seen_at: iso(first), last_seen_at: iso(now - Math.floor(rnd() * 3) * DAY), listing_status: rnd() < 0.9 ? 'active' : 'missing',
    has_draft: false, recruiter_contacted_at: i % 5 === 0 ? iso(now - 6 * DAY) : null,
    description: `MOCK DATA. We are hiring a ${title}. You will design and run production systems, lead engineers, and work with stakeholders.\n\nRequirements:\n- 10+ years of experience\n- Strong Python and cloud experience (AWS, Azure or GCP)\n- Experience with LLMs, RAG or data platforms is a plus.\n\nVisa sponsorship and relocation support provided.`,
    skills: ['Python', 'AWS', 'LLM', 'RAG', 'SQL'].slice(0, 3 + Math.floor(rnd() * 3)), salary_text: rnd() < 0.5 ? 'AED 30,000–45,000' : null,
    employment_type: 'CONTRACT', work_mode: 'ONSITE', visa_sponsored: true, hr_name: null, hr_phone: null,
    posted_at: iso(first - DAY), source: 'hireabroad',
    assessment: { score, relevant: score >= 60, reason: pick(REASONS), model: 'gpt-4o-mini', created_at: iso(first + 3600_000) },
    application, drafts: [], history, _rank: 0, _reached: [status],
  })
}

const RANK: Record<Status, number> = {
  discovered: 0, matched: 1, shortlisted: 2, draft_generated: 3, gmail_draft_created: 4, applied: 5, employer_replied: 6,
  interview_scheduled: 7, interview_completed: 7, offer_received: 8, rejected: -1, withdrawn: -1, closed: -1, not_interested: -1,
}
for (const j of jobs) {
  // reached rank is the max over history (terminal statuses never lower it)
  j._rank = Math.max(0, ...j.history.map((h) => RANK[h.to]))
  if (j.status === 'rejected' && j.score! >= 60) j._rank = Math.max(j._rank, 5)
}

let draftSeq = 0
const drafts: Draft[] = []
const matchedForDrafts = jobs.filter((j) => (j.score ?? 0) >= 60 && j.hr_email).slice(0, 16)
for (const j of matchedForDrafts) {
  const inGmail = ['gmail_draft_created', 'applied', 'employer_replied', 'interview_scheduled'].includes(j.status)
  drafts.push(makeDraft(j, inGmail ? 'gmail_draft' : 'generated'))
}
function makeDraft(j: MockJob, status: DraftStatus): Draft {
  const id = ++draftSeq
  const d: Draft = {
    id, recipient: j.hr_email!, job_ids: [j.id], job_titles: [j.title], countries: [j.country ?? ''],
    subject: `Application: ${j.title} – Your Name (13+ Years, GenAI & Data Architecture)`,
    body: `Dear Hiring Team,\n\nI am writing to express my interest in the ${j.title} position in ${j.country}. (MOCK DATA)\n\nYour requirements for LLM and RAG experience match my recent work: a RAG system over 100K+ documents that reduced hallucination from 15% to under 5%, and 15+ agentic workflows across AWS, Azure and GCP.\n\nMy resume is attached. I would welcome the opportunity to discuss the role in a short call at your convenience.\n\nSincerely,\nYour Name`,
    source: rnd() < 0.85 ? 'ai' : 'template', status, gmail_draft_id: status === 'gmail_draft' ? `r${1000 + id}` : null,
    gmail_url: status === 'gmail_draft' ? `https://mail.google.com/mail/u/0/#drafts/r${1000 + id}` : null, edited: false,
    created_at: j.first_seen_at, updated_at: j.first_seen_at,
  }
  j.has_draft = true
  j.drafts = [{ id, recipient: d.recipient, subject: d.subject, status, gmail_draft_id: d.gmail_draft_id }]
  return d
}

const profile: Profile = {
  id: 1, name: 'Default', categories: ['IT'], min_years: 10, max_years: null, countries_include: [], countries_exclude: ['INDIA'],
  keywords_include: [], keywords_exclude: [], threshold: 60, score_gap: 10, cooldown_days: 0, auto_gmail_drafts: false,
}
let settings: Settings = {
  sender: { name: 'Your Name', phone: '+91 00000 00000', email: 'you@example.com', linkedin: 'linkedin.com/in/example' },
  preferences_text: 'Wants senior AI/GenAI roles abroad. (MOCK DATA)', availability_line: '', openai_model: 'gpt-4o-mini',
  openai_key_set: true, resume: { id: 1, filename: 'Resume.pdf', uploaded_at: iso(now - 20 * DAY), chars: 4310 },
  gmail: { client_secret_present: true, connected: false, account: null },
}

const emptyStats = (): RunStats => ({
  listings_seen: null, unique_jobs: null, new_jobs: null, known_jobs: null, duplicates: null, passed_filters: null,
  scored: null, matched: null, drafts_generated: null, gmail_drafts_created: null, errors: null,
})
const runs: Run[] = []
let runSeq = 0
const history5 = [
  ['succeeded', 56, 340, 340, 0], ['succeeded', 42, 12, 328, 0], ['partial', 30, 9, 340, 2], ['succeeded', 14, 7, 355, 0], ['failed', 6, 0, 0, 1],
] as const
for (const [status, daysAgo, newJobs, known, errs] of history5) {
  const started = now - daysAgo * DAY
  runs.push({
    id: ++runSeq, profile_id: 1, mode: runSeq === 1 ? 'full' : 'incremental', dry_run: false, status, stage: status === 'failed' ? 'fetch' : 'done',
    progress: null, started_at: iso(started), finished_at: iso(started + 520_000), duration_s: 520,
    stats: status === 'failed' ? { ...emptyStats(), errors: 1 } : {
      listings_seen: newJobs + known, unique_jobs: newJobs + known - 6, new_jobs: newJobs, known_jobs: known - 6, duplicates: 6,
      passed_filters: Math.round(newJobs * 0.6), scored: newJobs, matched: Math.round(newJobs * 0.1), drafts_generated: Math.round(newJobs * 0.08),
      gmail_drafts_created: Math.round(newJobs * 0.05), errors: errs,
    },
    errors: errs ? [{ stage: status === 'failed' ? 'fetch' : 'score', job_id: status === 'failed' ? null : 5, message: status === 'failed' ? 'Site returned 522 after 3 attempts' : 'Model reply was not valid JSON' }] : [],
  })
}
const liveRuns = new Map<number, { startedAt: number; cancelled: boolean }>()
const STAGES = ['fetch', 'details', 'filter', 'score', 'draft', 'done'] as const

// ---------- helpers ----------
const num = (v: unknown) => (v === undefined || v === null || v === '' ? undefined : Number(v))
const bool = (v: unknown) => v === true || v === 'true'
const notFound = (what: string) => new ApiError(404, `${what} not found`)
const delay = (ms = 120) => new Promise((r) => setTimeout(r, ms))
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v))

function summary(j: MockJob): JobSummary {
  const { description: _d, skills: _s, salary_text: _st, employment_type: _e, work_mode: _w, visa_sponsored: _v, hr_name: _hn, hr_phone: _hp,
    posted_at: _p, source: _src, assessment: _a, application: _ap, drafts: _dr, history: _h, _rank: _r, _reached: _re, ...rest } = j
  return rest
}
function detail(j: MockJob): JobDetail {
  const { _rank: _r, _reached: _re, ...rest } = j
  return clone(rest)
}
function setStatus(j: MockJob, to: Status, by: 'user' | 'system') {
  if (j.status === to) return
  j.history.push({ from: j.status, to, at: iso(Date.now()), by, note: null })
  j.status = to
  j.application.status = to
  j._rank = Math.max(j._rank, RANK[to])
  if (to === 'applied' && !j.application.applied_at) { j.application.applied_at = iso(Date.now()); j.recruiter_contacted_at = iso(Date.now()) }
}
function advanceRun(run: Run) {
  const live = liveRuns.get(run.id)
  if (!live || run.status === 'cancelled' || run.status === 'succeeded') return
  const elapsed = (Date.now() - live.startedAt) / 1000
  if (elapsed < 1) { run.status = 'queued'; return }
  run.status = 'running'
  const idx = Math.min(Math.floor((elapsed - 1) / 3), STAGES.length - 1)
  run.stage = STAGES[idx]
  if (run.stage === 'done') {
    run.status = 'succeeded'; run.progress = null; run.finished_at = iso(Date.now()); run.duration_s = Math.round(elapsed)
    run.stats = { listings_seen: 351, unique_jobs: 345, new_jobs: 11, known_jobs: 334, duplicates: 6, passed_filters: 7, scored: 11, matched: 2,
      drafts_generated: run.dry_run ? 0 : 2, gmail_drafts_created: 0, errors: 0 }
    liveRuns.delete(run.id)
  } else {
    run.progress = { done: Math.round((((elapsed - 1) % 3) / 3) * 100), total: 100 }
  }
}

function markdownFor(d: Draft): string {
  return `# ${d.subject}\n\n- **To:** ${d.recipient}\n- **Roles:** ${d.job_titles.join(', ')}\n- **Status:** ${d.status}\n\n---\n\n${d.body}\n`
}
export function mockMarkdown(id: number): string {
  const d = drafts.find((x) => x.id === id)
  if (!d) throw notFound('Draft')
  return markdownFor(d)
}

function inRange(iso0: string, q: Q) {
  const from = q?.from ? Date.parse(String(q.from)) : now - 90 * DAY
  const to = q?.to ? Date.parse(String(q.to)) + DAY : now + DAY
  const t = Date.parse(iso0)
  return t >= from && t < to
}

function funnel(q: Q) {
  const js = jobs.filter((j) => inRange(j.first_seen_at, q))
  const at = (r: number) => js.filter((j) => j._rank >= r).length
  const stages: [string, string, number, string | null][] = [
    ['discovered', 'Discovered', js.length, null],
    ['passed_filters', 'Passed filters', Math.round(js.length * 0.6), 'discovered'],
    ['matched', 'Matched', at(1), 'passed_filters'], ['drafted', 'Drafted', at(3), 'matched'],
    ['gmail_drafted', 'Gmail drafted', at(4), 'drafted'], ['applied', 'Applied', at(5), 'gmail_drafted'],
    ['replied', 'Replied', at(6), 'applied'], ['interviewed', 'Interviewed', at(7), 'replied'], ['offered', 'Offered', at(8), 'interviewed'],
  ]
  return stages.map(([stage, label, count, of], i) => {
    const prev = i === 0 ? 0 : stages[i - 1][2]
    return { stage, label, count, of, rate: i === 0 || prev === 0 ? null : count / prev }
  })
}
const rate = (num0: number, den: number, definition: string) => ({ value: den ? num0 / den : null, numerator: num0, denominator: den, definition })

// ---------- router ----------
export async function mockRequest<T>(method: string, path: string, body?: unknown, query?: Q): Promise<T> {
  await delay()
  const b = (body ?? {}) as Record<string, unknown>
  let m: RegExpMatchArray | null
  const out = (v: unknown) => clone(v) as T

  // settings / resume
  if (path === '/settings' && method === 'GET') return out(settings)
  if (path === '/settings' && method === 'PUT') {
    settings = { ...settings, ...(b as object), sender: { ...settings.sender, ...((b.sender as object) ?? {}) } } as Settings
    return out(settings)
  }
  if (path === '/resume' && method === 'POST') {
    const file = (body as FormData).get('file') as File | null
    if (!file) throw new ApiError(422, 'No file uploaded')
    if (!/\.(pdf|docx|txt)$/i.test(file.name)) throw new ApiError(422, 'Unsupported file type (use pdf, docx or txt)')
    if (file.size > 5 * 1024 * 1024) throw new ApiError(413, 'File is larger than 5 MB')
    settings.resume = { id: (settings.resume?.id ?? 0) + 1, filename: file.name, uploaded_at: iso(Date.now()), chars: Math.max(500, file.size) }
    return out(settings.resume)
  }
  // profiles
  if (path === '/profiles' && method === 'GET') return out([profile])
  if ((m = path.match(/^\/profiles\/(\d+)$/))) {
    if (Number(m[1]) !== 1) throw notFound('Profile')
    if (method === 'PUT') Object.assign(profile, b)
    return out(profile)
  }
  // runs
  if (path === '/runs' && method === 'POST') {
    if (runs.some((r) => r.status === 'queued' || r.status === 'running')) throw new ApiError(409, 'A run is already in progress. Wait for it to finish or cancel it.')
    const run: Run = { id: ++runSeq, profile_id: Number(b.profile_id), mode: b.mode as Run['mode'], dry_run: bool(b.dry_run), status: 'queued', stage: null,
      progress: null, started_at: iso(Date.now()), finished_at: null, duration_s: null, stats: emptyStats(), errors: [] }
    runs.unshift(run); liveRuns.set(run.id, { startedAt: Date.now(), cancelled: false })
    return out(run)
  }
  if (path === '/runs' && method === 'GET') {
    runs.forEach(advanceRun)
    const sorted = [...runs].sort((a, c) => c.id - a.id)
    const page = num(query?.page) ?? 1, size = num(query?.page_size) ?? 20
    return out({ items: sorted.slice((page - 1) * size, page * size), total: sorted.length })
  }
  if ((m = path.match(/^\/runs\/(\d+)(?:\/(cancel|retry))?$/))) {
    const run = runs.find((r) => r.id === Number(m![1]))
    if (!run) throw notFound('Run')
    if (m[2] === 'cancel' && method === 'POST') {
      if (run.status !== 'queued' && run.status !== 'running') throw new ApiError(409, 'Run is not active')
      run.status = 'cancelled'; run.finished_at = iso(Date.now()); liveRuns.delete(run.id)
    } else if (m[2] === 'retry' && method === 'POST') {
      if (runs.some((r) => r.status === 'queued' || r.status === 'running')) throw new ApiError(409, 'A run is already in progress.')
      const next: Run = { ...clone(run), id: ++runSeq, status: 'queued', stage: null, progress: null, started_at: iso(Date.now()), finished_at: null,
        duration_s: null, stats: emptyStats(), errors: [] }
      runs.unshift(next); liveRuns.set(next.id, { startedAt: Date.now(), cancelled: false })
      return out(next)
    } else advanceRun(run)
    return out(run)
  }
  // jobs
  if (path === '/jobs' && method === 'GET') {
    const q = query ?? {}
    const text = String(q.query ?? '').toLowerCase()
    let list = jobs.filter((j) => {
      if (text && !`${j.title} ${j.company ?? ''} ${j.hr_email ?? ''} ${j.external_id}`.toLowerCase().includes(text)) return false
      if (q.status && j.status !== q.status) return false
      if (q.country && j.country !== q.country) return false
      if (q.category && j.category !== q.category) return false
      if (num(q.min_score) !== undefined && (j.score === null || j.score < num(q.min_score)!)) return false
      if (num(q.max_score) !== undefined && (j.score === null || j.score > num(q.max_score)!)) return false
      if (bool(q.new_only) && Date.now() - Date.parse(j.first_seen_at) > 4 * DAY) return false
      if (q.has_draft !== undefined && q.has_draft !== '' && bool(q.has_draft) !== j.has_draft) return false
      if (q.recruiter_contacted !== undefined && q.recruiter_contacted !== '' && bool(q.recruiter_contacted) !== (j.recruiter_contacted_at !== null)) return false
      return true
    })
    const dir = q.order === 'asc' ? 1 : -1
    const key = q.sort ?? 'first_seen'
    list = [...list].sort((a, c) => dir * (key === 'score' ? (a.score ?? -1) - (c.score ?? -1) : key === 'title' ? a.title.localeCompare(c.title) : Date.parse(a.first_seen_at) - Date.parse(c.first_seen_at)))
    const page = num(q.page) ?? 1, size = num(q.page_size) ?? 25
    return out({ items: list.slice((page - 1) * size, page * size).map(summary), total: list.length })
  }
  if (path === '/jobs/bulk' && method === 'POST') {
    const ids = b.ids as number[]; const status = b.status as Status
    if (!STATUSES.includes(status)) throw new ApiError(422, 'Invalid status')
    let n = 0
    for (const id of ids) { const j = jobs.find((x) => x.id === id); if (j) { setStatus(j, status, 'user'); n++ } }
    return out({ updated: n })
  }
  if ((m = path.match(/^\/jobs\/(\d+)(?:\/(rescore))?$/))) {
    const j = jobs.find((x) => x.id === Number(m![1]))
    if (!j) throw notFound('Job')
    if (m[2] === 'rescore' && method === 'POST') {
      await delay(600)
      const score = Math.min(100, Math.max(0, (j.score ?? 50) + Math.floor(rnd() * 11) - 5))
      j.score = score; j.relevant = score >= 60; j.reason = pick(REASONS)
      j.assessment = { score, relevant: j.relevant, reason: j.reason, model: settings.openai_model, created_at: iso(Date.now()) } as Assessment
    } else if (method === 'PATCH') {
      if (b.status !== undefined) {
        if (!STATUSES.includes(b.status as Status)) throw new ApiError(422, 'Invalid status')
        setStatus(j, b.status as Status, 'user')
      }
      if (typeof b.notes === 'string') j.application.notes = b.notes
    }
    return out(detail(j))
  }
  // drafts
  if (path === '/drafts/gmail' && method === 'POST') {
    if (!settings.gmail.connected) throw new ApiError(400, 'Gmail is not connected. Connect it in Settings first.')
    const created: { id: number; gmail_draft_id: string }[] = [], failed: { id: number; message: string }[] = []
    for (const id of b.ids as number[]) {
      const d = drafts.find((x) => x.id === id)
      if (!d) { failed.push({ id, message: 'Draft not found' }); continue }
      if (d.gmail_draft_id) { created.push({ id, gmail_draft_id: d.gmail_draft_id }); continue }
      if (id % 7 === 0) { failed.push({ id, message: 'Gmail API rate limit, try again shortly' }); continue }
      d.gmail_draft_id = `r${5000 + id}`; d.status = 'gmail_draft'; d.gmail_url = `https://mail.google.com/mail/u/0/#drafts/${d.gmail_draft_id}`
      for (const jid of d.job_ids) { const j = jobs.find((x) => x.id === jid); if (j) { setStatus(j, 'gmail_draft_created', 'system'); j.drafts = [{ id, recipient: d.recipient, subject: d.subject, status: d.status, gmail_draft_id: d.gmail_draft_id }] } }
      created.push({ id, gmail_draft_id: d.gmail_draft_id })
    }
    return out({ created, failed })
  }
  if (path === '/drafts' && method === 'GET') {
    const q = query ?? {}
    const list = drafts.filter((d) => (q.status ? d.status === q.status : true)).sort((a, c) => c.id - a.id)
    const page = num(q.page) ?? 1, size = num(q.page_size) ?? 25
    return out({ items: list.slice((page - 1) * size, page * size), total: list.length })
  }
  if ((m = path.match(/^\/drafts\/(\d+)(?:\/(regenerate|markdown))?$/))) {
    const d = drafts.find((x) => x.id === Number(m![1]))
    if (!d) throw notFound('Draft')
    if (m[2] === 'regenerate' && method === 'POST') {
      if (d.gmail_draft_id) throw new ApiError(409, 'This draft is already in Gmail and can no longer be changed here.')
      await delay(700)
      d.body = d.body.replace('(MOCK DATA)', '(MOCK DATA, regenerated)'); d.edited = false; d.updated_at = iso(Date.now())
    } else if (method === 'PATCH') {
      if (d.gmail_draft_id) throw new ApiError(409, 'This draft is already in Gmail and can no longer be changed here.')
      if (typeof b.subject === 'string') { d.subject = b.subject; d.edited = true }
      if (typeof b.body === 'string') { d.body = b.body; d.edited = true }
      if (b.status) d.status = b.status as DraftStatus
      d.updated_at = iso(Date.now())
    }
    return out(d)
  }
  // gmail
  if (path === '/gmail/status' && method === 'GET') return out(settings.gmail)
  if (path === '/gmail/connect' && method === 'POST') {
    if (!settings.gmail.client_secret_present) throw new ApiError(400, 'client_secret.json is missing. See the setup steps.')
    await delay(900)
    settings.gmail = { ...settings.gmail, connected: true, account: settings.sender.email }
    return out(settings.gmail)
  }
  if (path === '/gmail/disconnect' && method === 'POST') {
    settings.gmail = { ...settings.gmail, connected: false, account: null }
    return out(settings.gmail)
  }
  // analytics
  if (path === '/analytics/summary') {
    runs.forEach(advanceRun)
    const ok = runs.filter((r) => r.status === 'succeeded' || r.status === 'partial').sort((a, c) => c.id - a.id)
    const latest = [...runs].sort((a, c) => c.id - a.id)[0] ?? null
    const f = funnel(query)
    const at = (s: string) => f.find((x) => x.stage === s)?.count ?? 0
    const inflight = (s: Status) => jobs.filter((j) => j._rank >= RANK[s]).length
    return out({
      kpis: {
        total_unique_jobs: jobs.length, latest_run_discovered: latest?.stats.unique_jobs ?? null, new_since_previous_run: ok[0]?.stats.new_jobs ?? null,
        previously_seen: ok[0]?.stats.known_jobs ?? null, passed_filters: at('passed_filters'), matched: at('matched'), shortlisted: inflight('shortlisted'),
        drafts_generated: at('drafted'), gmail_drafts_created: at('gmail_drafted'), applied: at('applied'), employer_replied: at('replied'),
        interviews: at('interviewed'), offers: at('offered'),
      },
      latest_run: latest, last_successful_run: ok.find((r) => r.status === 'succeeded') ?? null, last_attempted_run: latest,
    })
  }
  if (path === '/analytics/funnel') return out(funnel(query))
  if (path === '/analytics/rates') {
    const f = funnel(query); const c = (s: string) => f.find((x) => x.stage === s)!.count
    return out({
      reply_rate: rate(c('replied'), c('applied'), 'employer_replied / applied'),
      interview_rate: rate(c('interviewed'), c('applied'), 'interviews / applied'),
      offer_rate: rate(c('offered'), c('applied'), 'offers / applied'),
    })
  }
  if (path === '/analytics/timeseries') {
    const metric = String(query?.metric ?? 'discovered'); const week = query?.bucket === 'week'
    const buckets = new Map<string, number>()
    const days = 60
    for (let d = days; d >= 0; d--) {
      const t = new Date(now - d * DAY); if (week) t.setUTCDate(t.getUTCDate() - ((t.getUTCDay() + 6) % 7))
      buckets.set(t.toISOString().slice(0, 10), 0)
    }
    for (const j of jobs) {
      const ts = metric === 'applied' ? j.application.applied_at : metric === 'replied' && j._rank >= 6 ? iso(Date.parse(j.first_seen_at) + 6 * DAY)
        : metric === 'matched' && j._rank >= 1 ? j.first_seen_at : metric === 'new' || metric === 'discovered' ? j.first_seen_at : null
      if (!ts || !inRange(ts, query)) continue
      const t = new Date(ts); if (week) t.setUTCDate(t.getUTCDate() - ((t.getUTCDay() + 6) % 7))
      const k = t.toISOString().slice(0, 10)
      buckets.set(k, (buckets.get(k) ?? 0) + 1)
    }
    return out([...buckets.entries()].sort().map(([date, value]) => ({ date, value })))
  }
  if (path === '/analytics/distributions') {
    const by = String(query?.by ?? 'country'); const counts = new Map<string, number>()
    for (const j of jobs.filter((x) => inRange(x.first_seen_at, query))) {
      const label = by === 'country' ? j.country ?? 'Unknown' : by === 'category' ? j.category ?? 'Unknown' : by === 'company' ? j.company ?? 'Unknown'
        : by === 'status' ? j.status : j.score === null ? 'Unscored' : j.score >= 80 ? '80-100' : `${Math.floor(j.score / 20) * 20}-${Math.floor(j.score / 20) * 20 + 19}`
      counts.set(label, (counts.get(label) ?? 0) + 1)
    }
    return out([...counts.entries()].map(([label, count]) => ({ label, count })).sort((a, c) => c.count - a.count))
  }
  if (path === '/analytics/runs') {
    return out([...runs].filter((r) => r.stats.new_jobs !== null || r.status === 'failed').sort((a, c) => a.id - c.id).map((r) => ({
      run_id: r.id, started_at: r.started_at, new_jobs: r.stats.new_jobs, known_jobs: r.stats.known_jobs, matched: r.stats.matched,
      drafts_generated: r.stats.drafts_generated, errors: r.stats.errors })))
  }
  throw new ApiError(404, `Mock has no route for ${method} ${path}`)
}
