import type { Run, RunStage } from '../api/types'
import { fmtNum } from '../lib/format'
import { ProgressBar } from './ui'

export const STAGE_TEXT: Record<RunStage, string> = {
  fetch: 'Fetching listings', details: 'Fetching job details', filter: 'Applying filters', score: 'Scoring with AI',
  draft: 'Writing email drafts', gmail: 'Creating Gmail drafts', done: 'Finished',
}
const STAT_LABELS: [keyof Run['stats'], string][] = [
  ['listings_seen', 'Listings seen'], ['unique_jobs', 'Unique jobs'], ['new_jobs', 'New'], ['known_jobs', 'Previously seen'], ['duplicates', 'Duplicates'],
  ['passed_filters', 'Passed filters'], ['scored', 'Scored'], ['matched', 'Matched'], ['drafts_generated', 'Drafts generated'],
  ['gmail_drafts_created', 'Gmail drafts'], ['errors', 'Errors'],
]

export function RunStatsGrid({ stats }: { stats: Run['stats'] }) {
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {STAT_LABELS.map(([k, label]) => (
        <div key={k} className="rounded-md bg-slate-50 px-3 py-2">
          <dt className="text-xs text-slate-600">{label}</dt>
          <dd className="text-lg font-semibold">{fmtNum(stats[k])}</dd>
        </div>
      ))}
    </dl>
  )
}

export function RunProgress({ run }: { run: Run }) {
  return (
    <div className="space-y-2" aria-live="polite">
      <p className="text-sm font-medium">{run.status === 'queued' ? 'Queued, waiting to start…' : run.stage ? STAGE_TEXT[run.stage] : 'Working…'}</p>
      {run.progress && <ProgressBar done={run.progress.done} total={run.progress.total} label={`${run.progress.done} of ${run.progress.total}`} />}
    </div>
  )
}
