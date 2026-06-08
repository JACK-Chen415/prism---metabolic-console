import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('log view offers frequent meal shortcuts from existing meal list API', () => {
  const logSource = read('components/views/LogView.tsx');

  for (const required of [
    '最近常吃',
    'MealsAPI.list',
    'start_date: addDays(currentDate, -13)',
    'end_date: currentDate',
    'page_size: 100',
    'buildFrequentMealShortcuts',
    'normalizeRecentMealList',
    "Array.isArray((response as { items?: unknown[] }).items)",
    'mapMeal(rawMeal)',
    'normalizeFrequentMealText(name)',
    'normalizeFrequentMealText(portion)',
    '.sort((a, b) => b.count - a.count || getDateValue(b.latestDate) - getDateValue(a.latestDate))',
    '.slice(0, 6)',
    'fillMealFromShortcut',
    'copyRecentMealIntoAddForm',
    'recentMealHistory',
    'previousMealShortcut',
    'yesterdaySameMealTypeShortcut',
    '复制上一餐',
    '复制昨日同餐',
    '填入后可编辑',
    'setMealInput({',
    'onClick={() => fillMealFromShortcut(shortcut)}',
    'onClick={() => copyRecentMealIntoAddForm(previousMealShortcut)}',
    'onClick={() => copyRecentMealIntoAddForm(yesterdaySameMealTypeShortcut)}',
  ]) {
    assert.ok(logSource.includes(required), `Missing frequent meal shortcut contract: ${required}`);
  }

  const fillStart = logSource.indexOf('const fillMealFromShortcut');
  const fillEnd = logSource.indexOf('const addMeal', fillStart);
  const fillSource = logSource.slice(fillStart, fillEnd);
  for (const field of ['name: shortcut.name', 'portion: shortcut.portion', 'type: shortcut.type', 'category: shortcut.category', 'note: shortcut.note']) {
    assert.ok(fillSource.includes(field), `Shortcut fill should preserve editable field: ${field}`);
  }
  assert.equal(fillSource.includes('setIsAdding(false)'), false, 'Shortcut click should keep add modal open for editing before save');

  const copyStart = logSource.indexOf('const copyRecentMealIntoAddForm');
  const copyEnd = logSource.indexOf('const addMeal', copyStart);
  const copySource = logSource.slice(copyStart, copyEnd);
  for (const field of ['name: meal.name', "portion: meal.portion || '1份'", 'type: meal.type', 'category: meal.category', "note: meal.note || ''"]) {
    assert.ok(copySource.includes(field), `Copy previous/yesterday meal should preserve editable field: ${field}`);
  }
  assert.equal(copySource.includes('setIsAdding(false)'), false, 'Previous/yesterday copy should keep add modal open for editing before save');

  const quickCopyStart = logSource.indexOf('const previousMealShortcut');
  const quickCopyEnd = logSource.indexOf('const changeDate', quickCopyStart);
  const quickCopySource = logSource.slice(quickCopyStart, quickCopyEnd);
  assert.ok(quickCopySource.includes("recentMealHistory.find(meal => meal.name.trim())"), 'Previous meal should use authenticated recent meal history order');
  assert.ok(quickCopySource.includes("meal.recordDate === yesterdayDate && meal.type === mealInput.type"), 'Yesterday shortcut should prefer same meal type');

  const normalizeStart = logSource.indexOf('const normalizeRecentMealList');
  const normalizeEnd = logSource.indexOf('const addDays', normalizeStart);
  const normalizeSource = logSource.slice(normalizeStart, normalizeEnd);
  assert.ok(normalizeSource.includes('Array.isArray(response)'), 'Recent meal shortcuts should accept direct array responses');
  assert.ok(normalizeSource.includes('items?: unknown[]'), 'Recent meal shortcuts should accept paginated { items } responses');
  assert.ok(normalizeSource.includes("'meal_type' in rawMeal"), 'Recent meal shortcuts should detect backend snake_case meal payloads');
  assert.ok(normalizeSource.includes('mapMeal(rawMeal)'), 'Recent meal shortcuts should map backend payloads before grouping');

  const apiSource = read('services/api.ts');
  assert.ok(apiSource.includes('list: (params?: {'), 'Expected existing MealsAPI.list to remain the data source');
});
