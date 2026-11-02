import { test as base, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';

const test = base.extend({
  page: async ({ page }, use, testInfo) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await use(page);
    if (errors.length) await testInfo.attach('uncaught-browser-errors', { body: JSON.stringify(errors), contentType: 'application/json' });
    expect(errors, 'The actual application must not throw uncaught browser errors.').toEqual([]);
  }
});
const alzheimer = 'Disease::DOID:10652', nicotine = 'Compound::DB00184';
const arthritis = 'Disease::DOID:7148', marimastat = 'Compound::DB00786';
const dataRoot = new URL('../data/', import.meta.url);
const apiOrigin = `http://127.0.0.1:${Number(process.env.ARIADNE_BROWSER_API_PORT || 4180)}`;
let manifest;

test.beforeAll(async () => {
  manifest = JSON.parse(await readFile(new URL('manifest.json', dataRoot), 'utf8'));
});

async function exportedCase(diseaseId) {
  const descriptor = manifest.cases[diseaseId];
  expect(descriptor, `Exported case ${diseaseId} is required; run make snapshot.`).toBeTruthy();
  const bytes = await readFile(new URL(descriptor.file, dataRoot));
  const record = manifest.files.find(item => item.path === descriptor.file);
  expect(record).toBeTruthy();
  expect(bytes.byteLength).toBe(record.bytes);
  expect(createHash('sha256').update(bytes).digest('hex')).toBe(record.sha256);
  return JSON.parse(bytes);
}

async function investigate(page, diseaseId = alzheimer, compoundId = nicotine) {
  const query = new URLSearchParams({ mode: 'snapshot', view: 'investigate', disease: diseaseId, compound: compoundId });
  await page.goto(`/?${query}`);
  await expect(page.locator('#fatal-error')).toBeHidden();
  await expect(page.locator('#workbench')).toHaveAttribute('aria-busy', 'false');
  await expect(page.locator('#assessment-section')).toBeVisible();
  await expect(page.locator('#agent-submit')).toBeEnabled();
}

test('native evidence checkbox changes rank to the exported challenge result and restores it', async ({ page }) => {
  const data = await exportedCase(alzheimer);
  const original = data.assessments[nicotine][''];
  const challenged = data.assessments[nicotine].INTERACTS;
  expect(original.current.supported).toBe(true);
  expect(challenged.current.supported).toBe(true);
  expect(challenged.current.rank).not.toBe(original.current.rank);
  const baselineRank = `#${original.baseline.rank}`;
  const originalRank = `#${original.current.rank}`;
  const challengedRank = `#${challenged.current.rank}`;
  await investigate(page);
  await expect(page.locator('#assessment-title')).toContainText('Nicotine');
  const row = page.locator('.assessment-table').getByRole('row', { name: /^Supported rank / });
  await expect(row.getByRole('cell').nth(0)).toHaveText(baselineRank);
  await expect(row.getByRole('cell').nth(1)).toHaveText(originalRank);
  const label = page.locator('#evidence-switches label').filter({ hasText: 'Gene interactions' });
  const checkbox = label.getByRole('checkbox');
  await expect(checkbox).toBeChecked();
  // Click the visible native label. Do not dispatch a synthetic change event or edit state.
  await label.click();
  await expect(checkbox).not.toBeChecked();
  await expect(row.getByRole('cell').nth(0)).toHaveText(baselineRank);
  await expect(row.getByRole('cell').nth(1)).toHaveText(challengedRank);
  await expect(page.locator('#path-count-interaction')).toHaveText('0');
  await expect(page).toHaveURL(/exclude=INTERACTS/);
  await label.click();
  await expect(checkbox).toBeChecked();
  await expect(row.getByRole('cell').nth(1)).toHaveText(originalRank);
  await expect.poll(() => new URL(page.url()).searchParams.get('exclude')).toBeNull();
});

