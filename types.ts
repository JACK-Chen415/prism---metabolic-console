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
  HEALTH_METRICS = 'HEALTH_METRICS',
  REPORTS = 'REPORTS',
  BILLING = 'BILLING',
  ADMIN = 'ADMIN'
}

export type ComplianceDocumentKey =
  | 'terms'
  | 'privacy'
  | 'ai_use'
  | 'health_disclaimer'
  | 'data_rights';

export interface ComplianceDocumentSection {
  heading: string;
  body?: string;
  bullets?: string[];
}

export interface ComplianceDocument {
  key: ComplianceDocumentKey;
  title: string;
  shortTitle: string;
  subtitle: string;
  sections: ComplianceDocumentSection[];
}

export interface DataExportSection<T = unknown> {
  data?: T;
  error?: string;
}

export interface UserDataExportManifest {
  request_id: string;
  export_version: string;
  generated_at: string;
  section_count: number;
  section_keys: string[];
  medical_disclaimer: string;
}

export interface UserDataExportBundle {
  export_version: string;
  generated_at: string;
  medical_disclaimer: string;
  request_id?: string;
  export_manifest?: UserDataExportManifest;
  profile: DataExportSection;
  daily_targets: DataExportSection;
  meals: DataExportSection;
  conditions: DataExportSection;
  messages: DataExportSection;
  insights: DataExportSection;
  chat_sessions: DataExportSection;
  ai_feedback?: DataExportSection;
  health_metrics?: DataExportSection;
}

export interface DataRightsRequestResponse {
  success?: boolean;
  status?: string;
  message?: string;
  request_id?: string;
}

export interface DeviceSessionItem {
  session_id: string;
  device_label?: string | null;
  is_current: boolean;
  is_revoked: boolean;
  expires_at: string;
  created_at: string;
  last_seen_at: string;
  revoked_at?: string | null;
  revoke_reason?: string | null;
}

export type PlanTier = 'FREE' | 'PRO' | 'COACH';
export type UserRole = 'USER' | 'ADMIN' | 'COACH';
export type SubscriptionStatus = 'inactive' | 'active' | 'canceled';
export type BillingProviderKind = 'mock' | 'payment';
export type BillingProviderStatus = 'active' | 'mock' | 'planned' | 'disabled';
export type BillingEnforcementScope = 'observe_only' | 'feature_entitlement_gate' | string;

export interface EntitlementSnapshot {
  provider: string;
  plan: PlanTier;
  billing_plan: PlanTier;
  status: SubscriptionStatus;
  enforce_limits: boolean;
  enforcement_scope: BillingEnforcementScope;
  features: Record<string, boolean>;
  limits: Record<string, string | number | boolean | null>;
  upgrade_reasons: string[];
  notes: string[];
}

export interface PlanCatalogItem {
  plan: PlanTier;
  title: string;
  subtitle: string;
  monthly_price_cents: number;
  recommended: boolean;
  features: Record<string, boolean>;
  limits: Record<string, string | number | boolean | null>;
  upgrade_reasons: string[];
}

export interface BillingProviderItem {
  provider: string;
  display_name: string;
  kind: BillingProviderKind;
  status: BillingProviderStatus;
  description: string;
  supports_checkout: boolean;
  supports_cancel: boolean;
  supports_webhook: boolean;
  supports_refund: boolean;
  requires_secret: boolean;
  is_configured: boolean;
}

export interface CheckoutSession {
  provider: string;
  plan: PlanTier;
  checkout_id: string;
  checkout_url: string;
  status: string;
  message: string;
}

export interface SubscriptionLifecycleResponse {
  provider: string;
  plan: PlanTier;
  status: SubscriptionStatus;
  message: string;
  entitlement: EntitlementSnapshot;
}

export interface BillingUsageItem {
  key: string;
  label: string;
  current: number;
  limit?: number | null;
  remaining?: number | null;
  usage_ratio?: number | null;
  period: 'day' | 'month' | string;
  period_start: string;
  period_end: string;
  enforce_limits: boolean;
  status: 'ok' | 'near_limit' | 'blocked' | 'over_soft_limit' | 'unmetered' | string;
}

export interface BillingUsageSnapshot {
  generated_at: string;
  provider: string;
  plan: PlanTier;
  billing_plan: PlanTier;
  subscription_status: SubscriptionStatus;
  enforce_limits: boolean;
  enforcement_scope: BillingEnforcementScope;
  usage: BillingUsageItem[];
  notes: string[];
}

