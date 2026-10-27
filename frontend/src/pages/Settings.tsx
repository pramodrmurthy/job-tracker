import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Profile, Settings } from '../api/types'
import { Button, Card, ConfirmDialog, ErrorBox, Field, PageHeader, SkeletonRows, Tag, inputCls, useToast } from '../components/ui'
import { fmtDateTime } from '../lib/format'

const MAX_RESUME_BYTES = 5 * 1024 * 1024
const list = (s: string) => s.split(',').map((x) => x.trim()).filter(Boolean)
const optNum = (s: string) => (s.trim() === '' ? null : Number(s))

function ResumeCard({ settings }: { settings: Settings }) {
  const toast = useToast()
  const qc = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)
  const upload = useMutation({
    mutationFn: (f: File) => api.uploadResume(f),
    onSuccess: () => { toast('success', 'Resume uploaded. New runs will use it; past results are kept.'); setError(null); qc.invalidateQueries({ queryKey: ['settings'] }) },
    onError: (e: Error) => setError(e.message),
  })
  const pick = (f: File | undefined) => {
    if (!f) return
    if (!/\.(pdf|docx|txt)$/i.test(f.name)) return setError('Unsupported file type. Use a PDF, DOCX or TXT file.')
    if (f.size > MAX_RESUME_BYTES) return setError('That file is larger than 5 MB.')
    upload.mutate(f)
  }
  return (
    <Card title="Resume">
      {settings.resume ? (
        <p className="text-sm"><strong>{settings.resume.filename}</strong> · {settings.resume.chars.toLocaleString()} characters read · uploaded {fmtDateTime(settings.resume.uploaded_at)}</p>
      ) : <p className="text-sm text-amber-900">No resume yet. Upload one so jobs can be scored and drafts can be written.</p>}
      <p className="mt-1 text-xs text-slate-600">Uploading a new version replaces the active resume. Earlier jobs, drafts and statuses are kept.</p>
      <div className="mt-3">
        <input ref={input} id="resume-file" type="file" accept=".pdf,.docx,.txt" className="sr-only" onChange={(e) => { pick(e.target.files?.[0]); e.target.value = '' }} />
        <Button variant="primary" disabled={upload.isPending} onClick={() => input.current?.click()}>{upload.isPending ? 'Uploading…' : settings.resume ? 'Replace resume' : 'Upload resume'}</Button>
        <span className="ml-3 text-xs text-slate-500">PDF, DOCX or TXT, up to 5 MB</span>
      </div>
      {error && <p role="alert" className="mt-2 text-sm text-rose-800">{error}</p>}
    </Card>
  )
}

function GeneralCard({ settings }: { settings: Settings }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [f, setF] = useState(() => ({ ...settings }))
  useEffect(() => setF({ ...settings }), [settings])
  const save = useMutation({
    mutationFn: () => api.updateSettings({ sender: f.sender, preferences_text: f.preferences_text, availability_line: f.availability_line, openai_model: f.openai_model }),
    onSuccess: () => { toast('success', 'Settings saved'); qc.invalidateQueries({ queryKey: ['settings'] }) }, onError: (e: Error) => toast('error', e.message),
  })
  const sender = (k: keyof Settings['sender']) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, sender: { ...f.sender, [k]: e.target.value } })
  return (
    <Card title="Sender and writing preferences">
      <form className="grid gap-4 md:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
        <Field label="Your name">{(id) => <input id={id} className={inputCls} value={f.sender.name} onChange={sender('name')} />}</Field>
        <Field label="Email shown in the signature">{(id) => <input id={id} type="email" className={inputCls} value={f.sender.email} onChange={sender('email')} />}</Field>
        <Field label="Phone">{(id) => <input id={id} className={inputCls} value={f.sender.phone} onChange={sender('phone')} />}</Field>
        <Field label="LinkedIn">{(id) => <input id={id} className={inputCls} value={f.sender.linkedin} onChange={sender('linkedin')} />}</Field>
        <div className="md:col-span-2"><Field label="Job preferences" hint="Used by the AI when it scores jobs. Say what you want and what you do not.">
          {(id) => <textarea id={id} rows={4} className={inputCls} value={f.preferences_text} onChange={(e) => setF({ ...f, preferences_text: e.target.value })} />}</Field></div>
        <div className="md:col-span-2"><Field label="Availability line (optional)" hint="One sentence added to every email, e.g. your notice period and relocation. Leave empty to say nothing about it.">
          {(id) => <input id={id} className={inputCls} value={f.availability_line} onChange={(e) => setF({ ...f, availability_line: e.target.value })} />}</Field></div>
        <Field label="Gemini model" hint="The model name used for scoring and writing.">{(id) => <input id={id} className={inputCls} value={f.openai_model} onChange={(e) => setF({ ...f, openai_model: e.target.value })} />}</Field>
        <div className="text-sm"><div className="font-medium">OpenAI API key</div>
          <p className="mt-1">{settings.openai_key_set ? <Tag tone="green">Key is set</Tag> : <Tag tone="amber">Key not set</Tag>}</p>
          <p className="mt-1 text-xs text-slate-500">The key is never shown or sent through this page. Set <code>GEMINI_API_KEY</code> in the backend's <code>.env</code> file.</p></div>
        <div className="md:col-span-2"><Button variant="primary" type="submit" disabled={save.isPending}>{save.isPending ? 'Saving…' : 'Save settings'}</Button></div>
      </form>
    </Card>
  )
}