test('native details expand and the actual research form submits a deterministic answer', async ({ page }) => {
  await investigate(page);
  const details = page.locator('.assessment-details');
  await expect(details).toHaveJSProperty('open', false);
  await details.locator('summary').click();
  await expect(details).toHaveJSProperty('open', true);
  await expect(details.getByRole('region', { name: 'Exact model terms table' })).toBeVisible();
  await details.locator('summary').click();
  await expect(details).toHaveJSProperty('open', false);
  await page.getByLabel('Ask the research guide about the selected compound').fill("Explain Nicotine for Alzheimer's disease.");
  await page.locator('#agent-form').getByRole('button', { name: 'Investigate', exact: true }).click();
  const answer = page.locator('#agent-response');
  await expect(answer).toBeVisible();
  await expect(answer.locator('.agent-response-header')).toContainText('EVIDENCE BRIEF');
  await expect(answer.locator('.agent-response-header')).toContainText('Deterministic · snapshot');
  await expect(answer.locator('.agent-answer')).toContainText('Nicotine');
  await expect(answer.locator('.agent-trace')).toContainText('load_recorded_assessment');
  await expect(answer.locator('.agent-citations')).toBeVisible();
  await expect(page.locator('#investigate-view')).toBeVisible();
});

test('navigation controls change views while an ordinary source link opens its own page', async ({ page, context }) => {
  // Fulfill the external destination locally; the browser must still perform native popup navigation.
  await context.route('https://github.com/**', route => route.fulfill({
    status: 200, contentType: 'text/plain', body: 'Local fixture for the source-link destination.'
  }));
  await page.goto('/?mode=snapshot');
  await expect(page.locator('#overview-view')).toBeVisible();
  const nav = page.getByRole('navigation', { name: 'Main navigation' });
  await nav.getByRole('button', { name: 'Workbench', exact: true }).click();
  await expect(page.locator('#investigate-view')).toBeVisible();
  await expect(page.locator('#workbench')).toHaveAttribute('aria-busy', 'false');
  await nav.getByRole('button', { name: 'Benchmark', exact: true }).click();
  await expect(page.locator('#benchmark-view')).toBeVisible();
  await expect(page.locator('#investigate-view')).toBeHidden();
  await nav.getByRole('button', { name: 'Method & sources', exact: true }).click();
  await expect(page.locator('#method-view')).toBeVisible();
  await page.getByRole('link', { name: 'ARIADNE home', exact: true }).click();
  await expect(page.locator('#overview-view')).toBeVisible();
  const popupPromise = page.waitForEvent('popup');
  await page.getByRole('link', { name: 'View source code on GitHub', exact: true }).click();
  const popup = await popupPromise;
  await expect(popup).toHaveURL('https://github.com/Azzbee/ariadne-bio');
  await popup.close();
  await expect(page.locator('#overview-view')).toBeVisible();
});

