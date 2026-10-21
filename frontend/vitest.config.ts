import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Tests run against the in-browser mock backend (the same fixtures as `npm run dev:mock`).
export default defineConfig({
  plugins: [react()],
  define: { 'import.meta.env.VITE_MOCK': JSON.stringify('1') },
  test: { environment: 'jsdom', globals: true, setupFiles: ['./src/test/setup.ts'], testTimeout: 15000 },
})
