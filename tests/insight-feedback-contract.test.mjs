import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('smart insight feedback is wired from home UI to audited backend storage', () => {
  const apiSource = read('services/api.ts');
  const homeSource = read('components/views/HomeView.tsx');
  const backendSource = read('backend/app/api/routes/insights.py');
  const feedbackModel = read('backend/app/models/feedback.py');
  const migration = read('backend/alembic/versions/20260530_0009_ai_feedback_app_messages.py');
  const backendTest = read('backend/tests/test_insights_feedback.py');

  for (const required of [
    'sendFeedback',
    'listFeedback',
    '/insights/${messageId}/feedback',
    'InsightFeedbackPayload',
  ]) {
    assert.ok(apiSource.includes(required), `Missing insight feedback API contract: ${required}`);
  }

  for (const required of [
    'INSIGHT_FEEDBACK_CHOICES',
    'submitInsightFeedback',
    'InsightsAPI.sendFeedback',
    'InsightsAPI.listFeedback',
    '有用',
    '没用',
    '补充',
    '已记录',
  ]) {
    assert.ok(homeSource.includes(required), `Missing home insight feedback UI contract: ${required}`);
  }

  for (const required of [
    '@router.post("/{message_id}/feedback"',
    '@router.get("/{message_id}/feedback"',
    'insight.feedback.create',
    '_safe_insight_feedback_metadata',
    '_insight_feedback_audit_metadata',
    'SMART_INSIGHT_ATTRIBUTION_PREFIX',
  ]) {
    assert.ok(backendSource.includes(required), `Missing backend insight feedback route contract: ${required}`);
  }

  for (const required of [
    'app_message_id',
    'ForeignKey("app_messages.id"',
  ]) {
    assert.ok(feedbackModel.includes(required), `Missing feedback model insight link: ${required}`);
  }

  for (const required of [
    '20260530_0009',
    'ix_ai_feedback_app_message_id',
    'fk_ai_feedback_app_message_id_app_messages',
  ]) {
    assert.ok(migration.includes(required), `Missing migration contract: ${required}`);
  }

  for (const required of [
    'test_create_insight_feedback_links_app_message_without_raw_audit_text',
    'test_create_insight_feedback_rejects_non_smart_messages',
    'test_list_insight_feedback_returns_current_user_app_message_feedback',
  ]) {
    assert.ok(backendTest.includes(required), `Missing backend insight feedback test: ${required}`);
  }
});
