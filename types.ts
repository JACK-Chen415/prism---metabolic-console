
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
  backendId?: number;
  conditionCode?: string;
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
  id?: number;
  phone?: string;
  nickname?: string;
  avatarUrl?: string;
  gender: 'MALE' | 'FEMALE';
  age: number;
  height: number; // cm
  weight: number; // kg
}

export interface CalorieRange {
  min: number;
  max: number;
}

export interface DailyTargets {
  calories: number; // 推荐摄入热量目标(kcal)，兼容旧字段
  sodium: number;   // mg
  purine: number;   // mg
  bmi?: number | null;
  bmi_category?: 'underweight' | 'normal' | 'overweight' | 'obese' | string | null;
  bmr?: number | null;
  bmr_range?: CalorieRange | null;
  activity_factor?: number;
  estimated_tdee?: number | null;
  recommended_calorie_target?: number;
  target_strategy?: string;
  target_explanation?: string;
  is_estimated?: boolean;
  has_complete_profile?: boolean;
}

export type FoodCategory = 'STAPLE' | 'MEAT' | 'VEG' | 'DRINK' | 'SNACK';
export type MealSource = 'manual' | 'voice' | 'photo' | 'ai_quick_log';

export interface Meal {
  id: string;
  clientId?: string;
  name: string;
  portion: string;
  calories: number;
  sodium: number; // mg
  purine: number; // mg
  protein?: number; // g
  carbs?: number; // g
  fat?: number; // g
  fiber?: number; // g
  type: 'BREAKFAST' | 'LUNCH' | 'DINNER' | 'SNACK';
  category: FoodCategory;
  note?: string; // Added note field
  source?: MealSource;
  sourceDetail?: string;
  confidence?: number;
  estimatedFields?: string[];
  ruleWarnings?: string[];
  recognitionMeta?: Record<string, unknown>;
}

export type MealUpdateInput = Partial<Pick<
  Meal,
  'name' | 'portion' | 'calories' | 'sodium' | 'purine' | 'protein' | 'carbs' | 'fat' | 'fiber' | 'type' | 'category' | 'note'
>>;

export interface AppMessage {
  id: number;
  type: 'WARNING' | 'ADVICE' | 'BRIEF';
  title: string;
  time: string;
  content: string;
  attribution: string;
  isRead: boolean;
}

export interface KnowledgeCitation {
  source_code: string;
  source_title: string;
  issuing_body: string;
  source_year: number;
  source_version?: string | null;
  source_tier: 'TIER_1' | 'TIER_2' | 'TIER_3' | 'TIER_4';
  source_type: 'GUIDELINE' | 'CONSENSUS' | 'FAQ' | 'EDUCATION';
  localization: 'CN' | 'INTL';
  section_ref?: string | null;
  is_primary: boolean;
}

export interface IntakeCandidate {
  draft_id: string;
  source: Extract<MealSource, 'voice' | 'photo' | 'ai_quick_log'>;
  meal_type: 'BREAKFAST' | 'LUNCH' | 'DINNER' | 'SNACK';
  category: FoodCategory;
  food_name: string;
  food_code?: string | null;
  amount_text: string;
  normalized_amount?: number | null;
  unit?: string | null;
  time_hint?: string | null;
  note?: string | null;
  confidence: number;
  ingredients: string[];
  cooking_method?: string | null;
  calories?: number | null;
  protein?: number | null;
  carbs?: number | null;
  fat?: number | null;
  fiber?: number | null;
  sodium?: number | null;
  sugar?: number | null;
  purine?: number | null;
  allergen_tags: string[];
  risk_tags: string[];
  estimated_fields: string[];
  estimated_notes: string[];
  local_rule_hit: boolean;
  matched_disease_codes: string[];
  recommendation_level?: 'RECOMMEND' | 'MODERATE' | 'LIMIT' | 'AVOID' | 'CONDITIONAL' | 'INSUFFICIENT' | null;
  warnings: string[];
  citations: KnowledgeCitation[];
  origin: 'LOCAL_RULE' | 'LOCAL_KNOWLEDGE' | 'CLOUD_SUPPLEMENT' | 'MIXED';
  fallback_status: 'LOCAL_COMPLETE' | 'LOCAL_PARTIAL_ALLOW_CLOUD' | 'LOCAL_BLOCKED_NO_CLOUD' | 'NO_LOCAL_MATCH_ALLOW_CLOUD';
  conflict_note?: string | null;
  caution_note?: string | null;
}

export interface IntakeDraftSession {
  source: Extract<MealSource, 'voice' | 'photo' | 'ai_quick_log'>;
  raw_input_text?: string | null;
  raw_summary?: string | null;
  record_date: string;
  meal_time_hint?: string | null;
  candidates: IntakeCandidate[];
  summary_warning?: string | null;
}