function ProfileCard({ profile }: { profile: Profile }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [f, setF] = useState(profile)
  const [text, setText] = useState(() => toText(profile))
  useEffect(() => { setF(profile); setText(toText(profile)) }, [profile])
  const save = useMutation({
    mutationFn: () => api.updateProfile({
      ...f, categories: list(text.categories), countries_include: list(text.countries_include), countries_exclude: list(text.countries_exclude),
      keywords_include: list(text.keywords_include), keywords_exclude: list(text.keywords_exclude), min_years: optNum(text.min_years), max_years: optNum(text.max_years),
    }),
    onSuccess: () => { toast('success', 'Search profile saved'); qc.invalidateQueries({ queryKey: ['profiles'] }) }, onError: (e: Error) => toast('error', e.message),
  })
  const t = (k: keyof typeof text) => (e: React.ChangeEvent<HTMLInputElement>) => setText({ ...text, [k]: e.target.value })
  const num = (k: 'threshold' | 'score_gap' | 'cooldown_days') => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: Number(e.target.value) })
  return (
    <Card title={`Search profile: ${profile.name}`}>
      <form className="grid gap-4 md:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
        <Field label="Profile name">{(id) => <input id={id} className={inputCls} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />}</Field>
        <Field label="Categories" hint="Comma-separated, e.g. IT. Empty means all.">{(id) => <input id={id} className={inputCls} value={text.categories} onChange={t('categories')} />}</Field>
        <Field label="Minimum years of experience">{(id) => <input id={id} type="number" min={0} className={inputCls} value={text.min_years} onChange={t('min_years')} />}</Field>
        <Field label="Maximum years of experience" hint="Empty means no maximum.">{(id) => <input id={id} type="number" min={0} className={inputCls} value={text.max_years} onChange={t('max_years')} />}</Field>
        <Field label="Only these countries" hint="Comma-separated. Empty means any.">{(id) => <input id={id} className={inputCls} value={text.countries_include} onChange={t('countries_include')} />}</Field>
        <Field label="Exclude countries" hint="Comma-separated, e.g. INDIA.">{(id) => <input id={id} className={inputCls} value={text.countries_exclude} onChange={t('countries_exclude')} />}</Field>
        <Field label="Keywords to include">{(id) => <input id={id} className={inputCls} value={text.keywords_include} onChange={t('keywords_include')} />}</Field>
        <Field label="Keywords to exclude">{(id) => <input id={id} className={inputCls} value={text.keywords_exclude} onChange={t('keywords_exclude')} />}</Field>
        <Field label="Match threshold (0-100)" hint="Jobs scoring below this are not matched. The score is an AI opinion, not a hiring probability.">{(id) => <input id={id} type="number" min={0} max={100} className={inputCls} value={f.threshold} onChange={num('threshold')} />}</Field>
        <Field label="Score gap" hint="One email only pitches roles within this many points of a recruiter's best match.">{(id) => <input id={id} type="number" min={0} max={100} className={inputCls} value={f.score_gap} onChange={num('score_gap')} />}</Field>
        <Field label="Recruiter cooldown (days)" hint="0 = off (default). A job is never drafted twice either way; set days only if you also want a pause between emails to the same recruiter.">{(id) => <input id={id} type="number" min={0} className={inputCls} value={f.cooldown_days} onChange={num('cooldown_days')} />}</Field>
        <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={f.auto_gmail_drafts} onChange={(e) => setF({ ...f, auto_gmail_drafts: e.target.checked })} />
          <span><strong>Create Gmail drafts automatically after each run</strong><br /><span className="text-slate-600">Off by default so you can review drafts here first. Drafts are never sent either way.</span></span></label>
        <div className="md:col-span-2"><Button variant="primary" type="submit" disabled={save.isPending}>{save.isPending ? 'Saving…' : 'Save search profile'}</Button></div>
      </form>
    </Card>
  )
}
const toText = (p: Profile) => ({
  categories: p.categories.join(', '), countries_include: p.countries_include.join(', '), countries_exclude: p.countries_exclude.join(', '),
  keywords_include: p.keywords_include.join(', '), keywords_exclude: p.keywords_exclude.join(', '),
  min_years: p.min_years === null ? '' : String(p.min_years), max_years: p.max_years === null ? '' : String(p.max_years),
})

