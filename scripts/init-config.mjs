// Create a local gateway / inference key without printing it or changing existing settings.
import { randomBytes } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
const config = new URL('../ai/.env', import.meta.url);
const template = await readFile(new URL('../ai/.env.example', import.meta.url), 'utf8');
const keyLine = /^INTERNAL_API_KEY=[ \t]*\r?$/m;
if (!keyLine.test(template)) throw new Error('Expected an empty key in ai/.env.example');
try {
  await writeFile(config, template.replace(keyLine, 'INTERNAL_API_KEY=' + randomBytes(32).toString('hex')), { flag: 'wx', mode: 0o600 });
  console.log('Created ai/.env with a private service key.');
} catch (e) {
  if (e.code !== 'EEXIST') throw e;
  console.log('Kept existing ai/.env. Both services must use its INTERNAL_API_KEY.');
}
