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

test('intake candidate feedback is wired from confirmation sheet to safe backend endpoint', () => {
  const api = normalize(read('services/api.ts'));
  const types = normalize(read('types.ts'));
  const sheet = normalize(read('components/intake/IntakeConfirmationSheet.tsx'));
  const chat = normalize(read('components/views/ChatView.tsx'));
  const backendSchema = normalize(read('backend/app/schemas/intake.py'));
  const backendRoute = normalize(read('backend/app/api/routes/intake.py'));

  for (const required of [
    'IntakeCandidateFeedbackPayload',
    'submitCandidateFeedback',
    '/intake/candidate-feedback',
    'onSubmitCandidateFeedback',
    'submittingFeedbackDraftIds',
    'submittedFeedbackDraftIds',
    '提交纠错',
    'buildCandidateFeedbackPayload',
    'handleSubmitCandidateFeedback',
    'IntakeCandidateFeedbackRequest',
    'INTAKE_CANDIDATE_FEEDBACK_TYPES',
    'intake_candidate_correction_submitted',
    'correction_text_hash',
  ]) {
    assert(
      `${api} ${types} ${sheet} ${chat} ${backendSchema} ${backendRoute}`.includes(required),
      `Candidate feedback contract missing ${required}`,
    );
  }

  for (const allowedType of ['recognition_correction', 'correction', 'knowledge_gap']) {
    assert(backendSchema.includes(allowedType), `Backend schema should allow ${allowedType}`);
  }
});

test('candidate feedback payload and audit path do not include raw candidate content', () => {
  const chatRaw = read('components/views/ChatView.tsx');
  const backendRouteRaw = read('backend/app/api/routes/intake.py');
  const payloadSlice = sliceBetween(chatRaw, 'const buildCandidateFeedbackPayload', 'const handleSubmitCandidateFeedback');
  const metadataSlice = sliceBetween(backendRouteRaw, 'def _safe_intake_candidate_feedback_metadata', 'def _intake_feedback_audit_metadata');
  const auditSlice = sliceBetween(backendRouteRaw, 'def _intake_feedback_audit_metadata', 'def _intake_feedback_response');

  assert.match(payloadSlice, /correction_text:\s*["']用户在候选确认中提交了识别或估算纠错/, 'Payload should use a generic correction marker');
  assert.match(payloadSlice, /risk_tag_count:\s*candidate\.risk_tags\.length/, 'Payload may send only risk tag counts');
  assert.match(payloadSlice, /allergen_tag_count:\s*candidate\.allergen_tags\.length/, 'Payload may send only allergen tag counts');

  for (const forbidden of [
    /food_name/,
    /food_code/,
    /note/,
    /raw_input_text/,
    /raw_summary/,
    /image/,
    /base64/i,
    /ingredients/,
    /seasonings/,
    /cooking_method/,
    /amount_text/,
  ]) {
    assert.doesNotMatch(payloadSlice, forbidden, `Candidate feedback payload must not reference ${forbidden}`);
    assert.doesNotMatch(metadataSlice, forbidden, `Backend metadata allowlist must not reference ${forbidden}`);
    assert.doesNotMatch(auditSlice, forbidden, `Backend audit metadata must not reference ${forbidden}`);
  }

  assert.doesNotMatch(
    backendRouteRaw,
    /correction_text=data\.correction_text|correction_text\s*=\s*data\.correction_text/,
    'Backend must not persist raw client correction text for intake candidates',
  );
  assert.match(backendRouteRaw, /correction_text_hash\s*=\s*hash_sensitive_value\(data\.correction_text\.strip\(\)\)/, 'Backend should hash raw correction text');
});
