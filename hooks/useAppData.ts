import { useCallback, useState } from 'react';
import { AppMessage, ConditionData, DailyTargets, Meal, UserProfile } from '../types';
import { DEFAULT_DAILY_TARGETS, DEFAULT_USER_PROFILE } from '../constants/app';
import { GUEST_APP_MESSAGES, GUEST_MEALS, GUEST_MEDICAL_DATA, GUEST_USER_PROFILE } from '../data/demoData';
import { AuthAPI, ConditionsAPI, MealsAPI, MessagesAPI, TokenManager } from '../services/api';
import { CacheCleanupService, OfflineMealsService, getTodayDateString, syncScheduler } from '../services/offline';
import { clearSensitiveSessionState } from '../services/sessionState';
import { mapCondition, mapMeal, mapMessage, mapProfile } from '../services/mappers/appMappers';

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
    type: item.mealType || 'DINNER',
    category: item.category || 'STAPLE',
    note: item.note || '',
  };
}

export function useAppData() {
  const [isGuest, setIsGuest] = useState(false);
  const [currentUserId, setCurrentUserId] = useState<number | null>(null);
  const [userProfile, setUserProfile] = useState<UserProfile>(DEFAULT_USER_PROFILE);
  const [medicalConditions, setMedicalConditions] = useState<ConditionData[]>([]);
  const [meals, setMeals] = useState<Meal[]>([]);
  const [appMessages, setAppMessages] = useState<AppMessage[]>([]);
  const [dailyTargets, setDailyTargets] = useState<DailyTargets>(DEFAULT_DAILY_TARGETS);

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
        setDailyTargets(targetsRes.value as DailyTargets);
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
        meal_type: meal.type,
        category: meal.category,
        record_date: getTodayDateString(),
        note: meal.note,
      });
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
        mealType: meal.type,
        category: meal.category,
        recordDate: getTodayDateString(),
        note: meal.note,
        aiRecognized: false,
      });
    }
  }, [currentUserId]);

  const updateProfile = useCallback((profile: UserProfile) => {
    setUserProfile(profile);
  }, []);

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
    refreshMeals,
    updateProfile,
    updateNickname,
  };
}
