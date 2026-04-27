import React from 'react';
import { IntakeCandidate, IntakeDraftSession, FoodCategory } from '../../types';

interface IntakeConfirmationSheetProps {
  session: IntakeDraftSession;
  isSubmitting: boolean;
  error?: string | null;
  onClose: () => void;
  onChangeCandidate: (draftId: string, patch: Partial<IntakeCandidate>) => void;
  onDeleteCandidate: (draftId: string) => void;
  onAddCandidate: () => void;
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

const IntakeConfirmationSheet: React.FC<IntakeConfirmationSheetProps> = ({
  session,
  isSubmitting,
  error,
  onClose,
  onChangeCandidate,
  onDeleteCandidate,
  onAddCandidate,
  onConfirm,
}) => {
  const sourceLabel = session.source === 'voice' ? '语音候选' : session.source === 'photo' ? '拍照候选' : 'AI候选';

  return (
    <div className="fixed inset-0 z-[70] bg-black/80 backdrop-blur-sm p-4 flex items-end justify-center">
      <div className="w-full max-w-md rounded-3xl border border-white/10 bg-[#101719] shadow-2xl overflow-hidden max-h-[92vh] flex flex-col">
        <div className="sticky top-0 z-10 px-5 py-4 border-b border-white/10 bg-[#101719]/95 backdrop-blur flex items-start justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-[0.25em] text-primary/80 font-bold">{sourceLabel}</div>
            <h3 className="text-white text-lg font-serif font-bold tracking-wide mt-1">确认后写入生命日志</h3>
            <p className="text-slate-400 text-xs mt-1 font-serif tracking-wide">
              {session.raw_input_text || session.raw_summary || '请核对候选项后再正式记账。'}
            </p>
          </div>
          <button
            onClick={onClose}
            className="w-9 h-9 rounded-full flex items-center justify-center text-slate-400 hover:text-white hover:bg-white/5 transition-colors"
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
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
            return (
              <div key={candidate.draft_id} className="rounded-2xl border border-white/10 bg-white/[0.03] p-4 space-y-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`inline-flex px-2 py-0.5 rounded-full border text-[10px] font-bold tracking-wide ${levelClass}`}>
                        {candidate.recommendation_level || '待评估'}
                      </span>
                      <span className="inline-flex px-2 py-0.5 rounded-full border border-white/10 bg-white/5 text-[10px] text-slate-300 font-bold tracking-wide">
                        置信度 {Math.round((candidate.confidence || 0) * 100)}%
                      </span>
                      {candidate.local_rule_hit && (
                        <span className="inline-flex px-2 py-0.5 rounded-full border border-primary/20 bg-primary/10 text-[10px] text-primary font-bold tracking-wide">
                          命中本地规则
                        </span>
                      )}
                    </div>
                    <p className="text-slate-400 text-[11px] mt-2 font-serif tracking-wide">
                      {candidate.matched_disease_codes.length > 0 ? `命中病种：${candidate.matched_disease_codes.join('、')}` : '本地病种规则未命中'}
                    </p>
                  </div>
                  <button
                    onClick={() => onDeleteCandidate(candidate.draft_id)}
                    className="w-8 h-8 rounded-full flex items-center justify-center text-slate-500 hover:text-red-300 hover:bg-red-500/10 transition-colors"
                  >
                    <span className="material-symbols-outlined text-[18px]">delete</span>
                  </button>
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

                {(candidate.ingredients.length > 0 || candidate.cooking_method) && (
                  <div className="rounded-xl bg-black/20 border border-white/5 px-3 py-3 space-y-2">
                    {candidate.ingredients.length > 0 && (
                      <p className="text-xs text-slate-300 font-serif tracking-wide">主要食材：{candidate.ingredients.join('、')}</p>
                    )}
                    {candidate.cooking_method && (
                      <p className="text-xs text-slate-300 font-serif tracking-wide">烹调方式：{candidate.cooking_method}</p>
                    )}
                  </div>
                )}

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
                        {field} 估算
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

        <div className="border-t border-white/10 px-4 py-4 bg-[#101719] space-y-3">
          <button
            onClick={onAddCandidate}
            className="w-full h-11 rounded-2xl border border-white/10 bg-white/5 text-slate-200 text-sm font-serif font-bold tracking-wide hover:bg-white/10 transition-colors"
          >
            新增一条候选
          </button>
          <button
            onClick={onConfirm}
            disabled={isSubmitting || session.candidates.length === 0}
            className="w-full h-12 rounded-2xl bg-gradient-to-r from-primary to-[#45b7aa] text-[#081012] text-sm font-serif font-bold tracking-wide disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting ? '正在写入生命日志...' : '确认并写入日志'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default IntakeConfirmationSheet;
