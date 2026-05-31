import { useCallback, useEffect, useState } from 'react';
import { AppMessage, ConditionData, DailyTargets, Meal, MealUpdateInput, UserProfile } from '../types';
import { DEFAULT_DAILY_TARGETS, DEFAULT_USER_PROFILE } from '../constants/app';
import { GUEST_APP_MESSAGES, GUEST_MEALS, GUEST_MEDICAL_DATA, GUEST_USER_PROFILE } from '../data/demoData';
import { AuthAPI, ConditionsAPI, InsightsAPI, MealsAPI, MessagesAPI, TokenManager } from '../services/api';
import { CacheCleanupService, CachedMeal, OfflineMealsService, getTodayDateString, syncScheduler } from '../services/offline';
import { clearSensitiveSessionState } from '../services/sessionState';
import { mapCondition, mapDailyTargets, mapMeal, mapMessage, mapProfile } from '../services/mappers/appMappers';

type LoadUserDataResult = {
  success: boolean;
  userId?: number;
};

function cachedMealToMeal(item: Awaited<ReturnType<typeof OfflineMealsService.getToday>>[number]): Meal | null {
  if (item.pendingDelete) return null;
  const syncStatusLabel =
    item.syncStatus === 'FAILED' ? '离线同步失败' :
      item.syncStatus === 'CONFLICT' ? '离线冲突待处理' :
        item.syncStatus === 'PENDING' ? '离线待同步' : '已同步';
  return {
    id: item.clientId,
    clientId: item.clientId,
    recordDate: item.recordDate,
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
    source: item.source || 'manual',
    sourceDetail: item.sourceDetail || syncStatusLabel,
    confidence: item.confidence,
    estimatedFields: item.estimatedFields || ['calories', 'sodium', 'purine'],
    ruleWarnings: item.ruleWarnings || [],
    recognitionMeta: item.recognitionMeta,
    pendingDelete: item.pendingDelete ?? false,
    syncStatus: item.syncStatus,
    lastSyncError: item.lastSyncError,
    retryCount: item.retryCount,
  };
}

function cachedMealsToVisibleMeals(items: Awaited<ReturnType<typeof OfflineMealsService.getToday>>): Meal[] {
  return items.map(cachedMealToMeal).filter(Boolean) as Meal[];
}

function parseServerMealId(mealId: string): number {
  const parsed = Number(mealId);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error('这条记录仍在离线待同步状态，暂不支持编辑或删除。请联网同步后再操作。');
  }
  return parsed;
}

