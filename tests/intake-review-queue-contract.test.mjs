import assert from 'node:assert/strict';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, '..');
const ignoredDirs = new Set([
  '.git',
  '.next',
  '.pytest_cache',
  '.venv',
  '__pycache__',
  'build',
  'coverage',
  'dist',
  'node_modules',
]);

function normalizeSource(source) {
  return source.replace(/\s+/g, ' ');
}

function walkFiles(dir) {
  if (!existsSync(dir)) return [];

  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch (error) {
    if (error?.code === 'EACCES' || error?.code === 'EPERM') return [];
    throw error;
  }

  return entries.flatMap((entry) => {
    const fullPath = path.join(dir, entry.name);

    if (entry.isDirectory()) {
      return ignoredDirs.has(entry.name) || entry.name.startsWith('pytest-cache-files-') ? [] : walkFiles(fullPath);
    }

    return entry.isFile() ? [fullPath] : [];
  });
}

const sourceFiles = walkFiles(projectRoot).filter((filePath) =>
  /\.(c|m)?(t|j)sx?$/.test(filePath),
);

function readRequiredSource({ basename, includes = [] }) {
  const matches = sourceFiles.filter((filePath) => {
    if (path.basename(filePath) !== basename) return false;

    const source = readFileSync(filePath, 'utf8');
    return includes.every((needle) => source.includes(needle));
  });

  assert.equal(
    matches.length,
    1,
    `Expected exactly one ${basename} containing ${includes.join(', ') || 'source'}, found ${
      matches.length
    }: ${matches.map((filePath) => path.relative(projectRoot, filePath)).join(', ')}`,
  );

  return {
    path: matches[0],
    raw: readFileSync(matches[0], 'utf8'),
    source: normalizeSource(readFileSync(matches[0], 'utf8')),
  };
}

function assertAll(source, needles, context) {
  for (const needle of needles) {
    assert.match(source, needle, `${context} should contain ${needle}`);
  }
}

function assertAny(source, needles, context) {
  assert(
    needles.some((needle) => {
      if (typeof needle === 'string') return source.includes(needle);
      return needle.test(source);
    }),
    `${context} should contain one of: ${needles.map(String).join(', ')}`,
  );
}

