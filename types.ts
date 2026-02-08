
export enum View {
  SPLASH = 'SPLASH',
  LOGIN = 'LOGIN',
  REGISTER = 'REGISTER',
  FORGOT_PASSWORD = 'FORGOT_PASSWORD',
  HOME = 'HOME',
  LOG = 'LOG',
  CHAT = 'CHAT',
  PROFILE = 'PROFILE',
  CAMERA = 'CAMERA',
  SETTINGS = 'SETTINGS',
  MESSAGES = 'MESSAGES',
  MEDICAL_ARCHIVES = 'MEDICAL_ARCHIVES',
  HEALTH_REPORT_ARCHIVES = 'HEALTH_REPORT_ARCHIVES'
}

export interface MetricData {
  time: string;
  value: number;
}

export type ConditionStatus = 'ACTIVE' | 'MONITORING' | 'STABLE' | 'ALERT';
export type TrendType = 'IMPROVED' | 'WORSENING' | 'STABLE';

export interface ConditionData {
  id: string;
  title: string;
  icon: string;
  status: ConditionStatus;
  trend: TrendType;
  value?: string;
  unit?: string;
  dictum: string;
  attribution: string;
  type: 'CHRONIC' | 'ALLERGY';
}

export interface UserProfile {
  gender: 'MALE' | 'FEMALE';
  age: number;
  height: number; // cm
  weight: number; // kg
}

export interface DailyTargets {
  calories: number; // kcal
  sodium: number;   // mg
  purine: number;   // mg
}

export type FoodCategory = 'STAPLE' | 'MEAT' | 'VEG' | 'DRINK' | 'SNACK';

export interface Meal {
  id: string;
  name: string;
  portion: string;
  calories: number;
  sodium: number; // mg
  purine: number; // mg
  type: 'BREAKFAST' | 'LUNCH' | 'DINNER' | 'SNACK';
  category: FoodCategory;
  note?: string; // Added note field
}

export interface AppMessage {
  id: number;
  type: 'WARNING' | 'ADVICE' | 'BRIEF';
  title: string;
  time: string;
  content: string;
  attribution: string;
  isRead: boolean;
}