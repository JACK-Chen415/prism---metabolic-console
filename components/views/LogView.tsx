import React, { useState, useEffect } from 'react';
import { UserProfile, Meal, FoodCategory, DailyTargets } from '../../types';
import { HEALTH_TIPS } from '../../data/healthTips';

interface LogViewProps {
  userProfile: UserProfile;
  meals: Meal[];
  dailyTargets: DailyTargets;
  onAddMeal: (meal: Meal) => void;
}

const FOOD_CATEGORIES: { id: FoodCategory; label: string; icon: string; color: string }[] = [
  { id: 'STAPLE', label: '主食', icon: 'ramen_dining', color: 'text-amber-400' },
  { id: 'MEAT', label: '肉蛋', icon: 'egg', color: 'text-red-400' },
  { id: 'VEG', label: '蔬果', icon: 'eco', color: 'text-emerald-400' },
  { id: 'DRINK', label: '饮品', icon: 'local_cafe', color: 'text-blue-400' },
  { id: 'SNACK', label: '零食', icon: 'cookie', color: 'text-purple-400' },
];

const LogView: React.FC<LogViewProps> = ({ userProfile, meals, dailyTargets, onAddMeal }) => {
  // BMI Calculation
  const bmi = (userProfile.weight / Math.pow(userProfile.height / 100, 2)).toFixed(1);
  const getBmiStatus = (bmiVal: string) => {
    const val = parseFloat(bmiVal);
    if (val < 18.5) return { label: '偏瘦', color: 'text-ochre', bg: 'bg-ochre/10', border: 'border-ochre/20' };
    if (val < 24) return { label: '标准', color: 'text-emerald-500', bg: 'bg-emerald-500/10', border: 'border-emerald-500/20' };
    if (val < 28) return { label: '超重', color: 'text-ochre', bg: 'bg-ochre/10', border: 'border-ochre/20' };
    return { label: '肥胖', color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/20' };
  };
  const bmiStatus = getBmiStatus(bmi);

  // Targets from Props
  const targetCalories = dailyTargets.calories;

  // State
  const [isAdding, setIsAdding] = useState(false);
  const [dailyTip, setDailyTip] = useState('');
  const [mealInput, setMealInput] = useState<{
    name: string;
    portion: string;
    type: 'BREAKFAST' | 'LUNCH' | 'DINNER' | 'SNACK';
    category: FoodCategory;
    note: string;
  }>({ name: '', portion: '', type: 'DINNER', category: 'STAPLE', note: '' });

  const refreshDailyTip = (e?: React.MouseEvent) => {
    e?.stopPropagation();
    const randomIndex = Math.floor(Math.random() * HEALTH_TIPS.length);
    setDailyTip(HEALTH_TIPS[randomIndex]);
  };

  // Initialize Random Health Tip on Mount
  useEffect(() => {
    refreshDailyTip();
  }, []);

  const totalCalories = meals.reduce((sum, item) => sum + item.calories, 0);
  const progress = Math.min((totalCalories / targetCalories) * 100, 100);
  const remainingCalories = Math.max(targetCalories - totalCalories, 0);

  const addMeal = () => {
    if(!mealInput.name) return;
    
    // Improved AI Simulation Logic
    let estCal = 0;
    let estSod = 0;
    let estPur = 0;

    // Base calculation
    switch(mealInput.category) {
        case 'MEAT':
            estCal = Math.floor(Math.random() * 300) + 200; // 200-500
            estSod = Math.floor(Math.random() * 400) + 100; // 100-500
            estPur = Math.floor(Math.random() * 150) + 50;  // High Purine
            break;
        case 'VEG':
            estCal = Math.floor(Math.random() * 100) + 50;  // 50-150
            estSod = Math.floor(Math.random() * 50) + 10;   // Low Sodium
            estPur = Math.floor(Math.random() * 20) + 5;    // Low Purine
            break;
        case 'STAPLE':
            estCal = Math.floor(Math.random() * 400) + 150; // 150-550
            estSod = Math.floor(Math.random() * 200) + 50;  
            estPur = Math.floor(Math.random() * 50) + 10;
            break;
        case 'SNACK':
            estCal = Math.floor(Math.random() * 400) + 100;
            estSod = Math.floor(Math.random() * 500) + 50;  // potentially salty
            estPur = Math.floor(Math.random() * 30) + 0;
            break;
        case 'DRINK':
            estCal = Math.floor(Math.random() * 200) + 0;
            estSod = Math.floor(Math.random() * 50) + 0;
            estPur = Math.floor(Math.random() * 50) + 0;
            break;
    }

    // AI Analysis adjustment based on Note
    if (mealInput.note) {
        const note = mealInput.note;
        // Sodium adjustment
        if (note.includes('咸') || note.includes('盐') || note.includes('酱') || note.includes('卤')) {
            estSod += 300;
        }
        // Calories adjustment
        if (note.includes('油') || note.includes('炸') || note.includes('煎') || note.includes('肥')) {
            estCal += 100;
        }
        // Purine adjustment
        if (note.includes('汤') || note.includes('内脏') || note.includes('海鲜')) {
            estPur += 80;
        }
        // Spicy sauces often have hidden sodium/oil
        if (note.includes('辣')) {
            estSod += 50; 
            estCal += 30;
        }
    }

    onAddMeal({
        id: Date.now().toString(),
        name: mealInput.name,
        portion: mealInput.portion || '1份',
        calories: estCal,
        sodium: estSod,
        purine: estPur,
        type: mealInput.type,
        category: mealInput.category,
        note: mealInput.note
    });
    
    setIsAdding(false);
    setMealInput({ name: '', portion: '', type: 'DINNER', category: 'STAPLE', note: '' });
  };

  return (
    <div className="flex flex-col w-full pb-28 relative">
      <div className="sticky top-0 z-20 flex items-center bg-background-dark/90 backdrop-blur-md p-4 pb-2 justify-between border-b border-white/5">
        <h2 className="text-xl font-bold leading-tight tracking-wide flex-1 text-white font-serif">生命日志</h2>
        <div className="flex items-center justify-center bg-surface-dark rounded-full px-3 py-1 border border-white/10">
          <span className="material-symbols-outlined text-base mr-1 text-primary">calendar_today</span>
          <p className="text-mineral text-sm font-bold leading-normal tracking-wide shrink-0 font-serif">2024年10月24日</p>
        </div>
      </div>

      <div className="p-4 pt-6">
        {/* Main Insight Card */}
        <div className="relative overflow-hidden rounded-2xl shadow-lg group">
          <div 
            className="absolute inset-0 bg-cover bg-center transition-transform duration-700 group-hover:scale-105"
            style={{ backgroundImage: 'url("/images/log-header.png")' }}
          />
          <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/40 to-black/10"></div>
          <div className="relative z-10 flex flex-col items-start justify-end pt-[140px] p-5">
            <div className="flex items-center justify-between w-full mb-2">
                <h3 className="text-white tracking-wide text-2xl font-bold leading-tight font-serif">每日健康建议</h3>
                <button 
                    onClick={refreshDailyTip}
                    className="flex items-center gap-1 px-2 py-1 rounded-lg bg-white/10 hover:bg-white/20 border border-white/10 backdrop-blur-md transition-all active:scale-95 group"
                >
                    <span className="material-symbols-outlined text-xs text-slate-300 group-hover:text-white transition-colors">refresh</span>
                    <span className="text-[10px] font-serif font-bold text-slate-300 group-hover:text-white transition-colors tracking-wide">换一条</span>
                </button>
            </div>
            <p className="text-slate-200 text-sm font-bold leading-relaxed font-serif tracking-wide">
              {dailyTip || "正在获取今日健康建议..."}
            </p>
          </div>
        </div>

        {/* Basic Vitals */}
        <div className="flex flex-col gap-0 mt-6">
          <h3 className="text-white tracking-wide text-lg font-bold leading-tight px-2 pb-3 pt-2 font-serif">基础体征</h3>
          <div className="grid grid-cols-2 gap-3">
            {/* BMI Card */}
            <div className="flex flex-col justify-between gap-3 rounded-2xl p-4 bg-surface-dark shadow-sm border border-white/5">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-primary text-[20px]">accessibility_new</span>
                  <p className="text-slate-400 text-sm font-bold font-serif tracking-wide">BMI</p>
                </div>
                {/* Dynamic BMI status indicator */}
                <div className={`px-1.5 py-0.5 rounded ${bmiStatus.bg} border ${bmiStatus.border}`}>
                    <p className={`${bmiStatus.color} text-[10px] font-bold font-serif tracking-wide`}>{bmiStatus.label}</p>
                </div>
              </div>
              <div>
                <p className="text-white tracking-wide text-2xl font-bold leading-tight font-serif">{bmi}</p>
                <div className="flex items-center gap-1 mt-1">
                  <p className="text-slate-400 text-[10px] ml-0.5 font-serif font-bold tracking-wide opacity-70">
                    {userProfile.height}cm | {userProfile.weight}kg
                  </p>
                </div>
              </div>
            </div>
            
            {/* BMR (Calculated Estimate) */}
            <div className="flex flex-col justify-between gap-3 rounded-2xl p-4 bg-surface-dark shadow-sm border border-white/5">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-primary text-[20px]">local_fire_department</span>
                  <p className="text-slate-400 text-sm font-bold font-serif tracking-wide">每日基础代谢</p>
                </div>
                <div className="h-2 w-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"></div>
              </div>
              <div>
                <p className="text-white tracking-wide text-2xl font-bold leading-tight font-serif">{Math.round(targetCalories / 1.375)}</p>
                <div className="flex items-center justify-between mt-1 pr-1">
                    <p className="text-slate-400 text-xs font-bold font-serif tracking-wide">kcal/day</p>
                    <span className="text-[10px] text-slate-500 font-serif font-bold tracking-wide opacity-60">基于{userProfile.gender === 'MALE' ? '男' : '女'}性</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Calorie Statistics Section */}
        <div className="flex flex-col mt-6">
            <div className="flex items-center justify-between px-2 pb-3 pt-2">
                <h3 className="text-white tracking-wide text-lg font-bold leading-tight font-serif">热量统计</h3>
                <button 
                    onClick={() => setIsAdding(true)}
                    className="flex items-center gap-1 text-primary text-xs font-bold px-3 py-1.5 bg-primary/10 rounded-full border border-primary/20 hover:bg-primary/20 transition-colors active:scale-95 font-serif tracking-wide"
                >
                    <span className="material-symbols-outlined text-[14px]">add</span>
                    记一笔
                </button>
            </div>
            
            {/* Calorie Summary Card */}
            <div className="bg-surface-dark border border-white/5 rounded-2xl p-5 shadow-sm relative overflow-hidden mb-4">
                 {/* Decorative background glow */}
                 <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-2xl -mr-10 -mt-10"></div>

                 <div className="flex justify-between items-end mb-4 relative z-10">
                     <div>
                         <p className="text-slate-400 text-xs font-serif font-bold tracking-wide mb-1 flex items-center gap-1">
                             今日摄入 
                             <span className="text-white/20">/</span> 
                             <span className="text-slate-500">目标 {targetCalories}</span>
                         </p>
                         <div className="flex items-baseline gap-1.5">
                             <span className={`text-4xl font-serif font-bold tracking-wide ${totalCalories > targetCalories ? 'text-ochre' : 'text-white'}`}>
                                {totalCalories}
                             </span>
                             <span className="text-xs text-slate-500 font-bold font-serif tracking-wide">kcal</span>
                         </div>
                     </div>
                     <div className="text-right">
                         <p className="text-xs text-slate-500 mb-1 font-serif font-bold tracking-wide">剩余额度</p>
                         <span className={`text-xl font-serif font-bold tracking-wide ${remainingCalories > 0 ? 'text-emerald-500' : 'text-ochre'}`}>
                             {remainingCalories}
                         </span>
                     </div>
                 </div>
                 
                 {/* Progress Bar */}
                 <div className="h-2.5 w-full bg-black/40 rounded-full overflow-hidden mb-4 border border-white/5 relative z-10">
                     <div 
                        className={`h-full rounded-full transition-all duration-1000 ease-out relative ${totalCalories > targetCalories ? 'bg-gradient-to-r from-ochre to-red-400' : 'bg-gradient-to-r from-emerald-500 to-primary'}`} 
                        style={{ width: `${progress}%` }}
                     >
                         <div className="absolute inset-0 bg-white/20 animate-[pulse_2s_infinite]"></div>
                     </div>
                 </div>

                 {/* AI Suggestion Box */}
                 <div className="bg-white/5 rounded-xl p-3 flex gap-3 items-start border border-white/5 relative z-10">
                     <div className="shrink-0 w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center text-primary mt-0.5">
                        <span className="material-symbols-outlined text-sm">smart_toy</span>
                     </div>
                     <p className="text-xs text-slate-300 leading-relaxed text-justify font-serif tracking-wide">
                         {totalCalories > targetCalories 
                          ? "今日热量摄入已超过目标。建议晚餐减少碳水化合物摄入（如米饭、面条），并增加 30 分钟中等强度运动来平衡热量盈余。" 
                          : "今日热量控制良好。建议晚餐补充优质蛋白质（如鱼肉、豆腐），促进夜间基础代谢与身体修复。"}
                     </p>
                 </div>
            </div>

            {/* Meal List */}
            <div className="flex flex-col gap-3">
                {meals.map(meal => {
                    const categoryConfig = FOOD_CATEGORIES.find(c => c.id === meal.category) || FOOD_CATEGORIES[0];
                    return (
                        <div key={meal.id} className="group flex flex-col p-3.5 rounded-xl bg-surface-dark border border-white/5 hover:border-white/10 transition-colors gap-3">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3.5">
                                    <div className={`w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center border border-white/5 group-hover:scale-105 transition-transform ${categoryConfig.color}`}>
                                        <span className="material-symbols-outlined text-2xl">{categoryConfig.icon}</span>
                                    </div>
                                    <div className="flex flex-col gap-0.5">
                                        <p className="text-white text-sm font-bold tracking-wide font-serif">{meal.name}</p>
                                        <div className="flex items-center gap-2">
                                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-slate-400 border border-white/5 font-serif font-bold tracking-wide">
                                                {meal.type === 'BREAKFAST' ? '早餐' : meal.type === 'LUNCH' ? '午餐' : meal.type === 'DINNER' ? '晚餐' : '加餐'}
                                            </span>
                                            <p className="text-slate-500 text-xs font-serif font-bold tracking-wide">{meal.portion}</p>
                                        </div>
                                        {/* Display Note if exists */}
                                        {meal.note && (
                                            <p className="text-[10px] text-slate-500 font-serif mt-1 flex items-center gap-1">
                                                <span className="material-symbols-outlined text-[10px]">edit_note</span>
                                                {meal.note}
                                            </p>
                                        )}
                                    </div>
                                </div>
                                <div className="text-right flex flex-col items-end">
                                    <p className="text-white text-base font-serif font-bold tracking-wide">{meal.calories}</p>
                                    <p className="text-slate-500 text-[10px] font-serif font-bold tracking-wide leading-none">kcal</p>
                                </div>
                            </div>
                            
                            {/* Nutrients Detail Line */}
                            <div className="flex items-center justify-between pl-[54px] border-t border-white/5 pt-2">
                                <div className="flex items-center gap-4">
                                    <div className="flex items-center gap-1.5">
                                        <span className="w-1.5 h-1.5 rounded-full bg-primary/50"></span>
                                        <span className="text-[10px] text-slate-400 font-serif font-bold tracking-wide">钠: {meal.sodium}mg</span>
                                    </div>
                                    <div className="flex items-center gap-1.5">
                                        <span className="w-1.5 h-1.5 rounded-full bg-purple/50"></span>
                                        <span className="text-[10px] text-slate-400 font-serif font-bold tracking-wide">嘌呤: {meal.purine}mg</span>
                                    </div>
                                </div>
                                <span className="text-[9px] text-slate-500/80 bg-white/5 px-1 py-0.5 rounded border border-white/5 font-serif tracking-wide transform scale-90 origin-right">
                                    估计
                                </span>
                            </div>
                        </div>
                    );
                })}
                
                {meals.length === 0 && (
                    <div className="py-8 text-center border border-dashed border-white/10 rounded-xl">
                        <p className="text-slate-500 text-xs font-serif font-bold tracking-wide">今日暂无饮食记录</p>
                    </div>
                )}
            </div>
        </div>

      </div>

      {/* Add Meal Modal */}
      {isAdding && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
              <div className="bg-[#131b1d] border border-white/10 w-full max-w-xs rounded-2xl p-5 shadow-2xl relative max-h-[90vh] overflow-y-auto">
                  <button 
                      onClick={() => setIsAdding(false)}
                      className="absolute top-4 right-4 text-white/40 hover:text-white transition-colors"
                  >
                      <span className="material-symbols-outlined">close</span>
                  </button>
                  <h3 className="text-white font-serif tracking-wide text-lg font-bold mb-5 text-center">记录餐食</h3>
                  
                  <div className="space-y-5">
                       {/* Time Selector */}
                       <div className="flex gap-2 p-1 bg-black/20 rounded-lg">
                           {['BREAKFAST', 'LUNCH', 'DINNER', 'SNACK'].map((t) => (
                               <button 
                                 key={t}
                                 onClick={() => setMealInput({...mealInput, type: t as any})}
                                 className={`flex-1 py-2 rounded-md text-[10px] font-bold tracking-wide font-serif transition-all ${mealInput.type === t ? 'bg-primary text-[#080c0d] shadow-sm' : 'text-slate-500 hover:text-slate-300'}`}
                               >
                                   {t === 'BREAKFAST' ? '早' : t === 'LUNCH' ? '午' : t === 'DINNER' ? '晚' : '加'}
                               </button>
                           ))}
                       </div>

                       {/* Category Selector */}
                       <div>
                            <label className="text-xs text-slate-500 ml-1 mb-2 block font-serif font-bold tracking-wide">食物类型</label>
                            <div className="grid grid-cols-5 gap-2">
                                {FOOD_CATEGORIES.map(cat => (
                                    <button
                                        key={cat.id}
                                        onClick={() => setMealInput({...mealInput, category: cat.id})}
                                        className={`flex flex-col items-center justify-center gap-1 py-2 rounded-xl border transition-all ${
                                            mealInput.category === cat.id 
                                            ? 'bg-white/10 border-primary/50 text-primary' 
                                            : 'bg-black/20 border-transparent text-slate-500 hover:bg-white/5'
                                        }`}
                                    >
                                        <span className={`material-symbols-outlined text-xl ${mealInput.category === cat.id ? 'icon-filled' : ''}`}>
                                            {cat.icon}
                                        </span>
                                        <span className="text-[10px] font-bold font-serif tracking-wide">{cat.label}</span>
                                    </button>
                                ))}
                            </div>
                       </div>
                       
                       <div className="space-y-3">
                           <div>
                               <label className="text-xs text-slate-500 ml-1 mb-1 block font-serif font-bold tracking-wide">食物名称</label>
                               <input 
                                  type="text" 
                                  placeholder="如: 牛肉面"
                                  value={mealInput.name}
                                  onChange={e => setMealInput({...mealInput, name: e.target.value})}
                                  className="w-full bg-black/20 border border-white/10 rounded-xl p-3 text-white text-sm outline-none focus:border-primary/50 transition-colors font-serif tracking-wide"
                               />
                           </div>
                           <div>
                               <label className="text-xs text-slate-500 ml-1 mb-1 block font-serif font-bold tracking-wide">分量估算</label>
                               <input 
                                  type="text" 
                                  placeholder="如: 1碗, 200g"
                                  value={mealInput.portion}
                                  onChange={e => setMealInput({...mealInput, portion: e.target.value})}
                                  className="w-full bg-black/20 border border-white/10 rounded-xl p-3 text-white text-sm outline-none focus:border-primary/50 transition-colors font-serif tracking-wide"
                               />
                           </div>
                           {/* Note Input */}
                           <div>
                               <label className="text-xs text-slate-500 ml-1 mb-1 block font-serif font-bold tracking-wide">备注信息 (口味/特殊说明)</label>
                               <textarea 
                                  placeholder="如: 多放了酱油, 比较咸, 少油..."
                                  value={mealInput.note}
                                  onChange={e => setMealInput({...mealInput, note: e.target.value})}
                                  rows={2}
                                  className="w-full bg-black/20 border border-white/10 rounded-xl p-3 text-white text-sm outline-none focus:border-primary/50 transition-colors font-serif tracking-wide resize-none"
                               />
                           </div>
                       </div>

                       <div className="pt-2 flex flex-col gap-3">
                           <button 
                              onClick={addMeal}
                              className="w-full bg-gradient-to-r from-primary to-[#45b7aa] text-background-dark font-bold py-3.5 rounded-xl hover:shadow-[0_0_20px_rgba(17,196,212,0.4)] transition-all active:scale-[0.98] flex items-center justify-center gap-2 font-serif tracking-wide"
                           >
                               <span className="material-symbols-outlined text-lg">auto_awesome</span>
                               AI 智能估算记录(含钠/嘌呤)
                           </button>
                           <button 
                              onClick={() => setIsAdding(false)}
                              className="w-full text-slate-500 text-xs py-2 hover:text-white transition-colors font-serif font-bold tracking-wide"
                           >
                               取消
                           </button>
                       </div>
                  </div>
              </div>
          </div>
      )}
    </div>
  );
};

export default LogView;