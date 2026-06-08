import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('pre-meal simulation uses local knowledge rules without auto-saving meals', () => {
  const logSource = read('components/views/LogView.tsx');
  const apiSource = read('services/api.ts');
  const typesSource = read('types.ts');
  const complianceSource = read('constants/compliance.ts');

  for (const required of [
    '餐前模拟',
    '先做餐前预判',
    '不会自动保存餐食',
    'runPreMealSimulation',
    'KnowledgeAPI.evaluateFood',
    'condition_codes: packagedConditionCodes',
    'manual_restrictions: packagedRestrictionTerms',
    'buildPreMealSwapSuggestions',
    'getPreMealRiskLevel',
    "decision?.recommendation_level === 'AVOID'",
    "decision?.recommendation_level === 'LIMIT'",
    '本地规则提示避开或存在硬性风险时，不要用 AI/个人偏好放宽',
    'COMPLIANCE_MEDICAL_DISCLAIMER',
    '当前输入已变化，请重新餐前预判后再参考结果。',
  ]) {
    assert.ok(logSource.includes(required), `Missing pre-meal simulation contract: ${required}`);
  }

  const simulationStart = logSource.indexOf('const runPreMealSimulation');
  const simulationEnd = logSource.indexOf('const addMeal', simulationStart);
  const simulationSource = logSource.slice(simulationStart, simulationEnd);
  assert.ok(simulationSource.includes('estimateMealNutrition(mealInput)'), 'Pre-meal simulation should include local nutrition estimate');
  assert.ok(simulationSource.includes("food_name: mealInput.name.trim()"), 'Pre-meal simulation should evaluate the intended food name');
  assert.equal(simulationSource.includes('onAddMeal('), false, 'Pre-meal simulation must not save a meal');
  assert.equal(simulationSource.includes('setIsAdding(false)'), false, 'Pre-meal simulation must keep the add modal open for review');

  assert.ok(apiSource.includes('evaluateFood: (payload: EvaluateFoodRequest)'), 'KnowledgeAPI should expose a typed evaluateFood client');
  assert.ok(apiSource.includes("apiClient.post<EvaluateFoodResponse>('/knowledge/evaluate-food', payload)"), 'evaluateFood should call the audited local knowledge endpoint');
  assert.ok(typesSource.includes('export interface EvaluateFoodRequest'), 'EvaluateFoodRequest type should be shared');
  assert.ok(typesSource.includes('export interface EvaluateFoodResponse extends PackagedFoodLocalDecision'), 'EvaluateFoodResponse should reuse local decision fields');
  assert.ok(complianceSource.includes('不提供医疗诊断'), 'Medical disclaimer should preserve non-diagnostic boundary');
});
