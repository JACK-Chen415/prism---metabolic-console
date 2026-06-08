import React from 'react';
import { IntakeCandidate, IntakeCandidateAlternative, IntakeConfirmPreviewResponse, IntakeDraftSession, FoodCategory } from '../../types';
import { AI_INTAKE_CONFIRMATION_NOTICE } from '../../constants/compliance';

interface IntakeConfirmationSheetProps {
  session: IntakeDraftSession;
  isSubmitting: boolean;
  error?: string | null;
  reevaluatingDraftIds?: string[];
  staleEvaluationDraftIds?: string[];
  onClose: () => void;
  onChangeCandidate: (draftId: string, patch: Partial<IntakeCandidate>) => void;
  onDeleteCandidate: (draftId: string) => void;
  onAddCandidate: () => void;
  onReevaluateCandidate?: (draftId: string) => void;
  onSuggestCandidateAlternatives?: (candidate: IntakeCandidate) => void | Promise<void>;
  alternativeSuggestionsByDraftId?: Record<string, IntakeCandidateAlternative[]>;
  alternativeNotesByDraftId?: Record<string, string[]>;
  loadingAlternativeDraftIds?: string[];
  confirmImpactPreview?: IntakeConfirmPreviewResponse | null;
  isLoadingConfirmImpactPreview?: boolean;
  onPreviewConfirmImpact?: () => void | Promise<void>;
  onSubmitCandidateFeedback?: (candidate: IntakeCandidate) => void | Promise<void>;
  submittingFeedbackDraftIds?: string[];
  submittedFeedbackDraftIds?: string[];
  onConfirm: () => void;
}

const MEAL_OPTIONS: Array<{ value: IntakeCandidate['meal_type']; label: string }> = [
  { value: 'BREAKFAST', label: '早餐' },
  { value: 'LUNCH', label: '午餐' },
  { value: 'DINNER', label: '晚餐' },
  { value: 'SNACK', label: '加餐' },
];

const CATEGORY_OPTIONS: Array<{ value: FoodCategory; label: string }> = [
  { value: 'STAPLE', label: '主食' },
  { value: 'MEAT', label: '蛋白' },
  { value: 'VEG', label: '蔬果' },
  { value: 'DRINK', label: '饮品' },
  { value: 'SNACK', label: '零食' },
];

const UNIT_OPTIONS = ['份', '个', '碗', '杯', '根', 'g', 'ml', '包', '瓶', '听', '块'];

const levelClassMap: Record<string, string> = {
  AVOID: 'text-red-300 border-red-400/30 bg-red-500/10',
  LIMIT: 'text-amber-200 border-amber-300/30 bg-amber-500/10',
  CONDITIONAL: 'text-sky-200 border-sky-300/30 bg-sky-500/10',
  MODERATE: 'text-emerald-200 border-emerald-300/30 bg-emerald-500/10',
  RECOMMEND: 'text-emerald-200 border-emerald-300/30 bg-emerald-500/10',
  INSUFFICIENT: 'text-slate-300 border-white/10 bg-white/5',
};

const levelLabelMap: Record<string, string> = {
  AVOID: '避免',
  LIMIT: '限量',
  CONDITIONAL: '条件食用',
  MODERATE: '适量',
  RECOMMEND: '推荐',
  INSUFFICIENT: '信息不足',
};

const fieldLabelMap: Record<string, string> = {
  amount: '份量',
  normalized_amount: '份量',
  calories: '热量',
  sodium: '钠',
  purine: '嘌呤',
  protein: '蛋白质',
  carbs: '碳水',
  fat: '脂肪',
  fiber: '膳食纤维',
  sugar: '糖',
};

const originLabelMap: Record<string, string> = {
  LOCAL_RULE: '本地规则',
  LOCAL_KNOWLEDGE: '本地知识库',
  CLOUD_SUPPLEMENT: '云端补充',
  MIXED: '混合来源',
};

const LOW_CONFIDENCE_THRESHOLD = 0.55;

const sourceLabelMap: Record<IntakeCandidate['source'], string> = {
  voice: '语音',
  photo: '拍照',
  ai_quick_log: 'AI',
};

