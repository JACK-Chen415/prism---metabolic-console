import React, { useState, useEffect } from 'react';
import { UserProfile, Meal, FoodCategory, DailyTargets, MealUpdateInput } from '../../types';
import { HEALTH_TIPS } from '../../data/healthTips';
import { formatChineseDate, getLocalDateString } from '../../services/date';
import { estimateMealNutrition } from '../../services/mealEstimation';

interface LogViewProps {
  userProfile: UserProfile;
  meals: Meal[];
  dailyTargets: DailyTargets;
  onAddMeal: (meal: Meal) => void;
  onUpdateMeal: (mealId: string, changes: MealUpdateInput) => Promise<void>;
  onDeleteMeal: (mealId: string) => Promise<void>;
}

const FOOD_CATEGORIES: { id: FoodCategory; label: string; icon: string; color: string }[] = [
  { id: 'STAPLE', label: '主食', icon: 'ramen_dining', color: 'text-amber-400' },
  { id: 'MEAT', label: '肉蛋', icon: 'egg', color: 'text-red-400' },
  { id: 'VEG', label: '蔬果', icon: 'eco', color: 'text-emerald-400' },
  { id: 'DRINK', label: '饮品', icon: 'local_cafe', color: 'text-blue-400' },
  { id: 'SNACK', label: '零食', icon: 'cookie', color: 'text-purple-400' },
];

const MEAL_TYPES: Array<{ id: Meal['type']; label: string; shortLabel: string }> = [
  { id: 'BREAKFAST', label: '早餐', shortLabel: '早' },
  { id: 'LUNCH', label: '午餐', shortLabel: '午' },
  { id: 'DINNER', label: '晚餐', shortLabel: '晚' },
  { id: 'SNACK', label: '加餐', shortLabel: '加' },
];

type MealEditInput = {
  name: string;
  portion: string;
  type: Meal['type'];
  category: FoodCategory;
  calories: string;
  sodium: string;
  purine: string;
  protein: string;
  carbs: string;
  fat: string;
  fiber: string;
  note: string;
};

const formatMealType = (type: Meal['type']) => (
  MEAL_TYPES.find(item => item.id === type)?.label || '晚餐'
);

const formatOptionalNumber = (value?: number) => (
  value === undefined || value === null ? '' : String(value)
);

const mealToEditInput = (meal: Meal): MealEditInput => ({
  name: meal.name,
  portion: meal.portion || '1份',
  type: meal.type,
  category: meal.category,
  calories: String(meal.calories ?? 0),
  sodium: String(meal.sodium ?? 0),
  purine: String(meal.purine ?? 0),
  protein: formatOptionalNumber(meal.protein),
  carbs: formatOptionalNumber(meal.carbs),
  fat: formatOptionalNumber(meal.fat),
  fiber: formatOptionalNumber(meal.fiber),
  note: meal.note || '',
});

const parseRequiredNumber = (value: string) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
};

const parseOptionalNumber = (value: string) => {
  if (!value.trim()) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined;
};

