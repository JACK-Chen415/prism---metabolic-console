import React, { useState } from 'react';
import { View } from '../../types';

interface HealthReportArchivesViewProps {
  onViewChange: (view: View) => void;
}

// Extended Data Types
interface MetricItem {
  name: string;
  value: string;
  unit: string;
  refRange: string;
  status: 'HIGH' | 'LOW' | 'NORMAL';
}

interface ReportDetail {
  metrics: MetricItem[];
  abnormalities: string[]; // Quick summary of issues
  aiAdvice: string;
  imageUrl: string;
}

interface Report {
  id: number;
  year: string;
  date: string;
  title: string;
  summary: string;
  status: 'IMPROVED' | 'FLUCTUATING' | 'STABLE';
  details: ReportDetail;
}

const HealthReportArchivesView: React.FC<HealthReportArchivesViewProps> = ({ onViewChange }) => {
  const [selectedReport, setSelectedReport] = useState<Report | null>(null);
  const [activeTab, setActiveTab] = useState<'ANALYSIS' | 'ORIGINAL'>('ANALYSIS');

  // Enhanced Mock Data
  const reports: Report[] = [
    {
      id: 1,
      year: '2023',
      date: '10.24',
      title: '年度综合体检',
      summary: '尿酸控制显著改善，痛风风险降低。血脂略有波动，建议保持关注。',
      status: 'IMPROVED',
      details: {
        imageUrl: '/images/log-header.png', // Placeholder (reusing log header for demo)
        abnormalities: ['甘油三酯偏高', '体重指数超标'],
        aiAdvice: '相较于半年前，您的尿酸水平已回归正常区间，这归功于良好的饮食控制。但甘油三酯略有上升，建议减少精制碳水摄入，增加每周2次有氧运动。',
        metrics: [
          { name: '血尿酸', value: '342', unit: 'μmol/L', refRange: '208-428', status: 'NORMAL' },
          { name: '甘油三酯', value: '1.85', unit: 'mmol/L', refRange: '< 1.7', status: 'HIGH' },
          { name: '总胆固醇', value: '4.8', unit: 'mmol/L', refRange: '< 5.18', status: 'NORMAL' },
          { name: '空腹血糖', value: '5.4', unit: 'mmol/L', refRange: '3.9-6.1', status: 'NORMAL' },
          { name: 'BMI', value: '24.8', unit: '', refRange: '18.5-23.9', status: 'HIGH' },
        ]
      }
    },
    {
      id: 2,
      year: '2023',
      date: '05.12',
      title: '肾功能专项复查',
      summary: '尿酸水平偏高（480 μmol/L），超出正常范围，建议加强低嘌呤饮食干预。',
      status: 'FLUCTUATING',
      details: {
        imageUrl: '',
        abnormalities: ['血尿酸过高'],
        aiAdvice: '此次复查显示尿酸出现反弹，可能与近期海鲜摄入有关。请严格执行低嘌呤饮食，并每日饮水2000ml以上促进排泄。',
        metrics: [
          { name: '血尿酸', value: '480', unit: 'μmol/L', refRange: '208-428', status: 'HIGH' },
          { name: '肌酐', value: '85', unit: 'μmol/L', refRange: '57-97', status: 'NORMAL' },
          { name: '尿素氮', value: '5.2', unit: 'mmol/L', refRange: '2.9-8.2', status: 'NORMAL' },
        ]
      }
    },
    {
      id: 3,
      year: '2022',
      date: '11.08',
      title: '入职体检',
      summary: '各项基础指标基本正常，心电图显示窦性心律。',
      status: 'STABLE',
      details: {
        imageUrl: '',
        abnormalities: [],
        aiAdvice: '身体各项机能处于良好状态，建议保持当前的作息与饮食习惯。',
        metrics: [
          { name: '血尿酸', value: '380', unit: 'μmol/L', refRange: '208-428', status: 'NORMAL' },
          { name: '谷丙转氨酶', value: '25', unit: 'U/L', refRange: '0-40', status: 'NORMAL' },
          { name: '血压', value: '120/80', unit: 'mmHg', refRange: '90-140/60-90', status: 'NORMAL' },
        ]
      }
    }
  ];

  const getStatusStyle = (status: string) => {
    switch(status) {
      case 'IMPROVED':
        return { bg: 'bg-[#10b981]', text: '改善', color: 'text-[#10b981]' };
      case 'FLUCTUATING':
        return { bg: 'bg-ochre', text: '波动', color: 'text-ochre' };
      case 'STABLE':
        return { bg: 'bg-slate-400', text: '平稳', color: 'text-slate-400' };
      case 'HIGH':
        return { color: 'text-ochre', icon: 'arrow_upward' };
      case 'LOW':
        return { color: 'text-ochre', icon: 'arrow_downward' };
      case 'NORMAL':
        return { color: 'text-[#45b7aa]', icon: 'check' };
      default:
        return { bg: 'bg-slate-400', text: '未知', color: 'text-slate-400', icon: 'remove' };
    }
  };

  const handleAiInterpretation = () => {
    // Generate context string
    const context = reports.map(r => 
      `【${r.year}.${r.date} ${r.title}】\n` +
      `状态: ${r.status === 'IMPROVED' ? '改善' : r.status === 'FLUCTUATING' ? '波动' : '平稳'}\n` +
      `摘要: ${r.summary}\n` +
      (r.details.abnormalities.length ? `异常项: ${r.details.abnormalities.join('、')}\n` : '') +
      `关键指标: ${r.details.metrics.map(m => `${m.name} ${m.value}${m.unit}`).join(' | ')}`
    ).join('\n-------------------\n');

    const message = `生成体检报告深度分析。\n\n以下是我的历史体检档案数据：\n\n${context}\n\n请分析我的健康趋势，特别是尿酸和代谢相关指标的变化，并给出后续建议。`;

    sessionStorage.setItem('PRISM_AUTO_SEND_MESSAGE', message);
    onViewChange(View.CHAT);
  };

  // --- Sub-View: Report Details ---
  if (selectedReport) {
    return (
      <div className="flex flex-col w-full h-full bg-[#080c0d] animate-fade-in">
        {/* Detail Header */}
        <div className="sticky top-0 z-20 bg-[#080c0d]/95 backdrop-blur-md border-b border-white/5">
          <div className="flex items-center gap-4 p-4">
              <button 
                  onClick={() => setSelectedReport(null)}
                  className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/5 transition-colors -ml-2"
              >
                  <span className="material-symbols-outlined text-white/80">arrow_back</span>
              </button>
              <div className="flex flex-col">
                  <h1 className="text-white text-lg font-bold font-serif">{selectedReport.title}</h1>
                  <p className="text-xs text-slate-500 font-display">{selectedReport.year}.{selectedReport.date}</p>
              </div>
          </div>
          
          {/* Tabs */}
          <div className="flex px-4 border-b border-white/5">
            <button 
                onClick={() => setActiveTab('ANALYSIS')}
                className={`flex-1 py-3 text-sm font-medium transition-all relative ${activeTab === 'ANALYSIS' ? 'text-[#45b7aa]' : 'text-slate-400'}`}
            >
                智能分析
                {activeTab === 'ANALYSIS' && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-[#45b7aa]"></div>}
            </button>
            <button 
                onClick={() => setActiveTab('ORIGINAL')}
                className={`flex-1 py-3 text-sm font-medium transition-all relative ${activeTab === 'ORIGINAL' ? 'text-[#45b7aa]' : 'text-slate-400'}`}
            >
                原始报告
                {activeTab === 'ORIGINAL' && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-[#45b7aa]"></div>}
            </button>
          </div>
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto p-4 pb-20">
          
          {activeTab === 'ANALYSIS' ? (
            <div className="space-y-6">
                {/* 1. Summary Card */}
                <div className="bg-[#162624] border border-[#45b7aa]/20 rounded-xl p-5 shadow-lg relative overflow-hidden">
                    <div className="absolute top-0 right-0 p-3 opacity-10">
                        <span className="material-symbols-outlined text-6xl text-[#45b7aa]">psychology</span>
                    </div>
                    <h3 className="text-[#45b7aa] font-bold font-serif text-sm mb-2 flex items-center gap-2">
                        <span className="material-symbols-outlined text-base">auto_awesome</span>
                        AI 综合解读
                    </h3>
                    <p className="text-white/90 text-sm leading-relaxed text-justify font-sans">
                        {selectedReport.details.aiAdvice}
                    </p>
                    
                    {/* Abnormal Tags */}
                    {selectedReport.details.abnormalities.length > 0 && (
                        <div className="flex flex-wrap gap-2 mt-4 pt-3 border-t border-white/5">
                            {selectedReport.details.abnormalities.map((tag, idx) => (
                                <span key={idx} className="px-2 py-1 rounded bg-ochre/10 text-ochre text-xs font-bold border border-ochre/20">
                                    ! {tag}
                                </span>
                            ))}
                        </div>
                    )}
                </div>

                {/* 2. Metrics Table */}
                <div className="space-y-3">
                    <h3 className="text-white font-serif text-base font-bold pl-1 border-l-2 border-white/20">关键指标详情</h3>
                    <div className="bg-[#131b1d] border border-white/5 rounded-xl overflow-hidden">
                        <table className="w-full text-left text-sm">
                            <thead className="bg-white/5 text-slate-400 font-medium">
                                <tr>
                                    <th className="px-4 py-3 font-normal">项目</th>
                                    <th className="px-4 py-3 font-normal text-right">结果</th>
                                    <th className="px-4 py-3 font-normal text-right">参考值</th>
                                    <th className="px-4 py-3 font-normal text-center w-12">状态</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-white/5">
                                {selectedReport.details.metrics.map((metric, idx) => {
                                    const style = getStatusStyle(metric.status);
                                    return (
                                        <tr key={idx} className="hover:bg-white/5 transition-colors">
                                            <td className="px-4 py-3 text-white font-medium">{metric.name}</td>
                                            <td className={`px-4 py-3 text-right font-display font-bold ${metric.status !== 'NORMAL' ? 'text-ochre' : 'text-white'}`}>
                                                {metric.value} <span className="text-[10px] text-slate-500 font-normal">{metric.unit}</span>
                                            </td>
                                            <td className="px-4 py-3 text-right text-slate-500 text-xs font-display">{metric.refRange}</td>
                                            <td className="px-4 py-3 text-center">
                                                <span className={`material-symbols-outlined text-base ${style.color}`}>
                                                    {style.icon}
                                                </span>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full min-h-[50vh] gap-4">
                {selectedReport.details.imageUrl ? (
                     <div className="w-full rounded-xl overflow-hidden border border-white/10 shadow-lg relative group">
                        <img src={selectedReport.details.imageUrl} alt="Original Report" className="w-full h-auto object-cover" />
                        <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                            <button className="px-4 py-2 bg-white/20 backdrop-blur rounded-full text-white font-bold flex items-center gap-2 hover:bg-white/30">
                                <span className="material-symbols-outlined">zoom_in</span> 查看大图
                            </button>
                        </div>
                     </div>
                ) : (
                    <div className="flex flex-col items-center text-slate-500">
                         <span className="material-symbols-outlined text-4xl mb-2 opacity-50">image_not_supported</span>
                         <p className="text-sm">暂无原始图片存档</p>
                    </div>
                )}
            </div>
          )}
        </div>
      </div>
    );
  }

  // --- Main View: Archive List ---
  return (
    <div className="flex flex-col w-full h-full bg-[#080c0d] relative animate-fade-in">
      {/* 1. Header Area */}
      <div className="sticky top-0 z-20 bg-[#080c0d]/95 backdrop-blur-md border-b border-white/5 pb-2">
        {/* Nav Bar */}
        <div className="flex items-center gap-4 p-4">
            <button 
                onClick={() => onViewChange(View.PROFILE)}
                className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/5 transition-colors -ml-2"
            >
                <span className="material-symbols-outlined text-white/80">arrow_back</span>
            </button>
            <h1 className="text-white text-xl font-bold font-serif tracking-widest">体检档案</h1>
        </div>
        
        {/* Key Metrics Ticker */}
        <div className="px-4 overflow-hidden">
            <div className="bg-[#131b1d] rounded-lg p-2.5 flex items-center gap-3 border border-white/5 shadow-inner">
                <span className="material-symbols-outlined text-[#45b7aa] text-lg shrink-0">analytics</span>
                <div className="flex-1 overflow-hidden whitespace-nowrap">
                    <p className="text-xs text-slate-300 font-display animate-marquee inline-block">
                        最新数据 (2023.10.24) &nbsp;|&nbsp; 
                        <span className="text-[#10b981]">尿酸 342 (正常)</span> &nbsp;|&nbsp; 
                        <span className="text-[#10b981]">血压 118/78 (正常)</span> &nbsp;|&nbsp; 
                        <span className="text-ochre">体重 72.5kg (微胖)</span>
                    </p>
                </div>
            </div>
        </div>
      </div>

      {/* 2. Timeline List */}
      <div className="flex-1 overflow-y-auto p-6 pb-24 relative">
        {/* Timeline Line */}
        <div className="absolute left-[86px] top-6 bottom-0 w-px bg-white/10"></div>

        <div className="flex flex-col gap-8">
            {reports.map((report) => {
                const statusStyle = getStatusStyle(report.status);
                
                return (
                    <div key={report.id} className="relative flex gap-6">
                        {/* Left: Date */}
                        <div className="w-14 shrink-0 flex flex-col items-end pt-1">
                            <span className="text-white font-display font-bold text-lg leading-none">{report.year}</span>
                            <span className="text-slate-500 font-display text-xs mt-0.5">{report.date}</span>
                        </div>

                        {/* Node Dot */}
                        <div className="absolute left-[59px] top-2.5 w-2.5 h-2.5 rounded-full bg-[#080c0d] border-2 border-[#45b7aa] z-10 shadow-[0_0_0_4px_rgba(8,12,13,1)]"></div>

                        {/* Right: Card */}
                        <div 
                            onClick={() => setSelectedReport(report)}
                            className="flex-1 bg-[#162624] border border-white/5 rounded-xl p-4 shadow-lg hover:border-[#45b7aa]/30 transition-colors active:scale-[0.99] cursor-pointer group"
                        >
                            <div className="flex justify-between items-start mb-2">
                                <h3 className="text-white font-bold font-serif text-base group-hover:text-[#45b7aa] transition-colors">{report.title}</h3>
                                <div className={`px-2 py-0.5 rounded text-[10px] font-bold ${statusStyle.color} bg-white/5 border border-white/5`}>
                                    {statusStyle.text}
                                </div>
                            </div>
                            
                            <p className="text-slate-400 text-xs leading-relaxed text-justify mb-3 line-clamp-2">
                                {report.summary}
                            </p>

                            <div className="flex items-center gap-2 pt-2 border-t border-white/5">
                                <span className="material-symbols-outlined text-white/20 text-sm group-hover:text-[#45b7aa] transition-colors">visibility</span>
                                <span className="text-[10px] text-white/30 group-hover:text-[#45b7aa] transition-colors">查看详情</span>
                            </div>
                        </div>
                    </div>
                );
            })}
        </div>
      </div>

      {/* 3. FAB: AI Interpretation */}
      <button 
        onClick={handleAiInterpretation}
        className="fixed bottom-8 right-6 z-30 flex items-center gap-2 pl-4 pr-5 py-3 rounded-full bg-[#45b7aa] text-[#080c0d] font-bold shadow-[0_0_20px_rgba(69,183,170,0.4)] hover:shadow-[0_0_30px_rgba(69,183,170,0.6)] active:scale-95 transition-all"
      >
        <span className="material-symbols-outlined text-xl">document_scanner</span>
        <span className="text-sm font-serif">AI 解读</span>
      </button>

      {/* Inline Styles for Marquee */}
      <style>{`
        @keyframes marquee {
          0% { transform: translateX(100%); }
          100% { transform: translateX(-100%); }
        }
        .animate-marquee {
          animation: marquee 15s linear infinite;
        }
        @keyframes fade-in {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .animate-fade-in {
            animation: fade-in 0.3s ease-out forwards;
        }
      `}</style>
    </div>
  );
};

export default HealthReportArchivesView;