const getLevelLabel = (level?: IntakeCandidate['recommendation_level']) => {
  if (!level) return '待评估';
  return levelLabelMap[level] || '待评估';
};

const getImpactStatusClass = (status: string) => {
  if (status === 'over_limit') return 'border-red-400/25 bg-red-500/10 text-red-100';
  if (status === 'near_limit') return 'border-amber-300/25 bg-amber-500/10 text-amber-100';
  return 'border-white/10 bg-black/20 text-slate-200';
};

const getImpactStatusLabel = (status: string) => {
  if (status === 'over_limit') return '超过上限';
  if (status === 'near_limit') return '接近上限';
  if (status === 'no_target') return '目标待完善';
  return '可记录';
};

const formatFieldLabel = (field: string) => fieldLabelMap[field] || field;
const getCategoryLabel = (category: FoodCategory) => CATEGORY_OPTIONS.find((option) => option.value === category)?.label || category;

const summarizeFields = (fields: string[], emptyText: string) => {
  if (fields.length === 0) return emptyText;
  const visibleFields = fields.slice(0, 2).map(formatFieldLabel).join('、');
  return fields.length > 2 ? `${visibleFields}等${fields.length}项` : visibleFields;
};

const splitListText = (value: string): string[] => {
  return value
    .split(/[，,、；;\n/]+/)
    .map((item) => item.trim())
    .filter(Boolean);
};

