import { useCallback, useState } from 'react';
import { AppMessage, ConditionData, DailyTargets, Meal, MealUpdateInput, UserProfile } from '../types';
import { DEFAULT_DAILY_TARGETS, DEFAULT_USER_PROFILE } from '../constants/app';
import { GUEST_APP_MESSAGES, GUEST_MEALS, GUEST_MEDICAL_DATA, GUEST_USER_PROFILE } from '../data/demoData';
import { AuthAPI, ConditionsAPI, MealsAPI, MessagesAPI, TokenManager } from '../services/api';
import { CacheCleanupService, OfflineMealsService, getTodayDateString, syncScheduler } from '../services/offline';
import { clearSensitiveSessionState } from '../services/sessionState';
import { mapCondition, mapDailyTargets, mapMeal, mapMessage, mapProfile } from '../services/mappers/appMappers';

type LoadUserDataResult = {
  success: boolean;
  userId?: number;
};

function cachedMealToMeal(item: Awaited<ReturnType<typeof OfflineMealsService.getToday>>[number]): Meal {
  return {
    id: item.clientId,
    clientId: item.clientId,
    name: item.name,
    portion: item.portion || '1份',
    calories: item.calories || 0,
    sodium: item.sodium || 0,
    purine: item.purine || 0,
    protein: item.protein,
    carbs: item.carbs,
    fat: item.fat,
    fiber: item.fiber,
    type: item.mealType || 'DINNER',
    category: item.category || 'STAPLE',
    note: item.note || '',
    source: 'manual',
    estimatedFields: ['calories', 'sodium', 'purine'],
  };
}

function parseServerMealId(mealId: string): number {
  const parsed = Number(mealId);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error('这条记录仍在离线待同步状态，暂不支持编辑或删除。请联网同步后再操作。');
  }
  return parsed;
}

