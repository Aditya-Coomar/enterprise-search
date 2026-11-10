import express from 'express';
import { createHash, randomBytes } from 'node:crypto';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import {
  addDoc,
  checkSpace,
  details,
  fault,
  getDoc,
  init,
  listDocs,
  maxBytes,
  preview,
  publicDoc,
  removeDoc,
  repo,
  retry,
  search,
} from './library.mjs';

const app = express();
app.disable('x-powered-by');
await init();
const router = express.Router();
const limits = new Map();
function withinLimit(key, maximum, window) {
  const now = Date.now();
  const slot = limits.get(key);
  if (!slot || slot.until <= now) {
    limits.set(key, { until: now + window, count: 1 });
    return true;
  }
  return ++slot.count <= maximum;
}
setInterval(() => {
  for (const [key, v] of limits) if (v.until < Date.now()) limits.delete(key);
}, 60000).unref();
router.use((req, res, next) => {
  res.set({
    'Cache-Control': 'private, no-store',
    'X-Content-Type-Options': 'nosniff',
    Vary: 'Cookie',
  });
  if (req.method !== 'GET' && req.get('X-Folio-Request') !== '1')
    return next(fault(403, 'Open this request from the workspace.'));
  const cookie = req.headers.cookie?.match(
    /(?:^|;\s*)folio_session=([a-f0-9]{64})(?:;|$)/,
  )?.[1];
  const session = cookie || randomBytes(32).toString('hex');
  if (!cookie)
    res.cookie('folio_session', session, {
      httpOnly: true,
      sameSite: 'strict',
      secure: req.get('X-Forwarded-Proto') === 'https',
      maxAge: 86400000,
      path: '/',
    });
  req.tenant = createHash('sha256').update(session).digest('hex').slice(0, 32);
  if (req.method !== 'GET') {
    const ip =
      req.get('CF-Connecting-IP') || req.socket.remoteAddress || 'local';
    if (!withinLimit('request:' + ip, 120, 60000))
      return next(fault(429, 'Too many requests. Try again in a minute.'));
    if (req.path === '/documents' && !withinLimit('upload:' + ip, 20, 3600000))
      return next(fault(429, 'Upload limit reached. Try again later.'));
  }
  next();
});
router.get('/documents', (req, res) =>
  res.json({ documents: listDocs(req.tenant), maxBytes }),
);
let incoming = 0;
router.post(
  '/documents',
  async (req, res, next) => {
    if (incoming >= 2)
      return next(
        fault(429, 'Another upload is in progress. Try again shortly.'),
      );
    if (req.get('Content-Type')?.split(';')[0] !== 'application/pdf')
      return next(fault(415, 'Choose a PDF file.'));
    await checkSpace();
    incoming++;
    let released = false;
    const release = () => {
      if (!released) {
        released = true;
        incoming--;
      }
    };
    res.once('finish', release);
    res.once('close', release);
    next();
  },
  express.raw({ type: 'application/pdf', limit: maxBytes }),
  async (req, res) => {
    let name;
    try {
      name = decodeURIComponent(req.get('X-Filename') || 'document.pdf');
    } catch {
      throw fault(400, 'Invalid filename.');
    }
    name = path
      .basename(name.replaceAll('\\', '/'))
      .replace(/[\x00-\x1f\x7f]/g, '')
      .trim();
    if (!name.toLowerCase().endsWith('.pdf'))
      throw fault(415, 'Choose a file with a .pdf extension.');
    res.status(202).json(publicDoc(await addDoc(req.tenant, name, req.body)));
  },
);
router.post('/sample', async (req, res) => {
  const bytes = await fs.readFile(
    path.join(repo, 'web/public/sample/northline-field-report.pdf'),
  );
  res
    .status(202)
    .json(
      publicDoc(
        await addDoc(req.tenant, 'Northline Field Report.pdf', bytes, true),
      ),
    );
});
router.get('/documents/:id', (req, res) =>
  res.json(publicDoc(getDoc(req.tenant, req.params.id))),
);
router.delete('/documents/:id', async (req, res) => {
  await removeDoc(getDoc(req.tenant, req.params.id));
  res.sendStatus(204);
});
router.post('/documents/:id/retry', async (req, res) =>
  res.json(await retry(getDoc(req.tenant, req.params.id))),
);
router.get('/documents/:id/pages/:page', async (req, res) => {
  const result = await preview(
    getDoc(req.tenant, req.params.id),
    Number(req.params.page),
  );
  res.type(result.type).send(result.bytes);
});
router.get('/documents/:id/pages/:page/details', async (req, res) => {
  res.json(
    await details(getDoc(req.tenant, req.params.id), Number(req.params.page)),
  );
});
router.post(
  '/documents/:id/search',
  express.json({ limit: '8kb' }),
  async (req, res) => {
    const query = req.body?.query;
    const mode = req.body?.mode || 'hybrid';
    if (
      typeof query !== 'string' ||
      !query.trim() ||
      query.length > 500 ||
      !['hybrid', 'text', 'visual'].includes(mode)
    )
      throw fault(400, 'Enter a search of up to 500 characters.');
    res.json(
      await search(getDoc(req.tenant, req.params.id), query.trim(), mode),
    );
  },
);
app.use('/workspace-api', router);
app.use('/workspace-api', (_req, res) =>
  res.status(404).json({ error: 'Route not found.' }),
);
app.use(
  express.static(path.join(repo, 'web/out'), {
    index: 'index.html',
    dotfiles: 'deny',
  }),
);
app.use((error, req, res, _next) => {
  const code = error.status || 500;
  if (code >= 500)
    console.error('Workspace request failed', req.method, code, error.name);
  res
    .status(code)
    .json({
      error:
        error.type === 'entity.too.large'
          ? 'This file exceeds the upload limit.'
          : error.status
            ? error.message
            : 'The workspace could not complete that request.',
    });
});
const port = Number(process.env.WORKSPACE_PORT || 3108);
app.listen(port, '127.0.0.1', () =>
  console.log('Folio workspace listening on http://127.0.0.1:' + port),
);
