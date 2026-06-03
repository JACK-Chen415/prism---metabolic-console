import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('frontend auth client keeps refresh tokens in httpOnly cookies only', () => {
  const apiSource = read('services/api.ts');
  const loginSource = read('components/views/LoginView.tsx');
  const registerSource = read('components/views/RegisterView.tsx');
  const refreshFetch = apiSource.slice(
    apiSource.indexOf("fetch(`${this.baseUrl}/auth/refresh`"),
    apiSource.indexOf('});', apiSource.indexOf("fetch(`${this.baseUrl}/auth/refresh`")) + 3,
  );
  const logoutClient = apiSource.slice(
    apiSource.indexOf('logout: async () =>'),
    apiSource.indexOf('getProfile:', apiSource.indexOf('logout: async () =>')),
  );

  for (const required of [
    "credentials: 'include'",
    "fetch(`${this.baseUrl}/auth/refresh`",
    'TokenManager.setTokens(data.access_token);',
    "fetch(`${API_BASE_URL}/auth/logout`",
    "'X-Prism-Client': 'web'",
  ]) {
    assert.ok(apiSource.includes(required), `Missing auth cookie contract: ${required}`);
  }

  assert.ok(
    refreshFetch.includes('headers: AUTH_MUTATION_CLIENT_HEADERS'),
    'Refresh request must include the auth mutation client header',
  );
  assert.ok(
    logoutClient.includes('...AUTH_MUTATION_CLIENT_HEADERS'),
    'Logout request must include the auth mutation client header',
  );

  for (const forbidden of [
    'getRefreshToken',
    'AUTH_STORAGE_KEYS.refreshToken',
    'localStorage.getItem(AUTH_STORAGE_KEYS.refreshToken)',
    'localStorage.setItem(AUTH_STORAGE_KEYS.refreshToken',
    'localStorage.removeItem(AUTH_STORAGE_KEYS.refreshToken',
    'prism_refresh_token',
    'body: JSON.stringify({ refresh_token:',
    'response.tokens.refresh_token',
  ]) {
    assert.equal(apiSource.includes(forbidden), false, `Auth API must not expose refresh token via ${forbidden}`);
    assert.equal(loginSource.includes(forbidden), false, `Login view must not expose refresh token via ${forbidden}`);
    assert.equal(registerSource.includes(forbidden), false, `Register view must not expose refresh token via ${forbidden}`);
  }

  assert.ok(
    loginSource.includes('TokenManager.setTokens(response.tokens.access_token);'),
    'Login view should save only the access token',
  );
  assert.ok(
    registerSource.includes('TokenManager.setTokens(response.tokens.access_token);'),
    'Register view should save only the access token',
  );
});
