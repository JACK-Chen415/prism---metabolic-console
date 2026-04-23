export type RecommendationSeverity = 'info' | 'caution' | 'block';

export interface RuleCheckContext {
  userId: number;
  conditionCodes: string[];
  allergyCodes: string[];
}

export interface RuleCheckResult {
  severity: RecommendationSeverity;
  message: string;
  source?: string;
}

