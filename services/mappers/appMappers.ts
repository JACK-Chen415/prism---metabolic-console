import { AppMessage, ConditionData, DailyTargets, Meal, UserProfile } from '../../types';
import { DEFAULT_DAILY_TARGETS, DEFAULT_USER_PROFILE } from '../../constants/app';

type ApiProfile = {
  id?: number;
  phone?: string;
  nickname?: string;
  avatar_url?: string;
  gender?: 'MALE' | 'FEMALE';
  age?: number;
  height?: number;
  weight?: number;
};

export function mapProfile(apiProfile: ApiProfile): UserProfile {
  return {
    ...DEFAULT_USER_PROFILE,
    id: apiProfile.id,
    phone: apiProfile.phone,
    nickname: apiProfile.nickname || apiProfile.phone || '用户',
    avatarUrl: apiProfile.avatar_url,
    gender: apiProfile.gender || DEFAULT_USER_PROFILE.gender,
    age: apiProfile.age || DEFAULT_USER_PROFILE.age,
    height: apiProfile.height || DEFAULT_USER_PROFILE.height,
    weight: apiProfile.weight || DEFAULT_USER_PROFILE.weight,
  };
}

export function mapMeal(apiMeal: any): Meal {
  return {
    id: String(apiMeal.id ?? apiMeal.client_id),
    clientId: apiMeal.client_id || String(apiMeal.id),
    name: apiMeal.name,
    portion: apiMeal.portion || '1份',
    calories: Math.round(apiMeal.calories || 0),
    sodium: Math.round(apiMeal.sodium || 0),
    purine: Math.round(apiMeal.purine || 0),
    protein: apiMeal.protein ?? undefined,
    carbs: apiMeal.carbs ?? undefined,
    fat: apiMeal.fat ?? undefined,
    fiber: apiMeal.fiber ?? undefined,
    type: apiMeal.meal_type || 'DINNER',
    category: apiMeal.category || 'STAPLE',
    note: apiMeal.note || '',
    source: apiMeal.source || 'manual',
    sourceDetail: apiMeal.source_detail || undefined,
    confidence: apiMeal.confidence ?? undefined,
    estimatedFields: Array.isArray(apiMeal.estimated_fields_json) ? apiMeal.estimated_fields_json : [],
    ruleWarnings: Array.isArray(apiMeal.rule_warnings_json) ? apiMeal.rule_warnings_json : [],
    recognitionMeta: apiMeal.recognition_meta_json || undefined,
  };
}

export function mapDailyTargets(apiTargets: any): DailyTargets {
  const recommendedCalories = Math.round(
    apiTargets?.recommended_calorie_target ?? apiTargets?.calories ?? DEFAULT_DAILY_TARGETS.recommended_calorie_target ?? 0
  );

  return {
    ...DEFAULT_DAILY_TARGETS,
    ...apiTargets,
    calories: recommendedCalories,
    recommended_calorie_target: recommendedCalories,
    sodium: Math.round(apiTargets?.sodium ?? DEFAULT_DAILY_TARGETS.sodium),
    purine: Math.round(apiTargets?.purine ?? DEFAULT_DAILY_TARGETS.purine),
    bmi: apiTargets?.bmi ?? null,
    bmr: apiTargets?.bmr ?? null,
    bmr_range: apiTargets?.bmr_range ?? null,
    estimated_tdee: apiTargets?.estimated_tdee ?? null,
  };
}

export function mapCondition(apiCondition: any): ConditionData {
  return {
    id: apiCondition.condition_code || `condition-${apiCondition.id}`,
    backendId: apiCondition.id,
    conditionCode: apiCondition.condition_code || `condition-${apiCondition.id}`,
    title: apiCondition.title,
    icon: apiCondition.icon || 'medical_services',
    status: apiCondition.status || 'MONITORING',
    trend: apiCondition.trend || 'STABLE',
    value: apiCondition.value,
    unit: apiCondition.unit,
    dictum: apiCondition.dictum || '',
    attribution: apiCondition.attribution || '',
    type: apiCondition.condition_type || 'CHRONIC',
  };
}

export function mapMessage(apiMessage: any): AppMessage {
  return {
    id: apiMessage.id,
    type: apiMessage.message_type || 'ADVICE',
    title: apiMessage.title,
    time: apiMessage.created_at
      ? new Date(apiMessage.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
      : '现在',
    content: apiMessage.content,
    attribution: apiMessage.attribution || '',
    isRead: apiMessage.is_read || false,
  };
}
