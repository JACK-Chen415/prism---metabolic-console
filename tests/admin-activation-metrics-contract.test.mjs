import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('admin activation metrics stay wired as sanitized gray-release aggregates', () => {
  const apiSource = read('services/api.ts');
  const typeSource = read('types.ts');
  const adminSource = read('components/views/AdminView.tsx');
  const backendSource = read('backend/app/api/routes/admin.py');
  const backendTest = read('backend/tests/test_admin_routes.py');

  for (const required of [
    'getActivationMetrics',
    '/admin/activation/metrics?window_days=${windowDays}',
    'AdminActivationMetricsSummary',
  ]) {
    assert.ok(apiSource.includes(required) || typeSource.includes(required), `Missing activation metrics API/type contract: ${required}`);
  }

  for (const required of [
    '激活指标',
    '灰度激活指标',
    'activationDailyMax',
    'daily_activity',
    '记餐用户',
    '付费活跃',
  ]) {
    assert.ok(adminSource.includes(required), `Missing activation metrics UI contract: ${required}`);
  }

  for (const required of [
    '@router.get("/activation/metrics"',
    'ActivationMetricsSummary',
    '_build_activation_metrics_summary',
    'admin.activation.metrics.list',
    '仅展示聚合计数',
    'Meal.created_at >= start_at',
    'HealthMetric.created_at >= start_at',
  ]) {
    assert.ok(backendSource.includes(required), `Missing backend activation metrics contract: ${required}`);
  }

  for (const required of [
    'test_admin_activation_metrics_summary_aggregates_without_sensitive_content',
    'raw_phone not in serialized',
    'raw_chat not in serialized',
    'raw_correction not in serialized',
  ]) {
    assert.ok(backendTest.includes(required), `Missing activation metrics backend test contract: ${required}`);
  }
});
