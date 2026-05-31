import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('admin knowledge backlog stays wired to sanitized backend and UI contracts', () => {
  const apiSource = read('services/api.ts');
  const adminSource = read('components/views/AdminView.tsx');
  const backendSource = read('backend/app/api/routes/admin.py');
  const typeSource = read('types.ts');

  for (const required of [
    '/admin/knowledge/backlog',
    'getKnowledgeBacklog',
    'AdminKnowledgeBacklogSummary',
  ]) {
    assert.ok(apiSource.includes(required), `Missing admin knowledge backlog API contract: ${required}`);
  }

  for (const required of [
    '知识改进 backlog',
    'knowledgeBacklog',
    'formatCounts',
    'cloud_call_reason_counts',
    'cloud_blocked_reason_counts',
    'unmapped_condition_counts',
    'food_nutrition_source_counts',
    'food_nutrition_quality_counts',
    'food_nutrition_review_status_counts',
    'food_nutrition_unreviewed_count',
    'metadata_keys',
    'rule_settings',
    'recent_items',
    "row.source === 'feedback'",
    "updateFeedbackStatus(row.id, nextStatus)",
    "(['open', 'reviewed', 'closed'] as const)",
    "await loadKnowledgeBacklog()",
  ]) {
    assert.ok(adminSource.includes(required), `Missing admin knowledge backlog UI contract: ${required}`);
  }

  for (const required of [
    '@router.get("/knowledge/backlog"',
    'admin.knowledge.backlog.list',
    '_build_knowledge_backlog_summary',
    'KnowledgeBacklogSummary',
    'knowledge_backlog_feedback_item',
    'knowledge_backlog_audit_item',
    'metadata_keys',
    'unmapped_condition_hashes',
    'cloud_call_reason_code',
    'cloud_blocked_reason_code',
    'food_nutrition_source_counts',
    'food_nutrition_quality_counts',
    'food_nutrition_review_status_counts',
    'food_nutrition_unreviewed_count',
    'reason_',
  ]) {
    assert.ok(backendSource.includes(required), `Missing backend knowledge backlog contract: ${required}`);
  }

  for (const required of [
    'food_nutrition_source_counts',
    'food_nutrition_quality_counts',
    'food_nutrition_review_status_counts',
    'food_nutrition_unreviewed_count',
  ]) {
    assert.ok(typeSource.includes(required), `Missing admin knowledge backlog type contract: ${required}`);
  }

});
