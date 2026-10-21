// Types mirror docs/API.md. Missing data is null (never 0).

export const STATUSES = [
  'discovered', 'matched', 'shortlisted', 'draft_generated', 'gmail_draft_created', 'applied',
  'employer_replied', 'interview_scheduled', 'interview_completed', 'offer_received', 'rejected',
  'withdrawn', 'closed', 'not_interested',
] as const
export type Status = (typeof STATUSES)[number]

export const STATUS_LABELS: Record<Status, string> = {
  discovered: 'Discovered', matched: 'Matched', shortlisted: 'Shortlisted', draft_generated: 'Draft generated',
  gmail_draft_created: 'Gmail draft created', applied: 'Applied', employer_replied: 'Employer replied',
  interview_scheduled: 'Interview scheduled', interview_completed: 'Interview completed',
  offer_received: 'Offer received', rejected: 'Rejected', withdrawn: 'Withdrawn', closed: 'Closed',
  not_interested: 'Not interested',
}

export interface Paged<T> { items: T[]; total: number }

export interface Sender { name: string; phone: string; email: string; linkedin: string }
export interface ResumeInfo { id: number; filename: string; uploaded_at: string; chars: number }
export interface GmailStatus { client_secret_present: boolean; connected: boolean; account: string | null }
export interface Settings {
  sender: Sender
  preferences_text: string
  availability_line: string
  openai_model: string
  openai_key_set: boolean
  resume: ResumeInfo | null
  gmail: GmailStatus
}
export type SettingsUpdate = Partial<Pick<Settings, 'sender' | 'preferences_text' | 'availability_line' | 'openai_model'>>

export interface Profile {
  id: number
  name: string
  categories: string[]
  min_years: number | null
  max_years: number | null
  countries_include: string[]
  countries_exclude: string[]
  keywords_include: string[]
  keywords_exclude: string[]
  threshold: number
  score_gap: number
  cooldown_days: number
  auto_gmail_drafts: boolean
}

export type RunStatus = 'queued' | 'running' | 'succeeded' | 'partial' | 'failed' | 'cancelled'
export type RunStage = 'fetch' | 'details' | 'filter' | 'score' | 'draft' | 'gmail' | 'done'
export interface RunStats {
  listings_seen: number | null; unique_jobs: number | null; new_jobs: number | null; known_jobs: number | null
  duplicates: number | null; passed_filters: number | null; scored: number | null; matched: number | null
  drafts_generated: number | null; gmail_drafts_created: number | null; errors: number | null
}
export interface RunError { stage: string; job_id: number | null; message: string }
export interface Run {
  id: number
  profile_id: number
  mode: 'incremental' | 'full'
  dry_run: boolean
  status: RunStatus
  stage: RunStage | null
  progress: { done: number; total: number } | null
  started_at: string | null
  finished_at: string | null
  duration_s: number | null
  stats: RunStats
  errors: RunError[]
}
export interface StartRun { profile_id: number; mode: 'incremental' | 'full'; dry_run: boolean }

export interface JobSummary {
  id: number
  external_id: string
  title: string
  company: string | null
  country: string | null
  city: string | null
  category: string | null
  sub_category: string | null
  experience_level: string | null
  hr_email: string | null
  score: number | null
  relevant: boolean | null
  reason: string | null
  status: Status
  first_seen_at: string
  last_seen_at: string
  listing_status: 'active' | 'missing'
  has_draft: boolean
  recruiter_contacted_at: string | null  // when this job's recruiter was last emailed about ANY job
}
export interface DraftSummary { id: number; recipient: string; subject: string; status: DraftStatus; gmail_draft_id: string | null }
export interface Assessment { score: number; relevant: boolean; reason: string; model: string; created_at: string }
export interface Application {
  status: Status; notes: string; applied_at: string | null; last_follow_up_at: string | null
}
export interface HistoryEntry { from: Status | null; to: Status; at: string; by: 'user' | 'system'; note: string | null }
export interface JobDetail extends JobSummary {
  description: string
  skills: string[]
  salary_text: string | null
  employment_type: string | null
  work_mode: string | null
  visa_sponsored: boolean | null
  hr_name: string | null
  hr_phone: string | null
  posted_at: string | null
  source: string
  assessment: Assessment | null
  application: Application
  drafts: DraftSummary[]
  history: HistoryEntry[]
}
export interface JobQuery {
  query?: string; status?: string; min_score?: number; max_score?: number; country?: string; category?: string
  run_id?: number; new_only?: boolean; has_draft?: boolean; recruiter_contacted?: boolean; sort?: 'score' | 'first_seen' | 'title'
  order?: 'asc' | 'desc'; page?: number; page_size?: number
}

export type DraftStatus = 'generated' | 'approved' | 'gmail_draft' | 'discarded'
export interface Draft {
  id: number
  recipient: string
  job_ids: number[]
  job_titles: string[]
  countries: string[]
  subject: string
  body: string
  source: 'ai' | 'template'
  status: DraftStatus
  gmail_draft_id: string | null
  gmail_url: string | null
  edited: boolean
  created_at: string
  updated_at: string
}
export interface GmailBulkResult {
  created: { id: number; gmail_draft_id: string }[]
  failed: { id: number; message: string }[]
}

export interface Kpis {
  total_unique_jobs: number | null; latest_run_discovered: number | null; new_since_previous_run: number | null
  previously_seen: number | null; passed_filters: number | null; matched: number | null; shortlisted: number | null
  drafts_generated: number | null; gmail_drafts_created: number | null; applied: number | null
  employer_replied: number | null; interviews: number | null; offers: number | null
}
export interface AnalyticsSummary {
  kpis: Kpis
  latest_run: Run | null
  last_successful_run: Run | null
  last_attempted_run: Run | null
}
export interface FunnelStage { stage: string; label: string; count: number; of: string | null; rate: number | null }
export interface RateInfo { value: number | null; numerator: number; denominator: number; definition: string }
export type Rates = Record<string, RateInfo>
export interface TimePoint { date: string; value: number }
export interface Distribution { label: string; count: number }
export interface RunPoint {
  run_id: number; started_at: string; new_jobs: number | null; known_jobs: number | null
  matched: number | null; drafts_generated: number | null; errors: number | null
}
export type TimeseriesMetric = 'discovered' | 'new' | 'matched' | 'applied' | 'replied'
export type DistributionBy = 'country' | 'category' | 'company' | 'score' | 'status'
export interface DateRange { from?: string; to?: string }
