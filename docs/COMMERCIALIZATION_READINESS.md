# Prism Commercialization Readiness Notes

_Last updated: 2026-06-09_

This note tracks the current engineering state for controlled internal testing, small gray release, and commercialization foundation work.

## Recently Completed Baseline

- Authentication security now separates dev/prod OTP behavior, uses provider abstraction, rate limits, failure lockout, and audit logging. Password login also uses sanitized audit-log counters for temporary actor-hash lockout after repeated failures, without storing passwords, tokens, or raw phone numbers.
- Refresh tokens use device sessions with `sid`/`jti` and support current-session revocation on logout.
- JWT settings now normalize to reviewed HMAC algorithms and production startup rejects non-positive or over-long access/refresh token lifetimes above the gray-release caps.
- Settings now lists device sessions and lets users revoke any non-current session from the UI, with backend audit logging on list and revoke actions.
- Production startup guardrails reject default secrets, unsafe CORS, dev OTP provider, and unsafe database URLs.
- Production startup guardrails also reject placeholder `ARK_API_KEY` and `DOUBAO_MODEL` values so gray-release AI calls cannot boot with sample config.
- Production startup guardrails now also fail closed when upload size or image-pixel limits exceed the reviewed gray-release budget, and readiness reports `upload_limits_exceed_reviewed_cap` as a sanitized warning outside production.
- Frontend API base URL now refuses localhost fallback in production-like runtime and requires an explicit `VITE_API_URL`.
- Frontend CI now runs contract tests, `tsc --noEmit`, and production build before backend tests.
- Frontend test coverage now includes a Vite SSR runtime smoke for the app shell, registration compliance entries, and compliance document rendering, in addition to source-level contract checks.
- CI now provisions PostgreSQL and runs `alembic upgrade head` as a migration smoke test before backend pytest, so new security/session/data-rights tables are deploy-gated.
- Frontend production build now splits React, markdown/storage libraries, and view modules into stable chunks, clearing prior Vite chunk and mixed-import warnings.
- Compliance documents are available in the app: user terms, privacy policy, AI usage notes, health disclaimer, and data rights.
- AI chat and intake candidates pass through local knowledge review so allergies, explicit avoid rules, and AVOID/LIMIT decisions cannot be relaxed by LLM output.
- Natural-language allergy phrases now normalize to canonical local tags for shellfish/shrimp, peanut, dairy, egg, wheat/gluten, soy, sesame, fish/seafood, and hard-block reasons avoid echoing the raw allergy phrase.
- Image uploads are validated by MIME, file header, byte size, and pixel budget, then stripped of EXIF and re-encoded before model submission. Multi-frame or animated images are rejected so the gray-release intake path does not quietly admit animated payloads.
- User data export, data deletion, and account deletion are implemented with user-scoped authorization, security audit logs, request-traceable export manifests, explicit account/subscription/consent state, and safe device-session export that omits token, jti, UA, and IP hash material.
- Request IDs, structured HTTP logs, DB readiness checks, sanitized config readiness snapshots, baseline API security response headers, and AI timing plus configurable cost-estimation telemetry are in place.
- Security audit metadata now has a helper-level redaction pass for sensitive keys, long raw text, tokens, API keys, OTPs, images, and raw content before `security_audit_logs.metadata_json` is written.
- AI cloud error handling now returns category-level, sanitized failure messages and logs only structured error types instead of upstream raw exception bodies, model IDs, endpoint IDs, tokens, or API key fragments.
- Backend responses now include baseline security headers such as `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, and `Cache-Control`; production responses also add HSTS.
- Admin AI telemetry summary surfaces sanitized timing, failure, and cost status from recent assistant messages; cost is marked `local_only`, `unconfigured`, or `estimated` instead of a fixed placeholder.
- Optional `AI_COST_USD_PER_1K_TOKENS` can enable rough character-based AI cost estimation for gray-release monitoring without storing prompts, images, tokens, API keys, or raw health content in telemetry.
- A sanitized gray-release smoke script lives at `backend/scripts/ai_release_smoke.py` and can exercise `/api/ready`, registration/login, a chat turn, and an optional image-recognition check without printing secrets or raw content.
- Weekly/monthly reports are exposed as JSON and CSV, with disclaimer and audit logging.
- FREE/PRO/COACH 权益骨架和 mock 计费 provider 已可用；真实扣费仍未实现。
- Mock 订阅会话现在会把 subscription plan/status 持久化到用户记录，entitlement snapshots 读取这份状态。
- Billing now exposes a mock plan catalog, advisory plan limits, persisted billing/effective plan state, and audited subscription cancellation back to FREE entitlements.
- Billing provider status now uses a registry surface: the UI shows the active `mock` provider and a planned external payment provider slot, and startup rejects unsupported `BILLING_PROVIDER` values. No live gateway is wired.
- Billing usage snapshots now expose daily AI chat and monthly photo recognition counts/limits through `/api/billing/usage`, with aggregate-only payloads and no raw content or credential material.
- Admin audit/knowledge overview skeleton is guarded by admin phone-hash allowlist and also supports a persisted ADMIN role bootstrap path.
- Production readiness now warns with `admin_bootstrap_allowlist_missing` when no break-glass `ADMIN_PHONE_HASHES` entry is configured; the snapshot exposes only the allowlist count, never hash values or phone numbers.
- OTP readiness now warns on the `audit_only` mock provider and fails closed on unsupported `OTP_PROVIDER` names, so typos cannot silently fall back to an audit-only delivery path.
- Admin ops can list users and update user role/subscription state through audited endpoints that never expose raw phone numbers.
- Admin user operations now support safe search by nickname/user ID plus role, plan, and subscription-status filters for gray-release triage.
- Admin release readiness now aggregates unsafe feedback, refresh reuse, OTP/password-login lockouts, knowledge gaps, food nutrition provenance/review gaps, offline sync failed/conflict states, local intake-review backlog telemetry, AI error signals, and the sanitized `/api/ready` config readiness into a red/yellow/green gray-release gate, without exposing secrets, model IDs, database credentials, raw food notes, meal details, images, client draft payloads, or user health content.
- Admin release readiness now returns sanitized `action_items` for the top block/warn gates, and the UI displays them as an operator action queue so gray-release triage starts from the highest severity aggregate signals without adding raw food, meal, image, chat, or health-content exposure.
- Admin activation metrics now summarize recent total/active/verified/new/paid users, meal/chat/feedback/health-metric activity, security events, and daily usage trends from aggregate counts only; no raw phone, meal text, chat content, feedback text, or health values are returned.
- Admin commercialization summary now exposes aggregate plan/status distribution, billing event counts, and AI/photo quota pressure through `/api/admin/commercialization/summary`, audited without raw payment notes, phone numbers, meal names, chat text, images, or credentials.
- Gray-release operator runbook is available at `docs/GRAY_RELEASE_RUNBOOK.md`.
- Core knowledge seed now includes additional China-market foods for congee, pickles, hot pot broth, peanuts, crab, steamed buns, fried dough sticks, beef noodles, common vegetables/starches, home-style dishes, regional restaurant staples such as xiaolongbao, braised pork belly, kung pao chicken, scallion pancakes, steamed egg custard, steamed perch, zhajiangmian, hot dry noodles, salted duck egg, tea egg, braised eggplant, roujiamo, liangpi, wonton soup, malatang, grilled skewers, meat/vegetable baozi, jianbing guozi, shaomai, sweetened soy milk, cheung fun, sweet tofu pudding, sticky rice rolls, luosifen, fried chicken cutlets, and grilled cold noodles, with allergen/risk tags and rules across all supported disease profiles.
- Knowledge seed validation now fails before import when tags leave the reviewed vocabulary, food aliases normalize to conflicting terms, aliases are too broad for safe substring matching, or any supported disease ruleset misses a food. `/api/knowledge/foods?q=` now uses the same normalized food-text matching as local rule evaluation, with matcher tests covering whitespace-normalized aliases and duplicate food-code suppression.
- Report center now supports date/month filters and a small local history of recent reports.
- Billing and admin skeleton pages are wired into the app shell and settings surface.
- Camera intake now supports upload progress, cancel, and retry for the last successful upload attempt.
- Chat composer image recognition now also has staged progress, AbortController cancellation, and retry for the previous image upload.
- Offline intake confirmation can fall back to IndexedDB when the network is unavailable, preserving candidate metadata for later sync.
- Intake confirmation now requires explicit review for low-confidence candidates and lets users edit ingredients, seasonings, and cooking method before re-evaluation.
- Intake confirmation now includes on-demand local-rule alternative suggestions for risky candidates, with conservative disclaimers and no automatic candidate replacement or meal creation.
- Intake confirmation now includes a read-only impact preview for calories, sodium, and purine before final logging; it uses shared daily target calculation and keeps the health-management disclaimer visible.
- Chat now includes a local候选复核台: unconfirmed photo/voice/text/chat intake drafts are stored in the user-scoped IndexedDB `intakeDrafts` queue, can be resumed or discarded, and never call `/api/intake/confirm` until the user returns to `IntakeConfirmationSheet` and explicitly confirms. The panel also shows local-only review pressure metrics for pending/in-review drafts, low-confidence candidates, high-risk/AVOID candidates, and photo/voice source mix. It now supports filter chips for all/risk/low-confidence/photo/voice/text-AI queues and sorts visible drafts by AVOID, risk, low-confidence, active-review, and recency priority so the safety-critical items are handled first.
- Settings can submit privacy-preserving intake-review telemetry through `POST /api/intake/review-telemetry`: only aggregate counts and allowlisted source/status distributions leave the device. Food names, notes, health text, images, raw candidates, and IndexedDB draft payloads remain local. Admin activation metrics and release readiness consume those snapshots as aggregate gray-release signals.
- Intake candidate correction feedback is now wired from `IntakeConfirmationSheet` to `POST /api/intake/candidate-feedback`. It creates open AI/recognition feedback using only the correction type, tags, hashed draft/correction markers, and allowlisted count/level metadata; the backend stores a generic placeholder instead of raw client correction text, and audit metadata never includes candidate food names, notes, images, raw summaries, ingredients, seasonings, or cooking methods.
- Candidate safety alternatives are now available through `POST /api/intake/candidate/alternatives` and the confirmation sheet `替代建议` action. Suggestions are generated only from the local knowledge base, filter out hard-blocked/AVOID/LIMIT/insufficient candidates, remain read-only, and never confirm or create meals automatically.
- Confirm-before-write impact preview is available through `POST /api/intake/confirm/preview` and the confirmation sheet `影响预览` action. It combines saved same-day meals with current candidates against shared daily targets for calories, sodium, and purine, returns `will_create_meal=false`, and does not confirm, replace, or persist candidates.
- Admin feedback triage can list AI/recognition feedback, filter by open/reviewed/closed status and feedback type, and move items through those statuses with audit logging. Unsafe feedback cannot be closed directly from open; it must be marked reviewed first, and rejected close attempts are audited.
- Admin knowledge backlog now aggregates feedback gaps, recognition corrections, local-rule fallback samples, hash-only reason codes, safe metadata keys, and food nutrition source/quality/review counts through `/api/admin/knowledge/backlog` so seed/rule improvements can be prioritized without exposing raw text; feedback items can be moved through open/reviewed/closed directly from the backlog while retaining the audited backend status transition.
- Smart insight feedback is now available from the Home latest-insight card and stored in the existing AI feedback loop via `app_message_id`; audit metadata stores only hashes, counts, IDs, and safe metadata keys, not raw correction text or insight content.

## Latest Product Surface Additions

- Admin release readiness operator queue:
  - `GET /api/admin/release/readiness` returns `action_items`, the top three block/warn gate items ranked by severity and count.
  - The “灰度门禁” admin tab renders those sanitized `action_items` under “处置优先级”, with a local fallback for older readiness payloads.
  - The queue reuses existing sanitized gate labels, messages, counts, and thresholds; it does not expose raw user health content, food notes, meal names, images, or client drafts.
  - Frontend and backend tests now lock the readiness API/type/UI/backend wiring for food review, offline sync gates, intake-review backlog telemetry, and the operator queue.
- Admin activation metrics:
  - `GET /api/admin/activation/metrics?window_days=7` returns a gray-release usage snapshot for activation, retention proxy, meal logging, AI usage, feedback load, health-metric usage, intake-review backlog snapshots, and security events.
  - Admin UI includes an “激活指标” tab with daily trend bars for meal, AI reply, and feedback volume, plus aggregate intake-review snapshot/pending/high-risk cards.
  - The endpoint is admin-gated and audited as `admin.activation.metrics.list`; payloads are aggregate-only and avoid raw user health content.
- Admin commercialization summary:
  - `GET /api/admin/commercialization/summary?window_days=30` returns plan/status distribution, mock 计费 event counts, and advisory quota pressure for daily AI chat and monthly photo recognition.
  - Admin UI includes a “商业化概览” tab for gray-release interviews and subscription triage.
  - The endpoint is admin-gated and audited as `admin.commercialization.summary.list`; payloads are aggregate-only and do not include raw content, files, credentials, or contact details.
- AI feedback loop:
  - `POST /api/chat/messages/{message_id}/feedback`
  - Feedback stores user-owned correction text but audit metadata stores only safe type/rating/tag counts/hash fields.
  - Frontend AI messages expose helpful/not-helpful/risk feedback actions when a persisted message id is available, plus separate correction/knowledge-gap entry points for text feedback.
  - Chat history reload restores each AI message's latest submitted feedback state so users can review what they already marked.
  - `POST/GET /api/insights/{message_id}/feedback` records Home smart-insight helpful/not-helpful/knowledge-gap feedback against `app_message_id`, and account export/admin feedback views include that link without exposing raw insight content in audit logs.
  - `POST /api/intake/candidate-feedback` records candidate recognition/correction/knowledge-gap feedback into the same backlog with hash-only correction evidence and safe metadata keys, so operators can count recurring recognition issues without seeing raw candidate contents.
- Health metrics:
  - `POST/GET/PUT/DELETE /api/health-metrics`
  - Supports weight, body fat, blood pressure, blood glucose, uric acid, blood lipid, and waist records.
  - `GET /api/health-metrics/providers` exposes manual, mock-device, and planned vendor-device provider status without secrets.
  - Settings links to a manual health metric page with latest values and recent history.
  - Account export/delete includes health metrics, AI feedback, account consent/subscription state, and safe device-session visibility.
- AI session management:
  - Chat page supports session list, create, switch, delete, and persisted analyst/coach mode.
  - Assistant style and intervention-strength preferences are sent with chat requests, stored in safe message attachments, restored from history, and injected into the cloud prompt without changing local-rule safety boundaries.
- Daily console:
  - Home page now includes streak, risk summary, next-step suggestion, and seven-day logging trend.
- Meal logging friction reduction:
  - Log add-meal modal now shows recent/frequent meal shortcuts from the existing `/api/meals` list API for the selected 14-day window.
  - Favorite meals are now persisted server-side through `GET /api/meals/favorites`, `POST /api/meals/{meal_id}/favorite`, `POST /api/meals/favorites/{favorite_id}/use`, and `DELETE /api/meals/favorites/{favorite_id}`.
  - Favorite meal cards can be saved from synced meal logs, reused from the add-meal modal as editable templates, and removed without exposing raw meal names or notes in audit metadata.
  - Recent meal shortcuts group by normalized food name and portion, rank by frequency and recency, and fill name, portion, meal type, category, and note into the editable manual form without auto-saving.
  - Quick-copy actions for previous meal, yesterday's same meal type, and saved favorite meals use authenticated user-owned data and only prefill editable fields.
  - The add-meal modal includes a pre-meal simulation button that estimates calories/sodium/purine locally, calls the audited local knowledge `/api/knowledge/evaluate-food` endpoint, and proposes conservative swaps without auto-saving.
  - The client accepts both direct meal arrays and paginated `{ items }` backend responses, and maps snake_case backend meals through the shared mapper before grouping.
- Report center:
  - Settings links to a report page for weekly/monthly summaries, target comparison, daily trend preview, recent insight context, risk notes, disclaimer, and JSON/CSV download.
- Billing lifecycle:
  - `GET /api/billing/plans` returns the FREE/PRO/COACH catalog with mock prices, limits, and upgrade reasons.
  - `GET /api/billing/providers` returns the configured mock provider and planned external payment provider capabilities without exposing secrets.
  - `GET /api/billing/usage` returns current-period advisory quota usage for daily AI chat and monthly photo recognition; it is audited and intentionally gray-release observe-only.
  - Billing UI shows current-period usage bars and remaining advisory quotas without enforcing limits.
  - `settings.readiness_snapshot()` flags mock 计费 as a yellow gray-release warning so operators know payment remains mock-only.
  - `POST /api/billing/subscription/cancel` requires explicit confirmation, audits the action, preserves the previous paid plan for admin visibility, and removes active paid entitlements.
  - Billing UI shows effective entitlement plan, billing plan, current status, advisory limits, provider capability status, and a safe cancel action for active paid mock subscriptions.
- Offline queue status:
  - Local IndexedDB meal records distinguish `PENDING`, `SYNCED`, `CONFLICT`, and `FAILED`, and the server enum now matches the four-state queue. Admin release readiness now treats server-side `FAILED`/`CONFLICT` meal sync states as gray-release warning/blocking signals.
  - Local intake-review queue telemetry is manual/explicit from Settings and records only counts: total, pending, in-review, low-confidence, high-risk, hard-block, and source/status distributions. Account export/delete includes these telemetry snapshots as user data, still without raw candidates.
  - Sync conflicts and failures are preserved locally and surfaced in cache statistics.
  - Offline meal edits and deletes now use a server sync protocol with update operations, delete tombstones, conflict reporting, and server-confirmed tombstone cleanup.
- Settings now exposes a queue inspector with per-item status, retry, discard-local-draft, and jump-to-log actions. The logout confirmation now refreshes local queue stats and shows pending/failed/conflict counts with direct queue/retry actions before a user can choose to clear local unsynced drafts.
- Settings now includes a login-device panel for reviewing active sessions and revoking suspicious devices without exposing raw token material.
- Settings now exposes real AI assistant preference controls instead of placeholder "unavailable" rows, and those preferences are applied to subsequent chat requests.
- Log cards show pending, failed, and conflict status so offline candidates are visible before and after sync.
- Food knowledge coverage:
  - Added high-frequency China-market staples and dishes: steamed buns, fried dough sticks, and braised beef noodles.
  - Added common daily vegetables, starches, fish, dumplings, fried rice, tofu dishes, egg dishes, and regional restaurant staples including xiaolongbao, braised pork belly, kung pao chicken, scallion pancakes, steamed egg custard, and steamed perch.
  - Added high-frequency external meals and night-market items including zhajiangmian, hot dry noodles, salted duck egg, tea egg, braised eggplant, roujiamo, liangpi, wonton soup, malatang, and grilled skewers.
  - Added breakfast and snack gaps including meat/vegetable baozi, jianbing guozi, shaomai, sweetened soy milk, cheung fun, sweet tofu pudding, sticky rice rolls, luosifen, fried chicken cutlets, and grilled cold noodles.
  - Seed validation now checks their aliases, allergen tags, sodium/fat/glycemic/purine risk tags, and conservative per-disease rule coverage.
- Food nutrition provenance now flows through `food_items`, seed validation, `/api/knowledge/foods`, admin backlog summaries, and the release readiness gate; unreviewed or missing-source foods turn the gray-release gate yellow/red based on count.

## Validation Commands

Run both before a gray-release build:

```bash
npm run test
npm run typecheck
npm run build
backend/.venv/bin/python -m pytest -q backend/tests
```

Validation evidence should be recorded with the commit SHA and date of each gray-release candidate. Do not treat older pass counts as current evidence; rerun the commands above after each review/fix batch.

Latest local evidence on 2026-06-07:

- `node --test tests/frequent-meals-contract.test.mjs`: 1 passed, including recent/frequent shortcuts plus previous/yesterday quick-copy contracts.
- `node --test tests/favorite-meals-contract.test.mjs`: 3 passed, covering typed API methods, LogView confirmation flow, and backend user-scoped/audit allowlist contracts.
- `backend/.venv/bin/python -m pytest backend/tests/test_favorite_meals.py -q`: 3 passed, covering FavoriteMeal schema fields, sanitized audit metadata, and use-count updates without creating meals.
- `node --test tests/premeal-simulation-contract.test.mjs`: 1 passed.
- `node --test tests/intake-review-queue-contract.test.mjs`: 3 passed, covering IndexedDB review queue state, ChatView resume/discard flow, and settings cleanup risk counts.
- `node --test tests/intake-review-telemetry-contract.test.mjs`: 2 passed, covering aggregate-only API wiring and admin readiness/activation signals.
- `node --test tests/intake-alternatives-contract.test.mjs`: 2 passed, covering local-rule alternative API/UI wiring and read-only/no-confirm contracts.
- `node --test tests/intake-confirm-preview-contract.test.mjs`: 2 passed, covering confirm impact preview API/UI wiring and read-only/no-confirm contracts.
- `node --test tests/intake-candidate-feedback-contract.test.mjs`: 2 passed, covering candidate correction API/UI wiring and no-raw-candidate payload/audit contracts.
- `backend/.venv/bin/python -m pytest -q backend/tests/test_intake_review_telemetry.py backend/tests/test_admin_routes.py backend/tests/test_account_data_rights.py`: 32 passed, 1 known dependency deprecation warning.
- `backend/.venv/bin/python -m pytest -q backend/tests/test_intake_review_telemetry.py`: 5 passed, including candidate feedback hashing, tag allowlist, typed metadata filtering, and feedback-type constraints.
- `backend/.venv/bin/python -m pytest -q backend/tests/test_intake_service.py`: 15 passed, including read-only candidate alternatives and confirm impact preview target projections.
- `node --test tests/*.test.mjs`: 54 passed, including confirm impact preview, candidate alternatives, candidate feedback privacy contracts, intake review queue telemetry, favorite meals, pre-meal simulation, offline sync, billing/admin, compliance, and SSR smoke contracts.
- `npm run test`: 54 passed.
- `npm run typecheck`: passed.
- `npm run build`: passed.
- `backend/.venv/bin/python -m pytest -q backend/tests`: 254 passed, 5 known dependency deprecation warnings.
- `git diff --check`: passed.

## Remaining High-Value Gaps

- Food knowledge base now carries source-backed nutrition provenance (`nutrition_source_code`, `nutrition_source_detail`, `nutrition_estimate_quality`, `nutrition_review_status`) through seed validation, database schema, API responses, admin backlog summaries, and release readiness gates; it should continue expanding with stronger regional dish coverage and more reviewed external references.
- Admin console still needs real production support workflows before public launch, but security, knowledge, feedback, and user-management surfaces now have lightweight filtering support.
- Payment remains mock/provider abstraction only; no real billing gateway is connected. The current lifecycle and provider registry are sufficient for internal and gray-release entitlement testing, not for real charging.
- `ENTITLEMENT_ENFORCE_LIMITS=false` keeps billing in observe-only mode during internal tests. Set it to `true` only after the gray-release gate, audit review, and operator training are complete.
- Frontend automated tests are still minimal compared with backend coverage, especially around live UI flows.

## Next Product Goal Queue

After the current controlled-test, gray-release, and commercialization-foundation goal is verified, continue with these eight high-value app features:

1. Meal Safety Review Desk: review and edit AI/photo/voice/text intake candidates before final logging, then re-run local metabolic and allergy rules.
2. Pre-meal Simulation And Swaps: predict likely risk before eating and suggest safer food, portion, and cooking substitutions without making medical claims.
3. Daily Metabolic Console: show goal progress, next best action, risk summary, and logging streak from verified local data.
4. Low-confidence Strong Confirmation: require explicit user confirmation when recognition confidence is low, food split is ambiguous, or portion estimates are weak.
5. Packaged-food Scan And Nutrition-label OCR: barcode-first matching with OCR fallback into reviewed personal food entries.
6. Personal Correction Loop: convert user edits and recognition corrections into sanitized feedback for food aliases, nutrition provenance, and rule improvements.
7. Weekly And Monthly Reports: export trend summaries with JSON/CSV/PDF-ready payloads and health disclaimer.
8. Coach Review Queue: for authorized COACH plans, surface only high-risk or low-confidence cases for audited coach review.
