import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('settings exposes real assistant preference controls instead of placeholder badges', () => {
  const settingsSource = read('components/views/SettingsView.tsx');
  const sessionStateSource = read('services/sessionState.ts');
  const storageSource = read('constants/storage.ts');

  for (const required of [
    'AI 助手配置',
    '全局助手偏好',
    '干预强度',
    'ASSISTANT_PREF',
    'INTENSITY_SELECT',
    'openAssistantModeModal',
    'openAssistantIntensityModal',
    'setChatMode(mode)',
    'setAssistantIntensity(intensity)',
    'assistantModeLabelMap',
    'assistantIntensityLabelMap',
  ]) {
    assert.ok(settingsSource.includes(required), `Missing assistant preference UI contract: ${required}`);
  }

  for (const required of [
    'export type AssistantIntensity',
    'getAssistantIntensity',
    'setAssistantIntensity',
  ]) {
    assert.ok(sessionStateSource.includes(required), `Missing assistant preference state contract: ${required}`);
  }

  for (const required of [
    'assistantIntensity:',
    'prism.assistant.intensity',
  ]) {
    assert.ok(storageSource.includes(required), `Missing assistant preference storage contract: ${required}`);
  }

  assert.ok(!settingsSource.includes('未开放'), 'Settings should no longer show placeholder badge text for assistant preferences');
});
