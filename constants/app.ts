import { DailyTargets, UserProfile } from '../types';

export const APP_NAME = 'Prism Metabolic Console';
export const APP_DISPLAY_NAME = '食鉴';
export const APP_VERSION = import.meta.env.VITE_APP_VERSION || '0.0.0';
export const APP_BUILD = import.meta.env.VITE_APP_BUILD || 'local';

export const SPLASH_DURATION_MS = 1800;
export const VIEW_TRANSITION_MS = 350;

export const DEFAULT_USER_PROFILE: UserProfile = {
  gender: 'MALE',
  age: 28,
  height: 175,
  weight: 70,
};

const DEFAULT_ACTIVITY_FACTOR = 1.375;
const DEFAULT_BMR = Math.round(
  (10 * DEFAULT_USER_PROFILE.weight) +
  (6.25 * DEFAULT_USER_PROFILE.height) -
  (5 * DEFAULT_USER_PROFILE.age) +
  5
);
const DEFAULT_RECOMMENDED_CALORIES = Math.round((DEFAULT_BMR * DEFAULT_ACTIVITY_FACTOR) / 10) * 10;

export const DEFAULT_DAILY_TARGETS: DailyTargets = {
  calories: DEFAULT_RECOMMENDED_CALORIES,
  sodium: 2300,
  purine: 600,
  bmi: Number((DEFAULT_USER_PROFILE.weight / Math.pow(DEFAULT_USER_PROFILE.height / 100, 2)).toFixed(1)),
  bmi_category: 'normal',
  bmr: DEFAULT_BMR,
  bmr_range: {
    min: Math.round(DEFAULT_BMR * 0.95),
    max: Math.round(DEFAULT_BMR * 1.05),
  },
  activity_factor: DEFAULT_ACTIVITY_FACTOR,
  estimated_tdee: Math.round(DEFAULT_BMR * DEFAULT_ACTIVITY_FACTOR),
  recommended_calorie_target: DEFAULT_RECOMMENDED_CALORIES,
  target_strategy: 'maintain',
  target_explanation: '当前 BMI 处于正常范围，建议摄入量接近日常总消耗，用于维持当前体重。',
  is_estimated: true,
  has_complete_profile: true,
};
