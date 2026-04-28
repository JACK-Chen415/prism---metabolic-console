import React from 'react';
import { View, Meal, DailyTargets, AppMessage } from '../../types';

interface HomeViewProps {
  onViewChange: (view: View) => void;
  meals: Meal[];
  dailyTargets: DailyTargets;
  latestMessage?: AppMessage;
  appMessages: AppMessage[];
}

const HomeView: React.FC<HomeViewProps> = ({ onViewChange, meals, dailyTargets, latestMessage, appMessages }) => {
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

      {/* AI Insights Section */}
      <section className="px-4 flex flex-col gap-5">
        <div className="flex items-center justify-between px-2">
          <div className="flex items-center gap-3">
            <h3 className="text-white font-serif font-bold text-xl tracking-wide">AI 智能洞察</h3>
            <button
              onClick={() => onViewChange(View.MESSAGES)}
              className="group flex items-center gap-0.5 px-3 py-1.5 rounded-full bg-white/5 border border-white/10 text-xs text-slate-400 hover:text-white hover:bg-white/10 hover:border-white/20 transition-all active:scale-95"
            >
              <span className="tracking-wide font-serif font-bold">所有消息</span>
              <span className="material-symbols-outlined text-[14px] text-slate-500 group-hover:text-white group-hover:translate-x-0.5 transition-transform">chevron_right</span>
            </button>
          </div>
          <button
            onClick={() => onViewChange(View.MESSAGES)}
            className="text-xs text-primary/80 border border-primary/30 px-2 py-1 rounded-full bg-primary/5 font-serif font-bold tracking-wide active:scale-95 transition-transform hover:bg-primary/10"
          >
            {(() => {
              const unreadCount = appMessages.filter(m => !m.isRead).length;
              return unreadCount > 0 ? `${unreadCount} 条新消息` : '暂无新消息';
            })()}
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

              {/* Footer / Action (Optional, for future layout) */}
              {/* <div className="mt-3 pt-3 border-t border-white/5 flex justify-end">
                <span className="text-[10px] text-white/40 font-serif tracking-widest">JUST NOW</span>
              </div> */}
            </div>
          </div>
        )}

        {/* Recommendation Guardrail Card */}
        <div className="group relative overflow-hidden rounded-2xl border border-white/5 p-0 shadow-lg transition-all duration-500 hover:shadow-2xl hover:shadow-glow-purple hover:-translate-y-0.5 bg-surface-dark">
          {/* Background Effects */}
          <div className="absolute inset-0 bg-surface-dark opacity-90"></div>
          <div className="absolute inset-0 bg-gradient-to-br from-purple/10 to-transparent opacity-40"></div>
          <div className="absolute -top-10 -right-10 w-32 h-32 bg-purple/20 rounded-full blur-[60px] opacity-40"></div>

          <div className="relative z-10 p-4">
            <div className="flex items-stretch gap-4">
              <div className="w-24 h-24 shrink-0 rounded-xl bg-black/20 relative overflow-hidden shadow-md ring-1 ring-white/10 flex items-center justify-center">
                <span className="material-symbols-outlined text-purple/70 text-4xl">rule</span>
              </div>

              <div className="flex flex-col justify-between py-1 flex-1 min-w-0">
                <div>
                  <div className="flex justify-between items-start">
                    <h4 className="text-white text-base font-bold font-serif tracking-wide truncate pr-2 transition-colors">推荐安全提示</h4>
                    <div className="px-2 py-0.5 rounded-full bg-white/5 border border-white/10">
                      <span className="text-[10px] text-white/40 font-bold font-serif tracking-wide">未开放</span>
                    </div>
                  </div>
                  <p className="text-slate-400 text-sm mt-1.5 line-clamp-2 font-serif tracking-wide leading-snug">
                    个性化菜谱推荐需先经过过敏与慢病规则校验。当前仅展示摄入余额，不再输出未经校验的具体菜品。
                  </p>
                </div>

                <div className="flex items-center gap-2 mt-2">
                  <span className="text-[10px] px-2 py-0.5 rounded-md border border-purple/20 text-purple/90 bg-purple/10 font-bold tracking-wide backdrop-blur-sm">规则引擎待接入</span>
                  <span className="text-[10px] px-2 py-0.5 rounded-md border border-ochre/20 text-ochre/90 bg-ochre/10 font-bold tracking-wide backdrop-blur-sm">嘌呤余额 {remaining.purine}mg</span>
                </div>
              </div>
            </div>
          </div>
        </div>

      </section>
    </div>
  );
};

export default HomeView;
