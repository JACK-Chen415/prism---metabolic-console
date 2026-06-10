import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('mock billing persists subscriptions and admin can manage roles safely', () => {
  const apiSource = read('services/api.ts');
  const adminSource = read('components/views/AdminView.tsx');
  const billingSource = read('components/views/BillingView.tsx');
  const backendBilling = read('backend/app/api/routes/billing.py');
  const backendBillingService = read('backend/app/services/billing_service.py');
  const backendAdmin = read('backend/app/api/routes/admin.py');
  const userModel = read('backend/app/models/user.py');

  for (const required of [
    'subscription_plan',
    'subscription_status',
    'class UserRole',
    'class SubscriptionPlan',
    'class SubscriptionStatus',
  ]) {
    assert.ok(userModel.includes(required), `Missing persisted user commercial field: ${required}`);
  }

  for (const required of [
    '_apply_mock_checkout_subscription',
    '_apply_mock_subscription_cancel',
    'SubscriptionStatus.ACTIVE',
    'SubscriptionStatus.CANCELED',
    'BillingProviderResponse',
    'billing_provider_registry',
    '@router.get("/plans"',
    '@router.get("/providers"',
    '@router.get("/usage"',
    'billing.usage.list',
    '_build_usage_response',
    'enforcement_scope',
    '@router.post("/subscription/cancel"',
  ]) {
    assert.ok(backendBilling.includes(required), `Missing mock billing persistence contract: ${required}`);
  }

  for (const required of [
    'create_checkout_order',
    'cancel_user_subscription',
    'billing.checkout',
    'billing.subscription.cancel',
    'audit_security_event',
  ]) {
    assert.ok(backendBillingService.includes(required), `Missing billing service audit contract: ${required}`);
  }

  for (const required of [
    '@router.get("/users"',
    '@router.patch("/users/{user_id}/role"',
    '@router.patch("/users/{user_id}/subscription"',
    'admin.user.role_update',
    'admin.user.subscription_update',
    'hash_sensitive_value(row.phone)',
  ]) {
    assert.ok(backendAdmin.includes(required), `Missing audited admin user contract: ${required}`);
  }

  for (const required of [
    'getPlans',
    'getProviders',
    'listUsers',
    'subscription_plan',
    'subscription_status',
    'cancelSubscription',
    '/billing/providers',
    '/billing/usage',
    '/billing/subscription/cancel',
    "confirm: 'CANCEL_SUBSCRIPTION'",
    'updateUserRole',
    'updateUserSubscription',
  ]) {
    assert.ok(apiSource.includes(required), `Missing frontend admin API contract: ${required}`);
  }

  for (const required of [
    '用户角色',
    'updateUserRole',
    'updateUserSubscription',
    '手机哈希',
    '用户筛选',
    'userQuery',
    'userRoleFilter',
    'userPlanFilter',
    'userStatusFilter',
    'handleUserSearch',
    '搜索昵称或用户 ID',
  ]) {
    assert.ok(adminSource.includes(required), `Missing admin role UI contract: ${required}`);
  }

  for (const required of [
    '当前订阅',
    '账单档位',
    '取消订阅',
    'handleCancelSubscription',
    'planCatalog',
    'providerCatalog',
    '计费 Provider',
    'supports_webhook',
    'requires_secret',
    'upgrade_reasons',
    'formatPrice',
    '本周期用量',
    'usageSnapshot',
    'usageBarWidth',
    '灰度观测，不强制拦截',
    'enforcementScopeLabelMap',
    '权益门禁',
    '创建模拟订阅',
  ]) {
    assert.ok(billingSource.includes(required), `Missing billing lifecycle UI contract: ${required}`);
  }

  assert.ok(billingSource.includes("snapshot?.status"), 'Billing page should display persisted subscription status');
  assert.ok(billingSource.includes('模拟会话'), 'Billing page should label checkout as a mock session');
  assert.ok(apiSource.includes('BillingUsageSnapshot'), 'Frontend API should expose billing usage snapshots');
  assert.ok(read('types.ts').includes('BillingEnforcementScope'), 'Frontend types should model billing enforcement mode');
});