export interface AdminActivationDailyMetric {
  date: string;
  meals: number;
  meal_users: number;
  chat_sessions: number;
  assistant_messages: number;
  feedback: number;
  security_events: number;
  health_metrics: number;
}

export interface AdminActivationMetricsSummary {
  generated_at: string;
  window_days: number;
  total_users: number;
  active_users: number;
  verified_users: number;
  new_users: number;
  paid_active_users: number;
  meal_users: number;
  meal_count: number;
  photo_meal_count: number;
  ai_quick_log_count: number;
  chat_users: number;
  chat_session_count: number;
  assistant_message_count: number;
  feedback_count: number;
  open_feedback_count: number;
  unsafe_open_feedback_count: number;
  health_metric_users: number;
  health_metric_count: number;
  security_event_count: number;
  auth_lockout_count: number;
  refresh_reuse_count: number;
  admin_denied_count: number;
  daily_activity: AdminActivationDailyMetric[];
  notes: string[];
}

export interface AdminCommercializationUsagePressureItem {
  key: string;
  label: string;
  period: 'day' | 'month' | string;
  total_usage: number;
  usage_users: number;
  near_limit_users: number;
  over_limit_users: number;
}

export interface AdminCommercializationSummary {
  generated_at: string;
  window_days: number;
  billing_provider: string;
  total_users: number;
  active_paid_users: number;
  canceled_paid_users: number;
  plan_counts: Record<string, number>;
  status_counts: Record<string, number>;
  checkout_event_count: number;
  cancel_event_count: number;
  usage_snapshot_count: number;
  usage_pressure: AdminCommercializationUsagePressureItem[];
  event_type_counts: Record<string, number>;
  event_status_counts: Record<string, number>;
  notes: string[];
}

export interface SecurityAuditItem {
  id: number;
  user_id?: number | null;
  event_type: string;
  event_status: string;
  route_name?: string | null;
  actor_hash?: string | null;
  ip_hash?: string | null;
  session_id?: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
}

export interface KnowledgeAuditItem {
  id: number;
  user_id?: number | null;
  route_name: string;
  query_excerpt_hash?: string | null;
  origin: string;
  fallback_status: string;
  matched_disease_codes: string[];
  matched_food_codes: string[];
  unmapped_conditions?: string[];
  local_decision_level?: string | null;
  called_cloud: boolean;
  cloud_call_reason?: string | null;
  cloud_blocked_reason?: string | null;
  created_at: string;
}

export type FeedbackStatus = 'open' | 'reviewed' | 'closed';

export interface AdminFeedbackItem {
  id: number;
  user_id: number;
  session_id?: number | null;
  message_id?: number | null;
  app_message_id?: number | null;
  feedback_type: AIFeedbackType;
  rating?: number | null;
  tags: string[];
  status: FeedbackStatus;
  has_correction: boolean;
  correction_text_hash?: string | null;
  metadata_json?: Record<string, unknown> | null;
  metadata_keys: string[];
  created_at: string;
  reviewed_at?: string | null;
}

export interface AdminKnowledgeBacklogItem {
  source: 'feedback' | 'knowledge_audit' | string;
  id: number;
  user_id?: number | null;
  feedback_type?: AIFeedbackType | string | null;
  status?: FeedbackStatus | string | null;
  route_name?: string | null;
  tags: string[];
  metadata_keys: string[];
  has_correction: boolean;
  correction_text_hash?: string | null;
  query_excerpt_hash?: string | null;
  origin?: string | null;
  fallback_status?: string | null;
  matched_disease_codes: string[];
  matched_food_codes: string[];
  unmapped_condition_hashes: string[];
  called_cloud?: boolean | null;
  cloud_call_reason_code?: string | null;
  cloud_blocked_reason_code?: string | null;
  created_at: string;
}

