import React, { useEffect, useState } from 'react';
import { BillingAPI } from '../../services/api';
import { BillingProviderItem, BillingUsageSnapshot, EntitlementSnapshot, PlanCatalogItem, PlanTier, View } from '../../types';

interface BillingViewProps {
  onViewChange: (view: View) => void;
}

const planMeta: Record<PlanTier, { title: string; subtitle: string; accent: string; icon: string }> = {
  FREE: { title: 'FREE', subtitle: '基础记录与提醒', accent: 'text-slate-400', icon: 'folder_open' },
  PRO: { title: 'PRO', subtitle: '灰度内测主套餐', accent: 'text-primary', icon: 'verified' },
  COACH: { title: 'COACH', subtitle: '教练协作与管理扩展', accent: 'text-[#45b7aa]', icon: 'support_agent' },
};

const limitLabelMap: Record<string, string> = {
  ai_chat_daily: '每日 AI 对话',
  photo_recognition_monthly: '每月拍照识别',
  report_history_months: '报告历史（月）',
  coach_review: '教练复核',
  support_level: '支持等级',
};

const providerSupportLabelMap: Record<string, string> = {
  supports_checkout: '可 checkout',
  supports_cancel: '可取消',
  supports_webhook: '可 webhook',
  supports_refund: '可退款',
  requires_secret: '需密钥',
};

const providerStatusLabelMap: Record<BillingProviderItem['status'], string> = {
  active: '已启用',
  mock: '模拟',
  planned: '预留',
  disabled: '停用',
};

const usageStatusLabelMap: Record<string, string> = {
  ok: '正常',
  near_limit: '接近上限',
  over_soft_limit: '已超软限',
  blocked: '已达上限',
  unmetered: '未计量',
};

const enforcementScopeLabelMap: Record<string, string> = {
  observe_only: '观察模式',
  feature_entitlement_gate: '权益门禁',
};

const usageStatusClass: Record<string, string> = {
  ok: 'border-emerald-300/20 bg-emerald-500/10 text-emerald-200',
  near_limit: 'border-amber-300/25 bg-amber-500/10 text-amber-100',
  over_soft_limit: 'border-amber-300/25 bg-amber-500/10 text-amber-100',
  blocked: 'border-red-400/25 bg-red-500/10 text-red-200',
  unmetered: 'border-white/10 bg-white/[0.03] text-slate-400',
};

const formatPrice = (cents: number): string => {
  if (cents <= 0) return '¥0/月';
  const value = cents / 100;
  return `¥${Number.isInteger(value) ? value.toFixed(0) : value.toFixed(2)}/月`;
};

const formatLimitValue = (value: string | number | boolean | null): string => {
  if (typeof value === 'boolean') return value ? '支持' : '不支持';
  if (value == null) return '-';
  return String(value);
};

const usageBarWidth = (ratio?: number | null): string => {
  if (ratio == null || Number.isNaN(ratio)) return '0%';
  return `${Math.max(0, Math.min(100, Math.round(ratio * 100)))}%`;
};

