import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('health metrics provider boundary is enforced safely', () => {
  const apiSource = read('services/api.ts');
  const viewSource = read('components/views/HealthMetricsView.tsx');
  const routeSource = read('backend/app/api/routes/health_metrics.py');
  const providerSource = read('backend/app/services/health_metric_providers.py');
  const schemaSource = read('backend/app/schemas/health_metric.py');

  for (const required of [
    'listProviders',
    '/health-metrics/providers',
  ]) {
    assert.ok(apiSource.includes(required), `Missing health metric provider API contract: ${required}`);
  }

  for (const required of [
    '设备预留',
    'supports_import',
    'supports_realtime',
    'supports_history',
  ]) {
    assert.ok(viewSource.includes(required), `Missing health metric provider UI contract: ${required}`);
  }

  for (const required of [
    '@router.get("/providers"',
    'HealthMetricProviderResponse',
    'health_metric_provider_registry.list_providers()',
    'resolve_manual_create',
    'HTTPException(status_code=status.HTTP_400_BAD_REQUEST',
  ]) {
    assert.ok(routeSource.includes(required), `Missing health metric provider backend route: ${required}`);
  }

  for (const required of [
    'mock_device',
    'vendor_device',
    'HealthMetricProviderRegistry',
    'manual_create_allowed',
    'allowed_sources',
    'normalize_health_metric_provider',
  ]) {
    assert.ok(providerSource.includes(required), `Missing provider abstraction contract: ${required}`);
  }

  for (const required of [
    'ConfigDict(extra="forbid")',
    'class HealthMetricUpdate',
  ]) {
    assert.ok(schemaSource.includes(required), `Missing health metric schema contract: ${required}`);
  }
});
