// Checks that REAL backend responses (dumped by `uv run python -m tests.dump_contract_fixtures`) have the same
// shape (field names and nesting) as the mock the UI was built and tested against.
import { afterAll, describe, expect, it } from 'vitest'
import fixtures from './real_fixtures.json'
import { mockRequest } from '../api/mock'

type Json = unknown

const emptyLists = new Set<string>()  // lists that are empty in a sample: nothing to compare inside them

function shape(v: Json, path = '$'): string[] {
  if (Array.isArray(v)) {
    if (!v.length) { emptyLists.add(`${path}[]`); return [`${path}[]`] }
    return [`${path}[]`, ...shape(v[0], `${path}[]`)]
  }
  if (v && typeof v === 'object') {
    return Object.entries(v as Record<string, Json>).flatMap(([k, x]) => [`${path}.${k}`, ...shape(x, `${path}.${k}`)])
  }
  return []
}

// keys whose values are free-form maps or legitimately differ between backend and mock samples
const SKIP = /\.(sender|stats|progress)\./

const compared: string[] = []
const skipped: string[] = []

describe('real backend responses match the mock contract', () => {
  afterAll(() => {
    // fail loudly if the comparison silently covers too little
    expect(skipped, `skipped: ${skipped.join(' | ')}`).toEqual([])
    expect(compared.length).toBeGreaterThanOrEqual(24)
  })
  for (const [name, fx] of Object.entries(fixtures as Record<string, { method: string; path: string; query: Record<string, string | number>; body: unknown; response: Json }>)) {
    it(name, async () => {
      let mock: Json
      try {
        let body = fx.body ?? undefined
        if (fx.path === '/drafts/gmail') {  // the mock, like the real API, needs Gmail connected and real draft ids
          await mockRequest('POST', '/gmail/connect')
          const all = await mockRequest<{ items: { id: number; gmail_draft_id: string | null; status: string }[] }>('GET', '/drafts', undefined, { page_size: 100 })
          body = { ids: all.items.filter((d) => !d.gmail_draft_id && d.status === 'generated').slice(0, 2).map((d) => d.id) }
        }
        mock = await mockRequest(fx.method, fx.path, body, fx.query)
      } catch {
        mock = undefined
      }
      if (mock === undefined) { skipped.push(name); return }
      compared.push(name)
      emptyLists.clear()
      const realPaths = shape(fx.response)
      const mockPaths = shape(mock)
      const inEmpty = (p: string) => [...emptyLists].some((e) => p.startsWith(`${e}.`))
      const real = new Set(realPaths.filter((p) => !SKIP.test(p + '.') && !inEmpty(p)))
      const expected = new Set(mockPaths.filter((p) => !SKIP.test(p + '.') && !inEmpty(p)))
      const missingInReal = [...expected].filter((p) => !real.has(p))
      const extraInReal = [...real].filter((p) => !expected.has(p))
      expect({ missingInReal, extraInReal }).toEqual({ missingInReal: [], extraInReal: [] })
    })
  }
})
