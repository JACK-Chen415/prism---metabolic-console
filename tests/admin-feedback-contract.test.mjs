import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('admin feedback triage stays wired to audited backend endpoints', () => {
  const apiSource = read('services/api.ts');
  const adminSource = read('components/views/AdminView.tsx');
  const backendSource = read('backend/app/api/routes/admin.py');

  for (const required of [
    '/admin/feedback',
    '/admin/feedback/${feedbackId}/status',
    'listFeedback',
    'feedback_type',
    'updateFeedbackStatus',
  ]) {
    assert.ok(apiSource.includes(required), `Missing admin API contract: ${required}`);
  }

  for (const required of [
    '反馈闭环',
    '反馈筛选',
    'feedbackFilter',
    'feedbackTypeFilter',
    'handleFeedbackFilterChange',
    'handleFeedbackTypeChange',
    "nextFilter === 'all' ? undefined : nextFilter",
    '只看未处理',
    '当前筛选下暂无反馈项',
    'updateFeedbackStatus',
    'requiresUnsafeReviewBeforeClose',
    '先审阅后关闭',
    '洞察：',
    'metadata key：',
    'metadata_keys',
    "'open'",
    "'reviewed'",
    "'closed'",
  ]) {
    assert.ok(adminSource.includes(required), `Missing admin feedback UI contract: ${required}`);
  }

  for (const required of [
    '@router.get("/feedback"',
    '@router.patch("/feedback/{feedback_id}/status"',
    'admin.feedback.status_update',
    'correction_text_hash',
    'metadata_keys',
    'metadata_json=None',
    'app_message_id',
    '_build_feedback_query',
    'feedback_type: Optional[AIFeedbackType]',
    '_feedback_status_transition_rejection',
    'unsafe_requires_review_before_close',
    'event_status="rejected"',
  ]) {
    assert.ok(backendSource.includes(required), `Missing backend feedback triage contract: ${required}`);
  }
});
