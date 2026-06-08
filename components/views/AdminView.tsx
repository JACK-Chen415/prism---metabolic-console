import React, { useEffect, useState } from 'react';
import { AdminAPI } from '../../services/api';
import { AIFeedbackType, AdminActivationMetricsSummary, AdminAITelemetrySummary, AdminCommercializationSummary, AdminFeedbackItem, AdminKnowledgeBacklogSummary, AdminReleaseReadinessSummary, AdminUserItem, FeedbackStatus, KnowledgeAuditItem, PlanTier, SecurityAuditItem, SubscriptionStatus, UserRole, View } from '../../types';

interface AdminViewProps {
  onViewChange: (view: View) => void;
}

type AdminTab = 'readiness' | 'metrics' | 'security' | 'knowledge' | 'backlog' | 'feedback' | 'users' | 'telemetry' | 'commercialization';
type FeedbackFilter = FeedbackStatus | 'all';
type FeedbackTypeFilter = AIFeedbackType | 'all';
type SecurityStatusFilter = 'all' | 'success' | 'limited' | 'revoked_or_reused' | 'denied';
type KnowledgeFallbackFilter =
  | 'all'
  | 'LOCAL_COMPLETE'
  | 'LOCAL_PARTIAL_ALLOW_CLOUD'
  | 'LOCAL_BLOCKED_NO_CLOUD'
  | 'NO_LOCAL_MATCH_ALLOW_CLOUD';
type KnowledgeCloudFilter = 'all' | 'cloud' | 'local';
type UserRoleFilter = UserRole | 'all';
type UserPlanFilter = PlanTier | 'all';
type UserStatusFilter = SubscriptionStatus | 'all';

const formatDate = (value: string) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
};

const formatCounts = (counts?: Record<string, number>, maxItems = 5) => {
  const entries = Object.entries(counts || {}).slice(0, maxItems);
  return entries.length ? entries.map(([key, count]) => `${key}:${count}`).join(' · ') : '-';
};

const readinessStatusLabel: Record<AdminReleaseReadinessSummary['status'], string> = {
  green: '可控',
  yellow: '观察',
  red: '暂停',
};

const readinessStatusClass: Record<AdminReleaseReadinessSummary['status'], string> = {
  green: 'border-emerald-300/25 bg-emerald-500/10 text-emerald-200',
  yellow: 'border-amber-300/25 bg-amber-500/10 text-amber-100',
  red: 'border-red-400/25 bg-red-500/10 text-red-200',
};

const gateStatusClass: Record<string, string> = {
  pass: 'border-emerald-300/20 bg-emerald-500/10 text-emerald-200',
  warn: 'border-amber-300/25 bg-amber-500/10 text-amber-100',
  block: 'border-red-400/25 bg-red-500/10 text-red-200',
};

const gateStatusLabel: Record<string, string> = {
  pass: '通过',
  warn: '观察',
  block: '阻断',
};

