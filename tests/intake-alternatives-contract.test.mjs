import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, '..');

function read(relPath) {
  return readFileSync(path.join(projectRoot, relPath), 'utf8');
}

function normalize(source) {
  return source.replace(/\s+/g, ' ');
}

function sliceBetween(source, startNeedle, endNeedle) {
  const start = source.indexOf(startNeedle);
  assert.notEqual(start, -1, `Missing source marker: ${startNeedle}`);
  const end = source.indexOf(endNeedle, start + startNeedle.length);
  assert.notEqual(end, -1, `Missing end marker: ${endNeedle}`);
  return source.slice(start, end);
}

test('intake candidate alternatives are wired as local-rule suggestions', () => {
  const api = normalize(read('services/api.ts'));
  const types = normalize(read('types.ts'));
  const sheet = normalize(read('components/intake/IntakeConfirmationSheet.tsx'));
  const chat = normalize(read('components/views/ChatView.tsx'));
  const backendSchema = normalize(read('backend/app/schemas/intake.py'));
  const backendRoute = normalize(read('backend/app/api/routes/intake.py'));
  const backendService = normalize(read('backend/app/services/intake.py'));
  const matcher = normalize(read('backend/app/services/knowledge/matcher.py'));

  for (const required of [
    'IntakeCandidateAlternative',
    'IntakeCandidateAlternativesRequest',
    'IntakeCandidateAlternativesResponse',
    'suggestCandidateAlternatives',
    '/intake/candidate/alternatives',
    'suggest_candidate_alternatives',
    'list_enabled_foods',
    'onSuggestCandidateAlternatives',
    'alternativeSuggestionsByDraftId',
    'loadingAlternativeDraftIds',
    '替代建议',
    '不作诊断',
    '不会自动替换候选',
  ]) {
    assert(
      `${api} ${types} ${sheet} ${chat} ${backendSchema} ${backendRoute} ${backendService} ${matcher}`.includes(required),
      `Candidate alternatives contract missing ${required}`,
    );
  }
});

test('candidate alternatives stay read-only and do not bypass confirmation', () => {
  const chatRaw = read('components/views/ChatView.tsx');
  const serviceRaw = read('backend/app/services/intake.py');
  const handlerSlice = sliceBetween(chatRaw, 'const handleSuggestCandidateAlternatives', 'const handleReevaluatePendingCandidate');
  const serviceSlice = sliceBetween(serviceRaw, 'async def suggest_candidate_alternatives', 'async def reevaluate_confirm_item');

  assert.match(handlerSlice, /IntakeAPI\.suggestCandidateAlternatives/, 'Chat handler should call the alternatives API');
  assert.doesNotMatch(handlerSlice, /IntakeAPI\.confirm|handleConfirmIntake|onConfirm|markConfirmed/, 'Alternatives handler must not confirm or mark candidates confirmed');
  assert.doesNotMatch(serviceSlice, /\bMeal\s*\(|\.add\(|\.flush\(|\.refresh\(/, 'Alternatives service must not create or persist meals');
  assert.match(serviceSlice, /RecommendationLevel\.RECOMMEND/, 'Alternatives should prefer locally acceptable levels');
  assert.match(serviceSlice, /decision\.hard_blocks/, 'Alternatives should filter local hard blocks');
});