function assertNoConfirmNearReviewRestore(chatRaw) {
  const restoreMarkers = [
    'markInReview',
    '继续复核',
    '候选复核台',
    '待复核候选',
    'PENDING_REVIEW',
    'IN_REVIEW',
  ];
  const markerIndex = restoreMarkers
    .map((marker) => chatRaw.indexOf(marker))
    .filter((index) => index >= 0)
    .sort((a, b) => a - b)[0];

  assert.notEqual(markerIndex, undefined, 'ChatView should expose a review restore flow');

  const restoreSlice = chatRaw.slice(markerIndex, markerIndex + 2200);
  assert.doesNotMatch(
    restoreSlice,
    /IntakeAPI\s*\.\s*confirm|\.confirm\s*\(/,
    'Restoring an intake draft for review must not directly confirm it',
  );
}

test('offline intake draft queue persists review candidates with user isolation', () => {
  const offline = readRequiredSource({
    basename: 'offline.ts',
    includes: ['IntakeDraftQueueService'],
  });

  assertAll(
    offline.source,
    [
      /\bCachedIntakeDraft\b/,
      /\bIntakeDraftQueueService\b/,
      /\bintakeDrafts\b/,
      /\bPENDING_REVIEW\b/,
      /\bIN_REVIEW\b/,
      /\bCONFIRMED\b/,
      /\bDISCARDED\b/,
      /\bgetQueue\b/,
      /\bsaveDraft\b/,
      /\bmarkInReview\b/,
      /\bmarkConfirmed\b/,
      /\bdiscard\b/,
    ],
    'offline intake draft queue service',
  );

  assertAny(
    offline.source,
    [
      /\[userId[+\],]/,
      /userId[+,][^'"]*status/,
      /status[+,][^'"]*userId/,
      /where\(\s*['"]userId['"]\s*\)/,
      /where\(\s*\{\s*userId\b/,
    ],
    'offline intake draft queue storage contract',
  );
});

test('ChatView exposes a review queue entry and restores drafts without auto-confirming', () => {
  const chat = readRequiredSource({
    basename: 'ChatView.tsx',
    includes: ['IntakeDraftQueueService'],
  });

  assertAny(
    chat.source,
    ['待复核候选', '候选复核台'],
    'ChatView review queue entry copy',
  );
  assertAny(chat.source, ['继续复核', /markInReview\b/], 'ChatView resume review action');
  assertAny(chat.source, ['丢弃', /discard\b/], 'ChatView discard action');
  assert.match(
    chat.source,
    /\bIntakeConfirmationSheet\b/,
    'Restored draft should still use IntakeConfirmationSheet',
  );
  assertAny(
    chat.source,
    [/setPending[A-Za-z]*(Session|Intake|Confirmation|Draft)?\b/, /\bpending[A-Za-z]*Session\b/],
    'Restoring from the queue should only set a pending session before confirmation',
  );
  assertAll(
    chat.source,
    [
      /\bgetQueue\b/,
      /\bsaveDraft\b/,
      /\bmarkInReview\b/,
      /\bmarkConfirmed\b/,
      /\bdiscard\b/,
    ],
    'ChatView queue service integration',
  );
  assertNoConfirmNearReviewRestore(chat.raw);
  assertAny(
    chat.source,
    [/stop/i, /stopPropagation\b/, /aria-label=["'][^"']*丢弃/, /title=["'][^"']*丢弃/, /discard\b/],
    'Discard should be an independent queue action',
  );
  assertAny(
    chat.source,
    [
      /低置信度.*复核/,
      /风险候选.*复核/,
      /不自动写入日志/,
      /不会自动写入日志/,
    ],
    'ChatView safety copy',
  );
  assertAll(
    chat.source,
    [
      /\bintakeDraftQueueMetrics\b/,
      /本地复核指标/,
      /仅保存在本机/,
      /当前复核/,
      /高风险/,
      /AVOID/,
      /拍照\/语音/,
      /sourceCounts/,
      /\bIntakeReviewFilter\b/,
      /\bintakeReviewFilterOptions\b/,
      /\bprioritizedIntakeDraftQueue\b/,
      /当前筛选下没有待复核候选/,
    ],
    'ChatView local review metrics and filters',
  );
  assert.doesNotMatch(
    chat.source,
    /intakeDraftQueue\.slice\(0,\s*6\)/,
    'ChatView review desk should not hide drafts behind a fixed six-item slice',
  );
});

test('settings and cleanup surfaces include pending intake draft review risk counts', () => {
  const settings = readRequiredSource({
    basename: 'SettingsView.tsx',
    includes: ['intakeDraftCount'],
  });
  const cacheCleanup = readRequiredSource({
    basename: 'offline.ts',
    includes: ['CacheCleanupService'],
  });
  const combined = `${settings.source} ${cacheCleanup.source}`;

  assertAll(
    combined,
    [/\bintakeDraftCount\b/, /\bpendingReviewCount\b/, /\bIntakeDraftQueueService\b/],
    'local data cleanup summary',
  );
  assertAny(
    combined,
    [
      /待复核候选/,
      /候选复核台/,
      /低置信度/,
      /风险候选/,
      /不自动写入日志/,
      /退出前/,
    ],
    'settings and cleanup risk messaging',
  );
  assertAll(
    settings.source,
    [
      /候选复核/,
      /去复核台/,
      /丢弃候选/,
      /食物名、备注和健康文本仍留在本机候选草稿内/,
    ],
    'settings review desk entry',
  );
  const settingsReviewIndex = settings.raw.indexOf('候选复核');
  assert.notEqual(settingsReviewIndex, -1, 'Settings should expose a candidate review section');
  const settingsReviewSlice = settings.raw.slice(settingsReviewIndex, settingsReviewIndex + 4200);
  assert.doesNotMatch(
    settingsReviewSlice,
    /session\.candidates|food_name|raw_input_text|raw_summary|\bnote\b|image|base64/i,
    'Settings review desk summary must not render raw candidate/session/image fields',
  );
});
