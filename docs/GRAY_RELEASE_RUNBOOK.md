# Prism Gray Release Runbook

_Last updated: 2026-05-31_

This runbook is for controlled internal testing and small gray release. It assumes mock billing is still enabled and no real payment provider is connected.

## 1. Preflight Gate

Run these checks before each gray-release build:

```bash
npm run test
npm run typecheck
npm run build
backend/.venv/bin/python -m pytest -q backend/tests
```

Do not promote if any check fails. Existing acceptable warnings are passlib `crypt` deprecation and jose `utcnow` deprecation.

For a deployed environment, also run the sanitized smoke script against the target API before opening a gray cohort:

```bash
PRISM_API_URL=https://<backend-host>/api \
PRISM_SMOKE_PASSWORD=<temporary-test-password> \
backend/.venv/bin/python backend/scripts/ai_release_smoke.py
```

The smoke script registers or reuses a test account and writes chat/image smoke records to the target database unless `--skip-chat` is used. Use a dedicated non-production cohort or a clearly labeled disposable gray-release test account, and include cleanup/account-deletion policy in the release checklist.

Optional image recognition smoke requires an operator-owned non-sensitive image path:

```bash
PRISM_API_URL=https://<backend-host>/api \
PRISM_SMOKE_PASSWORD=<temporary-test-password> \
PRISM_SMOKE_IMAGE_PATH=/path/to/non-sensitive-food-image.jpg \
backend/.venv/bin/python backend/scripts/ai_release_smoke.py
```

The smoke report is JSON and may be attached to release notes because it is designed not to expose secrets or health content. It must not output passwords, token values, OTP codes, raw chat content, raw response bodies, original image content, or image paths; 换言之，冒烟报告不得输出密码、token、验证码、原始聊天内容或图片内容。 It reports status codes, `X-Request-ID`, timings, hash identifiers, aggregate food counts, and AI telemetry status such as `cost_status`.

## 2. Production Config Gate

Before deployment, confirm:

