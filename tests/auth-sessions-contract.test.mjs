import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

function assertContainsAll(source, snippets, label) {
  for (const snippet of snippets) {
    assert.ok(source.includes(snippet), `${label} should include ${snippet}`);
  }
}

test('device session management stays wired from settings to audited backend routes', () => {
  const apiSource = read('services/api.ts');
  const settingsSource = read('components/views/SettingsView.tsx');
  const typeSource = read('types.ts');
  const backendAuthSource = read('backend/app/api/routes/auth.py');
  const backendSchemaSource = read('backend/app/schemas/user.py');

  assertContainsAll(
    typeSource,
    [
      'export interface DeviceSessionItem',
      'session_id: string;',
      'is_current: boolean;',
      'is_revoked: boolean;',
      'last_seen_at: string;',
    ],
    'device session type',
  );

  assertContainsAll(
    apiSource,
    [
      'listSessions',
      "apiClient.get<DeviceSessionItem[]>('/auth/sessions')",
      'revokeSession',
      '`/auth/sessions/${sessionId}`',
      "method: 'DELETE'",
      "confirm: 'REVOKE_SESSION'",
    ],
    'auth session API client',
  );

  assertContainsAll(
    settingsSource,
    [
      '登录设备',
      'AuthAPI.listSessions',
      'AuthAPI.revokeSession',
      'DeviceSessionItem',
      '当前设备',
      '已撤销',
      '撤销会话',
      '这台设备将需要重新登录',
    ],
    'settings device session UI',
  );

  assertContainsAll(
    backendAuthSource,
    [
      '@router.get("/sessions"',
      '@router.delete("/sessions/{session_id}"',
      'DeviceSessionResponse',
      'RevokeSessionRequest',
      'auth.session.list',
      'auth.session.revoke',
      '请使用退出登录关闭当前会话',
    ],
    'backend auth session routes',
  );

  assertContainsAll(
    backendSchemaSource,
    [
      'class RevokeSessionRequest',
      'REVOKE_SESSION',
      'class DeviceSessionResponse',
      'is_current',
      'is_revoked',
    ],
    'backend auth session schemas',
  );
});
