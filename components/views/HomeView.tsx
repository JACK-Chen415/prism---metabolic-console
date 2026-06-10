import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AIFeedbackType, AppMessage, DailyTargets, Meal, View } from '../../types';
import { InsightsAPI } from '../../services/api';
import { formatChineseDate, getLocalDateString } from '../../services/date';

interface HomeViewProps {
  onViewChange: (view: View) => void;
  meals: Meal[];
  dailyTargets: DailyTargets;
  latestMessage?: AppMessage;
  appMessages: AppMessage[];
}

type InsightFeedbackChoice = Extract<AIFeedbackType, 'helpful' | 'not_helpful' | 'knowledge_gap'>;

const INSIGHT_FEEDBACK_CHOICES: Array<{
  type: InsightFeedbackChoice;
  label: string;
  icon: string;
  rating: number;
  tags: string[];
}> = [
  { type: 'helpful', label: '有用', icon: 'thumb_up', rating: 5, tags: ['insight', 'helpful'] },
  { type: 'not_helpful', label: '没用', icon: 'thumb_down', rating: 2, tags: ['insight', 'not_helpful'] },
  { type: 'knowledge_gap', label: '补充', icon: 'travel_explore', rating: 3, tags: ['insight', 'knowledge_gap'] },
];

const MEAL_ORDER: Record<Meal['type'], number> = {
  BREAKFAST: 0,
  LUNCH: 1,
  DINNER: 2,
  SNACK: 3,
};

const MEAL_TYPE_LABELS: Record<Meal['type'], string> = {
  BREAKFAST: '早餐',
  LUNCH: '午餐',
  DINNER: '晚餐',
  SNACK: '加餐',
};

const FOOD_CATEGORY_LABELS: Record<Meal['category'], string> = {
  STAPLE: '主食',
  MEAT: '肉蛋水产',
  VEG: '蔬果',
  DRINK: '饮品',
  SNACK: '零食',
};

const addDays = (date: Date, offset: number) => {
  const next = new Date(date);
  next.setDate(next.getDate() + offset);
  return next;
};

const formatTrendLabel = (date: Date) => `${date.getMonth() + 1}/${date.getDate()}`;

const clampProgress = (current: number, target: number) => {
  if (target <= 0) return 0;
  return Math.min(Math.max((current / target) * 100, 0), 100);
};

const getProgressStyle = (current: number, target: number, colorStart: string, colorEnd = '#1c2829') => (
  `conic-gradient(${colorStart} ${clampProgress(current, target)}%, ${colorEnd} 0)`
);

const formatCompactAmount = (value: number, unit: 'kcal' | 'mg') => {
  if (unit === 'mg' && Math.abs(value) >= 1000) {
    const grams = Math.abs(value) / 1000;
    return `${value < 0 ? '-' : ''}${grams >= 10 ? grams.toFixed(0) : grams.toFixed(1)}g`;
  }
  return `${value}${unit}`;
};

const formatBalanceAmount = (remaining: number, unit: 'kcal' | 'mg') => {
  if (remaining < 0) return `超 ${formatCompactAmount(Math.abs(remaining), unit)}`;
  return formatCompactAmount(remaining, unit);
};

const formatTargetDelta = (current: number, target: number, unit: 'kcal' | 'mg') => {
  if (target <= 0) return `${formatCompactAmount(current, unit)} 已记录`;
  const delta = target - current;
  if (delta > 0) return `剩余 ${formatCompactAmount(delta, unit)}`;
  if (delta < 0) return `超出 ${formatCompactAmount(Math.abs(delta), unit)}`;
  return '刚好达标';
};

