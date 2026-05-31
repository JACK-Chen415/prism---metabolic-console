import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('admin AI telemetry summarizes sanitized metrics only', () => {
  const apiSource = read('services/api.ts');
  const adminSource = read('components/views/AdminView.tsx');
  const backendAdmin = read('backend/app/api/routes/admin.py');
  const backendChat = read('backend/app/api/routes/chat.py');

  for (const required of [
    'getAITelemetry',
    '/admin/ai/telemetry',
  ]) {
    assert.ok(apiSource.includes(required), `Missing admin AI telemetry API contract: ${required}`);
  }

  for (const required of [
    'AI 监控',
    'AI 调用汇总',
    'cost_status',
    'unconfigured',
    'avg_chat_total_ms',
  ]) {
    assert.ok(adminSource.includes(required), `Missing admin AI telemetry UI contract: ${required}`);
  }

  for (const required of [
    '@router.get("/ai/telemetry"',
    'AITelemetrySummary',
    'admin.ai.telemetry.list',
    '_build_ai_telemetry_summary',
    '_ai_cost_summary',
  ]) {
    assert.ok(backendAdmin.includes(required), `Missing backend AI telemetry contract: ${required}`);
  }

  for (const required of [
    '_chat_telemetry_attachment',
    'estimated_cost_usd',
    'cost_status',
    'local_only',
    'unconfigured',
    'char_based_estimate',
    '_merge_chat_attachments',
  ]) {
    assert.ok(backendChat.includes(required), `Missing chat telemetry persistence contract: ${required}`);
  }
});