export function useAppData() {
  const [isGuest, setIsGuest] = useState(false);
  const [currentUserId, setCurrentUserId] = useState<number | null>(null);
  const [userProfile, setUserProfile] = useState<UserProfile>(DEFAULT_USER_PROFILE);
  const [medicalConditions, setMedicalConditions] = useState<ConditionData[]>([]);
  const [meals, setMeals] = useState<Meal[]>([]);
  const [appMessages, setAppMessages] = useState<AppMessage[]>([]);
  const [dailyTargets, setDailyTargets] = useState<DailyTargets>(DEFAULT_DAILY_TARGETS);

  const refreshDailyTargets = useCallback(async (): Promise<void> => {
    if (!TokenManager.isAuthenticated()) {
      setDailyTargets(DEFAULT_DAILY_TARGETS);
      return;
    }

    try {
      const targets = await AuthAPI.getDailyTargets();
      setDailyTargets(mapDailyTargets(targets));
    } catch (error) {
      console.error('刷新每日目标失败:', error);
      setDailyTargets(DEFAULT_DAILY_TARGETS);
    }
  }, []);

  const refreshMeals = useCallback(async (userId: number = currentUserId ?? 0): Promise<void> => {
    if (!userId) return;

    try {
      const remoteMeals = await MealsAPI.getToday() as any[];
      const mappedRemoteMeals = Array.isArray(remoteMeals) ? remoteMeals.map(mapMeal) : [];
      const localPending = (await OfflineMealsService.getToday(userId))
        .filter(item => item.syncStatus === 'PENDING')
        .map(cachedMealToMeal);

      const remoteClientIds = new Set(mappedRemoteMeals.map(meal => meal.clientId));
      setMeals([
        ...mappedRemoteMeals,
        ...localPending.filter(meal => !remoteClientIds.has(meal.clientId)),
      ]);
    } catch {
      const localMeals = await OfflineMealsService.getToday(userId);
      setMeals(localMeals.map(cachedMealToMeal));
    }
  }, [currentUserId]);

  const loadUserData = useCallback(async (): Promise<LoadUserDataResult> => {
    try {
      const [profileRes, targetsRes, mealsRes, conditionsRes, messagesRes] = await Promise.allSettled([
        AuthAPI.getProfile(),
        AuthAPI.getDailyTargets(),
        MealsAPI.getToday(),
        ConditionsAPI.list(),
        MessagesAPI.list({ limit: 20 }),
      ]);

      if (profileRes.status !== 'fulfilled') {
        TokenManager.clearTokens();
        return { success: false };
      }

      const profile = mapProfile(profileRes.value as any);
      if (!profile.id) {
        TokenManager.clearTokens();
        return { success: false };
      }

      setIsGuest(false);
      setCurrentUserId(profile.id);
      setUserProfile(profile);

      if (targetsRes.status === 'fulfilled') {
        setDailyTargets(mapDailyTargets(targetsRes.value));
      } else {
        setDailyTargets(DEFAULT_DAILY_TARGETS);
      }

      if (mealsRes.status === 'fulfilled') {
        const remoteMeals = Array.isArray(mealsRes.value) ? (mealsRes.value as any[]).map(mapMeal) : [];
        const localPending = (await OfflineMealsService.getToday(profile.id))
          .filter(item => item.syncStatus === 'PENDING')
          .map(cachedMealToMeal);
        const remoteClientIds = new Set(remoteMeals.map(meal => meal.clientId));
        setMeals([...remoteMeals, ...localPending.filter(meal => !remoteClientIds.has(meal.clientId))]);
      } else {
        const localMeals = await OfflineMealsService.getToday(profile.id);
        setMeals(localMeals.map(cachedMealToMeal));
      }

      if (conditionsRes.status === 'fulfilled') {
        const conditions = Array.isArray(conditionsRes.value) ? (conditionsRes.value as any[]).map(mapCondition) : [];
        setMedicalConditions(conditions);
      } else {
        setMedicalConditions([]);
      }

      if (messagesRes.status === 'fulfilled') {
        const messages = Array.isArray(messagesRes.value) ? (messagesRes.value as any[]).map(mapMessage) : [];
        setAppMessages(messages);
      } else {
        setAppMessages([]);
      }

      syncScheduler.start(profile.id);
      return { success: true, userId: profile.id };
    } catch (error) {
      console.error('加载用户数据失败:', error);
      TokenManager.clearTokens();
      return { success: false };
    }
  }, []);

  const enterGuestMode = useCallback(() => {
    TokenManager.clearTokens();
    syncScheduler.stop();
    clearSensitiveSessionState();
    setIsGuest(true);
    setCurrentUserId(null);
    setUserProfile(GUEST_USER_PROFILE);
    setMedicalConditions(GUEST_MEDICAL_DATA);
    setMeals(GUEST_MEALS);
    setAppMessages(GUEST_APP_MESSAGES);
    setDailyTargets(DEFAULT_DAILY_TARGETS);
  }, []);

  const logout = useCallback(() => {
    const userId = currentUserId;
    TokenManager.clearTokens();
    syncScheduler.stop();
    clearSensitiveSessionState();
    setIsGuest(false);
    setCurrentUserId(null);
    setUserProfile(DEFAULT_USER_PROFILE);
    setMedicalConditions([]);
    setMeals([]);
    setAppMessages([]);
    setDailyTargets(DEFAULT_DAILY_TARGETS);

    void (async () => {
      if (userId) {
        await CacheCleanupService.clearUserLocalData(userId);
      } else {
        await CacheCleanupService.clearAll();
      }
    })();
  }, [currentUserId]);

  const markAllMessagesRead = useCallback(async () => {
    setAppMessages(prev => prev.map(message => ({ ...message, isRead: true })));

    if (TokenManager.isAuthenticated()) {
      try {
        await MessagesAPI.markAllAsRead();
      } catch (err) {
        console.error('标记已读失败:', err);
      }
    }
  }, []);

  const addMeal = useCallback(async (meal: Meal) => {
    setMeals(prev => [...prev, meal]);

    if (!TokenManager.isAuthenticated() || !currentUserId) return;

    try {
      await MealsAPI.create({
        client_id: meal.clientId || meal.id,
        name: meal.name,
        portion: meal.portion || '1份',
        calories: meal.calories,
        sodium: meal.sodium,
        purine: meal.purine,
        protein: meal.protein,
        carbs: meal.carbs,
        fat: meal.fat,
        fiber: meal.fiber,
        meal_type: meal.type,
        category: meal.category,
        record_date: getTodayDateString(),
        note: meal.note,
        source: meal.source || 'manual',
        source_detail: meal.sourceDetail,
        confidence: meal.confidence,
        estimated_fields_json: meal.estimatedFields || [],
        rule_warnings_json: meal.ruleWarnings || [],
        recognition_meta_json: meal.recognitionMeta,
      });
      await refreshMeals(currentUserId);
    } catch (error) {
      console.error('同步饮食记录失败:', error);
      await OfflineMealsService.add(currentUserId, {
        clientId: meal.clientId || meal.id,
        serverId: undefined,
        name: meal.name,
        portion: meal.portion || '1份',
        calories: meal.calories || 0,
        sodium: meal.sodium || 0,
        purine: meal.purine || 0,
        protein: meal.protein,
        carbs: meal.carbs,
        fat: meal.fat,
        fiber: meal.fiber,
        mealType: meal.type,
        category: meal.category,
        recordDate: getTodayDateString(),
        note: meal.note,
        aiRecognized: false,
      });
    }
  }, [currentUserId, refreshMeals]);

  const updateMeal = useCallback(async (mealId: string, changes: MealUpdateInput): Promise<void> => {
    if (!TokenManager.isAuthenticated()) {
      throw new Error('请先登录后再编辑饮食记录。');
    }

    const serverMealId = parseServerMealId(mealId);
    await MealsAPI.updateMeal(serverMealId, {
      name: changes.name,
      portion: changes.portion,
      calories: changes.calories,
      sodium: changes.sodium,
      purine: changes.purine,
      protein: changes.protein,
      carbs: changes.carbs,
      fat: changes.fat,
      fiber: changes.fiber,
      meal_type: changes.type,
      category: changes.category,
      note: changes.note,
    });
    await refreshMeals();
  }, [refreshMeals]);

  const deleteMeal = useCallback(async (mealId: string): Promise<void> => {
    if (!TokenManager.isAuthenticated()) {
      throw new Error('请先登录后再删除饮食记录。');
    }

    const serverMealId = parseServerMealId(mealId);
    await MealsAPI.deleteMeal(serverMealId);
    await refreshMeals();
  }, [refreshMeals]);

  const updateProfile = useCallback(async (profile: UserProfile) => {
    setUserProfile(profile);
    if (!TokenManager.isAuthenticated()) return;

    const updatedProfile = await AuthAPI.updateProfile({
      gender: profile.gender,
      age: profile.age,
      height: profile.height,
      weight: profile.weight,
    });
    setUserProfile(mapProfile(updatedProfile as any));
    await refreshDailyTargets();
  }, [refreshDailyTargets]);

  const updateNickname = useCallback(async (nickname: string) => {
    const trimmed = nickname.trim();
    if (!trimmed) return;

    setUserProfile(prev => ({ ...prev, nickname: trimmed }));
    if (TokenManager.isAuthenticated()) {
      try {
        await AuthAPI.updateProfile({ nickname: trimmed });
      } catch (error) {
        console.error('保存昵称失败:', error);
      }
    }
  }, []);

  return {
    isGuest,
    currentUserId,
    userProfile,
    medicalConditions,
    meals,
    appMessages,
    dailyTargets,
    setMedicalConditions,
    loadUserData,
    enterGuestMode,
    logout,
    markAllMessagesRead,
    addMeal,
    updateMeal,
    deleteMeal,
    refreshMeals,
    refreshDailyTargets,
    updateProfile,
    updateNickname,
  };
}
