const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const read = (relativePath) => fs.readFileSync(path.join(__dirname, '..', relativePath), 'utf8');

test('production api base url allows same-origin relative deployments while still rejecting local absolute targets', () => {
  const source = read('services/api.ts');

  assert.match(source, /if \(parsed\.isAbsolute && isLocalHostname\(parsed\.url\.hostname\)\)/);
  assert.match(source, /if \(locationRef\?\.protocol === 'https:' && parsed\.isAbsolute && parsed\.url\.protocol === 'http:'\)/);
  assert.match(source, /if \(isProductionRuntime\) \{[\s\S]*?return apiUrl\.replace\(/);
  assert.ok(source.includes('const apiUrl = configuredApiUrl || LOCAL_API_FALLBACK;'));
});
