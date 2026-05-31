import React, { useEffect, useState } from 'react';
import { MetabolicReport, View } from '../../types';
import { ReportsAPI } from '../../services/api';
import { getLocalDateString } from '../../services/date';

interface ReportsViewProps {
  onViewChange: (view: View) => void;
}

type ReportPeriod = 'weekly' | 'monthly';

type ReportFilters = {
  weeklyEndDate: string;
  targetMonth: string;
};

type ReportHistoryEntry = {
  id: string;
  period: ReportPeriod;
  startDate: string;
  endDate: string;
  generatedAt: string;
  weeklyEndDate?: string;
  targetMonth?: string;
};

const REPORT_HISTORY_STORAGE_KEY = 'prism.report.history.v1';

const nutrientLabels = [
  { key: 'calories', label: '热量', unit: 'kcal', icon: 'local_fire_department' },
  { key: 'sodium', label: '钠', unit: 'mg', icon: 'grain' },
  { key: 'purine', label: '嘌呤', unit: 'mg', icon: 'water_drop' },
  { key: 'fiber', label: '纤维', unit: 'g', icon: 'grass' },
] as const;

function downloadBlob(fileName: string, text: string, type: string) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function formatNumber(value: number, maximumFractionDigits = 0): string {
  return Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits });
}

function formatDateTime(value?: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

function defaultFilters(): ReportFilters {
  const today = getLocalDateString();
  return {
    weeklyEndDate: today,
    targetMonth: today.slice(0, 7),
  };
}

function readReportHistory(): ReportHistoryEntry[] {
  try {
    const raw = localStorage.getItem(REPORT_HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.slice(0, 6) : [];
  } catch {
    return [];
  }
}

function writeReportHistory(entries: ReportHistoryEntry[]) {
  localStorage.setItem(REPORT_HISTORY_STORAGE_KEY, JSON.stringify(entries.slice(0, 6)));
}

const ReportsView: React.FC<ReportsViewProps> = ({ onViewChange }) => {
  const [period, setPeriod] = useState<ReportPeriod>('weekly');
  const [weeklyEndDate, setWeeklyEndDate] = useState(() => defaultFilters().weeklyEndDate);
  const [targetMonth, setTargetMonth] = useState(() => defaultFilters().targetMonth);
  const [history, setHistory] = useState<ReportHistoryEntry[]>(() => readReportHistory());
  const [report, setReport] = useState<MetabolicReport | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const rememberReport = (nextReport: MetabolicReport, nextPeriod: ReportPeriod, filters: ReportFilters) => {
    const entry: ReportHistoryEntry = {
      id: `${nextPeriod}:${nextReport.start_date}:${nextReport.end_date}`,
      period: nextPeriod,
      startDate: nextReport.start_date,
      endDate: nextReport.end_date,
      generatedAt: nextReport.generated_at,
      weeklyEndDate: nextPeriod === 'weekly' ? filters.weeklyEndDate : undefined,
      targetMonth: nextPeriod === 'monthly' ? filters.targetMonth : undefined,
    };
    setHistory(prev => {
      const nextHistory = [
        entry,
        ...prev.filter(item => item.id !== entry.id),
      ].slice(0, 6);
      writeReportHistory(nextHistory);
      return nextHistory;
    });
  };

  const loadReport = async (
    nextPeriod: ReportPeriod = period,
    filters: ReportFilters = { weeklyEndDate, targetMonth },
  ) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = nextPeriod === 'weekly'
        ? await ReportsAPI.getWeekly({ endDate: filters.weeklyEndDate })
        : await ReportsAPI.getMonthly({ targetMonth: filters.targetMonth });
      setReport(data);
      rememberReport(data, nextPeriod, filters);
    } catch (err) {
      setError(err instanceof Error ? err.message : '报告加载失败。');
      setReport(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadReport(period, { weeklyEndDate, targetMonth });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDownload = async (format: 'json' | 'csv') => {
    if (!report) return;
    setIsDownloading(true);
    setError(null);
    try {
      const stamp = report.end_date || getLocalDateString();
      const label = period === 'weekly' ? 'weekly' : 'monthly';
      if (format === 'json') {
        downloadBlob(
          `prism-${label}-report-${stamp}.json`,
          JSON.stringify(report, null, 2),
          'application/json;charset=utf-8',
        );
      } else {
        const csv = period === 'weekly'
          ? await ReportsAPI.getWeeklyCsv({ endDate: weeklyEndDate || report.end_date })
          : await ReportsAPI.getMonthlyCsv({ targetMonth: targetMonth || report.start_date.slice(0, 7) });
        downloadBlob(`prism-${label}-report-${stamp}.csv`, csv, 'text/csv;charset=utf-8');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '导出失败，请稍后再试。');
    } finally {
      setIsDownloading(false);
    }
  };

  const handleHistoryClick = (entry: ReportHistoryEntry) => {
    const nextFilters = {
      weeklyEndDate: entry.weeklyEndDate || entry.endDate,
      targetMonth: entry.targetMonth || entry.startDate.slice(0, 7),
    };
    setPeriod(entry.period);
    setWeeklyEndDate(nextFilters.weeklyEndDate);
    setTargetMonth(nextFilters.targetMonth);
    void loadReport(entry.period, nextFilters);
  };

  const handlePeriodChange = (nextPeriod: ReportPeriod) => {
    setPeriod(nextPeriod);
    void loadReport(nextPeriod, {
      weeklyEndDate,
      targetMonth,
    });
  };

  const maxCalories = Math.max(1, ...(report?.daily_trends || []).map(day => day.calories));
  const targetCards = report
    ? [
      {
        key: 'calories',
        label: '热量目标',
        value: report.summary.targets.recommended_calorie_target ?? report.summary.targets.calories,
        unit: 'kcal',
      },
      { key: 'sodium', label: '钠上限', value: report.summary.targets.sodium, unit: 'mg' },
      { key: 'purine', label: '嘌呤上限', value: report.summary.targets.purine, unit: 'mg' },
    ].filter(item => item.value !== null && item.value !== undefined)
    : [];
  const latestInsights = report?.summary.latest_insights || [];

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
            <h1 className="font-serif text-lg font-bold tracking-wide text-white">报告中心</h1>
            <p className="mt-1 font-display text-[10px] uppercase tracking-[0.28em] text-primary/50">REPORTS</p>
          </div>
          <button
            type="button"
            onClick={() => void loadReport(period, { weeklyEndDate, targetMonth })}
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
        <div className="flex rounded-xl border border-white/10 bg-surface-dark p-1">
          {(['weekly', 'monthly'] as ReportPeriod[]).map(item => (
            <button
              key={item}
              type="button"
              onClick={() => handlePeriodChange(item)}
              className={`flex-1 rounded-lg py-2 font-serif text-sm font-bold tracking-wide transition-colors ${period === item
                ? 'bg-primary/10 text-primary'
                : 'text-slate-400 hover:bg-white/5'
                }`}
            >
              {item === 'weekly' ? '7 天周报' : '本月月报'}
            </button>
          ))}
        </div>

        <section className="rounded-2xl border border-white/10 bg-[#101719]/80 p-4">
          <div className="grid grid-cols-[1fr_auto] items-end gap-3">
            <label className="block">
              <span className="mb-1 block font-serif text-[11px] font-bold tracking-[0.2em] text-slate-500">
                {period === 'weekly' ? '周报截止日' : '报告月份'}
              </span>
              <input
                type={period === 'weekly' ? 'date' : 'month'}
                value={period === 'weekly' ? weeklyEndDate : targetMonth}
                onChange={(event) => {
                  if (period === 'weekly') {
                    setWeeklyEndDate(event.target.value);
                  } else {
                    setTargetMonth(event.target.value);
                  }
                }}
                className="h-11 w-full rounded-xl border border-white/10 bg-black/20 px-3 font-serif text-sm font-bold tracking-wide text-white outline-none transition-colors focus:border-primary/40"
              />
            </label>
            <button
              type="button"
              onClick={() => void loadReport(period, { weeklyEndDate, targetMonth })}
              disabled={isLoading}
              className="flex h-11 items-center justify-center gap-1 rounded-xl bg-white/[0.06] px-4 font-serif text-sm font-bold tracking-wide text-slate-200 transition-colors hover:bg-white/[0.1] disabled:opacity-50"
            >
              <span className="material-symbols-outlined text-[18px]">auto_graph</span>
              生成
            </button>
          </div>

          {history.length > 0 && (
            <div className="mt-4 border-t border-white/5 pt-3">
              <p className="font-serif text-[10px] font-bold tracking-[0.22em] text-slate-500">最近报告</p>
              <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
                {history.map(item => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => handleHistoryClick(item)}
                    className="shrink-0 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 font-serif text-[11px] font-bold tracking-wide text-slate-300 transition-colors hover:border-primary/30 hover:text-primary"
                  >
                    {item.period === 'weekly' ? '周报' : '月报'} {item.endDate.slice(5)}
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>

        {error && (
          <div className="rounded-xl border border-ochre/20 bg-ochre/10 px-4 py-3 font-serif text-xs leading-relaxed text-ochre">
            {error}
          </div>
        )}

        {isLoading && (
          <div className="rounded-xl border border-white/10 bg-[#101719]/80 px-4 py-8 text-center font-serif text-xs font-bold tracking-wide text-slate-500">
            正在生成报告...
          </div>
        )}

        {report && !isLoading && (
          <>
            <section className="rounded-2xl border border-white/10 bg-[#101719]/80 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-serif text-[11px] font-bold tracking-[0.24em] text-primary/70">
                    {report.start_date} - {report.end_date}
                  </p>
                  <h2 className="mt-1 font-serif text-xl font-bold tracking-wide text-white">
                    {period === 'weekly' ? '7 天代谢周报' : '月度代谢报告'}
                  </h2>
                </div>
                <span className="rounded-full border border-white/10 bg-white/[0.03] px-2 py-1 font-serif text-[10px] font-bold tracking-wide text-slate-400">
                  {report.summary.logged_days}/{report.summary.day_count} 天
                </span>
              </div>
              <p className="mt-2 font-serif text-[11px] tracking-wide text-slate-500">
                生成于 {formatDateTime(report.generated_at)}
              </p>

              <div className="mt-4 grid grid-cols-2 gap-3">
                <div className="rounded-xl border border-white/5 bg-white/[0.03] p-3">
                  <p className="font-serif text-[10px] font-bold tracking-[0.2em] text-slate-500">记录餐次</p>
                  <p className="mt-1 font-serif text-2xl font-bold text-white">{report.summary.meal_count}</p>
                </div>
                <div className="rounded-xl border border-white/5 bg-white/[0.03] p-3">
                  <p className="font-serif text-[10px] font-bold tracking-[0.2em] text-slate-500">日均热量</p>
                  <p className="mt-1 font-serif text-2xl font-bold text-white">{formatNumber(report.summary.averages_per_day.calories)}</p>
                </div>
              </div>
            </section>

            <section className="grid grid-cols-2 gap-3">
              {nutrientLabels.map(item => (
                <div key={item.key} className="rounded-xl border border-white/10 bg-[#131b1d]/80 p-3">
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-[18px] text-primary">{item.icon}</span>
                    <span className="font-serif text-xs font-bold tracking-wide text-slate-400">{item.label}</span>
                  </div>
                  <p className="mt-2 font-serif text-lg font-bold tracking-wide text-white">
                    {formatNumber(report.summary.totals[item.key], item.key === 'fiber' ? 1 : 0)}
                    <span className="ml-1 text-[11px] text-slate-500">{item.unit}</span>
                  </p>
                </div>
              ))}
            </section>

            {targetCards.length > 0 && (
              <section className="rounded-2xl border border-white/10 bg-[#101719]/80 p-4">
                <h3 className="font-serif text-base font-bold tracking-wide text-white">目标对照</h3>
                <div className="mt-3 grid grid-cols-3 gap-2">
                  {targetCards.map(item => (
                    <div key={item.key} className="min-w-0 rounded-xl border border-white/5 bg-white/[0.03] px-3 py-2">
                      <p className="truncate font-serif text-[10px] font-bold tracking-wide text-slate-500">{item.label}</p>
                      <p className="mt-1 font-serif text-sm font-bold tracking-wide text-white">
                        {formatNumber(item.value as number)}
                        <span className="ml-1 text-[10px] text-slate-500">{item.unit}</span>
                      </p>
                    </div>
                  ))}
                </div>
              </section>
            )}

            <section className="rounded-2xl border border-white/10 bg-[#101719]/80 p-4">
              <div className="flex items-center justify-between">
                <h3 className="font-serif text-base font-bold tracking-wide text-white">每日趋势</h3>
                <span className="font-serif text-[10px] font-bold tracking-[0.2em] text-slate-500">热量</span>
              </div>
              <div className="mt-4 flex items-end gap-2">
                {report.daily_trends.map(day => {
                  const height = Math.max(10, Math.min(72, Math.round((day.calories / maxCalories) * 72)));
                  return (
                    <div key={day.date} className="flex min-w-0 flex-1 flex-col items-center gap-2">
                      <div className="flex h-20 w-full items-end justify-center">
                        <div
                          className="w-full max-w-[18px] rounded-t-md bg-primary/70"
                          style={{ height }}
                          title={`${day.date} ${formatNumber(day.calories)} kcal`}
                        />
                      </div>
                      <span className="truncate font-serif text-[10px] font-bold tracking-wide text-slate-500">
                        {day.date.slice(5)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </section>

            {latestInsights.length > 0 && (
              <section className="rounded-2xl border border-white/10 bg-[#101719]/80 p-4">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="font-serif text-base font-bold tracking-wide text-white">周期洞察</h3>
                  <span className="rounded-full border border-white/10 bg-white/[0.03] px-2 py-1 font-serif text-[10px] font-bold tracking-wide text-slate-400">
                    {latestInsights.length}
                  </span>
                </div>
                <div className="mt-3 space-y-2">
                  {latestInsights.slice(0, 5).map((insight, index) => {
                    const title = insight.title?.trim() || '代谢洞察';
                    const content = insight.content?.trim() || '暂无洞察正文。';
                    const typeLabel = insight.type || 'insight';
                    return (
                      <article key={`${title}-${index}`} className="rounded-xl border border-white/5 bg-white/[0.03] px-3 py-3">
                        <div className="flex items-start justify-between gap-3">
                          <p className="min-w-0 break-words font-serif text-sm font-bold tracking-wide text-white">{title}</p>
                          <span className="shrink-0 rounded-full border border-primary/15 bg-primary/[0.06] px-2 py-0.5 font-serif text-[9px] font-bold tracking-wide text-primary/80">
                            {typeLabel}
                          </span>
                        </div>
                        <p className="mt-2 break-words font-serif text-xs leading-relaxed text-slate-300">{content}</p>
                        <p className="mt-2 font-serif text-[10px] leading-relaxed text-slate-500">
                          {insight.attribution || 'Prism'} · {formatDateTime(insight.created_at)}
                        </p>
                      </article>
                    );
                  })}
                </div>
              </section>
            )}

            <section className="rounded-2xl border border-white/10 bg-[#101719]/80 p-4">
              <h3 className="font-serif text-base font-bold tracking-wide text-white">风险摘要</h3>
              <div className="mt-3 space-y-2">
                {(report.summary.risk_summary.length ? report.summary.risk_summary : ['本周期暂无明显超标提示。']).map((item, index) => (
                  <div key={`${item}-${index}`} className="flex items-start gap-2 rounded-xl border border-white/5 bg-white/[0.03] px-3 py-2">
                    <span className="material-symbols-outlined mt-0.5 text-[16px] text-ochre">warning</span>
                    <p className="font-serif text-xs leading-relaxed text-slate-300">{item}</p>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-2xl border border-primary/15 bg-primary/[0.05] p-4">
              <div className="flex items-start gap-2">
                <span className="material-symbols-outlined mt-0.5 text-[18px] text-primary">verified_user</span>
                <p className="font-serif text-xs leading-relaxed tracking-wide text-slate-300">{report.medical_disclaimer}</p>
              </div>
            </section>

            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => void handleDownload('json')}
                disabled={isDownloading}
                className="flex h-11 items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] font-serif text-sm font-bold tracking-wide text-slate-200 transition-colors hover:bg-white/[0.08] disabled:opacity-50"
              >
                <span className="material-symbols-outlined text-[18px]">data_object</span>
                JSON
              </button>
              <button
                type="button"
                onClick={() => void handleDownload('csv')}
                disabled={isDownloading}
                className="flex h-11 items-center justify-center gap-2 rounded-xl bg-primary font-serif text-sm font-bold tracking-wide text-background-dark shadow-glow-cyan transition-transform active:scale-[0.99] disabled:opacity-50"
              >
                <span className={`material-symbols-outlined text-[18px] ${isDownloading ? 'animate-spin' : ''}`}>
                  {isDownloading ? 'progress_activity' : 'table_chart'}
                </span>
                CSV
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default ReportsView;