export interface AdminKnowledgeBacklogSummary {
  generated_at: string;
  window_limit: number;
  feedback_followup_count: number;
  feedback_open_count: number;
  knowledge_audit_gap_count: number;
  has_correction_count: number;
  feedback_type_counts: Record<string, number>;
  feedback_status_counts: Record<string, number>;
  tag_counts: Record<string, number>;
  correction_hash_counts: Record<string, number>;
  fallback_status_counts: Record<string, number>;
  cloud_call_reason_counts: Record<string, number>;
  cloud_blocked_reason_counts: Record<string, number>;
  matched_disease_counts: Record<string, number>;
  matched_food_counts: Record<string, number>;
  unmapped_condition_counts: Record<string, number>;
  food_nutrition_source_counts: Record<string, number>;
  food_nutrition_quality_counts: Record<string, number>;
  food_nutrition_review_status_counts: Record<string, number>;
  food_nutrition_unreviewed_count: number;
  recent_items: AdminKnowledgeBacklogItem[];
  notes: string[];
}

export interface AIFeedbackItem {
  id: number;
  session_id?: number | null;
  message_id?: number | null;
  app_message_id?: number | null;
  feedback_type: AIFeedbackType;
  rating?: number | null;
  tags: string[];
  status: FeedbackStatus;
  has_correction: boolean;
  created_at: string;
}

export interface InsightFeedbackPayload {
  feedback_type: AIFeedbackType;
  rating?: number;
  tags?: string[];
  correction_text?: string;
  metadata?: Record<string, unknown>;
}

export interface AdminUserItem {
  id: number;
  phone_hash?: string | null;
  nickname?: string | null;
  role: UserRole;
  subscription_plan: PlanTier;
  subscription_status: SubscriptionStatus;
  subscription_updated_at?: string | null;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  updated_at: string;
  last_login_at?: string | null;
}

export interface MetabolicReportNutrients {
  calories: number;
  sodium: number;
  purine: number;
  protein: number;
  carbs: number;
  fat: number;
  fiber: number;
}

export interface MetabolicReportDailyTrend extends MetabolicReportNutrients {
  date: string;
  meal_count: number;
}

export interface MetabolicReportTargets {
  calories?: number | null;
  recommended_calorie_target?: number | null;
  sodium?: number | null;
  purine?: number | null;
}

export interface MetabolicReportInsight {
  type?: string | null;
  title?: string | null;
  content?: string | null;
  attribution?: string | null;
  is_read?: boolean | null;
  created_at?: string | null;
}

export interface MetabolicReport {
  report_type: 'weekly' | 'monthly';
  start_date: string;
  end_date: string;
  generated_at: string;
  medical_disclaimer: string;
  summary: {
    day_count: number;
    logged_days: number;
    meal_count: number;
    totals: MetabolicReportNutrients;
    averages_per_day: MetabolicReportNutrients;
    targets: MetabolicReportTargets;
    risk_summary: string[];
    latest_insights: MetabolicReportInsight[];
  };
  daily_trends: MetabolicReportDailyTrend[];
  csv_endpoint: string;
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
  height: number;
  weight: number;
}

export interface CalorieRange {
  min: number;
  max: number;
}

