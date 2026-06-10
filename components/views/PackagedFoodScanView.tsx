import React, { useMemo, useState } from 'react';
import { ConditionData, PackagedFoodCandidateResponse, PackagedFoodCategory, PackagedFoodLookupResponse, View } from '../../types';
import { KnowledgeAPI } from '../../services/api';
import { PACKAGED_FOOD_DISCLAIMER } from '../../constants/compliance';

interface PackagedFoodScanViewProps {
  onViewChange: (view: View) => void;
  medicalConditions: ConditionData[];
}

type PackagedFoodFormState = {
  productName: string;
  brand: string;
  barcode: string;
  category: PackagedFoodCategory;
  servingSize: string;
  servingSizeG: string;
  caloriesPer100g: string;
  proteinPer100g: string;
  carbsPer100g: string;
  fatPer100g: string;
  fiberPer100g: string;
  sodiumPer100g: string;
  sugarPer100g: string;
  purinePer100g: string;
  ingredients: string;
  allergenTags: string;
  riskTags: string;
};

const DEFAULT_FORM_STATE: PackagedFoodFormState = {
  productName: '',
  brand: '',
  barcode: '',
  category: 'SNACK',
  servingSize: '',
  servingSizeG: '',
  caloriesPer100g: '',
  proteinPer100g: '',
  carbsPer100g: '',
  fatPer100g: '',
  fiberPer100g: '',
  sodiumPer100g: '',
  sugarPer100g: '',
  purinePer100g: '',
  ingredients: '',
  allergenTags: '',
  riskTags: '',
};

const CATEGORY_OPTIONS: Array<{ value: PackagedFoodCategory; label: string }> = [
  { value: 'SNACK', label: '零食' },
  { value: 'STAPLE', label: '主食' },
  { value: 'MEAT', label: '肉蛋' },
  { value: 'VEG', label: '蔬果' },
  { value: 'DRINK', label: '饮品' },
  { value: 'SOY', label: '豆制品' },
  { value: 'DAIRY', label: '乳制品' },
  { value: 'SEAFOOD', label: '海鲜' },
  { value: 'CONDIMENT', label: '调味品' },
  { value: 'BEVERAGE', label: '饮料' },
];

const splitListField = (value: string) => value
  .split(/[，,、；;\n/]+/)
  .map((item) => item.trim())
  .filter(Boolean);

const parseOptionalNumber = (value: string) => {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined;
};

const normalizeBarcode = (value: string) => value.replace(/\D/g, '');

const formatConfidence = (value: number) => `${Math.round(value * 100)}%`;

const formatRecommendation = (candidate: PackagedFoodCandidateResponse) => {
  const level = candidate.local_decision.recommendation_level;
  if (!level) return '未分级';
  return ({
    RECOMMEND: '推荐',
    MODERATE: '适中',
    LIMIT: '限制',
    AVOID: '避免',
    CONDITIONAL: '有条件',
    INSUFFICIENT: '信息不足',
  } as const)[level] || level;
};