function maybeServerMealId(mealId: string): number | null {
  const parsed = Number(mealId);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function applyMealUpdateInput(meal: Meal, changes: MealUpdateInput): Meal {
  return {
    ...meal,
    ...changes,
    type: changes.type || meal.type,
    category: changes.category || meal.category,
  };
}

function mealToCachedDraft(meal: Meal, serverId?: number): Omit<CachedMeal, 'id' | 'userId' | 'syncStatus' | 'createdAt' | 'updatedAt'> {
  return {
    clientId: meal.clientId || meal.id,
    serverId,
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
    recordDate: meal.recordDate || getTodayDateString(),
    note: meal.note,
    aiRecognized: meal.source === 'photo' || meal.source === 'ai_quick_log',
    source: meal.source || 'manual',
    sourceDetail: meal.sourceDetail,
    confidence: meal.confidence,
    estimatedFields: meal.estimatedFields || [],
    ruleWarnings: meal.ruleWarnings || [],
    recognitionMeta: meal.recognitionMeta,
  };
}

function mealUpdateInputToCachedChanges(changes: MealUpdateInput): Partial<CachedMeal> {
  return {
    name: changes.name,
    portion: changes.portion,
    calories: changes.calories,
    sodium: changes.sodium,
    purine: changes.purine,
    protein: changes.protein,
    carbs: changes.carbs,
    fat: changes.fat,
    fiber: changes.fiber,
    mealType: changes.type,
    category: changes.category,
    note: changes.note,
  };
}

export function useAppData() {
  const [isGuest, setIsGuest] = useState(false);
  const [currentUserId, setCurrentUserId] = useState<number | null>(null);
  const [userProfile, setUserProfile] = useState<UserProfile>(DEFAULT_USER_PROFILE);
  const [medicalConditions, setMedicalConditions] = useState<ConditionData[]>([]);
  const [meals, setMeals] = useState<Meal[]>([]);
  const [currentMealDate, setCurrentMealDate] = useState(getTodayDateString());
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

  const refreshMeals = useCallback(async (
    targetDate: string = currentMealDate,
    userId: number = currentUserId ?? 0
  ): Promise<void> => {
    if (!userId) return;
    setCurrentMealDate(targetDate);

    try {
      const remoteMealsResponse = await MealsAPI.list({ record_date: targetDate, page_size: 100 }) as any;
      const remoteMeals = Array.isArray(remoteMealsResponse?.items)
        ? remoteMealsResponse.items
        : Array.isArray(remoteMealsResponse)
          ? remoteMealsResponse
          : [];
      const mappedRemoteMeals = remoteMeals.map(mapMeal);
      const localPending = (await OfflineMealsService.getByDate(userId, targetDate))
        .filter(item => item.syncStatus === 'PENDING' || item.syncStatus === 'FAILED' || item.syncStatus === 'CONFLICT')
        .map(cachedMealToMeal)
        .filter(Boolean) as Meal[];

      const remoteClientIds = new Set(mappedRemoteMeals.map(meal => meal.clientId));
      setMeals([
        ...mappedRemoteMeals,
        ...localPending.filter(meal => !remoteClientIds.has(meal.clientId)),
      ]);
    } catch {
      const localMeals = await OfflineMealsService.getByDate(userId, targetDate);
      setMeals(cachedMealsToVisibleMeals(localMeals));
    }
  }, [currentMealDate, currentUserId]);

  const refreshMessages = useCallback(async (): Promise<void> => {
    if (!TokenManager.isAuthenticated()) return;

    try {
      const messagesResponse = await MessagesAPI.list({ limit: 20 });
      const messages = Array.isArray(messagesResponse) ? (messagesResponse as any[]).map(mapMessage) : [];
      setAppMessages(messages);
    } catch (error) {
      console.error('刷新消息失败:', error);
    }
  }, []);

  const refreshSmartInsightsAndMessages = useCallback(async (): Promise<void> => {
    if (!TokenManager.isAuthenticated()) return;

    try {
      await InsightsAPI.refresh();
    } catch (error) {
      console.error('刷新智能洞察失败:', error);
    }

    await refreshMessages();
  }, [refreshMessages]);

  const refreshAfterMealChange = useCallback(async (
    recordDate: string = getTodayDateString()
  ): Promise<void> => {
    await refreshMeals(recordDate);

    if (recordDate === getTodayDateString()) {
      await refreshSmartInsightsAndMessages();
    }
  }, [refreshMeals, refreshSmartInsightsAndMessages]);

  useEffect(() => {
    const handleMealsSynced = () => {
      if (!currentUserId) return;
      void refreshAfterMealChange(currentMealDate);
    };

    window.addEventListener('prism:meals-synced', handleMealsSynced);
    return () => window.removeEventListener('prism:meals-synced', handleMealsSynced);
  }, [currentMealDate, currentUserId, refreshAfterMealChange]);

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
      setCurrentMealDate(getTodayDateString());

      if (targetsRes.status === 'fulfilled') {
        setDailyTargets(mapDailyTargets(targetsRes.value));
      } else {
        setDailyTargets(DEFAULT_DAILY_TARGETS);
      }

      if (mealsRes.status === 'fulfilled') {
        const remoteMeals = Array.isArray(mealsRes.value) ? (mealsRes.value as any[]).map(mapMeal) : [];
        const localPending = (await OfflineMealsService.getToday(profile.id))
          .filter(item => item.syncStatus === 'PENDING' || item.syncStatus === 'FAILED' || item.syncStatus === 'CONFLICT')
          .map(cachedMealToMeal)
          .filter(Boolean) as Meal[];
        const remoteClientIds = new Set(remoteMeals.map(meal => meal.clientId));
        setMeals([...remoteMeals, ...localPending.filter(meal => !remoteClientIds.has(meal.clientId))]);
      } else {
        const localMeals = await OfflineMealsService.getToday(profile.id);
        setMeals(cachedMealsToVisibleMeals(localMeals));
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
      void refreshSmartInsightsAndMessages();
      return { success: true, userId: profile.id };
    } catch (error) {
      console.error('加载用户数据失败:', error);
      TokenManager.clearTokens();
      return { success: false };
    }
  }, [refreshSmartInsightsAndMessages]);

  const enterGuestMode = useCallback(() => {
    TokenManager.clearTokens();
    syncScheduler.stop();
    clearSensitiveSessionState();
    setIsGuest(true);
    setCurrentUserId(null);
    setUserProfile(GUEST_USER_PROFILE);
    setMedicalConditions(GUEST_MEDICAL_DATA);
    setMeals(GUEST_MEALS);
    setCurrentMealDate(getTodayDateString());
    setAppMessages(GUEST_APP_MESSAGES);
    setDailyTargets(DEFAULT_DAILY_TARGETS);
  }, []);

  const exitGuestMode = useCallback(() => {
    TokenManager.clearTokens();
    syncScheduler.stop();
    clearSensitiveSessionState();
    setIsGuest(false);
    setCurrentUserId(null);
    setUserProfile(DEFAULT_USER_PROFILE);
    setMedicalConditions([]);
    setMeals([]);
    setCurrentMealDate(getTodayDateString());
    setAppMessages([]);
    setDailyTargets(DEFAULT_DAILY_TARGETS);
  }, []);

  const logout = useCallback(() => {
    const userId = currentUserId;
    if (TokenManager.isAuthenticated()) {
      void AuthAPI.logout().catch(error => {
        console.warn('远程注销失败:', error);
      });
    }
    TokenManager.clearTokens();
    syncScheduler.stop();
    clearSensitiveSessionState();
    setIsGuest(false);
    setCurrentUserId(null);
    setUserProfile(DEFAULT_USER_PROFILE);
    setMedicalConditions([]);
    setMeals([]);
    setCurrentMealDate(getTodayDateString());
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

  const clearUserContent = useCallback(() => {
    setMedicalConditions([]);
    setMeals([]);
    setAppMessages([]);
    setDailyTargets(DEFAULT_DAILY_TARGETS);
    setCurrentMealDate(getTodayDateString());
  }, []);

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

  const addMeal = useCallback(async (meal: Meal, recordDate: string = currentMealDate) => {
    const mealForDate = { ...meal, recordDate };
    setMeals(prev => recordDate === currentMealDate ? [...prev, mealForDate] : prev);

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
        record_date: recordDate,
        note: meal.note,
        source: meal.source || 'manual',
        source_detail: meal.sourceDetail,
        confidence: meal.confidence,
        estimated_fields_json: meal.estimatedFields || [],
        rule_warnings_json: meal.ruleWarnings || [],
        recognition_meta_json: meal.recognitionMeta,
      });
      await refreshMeals(recordDate, currentUserId);
      if (recordDate === getTodayDateString()) {
        await refreshSmartInsightsAndMessages();
      }
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
        recordDate,
        note: meal.note,
        aiRecognized: false,
      });
      setMeals(prev => prev.map(item =>
        item.id === meal.id || item.clientId === meal.clientId
          ? { ...item, sourceDetail: '离线待同步', syncStatus: 'PENDING' }
          : item
      ));
    }
  }, [currentMealDate, currentUserId, refreshMeals, refreshSmartInsightsAndMessages]);

  const updateMeal = useCallback(async (mealId: string, changes: MealUpdateInput): Promise<void> => {
    if (!TokenManager.isAuthenticated() || !currentUserId) {
      throw new Error('请先登录后再编辑饮食记录。');
    }

    const serverMealId = maybeServerMealId(mealId);
    const targetMeal = meals.find(meal => meal.id === mealId || meal.clientId === mealId);

    const persistOfflineUpdate = async () => {
      if (!targetMeal) {
        throw new Error('未找到可编辑的本地记录。');
      }
      const updatedMeal = applyMealUpdateInput(targetMeal, changes);
      const clientId = updatedMeal.clientId || updatedMeal.id;
      const cachedChanges = mealUpdateInputToCachedChanges(changes);
      const existing = await OfflineMealsService.getByClientId(currentUserId, clientId);

      if (existing?.id) {
        await OfflineMealsService.update(currentUserId, existing.id, cachedChanges);
      } else {
        await OfflineMealsService.add(currentUserId, mealToCachedDraft(updatedMeal, serverMealId || undefined));
        const created = await OfflineMealsService.getByClientId(currentUserId, clientId);
        if (created?.id) {
          await OfflineMealsService.update(currentUserId, created.id, cachedChanges);
        }
      }

      setMeals(prev => prev.map(meal =>
        meal.id === mealId || meal.clientId === mealId
          ? { ...applyMealUpdateInput(meal, changes), sourceDetail: '离线待同步', syncStatus: 'PENDING', lastSyncError: undefined }
          : meal
      ));
    };

    if (serverMealId) {
      try {
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
        await refreshMeals(currentMealDate);
        if (currentMealDate === getTodayDateString()) {
          await refreshSmartInsightsAndMessages();
        }
        return;
      } catch (error) {
        console.warn('在线编辑失败，写入离线更新队列:', error);
        await persistOfflineUpdate();
        return;
      }
    }

    await persistOfflineUpdate();
  }, [currentMealDate, currentUserId, meals, refreshMeals, refreshSmartInsightsAndMessages]);

  const deleteMeal = useCallback(async (mealId: string): Promise<void> => {
    if (!TokenManager.isAuthenticated() || !currentUserId) {
      throw new Error('请先登录后再删除饮食记录。');
    }

    const serverMealId = maybeServerMealId(mealId);
    const targetMeal = meals.find(meal => meal.id === mealId || meal.clientId === mealId);

    const persistOfflineDelete = async () => {
      if (!targetMeal) {
        throw new Error('未找到可删除的本地记录。');
      }
      const clientId = targetMeal.clientId || targetMeal.id;
      const existing = await OfflineMealsService.getByClientId(currentUserId, clientId);

      if (existing?.id) {
        await OfflineMealsService.delete(currentUserId, existing.id);
      } else {
        await OfflineMealsService.add(currentUserId, mealToCachedDraft(targetMeal, serverMealId || undefined));
        const created = await OfflineMealsService.getByClientId(currentUserId, clientId);
        if (created?.id) {
          await OfflineMealsService.delete(currentUserId, created.id);
        }
      }

      setMeals(prev => prev.filter(meal => meal.id !== mealId && meal.clientId !== mealId));
    };

    if (serverMealId) {
      try {
        await MealsAPI.deleteMeal(serverMealId);
        await refreshMeals(currentMealDate);
        if (currentMealDate === getTodayDateString()) {
          await refreshSmartInsightsAndMessages();
        }
        return;
      } catch (error) {
        console.warn('在线删除失败，写入离线删除队列:', error);
        await persistOfflineDelete();
        return;
      }
    }

    await persistOfflineDelete();
  }, [currentMealDate, currentUserId, meals, refreshMeals, refreshSmartInsightsAndMessages]);

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
    await refreshSmartInsightsAndMessages();
  }, [refreshDailyTargets, refreshSmartInsightsAndMessages]);

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
    currentMealDate,
    appMessages,
    dailyTargets,
    setMedicalConditions,
    loadUserData,
    enterGuestMode,
    exitGuestMode,
    logout,
    markAllMessagesRead,
    addMeal,
    updateMeal,
    deleteMeal,
    refreshMeals,
    refreshAfterMealChange,
    refreshDailyTargets,
    refreshSmartInsightsAndMessages,
    updateProfile,
    updateNickname,
    clearUserContent,
  };
}
