# Job Tracker frontend

React 18 + Vite + TypeScript + Tailwind. Talks to the FastAPI backend through `src/api/client.ts` only; the
contract is in `../docs/API.md`.

## Run

```bash
npm install
npm run dev          # http://localhost:5173, proxies /api to http://127.0.0.1:8000
npm run dev:mock     # same UI with FAKE in-browser data, no backend needed (a yellow MOCK DATA banner is shown)
npm run build        # type-checks, then builds to dist/ (the backend serves dist/ at /)
npm run typecheck    # tsc --noEmit
npm test             # render + contract tests against the mock backend (vitest, jsdom)
```

## Layout

- `src/api/` `types.ts` (contract types), `client.ts` (all requests), `mock.ts` (mock backend, only loaded when `VITE_MOCK=1`; not in the production bundle)
- `src/pages/` Dashboard, Jobs, JobDetail, Drafts, Runs, RunDetail, Settings
- `src/components/` shared UI (`ui.tsx`), charts, run progress
- `src/lib/` formatting (`-` for missing data, `0` for real zeros) and dashboard drill-down links

## Notes

- Jobs filters live in the URL query, so dashboard cards and chart bars deep-link into a filtered Jobs list.
- Dashboard counts are "ever reached this stage"; the Jobs filter uses a job's current status, so a drill-down can show
  fewer rows (for example an applied job that was later rejected).
- The mock mode and tests were checked in jsdom and by type-check/build. Nothing here has been checked visually in a browser.
