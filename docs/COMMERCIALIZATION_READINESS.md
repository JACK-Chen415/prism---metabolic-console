# Prism Commercialization Readiness Notes

_Last updated: 2026-05-31_

This note tracks the current engineering state for controlled internal testing, small gray release, and commercialization foundation work.

## Recently Completed Baseline

- Authentication security now separates dev/prod OTP behavior, uses provider abstraction, rate limits, failure lockout, and audit logging.
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
- User data export, data deletion, and account deletion are implemented with user-scoped authorization, security audit logs, explicit account/subscription/consent state, and safe device-session export that omits token, jti, UA, and IP hash material.
- Request IDs, structured HTTP logs, DB readiness checks, sanitized config readiness snapshots, baseline API security response headers, and AI timing plus configurable cost-estimation telemetry are in place.
- Security audit metadata now has a helper-level redaction pass for sensitive keys, long raw text, tokens, API keys, OTPs, images, and raw content before `security_audit_logs.metadata_json` is written.
- AI cloud error handling now returns category-level, sanitized failure messages and logs only structured error types instead of upstream raw exception bodies, model IDs, endpoint IDs, tokens, or API key fragments.
- Backend responses now include baseline security headers such as `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, and `Cache-Control`; production responses also add HSTS.
- Admin AI telemetry summary surfaces sanitized timing, failure, and cost status from recent assistant messages; cost is marked `local_only`, `unconfigured`, or `estimated` instead of a fixed placeholder.
- Optional `AI_COST_USD_PER_1K_TOKENS` can enable rough character-based AI cost estimation for gray-release monitoring without storing prompts, images, tokens, API keys, or raw health content in telemetry.
- A sanitized gray-release smoke script lives at `backend/scripts/ai_release_smoke.py` and can exercise `/api/ready`, registration/login, a chat turn, and an optional image-recognition check without printing secrets or raw content.
- Weekly/monthly reports are exposed as JSON and CSV, with disclaimer and audit logging.
- FREE/PRO/COACH entitlement skeleton and mock checkout provider are available.
- Mock checkout now persists subscription plan/status on the user record, and entitlement snapshots read that persisted state.
- Billing now exposes a mock plan catalog, advisory plan limits, persisted billing/effective plan state, and audited subscription cancellation back to FREE entitlements.
- Billing provider status now uses a registry surface: current `mock` provider is visible to the UI, the real payment gateway slot is marked planned, and startup rejects unsupported `BILLING_PROVIDER` values.
- Billing usage snapshots now expose daily AI chat and monthly photo recognition counts/limits through `/api/billing/usage`, with aggregate-only payloads and no raw content or credential material.
- Admin audit/knowledge overview skeleton is guarded by admin phone-hash allowlist and also supports a persisted ADMIN role bootstrap path.
- Production readiness now warns with `admin_bootstrap_allowlist_missing` when no break-glass `ADMIN_PHONE_HASHES` entry is configured; the snapshot exposes only the allowlist count, never hash values or phone numbers.
- OTP readiness now warns on the `audit_only` mock provider and fails closed on unsupported `OTP_PROVIDER` names, so typos cannot silently fall back to an audit-only delivery path.
- Admin ops can list users and update user role/subscription state through audited endpoints that never expose raw phone numbers.
- Admin user operations now support safe search by nickname/user ID plus role, plan, and subscription-status filters for gray-release triage.
- Admin release readiness now aggregates unsafe feedback, refresh reuse, OTP lockouts, knowledge gaps, food nutrition provenance/review gaps, offline sync failed/conflict states, AI error signals, and the sanitized `/api/ready` config readiness into a red/yellow/green gray-release gate, without exposing secrets, model IDs, database credentials, raw food notes, meal details, images, or user health content.
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
- Admin feedback triage can list AI/recognition feedback, filter by open/reviewed/closed status and feedback type, and move items through those statuses with audit logging. Unsafe feedback cannot be closed directly from open; it must be marked reviewed first, and rejected close attempts are audited.
- Admin knowledge backlog now aggregates feedback gaps, recognition corrections, local-rule fallback samples, hash-only reason codes, safe metadata keys, and food nutrition source/quality/review counts through `/api/admin/knowledge/backlog` so seed/rule improvements can be prioritized without exposing raw text; feedback items can be moved through open/reviewed/closed directly from the backlog while retaining the audited backend status transition.
- Smart insight feedback is now available from the Home latest-insight card and stored in the existing AI feedback loop via `app_message_id`; audit metadata stores only hashes, counts, IDs, and safe metadata keys, not raw correction text or insight content.

## Latest Product Surface Additions

- Admin release readiness operator queue:
  - `GET /api/admin/release/readiness` returns `action_items`, the top three block/warn gate items ranked by severity and count.
  - The “灰度门禁” admin tab renders those sanitized `action_items` under “处置优先级”, with a local fallback for older readiness payloads.
  - The queue reuses existing sanitized gate labels, messages, counts, and thresholds; it does not expose raw user health content, food notes, meal names, images, or client drafts.
  - Frontend and backend tests now lock the readiness API/type/UI/backend wiring for food review, offline sync gates, and the operator queue.
- Admin activation metrics:
  - `GET /api/admin/activation/metrics?window_days=7` returns a gray-release usage snapshot for activation, retention proxy, meal logging, AI usage, feedback load, health-metric usage, and security events.
  - Admin UI includes an “激活指标” tab with daily trend bars for meal, AI reply, and feedback volume.
  - The endpoint is admin-gated and audited as `admin.activation.metrics.list`; payloads are aggregate-only and avoid raw user health content.
- Admin commercialization summary:
  - `GET /api/admin/commercialization/summary?window_days=30` returns plan/status distribution, mock billing event counts, and advisory quota pressure for daily AI chat and monthly photo recognition.
  - Admin UI includes a “商业化概览” tab for gray-release interviews and subscription triage.
  - The endpoint is admin-gated and audited as `admin.commercialization.summary.list`; payloads are aggregate-only and do not include raw content, files, credentials, or contact details.
- AI feedback loop:
  - `POST /api/chat/messages/{message_id}/feedback`
  - Feedback stores user-owned correction text but audit metadata stores only safe type/rating/tag counts/hash fields.
  - Frontend AI messages expose helpful/not-helpful/risk feedback actions when a persisted message id is available, plus separate correction/knowledge-gap entry points for text feedback.
  - Chat history reload restores each AI message's latest submitted feedback state so users can review what they already marked.
  - `POST/GET /api/insights/{message_id}/feedback` records Home smart-insight helpful/not-helpful/knowledge-gap feedback against `app_message_id`, and account export/admin feedback views include that link without exposing raw insight content in audit logs.
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
- Report center:
  - Settings links to a report page for weekly/monthly summaries, target comparison, daily trend preview, recent insight context, risk notes, disclaimer, and JSON/CSV download.
- Billing lifecycle:
  - `GET /api/billing/plans` returns the FREE/PRO/COACH catalog with mock prices, limits, and upgrade reasons.
  - `GET /api/billing/providers` returns the configured mock provider and planned external payment provider capabilities without exposing secrets.
  - `GET /api/billing/usage` returns current-period advisory quota usage for daily AI chat and monthly photo recognition; it is audited and intentionally gray-release observe-only.
  - Billing UI shows current-period usage bars and remaining advisory quotas without enforcing limits.
  - `settings.readiness_snapshot()` flags mock billing as a yellow gray-release warning so operators know payment remains mock-only.
  - `POST /api/billing/subscription/cancel` requires explicit confirmation, audits the action, preserves the previous paid plan for admin visibility, and removes active paid entitlements.
  - Billing UI shows effective entitlement plan, billing plan, current status, advisory limits, provider capability status, and a safe cancel action for active paid mock subscriptions.
- Offline queue status:
  - Local IndexedDB meal records distinguish `PENDING`, `SYNCED`, `CONFLICT`, and `FAILED`, and the server enum now matches the four-state queue. Admin release readiness now treats server-side `FAILED`/`CONFLICT` meal sync states as gray-release warning/blocking signals.
  - Sync conflicts and failures are preserved locally and surfaced in cache statistics.
  - Offline meal edits and deletes now use a server sync protocol with update operations, delete tombstones, conflict reporting, and server-confirmed tombstone cleanup.
- Settings now exposes a queue inspector with per-item status, retry, discard-local-draft, and jump-to-log actions.
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

## Remaining High-Value Gaps

- Food knowledge base now carries source-backed nutrition provenance (`nutrition_source_code`, `nutrition_source_detail`, `nutrition_estimate_quality`, `nutrition_review_status`) through seed validation, database schema, API responses, admin backlog summaries, and release readiness gates; it should continue expanding with stronger regional dish coverage and more reviewed external references.
- Admin console still needs real production support workflows before public launch, but security, knowledge, feedback, and user-management surfaces now have lightweight filtering support.
- Payment remains mock/provider abstraction only; no real billing gateway is connected. The current lifecycle and provider registry are sufficient for internal and gray-release entitlement testing, not for real charging.
- `ENTITLEMENT_ENFORCE_LIMITS=false` keeps billing in observe-only mode during internal tests. Set it to `true` only after the gray-release gate, audit review, and operator training are complete.
- Frontend automated tests are still minimal compared with backend coverage, especially around live UI flows.
