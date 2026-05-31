import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('gray release smoke script stays sanitized and documented', () => {
  const script = read('backend/scripts/ai_release_smoke.py');
  const runbook = read('docs/GRAY_RELEASE_RUNBOOK.md');

  for (const required of [
    'SENSITIVE_METADATA_KEYS',
    'sanitize_metadata',
    'hash_identifier',
    'PRISM_API_URL',
    'PRISM_SMOKE_PASSWORD',
    '/auth/register',
    '/chat/sessions',
    '/chat/recognize-food/upload',
    'cost_status',
  ]) {
    assert.ok(script.includes(required), `Missing smoke script contract: ${required}`);
  }

  for (const forbidden of [
    'print(args.password)',
    'print(self.access_token)',
    'print(response.text)',
    'print(payload)',
  ]) {
    assert.equal(script.includes(forbidden), false, `Smoke script must not expose ${forbidden}`);
  }

  for (const required of [
    'ai_release_smoke.py',
    'PRISM_API_URL',
    'PRISM_SMOKE_PASSWORD',
    '不得输出密码、token、验证码、原始聊天内容或图片内容',
  ]) {
    assert.ok(runbook.includes(required), `Missing runbook smoke contract: ${required}`);
  }
});
