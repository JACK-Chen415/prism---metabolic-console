import React, { useMemo, useState, useEffect, useCallback } from 'react';
import { UserProfile, Meal, FavoriteMeal, FoodCategory, DailyTargets, MealUpdateInput, MealSyncStatus, ConditionData, EvaluateFoodResponse, PackagedFoodCategory, PackagedFoodLookupResponse } from '../../types';
import { HEALTH_TIPS } from '../../data/healthTips';
import { formatChineseDate, getLocalDateString } from '../../services/date';
import { estimateMealNutrition } from '../../services/mealEstimation';
import { KnowledgeAPI, MealsAPI } from '../../services/api';
import { mapMeal } from '../../services/mappers/appMappers';
import { COMPLIANCE_MEDICAL_DISCLAIMER, PACKAGED_FOOD_DISCLAIMER } from '../../constants/compliance';

interface LogViewProps {
  userProfile: UserProfile;
  medicalConditions: ConditionData[];
  meals: Meal[];
  currentDate: string;
  dailyTargets: DailyTargets;
  onAddMeal: (meal: Meal, recordDate?: string) => Promise<void> | void;
  onUpdateMeal: (mealId: string, changes: MealUpdateInput) => Promise<void>;
  onDeleteMeal: (mealId: string) => Promise<void>;
  onDateChange: (date: string) => Promise<void> | void;
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

const SYNC_STATUS_LABELS: Record<MealSyncStatus, string> = {
  PENDING: '待同步',
  SYNCED: '已同步',
  CONFLICT: '冲突待处理',
  FAILED: '同步失败',
};

const SYNC_STATUS_CLASS: Record<MealSyncStatus, string> = {
  PENDING: 'border-primary/20 bg-primary/10 text-primary',
  SYNCED: 'border-emerald-400/15 bg-emerald-500/10 text-emerald-200',
  CONFLICT: 'border-amber-300/25 bg-amber-500/10 text-amber-100',
  FAILED: 'border-red-400/25 bg-red-500/10 text-red-200',
};

type ManualMealInput = {
  name: string;
  portion: string;
  type: Meal['type'];
  category: FoodCategory;
  note: string;
};

type MealEditInput = ManualMealInput & {
  calories: string;
  sodium: string;
  purine: string;
  protein: string;
  carbs: string;
  fat: string;
  fiber: string;
};

type PackagedFoodLookupState = {
  barcode: string;
  isLoading: boolean;
  error: string | null;
  response: PackagedFoodLookupResponse | null;
  selectedCandidateIndex: number;
};

type PackagedFoodLabelInput = {
  productName: string;
  brand: string;
  barcode: string;
  category: PackagedFoodCategory;
  servingSize: string;
  servingSizeG: string;
  caloriesPer100g: string;
  proteinPer100g: string;
  carbsPer100g: string;
  fatPer100g: string;
  fiberPer100g: string;
  sodiumPer100g: string;
  sugarPer100g: string;
  purinePer100g: string;
  ingredients: string;
  allergenTags: string;
  riskTags: string;
};

type FrequentMealShortcut = {
  key: string;
  name: string;
  portion: string;
  type: Meal['type'];
  category: FoodCategory;
  note: string;
  count: number;
  latestDate: string;
};

type PreMealSimulationState = {
  isLoading: boolean;
  error: string | null;
  decision: EvaluateFoodResponse | null;
  estimated: Pick<Meal, 'calories' | 'sodium' | 'purine'> | null;
  swaps: string[];
  lastKey: string | null;
};

type PreMealRiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'UNKNOWN';

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

const splitConditionCodes = (conditions: ConditionData[]) => Array.from(new Set(conditions.map(item => item.conditionCode || item.id).filter((value): value is string => Boolean(value))));

const splitListField = (value: string) => value
  .split(/[，,、；;\n/]+/)
  .map(item => item.trim())
  .filter(Boolean);


const normalizeFrequentMealText = (value: string) => value.trim().replace(/\s+/g, ' ').toLowerCase();

const getDateValue = (dateString: string) => {
  const timestamp = Date.parse(dateString);
  return Number.isNaN(timestamp) ? 0 : timestamp;
};

const buildFrequentMealShortcuts = (recentMeals: Meal[]): FrequentMealShortcut[] => {
  const grouped = new Map<string, FrequentMealShortcut>();

  recentMeals.forEach((meal) => {
    const name = meal.name.trim();
    if (!name) return;
    const portion = meal.portion?.trim() || '1份';
    const key = `${normalizeFrequentMealText(name)}|${normalizeFrequentMealText(portion)}`;
    const latestDate = meal.recordDate || '';
    const existing = grouped.get(key);

    if (!existing) {
      grouped.set(key, {
        key,
        name,
        portion,
        type: meal.type,
        category: meal.category,
        note: meal.note || '',
        count: 1,
        latestDate,
      });
      return;
    }

    existing.count += 1;
    if (getDateValue(latestDate) >= getDateValue(existing.latestDate)) {
      existing.name = name;
      existing.portion = portion;
      existing.type = meal.type;
      existing.category = meal.category;
      existing.note = meal.note || '';
      existing.latestDate = latestDate;
    }
  });

  return Array.from(grouped.values())
    .sort((a, b) => b.count - a.count || getDateValue(b.latestDate) - getDateValue(a.latestDate))
    .slice(0, 6);
};

const buildFrequentMealCTA = (shortcut: FrequentMealShortcut) => {
  const base = shortcut.count > 1 ? '再次使用' : '快速使用';
  return `${base}到餐盘`;
};

const normalizeRecentMealList = (response: unknown): Meal[] => {
  const items = Array.isArray(response)
    ? response
    : response && typeof response === 'object' && Array.isArray((response as { items?: unknown[] }).items)
      ? (response as { items: unknown[] }).items
      : [];

  return items
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const rawMeal = item as Record<string, unknown>;
      if ('meal_type' in rawMeal || 'record_date' in rawMeal || 'client_id' in rawMeal) {
        return mapMeal(rawMeal);
      }
      return rawMeal as unknown as Meal;
    })
    .filter((meal): meal is Meal => Boolean(meal?.name));
};


const normalizeFavoriteMealList = (response: unknown): FavoriteMeal[] => {
  const items = Array.isArray(response)
    ? response
    : response && typeof response === 'object' && Array.isArray((response as { items?: unknown[] }).items)
      ? (response as { items: unknown[] }).items
      : [];

  return items
    .map(item => item as FavoriteMeal)
    .filter((favorite): favorite is FavoriteMeal => Boolean(favorite?.id && favorite?.name))
    .sort((a, b) => b.usage_count - a.usage_count || getDateValue(b.updated_at) - getDateValue(a.updated_at));
};

const favoriteMealToInput = (favorite: FavoriteMeal): ManualMealInput => ({
  name: favorite.name,
  portion: favorite.portion || '1份',
  type: favorite.meal_type,
  category: favorite.category,
  note: favorite.note || '',
});

const upsertFavoriteMeal = (items: FavoriteMeal[], nextFavorite: FavoriteMeal) => {
  const withoutExisting = items.filter(item => item.id !== nextFavorite.id);
  return normalizeFavoriteMealList([nextFavorite, ...withoutExisting]);
};

const EMPTY_PRE_MEAL_SIMULATION: PreMealSimulationState = {
  isLoading: false,
  error: null,
  decision: null,
  estimated: null,
  swaps: [],
  lastKey: null,
};

const PRE_MEAL_RISK_STYLES: Record<PreMealRiskLevel, { label: string; className: string }> = {
  LOW: { label: '可参考', className: 'border-emerald-400/20 bg-emerald-500/10 text-emerald-200' },
  MEDIUM: { label: '需控制', className: 'border-amber-300/25 bg-amber-500/10 text-amber-100' },
  HIGH: { label: '建议避开', className: 'border-red-400/30 bg-red-500/10 text-red-200' },
  UNKNOWN: { label: '待评估', className: 'border-white/10 bg-white/5 text-slate-300' },
};

