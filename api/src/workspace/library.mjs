import { promises as fs } from 'node:fs';
import path from 'node:path';
import { randomBytes, createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';

export const repo = fileURLToPath(new URL('../../../', import.meta.url));
const aiRoot = path.join(repo, 'ai');
try {
  process.loadEnvFile(path.join(aiRoot, '.env'));
} catch (error) {
  if (error.code !== 'ENOENT') throw error;
}
if (!process.env.INTERNAL_API_KEY)
  throw new Error('Configure INTERNAL_API_KEY for the AI service.');
if ((process.env.STORAGE_BACKEND || 'local') !== 'local')
  throw new Error(
    'The workspace gateway requires the shared local object adapter.',
  );
export const root = path.resolve(aiRoot, process.env.STORAGE_ROOT || 'objects');
export const stateRoot = path.resolve(
  process.env.WORKSPACE_STATE || path.join(repo, 'api', '.workspace-data'),
);
const ai = process.env.AI_BASE_URL || 'http://127.0.0.1:8000';
const python =
  process.env.RETRIEVAL_PYTHON ||
  path.join(
    aiRoot,
    '.venv',
    process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
  );
export const maxBytes = Number(process.env.MAX_UPLOAD_BYTES || 50000000);
const ttl = 24 * 60 * 60 * 1000;
const docs = new Map();
let active = null;
let searches = 0;
let maintenance = false;
const id = () => randomBytes(16).toString('hex');
const key = (tenant, doc) => tenant + '/' + doc;
const recordPath = (d) => path.join(stateRoot, d.tenant, d.id + '.json');
const prefix = (d) =>
  'tenant/' + d.tenant + '/documents/' + d.id + '/versions/v1/';
const sourceKey = (d) => prefix(d) + 'original/source.pdf';
const assertId = (val) => /^[a-f0-9]{32}$/.test(val);
export function fault(status, message) {
  return Object.assign(new Error(message), { status });
}
export async function writeAtomic(file, data) {
  await fs.mkdir(path.dirname(file), { recursive: true, mode: 0o700 });
  const tmp = file + '.' + id() + '.tmp';
  try {
    await fs.writeFile(tmp, data, { mode: 0o600 });
    await fs.rename(tmp, file);
  } finally {
    await fs.rm(tmp, { force: true });
  }
}
async function persist(d) {
  await writeAtomic(recordPath(d), JSON.stringify(d));
}
export function getDoc(tenant, doc) {
  if (!assertId(doc)) throw fault(404, 'Document not found.');
  const d = docs.get(key(tenant, doc));
  if (!d) throw fault(404, 'Document not found.');
  return d;
}
export function publicDoc(d) {
  return {
    id: d.id,
    name: d.name,
    size: d.size,
    created: d.created,
    status: d.status,
    total: d.total,
    pages: d.pages.map((p) => p.page),
    visualCount: d.pages.filter((p) => p.visual).length,
    visualStatus: d.visualStatus,
    error: d.error,
    warning: d.warning,
    sample: d.sample,
  };
}
export function listDocs(tenant) {
  return [...docs.values()]
    .filter((d) => d.tenant === tenant)
    .sort((a, b) => b.created - a.created)
    .map(publicDoc);
}
export async function checkSpace() {
  const disk = await fs.statfs(root);
  if (disk.bavail * disk.bsize < 1600000000)
    throw fault(507, 'Storage is busy. Remove a document and try again.');
}
export async function addDoc(tenant, name, bytes, sample = false) {
  if (!bytes.length || bytes.length > maxBytes)
    throw fault(413, 'PDF exceeds the upload limit or is empty.');
  if (bytes.subarray(0, 5).toString() !== '%PDF-')
    throw fault(415, 'Select a valid PDF file.');
  const hash = createHash('sha256').update(bytes).digest('hex');
  const old = [...docs.values()].find(
    (d) => d.tenant === tenant && d.hash === hash && d.status !== 'error',
  );
  if (old) return old;
  if (listDocs(tenant).length >= 12)
    throw fault(
      429,
      'This workspace holds 12 PDFs. Remove one to add another.',
    );
  if (
    [...docs.values()].filter((d) => ['queued', 'reading'].includes(d.status))
      .length >= 8
  )
    throw fault(429, 'The processing queue is full. Try again shortly.');
  await checkSpace();
  const d = {
    tenant,
    id: id(),
    name: name.slice(0, 180),
    size: bytes.length,
    hash,
    created: Date.now(),
    sample,
    status: 'queued',
    visualStatus: 'waiting',
    total: 0,
    pages: [],
    error: '',
    warning: '',
  };
  await writeAtomic(path.join(root, sourceKey(d)), bytes);
  await persist(d);
  docs.set(key(tenant, d.id), d);
  wake();
  return d;
}
async function aiPost(endpoint, body) {
  const response = await fetch(ai + '/api/v1/' + endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Internal-Key': process.env.INTERNAL_API_KEY,
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(15 * 60 * 1000),
  });
  const result = await response.json();
  if (!response.ok)
    throw fault(
      response.status,
      result.error?.message ||
        'The AI service could not complete this request.',
    );
  return result;
}
async function processDoc(d, stages, pages) {
  return aiPost('process', {
    tenant_id: d.tenant,
    document_id: d.id,
    document_version_id: 'v1',
    source: { key: sourceKey(d), mime_type: 'application/pdf', sha256: d.hash },
    stages,
    pages,
  });
}
async function indexText(d) {
  d.status = 'reading';
  await persist(d);
  const m = await processDoc(
    d,
    ['render', 'extraction', 'chunks', 'text_embeddings'],
    null,
  );
  d.total = m.total_pages;
  d.pages = m.pages
    .filter((p) => p.artifacts.render && p.artifacts.extraction)
    .map((p) => ({ page: p.page_number, artifacts: p.artifacts }));
  if (!d.pages.length)
    throw fault(
      422,
      m.pages.flatMap((p) => p.errors)[0]?.message ||
        'No readable pages in this PDF.',
    );
  if (m.status !== 'success')
    d.warning =
      'Some page features could not be indexed. Available pages remain searchable.';
  d.status = 'ready';
  d.visualStatus = 'pending';
  await persist(d);
}
async function indexVisual(d) {
  const page = d.pages.find((p) => !p.visual && !p.visualFailed);
  if (!page) {
    d.visualStatus = d.pages.some((p) => p.visualFailed) ? 'partial' : 'ready';
    await persist(d);
    return;
  }
  await checkSpace();
  const m = await processDoc(d, ['visual_embeddings'], [page.page]);
  const ref = m.pages[0]?.artifacts.visual_embeddings;
  if (ref) page.visual = ref;
  else if (
    m.pages[0]?.errors.some((e) => e.retryable) &&
    (page.attempts || 0) < 2
  ) {
    page.attempts = (page.attempts || 0) + 1;
    await sleep(1000);
  } else page.visualFailed = true;
  await persist(d);
}
async function work() {
  if (active || maintenance) return;
  const all = [...docs.values()];
  const d =
    all.find((r) => r.status === 'queued') ||
    (!searches &&
      all.find((r) => r.status === 'ready' && r.visualStatus === 'pending'));
  if (!d) return;
  active = d;
  try {
    if (d.status === 'queued') await indexText(d);
    else await indexVisual(d);
  } catch (error) {
    if (error.status === 429 && (d.busyRetries || 0) < 20) {
      d.busyRetries = (d.busyRetries || 0) + 1;
      if (d.status === 'reading') d.status = 'queued';
      await sleep(1200);
    } else if (d.status === 'ready') {
      d.visualStatus = 'partial';
      d.warning = 'Visual indexing is unavailable. Text search is ready.';
    } else {
      d.status = 'error';
      d.error =
        error.status && error.status < 500
          ? error.message
          : 'Indexing failed. Retry the document to try again.';
    }
    await persist(d);
  } finally {
    active = null;
    if (d.deleteRequested) await removeDoc(d);
    wake();
  }
}
function wake() {
  setTimeout(
    () => work().catch((e) => console.error('Workspace worker:', e.name)),
    100,
  ).unref();
}
export async function removeDoc(d) {
  if (active === d) {
    // Hide immediately; discard any remaining writes when the in-flight AI call exits.
    d.deleteRequested = true;
    await persist(d);
    docs.delete(key(d.tenant, d.id));
    return;
  }
  docs.delete(key(d.tenant, d.id));
  await fs.rm(recordPath(d), { force: true });
  await fs.rm(path.join(root, 'tenant', d.tenant, 'documents', d.id), {
    recursive: true,
    force: true,
  });
  if (!listDocs(d.tenant).length)
    await fs.rm(path.join(root, 'tenant', d.tenant, 'queries'), {
      recursive: true,
      force: true,
    });
}
export async function retry(d) {
  if (active === d) throw fault(409, 'This document is already being indexed.');
  if (d.status === 'error') {
    d.status = 'queued';
    d.error = '';
  } else if (d.visualStatus === 'partial') {
    for (const p of d.pages) {
      delete p.visualFailed;
      delete p.attempts;
    }
    d.visualStatus = 'pending';
  }
  d.busyRetries = 0;
  await persist(d);
  wake();
  return publicDoc(d);
}
async function sweep() {
  if (maintenance) return;
  maintenance = true;
  try {
    for (const d of docs.values())
      if (d.created < Date.now() - ttl && active !== d) await removeDoc(d);
  } finally {
    maintenance = false;
    wake();
  }
}
export async function init() {
  await fs.mkdir(stateRoot, { recursive: true, mode: 0o700 });
  await fs.mkdir(root, { recursive: true });
  for (const t of await fs.readdir(stateRoot)) {
    if (!assertId(t)) continue;
    for (const f of await fs.readdir(path.join(stateRoot, t))) {
      if (!/^[a-f0-9]{32}\.json$/.test(f)) continue;
      const d = JSON.parse(
        await fs.readFile(path.join(stateRoot, t, f), 'utf8'),
      );
      if (d.tenant !== t || f !== d.id + '.json') continue;
      if (d.deleteRequested) {
        await removeDoc(d);
        continue;
      }
      if (d.status === 'reading') d.status = 'queued';
      docs.set(key(t, d.id), d);
    }
  }
  await sweep();
  setInterval(
    () => sweep().catch((e) => console.error('Workspace cleanup:', e.name)),
    600000,
  ).unref();
  wake();
}
export async function preview(d, n) {
  const p = d.pages.find((p) => p.page === n);
  if (!p) throw fault(404, 'Page not found.');
  const ref = p.artifacts.render;
  if (!ref.key.startsWith(prefix(d)))
    throw fault(500, 'Invalid page reference.');
  return {
    bytes: await fs.readFile(path.join(root, ref.key)),
    type: ref.media_type,
  };
}
export async function details(d, n) {
  const page = d.pages.find((p) => p.page === n);
  if (!page) throw fault(404, 'Page not found.');
  const ref = page.artifacts.extraction;
  if (!ref.key.startsWith(prefix(d)))
    throw fault(500, 'Invalid extraction reference.');
  const bytes = await fs.readFile(path.join(root, ref.key));
  if (createHash('sha256').update(bytes).digest('hex') !== ref.sha256)
    throw fault(502, 'Page integrity check failed.');
  const p = JSON.parse(bytes);
  return {
    page: p.page_number,
    method: p.extraction_method,
    confidence: p.confidence,
    text: p.text,
    tables: p.tables,
  };
}
function score(input) {
  return new Promise((resolve, reject) => {
    const worker = spawn(
      python,
      [path.join(repo, 'retrieval', 'workspace', 'rank.py')],
      {
        stdio: ['pipe', 'pipe', 'pipe'],
        env: {
          ...process.env,
          PYTHONIOENCODING: 'utf-8',
          OPENBLAS_NUM_THREADS: '1',
          OMP_NUM_THREADS: '1',
        },
      },
    );
    let out = '';
    worker.stdout.on('data', (b) => (out += b));
    worker.stderr.resume();
    const timer = setTimeout(() => worker.kill(), 45000);
    timer.unref();
    worker.on('error', reject);
    worker.on('close', (code) => {
      clearTimeout(timer);
      if (code !== 0)
        return reject(fault(503, 'Page ranking failed. Please try again.'));
      try {
        resolve(JSON.parse(out));
      } catch {
        reject(fault(503, 'Invalid ranking response.'));
      }
    });
    worker.stdin.on('error', () => {});
    worker.stdin.end(JSON.stringify(input));
  });
}
export async function search(d, query, mode) {
  if (d.status !== 'ready')
    throw fault(409, 'Your PDF is still being indexed.');
  if (searches >= 4)
    throw fault(429, 'Search is busy. Please try again shortly.');
  if (mode === 'visual' && !d.pages.some((p) => p.visual))
    throw fault(409, 'Visual indexing is still in progress.');
  searches++;
  const body = { tenant_id: d.tenant, text: query };
  let visual = null,
    dense = null;
  const notes = [];
  async function queryModel(endpoint) {
    for (let i = 0; ; i++) {
      try {
        return await aiPost(endpoint, body);
      } catch (e) {
        if (e.status !== 429 || i === 4) throw e;
        await sleep(350 * (i + 1));
      }
    }
  }
  try {
    if (mode !== 'visual') {
      try {
        dense = await queryModel('embeddings/query');
      } catch {
        notes.push('Semantic search is busy. Showing available matches.');
      }
    }
    if (mode !== 'text' && d.pages.some((p) => p.visual)) {
      try {
        visual = await queryModel('embeddings/visual/query');
      } catch {
        if (mode === 'visual')
          throw fault(503, 'Visual search is busy. Please try again.');
        notes.push('Visual search is busy. Showing available matches.');
      }
    }
    const results = await score({
      root,
      prefix: prefix(d),
      queryPrefix: 'tenant/' + d.tenant + '/queries/derived/',
      pages: d.pages,
      query,
      mode,
      dense,
      visual,
    });
    return { results, notes };
  } finally {
    searches--;
    wake();
  }
}