const AdminView: React.FC<AdminViewProps> = ({ onViewChange }) => {
  const [tab, setTab] = useState<AdminTab>('readiness');
  const [securityRows, setSecurityRows] = useState<SecurityAuditItem[]>([]);
  const [knowledgeRows, setKnowledgeRows] = useState<KnowledgeAuditItem[]>([]);
  const [knowledgeBacklog, setKnowledgeBacklog] = useState<AdminKnowledgeBacklogSummary | null>(null);
  const [feedbackRows, setFeedbackRows] = useState<AdminFeedbackItem[]>([]);
  const [userRows, setUserRows] = useState<AdminUserItem[]>([]);
  const [aiTelemetry, setAiTelemetry] = useState<AdminAITelemetrySummary | null>(null);
  const [releaseReadiness, setReleaseReadiness] = useState<AdminReleaseReadinessSummary | null>(null);
  const [activationMetrics, setActivationMetrics] = useState<AdminActivationMetricsSummary | null>(null);
  const [commercializationSummary, setCommercializationSummary] = useState<AdminCommercializationSummary | null>(null);
  const [securityQuery, setSecurityQuery] = useState('');
  const [securityStatusFilter, setSecurityStatusFilter] = useState<SecurityStatusFilter>('all');
  const [knowledgeQuery, setKnowledgeQuery] = useState('');
  const [knowledgeFallbackFilter, setKnowledgeFallbackFilter] = useState<KnowledgeFallbackFilter>('all');
  const [knowledgeCloudFilter, setKnowledgeCloudFilter] = useState<KnowledgeCloudFilter>('all');
  const [feedbackFilter, setFeedbackFilter] = useState<FeedbackFilter>('all');
  const [feedbackTypeFilter, setFeedbackTypeFilter] = useState<FeedbackTypeFilter>('all');
  const [userQuery, setUserQuery] = useState('');
  const [userRoleFilter, setUserRoleFilter] = useState<UserRoleFilter>('all');
  const [userPlanFilter, setUserPlanFilter] = useState<UserPlanFilter>('all');
  const [userStatusFilter, setUserStatusFilter] = useState<UserStatusFilter>('all');
  const [isLoading, setIsLoading] = useState(false);
  const [isSecurityLoading, setIsSecurityLoading] = useState(false);
  const [isKnowledgeLoading, setIsKnowledgeLoading] = useState(false);
  const [isBacklogLoading, setIsBacklogLoading] = useState(false);
  const [isFeedbackLoading, setIsFeedbackLoading] = useState(false);
  const [isUserLoading, setIsUserLoading] = useState(false);
  const [loadingFeedbackId, setLoadingFeedbackId] = useState<number | null>(null);
  const [loadingUserId, setLoadingUserId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const securityQueryValue = securityQuery.trim() || undefined;
  const securityStatusValue = securityStatusFilter === 'all' ? undefined : securityStatusFilter;
  const knowledgeQueryValue = knowledgeQuery.trim() || undefined;
  const knowledgeFallbackValue = knowledgeFallbackFilter === 'all' ? undefined : knowledgeFallbackFilter;
  const knowledgeCalledCloudValue = knowledgeCloudFilter === 'all' ? undefined : knowledgeCloudFilter === 'cloud';
  const userQueryValue = userQuery.trim() || undefined;
  const userRoleValue = userRoleFilter === 'all' ? undefined : userRoleFilter;
  const userPlanValue = userPlanFilter === 'all' ? undefined : userPlanFilter;
  const userStatusValue = userStatusFilter === 'all' ? undefined : userStatusFilter;

  const loadSecurityRows = async (
    nextQuery: string | undefined = securityQueryValue,
    nextStatus: SecurityStatusFilter = securityStatusFilter,
  ) => {
    setIsSecurityLoading(true);
    setError(null);
    try {
      const security = await AdminAPI.listSecurityAudit(
        30,
        nextQuery,
        nextStatus === 'all' ? undefined : nextStatus,
      );
      setSecurityRows(security);
    } catch (err) {
      setError(err instanceof Error ? err.message : '安全审计加载失败。');
      setSecurityRows([]);
    } finally {
      setIsSecurityLoading(false);
    }
  };

  const loadKnowledgeRows = async (
    nextQuery: string | undefined = knowledgeQueryValue,
    nextFallback: KnowledgeFallbackFilter = knowledgeFallbackFilter,
    nextCloud: KnowledgeCloudFilter = knowledgeCloudFilter,
  ) => {
    setIsKnowledgeLoading(true);
    setError(null);
    try {
      const knowledge = await AdminAPI.listKnowledgeAudit(
        30,
        nextQuery,
        undefined,
        nextFallback === 'all' ? undefined : nextFallback,
        nextCloud === 'all' ? undefined : nextCloud === 'cloud',
      );
      setKnowledgeRows(knowledge);
    } catch (err) {
      setError(err instanceof Error ? err.message : '知识审计加载失败。');
      setKnowledgeRows([]);
    } finally {
      setIsKnowledgeLoading(false);
    }
  };

  const loadKnowledgeBacklog = async () => {
    setIsBacklogLoading(true);
    setError(null);
    try {
      const backlog = await AdminAPI.getKnowledgeBacklog(50);
      setKnowledgeBacklog(backlog);
    } catch (err) {
      setError(err instanceof Error ? err.message : '知识改进待办加载失败。');
      setKnowledgeBacklog(null);
    } finally {
      setIsBacklogLoading(false);
    }
  };

  const loadFeedbackRows = async (
    nextFilter: FeedbackFilter = feedbackFilter,
    nextType: FeedbackTypeFilter = feedbackTypeFilter,
  ) => {
    setIsFeedbackLoading(true);
    setError(null);
    try {
      const feedback = await AdminAPI.listFeedback(
        nextFilter === 'all' ? undefined : nextFilter,
        30,
        nextType === 'all' ? undefined : nextType,
      );
      setFeedbackRows(feedback);
    } catch (err) {
      setError(err instanceof Error ? err.message : '反馈列表加载失败。');
      setFeedbackRows([]);
    } finally {
      setIsFeedbackLoading(false);
    }
  };

  const loadUserRows = async (
    nextQuery: string | undefined = userQueryValue,
    nextRole: UserRoleFilter = userRoleFilter,
    nextPlan: UserPlanFilter = userPlanFilter,
    nextStatus: UserStatusFilter = userStatusFilter,
  ) => {
    setIsUserLoading(true);
    setError(null);
    try {
      const users = await AdminAPI.listUsers(30, {
        q: nextQuery,
        role: nextRole === 'all' ? undefined : nextRole,
        subscriptionPlan: nextPlan === 'all' ? undefined : nextPlan,
        subscriptionStatus: nextStatus === 'all' ? undefined : nextStatus,
      });
      setUserRows(users);
    } catch (err) {
      setError(err instanceof Error ? err.message : '用户列表加载失败。');
      setUserRows([]);
    } finally {
      setIsUserLoading(false);
    }
  };

  const loadAudit = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [security, knowledge, backlog, feedback, users, telemetry, readiness, activation, commercialization] = await Promise.all([
        AdminAPI.listSecurityAudit(30, securityQueryValue, securityStatusValue),
        AdminAPI.listKnowledgeAudit(
          30,
          knowledgeQueryValue,
          undefined,
          knowledgeFallbackValue,
          knowledgeCalledCloudValue,
        ),
        AdminAPI.getKnowledgeBacklog(50),
        AdminAPI.listFeedback(
          feedbackFilter === 'all' ? undefined : feedbackFilter,
          30,
          feedbackTypeFilter === 'all' ? undefined : feedbackTypeFilter,
        ),
        AdminAPI.listUsers(30, {
          q: userQueryValue,
          role: userRoleValue,
          subscriptionPlan: userPlanValue,
          subscriptionStatus: userStatusValue,
        }),
        AdminAPI.getAITelemetry(50),
        AdminAPI.getReleaseReadiness(50),
        AdminAPI.getActivationMetrics(7),
        AdminAPI.getCommercializationSummary(30),
      ]);
      setSecurityRows(security);
      setKnowledgeRows(knowledge);
      setKnowledgeBacklog(backlog);
      setFeedbackRows(feedback);
      setUserRows(users);
      setAiTelemetry(telemetry);
      setReleaseReadiness(readiness);
      setActivationMetrics(activation);
      setCommercializationSummary(commercialization);
    } catch (err) {
      setError(err instanceof Error ? err.message : '运营审计加载失败。');
      setSecurityRows([]);
      setKnowledgeRows([]);
      setKnowledgeBacklog(null);
      setFeedbackRows([]);
      setUserRows([]);
      setAiTelemetry(null);
      setReleaseReadiness(null);
      setActivationMetrics(null);
      setCommercializationSummary(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadAudit();
  }, []);

  const handleSecuritySearch = () => {
    void loadSecurityRows(securityQueryValue, securityStatusFilter);
  };

  const handleSecurityStatusChange = (nextStatus: SecurityStatusFilter) => {
    setSecurityStatusFilter(nextStatus);
    void loadSecurityRows(securityQueryValue, nextStatus);
  };

  const handleKnowledgeSearch = () => {
    void loadKnowledgeRows(knowledgeQueryValue, knowledgeFallbackFilter, knowledgeCloudFilter);
  };

  const handleKnowledgeFallbackChange = (nextFallback: KnowledgeFallbackFilter) => {
    setKnowledgeFallbackFilter(nextFallback);
    void loadKnowledgeRows(knowledgeQueryValue, nextFallback, knowledgeCloudFilter);
  };

  const handleKnowledgeCloudChange = (nextCloud: KnowledgeCloudFilter) => {
    setKnowledgeCloudFilter(nextCloud);
    void loadKnowledgeRows(knowledgeQueryValue, knowledgeFallbackFilter, nextCloud);
  };

  const handleFeedbackFilterChange = (nextFilter: FeedbackFilter) => {
    setFeedbackFilter(nextFilter);
    void loadFeedbackRows(nextFilter, feedbackTypeFilter);
  };

  const handleFeedbackTypeChange = (nextType: FeedbackTypeFilter) => {
    setFeedbackTypeFilter(nextType);
    void loadFeedbackRows(feedbackFilter, nextType);
  };

  const handleUserSearch = () => {
    void loadUserRows(userQueryValue, userRoleFilter, userPlanFilter, userStatusFilter);
  };

  const requiresUnsafeReviewBeforeClose = (
    row: { feedback_type?: string | null; status?: string | null },
    nextStatus: FeedbackStatus,
  ) => (
    row.feedback_type === 'unsafe' && row.status === 'open' && nextStatus === 'closed'
  );

  const updateFeedbackStatus = async (feedbackId: number, status: FeedbackStatus) => {
    setLoadingFeedbackId(feedbackId);
    setError(null);
    try {
      const updated = await AdminAPI.updateFeedbackStatus(feedbackId, status);
      setFeedbackRows(prev => {
        const nextRows = prev.map(row => (row.id === feedbackId ? updated : row));
        if (feedbackFilter !== 'all' && updated.status !== feedbackFilter) {
          return nextRows.filter(row => row.id !== feedbackId);
        }
        return nextRows;
      });
      await loadKnowledgeBacklog();
    } catch (err) {
      setError(err instanceof Error ? err.message : '反馈状态更新失败。');
    } finally {
      setLoadingFeedbackId(null);
    }
  };

  const updateUserRole = async (userId: number, role: UserRole) => {
    setLoadingUserId(userId);
    setError(null);
    try {
      await AdminAPI.updateUserRole(userId, role);
      await loadUserRows(userQueryValue, userRoleFilter, userPlanFilter, userStatusFilter);
    } catch (err) {
      setError(err instanceof Error ? err.message : '用户角色更新失败。');
    } finally {
      setLoadingUserId(null);
    }
  };

  const activationDailyMax = Math.max(
    1,
    ...(activationMetrics?.daily_activity || []).map(day => Math.max(day.meals, day.assistant_messages, day.feedback)),
  );

  const releaseReadinessActionGates = [
    ...(releaseReadiness?.action_items?.length
      ? releaseReadiness.action_items
      : releaseReadiness?.gate_items || [])
  ]
    .filter(item => item.status === 'block' || item.status === 'warn')
    .sort((left, right) => {
      const severity: Record<'block' | 'warn' | 'pass', number> = { block: 2, warn: 1, pass: 0 };
      return severity[right.status] - severity[left.status] || right.count - left.count;
    })
    .slice(0, 3);

  const updateUserSubscription = async (userId: number, plan: PlanTier, status: SubscriptionStatus = 'active') => {
    setLoadingUserId(userId);
    setError(null);
    try {
      await AdminAPI.updateUserSubscription(userId, plan, plan === 'FREE' ? 'inactive' : status);
      await loadUserRows(userQueryValue, userRoleFilter, userPlanFilter, userStatusFilter);
    } catch (err) {
      setError(err instanceof Error ? err.message : '用户订阅更新失败。');
    } finally {
      setLoadingUserId(null);
    }
  };

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
            <h1 className="font-serif text-lg font-bold tracking-wide text-white">运营后台</h1>
            <p className="mt-1 font-display text-[10px] uppercase tracking-[0.28em] text-primary/50">ADMIN</p>
          </div>
          <button
            type="button"
            onClick={() => void loadAudit()}
            disabled={isLoading}
            className="flex h-9 w-9 items-center justify-center rounded-full text-white transition-colors hover:bg-white/5 disabled:opacity-40"
            aria-label="刷新"
          >
            <span className={`material-symbols-outlined ${isLoading ? 'animate-spin' : ''}`}>
              {isLoading ? 'progress_activity' : 'refresh'}
            </span>
          </button>
        </div>
      </div>

      <div className="space-y-4 p-4">
        <section className="rounded-2xl border border-white/10 bg-[#101719]/80 p-4">
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-xl border border-white/5 bg-white/[0.03] p-3">
              <p className="font-serif text-[10px] font-bold tracking-[0.2em] text-slate-500">安全审计</p>
              <p className="mt-1 font-serif text-2xl font-bold text-white">{securityRows.length}</p>
            </div>
            <div className="rounded-xl border border-white/5 bg-white/[0.03] p-3">
              <p className="font-serif text-[10px] font-bold tracking-[0.2em] text-slate-500">知识审计</p>
              <p className="mt-1 font-serif text-2xl font-bold text-white">{knowledgeRows.length}</p>
            </div>
            <div className="rounded-xl border border-white/5 bg-white/[0.03] p-3">
              <p className="font-serif text-[10px] font-bold tracking-[0.2em] text-slate-500">知识待办</p>
              <p className="mt-1 font-serif text-2xl font-bold text-white">{knowledgeBacklog?.recent_items.length ?? 0}</p>
            </div>
            <div className="rounded-xl border border-white/5 bg-white/[0.03] p-3">
              <p className="font-serif text-[10px] font-bold tracking-[0.2em] text-slate-500">待审反馈</p>
              <p className="mt-1 font-serif text-2xl font-bold text-white">{feedbackRows.filter(row => row.status === 'open').length}</p>
            </div>
            <div className="rounded-xl border border-white/5 bg-white/[0.03] p-3">
              <p className="font-serif text-[10px] font-bold tracking-[0.2em] text-slate-500">用户角色</p>
              <p className="mt-1 font-serif text-2xl font-bold text-white">{userRows.length}</p>
            </div>
            <div className="rounded-xl border border-white/5 bg-white/[0.03] p-3">
              <p className="font-serif text-[10px] font-bold tracking-[0.2em] text-slate-500">AI 云端</p>
              <p className="mt-1 font-serif text-2xl font-bold text-white">{aiTelemetry?.cloud_call_count ?? 0}</p>
            </div>
            <div className="rounded-xl border border-white/5 bg-white/[0.03] p-3">
              <p className="font-serif text-[10px] font-bold tracking-[0.2em] text-slate-500">AI 失败</p>
              <p className="mt-1 font-serif text-2xl font-bold text-white">{aiTelemetry?.error_count ?? 0}</p>
            </div>
            <div className="rounded-xl border border-white/5 bg-white/[0.03] p-3">
              <p className="font-serif text-[10px] font-bold tracking-[0.2em] text-slate-500">付费活跃</p>
              <p className="mt-1 font-serif text-2xl font-bold text-white">{commercializationSummary?.active_paid_users ?? 0}</p>
            </div>
            <div className="col-span-2 rounded-xl border border-white/5 bg-white/[0.03] p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="font-serif text-[10px] font-bold tracking-[0.2em] text-slate-500">灰度状态</p>
                  <p className="mt-1 font-serif text-2xl font-bold text-white">
                    {releaseReadiness ? readinessStatusLabel[releaseReadiness.status] : '-'}
                  </p>
                </div>
                <span className={`rounded-full border px-3 py-1 font-serif text-[10px] font-bold tracking-wide ${releaseReadiness ? readinessStatusClass[releaseReadiness.status] : 'border-white/10 bg-white/[0.03] text-slate-400'}`}>
                  {releaseReadiness?.status || 'unknown'}
                </span>
              </div>
              <p className="mt-2 font-serif text-[11px] leading-relaxed text-slate-500">
                阻断 {releaseReadiness?.blocker_count ?? 0} · 观察 {releaseReadiness?.warning_count ?? 0}
              </p>
            </div>
          </div>
          <p className="mt-3 font-serif text-xs leading-relaxed text-slate-400">
            后台仅显示哈希与结构化审计字段，管理员权限由后端角色或 allowlist 判定。
          </p>
        </section>

        {error && (
          <div className="rounded-xl border border-amber-300/20 bg-amber-500/10 px-4 py-3 font-serif text-xs leading-relaxed text-amber-100">
            {error}
          </div>
        )}

        <div className="flex gap-1 overflow-x-auto rounded-xl border border-white/10 bg-surface-dark p-1 no-scrollbar">
          {([
            ['readiness', '灰度门禁'],
            ['metrics', '激活指标'],
            ['security', '安全审计'],
            ['knowledge', '知识审计'],
            ['backlog', '知识改进'],
            ['telemetry', 'AI 监控'],
            ['commercialization', '商业化概览'],
            ['feedback', '反馈闭环'],
            ['users', '用户角色'],
          ] as [AdminTab, string][]).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setTab(value)}
              className={`min-w-[88px] flex-1 rounded-lg px-2 py-2 font-serif text-sm font-bold tracking-wide transition-colors ${tab === value
                ? 'bg-primary/10 text-primary'
                : 'text-slate-400 hover:bg-white/5'
                }`}
            >
              {label}
            </button>
          ))}
        </div>

        {tab === 'metrics' && (
          <section className="space-y-3">
            <article className="rounded-2xl border border-white/10 bg-[#101719]/80 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-serif text-sm font-bold tracking-wide text-white">灰度激活指标</p>
                  <p className="mt-1 font-serif text-[11px] tracking-wide text-slate-500">
                    最近 {activationMetrics?.window_days ?? 7} 天的聚合使用趋势
                  </p>
                </div>
                <span className="rounded-full border border-primary/20 bg-primary/10 px-2 py-1 font-serif text-[10px] font-bold tracking-wide text-primary">
                  {activationMetrics ? `${activationMetrics.window_days}d` : 'loading'}
                </span>
              </div>

              <div className="mt-4 grid grid-cols-3 gap-2">
                {[
                  ['总用户', activationMetrics?.total_users ?? 0],
                  ['活跃用户', activationMetrics?.active_users ?? 0],
                  ['已验证', activationMetrics?.verified_users ?? 0],
                  ['新增用户', activationMetrics?.new_users ?? 0],
                  ['付费活跃', activationMetrics?.paid_active_users ?? 0],
                  ['记餐用户', activationMetrics?.meal_users ?? 0],
                  ['聊天会话', activationMetrics?.chat_session_count ?? 0],
                  ['AI 回复', activationMetrics?.assistant_message_count ?? 0],
                  ['反馈', activationMetrics?.feedback_count ?? 0],
                  ['复核快照', activationMetrics?.intake_review_telemetry.snapshot_count ?? 0],
                  ['待复核', (activationMetrics?.intake_review_telemetry.pending_review_count ?? 0) + (activationMetrics?.intake_review_telemetry.in_review_count ?? 0)],
                  ['风险候选', activationMetrics?.intake_review_telemetry.high_risk_count ?? 0],
                ].map(([label, value]) => (
                  <div key={label as string} className="rounded-xl border border-white/5 bg-white/[0.03] px-3 py-2 text-center">
                    <p className="font-serif text-[10px] font-bold tracking-wide text-slate-500">{label as string}</p>
                    <p className="mt-1 font-serif text-lg font-bold tracking-wide text-white">{value as number}</p>
                  </div>
                ))}
              </div>

              <div className="mt-4 space-y-2">
                {(activationMetrics?.daily_activity || []).map(day => {
                  const mealHeight = Math.max(8, Math.round((day.meals / activationDailyMax) * 72));
                  const chatHeight = Math.max(8, Math.round((day.assistant_messages / activationDailyMax) * 72));
                  const feedbackHeight = Math.max(8, Math.round((day.feedback / activationDailyMax) * 72));
                  return (
                    <div key={day.date} className="rounded-xl border border-white/5 bg-black/20 px-3 py-3">
                      <div className="flex items-center justify-between gap-3">
                        <p className="font-serif text-[11px] font-bold tracking-wide text-white">{day.date}</p>
                        <p className="font-serif text-[10px] tracking-wide text-slate-500">餐 {day.meals} · 聊天 {day.assistant_messages} · 反馈 {day.feedback}</p>
                      </div>
                      <div className="mt-3 grid grid-cols-3 gap-2">
                        {[
                          ['餐', mealHeight, 'bg-primary/80'],
                          ['聊', chatHeight, 'bg-emerald-400/80'],
                          ['反', feedbackHeight, 'bg-amber-300/80'],
                        ].map(([label, height, color]) => (
                          <div key={label as string} className="flex h-20 flex-col justify-end rounded-lg border border-white/5 bg-white/[0.02] p-2">
                            <div className={`rounded-t-md ${color as string}`} style={{ height: `${height}px` }} />
                            <p className="mt-2 text-center font-serif text-[10px] font-bold tracking-wide text-slate-500">{label as string}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="mt-4 space-y-1 border-t border-white/5 pt-3">
                {(activationMetrics?.notes || []).map(note => (
                  <p key={note} className="font-serif text-[11px] leading-relaxed text-slate-500">{note}</p>
                ))}
              </div>
            </article>
          </section>
        )}

        {tab === 'readiness' && (
          <section className="space-y-3">
            <article className="rounded-2xl border border-white/10 bg-[#101719]/80 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-serif text-sm font-bold tracking-wide text-white">灰度发布门禁</p>
                  <p className="mt-1 font-serif text-[11px] tracking-wide text-slate-500">
                    最近 {releaseReadiness?.window_limit ?? 50} 条结构化样本
                  </p>
                </div>
                <span className={`rounded-full border px-3 py-1 font-serif text-[10px] font-bold tracking-wide ${releaseReadiness ? readinessStatusClass[releaseReadiness.status] : 'border-white/10 bg-white/[0.03] text-slate-400'}`}>
                  {releaseReadiness ? readinessStatusLabel[releaseReadiness.status] : '加载中'}
                </span>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-6">
                {[
                  ['阻断项', releaseReadiness?.blocker_count ?? 0],
                  ['观察项', releaseReadiness?.warning_count ?? 0],
                  ['AI 样本', releaseReadiness?.signals.sampled_ai_messages ?? 0],
                  ['食物待审', releaseReadiness?.signals.food_nutrition_problem_count ?? 0],
                  ['同步异常', releaseReadiness?.signals.offline_sync_problem_count ?? 0],
                  ['复核积压', releaseReadiness?.signals.intake_review_backlog_count ?? 0],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-xl border border-white/5 bg-white/[0.03] px-3 py-2 text-center">
                    <p className="font-serif text-[10px] font-bold tracking-wide text-slate-500">{label}</p>
                    <p className="mt-1 font-serif text-lg font-bold tracking-wide text-white">{value}</p>
                  </div>
                ))}
              </div>

              <div className="mt-4 rounded-xl border border-white/5 bg-black/20 px-3 py-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="font-serif text-[11px] font-bold tracking-[0.2em] text-slate-400">处置优先级</p>
                  <span className="rounded-full border border-white/10 bg-white/[0.03] px-2 py-1 font-serif text-[10px] font-bold tracking-wide text-slate-500">
                    TOP {releaseReadinessActionGates.length || 0}
                  </span>
                </div>
                <div className="mt-3 space-y-2">
                  {releaseReadinessActionGates.length ? releaseReadinessActionGates.map(item => (
                    <div key={`action-${item.key}`} className="grid grid-cols-[auto_1fr_auto] items-start gap-2 rounded-lg border border-white/5 bg-white/[0.03] px-3 py-2">
                      <span className={`rounded-full border px-2 py-1 font-serif text-[10px] font-bold tracking-wide ${gateStatusClass[item.status] || gateStatusClass.pass}`}>
                        {gateStatusLabel[item.status] || item.status}
                      </span>
                      <div className="min-w-0">
                        <p className="font-serif text-xs font-bold tracking-wide text-white">{item.label}</p>
                        <p className="mt-1 font-serif text-[11px] leading-relaxed text-slate-400">{item.message}</p>
                      </div>
                      <span className="font-serif text-xs font-bold tracking-wide text-slate-300">{item.count}</span>
                    </div>
                  )) : (
                    <p className="rounded-lg border border-emerald-300/10 bg-emerald-500/5 px-3 py-2 font-serif text-[11px] leading-relaxed text-emerald-100">
                      暂无阻断或观察门禁
                    </p>
                  )}
                </div>
              </div>

              <div className="mt-4 space-y-2">
                {(releaseReadiness?.gate_items || []).map(item => (
                  <div key={item.key} className="rounded-xl border border-white/5 bg-black/20 px-3 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-serif text-sm font-bold tracking-wide text-white">{item.label}</p>
                        <p className="mt-1 font-serif text-[11px] leading-relaxed text-slate-400">{item.message}</p>
                      </div>
                      <span className={`shrink-0 rounded-full border px-2 py-1 font-serif text-[10px] font-bold tracking-wide ${gateStatusClass[item.status] || gateStatusClass.pass}`}>
                        {gateStatusLabel[item.status] || item.status}
                      </span>
                    </div>
                    <p className="mt-2 font-serif text-[10px] tracking-wide text-slate-500">
                      当前 {item.count} · 观察阈值 {item.warn_threshold} · 阻断阈值 {item.block_threshold}
                    </p>
                  </div>
                ))}
              </div>

              <div className="mt-4 space-y-1 border-t border-white/5 pt-3">
                {(releaseReadiness?.notes || []).map(note => (
                  <p key={note} className="font-serif text-[11px] leading-relaxed text-slate-500">{note}</p>
                ))}
              </div>
            </article>
          </section>
        )}

        {tab === 'security' && (
          <section className="space-y-3">
            <div className="rounded-2xl border border-white/10 bg-[#101719]/80 p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="font-serif text-sm font-bold tracking-wide text-white">安全审计筛选</p>
                  <p className="mt-1 font-serif text-[11px] tracking-wide text-slate-500">
                    当前 {securityRows.length} 条 · {securityQueryValue || '全部事件'} · {securityStatusFilter === 'all' ? '全部状态' : securityStatusFilter}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleSecuritySearch}
                  disabled={isSecurityLoading}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/[0.03] text-slate-300 transition-colors hover:border-primary/25 hover:text-primary disabled:opacity-50"
                  aria-label="搜索安全审计"
                  title="搜索安全审计"
                >
                  <span className={`material-symbols-outlined text-[18px] ${isSecurityLoading ? 'animate-spin' : ''}`}>
                    {isSecurityLoading ? 'progress_activity' : 'manage_search'}
                  </span>
                </button>
              </div>
              <div className="mt-3 grid grid-cols-[1fr_auto] gap-2">
                <input
                  type="search"
                  value={securityQuery}
                  onChange={(event) => setSecurityQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      handleSecuritySearch();
                    }
                  }}
                  placeholder="搜索 auth、otp、report、account..."
                  className="min-w-0 rounded-xl border border-white/10 bg-black/20 px-3 py-2 font-serif text-xs font-bold tracking-wide text-white outline-none transition-colors placeholder:text-slate-600 focus:border-primary/40"
                />
                <button
                  type="button"
                  onClick={() => {
                    setSecurityQuery('');
                    void loadSecurityRows(undefined, securityStatusFilter);
                  }}
                  disabled={isSecurityLoading || !securityQuery}
                  className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 font-serif text-[11px] font-bold tracking-wide text-slate-300 transition-colors hover:border-primary/25 hover:text-primary disabled:opacity-40"
                >
                  清空
                </button>
              </div>
              <div className="mt-3 grid grid-cols-5 gap-2">
                {([
                  ['all', '全部'],
                  ['success', '成功'],
                  ['limited', '限流'],
                  ['revoked_or_reused', '复用'],
                  ['denied', '拒绝'],
                ] as [SecurityStatusFilter, string][]).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => handleSecurityStatusChange(value)}
                    disabled={isSecurityLoading && securityStatusFilter === value}
                    className={`min-w-0 rounded-xl border px-2 py-2 font-serif text-[11px] font-bold tracking-wide transition-colors ${securityStatusFilter === value
                      ? 'border-primary/30 bg-primary/10 text-primary'
                      : 'border-white/10 bg-white/[0.03] text-slate-300 hover:border-primary/25 hover:text-primary'
                      } disabled:opacity-50`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {isSecurityLoading && (
              <div className="rounded-xl border border-white/10 bg-[#101719]/80 px-4 py-6 text-center font-serif text-xs font-bold tracking-wide text-slate-500">
                正在加载安全审计...
              </div>
            )}

            {!isSecurityLoading && securityRows.length === 0 && (
              <div className="rounded-xl border border-white/10 bg-[#101719]/80 px-4 py-6 text-center font-serif text-xs leading-relaxed text-slate-400">
                当前筛选下暂无安全审计记录。
              </div>
            )}

            {!isSecurityLoading && securityRows.map(row => (
              <article key={row.id} className="rounded-2xl border border-white/10 bg-[#101719]/80 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-serif text-sm font-bold tracking-wide text-white">{row.event_type}</p>
                    <p className="mt-1 font-serif text-[11px] tracking-wide text-slate-500">{row.route_name || 'unknown route'}</p>
                  </div>
                  <span className={`rounded-full border px-2 py-1 font-serif text-[10px] font-bold tracking-wide ${row.event_status === 'success' ? 'border-emerald-300/20 text-emerald-300' : 'border-amber-300/20 text-amber-200'}`}>
                    {row.event_status}
                  </span>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 font-serif text-[11px] tracking-wide text-slate-400">
                  <span>用户 {row.user_id ?? '-'}</span>
                  <span>{formatDate(row.created_at)}</span>
                  <span className="truncate">IP {row.ip_hash || '-'}</span>
                  <span className="truncate">会话 {row.session_id || '-'}</span>
                </div>
              </article>
            ))}
          </section>
        )}

        {tab === 'knowledge' && (
          <section className="space-y-3">
            <div className="rounded-2xl border border-white/10 bg-[#101719]/80 p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="font-serif text-sm font-bold tracking-wide text-white">知识审计筛选</p>
                  <p className="mt-1 font-serif text-[11px] tracking-wide text-slate-500">
                    当前 {knowledgeRows.length} 条 · {knowledgeQueryValue || '全部路由'} · {knowledgeFallbackFilter === 'all' ? '全部回退' : knowledgeFallbackFilter} · {knowledgeCloudFilter === 'all' ? '全部云端' : knowledgeCloudFilter}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleKnowledgeSearch}
                  disabled={isKnowledgeLoading}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/[0.03] text-slate-300 transition-colors hover:border-primary/25 hover:text-primary disabled:opacity-50"
                  aria-label="搜索知识审计"
                  title="搜索知识审计"
                >
                  <span className={`material-symbols-outlined text-[18px] ${isKnowledgeLoading ? 'animate-spin' : ''}`}>
                    {isKnowledgeLoading ? 'progress_activity' : 'travel_explore'}
                  </span>
                </button>
              </div>
              <div className="mt-3 grid grid-cols-[1fr_auto] gap-2">
                <input
                  type="search"
                  value={knowledgeQuery}
                  onChange={(event) => setKnowledgeQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      handleKnowledgeSearch();
                    }
                  }}
                  placeholder="搜索 /api/chat、fallback、blocked..."
                  className="min-w-0 rounded-xl border border-white/10 bg-black/20 px-3 py-2 font-serif text-xs font-bold tracking-wide text-white outline-none transition-colors placeholder:text-slate-600 focus:border-primary/40"
                />
                <button
                  type="button"
                  onClick={() => {
                    setKnowledgeQuery('');
                    void loadKnowledgeRows(undefined, knowledgeFallbackFilter, knowledgeCloudFilter);
                  }}
                  disabled={isKnowledgeLoading || !knowledgeQuery}
                  className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 font-serif text-[11px] font-bold tracking-wide text-slate-300 transition-colors hover:border-primary/25 hover:text-primary disabled:opacity-40"
                >
                  清空
                </button>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2">
                {([
                  ['all', '全部云端'],
                  ['cloud', '已调用云端'],
                  ['local', '本地处理'],
                ] as [KnowledgeCloudFilter, string][]).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => handleKnowledgeCloudChange(value)}
                    disabled={isKnowledgeLoading && knowledgeCloudFilter === value}
                    className={`min-w-0 rounded-xl border px-2 py-2 font-serif text-[11px] font-bold tracking-wide transition-colors ${knowledgeCloudFilter === value
                      ? 'border-[#45b7aa]/30 bg-[#45b7aa]/10 text-[#45b7aa]'
                      : 'border-white/10 bg-white/[0.03] text-slate-300 hover:border-[#45b7aa]/25 hover:text-[#45b7aa]'
                      } disabled:opacity-50`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2">
                {([
                  ['all', '全部回退'],
                  ['LOCAL_COMPLETE', '本地完整'],
                  ['LOCAL_PARTIAL_ALLOW_CLOUD', '本地部分+云端'],
                  ['LOCAL_BLOCKED_NO_CLOUD', '本地阻断'],
                  ['NO_LOCAL_MATCH_ALLOW_CLOUD', '无本地匹配+云端'],
                ] as [KnowledgeFallbackFilter, string][]).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => handleKnowledgeFallbackChange(value)}
                    disabled={isKnowledgeLoading && knowledgeFallbackFilter === value}
                    className={`min-w-0 rounded-xl border px-2 py-2 font-serif text-[10px] font-bold tracking-wide transition-colors ${knowledgeFallbackFilter === value
                      ? 'border-primary/30 bg-primary/10 text-primary'
                      : 'border-white/10 bg-white/[0.03] text-slate-300 hover:border-primary/25 hover:text-primary'
                      } disabled:opacity-50`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {isKnowledgeLoading && (
              <div className="rounded-xl border border-white/10 bg-[#101719]/80 px-4 py-6 text-center font-serif text-xs font-bold tracking-wide text-slate-500">
                正在加载知识审计...
              </div>
            )}

            {!isKnowledgeLoading && knowledgeRows.length === 0 && (
              <div className="rounded-xl border border-white/10 bg-[#101719]/80 px-4 py-6 text-center font-serif text-xs leading-relaxed text-slate-400">
                当前筛选下暂无知识审计记录。
              </div>
            )}

            {!isKnowledgeLoading && knowledgeRows.map(row => (
              <article key={row.id} className="rounded-2xl border border-white/10 bg-[#101719]/80 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-serif text-sm font-bold tracking-wide text-white">{row.origin}</p>
                    <p className="mt-1 font-serif text-[11px] tracking-wide text-slate-500">{row.route_name}</p>
                  </div>
                  <span className="rounded-full border border-white/10 bg-white/[0.03] px-2 py-1 font-serif text-[10px] font-bold tracking-wide text-slate-300">
                    {row.fallback_status}
                  </span>
                </div>
                <div className="mt-3 space-y-2 font-serif text-[11px] tracking-wide text-slate-400">
                  <p>病种：{row.matched_disease_codes.join('、') || '-'}</p>
                  <p>食物：{row.matched_food_codes.join('、') || '-'}</p>
                  <p>云端：{row.called_cloud ? '调用' : '未调用'} · {formatDate(row.created_at)}</p>
                </div>
              </article>
            ))}
          </section>
        )}

        {tab === 'backlog' && (
          <section className="space-y-3">
            <article className="rounded-2xl border border-white/10 bg-[#101719]/80 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-serif text-sm font-bold tracking-wide text-white">知识改进 backlog</p>
                  <p className="mt-1 font-serif text-[11px] tracking-wide text-slate-500">
                    聚合知识缺口、识别纠错与本地规则覆盖缺口
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void loadKnowledgeBacklog()}
                  disabled={isBacklogLoading}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/[0.03] text-slate-300 transition-colors hover:border-primary/25 hover:text-primary disabled:opacity-50"
                  aria-label="刷新知识改进待办"
                  title="刷新知识改进待办"
                >
                  <span className={`material-symbols-outlined text-[18px] ${isBacklogLoading ? 'animate-spin' : ''}`}>
                    {isBacklogLoading ? 'progress_activity' : 'rule_settings'}
                  </span>
                </button>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-2">
                {[
                  ['待处理反馈', knowledgeBacklog?.feedback_open_count ?? 0],
                  ['审计缺口', knowledgeBacklog?.knowledge_audit_gap_count ?? 0],
                  ['纠错哈希', knowledgeBacklog?.has_correction_count ?? 0],
                  ['样本上限', knowledgeBacklog?.window_limit ?? 0],
                ].map(([label, value]) => (
                  <div key={label as string} className="rounded-xl border border-white/5 bg-white/[0.03] px-3 py-2">
                    <p className="font-serif text-[10px] font-bold tracking-wide text-slate-500">{label as string}</p>
                    <p className="mt-1 font-serif text-lg font-bold tracking-wide text-white">{value as number}</p>
                  </div>
                ))}
              </div>

              <div className="mt-4 grid gap-2 md:grid-cols-2">
                <div className="rounded-xl border border-white/5 bg-black/20 p-3 font-serif text-[11px] leading-relaxed text-slate-400">
                  <p>反馈类型：{formatCounts(knowledgeBacklog?.feedback_type_counts)}</p>
                  <p>反馈状态：{formatCounts(knowledgeBacklog?.feedback_status_counts)}</p>
                  <p>高频标签：{formatCounts(knowledgeBacklog?.tag_counts)}</p>
                  <p>回退状态：{formatCounts(knowledgeBacklog?.fallback_status_counts)}</p>
                  <p>病种代码：{formatCounts(knowledgeBacklog?.matched_disease_counts)}</p>
                  <p>食物代码：{formatCounts(knowledgeBacklog?.matched_food_counts)}</p>
                  <p>未映射条件哈希：{formatCounts(knowledgeBacklog?.unmapped_condition_counts, 3)}</p>
                  <p>云端原因码：{formatCounts(knowledgeBacklog?.cloud_call_reason_counts)}</p>
                  <p>阻断原因码：{formatCounts(knowledgeBacklog?.cloud_blocked_reason_counts)}</p>
                </div>
                <div className="rounded-xl border border-white/5 bg-black/20 p-3 font-serif text-[11px] leading-relaxed text-slate-400">
                  <p>营养来源：{formatCounts(knowledgeBacklog?.food_nutrition_source_counts)}</p>
                  <p>估算质量：{formatCounts(knowledgeBacklog?.food_nutrition_quality_counts)}</p>
                  <p>复核状态：{formatCounts(knowledgeBacklog?.food_nutrition_review_status_counts)}</p>
                  <p>待复核食物：{knowledgeBacklog?.food_nutrition_unreviewed_count ?? 0}</p>
                  <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
                    灰度前先把未复核食物补到 REVIEWED，并确认 source/detail 对应真实成分表、标签或配方估算。
                  </p>
                </div>
              </div>

              <div className="mt-4 space-y-1 border-t border-white/5 pt-3">
                {(knowledgeBacklog?.notes || []).map(note => (
                  <p key={note} className="font-serif text-[11px] leading-relaxed text-slate-500">{note}</p>
                ))}
              </div>
            </article>

            {isBacklogLoading && (
              <div className="rounded-xl border border-white/10 bg-[#101719]/80 px-4 py-6 text-center font-serif text-xs font-bold tracking-wide text-slate-500">
                正在加载知识改进待办...
              </div>
            )}

            {!isBacklogLoading && (knowledgeBacklog?.recent_items || []).length === 0 && (
              <div className="rounded-xl border border-white/10 bg-[#101719]/80 px-4 py-6 text-center font-serif text-xs leading-relaxed text-slate-400">
                当前暂无知识缺口或纠错待办。
              </div>
            )}

            {!isBacklogLoading && (knowledgeBacklog?.recent_items || []).map(row => (
              <article key={`${row.source}-${row.id}`} className="rounded-2xl border border-white/10 bg-[#101719]/80 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-serif text-sm font-bold tracking-wide text-white">
                      {row.source === 'feedback' ? row.feedback_type || 'feedback' : row.fallback_status || 'knowledge_audit'}
                    </p>
                    <p className="mt-1 font-serif text-[11px] tracking-wide text-slate-500">
                      {row.source} · 用户 {row.user_id ?? '-'} · {formatDate(row.created_at)}
                    </p>
                  </div>
                  <span className="rounded-full border border-white/10 bg-white/[0.03] px-2 py-1 font-serif text-[10px] font-bold tracking-wide text-slate-300">
                    {row.status || row.origin || '-'}
                  </span>
                </div>
                <div className="mt-3 space-y-2 font-serif text-[11px] tracking-wide text-slate-400">
                  <p>标签：{row.tags.join('、') || '-'}</p>
                  <p>metadata key：{row.metadata_keys.join('、') || '-'}</p>
                  <p>纠错哈希：{row.correction_text_hash ? row.correction_text_hash.slice(0, 16) : '-'}</p>
                  <p>查询哈希：{row.query_excerpt_hash ? row.query_excerpt_hash.slice(0, 16) : '-'}</p>
                  <p>病种：{row.matched_disease_codes.join('、') || '-'}</p>
                  <p>食物：{row.matched_food_codes.join('、') || '-'}</p>
                  <p>未映射：{row.unmapped_condition_hashes.join('、') || '-'}</p>
                  <p>云端：{row.called_cloud == null ? '-' : row.called_cloud ? '调用' : '未调用'} · 原因 {row.cloud_call_reason_code || row.cloud_blocked_reason_code || '-'}</p>
                </div>
                {row.source === 'feedback' && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {(['open', 'reviewed', 'closed'] as const).map(nextStatus => {
                      const unsafeCloseBlocked = requiresUnsafeReviewBeforeClose(row, nextStatus);
                      return (
                        <button
                          key={nextStatus}
                          type="button"
                          onClick={() => void updateFeedbackStatus(row.id, nextStatus)}
                          disabled={loadingFeedbackId === row.id || row.status === nextStatus || unsafeCloseBlocked}
                          title={unsafeCloseBlocked ? 'unsafe 反馈需先标记为已审阅后才能关闭' : undefined}
                          className={`rounded-full border px-3 py-1 font-serif text-[10px] font-bold tracking-wide transition-colors ${row.status === nextStatus
                            ? 'border-primary/30 bg-primary/10 text-primary'
                            : unsafeCloseBlocked
                              ? 'border-amber-300/20 bg-amber-500/5 text-amber-100/70'
                              : 'border-white/10 bg-white/[0.03] text-slate-300 hover:border-primary/25 hover:text-primary'
                            } disabled:opacity-50`}
                        >
                          {nextStatus === 'open' ? '打开' : nextStatus === 'reviewed' ? '已审阅' : unsafeCloseBlocked ? '先审阅后关闭' : '已关闭'}
                        </button>
                      );
                    })}
                  </div>
                )}
              </article>
            ))}
          </section>
        )}

        {tab === 'feedback' && (
          <section className="space-y-3">
            <div className="rounded-2xl border border-white/10 bg-[#101719]/80 p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="font-serif text-sm font-bold tracking-wide text-white">反馈筛选</p>
                  <p className="mt-1 font-serif text-[11px] tracking-wide text-slate-500">
                    当前 {feedbackRows.length} 条 · {feedbackFilter === 'all' ? '全部状态' : feedbackFilter} · {feedbackTypeFilter === 'all' ? '全部类型' : feedbackTypeFilter}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void loadFeedbackRows(feedbackFilter, feedbackTypeFilter)}
                  disabled={isFeedbackLoading}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/[0.03] text-slate-300 transition-colors hover:border-primary/25 hover:text-primary disabled:opacity-50"
                  aria-label="刷新反馈"
                  title="刷新反馈"
                >
                  <span className={`material-symbols-outlined text-[18px] ${isFeedbackLoading ? 'animate-spin' : ''}`}>
                    {isFeedbackLoading ? 'progress_activity' : 'refresh'}
                  </span>
                </button>
              </div>
              <div className="mt-3 grid grid-cols-4 gap-2">
                {([
                  ['all', '全部'],
                  ['open', '只看未处理'],
                  ['reviewed', '已审阅'],
                  ['closed', '已关闭'],
                ] as [FeedbackFilter, string][]).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => handleFeedbackFilterChange(value)}
                    disabled={isFeedbackLoading && feedbackFilter === value}
                    className={`min-w-0 rounded-xl border px-2 py-2 font-serif text-[11px] font-bold tracking-wide transition-colors ${feedbackFilter === value
                      ? 'border-primary/30 bg-primary/10 text-primary'
                      : 'border-white/10 bg-white/[0.03] text-slate-300 hover:border-primary/25 hover:text-primary'
                      } disabled:opacity-50`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="mt-2 grid grid-cols-3 gap-2">
                {([
                  ['all', '全部类型'],
                  ['unsafe', '有风险'],
                  ['knowledge_gap', '知识缺口'],
                  ['recognition_correction', '识别纠错'],
                  ['correction', '建议纠错'],
                  ['not_helpful', '没帮助'],
                  ['helpful', '有帮助'],
                ] as [FeedbackTypeFilter, string][]).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => handleFeedbackTypeChange(value)}
                    disabled={isFeedbackLoading && feedbackTypeFilter === value}
                    className={`min-w-0 rounded-xl border px-2 py-2 font-serif text-[10px] font-bold tracking-wide transition-colors ${feedbackTypeFilter === value
                      ? 'border-[#45b7aa]/30 bg-[#45b7aa]/10 text-[#45b7aa]'
                      : 'border-white/10 bg-white/[0.03] text-slate-300 hover:border-[#45b7aa]/25 hover:text-[#45b7aa]'
                      } disabled:opacity-50`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {isFeedbackLoading && (
              <div className="rounded-xl border border-white/10 bg-[#101719]/80 px-4 py-6 text-center font-serif text-xs font-bold tracking-wide text-slate-500">
                正在加载反馈...
              </div>
            )}

            {!isFeedbackLoading && feedbackRows.length === 0 && (
              <div className="rounded-xl border border-white/10 bg-[#101719]/80 px-4 py-6 text-center font-serif text-xs leading-relaxed text-slate-400">
                当前筛选下暂无反馈项。
              </div>
            )}

            {!isFeedbackLoading && feedbackRows.map(row => (
              <article key={row.id} className="rounded-2xl border border-white/10 bg-[#101719]/80 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-serif text-sm font-bold tracking-wide text-white">{row.feedback_type}</p>
                    <p className="mt-1 font-serif text-[11px] tracking-wide text-slate-500">
                      用户 {row.user_id} · {formatDate(row.created_at)}
                    </p>
                  </div>
                  <span className="rounded-full border border-white/10 bg-white/[0.03] px-2 py-1 font-serif text-[10px] font-bold tracking-wide text-slate-300">
                    {row.status}
                  </span>
                </div>
                <div className="mt-3 space-y-2 font-serif text-[11px] tracking-wide text-slate-400">
                  <p>评分：{row.rating ?? '-'}</p>
                  <p>标签：{row.tags.join('、') || '-'}</p>
                  <p>修正：{row.has_correction ? '有' : '无'}</p>
                  <p>metadata key：{row.metadata_keys.join('、') || '-'}</p>
                  <p>会话：{row.session_id ?? '-'} · 消息：{row.message_id ?? '-'} · 洞察：{row.app_message_id ?? '-'}</p>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {(['open', 'reviewed', 'closed'] as const).map(nextStatus => {
                    const unsafeCloseBlocked = requiresUnsafeReviewBeforeClose(row, nextStatus);
                    return (
                      <button
                        key={nextStatus}
                        type="button"
                        onClick={() => void updateFeedbackStatus(row.id, nextStatus)}
                        disabled={loadingFeedbackId === row.id || row.status === nextStatus || unsafeCloseBlocked}
                        title={unsafeCloseBlocked ? 'unsafe 反馈需先标记为已审阅后才能关闭' : undefined}
                        className={`rounded-full border px-3 py-1 font-serif text-[10px] font-bold tracking-wide transition-colors ${row.status === nextStatus
                          ? 'border-primary/30 bg-primary/10 text-primary'
                          : unsafeCloseBlocked
                            ? 'border-amber-300/20 bg-amber-500/5 text-amber-100/70'
                            : 'border-white/10 bg-white/[0.03] text-slate-300 hover:border-primary/25 hover:text-primary'
                          } disabled:opacity-50`}
                      >
                        {nextStatus === 'open' ? '打开' : nextStatus === 'reviewed' ? '已审阅' : unsafeCloseBlocked ? '先审阅后关闭' : '已关闭'}
                      </button>
                    );
                  })}
                </div>
              </article>
            ))}
          </section>
        )}

        {tab === 'telemetry' && (
          <section className="space-y-3">
            <article className="rounded-2xl border border-white/10 bg-[#101719]/80 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-serif text-sm font-bold tracking-wide text-white">AI 调用汇总</p>
                  <p className="mt-1 font-serif text-[11px] tracking-wide text-slate-500">
                    最近 {aiTelemetry?.window_limit ?? 50} 条 AI 回复
                  </p>
                </div>
                <span className="rounded-full border border-primary/20 bg-primary/10 px-2 py-1 font-serif text-[10px] font-bold tracking-wide text-primary">
                  {aiTelemetry?.cost_status || 'unconfigured'}
                </span>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-2">
                {[
                  ['样本', aiTelemetry?.sampled_messages ?? 0],
                  ['云端调用', aiTelemetry?.cloud_call_count ?? 0],
                  ['本地直答', aiTelemetry?.local_direct_count ?? 0],
                  ['失败类型', aiTelemetry?.error_count ?? 0],
                  ['平均总耗时', aiTelemetry?.avg_chat_total_ms != null ? `${aiTelemetry.avg_chat_total_ms}ms` : '-'],
                  ['P95 总耗时', aiTelemetry?.p95_chat_total_ms != null ? `${aiTelemetry.p95_chat_total_ms}ms` : '-'],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-xl border border-white/5 bg-white/[0.03] px-3 py-2">
                    <p className="font-serif text-[10px] font-bold tracking-wide text-slate-500">{label}</p>
                    <p className="mt-1 font-serif text-sm font-bold tracking-wide text-white">{value}</p>
                  </div>
                ))}
              </div>
              <div className="mt-3 space-y-2 font-serif text-[11px] tracking-wide text-slate-400">
                <p>模型耗时：{aiTelemetry?.avg_doubao_total_ms != null ? `${aiTelemetry.avg_doubao_total_ms}ms` : '-'}</p>
                <p>成本估算：{aiTelemetry?.estimated_cost_usd == null ? '未接真实计费' : `$${aiTelemetry.estimated_cost_usd}`}</p>
                <p>来源：{Object.entries(aiTelemetry?.origin_counts || {}).map(([key, count]) => `${key}:${count}`).join(' · ') || '-'}</p>
                <p>状态：{Object.entries(aiTelemetry?.fallback_status_counts || {}).map(([key, count]) => `${key}:${count}`).join(' · ') || '-'}</p>
                <p>错误：{aiTelemetry?.recent_error_types.join('、') || '-'}</p>
              </div>
            </article>
          </section>
        )}


        {tab === 'commercialization' && (
          <section className="space-y-3">
            <article className="rounded-2xl border border-white/10 bg-[#101719]/80 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-serif text-sm font-bold tracking-wide text-white">商业化概览</p>
                  <p className="mt-1 font-serif text-[11px] tracking-wide text-slate-500">
                    最近 {commercializationSummary?.window_days ?? 30} 天的订阅、事件和用量压力
                  </p>
                </div>
                <span className="rounded-full border border-[#45b7aa]/25 bg-[#45b7aa]/10 px-2 py-1 font-serif text-[10px] font-bold tracking-wide text-[#45b7aa]">
                  {commercializationSummary?.billing_provider || 'mock'}
                </span>
              </div>

              <div className="mt-4 grid grid-cols-3 gap-2">
                {[
                  ['总用户', commercializationSummary?.total_users ?? 0],
                  ['付费活跃', commercializationSummary?.active_paid_users ?? 0],
                  ['已取消付费', commercializationSummary?.canceled_paid_users ?? 0],
                  ['checkout', commercializationSummary?.checkout_event_count ?? 0],
                  ['cancel', commercializationSummary?.cancel_event_count ?? 0],
                  ['usage views', commercializationSummary?.usage_snapshot_count ?? 0],
                ].map(([label, value]) => (
                  <div key={label as string} className="rounded-xl border border-white/5 bg-white/[0.03] px-3 py-2 text-center">
                    <p className="font-serif text-[10px] font-bold tracking-wide text-slate-500">{label as string}</p>
                    <p className="mt-1 font-serif text-lg font-bold tracking-wide text-white">{value as number}</p>
                  </div>
                ))}
              </div>

              <div className="mt-4 space-y-2">
                {(commercializationSummary?.usage_pressure || []).map(item => (
                  <div key={item.key} className="rounded-xl border border-white/5 bg-black/20 px-3 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-serif text-sm font-bold tracking-wide text-white">{item.label}</p>
                        <p className="mt-1 font-serif text-[11px] tracking-wide text-slate-500">
                          {item.period === 'day' ? '今日' : '本月'} · {item.total_usage} 次 · {item.usage_users} 位用户
                        </p>
                      </div>
                      <span className={`rounded-full border px-2 py-1 font-serif text-[10px] font-bold tracking-wide ${item.over_limit_users
                        ? 'border-amber-300/25 bg-amber-500/10 text-amber-100'
                        : item.near_limit_users
                          ? 'border-primary/25 bg-primary/10 text-primary'
                          : 'border-emerald-300/20 bg-emerald-500/10 text-emerald-200'
                        }`}>
                        {item.over_limit_users ? '超软额' : item.near_limit_users ? '接近' : '正常'}
                      </span>
                    </div>
                    <p className="mt-2 font-serif text-[10px] tracking-wide text-slate-500">
                      接近 {item.near_limit_users} · 超过 {item.over_limit_users}
                    </p>
                  </div>
                ))}
              </div>

              <div className="mt-4 space-y-1 border-t border-white/5 pt-3 font-serif text-[11px] leading-relaxed text-slate-500">
                <p>订阅分布：{formatCounts(commercializationSummary?.plan_counts)}</p>
                <p>状态分布：{formatCounts(commercializationSummary?.status_counts)}</p>
                <p>事件类型：{formatCounts(commercializationSummary?.event_type_counts)}</p>
                <p>事件状态：{formatCounts(commercializationSummary?.event_status_counts)}</p>
                {(commercializationSummary?.notes || []).map(note => (
                  <p key={note}>{note}</p>
                ))}
              </div>
            </article>
          </section>
        )}

        {tab === 'users' && (
          <section className="space-y-3">
            <div className="rounded-2xl border border-white/10 bg-[#101719]/80 p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="font-serif text-sm font-bold tracking-wide text-white">用户筛选</p>
                  <p className="mt-1 font-serif text-[11px] tracking-wide text-slate-500">
                    当前 {userRows.length} 条 · {userQueryValue || '全部用户'} · {userRoleFilter === 'all' ? '全部角色' : userRoleFilter} · {userPlanFilter === 'all' ? '全部订阅' : userPlanFilter} · {userStatusFilter === 'all' ? '全部状态' : userStatusFilter}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleUserSearch}
                  disabled={isUserLoading}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/[0.03] text-slate-300 transition-colors hover:border-primary/25 hover:text-primary disabled:opacity-50"
                  aria-label="刷新用户"
                  title="刷新用户"
                >
                  <span className={`material-symbols-outlined text-[18px] ${isUserLoading ? 'animate-spin' : ''}`}>
                    {isUserLoading ? 'progress_activity' : 'refresh'}
                  </span>
                </button>
              </div>
              <div className="mt-3 grid grid-cols-[1fr_auto] gap-2">
                <input
                  type="search"
                  value={userQuery}
                  onChange={(event) => setUserQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      handleUserSearch();
                    }
                  }}
                  placeholder="搜索昵称或用户 ID..."
                  className="min-w-0 rounded-xl border border-white/10 bg-black/20 px-3 py-2 font-serif text-xs font-bold tracking-wide text-white outline-none transition-colors placeholder:text-slate-600 focus:border-primary/40"
                />
                <button
                  type="button"
                  onClick={() => {
                    setUserQuery('');
                    void loadUserRows(undefined, userRoleFilter, userPlanFilter, userStatusFilter);
                  }}
                  disabled={isUserLoading || !userQuery}
                  className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 font-serif text-[11px] font-bold tracking-wide text-slate-300 transition-colors hover:border-primary/25 hover:text-primary disabled:opacity-40"
                >
                  清空
                </button>
              </div>
              <div className="mt-3 grid grid-cols-4 gap-2">
                {([
                  ['all', '全部角色'],
                  ['USER', '用户'],
                  ['ADMIN', '管理员'],
                  ['COACH', '教练'],
                ] as [UserRoleFilter, string][]).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => {
                      setUserRoleFilter(value);
                      void loadUserRows(userQueryValue, value, userPlanFilter, userStatusFilter);
                    }}
                    disabled={isUserLoading && userRoleFilter === value}
                    className={`min-w-0 rounded-xl border px-2 py-2 font-serif text-[11px] font-bold tracking-wide transition-colors ${userRoleFilter === value
                      ? 'border-primary/30 bg-primary/10 text-primary'
                      : 'border-white/10 bg-white/[0.03] text-slate-300 hover:border-primary/25 hover:text-primary'
                      } disabled:opacity-50`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="mt-2 grid grid-cols-4 gap-2">
                {([
                  ['all', '全部订阅'],
                  ['FREE', 'FREE'],
                  ['PRO', 'PRO'],
                  ['COACH', 'COACH'],
                ] as [UserPlanFilter, string][]).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => {
                      setUserPlanFilter(value);
                      void loadUserRows(userQueryValue, userRoleFilter, value, userStatusFilter);
                    }}
                    disabled={isUserLoading && userPlanFilter === value}
                    className={`min-w-0 rounded-xl border px-2 py-2 font-serif text-[11px] font-bold tracking-wide transition-colors ${userPlanFilter === value
                      ? 'border-[#45b7aa]/30 bg-[#45b7aa]/10 text-[#45b7aa]'
                      : 'border-white/10 bg-white/[0.03] text-slate-300 hover:border-[#45b7aa]/25 hover:text-[#45b7aa]'
                      } disabled:opacity-50`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="mt-2 grid grid-cols-4 gap-2">
                {([
                  ['all', '全部状态'],
                  ['active', '活跃'],
                  ['inactive', '停用'],
                  ['canceled', '取消'],
                ] as [UserStatusFilter, string][]).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => {
                      setUserStatusFilter(value);
                      void loadUserRows(userQueryValue, userRoleFilter, userPlanFilter, value);
                    }}
                    disabled={isUserLoading && userStatusFilter === value}
                    className={`min-w-0 rounded-xl border px-2 py-2 font-serif text-[11px] font-bold tracking-wide transition-colors ${userStatusFilter === value
                      ? 'border-amber-300/25 bg-amber-500/10 text-amber-100'
                      : 'border-white/10 bg-white/[0.03] text-slate-300 hover:border-amber-300/25 hover:text-amber-100'
                      } disabled:opacity-50`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {isUserLoading && (
              <div className="rounded-xl border border-white/10 bg-[#101719]/80 px-4 py-6 text-center font-serif text-xs font-bold tracking-wide text-slate-500">
                正在加载用户...
              </div>
            )}

            {!isUserLoading && userRows.length === 0 && (
              <div className="rounded-xl border border-white/10 bg-[#101719]/80 px-4 py-6 text-center font-serif text-xs leading-relaxed text-slate-400">
                当前筛选下暂无用户记录。
              </div>
            )}

            {!isUserLoading && userRows.map(row => (
              <article key={row.id} className="rounded-2xl border border-white/10 bg-[#101719]/80 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-serif text-sm font-bold tracking-wide text-white">用户 {row.id}</p>
                    <p className="mt-1 max-w-[220px] truncate font-serif text-[11px] tracking-wide text-slate-500">
                      手机哈希 {row.phone_hash || '-'}
                    </p>
                  </div>
                  <span className="rounded-full border border-white/10 bg-white/[0.03] px-2 py-1 font-serif text-[10px] font-bold tracking-wide text-slate-300">
                    {row.role}
                  </span>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 font-serif text-[11px] tracking-wide text-slate-400">
                  <span>订阅 {row.subscription_plan}</span>
                  <span>状态 {row.subscription_status}</span>
                  <span>验证 {row.is_verified ? '是' : '否'}</span>
                  <span>最近登录 {row.last_login_at ? formatDate(row.last_login_at) : '-'}</span>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {(['USER', 'ADMIN', 'COACH'] as UserRole[]).map(role => (
                    <button
                      key={role}
                      type="button"
                      onClick={() => void updateUserRole(row.id, role)}
                      disabled={loadingUserId === row.id || row.role === role}
                      className={`rounded-full border px-3 py-1 font-serif text-[10px] font-bold tracking-wide transition-colors ${row.role === role
                        ? 'border-primary/30 bg-primary/10 text-primary'
                        : 'border-white/10 bg-white/[0.03] text-slate-300 hover:border-primary/25 hover:text-primary'
                        } disabled:opacity-50`}
                    >
                      {role}
                    </button>
                  ))}
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {(['FREE', 'PRO', 'COACH'] as PlanTier[]).map(plan => (
                    <button
                      key={plan}
                      type="button"
                      onClick={() => void updateUserSubscription(row.id, plan)}
                      disabled={
                        loadingUserId === row.id
                        || (row.subscription_plan === plan && (plan === 'FREE' ? row.subscription_status === 'inactive' : row.subscription_status === 'active'))
                      }
                      className={`rounded-full border px-3 py-1 font-serif text-[10px] font-bold tracking-wide transition-colors ${row.subscription_plan === plan
                        ? 'border-[#45b7aa]/30 bg-[#45b7aa]/10 text-[#45b7aa]'
                        : 'border-white/10 bg-white/[0.03] text-slate-300 hover:border-[#45b7aa]/25 hover:text-[#45b7aa]'
                        } disabled:opacity-50`}
                    >
                      {plan}
                    </button>
                  ))}
                  {row.subscription_status === 'active' && (
                    <button
                      type="button"
                      onClick={() => void updateUserSubscription(row.id, row.subscription_plan, 'canceled')}
                      disabled={loadingUserId === row.id}
                      className="rounded-full border border-amber-300/20 bg-amber-500/10 px-3 py-1 font-serif text-[10px] font-bold tracking-wide text-amber-100 transition-colors hover:border-amber-300/35 disabled:opacity-50"
                    >
                      取消订阅
                    </button>
                  )}
                </div>
              </article>
            ))}
          </section>
        )}
      </div>
    </div>
  );
};

export default AdminView;