const BillingView: React.FC<BillingViewProps> = ({ onViewChange }) => {
  const [snapshot, setSnapshot] = useState<EntitlementSnapshot | null>(null);
  const [usageSnapshot, setUsageSnapshot] = useState<BillingUsageSnapshot | null>(null);
  const [planCatalog, setPlanCatalog] = useState<PlanCatalogItem[]>([]);
  const [providerCatalog, setProviderCatalog] = useState<BillingProviderItem[]>([]);
  const [notice, setNotice] = useState<{ title: string; detail: string } | null>(null);
  const [loadingPlan, setLoadingPlan] = useState<PlanTier | null>(null);
  const [canceling, setCanceling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadBilling = async () => {
    setError(null);
    try {
      const [nextSnapshot, nextUsage, nextPlans, nextProviders] = await Promise.all([
        BillingAPI.getEntitlements(),
        BillingAPI.getUsage(),
        BillingAPI.getPlans(),
        BillingAPI.getProviders(),
      ]);
      setSnapshot(nextSnapshot);
      setUsageSnapshot(nextUsage);
      setPlanCatalog(nextPlans);
      setProviderCatalog(nextProviders);
    } catch (err) {
      setError(err instanceof Error ? err.message : '权益加载失败。');
    }
  };

  useEffect(() => {
    void loadBilling();
  }, []);

  const handleCheckout = async (plan: PlanTier) => {
    setLoadingPlan(plan);
    setError(null);
    try {
      const session = await BillingAPI.createCheckout(plan);
      setNotice({
        title: session.message,
        detail: `供应商 ${session.provider} · 方案 ${session.plan} · checkout ${session.status}`,
      });
      await loadBilling();
    } catch (err) {
      setError(err instanceof Error ? err.message : '发起模拟 checkout 失败。');
    } finally {
      setLoadingPlan(null);
    }
  };

  const handleCancelSubscription = async () => {
    setCanceling(true);
    setError(null);
    try {
      const result = await BillingAPI.cancelSubscription();
      setSnapshot(result.entitlement);
      setNotice({
        title: result.message,
        detail: `权益已回退至 ${result.plan} · 状态 ${result.status}`,
      });
      await loadBilling();
    } catch (err) {
      setError(err instanceof Error ? err.message : '取消订阅失败。');
    } finally {
      setCanceling(false);
    }
  };

  const features = snapshot?.features || {};
  const snapshotLimits = snapshot?.limits || {};
  const billingPlan = snapshot?.billing_plan || snapshot?.plan || 'FREE';
  const enforcementScope = usageSnapshot?.enforcement_scope || snapshot?.enforcement_scope || 'observe_only';
  const enforcementScopeLabel = enforcementScopeLabelMap[enforcementScope] || enforcementScope;
  const isPaidActive = snapshot?.status === 'active' && billingPlan !== 'FREE';
  const configuredProvider = providerCatalog.find((provider) => provider.is_configured);
  const plans = (['FREE', 'PRO', 'COACH'] as PlanTier[]).map((plan) => ({
    plan,
    catalog: planCatalog.find((item) => item.plan === plan),
  }));

  return (
    <div className="flex min-h-screen w-full flex-col bg-background-dark pb-24">
      <div className="sticky top-0 z-20 border-b border-white/5 bg-[#0c1416]/95 p-4 backdrop-blur-md">
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={() => onViewChange(View.SETTINGS)}
            className="flex h-9 w-9 items-center justify-center rounded-full text-white transition-colors hover:bg-white/5"
            aria-label="返回"
          >
            <span className="material-symbols-outlined">arrow_back</span>
          </button>
          <div className="text-center">
            <h1 className="font-serif text-lg font-bold tracking-wide text-white">订阅与权益</h1>
            <p className="mt-1 font-display text-[10px] uppercase tracking-[0.28em] text-primary/50">BILLING</p>
          </div>
          <button
            type="button"
            onClick={() => void loadBilling()}
            className="flex h-9 w-9 items-center justify-center rounded-full text-white transition-colors hover:bg-white/5"
            aria-label="刷新"
          >
            <span className="material-symbols-outlined">refresh</span>
          </button>
        </div>
      </div>

      <div className="space-y-4 p-4">
        {error && (
          <div className="rounded-xl border border-red-400/20 bg-red-500/10 px-4 py-3 font-serif text-xs leading-relaxed text-red-100">
            {error}
          </div>
        )}

        {notice && (
          <div className="rounded-2xl border border-primary/20 bg-primary/[0.06] p-4">
            <p className="font-serif text-sm font-bold tracking-wide text-white">{notice.title}</p>
            <p className="mt-1 font-serif text-[11px] tracking-wide text-slate-400">{notice.detail}</p>
          </div>
        )}

        <section className="rounded-2xl border border-white/10 bg-[#101719]/80 p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="font-serif text-base font-bold tracking-wide text-white">当前订阅</h2>
              <p className="mt-1 font-serif text-xs tracking-wide text-slate-400">
                生效权益 {snapshot?.plan || 'FREE'} · 账单档位 {billingPlan} · {snapshot?.status || 'inactive'} · {enforcementScopeLabel}
              </p>
            </div>
            {isPaidActive && (
              <button
                type="button"
                onClick={() => void handleCancelSubscription()}
                disabled={canceling}
                className="flex h-9 items-center gap-2 rounded-xl border border-amber-300/20 bg-amber-500/10 px-3 font-serif text-xs font-bold tracking-wide text-amber-100 transition-colors hover:border-amber-300/35 disabled:opacity-50"
              >
                <span className="material-symbols-outlined text-[17px]">
                  {canceling ? 'progress_activity' : 'block'}
                </span>
                取消订阅
              </button>
            )}
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2">
            {Object.entries(snapshotLimits).map(([key, value]) => (
              <div key={key} className="rounded-xl border border-white/5 bg-white/[0.03] px-3 py-2">
                <p className="font-serif text-[10px] font-bold tracking-wide text-slate-500">{limitLabelMap[key] || key}</p>
                <p className="mt-1 font-serif text-sm font-bold tracking-wide text-white">{formatLimitValue(value)}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-white/10 bg-[#101719]/80 p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="font-serif text-base font-bold tracking-wide text-white">本周期用量</h3>
              <p className="mt-1 font-serif text-xs tracking-wide text-slate-400">
                {usageSnapshot?.enforce_limits ? '已启用限制执行' : '灰度观测，不强制拦截'} · {enforcementScopeLabel}
              </p>
            </div>
            <span className="font-serif text-[10px] font-bold tracking-[0.24em] text-slate-500">
              {usageSnapshot?.provider || snapshot?.provider || 'mock'}
            </span>
          </div>
          <div className="mt-4 space-y-3">
            {(usageSnapshot?.usage || []).map(item => (
              <div key={item.key} className="rounded-xl border border-white/5 bg-white/[0.03] px-3 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-serif text-sm font-bold tracking-wide text-white">{item.label}</p>
                    <p className="mt-1 font-serif text-[11px] tracking-wide text-slate-500">
                      {item.period === 'day' ? '今日' : '本月'} · {item.current}/{item.limit ?? '-'}
                    </p>
                  </div>
                  <span className={`rounded-full border px-2 py-1 font-serif text-[10px] font-bold tracking-wide ${usageStatusClass[item.status] || usageStatusClass.unmetered}`}>
                    {usageStatusLabelMap[item.status] || item.status}
                  </span>
                </div>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-black/30">
                  <div
                    className={`h-full rounded-full ${item.status === 'blocked' || item.status === 'over_soft_limit' ? 'bg-amber-300' : 'bg-primary'}`}
                    style={{ width: usageBarWidth(item.usage_ratio) }}
                  />
                </div>
                <p className="mt-2 font-serif text-[10px] tracking-wide text-slate-500">
                  剩余 {item.remaining ?? '-'} · {new Date(item.period_start).toLocaleDateString('zh-CN')} - {new Date(item.period_end).toLocaleDateString('zh-CN')}
                </p>
              </div>
            ))}
          </div>
          <div className="mt-4 space-y-1 border-t border-white/5 pt-3">
            {(usageSnapshot?.notes || []).map(note => (
              <p key={note} className="font-serif text-[11px] leading-relaxed text-slate-500">{note}</p>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-white/10 bg-[#101719]/80 p-4">
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-serif text-base font-bold tracking-wide text-white">支付 Provider</h3>
            <span className="font-serif text-[10px] font-bold tracking-[0.24em] text-slate-500">
              {configuredProvider?.provider || snapshot?.provider || 'mock'}
            </span>
          </div>
          <div className="mt-3 space-y-2">
            {providerCatalog.map((provider) => (
              <div key={provider.provider} className="rounded-xl border border-white/5 bg-white/[0.03] px-3 py-2">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-serif text-sm font-bold tracking-wide text-white">{provider.display_name}</p>
                    <p className="mt-1 font-serif text-[11px] leading-relaxed text-slate-400">{provider.description}</p>
                  </div>
                  <span className={`rounded-full border px-2 py-1 font-serif text-[10px] font-bold tracking-wide ${provider.is_configured ? 'border-primary/20 bg-primary/10 text-primary' : 'border-white/10 bg-white/[0.03] text-slate-300'}`}>
                    {providerStatusLabelMap[provider.status]}
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {Object.entries(providerSupportLabelMap).map(([field, label]) => {
                    const enabled = provider[field as keyof BillingProviderItem] === true;
                    return (
                      <span
                        key={`${provider.provider}-${field}`}
                        className={`rounded-full border px-2 py-1 font-serif text-[10px] font-bold tracking-wide ${enabled ? 'border-emerald-300/20 bg-emerald-500/10 text-emerald-200' : 'border-white/10 bg-white/[0.03] text-slate-500'}`}
                      >
                        {label}
                      </span>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="grid gap-3">
          {plans.map(({ plan, catalog }) => {
            const active = snapshot?.status === 'active' && billingPlan === plan;
            const effective = snapshot?.plan === plan;
            const meta = planMeta[plan];
            const featureEntries = Object.entries(catalog?.features || {});
            const limitEntries = Object.entries(catalog?.limits || {});
            return (
              <article
                key={plan}
                className={`rounded-2xl border p-4 ${active || effective ? 'border-primary/30 bg-primary/[0.06]' : 'border-white/10 bg-[#101719]/80'}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <div className={`flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/[0.03] ${meta.accent}`}>
                      <span className="material-symbols-outlined text-[20px]">{meta.icon}</span>
                    </div>
                    <div>
                      <h2 className="font-serif text-base font-bold tracking-wide text-white">{catalog?.title || meta.title}</h2>
                      <p className="mt-1 font-serif text-xs tracking-wide text-slate-400">{catalog?.subtitle || meta.subtitle}</p>
                      <p className="mt-2 font-serif text-sm font-bold tracking-wide text-white">
                        {catalog ? formatPrice(catalog.monthly_price_cents) : 'mock 定价'}
                      </p>
                    </div>
                  </div>
                  {active ? (
                    <span className="rounded-full border border-primary/20 bg-primary/10 px-2 py-1 font-serif text-[10px] font-bold tracking-wide text-primary">
                      当前
                    </span>
                  ) : effective ? (
                    <span className="rounded-full border border-slate-400/20 bg-white/[0.03] px-2 py-1 font-serif text-[10px] font-bold tracking-wide text-slate-300">
                      生效中
                    </span>
                  ) : catalog?.recommended ? (
                    <span className="rounded-full border border-[#45b7aa]/20 bg-[#45b7aa]/10 px-2 py-1 font-serif text-[10px] font-bold tracking-wide text-[#45b7aa]">
                      推荐
                    </span>
                  ) : null}
                </div>

                <div className="mt-4 grid grid-cols-2 gap-2">
                  {limitEntries.map(([key, value]) => (
                    <div key={`${plan}-${key}`} className="rounded-xl border border-white/5 bg-white/[0.03] px-3 py-2">
                      <p className="font-serif text-[10px] font-bold tracking-wide text-slate-500">{limitLabelMap[key] || key}</p>
                      <p className="mt-1 font-serif text-xs font-bold tracking-wide text-white">{formatLimitValue(value)}</p>
                    </div>
                  ))}
                </div>

                {catalog?.upgrade_reasons?.length ? (
                  <div className="mt-3 space-y-2">
                    {catalog.upgrade_reasons.map((reason) => (
                      <p key={`${plan}-${reason}`} className="font-serif text-xs leading-relaxed text-slate-300">
                        {reason}
                      </p>
                    ))}
                  </div>
                ) : null}

                {featureEntries.length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {featureEntries.filter(([, enabled]) => enabled).slice(0, 4).map(([key]) => (
                      <span key={`${plan}-${key}`} className="rounded-full border border-white/10 bg-white/[0.03] px-2 py-1 font-serif text-[10px] font-bold tracking-wide text-slate-300">
                        {key}
                      </span>
                    ))}
                  </div>
                ) : null}

                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => void handleCheckout(plan)}
                    disabled={loadingPlan === plan || active || plan === 'FREE'}
                    className="flex h-10 items-center gap-2 rounded-xl bg-primary px-4 font-serif text-sm font-bold tracking-wide text-background-dark transition-colors hover:bg-primary/90 disabled:opacity-50"
                  >
                    <span className="material-symbols-outlined text-[18px]">
                      {loadingPlan === plan ? 'progress_activity' : 'shopping_cart'}
                    </span>
                    {plan === 'FREE' ? '默认可用' : active ? '已启用' : '发起模拟 checkout'}
                  </button>
                </div>
              </article>
            );
          })}
        </section>

        <section className="rounded-2xl border border-white/10 bg-[#101719]/80 p-4">
          <div className="flex items-center justify-between">
            <h3 className="font-serif text-base font-bold tracking-wide text-white">当前权益</h3>
            <span className="font-serif text-[10px] font-bold tracking-[0.24em] text-slate-500">
              {snapshot?.provider || 'mock-provider'} · {snapshot?.status || 'inactive'} · {enforcementScopeLabel}
            </span>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2">
            {Object.entries(features).map(([key, enabled]) => (
              <div key={key} className="rounded-xl border border-white/5 bg-white/[0.03] px-3 py-2">
                <p className="font-serif text-[10px] font-bold tracking-wide text-slate-500">{key}</p>
                <p className={`mt-1 font-serif text-sm font-bold tracking-wide ${enabled ? 'text-emerald-300' : 'text-slate-400'}`}>
                  {enabled ? '开启' : '关闭'}
                </p>
              </div>
            ))}
          </div>
          {snapshot?.notes?.length ? (
            <div className="mt-3 space-y-2">
              {snapshot.notes.map((note, index) => (
                <p key={`${note}-${index}`} className="rounded-xl border border-white/5 bg-white/[0.03] px-3 py-2 font-serif text-xs leading-relaxed text-slate-300">
                  {note}
                </p>
              ))}
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
};

export default BillingView;
