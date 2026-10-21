import { useState } from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { MOCK } from './api/client'
import { cx } from './components/ui'
import Dashboard from './pages/Dashboard'
import Drafts from './pages/Drafts'
import JobDetail from './pages/JobDetail'
import Jobs from './pages/Jobs'
import RunDetail from './pages/RunDetail'
import Runs from './pages/Runs'
import SettingsPage from './pages/Settings'

const NAV = [
  { to: '/', label: 'Dashboard', end: true }, { to: '/jobs', label: 'Jobs' }, { to: '/drafts', label: 'Drafts' },
  { to: '/runs', label: 'Runs' }, { to: '/settings', label: 'Settings' },
]

export default function App() {
  const [open, setOpen] = useState(false)
  return (
    <div className="flex min-h-full flex-col">
      {MOCK && (
        <div role="note" className="bg-amber-300 px-4 py-1.5 text-center text-sm font-semibold text-amber-950">
          MOCK DATA: this is a preview with fake data and no backend. Nothing you do here is saved.
        </div>
      )}
      <div className="flex flex-1">
        <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">Skip to content</a>
        <aside className={cx('fixed inset-y-0 left-0 z-40 w-56 transform border-r border-slate-200 bg-white p-4 transition md:static md:translate-x-0', open ? 'translate-x-0' : '-translate-x-full')} aria-label="Primary">
          <div className="mb-6 text-lg font-bold text-indigo-800">Job Tracker</div>
          <nav className="flex flex-col gap-1">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} onClick={() => setOpen(false)}
                className={({ isActive }) => cx('rounded-md px-3 py-2 text-sm font-medium', isActive ? 'bg-indigo-50 text-indigo-800' : 'text-slate-700 hover:bg-slate-100')}>
                {n.label}
              </NavLink>
            ))}
          </nav>
        </aside>
        {open && <div className="fixed inset-0 z-30 bg-slate-900/30 md:hidden" onClick={() => setOpen(false)} aria-hidden />}
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-2 md:hidden">
            <button className="rounded-md px-2 py-1 ring-1 ring-slate-300" aria-label="Open navigation" aria-expanded={open} onClick={() => setOpen(true)}>☰</button>
            <span className="font-semibold text-indigo-800">Job Tracker</span>
          </header>
          <main id="main" className="mx-auto w-full max-w-7xl flex-1 p-4 md:p-6">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/jobs" element={<Jobs />} />
              <Route path="/jobs/:id" element={<JobDetail />} />
              <Route path="/drafts" element={<Drafts />} />
              <Route path="/runs" element={<Runs />} />
              <Route path="/runs/:id" element={<RunDetail />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </div>
    </div>
  )
}