export interface DailyTargets {
  calories: number;
  sodium: number;
  purine: number;
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

export type AIFeedbackType =
  | 'helpful'
  | 'not_helpful'
  | 'unsafe'
  | 'correction'
  | 'recognition_correction'
  | 'knowledge_gap';

export type HealthMetricType =
  | 'weight'
  | 'body_fat'
  | 'blood_pressure'
  | 'blood_glucose'
  | 'uric_acid'
  | 'blood_lipid'
  | 'waist';

export type HealthMetricProviderKind = 'manual' | 'device';
export type HealthMetricProviderStatus = 'available' | 'mock' | 'planned';

export interface HealthMetricProvider {
  provider: string;
  display_name: string;
  kind: HealthMetricProviderKind;
  status: HealthMetricProviderStatus;
  description: string;
  supports_import: boolean;
  supports_realtime: boolean;
  supports_history: boolean;
}

export interface AdminAITelemetrySummary {
  window_limit: number;
  sampled_messages: number;
  telemetry_sample_count: number;
  cloud_call_count: number;
  local_direct_count: number;
  error_count: number;
  avg_chat_total_ms?: number | null;
  avg_doubao_total_ms?: number | null;
  p95_chat_total_ms?: number | null;
  estimated_cost_usd?: number | null;
  cost_status: string;
  origin_counts: Record<string, number>;
  fallback_status_counts: Record<string, number>;
  recent_error_types: string[];
}

export interface AdminReadinessGateItem {
  key: string;
  label: string;
  status: 'pass' | 'warn' | 'block';
  count: number;
  warn_threshold: number;
  block_threshold: number;
  message: string;
}

export interface AdminReleaseReadinessSummary {
  status: 'green' | 'yellow' | 'red';
  generated_at: string;
  window_limit: number;
  blocker_count: number;
  warning_count: number;
  gate_items: AdminReadinessGateItem[];
  action_items: AdminReadinessGateItem[];
  signals: Record<string, number>;
  notes: string[];
}

export interface HealthMetric {
  id: number;
  metric_type: HealthMetricType;
  value: number;
  value_secondary?: number | null;
  unit: string;
  source: string;
  provider?: string | null;
  metadata?: Record<string, unknown> | null;
  recorded_at: string;
  created_at: string;
  updated_at: string;
}

export interface HealthMetricCreateInput {
  metric_type: HealthMetricType;
  value: number;
  value_secondary?: number | null;
  unit?: string;
  recorded_at?: string;
  source?: string;
  provider?: string | null;
  metadata?: Record<string, unknown> | null;
}

export type FoodCategory = 'STAPLE' | 'MEAT' | 'VEG' | 'DRINK' | 'SNACK';
export type MealSource = 'manual' | 'voice' | 'photo' | 'ai_quick_log';
export type MealSyncStatus = 'PENDING' | 'SYNCED' | 'CONFLICT' | 'FAILED';

export interface Meal {
  id: string;
  clientId?: string;
  recordDate?: string;
  name: string;
  portion: string;
  calories: number;
  sodium: number;
  purine: number;
  protein?: number;
  carbs?: number;
  fat?: number;
  fiber?: number;
  type: 'BREAKFAST' | 'LUNCH' | 'DINNER' | 'SNACK';
  category: FoodCategory;
  note?: string;
  source?: MealSource;
  sourceDetail?: string;
  confidence?: number;
  estimatedFields?: string[];
  ruleWarnings?: string[];
  recognitionMeta?: Record<string, unknown>;
  pendingDelete?: boolean;
  syncStatus?: MealSyncStatus;
  lastSyncError?: string;
  retryCount?: number;
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

export type KnowledgeOrigin = 'LOCAL_RULE' | 'LOCAL_KNOWLEDGE' | 'CLOUD_SUPPLEMENT' | 'MIXED';

export type KnowledgeFallbackStatus =
  | 'LOCAL_COMPLETE'
  | 'LOCAL_PARTIAL_ALLOW_CLOUD'
  | 'LOCAL_BLOCKED_NO_CLOUD'
  | 'NO_LOCAL_MATCH_ALLOW_CLOUD';

export interface ChatStreamEvent {
  event: 'meta' | 'status' | 'delta' | 'done' | 'error' | string;
  data: {
    request_id?: string;
    session_id?: number;
    fallback?: boolean;
    interrupted?: boolean;
    stage?: string;
    message?: string;
    content?: string;
    message_id?: number;
    attachments?: Record<string, unknown>;
    origin?: KnowledgeOrigin;
    fallback_status?: KnowledgeFallbackStatus;
  };
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
  seasonings?: string[];
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
  origin: KnowledgeOrigin;
  fallback_status: KnowledgeFallbackStatus;
  conflict_note?: string | null;
  caution_note?: string | null;
}

export type IntakeParseStatus = 'ready' | 'needs_clarification' | 'refused';

export interface IntakeDraftSession {
  source: Extract<MealSource, 'voice' | 'photo' | 'ai_quick_log'>;
  status?: IntakeParseStatus;
  raw_input_text?: string | null;
  raw_summary?: string | null;
  record_date: string;
  meal_time_hint?: string | null;
  candidates: IntakeCandidate[];
  summary_warning?: string | null;
  missing_fields?: string[];
  follow_up_prompt?: string | null;
  refusal_reason?: string | null;
}

export interface VoiceAutoLogRequest {
  transcript: string;
  meal_time_hint?: string | null;
  record_date?: string | null;
  auto_confirm?: boolean;
}

export interface IntakeConfirmFailure {
  draft_id: string;
  food_name: string;
  reason: string;
}

export interface IntakeConfirmResponse {
  meals: unknown[];
  meal_ids: number[];
  warning_summary: string[];
  failed_items: IntakeConfirmFailure[];
  should_refresh_log: boolean;
  should_refresh_home: boolean;
}

export type VoiceAutoLogResponse = IntakeConfirmResponse;
