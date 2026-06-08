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

test('intake review telemetry is wired as aggregate-only client API', () => {
  const api = normalize(read('services/api.ts'));
  const types = normalize(read('types.ts'));
  const offline = normalize(read('services/offline.ts'));
  const settings = normalize(read('components/views/SettingsView.tsx'));

  assert.match(api, /submitReviewTelemetry\b/, 'IntakeAPI should expose telemetry submission');
  assert.match(api, /\/intake\/review-telemetry/, 'Telemetry endpoint path should be wired');
  assert.match(types, /IntakeReviewTelemetryPayload/, 'Telemetry payload type should exist');
  assert.match(types, /source_counts: Record<string, number>/, 'Payload should use source count distribution');
  assert.match(types, /status_counts: Record<string, number>/, 'Payload should use status count distribution');

  for (const required of [
    'hardBlockDraftCount',
    'intakeDraftSourceCounts',
    'intakeDraftStatusCounts',
    'submitReviewTelemetry',
    '同步复核指标',
    '仅上传聚合计数',
  ]) {
    assert(
      `${offline} ${settings} ${api}`.includes(required),
      `Aggregate telemetry contract missing ${required}`,
    );
  }

  const handlerIndex = settings.indexOf('handleSubmitReviewTelemetry');
  assert.notEqual(handlerIndex, -1, 'Settings should have a telemetry submit handler');
  const handlerSlice = settings.slice(handlerIndex, handlerIndex + 2200);
  assert.doesNotMatch(
    handlerSlice,
    /session\.candidates|food_name|raw_input_text|raw_summary|note|image|base64/i,
    'Telemetry submit handler must not read raw candidate/session/image fields',
  );
});

test('admin readiness and activation expose intake review aggregate signals', () => {
  const backendAdmin = normalize(read('backend/app/api/routes/admin.py'));
  const adminView = normalize(read('components/views/AdminView.tsx'));
  const types = normalize(read('types.ts'));

  for (const required of [
    'IntakeReviewTelemetryAggregate',
    'intake_review_telemetry',
    'intake_review_backlog',
    'intake_review_backlog_count',
    '候选复核待处理',
    '复核积压',
    'AdminIntakeReviewTelemetryAggregate',
  ]) {
    assert(
      `${backendAdmin} ${adminView} ${types}`.includes(required),
      `Admin telemetry contract missing ${required}`,
    );
  }

  assert.doesNotMatch(
    backendAdmin,
    /food_name|raw_input_text|raw_summary|image_base64/,
    'Admin intake review telemetry path should not mention raw intake fields',
  );
});
