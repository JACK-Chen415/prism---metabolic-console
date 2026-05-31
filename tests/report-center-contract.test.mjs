import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('report center renders targets, insights, and export contracts', () => {
  const typeSource = read('types.ts');
  const reportView = read('components/views/ReportsView.tsx');
  const reportsRoute = read('backend/app/api/routes/reports.py');
  const apiSource = read('services/api.ts');

  for (const required of [
    'export interface MetabolicReportTargets',
    'export interface MetabolicReportInsight',
    'latest_insights: MetabolicReportInsight[]',
    'csv_endpoint: string',
  ]) {
    assert.ok(typeSource.includes(required), `Missing report type contract: ${required}`);
  }

  for (const required of [
    '目标对照',
    '周期洞察',
    'latestInsights.slice(0, 5)',
    'formatDateTime(report.generated_at)',
    'report.summary.targets.recommended_calorie_target',
    'report.summary.targets.sodium',
    'report.summary.targets.purine',
  ]) {
    assert.ok(reportView.includes(required), `Missing report page surface: ${required}`);
  }

  for (const required of [
    'latest_insights=_insight_payload(insights)',
    'medical_disclaimer=MEDICAL_DISCLAIMER',
    '@router.get("/weekly.csv")',
    '@router.get("/monthly.csv")',
  ]) {
    assert.ok(reportsRoute.includes(required), `Missing backend report export contract: ${required}`);
  }

  for (const required of [
    'getWeeklyCsv',
    'getMonthlyCsv',
    '/reports/weekly.csv',
    '/reports/monthly.csv',
  ]) {
    assert.ok(apiSource.includes(required), `Missing frontend report API contract: ${required}`);
  }
});