const getPreMealRiskLevel = (
  decision: EvaluateFoodResponse | null,
  estimated: Pick<Meal, 'calories' | 'sodium' | 'purine'> | null,
): PreMealRiskLevel => {
  if (!decision && !estimated) return 'UNKNOWN';
  if (decision?.hard_blocks.length || decision?.recommendation_level === 'AVOID') return 'HIGH';
  if (
    decision?.recommendation_level === 'LIMIT'
    || decision?.recommendation_level === 'CONDITIONAL'
    || decision?.recommendation_level === 'INSUFFICIENT'
    || (estimated?.sodium ?? 0) >= 700
    || (estimated?.purine ?? 0) >= 180
  ) return 'MEDIUM';
  return 'LOW';
};

const buildPreMealSwapSuggestions = (
  input: ManualMealInput,
  estimated: Pick<Meal, 'calories' | 'sodium' | 'purine'>,
  decision: EvaluateFoodResponse | null,
): string[] => {
  const suggestions = new Set<string>();
  const note = `${input.name} ${input.note}`;

  if (decision?.hard_blocks.length || decision?.recommendation_level === 'AVOID') {
    suggestions.add('本地规则提示避开或存在硬性风险时，不要用 AI/个人偏好放宽；先换成已确认不过敏、不过度触发慢病规则的食物。');
  }
  if (decision?.recommendation_level === 'LIMIT' || decision?.recommendation_level === 'CONDITIONAL') {
    suggestions.add('先把份量减半，并把重油、重盐、浓汤、酱料分开确认后再记录。');
  }

  const categorySuggestion: Record<FoodCategory, string> = {
    STAPLE: '主食可优先换成半份米饭、杂粮饭或清汤面，少汤底和浇头。',
    MEAT: '肉蛋类可优先选择清蒸、白灼、少油煎的瘦肉或蛋类；若命中 AVOID/LIMIT，先换非触发食材。',
    VEG: '蔬果类保留高纤维优势，做法上优先白灼、清炒少油、酱汁分开。',
    DRINK: '饮品可优先换成水、无糖茶或无糖咖啡，并避免额外糖浆。',
    SNACK: '零食先换成小份、低盐、非油炸选项；含坚果、乳、蛋或小麦时先核对过敏标签。',
  };
  suggestions.add(categorySuggestion[input.category]);

  if (estimated.sodium >= 500 || /咸|盐|酱|卤|汤|火锅/.test(note)) {
    suggestions.add('钠风险偏高时，优先少汤、少酱、少卤汁，外卖备注少盐并避免喝汤底。');
  }
  if (estimated.purine >= 120 || /内脏|海鲜|浓汤|火锅|啤酒/.test(note)) {
    suggestions.add('嘌呤风险偏高时，避开内脏、浓汤、海鲜汤底和酒精搭配，改成清淡蛋白或蔬菜搭配。');
  }
  if (estimated.calories >= 600 || /炸|煎|肥|奶油|甜/.test(note)) {
    suggestions.add('热量偏高时，先改小份或半份，优先蒸煮炖，减少油炸、奶油和甜酱。');
  }

  if (suggestions.size === 0) {
    suggestions.add('保持当前份量并核对食物、做法、调料和过敏信息后再记录。');
  }

  return Array.from(suggestions).slice(0, 4);
};

const addDays = (dateString: string, days: number) => {
  const [year, month, day] = dateString.split('-').map(Number);
  const date = new Date(year, (month || 1) - 1, day || 1);
  date.setDate(date.getDate() + days);
  return getLocalDateString(date);
};

