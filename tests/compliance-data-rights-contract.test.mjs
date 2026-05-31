import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

function extractStringLiterals(source) {
  return Array.from(source.matchAll(/'([^']+)'/g), (match) => match[1]);
}

function extractComplianceDocumentKeys(source) {
  const typeMatch = source.match(/export type ComplianceDocumentKey =([\s\S]*?);/);
  assert.ok(typeMatch, 'Expected ComplianceDocumentKey union');
  return extractStringLiterals(typeMatch[1]);
}

test('compliance document order covers every declared document key', () => {
  const typesSource = read('types.ts');
  const complianceSource = read('components/views/ComplianceView.tsx');
  const declaredKeys = extractComplianceDocumentKeys(typesSource);
  const orderMatch = complianceSource.match(/COMPLIANCE_DOCUMENT_ORDER[^=]*=\s*\[([\s\S]*?)\];/);
  assert.ok(orderMatch, 'Expected COMPLIANCE_DOCUMENT_ORDER');
  const orderedKeys = extractStringLiterals(orderMatch[1]);

  assert.deepEqual(orderedKeys, declaredKeys);

  for (const key of declaredKeys) {
    assert.match(
      complianceSource,
      new RegExp(`\\n\\s{4}${key}:\\s*{[\\s\\S]*?key:\\s*'${key}'`),
      `Expected COMPLIANCE_DOCUMENTS.${key} to exist and self-identify`,
    );
  }
});

test('health, AI, privacy, and data-rights copy remains visible in compliance docs', () => {
  const complianceSource = read('components/views/ComplianceView.tsx');

  for (const requiredCopy of [
    '不提供医疗诊断',
    '不能替代医生',
    '隐私政策',
    'AI 使用说明',
    '导出数据',
    '删除数据',
    '注销账户',
  ]) {
    assert.ok(complianceSource.includes(requiredCopy), `Missing compliance copy: ${requiredCopy}`);
  }

  assert.match(complianceSource, /\{COMPLIANCE_MEDICAL_DISCLAIMER\}/);
});

test('settings data-rights UI stays wired to account endpoints and local cache cleanup', () => {
  const settingsSource = read('components/views/SettingsView.tsx');
  const apiSource = read('services/api.ts');

  for (const requiredLabel of ['导出个人数据', '删除云端个人内容', '注销账户', '本地离线缓存']) {
    assert.ok(settingsSource.includes(requiredLabel), `Missing settings label: ${requiredLabel}`);
  }

  for (const requiredCall of [
    'AccountAPI.exportData',
    'AccountAPI.deleteData',
    'AccountAPI.deleteAccount',
    'CacheCleanupService.clearUserLocalData',
  ]) {
    assert.ok(settingsSource.includes(requiredCall), `Missing data-rights call: ${requiredCall}`);
  }

  for (const requiredEndpoint of [
    "'/account/export'",
    "'/account/delete-data'",
    "confirm: 'DELETE_DATA'",
    "method: 'DELETE'",
    "confirm: 'DELETE_ACCOUNT'",
  ]) {
    assert.ok(apiSource.includes(requiredEndpoint), `Missing account API contract: ${requiredEndpoint}`);
  }
});


test('account export covers consent subscription and device-session state without token material', () => {
  const accountRouteSource = read('backend/app/api/routes/account.py');

  for (const required of [
    '"account_state"',
    '_export_account_state',
    '"subscription_plan"',
    '"subscription_status"',
    '"consents"',
    '"device_sessions"',
    '_export_device_sessions',
    '_device_session_export_item',
  ]) {
    assert.ok(accountRouteSource.includes(required), `Missing account export contract: ${required}`);
  }

  for (const forbidden of ['refresh_jti_hash', 'user_agent_hash', 'ip_hash', 'password_hash']) {
    const exportItemSource = accountRouteSource.slice(
      accountRouteSource.indexOf('def _device_session_export_item'),
      accountRouteSource.indexOf('async def _export_device_sessions'),
    );
    assert.ok(!exportItemSource.includes(forbidden), `Device session export must not include ${forbidden}`);
  }
});
