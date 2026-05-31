import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('admin commercialization summary stays aggregate-only and wired to UI', () => {
  const apiSource = read('services/api.ts');
  const typeSource = read('types.ts');
  const adminSource = read('components/views/AdminView.tsx');
  const backendSource = read('backend/app/api/routes/admin.py');
  const backendTest = read('backend/tests/test_admin_routes.py');

  for (const required of [
    'getCommercializationSummary',
    '/admin/commercialization/summary?window_days=${windowDays}',
    'AdminCommercializationSummary',
    'AdminCommercializationUsagePressureItem',
  ]) {
    assert.ok(apiSource.includes(required) || typeSource.includes(required), `Missing commercial summary API/type contract: ${required}`);
  }

  for (const required of [
    '商业化概览',
    'commercializationSummary',
    'usage_pressure',
    '用量压力',
    '付费活跃',
    '订阅分布',
    '事件类型',
  ]) {
    assert.ok(adminSource.includes(required), `Missing commercial summary UI contract: ${required}`);
  }

  for (const required of [
    '@router.get("/commercialization/summary"',
    'CommercializationSummary',
    '_build_commercialization_summary',
    'admin.commercialization.summary.list',
    'ai_chat_usage_by_user',
    'photo_usage_by_user',
    'PLAN_LIMITS',
    'billing.%',
  ]) {
    assert.ok(backendSource.includes(required), `Missing backend commercial summary contract: ${required}`);
  }

  for (const required of [
    'test_admin_commercialization_summary_aggregates_safe_billing_and_usage_pressure',
    'raw_phone not in payload',
    'raw_chat not in payload',
    'raw_meal_name not in payload',
    'raw_payment_note not in payload',
  ]) {
    assert.ok(backendTest.includes(required), `Missing commercial summary backend test contract: ${required}`);
  }
});