const IntakeConfirmationSheet: React.FC<IntakeConfirmationSheetProps> = ({
  session,
  isSubmitting,
  error,
  reevaluatingDraftIds = [],
  staleEvaluationDraftIds = [],
  onClose,
  onChangeCandidate,
  onDeleteCandidate,
  onAddCandidate,
  onReevaluateCandidate,
  onSuggestCandidateAlternatives,
  alternativeSuggestionsByDraftId = {},
  alternativeNotesByDraftId = {},
  loadingAlternativeDraftIds = [],
  confirmImpactPreview = null,
  isLoadingConfirmImpactPreview = false,
  onPreviewConfirmImpact,
  onSubmitCandidateFeedback,
  submittingFeedbackDraftIds = [],
  submittedFeedbackDraftIds = [],
  onConfirm,
}) => {
  const sourceLabel = session.source === 'voice' ? '语音候选' : session.source === 'photo' ? '拍照候选' : 'AI候选';
  const staleCandidates = session.candidates.filter((candidate) => staleEvaluationDraftIds.includes(candidate.draft_id));
  const staleCandidateNames = staleCandidates
    .map((candidate) => candidate.food_name.trim())
    .filter(Boolean);
  const staleReason = staleEvaluationDraftIds.length > 0
    ? `${staleEvaluationDraftIds.length}条候选修改后尚未重新评估${staleCandidateNames.length > 0 ? `：${staleCandidateNames.slice(0, 3).join('、')}` : ''}${staleCandidateNames.length > 3 ? '等' : ''}`
    : '';
  const blankCandidateCount = session.candidates.filter((candidate) => !candidate.food_name.trim()).length;
  const lowConfidenceCandidates = session.candidates.filter((candidate) => (candidate.confidence || 0) < LOW_CONFIDENCE_THRESHOLD || candidate.review_required);
  const lowConfidencePending = lowConfidenceCandidates.filter((candidate) => !candidate.review_confirmed);
  const confirmBlockedReason = blankCandidateCount > 0
    ? `${blankCandidateCount}条候选缺少食物名称，请补全后重新评估。`
    : staleReason || (lowConfidencePending.length > 0
      ? `${lowConfidencePending.length}条低置信度候选尚未核对，请先确认。`
      : '');

  return (
    <div className="fixed inset-0 z-[90] bg-black/80 backdrop-blur-sm px-4 pt-[calc(16px_+_env(safe-area-inset-top))] pb-[calc(120px_+_env(safe-area-inset-bottom))] flex items-end justify-center">
      <div className="w-full max-w-md max-h-full min-h-0 rounded-3xl border border-white/10 bg-[#101719] shadow-2xl overflow-hidden flex flex-col">
        <div className="shrink-0 px-5 py-4 border-b border-white/10 bg-[#101719]/95 backdrop-blur flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[11px] uppercase tracking-[0.25em] text-primary/80 font-bold">{sourceLabel}</div>
            <h3 className="text-white text-lg font-serif font-bold tracking-wide mt-1">确认后写入生命日志</h3>
            <p className="text-slate-400 text-xs mt-1 font-serif tracking-wide leading-relaxed max-h-10 overflow-y-auto pr-1">
              {session.raw_input_text || session.raw_summary || '请核对候选项后再正式记账。'}
            </p>
          </div>
          <button
            onClick={onClose}
            className="w-9 h-9 rounded-full flex items-center justify-center text-slate-400 hover:text-white hover:bg-white/5 transition-colors shrink-0"
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-4 py-4 space-y-4 scroll-pb-28">
          <div className="rounded-2xl border border-ochre/20 bg-ochre/10 px-4 py-3 text-xs text-ochre/90 leading-relaxed font-serif tracking-wide">
            {AI_INTAKE_CONFIRMATION_NOTICE}
          </div>

          {session.summary_warning && (
            <div className="rounded-2xl border border-amber-300/20 bg-amber-500/10 px-4 py-3 text-xs text-amber-100 leading-relaxed font-serif tracking-wide">
              {session.summary_warning}
            </div>
          )}

          {error && (
            <div className="rounded-2xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-xs text-red-100 leading-relaxed font-serif tracking-wide">
              {error}
            </div>
          )}

          {session.candidates.map((candidate) => {
            const levelClass = levelClassMap[candidate.recommendation_level || 'INSUFFICIENT'] || levelClassMap.INSUFFICIENT;
            const levelLabel = getLevelLabel(candidate.recommendation_level);
            const isReevaluating = reevaluatingDraftIds.includes(candidate.draft_id);
            const isLoadingAlternatives = loadingAlternativeDraftIds.includes(candidate.draft_id);
            const candidateAlternatives = alternativeSuggestionsByDraftId[candidate.draft_id] || [];
            const candidateAlternativeNotes = alternativeNotesByDraftId[candidate.draft_id] || [];
            const isSubmittingFeedback = submittingFeedbackDraftIds.includes(candidate.draft_id);
            const hasSubmittedFeedback = submittedFeedbackDraftIds.includes(candidate.draft_id);
            const isEvaluationStale = staleEvaluationDraftIds.includes(candidate.draft_id);
            const reviewReasons = candidate.review_reasons || [];
            const isLowConfidence = (candidate.confidence || 0) < LOW_CONFIDENCE_THRESHOLD || Boolean(candidate.review_required);
            const isLowConfidenceAcknowledged = Boolean(candidate.review_confirmed);
            const estimateSummary = summarizeFields(candidate.estimated_fields, '无估算项');
            const warningSummary = candidate.warnings.length > 0 ? `${candidate.warnings.length}条提醒` : '无风险提醒';
            const citationSummary = candidate.citations.length > 0 ? `${candidate.citations.length}个来源` : '无规则来源';
            const sourceSummary = `${sourceLabelMap[candidate.source]} · ${originLabelMap[candidate.origin] || '来源待确认'}`;
            return (
              <div key={candidate.draft_id} className="rounded-2xl border border-white/10 bg-white/[0.03] p-3.5 sm:p-4 space-y-3.5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-white text-base font-serif font-bold tracking-wide leading-snug truncate">
                      {candidate.food_name.trim() || '未命名候选'}
                    </p>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`inline-flex px-2 py-0.5 rounded-full border text-[10px] font-bold tracking-wide ${levelClass}`}>
                        {levelLabel}
                      </span>
                      <span className="inline-flex px-2 py-0.5 rounded-full border border-white/10 bg-white/5 text-[10px] text-slate-300 font-bold tracking-wide">
                        置信度 {Math.round((candidate.confidence || 0) * 100)}%
                      </span>
                      {candidate.local_rule_hit && (
                        <span className="inline-flex px-2 py-0.5 rounded-full border border-primary/20 bg-primary/10 text-[10px] text-primary font-bold tracking-wide">
                          命中本地规则
                        </span>
                      )}
                      {isReevaluating && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-primary/20 bg-primary/10 text-[10px] text-primary font-bold tracking-wide">
                          <span className="material-symbols-outlined text-[12px] animate-spin">sync</span>
                          重新评估中
                        </span>
                      )}
                      {isEvaluationStale && !isReevaluating && (
                        <span className="inline-flex px-2 py-0.5 rounded-full border border-amber-300/30 bg-amber-500/10 text-[10px] text-amber-100 font-bold tracking-wide">
                          已修改待评估
                        </span>
                      )}
                    </div>
                    <p className="text-slate-400 text-[11px] mt-1.5 font-serif tracking-wide leading-relaxed">
                      {candidate.matched_disease_codes.length > 0 ? `命中病种：${candidate.matched_disease_codes.join('、')}` : '本地病种规则未命中'}
                    </p>
                  </div>
                  <div className="shrink-0 flex items-center gap-1">
                    {onReevaluateCandidate && (
                      <button
                        onClick={() => onReevaluateCandidate(candidate.draft_id)}
                        disabled={isSubmitting || isReevaluating || !candidate.food_name.trim()}
                        className="h-8 rounded-full border border-white/10 bg-white/5 px-2 inline-flex items-center gap-1 text-[11px] text-slate-300 hover:text-primary hover:border-primary/30 hover:bg-primary/10 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        title="重新评估本地饮食规则"
                      >
                        <span className={`material-symbols-outlined text-[16px] ${isReevaluating ? 'animate-spin' : ''}`}>sync</span>
                        <span>{isReevaluating ? '评估中' : '重新评估'}</span>
                      </button>
                    )}
                    {onSuggestCandidateAlternatives && (
                      <button
                        onClick={() => void onSuggestCandidateAlternatives(candidate)}
                        disabled={isLoadingAlternatives || !candidate.food_name.trim()}
                        className="h-8 rounded-full border border-white/10 bg-white/5 px-2 inline-flex items-center gap-1 text-[11px] text-slate-300 hover:text-emerald-100 hover:border-emerald-300/30 hover:bg-emerald-500/10 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        title="查看本地规则替代建议"
                      >
                        <span className={`material-symbols-outlined text-[16px] ${isLoadingAlternatives ? 'animate-spin' : ''}`}>
                          {isLoadingAlternatives ? 'sync' : 'alt_route'}
                        </span>
                        <span>{isLoadingAlternatives ? '生成中' : '替代建议'}</span>
                      </button>
                    )}
                    {onSubmitCandidateFeedback && (
                      <button
                        onClick={() => void onSubmitCandidateFeedback(candidate)}
                        disabled={isSubmittingFeedback || hasSubmittedFeedback || !candidate.food_name.trim()}
                        className={`h-8 rounded-full border px-2 inline-flex items-center gap-1 text-[11px] transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${hasSubmittedFeedback
                          ? 'border-emerald-300/20 bg-emerald-500/10 text-emerald-200'
                          : 'border-white/10 bg-white/5 text-slate-300 hover:text-amber-100 hover:border-amber-300/30 hover:bg-amber-500/10'
                          }`}
                        title="提交识别纠错反馈"
                      >
                        <span className={`material-symbols-outlined text-[16px] ${isSubmittingFeedback ? 'animate-spin' : ''}`}>
                          {isSubmittingFeedback ? 'sync' : hasSubmittedFeedback ? 'check' : 'flag'}
                        </span>
                        <span>{isSubmittingFeedback ? '提交中' : hasSubmittedFeedback ? '已提交' : '提交纠错'}</span>
                      </button>
                    )}
                    <button
                      onClick={() => onDeleteCandidate(candidate.draft_id)}
                      className="w-8 h-8 rounded-full flex items-center justify-center text-slate-500 hover:text-red-300 hover:bg-red-500/10 transition-colors"
                    >
                      <span className="material-symbols-outlined text-[18px]">delete</span>
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded-xl border border-white/5 bg-black/20 px-3 py-2">
                    <p className="text-[10px] text-slate-500 font-serif font-bold tracking-wide">估算</p>
                    <p className="text-xs text-slate-200 font-serif tracking-wide mt-1 leading-snug">{estimateSummary}</p>
                  </div>
                  <div className={`rounded-xl border px-3 py-2 ${candidate.warnings.length > 0 ? 'border-red-400/20 bg-red-500/10' : 'border-white/5 bg-black/20'}`}>
                    <p className={`text-[10px] font-serif font-bold tracking-wide ${candidate.warnings.length > 0 ? 'text-red-200' : 'text-slate-500'}`}>提醒</p>
                    <p className={`text-xs font-serif tracking-wide mt-1 leading-snug ${candidate.warnings.length > 0 ? 'text-red-100' : 'text-slate-200'}`}>{warningSummary}</p>
                  </div>
                  <div className="rounded-xl border border-white/5 bg-black/20 px-3 py-2">
                    <p className="text-[10px] text-slate-500 font-serif font-bold tracking-wide">来源</p>
                    <p className="text-xs text-slate-200 font-serif tracking-wide mt-1 leading-snug">{sourceSummary}</p>
                  </div>
                  <div className="rounded-xl border border-white/5 bg-black/20 px-3 py-2">
                    <p className="text-[10px] text-slate-500 font-serif font-bold tracking-wide">依据</p>
                    <p className="text-xs text-slate-200 font-serif tracking-wide mt-1 leading-snug">{citationSummary}</p>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="col-span-2">
                    <label className="text-[11px] text-slate-500 font-serif font-bold tracking-wide block mb-1">食物名称</label>
                    <input
                      value={candidate.food_name}
                      onChange={(e) => onChangeCandidate(candidate.draft_id, { food_name: e.target.value })}
                      className="w-full bg-black/20 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm outline-none focus:border-primary/40 transition-colors font-serif tracking-wide"
                    />
                  </div>

                  <div>
                    <label className="text-[11px] text-slate-500 font-serif font-bold tracking-wide block mb-1">餐次</label>
                    <select
                      value={candidate.meal_type}
                      onChange={(e) => onChangeCandidate(candidate.draft_id, { meal_type: e.target.value as IntakeCandidate['meal_type'] })}
                      className="w-full bg-black/20 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm outline-none focus:border-primary/40 transition-colors font-serif tracking-wide"
                    >
                      {MEAL_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="text-[11px] text-slate-500 font-serif font-bold tracking-wide block mb-1">分类</label>
                    <select
                      value={candidate.category}
                      onChange={(e) => onChangeCandidate(candidate.draft_id, { category: e.target.value as FoodCategory })}
                      className="w-full bg-black/20 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm outline-none focus:border-primary/40 transition-colors font-serif tracking-wide"
                    >
                      {CATEGORY_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="text-[11px] text-slate-500 font-serif font-bold tracking-wide block mb-1">份量</label>
                    <input
                      type="number"
                      min="0"
                      step="0.1"
                      value={candidate.normalized_amount ?? ''}
                      onChange={(e) => onChangeCandidate(candidate.draft_id, {
                        normalized_amount: e.target.value ? Number(e.target.value) : null,
                      })}
                      className="w-full bg-black/20 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm outline-none focus:border-primary/40 transition-colors font-serif tracking-wide"
                    />
                  </div>

                  <div>
                    <label className="text-[11px] text-slate-500 font-serif font-bold tracking-wide block mb-1">单位</label>
                    <select
                      value={candidate.unit || '份'}
                      onChange={(e) => onChangeCandidate(candidate.draft_id, { unit: e.target.value })}
                      className="w-full bg-black/20 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm outline-none focus:border-primary/40 transition-colors font-serif tracking-wide"
                    >
                      {UNIT_OPTIONS.map((unit) => (
                        <option key={unit} value={unit}>{unit}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="rounded-xl bg-black/20 border border-white/5 px-3 py-2">
                  <p className="text-[11px] text-slate-500 font-serif font-bold tracking-wide">原始份量描述</p>
                  <p className="text-sm text-slate-200 font-serif tracking-wide mt-1">{candidate.amount_text || '1份'}</p>
                </div>

                {onSubmitCandidateFeedback && (candidate.review_required || candidate.confidence < 0.85 || candidate.warnings.length > 0 || isEvaluationStale) && (
                  <div className="rounded-2xl border border-white/10 bg-black/20 px-3 py-2.5 text-[11px] text-slate-400 font-serif leading-relaxed">
                    若本条候选识别或估算有误，可先编辑并重新评估，再提交纠错反馈；反馈会进入运营复核队列，本次仍需手动确认后才会写入日志。
                  </div>
                )}

                {(candidateAlternatives.length > 0 || candidateAlternativeNotes.length > 0) && (
                  <div className="rounded-2xl border border-emerald-300/20 bg-emerald-500/10 px-3 py-3 space-y-2">
                    <div className="flex items-start gap-2">
                      <span className="material-symbols-outlined mt-0.5 text-[16px] text-emerald-100">alt_route</span>
                      <div className="min-w-0 flex-1">
                        <p className="font-serif text-xs font-bold tracking-wide text-emerald-100">本地规则替代建议</p>
                        <p className="mt-1 font-serif text-[11px] leading-relaxed text-emerald-100/80">
                          建议只作记录辅助，不会自动替换候选；请选择后手动编辑并重新评估。
                        </p>
                      </div>
                    </div>
                    {candidateAlternatives.length > 0 && (
                      <div className="space-y-2">
                        {candidateAlternatives.map((alternative) => (
                          <div key={alternative.food_code} className="rounded-xl border border-emerald-300/15 bg-black/20 px-3 py-2">
                            <div className="flex items-center justify-between gap-2">
                              <p className="min-w-0 truncate font-serif text-xs font-bold tracking-wide text-white">{alternative.food_name}</p>
                              <span className="shrink-0 rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] font-bold tracking-wide text-emerald-100">
                                {getLevelLabel(alternative.recommendation_level)}
                              </span>
                            </div>
                            <p className="mt-1 font-serif text-[11px] leading-relaxed text-slate-300">
                              {getCategoryLabel(alternative.category)} · 钠 {Math.round(alternative.sodium_per_100g || 0)}mg/100g · 嘌呤 {Math.round(alternative.purine_per_100g || 0)}mg/100g
                            </p>
                            <p className="mt-1 line-clamp-2 font-serif text-[11px] leading-relaxed text-slate-400">{alternative.reason}</p>
                          </div>
                        ))}
                      </div>
                    )}
                    {candidateAlternativeNotes.length > 0 && (
                      <p className="font-serif text-[11px] leading-relaxed text-emerald-100/70">
                        {candidateAlternativeNotes.join(' ')}
                      </p>
                    )}
                  </div>
                )}

                {isLowConfidence && (
                  <div className="rounded-2xl border border-amber-300/25 bg-amber-500/10 px-3 py-3">
                    <div className="flex items-start gap-2">
                      <span className="material-symbols-outlined mt-0.5 text-[16px] text-amber-100">visibility</span>
                      <div className="min-w-0 flex-1">
                        <p className="font-serif text-xs font-bold tracking-wide text-amber-100">低置信度候选</p>
                        <p className="mt-1 font-serif text-[11px] leading-relaxed text-amber-100/80">
                          请核对名称、份量、食材、调料和烹调方式后再写入日志{reviewReasons.length > 0 ? `：${reviewReasons.join('、')}` : '。'}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => onChangeCandidate(candidate.draft_id, {
                          review_required: true,
                          review_reasons: reviewReasons.length > 0 ? reviewReasons : ['manual_review_required'],
                          review_confirmed: !isLowConfidenceAcknowledged,
                        })}
                        className={`shrink-0 rounded-full border px-2 py-1 font-serif text-[10px] font-bold tracking-wide transition-colors ${isLowConfidenceAcknowledged
                          ? 'border-emerald-300/25 bg-emerald-500/10 text-emerald-200'
                          : 'border-amber-300/30 bg-black/20 text-amber-100'
                          }`}
                      >
                        {isLowConfidenceAcknowledged ? '已核对' : '确认核对'}
                      </button>
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[11px] text-slate-500 font-serif font-bold tracking-wide block mb-1">主要食材</label>
                    <input
                      value={(candidate.ingredients || []).join('、')}
                      onChange={(e) => onChangeCandidate(candidate.draft_id, { ingredients: splitListText(e.target.value) })}
                      placeholder="如 米饭、鸡蛋"
                      className="w-full bg-black/20 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm outline-none focus:border-primary/40 transition-colors font-serif tracking-wide placeholder:text-slate-600"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] text-slate-500 font-serif font-bold tracking-wide block mb-1">调料</label>
                    <input
                      value={(candidate.seasonings || []).join('、')}
                      onChange={(e) => onChangeCandidate(candidate.draft_id, { seasonings: splitListText(e.target.value) })}
                      placeholder="如 酱油、糖"
                      className="w-full bg-black/20 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm outline-none focus:border-primary/40 transition-colors font-serif tracking-wide placeholder:text-slate-600"
                    />
                  </div>
                  <div className="col-span-2">
                    <label className="text-[11px] text-slate-500 font-serif font-bold tracking-wide block mb-1">烹调方式</label>
                    <input
                      value={candidate.cooking_method || ''}
                      onChange={(e) => onChangeCandidate(candidate.draft_id, { cooking_method: e.target.value.trim() || null })}
                      placeholder="如 清蒸、红烧、油炸"
                      className="w-full bg-black/20 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm outline-none focus:border-primary/40 transition-colors font-serif tracking-wide placeholder:text-slate-600"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-2">
                  <div className="rounded-xl border border-white/5 bg-black/20 px-3 py-2">
                    <p className="text-[10px] text-slate-500 font-serif font-bold tracking-wide">热量</p>
                    <p className="text-sm text-white font-serif font-bold mt-1">{candidate.calories ?? '--'}</p>
                  </div>
                  <div className="rounded-xl border border-white/5 bg-black/20 px-3 py-2">
                    <p className="text-[10px] text-slate-500 font-serif font-bold tracking-wide">钠</p>
                    <p className="text-sm text-white font-serif font-bold mt-1">{candidate.sodium ?? '--'}</p>
                  </div>
                  <div className="rounded-xl border border-white/5 bg-black/20 px-3 py-2">
                    <p className="text-[10px] text-slate-500 font-serif font-bold tracking-wide">嘌呤</p>
                    <p className="text-sm text-white font-serif font-bold mt-1">{candidate.purine ?? '--'}</p>
                  </div>
                </div>

                {candidate.estimated_fields.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {candidate.estimated_fields.map((field) => (
                      <span key={field} className="inline-flex px-2 py-1 rounded-full border border-white/10 bg-white/5 text-[10px] text-slate-300 font-bold tracking-wide">
                        {formatFieldLabel(field)} 估算
                      </span>
                    ))}
                  </div>
                )}

                {candidate.warnings.length > 0 && (
                  <div className="rounded-2xl border border-red-400/20 bg-red-500/10 px-3 py-3">
                    {candidate.warnings.map((warning) => (
                      <p key={warning} className="text-xs text-red-100 leading-relaxed font-serif tracking-wide">
                        {warning}
                      </p>
                    ))}
                  </div>
                )}

                {candidate.citations.length > 0 && (
                  <div className="rounded-2xl border border-white/10 bg-black/20 px-3 py-3 space-y-1">
                    <p className="text-[11px] text-slate-500 font-serif font-bold tracking-wide">规则来源</p>
                    {candidate.citations.slice(0, 3).map((citation) => (
                      <p key={`${citation.source_code}-${citation.section_ref || 'root'}`} className="text-[11px] text-slate-300 font-serif tracking-wide leading-relaxed">
                        {citation.source_title} {citation.section_ref ? `· ${citation.section_ref}` : ''}
                      </p>
                    ))}
                  </div>
                )}

                <div>
                  <label className="text-[11px] text-slate-500 font-serif font-bold tracking-wide block mb-1">备注</label>
                  <textarea
                    rows={2}
                    value={candidate.note || ''}
                    onChange={(e) => onChangeCandidate(candidate.draft_id, { note: e.target.value })}
                    className="w-full bg-black/20 border border-white/10 rounded-xl px-3 py-2.5 text-white text-sm outline-none focus:border-primary/40 transition-colors font-serif tracking-wide resize-none"
                  />
                </div>
              </div>
            );
          })}

          {session.candidates.length === 0 && (
            <div className="rounded-2xl border border-dashed border-white/10 px-4 py-8 text-center text-slate-500 text-sm font-serif tracking-wide">
              暂无候选项，可新增一条手动确认。
            </div>
          )}
        </div>

        <div className="shrink-0 border-t border-white/10 px-4 py-4 bg-[#101719] space-y-3 shadow-[0_-12px_24px_rgba(0,0,0,0.18)]">
          {confirmImpactPreview && (
            <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-3 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <p className="font-serif text-xs font-bold tracking-wide text-white">确认前影响预览</p>
                <span className="font-serif text-[10px] text-slate-500">{confirmImpactPreview.record_date}</span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {confirmImpactPreview.metrics.map((metric) => (
                  <div key={metric.key} className={`rounded-xl border px-2 py-2 ${getImpactStatusClass(metric.status)}`}>
                    <p className="font-serif text-[10px] font-bold tracking-wide">{metric.label}</p>
                    <p className="mt-1 font-serif text-sm font-bold tracking-wide">{Math.round(metric.projected)}{metric.unit}</p>
                    <p className="mt-1 font-serif text-[10px] leading-snug opacity-80">
                      +{Math.round(metric.pending)} · {metric.target ? `目标${Math.round(metric.target)}` : '目标待完善'}
                    </p>
                    <p className="mt-1 font-serif text-[10px] font-bold tracking-wide opacity-90">{getImpactStatusLabel(metric.status)}</p>
                  </div>
                ))}
              </div>
              <p className="font-serif text-[11px] leading-relaxed text-slate-400">
                {confirmImpactPreview.notes.join(' ')}
              </p>
            </div>
          )}
          {confirmBlockedReason && (
            <div className="rounded-2xl border border-amber-300/25 bg-amber-500/10 px-3 py-2.5 text-xs text-amber-100 leading-relaxed font-serif tracking-wide">
              <div className="flex items-start gap-2">
                <span className="material-symbols-outlined text-[16px] mt-0.5">info</span>
                <span>暂不能确认。{confirmBlockedReason}{blankCandidateCount === 0 && staleReason ? '，请先点击对应候选的“重新评估”。' : ''}</span>
              </div>
            </div>
          )}
          {onPreviewConfirmImpact && (
            <button
              type="button"
              onClick={() => void onPreviewConfirmImpact()}
              disabled={isLoadingConfirmImpactPreview || session.candidates.length === 0}
              className="w-full h-11 rounded-2xl border border-primary/25 bg-primary/10 text-primary text-sm font-serif font-bold tracking-wide hover:bg-primary/15 transition-colors disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center justify-center gap-2"
            >
              <span className={`material-symbols-outlined text-[17px] ${isLoadingConfirmImpactPreview ? 'animate-spin' : ''}`}>
                {isLoadingConfirmImpactPreview ? 'sync' : 'monitoring'}
              </span>
              <span>{isLoadingConfirmImpactPreview ? '正在预览...' : '影响预览'}</span>
            </button>
          )}
          <button
            onClick={onAddCandidate}
            className="w-full h-11 rounded-2xl border border-white/10 bg-white/5 text-slate-200 text-sm font-serif font-bold tracking-wide hover:bg-white/10 transition-colors"
          >
            新增一条候选
          </button>
          <button
            onClick={onConfirm}
            disabled={isSubmitting || session.candidates.length === 0 || staleEvaluationDraftIds.length > 0 || blankCandidateCount > 0 || lowConfidencePending.length > 0}
            className="w-full h-12 rounded-2xl bg-gradient-to-r from-primary to-[#45b7aa] text-[#081012] text-sm font-serif font-bold tracking-wide disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting
              ? '正在写入生命日志...'
              : blankCandidateCount > 0
                ? '请补全食物名称'
              : staleEvaluationDraftIds.length > 0
                ? '请先重新评估候选'
              : lowConfidencePending.length > 0
                ? '请先核对低置信度候选'
                : '确认并写入日志'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default IntakeConfirmationSheet;