const PackagedFoodScanView: React.FC<PackagedFoodScanViewProps> = ({ onViewChange, medicalConditions }) => {
  const [lookupBarcode, setLookupBarcode] = useState('');
  const [lookupState, setLookupState] = useState<{
    isLoading: boolean;
    error: string | null;
    response: PackagedFoodLookupResponse | null;
    selectedCandidateIndex: number;
  }>({
    isLoading: false,
    error: null,
    response: null,
    selectedCandidateIndex: 0,
  });
  const [form, setForm] = useState<PackagedFoodFormState>(DEFAULT_FORM_STATE);
  const [formMessage, setFormMessage] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [isNormalizing, setIsNormalizing] = useState(false);

  const conditionCodes = useMemo(
    () => Array.from(new Set(medicalConditions.map((condition) => condition.conditionCode || condition.id).filter(Boolean) as string[])),
    [medicalConditions],
  );
  const restrictionTerms = useMemo(
    () => medicalConditions.map((condition) => condition.title).filter(Boolean),
    [medicalConditions],
  );
  const activeCandidate = lookupState.response?.candidates[lookupState.selectedCandidateIndex] || null;
  const conditionSummary = conditionCodes.length > 0 ? `${conditionCodes.length} 项条件上下文` : '无条件上下文';
  const restrictionSummary = restrictionTerms.length > 0 ? `${restrictionTerms.length} 条忌口/备注` : '无额外限制';

  const lookupPackagedFood = async () => {
    const barcode = normalizeBarcode(lookupBarcode);
    if (!barcode) {
      setLookupState((prev) => ({ ...prev, error: '请输入条码。' }));
      return;
    }

    setLookupState((prev) => ({ ...prev, isLoading: true, error: null, response: null, selectedCandidateIndex: 0 }));
    try {
      const response = await KnowledgeAPI.lookupPackagedFoodBarcode({
        barcode,
        condition_codes: conditionCodes,
        manual_restrictions: restrictionTerms,
      });
      setLookupState({
        isLoading: false,
        error: response.matched ? null : '未匹配到候选，可切换到手动标签归一化。',
        response,
        selectedCandidateIndex: 0,
      });
      setFormMessage(response.disclaimer);
      setFormError(null);
    } catch (error) {
      setLookupState((prev) => ({
        ...prev,
        isLoading: false,
        response: null,
        selectedCandidateIndex: 0,
        error: error instanceof Error ? error.message : '包装食品查询失败。',
      }));
    }
  };

  const normalizePackagedLabel = async () => {
    if (!form.productName.trim()) {
      setFormError('请输入商品名称。');
      return;
    }

    setIsNormalizing(true);
    setFormError(null);
    setFormMessage(null);
    try {
      const response = await KnowledgeAPI.normalizePackagedFoodLabel({
        product_name: form.productName.trim(),
        brand: form.brand.trim() || undefined,
        barcode: normalizeBarcode(form.barcode) || undefined,
        category: form.category,
        serving_size: form.servingSize.trim() || undefined,
        serving_size_g: parseOptionalNumber(form.servingSizeG),
        calories_per_100g: parseOptionalNumber(form.caloriesPer100g),
        protein_per_100g: parseOptionalNumber(form.proteinPer100g),
        carbs_per_100g: parseOptionalNumber(form.carbsPer100g),
        fat_per_100g: parseOptionalNumber(form.fatPer100g),
        fiber_per_100g: parseOptionalNumber(form.fiberPer100g),
        sodium_per_100g: parseOptionalNumber(form.sodiumPer100g),
        sugar_per_100g: parseOptionalNumber(form.sugarPer100g),
        purine_per_100g: parseOptionalNumber(form.purinePer100g),
        ingredients: splitListField(form.ingredients),
        allergen_tags: splitListField(form.allergenTags),
        risk_tags: splitListField(form.riskTags),
        condition_codes: conditionCodes,
        manual_restrictions: restrictionTerms,
      });

      const synthesizedResponse: PackagedFoodLookupResponse = {
        provider: response.provider,
        provider_status: response.provider_status,
        barcode_last4: response.barcode_last4,
        matched: true,
        candidates: [response],
        disclaimer: response.disclaimer,
      };

      setLookupState({
        isLoading: false,
        error: null,
        response: synthesizedResponse,
        selectedCandidateIndex: 0,
      });
      setFormMessage(response.disclaimer);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : '营养标签归一化失败。');
    } finally {
      setIsNormalizing(false);
    }
  };

  return (
    <div className="flex min-h-full flex-col pb-28 text-white">
      <header className="border-b border-white/8 px-4 pt-5 pb-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.28em] text-cyan-200/70">Packaged Food Scan</p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-white">包装食品扫描</h1>
            <p className="mt-2 max-w-[34ch] text-sm leading-6 text-slate-400">
              条码查询和标签归一化共用同一套知识评估。
            </p>
          </div>
          <button
            type="button"
            onClick={() => onViewChange(View.HOME)}
            className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/[0.03] text-white/80 transition-colors hover:bg-white/[0.06] hover:text-white"
            aria-label="返回首页"
          >
            <span className="material-symbols-outlined text-[20px]">home</span>
          </button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-1.5 text-[11px] font-medium text-slate-200">
            <span className="material-symbols-outlined text-[14px] text-cyan-300">verified</span>
            {conditionSummary}
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-1.5 text-[11px] font-medium text-slate-200">
            <span className="material-symbols-outlined text-[14px] text-violet-300">policy</span>
            {restrictionSummary}
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-1.5 text-[11px] font-medium text-slate-200">
            <span className="material-symbols-outlined text-[14px] text-emerald-300">camera_alt</span>
            可切换相机
          </span>
        </div>
      </header>

      <section className="border-b border-white/8 px-4 py-4">
        <div className="grid gap-3 md:grid-cols-[1fr_auto_auto]">
          <label className="block min-w-0">
            <span className="mb-2 block text-[10px] font-semibold uppercase tracking-[0.24em] text-slate-500">条码</span>
            <input
              value={lookupBarcode}
              onChange={(event) => setLookupBarcode(event.target.value)}
              inputMode="numeric"
              placeholder="例如 6901234567892"
              className="h-11 w-full rounded-2xl border border-white/10 bg-white/[0.03] px-3 text-sm text-white outline-none transition-colors placeholder:text-slate-600 focus:border-cyan-400/40"
            />
          </label>
          <button
            type="button"
            onClick={lookupPackagedFood}
            disabled={lookupState.isLoading}
            className="mt-6 inline-flex h-11 items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-500/15 px-4 text-sm font-medium text-cyan-100 transition-colors hover:bg-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {lookupState.isLoading ? '查询中' : '查条码'}
          </button>
          <button
            type="button"
            onClick={() => onViewChange(View.CAMERA)}
            className="mt-6 inline-flex h-11 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.03] px-4 text-sm font-medium text-slate-200 transition-colors hover:bg-white/[0.06]"
          >
            去相机
          </button>
        </div>

        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={() => onViewChange(View.LOG)}
            className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-[11px] font-medium text-slate-300 transition-colors hover:bg-white/[0.06] hover:text-white"
          >
            <span className="material-symbols-outlined text-[14px]">edit_note</span>
            打开日志
          </button>
          <button
            type="button"
            onClick={() => setForm(DEFAULT_FORM_STATE)}
            className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-[11px] font-medium text-slate-300 transition-colors hover:bg-white/[0.06] hover:text-white"
          >
            <span className="material-symbols-outlined text-[14px]">restart_alt</span>
            清空表单
          </button>
        </div>

        {lookupState.error && (
          <p className="mt-3 rounded-2xl border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-sm leading-6 text-amber-100">
            {lookupState.error}
          </p>
        )}
      </section>

      <section className="border-b border-white/8 px-4 py-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.28em] text-slate-500">Label Normalize</p>
            <h2 className="mt-1 text-lg font-semibold tracking-tight text-white">手动标签归一化</h2>
          </div>
          <span className="text-[11px] text-slate-500">补全项越多，候选越稳</span>
        </div>

        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <label className="block md:col-span-2">
            <span className="mb-2 block text-[10px] font-semibold uppercase tracking-[0.24em] text-slate-500">商品名称</span>
            <input
              value={form.productName}
              onChange={(event) => setForm((prev) => ({ ...prev, productName: event.target.value }))}
              placeholder="例如 原味酸奶"
              className="h-11 w-full rounded-2xl border border-white/10 bg-white/[0.03] px-3 text-sm text-white outline-none transition-colors placeholder:text-slate-600 focus:border-cyan-400/40"
            />
          </label>
          <label className="block">
            <span className="mb-2 block text-[10px] font-semibold uppercase tracking-[0.24em] text-slate-500">品牌</span>
            <input
              value={form.brand}
              onChange={(event) => setForm((prev) => ({ ...prev, brand: event.target.value }))}
              placeholder="品牌"
              className="h-11 w-full rounded-2xl border border-white/10 bg-white/[0.03] px-3 text-sm text-white outline-none transition-colors placeholder:text-slate-600 focus:border-cyan-400/40"
            />
          </label>
          <label className="block">
            <span className="mb-2 block text-[10px] font-semibold uppercase tracking-[0.24em] text-slate-500">条码</span>
            <input
              value={form.barcode}
              onChange={(event) => setForm((prev) => ({ ...prev, barcode: event.target.value }))}
              placeholder="可选"
              className="h-11 w-full rounded-2xl border border-white/10 bg-white/[0.03] px-3 text-sm text-white outline-none transition-colors placeholder:text-slate-600 focus:border-cyan-400/40"
            />
          </label>
          <label className="block md:col-span-2">
            <span className="mb-2 block text-[10px] font-semibold uppercase tracking-[0.24em] text-slate-500">分类</span>
            <select
              value={form.category}
              onChange={(event) => setForm((prev) => ({ ...prev, category: event.target.value as PackagedFoodCategory }))}
              className="h-11 w-full rounded-2xl border border-white/10 bg-white/[0.03] px-3 text-sm text-white outline-none transition-colors focus:border-cyan-400/40"
            >
              {CATEGORY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          {[
            ['servingSize', '份量'],
            ['servingSizeG', '份量(g)'],
            ['caloriesPer100g', '千卡/100g'],
            ['proteinPer100g', '蛋白质/100g'],
            ['carbsPer100g', '碳水/100g'],
            ['fatPer100g', '脂肪/100g'],
            ['fiberPer100g', '膳食纤维/100g'],
            ['sodiumPer100g', '钠/100g'],
            ['sugarPer100g', '糖/100g'],
            ['purinePer100g', '嘌呤/100g'],
          ].map(([field, label]) => (
            <label key={field} className="block">
              <span className="mb-2 block text-[10px] font-semibold uppercase tracking-[0.24em] text-slate-500">{label}</span>
              <input
                value={form[field as keyof PackagedFoodFormState] as string}
                onChange={(event) => setForm((prev) => ({ ...prev, [field]: event.target.value }))}
                placeholder="可选"
                className="h-11 w-full rounded-2xl border border-white/10 bg-white/[0.03] px-3 text-sm text-white outline-none transition-colors placeholder:text-slate-600 focus:border-cyan-400/40"
              />
            </label>
          ))}
          <label className="block md:col-span-2">
            <span className="mb-2 block text-[10px] font-semibold uppercase tracking-[0.24em] text-slate-500">配料</span>
            <textarea
              value={form.ingredients}
              onChange={(event) => setForm((prev) => ({ ...prev, ingredients: event.target.value }))}
              rows={2}
              className="w-full rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-white outline-none transition-colors placeholder:text-slate-600 focus:border-cyan-400/40"
              placeholder="逗号、顿号或换行分隔"
            />
          </label>
          <label className="block">
            <span className="mb-2 block text-[10px] font-semibold uppercase tracking-[0.24em] text-slate-500">过敏标签</span>
            <textarea
              value={form.allergenTags}
              onChange={(event) => setForm((prev) => ({ ...prev, allergenTags: event.target.value }))}
              rows={2}
              className="w-full rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-white outline-none transition-colors placeholder:text-slate-600 focus:border-cyan-400/40"
            />
          </label>
          <label className="block">
            <span className="mb-2 block text-[10px] font-semibold uppercase tracking-[0.24em] text-slate-500">风险标签</span>
            <textarea
              value={form.riskTags}
              onChange={(event) => setForm((prev) => ({ ...prev, riskTags: event.target.value }))}
              rows={2}
              className="w-full rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-white outline-none transition-colors placeholder:text-slate-600 focus:border-cyan-400/40"
            />
          </label>
        </div>

        {formError && (
          <p className="mt-3 rounded-2xl border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-sm leading-6 text-amber-100">
            {formError}
          </p>
        )}

        <button
          type="button"
          onClick={normalizePackagedLabel}
          disabled={isNormalizing}
          className="mt-3 inline-flex h-11 w-full items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-500/15 px-4 text-sm font-medium text-cyan-100 transition-colors hover:bg-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isNormalizing ? '归一化中' : '归一化并复核'}
        </button>
      </section>

      <section className="px-4 py-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.28em] text-slate-500">Result</p>
            <h2 className="mt-1 text-lg font-semibold tracking-tight text-white">结果面板</h2>
          </div>
          <span className="text-[11px] text-slate-500">
            {lookupState.response?.provider || '等待查询'}
          </span>
        </div>

        {lookupState.response ? (
          <div className="mt-3 space-y-2">
            <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
                    {lookupState.response.matched ? '已匹配候选' : '未匹配到条码'}
                  </p>
                  <h3 className="mt-1 text-base font-semibold text-white">
                    {lookupState.response.candidates[lookupState.selectedCandidateIndex || 0]?.food_name || '无候选'}
                  </h3>
                  <p className="mt-1 text-sm leading-6 text-slate-400">
                    {lookupState.response.disclaimer}
                  </p>
                </div>
                <span className="shrink-0 rounded-xl border border-white/10 bg-white/[0.03] px-2 py-1 text-[10px] font-medium text-slate-300">
                  {lookupState.response.provider_status}
                </span>
              </div>
            </div>

            <div className="space-y-2">
              {lookupState.response.candidates.map((candidate, index) => {
                const isActive = index === lookupState.selectedCandidateIndex;
                return (
                  <button
                    key={`${candidate.food_name}-${index}`}
                    type="button"
                    onClick={() => setLookupState((prev) => ({ ...prev, selectedCandidateIndex: index }))}
                    className={`w-full rounded-2xl border p-4 text-left transition-colors ${
                      isActive ? 'border-cyan-400/30 bg-cyan-500/10' : 'border-white/10 bg-white/[0.03] hover:bg-white/[0.05]'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-white">{candidate.food_name}</p>
                        <p className="mt-1 text-[11px] leading-5 text-slate-400">
                          {candidate.brand || '无品牌'} · {candidate.category} · {formatConfidence(candidate.confidence)}
                        </p>
                      </div>
                      <span className="rounded-xl border border-white/10 bg-white/[0.03] px-2 py-1 text-[10px] font-medium text-slate-300">
                        {formatRecommendation(candidate)}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>

            {activeCandidate && (
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">Active Candidate</p>
                <h3 className="mt-1 text-base font-semibold text-white">{activeCandidate.food_name}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-300">
                  {activeCandidate.local_decision.summary}
                </p>
                <div className="mt-3 grid grid-cols-2 gap-2 text-sm text-slate-300">
                  <div className="rounded-xl border border-white/10 bg-black/15 p-3">
                    <p className="text-[10px] uppercase tracking-[0.22em] text-slate-500">营养来源</p>
                    <p className="mt-1">{activeCandidate.nutrition_source_detail}</p>
                  </div>
                  <div className="rounded-xl border border-white/10 bg-black/15 p-3">
                    <p className="text-[10px] uppercase tracking-[0.22em] text-slate-500">复核状态</p>
                    <p className="mt-1">{activeCandidate.nutrition_review_status}</p>
                  </div>
                  <div className="rounded-xl border border-white/10 bg-black/15 p-3">
                    <p className="text-[10px] uppercase tracking-[0.22em] text-slate-500">份量</p>
                    <p className="mt-1">{activeCandidate.serving_size || '未提供'}</p>
                  </div>
                  <div className="rounded-xl border border-white/10 bg-black/15 p-3">
                    <p className="text-[10px] uppercase tracking-[0.22em] text-slate-500">置信度</p>
                    <p className="mt-1">{formatConfidence(activeCandidate.confidence)}</p>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {activeCandidate.review_required && (
                    <span className="rounded-xl border border-amber-400/20 bg-amber-500/10 px-2.5 py-1 text-[11px] text-amber-100">
                      需复核: {activeCandidate.review_reasons.join('、')}
                    </span>
                  )}
                  {activeCandidate.notes.slice(0, 3).map((note) => (
                    <span key={note} className="rounded-xl border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[11px] text-slate-300">
                      {note}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="mt-3 rounded-2xl border border-dashed border-white/10 bg-white/[0.02] px-3 py-4 text-sm leading-6 text-slate-400">
            先查条码，或用右侧表单生成一条归一化候选。
          </div>
        )}

        {formMessage && (
          <p className="mt-3 rounded-2xl border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-sm leading-6 text-emerald-100">
            {formMessage}
          </p>
        )}
        <p className="mt-3 text-[11px] leading-6 text-slate-500">
          {PACKAGED_FOOD_DISCLAIMER}
        </p>
      </section>
    </div>
  );
};

export default PackagedFoodScanView;
