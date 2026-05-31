import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('admin knowledge audit filtering stays wired to structured backend filters', () => {
  const apiSource = read('services/api.ts');
  const adminSource = read('components/views/AdminView.tsx');
  const backendSource = read('backend/app/api/routes/admin.py');

  for (const required of [
    '/admin/audit/knowledge',
    'listKnowledgeAudit',
    'fallback_status',
  ]) {
    assert.ok(apiSource.includes(required) || backendSource.includes(required), `Missing admin knowledge audit contract: ${required}`);
  }

  for (const required of [
    '知识审计筛选',
    'knowledgeQuery',
    'knowledgeFallbackFilter',
    'knowledgeCloudFilter',
    'handleKnowledgeSearch',
    'handleKnowledgeFallbackChange',
    'handleKnowledgeCloudChange',
    'travel_explore',
    '本地完整',
    '已调用云端',
    '本地阻断',
  ]) {
    assert.ok(adminSource.includes(required), `Missing knowledge audit UI contract: ${required}`);
  }

  for (const required of [
    '_build_knowledge_audit_query',
    '@router.get("/audit/knowledge"',
    'origin: Optional[KnowledgeOrigin] = Query(None',
    'fallback_status: Optional[FallbackStatus] = Query(None',
    'called_cloud: Optional[bool] = Query(None',
    'admin.audit.knowledge.list',
    'cloud_call_reason.ilike',
    'cloud_blocked_reason.ilike',
  ]) {
    assert.ok(backendSource.includes(required), `Missing backend knowledge audit filter contract: ${required}`);
  }
});
