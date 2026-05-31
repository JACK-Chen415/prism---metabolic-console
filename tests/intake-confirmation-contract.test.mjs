import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('intake confirmation requires low-confidence review and keeps editable prep details', () => {
  const sheetSource = read('components/intake/IntakeConfirmationSheet.tsx');
  const chatSource = read('components/views/ChatView.tsx');
  const backendSchema = read('backend/app/schemas/intake.py');
  const backendService = read('backend/app/services/intake.py');

  for (const required of [
    'LOW_CONFIDENCE_THRESHOLD',
    '低置信度候选',
    '确认核对',
    '主要食材',
    '调料',
    '烹调方式',
    'lowConfidencePending.length > 0',
  ]) {
    assert.ok(sheetSource.includes(required), `Missing intake confirmation UI contract: ${required}`);
  }

  for (const required of ['seasonings', 'ingredients', 'cooking_method']) {
    assert.ok(chatSource.includes(required), `Missing chat candidate mutation contract: ${required}`);
    assert.ok(backendSchema.includes(required), `Missing backend intake schema field: ${required}`);
    assert.ok(backendService.includes(required), `Missing backend intake persistence field: ${required}`);
  }
});
