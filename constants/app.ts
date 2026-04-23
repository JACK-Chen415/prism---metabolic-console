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

export const DEFAULT_DAILY_TARGETS: DailyTargets = {
  calories: 2000,
  sodium: 2300,
  purine: 600,
};

