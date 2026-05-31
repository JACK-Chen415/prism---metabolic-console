import React, { useEffect, useMemo, useState } from 'react';
import { HealthMetric, HealthMetricProvider, HealthMetricType, View } from '../../types';
import { HealthMetricsAPI, TokenManager } from '../../services/api';

interface HealthMetricsViewProps {
  onViewChange: (view: View) => void;
}

const METRIC_CONFIG: Record<HealthMetricType, {
  label: string;
  icon: string;
  unit: string;
  secondaryLabel?: string;
  valueLabel: string;
}> = {
  weight: { label: '体重', icon: 'monitor_weight', unit: 'kg', valueLabel: '数值' },
  body_fat: { label: '体脂率', icon: 'percent', unit: '%', valueLabel: '数值' },
  blood_pressure: { label: '血压', icon: 'monitor_heart', unit: 'mmHg', valueLabel: '收缩压', secondaryLabel: '舒张压' },
  blood_glucose: { label: '血糖', icon: 'bloodtype', unit: 'mmol/L', valueLabel: '数值' },
  uric_acid: { label: '尿酸', icon: 'science', unit: 'umol/L', valueLabel: '数值' },
  blood_lipid: { label: '血脂', icon: 'water_drop', unit: 'mmol/L', valueLabel: '总胆固醇' },
  waist: { label: '腰围', icon: 'straighten', unit: 'cm', valueLabel: '数值' },
};

const METRIC_TYPES = Object.keys(METRIC_CONFIG) as HealthMetricType[];

