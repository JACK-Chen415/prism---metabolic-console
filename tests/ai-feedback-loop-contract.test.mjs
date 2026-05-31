import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('ai feedback loop exposes correction and knowledge-gap entry points safely', () => {
  const chatSource = read('components/views/ChatView.tsx');
  const apiSource = read('services/api.ts');
  const backendRouteSource = read('backend/app/api/routes/chat.py');
  const backendModelSource = read('backend/app/models/feedback.py');
  const backendTestSource = read('backend/tests/test_ai_feedback.py');

  for (const required of [
    'feedbackComposer',
    'openFeedbackComposer',
    'submitComposerFeedback',
    'loadChatSessionMessages',
    'chatHistoryLoadSeqRef',
    'ChatAPI.listMessageFeedback',
    'ensureActiveChatSession',
    'sessionBootstrapPromiseRef',
    'restoredFeedback',
    'runImageRecognitionUpload',
    'recognizeFoodUpload(',
    'signal: uploadController.signal',
    'retryLastImageUpload',
    'serverId: result?.message_id || undefined',
    'recognitionFoods',
    '识别纠错',
    '纠错',
    '补知识',
    'knowledge_gap',
    'recognition_correction',
  ]) {
    assert.ok(chatSource.includes(required), `Missing AI feedback UI contract: ${required}`);
  }

  for (const required of [
    'sendMessageFeedback',
    'correction_text',
    'feedback_type: AIFeedbackType',
    'listMessageFeedback',
    "apiClient.upload('/chat/recognize-food/upload', file, 'file', { prompt, session_id: sessionId }, options)",
  ]) {
    assert.ok(apiSource.includes(required), `Missing AI feedback API contract: ${required}`);
  }

  for (const required of [
    '@router.post(',
    '"/messages/{message_id}/feedback"',
    '@router.get("/messages/{message_id}/feedback"',
    '_safe_feedback_metadata',
    '_feedback_audit_metadata',
    '_FEEDBACK_METADATA_ALLOWLIST',
    '_recognition_message_attachments',
    'query_excerpt="image_upload"',
    'chat_message_id=assistant_message.id if assistant_message else None',
    'message_id=assistant_message.id if assistant_message else None',
    'intensity',
    'ai.feedback.create',
  ]) {
    assert.ok(backendRouteSource.includes(required), `Missing backend feedback route contract: ${required}`);
  }

  for (const required of [
    'RECOGNITION_CORRECTION',
    'KNOWLEDGE_GAP',
    'correction_text_hash',
  ]) {
    assert.ok(backendModelSource.includes(required), `Missing backend feedback model contract: ${required}`);
  }

  for (const required of [
    'test_feedback_metadata_allowlist_removes_raw_sensitive_text',
    'test_feedback_audit_metadata_never_contains_raw_correction_text',
    'test_feedback_tags_are_deduplicated_lowercase_and_bounded',
    'test_recognition_upload_returns_message_id_without_auditing_raw_image',
  ]) {
    assert.ok(backendTestSource.includes(required), `Missing backend feedback test contract: ${required}`);
  }
});
