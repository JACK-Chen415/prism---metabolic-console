import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('chat requests persist assistant preferences through api and history rendering', () => {
  const apiSource = read('services/api.ts');
  const chatViewSource = read('components/views/ChatView.tsx');
  const sessionStateSource = read('services/sessionState.ts');
  const backendSchemaSource = read('backend/app/schemas/chat.py');
  const backendRouteSource = read('backend/app/api/routes/chat.py');
  const backendAiSource = read('backend/app/services/ai_service.py');

  for (const required of [
    'ai_mode: assistantPreferences?.aiMode',
    'intervention_intensity: assistantPreferences?.interventionIntensity',
    'assistantPreferences',
    'ChatPreferencePayload',
  ]) {
    assert.ok(apiSource.includes(required), `Missing chat API preference contract: ${required}`);
  }

  for (const required of [
    'CHAT_PREFERENCE_CHANGED_EVENT',
    'assistantIntensity',
    'ui_preferences',
    'intervention_intensity',
    'buildChatPreferences',
    'aiMode: currentMode',
  ]) {
    assert.ok(chatViewSource.includes(required), `Missing chat view preference contract: ${required}`);
  }

  for (const required of [
    'export const CHAT_PREFERENCE_CHANGED_EVENT',
    'setChatMode(mode:',
    'setAssistantIntensity(intensity:',
  ]) {
    assert.ok(sessionStateSource.includes(required), `Missing chat preference state contract: ${required}`);
  }

  for (const required of [
    'ai_mode',
    'intervention_intensity',
    'normalize_ai_mode',
    'normalize_intervention_intensity',
  ]) {
    assert.ok(backendSchemaSource.includes(required), `Missing backend chat preference schema contract: ${required}`);
  }

  for (const required of [
    '_ui_preferences_payload',
    'assistant_preferences=ui_preferences',
    'ui_preferences',
  ]) {
    assert.ok(backendRouteSource.includes(required), `Missing backend chat preference route contract: ${required}`);
  }

  for (const required of [
    '_assistant_preference_context',
    '用户对话偏好',
    '不改变本地规则',
  ]) {
    assert.ok(backendAiSource.includes(required), `Missing backend assistant preference prompt contract: ${required}`);
  }
});
