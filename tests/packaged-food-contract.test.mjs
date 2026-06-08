import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (filePath) => readFileSync(resolve(repoRoot, filePath), 'utf8');

test('packaged-food lookup UI stays wired to knowledge APIs and compliance copy', () => {
  const typesSource = read('types.ts');
  const apiSource = read('services/api.ts');
  const logViewSource = read('components/views/LogView.tsx');
  const appSource = read('App.tsx');
  const complianceSource = read('constants/compliance.ts');

  for (const requiredType of [
    'export type PackagedFoodCategory',
    'export type PackagedFoodProviderStatus',
    'export interface PackagedFoodCandidateResponse',
    'export interface PackagedFoodLookupResponse',
    'export interface PackagedFoodLabelNormalizeRequest',
  ]) {
    assert.ok(typesSource.includes(requiredType), `Missing packaged-food type contract: ${requiredType}`);
  }

  for (const requiredApi of [
    'export const KnowledgeAPI = {',
    'lookupPackagedFoodBarcode',
    'normalizePackagedFoodLabel',
    '/knowledge/packaged-food/barcode',
    '/knowledge/packaged-food/label',
  ]) {
    assert.ok(apiSource.includes(requiredApi), `Missing packaged-food API contract: ${requiredApi}`);
  }

  for (const requiredUi of [
    '包装食品复核',
    '条码查询',
    '手动营养标签',
    '本地规则复核',
    '灰度入口',
    'PACKAGED_FOOD_DISCLAIMER',
  ]) {
    assert.ok(logViewSource.includes(requiredUi), `Missing packaged-food UI contract: ${requiredUi}`);
  }

  assert.ok(appSource.includes('medicalConditions={medicalConditions}'), 'LogView should receive medicalConditions for local rule review');
  assert.ok(complianceSource.includes('PACKAGED_FOOD_DISCLAIMER'), 'Packaged-food disclaimer should live in shared compliance constants');
});