const getMessageCardStyle = (type: string) => {
  switch (type) {
    case 'WARNING':
      return {
        border: 'border-amber-300/25',
        bg: 'bg-amber-500/[0.08]',
        iconBg: 'bg-amber-300/[0.12]',
        iconColor: 'text-amber-200',
        icon: 'notifications_active',
        label: '预警',
      };
    case 'ADVICE':
      return {
        border: 'border-emerald-300/20',
        bg: 'bg-emerald-500/[0.07]',
        iconBg: 'bg-emerald-300/[0.10]',
        iconColor: 'text-emerald-200',
        icon: 'check_circle',
        label: '建议',
      };
    case 'BRIEF':
      return {
        border: 'border-cyan-300/20',
        bg: 'bg-cyan-500/[0.07]',
        iconBg: 'bg-cyan-300/[0.10]',
        iconColor: 'text-cyan-200',
        icon: 'article',
        label: '简报',
      };
    default:
      return {
        border: 'border-white/10',
        bg: 'bg-white/[0.03]',
        iconBg: 'bg-white/[0.08]',
        iconColor: 'text-white',
        icon: 'info',
        label: '洞察',
      };
  }
};

const HomeView: React.FC<HomeViewProps> = ({ onViewChange, meals, dailyTargets, latestMessage, appMessages }) => {
  const [insightFeedbackByMessage, setInsightFeedbackByMessage] = useState<Record<number, InsightFeedbackChoice>>({});
  const [submittingInsightFeedbackId, setSubmittingInsightFeedbackId] = useState<number | null>(null);
  const [insightFeedbackError, setInsightFeedbackError] = useState<string | null>(null);

  const today = new Date();
  const todayKey = getLocalDateString(today);
  const todayLabel = formatChineseDate(todayKey);
  const sortedMessages = useMemo(() => [...appMessages].sort((left, right) => right.id - left.id), [appMessages]);
  const activeMessage = sortedMessages[0] ?? latestMessage ?? null;

  const mealsByDate = useMemo(() => meals.reduce<Record<string, Meal[]>>((acc, meal) => {
    if (!meal.recordDate) return acc;
    (acc[meal.recordDate] ||= []).push(meal);
    return acc;
  }, {}), [meals]);

  const todaysMeals = useMemo(
    () => [...(mealsByDate[todayKey] || [])].sort((left, right) => (
      MEAL_ORDER[left.type] - MEAL_ORDER[right.type] || left.name.localeCompare(right.name, 'zh-CN')
    )),
    [mealsByDate, todayKey],
  );

  const todaysTotals = todaysMeals.reduce((acc, meal) => ({
    calories: acc.calories + meal.calories,
    sodium: acc.sodium + meal.sodium,
    purine: acc.purine + meal.purine,
  }), { calories: 0, sodium: 0, purine: 0 });

  const calorieTarget = dailyTargets.recommended_calorie_target || dailyTargets.calories || 0;
  const remainingCalories = calorieTarget > 0 ? calorieTarget - todaysTotals.calories : 0;
  const remainingSodium = dailyTargets.sodium - todaysTotals.sodium;
  const remainingPurine = dailyTargets.purine - todaysTotals.purine;
  const completenessCount = [
    todaysMeals.length > 0,
    calorieTarget > 0,
    dailyTargets.sodium > 0,
    dailyTargets.purine > 0,
  ].filter(Boolean).length;

  const riskNotes = [
    remainingSodium < 0 ? '钠摄入已超出建议上限' : null,
    remainingPurine < 0 ? '嘌呤摄入已超出建议上限' : null,
    remainingCalories < 0 ? '热量已超出今日目标' : null,
    todaysMeals.length === 0 ? '今天还没有确认记录' : null,
  ].filter(Boolean) as string[];

  const nextStep = (() => {
    const note = riskNotes[0];
    if (!note) return '保持当前节奏，继续记录下一餐。';
    if (note.includes('钠')) return '下一餐优先少盐、少酱、少加工调味。';
    if (note.includes('嘌呤')) return '下一餐优先低嘌呤，避开浓汤、内脏和海鲜汤底。';
    if (note.includes('热量')) return '下一餐优先减量主食和油脂，控制份量。';
    return '先补一条今天的饮食记录，再看趋势。';
  })();

  const trendSeries = useMemo(() => Array.from({ length: 7 }, (_, index) => {
    const date = addDays(today, index - 6);
    const key = getLocalDateString(date);
    return {
      key,
      label: formatTrendLabel(date),
      count: meals.filter((meal) => meal.recordDate === key).length,
    };
  }), [meals, today]);

  const streakDays = useMemo(() => {
    const dateSet = new Set(meals.map((meal) => meal.recordDate).filter(Boolean) as string[]);
    let streak = 0;
    const cursor = new Date(today);
    while (true) {
      const key = getLocalDateString(cursor);
      if (!dateSet.has(key)) break;
      streak += 1;
      cursor.setDate(cursor.getDate() - 1);
    }
    return streak;
  }, [meals, today]);

  const unreadCount = appMessages.filter((message) => !message.isRead).length;
  const trendSummary = trendSeries.some((day) => day.count > 0)
    ? `${trendSeries.filter((day) => day.count > 0).length}/7 天有记录`
    : '近 7 天无记录';

  const activeMessageStyle = getMessageCardStyle(activeMessage?.type || 'ADVICE');
  const latestInsightFeedback = activeMessage ? insightFeedbackByMessage[activeMessage.id] : undefined;

  useEffect(() => {
    if (!activeMessage?.id) return;

    let cancelled = false;
    void InsightsAPI.listFeedback(activeMessage.id)
      .then((items) => {
        if (cancelled) return;
        const latestFeedback = items.find((item) => (
          item.feedback_type === 'helpful'
          || item.feedback_type === 'not_helpful'
          || item.feedback_type === 'knowledge_gap'
        ));
        if (latestFeedback) {
          setInsightFeedbackByMessage((prev) => ({
            ...prev,
            [activeMessage.id]: latestFeedback.feedback_type as InsightFeedbackChoice,
          }));
        }
      })
      .catch(() => {
        // Feedback is advisory UI only.
      });

    return () => {
      cancelled = true;
    };
  }, [activeMessage?.id]);

  const submitInsightFeedback = useCallback(async (choice: InsightFeedbackChoice) => {
    if (!activeMessage || submittingInsightFeedbackId === activeMessage.id) return;

    const meta = INSIGHT_FEEDBACK_CHOICES.find((item) => item.type === choice);
    if (!meta) return;

    setSubmittingInsightFeedbackId(activeMessage.id);
    setInsightFeedbackError(null);
    try {
      const feedback = await InsightsAPI.sendFeedback(activeMessage.id, {
        feedback_type: choice,
        rating: meta.rating,
        tags: meta.tags,
        metadata: {
          source: 'home',
          surface: 'daily_console',
          context: activeMessage.type,
        },
      });
      setInsightFeedbackByMessage((prev) => ({
        ...prev,
        [activeMessage.id]: feedback.feedback_type as InsightFeedbackChoice,
      }));
    } catch (error) {
      setInsightFeedbackError(error instanceof Error ? error.message : '洞察反馈提交失败。');
    } finally {
      setSubmittingInsightFeedbackId(null);
    }
  }, [activeMessage, submittingInsightFeedbackId]);

  const balanceMetrics = [
    {
      key: 'calories',
      label: '热量',
      unit: 'kcal' as const,
      current: todaysTotals.calories,
      target: calorieTarget,
      remaining: remainingCalories,
      icon: 'local_fire_department',
      color: remainingCalories < 0 ? '#f59e0b' : '#d9a441',
      textColor: remainingCalories < 0 ? 'text-amber-200' : 'text-[#f0c96d]',
      ringSize: 'h-20 w-20',
      innerInset: 'inset-[6px]',
      valueClass: 'text-lg',
      featured: false,
    },
    {
      key: 'sodium',
      label: '钠',
      unit: 'mg' as const,
      current: todaysTotals.sodium,
      target: dailyTargets.sodium,
      remaining: remainingSodium,
      icon: 'science',
      color: remainingSodium < 0 ? '#f59e0b' : '#11c4d4',
      textColor: remainingSodium < 0 ? 'text-amber-200' : 'text-cyan-100',
      ringSize: 'h-28 w-28',
      innerInset: 'inset-[7px]',
      valueClass: 'text-2xl',
      featured: true,
    },
    {
      key: 'purine',
      label: '嘌呤',
      unit: 'mg' as const,
      current: todaysTotals.purine,
      target: dailyTargets.purine,
      remaining: remainingPurine,
      icon: 'water_drop',
      color: remainingPurine < 0 ? '#f59e0b' : '#7aa0a0',
      textColor: remainingPurine < 0 ? 'text-amber-200' : 'text-[#b8d2cf]',
      ringSize: 'h-20 w-20',
      innerInset: 'inset-[6px]',
      valueClass: 'text-lg',
      featured: false,
    },
  ] as const;

  const consoleActions = [
    { view: View.LOG, label: '日志', icon: 'edit_note', description: '补录或修订' },
    { view: View.CAMERA, label: '拍照', icon: 'photo_camera', description: '识别一餐' },
    { view: View.PACKAGED_FOOD_SCAN, label: '扫码', icon: 'barcode_scanner', description: '包装食品' },
    { view: View.MESSAGES, label: '洞察', icon: 'notifications', description: unreadCount > 0 ? `${unreadCount} 条未读` : '查看建议' },
  ] as const;

  const statusTone = riskNotes.length > 0
    ? 'border-amber-300/20 bg-amber-500/[0.08] text-amber-100'
    : 'border-emerald-300/20 bg-emerald-500/[0.07] text-emerald-100';

  return (
    <div className="min-h-full bg-[#091111] pb-28 font-serif font-bold tracking-wide text-slate-100">
      <header className="px-4 pt-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[10px] uppercase text-cyan-200/70">Daily Metabolic Console</p>
            <h1 className="mt-1 text-2xl text-white">今日代谢余额</h1>
            <p className="mt-2 text-sm leading-6 text-slate-400">{todayLabel} · {trendSummary}</p>
          </div>
          <button
            type="button"
            onClick={() => onViewChange(View.SETTINGS)}
            className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-white/75 transition-colors hover:bg-white/[0.08] hover:text-white"
            aria-label="进入设置"
          >
            <span className="material-symbols-outlined text-[20px]">settings</span>
          </button>
        </div>
      </header>

      <section className="px-4 pt-4">
        <div className="overflow-hidden rounded-lg border border-white/10 bg-[#0f1819]/95 shadow-[0_18px_60px_rgba(0,0,0,0.28)]">
          <div className="border-b border-white/[0.08] px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-[10px] uppercase text-slate-500">Balance</p>
                <h2 className="mt-1 text-lg text-white">三项核心摄入</h2>
              </div>
              <span className={`rounded-md border px-2.5 py-1 text-[11px] ${statusTone}`}>
                {riskNotes[0] || '未见明显超标'}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-3 items-end gap-2 px-3 py-5">
            {balanceMetrics.map((metric) => (
              <div key={metric.key} className={`flex flex-col items-center ${metric.featured ? 'gap-3' : 'gap-2'}`}>
                <div
                  className={`relative flex ${metric.ringSize} items-center justify-center rounded-full shadow-[inset_0_0_20px_rgba(255,255,255,0.03)]`}
                  style={{ background: getProgressStyle(metric.current, metric.target, metric.color) }}
                >
                  <div className={`absolute ${metric.innerInset} rounded-full bg-[#091111]`} />
                  <div className="relative flex flex-col items-center justify-center text-center">
                    <span className={`material-symbols-outlined ${metric.featured ? 'text-[22px]' : 'text-[18px]'} ${metric.textColor}`}>
                      {metric.icon}
                    </span>
                    {metric.featured && (
                      <span className={`mt-1 max-w-[88px] truncate leading-none ${metric.valueClass} ${metric.textColor}`}>
                        {formatBalanceAmount(metric.remaining, metric.unit)}
                      </span>
                    )}
                  </div>
                </div>
                <div className="min-h-[54px] text-center">
                  <p className="text-[11px] text-slate-300">{metric.label}</p>
                  {!metric.featured && (
                    <p className={`mt-1 leading-tight ${metric.valueClass} ${metric.textColor}`}>
                      {formatBalanceAmount(metric.remaining, metric.unit)}
                    </p>
                  )}
                  <p className="mt-1 text-[10px] leading-4 text-slate-500">
                    {formatTargetDelta(metric.current, metric.target, metric.unit)}
                  </p>
                </div>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-2 border-t border-white/[0.08]">
            <div className="border-r border-white/[0.08] px-4 py-3">
              <p className="text-[10px] uppercase text-slate-500">Completeness</p>
              <p className="mt-1 text-xl text-white">{completenessCount}/4</p>
              <p className="mt-1 text-[11px] leading-5 text-slate-500">{todaysMeals.length > 0 ? '今天已有确认记录' : '等待第一条记录'}</p>
            </div>
            <div className="px-4 py-3">
              <p className="text-[10px] uppercase text-slate-500">Next Step</p>
              <p className="mt-1 text-sm leading-5 text-slate-200">{nextStep}</p>
            </div>
          </div>
        </div>
      </section>

      <section className="px-4 pt-3">
        <div className="grid grid-cols-4 gap-2">
          {consoleActions.map((action) => (
            <button
              key={action.view}
              type="button"
              onClick={() => onViewChange(action.view)}
              className="group flex min-h-[78px] flex-col items-center justify-center rounded-lg border border-white/10 bg-white/[0.035] px-2 py-2 text-center transition-colors hover:border-cyan-300/25 hover:bg-cyan-300/[0.06] active:scale-[0.98]"
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/[0.06] text-slate-200 transition-colors group-hover:text-cyan-100">
                <span className="material-symbols-outlined text-[19px]">{action.icon}</span>
              </span>
              <span className="mt-2 text-xs text-white">{action.label}</span>
              <span className="mt-0.5 max-w-full truncate text-[10px] text-slate-500">{action.description}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="px-4 pt-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[10px] uppercase text-slate-500">Today&apos;s Log</p>
            <h2 className="mt-1 text-lg text-white">今日记录</h2>
          </div>
          <button
            type="button"
            onClick={() => onViewChange(View.LOG)}
            className="inline-flex items-center gap-1 rounded-md border border-white/10 px-2.5 py-1.5 text-[11px] text-slate-300 transition-colors hover:bg-white/[0.05] hover:text-white"
          >
            查看全部
            <span className="material-symbols-outlined text-[16px]">chevron_right</span>
          </button>
        </div>

        <div className="mt-3 rounded-lg border border-white/10 bg-[#0f1819]/80">
          {todaysMeals.length > 0 ? (
            <div className="divide-y divide-white/[0.08]">
              {todaysMeals.slice(0, 3).map((meal) => (
                <div key={meal.id} className="flex items-center justify-between gap-3 px-3 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm text-white">{meal.name}</p>
                    <p className="mt-1 truncate text-[11px] text-slate-500">
                      {MEAL_TYPE_LABELS[meal.type]} · {FOOD_CATEGORY_LABELS[meal.category]} · {meal.portion || '1份'}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="text-sm text-white">{meal.calories} kcal</p>
                    <p className="mt-1 text-[11px] text-slate-500">{meal.sodium} mg 钠</p>
                  </div>
                </div>
              ))}
              {todaysMeals.length > 3 && (
                <button
                  type="button"
                  onClick={() => onViewChange(View.LOG)}
                  className="flex w-full items-center justify-center gap-1 px-3 py-2 text-[11px] text-cyan-100/80 transition-colors hover:text-cyan-50"
                >
                  还有 {todaysMeals.length - 3} 条记录
                  <span className="material-symbols-outlined text-[14px]">chevron_right</span>
                </button>
              )}
            </div>
          ) : (
            <div className="px-3 py-4 text-sm leading-6 text-slate-400">
              今天还没有确认记录。先补一条饮食日志，首页会自动更新代谢余额。
            </div>
          )}
        </div>

        <div className="mt-3 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm text-white">7 天记录节奏</h3>
            <span className="text-[11px] text-slate-500">{streakDays} 天连续</span>
          </div>
          <div className="mt-3 grid grid-cols-7 items-end gap-2">
            {trendSeries.map((day) => {
              const height = Math.max(10, Math.min(58, day.count * 14 + 10));
              const isToday = day.key === todayKey;
              return (
                <div key={day.key} className="flex min-w-0 flex-col items-center gap-2">
                  <div className="flex h-[62px] w-full items-end justify-center rounded-md bg-black/10">
                    <div
                      className={`w-full max-w-[16px] rounded-t-sm ${isToday ? 'bg-cyan-300' : 'bg-white/[0.22]'}`}
                      style={{ height }}
                      title={`${day.label} ${day.count} 条`}
                    />
                  </div>
                  <span className={`text-[10px] ${isToday ? 'text-cyan-100' : 'text-slate-500'}`}>{day.label}</span>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section className="px-4 pt-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[10px] uppercase text-slate-500">Insight Feed</p>
            <h2 className="mt-1 text-lg text-white">最新洞察</h2>
          </div>
          <button
            type="button"
            onClick={() => onViewChange(View.MESSAGES)}
            className="inline-flex items-center gap-1 rounded-md border border-white/10 px-2.5 py-1.5 text-[11px] text-slate-300 transition-colors hover:bg-white/[0.05] hover:text-white"
            aria-label={unreadCount > 0 ? `查看洞察记录，${unreadCount} 条未读` : '查看洞察记录'}
          >
            洞察记录
            <span className="material-symbols-outlined text-[16px]">chevron_right</span>
          </button>
        </div>

        {activeMessage ? (
          <div className={`mt-3 rounded-lg border ${activeMessageStyle.border} ${activeMessageStyle.bg} p-4`}>
            <div className="flex items-start gap-3">
              <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${activeMessageStyle.iconBg} ${activeMessageStyle.iconColor}`}>
                <span className="material-symbols-outlined text-[20px]">{activeMessageStyle.icon}</span>
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="truncate text-base text-white">{activeMessage.title}</h3>
                  <span className="shrink-0 text-[10px] uppercase text-slate-500">{activeMessageStyle.label}</span>
                </div>
                <p className="mt-2 text-sm leading-6 text-slate-300">{activeMessage.content}</p>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  {INSIGHT_FEEDBACK_CHOICES.map((choice) => {
                    const isSelected = latestInsightFeedback === choice.type;
                    return (
                      <button
                        key={choice.type}
                        type="button"
                        onClick={() => void submitInsightFeedback(choice.type)}
                        disabled={submittingInsightFeedbackId === activeMessage.id}
                        aria-pressed={isSelected}
                        className={`inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-[11px] transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                          isSelected
                            ? 'border-cyan-300/40 bg-cyan-300/[0.12] text-cyan-50'
                            : 'border-white/10 bg-white/[0.03] text-slate-300 hover:border-cyan-300/25 hover:text-white'
                        }`}
                      >
                        <span className="material-symbols-outlined text-[16px]">{choice.icon}</span>
                        {choice.label}
                      </button>
                    );
                  })}
                  {submittingInsightFeedbackId === activeMessage.id && (
                    <span className="text-[11px] text-cyan-100">提交中</span>
                  )}
                  {latestInsightFeedback && submittingInsightFeedbackId !== activeMessage.id && (
                    <span className="text-[11px] text-cyan-100/80">已记录</span>
                  )}
                </div>
                {insightFeedbackError && (
                  <p className="mt-2 text-[11px] leading-5 text-amber-200">{insightFeedbackError}</p>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="mt-3 rounded-lg border border-dashed border-white/10 bg-white/[0.02] px-3 py-4 text-sm leading-6 text-slate-400">
            暂无洞察内容。
          </div>
        )}
      </section>
    </div>
  );
};

export default HomeView;
