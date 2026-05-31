import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('admin security audit filtering stays wired to audited backend endpoints', () => {
  const apiSource = read('services/api.ts');
  const adminSource = read('components/views/AdminView.tsx');
  const backendSource = read('backend/app/api/routes/admin.py');

  for (const required of [
    '/admin/audit/security',
    'listSecurityAudit',
    'event_status',
  ]) {
    assert.ok(apiSource.includes(required) || backendSource.includes(required), `Missing admin security audit contract: ${required}`);
  }

  for (const required of [
    '安全审计筛选',
    'securityQuery',
    'securityStatusFilter',
    'handleSecuritySearch',
    'handleSecurityStatusChange',
    'manage_search',
    '搜索 auth、otp、report、account',
  ]) {
    assert.ok(adminSource.includes(required), `Missing security audit UI contract: ${required}`);
  }

  for (const required of [
    '_build_security_audit_query',
    '@router.get("/audit/security"',
    'event_status: Optional[str] = Query(None',
    'or_(',
    'admin.audit.security.list',
    'q.strip() if q else None',
  ]) {
    assert.ok(backendSource.includes(required), `Missing backend security audit filter contract: ${required}`);
  }
});
