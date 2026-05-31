import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

function assertContainsAll(source, snippets, label) {
  for (const snippet of snippets) {
    assert.ok(source.includes(snippet), `${label} should include ${snippet}`);
  }
}

test('offline meal create payload preserves backend sync field names', () => {
  const offlineSource = read('services/offline.ts');
  const mealCreatesMatch = offlineSource.match(/const mealCreates = pendingMeals[\s\S]*?const mealOperations =/);
  assert.ok(mealCreatesMatch, 'Expected to find mealCreates sync mapping');

  assertContainsAll(
    mealCreatesMatch[0],
    [
      'client_id:',
      'name:',
      'portion:',
      'calories:',
      'sodium:',
      'purine:',
      'protein:',
      'carbs:',
      'fat:',
      'fiber:',
      'meal_type:',
      'category:',
      'record_date:',
      'note:',
      'image_url:',
      'ai_recognized:',
      'source:',
      'source_detail:',
      'confidence:',
      'estimated_fields_json:',
      'rule_warnings_json:',
      'recognition_meta_json:',
    ],
    'mealCreates payload',
  );
});

test('offline update/delete operations and API sync envelope stay compatible', () => {
  const offlineSource = read('services/offline.ts');
  const apiSource = read('services/api.ts');
  const backendModel = read('backend/app/models/meal.py');
  const migration = read('backend/alembic/versions/20260530_0010_meal_sync_failed_status.py');
  const operationsMatch = offlineSource.match(/const mealOperations = pendingMeals[\s\S]*?const mealsToSync =/);
  assert.ok(operationsMatch, 'Expected to find mealOperations sync mapping');

  assertContainsAll(
    operationsMatch[0],
    [
      "op_type: m.pendingDelete ? 'delete' as const : 'update' as const",
      'client_id:',
      'server_id:',
      'changes:',
      'meal_type:',
      'category:',
      'note:',
      'source_detail:',
      'confidence:',
      'estimated_fields_json:',
      'rule_warnings_json:',
      'recognition_meta_json:',
    ],
    'mealOperations payload',
  );

  const syncMethodStart = apiSource.indexOf('sync: (meals: unknown[]');
  assert.notEqual(syncMethodStart, -1, 'Expected MealsAPI.sync to be present');
  const syncMethod = apiSource.slice(syncMethodStart, apiSource.indexOf('};', syncMethodStart));

  assertContainsAll(
    syncMethod,
    [
      "'/meals/sync'",
      '{ meals, operations, last_sync_at: lastSyncAt }',
      'operations: unknown[] = []',
    ],
    'MealsAPI.sync',
  );

  assert.ok(
    offlineSource.includes("import { MealsAPI } from './api';"),
    'offline sync should use a static API import so production builds do not emit mixed import warnings',
  );
  assert.ok(
    !offlineSource.includes("await import('./api')"),
    'offline sync should not dynamically import services/api',
  );

  assertContainsAll(
    offlineSource,
    [
      'synced_count: number;',
      'conflicts: string[];',
      'deleted_client_ids: string[];',
      'server_meals: Array<{',
      'async getQueue',
      'async markRetry',
      'async discardLocal',
      'OfflineMealsService.markConflict',
      'OfflineMealsService.removeByClientId',
      'OfflineMealsService.mergeFromServer',
    ],
    'sync response handling',
  );

  assertContainsAll(
    backendModel,
    [
      'class SyncStatus',
      'FAILED = "FAILED"',
    ],
    'backend sync status model',
  );

  assertContainsAll(
    migration,
    [
      '20260530_0010',
      "ALTER TYPE syncstatus ADD VALUE IF NOT EXISTS 'FAILED'",
    ],
    'backend sync status migration',
  );
});

test('settings exposes offline queue status and safe retry action', () => {
  const settingsSource = read('components/views/SettingsView.tsx');

  assertContainsAll(
    settingsSource,
    [
      '离线同步队列',
      '立即重试',
      'handleRetryOfflineSync',
      'syncScheduler.triggerSync',
      'SyncMetaService.getSyncStatus',
      'SyncMetaService.getLastSyncTime',
      '冲突项会保留在本地',
      'OFFLINE_QUEUE',
      'OfflineMealsService.getQueue',
      'OfflineMealsService.markRetry',
      'OfflineMealsService.discardLocal',
      '日志编辑',
      '本地草稿已丢弃',
    ],
    'offline queue settings surface',
  );
});
