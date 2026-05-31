import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

function extractEnumMembers(source, enumName) {
  const enumMatch = source.match(new RegExp(`export\\s+enum\\s+${enumName}\\s*{([\\s\\S]*?)\\n}`));
  assert.ok(enumMatch, `Expected to find enum ${enumName}`);
  return Array.from(enumMatch[1].matchAll(/^\s*([A-Z_]+)\s*=/gm), (match) => match[1]);
}

function extractViewReferences(source) {
  return new Set(Array.from(source.matchAll(/View\.([A-Z_]+)/g), (match) => match[1]));
}

test('every public View enum member has an App render branch', () => {
  const views = extractEnumMembers(read('types.ts'), 'View');
  const appSource = read('App.tsx');
  const internalOnlyViews = new Set(['BILLING', 'ADMIN']);

  const missing = views.filter((view) => {
    if (internalOnlyViews.has(view)) {
      return false;
    }
    const renderBranch = new RegExp(`currentView\\s*===\\s*View\\.${view}\\b`);
    return !renderBranch.test(appSource);
  });

  assert.deepEqual(missing, []);
});

test('navigation shell keeps the primary mobile tabs wired', () => {
  const bottomNavViews = extractViewReferences(read('components/BottomNav.tsx'));
  const shellViews = extractViewReferences(read('components/AppShell.tsx'));

  for (const tabView of ['HOME', 'LOG', 'CAMERA', 'CHAT', 'PROFILE']) {
    assert.ok(bottomNavViews.has(tabView), `Expected BottomNav to expose View.${tabView}`);
  }

  for (const systemView of ['SPLASH', 'LOGIN', 'REGISTER', 'FORGOT_PASSWORD', 'SETTINGS', 'BILLING', 'ADMIN']) {
    assert.ok(shellViews.has(systemView), `Expected AppShell to handle system view View.${systemView}`);
  }
});