- `APP_ENV` is production-like only when real production configuration is present.
- Frontend `VITE_APP_ENV=production` is paired with an explicit `VITE_API_URL`; deployed HTTPS frontends must not fall back to localhost or plain HTTP API URLs.
- `JWT_SECRET_KEY` is not a default or sample value.
- `JWT_ALGORITHM` is one of `HS256`, `HS384`, or `HS512`; access tokens are at most 60 minutes and refresh tokens are at most 30 days in production.
- `OTP_PROVIDER` is not `dev` or `console` in production, and `OTP_PROVIDER=audit_only` is treated as a warning-level gray-release mock provider rather than a real SMS path.
- `ARK_API_KEY` and `DOUBAO_MODEL` are real production values, not placeholders.
- `ADMIN_PHONE_HASHES` contains at least one break-glass admin hash until deployed role management has been tested; readiness reports `admin_bootstrap_allowlist_missing` when production has none.
- `BILLING_PROVIDER=mock` unless a real provider implementation, webhook signature verification, idempotency, invoice audit events, and refund/cancel flows have all been implemented and tested.
- `ENTITLEMENT_ENFORCE_LIMITS=false` during internal and small gray-release cohorts unless feature-gate enforcement has passed audit review and operator training; turning it on does not mean real payment is connected.
- CORS origins are explicit HTTPS origins, not wildcards.
- Database URL points to the intended production PostgreSQL instance.
- `MAX_UPLOAD_SIZE_MB` is at or below 10 and `MAX_UPLOAD_IMAGE_PIXELS` is at or below 20,000,000; production startup rejects higher values.
- Upload intake rejects multi-frame or animated images, even when the content type and magic bytes otherwise look valid.
- No real API key or payment secret is committed to the repository.
- `/api/ready` returns `checks.config=ok` and sanitized `config_details` without exposing API keys, model ids, admin hashes, or phone numbers.
- Baseline API security headers are present on backend responses, including `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, and `Cache-Control`; production should also include `Strict-Transport-Security`.
- `/api/admin/release/readiness` is checked before gray release; its config gate includes the sanitized `/api/ready` config signal without exposing secrets, model IDs, or database credentials.

## 3. Admin Bootstrap

Admin access is allowed by either:

- phone hash in `ADMIN_PHONE_HASHES`, for first bootstrap and emergency access;
- persisted `User.role == ADMIN`, for normal operations.

Operational rules:

- Never expose or paste raw phone numbers in issue trackers, chat, or logs.
- Use the admin user list only for role and subscription operations.
- Use admin user filters by nickname/user ID, role, plan, and subscription status during gray-release triage; do not search or share raw phone numbers.
- Role and subscription changes must appear in security audit logs as `admin.user.role_update` or `admin.user.subscription_update`.
- Keep at least one break-glass allowlist admin until role management has been tested in the deployed environment; treat `admin_bootstrap_allowlist_missing` as a pre-expansion warning even though it does not block startup.

## 4. Billing And Entitlements

Current billing is mock-only:

- `/api/billing/plans` returns the current FREE/PRO/COACH catalog, mock prices, advisory limits, and upgrade reasons.
- `/api/billing/providers` returns the configured mock provider and planned external payment provider capabilities without exposing payment secrets.
- `/api/billing/usage` returns current daily AI-chat and monthly photo-recognition usage against advisory plan limits; use it to monitor user-scoped limit pressure during gray release, not to block users yet.
- Billing responses expose `enforcement_scope`: `observe_only` for soft quota observation, `feature_entitlement_gate` when entitlement checks are enforced by the server.
- `/api/admin/commercialization/summary` returns admin-scoped aggregate plan/status distribution, mock billing event counts, and quota pressure for cohort-level review.
- `settings.readiness_snapshot()` keeps mock billing visible as a warning in the gray-release gate so it cannot be mistaken for real commercial readiness.
- `/api/billing/checkout` creates a mock checkout session and persists `subscription_plan`, `subscription_status`, and `subscription_updated_at`.
- `/api/billing/subscription/cancel` requires `CANCEL_SUBSCRIPTION`, audits the request, preserves the prior paid plan for admin visibility, and removes active paid entitlements.
- Entitlements are read from the persisted user subscription state and expose both effective plan and billing plan.
- Canceled or inactive subscriptions fall back to FREE entitlements while the previous billing plan remains visible to admins.

Do not add a real payment provider until webhook signature verification, idempotency, invoice audit events, and refund/cancel flows are implemented.

## 5. Safety Monitoring

Review during gray release:

- `/api/admin/audit/security` for auth, data rights, billing, and admin operations; search by event keywords such as `otp`, `auth`, `report`, `account`, or filter by event status when investigating noisy gray-release windows. Audit metadata is helper-sanitized before write; do not paste raw support text, OTPs, tokens, images, or health notes into operator comments.
- `/api/admin/audit/knowledge` for local-rule fallback, cloud-call reasons, and blocked cloud calls; filter by fallback status and cloud-call mode when investigating whether LLM output was properly constrained by local rules.
- `/api/admin/activation/metrics` for aggregate gray-release activation and usage signals: active/new/paid users, meal users, AI replies, feedback volume, health-metric usage, security events, and daily trends. Do not use this panel for raw health review.
- `/api/admin/commercialization/summary` and the Admin “商业化概览” tab for aggregate plan/status distribution, mock billing events, and quota-pressure checks before expanding a cohort. Do not use it to infer individual health behavior.
- `/api/billing/usage` and the Billing page for user-scoped quota-pressure checks during interviews; this is observe-only until real billing enforcement is implemented.
- `/api/admin/ai/telemetry` for sanitized AI latency, failure, and cost status (`local_only`, `unconfigured`, `estimated`, or `partial_estimate`). AI upstream exceptions should be reviewed by error type and request ID; raw upstream exception bodies, endpoint IDs, model IDs, API keys, and token fragments must not be copied into release notes.
- `/api/admin/release/readiness` for the red/yellow/green gray-release gate before expanding traffic; it includes the sanitized `/api/ready` config signal and `action_items` with the top block/warn operator priorities, and must be checked before gray release.
- `/api/admin/feedback` for unsafe answer reports, recognition corrections, and knowledge gaps; use the status and type filters to isolate open items during gray-release triage.
- `/api/admin/knowledge/backlog` for sanitized backlog counts, hash-only reason codes, metadata keys, and recent knowledge-gap / recognition-correction items when prioritizing seed or rule updates; feedback items can be marked open/reviewed/closed from this panel, but do not use it to inspect raw health text.
- In the Admin “灰度门禁” tab, start from “处置优先级”; it mirrors readiness `action_items` and should be cleared or accepted before expanding a cohort.
- User-facing chat feedback now supports direct helpful/not-helpful/risk actions and text-based correction or knowledge-gap reports; chat history restores the latest saved state, and operators should review the sanitized audit trail rather than raw feedback text.
- `/api/health-metrics/providers` for the current manual/mock/planned device integration status.
- Settings page offline sync queue for inspecting pending/failed/conflict local meals, retrying items, discarding local drafts, and jumping to the log date for manual review.
- Settings page login-device panel for users to review active sessions and revoke non-current devices; operators can verify `auth.session.list` and `auth.session.revoke` audit events without handling raw refresh tokens.
- Settings page AI assistant preferences for switching default analyst/coach style and intervention strength before gray-release user interviews; those choices now flow into chat requests and history rendering.

Incident thresholds:

- Any allergy or AVOID/LIMIT relaxation report: pause affected AI/intake flow and inspect local knowledge audit.
- Repeated OTP failures or lockouts from the same actor hash: keep lockout active and inspect rate-limit behavior.
- Upload rejection spike: inspect MIME/file-header patterns without storing or sharing raw images.

## 6. Data Rights

For export/delete/account deletion requests:

- Use user-facing settings flows first.
- Verify the security audit event exists.
- Do not manually query or share raw health text unless a formal support process is created.
- Account deletion should revoke device sessions and leave only allowed audit records.
- Suspicious device reports should be handled by guiding the user to revoke the affected non-current session first, then reviewing sanitized audit entries.

## 7. Rollback

Rollback order:

1. Disable frontend entry points for the affected feature.
2. Revert the backend route or feature flag if available.
3. Preserve audit logs and user data.
4. Re-run the full validation gate before redeploy.

Never rollback by destructive database edits without a backup and explicit operator approval.