test('joint audit verifies and downloads the complete unchanged certificate through native browser events', async ({ page, browser }, testInfo) => {
  const data = await exportedCase(arthritis);
  const expected = data.mixed_audits[marimastat]['10:1:1'];
  await investigate(page, arthritis, marimastat);
  await page.locator('#mixed-run').click();
  await expect(page.locator('#mixed-body .mixed-cell')).toHaveCount(4);
  await page.locator('#mixed-verify').click();
  await expect(page.locator('#mixed-verification')).toContainText('Matches a verified recorded joint certificate.');
  const downloadPromise = page.waitForEvent('download');
  await page.locator('#mixed-section').getByRole('button', { name: 'Certificate', exact: true }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('ariadne-rheumatoid-arthritis-marimastat-joint-audit.json');
  const target = testInfo.outputPath('joint-audit.json');
  await download.saveAs(target);
  expect(await download.failure()).toBeNull();
  const bytes = await readFile(target);
  expect(bytes.equals(Buffer.from(JSON.stringify(expected, null, 2)))).toBe(true);
  expect(JSON.parse(bytes)).toEqual(expected);
  await testInfo.attach('downloaded-joint-certificate', { path: target, contentType: 'application/json' });
  await testInfo.attach('executed-browser-and-inputs', {
    body: JSON.stringify({ browser: browser.version(), node: process.version, snapshot_version: manifest.health.version,
      graph_sha256: manifest.graph_sha256, model_sha256: manifest.model_sha256,
      certificate_sha256: expected.certificate_sha256, downloaded_bytes: bytes.byteLength }),
    contentType: 'application/json'
  });
});

async function blockExternalRequests(context) {
  const blocked = [];
  await context.route('**/*', route => {
    const url = route.request().url();
    if (new URL(url).origin === apiOrigin) return route.continue();
    blocked.push(url);
    return route.abort('blockedbyclient');
  });
  return blocked;
}

test('self-hosted Swagger renders and executes GET health with external requests blocked', async ({ page, context }, testInfo) => {
  const blocked = await blockExternalRequests(context);
  await page.goto(`${apiOrigin}/docs`);
  await expect(page.getByRole('heading', { name: /ARIADNE.*Biomedical Evidence Investigator/ })).toBeVisible();
  const health = page.locator('.opblock').filter({ has: page.locator('[data-path="/api/health"]') });
  await health.locator('.opblock-summary-control').click();
  await health.getByRole('button', { name: 'Try it out', exact: true }).click();
  const responsePromise = page.waitForResponse(response =>
    response.url() === `${apiOrigin}/api/health` && response.request().method() === 'GET');
  await health.getByRole('button', { name: 'Execute', exact: true }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body).toMatchObject({ status: 'ok', graph_backend: 'memory', dataset_ready: true,
    agent_mode: 'deterministic', version: manifest.health.version });
  await expect(health.locator('.live-responses-table')).toContainText('200');
  await expect(health.locator('.live-responses-table')).toContainText('"dataset_ready": true');
  expect(blocked, 'The self-hosted reference must not request third-party assets or validators.').toEqual([]);
  await testInfo.attach('actual-swagger-health-response', {
    body: JSON.stringify({ status: response.status(), body, blocked_external_requests: blocked }),
    contentType: 'application/json'
  });
});

test('self-hosted ReDoc renders and navigates to the health endpoint with external requests blocked', async ({ page, context }, testInfo) => {
  const blocked = await blockExternalRequests(context);
  const schemaPromise = page.waitForResponse(response => response.url() === `${apiOrigin}/openapi.json`);
  await page.goto(`${apiOrigin}/redoc`);
  const schemaResponse = await schemaPromise;
  expect(schemaResponse.status()).toBe(200);
  const schema = await schemaResponse.json();
  await expect(page.getByRole('heading', { level: 1, name: /ARIADNE.*Biomedical Evidence Investigator/ })).toBeVisible();
  const menu = page.locator('.menu-content');
  await expect(menu).toBeVisible();
  await menu.getByText('Operations', { exact: true }).click();
  await menu.getByText('Health', { exact: true }).click();
  const health = schema.paths['/api/health'].get;
  const operation = health.operationId;
  const anchor = `tag/${health.tags[0]}/operation/${operation}`;
  await expect.poll(() => decodeURIComponent(new URL(page.url()).hash)).toBe(`#${anchor}`);
  const endpoint = page.locator(`[data-section-id="${anchor}"]`);
  await expect(endpoint.getByRole('heading').filter({ hasText: 'Health' })).toBeVisible();
  await expect(endpoint.getByRole('button', { name: 'get /api/health', exact: true })).toBeInViewport();
  expect(blocked, 'The self-hosted reference must not request third-party assets or fonts.').toEqual([]);
  await testInfo.attach('actual-redoc-navigation', {
    body: JSON.stringify({ title: schema.info.title, version: schema.info.version,
      selected_operation: operation, browser_url: page.url(), blocked_external_requests: blocked }),
    contentType: 'application/json'
  });
});