function toLocalInputValue(date = new Date()): string {
  const offsetMs = date.getTimezoneOffset() * 60 * 1000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function formatRecordedAt(value: string): string {
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatMetricValue(metric: HealthMetric): string {
  const primary = Number(metric.value).toLocaleString('zh-CN', { maximumFractionDigits: 1 });
  if (metric.metric_type === 'blood_pressure' && metric.value_secondary != null) {
    return `${primary}/${Number(metric.value_secondary).toLocaleString('zh-CN', { maximumFractionDigits: 0 })} ${metric.unit}`;
  }
  return `${primary} ${metric.unit}`;
}

const HealthMetricsView: React.FC<HealthMetricsViewProps> = ({ onViewChange }) => {
  const [records, setRecords] = useState<HealthMetric[]>([]);
  const [selectedType, setSelectedType] = useState<HealthMetricType>('weight');
  const [value, setValue] = useState('');
  const [valueSecondary, setValueSecondary] = useState('');
  const [unit, setUnit] = useState(METRIC_CONFIG.weight.unit);
  const [recordedAt, setRecordedAt] = useState(toLocalInputValue());
  const [providers, setProviders] = useState<HealthMetricProvider[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const selectedConfig = METRIC_CONFIG[selectedType];

  const latestByType = useMemo(() => {
    const latest = new Map<HealthMetricType, HealthMetric>();
    records.forEach(record => {
      if (!latest.has(record.metric_type)) latest.set(record.metric_type, record);
    });
    return latest;
  }, [records]);

  const loadMetrics = async () => {
    if (!TokenManager.isAuthenticated()) return;
    setIsLoading(true);
    setNotice(null);
    try {
      const [data, providerData] = await Promise.all([
        HealthMetricsAPI.list(undefined, 100),
        HealthMetricsAPI.listProviders(),
      ]);
      setRecords(data);
      setProviders(providerData);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '健康指标读取失败。');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadMetrics();
  }, []);

  useEffect(() => {
    setUnit(METRIC_CONFIG[selectedType].unit);
    setValue('');
    setValueSecondary('');
  }, [selectedType]);

  const handleSave = async () => {
    const numericValue = Number(value);
    const numericSecondary = valueSecondary ? Number(valueSecondary) : null;
    if (!Number.isFinite(numericValue) || numericValue < 0) {
      setNotice('请输入有效数值。');
      return;
    }
    if (selectedType === 'blood_pressure' && (!Number.isFinite(numericSecondary) || numericSecondary === null)) {
      setNotice('请补充舒张压。');
      return;
    }
    const recordedAtDate = recordedAt ? new Date(recordedAt) : new Date();
    if (Number.isNaN(recordedAtDate.getTime())) {
      setNotice('请选择有效时间。');
      return;
    }

    setIsSaving(true);
    setNotice(null);
    try {
      const created = await HealthMetricsAPI.create({
        metric_type: selectedType,
        value: numericValue,
        value_secondary: numericSecondary,
        unit,
        recorded_at: recordedAtDate.toISOString(),
        source: 'manual',
        metadata: { source_detail: 'settings_manual_entry' },
      });
      setRecords(prev => [created, ...prev].sort((a, b) => +new Date(b.recorded_at) - +new Date(a.recorded_at)));
      setValue('');
      setValueSecondary('');
      setRecordedAt(toLocalInputValue());
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '保存失败，请稍后再试。');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (record: HealthMetric) => {
    setDeletingId(record.id);
    setNotice(null);
    try {
      await HealthMetricsAPI.delete(record.id);
      setRecords(prev => prev.filter(item => item.id !== record.id));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '删除失败，请稍后再试。');
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="flex min-h-screen w-full flex-col bg-background-dark pb-24">
      <div className="sticky top-0 z-20 border-b border-white/5 bg-[#0c1416]/95 p-4 backdrop-blur-md">
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={() => onViewChange(View.SETTINGS)}
            className="flex h-9 w-9 items-center justify-center rounded-full text-white transition-colors hover:bg-white/5"
            aria-label="返回"
          >
            <span className="material-symbols-outlined">arrow_back</span>
          </button>
          <div className="text-center">
            <h1 className="font-serif text-lg font-bold tracking-wide text-white">健康指标</h1>
            <p className="mt-1 font-display text-[10px] uppercase tracking-[0.28em] text-primary/50">METRICS</p>
          </div>
          <button
            type="button"
            onClick={() => void loadMetrics()}
            disabled={isLoading}
            className="flex h-9 w-9 items-center justify-center rounded-full text-white transition-colors hover:bg-white/5 disabled:opacity-40"
            aria-label="刷新"
            title="刷新"
          >
            <span className={`material-symbols-outlined text-[20px] ${isLoading ? 'animate-spin' : ''}`}>
              {isLoading ? 'progress_activity' : 'refresh'}
            </span>
          </button>
        </div>
      </div>

      <div className="space-y-5 p-4">
        <section className="grid grid-cols-2 gap-3">
          {METRIC_TYPES.map(type => {
            const metric = latestByType.get(type);
            const config = METRIC_CONFIG[type];
            return (
              <button
                key={type}
                type="button"
                onClick={() => setSelectedType(type)}
                className={`min-h-[88px] rounded-xl border p-3 text-left transition-colors ${selectedType === type
                  ? 'border-primary/35 bg-primary/[0.08]'
                  : 'border-white/10 bg-[#131b1d]/80 hover:bg-white/[0.04]'
                  }`}
              >
                <div className="flex items-center gap-2">
                  <span className={`material-symbols-outlined text-[18px] ${selectedType === type ? 'text-primary' : 'text-slate-400'}`}>{config.icon}</span>
                  <span className="font-serif text-sm font-bold tracking-wide text-white">{config.label}</span>
                </div>
                <div className="mt-2 font-serif text-xs text-slate-400">
                  {metric ? formatMetricValue(metric) : '暂无记录'}
                </div>
              </button>
            );
          })}
        </section>

        <section className="rounded-xl border border-mineral/20 bg-[#131b1d]/80 p-4">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-primary">{selectedConfig.icon}</span>
              <h2 className="font-serif text-base font-bold tracking-wide text-white">{selectedConfig.label}</h2>
            </div>
            <span className="rounded-full border border-white/10 px-2 py-0.5 font-serif text-[10px] font-bold tracking-wide text-slate-400">
              {unit}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="col-span-1">
              <span className="mb-1 block font-serif text-[11px] font-bold tracking-wide text-slate-400">{selectedConfig.valueLabel}</span>
              <input
                type="number"
                inputMode="decimal"
                value={value}
                onChange={(event) => setValue(event.target.value)}
                className="h-11 w-full rounded-lg border border-white/10 bg-white/5 px-3 font-serif text-sm text-white outline-none focus:border-primary/50"
              />
            </label>

            <label className="col-span-1">
              <span className="mb-1 block font-serif text-[11px] font-bold tracking-wide text-slate-400">
                {selectedConfig.secondaryLabel || '单位'}
              </span>
              {selectedConfig.secondaryLabel ? (
                <input
                  type="number"
                  inputMode="decimal"
                  value={valueSecondary}
                  onChange={(event) => setValueSecondary(event.target.value)}
                  className="h-11 w-full rounded-lg border border-white/10 bg-white/5 px-3 font-serif text-sm text-white outline-none focus:border-primary/50"
                />
              ) : (
                <input
                  type="text"
                  value={unit}
                  onChange={(event) => setUnit(event.target.value)}
                  className="h-11 w-full rounded-lg border border-white/10 bg-white/5 px-3 font-serif text-sm text-white outline-none focus:border-primary/50"
                />
              )}
            </label>

            <label className="col-span-2">
              <span className="mb-1 block font-serif text-[11px] font-bold tracking-wide text-slate-400">时间</span>
              <input
                type="datetime-local"
                value={recordedAt}
                onChange={(event) => setRecordedAt(event.target.value)}
                className="h-11 w-full rounded-lg border border-white/10 bg-white/5 px-3 font-serif text-sm text-white outline-none focus:border-primary/50"
              />
            </label>
          </div>

          {notice && (
            <div className="mt-3 rounded-lg border border-ochre/20 bg-ochre/10 px-3 py-2 font-serif text-xs leading-relaxed text-ochre">
              {notice}
            </div>
          )}

          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={isSaving}
            className="mt-4 flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-primary font-serif text-sm font-bold tracking-widest text-background-dark shadow-glow-cyan transition-transform active:scale-[0.99] disabled:opacity-50"
          >
            <span className={`material-symbols-outlined text-[18px] ${isSaving ? 'animate-spin' : ''}`}>
              {isSaving ? 'progress_activity' : 'add'}
            </span>
            保存记录
          </button>
        </section>

        <section className="rounded-xl border border-white/10 bg-[#131b1d]/70">
          <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
            <h2 className="font-serif text-sm font-bold tracking-wide text-white">设备预留</h2>
            <span className="font-serif text-[11px] font-bold tracking-wide text-slate-500">{providers.length}</span>
          </div>
          <div className="divide-y divide-white/5">
            {providers.map(provider => (
              <div key={provider.provider} className="px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-serif text-sm font-bold tracking-wide text-white">{provider.display_name}</span>
                      <span className={`rounded-full border px-2 py-0.5 font-serif text-[10px] font-bold tracking-wide ${provider.status === 'available'
                        ? 'border-emerald-300/20 bg-emerald-500/10 text-emerald-200'
                        : provider.status === 'mock'
                          ? 'border-primary/25 bg-primary/10 text-primary'
                          : 'border-white/10 bg-white/[0.03] text-slate-400'
                        }`}>
                        {provider.status}
                      </span>
                    </div>
                    <p className="mt-1 font-serif text-[11px] leading-relaxed text-slate-400">{provider.description}</p>
                  </div>
                  <span className="rounded-full border border-white/10 bg-white/[0.03] px-2 py-1 font-serif text-[10px] font-bold tracking-wide text-slate-400">
                    {provider.kind}
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-2 font-serif text-[10px] tracking-wide text-slate-500">
                  <span>导入 {provider.supports_import ? '支持' : '未开放'}</span>
                  <span>实时 {provider.supports_realtime ? '支持' : '未开放'}</span>
                  <span>历史 {provider.supports_history ? '支持' : '未开放'}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-xl border border-white/10 bg-[#131b1d]/70">
          <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
            <h2 className="font-serif text-sm font-bold tracking-wide text-white">最近记录</h2>
            <span className="font-serif text-[11px] font-bold tracking-wide text-slate-500">{records.length}</span>
          </div>
          <div className="divide-y divide-white/5">
            {records.length === 0 && (
              <div className="px-4 py-8 text-center font-serif text-xs font-bold tracking-wide text-slate-500">
                暂无记录
              </div>
            )}
            {records.slice(0, 30).map(record => {
              const config = METRIC_CONFIG[record.metric_type];
              return (
                <div key={record.id} className="flex items-center gap-3 px-4 py-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-primary/15 bg-primary/[0.06] text-primary">
                    <span className="material-symbols-outlined text-[19px]">{config.icon}</span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2">
                      <span className="font-serif text-sm font-bold tracking-wide text-white">{config.label}</span>
                      <span className="font-serif text-xs text-slate-400">{formatMetricValue(record)}</span>
                    </div>
                    <div className="mt-0.5 font-serif text-[11px] tracking-wide text-slate-500">
                      {formatRecordedAt(record.recorded_at)} · {record.source === 'manual' ? '手动' : record.source}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleDelete(record)}
                    disabled={deletingId === record.id}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-slate-500 transition-colors hover:bg-red-500/10 hover:text-red-300 disabled:opacity-40"
                    aria-label="删除"
                    title="删除"
                  >
                    <span className={`material-symbols-outlined text-[18px] ${deletingId === record.id ? 'animate-spin' : ''}`}>
                      {deletingId === record.id ? 'progress_activity' : 'delete'}
                    </span>
                  </button>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
};

export default HealthMetricsView;
