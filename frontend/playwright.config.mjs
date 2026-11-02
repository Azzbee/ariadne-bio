import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const reports = fileURLToPath(new URL('../reports/browser/', import.meta.url));
const executablePath = process.env.ARIADNE_BROWSER_EXECUTABLE;
const port = Number(process.env.ARIADNE_BROWSER_PORT || 4173);
const apiPort = Number(process.env.ARIADNE_BROWSER_API_PORT || 4180);
for (const [name, value] of [['ARIADNE_BROWSER_PORT', port], ['ARIADNE_BROWSER_API_PORT', apiPort]]) {
  if (!Number.isInteger(value) || value < 1024 || value > 65535) {
    throw new Error(`${name} must be an integer from 1024 to 65535.`);
  }
}
if (port === apiPort) throw new Error('Browser static and API ports must be distinct.');

export default defineConfig({
  testDir: './browser',
  testMatch: 'smoke.spec.mjs',
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 60_000,
  globalTimeout: 300_000,
  expect: { timeout: 10_000 },
  outputDir: `${reports}/artifacts`,
  reporter: [
    ['line'],
    ['junit', { outputFile: `${reports}/junit.xml` }],
    ['json', { outputFile: `${reports}/results.json` }]
  ],
  metadata: {
    edition: 'Actual generated research snapshot and local memory API; native Chromium interactions',
    executable: executablePath || 'Playwright bundled Chromium'
  },
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    browserName: 'chromium',
    headless: true,
    viewport: { width: 1440, height: 1000 },
    reducedMotion: 'reduce',
    acceptDownloads: true,
    actionTimeout: 10_000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: executablePath ? { executablePath } : {}
  },
  webServer: [
    {
      command: 'node browser/server.mjs',
      url: `http://127.0.0.1:${port}/__browser_ready`,
      timeout: 30_000,
      reuseExistingServer: false,
      env: { ARIADNE_BROWSER_PORT: String(port) }
    },
    {
      command: `"$ARIADNE_BROWSER_PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: fileURLToPath(new URL('..', import.meta.url)),
      url: `http://127.0.0.1:${apiPort}/api/health`,
      timeout: 60_000,
      reuseExistingServer: false,
      env: {
        ARIADNE_BROWSER_PYTHON: process.env.ARIADNE_BROWSER_PYTHON || '.venv/bin/python',
        ARIADNE_DATA_DIR: fileURLToPath(new URL('../data/processed', import.meta.url)),
        ARIADNE_GRAPH_BACKEND: 'memory',
        ARIADNE_AGENT_MODE: 'deterministic',
        ARIADNE_LLM_BASE_URL: '',
        ARIADNE_LLM_API_KEY: ''
      }
    }
  ]
});
