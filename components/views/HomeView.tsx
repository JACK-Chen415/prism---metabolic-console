import React from 'react';
import { AIFeedbackType, View, Meal, DailyTargets, AppMessage } from '../../types';
import { InsightsAPI } from '../../services/api';

interface HomeViewProps {
  onViewChange: (view: View) => void;
  meals: Meal[];
  dailyTargets: DailyTargets;
  latestMessage?: AppMessage;
  appMessages: AppMessage[];
}

type InsightFeedbackChoice = Extract<AIFeedbackType, 'helpful' | 'not_helpful' | 'knowledge_gap'>;

const INSIGHT_FEEDBACK_CHOICES: Array<{ type: InsightFeedbackChoice; label: string; icon: string; rating: number; tags: string[] }> = [
  { type: 'helpful', label: '有用', icon: 'thumb_up', rating: 5, tags: ['insight', 'helpful'] },
  { type: 'not_helpful', label: '没用', icon: 'thumb_down', rating: 2, tags: ['insight', 'not_helpful'] },
  { type: 'knowledge_gap', label: '补充', icon: 'travel_explore', rating: 3, tags: ['insight', 'knowledge_gap'] },
];

const HomeView: React.FC<HomeViewProps> = ({ onViewChange, meals, dailyTargets, latestMessage, appMessages }) => {
  const [insightFeedbackByMessage, setInsightFeedbackByMessage] = React.useState<Record<number, InsightFeedbackChoice>>({});
  const [submittingInsightFeedbackId, setSubmittingInsightFeedbackId] = React.useState<number | null>(null);
  const [insightFeedbackError, setInsightFeedbackError] = React.useState<string | null>(null);
  const todayKey = new Date().toISOString().slice(0, 10);
  const mealDates = Array.from(new Set(meals.map(meal => meal.recordDate).filter(Boolean))) as string[];
  // Calculate Totals
  const totalConsumed = meals.reduce((acc, meal) => ({
    calories: acc.calories + meal.calories,
    sodium: acc.sodium + meal.sodium,
    purine: acc.purine + meal.purine
  }), { calories: 0, sodium: 0, purine: 0 });

  const calorieTarget = dailyTargets.recommended_calorie_target || dailyTargets.calories || 0;

  // Calculate Remaining
  const remaining = {
    calories: calorieTarget > 0 ? calorieTarget - totalConsumed.calories : 0,
    sodium: dailyTargets.sodium - totalConsumed.sodium,
    purine: dailyTargets.purine - totalConsumed.purine
  };

  const latestInsightFeedback = latestMessage ? insightFeedbackByMessage[latestMessage.id] : undefined;

  React.useEffect(() => {
    if (!latestMessage?.id) return;

    let cancelled = false;
    void InsightsAPI.listFeedback(latestMessage.id)
      .then(items => {
        if (cancelled) return;
        const latestFeedback = items.find(item => (
          item.feedback_type === 'helpful'
          || item.feedback_type === 'not_helpful'
          || item.feedback_type === 'knowledge_gap'
        ));
        if (latestFeedback) {
          setInsightFeedbackByMessage(prev => ({
            ...prev,
            [latestMessage.id]: latestFeedback.feedback_type as InsightFeedbackChoice,
          }));
        }
      })
      .catch(() => {
        // Feedback state is advisory UI only; the insight itself should still render.
      });

    return () => {
      cancelled = true;
    };
  }, [latestMessage?.id]);

  const submitInsightFeedback = async (choice: InsightFeedbackChoice) => {
    if (!latestMessage || submittingInsightFeedbackId === latestMessage.id) return;

    const meta = INSIGHT_FEEDBACK_CHOICES.find(item => item.type === choice);
    if (!meta) return;

    setSubmittingInsightFeedbackId(latestMessage.id);
    setInsightFeedbackError(null);
    try {
      const feedback = await InsightsAPI.sendFeedback(latestMessage.id, {
        feedback_type: choice,
        rating: meta.rating,
        tags: meta.tags,
        metadata: {
          source: 'home',
          surface: 'latest_insight',
          context: latestMessage.type,
        },
      });
      setInsightFeedbackByMessage(prev => ({
        ...prev,
        [latestMessage.id]: feedback.feedback_type as InsightFeedbackChoice,
      }));
    } catch (error) {
      setInsightFeedbackError(error instanceof Error ? error.message : '洞察反馈提交失败。');
    } finally {
      setSubmittingInsightFeedbackId(null);
    }
  };

  // Helper for progress percentage (for the ring visual)
  const getProgressStyle = (current: number, target: number, colorStart: string, colorEnd: string) => {
    const percentage = target > 0 ? Math.min(Math.max((current / target) * 100, 0), 100) : 0;
    return `conic-gradient(${colorStart} ${percentage}%, ${colorEnd} 0)`;
  };

  // Helper to determine text color based on remaining amount
  const getRemainingColor = (value: number, type: 'CAL' | 'SOD' | 'PUR') => {
    if (value < 0) return 'text-[#fa5c38]'; // Warning color if exceeded
    return 'text-white';
  };

  // Determine card style based on message type
  const getMessageCardStyle = (type: string) => {
    switch (type) {
      case 'WARNING':
        return {
          border: 'border-[#fa5c38]/20',
          bg: 'bg-surface-dark',
          glowColor: 'bg-[#fa5c38]/5',
          iconBg: 'bg-[#fa5c38]/10',
          iconColor: 'text-[#fa5c38]',
          icon: 'notifications_active',
          textColor: 'text-white'
        };
      case 'ADVICE':
        return {
          border: 'border-emerald-500/20',
          bg: 'bg-surface-dark',
          glowColor: 'bg-emerald-500/5',
          iconBg: 'bg-emerald-500/10',
          iconColor: 'text-emerald-500',
          icon: 'check_circle',
          textColor: 'text-white'
        };
      case 'BRIEF':
        return {
          border: 'border-mineral/20',
          bg: 'bg-surface-dark',
          glowColor: 'bg-mineral/5',
          iconBg: 'bg-mineral/10',
          iconColor: 'text-mineral',
          icon: 'article',
          textColor: 'text-white'
        };
      default:
        return {
          border: 'border-white/5',
          bg: 'bg-surface-dark',
          glowColor: 'bg-white/5',
          iconBg: 'bg-white/10',
          iconColor: 'text-white',
          icon: 'info',
          textColor: 'text-white'
        };
    }
  };

  const msgStyle = getMessageCardStyle(latestMessage?.type || 'ADVICE');
  const unreadCount = appMessages.filter(m => !m.isRead).length;
  const streakDays = (() => {
    const dateSet = new Set(mealDates);
    let streak = 0;
    const cursor = new Date();
    while (true) {
      const key = cursor.toISOString().slice(0, 10);
      if (!dateSet.has(key)) break;
      streak += 1;
      cursor.setDate(cursor.getDate() - 1);
    }
    return streak;
  })();
  const sevenDayTrend = Array.from({ length: 7 }, (_, index) => {
    const date = new Date();
    date.setDate(date.getDate() - (6 - index));
    const key = date.toISOString().slice(0, 10);
    return {
      key,
      label: `${date.getMonth() + 1}/${date.getDate()}`,
      count: meals.filter(meal => meal.recordDate === key).length,
    };
  });
  const riskNotes = [
    remaining.sodium < 0 ? '钠摄入已超出建议上限' : null,
    remaining.purine < 0 ? '嘌呤摄入已超出建议上限' : null,
    remaining.calories < 0 ? '热量已超出今日目标' : null,
  ].filter(Boolean) as string[];
  const nextStep = riskNotes[0]
    ? riskNotes[0].includes('钠')
      ? '下一餐优先清淡，少盐少酱油。'
      : riskNotes[0].includes('嘌呤')
        ? '下一餐优先低嘌呤、少汤少内脏。'
        : '下一餐适当减量主食和油脂。'
    : '保持当前节奏，继续记录下一餐。';

  return (
    <div className="flex flex-col w-full h-full pb-28">
      <header className="flex items-center justify-between p-6 pb-2">
        <div className="flex items-center gap-2 text-white/80">
          <span className="material-symbols-outlined text-[28px]">landscape</span>
        </div>
        <h1 className="text-white text-xl font-serif font-bold tracking-wide flex-1 text-center">代谢分析</h1>
        <button
          onClick={() => onViewChange(View.SETTINGS)}
          className="flex items-center justify-center text-white/80 hover:text-primary transition-colors"
        >
          <span className="material-symbols-outlined">settings</span>
        </button>
      </header>

      <section className="px-4 pb-2">
        <div className="grid grid-cols-3 gap-2 rounded-2xl border border-white/5 bg-[#101719]/80 p-3">
          <div className="rounded-xl border border-white/5 bg-white/[0.03] p-3">
            <p className="text-[10px] font-serif font-bold tracking-[0.2em] text-slate-500">连续记录</p>
            <p className="mt-1 text-xl font-serif font-bold tracking-wide text-white">{streakDays}</p>
            <p className="mt-0.5 text-[11px] text-slate-400">天</p>
          </div>
          <div className="rounded-xl border border-white/5 bg-white/[0.03] p-3">
            <p className="text-[10px] font-serif font-bold tracking-[0.2em] text-slate-500">风险摘要</p>
            <p className="mt-1 text-xs leading-relaxed text-white">
              {riskNotes[0] || '当前未见明显超标'}
            </p>
          </div>
          <div className="rounded-xl border border-white/5 bg-white/[0.03] p-3">
            <p className="text-[10px] font-serif font-bold tracking-[0.2em] text-slate-500">下一步</p>
            <p className="mt-1 text-xs leading-relaxed text-white">{nextStep}</p>
          </div>
        </div>
      </section>

      {/* Ring Charts Section */}
      <section className="px-6 pt-8 pb-4">
        <h2 className="text-white/60 font-serif font-bold tracking-wide text-2xl mb-8 text-center">今日代谢余额</h2>
        <div className="flex justify-between items-end gap-2 px-2">

          {/* Left Ring: Calories */}
          <div className="flex flex-col items-center gap-3 flex-1">
            <div
              className="relative w-20 h-20 rounded-full flex items-center justify-center shadow-glow-ochre transition-all duration-1000"
              style={{ background: getProgressStyle(totalConsumed.calories, calorieTarget, '#d9a441', '#1f292b') }}
            >
              <div className="absolute inset-[6px] bg-background-dark rounded-full z-10"></div>
              <div className="relative z-20 flex flex-col items-center">
                <span className="material-symbols-outlined text-ochre text-xl">local_fire_department</span>
              </div>
            </div>
            <div className="text-center">
              <p className={`text-lg font-bold tracking-wide leading-tight font-serif ${getRemainingColor(remaining.calories, 'CAL')}`}>
                {remaining.calories}
              </p>
              <p className="text-white/50 text-xs font-bold uppercase tracking-widest font-serif">千卡</p>
            </div>
          </div>

          {/* Center Ring: Sodium (Primary) */}
          <div className="flex flex-col items-center gap-4 flex-1 -mt-4">
            <div
              className="relative w-28 h-28 rounded-full flex items-center justify-center shadow-glow-cyan transition-all duration-1000"
              style={{ background: getProgressStyle(totalConsumed.sodium, dailyTargets.sodium, '#11c4d4', '#1f292b') }}
            >
              <div className="absolute inset-[6px] bg-background-dark rounded-full z-10"></div>
              <div className="relative z-20 flex flex-col items-center justify-center">
                {(() => {
                  const val = remaining.sodium > 1000
                    ? (remaining.sodium / 1000).toFixed(1) + 'g'
                    : remaining.sodium + 'mg';

                  // Dynamic font sizing logic
                  // text-3xl (~30px) for short text, text-2xl (~24px) for medium, text-lg (~18px) for long
                  let sizeClass = 'text-3xl';
                  if (val.length >= 6) sizeClass = 'text-lg';
                  else if (val.length >= 5) sizeClass = 'text-2xl';

                  return (
                    <span className={`${sizeClass} font-bold tracking-wide font-serif ${getRemainingColor(remaining.sodium, 'SOD')}`}>
                      {val}
                    </span>
                  );
                })()}
                <span className="text-white/50 text-xs font-bold tracking-widest font-serif mt-0.5">钠</span>
              </div>
            </div>
            <p className="text-[10px] text-white/30 font-serif font-bold tracking-widest">
              目标 &lt;{dailyTargets.sodium}mg
            </p>
          </div>

          {/* Right Ring: Purine */}
          <div className="flex flex-col items-center gap-3 flex-1">
            <div
              className="relative w-20 h-20 rounded-full flex items-center justify-center shadow-glow-purple transition-all duration-1000"
              style={{ background: getProgressStyle(totalConsumed.purine, dailyTargets.purine, '#9d4edd', '#1f292b') }}
            >
              <div className="absolute inset-[6px] bg-background-dark rounded-full z-10"></div>
              <div className="relative z-20 flex flex-col items-center">
                <span className="material-symbols-outlined text-purple text-xl">water_drop</span>
              </div>
            </div>
            <div className="text-center">
              <p className={`text-lg font-bold tracking-wide leading-tight font-serif ${getRemainingColor(remaining.purine, 'PUR')}`}>
                {remaining.purine > 0 ? remaining.purine : '超标'}
              </p>
              <p className="text-white/50 text-xs font-bold uppercase tracking-widest font-serif">嘌呤(mg)</p>
            </div>
          </div>

        </div>
      </section>

      <div className="relative h-px w-full my-6 bg-gradient-to-r from-transparent via-white/10 to-transparent"></div>

      <section className="px-4 pb-2">
        <div className="rounded-2xl border border-white/5 bg-[#101719]/80 p-4">
          <div className="flex items-center justify-between">
            <h3 className="font-serif text-base font-bold tracking-wide text-white">7 天记录</h3>
            <span className="text-[10px] font-serif font-bold tracking-[0.2em] text-slate-500">{todayKey}</span>
          </div>
          <div className="mt-4 flex items-end gap-2">
            {sevenDayTrend.map(day => {
              const height = Math.max(12, Math.min(56, day.count * 14 + 12));
              const isToday = day.key === todayKey;
              return (
                <div key={day.key} className="flex min-w-0 flex-1 flex-col items-center gap-2">
                  <div className="flex h-16 w-full items-end justify-center">
                    <div
                      className={`w-full max-w-[18px] rounded-t-md ${isToday ? 'bg-primary shadow-glow-cyan' : 'bg-white/20'}`}
                      style={{ height }}
                      title={`${day.label} ${day.count} 条`}
                    />
                  </div>
                  <span className={`text-[10px] font-serif font-bold tracking-wide ${isToday ? 'text-primary' : 'text-slate-500'}`}>{day.label}</span>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* AI Insights Section */}
      <section className="px-4 flex flex-col gap-5">
        <div className="flex items-center justify-between px-2">
          <div className="flex items-center gap-3">
            <h3 className="text-white font-serif font-bold text-xl tracking-wide">AI 智能洞察</h3>
          </div>
          <button
            onClick={() => onViewChange(View.MESSAGES)}
            className="group flex items-center gap-1.5 text-xs text-slate-400 hover:text-white font-serif font-bold tracking-wide active:scale-95 transition-all"
            aria-label={unreadCount > 0 ? `查看洞察记录，${unreadCount} 条未读` : '查看洞察记录'}
          >
            {unreadCount > 0 && (
              <span className="min-w-5 h-5 px-1.5 rounded-full bg-primary/10 border border-primary/20 text-primary/90 flex items-center justify-center text-[10px] leading-none">
                {unreadCount}
              </span>
            )}
            <span>洞察记录</span>
            <span className="material-symbols-outlined text-[14px] text-slate-500 group-hover:text-white group-hover:translate-x-0.5 transition-transform">chevron_right</span>
          </button>
        </div>

        {/* Dynamic Insight Card based on Latest Message */}
        {latestMessage && (
          <div className={`group relative overflow-hidden rounded-2xl border ${msgStyle.border} p-0 shadow-lg transition-all duration-500 hover:shadow-2xl hover:-translate-y-0.5 animate-fade-in bg-surface-dark`}>
            {/* Background with Gradient */}
            <div className={`absolute inset-0 ${msgStyle.bg} opacity-90`}></div>
            <div className={`absolute inset-0 bg-gradient-to-br from-white/5 to-transparent opacity-50`}></div>

            {/* Glow Effect */}
            <div className={`absolute -top-10 -right-10 w-32 h-32 ${msgStyle.glowColor} rounded-full blur-[60px] opacity-60`}></div>

            <div className="relative z-10 p-5">
              {/* Header Row: Icon + Title */}
              <div className="flex items-center gap-3 mb-3">
                <div className={`w-8 h-8 rounded-lg ${msgStyle.iconBg} flex items-center justify-center ${msgStyle.iconColor} shadow-sm ring-1 ring-white/10`}>
                  <span className="material-symbols-outlined text-[20px]">{msgStyle.icon}</span>
                </div>
                <h4 className={`text-base font-bold font-sans tracking-wide ${msgStyle.textColor} flex-1 truncate`}>
                  {latestMessage.title}
                </h4>
                {/* Optional Status Indicator */}
                <div className={`w-1.5 h-1.5 rounded-full ${msgStyle.iconColor} bg-current animate-pulse opacity-80`}></div>
              </div>

              {/* Content Body */}
              <div className="pl-1">
                <p className="text-slate-300 text-sm leading-relaxed text-justify font-sans tracking-wide opacity-90">
                  {latestMessage.content}
                </p>
              </div>

              <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-white/5 pt-3">
                <div className="flex min-w-0 flex-wrap gap-1.5">
                  {INSIGHT_FEEDBACK_CHOICES.map(choice => {
                    const isSelected = latestInsightFeedback === choice.type;
                    return (
                      <button
                        key={choice.type}
                        type="button"
                        onClick={() => void submitInsightFeedback(choice.type)}
                        disabled={submittingInsightFeedbackId === latestMessage.id}
                        aria-pressed={isSelected}
                        className={`inline-flex h-8 items-center gap-1 rounded-full border px-2.5 font-serif text-[11px] font-bold tracking-wide transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${isSelected
                          ? 'border-primary/45 bg-primary/15 text-primary'
                          : 'border-white/10 bg-white/[0.03] text-slate-400 hover:border-primary/25 hover:text-slate-200'
                          }`}
                      >
                        <span className="material-symbols-outlined text-[14px]">{choice.icon}</span>
                        {choice.label}
                      </button>
                    );
                  })}
                </div>
                {submittingInsightFeedbackId === latestMessage.id && (
                  <span className="font-serif text-[11px] font-bold tracking-wide text-primary">提交中</span>
                )}
                {latestInsightFeedback && submittingInsightFeedbackId !== latestMessage.id && (
                  <span className="font-serif text-[11px] font-bold tracking-wide text-primary/80">已记录</span>
                )}
              </div>
              {insightFeedbackError && (
                <p className="mt-2 font-serif text-[11px] leading-relaxed tracking-wide text-[#fa5c38]">
                  {insightFeedbackError}
                </p>
              )}
            </div>
          </div>
        )}

      </section>
    </div>
  );
};

export default HomeView;