const LogView: React.FC<LogViewProps> = ({ userProfile, meals, dailyTargets, onAddMeal, onUpdateMeal, onDeleteMeal }) => {
  // BMI Calculation
  const localBmi = userProfile.height && userProfile.weight
    ? Number((userProfile.weight / Math.pow(userProfile.height / 100, 2)).toFixed(1))
    : null;
  const bmiValue = dailyTargets.bmi ?? (dailyTargets.has_complete_profile === false ? null : localBmi);
  const getBmiStatus = (bmiVal: number | null) => {
    if (bmiVal === null) return { label: '待完善', color: 'text-slate-400', bg: 'bg-white/5', border: 'border-white/10' };
    const val = bmiVal;
    if (val < 18.5) return { label: '偏瘦', color: 'text-ochre', bg: 'bg-ochre/10', border: 'border-ochre/20' };
    if (val < 24) return { label: '标准', color: 'text-emerald-500', bg: 'bg-emerald-500/10', border: 'border-emerald-500/20' };
    if (val < 28) return { label: '超重', color: 'text-ochre', bg: 'bg-ochre/10', border: 'border-ochre/20' };
    return { label: '肥胖', color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/20' };
  };
  const bmiStatus = getBmiStatus(bmiValue);

  // Targets from Props
  const targetCalories = dailyTargets.recommended_calorie_target || dailyTargets.calories || 0;
  const bmrDisplay = dailyTargets.bmr_range
    ? `${dailyTargets.bmr_range.min} - ${dailyTargets.bmr_range.max}`
    : dailyTargets.bmr ? String(dailyTargets.bmr) : '--';
  const targetExplanation = dailyTargets.has_complete_profile === false && targetCalories > 0
    ? `当前身体资料未完全填写，已按估算策略计算。${dailyTargets.target_explanation || ''}`
    : dailyTargets.target_explanation || '请先在设置中完善身高、体重、年龄、性别，以获得更准确估算。';
  const todayLabel = formatChineseDate(getLocalDateString());

  // State
  const [isAdding, setIsAdding] = useState(false);
  const [editingMeal, setEditingMeal] = useState<Meal | null>(null);
  const [editInput, setEditInput] = useState<MealEditInput | null>(null);
  const [deletingMeal, setDeletingMeal] = useState<Meal | null>(null);
  const [isSavingEdit, setIsSavingEdit] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
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
  const progress = targetCalories > 0 ? Math.min((totalCalories / targetCalories) * 100, 100) : 0;
  const remainingCalories = targetCalories > 0 ? Math.max(targetCalories - totalCalories, 0) : 0;
  const calorieGuidance = targetCalories <= 0
    ? '请先在设置中完善身高、体重、年龄、性别，以获得更准确的基础代谢和推荐摄入目标。'
    : totalCalories > targetCalories
      ? `今日热量摄入已超过推荐目标。${targetExplanation}`
      : targetExplanation;

  const addMeal = () => {
    if(!mealInput.name) return;
    const estimated = estimateMealNutrition(mealInput);

    const newClientId = crypto.randomUUID();
    onAddMeal({
        id: newClientId,
        clientId: newClientId,
        name: mealInput.name,
        portion: mealInput.portion || '1份',
        calories: estimated.calories,
        sodium: estimated.sodium,
        purine: estimated.purine,
        type: mealInput.type,
        category: mealInput.category,
        note: mealInput.note,
        source: 'manual',
        estimatedFields: ['calories', 'sodium', 'purine'],
        ruleWarnings: [],
    });
    
    setIsAdding(false);
    setMealInput({ name: '', portion: '', type: 'DINNER', category: 'STAPLE', note: '' });
  };

  const openEditMeal = (meal: Meal) => {
    setFeedbackMessage(null);
    setActionError(null);
    setEditingMeal(meal);
    setEditInput(mealToEditInput(meal));
  };

  const closeEditMeal = () => {
    if (isSavingEdit) return;
    setEditingMeal(null);
    setEditInput(null);
    setActionError(null);
  };

  const patchEditInput = (patch: Partial<MealEditInput>) => {
    setEditInput(prev => prev ? { ...prev, ...patch } : prev);
  };

  const saveEditedMeal = async () => {
    if (!editingMeal || !editInput) return;
    if (!editInput.name.trim()) {
      setActionError('食物名称不能为空。');
      return;
    }

    setIsSavingEdit(true);
    setActionError(null);
    try {
      await onUpdateMeal(editingMeal.id, {
        name: editInput.name.trim(),
        portion: editInput.portion.trim() || '1份',
        type: editInput.type,
        category: editInput.category,
        calories: parseRequiredNumber(editInput.calories),
        sodium: parseRequiredNumber(editInput.sodium),
        purine: parseRequiredNumber(editInput.purine),
        protein: parseOptionalNumber(editInput.protein),
        carbs: parseOptionalNumber(editInput.carbs),
        fat: parseOptionalNumber(editInput.fat),
        fiber: parseOptionalNumber(editInput.fiber),
        note: editInput.note.trim(),
      });
      setFeedbackMessage('餐食记录已更新。');
      setEditingMeal(null);
      setEditInput(null);
      setActionError(null);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '保存失败，请稍后再试。');
    } finally {
      setIsSavingEdit(false);
    }
  };

  const confirmDeleteMeal = async () => {
    if (!deletingMeal) return;

    setIsDeleting(true);
    setActionError(null);
    try {
      await onDeleteMeal(deletingMeal.id);
      setFeedbackMessage('餐食记录已删除。');
      setDeletingMeal(null);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '删除失败，请稍后再试。');
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="flex flex-col w-full pb-28 relative">
      <div className="sticky top-0 z-20 flex items-center bg-background-dark/90 backdrop-blur-md p-4 pb-2 justify-between border-b border-white/5">
        <h2 className="text-xl font-bold leading-tight tracking-wide flex-1 text-white font-serif">生命日志</h2>
        <div className="flex items-center justify-center bg-surface-dark rounded-full px-3 py-1 border border-white/10">
          <span className="material-symbols-outlined text-base mr-1 text-primary">calendar_today</span>
          <p className="text-mineral text-sm font-bold leading-normal tracking-wide shrink-0 font-serif">{todayLabel}</p>
        </div>
      </div>

      <div className="p-4 pt-6">
        {(feedbackMessage || actionError) && (
          <div className={`mb-4 rounded-xl border px-3 py-2 text-xs font-serif font-bold tracking-wide ${
            actionError
              ? 'bg-red-500/10 border-red-500/20 text-red-200'
              : 'bg-emerald-500/10 border-emerald-500/20 text-emerald-200'
          }`}>
            {actionError || feedbackMessage}
          </div>
        )}

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
                <p className="text-white tracking-wide text-2xl font-bold leading-tight font-serif">{bmiValue ?? '--'}</p>
                <div className="flex items-center gap-1 mt-1">
                  <p className="text-slate-400 text-[10px] ml-0.5 font-serif font-bold tracking-wide opacity-70">
                    {userProfile.height}cm | {userProfile.weight}kg
                  </p>
                </div>
              </div>
            </div>
            
            {/* BMR returned by backend target service */}
            <div className="flex flex-col justify-between gap-3 rounded-2xl p-4 bg-surface-dark shadow-sm border border-white/5">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-primary text-[20px]">local_fire_department</span>
                  <p className="text-slate-400 text-sm font-bold font-serif tracking-wide">每日基础代谢</p>
                </div>
                <div className="h-2 w-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"></div>
              </div>
              <div>
                <p className={`text-white tracking-wide font-bold leading-tight font-serif ${dailyTargets.bmr_range ? 'text-xl' : 'text-2xl'}`}>{bmrDisplay}</p>
                <div className="flex items-center justify-between mt-1 pr-1">
                    <p className="text-slate-400 text-xs font-bold font-serif tracking-wide">kcal/day</p>
                    <span className="text-[10px] text-slate-500 font-serif font-bold tracking-wide opacity-60">估算值</span>
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
                             <span className="text-slate-500">目标 {targetCalories > 0 ? targetCalories : '--'}</span>
                         </p>
                         <div className="flex items-baseline gap-1.5">
                             <span className={`text-4xl font-serif font-bold tracking-wide ${targetCalories > 0 && totalCalories > targetCalories ? 'text-ochre' : 'text-white'}`}>
                                {totalCalories}
                             </span>
                             <span className="text-xs text-slate-500 font-bold font-serif tracking-wide">kcal</span>
                         </div>
                     </div>
                     <div className="text-right">
                         <p className="text-xs text-slate-500 mb-1 font-serif font-bold tracking-wide">剩余额度</p>
                         <span className={`text-xl font-serif font-bold tracking-wide ${remainingCalories > 0 ? 'text-emerald-500' : 'text-ochre'}`}>
                             {targetCalories > 0 ? remainingCalories : '--'}
                         </span>
                     </div>
                 </div>
                 
                 {/* Progress Bar */}
                 <div className="h-2.5 w-full bg-black/40 rounded-full overflow-hidden mb-4 border border-white/5 relative z-10">
                     <div 
                        className={`h-full rounded-full transition-all duration-1000 ease-out relative ${targetCalories > 0 && totalCalories > targetCalories ? 'bg-gradient-to-r from-ochre to-red-400' : 'bg-gradient-to-r from-emerald-500 to-primary'}`} 
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
                          {calorieGuidance}
                     </p>
                 </div>
            </div>

            {/* Meal List */}
            <div className="flex flex-col gap-3">
                {meals.map(meal => {
                    const categoryConfig = FOOD_CATEGORIES.find(c => c.id === meal.category) || FOOD_CATEGORIES[0];
                    const macroSummary = [
                      meal.protein !== undefined ? `蛋白 ${meal.protein}g` : null,
                      meal.carbs !== undefined ? `碳水 ${meal.carbs}g` : null,
                      meal.fat !== undefined ? `脂肪 ${meal.fat}g` : null,
                      meal.fiber !== undefined ? `纤维 ${meal.fiber}g` : null,
                    ].filter((item): item is string => Boolean(item));
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
                                                {formatMealType(meal.type)}
                                            </span>
                                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary border border-primary/20 font-serif font-bold tracking-wide">
                                                {meal.source === 'voice' ? '语音' : meal.source === 'photo' ? '拍照' : meal.source === 'ai_quick_log' ? 'AI' : '手动'}
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
                                <div className="text-right flex flex-col items-end gap-1">
                                    <p className="text-white text-base font-serif font-bold tracking-wide">{meal.calories}</p>
                                    <p className="text-slate-500 text-[10px] font-serif font-bold tracking-wide leading-none">kcal</p>
                                    <div className="flex items-center gap-1 pt-1">
                                      <button
                                        onClick={() => openEditMeal(meal)}
                                        className="w-7 h-7 rounded-lg flex items-center justify-center text-slate-500 hover:text-primary hover:bg-primary/10 transition-colors"
                                        title="编辑记录"
                                        aria-label="编辑记录"
                                      >
                                        <span className="material-symbols-outlined text-[16px]">edit</span>
                                      </button>
                                      <button
                                        onClick={() => {
                                          setFeedbackMessage(null);
                                          setActionError(null);
                                          setDeletingMeal(meal);
                                        }}
                                        className="w-7 h-7 rounded-lg flex items-center justify-center text-slate-500 hover:text-red-300 hover:bg-red-500/10 transition-colors"
                                        title="删除记录"
                                        aria-label="删除记录"
                                      >
                                        <span className="material-symbols-outlined text-[16px]">delete</span>
                                      </button>
                                    </div>
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
                                     {meal.estimatedFields && meal.estimatedFields.length > 0 ? '估算' : '已记录'}
                                 </span>
                             </div>
                             {macroSummary.length > 0 && (
                               <div className="pl-[54px] flex flex-wrap gap-2 -mt-1">
                                 {macroSummary.map(item => (
                                   <span key={item} className="text-[10px] text-slate-500 bg-white/5 border border-white/5 rounded px-1.5 py-0.5 font-serif font-bold tracking-wide">
                                     {item}
                                   </span>
                                 ))}
                               </div>
                             )}
                             {meal.ruleWarnings && meal.ruleWarnings.length > 0 && (
                                 <div className="ml-[54px] rounded-xl border border-amber-300/20 bg-amber-500/10 px-3 py-2">
                                     {meal.ruleWarnings.slice(0, 2).map((warning) => (
                                         <p key={warning} className="text-[10px] text-amber-100 font-serif tracking-wide leading-relaxed">
                                             {warning}
                                         </p>
                                     ))}
                                 </div>
                             )}
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
                                本地估算记录(含钠/嘌呤)
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

      {/* Edit Meal Modal */}
      {editingMeal && editInput && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
              <div className="bg-[#131b1d] border border-white/10 w-full max-w-sm rounded-2xl p-5 shadow-2xl relative max-h-[90vh] overflow-y-auto">
                  <button
                      onClick={closeEditMeal}
                      disabled={isSavingEdit}
                      className="absolute top-4 right-4 text-white/40 hover:text-white transition-colors disabled:opacity-40"
                  >
                      <span className="material-symbols-outlined">close</span>
                  </button>
                  <h3 className="text-white font-serif tracking-wide text-lg font-bold mb-5 text-center">编辑餐食</h3>

                  <div className="space-y-4">
                      {actionError && (
                        <p className="text-xs text-red-300 bg-red-500/10 border border-red-500/20 rounded-lg p-2 font-serif tracking-wide">
                          {actionError}
                        </p>
                      )}

                      <div className="flex gap-2 p-1 bg-black/20 rounded-lg">
                          {MEAL_TYPES.map((item) => (
                              <button
                                key={item.id}
                                onClick={() => patchEditInput({ type: item.id })}
                                className={`flex-1 py-2 rounded-md text-[10px] font-bold tracking-wide font-serif transition-all ${editInput.type === item.id ? 'bg-primary text-[#080c0d] shadow-sm' : 'text-slate-500 hover:text-slate-300'}`}
                              >
                                  {item.shortLabel}
                              </button>
                          ))}
                      </div>

                      <div>
                          <label className="text-xs text-slate-500 ml-1 mb-2 block font-serif font-bold tracking-wide">食物类型</label>
                          <div className="grid grid-cols-5 gap-2">
                              {FOOD_CATEGORIES.map(cat => (
                                  <button
                                      key={cat.id}
                                      onClick={() => patchEditInput({ category: cat.id })}
                                      className={`flex flex-col items-center justify-center gap-1 py-2 rounded-xl border transition-all ${
                                          editInput.category === cat.id
                                          ? 'bg-white/10 border-primary/50 text-primary'
                                          : 'bg-black/20 border-transparent text-slate-500 hover:bg-white/5'
                                      }`}
                                  >
                                      <span className={`material-symbols-outlined text-xl ${editInput.category === cat.id ? 'icon-filled' : ''}`}>
                                          {cat.icon}
                                      </span>
                                      <span className="text-[10px] font-bold font-serif tracking-wide">{cat.label}</span>
                                  </button>
                              ))}
                          </div>
                      </div>

                      <div className="grid grid-cols-2 gap-3">
                          <div className="col-span-2">
                              <label className="text-xs text-slate-500 ml-1 mb-1 block font-serif font-bold tracking-wide">食物名称</label>
                              <input
                                type="text"
                                value={editInput.name}
                                onChange={e => patchEditInput({ name: e.target.value })}
                                className="w-full bg-black/20 border border-white/10 rounded-xl p-3 text-white text-sm outline-none focus:border-primary/50 transition-colors font-serif tracking-wide"
                              />
                          </div>
                          <div className="col-span-2">
                              <label className="text-xs text-slate-500 ml-1 mb-1 block font-serif font-bold tracking-wide">份量</label>
                              <input
                                type="text"
                                value={editInput.portion}
                                onChange={e => patchEditInput({ portion: e.target.value })}
                                className="w-full bg-black/20 border border-white/10 rounded-xl p-3 text-white text-sm outline-none focus:border-primary/50 transition-colors font-serif tracking-wide"
                              />
                          </div>
                          {[
                            ['calories', '热量 kcal'],
                            ['sodium', '钠 mg'],
                            ['purine', '嘌呤 mg'],
                            ['protein', '蛋白质 g'],
                            ['carbs', '碳水 g'],
                            ['fat', '脂肪 g'],
                            ['fiber', '纤维 g'],
                          ].map(([field, label]) => (
                            <div key={field}>
                              <label className="text-xs text-slate-500 ml-1 mb-1 block font-serif font-bold tracking-wide">{label}</label>
                              <input
                                type="number"
                                min="0"
                                step="0.1"
                                value={editInput[field as keyof MealEditInput]}
                                onChange={e => patchEditInput({ [field]: e.target.value } as Partial<MealEditInput>)}
                                className="w-full bg-black/20 border border-white/10 rounded-xl p-3 text-white text-sm outline-none focus:border-primary/50 transition-colors font-serif tracking-wide"
                              />
                            </div>
                          ))}
                          <div className="col-span-2">
                              <label className="text-xs text-slate-500 ml-1 mb-1 block font-serif font-bold tracking-wide">备注</label>
                              <textarea
                                rows={2}
                                value={editInput.note}
                                onChange={e => patchEditInput({ note: e.target.value })}
                                className="w-full bg-black/20 border border-white/10 rounded-xl p-3 text-white text-sm outline-none focus:border-primary/50 transition-colors font-serif tracking-wide resize-none"
                              />
                          </div>
                      </div>

                      <div className="pt-2 flex gap-3">
                          <button
                            onClick={closeEditMeal}
                            disabled={isSavingEdit}
                            className="flex-1 border border-white/10 text-slate-400 py-3 rounded-xl font-bold text-sm hover:bg-white/5 transition-colors font-serif tracking-wide disabled:opacity-50"
                          >
                              取消
                          </button>
                          <button
                            onClick={saveEditedMeal}
                            disabled={isSavingEdit}
                            className="flex-1 bg-primary/20 text-primary py-3 rounded-xl font-bold text-sm border border-primary/20 hover:bg-primary/30 transition-colors font-serif tracking-wide disabled:opacity-50"
                          >
                              {isSavingEdit ? '保存中...' : '保存'}
                          </button>
                      </div>
                  </div>
              </div>
          </div>
      )}

      {/* Delete Meal Confirm Modal */}
      {deletingMeal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
              <div className="bg-[#131b1d] border border-white/10 w-full max-w-xs rounded-2xl p-5 shadow-2xl relative">
                  <h3 className="text-white font-serif tracking-wide text-lg font-bold mb-3 text-center">删除餐食记录</h3>
                  {actionError ? (
                    <p className="text-xs text-red-300 bg-red-500/10 border border-red-500/20 rounded-lg p-2 mb-4 font-serif tracking-wide">
                      {actionError}
                    </p>
                  ) : (
                    <p className="text-slate-300 text-sm leading-relaxed text-center font-serif tracking-wide mb-5">
                      确认删除「{deletingMeal.name}」吗？删除后会同步移除后端数据库记录。
                    </p>
                  )}
                  <div className="flex gap-3">
                      <button
                        onClick={() => {
                          if (isDeleting) return;
                          setDeletingMeal(null);
                          setActionError(null);
                        }}
                        disabled={isDeleting}
                        className="flex-1 py-3 rounded-xl border border-white/10 text-slate-400 font-bold text-sm hover:bg-white/5 transition-colors font-serif tracking-wide disabled:opacity-50"
                      >
                        取消
                      </button>
                      <button
                        onClick={confirmDeleteMeal}
                        disabled={isDeleting}
                        className="flex-1 py-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-300 font-bold text-sm hover:bg-red-500/20 transition-colors font-serif tracking-wide disabled:opacity-50"
                      >
                        {isDeleting ? '删除中...' : '确认删除'}
                      </button>
                  </div>
              </div>
          </div>
      )}
    </div>
  );
};

export default LogView;
