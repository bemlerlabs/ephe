import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// The serial lane for wall-clock ceilings. One worker, no file parallelism and no
// concurrent test sequence, so the number describes the component. The plain-DOM
// control in the test marks an overloaded host instead of widening the budget.
export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.perf.test.{ts,tsx}'],
    pool: 'forks',
    maxWorkers: 1,
    minWorkers: 1,
    fileParallelism: false,
    sequence: { concurrent: false },
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, './src'),
    },
  },
})
