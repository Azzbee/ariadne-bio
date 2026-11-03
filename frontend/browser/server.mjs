/** Isolated loopback server for the real exported application, never a mocked API. */
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { extname, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
const dataRoot = resolve(root, 'data');
let manifest;
try {
  manifest = JSON.parse(await readFile(resolve(dataRoot, 'manifest.json'), 'utf8'));
} catch (error) {
  if (error.code === 'ENOENT') {
    throw new Error('Browser smoke requires generated frontend/data/manifest.json. Run make prepare-data and make snapshot first.');
  }
  throw error;
}
if (manifest.mode !== 'snapshot' || !manifest.cases || !manifest.files?.length) {
  throw new Error('Browser smoke requires a complete generated research snapshot, not an empty fixture.');
}
for (const disease of ['Disease::DOID:10652', 'Disease::DOID:7148']) {
  const file = manifest.cases[disease]?.file;
  const path = typeof file === 'string' ? resolve(dataRoot, file) : '';
  if (!path.startsWith(`${dataRoot}${sep}`) || !(await stat(path)).isFile()) {
    throw new Error(`Browser smoke is missing the exported case ${disease}. Run make snapshot.`);
  }
}

const types = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.ico': 'image/x-icon', '.woff2': 'font/woff2'
};
const server = createServer(async (request, response) => {
  try {
    const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
    if (pathname === '/__browser_ready') {
      response.writeHead(200, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify({ ready: true, edition: 'snapshot', version: manifest.health?.version }));
      return;
    }
    const path = resolve(root, `.${pathname === '/' ? '/index.html' : pathname}`);
    if (!path.startsWith(`${root}${sep}`) || !['GET', 'HEAD'].includes(request.method)) {
      response.writeHead(403); response.end(); return;
    }
    const bytes = await readFile(path);
    response.writeHead(200, {
      'Content-Type': types[extname(path)] || 'application/octet-stream',
      'Content-Length': bytes.byteLength, 'Cache-Control': 'no-store'
    });
    response.end(request.method === 'HEAD' ? undefined : bytes);
  } catch (error) {
    response.writeHead(error.code === 'ENOENT' || error.code === 'EISDIR' ? 404 : 500);
    response.end('Static browser-test resource unavailable.');
  }
});
server.listen(Number(process.env.ARIADNE_BROWSER_PORT || 4173), '127.0.0.1');
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => server.close(() => process.exit(0)));
