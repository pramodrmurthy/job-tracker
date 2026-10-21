import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Cell } from 'recharts'
import type { Distribution, FunnelStage, RunPoint } from '../api/types'
import { PALETTE, fmtDate, fmtNum, fmtPct } from '../lib/format'

/** Wraps a chart with an accessible name and a visually hidden data table with the same numbers. */
export function ChartFrame({ label, columns, rows, children, height = 260 }: {
  label: string; columns: string[]; rows: (string | number | null)[][]; children: React.ReactNode; height?: number
}) {
  return (
    <figure aria-label={label} className="m-0">
      <div style={{ height }} role="img" aria-label={label}>{children}</div>
      <table className="sr-only">
        <caption>{label}</caption>
        <thead><tr>{columns.map((c) => <th key={c} scope="col">{c}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c === null ? 'no data' : c}</td>)}</tr>)}</tbody>
      </table>
    </figure>
  )
}

export function FunnelChart({ stages, onSelect }: { stages: FunnelStage[]; onSelect?: (stage: string) => void }) {
  const label = (s: FunnelStage) => s.label
  return (
    <>
      <ChartFrame label="Application funnel" columns={['Stage', 'Count', 'Rate vs previous stage']}
        rows={stages.map((s) => [s.label, s.count, s.rate === null ? null : fmtPct(s.rate)])} height={Math.max(240, stages.length * 36)}>
        <ResponsiveContainer>
          <BarChart data={stages} layout="vertical" margin={{ left: 20, right: 30 }}>
            <CartesianGrid horizontal={false} stroke="#e2e8f0" />
            <XAxis type="number" allowDecimals={false} />
            <YAxis type="category" dataKey="label" width={110} tick={{ fontSize: 12 }} />
            <Tooltip content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const s = payload[0].payload as FunnelStage
              const prev = stages.find((x) => x.stage === s.of)
              return (
                <div className="rounded-md border border-slate-200 bg-white p-2 text-xs shadow">
                  <div className="font-semibold">{label(s)}: {fmtNum(s.count)}</div>
                  <div>{s.rate === null ? 'Rate: - (no previous stage or zero denominator)' : `${fmtPct(s.rate)} of ${prev?.label ?? s.of}`}</div>
                </div>
              )
            }} />
            <Bar dataKey="count" cursor={onSelect ? 'pointer' : undefined} onClick={(d) => onSelect?.((d as unknown as FunnelStage).stage)}>
              {stages.map((_, i) => <Cell key={i} fill={PALETTE[0]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </ChartFrame>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
        {stages.map((s) => <li key={s.stage}>{s.label}: <strong>{fmtNum(s.count)}</strong>{s.rate !== null && s.of ? ` (${fmtPct(s.rate)} of ${stages.find((x) => x.stage === s.of)?.label ?? s.of})` : ''}</li>)}
      </ul>
    </>
  )
}

export interface SeriesDef { key: string; name: string; dash?: string }
export function TimeseriesChart({ data, series }: { data: Record<string, number | string>[]; series: SeriesDef[] }) {
  return (
    <ChartFrame label="Jobs and applications over time" columns={['Date', ...series.map((s) => s.name)]} rows={data.map((d) => [String(d.date), ...series.map((s) => (d[s.key] as number) ?? null)])}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ left: 0, right: 16 }}>
          <CartesianGrid stroke="#e2e8f0" />
          <XAxis dataKey="date" tickFormatter={(v: string) => fmtDate(v).replace(/, \d{4}/, '')} tick={{ fontSize: 11 }} minTickGap={24} />
          <YAxis allowDecimals={false} width={32} />
          <Tooltip labelFormatter={(v) => fmtDate(String(v))} />
          <Legend />
          {series.map((s, i) => <Line key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={PALETTE[i]} strokeDasharray={s.dash} strokeWidth={2} dot={false} />)}
        </LineChart>
      </ResponsiveContainer>
    </ChartFrame>
  )
}

export function DistChart({ title, data, color = 0, onSelect }: { title: string; data: Distribution[]; color?: number; onSelect?: (label: string) => void }) {
  const top = data.slice(0, 8)
  return (
    <ChartFrame label={title} columns={['Label', 'Jobs']} rows={top.map((d) => [d.label, d.count])} height={Math.max(180, top.length * 30)}>
      <ResponsiveContainer>
        <BarChart data={top} layout="vertical" margin={{ left: 10, right: 24 }}>
          <CartesianGrid horizontal={false} stroke="#e2e8f0" />
          <XAxis type="number" allowDecimals={false} />
          <YAxis type="category" dataKey="label" width={96} tick={{ fontSize: 12 }} />
          <Tooltip />
          <Bar dataKey="count" name="Jobs" fill={PALETTE[color]} cursor={onSelect ? 'pointer' : undefined} onClick={(d) => onSelect?.((d as unknown as Distribution).label)} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  )
}

export function RunsChart({ data }: { data: RunPoint[] }) {
  const rows = data.map((r) => ({ ...r, name: `#${r.run_id}` }))
  return (
    <ChartFrame label="Jobs per run: new versus previously seen" columns={['Run', 'New', 'Previously seen', 'Matched', 'Errors']}
      rows={data.map((r) => [`#${r.run_id}`, r.new_jobs, r.known_jobs, r.matched, r.errors])}>
      <ResponsiveContainer>
        <BarChart data={rows} margin={{ left: 0, right: 16 }}>
          <CartesianGrid stroke="#e2e8f0" />
          <XAxis dataKey="name" />
          <YAxis allowDecimals={false} width={36} />
          <Tooltip />
          <Legend />
          <Bar dataKey="new_jobs" name="New" stackId="a" fill={PALETTE[0]} />
          <Bar dataKey="known_jobs" name="Previously seen" stackId="a" fill={PALETTE[4]} />
          <Bar dataKey="matched" name="Matched" fill={PALETTE[2]} />
          <Bar dataKey="errors" name="Errors" fill={PALETTE[5]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  )
}
