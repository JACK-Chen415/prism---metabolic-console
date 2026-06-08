import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, '..');

function read(relPath) {
  return readFileSync(path.join(projectRoot, relPath), 'utf8');
}

function normalize(source) {
  return source.replace(/\s+/g, ' ');
}

function sliceBetween(source, startNeedle, endNeedle) {
  const start = source.indexOf(startNeedle);
  assert.notEqual(start, -1, `Missing source marker: ${startNeedle}`);
  const end = source.indexOf(endNeedle, start + startNeedle.length);
  assert.notEqual(end, -1, `Missing end marker: ${endNeedle}`);
  return source.slice(start, end);
}

test('intake confirm impact preview is wired from sheet to backend', () => {
  const api = normalize(read('services/api.ts'));
  const types = normalize(read('types.ts'));
  const sheet = normalize(read('components/intake/IntakeConfirmationSheet.tsx'));
  const chat = normalize(read('components/views/ChatView.tsx'));
  const schema = normalize(read('backend/app/schemas/intake.py'));
  const route = normalize(read('backend/app/api/routes/intake.py'));
  const service = normalize(read('backend/app/services/intake.py'));

  for (const required of [
    'IntakeConfirmPreviewRequest',
    'IntakeConfirmPreviewResponse',
    'IntakeConfirmImpactMetric',
    'previewConfirmImpact',
    '/intake/confirm/preview',
    'preview_confirm_impact',
    'confirmImpactPreview',
    'onPreviewConfirmImpact',
    '影响预览',
    '确认前影响预览',
    '不作诊断',
    'will_create_meal',
  ]) {
    assert(
      `${api} ${types} ${sheet} ${chat} ${schema} ${route} ${service}`.includes(required),
      `Confirm impact preview contract missing ${required}`,
    );
  }
});

test('confirm impact preview remains read-only and does not confirm meals', () => {
  const chatRaw = read('components/views/ChatView.tsx');
  const serviceRaw = read('backend/app/services/intake.py');
  const handlerSlice = sliceBetween(chatRaw, 'const handlePreviewConfirmImpact', 'const handleConfirmIntake');
  const serviceSlice = sliceBetween(serviceRaw, 'async def preview_confirm_impact', 'async def confirm');

  assert.match(handlerSlice, /IntakeAPI\.previewConfirmImpact/, 'Preview handler should call preview API');
  assert.doesNotMatch(handlerSlice, /IntakeAPI\.confirm|markConfirmed|onConfirm/, 'Preview handler must not confirm intake');
  assert.doesNotMatch(serviceSlice, /\bMeal\s*\(|\.add\(|\.flush\(|\.refresh\(/, 'Preview service must not create or persist meals');
  assert.match(serviceSlice, /calculate_daily_targets/, 'Preview should use shared target calculation');
  assert.match(serviceSlice, /will_create_meal=False/, 'Preview response should declare it will not create meals');
});