function GmailCard({ settings }: { settings: Settings }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [confirm, setConfirm] = useState(false)
  const done = () => qc.invalidateQueries({ queryKey: ['settings'] })
  const connect = useMutation({ mutationFn: api.gmailConnect, onSuccess: () => { toast('success', 'Gmail connected'); done() }, onError: (e: Error) => toast('error', e.message) })
  const disconnect = useMutation({ mutationFn: api.gmailDisconnect, onSuccess: () => { toast('success', 'Gmail disconnected'); setConfirm(false); done() }, onError: (e: Error) => { setConfirm(false); toast('error', e.message) } })
  const g = settings.gmail
  return (
    <Card title="Gmail connection">
      <div className="space-y-2 text-sm">
        <p>{g.connected ? <><Tag tone="green">Connected</Tag> {g.account && <span className="ml-1">as {g.account}</span>}</> : <Tag tone="amber">Not connected</Tag>}</p>
        <p className="text-slate-600">Used only to create <strong>drafts</strong> in your Gmail. This app never sends email. Disconnecting deletes the stored login.</p>
        {!g.client_secret_present && <p role="note" className="rounded-md bg-amber-50 px-3 py-2 text-amber-900">Setup needed: <code>client_secret.json</code> (Google Cloud OAuth desktop client) is missing from the backend folder, so Gmail cannot be connected yet.</p>}
        <div className="flex gap-2 pt-1">
          {g.connected
            ? <Button variant="danger" onClick={() => setConfirm(true)} disabled={disconnect.isPending}>Disconnect Gmail</Button>
            : <Button variant="primary" onClick={() => connect.mutate()} disabled={!g.client_secret_present || connect.isPending}>{connect.isPending ? 'Waiting for Google… (check your browser)' : 'Connect Gmail'}</Button>}
        </div>
      </div>
      <ConfirmDialog open={confirm} title="Disconnect Gmail?" confirmLabel="Disconnect" danger busy={disconnect.isPending} onCancel={() => setConfirm(false)} onConfirm={() => disconnect.mutate()}>
        Drafts already in Gmail stay there. You will need to connect again before creating more.
      </ConfirmDialog>
    </Card>
  )
}

export default function SettingsPage() {
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: api.listProfiles })
  return (
    <>
      <PageHeader title="Settings" subtitle="Your resume, preferences, search profile and Gmail connection." />
      <div className="space-y-4">
        {settings.error ? <ErrorBox error={settings.error} onRetry={() => settings.refetch()} /> : settings.isLoading ? <SkeletonRows rows={6} /> : settings.data && (
          <><ResumeCard settings={settings.data} /><GeneralCard settings={settings.data} /><GmailCard settings={settings.data} /></>
        )}
        {profiles.error ? <ErrorBox error={profiles.error} onRetry={() => profiles.refetch()} /> : profiles.isLoading ? <SkeletonRows rows={6} /> : profiles.data?.map((p) => <ProfileCard key={p.id} profile={p} />)}
      </div>
    </>
  )
}