const LogView: React.FC<LogViewProps> = ({
  userProfile,
  medicalConditions,
  meals,
  currentDate,
  dailyTargets,
  onAddMeal,
  onUpdateMeal,
  onDeleteMeal,
  onDateChange,
}) => {
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
  const todayDate = getLocalDateString();
  const isViewingToday = currentDate === todayDate;
  const dateLabel = isViewingToday ? '今天' : formatChineseDate(currentDate);

  // State
  const [isAdding, setIsAdding] = useState(false);
  const [editingMeal, setEditingMeal] = useState<Meal | null>(null);
  const [editInput, setEditInput] = useState<MealEditInput | null>(null);
  const [deletingMeal, setDeletingMeal] = useState<Meal | null>(null);
  const [isChangingDate, setIsChangingDate] = useState(false);
  const [isSavingAdd, setIsSavingAdd] = useState(false);
  const [isSavingEdit, setIsSavingEdit] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [dailyTip, setDailyTip] = useState('');
  const [mealInput, setMealInput] = useState<ManualMealInput>({ name: '', portion: '', type: 'DINNER', category: 'STAPLE', note: '' });
  const [packagedLookup, setPackagedLookup] = useState<PackagedFoodLookupState>({
    barcode: '',
    isLoading: false,
    error: null,
    response: null,
    selectedCandidateIndex: 0,
  });
  const [packagedLabelInput, setPackagedLabelInput] = useState<PackagedFoodLabelInput>({
    productName: '',
    brand: '',
    barcode: '',
    category: 'SNACK',
    servingSize: '',
    servingSizeG: '',
    caloriesPer100g: '',
    proteinPer100g: '',
    carbsPer100g: '',
    fatPer100g: '',
    fiberPer100g: '',
    sodiumPer100g: '',
    sugarPer100g: '',
    purinePer100g: '',
    ingredients: '',
    allergenTags: '',
    riskTags: '',
  });
  const [recentMealHistory, setRecentMealHistory] = useState<Meal[]>([]);
  const [frequentMealShortcuts, setFrequentMealShortcuts] = useState<FrequentMealShortcut[]>([]);
  const [isLoadingFrequentMeals, setIsLoadingFrequentMeals] = useState(false);
  const [frequentMealsError, setFrequentMealsError] = useState<string | null>(null);
  const [favoriteMeals, setFavoriteMeals] = useState<FavoriteMeal[]>([]);
  const [isLoadingFavoriteMeals, setIsLoadingFavoriteMeals] = useState(false);
  const [favoriteMealsError, setFavoriteMealsError] = useState<string | null>(null);
  const [favoriteActionId, setFavoriteActionId] = useState<string | null>(null);
  const [preMealSimulation, setPreMealSimulation] = useState<PreMealSimulationState>(EMPTY_PRE_MEAL_SIMULATION);

  const refreshDailyTip = (e?: React.MouseEvent) => {
    e?.stopPropagation();
    const randomIndex = Math.floor(Math.random() * HEALTH_TIPS.length);
    setDailyTip(HEALTH_TIPS[randomIndex]);
  };

  // Initialize Random Health Tip on Mount
  useEffect(() => {
    refreshDailyTip();
  }, []);

  const loadFavoriteMealTemplates = useCallback(async () => {
    setIsLoadingFavoriteMeals(true);
    setFavoriteMealsError(null);
    try {
      const response = await MealsAPI.listFavorites(20);
      setFavoriteMeals(normalizeFavoriteMealList(response));
    } catch (error) {
      setFavoriteMeals([]);
      setFavoriteMealsError(error instanceof Error ? error.message : '收藏餐加载失败。');
    } finally {
      setIsLoadingFavoriteMeals(false);
    }
  }, []);

  useEffect(() => {
    if (!isAdding) return;

    let isCancelled = false;
    const loadFrequentMeals = async () => {
      setIsLoadingFrequentMeals(true);
      setFrequentMealsError(null);
      try {
        const response = await MealsAPI.list({
          start_date: addDays(currentDate, -13),
          end_date: currentDate,
          page_size: 100,
        });
        const recentMeals = normalizeRecentMealList(response);
        if (!isCancelled) {
          setRecentMealHistory(recentMeals);
          setFrequentMealShortcuts(buildFrequentMealShortcuts(recentMeals));
        }
      } catch (error) {
        if (!isCancelled) {
          setRecentMealHistory([]);
          setFrequentMealShortcuts([]);
          setFrequentMealsError(error instanceof Error ? error.message : '最近常吃加载失败。');
        }
      } finally {
        if (!isCancelled) setIsLoadingFrequentMeals(false);
      }
    };

    loadFrequentMeals();
    loadFavoriteMealTemplates();
    return () => {
      isCancelled = true;
    };
  }, [currentDate, isAdding, loadFavoriteMealTemplates]);

  const totalCalories = meals.reduce((sum, item) => sum + item.calories, 0);
  const totalSodium = meals.reduce((sum, item) => sum + item.sodium, 0);
  const totalPurine = meals.reduce((sum, item) => sum + item.purine, 0);
  const totalProtein = meals.reduce((sum, item) => sum + (item.protein || 0), 0);
  const totalCarbs = meals.reduce((sum, item) => sum + (item.carbs || 0), 0);
  const totalFat = meals.reduce((sum, item) => sum + (item.fat || 0), 0);
  const mealsByType = MEAL_TYPES.map(type => ({
    ...type,
    meals: meals.filter(meal => meal.type === type.id),
  }));
  const progress = targetCalories > 0 ? Math.min((totalCalories / targetCalories) * 100, 100) : 0;
  const remainingCalories = targetCalories > 0 ? Math.max(targetCalories - totalCalories, 0) : 0;
  const calorieGuidance = targetCalories <= 0
    ? '请先在设置中完善身高、体重、年龄、性别，以获得更准确的基础代谢和推荐摄入目标。'
    : totalCalories > targetCalories
      ? `${isViewingToday ? '今日' : '所选日期'}热量摄入已超过推荐目标。${targetExplanation}`
      : targetExplanation;

  const packagedConditionCodes = useMemo(() => splitConditionCodes(medicalConditions), [medicalConditions]);
  const packagedRestrictionTerms = useMemo(() => medicalConditions.map(item => item.title).filter((value): value is string => Boolean(value)), [medicalConditions]);
  const previousMealShortcut = useMemo(() => recentMealHistory.find(meal => meal.name.trim()) || null, [recentMealHistory]);
  const yesterdaySameMealTypeShortcut = useMemo(() => {
    const yesterdayDate = addDays(currentDate, -1);
    return recentMealHistory.find(meal => meal.recordDate === yesterdayDate && meal.type === mealInput.type)
      || recentMealHistory.find(meal => meal.recordDate === yesterdayDate)
      || null;
  }, [currentDate, mealInput.type, recentMealHistory]);
  const preMealSimulationKey = `${mealInput.name.trim()}|${mealInput.portion.trim()}|${mealInput.type}|${mealInput.category}|${mealInput.note.trim()}`;
  const preMealRiskLevel = getPreMealRiskLevel(preMealSimulation.decision, preMealSimulation.estimated);
  const preMealRiskStyle = PRE_MEAL_RISK_STYLES[preMealRiskLevel];
  const isPreMealSimulationStale = Boolean(preMealSimulation.lastKey && preMealSimulation.lastKey !== preMealSimulationKey);

  const changeDate = async (nextDate: string) => {
    setIsChangingDate(true);
    setActionError(null);
    try {
      await onDateChange(nextDate);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '切换日期失败，请稍后再试。');
    } finally {
      setIsChangingDate(false);
    }
  };

  const fillMealFromShortcut = (shortcut: FrequentMealShortcut) => {
    setMealInput({
      name: shortcut.name,
      portion: shortcut.portion,
      type: shortcut.type,
      category: shortcut.category,
      note: shortcut.note,
    });
    setFrequentMealsError(null);
  };

  const copyRecentMealIntoAddForm = (meal: Meal) => {
    setMealInput({
      name: meal.name,
      portion: meal.portion || '1份',
      type: meal.type,
      category: meal.category,
      note: meal.note || '',
    });
    setFrequentMealsError(null);
  };

  const canSaveMealAsFavorite = (meal: Meal) => {
    const syncStatus = meal.syncStatus || 'SYNCED';
    return syncStatus === 'SYNCED' && Number.isFinite(Number(meal.id));
  };

  const saveMealAsFavorite = async (meal: Meal) => {
    if (favoriteActionId || !meal.name.trim()) return;
    if (!canSaveMealAsFavorite(meal)) {
      setActionError('离线或待同步餐食需同步成功后再加入收藏餐。');
      return;
    }

    setFavoriteActionId(`save:${meal.id}`);
    setActionError(null);
    setFeedbackMessage(null);
    try {
      const favorite = await MealsAPI.favoriteMeal(meal.id);
      setFavoriteMeals(previous => upsertFavoriteMeal(previous, favorite));
      setFeedbackMessage('已加入收藏餐，记录餐食时可一键复记并编辑。');
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '加入收藏餐失败，请稍后再试。');
    } finally {
      setFavoriteActionId(null);
    }
  };

  const useFavoriteMealTemplate = async (favorite: FavoriteMeal) => {
    if (favoriteActionId) return;

    setMealInput(favoriteMealToInput(favorite));
    setPreMealSimulation(EMPTY_PRE_MEAL_SIMULATION);
    setFrequentMealsError(null);
    setFavoriteMealsError(null);
    setFeedbackMessage('已填入收藏餐，可继续编辑后保存。');
    setFavoriteActionId(`use:${favorite.id}`);
    try {
      const updatedFavorite = await MealsAPI.useFavorite(favorite.id);
      setFavoriteMeals(previous => upsertFavoriteMeal(previous, updatedFavorite));
    } catch (error) {
      setFavoriteMealsError(error instanceof Error ? error.message : '已填入表单，但收藏餐使用次数同步失败。');
    } finally {
      setFavoriteActionId(null);
    }
  };

  const deleteFavoriteMealTemplate = async (favorite: FavoriteMeal, event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (favoriteActionId) return;

    setFavoriteActionId(`delete:${favorite.id}`);
    setFavoriteMealsError(null);
    try {
      await MealsAPI.deleteFavorite(favorite.id);
      setFavoriteMeals(previous => previous.filter(item => item.id !== favorite.id));
      setFeedbackMessage('已移除收藏餐。');
    } catch (error) {
      setFavoriteMealsError(error instanceof Error ? error.message : '删除收藏餐失败，请稍后再试。');
    } finally {
      setFavoriteActionId(null);
    }
  };

  const runPreMealSimulation = async () => {
    if (!mealInput.name.trim() || preMealSimulation.isLoading) return;
    const estimated = estimateMealNutrition(mealInput);
    const simulationKey = preMealSimulationKey;
    setPreMealSimulation({
      isLoading: true,
      error: null,
      decision: null,
      estimated,
      swaps: buildPreMealSwapSuggestions(mealInput, estimated, null),
      lastKey: simulationKey,
    });
    try {
      const decision = await KnowledgeAPI.evaluateFood({
        food_name: mealInput.name.trim(),
        condition_codes: packagedConditionCodes,
        manual_restrictions: packagedRestrictionTerms,
      });
      setPreMealSimulation({
        isLoading: false,
        error: null,
        decision,
        estimated,
        swaps: buildPreMealSwapSuggestions(mealInput, estimated, decision),
        lastKey: simulationKey,
      });
    } catch (error) {
      setPreMealSimulation({
        isLoading: false,
        error: error instanceof Error ? error.message : '餐前模拟暂不可用，已保留本地营养估算。',
        decision: null,
        estimated,
        swaps: buildPreMealSwapSuggestions(mealInput, estimated, null),
        lastKey: simulationKey,
      });
    }
  };

  const addMeal = async () => {
    if (!mealInput.name.trim() || isSavingAdd) return;
    const estimated = estimateMealNutrition(mealInput);

    const newClientId = crypto.randomUUID();
    setIsSavingAdd(true);
    setActionError(null);
    try {
      await onAddMeal({
        id: newClientId,
        clientId: newClientId,
        recordDate: currentDate,
        name: mealInput.name.trim(),
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
      }, currentDate);
      setFeedbackMessage(`${dateLabel}餐食记录已保存。`);
      setIsAdding(false);
      setMealInput({ name: '', portion: '', type: 'DINNER', category: 'STAPLE', note: '' });
      setPreMealSimulation(EMPTY_PRE_MEAL_SIMULATION);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '保存失败，请稍后再试。');
    } finally {
      setIsSavingAdd(false);
    }
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

  const lookupPackagedFood = async () => {
    const barcode = packagedLookup.barcode.replace(/\D/g, '');
    if (!barcode) {
      setPackagedLookup(prev => ({ ...prev, error: '请输入条码。' }));
      return;
    }
    setPackagedLookup(prev => ({ ...prev, isLoading: true, error: null, response: null, selectedCandidateIndex: 0 }));
    try {
      const response = await KnowledgeAPI.lookupPackagedFoodBarcode({
        barcode,
        condition_codes: packagedConditionCodes,
        manual_restrictions: packagedRestrictionTerms,
      });
      setPackagedLookup(prev => ({ ...prev, isLoading: false, response, error: response.matched ? null : '未找到匹配条码，建议改用手动营养标签。', selectedCandidateIndex: 0 }));
      setFeedbackMessage(response.disclaimer);
    } catch (error) {
      setPackagedLookup(prev => ({ ...prev, isLoading: false, response: null, error: error instanceof Error ? error.message : '包装食品查询失败。', selectedCandidateIndex: 0 }));
    }
  };

  const normalizePackagedLabel = async () => {
    if (!packagedLabelInput.productName.trim()) {
      setPackagedLookup(prev => ({ ...prev, error: '请输入商品名称。' }));
      return;
    }
    setPackagedLookup(prev => ({ ...prev, isLoading: true, error: null }));
    try {
      const response = await KnowledgeAPI.normalizePackagedFoodLabel({
        product_name: packagedLabelInput.productName.trim(),
        brand: packagedLabelInput.brand.trim() || undefined,
        barcode: packagedLabelInput.barcode.replace(/\D/g, '') || undefined,
        category: packagedLabelInput.category,
        serving_size: packagedLabelInput.servingSize.trim() || undefined,
        serving_size_g: packagedLabelInput.servingSizeG ? Number(packagedLabelInput.servingSizeG) : undefined,
        calories_per_100g: packagedLabelInput.caloriesPer100g ? Number(packagedLabelInput.caloriesPer100g) : undefined,
        protein_per_100g: packagedLabelInput.proteinPer100g ? Number(packagedLabelInput.proteinPer100g) : undefined,
        carbs_per_100g: packagedLabelInput.carbsPer100g ? Number(packagedLabelInput.carbsPer100g) : undefined,
        fat_per_100g: packagedLabelInput.fatPer100g ? Number(packagedLabelInput.fatPer100g) : undefined,
        fiber_per_100g: packagedLabelInput.fiberPer100g ? Number(packagedLabelInput.fiberPer100g) : undefined,
        sodium_per_100g: packagedLabelInput.sodiumPer100g ? Number(packagedLabelInput.sodiumPer100g) : undefined,
        sugar_per_100g: packagedLabelInput.sugarPer100g ? Number(packagedLabelInput.sugarPer100g) : undefined,
        purine_per_100g: packagedLabelInput.purinePer100g ? Number(packagedLabelInput.purinePer100g) : undefined,
        ingredients: splitListField(packagedLabelInput.ingredients),
        allergen_tags: splitListField(packagedLabelInput.allergenTags),
        risk_tags: splitListField(packagedLabelInput.riskTags),
        condition_codes: packagedConditionCodes,
        manual_restrictions: packagedRestrictionTerms,
      });
      const lookupResponse: PackagedFoodLookupResponse = {
        provider: response.provider,
        provider_status: response.provider_status,
        barcode_last4: response.barcode_last4,
        matched: true,
        candidates: [response],
        disclaimer: response.disclaimer,
      };
      setPackagedLookup(prev => ({ ...prev, isLoading: false, response: lookupResponse, error: null, selectedCandidateIndex: 0 }));
      setFeedbackMessage(response.disclaimer);
    } catch (error) {
      setPackagedLookup(prev => ({ ...prev, isLoading: false, error: error instanceof Error ? error.message : '营养标签归一化失败。' }));
    }
  };

  const activePackagedCandidate = packagedLookup.response?.candidates[packagedLookup.selectedCandidateIndex || 0] || null;

  return (
    <div className="flex flex-col w-full pb-28 relative">
      <div className="sticky top-0 z-20 bg-background-dark/90 backdrop-blur-md px-4 pt-3 pb-3 border-b border-white/5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-xl font-bold leading-tight tracking-wide text-white font-serif">生命日志</h2>
            <p className="mt-1 text-xs text-slate-500 font-serif font-bold tracking-wide">
              {isChangingDate ? '正在切换日期...' : `${dateLabel} · ${meals.length} 条记录`}
            </p>
          </div>
          {!isViewingToday && (
            <button
              onClick={() => changeDate(todayDate)}
              disabled={isChangingDate}
              className="min-h-10 shrink-0 rounded-full border border-primary/25 bg-primary/10 px-3 text-xs text-primary font-serif font-bold tracking-wide disabled:opacity-50"
            >
              回到今天
            </button>
          )}
        </div>
        <div className="mt-3 grid grid-cols-[44px_minmax(0,1fr)_44px] items-center gap-2">
          <button
            onClick={() => changeDate(addDays(currentDate, -1))}
            disabled={isChangingDate}
            className="h-11 w-11 rounded-2xl flex items-center justify-center bg-surface-dark border border-white/10 text-slate-300 hover:text-white disabled:opacity-50"
            aria-label="前一天"
          >
            <span className="material-symbols-outlined text-[22px]">chevron_left</span>
          </button>
          <label className="h-11 min-w-0 flex items-center justify-center bg-surface-dark rounded-2xl px-3 border border-white/10">
            <span className="material-symbols-outlined text-lg mr-2 text-primary">calendar_today</span>
            <input
              type="date"
              value={currentDate}
              max={todayDate}
              onChange={(event) => changeDate(event.target.value)}
              disabled={isChangingDate}
              className="min-w-0 flex-1 bg-transparent text-mineral text-base font-bold leading-normal tracking-wide font-serif outline-none disabled:opacity-50"
              aria-label="选择日志日期"
            />
          </label>
          <button
            onClick={() => changeDate(addDays(currentDate, 1))}
            disabled={isChangingDate || isViewingToday}
            className="h-11 w-11 rounded-2xl flex items-center justify-center bg-surface-dark border border-white/10 text-slate-300 hover:text-white disabled:opacity-30"
            aria-label="后一天"
          >
            <span className="material-symbols-outlined text-[22px]">chevron_right</span>
          </button>
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
            <div className="bg-surface-dark border border-white/5 rounded-2xl p-4 sm:p-5 shadow-sm relative overflow-hidden mb-4">
                 {/* Decorative background glow */}
                 <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-2xl -mr-10 -mt-10"></div>

                 <div className="grid gap-3 mb-4 relative z-10 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
                     <div className="min-w-0">
                         <p className="text-slate-400 text-xs font-serif font-bold tracking-wide mb-1.5 flex items-center gap-1">
                             {isViewingToday ? '今日摄入' : '所选日期摄入'}
                             <span className="text-white/20">/</span>
                             <span className="text-slate-500">目标 {targetCalories > 0 ? targetCalories : '--'}</span>
                         </p>
                         <div className="flex items-baseline gap-2">
                             <span className={`text-[2.75rem] leading-none font-serif font-bold tracking-wide sm:text-4xl ${targetCalories > 0 && totalCalories > targetCalories ? 'text-ochre' : 'text-white'}`}>
                                {totalCalories}
                             </span>
                             <span className="text-xs text-slate-500 font-bold font-serif tracking-wide">kcal</span>
                         </div>
                     </div>
                     <div className="justify-self-start rounded-xl border border-white/5 bg-black/20 px-3 py-2 text-left sm:justify-self-end sm:border-0 sm:bg-transparent sm:p-0 sm:text-right">
                         <p className="text-[10px] text-slate-500 mb-1 font-serif font-bold tracking-wide sm:text-xs">剩余额度</p>
                         <span className={`text-lg font-serif font-bold tracking-wide sm:text-xl ${remainingCalories > 0 ? 'text-emerald-500' : 'text-ochre'}`}>
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

                 <div className="grid grid-cols-3 gap-1.5 mb-4 relative z-10 min-[380px]:grid-cols-5 sm:gap-2">
                   {[
                     ['钠', `${Math.round(totalSodium)}mg`],
                     ['嘌呤', `${Math.round(totalPurine)}mg`],
                     ['蛋白', `${Math.round(totalProtein * 10) / 10}g`],
                     ['碳水', `${Math.round(totalCarbs * 10) / 10}g`],
                     ['脂肪', `${Math.round(totalFat * 10) / 10}g`],
                   ].map(([label, value]) => (
                     <div key={label} className="min-w-0 rounded-lg border border-white/5 bg-black/20 px-1.5 py-2 text-center sm:rounded-xl sm:px-2">
                       <p className="text-[10px] leading-none text-slate-500 font-serif font-bold tracking-wide">{label}</p>
                       <p className="mt-1.5 truncate text-[11px] leading-none text-slate-200 font-serif font-bold tracking-wide">{value}</p>
                     </div>
                   ))}
                 </div>

                 {/* AI Suggestion Box */}
                 <div className="bg-white/5 rounded-xl px-3 py-3.5 flex gap-2.5 items-start border border-white/5 relative z-10 sm:gap-3">
                     <div className="shrink-0 w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center text-primary mt-0.5">
                        <span className="material-symbols-outlined text-sm">smart_toy</span>
                     </div>
                     <p className="min-w-0 text-xs text-slate-300 leading-6 font-serif tracking-wide">
                          {calorieGuidance}
                     </p>
                 </div>
            </div>

            {/* Meal List */}
            <div className="flex flex-col gap-3">
                {mealsByType.map(group => group.meals.length > 0 && (
                  <div key={group.id} className="space-y-2">
                    <div className="flex items-center justify-between px-1">
                      <h4 className="text-slate-300 text-sm font-serif font-bold tracking-wide">{group.label}</h4>
                      <span className="text-[11px] text-slate-500 font-serif font-bold tracking-wide">
                        {group.meals.reduce((sum, meal) => sum + meal.calories, 0)} kcal
                      </span>
                    </div>
                    <div className="flex flex-col gap-3">
                {group.meals.map(meal => {
                    const categoryConfig = FOOD_CATEGORIES.find(c => c.id === meal.category) || FOOD_CATEGORIES[0];
                    const syncStatus = meal.syncStatus || 'SYNCED';
                    const macroSummary = [
                      meal.protein !== undefined ? `蛋白 ${meal.protein}g` : null,
                      meal.carbs !== undefined ? `碳水 ${meal.carbs}g` : null,
                      meal.fat !== undefined ? `脂肪 ${meal.fat}g` : null,
                      meal.fiber !== undefined ? `纤维 ${meal.fiber}g` : null,
                    ].filter((item): item is string => Boolean(item));
                    const favoriteSaveActionId = `save:${meal.id}`;
                    const isSavingFavorite = favoriteActionId === favoriteSaveActionId;
                    const canFavoriteThisMeal = canSaveMealAsFavorite(meal);
                    return (
                        <div key={meal.id} className="group flex flex-col p-4 rounded-xl bg-surface-dark border border-white/5 hover:border-white/10 transition-colors gap-3">
                            <div className="flex items-start justify-between gap-3">
                                <div className="flex items-start gap-3 min-w-0 flex-1">
                                    <div className={`w-11 h-11 shrink-0 rounded-xl bg-white/5 flex items-center justify-center border border-white/5 group-hover:scale-105 transition-transform ${categoryConfig.color}`}>
                                        <span className="material-symbols-outlined text-2xl">{categoryConfig.icon}</span>
                                    </div>
                                    <div className="flex flex-col gap-1 min-w-0">
                                        <p className="text-white text-base font-bold tracking-wide font-serif leading-snug break-words">{meal.name}</p>
                                        <div className="flex flex-wrap items-center gap-1.5">
                                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-slate-400 border border-white/5 font-serif font-bold tracking-wide">
                                                {formatMealType(meal.type)}
                                            </span>
                                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary border border-primary/20 font-serif font-bold tracking-wide">
                                                {meal.source === 'voice' ? '语音' : meal.source === 'photo' ? '拍照' : meal.source === 'ai_quick_log' ? 'AI' : '手动'}
                                            </span>
                                            {syncStatus !== 'SYNCED' && (
                                              <span className={`text-[10px] px-1.5 py-0.5 rounded border font-serif font-bold tracking-wide ${SYNC_STATUS_CLASS[syncStatus as MealSyncStatus]}`}>
                                                {SYNC_STATUS_LABELS[syncStatus as MealSyncStatus]}
                                              </span>
                                            )}
                                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-slate-500 border border-white/5 font-serif font-bold tracking-wide">
                                                {categoryConfig.label}
                                            </span>
                                            <p className="text-slate-500 text-xs font-serif font-bold tracking-wide break-words">{meal.portion}</p>
                                        </div>
                                        {syncStatus !== 'SYNCED' && meal.lastSyncError && (
                                          <p className="text-[10px] text-amber-200 font-serif mt-1 flex items-start gap-1 leading-relaxed break-words">
                                            <span className="material-symbols-outlined text-[12px] mt-0.5">info</span>
                                            {meal.lastSyncError}
                                          </p>
                                        )}
                                        {/* Display Note if exists */}
                                        {meal.note && (
                                            <p className="text-[10px] text-slate-500 font-serif mt-1 flex items-start gap-1 leading-relaxed break-words">
                                                <span className="material-symbols-outlined text-[12px] mt-0.5">edit_note</span>
                                                {meal.note}
                                            </p>
                                        )}
                                    </div>
                                </div>
                                <div className="shrink-0 text-right flex flex-col items-end gap-0.5 rounded-xl bg-black/20 border border-white/5 px-3 py-2 min-w-[76px]">
                                    <p className="text-white text-2xl font-serif font-bold tracking-wide leading-none">{meal.calories}</p>
                                    <p className="text-slate-500 text-[10px] font-serif font-bold tracking-wide leading-none">kcal</p>
                                </div>
                            </div>

                            <div className="grid grid-cols-3 gap-2">
                              <button
                                onClick={() => openEditMeal(meal)}
                                className="h-9 rounded-lg flex items-center justify-center gap-1.5 text-xs font-serif font-bold tracking-wide text-slate-300 bg-white/5 border border-white/5 hover:text-primary hover:bg-primary/10 hover:border-primary/20 transition-colors"
                                title="编辑记录"
                                aria-label="编辑记录"
                              >
                                <span className="material-symbols-outlined text-[16px]">edit</span>
                                编辑
                              </button>
                              <button
                                onClick={() => saveMealAsFavorite(meal)}
                                disabled={!canFavoriteThisMeal || Boolean(favoriteActionId)}
                                className={`h-9 rounded-lg flex items-center justify-center gap-1.5 text-xs font-serif font-bold tracking-wide border transition-colors ${canFavoriteThisMeal ? 'text-slate-300 bg-white/5 border-white/5 hover:text-primary hover:bg-primary/10 hover:border-primary/20' : 'text-slate-600 bg-white/[0.03] border-white/5 cursor-not-allowed'}`}
                                title={canFavoriteThisMeal ? '加入收藏餐' : '同步成功后可收藏'}
                                aria-label="加入收藏餐"
                              >
                                <span className="material-symbols-outlined text-[16px]">bookmark_add</span>
                                {isSavingFavorite ? '保存' : '收藏'}
                              </button>
                              <button
                                onClick={() => {
                                  setFeedbackMessage(null);
                                  setActionError(null);
                                  setDeletingMeal(meal);
                                }}
                                className="h-9 rounded-lg flex items-center justify-center gap-1.5 text-xs font-serif font-bold tracking-wide text-slate-300 bg-white/5 border border-white/5 hover:text-red-300 hover:bg-red-500/10 hover:border-red-500/20 transition-colors"
                                title="删除记录"
                                aria-label="删除记录"
                              >
                                <span className="material-symbols-outlined text-[16px]">delete</span>
                                删除
                              </button>
                            </div>

                            {/* Nutrients Detail Line */}
                            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/5 pt-3">
                                <div className="flex flex-wrap items-center gap-2">
                                    <div className="flex items-center gap-1.5 rounded-lg bg-white/5 border border-white/5 px-2 py-1">
                                        <span className="w-1.5 h-1.5 rounded-full bg-primary/50"></span>
                                        <span className="text-[10px] text-slate-400 font-serif font-bold tracking-wide">钠: {meal.sodium}mg</span>
                                    </div>
                                    <div className="flex items-center gap-1.5 rounded-lg bg-white/5 border border-white/5 px-2 py-1">
                                        <span className="w-1.5 h-1.5 rounded-full bg-purple/50"></span>
                                        <span className="text-[10px] text-slate-400 font-serif font-bold tracking-wide">嘌呤: {meal.purine}mg</span>
                                    </div>
                                 </div>
                                 <span className="text-[10px] text-slate-500/80 bg-white/5 px-2 py-1 rounded-lg border border-white/5 font-serif tracking-wide">
                                     {meal.estimatedFields && meal.estimatedFields.length > 0 ? '估算' : '已记录'}
                                 </span>
                             </div>
                             {macroSummary.length > 0 && (
                               <div className="flex flex-wrap gap-2 -mt-1">
                                 {macroSummary.map(item => (
                                   <span key={item} className="text-[10px] text-slate-500 bg-white/5 border border-white/5 rounded-lg px-2 py-1 font-serif font-bold tracking-wide">
                                     {item}
                                   </span>
                                 ))}
                               </div>
                             )}
                             {meal.ruleWarnings && meal.ruleWarnings.length > 0 && (
                                 <div className="rounded-xl border border-amber-300/20 bg-amber-500/10 px-3 py-2">
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
                    </div>
                  </div>
                ))}

                {meals.length === 0 && (
                    <div className="py-8 text-center border border-dashed border-white/10 rounded-xl">
                        <p className="text-slate-500 text-xs font-serif font-bold tracking-wide">{dateLabel}暂无饮食记录</p>
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

                       {(previousMealShortcut || yesterdaySameMealTypeShortcut) && (
                         <div className="space-y-2">
                           <div className="flex items-center justify-between px-1">
                             <label className="text-xs text-slate-500 font-serif font-bold tracking-wide">快捷复记</label>
                             <span className="text-[10px] text-slate-600 font-serif font-bold tracking-wide">填入后可编辑</span>
                           </div>
                           <div className="grid grid-cols-2 gap-2">
                             {previousMealShortcut && (
                               <button
                                 type="button"
                                 onClick={() => copyRecentMealIntoAddForm(previousMealShortcut)}
                                 className="min-w-0 rounded-xl border border-white/10 bg-black/20 px-3 py-2.5 text-left transition-colors hover:border-primary/40 hover:bg-primary/10"
                               >
                                 <p className="text-[10px] text-slate-500 font-serif font-bold tracking-wide">复制上一餐</p>
                                 <p className="mt-1 truncate text-xs text-white font-serif font-bold tracking-wide">{previousMealShortcut.name}</p>
                               </button>
                             )}
                             {yesterdaySameMealTypeShortcut && (
                               <button
                                 type="button"
                                 onClick={() => copyRecentMealIntoAddForm(yesterdaySameMealTypeShortcut)}
                                 className="min-w-0 rounded-xl border border-white/10 bg-black/20 px-3 py-2.5 text-left transition-colors hover:border-primary/40 hover:bg-primary/10"
                               >
                                 <p className="text-[10px] text-slate-500 font-serif font-bold tracking-wide">复制昨日同餐</p>
                                 <p className="mt-1 truncate text-xs text-white font-serif font-bold tracking-wide">{yesterdaySameMealTypeShortcut.name}</p>
                               </button>
                             )}
                           </div>
                         </div>
                       )}

                       {/* Favorite Meals */}
                       <div className="space-y-2">
                            <div className="flex items-center justify-between px-1">
                                <label className="text-xs text-slate-500 font-serif font-bold tracking-wide">收藏餐</label>
                                {isLoadingFavoriteMeals && (
                                  <span className="text-[10px] text-slate-500 font-serif font-bold tracking-wide">加载中...</span>
                                )}
                            </div>
                            {favoriteMealsError && (
                              <p className="rounded-lg border border-amber-300/20 bg-amber-500/10 px-2.5 py-2 text-[11px] text-amber-100 font-serif leading-relaxed">
                                {favoriteMealsError}
                              </p>
                            )}
                            {!isLoadingFavoriteMeals && !favoriteMealsError && favoriteMeals.length === 0 && (
                              <p className="rounded-lg border border-white/5 bg-black/20 px-2.5 py-2 text-[11px] text-slate-500 font-serif leading-relaxed">
                                暂无收藏餐，可在已记录餐食卡片点击收藏。
                              </p>
                            )}
                            {favoriteMeals.length > 0 && (
                              <div className="-mx-1 overflow-x-auto pb-1">
                                <div className="flex gap-2 px-1">
                                  {favoriteMeals.slice(0, 8).map((favorite) => {
                                    const categoryConfig = FOOD_CATEGORIES.find(c => c.id === favorite.category) || FOOD_CATEGORIES[0];
                                    const isUsingFavorite = favoriteActionId === `use:${favorite.id}`;
                                    const isDeletingFavorite = favoriteActionId === `delete:${favorite.id}`;
                                    return (
                                      <div
                                        key={favorite.id}
                                        className="relative min-w-[158px] max-w-[184px] rounded-xl border border-white/10 bg-black/20 px-3 py-2.5 transition-colors hover:border-primary/40 hover:bg-primary/10"
                                      >
                                        <button
                                          type="button"
                                          onClick={() => useFavoriteMealTemplate(favorite)}
                                          disabled={isDeletingFavorite}
                                          className="w-full pr-7 text-left"
                                        >
                                          <div className="flex items-start justify-between gap-2">
                                            <div className="min-w-0">
                                              <p className="truncate text-xs text-white font-serif font-bold tracking-wide">{favorite.name}</p>
                                              <p className="mt-1 truncate text-[11px] text-slate-500 font-serif font-bold tracking-wide">{favorite.portion}</p>
                                            </div>
                                            <span className={`material-symbols-outlined shrink-0 text-lg ${categoryConfig.color}`}>{categoryConfig.icon}</span>
                                          </div>
                                          <div className="mt-2 flex items-center justify-between gap-2">
                                            <span className="text-[10px] text-slate-500 font-serif font-bold tracking-wide">{formatMealType(favorite.meal_type)}</span>
                                            <span className="rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[10px] text-primary font-serif font-bold tracking-wide">{isUsingFavorite ? '填入中' : `${favorite.usage_count} 次`}</span>
                                          </div>
                                        </button>
                                        <button
                                          type="button"
                                          onClick={(event) => deleteFavoriteMealTemplate(favorite, event)}
                                          disabled={Boolean(favoriteActionId)}
                                          className="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-full border border-white/10 bg-white/5 text-slate-500 transition-colors hover:border-red-400/30 hover:bg-red-500/10 hover:text-red-200 disabled:cursor-not-allowed disabled:opacity-50"
                                          title="移除收藏餐"
                                          aria-label="移除收藏餐"
                                        >
                                          <span className="material-symbols-outlined text-[14px]">close</span>
                                        </button>
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            )}
                       </div>

                       {/* Frequent Meals */}
                       <div className="space-y-2">
                            <div className="flex items-center justify-between px-1">
                                <label className="text-xs text-slate-500 font-serif font-bold tracking-wide">最近常吃</label>
                                {isLoadingFrequentMeals && (
                                  <span className="text-[10px] text-slate-500 font-serif font-bold tracking-wide">加载中...</span>
                                )}
                            </div>
                            {frequentMealsError && (
                              <p className="rounded-lg border border-amber-300/20 bg-amber-500/10 px-2.5 py-2 text-[11px] text-amber-100 font-serif leading-relaxed">
                                {frequentMealsError}
                              </p>
                            )}
                            {!isLoadingFrequentMeals && !frequentMealsError && frequentMealShortcuts.length === 0 && (
                              <p className="rounded-lg border border-white/5 bg-black/20 px-2.5 py-2 text-[11px] text-slate-500 font-serif leading-relaxed">
                                最近 14 天暂无可复记餐食。
                              </p>
                            )}
                            {frequentMealShortcuts.length > 0 && (
                              <div className="-mx-1 overflow-x-auto pb-1">
                                <div className="flex gap-2 px-1">
                                  {frequentMealShortcuts.map((shortcut) => {
                                    const categoryConfig = FOOD_CATEGORIES.find(c => c.id === shortcut.category) || FOOD_CATEGORIES[0];
                                    return (
                                      <button
                                        key={shortcut.key}
                                        type="button"
                                        onClick={() => fillMealFromShortcut(shortcut)}
                                        className="min-w-[148px] max-w-[168px] rounded-xl border border-white/10 bg-black/20 px-3 py-2.5 text-left transition-colors hover:border-primary/40 hover:bg-primary/10"
                                      >
                                        <div className="flex items-start justify-between gap-2">
                                          <div className="min-w-0">
                                            <p className="truncate text-xs text-white font-serif font-bold tracking-wide">{shortcut.name}</p>
                                            <p className="mt-1 truncate text-[11px] text-slate-500 font-serif font-bold tracking-wide">{shortcut.portion}</p>
                                          </div>
                                          <span className={`material-symbols-outlined shrink-0 text-lg ${categoryConfig.color}`}>{categoryConfig.icon}</span>
                                        </div>
                                        <div className="mt-2 flex items-center justify-between gap-2">
                                          <span className="text-[10px] text-slate-500 font-serif font-bold tracking-wide">{formatMealType(shortcut.type)}</span>
                                          <span className="rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[10px] text-primary font-serif font-bold tracking-wide">{shortcut.count} 次</span>
                                        </div>
                                        <p className="mt-2 text-[10px] font-serif font-bold tracking-wide text-primary/90">
                                          {buildFrequentMealCTA(shortcut)}
                                        </p>
                                      </button>
                                    );
                                  })}
                                </div>
                              </div>
                            )}
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

                       <div className="rounded-xl border border-white/10 bg-black/20 p-3 space-y-3">
                           <div className="flex items-start justify-between gap-3">
                               <div className="min-w-0">
                                   <p className="text-xs text-white font-serif font-bold tracking-wide">餐前模拟</p>
                                   <p className="mt-1 text-[11px] text-slate-500 font-serif leading-relaxed">先用本地规则预判风险和替换方向，不会自动保存餐食。</p>
                               </div>
                               {(preMealSimulation.decision || preMealSimulation.estimated) && (
                                 <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-bold tracking-wide ${preMealRiskStyle.className}`}>
                                   {preMealRiskStyle.label}
                                 </span>
                               )}
                           </div>
                           <button
                             type="button"
                             onClick={runPreMealSimulation}
                             disabled={preMealSimulation.isLoading || !mealInput.name.trim()}
                             className="w-full rounded-xl border border-primary/20 bg-primary/10 px-3 py-2.5 text-xs font-bold tracking-wide text-primary transition-colors hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-50"
                           >
                             {preMealSimulation.isLoading ? '模拟中...' : '先做餐前预判'}
                           </button>
                           {isPreMealSimulationStale && (
                             <p className="rounded-lg border border-amber-300/20 bg-amber-500/10 px-2.5 py-2 text-[11px] text-amber-100 font-serif leading-relaxed">
                               当前输入已变化，请重新餐前预判后再参考结果。
                             </p>
                           )}
                           {preMealSimulation.error && (
                             <p className="rounded-lg border border-amber-300/20 bg-amber-500/10 px-2.5 py-2 text-[11px] text-amber-100 font-serif leading-relaxed">
                               {preMealSimulation.error}
                             </p>
                           )}
                           {preMealSimulation.estimated && (
                             <div className="grid grid-cols-3 gap-2">
                               <div className="rounded-lg bg-white/[0.03] px-2 py-2"><p className="text-[10px] text-slate-500 font-bold">热量</p><p className="text-xs text-white font-bold">{preMealSimulation.estimated.calories} kcal</p></div>
                               <div className="rounded-lg bg-white/[0.03] px-2 py-2"><p className="text-[10px] text-slate-500 font-bold">钠</p><p className="text-xs text-white font-bold">{preMealSimulation.estimated.sodium} mg</p></div>
                               <div className="rounded-lg bg-white/[0.03] px-2 py-2"><p className="text-[10px] text-slate-500 font-bold">嘌呤</p><p className="text-xs text-white font-bold">{preMealSimulation.estimated.purine} mg</p></div>
                             </div>
                           )}
                           {preMealSimulation.decision && (
                             <div className="space-y-2">
                               <p className="text-[11px] text-slate-300 font-serif leading-relaxed">{preMealSimulation.decision.summary}</p>
                               {(preMealSimulation.decision.portion_guidance || preMealSimulation.decision.frequency_guidance) && (
                                 <p className="text-[11px] text-slate-400 font-serif leading-relaxed">
                                   {[preMealSimulation.decision.portion_guidance, preMealSimulation.decision.frequency_guidance].filter(Boolean).join(' ')}
                                 </p>
                               )}
                               {preMealSimulation.decision.hard_blocks.length > 0 && (
                                 <p className="rounded-lg border border-red-400/20 bg-red-500/10 px-2.5 py-2 text-[11px] text-red-100 font-serif leading-relaxed">
                                   {preMealSimulation.decision.hard_blocks.join('、')}
                                 </p>
                               )}
                             </div>
                           )}
                           {preMealSimulation.swaps.length > 0 && (
                             <div className="space-y-1.5">
                               <p className="text-[10px] text-slate-500 font-serif font-bold tracking-wide">可选替换/调整</p>
                               {preMealSimulation.swaps.map((swap) => (
                                 <p key={swap} className="text-[11px] text-slate-300 font-serif leading-relaxed">- {swap}</p>
                               ))}
                             </div>
                           )}
                           <p className="text-[10px] text-slate-500 font-serif leading-relaxed">{COMPLIANCE_MEDICAL_DISCLAIMER}</p>
                       </div>

                       <div className="pt-2 flex flex-col gap-3">
                           <button
                              onClick={addMeal}
                              disabled={isSavingAdd || !mealInput.name.trim()}
                              className="w-full bg-gradient-to-r from-primary to-[#45b7aa] text-background-dark font-bold py-3.5 rounded-xl hover:shadow-[0_0_20px_rgba(17,196,212,0.4)] transition-all active:scale-[0.98] flex items-center justify-center gap-2 font-serif tracking-wide disabled:opacity-50 disabled:cursor-not-allowed"
                           >
                               <span className="material-symbols-outlined text-lg">auto_awesome</span>
                                {isSavingAdd ? '保存中...' : `记录到${dateLabel}`}
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

      {/* Packaged Food Panel */}
      <div className="mt-6 space-y-4">
        <div className="rounded-2xl border border-white/5 bg-surface-dark p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="text-white tracking-wide text-lg font-bold leading-tight font-serif">包装食品复核</h3>
              <p className="mt-1 text-xs text-slate-500 font-serif font-bold tracking-wide leading-relaxed">
                条码或营养标签会先经过本地规则复核，过敏、忌口、AVOID / LIMIT 约束不会被放宽。
              </p>
            </div>
            <span className="rounded-full border border-primary/20 bg-primary/10 px-2 py-1 text-[10px] font-bold tracking-wide text-primary">
              灰度入口
            </span>
          </div>
          <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
            <div className="rounded-2xl border border-white/5 bg-black/20 p-3 space-y-3">
              <label className="text-xs text-slate-500 ml-1 mb-1 block font-serif font-bold tracking-wide">条码查询</label>
              <div className="flex gap-2">
                <input
                  value={packagedLookup.barcode}
                  onChange={(e) => setPackagedLookup(prev => ({ ...prev, barcode: e.target.value }))}
                  placeholder="例如 6901234567892"
                  className="min-w-0 flex-1 bg-black/20 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm outline-none focus:border-primary/50 transition-colors font-serif tracking-wide"
                />
                <button
                  onClick={lookupPackagedFood}
                  disabled={packagedLookup.isLoading}
                  className="shrink-0 rounded-xl bg-primary/20 border border-primary/20 px-3 py-2.5 text-xs font-bold tracking-wide text-primary disabled:opacity-50"
                >
                  {packagedLookup.isLoading ? '查询中...' : '查询'}
                </button>
              </div>
              <p className="text-[11px] text-slate-500 font-serif leading-relaxed">
                仅返回条码后四位用于审计，生产环境不会回传完整条码。
              </p>
              {packagedLookup.error && (
                <p className="rounded-xl border border-amber-300/20 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-100 font-serif leading-relaxed">
                  {packagedLookup.error}
                </p>
              )}
              {packagedLookup.response && (
                <div className="rounded-xl border border-white/5 bg-white/[0.03] p-3 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-serif font-bold tracking-wide text-white">
                      {packagedLookup.response.matched ? '已匹配候选' : '未匹配到条码'}
                    </p>
                    <span className="text-[10px] font-bold tracking-wide text-slate-400">
                      {packagedLookup.response.provider} · {packagedLookup.response.provider_status}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 leading-relaxed font-serif">
                    {packagedLookup.response.disclaimer}
                  </p>
                  {packagedLookup.response.candidates.map((candidate, index) => (
                    <button
                      key={`${candidate.food_name}-${index}`}
                      onClick={() => setPackagedLookup(prev => ({ ...prev, selectedCandidateIndex: index }))}
                      className={`w-full text-left rounded-xl border px-3 py-2.5 transition-colors ${packagedLookup.selectedCandidateIndex === index ? 'border-primary/40 bg-primary/10' : 'border-white/5 bg-black/20'}`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-sm font-serif font-bold tracking-wide text-white break-words">{candidate.food_name}</p>
                          <p className="mt-0.5 text-[11px] text-slate-500 font-serif">
                            {candidate.brand || '无品牌'} · {candidate.category} · 置信度 {Math.round(candidate.confidence * 100)}%
                          </p>
                        </div>
                        <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] font-bold tracking-wide text-slate-300">
                          {candidate.review_required ? '需复核' : '可参考'}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="rounded-2xl border border-white/5 bg-black/20 p-3 space-y-3">
              <label className="text-xs text-slate-500 ml-1 mb-1 block font-serif font-bold tracking-wide">手动营养标签</label>
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                  <input value={packagedLabelInput.productName} onChange={(e) => setPackagedLabelInput(prev => ({ ...prev, productName: e.target.value }))} placeholder="商品名称" className="w-full bg-black/20 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm outline-none focus:border-primary/50 transition-colors font-serif tracking-wide" />
                </div>
                <input value={packagedLabelInput.brand} onChange={(e) => setPackagedLabelInput(prev => ({ ...prev, brand: e.target.value }))} placeholder="品牌" className="bg-black/20 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm outline-none focus:border-primary/50 transition-colors font-serif tracking-wide" />
                <input value={packagedLabelInput.barcode} onChange={(e) => setPackagedLabelInput(prev => ({ ...prev, barcode: e.target.value }))} placeholder="条码" className="bg-black/20 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm outline-none focus:border-primary/50 transition-colors font-serif tracking-wide" />
                <select value={packagedLabelInput.category} onChange={(e) => setPackagedLabelInput(prev => ({ ...prev, category: e.target.value as PackagedFoodLabelInput['category'] }))} className="col-span-2 bg-black/20 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm outline-none focus:border-primary/50 transition-colors font-serif tracking-wide">
                  <option value="SNACK">零食</option>
                  <option value="STAPLE">主食</option>
                  <option value="MEAT">肉蛋</option>
                  <option value="VEG">蔬果</option>
                  <option value="DRINK">饮品</option>
                  <option value="SOY">豆制品</option>
                  <option value="DAIRY">乳制品</option>
                  <option value="SEAFOOD">海鲜</option>
                  <option value="CONDIMENT">调味品</option>
                  <option value="BEVERAGE">饮料</option>
                </select>
                {['servingSize','servingSizeG','caloriesPer100g','proteinPer100g','carbsPer100g','fatPer100g','fiberPer100g','sodiumPer100g','sugarPer100g','purinePer100g'].map((field) => (
                  <input
                    key={field}
                    value={(packagedLabelInput as any)[field]}
                    onChange={(e) => setPackagedLabelInput(prev => ({ ...prev, [field]: e.target.value }))}
                    placeholder={field}
                    className="bg-black/20 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm outline-none focus:border-primary/50 transition-colors font-serif tracking-wide"
                  />
                ))}
                <textarea value={packagedLabelInput.ingredients} onChange={(e) => setPackagedLabelInput(prev => ({ ...prev, ingredients: e.target.value }))} placeholder="配料，逗号分隔" rows={2} className="col-span-2 bg-black/20 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm outline-none focus:border-primary/50 transition-colors font-serif tracking-wide resize-none" />
                <textarea value={packagedLabelInput.allergenTags} onChange={(e) => setPackagedLabelInput(prev => ({ ...prev, allergenTags: e.target.value }))} placeholder="过敏标签" rows={2} className="bg-black/20 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm outline-none focus:border-primary/50 transition-colors font-serif tracking-wide resize-none" />
                <textarea value={packagedLabelInput.riskTags} onChange={(e) => setPackagedLabelInput(prev => ({ ...prev, riskTags: e.target.value }))} placeholder="风险标签" rows={2} className="bg-black/20 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm outline-none focus:border-primary/50 transition-colors font-serif tracking-wide resize-none" />
              </div>
              <button onClick={normalizePackagedLabel} disabled={packagedLookup.isLoading} className="w-full rounded-xl bg-primary/20 border border-primary/20 px-3 py-2.5 text-xs font-bold tracking-wide text-primary disabled:opacity-50">
                {packagedLookup.isLoading ? '归一化中...' : '按标签归一化并复核'}
              </button>
              {activePackagedCandidate && (
                <div className="rounded-xl border border-white/5 bg-white/[0.03] p-3 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-serif font-bold tracking-wide text-white break-words">{activePackagedCandidate.food_name}</p>
                    <span className="text-[10px] font-bold tracking-wide text-slate-400">
                      {activePackagedCandidate.nutrition_review_status}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 leading-relaxed font-serif">
                    {activePackagedCandidate.local_decision.summary}
                  </p>
                  {activePackagedCandidate.review_required && (
                    <p className="rounded-xl border border-amber-300/20 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-100 leading-relaxed font-serif">
                      {activePackagedCandidate.review_reasons.join('、')}
                    </p>
                  )}
                </div>
              )}
              <p className="text-[11px] text-slate-500 font-serif leading-relaxed">{PACKAGED_FOOD_DISCLAIMER}</p>
            </div>
          </div>
        </div>
      </div>

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
