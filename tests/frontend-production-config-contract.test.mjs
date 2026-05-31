import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('frontend api base url rejects production localhost fallback', () => {
  const apiSource = read('services/api.ts');
  const envSource = read('.env.example');
  const viteEnvSource = read('vite-env.d.ts');

  for (const required of [
    'resolveApiBaseUrl',
    'VITE_APP_ENV',
    '生产前端必须配置 VITE_API_URL',
    '不能指向 localhost',
    'HTTPS 前端必须使用 HTTPS API 地址',
    '同源路径',
  ]) {
    assert.ok(apiSource.includes(required), `Missing frontend production guard contract: ${required}`);
  }

  for (const required of [
    'VITE_API_URL=http://127.0.0.1:8000/api',
    'VITE_APP_ENV=development',
  ]) {
    assert.ok(envSource.includes(required), `Missing env example contract: ${required}`);
  }

  assert.ok(viteEnvSource.includes('VITE_APP_ENV'), 'Missing VITE_APP_ENV type declaration');
});

test('ci runs frontend typecheck before production build', () => {
  const packageJson = JSON.parse(read('package.json'));
  const workflow = read('.github/workflows/ci.yml');

  assert.equal(packageJson.scripts.typecheck, 'tsc --noEmit');
  assert.ok(workflow.includes('npm run typecheck'), 'CI should run frontend typecheck');
  assert.ok(
    workflow.indexOf('npm run typecheck') < workflow.indexOf('npm run build'),
    'typecheck should run before build in CI',
  );
});

test('vite production build keeps heavy dependencies in stable manual chunks', () => {
  const viteConfig = read('vite.config.ts');

  for (const required of [
    'manualChunks',
    'chunkNameFromViewPath',
    "id.includes('node_modules/react')",
    "id.includes('node_modules/marked')",
    "id.includes('node_modules/dompurify')",
    "id.includes('node_modules/dexie')",
    "'/components/views/'",
  ]) {
    assert.ok(viteConfig.includes(required), `Missing production chunk policy: ${required}`);
  }
});

test('backend readiness exposes sanitized config details', () => {
  const mainSource = read('backend/app/main.py');
  const configSource = read('backend/app/core/config.py');

  for (const required of [
    'readiness_snapshot',
    '"config_details": config_details',
    'is_ready = db_status == "ok" and config_status == "ok"',
    'HTTP_503_SERVICE_UNAVAILABLE',
  ]) {
    assert.ok(mainSource.includes(required) || configSource.includes(required), `Missing readiness config contract: ${required}`);
  }

  for (const required of [
    'ai_key_configured',
    'ai_model_configured',
    'otp_provider',
    'billing_provider',
    'mock_billing_provider',
    'cors_origin_count',
    'max_upload_size_mb',
    'max_upload_image_pixels',
  ]) {
    assert.ok(configSource.includes(required), `Missing sanitized readiness field: ${required}`);
  }
});


test('registration consent is enforced beyond the client checkbox', () => {
  const registerSource = read('components/views/RegisterView.tsx');
  const apiSource = read('services/api.ts');
  const schemaSource = read('backend/app/schemas/user.py');
  const modelSource = read('backend/app/models/user.py');
  const migrationSource = read('backend/alembic/versions/20260530_0008_registration_consent.py');

  for (const required of [
    'REGISTRATION_CONSENT_VERSION',
    'terms_accepted',
    'privacy_accepted',
    'ai_use_accepted',
    'health_disclaimer_accepted',
    'consent_version',
  ]) {
    assert.ok(registerSource.includes(required) || apiSource.includes(required), `Missing frontend registration consent contract: ${required}`);
  }

  for (const required of [
    'CONSENT_VERSION',
    'terms_accepted',
    'privacy_accepted',
    'ai_use_accepted',
    'health_disclaimer_accepted',
    'consent_version',
    'consent_accepted_at',
  ]) {
    assert.ok(schemaSource.includes(required) || modelSource.includes(required) || migrationSource.includes(required), `Missing backend registration consent contract: ${required}`);
  }
});

test('deploy config fails closed for production OTP readiness and migrations', () => {
  const dockerfile = read('backend/Dockerfile');
  const compose = read('docker-compose.yml');
  const render = read('render.yaml');
  const workflow = read('.github/workflows/ci.yml');
  const deploy = read('DEPLOY.md');

  for (const required of [
    '/api/ready',
    'raise_for_status()',
    'alembic upgrade head',
  ]) {
    assert.ok(dockerfile.includes(required), `Missing Docker deploy safety contract: ${required}`);
  }

  for (const required of ['APP_ENV', 'production', 'OTP_PROVIDER', 'audit_only']) {
    assert.ok(render.includes(required), `Missing Render production env contract: ${required}`);
    assert.ok(deploy.includes(required), `Missing deploy doc production env contract: ${required}`);
  }

  assert.ok(!render.includes('http://localhost'), 'Render production CORS must not include localhost');
  assert.ok(compose.includes('/api/ready'), 'Compose healthcheck should use readiness');
  assert.ok(workflow.includes('Validate Alembic migration chain'), 'CI should validate Alembic migration chain');
});
