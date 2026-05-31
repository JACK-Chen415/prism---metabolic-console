import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('admin release readiness gate stays wired end to end', () => {
  const apiSource = read('services/api.ts');
  const adminSource = read('components/views/AdminView.tsx');
  const typeSource = read('types.ts');
  const backendAdmin = read('backend/app/api/routes/admin.py');

  for (const required of [
    'getReleaseReadiness',
    '/admin/release/readiness',
    'AdminReleaseReadinessSummary',
    'action_items',
  ]) {
    assert.ok(apiSource.includes(required) || typeSource.includes(required), `Missing readiness API/type contract: ${required}`);
  }

  for (const required of [
    '灰度发布门禁',
    '灰度门禁',
    '阻断项',
    '观察项',
    '同步异常',
    '食物待审',
    '处置优先级',
    'releaseReadinessActionGates',
    'action_items',
    'readinessStatusLabel',
    'gateStatusLabel',
  ]) {
    assert.ok(adminSource.includes(required), `Missing readiness UI contract: ${required}`);
  }

  for (const required of [
    '@router.get("/release/readiness"',
    'ReleaseReadinessSummary',
    'action_items',
    '_build_release_readiness_summary',
    'settings.readiness_snapshot()',
    'config_readiness',
    'config_blocking_count',
    'unsafe_feedback',
    'refresh_reuse',
    'admin.release.readiness.list',
    'sampled_food_items',
    'food_nutrition_unreviewed_count',
    'food_nutrition_missing_provenance_count',
    'food_nutrition_problem_count',
    'food_nutrition_review',
    'sampled_offline_sync_problem_meals',
    'offline_sync_conflict_count',
    'offline_sync_failed_count',
    'offline_sync_problem_count',
    'offline_sync_health',
  ]) {
    assert.ok(backendAdmin.includes(required), `Missing backend readiness contract: ${required}`);
  }

  for (const required of [
    '配置 readiness gate 来自 settings.readiness_snapshot() 的脱敏快照',
    '不包含 API keys、model IDs、数据库凭据或其他 secrets',
    '不返回食物备注、用户输入或健康敏感内容',
    '食物营养来源 gate 只统计来源/质量/审核状态计数',
    '不返回餐名、备注、图片、营养值或客户端原始草稿',
    '离线同步 gate 只统计 FAILED/CONFLICT 状态数量',
  ]) {
    assert.ok(backendAdmin.includes(required), `Missing backend readiness sanitized config note: ${required}`);
  }
});
