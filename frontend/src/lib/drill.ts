import type { DistributionBy } from '../api/types'

/** Where a dashboard metric leads. Jobs filters work on a job's CURRENT status, while dashboard counts are
 *  "ever reached", so a drill-down can show fewer rows than the number clicked (e.g. an applied job later rejected). */
export function kpiLink(key: string, latestRunId?: number | null): string {
  switch (key) {
    case 'latest_run_discovered': return latestRunId ? `/jobs?run_id=${latestRunId}` : '/jobs'
    case 'new_since_previous_run': return '/jobs?new_only=true'
    case 'matched': return '/jobs?min_score=60'
    case 'shortlisted': return '/jobs?status=shortlisted'
    case 'drafts_generated': return '/jobs?has_draft=true'
    case 'gmail_drafts_created': return '/jobs?status=gmail_draft_created'
    case 'applied': return '/jobs?status=applied'
    case 'employer_replied': return '/jobs?status=employer_replied'
    case 'interviews': return '/jobs?status=interview_scheduled'
    case 'offers': return '/jobs?status=offer_received'
    default: return '/jobs'
  }
}
export function funnelLink(stage: string): string {
  const map: Record<string, string> = {
    gmail_drafted: 'gmail_draft_created', applied: 'applied', replied: 'employer_replied',
    interviewed: 'interview_scheduled', offered: 'offer_received',
  }
  if (stage === 'matched') return '/jobs?min_score=60'
  if (stage === 'drafted') return '/jobs?has_draft=true'
  return map[stage] ? `/jobs?status=${map[stage]}` : '/jobs'
}
export function distLink(by: DistributionBy, label: string): string {
  const enc = encodeURIComponent(label)
  if (by === 'country') return `/jobs?country=${enc}`
  if (by === 'category') return `/jobs?category=${enc}`
  if (by === 'status') return `/jobs?status=${enc}`
  if (by === 'company') return `/jobs?query=${enc}`
  const m = label.match(/^(\d+)-(\d+)$/)
  return m ? `/jobs?min_score=${m[1]}&max_score=${m[2]}` : '/jobs'
}
